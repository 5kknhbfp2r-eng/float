#!/usr/bin/env python3
"""STEP 1 of the per-name float engine: point-in-time filing GATHERER.

Given (ticker, as_of_date), pull every filing relevant to float that was filed ON OR
BEFORE as_of_date (no lookahead — critical for backtests) and emit ONE readable
"dossier": the ownership table + footnotes, all candidate O/S figures, IPO-offering /
SPAC-redeemable / PIPE signals, and recent 8-K/6-K events. A Claude session reads the
dossier and produces a decision JSON (see FLOAT_PROTOCOL.md); float_score.py computes +
scores it.

sec-api ONLY. Every query is capped at filedAt <= as_of_date.
Usage: python float_gather.py TICKER [AS_OF_DATE]   (default as_of 2026-06-04)
"""
import sys, re, json, requests
import os
import _cik_probe as cm, _formula_probe as fp, _widen_probe as wp, float_from_filings as ff
import edgar                                  # EDGAR-only discovery layer (sec-api retired)

# Persisted intermediate data (reused for any future ticker/day touching the same filing):
SCAN_CACHE = os.path.join(ff.DATA, "_cache", "scans")        # per-accession parse results
DOSS_CACHE = os.path.join(ff.DATA, "_cache", "dossiers")     # assembled per-(ticker,as_of) dossiers
MANI_CACHE = os.path.join(ff.DATA, "_cache", "manifests")    # per-(ticker,as_of) filing-dependency manifest
_USED = []                                                   # filings touched in the current gather()

OWN_FORMS = ["DEF 14A", "DEFM14A", "PRE 14A", "20-F", "20-F/A", "10-K", "40-F"]
PROXY_FORMS = ["DEF 14A", "DEFM14A", "PRE 14A", "20-F", "20-F/A"]   # have the ownership table
FALLBACK_FORMS = ["10-K", "40-F"]                                  # table often absent -> last resort
IPO_FORMS = ["424B4", "424B1", "424B3", "F-1", "F-1/A", "S-1", "S-1/A"]
EVENT_FORMS = ["8-K", "6-K"]
ADS_RE = re.compile(r"(?i)each\s+ADS\s+represent[s]?\s+([\d.]+|\w+)\s+(?:ordinary|common)|"
                    r"American Depositary Share[s]?[^.]{0,40}?represent[s]?\s+([\d.]+|\w+)\s+ordinary|"
                    r"based on\s+([\d,]{7,})\s+(?:ordinary|common)\s+shares")


def _query(cik, forms, asof, size=6, order="desc"):
    # EDGAR-only: per-CIK submissions index, form-filtered, filingDate <= asof (point-in-time).
    return edgar.query(cik, forms, asof, size=size, order=order)


def _text(f):
    _USED.append({"accession": f.get("accessionNo"), "form": f.get("formType"),
                  "filedAt": (f.get("filedAt") or "")[:10]})   # track float's filing dependencies
    return ff.fetch_text(f["linkToFilingDetails"], f["accessionNo"]).translate(wp.ZW)


def _os_candidates(text):
    """All 'N shares ... outstanding' figures (cover-page O/S, by class)."""
    out = []
    for m in re.finditer(r"([\d,]{6,})\s+(?:shares|ordinary shares|Class [A-Z][^.]{0,30})"
                         r"[^.]{0,70}?outstanding", text[:200000]):
        out.append(" ".join(m.group(0).split())[:110])
    return out[:6]


def _own_window(text):
    gm = wp.GROUP2.search(text) or wp.table_anchor(text)
    if not gm:
        return None
    a, b = max(0, gm.start() - 1700), min(len(text), gm.end() + 2700)
    fz = " ".join(text[gm.end():gm.end() + 1800].split())
    return " ".join(text[a:b].split())[:4400], fz[:1800]


