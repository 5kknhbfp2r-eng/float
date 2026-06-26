#!/usr/bin/env python3
"""Triage _audit_os.csv os-mismatch flags: separate XBRL-STALE (label likely RIGHT) from genuine
LABEL-ERROR candidates. The XBRL fact predates the as_of; if a share-changing event happened in
between, XBRL is stale and the label (which read the later number) is fine:
  - label > xbrl  -> an OFFERING (424B*/S-1 EFFECT) in (xbrl_end, as_of] explains the bigger label
  - label < xbrl  -> a REVERSE SPLIT (8-K 'reverse split'+ratio) in (xbrl_end, as_of] explains it
A flag with NO such event is a real candidate (the label disagrees with a fresh, corroborated XBRL
for no structural reason) -> verify against the primary filing.
"""
import os, re, csv, datetime as dt
import edgar, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
flags = [r for r in csv.DictReader(open(os.path.join(ROOT, "_audit_os.csv"), encoding="utf-8"))
         if r["flag"] == "os-mismatch"]
OFFER = ["424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "S-1MEF", "EFFECT", "POS AM"]
_RS = re.compile(r"reverse\s+(?:stock\s+)?split", re.I)
_RT = re.compile(r"\b(?:1[-\s]?for[-\s]?\d{1,3}|\d{1,3}[-\s]?for[-\s]?1|1[-:]\s?\d{1,3})\b", re.I)
ck = {}

def cik(t, a):
    ck[t] = ck.get(t) or fg.resolve_cik(t, a)
    return ck[t]

def offering_between(c, lo, hi):
    return any(lo < f["filedAt"][:10] <= hi for f in edgar.query(c, OFFER, hi, size=40))

def split_between(c, lo, hi):
    for f in edgar.query(c, ["8-K", "8-K/A"], hi, size=40):
        if lo < f["filedAt"][:10] <= hi:
            try:
                t = fg._text(f)
            except Exception:
                continue
            if _RS.search(t) and _RT.search(t):
                return True
    return False

cand, stale = [], []
for r in flags:
    t, a = r["ticker"], r["as_of"]
    lo, xv, end = float(r["label_os"]), float(r["xbrl_os"]), r["xbrl_end"]
    c = cik(t, a)
    if not c or not end:
        continue
    if lo > xv:
        why = "offering" if offering_between(c, end, a) else None
    else:
        why = "rev-split" if split_between(c, end, a) else None
    (stale if why else cand).append((r, why))

print(f"{len(flags)} os-mismatch flags -> {len(cand)} REAL candidates | {len(stale)} XBRL-stale (label likely OK)\n")
print("=== REAL label-error candidates (no structural event explains the gap) ===")
for r, _ in sorted(cand, key=lambda x: -float(x[0]["gap_pct"])):
    print(f"  {r['ticker']:6} {r['as_of']} label_os={r['label_os']:>9} xbrl={r['xbrl_os']:>9} "
          f"regex={r['regex_os']:>9} gap={r['gap_pct']}% float={r['label_float']} end={r['xbrl_end']}")
print("\n=== XBRL-stale (label read the later number; SKIP) ===")
for r, why in sorted(stale, key=lambda x: -float(x[0]["gap_pct"])):
    print(f"  {r['ticker']:6} {r['as_of']} gap={r['gap_pct']}% [{why}]")
