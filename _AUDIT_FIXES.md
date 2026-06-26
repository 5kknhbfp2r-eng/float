# Audit fix ledger (branch: audit-fixes)

Durable progress tracker for the engine-hardening sprint (option 4). Full finding detail in `_AUDIT_2026-06-26.md`.
Status: [ ] todo  [~] in-progress  [x] done  [-] skipped/needs-decision.  Commit ref noted when done.
Resume = read this file; do the next [ ] in dependency order; run the harness; commit; mark [x].

DESIGN-DECISION items (do NOT auto-fix; need user nod): F27 (per-archetype band), F28 (model D&O drift),
F48 (recalibrate band on float-error after the denominator fix). Marked [-] below.

## A. replay (recipe_cache.py)
- [x] **F01** (CRITICAL/confirmed) `recipe_cache.py:29-37,124,154-155` — SPAC/IPO carried-float replay has NO staleness signal for the 8-K events that actually change it (de-SPAC, redemptions, IPO lock-up/dilution)  (f28e074)
- [x] **F04** (HIGH/confirmed) `recipe_cache.py:24-25,111` — Reverse-split detector misses 'consolidation' phrasing (foreign reverse splits) and requires a ratio token, re-opening the HUSA pre-split-O/S failure for foreign issuers  (f28e074)
- [x] **F06** (HIGH/confirmed) `recipe_cache.py:116-173` — Frozen-XBRL-fact staleness guard (calib_age) never ported to replay -> stale O/S replays as confident-wrong 'ok'  (f28e074)
- [x] **F12** (HIGH/confirmed) `recipe_cache.py:37,97-113,124` — Foreign issuers (ads_ratio != 1): is_stale and _split_in_window ignore 6-K, so 6-K-announced reverse splits and share issuances replay as a wrong free float  (f28e074)
- [x] **F17** (MEDIUM/confirmed) `recipe_cache.py:139-170` — Anchor band compares raw ordinary xv against os_at whose semantics contradict the recipe-emit spec -> ADS replays dead (cost) or wrong-anchored (accuracy)  (f28e074)
- [x] **F22** (MEDIUM/uncertain) `recipe_cache.py:29-31,83-94` — is_stale misses DEF 14C / PRE 14C / DEFR14C information statements -> control/D&O/reverse-split changes effected by written consent replay as a wrong free float  (f28e074)
- [-] **F27** (LOW/confirmed) `recipe_cache.py:139-153,170-172` — Single global ±30% anchor band ignores the recipe's own confidence and archetype, leaving safe-cost and accuracy on the table  — RESOLVED: no change (band can't catch ratio~1 float-misses; data-backed)
- [x] **F28** (LOW/confirmed) `recipe_cache.py:158-170` — dno_M/control_M carried fixed in shares assumes zero D&O drift between proxies — true vs the self-referential label, an unquantified real-world error for the production OOS path  (50ea735)
- [x] **F29** (LOW/uncertain) `recipe_cache.py:139-140,170` — ADS-ratio unit convention (exclusion carried in ADS units, O/S anchored in ordinary) is implicit and undocumented in the replay formula — a latent wrong-unit float on the next ADS recipe  (f28e074)
- [x] **F30** (LOW/confirmed) `recipe_cache.py:97-113` — _split_in_window caps 8-K fetch at size=30; a long-lived recipe window can truncate the older end and miss a reverse-split announcement  (f28e074)
- [x] **F45** (LOW/confirmed) `recipe_cache.py:97-113,168` — _split_in_window runs on the FREE happy path and fetches up to 30 8-K full texts per replay day  (f28e074)
- [x] **F46** (LOW/confirmed) `recipe_cache.py:139-140` — Anchor band silently disabled when os_at is falsy (0/missing) -> band cannot reject a misparse  (f28e074)
- [x] **F47** (LOW/confirmed) `recipe_cache.py:170-171` — Implausibility upper bound fl > os_*1.01 is in mismatched units for ads_ratio>1, making it ~ads_ratio x too loose  (f28e074)

