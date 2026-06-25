# REBUILD.md — reproduce this project from a clean checkout

> Goal: a future session can `git checkout <hash>` and rebuild/verify everything. This repo is the
> **`float/` project** — a point-in-time free-float dataset for a micro-cap backtest, derived from
> **SEC EDGAR only** (the prior sec-api subscription lapsed). Read `STATUS.md` first for the overview;
> this file is the mechanical rebuild/verify guide.

## 0. What IS vs IS NOT in git
**IN git (the verification baseline + everything needed to RUN):**
- Code: `engine/*.py` (the EDGAR float tool) + root helper scripts (`record.py`, `triage.py`,
  `sync_records.py`, `remaining.py`, `validate_edgar.py`, `save_receipt.py`, `record_redo.py`).
- The deliverable: **`float_is.csv`** (master, 1,025 rows), `float_may.csv`, `engine/float_records.csv`.
- Inputs: `_float_candidates_is.csv` (the 1,025 candidate-days), `dt_os_float_2026-06-04.csv` (DT
  sanity snapshot), `engine/FLOAT_PROTOCOL.md` + `FLOAT_PLAYBOOK.md` (the derivation method).
- Reuse/audit: `engine/data/_cache/receipts/` + `manifests/` (per-name derivation records),
  `_redo_diff.csv`, `_may_hard_sonnet.csv`. Workflow: `workflows/parallel_sweep.js`.

**NOT in git (gitignored — rebuildable or secret):**
- Bulk caches (~1.2 GB): `engine/data/_cache/filing_text/`, `edgar_submissions/`, `scans/`,
  `dossiers/`, `company_tickers.json`, `secapi_ticker_cik.json`; `engine/data/*.parquet`.
- Secrets: `capi.txt` (Claude API key), `engine/sapi.txt` (legacy sec-api key, now unused). `*.log`.

## 1. Prerequisites + install
```
# Python 3.10 (the producing venv is claudebacktest_init2-2.4\.venv, Python 3.10)
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r requirements.txt                        # polars==1.41.0, requests==2.32.3
```
Run scripts with `PYTHONUTF8=1` prefixed (Windows cp1252 crashes on unicode prints).
In the dev environment, the working interpreter is
`C:\Users\explo\claude2\claudebacktest_init2-2.4\.venv\Scripts\python.exe`.

## 2. Credentials / env / external services (where each goes)
| What | Needed for | Where | Notes |
|---|---|---|---|
| **SEC EDGAR** | the whole engine (gather, O/S, holders) | none — public | Sends a `User-Agent` header with a contact email (`engine/float_from_filings.py` → `UA`). EDGAR requires it; rate-limited ~10 req/s. Change the email to your own. |
| **Claude API key** | RE-DERIVING floats via LLM agents only | `capi.txt` (repo root) | `set ANTHROPIC_API_KEY=$(cat capi.txt)` before launching, to bill agents to the API. **Not needed** to use `float_is.csv` or run the deterministic dossier. |
| sec-api key | nothing (retired) | `engine/sapi.txt` | Optional — code now tolerates its absence (`KEY=""`). Leave it out on a fresh clone. |

