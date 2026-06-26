#!/usr/bin/env python3
"""Calibrate an XBRL O/S-fact STALENESS guard. The frozen-fact misses (MB foreign IPO: dei end
2024-12-31 used on 2025-07-08; AGEN) use an O/S fact whose `end` long predates the replay day, so it
misses an IPO/offering/restatement the periodic cadence hasn't caught up to. Tabulate, per age
threshold (replay_day - xbrl_end, days), misses(>10%) caught vs accurate(<=5%) wrongly deferred.
"""
import os, csv, datetime as dt
import det_float as D, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))
        if r["status"] == "ok" and r["err_os_rel"] != ""]
cache = {}
for r in rows:
    cik = cache.get(r["ticker"]) or fg.resolve_cik(r["ticker"], r["derived_day"])
    cache[r["ticker"]] = cik
    x = D.xbrl_os(cik, r["day"]) if cik else None
    if x and x.get("end"):
        r["_age"] = (dt.date.fromisoformat(r["day"]) - dt.date.fromisoformat(x["end"])).days
    else:
        r["_age"] = None
    r["_err"] = float(r["err_os_rel"])

miss = [r for r in rows if r["_err"] > 0.10 and r["_age"] is not None]
acc  = [r for r in rows if r["_err"] <= 0.05 and r["_age"] is not None]
print(f"scored {len(rows)} | misses w/age {len(miss)} | accurate w/age {len(acc)}\n")
print(f"{'age>N days':>12} | misses caught | accurate wrongly deferred")
for N in (300, 250, 200, 180, 150, 135, 120, 100):
    c = sum(r["_age"] > N for r in miss)
    x = sum(r["_age"] > N for r in acc)
    print(f"   >{N:>4}d     | {c:2}/{len(miss)}        | {x:2}/{len(acc)}")
print("\nmiss ages:", sorted([r["_age"] for r in miss], reverse=True))
print("worst accurate ages (top 8):", sorted([r["_age"] for r in acc], reverse=True)[:8])
