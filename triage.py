"""Route each (ticker, day) to a model by ARCHETYPE difficulty, for the single-pass
hard->Opus / easy->Sonnet split. Reads the cached dossier (engine/data/_cache/dossiers/
{ticker}_{asof}.txt) if present, else runs gather (which also warms the cache).

HARD (=> Opus) if the dossier shows any error-prone archetype:
  - foreign filer: ownership filing is 20-F/40-F, or the latest periodic is a 6-K;
  - a reverse/forward split or consolidation;
  - an ADS structure (ratio or 'American Depositary');
  - multi-class (>=2 share classes among the O/S candidates / 'Class A|B|C ... outstanding');
  - a SPAC redeemable block or a fresh IPO prospectus with an offering;
  - NO CIK (needs manual resolution).
EASY (=> Sonnet) otherwise: US single-class 10-K/10-Q, one O/S basis, no split/ADS/IPO.

Usage:  python triage.py MONTH        # e.g. 2025-06  (or 'may'/'all'); classifies the REMAINING
        python triage.py done-may      # classify the already-recorded May rows (for the Opus redo)
Writes _triage_hard.txt and _triage_easy.txt (one 'TICKER DATE' per line) and prints a summary.
"""
import sys, os, re, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
import float_gather as fg

HERE = os.path.dirname(os.path.abspath(__file__))
DOSS = os.path.join(HERE, "engine", "data", "_cache", "dossiers")

CLASS_RE = re.compile(r"Class\s+[A-H]\b", re.I)


def dossier(ticker, asof):
    p = os.path.join(DOSS, f"{ticker}_{asof}.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8", errors="replace").read()
    try:
        return fg.gather(ticker, asof)
    except Exception as e:
        return f"GATHER-ERROR {e}"


def classify(text):
    reasons = []
    if "NO CIK" in text or "GATHER-ERROR" in text:
        reasons.append("no-cik/err")
    if re.search(r"OWNERSHIP FILING:\s*(20-F|40-F)", text) or "latest periodic 6-K" in text:
        reasons.append("foreign")
    # rely on the dossier's EXPLICIT split flag (proper N-for-M SPLIT_RE) — a loose
    # "consolidat"/"reverse" match hits "consolidated financial statements" in every filing.
    if "SPLIT/CONSOLIDATION detected" in text:
        reasons.append("split")
    if "ADS RATIO" in text or "ADS-listed" in text or "ADS/RESCALE" in text or "American Depositary Share" in text:
        reasons.append("ads")
    classes = set(m.group(0).title() for m in CLASS_RE.finditer(text))
    if len(classes) >= 2:
        reasons.append("multi-class")
    if "REDEEMABLE (SPAC)" in text or "## IPO PROSPECTUS" in text:
        reasons.append("ipo/spac")
    return reasons


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    cand = [(r["ticker"], r["date"]) for r in
            csv.DictReader(open(os.path.join(HERE, "_float_candidates_is.csv"), newline="", encoding="utf-8"))]
    rows = list(csv.DictReader(open(os.path.join(HERE, "float_is.csv"), newline="", encoding="utf-8")))
    done = {(r["ticker"], r["as_of"]) for r in rows}
    if arg == "done-may":
        work = [(t, d) for t, d in cand if d.startswith("2025-05") and (t, d) in done]
    else:
        mon = {"may": "2025-05", "jun": "2025-06", "jul": "2025-07", "aug": "2025-08"}.get(arg, arg)
        pref = "" if mon == "all" else mon
        work = [(t, d) for t, d in cand if d.startswith(pref) and (t, d) not in done]
    hard, easy = [], []
    for t, d in work:
        r = classify(dossier(t, d))
        (hard if r else easy).append((t, d, ",".join(r)))
    open(os.path.join(HERE, "_triage_hard.txt"), "w").write(
        "\n".join(f"{t} {d}  # {why}" for t, d, why in hard))
    open(os.path.join(HERE, "_triage_easy.txt"), "w").write(
        "\n".join(f"{t} {d}" for t, d, _ in easy))
    print(f"triaged {len(work)} ({arg}): HARD(Opus)={len(hard)}  EASY(Sonnet)={len(easy)}")
    print("-> _triage_hard.txt , _triage_easy.txt")


if __name__ == "__main__":
    main()
