"""Save a per-(ticker, as_of) DERIVATION RECEIPT: a compact, machine-readable record of HOW the
float was derived, so a future date for the same ticker is a cheap delta ("did a newer filing
change the O/S or any of these holders?") and there's a full audit trail.

It combines three things into engine/data/_cache/receipts/{ticker}_{asof}.json:
  - the agent's structured derivation (passed as simple delimited args, below),
  - the engine's filing-dependency manifest (auto-saved by gather: which filings the float used),
  - the recorded float result (read from float_is.csv).

Usage:
  python save_receipt.py TICKER AS_OF "OS_SOURCE" "EXCLUDED" "KEPT_13G"
    OS_SOURCE : free text, e.g. "10-Q 2025-05-15 acc=0000950170-25-067982 : 16,019,787 common"
    EXCLUDED  : "name=shares_M|name=shares_M|..."  (shares in MILLIONS; the blocks you subtracted)
    KEPT_13G  : "name=shares_M|name=shares_M|..."  (passive/index holders you kept in float; may be "")
Robust to missing pieces; never raises (a receipt is best-effort, must not block recording).
"""
import sys, os, csv, json

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "float_is.csv")
MANI = os.path.join(HERE, "engine", "data", "_cache", "manifests")
RECEIPTS = os.path.join(HERE, "engine", "data", "_cache", "receipts")


def parse_pairs(s):
    out = []
    for part in (s or "").split("|"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, val = part.rsplit("=", 1)
            try:
                out.append({"name": name.strip(), "shares_M": float(val)})
            except ValueError:
                out.append({"name": part, "shares_M": None})
        else:
            out.append({"name": part, "shares_M": None})
    return out


def main(a):
    if len(a) < 3:
        print(__doc__); sys.exit(1)
    ticker, as_of, os_source = a[0], a[1], a[2]
    excluded = parse_pairs(a[3] if len(a) > 3 else "")
    kept = parse_pairs(a[4] if len(a) > 4 else "")
    rec = {"ticker": ticker, "as_of": as_of, "os_source": os_source,
           "excluded": excluded, "kept_13g": kept}
    # attach the recorded float result
    try:
        for r in csv.DictReader(open(LEDGER, newline="", encoding="utf-8")):
            if r["ticker"] == ticker and r["as_of"] == as_of:
                rec["float_M"], rec["os_M"], rec["under_20M"], rec["confidence"] = \
                    r["float_M"], r["os_M"], r["under_20M"], r["confidence"]
                break
    except Exception:
        pass
    # attach the engine filing-dependency manifest
    try:
        m = json.load(open(os.path.join(MANI, f"{ticker}_{as_of}.json")))
        rec["cik"] = m.get("cik")
        rec["depends_on_filings"] = m.get("filings", [])
    except Exception:
        pass
    try:
        os.makedirs(RECEIPTS, exist_ok=True)
        json.dump(rec, open(os.path.join(RECEIPTS, f"{ticker}_{as_of}.json"), "w"), indent=1)
        print(f"RECEIPT {ticker}@{as_of}: {len(excluded)} excluded, {len(kept)} kept, "
              f"{len(rec.get('depends_on_filings', []))} dep-filings")
    except Exception as e:
        print(f"(receipt not saved: {e})")


if __name__ == "__main__":
    main(sys.argv[1:])
