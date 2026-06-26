"""RETIRED (F40). float_may.csv is now a DERIVED artifact — sync_records.py REGENERATES it from
float_is.csv, so any row written here is silently destroyed on the next sync, and (unlike record.py)
this script never had the confidence/column-shift guard. Record via record.py (the single validated
writer), then run sync_records.py. Kept only so stale references don't ImportError; __main__ refuses.

Schema (float_may.csv): ticker,as_of,float_M,os_M,under_20M,confidence,basis,note
  under_20M is derived: (float_M < 20) when float_M numeric; 'false' when float_M left blank.

Usage:
  python record_may.py TICKER AS_OF FLOAT_M OS_M CONF BASIS "NOTE"
Idempotent on (TICKER, AS_OF): re-recording the same ticker+day is refused; the SAME ticker on
a DIFFERENT day is allowed (point-in-time per day).
"""
import sys, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "float_may.csv")
COLS = ["ticker", "as_of", "float_M", "os_M", "under_20M", "confidence", "basis", "note"]


def main(a):
    sys.exit("record_may.py is RETIRED: float_may.csv is a DERIVED artifact (regenerated from "
             "float_is.csv by sync_records.py) — rows written here are silently overwritten. "
             "Use record.py (the single validated writer), then sync_records.py.")
    ticker, as_of, float_m, os_m, conf, basis = a[:6]
    note = a[6] if len(a) > 6 else ""
    seen = set()
    if os.path.exists(CSV):
        seen = {(r["ticker"], r["as_of"]) for r in csv.DictReader(open(CSV, newline=""))}
    if (ticker, as_of) in seen:
        print(f"SKIP {ticker}@{as_of}: already recorded -- not overwriting.")
        return
    fm = float_m.strip()
    if fm.upper() in ("", "NA", "NONE"):
        fm, under = "", "false"
    else:
        under = "true" if float(fm) < 20 else "false"
    new = not os.path.exists(CSV)
    with open(CSV, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([ticker, as_of, fm, os_m, under, conf, basis, note])
        f.flush(); os.fsync(f.fileno())
    print(f"RECORDED {ticker}@{as_of}: float_M={fm or '(blank,>20M)'} os_M={os_m} "
          f"under_20M={under} conf={conf}")


if __name__ == "__main__":
    main(sys.argv[1:])
