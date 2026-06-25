"""Append ONE derived per-(ticker, day) float to float_is.csv (the master IS ledger) and flush
immediately. Durable, interruption-resilient: one row per (ticker, as_of), written the instant
it's derived, so a usage stop loses nothing and a re-spawn resumes from this file.

float_is.csv is the SINGLE source of truth for ALL in-sample months (May-Aug 2025). The native
ledger engine/float_records.csv and the May-subset float_may.csv are REGENERATED from it by
sync_records.py -- never written here -- so nothing can desync.

Schema: ticker,as_of,float_M,os_M,under_20M,confidence,basis,note
  under_20M derived: (float_M < 20) when float_M numeric; 'false' when float_M left blank.

Usage:  python record.py TICKER AS_OF FLOAT_M OS_M CONF BASIS "NOTE"
Idempotent on (TICKER, AS_OF): re-recording the same ticker+day is refused; the same ticker on a
DIFFERENT day is allowed (point-in-time per day).
"""
import sys, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "float_is.csv")
COLS = ["ticker", "as_of", "float_M", "os_M", "under_20M", "confidence", "basis", "note"]


def main(a):
    if len(a) < 6:
        print(__doc__); sys.exit(1)
    ticker, as_of, float_m, os_m, conf, basis = a[:6]
    note = a[6] if len(a) > 6 else ""
    if conf.lower() not in ("high", "med", "medium", "low"):
        print(f"ERROR: CONF must be high|med|low (got {conf!r}). You likely added an extra "
              f"under_20M argument — call EXACTLY: record.py TICKER AS_OF FLOAT OS CONF BASIS \"NOTE\".")
        sys.exit(2)
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
