# FLOAT JOB — HANDOFF / RESUME (read this first)

> **Self-sufficient handoff for a fresh session with no prior context.** This directory
> (`C:\Users\explo\claude2\float\`) is a standalone git repo and the project root for the
> "LLM float" work. The sibling `C:\Users\explo\claude2\claudebacktest_init2-2.4\` is the
> larger backtest project — **READ-ONLY, never edit it** (we copied what we needed out of it).

---

## 0. WHAT THIS IS (one paragraph)
A backtester for a micro-cap momentum strategy ("Warrior") needs each stock's **free float**
on the day it traded, and the strategy gates on **float < 20M shares**. This project computes a
**point-in-time free float** for every `(ticker, day)` that passes the strategy's Stage-1 scanner
(common stock, premarket open $3.50–20, ≥18% up vs prev close, RVOL ≥2.7), from **SEC EDGAR
filings only** (the prior `sec-api` subscription lapsed), with **no lookahead** (only filings
dated ≤ the trading day). "Free float" = DilutionTracker-style:
`O/S − (officers + directors + control-affiliates + non-passive >20% holders)`, **keeping**
passive 13G/index holders even if >20%.

## 1. CURRENT STATE — in-sample is COMPLETE
- **In-sample window = May–Aug 2025. ALL 1,025 candidate-days are done** (May 237, Jun 322,
  Jul 266, Aug 200). 1,024 resolved; **1 unresolvable = SSBI** (Summit State Bank — a Nasdaq bank
  with no SEC filings; recorded blank/low-conf).
- **670 of 1,025 are trade candidates (<20M float).** 0 bad-confidence rows.
- **Committed locally**: git repo on branch `main`, first commit `27952ba` (run `git log`).
  Secrets and the 1.1 GB filing cache are gitignored (see `.gitignore`).
- **Nothing is running.** No background workflow/agent is active. Out-of-sample (OOS) NOT started.

## 2. ENVIRONMENT / RUNTIME
- **Python (bare `python` is the broken Store stub — always use this full path):**
  `C:\Users\explo\claude2\claudebacktest_init2-2.4\.venv\Scripts\python.exe`
  Prefix every run with `PYTHONUTF8=1` (Windows cp1252 crashes on unicode prints otherwise).
- **Engine** lives in `float\engine\` — EDGAR-only (no API key needed for SEC data).
- **Secrets (gitignored, must exist on disk to run):** `engine\sapi.txt` (legacy sec-api key,
  now UNUSED by the engine), `capi.txt` (your Claude API key, used to fund parallel agents — set
  `ANTHROPIC_API_KEY` from it at launch to bill agents to the API rather than your Max plan).

## 3. THE DELIVERABLE (files in `float\`)
- **`float_is.csv`** — THE master ledger (1,025 rows). Single source of truth. Cols:
  `ticker,as_of,float_M,os_M,under_20M,confidence,basis,note`. Floats in **millions**. A blank
  `float_M` with a value in `os_M` means "clearly >20M, exact float not itemized" (72 such rows).
- **`float_may.csv`** — May subset, the format `claudebacktest_init2\warrior_float_may.py` reads
  (col `float_M`). DERIVED from `float_is.csv` — never hand-edit; run `sync_records.py`.
- **`engine\float_records.csv`** — native ledger keyed `(ticker, as_of)` for
  `python float_backtest.py get T D`. Also DERIVED by `sync_records.py`.
- **Reuse/audit (committed):** `engine\data\_cache\receipts\` (per-name derivation receipt:
  os_source + excluded/kept holders + result) and `manifests\` (the filings each float depended
  on, for cheap delta-updates). `_redo_diff.csv` + `_may_hard_sonnet.csv` (Opus-vs-Sonnet diffs).
- **Caches (gitignored, on disk, make re-runs cheap):** `engine\data\_cache\filing_text\`
  (1.1 GB, per-accession filing text), `edgar_submissions\` (per-CIK filing index, full history →
  cache-hit for ANY date), `scans\`, `dossiers\`.

## 4. THE PIPELINE — how a float gets made (and how to run it)
Per `(ticker, as_of)`:
1. **Gather** (deterministic, EDGAR-only): `cd engine && PYTHONUTF8=1 <py> float_backtest.py
   dossier TICKER YYYY-MM-DD` prints a point-in-time **dossier** — cover O/S candidates by class,
   a `⚠ RECONCILIATION` block (current O/S from the latest periodic ≤ as_of, split/ADS ratios,
   post-filing dilution), the ownership table, footnotes. All filings capped at filedAt ≤ as_of.
2. **Judge** (the LLM part): read the dossier per `engine\FLOAT_PROTOCOL.md` + `FLOAT_PLAYBOOK.md`
   and compute float. **Routing:** HARD archetypes (foreign 20-F/6-K, multi-class, reverse-split/
   consolidation, ADS, SPAC/de-SPAC, fresh IPO, China/Cayman/BVI, death-spiral diluter) → **Opus**;
   EASY (US single-class 10-K/10-Q, no split/ADS/IPO) → **Sonnet**. `triage.py` does this routing.
3. **Record** (durable, instant): `python record.py T D FLOAT OS CONF "BASIS" "NOTE"` appends to
   `float_is.csv` (dedup on ticker+day; skip-existing → resume-safe). Then
   `python save_receipt.py T D "OS_SOURCE" "Excl=M|..." "Kept=M|..."`.
4. **Carry-forward** (efficiency): if a ticker already has a float on an earlier day and no new
   O/S-relevant filing was filed between, record the same float ("carried from <date>").

**Engine key files (`engine\`):** `float_backtest.py` (CLI: dossier/get/record), `float_gather.py`
(builds the dossier; `resolve_cik` with a point-in-time ticker-reuse guard), **`edgar.py`** (the
EDGAR-only shim that replaced sec-api: `data.sec.gov/submissions` + `efts.sec.gov` full-text-search
+ doc fetch from sec.gov), `float_from_filings.py`, helper probes (`_cik_probe`, `_formula_probe`,
`_widen_probe`, `_affil_probe`), `FLOAT_PROTOCOL.md` (the derivation method = the "prompt"),
`FLOAT_PLAYBOOK.md` (archetypes + worked examples).

**Helper scripts (`float\` root):** `remaining.py [MONTH] [N]` (resumable work list),
`triage.py MONTH` (route remaining names → `_triage_hard.txt`/`_triage_easy.txt`),
`record.py` (append, new names), `record_redo.py` (atomic OVERWRITE + logs `_redo_diff.csv`,
used to re-derive/fix existing rows), `save_receipt.py`, `sync_records.py` (regen the derived
ledgers — run after every batch), `validate_edgar.py` (the EDGAR-vs-prior-results validation).

## 5. WHAT'S DONE / IN-PROGRESS / BLOCKERS
- **DONE:** EDGAR-only engine built + validated (reproduces the prior sec-api results); all 1,025
  IS floats; May hard names re-derived on Opus; bugs fixed (below); committed.
- **IN-PROGRESS:** none (no active runs).
- **BLOCKERS:** none. (One permanent edge: SSBI and any non-SEC-filer can't be derived from EDGAR.)

## 6. KNOWN CAVEATS (none affect the <20M strategy gate)
- **SSBI 2025-07-01** — unresolvable (no SEC filings); blank/low-conf. The only one of 1,025.
- **72 rows have blank `float_M`** (O/S recorded, exact float not itemized) — all clearly >20M, so
  not trade candidates; fine for the gate. Filling them is a cheap optional polish.
- **20 low-confidence rows** — genuinely hard names, flagged per the NO-DROP rule.
- DT (`dt_os_float_2026-06-04.csv`) is a 2026-06-04 snapshot; it's a gross-error sanity check only,
  NOT a target (post-date dilution legitimately makes DT's O/S larger than a May–Aug value).

## 7. FIXES / LESSONS (load-bearing — don't re-learn the hard way)
- **EDGAR reproduces sec-api**: validated before doing new work (`validate_edgar.py`). sec-api was
  only a structuring layer over free EDGAR data; the doc text always came from sec.gov.
- **Point-in-time CIK guard** (ticker reuse): a statically-mapped CIK with no filing ≤ as_of is the
  wrong entity → re-resolve via EFTS scoped to enddt=as_of. (Fixed MTAL: company_tickers now maps it
  to an unfiled 2026 SPAC; in 2025 MTAL = Metals Acquisition Ltd, CIK 1950246, kept in `CIK_OVERRIDES`.)
- **Opus catches what Sonnet misses on hard names**: reverse splits & ADS ratios — e.g. HOLO
  (40:1 consolidation, ~82M O/S not 4.4M/189M), SOS (1 ADS = 150 ordinary), LITM (1:13 split),
  CMCT (serial splits), VMAR (no split by May; ~10.4M not 1.03M). Several flipped the <20M gate.
- **`record.py`/`record_redo.py` validate confidence** (reject `true`/`false`) — a Sonnet batch once
  passed an extra `under_20M` arg, shifting columns in 19 rows (found + fixed).
- **Triage writes shared files** (`_triage_hard.txt`/`_triage_easy.txt`): running a new `triage.py`
  while a sweep is still reading them clobbers it. **Copy them to month-specific names** (e.g.
  `_aug_hard.txt`) before launching a sweep, or finish the sweep first.
- **Every name is `fsync`'d on record** → interruption-resilient. A stopped sweep loses nothing;
  rebuild the remaining list (candidate set minus done) and re-launch.

## 8. ▶ FRESH SESSION — READ THESE, IN THIS ORDER
1. **This file** (`float\STATUS.md`) — you're done; it's the entry point.
2. **`float\CLAUDE.md`** — the user's original task instruction (the success criteria).
3. **`engine\FLOAT_PROTOCOL.md`** + **`engine\FLOAT_PLAYBOOK.md`** — the float-derivation method
   and archetypes (this is the judgment you apply when reading a dossier).
4. **`float\COST_OPTIMIZATION.md`** — the cheaper-pipeline workstream (data vendors + a
   deterministic free-EDGAR engine the user wants explored). Read if pursuing cost reduction.
5. (Optional, READ-ONLY background — how floats feed the strategy):
   `..\claudebacktest_init2-2.4\WARRIOR_HANDOFF_2026-06-23.md` and `FLOAT_HANDOFF_2026-06-18_K.md`.
6. **Verify the env (≈1 min):** `cd engine && PYTHONUTF8=1 <py> float_backtest.py dossier GOGO
   2025-05-09` should print a full dossier (proves EDGAR engine works). Then
   `PYTHONUTF8=1 <py> remaining.py` (from `float\`) should print `done 1025 / 1025, remaining 0`.

## 9. ▶ THEN PROMPT THE USER (IS is complete — this is a direction fork; surface the options)
> **The in-sample (May–Aug 2025) float dataset is complete and committed (1,025 floats, 670 trade
> candidates). What next?** Suggested order:
>
> - **(A) Build the cheaper deterministic engine + benchmark it against the 1,025 labels — RECOMMENDED
>   & the user's stated interest.** Goal: replace most of the LLM with free-EDGAR data + rules
>   (regex O/S, Form 3/4 insiders, **13D vs 13G form-type = control vs passive**), keep a thin
>   compressed-LLM pass only for the ~10–15% control-judgment tail. We have a perfect labeled test
>   set (`float_is.csv`) to measure accuracy for almost nothing. Details + cost math in
>   `COST_OPTIMIZATION.md`. This turns "can it be cheaper?" into a measured number before scaling.
> - **(B) Extend to OUT-OF-SAMPLE (Sep 2025 – Apr 2026).** Same pipeline, per month:
>   `triage.py 2025-09` → copy `_triage_hard.txt`/`_triage_easy.txt` to month-specific names →
>   build combined `_rem_hard.txt`/`_rem_easy.txt` (remaining only) → run the parallel sweep via
>   **`workflows\parallel_sweep.js`** (the committed Workflow script; reads `_rem_hard.txt`→Opus /
>   `_rem_easy.txt`→Sonnet; args `{hardN,easyN,hchunk:6,echunk:9,maxconc:12}`) → `sync_records.py`
>   → QC. Many tickers recur → cache-hits → cheap. (User has the API key + 12-agent allowance;
>   non-OTC only per the user.)
> - **(C) Fill the 72 blank >20M floats** for completeness (exact numbers on clearly-large names).
> - **(D) Wire `float_is.csv` into the Warrior backtest** — the actual consumer. The strategy code is
>   in the read-only `..\claudebacktest_init2-2.4\claudebacktest_init2\` (`warrior_float_may.py` etc.);
>   the rule is "use ONLY LLM-derived floats (`float_M`)". This is the float's whole purpose.
>
> State a recommendation (A or B) and proceed if the user is hands-off.

## 10. RESUME / EXTEND MECHANICS (quick reference)
- Overall/per-month status: `PYTHONUTF8=1 <py> remaining.py [2025-09]`.
- A sweep was interrupted? Rebuild remaining = candidate-days minus what's in `float_is.csv`, write
  to `_rem_hard.txt`/`_rem_easy.txt`, re-launch the parallel sweep (record.py skips done names).
- After every batch: `PYTHONUTF8=1 <py> sync_records.py`, then QC: scan `float_is.csv` for
  confidence ∉ {high,med,low}, `float==os` near 20M, DT-divergence >2×, blanks with os<30M; spot-fix.
- Parallel sweeps: run **`workflows\parallel_sweep.js`** via the Workflow tool — 12 agents/wave,
  hard(`_rem_hard.txt`)→Opus, easy(`_rem_easy.txt`)→Sonnet, `record.py` + `save_receipt.py`,
  carry-forward. Args `{hardN:<#>, easyN:<#>, hchunk:6, echunk:9, maxconc:12}`. The per-agent prompt
  (full derivation method) is embedded in that script.
- Do NOT update `version.txt` / `v.txt`. Never commit `capi.txt`/`sapi.txt` or `data\_cache\filing_text`.

## 11. ▶ COST-OPTIMIZATION WORKSTREAM (2026-06-25) — read `COST_OPTIMIZATION.md` (esp. the ★SUMMARY★ at the end)
This pursued option (A): make float derivation cheap WITHOUT losing accuracy. Substantially explored +
validated. **Full detail + the lever ledger + the target architecture are in `COST_OPTIMIZATION.md`** (the
**★ SUMMARY & TARGET ARCHITECTURE ★** block at the very end is the entry point — sections above it are out
of strict numeric order from incremental edits).

> **▶▶ RESUME HERE (next session) — 2 steps: warm the cache, then test cost on 1 OOS month.**
> The system is PROVEN and the benchmark is QC'd clean (see the QC bullet below). State now: ~90% within-10%
> accuracy, never confidently wrong; ~$300–600/yr (~2× above the ~$200–300 floor). Closing the cost gap =
> warming the cache at scale, then measuring the real steady-state cost on out-of-sample data.
>
> **STEP 1 — Warm the production cache (full 236 multi-day tickers).** `cd engine && python emit_worklist.py`
> → `_emit_worklist.json` (236 tickers + earliest day + cik). Put the full 236 `{t,a}` list into
> `workflows/recipe_emit_wave.js` ITEMS (currently the 30-wave; it's already 6-at-a-time + resume-safe), run it
> via the Workflow tool (needs user opt-in — Max spend ~8–10M tokens; resume via `resumeFromRunId` if cut off).
> Then `python merge_emitted.py` (folds → `_recipes_emitted.json`) → `python validate_recipes.py` (replays +
> scores + warms `holder_registry.json` to several hundred entities). Output: warmed `recipes.json` (versioned)
> + `holder_registry.json` = the production cache.
>
> **STEP 2 — OOS cost test (1 month, e.g. 2025-09).** Get a month of scanner hits AFTER 2025-08-29 as a
> `_oos_candidates.csv` (cols `ticker,date`). The scanner (up>18%/day, RVOL≥2.7, $3.50–20) lives in the SIBLING
> repo `claudebacktest_init2-2.4` (READ-ONLY — never edit it) — re-run it for Sept, or hand-pick a month. Then
> `cd engine && python oos_cost.py ../_oos_candidates.csv` — runs `recipe_cache.replay` FIRST (free on a warmed
> recipe), tallies free-vs-needs-LLM = the REAL blended cost (the IS numbers were self-referential since IS
> warmed its own cache). NEW OOS tickers miss the recipe cache but the holder REGISTRY still cuts their LLM
> cost; recurring momentum names hit the recipe cache. Extrapolate $/yr, compare to the ~$300–600 IS estimate.
> (Cost-only test — no OOS labels needed; if labels exist later, score accuracy too.)
> Harness ready: `engine/{emit_worklist,merge_emitted,validate_recipes,oos_cost}.py` + `workflows/recipe_emit_wave.js`.

> **▶▶ 2026-06-26 — COST/ACCURACY AUDIT + ENGINE-HARDENING (branch `audit-fixes`; do this BEFORE the warm).**
> A multi-agent audit (12 module finders + adversarial verify; full record `_AUDIT_2026-06-26.md`, tracker
> `_AUDIT_FIXES.md`) found 50 verified defects (3 critical, 12 high). **45 are FIXED** on branch `audit-fixes`
> (commits `f28e074`..`50ea735`, each group tested). The 5 deferred are now resolved: **F28** implemented
> (a low-float `insider-drift` guard — for a recipe whose float is <12% of O/S, defer on any Form 3/4/5 in
> the window; `calib_dno_drift.py` measured median ~1% annual D&O drift, with the big drifts already caught
> by the proxy-changed re-derive); **F27/F48 analyzed → NO CHANGE** (the band is an O/S-drift guard and
> tightening k catches 0/19 float-misses — they're ratio≈1.0, orthogonal); **F44/F34 intentionally left**
> (each proposed fix adds a NEW regression, per the adversarial verifier). **The 3 criticals are closed:** point-in-time CIK resolution (edgar picked the highest-
> relevance EFTS hit, not the latest-dated entity <= asof — wrong company for reused tickers); 13F false-
> passive (a control person/family vehicle auto-classified passive via a single shared token -> kept ->
> float too high, cached forever); and SPAC/IPO carried-float replayed `ok` with NO de-SPAC/redemption/
> lockup (8-K **and 6-K**) staleness.
> **HEADLINE-ACCURACY CORRECTION (F13/F24):** every §16 accuracy number BELOW was computed relative to O/S,
> not the float being measured — so they OVERSTATE float accuracy (a replay ~100% wrong on the float could
> read "within-10%"). The scoring harness now reports `err_float_rel` as the primary metric.
> **Post-fix sim (236-ticker / 383-later-day, FLOAT denominator):** 35% free | within-5% **72%** | within-10%
> **86%** | miss>10% **13%** | median **0.23%**. The >10% tail is dominated by foreign/ADS SIM ARTIFACTS (the
> label-stand-in sim carries NO ads_ratio — e.g. LSE replays ~0 float; the REAL 30-recipe wave, which carries
> the ratio, had worst 12%). New guards (frozen-XBRL `stale-osfact` age defer >300d/>100d-foreign, positive-
> anchor, 14C + foreign-consolidation staleness, native-unit ADS) shed wrong-free replays — ARBKL's old ~10%
> free miss now correctly defers. **For the warm:** `recipe_emit_wave.js` is now durable (per-agent
> `engine/record_recipe.py`, resume = worklist minus recorded), Opus-pinned, and emits os_M in the issuer's
> NATIVE/ordinary units (ads_ratio converts) so replay's re-fetch is unit-consistent; and **re-derive (don't
> skip) the QC-flagged AGENT-ERROR recipes ARBKL + BMGL** before/within the warm (they're in the 33 already-
> emitted but STATUS QC found them wrong). Re-run the sim: `python sim_replay.py` then score `err_float_rel`.

**Key outcomes (so a fresh session has the bottom line):**
- **Deterministic engine built** (`engine/det_float.py`): XBRL O/S (`dei:EntityCommonStockSharesOutstanding`,
  point-in-time) + the reused `_widen_probe`/`_formula_probe` exclusion machinery + a 13D/13G form-type leg +
  a compressed-dossier builder + the canonical abstention rule `is_confident`. Harnesses:
  `engine/bench_os.py`, `engine/bench_full.py`, `engine/ab_13dg.py`.
- **It plateaus at ~50% exact** (control-vs-passive judgment is irreducible — triple-confirmed). Good for the
  easy slice + as LLM INPUT; NOT a standalone exact-float engine.
- **The hybrid LLM tail is validated** (`record_llm.py` records, `score_llm.py` scores): each abstained name →
  a routed agent reads the **compressed dossier** and derives the float. `det → Sonnet → Opus(escalation)`
  hit **10/12 within 10% (median 7%)** on the hardest tail and surfaced **2 likely label errors** in
  `float_is.csv` (**WHLR 2025-06-04, TGEN 2025-07-18** — re-derive/QC these). Results in
  `_llm_tail_results.csv` (Sonnet) + `_llm_tail_opus.csv` (Opus).
- **Cost now: ~$2–4K/yr** for the full non-OTC universe (~40K derivations) vs naive all-LLM ~$15–20K. The
  old "~$200 deterministic-only" target did NOT survive (LLM does the majority).
- **Path to ~$200/yr (target, not yet built):** LLM-as-compiler — a **CIK-keyed holder registry** (13F-filer
  passive backbone, free + LLM-classified control entities, cached) + **per-ticker float-recipe cache** +
  **event-driven recompute** (re-judge only when a new O/S/13D/13G filing changes the recipe). See §16.
- **Runtime note:** these run as **Workflow** sub-agents on the Max plan (no API key), **3 agents at a time**
  per the updated `CLAUDE.md`, durably recorded (resume-safe). `CLAUDE.md` was rewritten 2026-06-25 (generic
  guidelines + TEMP: 3 agents max, interruption-resilient, surface concerns first). The float gate is now
  **all-floats-exact** (the <20M-gate framing was dropped).
- **§16 lever 1 STARTED — `engine/holder_registry.py` built + tested.** CIK-keyed holder-classification
  registry (`holder_registry.json`): `classify(name, form_type)` → passive | control | judge, via
  (1) cached verdict, (2) keep-list (the recurring passive complex), (3) **CIK-verified 13F-filer** (efts →
  holder CIK → that CIK's submissions contain 13F-HR ⇒ institutional manager ⇒ passive on a 13G), else
  (4) **judge** → LLM classifies ONCE → `set_class()` caches it. **Form-type gate:** a 13D filer is never
  auto-passive (→ judge), which correctly routes Beach MHC / Bryant Riley / A. Gile. **Safe by design:** no
  control entity is ever auto-passive (verified — the only auto-passives are real institutions). Recall is
  partial (some institutions fall to judge-then-cache); that's a cost miss, never an accuracy error. On the
  12 hard-tail names: 14% free / 85% judge-once-cached (a floor — representative stocks are mostly
  institutional 13G ⇒ much higher free; value compounds as the cache warms across the universe).
- **Receipts-seeding TRIED → ABANDONED as unsafe (2026-06-25).** Bulk-seeding the registry from the
  receipts' `kept_13g` free-text pulls control entities as "passive" (e.g. Hannover Holdings — a 13D block;
  Jinshan Intl BVI — a foreign control shell; named individuals / family trusts), which would cause a
  false exclusion → wrong float. The free-text holder strings can't be cleanly partitioned (the §8.1
  name-noise problem). **Decision:** the registry warms ONLY from clean structured verdicts —
  `set_class()` called by the LLM tail when an agent names an entity + its class — plus the live
  keep-list / CIK-verified-13F checks. No bulk receipt seeding.
- **§16 levers 2-3 STARTED — `engine/recipe_cache.py` core built.** Per-ticker float-recipe cache +
  event-driven recompute. `replay(ticker, day)` computes the float deterministically (no LLM) on a later
  day; `is_stale()` re-fires the LLM only when an EXCLUSION-changing filing (13D/13G/proxy) appears after
  the recipe's date. **Design lesson (from a 25-ticker demo):** carrying the *whole* exclusion is too coarse
  (~20% exact — the D&O block drifts with insider Form-4 activity, and a deterministic O/S re-fetch diverges
  from the label's O/S). **Correct design (implemented):** re-fetch O/S **and** the D&O group (`group_exoptions`)
  deterministically every day, and carry ONLY the LLM's **control-block judgment** (`control_M`). Replay has
  the L8 O/S guards (XBRL-vs-regex disagree / multi-class / implausible → defer, never a wrong float).
- **§16 levers 2-3 VALIDATED end-to-end (2026-06-25).** Recipe-emit (3 Opus agents on recurring tickers
  KALA/NUKK/LIVE → `engine/validate_recipes.py`) emitted structured recipes (dno/control split + holders),
  `save_recipe()`'d them, warmed the registry (6→20 clean entities — the SAFE organic path works), then
  REPLAYED later candidate-days deterministically. Result on 14 later days: **35% replayed FREE (no LLM)**,
  of those **3/5 within 5%** (KALA exact for ~3 weeks then ~6% drift); the rest **correctly deferred** —
  NUKK→os-uncertain (multi-class XBRL-vs-regex), LIVE→stale (frequent 13D/proxy). The agents nailed the hard
  judgment (KALA kept Baker Bros passive despite its 13D tag; LIVE folded Isaac Capital into D&O to avoid a
  double-count). **Free-fraction is type-dependent:** clean single-class → high; multi-class/foreign → defer
  on O/S; frequent-filers → stale. So ~35% is a FLOOR (hard micro-caps); the broad universe (clean large/mid
  caps) is higher.
- **$200/yr — updated to ~$300–600/yr steady-state.** The recipe amortization is real but smaller than the
  optimistic ~3× (≈35% free on hard names, higher on clean → ~2× blended) × the cheap-model/compressed cut
  (~6×) ⇒ low hundreds, not a hard $200. Still ~30–50× under naive all-LLM (~$15–20K) and ~6–12× under the
  current hybrid (~$2–4K).
- **§16 levers 2-3 IMPROVED — replay free-fraction 35%→50% (2026-06-25, commit `96f4bc3`).** Two fixes to
  `recipe_cache.replay`, both accuracy-safe (only ever defer MORE, never a wrong float): (a) **O/S anchoring** —
  the recipe's LLM-validated `os_at` is a magnitude anchor; a 30x XBRL-vs-regex gap is a regex MISPARSE
  (authorized shares), so anchor on `os_at` to reject it instead of a symmetric disagree-veto (fixed NUKK,
  whose clean single-class XBRL was vetoed by a 150M authorized-shares regex hit); (b) **carry the exclusion
  in shares** — store + carry the LLM's `dno_M` AND `control_M`, held fixed against the drifting O/S exactly
  as the LABELS are built (D&O constant between proxies). The old deterministic D&O re-fetch re-read the SAME
  proxy (no intra-proxy drift to capture) at the proxy's stale PRE-split basis → the reverse-split bug (NUKK
  dno=11M on a 52.7M basis vs 5M O/S → negative float → implausible). Removed it; added a `proxy-changed` guard
  (new ownership source → defer to LLM). On the validated set: FREE 35%→50% (7/14), within-5% 3/5→4/7, bad
  deferrals 2→0; the remaining 7 deferrals are all `stale` (real structural events, correctly → LLM).
- **§16 FULL-SCALE $0 ACCURACY SIMULATION (2026-06-25, commit `6737db2`).** `engine/sim_replay.py`: the
  LABEL is the ground-truth recipe at its derivation day (exclusion = os_M − float_M), so we replay every
  later labeled day through `recipe_cache.replay()` and score vs the labels — proving the recipe system at
  **236-ticker / 383-later-day scale for $0** (no LLM; the one thing it can't test, "can the LLM produce the
  split," is already proven on KALA/NUKK/LIVE). **Findings:** naive replay = 52% free but **26% of free
  replays miss >10%**, archetype-concentrated (foreign/ADS without a carried ADS ratio, reverse splits,
  multi-class, IPO churn) and — key — **NOT gated by derivation confidence** (the misses are REPLAY-TIME O/S
  problems: a name clean at derivation gets corrupted by a later split/offering/basis-change). Gap-form guards
  are too blunt (`calib_guard.py`: defer 32–81 accurate to catch 30–41 misses). The clean knob (`calib_band.py`):
  the `os_selected/os_at` ratio — accurate replays barely move O/S (ratio~1.0); basis-change/split misses land
  outside. **Two accuracy-safe fixes applied:** (a) tighten the replay anchor band 8×→**±30% (k=1.3)** —
  calibrated knee (`calib_band.py`) catches ~30/52 misses at ZERO cost to accurate replays; (b) add **424B
  offering forms to `is_stale`** (new `OS_EVENT_FORMS`) — an offering CLOSES at a 424B but the XBRL O/S fact
  LAGS it (refreshes only at the next 10-Q), so a deterministic re-fetch is stale → treat as an event that
  re-fires the LLM (the §16 event-driven-recompute principle; the AGEN/HUSA frozen-XBRL failure mode).
  (c) **reverse-split defer** (`_split_in_window`, commit `e27f8c3`) — a reverse split changes the share
  basis but XBRL keeps reporting the PRE-split count until the next periodic; the announcing 8-K can predate
  derivation, so defer if a "reverse split"+ratio 8-K is filed in [derived−30d, day] (kills the HUSA 899%).
  (d) **close a band leak** (`a0b0b48`) — the XBRL-vs-regex agreement fallback bypassed the anchor band when
  the regex echoed a stale wrong-class O/S (METCB Class-A 44M vs the listed Class-B 10.7M anchor → 315%);
  gate it on `not anchor`. (e) **revised/additional proxies** (DEFR14A/DEFA14A/PRER14A → `STRUCT_FORMS`,
  `4c76ae7`) — a revised proxy updates D&O just like a definitive one; catches AGEN (DEFR14A restated O/S
  between 10-Qs while XBRL froze) at zero false-defers. **FULL $0 ARC (naive → carry-dno + band + 424B +
  split + leak-fix + proxy-rev) on the 236-ticker / 383-later-day IS sim: free 52%→37% | within-5% 62%→75% |
  within-10% 73%→90% | misses 26%→9% | WORST-CASE 899%→30% | median 0.1%.** Every dropped free replay was wrong/uncertain — the band/leak fixes
  shed ONLY bad replays; 424B + split are accuracy↔cost knobs (tune via `OS_EVENT_FORMS` / the lookback).
  **Residual ~10% are all SOFT now (11–30%, no catastrophes):** foreign/ADS O/S-source (UBXG/PRE/MB — a real
  LLM recipe carries the ADS ratio, so these are sim artifacts), AGEN frozen-XBRL+8-K dilution (no 424B/split
  signal — needs 8-K item reading, diminishing returns), a few clean drifts (SRM/XCUR/BSGM), and label errors
  (TGEN). **Bottom line: recipe-replay is ~37% free at ~90% within-10% / 75% within-5% accuracy, worst-case
  30%, on its proper domain; everything uncertain routes to the LLM.** Re-run: `python sim_replay.py`
  (resume-safe ~10 min) then score; `calib_band.py` / `calib_split.py` reproduce the knees. Outputs gitignored.
- **§16 RECIPE-EMIT WAVE — 30 REAL recipes, end-to-end PROOF (2026-06-26, commit `33477f7`).** Ran
  `workflows/recipe_emit_wave.js` (30 agents, 3-at-a-time, ~1.2M tokens, ~42 min) over a stratified IS wave
  (5 per archetype). Each agent self-fetched its dossier (`emit_worklist.py dossier T`), derived the recipe
  (basis + dno/control split + ADS ratio + held/excluded holders) via structured output;
  `engine/merge_emitted.py` resolved CIKs + folded into `_recipes_emitted.json` (33 total); `recipes.json` +
  `holder_registry.json` warmed; `validate_recipes.py` scored. **Results (REAL recipes, not label stand-ins):
  DERIVATION 75% within-5% / 84% within-10% / median 1.3%; REPLAY 60 later-days, 38% free (matches the sim),
  of free 69% within-5% / 95% within-10% / worst 12% / median 1.1%; REGISTRY 20→135 entities.** The ADS ratio
  carrying WORKS (ARBKL ads=10) — the foreign/ADS residual that capped the sim at 30% worst-case is GONE
  (worst replay now 12%). The guard stack deferred every bad recipe (ATNF negative float → implausible;
  LIMN/MARPS/MTR → no-os/no-proxy; LIVE/NUKK → stale). **Label-QC candidates the agents surfaced** (derivation
  vs label disagreements to review): **ANNA** (agent 3.53 excl Nautilus/Wilder 37M control SPV vs label 29.44
  KEPT it → likely label error), **ATNF** (agent −0.59 over-excl Elray 47.8% 13D vs label 4.10), BNGO (split
  basis), ARBKL (ADS ratio 10 vs implied ~8), BMGL (control-SPV size). Re-run: `python merge_emitted.py`
  (from `_wave_emitted_raw.json`) then `python validate_recipes.py`. **The 30-ticker wave PROVES the system;
  the full 236 is the production cache-warming step (one-time, amortizing), NOT required for proof.**
- **§16 BENCHMARK QC + O/S AUDIT (2026-06-26, commits `a3f67ae`, `032fc64`, audit commit).** Resolved the 7
  wave disputes via `workflows/label_qc.js` (investigate + adversarial verify, 14 agents) — BUT independent
  spot-checking (reading primary filings myself) **overturned the agents on 4 of 7.** ⚠ **Key reliability
  lesson: two SAME-MODEL adversarial agents share blind spots — their unanimous high-confidence verdicts are a
  SIGNAL, not ground truth for benchmark edits; an independent tool/human check is mandatory.** Outcome:
  **3 real label errors CORRECTED** in `float_is.csv` (+ derived ledgers, via `engine/apply_qc.py`):
  **ANNA** 29.44→3.53 (Wilder's Nautilus 30.48M = 75.05% of Class A → it IS listed Class A; label wrongly
  called it exchangeable), **BNGO** 1.84→3.36/4.68 (actual 10-Q covers 3.364M/4.681M; label O/S stale),
  **ATNF** 4.10→3.73 (Elray 13D control sits in the D&O group via a board voting agreement) → derivation
  accuracy **84%→90% within-10%**, and the only remaining recipe misses are exactly where the AGENT erred.
  **4 were AGENT errors, label stands:** ARBKL (agents' 577M ord < the 20-F floor 638M — impossible),
  BMGL (agents kept founder Yip), TGEN (agents missed a 7/18 offering 24.99M+3.5M=28.49M AND over-excluded
  Hatsopoulos family trusts), WHLR (O/S 0.56M correct post 1-for-7 split; float ambiguous in toxic dilution).
  Then a **SYSTEMATIC O/S audit** (`engine/audit_os.py` + `audit_triage.py`) cross-checked all 952 labels' os_M
  vs corroborated single-class XBRL: 15 flags → 12 XBRL-stale (split/offering in the gap → label right) →
  3 candidates → **all 3 FALSE** (KIDZ: XBRL tagged founder Class A, listed class is Class B = label; PRCH:
  voting-only vs total incl non-voting; PBM: foreign annual). **Benchmark O/S is accurate — 0 new errors.**
  The residual label-error frontier is float/control-JUDGMENT (multi-class like ANNA), not O/S — rare, not
  cheaply detectable; a same-model agent sweep is unreliable for it (see the 4/7 lesson).
- **▶ Next:** (1) ~~reduce replay deferrals~~ DONE; ~~$0 accuracy guards~~ DONE (worst 899%→30%);
  ~~prove with real recipes (30-wave)~~ DONE (replay 95% within-10%); ~~QC the disputes + audit O/S~~ DONE
  (3 labels corrected, O/S verified clean). (2) OPTIONAL: run the full 236-ticker recipe-emit to warm the
  production cache (same `recipe_emit_wave.js`, full `emit_worklist.py` list, now 6-at-a-time; one-time,
  amortizes). (3) OPTIONAL: deeper float/control-judgment audit (the ANNA-class errors) — needs careful
  per-ticker primary-filing review, NOT a same-model agent sweep. Artifacts: `recipes.json` +
  `_recipes_emitted.json` (33 recipes, versioned cache), `holder_registry.json` (135 entities); harness:
  `engine/{sim_replay,calib_band,calib_split,emit_worklist,merge_emitted,dump_filing,apply_qc,audit_os,audit_triage}.py`
  + `workflows/{recipe_emit_wave,label_qc}.js`.
