#!/usr/bin/env python3
"""OOS COST TEST — measure the steady-state cost on a NEW month with the cache already warmed.

Input: an OOS candidate CSV (cols: ticker,date) — a month of scanner hits AFTER the IS window
(IS = 2025-05-02..2025-08-29). Default _oos_candidates.csv. (The scanner — up>18%/day, RVOL>=2.7,
$3.50-20 — lives in the sibling repo claudebacktest_init2-2.4; re-run it for e.g. 2025-09, or hand-
pick a month, and write ticker,date rows here.)

For each (ticker, day) it runs recipe_cache.replay FIRST (FREE if a warmed recipe exists + not stale);
anything else must go to the LLM. The split = the real blended cost (the IS numbers were self-
referential — IS warmed its own cache). Run AFTER warming the cache (full-236 recipe-emit). $0, no LLM.
"""
import os, sys, csv, collections
import recipe_cache as RC, holder_registry as H, float_gather as fg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_oos_candidates.csv")
cand = list(csv.DictReader(open(SRC, encoding="utf-8")))
print(f"OOS candidates: {len(cand)} | recipes cached: {len(RC.RECIPES)} tickers | "
      f"registry: {len(H.REGISTRY)} entities\n")

tally = collections.Counter()
free = 0                                  # COLD: free only via the pre-warmed cache (status 'ok')
warm_derived = set()                      # WARMED: tickers that triggered a (modeled) first derivation this run
warm_free = warm_llm = 0
for r in cand:
    t = r["ticker"]; d = r.get("date", r.get("as_of", ""))[:10]
    cik = fg.resolve_cik(t, d)
    st, fv = RC.replay(t, d, cik) if cik else ("no-cik", None)
    tally[st] += 1
    free += (st == "ok")
    # (F49) within-month warming: production derives a NEW ticker ONCE (first non-'ok' day -> cache it),
    # then replays its later same-ticker days free. Model that by de-duping LLM billing per ticker, so a
    # recurring momentum name isn't billed as N full derivations. (Can't actually derive — needs the LLM —
    # so this is the cheap, accurate proxy the verifier prescribed; reported alongside the cold snapshot.)
    if st == "ok":
        warm_free += 1
    elif t in warm_derived:
        warm_free += 1                    # later same-ticker day -> free replay off the within-month recipe
    else:
        warm_derived.add(t); warm_llm += 1   # first appearance -> one modeled LLM derivation

n = len(cand)
print("=== replay status split (COLD: pre-warmed cache only) ===")
for k, v in tally.most_common():
    print(f"  {k:14} {v:4} ({100*v//max(1,n)}%)")
print(f"\nFREE (recipe-cache hit, no LLM): {free}/{n} ({100*free//max(1,n)}%)")
print(f"NEEDS LLM (cold): {n-free}/{n} ({100*(n-free)//max(1,n)}%)")
print(f"\n=== within-month WARMED (de-dup LLM billing per distinct ticker) ===")
print(f"  modeled LLM derivations: {warm_llm} (distinct new tickers) | free (cache+within-month): {warm_free}/{n} "
      f"({100*warm_free//max(1,n)}%)")
print(f"NEEDS LLM (warmed): {warm_llm}/{n} ({100*warm_llm//max(1,n)}%) — and each derivation's holder "
      f"classifications hit/warm the {len(H.REGISTRY)}-entity registry, lowering marginal cost further.")
print("\nCost: FREE share * $0 + LLM share * (~compressed-dossier cost, ~$0.05-0.15/derivation w/ registry).")
print("Extrapolate /yr = (annual scanner hits) * blended; compare to the IS ~$300-600/yr estimate.")