def _signals(text):
    s = {}
    rs = [" ".join(m.group(0).split())[:90] for m in re.finditer(
        r"(?i)([\d,]{6,})\s+(?:ordinary |class a |)shares?[^.]{0,40}"
        r"(?:subject to possible redemption|redeemable)", text)][:3]
    if rs:
        s["REDEEMABLE (SPAC)"] = rs
    off = [" ".join(m.group(0).split())[:90] for m in re.finditer(
        r"(?i)(?:initial public offering of|offering of|are offering)\s+([\d,]{5,})\s+"
        r"(?:ordinary|common|class a|ADS)", text)][:3]
    if off:
        s["OFFERING (IPO)"] = off
    pipe = [" ".join(m.group(0).split())[:90] for m in re.finditer(
        r"(?i)(?:aggregate of|issue|sell|sold)\s+(?:up to\s+)?([\d,]{6,})\s+"
        r"(?:units|ordinary shares|common shares|shares|ADS)", text)][:3]
    if pipe:
        s["PIPE/ISSUANCE"] = pipe
    return s


PERIODIC = ["10-Q", "10-K", "20-F", "20-F/A", "6-K", "40-F"]
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20,
            "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90, "hundred": 100}
SPLIT_RE = re.compile(r"(?i)((?:one|1|\d+)[\s-]?(?:for|to|:)[\s-]?(?:one|\d+)|"
                      r"(?:two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|"
                      r"forty|fifty|sixty)[\s-]?(?:for|to)[\s-]?one)[\s-]*"
                      r"(?:reverse |forward |)(?:stock |share |)(?:split|consolidation|subdivision)")
ADS_RATIO_RE = re.compile(r"(?i)(?:each|one)\s+ADS[^.]{0,12}?represent[s]?\s+([\w.]+)\s+"
                          r"(?:Class\s+[A-Z]\s+)?(?:ordinary|common)|"
                          r"ratio of\s+([\w.]+)\s+(?:Class\s+[A-Z]\s+)?(?:ordinary|common)\s+shares?\s+to\s+(?:one|1)\s+ADS")


def _num(s):
    s = s.replace(",", "").lower()
    if s.replace(".", "").isdigit():
        return float(s)
    return _WORDNUM.get(s)


def _ads_ratio(text):
    """Ordinary shares per ADS, as a number (HLG 16, JFIN 4, AZI 10, KRKR 500). None if not stated."""
    m = ADS_RATIO_RE.search(text)
    if m:
        return _num(m.group(1) or m.group(2) or "")
    return None


def _current_os(cik, asof):
    """The authoritative CURRENT O/S: O/S candidates from the LATEST periodic (10-Q/10-K/20-F/
    6-K) <= asof. This is the count that reflects every split + post-proxy offering."""
    f = (_query(cik, PERIODIC, asof, size=1) or [None])[0]
    if not f:
        return None
    return f["formType"], f["filedAt"][:10], _os_candidates(_text(f))


def _reconcile_block(cik, asof, own_text, own_filed):
    """⚠ The noisy-name checklist, surfaced prominently so splits/ADS/dilution can't be missed."""
    out = ["\n## ⚠ RECONCILIATION (noisy-name checklist — resolve ALL before trusting O/S)"]
    cur = _current_os(cik, asof)
    if cur:
        out.append(f"CURRENT O/S — latest periodic {cur[0]} {cur[1]} (use THIS, post all splits/offerings):")
        out += ["   " + c for c in cur[2]] or ["   (none parsed — read its cover)"]
    sp = sorted({" ".join(m.group(0).split()) for m in SPLIT_RE.finditer(own_text)})
    if sp:
        out.append("SPLIT/CONSOLIDATION detected (current O/S already reflects it; don't double-apply): "
                   + " | ".join(sp[:4]))
    r = _ads_ratio(own_text)
    if r:
        out.append(f"ADS RATIO = {r:g} ordinary per ADS → DT counts in ADS; ADS O/S = ordinary_O/S / {r:g}. "
                   f"Convert EVERY ordinary holder block by /{r:g} before subtracting.")
    elif re.search(r"(?i)American Depositary Share", own_text):
        out.append("ADS-listed but ratio not auto-found — search 'each ADS represents N ordinary' "
                   "and divide ordinary counts by it (DT's O/S is in ADS).")
    # dilution filed AFTER the ownership filing (offerings/PIPEs that grew O/S since)
    later = [f for f in _query(cik, EVENT_FORMS + IPO_FORMS + ["F-3", "F-3/A", "S-3", "S-3/A"], asof, size=10)
             if f["filedAt"][:10] > own_filed]
    dils = []
    for f in later[:6]:
        s = _signals(_text(f))
        if "OFFERING (IPO)" in s or "PIPE/ISSUANCE" in s:
            dils.append(f"   {f['formType']} {f['filedAt'][:10]}: "
                        + " | ".join((s.get("OFFERING (IPO)", []) + s.get("PIPE/ISSUANCE", []))[:2]))
    if dils:
        out.append("DILUTION since the ownership filing (O/S grew — use the current O/S above, not the table's):")
        out += dils
    return out if len(out) > 1 else []


