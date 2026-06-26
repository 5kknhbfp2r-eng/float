#!/usr/bin/env python3
"""(F28) BOUND the D&O-drift error of carrying dno_M fixed in shares between proxies.

The recipe carries the proxy "officers+directors as a group" block fixed (in shares) and re-fires the
LLM only when a NEW proxy/ownership source appears (recipe_cache proxy-changed guard). So the carried
block can only drift via insider Form-4 activity WITHIN one proxy's validity window. The replay sim
can't measure this (replay and label share the same proxy between re-derivations), so measure it
directly: for each multi-day IS ticker, parse the "as a group" total from its two most-recent proxies
<= a recent date and report |Δgroup| / O/S — the ANNUAL proxy-to-proxy drift, an UPPER BOUND on the
sub-annual intra-recipe drift the fixed carry actually incurs.
"""
import os, sys, csv, json, collections, statistics
import float_gather as fg
import det_float as D
import _widen_probe as wp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
PROXIES = ["DEF 14A", "DEFM14A", "DEFR14A"]


def group_total(cik, asof):
    """The proxy 'as a group' officer+director block (shares), via the production extractor."""
    f = fg._pick_own(cik, asof)
    if not f or f["formType"] not in PROXIES:
        return None, None
    text = fg._text(f).translate(wp.ZW)
    gm = wp.GROUP2.search(text)
    if not gm:
        return None, f["filedAt"][:10]
    ge = wp.group_exoptions(text, 1e9)        # os only caps misparse; we want the raw group shares
    if not ge:
        return None, f["filedAt"][:10]
    g_exo, benef, conf, iosb = ge
    return (benef or g_exo), f["filedAt"][:10]


work = json.load(open(os.path.join(ROOT, "_emit_worklist.json"), encoding="utf-8"))
rows, drifts = [], []
for w in work[:N]:
    t, cik = w["ticker"], w["cik"]
    if not cik:
        continue
    # two most-recent distinct proxies (latest, and the one before it)
    pf = fg._query(cik, PROXIES, "2026-06-04", size=8, order="desc")
    days = []
    seen = set()
    for f in pf:
        d = f["filedAt"][:10]
        if d not in seen:
            seen.add(d); days.append(d)
        if len(days) >= 2:
            break
    if len(days) < 2:
        continue
    g_new, dn = group_total(cik, days[0])
    g_old, do = group_total(cik, days[1])
    if not g_new or not g_old:
        continue
    os_ = (D.xbrl_os(cik, days[0]) or {}).get("val_M")
    if not os_:
        continue
    drift = abs(g_new - g_old)
    rel = drift / os_
    drifts.append(rel)
    rows.append((t, round(g_old, 3), round(g_new, 3), round(drift, 3), round(os_, 2),
                 f"{rel*100:.2f}%", do, dn))

rows.sort(key=lambda r: -float(r[5][:-1]))
print(f"{'ticker':7} {'g_old':>8} {'g_new':>8} {'|Δ|M':>7} {'os_M':>8} {'Δ/OS':>7}  proxies")
for r in rows:
    print(f"{r[0]:7} {r[1]:8} {r[2]:8} {r[3]:7} {r[4]:8} {r[5]:>7}  {r[6]}..{r[7]}")
if drifts:
    print(f"\nmeasured {len(drifts)} tickers (annual proxy-to-proxy D&O drift / O/S):")
    print(f"  median {statistics.median(drifts)*100:.2f}% | mean {statistics.mean(drifts)*100:.2f}% "
          f"| p90 {sorted(drifts)[int(0.9*len(drifts))]*100:.2f}% | max {max(drifts)*100:.2f}%")
    print(f"  >2% of O/S: {sum(d>0.02 for d in drifts)}/{len(drifts)} | "
          f">5%: {sum(d>0.05 for d in drifts)}/{len(drifts)}")
    print("  (this is the ANNUAL bound; intra-recipe drift between the recipe proxy and the next is less)")
