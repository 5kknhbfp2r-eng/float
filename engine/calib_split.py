#!/usr/bin/env python3
"""Calibrate a reverse-split defer for replay. A reverse split changes the share basis; XBRL lags it
(announced in an 8-K, effective days later, absorbed at the next periodic), so during the lag the
re-fetched O/S is the stale pre-split count (HUSA 899%). Detector: a reverse-split 8-K filed in
[derived_day-60d, day] (the announcement usually precedes the effective date, sometimes before the
recipe's derivation). Measure misses(>10%) caught vs accurate(<=5%) wrongly deferred over the current
band+424B sim's FREE replays.
"""
import os, re, csv, datetime as dt, collections
import float_gather as fg, edgar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RS = re.compile(r"reverse\s+(?:stock\s+)?split", re.I)
RATIO = re.compile(r"\b(?:1[-\s]?for[-\s]?\d{1,3}|\d{1,3}[-\s]?for[-\s]?1|1[-:]\s?\d{1,3})\b", re.I)
_cache = {}

def split_risk(tk, derived_day, day):
    cik = _cache.get(tk) or fg.resolve_cik(tk, derived_day)
    _cache[tk] = cik
    if not cik:
        return False
    lo = (dt.date.fromisoformat(derived_day) - dt.timedelta(days=60)).isoformat()
    for f in edgar.query(cik, ["8-K", "8-K/A"], day, size=30):
        if not (lo <= f["filedAt"][:10] <= day):
            continue
        try:
            t = fg._text(f)
        except Exception:
            continue
        if RS.search(t) and RATIO.search(t):
            return True
    return False

rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))
        if r["status"] == "ok" and r["err_os_rel"] != ""]
for r in rows:
    r["_err"] = float(r["err_os_rel"])
    r["_split"] = split_risk(r["ticker"], r["derived_day"], r["day"])

miss = [r for r in rows if r["_err"] > 0.10]
acc  = [r for r in rows if r["_err"] <= 0.05]
caught = sum(r["_split"] for r in miss)
cost   = sum(r["_split"] for r in acc)
print(f"FREE replays {len(rows)} | misses>10% {len(miss)} | accurate<=5% {len(acc)}")
print(f"reverse-split defer: catches {caught}/{len(miss)} misses | wrongly defers {cost}/{len(acc)} accurate")
print(f"  free left {len(rows)-sum(r['_split'] for r in rows)} | misses left {len(miss)-caught}")
print("\nmisses CAUGHT:")
for r in sorted([r for r in miss if r["_split"]], key=lambda r:-r["_err"]):
    print(f"  {r['ticker']:6} {r['day']} err={r['_err']*100:4.0f}% {r['archetype']}")
print("accurate WRONGLY deferred:")
for r in [r for r in acc if r["_split"]]:
    print(f"  {r['ticker']:6} {r['day']} err={r['_err']*100:.0f}% {r['archetype']}")