def _pick_own(cik, asof):
    """Prefer a proxy/20-F that actually has an ownership table; fall back to 10-K/40-F."""
    for f in _query(cik, PROXY_FORMS, asof, size=4):
        if _own_window(_text(f)):
            return f
    px = _query(cik, PROXY_FORMS, asof, size=1)
    fb = _query(cik, FALLBACK_FORMS, asof, size=1)
    return (px or fb or [None])[0]


def _ads_note(t):
    m = ADS_RE.search(t)
    if m:
        return "ADS/RESCALE signal: " + " ".join((m.group(0)).split())[:90]
    return None


import re as _re
_RESOLVE_CACHE = {}

# Known ticker-REUSE fixes: company_tickers.json maps to the CURRENT holder, which can be the
# wrong entity for a past as_of. (MTAL now -> unfiled 2026 "Metals Acquisition Corp. II"; in
# 2025 MTAL = Metals Acquisition Ltd / MAC Copper, CIK 1950246.) The point-in-time guard below
# catches these generally; this map is an explicit shortcut for ones we've confirmed.
CIK_OVERRIDES = {"MTAL": 1950246}


def resolve_cik(ticker, asof="2026-06-04"):
    """Robust, POINT-IN-TIME ticker->CIK. Static map first (override / cik_of / ALIAS); if the
    statically-mapped CIK has NO filing on/before as_of (the ticker-reuse signature — the ticker
    now belongs to a different/unfiled entity), fall back to EDGAR full-text-search for the filer
    that actually used the ticker at that date. Chain:
      1. cm.cik_of / fp.resolve_cik_relaxed / fp.ALIAS
      2. sec-api full-text search for the listing symbol — a filing names itself "Co. (TICKER)"
         (this is how IMG resolved -> 'CIMG Inc. (IMG)' CIK 1527613; DT ticker != SEC ticker).
      3. sec-api mapping API (fuzzy) as a last hint.
    Returns an int CIK or None. Caches results."""
    key = (ticker, asof)
    if key in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[key]
    # static/free legs first (override, company_tickers.json/stale parquet/cached map, alias);
    # resolve_cik_relaxed dropped (it hit the retired sec-api mapping endpoint).
    cik = CIK_OVERRIDES.get(ticker) or cm.cik_of(ticker) or fp.ALIAS.get(ticker)
    if not (cik and str(cik).strip().isdigit()):       # guard cached junk like the string "None"
        cik = None
    # POINT-IN-TIME guard: a mapped CIK with no filing <= asof is the wrong entity for this date
    # (ticker reuse). Re-resolve via EFTS, scoped to enddt=asof so only the then-filer matches.
    if cik and not edgar.all_filings(cik, asof, 1):
        alt = edgar.resolve_cik_edgar(ticker, asof)
        if alt:
            cik = alt
    if not cik:                                         # EDGAR full-text-search fallback for
        cik = edgar.resolve_cik_edgar(ticker, asof)     # delisted/renamed/foreign tickers
    if cik:
        _RESOLVE_CACHE[key] = int(cik)
    return int(cik) if cik else None


