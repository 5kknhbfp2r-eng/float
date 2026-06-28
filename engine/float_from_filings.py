"""Reconcile-both point-in-time free float for US equities, closest-to-provider.

Per (ticker, date):
  1. STRUCTURED read  = sec-api `/float` outstandingShares (cached in
     shares_outstanding.parquet), with its as-of date. Machine-clean, but can be
     a stale period-end balance for foreign/20-F filers.
  2. PROSE read (Path A) = sec-api Query API -> fetch primary doc -> parse the
     "as of [date] ... N shares ... outstanding" sentence. Recovers the fresh
     cover/narrative count the structured tag misses (diluters, 20-F shells).
  3. RECONCILE: take the read with the LATEST as-of date (both lookahead-safe:
     filedAt <= date). Tie -> trust the structured XBRL value; flag if prose
     disagrees materially (catches misparses).
  4. SPLIT-ADJUST forward to the trade date (lookahead-safe).
  5. LISTED CLASS only (dual-class -> the tradeable class named in the ticker).
  6. minus split-adjusted INSIDERS (sec-api Form 3/4) for true free float.

Standalone / on-demand (one ticker-date at a time) — NOT a universe batch.
"""
import re, html, json, os, datetime as dt
import requests
import polars as pl

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(PROJECT_DIR, "data")
try:                                            # sec-api retired; EDGAR-only engine doesn't use KEY.
    KEY = open(os.path.join(PROJECT_DIR, "sapi.txt")).read().strip()
except FileNotFoundError:                       # a fresh clone has no sapi.txt (gitignored) — fine.
    KEY = ""
HDR = {"Authorization": KEY, "Content-Type": "application/json"}
UA = {"User-Agent": "research kelsenowens@gmail.com"}
TEXT_CACHE = os.path.join(DATA, "_cache", "filing_text")

FORMS = ["20-F", "10-K", "10-Q", "424B4", "424B3", "424B5", "F-1"]
MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
NUM = r"\d{1,3}(?:,\d{3})+|\d{7,}"
CLS = (r"Class\s+[A-H]\s+Ordinary\s+Shares|Class\s+[A-H]\s+Common\s+Stock|"
       r"Ordinary\s+Shares|common\s+stock|common\s+shares")
REL = (r"as of the date of this (?:annual report|quarterly report|"
       r"transition report|report|prospectus|registration statement)")
ABS = rf"(?:as of|as at|on|at)\s+((?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}})"


# ----------------------------------------------------------------------------
# Path A: find -> fetch -> parse
# ----------------------------------------------------------------------------
def latest_filing_asof(cik: str, asof: str) -> dict | None:
    ft = ",".join(f'"{t}"' for t in FORMS)
    q = (f"cik:{int(cik)} AND formType:({ft}) "
         f"AND filedAt:[2001-01-01 TO {asof}T23:59:59]")
    body = {"query": q, "from": "0", "size": "10",
            "sort": [{"filedAt": {"order": "desc"}}]}
    r = requests.post("https://api.sec-api.io", json=body, headers=HDR, timeout=60)
    r.raise_for_status()
    for f in r.json().get("filings", []):
        if f["formType"] in FORMS:          # exact guard: formType is tokenized
            return f
    return None


def fetch_text(url: str, accession: str) -> str:
    os.makedirs(TEXT_CACHE, exist_ok=True)
    cache = os.path.join(TEXT_CACHE, f"{accession.replace('/', '-')}.txt")
    if os.path.exists(cache):
        return open(cache, encoding="utf-8").read()
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    t = html.unescape(h).replace(" ", " ").replace("’", "'")
    t = re.sub(r"\s+", " ", t)
    open(cache, "w", encoding="utf-8").write(t)
    return t


def _parse_date(s: str) -> str:
    return dt.datetime.strptime(s, "%B %d, %Y").date().isoformat()


# A number is "current shares outstanding" only when it is bound to a share class AND
# the word "outstanding" within one clause (either order). Numbers in authorized /
# converted / consolidated / issuable contexts, or in a filer-status checkbox blob
# ("Large accelerated filer [ ] ..."), are NOT the current count and are rejected.
_NOT_CURRENT = re.compile(
    r"consolidated\s+into|reverse\s+(?:stock\s+)?split|divided\s+into|"
    r"reserved\s+for|issuable", re.I)