## B. registry (holder_registry.py)
- [x] **F03** (CRITICAL/confirmed) `holder_registry.py:91-105, 119-124` — 13F-filer name match accepts a single shared token, auto-classifying a control person/entity as passive (false exclusion)  (d9fb002)
- [x] **F05** (HIGH/confirmed) `holder_registry.py:113-124` — Registry lookup precedes the 13D-active gate, so a 13F-auto-cached entity that later files a 13D is returned passive (control block kept in float)  (d9fb002)
- [x] **F08** (HIGH/confirmed) `holder_registry.py:33-41, 51-52, 113, 122, 133` — Registry/_F13 keyed solely on norm(name); aggressive normalization collapses distinct entities, propagating one verdict to all  (d9fb002)
- [x] **F16** (MEDIUM/confirmed) `holder_registry.py:33-41,113,122,133` — Holder registry is keyed on normalized NAME, not CIK (contrary to its own docstring) — distinct entities can collide to one verdict; one entity under two spellings is re-judged  (d9fb002)
- [x] **F19** (MEDIUM/confirmed) `holder_registry.py:22-30, 64-65, 117-118` — Keep-list uses unanchored substring regexes over the full name, auto-passing unrelated entities  (d9fb002)
- [x] **F39** (LOW/uncertain) `holder_registry.py:113-116` — Registry lookup precedes the 13D-active gate, so a cached 'passive' verdict overrides a 13D control signal  (d9fb002)

## C. edgar/gather (edgar.py, float_gather.py)
- [x] **F02** (CRITICAL/confirmed) `edgar.py:117-140` — resolve_cik_edgar picks the highest-relevance EFTS hit, not the point-in-time filer — returns the WRONG entity for reused tickers  (f28e074)
- [x] **F38** (LOW/confirmed) `edgar.py:90-105` — Filing ordering uses acceptanceDateTime (UTC) while the point-in-time filter uses filingDate (ET business date) — sort inversions across mixed forms  (f28e074)

## D. probes (_cik/_widen/_affil_probe.py)
- [x] **F09** (HIGH/confirmed) `_cik_probe.py:57-71` — resolve_via_query mis-resolves CIK: no exact-ticker check + overwrites mapping's verified None  (da13924)
- [x] **F10** (HIGH/confirmed) `_widen_probe.py:134-138, 280-282` — AFFIL footnote regex over-matches passive holders -> false affiliate exclusion (too-low float)  (da13924)
- [x] **F11** (HIGH/confirmed) `_widen_probe.py:227-229` — >88% holder rows are silently dropped, not deferred -> controlled-company float reported far too high  (da13924)
- [x] **F20** (MEDIUM/confirmed) `_widen_probe.py:187-198, 199` — Affiliate footnotes only scanned AFTER the group row -> missed affiliates in pre-group 5% tables (too-high float)  (da13924)
- [x] **F21** (MEDIUM/confirmed) `_widen_probe.py:233-237, 257-273` — Foreign 'linked' affiliate test fires on a single shared name token -> false affiliate exclusion (too-low float)  (da13924)
- [-] **F44** (LOW/confirmed) `_widen_probe.py:276-279` — Identical share-count across distinct holders skips the second exclusion -> possible missed control block  — deferred to design — name-aware dedup would re-introduce different-name deemed-relist double-count (verifier)

## E. formula (_formula_probe.py)
- [x] **F07** (HIGH/confirmed) `_formula_probe.py:510-532` — Solver double-counts the SAME holder (multiple source/amendment rows summed) -> spurious exclusion in the recovered formula  (747b9c7)
- [x] **F36** (LOW/uncertain) `_formula_probe.py:679-697` — A D&O-section row kept as a candidate is ALSO included in the 'dno' group basis -> same holder counted in both the group and the holder leg  (747b9c7)
- [x] **F37** (LOW/confirmed) `_formula_probe.py:84-87` — holders() retains the `~basic` ex-warrant variant as a distinct candidate that the solver can sum with the full row  (747b9c7)