def list_filings(ticker, asof="2026-06-04", limit=40):
    """The cheap FILING INDEX (metadata only — types/dates/accession), filedAt <= asof.
    The Claude session browses this to decide which filings it still needs, then calls
    fetch_one() for each. This is 'pull what you need' WITHOUT dumping full texts (which
    would blow the context window). Point-in-time enforced by the asof cap."""
    cik = resolve_cik(ticker, asof)
    if not cik:
        return "NO CIK"
    fs = edgar.all_filings(cik, asof, limit)            # EDGAR submissions index, <= asof
    out = [f"FILING INDEX {ticker} (CIK {cik}), <= {asof}, newest first:"]
    for f in fs:
        out.append(f"  {f['filedAt'][:10]}  {f['formType']:10s}  acc={f['accessionNo']}  {f.get('linkToFilingDetails','')}")
    return "\n".join(out)


def fetch_one(ticker, accession, what="ownership", asof="2026-06-04"):
    """On-demand: fetch ONE filing (by accession from list_filings) and return a focused
    view. what='ownership' -> the ownership window; 'os' -> O/S candidates; 'cover' -> first
    8k chars (cover page); 'full' -> whole text (use sparingly)."""
    cik = resolve_cik(ticker, asof)
    f0 = edgar.by_accession(cik, accession)             # EDGAR: find the filing in the index
    if not f0:
        return "accession not found"
    t = _text(f0)
    if what == "os":
        return "O/S candidates:\n" + "\n".join("  " + c for c in _os_candidates(t)) + ("\n" + (_ads_note(t) or ""))
    if what == "cover":
        return " ".join(t[:8000].split())
    if what == "full":
        return " ".join(t.split())
    w = _own_window(t)
    return ("-- OWNERSHIP TABLE --\n" + w[0] + "\n-- FOOTNOTES --\n" + w[1]) if w else "(no ownership table in this filing)"


def _scan(f):
    """Parse + PERSIST every float-relevant field from ONE filing, keyed by accession, so any
    future ticker/day that touches the same filing reuses the scan (and it's auditable). Pure
    side-effect cache — does not alter the dossier text. Cheap (regex over already-cached text)."""
    try:
        acc = f["accessionNo"].replace("/", "-")
        p = os.path.join(SCAN_CACHE, f"{acc}.json")
        if os.path.exists(p):
            return
        t = _text(f)
        w = _own_window(t)
        rec = {"accession": f["accessionNo"], "formType": f["formType"],
               "filedAt": f["filedAt"][:10], "link": f.get("linkToFilingDetails"),
               "os_candidates": _os_candidates(t),
               "ownership_table": (w[0] if w else None),
               "footnotes": (w[1] if w else None),
               "signals": _signals(t), "ads_ratio": _ads_ratio(t),
               "splits": sorted({" ".join(m.group(0).split()) for m in SPLIT_RE.finditer(t)}),
               "ads_note": _ads_note(t), "scanned_chars": len(t)}
        os.makedirs(SCAN_CACHE, exist_ok=True)
        json.dump(rec, open(p, "w"))
    except Exception:
        pass                                   # caching must never break a dossier


def _save_dossier(ticker, asof, text):
    try:
        os.makedirs(DOSS_CACHE, exist_ok=True)
        open(os.path.join(DOSS_CACHE, f"{ticker}_{asof}.txt"), "w", encoding="utf-8").write(text)
    except Exception:
        pass


def _save_manifest(ticker, asof, cik):
    """Persist the filing-dependency manifest for this (ticker, as_of): the distinct filings the
    dossier touched (accession/form/date). A future date for the same ticker reads this to check
    whether any NEWER filing supersedes them — enabling cheap delta-updates."""
    try:
        os.makedirs(MANI_CACHE, exist_ok=True)
        seen = {}
        for u in _USED:
            if u["accession"] and u["accession"] not in seen:
                seen[u["accession"]] = u
        filings = sorted(seen.values(), key=lambda x: x["filedAt"], reverse=True)
        json.dump({"ticker": ticker, "as_of": asof, "cik": cik, "filings": filings},
                  open(os.path.join(MANI_CACHE, f"{ticker}_{asof}.json"), "w"), indent=1)
    except Exception:
        pass


