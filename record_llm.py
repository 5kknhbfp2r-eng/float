#!/usr/bin/env python3
"""Durable, resume-safe recorder for the LLM-tail run. Appends one float result to
_llm_tail_results.csv, deduped on (ticker, as_of) so a re-run skips done names.
Usage: record_llm.py TICKER AS_OF FLOAT_M OS_M CONF MODEL "NOTE" """
import sys, csv, os

ROOT = os.path.dirname(os.path.abspath(__file__))
HDR = ["ticker", "as_of", "float_M", "os_M", "conf", "model", "note"]
t, a, fl, osm, conf, model, note = (sys.argv[1:8] + [""] * 7)[:7]
outfile = sys.argv[8] if len(sys.argv) > 8 else "_llm_tail_results.csv"   # Opus pass -> separate file
P = os.path.join(ROOT, outfile)

done = set()
if os.path.exists(P):
    for r in csv.DictReader(open(P, encoding="utf-8")):
        done.add((r["ticker"], r["as_of"]))
if (t, a) in done:
    print(f"already recorded {t} {a}")
    sys.exit(0)

new = not os.path.exists(P)
with open(P, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if new:
        w.writerow(HDR)
    w.writerow([t, a, fl, osm, conf, model, note])
print(f"recorded {t} {a} float={fl} os={osm}")
