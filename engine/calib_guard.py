#!/usr/bin/env python3
"""Calibrate an O/S-freshness guard for recipe replay. For every FREE ('ok') replay in
_sim_replay.csv, find the forms filed in the gap (O/S-fact filed-date, replay day]. Then for
candidate form-sets, measure: misses (>10%) CAUGHT (good — defer the wrong float) vs accurate
(<5%) wrongly DEFERRED (cost). Picks the form-set that catches the staleness misses cheaply.
"""
import os, csv, collections
import det_float as D, float_gather as fg, edgar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))
        if r["status"] == "ok" and r["err_os_rel"] != ""]

OFFERING = {"424B1","424B2","424B3","424B4","424B5","424B7","S-1","S-1/A","S-3","S-3/A",
            "S-3ASR","POS AM","EFFECT","FWP","424B8","S-1MEF","S-3MEF"}
SPLIT8K  = {"8-K","8-K/A"}                       # reverse split / Item 3.02 dilution land here
PROXYREV = {"PRER14A","DEFR14A","DEFA14A","DEFM14A"}

cache = {}
def gap_forms(tk, day):
    cik = cache.get(tk) or fg.resolve_cik(tk, day)
    cache[tk] = cik
    if not cik:
        return set()
    x = D.xbrl_os(cik, day) or {}
    g = D.regex_os(cik, day) or {}
    osfiled = x.get("filed") or g.get("filed")
    if not osfiled:
        return set()
    allforms = OFFERING | SPLIT8K | PROXYREV
    return {f["formType"] for f in edgar.query(cik, list(allforms), day, size=60)
            if osfiled < f["filedAt"][:10] <= day}

# annotate each free replay with its gap-form buckets + error bucket
for r in rows:
    gf = gap_forms(r["ticker"], r["day"])
    r["_off"] = bool(gf & OFFERING)
    r["_8k"]  = bool(gf & SPLIT8K)
    r["_prx"] = bool(gf & PROXYREV)
    r["_err"] = float(r["err_os_rel"])

miss = [r for r in rows if r["_err"] > 0.10]
acc  = [r for r in rows if r["_err"] <= 0.05]
print(f"free replays: {len(rows)} | misses(>10%): {len(miss)} | accurate(<=5%): {len(acc)}\n")

def evalguard(name, pred):
    caught = sum(pred(r) for r in miss)
    cost   = sum(pred(r) for r in acc)
    kept_free = len(rows) - sum(pred(r) for r in rows)
    remain_miss = len(miss) - caught
    print(f"{name:32} catches {caught:2}/{len(miss)} misses | wrongly defers {cost:2}/{len(acc)} accurate "
          f"| free left {kept_free:3} | misses left {remain_miss}")

evalguard("offering-forms in gap",        lambda r: r["_off"])
evalguard("8-K in gap",                   lambda r: r["_8k"])
evalguard("proxy-revision in gap",        lambda r: r["_prx"])
evalguard("offering OR 8-K",              lambda r: r["_off"] or r["_8k"])
evalguard("offering OR 8-K OR proxy-rev", lambda r: r["_off"] or r["_8k"] or r["_prx"])
evalguard("offering OR proxy-rev",        lambda r: r["_off"] or r["_prx"])

# what archetypes are the misses NOT caught by 'offering OR proxy-rev'?
print("\nmisses NOT caught by (offering OR proxy-rev):")
for r in sorted([r for r in miss if not (r["_off"] or r["_prx"])], key=lambda r:-r["_err"]):
    print(f"  {r['ticker']:6} {r['day']} err={r['_err']*100:4.0f}% {r['archetype']:16} 8k={r['_8k']}")
