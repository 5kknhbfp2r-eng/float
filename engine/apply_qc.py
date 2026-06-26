#!/usr/bin/env python3
"""Apply the INDEPENDENTLY-CONFIRMED label-QC corrections to float_is.csv (auditable, reversible via git).
Only the 3 tickers that survived primary-filing spot-checking (ANNA, BNGO, ATNF) — NOT the workflow's
ARBKL/BMGL (agents demonstrably wrong) or TGEN/WHLR (unresolved). Each correction records its reason.
"""
import os, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "float_is.csv")

# (ticker, as_of) -> (float_M, os_M, reason)
FIX = {
    ("ANNA", "2025-06-25"): (3.53, 40.66, "QC 2026-06-26: Wilder control (SC 13D) excl = LISTED Class A 37.13M "
        "(Nautilus 30,478,724 = 75.05% of Class A + Foundation 6,655,470); 10-Q cover 40,659,881 Class A. Prior "
        "label wrongly treated listed Class A as exchangeable Class C (25.99M Class C/HoldCo units are additive, "
        "not in the Class A O/S). Float = 40.66 - 37.13 = 3.53."),
    ("ANNA", "2025-07-29"): (3.53, 40.66, "QC 2026-06-26: carried; no Class A offering 6/25-7/29. Wilder listed "
        "Class A excl 37.13M; float 40.66 - 37.13 = 3.53 (prior label inverted listed vs exchangeable)."),
    ("BNGO", "2025-05-14"): (3.362, 3.364, "QC 2026-06-26: 10-Q cover 'As of May 7, 2025, 3,364,000 shares' (prior "
        "os 1.865M wrong). No control holder; CVI Investments passive 13G (5/12) kept; D&O ~0.002M. Float 3.362."),
    ("BNGO", "2025-08-21"): (4.68, 4.681, "QC 2026-06-26: 10-Q cover 'As of August 7, 2025, 4,681,000 shares' "
        "(prior os 1.865M stale). Same DEF 14A, no control; float ~= O/S 4.681 - D&O ~0.002 = 4.68."),
    ("ATNF", "2025-07-29"): (3.73, 6.039, "QC 2026-06-26: float = O/S 6,039,208 - D&O group 2,309,883 (incl Elray "
        "1,318,000 control via board voting agreement; Elray's reported 4.318M includes 3M warrants NOT in O/S). "
        "Prior label kept the Elray control block. Float 3.73."),
}

rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
hdr = rows[0].keys()
n = 0
for r in rows:
    key = (r["ticker"], r["as_of"][:10])
    if key in FIX:
        f, o, why = FIX[key]
        old = (r["float_M"], r["os_M"])
        r["float_M"] = f"{f}"
        r["os_M"] = f"{o}"
        r["under_20M"] = "true" if f < 20 else "false"
        r["note"] = (r["note"] + "  || " + why) if r["note"] else why
        n += 1
        print(f"  {key[0]:5} {key[1]}  float {old[0]}->{f}  os {old[1]}->{o}")

with open(SRC, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(hdr))
    w.writeheader()
    w.writerows(rows)
print(f"\napplied {n} corrections to {SRC}")
