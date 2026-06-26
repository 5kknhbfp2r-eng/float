"""Print the in-sample candidate-DAYS that still need a point-in-time float — the resumable
work list. universe = the 1,025 (ticker, day) pairs in _float_candidates_is.csv (every day a
ticker passes the May-Aug 2025 selector). remaining = universe MINUS the (ticker, as_of) rows
already in float_is.csv. Reads the durable ledger each call, so it always reflects real progress.

Grouped by ticker; annotates any day whose ticker already has a float on another day with
`[prior <date> float=<f> os=<o>]` (carry-forward candidates).

Usage:  python remaining.py [MONTH] [N]
  MONTH = a YYYY-MM prefix (e.g. 2025-06) to show only that month, or 'all'/omitted for all IS.
  N     = show only the first N tickers (grouped).
"""
import sys, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    month = None
    if args and args[0] != "all" and not args[0].isdigit():
        month = args.pop(0)
    n = int(args[0]) if args else None

    cand = [(r["ticker"], r["date"]) for r in
            csv.DictReader(open(os.path.join(HERE, "_float_candidates_is.csv"), newline="", encoding="utf-8"))]
    if month:
        cand = [(t, d) for t, d in cand if d.startswith(month)]
    rows = []
    p = os.path.join(HERE, "float_is.csv")
    if os.path.exists(p):
        rows = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
    done = {(r["ticker"], r["as_of"]) for r in rows}
    by_ticker = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
    rem = [(t, d) for t, d in cand if (t, d) not in done]
    order, groups = [], {}
    for t, d in rem:
        if t not in groups:
            groups[t] = []; order.append(t)
        groups[t].append(d)
    show = order if n is None else order[:n]
    scope = f"month {month}" if month else "all IS (May-Aug)"
    print(f"# {scope}: {len(cand)} candidate-days, done {len([1 for t,d in cand if (t,d) in done])}, "
          f"remaining {len(rem)} pairs across {len(order)} tickers (showing {len(show)})")
    for t in show:
        for d in groups[t]:
            hint = ""
            if t in by_ticker:
                prior = [r for r in by_ticker[t] if r["as_of"] < d]      # (F43) strictly-earlier rows only
                if prior:
                    pr = max(prior, key=lambda r: r["as_of"])            # the most-recent prior day, not file order
                    hint = f"   [prior {pr['as_of']} float={pr['float_M'] or 'NA'} os={pr['os_M']}]"
            print(f"{t} {d}{hint}")


if __name__ == "__main__":
    main()