def gather(ticker, asof="2026-06-04"):
    import datetime as dt
    _USED.clear()                                         # reset filing-dependency tracking
    cik = resolve_cik(ticker, asof)
    out = [f"===== FLOAT DOSSIER  {ticker}  (as_of {asof}, no filing after this date) ====="]
    if not cik:
        return "\n".join(out + ["NO CIK — resolve manually"])
    out.append(f"CIK {cik}")

    f = _pick_own(cik, asof)
    if not f:
        out.append("NO ownership filing <= as_of")
    else:
        filed = f["filedAt"][:10]
        age = (dt.date.fromisoformat(asof) - dt.date.fromisoformat(filed)).days
        stale = "  ⚠ STALE (>400d old — verify O/S via a later 8-K/10-Q)" if age > 400 else ""
        out.append(f"\n## OWNERSHIP FILING: {f['formType']} filed {filed} ({age}d before as_of){stale}")
        t = _text(f)
        _scan(f)                              # persist this filing's parse for reuse
        out.append("O/S candidates (cover-page, by class — cross-check; pick the as_of basis):")
        out += ["   " + c for c in _os_candidates(t)]
        ads = _ads_note(t)
        if ads:
            out.append(ads)
        out += _reconcile_block(cik, asof, t, filed)
        w = _own_window(t)
        if w:
            out.append("\n-- OWNERSHIP TABLE --\n" + w[0])
            out.append("\n-- FOOTNOTES --\n" + w[1])
            # second ownership header further in the doc = a separate major/principal-shareholders
            # table (catches a control block NOT in the D&O table -- e.g. hidden pre-IPO holders)
            hdrs = list(wp.OWN_HDR.finditer(t))
            g0 = (wp.GROUP2.search(t) or wp.table_anchor(t))
            for h in hdrs:
                if g0 and abs(h.start() - g0.start()) > 6000:
                    out.append("\n-- ALSO: separate major/principal-shareholders table --\n"
                               + " ".join(t[h.start():h.start() + 1500].split())[:1500])
                    break
        else:
            out.append("(no as-a-group/anchor row — read the ownership section directly; "
                       "if this is a 10-K/40-F the table may be in the proxy/circular)")
        for k, v in _signals(t).items():
            out.append(f"\n{k} (in ownership filing): " + " | ".join(v))

    ipo = _query(cik, IPO_FORMS, asof, size=2, order="asc")
    if ipo:
        ti = _text(ipo[0])
        _scan(ipo[0])
        sig = _signals(ti)
        if "OFFERING (IPO)" in sig:
            out.append(f"\n## IPO PROSPECTUS {ipo[0]['formType']} {ipo[0]['filedAt'][:10]}: "
                       + " | ".join(sig["OFFERING (IPO)"]))

    ev = _query(cik, EVENT_FORMS, asof, size=4)
    hits = []
    for f in ev[:4]:
        _scan(f)
        sig = _signals(_text(f))
        for k, v in sig.items():
            hits.append(f"   {f['formType']} {f['filedAt'][:10]} {k}: " + " | ".join(v))
    if hits:
        out.append("\n## RECENT 8-K/6-K EVENTS (PIPE / offering / redemption):")
        out += hits

    out.append("\n(13D/G blocks: query form-13d-13g if a control holder's current block is "
               "needed and not in the table above.)")
    text = "\n".join(out)
    _save_dossier(ticker, asof, text)         # persist the assembled dossier for reuse/audit
    _save_manifest(ticker, asof, cik)         # persist the filing-dependency manifest (delta-updates)
    return text


if __name__ == "__main__":
    t = sys.argv[1]
    asof = sys.argv[2] if len(sys.argv) > 2 else "2026-06-04"
    print(gather(t, asof))
