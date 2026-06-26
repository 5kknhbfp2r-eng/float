"""Regenerate derived ledgers FROM float_is.csv (the single source of truth for all IS months):
  - engine/float_records.csv : native ledger keyed (ticker, as_of) for `float_backtest.py get T D`
  - float_may.csv            : the May-only subset (downstream warrior_float_may.py reads this)
Idempotent — run anytime; fully rebuilds both, so nothing can desync.

Run from float/ root with the venv python.
"""
import os, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "float_is.csv")
RECORDS = os.path.join(HERE, "engine", "float_records.csv")
MAY = os.path.join(HERE, "float_may.csv")
LCOLS = ["ticker", "as_of", "float_M", "os_M", "confidence", "basis", "computed_at", "note"]
MCOLS = ["ticker", "as_of", "float_M", "os_M", "under_20M", "confidence", "basis", "note"]


def main():
    rows = list(csv.DictReader(open(SRC, newline="", encoding="utf-8")))
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    with open(RECORDS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(LCOLS)
        for r in rows:
            w.writerow([r["ticker"], r["as_of"], r["float_M"], r["os_M"],
                        r["confidence"], r["basis"], now, r["note"]])
    may = [r for r in rows if r["as_of"].startswith("2025-05")]
    with open(MAY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MCOLS); w.writeheader()
        for r in may:
            w.writerow({k: r[k] for k in MCOLS})
    print(f"float_records.csv: {len(rows)} rows | float_may.csv: {len(may)} May rows "
          f"(regenerated from float_is.csv)")


if __name__ == "__main__":
    main()