_SHARE_OUT = re.compile(
    rf"(?P<num>{NUM})\s+(?:shares\s+of\s+)?(?:the\s+registrant'?s\s+)?"
    # (F18) the class->'outstanding' gap must NOT bridge a SECOND 6-digit number, else an AUTHORIZED
    # count can anchor here and reach the 'outstanding' belonging to a later (real) number.
    rf"(?:(?P<clsA>{CLS})(?:(?!\.\s|[\d,]{{6,}})[\s\S]){{0,80}}?(?:issued\s+and\s+)?outstanding"
    rf"|(?:issued\s+and\s+)?outstanding\s+(?P<clsB>{CLS}))", re.I)


def extract_shares(text: str, filing_date: str) -> dict | None:
    """Best {as_of, per_class, total, sentence} from the narrative prose.

    Requires the count to be bound to a share class AND "outstanding" within one clause
    (either order), and rejects authorized/converted/consolidated ("not current") numbers
    and filer-status checkbox blobs. Same-as-of matches merge into a per-class dict, so
    dual-class covers (e.g. ELPW Class A + B) are captured together.
    """
    by_asof: dict = {}
    for m in _SHARE_OUT.finditer(text):
        n = int(m.group("num").replace(",", ""))
        if n > 50_000_000_000:                                  # (F33) only impossibly-large = authorized cap;
            continue                                            # legit sub-penny issuers can exceed 5B shares
        if _NOT_CURRENT.search(text[max(0, m.start() - 45):m.start()]):
            continue                                            # not the current count
        if re.search(r"(?i)authoriz|designat", m.group(0)):     # (F18) 'authorized'/'designated' INSIDE the
            continue                                            # num..outstanding span -> the 'outstanding'
            #                                                     belongs to a LATER number, not this one
        cls = re.sub(r"\s+", " ", (m.group("clsA") or m.group("clsB"))).title()
        cls = "Common Stock" if "common" in cls.lower() and "class" not in cls.lower() else cls
        before = text[max(0, m.start() - 120):m.start()]
        after = text[m.end():m.end() + 70]
        if re.search(REL, before, re.I) or re.search(REL, after, re.I):
            asof, src = filing_date, "filing_date"
        elif (am := list(re.finditer(ABS, before, re.I))):
            asof, src = _parse_date(am[-1].group(1)), "absolute"    # nearest preceding
        elif (am := re.search(ABS, after, re.I)):
            asof, src = _parse_date(am.group(1)), "absolute"        # nearest following
        else:
            continue                                            # require a resolvable as-of
        slot = by_asof.setdefault((asof, src), {"per_class": {}, "sentence": None})
        slot["per_class"].setdefault(cls, n)                    # first/canonical per class
        if slot["sentence"] is None:
            slot["sentence"] = re.sub(r"\s+", " ", text[m.start():m.end() + 25]).strip()[:240]
    if not by_asof:
        return None
    (asof, src), best = max(by_asof.items(),
                            key=lambda kv: (kv[0][0], kv[0][1] == "filing_date"))
    return {"as_of": asof, "as_of_src": src, "per_class": best["per_class"],
            "total": sum(best["per_class"].values()), "sentence": best["sentence"]}


# ----------------------------------------------------------------------------
# Structured leg + helpers (read cached parquets; no API cost)
# ----------------------------------------------------------------------------
def structured_shares_asof(ticker: str, asof: str) -> dict | None:
    so = pl.read_parquet(os.path.join(DATA, "shares_outstanding.parquet"))
    row = so.filter((pl.col("ticker") == ticker) & (pl.col("date") == asof)).to_dicts()
    if not row or row[0]["shares_outstanding"] is None:
        return None
    return {"shares": row[0]["shares_outstanding"],
            "as_of": (row[0]["shares_outstanding_period"] or "")[:10] or asof}


def insiders_asof(ticker: str, asof: str) -> float | None:
    ins = pl.read_parquet(os.path.join(DATA, "insiders_daily.parquet"))
    row = ins.filter((pl.col("ticker") == ticker) & (pl.col("date") == asof)).to_dicts()
    return row[0]["insider_holdings"] if row else None


def split_factor(ticker: str, frm: str, to: str, splits: pl.DataFrame) -> float:
    f = 1.0
    for ed, r in (splits.filter(pl.col("ticker") == ticker)
                  .select(["execution_date", "ratio"]).iter_rows()):
        if ed and r and r > 0 and frm < ed <= to:
            f *= r
    return f


