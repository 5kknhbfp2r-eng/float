#!/usr/bin/env python3
"""The simulation carried a plain 'normal' recipe for EVERY ticker — including foreign/ADS,
multi-class, split/reverse and IPO names that the engine already abstains on. Re-measure honestly:
gate free-replay eligibility on det_float.is_confident AT THE DERIVATION DAY (the archetypes the real
system would carry as clean normal recipes) vs the rest (which route to the LLM). Report accuracy for
each bucket — the clean bucket is the system's true free-replay domain.
"""
import os, csv, collections
import det_float as D, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "_sim_replay.csv"), encoding="utf-8"))]

# det confidence + archetype at each ticker's derivation day (cached per ticker)
conf = {}
for t in sorted({r["ticker"] for r in rows}):
    der = next(r["derived_day"] for r in rows if r["ticker"] == t)
    cik = fg.resolve_cik(t, der)
    try:
        d = D.full(t, der, cik)
        conf[t] = (D.is_confident(d), d.get("conf", d.get("cls", "?")))
    except Exception as e:
        conf[t] = (False, "err:" + type(e).__name__)

ok = [r for r in rows if r["status"] == "ok" and r["err_os_rel"] != ""]
for r in ok:
    r["_conf"] = conf.get(r["ticker"], (False, "?"))[0]
    r["_err"] = float(r["err_os_rel"])

def acc(pop, label):
    if not pop:
        print(f"{label}: (none)"); return
    e = sorted(x["_err"] for x in pop)
    n = len(e)
    w5 = sum(x <= 0.05 for x in e); w10 = sum(x <= 0.10 for x in e); miss = sum(x > 0.10 for x in e)
    print(f"{label}: n={n} | <=5% {w5}({100*w5//n}%) | <=10% {w10}({100*w10//n}%) | >10% {miss}({100*miss//n}%) "
          f"| median {e[n//2]*100:.1f}%")

confident = [r for r in ok if r["_conf"]]
notconf   = [r for r in ok if not r["_conf"]]
print(f"=== free replays by DERIVATION-DAY confidence ===")
acc(ok,        "ALL free (naive sim)        ")
acc(confident, "det-CONFIDENT at derivation ")
acc(notconf,   "det-ABSTAINED at derivation ")

# how many tickers/days does the confident gate keep?
n_conf_tk = sum(1 for t, (c, _) in conf.items() if c)
print(f"\nmulti-day tickers det-confident at derivation: {n_conf_tk}/{len(conf)}")
print(f"free-replay later-days in confident bucket: {len(confident)} (of {len(ok)} naive-free, {383} total later-days)")

print("\n>10% misses REMAINING in the confident bucket (the real problem cases):")
for r in sorted([r for r in confident if r["_err"] > 0.10], key=lambda r: -r["_err"]):
    print(f"  {r['ticker']:6} {r['day']} err={r['_err']*100:4.0f}% {r['archetype']:16} conf={conf[r['ticker']][1]}")
