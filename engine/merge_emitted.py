#!/usr/bin/env python3
"""Fold workflow-emitted recipes into _recipes_emitted.json (then validate_recipes.py scores them).

Input  (_wave_emitted_raw.json): [{"t","a","recipe":{basis,os_M,float_M,dno_M,control_M,ads_ratio,
                                   control_holders[],passive_holders[],conf}}]  (the Workflow return)
Output (_recipes_emitted.json):  same shape + a resolved "cik" per ticker; existing entries kept
                                  (dedup by ticker — a re-emit overwrites). resolve_cik is cached.
"""
import os, sys, json, glob
import float_gather as fg
import float_from_filings as ff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_wave_emitted_raw.json")
DST = os.path.join(ROOT, "_recipes_emitted.json")
EMITTED = os.path.join(ff.DATA, "_cache", "emitted")    # (F15) per-agent durable records

# Fold BOTH the workflow return (if captured) AND the per-ticker durable files record_recipe.py wrote
# during the wave, so an INTERRUPTED run's already-paid recipes are still merged (resume-safe).
raw = json.load(open(RAW, encoding="utf-8")) if os.path.exists(RAW) else []
for p in sorted(glob.glob(os.path.join(EMITTED, "*.json"))):
    try:
        raw.append(json.load(open(p, encoding="utf-8")))
    except Exception as ex:
        print(f"  ! skip {p}: {ex}")
existing = json.load(open(DST, encoding="utf-8")) if os.path.exists(DST) else []
by = {e["t"]: e for e in existing}

added = skipped = 0
for e in raw:
    t, a, rc = e["t"], e["a"], e.get("recipe")
    if not rc:
        print(f"  {t}: no recipe (agent returned null) -> skip")
        continue
    cik = fg.resolve_cik(t, a)
    if not cik:                                          # (F42) a null-cik recipe can't replay -> don't fold
        print(f"  ! {t}: no CIK resolved for {a} -> SKIP (resolve the CIK before warming this recipe)")
        skipped += 1
        continue
    by[t] = {"t": t, "a": a, "cik": cik, "recipe": rc}
    added += 1
    print(f"  {t:6} cik={cik} basis={rc.get('basis')} os={rc.get('os_M')} float={rc.get('float_M')} "
          f"dno={rc.get('dno_M')} ctrl={rc.get('control_M')} ads={rc.get('ads_ratio')} conf={rc.get('conf')}")

out = sorted(by.values(), key=lambda x: x["t"])
json.dump(out, open(DST, "w", encoding="utf-8"), indent=1)
print(f"\nmerged {added} recipes -> {DST} ({len(out)} total)" + (f" | {skipped} skipped (no CIK)" if skipped else ""))
