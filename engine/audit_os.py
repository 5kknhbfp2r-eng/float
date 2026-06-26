#!/usr/bin/env python3
"""Systematic label-error finder: cross-check every float_is.csv label's os_M against the
point-in-time XBRL dei O/S (corroborated by the regex cover-page leg). HIGH-PRECISION flags only —
restricted to cases where XBRL is RELIABLE so a disagreement implicates the LABEL, not the XBRL:
  - single-class XBRL fact (n_at_pick == 1; multi-class is ambiguous -> skip)
  - fresh fact (end within 120d of as_of; stale annual/foreign facts -> skip)
  - corroborated: regex O/S agrees with XBRL within 12% (or regex absent)
  - the gap is NOT a clean integer ratio >=2 (that's an ADS/split ratio, label likely right -> skip)
Flags |label_os - xbrl_os| / max > 0.15. Also flags float>os (impossible). Resume-safe CSV.
These are CANDIDATES -> each must still be independently verified against the primary filing.
"""
import os, sys, csv, datetime as dt
import det_float as D, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_audit_os.csv")
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8"))
        if r["float_M"].strip() and r["os_M"].strip()]

done = set()
if os.path.exists(OUT):
    done = {(r["ticker"], r["as_of"]) for r in csv.DictReader(open(OUT, encoding="utf-8"))}
new = not os.path.exists(OUT)
fh = open(OUT, "a", newline="", encoding="utf-8"); w = csv.writer(fh)
if new:
    w.writerow(["ticker", "as_of", "label_os", "xbrl_os", "regex_os", "label_float",
                "gap_pct", "flag", "xbrl_end", "n_class"])

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
todo = [r for r in rows if (r["ticker"], r["as_of"]) not in done][:LIMIT]
print(f"{len(rows)} labels | {len(done)} done | auditing {len(todo)}")


def near_int_ratio(a, b):
    hi, lo = max(a, b), min(a, b)
    if lo <= 0:
        return False
    r = hi / lo
    return r >= 1.8 and abs(r - round(r)) <= 0.12      # ~ADS/split ratio (2:1, 8:1, 10:1...)


for i, r in enumerate(todo):
    t, a = r["ticker"], r["as_of"]
    lo = float(r["os_M"]); lf = float(r["float_M"])
    cik = fg.resolve_cik(t, a[:10])
    x = D.xbrl_os(cik, a[:10]) if cik else None
    g = D.regex_os(cik, a[:10]) if cik else None
    xv = (x or {}).get("val_M"); gv = (g or {}).get("val_M")
    nclass = (x or {}).get("n_at_pick") or 0
    end = (x or {}).get("end", "")
    flag = ""
    if lf > lo * 1.02:
        flag = "float>os"
    elif xv and nclass == 1 and end:
        fresh = (dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(end)).days <= 120
        corrob = (gv is None) or (abs(xv - gv) / max(xv, gv) <= 0.12)
        gap = abs(lo - xv) / max(lo, xv)
        if fresh and corrob and gap > 0.15 and not near_int_ratio(lo, xv):
            flag = "os-mismatch"
    gap = abs(lo - xv) / max(lo, xv) if xv else 0
    if flag:
        w.writerow([t, a[:10], f"{lo:.3f}", f"{xv:.3f}" if xv else "", f"{gv:.3f}" if gv else "",
                    f"{lf:.3f}", f"{gap*100:.0f}", flag, end, nclass]); fh.flush()
    if (i + 1) % 100 == 0:
        print(f"  ...{i+1}/{len(todo)}")
fh.close()
print(f"done -> {OUT}")
