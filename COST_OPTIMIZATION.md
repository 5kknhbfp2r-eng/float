# COST OPTIMIZATION — making float derivation cheaper (workstream notes)

> Captured from a design discussion. The IS float dataset was built with an LLM reading every
> dossier (Opus on hard names, Sonnet on easy). The user wants the SAME accuracy (incl. exact
> float, not just the <20M gate) at much lower cost. This file is the plan + evidence so a fresh
> session can pursue it. NOT yet built — the recommended first step is a benchmark (see §4).

## 1. The core insight
The expensive part was never the data (EDGAR is free) — it was the **LLM judgment**, and the only
judgment regex can't do is **classifying holders as control-affiliate (exclude) vs passive (keep)**.
But that signal is **free and structured on EDGAR**:
- **13D filer = active/control (usually exclude); 13G filer = passive (keep)** — it's just the
  **form type** of the beneficial-ownership filing. No vendor needed.
- **Form 3/4 (insiders) are XML on EDGAR** — machine-readable; gives the D&O block directly.
- **Current O/S** is regex-extractable from the latest periodic (the engine already surfaces it).

So a deterministic float = `O/S − insiders(Form 3/4 or proxy "as a group" row) − control blocks
(13D filers, >20% non-13G, board-nominees)`, computed from **free EDGAR data + rules**.

## 2. sec-api is NOT needed (decided)
sec-api ($200/mo) is a structuring layer over the same free EDGAR data; we already replaced its
query/full-text-search/CIK layer with `edgar.py` and reproduced its results. Its structured float
endpoint only adds the **annual 10-K cover public-float** (a $ figure, as of the prior June 30) —
too stale for a daily backtest. **Conclusion: skip sec-api; EDGAR-only adds ~$0 per-name cost.**
Third-party float vendors (DilutionTracker, Sharadar, FMP, Fintel, Fincoded) were researched —
none give clean *point-in-time historical FREE FLOAT*; they give current float and/or the raw
13D/G/13F/insider feeds (which EDGAR already has for free).

## 3. Honest accuracy expectation
The OLD repo's pure-regex engine plateaued at ~18% within-5% of DT — BUT it predicted float from
text patterns and did **not** use the 13D/G + Form-3/4 feeds with a label-tuned rules engine, so it
can do meaningfully better. Rough split of the 1,025 IS names:
- ~55–60% easy US single-class → deterministic, high accuracy.
- ~25–30% rule-able hard archetypes (multi-class via per-class O/S; foreign 20-F O/S; ADS ratio
  "each ADS represents N ordinary"; reverse-split = scale holders to current O/S) → good accuracy.
- ~10–15% irreducible control-judgment tail (pre-IPO SPV blocks on fresh China IPOs, acting-in-
  concert family stakes, ambiguous 10–20% strategics with no clean 13D/G) → keep a thin **compressed
  LLM** pass (feed it the extracted structured summary, NOT the raw 20-F → ~10–50× fewer tokens).

## 4. ▶ RECOMMENDED FIRST STEP — benchmark, don't guess
We have a perfect labeled test set: `float_is.csv` (1,025 LLM-derived floats). Build the
deterministic engine and **score it against those labels** to get the exact % it matches and which
slice still needs the LLM. Cheap, and it converts all the estimates below into measured fact.
Steps: (a) write `det_float.py` = regex O/S (reuse engine's `_os_candidates`/`_current_os`) +
Form 3/4 / proxy-group insiders + 13D/G-rule holder classification + split/ADS reconciliation;
(b) run it over the 1,025 `(ticker, as_of)` pairs; (c) compare float_M and the <20M gate to
`float_is.csv`; (d) report exact-match %, gate-match %, and the failing tail (→ that's the LLM's job).

## 5. Cost estimates (full universe, non-OTC, full year)
Float changes only on filing events → derive once per change, carry forward. Non-OTC universe
≈ 4,000–5,000 exchange-listed common stocks (all SEC filers), × ~8 O/S-change events/yr
≈ ~40K unique derivations/yr (fills ~1.5M ticker-days).

| Approach | Annual cost |
|---|---|
| Naive all-LLM, full filing reads | ~$15–20K |
| Compressed LLM (structured summary, not raw 20-Fs) | ~$2–4K |
| **Free-EDGAR + rules + thin LLM tail (recommended)** | **~$200 LLM + $0 data** |

As a fraction of a 20× Max plan: the ~$200/yr ≈ ~$4/week ≈ on the order of ~1% (likely <1%) of a
weekly 20× allowance — i.e. the whole year's float compute ≈ well under one week of a 20× plan.
(Very rough — Max weekly caps aren't a published token quota.)

## 6. Where the existing assets help
- Reuse the engine's deterministic pieces: `_current_os`, `_os_candidates`, `_own_window`,
  `_reconcile_block`, the ADS/split detectors (in `engine\float_gather.py` / `_widen_probe.py`).
- The caches (`filing_text`, `edgar_submissions`, `scans`, `manifests`) make re-running the 1,025
  benchmark instant (no re-fetch).
- `manifests\` already records which filings each float depended on → trivial delta-updates for
  later dates (only re-derive when a newer O/S-relevant filing appears).