## F. extract (float_from_filings.py, det_float.py)
- [x] **F18** (MEDIUM/confirmed) `float_from_filings.py:84-129` — extract_shares latches onto AUTHORIZED count instead of OUTSTANDING (authorized-vs-outstanding confusion)  (32ccf70)
- [x] **F31** (LOW/uncertain) `det_float.py:267-271, 389-404` — is_confident treats IPO basis_route float as a confident FREE float ("ipo" missing from ABSTAIN_TOKENS while "spac" is present)  (32ccf70)
- [x] **F32** (LOW/confirmed) `det_float.py:309-317, 389-404` — Reverse-split rescale band misses small reverse splits / has no guard when the proxy %-basis (iosb) is unparseable  (32ccf70)
- [x] **F33** (LOW/uncertain) `float_from_filings.py:104` — extract_shares silently drops legitimate share counts above 5 billion  (32ccf70)
- [-] **F34** (LOW/confirmed) `float_from_filings.py:68-73` — Share count split across an HTML tag boundary is unparseable after fetch_text whitespace-collapse  — deferred — below reporting bar, regression risk to adjacent-number lists (verifier)
- [x] **F35** (LOW/confirmed) `det_float.py:63-79` — ADJACENT (live, det_float.regex_os): authorized-vs-outstanding causes needless osdisagree DEFERs  (32ccf70)

## G. scoring (sim_replay/bench_*/validate_recipes/calib_band/oos_cost)
- [x] **F13** (HIGH/confirmed) `sim_replay.py:65-67` — sim_replay scores error relative to O/S, not float — all downstream accuracy claims use the wrong denominator  (9acb0c5)
- [x] **F14** (HIGH/confirmed) `bench_full.py:108,115-116` — bench_full reports accuracy-on-confident relative to O/S (os_relerr), not float — same denominator overstatement as the sim  (9acb0c5)
- [x] **F23** (MEDIUM/confirmed) `bench_full.py:69-72` — bench_full's inline confidence rule diverges from canonical is_confident — overstates confident coverage and pollutes accuracy-on-confident with cases production routes to the LLM  (9acb0c5)
- [x] **F24** (MEDIUM/confirmed) `validate_recipes.py:43-44,53` — validate_recipes scores replay accuracy relative to O/S, not float (same denominator bug) and reports it as 'within 5%'  (9acb0c5)
- [-] **F48** (LOW/uncertain) `calib_band.py:25-36` — Production anchor band (k=1.3) was calibrated against O/S-relative error, so it emits 24 float-wrong-as-'ok' replays the metric never counts as misses  — RESOLVED: no change, keep k=1.3 (tightening catches 0/19 float-misses)
- [x] **F49** (LOW/confirmed) `oos_cost.py:24-29` — oos_cost over-counts LLM cost: never caches a derivation within the run, so a recurring OOS ticker is billed as N full derivations instead of 1 derive + (N-1) free replays  (9acb0c5)

## H. workflows (recipe_emit_wave/parallel_sweep.js)
- [x] **F15** (HIGH/confirmed) `recipe_emit_wave.js:44-56` — recipe_emit_wave.js has NO durable per-agent write — a usage-credit stop mid-run loses every already-paid recipe in the current run  (8a15388)
- [x] **F25** (MEDIUM/confirmed) `recipe_emit_wave.js:49-52` — recipe_emit_wave.js pins no model — the largest run (203 tickers) uses the harness default, leaving the hardest archetypes' accuracy and the total token bill unspecified  (8a15388)
- [x] **F26** (MEDIUM/confirmed) `parallel_sweep.js:24` — parallel_sweep carry-forward checks only O/S-relevant filings — a new 13D/13G/proxy control change between dates carries a stale (too-high or too-low) float  (8a15388)
- [x] **F50** (LOW/confirmed) `recipe_emit_wave.js:31,34` — dossier command ignores as_of — prompt hardcodes `as_of ${it.a}` but the dossier always fetches the ticker's earliest labeled day, so a batch where a != earliest-day derives a recipe on mismatched filings  (8a15388)

## I. ledger (record*/merge_emitted/remaining.py)
- [x] **F40** (LOW/confirmed) `record_may.py:24-48` — record_may.py lacks the confidence/column-shift guard and writes a now-derived file (silent row loss)  (186cf72)
- [x] **F41** (LOW/confirmed) `record.py:34-44` — Ledger writers/readers open float_is.csv without encoding=utf-8 (cp1252 risk on non-ASCII notes)  (186cf72)
- [x] **F42** (LOW/confirmed) `merge_emitted.py:26-30` — merge_emitted.py folds recipes with cik=None without flagging, yielding unreplayable recipes  (186cf72)
- [x] **F43** (LOW/confirmed) `remaining.py:50-52` — remaining.py carry-forward hint uses first row in file order, not the earliest/most-recent prior day  (186cf72)
