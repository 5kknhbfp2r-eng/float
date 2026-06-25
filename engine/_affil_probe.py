"""Feasibility probe: does SEC Item 403 'officers & directors as a group' beneficial
ownership reproduce DT's exclusion (os - float)?  Compares to the 06-04 scrape labels.
Throwaway probe (like the other _*_probe.py)."""
import os, re, sys, csv, requests
import float_from_filings as ff

DT = {}
with open(os.path.join(ff.PROJECT_DIR, "..", "dt_os_float_2026-06-04.csv")) as f:
    for r in csv.DictReader(f):
        try: DT[r["ticker"]] = (float(r["float_M"]), float(r["os_M"]))
        except: pass

OWN_FORMS = [["DEF 14A", "DEFM14A", "DEF 14C", "PRE 14A"], ["20-F", "20-F/A"], ["10-K", "10-K/A"]]


def latest_ownership_filing(cik, asof="2026-06-04"):
    for forms in OWN_FORMS:
        ft = ",".join(f'"{t}"' for t in forms)
        q = f"cik:{int(cik)} AND formType:({ft}) AND filedAt:[2014-01-01 TO {asof}T23:59:59]"
        body = {"query": q, "from": "0", "size": "3", "sort": [{"filedAt": {"order": "desc"}}]}
        r = requests.post("https://api.sec-api.io", json=body, headers=ff.HDR, timeout=60)
        r.raise_for_status()
        fl = [f for f in r.json().get("filings", []) if f["formType"] in forms]
        if fl:
            return fl[0]
    return None


ASGROUP = re.compile(
    r"(?:all\s+)?(?:our\s+)?(?:current\s+)?"
    r"(?:(?:named\s+)?(?:executive\s+)?officers\s+and\s+directors"
    r"|directors\s+and\s+(?:our\s+)?(?:named\s+)?(?:executive\s+)?officers)"
    r"\s+as\s+a\s+group\s*\(?\s*\d*\s*persons?\)?", re.I)


def asgroup_rows(text):
    """Each 'as a group' occurrence: (beneficial_total_shares, pct, context).
    DT uses the BENEFICIALLY-OWNED total = the share-number immediately preceding
    the percent (last numeric column), NOT the first 'common stock' column."""
    out = []
    for m in ASGROUP.finditer(text):
        tail = text[m.end():m.end() + 140]
        pm = re.search(r"([\d.]+)\s*%", tail)
        seg = tail[:pm.start()] if pm else tail
        nums = re.findall(r"(\d[\d,]{3,})", seg)           # share counts (>=4 digits)
        if nums:
            out.append((int(nums[-1].replace(",", "")), pm.group(1) if pm else None, tail[:90]))
    return out


def probe(t):
    fl, os = DT[t]
    excl_sh = (os - fl) * 1e6
    excl_fr = 1 - fl / os
    try:
        row = (ff.pl.read_parquet(ff.DATA + r"\tickers.parquet")
               .filter(ff.pl.col("ticker") == t).to_dicts())
    except Exception:
        row = []
    cik = row[0]["cik"] if row else None
    if not cik:
        print(f"{t:6} excl {excl_sh/1e6:7.3f}M ({excl_fr:5.1%})  | no CIK in universe"); return
    fil = latest_ownership_filing(cik)
    if not fil:
        print(f"{t:6} excl {excl_sh/1e6:7.3f}M ({excl_fr:5.1%})  | no ownership filing"); return
    try:
        text = ff.fetch_text(fil["linkToFilingDetails"], fil["accessionNo"])
    except Exception as e:
        print(f"{t:6} | fetch fail {e}"); return
    rows = asgroup_rows(text)
    if not rows:
        print(f"{t:6} excl {excl_sh/1e6:7.3f}M ({excl_fr:5.1%})  | {fil['formType']:7} {fil['filedAt'][:10]}  NO as-a-group match"); return
    sh, pct, ctx = rows[0]
    ratio = sh / excl_sh if excl_sh > 0 else float("nan")
    print(f"{t:6} excl {excl_sh/1e6:7.3f}M ({excl_fr:5.1%})  | {fil['formType']:7} {fil['filedAt'][:10]} "
          f"as-a-group {sh/1e6:7.3f}M pct={pct}  ratio_grp/excl={ratio:5.2f}")


if __name__ == "__main__":
    names = sys.argv[1:] or ["ALPS", "CARM", "PCYO", "IDN", "TSE", "OSUR", "ETON", "ARQT", "DARE", "RCEL"]
    print("ticker  DT_exclusion           | ownership filing            as-a-group(beneficial)")
    for t in names:
        if t not in DT:
            print(f"{t:6} not in scrape"); continue
        try:
            probe(t)
        except Exception as e:
            print(f"{t:6} ERROR {e}")
