#!/usr/bin/env python3
"""Score the LLM-tail results (_llm_tail_results.csv) against the point-in-time labels
(float_is.csv). Exact-float only, O/S-relative (the real-use metric). DT is a single 2026-06-04
snapshot, so it's used ONLY for as_of==2026-06-04 names (and even then can be off)."""
import csv, os, statistics

ROOT = os.path.dirname(os.path.abspath(__file__))
lab = {(r["ticker"], r["as_of"]): r for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8"))}
res = list(csv.DictReader(open(os.path.join(ROOT, "_llm_tail_results.csv"), encoding="utf-8")))
print(f"scored {len(res)} LLM-tail results vs point-in-time labels\n")
print(f"{'tkr':6}{'asof':12}{'model':8}{'label':>9}{'llm':>9}{'os_lbl':>8}{'os_err%':>8}  note")

rows = []
for r in res:
    k = (r["ticker"], r["as_of"])
    L = lab.get(k)
    if not L or not L["float_M"].strip():
        continue
    fl_lab = float(L["float_M"])
    os_lab = float(L["os_M"]) if L["os_M"].strip() else None
    try:
        fl_llm = float(r["float_M"])
    except (ValueError, TypeError):
        continue
    os_err = abs(fl_llm - fl_lab) / os_lab if os_lab else None
    fl_err = abs(fl_llm - fl_lab) / fl_lab if fl_lab else None
    rows.append({"t": r["ticker"], "a": r["as_of"], "model": r.get("model", ""),
                 "lab": fl_lab, "llm": fl_llm, "os_lab": os_lab,
                 "os_err": os_err, "fl_err": fl_err, "note": (r.get("note") or "")[:34]})

for x in sorted(rows, key=lambda z: -(z["os_err"] or 0)):
    print(f"{x['t']:6}{x['a']:12}{x['model']:8}{x['lab']:>9.2f}{x['llm']:>9.2f}"
          f"{(x['os_lab'] or 0):>8.2f}{(x['os_err']*100 if x['os_err'] is not None else 0):>7.1f}%  {x['note']}")

if rows:
    osr = [x["os_err"] for x in rows if x["os_err"] is not None]
    w5 = sum(1 for e in osr if e <= 0.05)
    w10 = sum(1 for e in osr if e <= 0.10)
    print(f"\n=== EXACT-FLOAT ACCURACY (O/S-relative, vs point-in-time labels) ===")
    print(f"  within 5%  : {w5}/{len(osr)} ({100*w5//len(osr)}%)")
    print(f"  within 10% : {w10}/{len(osr)} ({100*w10//len(osr)}%)")
    print(f"  median O/S-rel error: {statistics.median(osr)*100:.1f}%")
