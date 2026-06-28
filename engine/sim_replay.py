#!/usr/bin/env python3
"""FULL-SCALE recipe-replay simulation — measures the blended free-fraction for $0 (no LLM).

The label IS the ground-truth recipe at its derivation day: at the earliest labeled day the total
exclusion = os_M - float_M (officers+directors+control, in shares). So we can carry that exclusion
and REPLAY every later labeled day through the real recipe_cache.replay() machinery — re-fetching O/S
fresh, anchoring on os_at, deferring on staleness / proxy-change / implausibility — and score the
deterministic float against the later-day labels. This proves the recipe-cache system at full IS-set
scale WITHOUT spending a cent on the LLM. (The one thing it can't test — can the LLM PRODUCE the
dno/control split — is already proven on KALA/NUKK/LIVE, where the agents nailed it.)

Carries the TOTAL exclusion as control_M (dno_M=0): the float math os_-dno_M-control_M is identical,
and with no control_holders staleness rests purely on STRUCT_FORMS + the proxy-changed guard (exactly
the deterministic signals). Writes _sim_replay.csv incrementally (resume-safe) + prints the rollup.
"""
import os, sys, csv, json, collections
import recipe_cache as RC
import det_float as D
import float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC.RECIPES_PATH = os.path.join(ROOT, "_sim_recipes.json")   # sandbox — never touch the real recipes.json
RC.RECIPES = {}
OUT = os.path.join(ROOT, "_sim_replay.csv")

# labels: ticker -> [(day, float, os, basis, note)]
by = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")):
    if r["float_M"].strip() and r["os_M"].strip():
        by[r["ticker"]].append((r["as_of"][:10], float(r["float_M"]), float(r["os_M"]),
                                r.get("basis", ""), r.get("note", "")))
multi = {t: sorted(v) for t, v in by.items() if len(v) >= 2}

# resume: skip tickers already in the output CSV
done = set()
if os.path.exists(OUT):
    done = {row["ticker"] for row in csv.DictReader(open(OUT, encoding="utf-8"))}
new = not os.path.exists(OUT)
fh = open(OUT, "a", newline="", encoding="utf-8")
w = csv.writer(fh)
if new:
    w.writerow(["ticker", "day", "status", "float_replay", "float_label", "os_label",
                "err_float_rel", "err_os_rel", "archetype", "derived_day"])

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
todo = [t for t in sorted(multi) if t not in done][:LIMIT]
print(f"{len(multi)} multi-day tickers | {len(done)} already done | running {len(todo)} now")

for i, t in enumerate(todo):
    days = multi[t]
    d0, fl0, os0, basis0, note0 = days[0]
    arche = D.archetype(basis0, note0)
    excl = os0 - fl0
    if excl < 0 or os0 <= 0:                      # bad label row — skip (can't form a recipe)
        w.writerow([t, d0, "bad-label", "", fl0, os0, "", arche, d0]); fh.flush(); continue
    cik = fg.resolve_cik(t, d0)
    if not cik:
        w.writerow([t, d0, "no-cik", "", fl0, os0, "", arche, d0]); fh.flush(); continue
    RC.save_recipe(t, cik, "normal", d0, os0, fl0, control_M=excl, dno_M=0.0)
    for d, fl, oss, _b, _n in days[1:]:
        try:
            st, fv = RC.replay(t, d, cik)
        except Exception as e:
            st, fv = "err:" + type(e).__name__, None
        err = (abs(fv - fl) / oss) if (st == "ok" and oss) else ""        # O/S-relative (anchor-band diagnostic)
        errf = (abs(fv - fl) / fl) if (st == "ok" and fl) else ""         # (F13) FLOAT-relative = the real accuracy
        w.writerow([t, d, st, (round(fv, 3) if fv is not None else ""), fl, oss,
                    (round(errf, 4) if errf != "" else ""),
                    (round(err, 4) if err != "" else ""), arche, d0])
    fh.flush()
    if (i + 1) % 20 == 0:
        print(f"  ...{i + 1}/{len(todo)} ({t})")

fh.close()
print(f"done -> {OUT}")
