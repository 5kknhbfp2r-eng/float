#!/usr/bin/env python3
"""A/B the L1 13D/13G leg on the SAME sample: USE_13DG off vs on. Reports the cost/accuracy
metric (confident coverage x O/S-relative accuracy on confident) + the error census shift."""
import os, csv, sys, json, glob, random, statistics
import det_float as D
import float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
random.seed(7)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 10


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


def confident(d, fl):
    if d.get("cls") != "ok":
        return None
    fd, os_ = d["float_det"], d["os"]
    osre = abs(fd - fl) / os_ if os_ else None
    return {"confident": D.is_confident(d), "osre": osre, "fd": fd}


def run(sample, cm, flag):
    D.USE_13DG = flag
    out = []
    for a, r, fl in sample:
        cik = cm.get((r["ticker"], r["as_of"])) or fg.resolve_cik(r["ticker"], r["as_of"])
        try:
            c = confident(D.full(r["ticker"], r["as_of"], cik), fl)
        except Exception:
            c = None
        out.append(c)
    return out


def report(name, res, N):
    comp = [c for c in res if c]
    conf = [c for c in comp if c["confident"]]
    cb = [c for c in conf if c["osre"] is not None and c["osre"] <= 0.05]
    print(f"  {name:8} coverage {len(conf):3}/{N} ({100*len(conf)//N:2}%)  "
          f"exact O/S≤5%-on-conf {len(cb):3}/{max(1,len(conf)):3} ({100*len(cb)//max(1,len(conf)):2}%)")


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
            continue
        buckets.setdefault(D.archetype(r["basis"], r["note"]), []).append((r, fl))
    sample = []
    for a, lst in buckets.items():
        random.shuffle(lst)
        sample += [(a, r, fl) for (r, fl) in lst[:K]]
    N = len(sample)
    print(f"A/B on {N} names (K={K}/archetype)\n=== COST/ACCURACY (coverage x accuracy-on-confident) ===")
    off = run(sample, cm, False)
    report("OFF", off, N)
    on = run(sample, cm, True)
    report("ON-13dg", on, N)


if __name__ == "__main__":
    main()
