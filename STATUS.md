# FLOAT JOB — STATUS / RESUME (in-sample May–Aug 2025)

**Goal:** a point-in-time **free float** for every `(ticker, day)` that passes the warrior Stage-1
selector (CS, premarket-open $3.50–20, ≥18% up vs prev close, RVOL ≥2.7) in the **in-sample**
window **May–Aug 2025**. EDGAR-only (sec-api subscription retired). One float per qualifying day
(point-in-time: filings ≤ that day, no lookahead).

**Working dir:** `C:\Users\explo\claude2\float\` (clean-room copy; the sibling
`claudebacktest_init2-2.4\` is READ-ONLY — never edit it).
**Python:** `C:\Users\explo\claude2\claudebacktest_init2-2.4\.venv\Scripts\python.exe` (bare
`python` is broken). Prefix runs with `PYTHONUTF8=1`. Engine in `float\engine\` (EDGAR-only,
no API key; sapi.txt unused).

## Files / data
- **`float_is.csv`** — MASTER ledger, single source of truth. Cols:
  `ticker,as_of,float_M,os_M,under_20M,confidence,basis,note`. Floats in millions.
- **`_float_candidates_is.csv`** — the 1,025 IS candidate-days (the work universe).
- **`engine/float_records.csv`**, **`float_may.csv`** — DERIVED from float_is.csv by
  `sync_records.py` (never hand-edit). float_records is keyed (ticker,as_of) for
  `float_backtest.py get T D`.
- **Caches (grow as we go, enable cheap reuse):** `engine/data/_cache/filing_text/` (per-accession
  filing text), `edgar_submissions/` (per-CIK filing index, full history → cache-hit for ANY date),
  `scans/` (per-document parse), `dossiers/` (per-(ticker,as_of) dossier), `manifests/`
  (per-(ticker,as_of) filing-dependency list, auto-saved by gather), `receipts/`
  (per-(ticker,as_of) DERIVATION RECEIPT: os_source + excluded/kept holders + deps + result).
  → a future date for a ticker = cheap delta: read its manifest/receipt, check for newer filings.
- `_may_hard.txt` (122 May hard ticker-days to Opus-redo), `_redo_log.txt` (redo progress).
- **Preservation/audit:** `float_is_before_opus_redo.csv` (full pre-redo backup),
  `_may_hard_sonnet.csv` (the 122 Sonnet hard values), `_redo_diff.csv` (every Opus old→new change).

## Helpers (run from float\ root unless noted)
- `python remaining.py [MONTH] [N]` — resumable work list (MONTH=2025-06 etc). done/remaining counts.
- `python record.py T D FLOAT OS CONF BASIS "NOTE"` — append one float (dedup ticker+day; skip-existing → resume-safe). For NEW names.
- `python record_redo.py T D FLOAT OS CONF BASIS "NOTE"` — OVERWRITE an existing row (Opus redo of hard names); atomic; logs to _redo_log.txt + old→new to _redo_diff.csv.
- `python save_receipt.py T D "OS_SOURCE" "name=sharesM|..." "name=sharesM|..."` — save the derivation receipt (excluded | kept-13g) after recording; combines with the auto manifest + result.
- `python triage.py MONTH` — route REMAINING names of a month into `_triage_hard.txt` (→Opus) and `_triage_easy.txt` (→Sonnet) by archetype.
- `python sync_records.py` — regenerate float_records.csv + float_may.csv from float_is.csv (run after each batch).
- Dossier: `cd engine && PYTHONUTF8=1 <py> float_backtest.py dossier T D`.

## Method (per (ticker,day))
`free_float = current_O/S − (officers+directors+control-affiliates+non-passive >20% holders)`;
KEEP passive 13G/index even if >20%; multi-class → listed class only; ADS → divide ordinary by
ratio; reverse/forward split → current O/S already reflects it; foreign IPO → exclude pre-IPO
affiliate SPVs (float = public offering). Use `RECONCILIATION → CURRENT O/S` (latest periodic ≤
as_of). NO-DROP: can't pin → confidence=low + best estimate + blocker. Carry-forward: a ticker
already floated on a nearby day → if no intervening offering/split/periodic changed O/S, record
the same float; else re-derive.

## Routing (single pass)
HARD archetypes (foreign 20-F/6-K, multi-class, reverse-split/consolidation, ADS, SPAC/de-SPAC,
fresh IPO, China/Cayman/BVI, death-spiral diluter) → **Opus** agent. EASY (US single-class
10-K/10-Q, no split/ADS/IPO) → **Sonnet** agent. One agent at a time (sequential re-spawn, no
fan-out). Each name recorded the instant it's derived → interruption-resilient.

## Engine notes / fixes already made
- EDGAR-only: `edgar.py` replaces sec-api Query/FTS with data.sec.gov submissions + efts search.
  Validated to reproduce the sec-api-era results (O/S 9/10 exact; live doc-fetch works).
- **Point-in-time CIK guard** (ticker reuse): a statically-mapped CIK with no filing ≤ as_of →
  EFTS re-resolve (fixed MTAL: now→unfiled SPAC II, 2025→Metals Acquisition Ltd CIK 1950246).
- Corrected hard-name errors found: HOLO (40:1 consolidation, ~82M O/S not 4.4M/189M), BIYA
  (exclude pre-IPO SPVs, ~3.7M not 11.1M), MTAL (ticker reuse), LITM (missed 1:13 split → <20M),
  SOS (missed 1-ADS=150-ord ratio → <20M), VMAR (no split by May; ~10.4M, NOT 1.03M — DT's 1.56M
  reflects a LATER split). record.py/record_redo.py now VALIDATE confidence (reject true/false).

## PROGRESS (update this section each session)
- **May (237/237) — COMPLETE & clean.** Easy=Sonnet; **122 hard re-derived on Opus** (2 correct
  <20M flips LITM/SOS; ~27 split/ADS fixes); a batch-5 19-row column-shift bug was realigned +
  Opus-redone (`_may_supplement.txt`). 146 under-20M trade candidates. (1 flagged low-conf
  inconsistency: YSXT 05-22 vs 05-28 — both <20M.)
- **June (322/322) — COMPLETE & QC'd.** 152 hard→Opus, 170 easy→Sonnet; 234 trade candidates (<20M); 0 bad-confidence; near-20M names spot-verified correct.
- **IS COMPLETE — 1,025/1,025 (May 237, Jun 322, Jul 266, Aug 200).** 1,024 resolved (99.9%);
  1 unresolvable = SSBI (Summit State Bank — no SEC filings). 670 trade candidates (<20M).
  Hard archetypes on Opus, easy on Sonnet; July+Aug finished parallel (12 agents/wave on the API key).
- **OOS (Sep 2025-Apr 2026) NOT started** — same pipeline: `triage.py 2025-09` (cache-warm; many tickers
  recur so cheap) -> parallel sweep (copy float-is-finish-parallel script, point at _rem_*.txt) -> QC.
  Use month-specific triage files (copy _triage_*.txt aside) to avoid the shared-file overwrite race.

## TO RESUME
1. `python remaining.py` (overall) / `python remaining.py 2025-06` (per month).
2. If a month's sweep was interrupted: just re-launch its sweep workflow — record.py skips
   already-done (ticker,as_of), so it continues. (Hard redo uses _redo_log.txt for progress.)
3. After each month: `sync_records.py`; QC = scan float_is.csv for confidence not in high/med/low,
   DT-divergence >2x, float==os, decision near 20M; spot-fix outliers. Update this section.
