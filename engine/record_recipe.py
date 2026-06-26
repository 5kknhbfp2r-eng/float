#!/usr/bin/env python3
"""(F15) Durable per-agent recipe record — mirrors record.py/record_llm.py so a recipe-emit wave is
interruption-resilient: each agent writes its recipe the INSTANT it derives it, so a usage-credit stop
loses nothing and resume = worklist minus the tickers already recorded here.

Usage (recipe JSON on stdin, to avoid shell-quoting the holder-name arrays):
  python record_recipe.py TICKER ASOF <<'JSON'
  {"basis":"normal","os_M":..,"float_M":..,"dno_M":..,"control_M":..,"ads_ratio":..,
   "control_holders":[..],"passive_holders":[..],"conf":".."}
  JSON

Writes one file per ticker -> engine/data/_cache/emitted/<TICKER>.json = {"t","a","recipe":{...}}.
Per-ticker files avoid the concurrent-write race that a shared JSON would have under 12 parallel agents.
merge_emitted.py folds these (plus the workflow return) into _recipes_emitted.json.
"""
import os, sys, json, tempfile
import float_from_filings as ff

REQ = {"basis", "os_M", "float_M", "dno_M", "control_M", "ads_ratio",
       "control_holders", "passive_holders", "conf"}
EMITTED = os.path.join(ff.DATA, "_cache", "emitted")


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: record_recipe.py TICKER ASOF  (recipe JSON on stdin)")
    t, a = sys.argv[1].upper(), sys.argv[2][:10]
    try:
        rc = json.load(sys.stdin)
    except Exception as e:
        sys.exit(f"record_recipe: stdin is not valid JSON: {e}")
    missing = REQ - set(rc)
    if missing:
        sys.exit(f"record_recipe: recipe missing keys {sorted(missing)}")
    # cheap unit-sanity (the same identity replay/save_recipe rely on) — warn, don't reject.
    if rc["basis"] == "normal" and rc.get("os_M") and rc.get("ads_ratio"):
        implied = rc["os_M"] / (rc["ads_ratio"] or 1.0) - rc["dno_M"] - rc["control_M"]
        if abs(implied - rc["float_M"]) > 0.01 * max(1.0, rc["os_M"]):
            print(f"  ! {t}: float_M {rc['float_M']} != os/ads-excl {implied:.3f} (check units)")
    os.makedirs(EMITTED, exist_ok=True)
    dst = os.path.join(EMITTED, f"{t}.json")
    rec = {"t": t, "a": a, "recipe": rc}
    fd, tmp = tempfile.mkstemp(dir=EMITTED, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dst)                      # atomic
    print(f"  recorded {t} @ {a} -> {dst}")


if __name__ == "__main__":
    main()