def pick_listed_class(per_class: dict, name: str) -> str:
    """The tradeable class named in the ticker (dual-class -> that class)."""
    m = re.search(r"Class\s+([A-H])\b", name, re.I)
    if m:
        letter = m.group(1).upper()
        for k in per_class:
            if re.search(rf"Class\s+{letter}\b", k, re.I):
                return k
    if len(per_class) == 1:
        return next(iter(per_class))
    return max(per_class, key=per_class.get)        # fallback: largest class


# ----------------------------------------------------------------------------
# Reconcile + free float
# ----------------------------------------------------------------------------
def reported_shares_asof(ticker: str, cik: str, asof: str, name: str) -> dict:
    struct = structured_shares_asof(ticker, asof)
    filing = latest_filing_asof(cik, asof)
    prose = None
    if filing:
        text = fetch_text(filing["linkToFilingDetails"], filing["accessionNo"])
        ext = extract_shares(text, filing["filedAt"][:10])
        if ext:
            lc = pick_listed_class(ext["per_class"], name)
            prose = {"shares": ext["per_class"][lc], "as_of": ext["as_of"],
                     "class": lc, "sentence": ext["sentence"],
                     "filing": filing["formType"], "accession": filing["accessionNo"]}
    # reconcile: later as-of wins; tie -> structured
    chosen, flag = None, None
    if struct and prose:
        if prose["as_of"] > struct["as_of"]:
            chosen = ("prose", prose)
        elif struct["as_of"] > prose["as_of"]:
            chosen = ("structured", struct)
        else:                                # same as-of date
            chosen = ("structured", struct)
            if abs(struct["shares"] - prose["shares"]) / max(struct["shares"], 1) > 0.02:
                flag = f"DISAGREE @ {struct['as_of']}: structured={struct['shares']:,.0f} prose={prose['shares']:,.0f}"
    elif prose:
        chosen = ("prose", prose)
    elif struct:
        chosen = ("structured", struct)
    else:
        return {"error": "no share count from either source"}
    return {"source": chosen[0], "shares": chosen[1]["shares"],
            "as_of": chosen[1]["as_of"], "flag": flag,
            "structured": struct, "prose": prose}


def free_float_asof(ticker: str, asof: str, splits: pl.DataFrame | None = None) -> dict:
    if splits is None:
        splits = pl.read_parquet(os.path.join(DATA, "splits.parquet"))
    tk = pl.read_parquet(os.path.join(DATA, "tickers.parquet"))
    trow = tk.filter(pl.col("ticker") == ticker).to_dicts()
    if not trow:
        return {"ticker": ticker, "error": "ticker not in universe"}
    cik, name = trow[0]["cik"], trow[0]["name"]
    rep = reported_shares_asof(ticker, cik, asof, name)
    if "error" in rep:
        return {"ticker": ticker, **rep}
    fac = split_factor(ticker, rep["as_of"], asof, splits)
    shares_adj = rep["shares"] * fac
    ins = insiders_asof(ticker, asof)
    ff = shares_adj - ins if (ins is not None and 0 < ins < shares_adj) else shares_adj
    return {
        "ticker": ticker, "trade_date": asof, "name": name,
        "source": rep["source"], "as_of": rep["as_of"], "flag": rep["flag"],
        "reported_shares": round(rep["shares"]),
        "split_factor": round(fac, 6),
        "shares_split_adjusted": round(shares_adj),
        "insiders_subtracted": None if ins is None else round(ins),
        "free_float": round(ff),
        "structured": rep["structured"], "prose": rep["prose"],
    }


if __name__ == "__main__":
    splits = pl.read_parquet(os.path.join(DATA, "splits.parquet"))
    cases = [("ELPW", "2026-04-24", 1_420_000), ("AUUD", "2026-04-23", 492_860)]
    for tkr, d, prov in cases:
        res = free_float_asof(tkr, d, splits)
        print("=" * 80)
        st, pr = res.pop("structured", None), res.pop("prose", None)
        print(json.dumps(res, indent=2))
        print(f"  structured read: {st}")
        print(f"  prose read     : {pr}")
        for label in ("shares_split_adjusted", "free_float"):
            v = res.get(label)
            if v:
                print(f"  {label:24s} = {v:>12,}  | provider {prov:,} | {v/prov*100:5.1f}%")
