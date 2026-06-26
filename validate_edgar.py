"""VALIDATION GATE (deterministic layer): confirm the EDGAR-only engine reproduces the
O/S basis that the sec-api-era run recorded, for EVERY already-done May name.

For each done row in float_may.csv, re-run the EDGAR gatherer at the SAME May as_of and
check that the O/S figures it SURFACES (current periodic + proxy cover) still contain the
recorded os_M. Any name that does NOT reproduce is printed as a MISMATCH for investigation
(it would indicate EDGAR selected a different filing than sec-api did).

This is the data-layer proof; a separate agent re-derives the FULL float (float_M) blind.

Run from float/ root with the venv python (PYTHONUTF8=1).  Arg: 'all' (default) or N names.
"""
import sys, os, re, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
import float_gather as fg


def nums(strs):
    out = []
    for s in strs:
        for m in re.finditer(r"\d{1,3}(?:,\d{3})+|\d{7,}", s):
            out.append(int(m.group(0).replace(",", "")))
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rows = [r for r in csv.DictReader(open(os.path.join(here, "float_may.csv"), newline="", encoding="utf-8"))]
    lim = None if (len(sys.argv) < 2 or sys.argv[1] == "all") else int(sys.argv[1])
    if lim:
        rows = rows[:lim]
    mism, n_ok, n = [], 0, 0
    for r in rows:
        tk, asof, rec_os = r["ticker"], r["as_of"], r["os_M"]
        if not rec_os:
            continue
        rec_raw = float(rec_os) * 1e6
        try:
            cik = fg.resolve_cik(tk)
            cand = []
            cur = fg._current_os(cik, asof)
            if cur:
                cand += cur[2]
            f = fg._pick_own(cik, asof)
            if f:
                cand += fg._os_candidates(fg._text(f))
            cands = nums(cand)
        except Exception as e:
            cands = []
            cur = None
        hit = any(abs(c - rec_raw) / max(rec_raw, 1) <= 0.01 for c in cands)
        n += 1
        if hit:
            n_ok += 1
        else:
            top = ",".join(f"{c/1e6:.4g}" for c in sorted(set(cands), reverse=True)[:5]) or "(none)"
            mism.append((tk, asof, rec_os, top, cur[0] + " " + cur[1] if cur else "no periodic"))
    print(f"\n=== EDGAR O/S reproduction across {n} done names: {n_ok}/{n} reproduce recorded os_M (<=1%) ===")
    if mism:
        print(f"\n{len(mism)} to investigate (EDGAR did not surface the recorded os_M):")
        print(f"  {'ticker':6} {'as_of':10} {'rec os_M':10} {'EDGAR surfaced (M)':30} latest periodic")
        for tk, asof, ro, top, per in mism:
            print(f"  {tk:6} {asof:10} {ro:<10} {top:30} {per}")
    else:
        print("\nAll done names reproduce — no mismatches.")


if __name__ == "__main__":
    main()
