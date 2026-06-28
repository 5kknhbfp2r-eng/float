"""Current ticker->CIK from SEC's own company_tickers.json (free SEC source, NOT
Massive/Polygon) — replaces the stale data/tickers.parquet for coverage. Also measures
the DT-universe coverage and the US(DEF 14A)/foreign(20-F)/none filer-type breakdown."""
import json, os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import float_from_filings as ff
import _affil_probe as ap

DT = ap.DT
CACHE = os.path.join(ff.DATA, "_cache", "company_tickers.json")


def load_map():
    if not os.path.exists(CACHE):
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=ff.UA, timeout=60)
        r.raise_for_status()
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        open(CACHE, "w").write(r.text)
    m = {}
    for v in json.load(open(CACHE)).values():
        m[v["ticker"].upper()] = str(v["cik_str"])
    return m


MAP = load_map()
try:    # stale producer parquet is gitignored; absent on a fresh clone -> SEC map only
    PQ = {r["ticker"]: str(r["cik"]).lstrip("0")
          for r in ff.pl.read_parquet(os.path.join(ff.DATA, "tickers.parquet"))
          .select(["ticker", "cik"]).to_dicts()}
except FileNotFoundError:
    PQ = {}

# Third leg: sec-api Mapping API (covers DELISTED names the SEC map lacks). Exact-ticker
# match ONLY — the endpoint prefix-matches, e.g. ADAP's first hit is ADAPQ = Adaptive
# Broadband, a different company. Cached; None = looked up, no exact match.
SAPI_CACHE = os.path.join(ff.DATA, "_cache", "secapi_ticker_cik.json")
try:
    SAPI = json.load(open(SAPI_CACHE))
except FileNotFoundError:
    SAPI = {}


def resolve_via_mapping(tickers):
    for i, t in enumerate(tickers):
        if t in SAPI:
            continue
        r = requests.get(f"https://api.sec-api.io/mapping/ticker/{t}?token={ff.KEY}", timeout=30)
        if not r.ok:
            continue                       # don't cache rate-limit/transient failures
        hits = [h for h in r.json() if h.get("ticker", "").upper() == t.upper() and h.get("cik")]
        SAPI[t] = str(hits[0]["cik"]).lstrip("0") if hits else None
        if i % 100 == 0:
            json.dump(SAPI, open(SAPI_CACHE, "w"))
    json.dump(SAPI, open(SAPI_CACHE, "w"))


def resolve_via_query(tickers):
    """Last resort: sec-api Query API search by at-filing-time ticker. Latest filer
    <= 2026-06-04 wins (handles ticker reuse; matches DT's 6/4 coverage date)."""
    for i, t in enumerate(tickers):
        if t in SAPI:
            continue                       # (F09) never overwrite a verified mapping result (incl. None)
        body = {"query": f"ticker:{t} AND filedAt:[2000-01-01 TO 2026-06-04T23:59:59]",
                "from": "0", "size": "1", "sort": [{"filedAt": {"order": "desc"}}]}
        r = requests.post("https://api.sec-api.io", json=body, headers=ff.HDR, timeout=30)
        if not r.ok:
            continue
        fl = r.json().get("filings", [])
        # (F09) require the filing's own ticker to match before caching (mirror resolve_via_mapping);
        # an unverified `ticker:T` hit can be a different entity that previously used the symbol. For a
        # truly point-in-time resolution prefer edgar.resolve_cik_edgar (latest-dated hit <= asof).
        if fl and fl[0].get("cik") and fl[0].get("ticker", "").upper() == t.upper():
            SAPI[t] = str(fl[0]["cik"]).lstrip("0")
        else:
            SAPI[t] = None                 # cache the miss so it isn't retried/overwritten
        if i % 100 == 0:
            json.dump(SAPI, open(SAPI_CACHE, "w"))
    json.dump(SAPI, open(SAPI_CACHE, "w"))


def cik_of(t):
    """Combined resolver: SEC company_tickers.json, else stale producer parquet, else
    the cached sec-api mapping/query lookups (delisted)."""
    return MAP.get(t.upper()) or PQ.get(t) or SAPI.get(t.upper())


if __name__ == "__main__":
    inmap = [t for t in DT if t in MAP]
    inpq = [t for t in DT if t in PQ]
    union = [t for t in DT if cik_of(t)]
    print(f"DT scrape names: {len(DT)}")
    print(f"  SEC company_tickers.json: {len(inmap)} ({len(inmap)/len(DT)*100:.1f}%)")
    print(f"  stale tickers.parquet:    {len(inpq)} ({len(inpq)/len(DT)*100:.1f}%)")
    print(f"  UNION (cik_of resolves):  {len(union)} ({len(union)/len(DT)*100:.1f}%)")
    print(f"  no CIK in either:         {len(DT)-len(union)} ({(len(DT)-len(union))/len(DT)*100:.1f}%)")
    resolve_via_mapping([t for t in sorted(DT) if not cik_of(t)])
    union = [t for t in DT if cik_of(t)]
    print(f"  + sec-api mapping (delisted): UNION {len(union)} ({len(union)/len(DT)*100:.1f}%)")
    resolve_via_query([t for t in sorted(DT) if not cik_of(t)])
    union = [t for t in DT if cik_of(t)]
    print(f"  + sec-api query (at-filing-time ticker): UNION {len(union)} ({len(union)/len(DT)*100:.1f}%)")
    miss = [t for t in sorted(DT) if not cik_of(t)][:25]
    print(f"  sample uncovered: {miss}")
