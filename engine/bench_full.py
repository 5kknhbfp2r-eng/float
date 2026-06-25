#!/usr/bin/env python3
"""Benchmark the FULL deterministic float (XBRL O/S - D&O group - strategic, 13G kept) against
the point-in-time labels in float_is.csv. Reports gate-match + exact-float error per archetype.
Run from engine/. Writes _bench_full.csv. Usage: bench_full.py [K_per_archetype]"""
import os, csv, sys, json, glob, random, statistics
import det_float as D
import float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
random.seed(7)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 25


def cik_map():
    m = {}
    for p in glob.glob(os.path.join(ROOT, "engine", "data", "_cache", "receipts", "*.json")):
        try:
            r = json.load(open(p, encoding="utf-8"))
            if r.get("cik"):
                m[(r["ticker"], r["as_of"])] = int(r["cik"])
        except Exception:
            pass
    return m


def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")))
    cm = cik_map()
    buckets = {}
    for r in rows:
        try:
            fl = float(r["float_M"]) if r["float_M"].strip() else None
        except ValueError:
            fl = None
        if fl is None:
            continue                                   # skip blank-float (>20M, no exact label)
        a = D.archetype(r["basis"], r["note"])
        buckets.setdefault(a, []).append((r, fl))
    sample = []
    for a, lst in buckets.items():
        random.shuffle(lst)
        sample += [(a, r, fl) for (r, fl) in lst[:K]]
    print(f"rows w/ exact float_M: {sum(len(v) for v in buckets.values())} | "
          f"sampling {K}/archetype -> {len(sample)}\n")

    out = []
    for a, r, fl in sample:
        t, asof = r["ticker"], r["as_of"]
        cik = cm.get((t, asof)) or fg.resolve_cik(t, asof)
        rec = {"ticker": t, "as_of": asof, "archetype": a, "float_label": fl,
               "under20_label": r["under_20M"].strip().lower() == "true", "conf_label": r["confidence"],
               "cik": cik, "float_det": "", "os": "", "os_src": "", "g_exo": "", "strat": "",
               "det_conf": "", "cls": "", "relerr": "", "os_relerr": "", "gate_match": "",
               "confident": ""}
        try:
            d = D.full(t, asof, cik)
            rec["cls"] = d.get("cls", "")
            if d.get("cls") == "ok":
                fd = d["float_det"]
                rec.update(float_det=round(fd, 3), os=round(d["os"], 3), os_src=d["os_src"],
                           g_exo=round(d["g_exo"], 3), strat=round(d["strat"], 3),
                           det_conf=d["conf"])
                rec["relerr"] = round(abs(fd - fl) / fl, 4) if fl else ""
                rec["os_relerr"] = round(abs(fd - fl) / d["os"], 4) if d["os"] else ""
                rec["gate_match"] = (fd < 20) == (fl < 20)
                # L7: ABSTAIN when uncertain -> route to the LLM (accuracy preserved).
                # NB 'noderiv' (no options to subtract) is NOT uncertainty -> stays confident.
                # SPAC redeemable / scaled / ADS / multiclass / nogroup bases ARE uncertain.
                unc = (any(k in d["conf"] for k in ("multiclass", "nogroup", "misparse",
                                                    "nil-group", "spac", "scaled", "ads"))
                       or d["os_src"] != "xbrl" or d.get("xbrl_n") not in ("", 1, None)
                       or fd <= 0 or fd > d["os"] * 1.01)
                rec["confident"] = not unc
        except Exception as e:
            rec["cls"] = f"ERR:{type(e).__name__}"
        out.append(rec)

    with open(os.path.join(ROOT, "_bench_full.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    def stats(rs):
        comp = [r for r in rs if r["cls"] == "ok"]
        gm = [r for r in comp if r["gate_match"] is True]
        e2 = [r for r in comp if r["relerr"] != "" and r["relerr"] <= 0.02]
        e5 = [r for r in comp if r["relerr"] != "" and r["relerr"] <= 0.05]
        med = statistics.median([r["relerr"] for r in comp if r["relerr"] != ""]) if comp else None
        return len(comp), len(gm), len(e2), len(e5), med

    print(f"{'archetype':17s} {'N':>3} {'comp':>4} {'gate✓':>6} {'≤2%':>4} {'≤5%':>4} {'medErr':>7}")
    for a in sorted(buckets):
        rs = [r for r in out if r["archetype"] == a]
        if not rs:
            continue
        c, gm, e2, e5, med = stats(rs)
        print(f"{a:17s} {len(rs):>3} {c:>4} {gm:>6} {e2:>4} {e5:>4} "
              f"{(f'{med*100:.1f}%' if med is not None else '-'):>7}")
    c, gm, e2, e5, med = stats(out)
    N = len(out)
    print(f"{'TOTAL':17s} {N:>3} {c:>4} {gm:>6} {e2:>4} {e5:>4} "
          f"{(f'{med*100:.1f}%' if med is not None else '-'):>7}")
    print(f"\ncomputed a float: {c}/{N} ({100*c//N}%)")
    print(f"gate-match (of computed): {gm}/{c} ({100*gm//max(1,c)}%)  | of ALL: {100*gm//N}%")
    print(f"exact float ≤5%: {e5}/{c} ({100*e5//max(1,c)}% of computed)")

    # ---- L7 reframe: the REAL cost/accuracy metric = coverage x accuracy-on-confident ----
    conf = [r for r in out if r["confident"] is True]
    cb = [r for r in conf if r["os_relerr"] != "" and r["os_relerr"] <= 0.05]
    cg = [r for r in conf if r["gate_match"] is True]
    abst = N - len(conf)                                   # abstained -> routed to the LLM
    print(f"\n=== COVERAGE x ACCURACY (the real cost/accuracy metric) ===")
    print(f"  confident coverage : {len(conf)}/{N} ({100*len(conf)//N}%)  -> deterministic, ~$0")
    print(f"  abstained -> LLM   : {abst}/{N} ({100*abst//N}%)  -> the per-name LLM cost")
    if conf:
        print(f"  accuracy ON confident: O/S≤5% {len(cb)}/{len(conf)} ({100*len(cb)//len(conf)}%)  "
              f"| gate {len(cg)}/{len(conf)} ({100*len(cg)//len(conf)}%)")
    # failure census
    cens = {}
    for r in out:
        if r["cls"] != "ok":
            cens[r["cls"]] = cens.get(r["cls"], 0) + 1
    if cens:
        print("non-computed census:", dict(sorted(cens.items(), key=lambda kv: -kv[1])))
    print("full rows -> _bench_full.csv")


if __name__ == "__main__":
    main()
