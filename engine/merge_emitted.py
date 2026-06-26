#!/usr/bin/env python3
"""Fold workflow-emitted recipes into _recipes_emitted.json (then validate_recipes.py scores them).

Input  (_wave_emitted_raw.json): [{"t","a","recipe":{basis,os_M,float_M,dno_M,control_M,ads_ratio,
                                   control_holders[],passive_holders[],conf}}]  (the Workflow return)
Output (_recipes_emitted.json):  same shape + a resolved "cik" per ticker; existing entries kept
                                  (dedup by ticker — a re-emit overwrites). resolve_cik is cached.
"""
import os, sys, json
import float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_wave_emitted_raw.json")
DST = os.path.join(ROOT, "_recipes_emitted.json")

raw = json.load(open(RAW, encoding="utf-8"))
existing = json.load(open(DST, encoding="utf-8")) if os.path.exists(DST) else []
by = {e["t"]: e for e in existing}

added = 0
for e in raw:
    t, a, rc = e["t"], e["a"], e.get("recipe")
    if not rc:
        print(f"  {t}: no recipe (agent returned null) -> skip")
        continue
    cik = fg.resolve_cik(t, a)
    by[t] = {"t": t, "a": a, "cik": cik, "recipe": rc}
    added += 1
    print(f"  {t:6} cik={cik} basis={rc.get('basis')} os={rc.get('os_M')} float={rc.get('float_M')} "
          f"dno={rc.get('dno_M')} ctrl={rc.get('control_M')} ads={rc.get('ads_ratio')} conf={rc.get('conf')}")

out = sorted(by.values(), key=lambda x: x["t"])
json.dump(out, open(DST, "w", encoding="utf-8"), indent=1)
print(f"\nmerged {added} recipes -> {DST} ({len(out)} total)")
