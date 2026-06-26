"""OVERWRITE one (ticker, as_of) row in float_is.csv with a fresh (Opus) derivation, and log it.
Used by the Opus re-derivation pass over hard names — unlike record.py (append, skip-existing),
this REPLACES an existing row. Atomic (temp-file + os.replace) so a crash can't corrupt the
ledger. Appends '(ticker as_of)' to _redo_log.txt so the redo is resumable (redo-remaining =
target list minus _redo_log.txt).

Usage:  python record_redo.py TICKER AS_OF FLOAT_M OS_M CONF BASIS "NOTE"
"""
import sys, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "float_is.csv")
LOG = os.path.join(HERE, "_redo_log.txt")
DIFF = os.path.join(HERE, "_redo_diff.csv")             # full old->new audit trail
COLS = ["ticker", "as_of", "float_M", "os_M", "under_20M", "confidence", "basis", "note"]
DIFFCOLS = ["ticker", "as_of", "old_float_M", "old_os_M", "old_conf", "old_basis",
            "new_float_M", "new_os_M", "new_conf", "new_basis", "old_note", "new_note"]


def main(a):
    if len(a) < 6:
        print(__doc__); sys.exit(1)
    ticker, as_of, float_m, os_m, conf, basis = a[:6]
    note = a[6] if len(a) > 6 else ""
    if conf.lower() not in ("high", "med", "medium", "low"):
        print(f"ERROR: CONF must be high|med|low (got {conf!r}). You likely added an extra "
              f"under_20M argument — call EXACTLY: record_redo.py TICKER AS_OF FLOAT OS CONF BASIS \"NOTE\".")
        sys.exit(2)
    fm = float_m.strip()
    if fm.upper() in ("", "NA", "NONE"):
        fm, under = "", "false"
    else:
        under = "true" if float(fm) < 20 else "false"
    rows = list(csv.DictReader(open(CSV, newline="", encoding="utf-8")))
    found, old = False, None
    for r in rows:
        if r["ticker"] == ticker and r["as_of"] == as_of:
            old = dict(r)                                # preserve the prior (Sonnet) values
            r["float_M"], r["os_M"], r["under_20M"], r["confidence"], r["basis"], r["note"] = \
                fm, os_m, under, conf, basis, note
            found = True; break
    if old is not None:                                  # append old->new to the audit trail
        dnew = not os.path.exists(DIFF)
        with open(DIFF, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if dnew:
                w.writerow(DIFFCOLS)
            w.writerow([ticker, as_of, old["float_M"], old["os_M"], old["confidence"], old["basis"],
                        fm, os_m, conf, basis, old["note"], note])
            f.flush(); os.fsync(f.fileno())
    if not found:
        rows.append({"ticker": ticker, "as_of": as_of, "float_M": fm, "os_M": os_m,
                     "under_20M": under, "confidence": conf, "basis": basis, "note": note})
    tmp = CSV + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, CSV)
    with open(LOG, "a") as f:
        f.write(f"{ticker} {as_of}\n"); f.flush(); os.fsync(f.fileno())
    print(f"REDONE {ticker}@{as_of}: float_M={fm or '(blank,>20M)'} os_M={os_m} "
          f"under_20M={under} conf={conf} ({'replaced' if found else 'added'})")


if __name__ == "__main__":
    main(sys.argv[1:])
