#!/usr/bin/env python3
"""Calibrate the anchor band (os_selected / os_at). A replay is trustworthy only if the re-fetched
O/S is close to the recipe's LLM-validated os_at. Beyond a band the O/S has either changed basis
(ADS/ordinary, multi-class) or moved too far (split/big dilution) to trust -> defer & re-derive.
Tabulate, per symmetric band [1/k, k], misses(>10%) caught vs accurate(<=5%) wrongly deferred.
os_selected backed out: float_replay = os_sel - exclusion, exclusion = os_at - float_at (sim: ads=1).
"""
import os, csv, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
labels = {}
for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")):
    if r["float_M"].strip() and r["os_M"].strip():
        labels.setdefault(r["ticker"], []).append((r["as_of"][:10], float(r["float_M"]), float(r["os_M"])))
anchor = {t: sorted(v)[0][2] for t, v in labels.items()}        # earliest-day os = os_at
exclu  = {t: sorted(v)[0][2] - sorted(v)[0][1] for t, v in labels.items()}

rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))
        if r["status"] == "ok" and r["err_os_rel"] != ""]
for r in rows:
    t = r["ticker"]
    os_sel = float(r["float_replay"]) + exclu[t]               # sim: os_sel = float + exclusion
    r["_ratio"] = os_sel / anchor[t] if anchor[t] else 1.0
    r["_err"] = float(r["err_os_rel"])

miss = [r for r in rows if r["_err"] > 0.10]
acc  = [r for r in rows if r["_err"] <= 0.05]
print(f"free replays {len(rows)} | misses>10% {len(miss)} | accurate<=5% {len(acc)}\n")
print(f"{'band [1/k,k]':>14} | misses caught | accur. deferred | free left | misses left | miss-rate left")
for k in (8.0, 3.0, 2.0, 1.5, 1.4, 1.35, 1.3, 1.25, 1.2, 1.15):
    out = lambda r: not (1.0 / k <= r["_ratio"] <= k)
    caught = sum(out(r) for r in miss)
    cost   = sum(out(r) for r in acc)
    kept   = [r for r in rows if not out(r)]
    ml = len(miss) - caught
    mr = 100 * ml // max(1, len(kept))
    print(f"   k={k:>4}      | {caught:2}/{len(miss):2}        | {cost:2}/{len(acc):3}          | {len(kept):3}       | {ml:2}          | {mr}%")

print("\nmisses that survive even k=1.5 (ratio within band -> basis-stable but still wrong):")
for r in sorted([r for r in miss if 1/1.5 <= r["_ratio"] <= 1.5], key=lambda r: -r["_err"]):
    print(f"  {r['ticker']:6} {r['day']} err={r['_err']*100:4.0f}% ratio={r['_ratio']:.2f} {r['archetype']}")
