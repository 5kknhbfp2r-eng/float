#!/usr/bin/env python3
"""float_backtest.py — turnkey entry point for getting a ticker's POINT-IN-TIME float in a
backtest and recording it to a file. Claude-in-the-loop (no API key): a session runs `dossier`,
reads it per FLOAT_PROTOCOL.md + FLOAT_PLAYBOOK.md, then `record`s the answer. Results persist in
`float_records.csv`, so `get` returns a cached value instantly on later runs.

WORKFLOW for a future backtest session (ticker T, trading date D = as_of, format YYYY-MM-DD):
  1. python float_backtest.py get T D                 # cache hit? use it, done.
  2. python float_backtest.py dossier T D             # else: prints the point-in-time dossier
        # READ it; follow FLOAT_PROTOCOL (current O/S from latest periodic ≤ D; exclude officers+
        # directors+control-affiliates+non-passive >20%; KEEP passive 13G/index; reconcile
        # splits/ADS/dilution via the ⚠ RECONCILIATION block). Fetch more with
        # `import float_gather as fg; fg.list_filings(T,D)` / fg.fetch_one(T,acc,what=...).
  3. python float_backtest.py record T D <float_M> <os_M> <conf high|med|low> <basis> "<note>"
  NEVER DROP: if you can't pin it, record confidence=low with your best estimate + the blocker;
  `python float_review.py` (or float_review.triage) routes low/near-cutoff names to a second pass.
Point-in-time: as_of = the TRADING date; every fetch is capped at ≤ as_of (no lookahead). A name
live on date D is resolvable from its then-current filings even if it later delists.

CLI:
  python float_backtest.py dossier TICKER YYYY-MM-DD
  python float_backtest.py record  TICKER YYYY-MM-DD FLOAT_M OS_M CONF BASIS "note"
  python float_backtest.py get     TICKER YYYY-MM-DD
"""
import sys, os, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "float_records.csv")
COLS = ["ticker", "as_of", "float_M", "os_M", "confidence", "basis", "computed_at", "note"]


def get(ticker, as_of):
    if not os.path.exists(LEDGER):
        return None
    hit = None
    for r in csv.DictReader(open(LEDGER)):
        if r["ticker"] == ticker and r["as_of"] == as_of:
            hit = r                       # last (most recent) wins
    return hit


def record(ticker, as_of, float_M, os_M, conf, basis, note=""):
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([ticker, as_of, float_M, os_M, conf, basis,
                    datetime.datetime.utcnow().isoformat(timespec="seconds"), note])
    print(f"recorded {ticker} @ {as_of}: float={float_M}M os={os_M}M conf={conf} -> {LEDGER}")


def main(argv):
    if not argv:
        print(__doc__); return
    cmd = argv[0]
    if cmd == "dossier":
        import float_gather as fg
        print(fg.gather(argv[1], argv[2] if len(argv) > 2 else "2026-06-04"))
    elif cmd == "get":
        r = get(argv[1], argv[2])
        print(r if r else f"(no record for {argv[1]} @ {argv[2]} — run dossier then record)")
    elif cmd == "record":
        t, d, fl, os_, conf, basis = argv[1:7]
        note = argv[7] if len(argv) > 7 else ""
        record(t, d, fl, os_, conf, basis, note)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