No other external services. (The upstream candidate scanner used Polygon, but its output is committed
as `_float_candidates_is.csv`, so you don't need Polygon to rebuild this repo.)

## 3. Pinned parameters (the exact config used)
- **In-sample date range:** `2025-05-01` … `2025-08-31` (May–Aug 2025). **OOS (not built):** `2025-09-01` … `2026-04-30`.
- **Selector (upstream, encoded in `_float_candidates_is.csv`):** common stock; premarket open ∈ [$3.50, $20];
  ≥18% up vs prev close; RVOL ≥ 2.7 (vs a 50-day SMA). Source: `claudebacktest_init2-2.4\claudebacktest_init2\warrior_candidates.csv` filtered to the IS dates.
- **Float gate:** `< 20,000,000` shares (`under_20M`).
- **Lookahead cap:** every filing query is capped at `filedAt ≤ as_of` (the trading day). No exceptions.
- **Model routing:** hard archetypes → **Opus** (`claude-opus-4-8`); easy US single-class → **Sonnet**
  (`claude-sonnet-4-6`). Parallel sweep: `hchunk=6, echunk=9, maxconc=12` (`workflows/parallel_sweep.js`).
- **DT sanity anchor:** `dt_os_float_2026-06-04.csv` — a fixed 2026-06-04 DilutionTracker snapshot; a
  gross-error check ONLY, never a target.
- **Random seeds:** none (no RNG anywhere). The only non-determinism is the LLM (see §6).

## 4. Rebuild commands (by artifact)
**(a) Derived ledgers (deterministic — always reproduce exactly):**
```
PYTHONUTF8=1 python sync_records.py          # regenerates engine/float_records.csv + float_may.csv from float_is.csv
PYTHONUTF8=1 python remaining.py             # sanity: should print "done 1025 / total 1025, remaining 0"
```
**(b) Filing caches (NOT in git; rebuilt live from EDGAR — slow, ~hours for the full set):**
```
# Re-fetches every filing the floats depend on. company_tickers.json auto-re-downloads from SEC on first run.
cd engine && PYTHONUTF8=1 python float_backtest.py dossier GOGO 2025-05-09     # one (ticker,as_of); repeat per candidate-day
```
To rebuild ALL caches, iterate `_float_candidates_is.csv` calling `dossier T D` for each (the agents do
this during a sweep). Point-in-time (`filedAt ≤ as_of`) makes refetches mostly stable; see §6 caveats.

**(c) The float values `float_is.csv` (LLM-derived — NON-deterministic, see §6):**
```
# Only if re-deriving from scratch (needs ANTHROPIC_API_KEY from capi.txt):
PYTHONUTF8=1 python triage.py 2025-05         # route remaining → _triage_hard.txt / _triage_easy.txt
# copy _triage_*.txt to month-specific names, build _rem_hard.txt/_rem_easy.txt, then run the
# Workflow tool with workflows/parallel_sweep.js (args {hardN,easyN,hchunk:6,echunk:9,maxconc:12}).
```
⚠ This will NOT bit-reproduce the committed `float_is.csv`. Treat `float_is.csv` as **data**, not a
reproducible build output. The committed file IS the canonical artifact.

## 5. How to verify a rebuild matches
- **Engine fidelity (deterministic):** `PYTHONUTF8=1 python validate_edgar.py` — re-derives O/S for a
  sample of done names via EDGAR and checks they reproduce the recorded `os_M` (proves the EDGAR-only
  engine still extracts the same numbers). Expect the same pass it logged when built.
- **Ledger consistency:** after `sync_records.py`, `git diff --stat float_may.csv engine/float_records.csv`
  should be empty (they are pure functions of `float_is.csv`).
- **Completeness:** `remaining.py` prints `remaining 0`.
- **Gate baseline:** if you re-derive, compare the `under_20M` column per `(ticker,as_of)` to the committed
  `float_is.csv` — the **gate decision** should match for ~all clean names (LLM variance affects only the
  exact float of the hard tail, rarely flipping <20M). There is no pytest suite; this column-diff is the test.

## 6. Non-determinism / drift caveats (READ before trusting a re-derive)
- **LLM derivation is non-deterministic.** Re-running the sweep yields slightly different exact floats on
  hard names (control-block judgment, ex-options rounding). Gate (<20M) decisions are stable; magnitudes
  on the ~10–15% hard tail are not. The committed `float_is.csv` + `receipts/` are the record of what WAS used.
- **EDGAR is live.** `company_tickers.json` changes over time → ticker reuse (a ticker now maps to a
  different company); the engine's point-in-time CIK guard (`engine/float_gather.py resolve_cik`) handles
  this by re-resolving via EFTS scoped to `enddt ≤ as_of`, but a manual override map exists
  (`CIK_OVERRIDES`, e.g. `MTAL: 1950246`). Filings can be amended; the `filedAt ≤ as_of` cap makes
  historical refetches mostly stable but not guaranteed identical.
- **Rate limits / time-of-day:** EDGAR throttles (~10 req/s) and `efts.sec.gov` (full-text search) can be
  flaky; a cold rebuild is slow and may need retries (the code backs off).
- **1 permanent gap:** `SSBI 2025-07-01` (Summit State Bank) has no SEC filings → unresolvable from EDGAR.
- **Upstream:** `_float_candidates_is.csv` came from the read-only sibling repo's Polygon-based scanner; it's
  committed here so you don't need Polygon, but it can't be rebuilt from this repo alone.
