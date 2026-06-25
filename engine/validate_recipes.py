#!/usr/bin/env python3
"""Validate §16 levers 2-3 end-to-end: take LLM-emitted recipes (_recipes_emitted.json), save them +
warm the holder registry with the clean verdicts, then REPLAY each ticker's later candidate-days
DETERMINISTICALLY (no LLM) and score vs the point-in-time labels in float_is.csv.

_recipes_emitted.json: [{"t","a","cik","recipe":{basis,dno_M,control_M,ads_ratio,float_M,os_M,
                          control_holders[],passive_holders[],conf}}]
"""
import os, json, csv, collections
import recipe_cache as RC
import holder_registry as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
emitted = json.load(open(os.path.join(ROOT, "_recipes_emitted.json"), encoding="utf-8"))

# labels: ticker -> [(day, float, os)]
by = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")):
    if r["float_M"].strip():
        by[r["ticker"]].append((r["as_of"][:10], float(r["float_M"]),
                                float(r["os_M"]) if r["os_M"].strip() else None))

free = match = stale = defer = 0
for e in emitted:
    t, cik, rc = e["t"], e["cik"], e.get("recipe")
    if not rc:
        continue
    RC.save_recipe(t, cik, rc["basis"], e["a"], rc["os_M"], rc["float_M"], rc["control_M"],
                   dno_M=rc.get("dno_M", 0.0), ads_ratio=rc.get("ads_ratio", 1.0) or 1.0,
                   control_holders=rc.get("control_holders", []), conf=rc.get("conf", "med"))
    for nm in rc.get("control_holders", []):
        H.set_class(nm, "control", source="llm-recipe")
    for nm in rc.get("passive_holders", []):
        H.set_class(nm, "passive", source="llm-recipe")
    days = sorted(by[t])
    print(f"\n{t}: recipe basis={rc['basis']} dno={rc['dno_M']:.2f} control={rc['control_M']:.2f} "
          f"ads={rc.get('ads_ratio',1)}  (derived {e['a']}: fl={rc['float_M']:.2f}/os={rc['os_M']:.2f})")
    for d, fl, os_ in days:
        if d <= e["a"]:
            continue
        st, fv = RC.replay(t, d, cik)
        if st == "ok":
            err = abs(fv - fl) / os_ if os_ else None
            free += 1; match += (err is not None and err <= 0.05)
            print(f"   {d}  REPLAY(free) float={fv:.2f} label={fl:.2f}  err={err*100:.1f}%" if err is not None
                  else f"   {d}  REPLAY(free) float={fv:.2f}")
        else:
            stale += (st == "stale"); defer += (st != "stale")
            print(f"   {d}  {st.upper()} -> LLM")

n = free + stale + defer
print(f"\n=== RECIPE REPLAY (derive once -> replay free) ===")
print(f"later days: {n} | FREE replay: {free} ({100*free//max(1,n)}%), of those within 5%: {match}/{max(1,free)} "
      f"| stale->LLM: {stale} | deferred->LLM: {defer}")
print(f"registry now warmed to {len(H.REGISTRY)} entities")
