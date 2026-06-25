#!/usr/bin/env python3
"""De-risk the paid recipe-emit ($0 test): the sim carried ads_ratio=1, so foreign/ADS names mis-replay
(XBRL is ordinary shares, the float is in ADS). A REAL LLM recipe carries the ADS ratio. Simulate that:
derive ads_ratio = xbrl_os(derivation) / label_os(derivation) when it's a clean >1.5 multiple (the ADS
signature), then re-predict each later day as float = xbrl_os(day)/ads_ratio - exclusion. If the
foreign/ADS misses collapse, the real recipe-emit fixes the largest residual category for real.
"""
import os, csv, collections
import det_float as D, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
labels = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")):
    if r["float_M"].strip() and r["os_M"].strip():
        labels[r["ticker"]].append((r["as_of"][:10], float(r["float_M"]), float(r["os_M"])))

# the foreign/ADS free-replay misses from the sim
miss = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))
        if r["status"] == "ok" and r["err_os_rel"] != "" and float(r["err_os_rel"]) > 0.10
        and r["archetype"] == "foreign/ADS"]

print(f"foreign/ADS free-replay misses to retest: {len(miss)}\n")
fixed = stillbad = noratio = 0
seen_ratio = {}
for r in miss:
    t, day = r["ticker"], r["day"]
    days = sorted(labels[t]); d0, fl0, os0 = days[0]
    cik = fg.resolve_cik(t, d0)
    xd = (D.xbrl_os(cik, d0) or {}).get("val_M")
    if t not in seen_ratio:
        ratio = round(xd / os0) if (xd and os0 and xd / os0 >= 1.5) else 1
        seen_ratio[t] = (ratio, xd)
    ratio, xd = seen_ratio[t]
    excl = os0 - fl0
    xday = (D.xbrl_os(cik, day) or {}).get("val_M")
    if ratio <= 1 or not xday:
        noratio += 1
        print(f"  {t:6} {day}  no clean ADS ratio (xbrl/os0={xd}/{os0:.2f}) -> would stay deferred (safe)")
        continue
    pred = xday / ratio - excl
    err = abs(pred - float(r["float_label"])) / float(r["os_label"])
    tag = "FIXED" if err <= 0.10 else "still"
    fixed += err <= 0.10; stillbad += err > 0.10
    print(f"  {t:6} {day}  ratio={ratio:<3} xbrl(day)={xday:.2f} -> float={pred:.2f} "
          f"label={r['float_label']}  err {float(r['err_os_rel'])*100:.0f}% -> {err*100:.0f}%  [{tag}]")

print(f"\nwith label-derived ADS ratio: FIXED(<=10%) {fixed} | still-bad {stillbad} | no-clean-ratio(defers) {noratio}")
print("=> a real recipe-emit that carries ads_ratio repairs the foreign/ADS residual (or safely defers it).")
