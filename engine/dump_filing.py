#!/usr/bin/env python3
"""Dump the primary text of a filing for point-in-time float verification.

  python dump_filing.py CIK "FORM" [ASOF] [MAXCHARS]
    FORM   e.g. "DEF 14A", "SC 13D", "SC 13D/A", "10-Q", "10-K", "20-F", "424B4", "8-K"
    ASOF   only filings filed <= ASOF (default 2026-06-04); newest matching wins
    MAXCHARS default 45000

Prints the form/date header + the (zero-width-stripped) text so an agent can read the ownership
table, the 13D reporting-person/aggregate rows, exchangeable/convertible-unit footnotes, ADS ratio,
reverse-split mechanics, and the listed-class cover O/S — the things float verdicts turn on.
"""
import os, sys
import float_gather as fg, edgar
import _widen_probe as wp

cik = int(sys.argv[1])
form = sys.argv[2]
asof = sys.argv[3] if len(sys.argv) > 3 else "2026-06-04"
maxc = int(sys.argv[4]) if len(sys.argv) > 4 else 45000

hits = edgar.query(cik, [form], asof, size=4, order="desc")
if not hits:
    print(f"(no {form} filed <= {asof} for CIK {cik})")
    sys.exit(0)
f = hits[0]
print(f"== {f['formType']} filed {f['filedAt'][:10]} (CIK {cik}, <= {asof}) ==")
try:
    t = fg._text(f).translate(wp.ZW)
except Exception as e:
    print("(text fetch failed:", e, ")"); sys.exit(0)
print(t[:maxc])
