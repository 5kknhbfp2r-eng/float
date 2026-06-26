"""EDGAR-only replacement for the sec-api Query/FTS layer.

The sec-api subscription lapsed, so the filing-DISCOVERY layer is reimplemented on FREE
SEC endpoints, returning the SAME filing dicts float_gather expects
(formType / filedAt / accessionNo / linkToFilingDetails):

  - https://data.sec.gov/submissions/CIK##########.json   per-CIK filing index
    (recent + overflow shards) -> replaces every `cik:.. AND formType:(..)` Query call.
  - https://efts.sec.gov/LATEST/search-index               full-text search ->
    replaces the sec-api FTS fallback that resolved delisted/renamed/foreign tickers.

Document TEXT is still fetched by float_from_filings.fetch_text from www.sec.gov (already
free, unchanged). Accession numbers are dashed (e.g. 0000950170-25-067982), identical to
sec-api's, so fetch_text's cache (keyed by accession) hits the SAME cached text -> the
dossier is byte-identical to the sec-api era for any already-cached filing.

Point-in-time is preserved: query() filters filingDate <= asof exactly like the sec-api
`filedAt:[.. TO asofT23:59:59]` cap.
"""
import os, re, json, time
import requests
import float_from_filings as ff

UA = ff.UA                                   # {"User-Agent": "research <email>"}
SUB_CACHE = os.path.join(ff.DATA, "_cache", "edgar_submissions")
_MEM = {}                                    # cik(int) -> assembled filing list


def _get(url, tries=4):
    """GET with EDGAR-polite retry/backoff (10 req/s limit; UA required)."""
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 403, 503):
                time.sleep(1.5 * (i + 1)); continue
            return None
        except requests.RequestException:
            time.sleep(1.0 * (i + 1))
    return None


def _rows_from(rec, cik):
    forms = rec.get("form", [])
    adt = rec.get("acceptanceDateTime", [None] * len(forms))
    out = []
    for i in range(len(forms)):
        acc = rec["accessionNumber"][i]
        pdoc = rec["primaryDocument"][i] or ""
        accnd = acc.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accnd}"
        link = f"{base}/{pdoc}" if pdoc else f"{base}/{acc}.txt"
        out.append({
            "formType": forms[i],
            "filedAt": adt[i] or (rec["filingDate"][i] + "T00:00:00"),
            "filingDate": rec["filingDate"][i],
            "accessionNo": acc,
            "linkToFilingDetails": link,
        })
    return out


def _assemble(cik):
    """Full filing list for a CIK (recent + overflow shards). Cached on disk + in memory
    so the many query() calls in one gather() — and re-spawned agents — reuse one fetch."""
    if not cik:
        return []
    cik = int(cik)
    if cik in _MEM:
        return _MEM[cik]
    os.makedirs(SUB_CACHE, exist_ok=True)
    cpath = os.path.join(SUB_CACHE, f"{cik}.json")
    if os.path.exists(cpath):
        out = json.load(open(cpath)); _MEM[cik] = out; return out
    r = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not r:
        _MEM[cik] = []; return []
    d = r.json()
    rows = _rows_from(d.get("filings", {}).get("recent", {}), cik)
    for shard in d.get("filings", {}).get("files", []):     # >1000 filings -> older shards
        rs = _get(f"https://data.sec.gov/submissions/{shard['name']}")
        if rs:
            rows += _rows_from(rs.json(), cik)
    json.dump(rows, open(cpath, "w"))
    _MEM[cik] = rows
    return rows


def query(cik, forms, asof, size=6, order="desc"):
    """sec-api-shaped Query replacement: filings whose form is in `forms` and
    filingDate <= asof, newest-first (order='desc') or oldest-first ('asc')."""
    if not cik:
        return []
    rows = [f for f in _assemble(cik)
            if f["formType"] in forms and f["filingDate"] <= asof]
    # Order on the SAME axis as the point-in-time filter (filingDate, ET business day), tie-broken by
    # the acceptance instant — so the sort can't invert vs the filter on rare late re-acceptances (F38).
    rows.sort(key=lambda f: (f["filingDate"], f["filedAt"]), reverse=(order == "desc"))
    return rows[:int(size)]


def all_filings(cik, asof, limit=40):
    """Every filing (any form) <= asof, newest-first — for list_filings()."""
    rows = [f for f in _assemble(cik) if f["filingDate"] <= asof]
    rows.sort(key=lambda f: (f["filingDate"], f["filedAt"]), reverse=True)
    return rows[:int(limit)]


def by_accession(cik, accession):
    """The filing with this accession (dashed or not) — for fetch_one()."""
    a = accession.replace("-", "")
    for f in _assemble(cik):
        if f["accessionNo"].replace("-", "") == a:
            return f
    return None


def resolve_cik_edgar(ticker, asof="2026-06-04"):
    """FTS fallback for tickers absent from company_tickers.json (delisted/renamed/foreign):
    find a filing whose own display_names contains '(TICKER)' and take that filer's CIK.
    The display_names filter rejects unrelated docs that merely mention the ticker string."""
    r = _get(f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
             f"&startdt=2022-01-01&enddt={asof}")
    if not r:
        return None
    try:
        hits = r.json().get("hits", {}).get("hits", [])
    except Exception:
        return None
    pat = re.compile(rf"\(\s*{re.escape(ticker)}\s*[\),]", re.I)
    # EFTS orders hits by relevance _score, NOT by date. For a REUSED ticker the newer/more-active
    # entity often scores highest while still having filings inside the enddt<=asof window, so taking
    # the first hit returns the wrong entity (F02). Pick the matched CIK from the LATEST-dated hit
    # (file_date <= asof) — the entity actually using the ticker at as_of.
    best = None                                  # (file_date, cik)
    for h in hits:
        src = h.get("_source", {})
        names, ciks = src.get("display_names", []), src.get("ciks", [])
        fd = src.get("file_date") or ""
        for j, nm in enumerate(names):
            if pat.search(nm):
                m = re.search(r"CIK\s*0*(\d+)", nm)
                if m:
                    cik = int(m.group(1))
                elif ciks:
                    cik = int(str(ciks[min(j, len(ciks) - 1)]).lstrip("0") or 0) or None
                else:
                    cik = None
                if cik and (best is None or fd > best[0]):
                    best = (fd, cik)
                break
    return best[1] if best else None
