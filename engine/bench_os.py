#!/usr/bin/env python3
"""Benchmark the deterministic O/S leg against the labeled float_is.csv.

Cheap proof: sample K rows per archetype, fetch XBRL + regex O/S, compare to recorded os_M.
Run from engine/ dir. Writes _bench_os.csv with every row for later full + DT cross-check.
"""
import os, csv, sys, json, glob, random
import det_float as D
import float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
random.seed(7)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 25           # per-archetype cap


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


def relerr(a, b):
    return abs(a - b) / b if b else None


def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")))
    cm = cik_map()
    # group by archetype, keep only rows with a usable os_M label
    buckets = {}
    for r in rows:
        try:
            osm = float(r["os_M"]) if r["os_M"].strip() else None
        except ValueError:
            osm = None
        if not osm:
            continue
        a = D.archetype(r["basis"], r["note"])
        buckets.setdefault(a, []).append((r, osm))
    sample = []
    for a, lst in buckets.items():
        random.shuffle(lst)
        sample += [(a, r, osm) for (r, osm) in lst[:K]]
    print(f"universe rows w/ os_M: {sum(len(v) for v in buckets.values())} | "
          f"archetypes: { {a: len(v) for a, v in buckets.items()} }")
    print(f"sampling up to {K}/archetype -> {len(sample)} rows\n")

    out = []
    for a, r, osm in sample:
        t, asof = r["ticker"], r["as_of"]
        cik = cm.get((t, asof)) or fg.resolve_cik(t, asof)
        rec = {"ticker": t, "as_of": asof, "archetype": a, "os_M_label": osm,
               "cik": cik, "xbrl_M": "", "xbrl_n": "", "xbrl_form": "",
               "regex_M": "", "xbrl_relerr": "", "regex_relerr": ""}
        if cik:
            try:
                x = D.xbrl_os(cik, asof)
                if x:
                    rec["xbrl_M"] = round(x["val_M"], 3)
                    rec["xbrl_n"] = x["n_at_pick"]
                    rec["xbrl_form"] = x["form"]
                    rec["xbrl_relerr"] = round(relerr(x["val_M"], osm), 4)
            except Exception as e:
                rec["xbrl_form"] = f"ERR:{type(e).__name__}"
            try:
                g = D.regex_os(cik, asof)
                if g:
                    rec["regex_M"] = round(g["val_M"], 3)
                    rec["regex_relerr"] = round(relerr(g["val_M"], osm), 4)
            except Exception:
                pass
        out.append(rec)

    # write full results
    with open(os.path.join(ROOT, "_bench_os.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    # report
    def summ(rows, key):
        rk = key.replace("_M", "_relerr")
        got = [r for r in rows if r[key] != ""]
        within1 = [r for r in got if r[rk] != "" and r[rk] <= 0.01]
        within5 = [r for r in got if r[rk] != "" and r[rk] <= 0.05]
        return len(got), len(within1), len(within5)

    print(f"{'archetype':18s} {'N':>3} | {'XBRL got':>8} {'≤1%':>4} {'≤5%':>4} | {'rgx got':>7} {'≤1%':>4} {'≤5%':>4}")
    for a in sorted(buckets):
        rs = [r for r in out if r["archetype"] == a]
        if not rs:
            continue
        xg, x1, x5 = summ(rs, "xbrl_M")
        rg, r1, r5 = summ(rs, "regex_M")
        print(f"{a:18s} {len(rs):>3} | {xg:>8} {x1:>4} {x5:>4} | {rg:>7} {r1:>4} {r5:>4}")
    xg, x1, x5 = summ(out, "xbrl_M")
    rg, r1, r5 = summ(out, "regex_M")
    print(f"{'TOTAL':18s} {len(out):>3} | {xg:>8} {x1:>4} {x5:>4} | {rg:>7} {r1:>4} {r5:>4}")
    print(f"\nXBRL: got {xg}/{len(out)} ({100*xg//len(out)}%), ≤1% on {x1} ({100*x1//max(1,xg)}% of got)")
    print(f"REGEX: got {rg}/{len(out)} ({100*rg//len(out)}%), ≤1% on {r1} ({100*r1//max(1,rg)}% of got)")
    print("full rows -> _bench_os.csv")


if __name__ == "__main__":
    main()
