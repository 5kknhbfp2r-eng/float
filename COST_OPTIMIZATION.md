# COST OPTIMIZATION — making float derivation cheaper (workstream notes)

> Captured from a design discussion. The IS float dataset was built with an LLM reading every
> dossier (Opus on hard names, Sonnet on easy). The user wants the SAME accuracy (incl. exact
> float, not just the <20M gate) at much lower cost. This file is the plan + evidence so a fresh
> session can pursue it. NOT yet built — the recommended first step is a benchmark (see §4).

> **⚠ ACCURACY IS NON-NEGOTIABLE (user directive, 2026-06-25).** Every `(ticker, day)` must get an
> **exact** free-float, not merely the `<20M` gate decision. Two otherwise-tempting cheap levers are
> therefore **DECLINED**: the **O/S-only pre-gate** (§7.7) and **trade-cohort tiering** (§9, "honest
> floor") — both settle the *gate* without computing the exact float, so they trade accuracy for cost.
> Do not use them. **Every other lever in this file is accuracy-preserving**: they cache or structure the
> *inputs and the holder-classification judgment*, never the float arithmetic itself. The headline
> question the user raised — *can the passive-holder allowlist be extended into a global keep-list?* — is
> answered, and measured against our own receipts, in **§8**.

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

---

## 7. Further levers — the Oxford pass (what §1–6 missed)
> Captured from a second design discussion + a verification pass. §1–6 had named: compress LLM input,
> deterministic fast-path, the gate reframe, carry-forward, caching, EDGAR-not-sec-api, and the free
> 13D/13G form-type rule. These are the remaining levers — where the rest of the money actually is.
> Items checked against live EDGAR / the API on 2026-06-25 are marked **✓ verified** (proof in §9).

**7.1 O/S is a structured XBRL fact — stop regex-parsing it. ✓ verified.** Every 10-K/10-Q tags
cover-page shares outstanding as `dei:EntityCommonStockSharesOutstanding`. SEC serves it free and
**point-in-time** at `data.sec.gov/api/xbrl/companyconcept/CIK##########/dei/EntityCommonStockSharesOutstanding.json`
— a list of dated facts, each carrying its source `form` + `filed` date, so point-in-time selection =
*take the fact with the largest `filed ≤ as_of`*. The **Frames API**
(`.../xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY2025Q2I.json`) returns the **entire
universe in one call**. This replaces the regex O/S leg — the single biggest input — with a clean
structured fetch; handles multi-class via XBRL members. **Caveat:** foreign 20-F filers on IFRS often
don't tag it → those stay on the regex/LLM path (and our non-OTC scope still has China/Israel 20-F names).

**7.2 Infra discounts on whatever LLM remains — ~70–95% off, zero accuracy cost. ✓ pricing verified.**
- **Batch API = −50%** on all token usage (float derivation is async, not latency-sensitive). Max 100K
  requests / 256 MB per batch; most finish < 1 h, max 24 h.
- **Prompt-cache the protocol** (`FLOAT_PROTOCOL.md` + `FLOAT_PLAYBOOK.md` are byte-identical every
  call): cache **read ≈ 0.1× input (−90%)**; cache **write 1.25×** (5-min TTL) or **2×** (1-h TTL).
  Put the static protocol first, the per-name dossier last, behind the breakpoint.
- **Drop to Haiku** for extraction once the input is pre-structured (you're reading numbers, not
  reasoning over a 20-F). Per-MTok input/output: **Haiku 4.5 $1/$5 · Sonnet 4.6 $3/$15 · Opus 4.8 $5/$25.**
  Batch + cache + Haiku stack to ~$0.005/name.

**7.3 Agreement-gated escalation (the smart router).** Run deterministic + a cheap model; **accept when
they agree, escalate to Opus only on disagreement or low confidence.** This is the fix to what we
actually overspent on — re-deriving *all* ~122 May hard names on Opus when only ~4 were wrong. Opus then
only ever touches genuine disagreements.

**7.4 A global passive-holder allowlist.** The index complex (BlackRock, Vanguard, FMR/Fidelity, State
Street, Geode, Dimensional, T. Rowe …) covers most 13G holders; classify them passive *instantly*, reused
across **every** stock. **This is the user's headline question — fully worked, measured, and generalized
in §8.**

**7.5 Use the LLM as a *compiler*, not a *worker*.** Run it once over the 1,025 labels (+ active learning
on names the deterministic engine is unsure about) to **generate/refine the rules**, then run the rules
forever at ~$0. The LLM becomes a one-time cost that *shrinks the tail over time*, not a recurring
per-name cost.

**7.6 Event-driven recompute.** Combine `manifests\` (already records each float's filing dependencies)
with EDGAR's filing feed: recompute a ticker **only when it files something O/S-relevant**. Turns
carry-forward into a true delta system — most tickers, most weeks, cost nothing.

**7.7 O/S-only pre-gate (volume filter). — ✗ DECLINED (breaks the exact-float requirement).** For the
`<20M` decision alone, O/S settles it when O/S `<20M` (float ≤ O/S, so it's a candidate) — ~40–50% of
names free, zero holder work. *But it yields no exact float for those names*, which the user requires.
Recorded for completeness; **do not use.** (The accuracy-preserving cousin we DO keep: O/S as a structured
fetch, 7.1 — that still feeds the full derivation.)

**7.8 SEC bulk data for universe runs.** `companyfacts.zip` + `submissions.zip` sidestep the ~10 req/s
EDGAR rate limit entirely for a full-universe pass.

### Levers added in the verification pass
**7.9 Form 3/4/5 XML = the structured *exclude* leg. ✓ filings enumerable.** Insiders (officers,
directors, 10% owners) file Form 3/4/5 as XML, each with the reporting person's own CIK and current
holdings (`SharesOwnedFollowingTransaction`). The set of an issuer's Form-3/4 filers **is** its D&O list,
machine-readable — so the exclude side's insider component is *also* a free structured fetch, not a
proxy-table parse. (The control-block component — 13D filers, >20% non-13G — stays form-type-driven.)

**7.10 Separate "structured-but-fiddly" from "irreducible judgment."** The hard-archetype tail we routed
to Opus isn't all judgment. Split/ADS/multi-class reconciliation is **mechanizable**: the XBRL O/S fact
already reflects post-split shares and is tagged per class member; ADS ratios ("each ADS = N ordinary")
are stable per ticker (cache once). What's genuinely irreducible is **control classification** (acting-in-
concert family blocks, pre-IPO SPVs, ambiguous 10–20% strategics). Mechanize the former; spend LLM only on
the latter.

**7.11 Deterministic self-routing / abstention triggers.** Replace `triage.py`'s text heuristics with
free structured flags that force the LLM path: foreign filer (20-F/6-K **and** no `dei` O/S tag),
any >20% holder with a **13D** on file, multiple share classes where only one is listed, S-1/IPO within
trailing 12 mo, reverse split within trailing 90 days. Clean US single-class + XBRL O/S + all-13G holders
→ deterministic, done. Auditable routing instead of keyword guessing.

**7.12 Formalize the eval harness (operationalizes §4).** We have a perfect labeled set (1,025 rows in
`float_is.csv` + `receipts\`). Score any engine change automatically with three metrics: **gate-match %**
(binary <20M), **exact-float error** `|Δfloat_M|` (the user wants exact, so track magnitude not just the
gate), and a **per-archetype breakdown** (US-single-class / multi-class / foreign-20F / ADS / reverse-split
/ SPAC) so you SEE which slice fails. **Every name is verified to the same standard — no gate-band
shortcuts; the float must be exact whether it's 2M or 200M.** This turns "is it still accurate?" into a
defended number.

### The synthesized cheapest accuracy-preserving stack
XBRL O/S (free, 7.1) → **deterministic derivation** = O/S − Form-3/4 insiders (7.9) − 13D/>20%-non-13G
control blocks, **keeping** 13G/13F-filer passives (§8) → split/ADS/class reconciled mechanically (7.10) →
**agreement-gated escalation** (7.3) on the residual, routed by structured flags (7.11) → all on
**Batch + prompt-cache + Haiku/Sonnet** (7.2), escalating to
Opus only on disagreement → **LLM-as-compiler** (7.5) shrinks the residual each cycle; **event-driven
recompute** (7.6) makes steady-state nearly free. Every step yields an exact float. Realistic LLM spend for
the full non-OTC universe-year: **well under ~$50** — the cost becomes engineering time, not compute.

## 13. MEASURED: L1 (13D/13G form-type) built + A/B'd — confirms the plateau (2026-06-25)
Built the keystone lever end-to-end (`det_float.forms13` + `strat_13dg`): pull every 13D/13G filed *about*
the subject (they're in its cached submissions feed — no new fetch path), parse cover for reporting-person
+ "Aggregate Amount Beneficially Owned," classify by **form type**, and override the parser's noisy
g13/affil tags — matched 13G → keep, matched 13D → exclude, plus control-adds for 13D filers absent from the
proxy. **In isolation it fixes the right names** (HHS 6.69→4.16 vs label 3.91; CFSB finds Beach MHC's 13D
3.59M; RILYT finds Bryant Riley 7.04M). **But the A/B (60 names, coverage × accuracy-on-confident) is
net-NEGATIVE:**

| | confident coverage | O/S≤5% on confident | gate on confident |
|---|---|---|---|
| OFF (no 13D/13G) | 43% | 50% | 100% |
| ON (control-adds → abstain) | 30% | 44% | 100% |

**Why it doesn't beat the wall** (exactly the sibling's `_phase3_engine` finding, reproduced): form-type
gets the *classification* right, but the *magnitude/sourcing* reintroduces error — stale 13Ds, acting-in-
concert dups (Bryant Riley + B. Riley Financial), and blocks whose count is as-of the 13D date not as_of.
Routing the uncertain control-adds to abstain (the correct, accuracy-preserving move) trades coverage for
honesty but **doesn't lift accuracy-on-confident past ~50%**. The deeper problem: **~half of "confident"
deterministic floats are wrong under EITHER setting**, because a missed control block is *invisible* to
deterministic confidence unless it filed a clean, current 13D — and many don't (foreign shells, family
acting-in-concert, holders inside dual-class/major-holder tables). Deterministic confidence cannot reach
the sibling's ~100%-on-confident bar; only the LLM's per-name judgment does.

**Conclusion (two independent lines of evidence — sibling Phase-3 + this A/B):** the deterministic engine
**plateaus on holder judgment AND on confidence calibration**. Pushing it further on the holder axis (L5
control_named, L6 13F) is more of the same axis → low expected value. **The cost win is NOT a more-accurate
deterministic engine — it's the architecture:** deterministic resolves the genuinely-easy slice
(clean US-single, no control block — reliably ~exact) + the GATE + surfaces structured hints (incl. the
13D/13G blocks), **abstains the rest**, and a **cheap compressed-LLM pass** (Batch+cache+Haiku, fed the
structured summary, §7.2) does the control-judgment tail. That MAINTAINS accuracy (the LLM does what only it
can) at a fraction of the naive cost. L1's lasting value: the 13D/13G blocks are excellent **LLM input**
(pre-classified control/passive candidates), not a deterministic answer.

**Remaining levers worth trying are a DIFFERENT axis (O/S foundation, not holder judgment):** L3 (multi-class
listed-class O/S via XBRL member dimension + ADS-ratio divide) targets the 0%-coverage archetypes;
L4 (Form-4 exact D&O) tightens clean-name floats. These raise deterministic *coverage* (→ fewer LLM calls)
without fighting the judgment wall. L7/L8 (abstention/staleness) are the accuracy guarantee.

## 14. MEASURED: L3/L4/L7/L8 done — the deterministic ceiling is ~50% exact, full stop (2026-06-25)
Completed the remaining deterministic levers and measured each. **All confirm the same ceiling.**

- **L3 (multi-class / ADS O/S):** probed — most "foreign/ADS" failures are NOT ADS-units (ratios are `None`;
  they trade ordinary directly). The real errors are staleness (HOLO 40:1 split), wrong-entity/class (ARBKL
  9×), later dilution (FMST/SUPX). XBRL `companyfacts` doesn't carry member labels → can't pick the listed
  class. So multi-class **abstains** (xbrl_n>1) and a true-ADS (ratio>1.5) **abstain** flag was added. Yield: low.
- **L4 (Form-4 exact D&O):** probed on 14 clean US names — `g_exo` **already** matches the recorded
  exclusion to ~1-5% (OCC 1.95→1.95, LINK 8.23→8.22, LCUT/AMLX/TWIN/VERB ≈). The D&O block is **not** the
  bottleneck; control blocks are (Form-4 = insiders, doesn't address them). **Not built** — work for ~0 gain.
- **L7 (abstention):** built the canonical rule `det_float.is_confident()` (shared by the bench and the
  future LLM router). **Decisive measured finding: abstention cannot lift precision-on-confident past ~50%**
  — tuning it only trades coverage, because the residual error is **missed control blocks, invisible to any
  O/S/structural signal**.
- **L8 (staleness / O/S-disagreement):** added `+stale` (proxy >550d) and `+osdisagree` (XBRL-vs-regex O/S
  >30% = wrong-entity, e.g. ARBKL). The real foreign/ADS guard — abstain the unreliable O/S — but, like all
  abstention, it can't beat the ceiling.

**THE BOTTOM LINE (now triple-confirmed: sibling Phase-3 + L1 A/B + L3/4/7/8):**
| metric | deterministic, on the confident slice |
|---|---|
| **gate (<20M)** | **100%** — reliable, cheap |
| **exact float (O/S≤5%)** | **~50%** — NOT trustworthy for the user's exact-float requirement |

No deterministic lever combination "maintains accuracy" for *exact* floats — the control-judgment tail is
irreducible. **The LLM is non-optional for exact accuracy** (this is exactly why the sibling pivoted to it
and hit ~95%). The deterministic engine's **settled role** in the cost-optimal stack:
1. **The gate** — reliable on the confident slice at ~$0.
2. **Trivial-clean-name exact floats** — large-caps / no control block (g_exo ≈ exclusion).
3. **Aggressive abstention** (`is_confident`) — route everything uncertain to the LLM, never emit a
   confident-wrong exact float.
4. **Cheap structured LLM INPUT** — XBRL O/S + D&O block + 13D/13G hints (`forms13`) + reconciliation, so
   the LLM pass is compressed (Batch+cache+Haiku/Sonnet, ≈$0.005/name) instead of reading raw filings.

`USE_13DG=False` for the deterministic emit (A/B net-negative); `forms13()` is retained purely as LLM input.

**▶ NEXT (the actual cost+accuracy win): build the LLM tail.** For each (ticker, day): `det_float.full` →
if `is_confident` emit deterministic; else feed the compressed structured dossier to the LLM and emit its
float. Validate the whole hybrid against the full 1,025 labels + DT. That is where "cost-effective while
maintaining accuracy" is actually realized — the deterministic work above is what makes the LLM pass cheap.

## 15. MEASURED: the LLM tail works — det → Sonnet → Opus cascade (2026-06-25)
Built the compressed-dossier LLM tail (`det_float.compressed_dossier`: XBRL O/S + regex cross-check +
deterministic estimate/abstention + the 13D/13G blocks as control/passive HINTS + proxy ownership window)
and ran it on a **12-name HARDEST-tail slice** (all abstained: foreign/ADS, multi-class, SPAC, reverse-split,
near-zero float). On Max (no API $), **one agent at a time → then 3 at a time** per CLAUDE.md, durably
recorded (resume-safe: `record_llm.py` → `_llm_tail_results.csv` / `_llm_tail_opus.csv`).

**Sonnet alone (compressed dossier):** exact O/S≤5% 1/12, ≤10% 6/12, median 11.4%. Real work (BBGI caught
XBRL "150M = authorized not outstanding"; EMPG nailed the IPO offering), but **over-excluded** on control-
judgment (trusted the dossier's "CONTROL(13D)" tag too literally).

**Escalate the 6 worst to Opus (same compressed dossier) → cascade result:**
| | within 5% | within 10% | median |
|---|---|---|---|
| Sonnet only | 1/12 | 6/12 | 11.4% |
| **det→Sonnet→Opus cascade** | **5/12** | **10/12** | **7.0%** |
| cascade, excl. 2 likely label-errors | — | **10/10** | — |

- **Opus recovered every model-tier miss:** ARQQ 3.8%, SATL 0.6%, BRLS exact, MTR exact (Sonnet had over-
  excluded or fallen for the 13D-tag trap; Opus judged control-vs-passive correctly).
- **The 2 remaining "misses" are likely LABEL errors, not engine errors** — Opus diverges with detailed,
  defensible reasoning: **TGEN** (label 26.4 kept the Hatsopoulos founder-family control trusts; Opus excludes
  them → 13.5M) and **WHLR** (insiders hold convertibles, not outstanding common → float≈O/S). The LLM tail
  **surfaces label errors** (the sibling found this too). → flag WHLR/TGEN in `float_is.csv` for review.

**Verdict — the cost-while-accurate architecture is validated:**
- **deterministic (free)** handles the easy slice + the GATE-free O/S + builds the compressed dossier;
- **Sonnet (cheap)** clears the moderate abstained names (~half, within ~8%);
- **Opus (escalation only)** nails the hard control-judgment tail — and even improves on the labels.
The compressed dossier is **sufficient input** even for Opus (each agent ~30-44K tokens incl. dossier +
reasoning), so the input-compression lever (§7.2) holds. Only the hardest ~third needs Opus → cost-efficient.

**Pipeline fixes from Opus's notes:** (1) the dossier's `CONTROL(13D)` tag misled the weaker model (MTR: A.
Gile is a passive investment *adviser* that filed 13D) → softened to "13D = active stake, JUDGE control-vs-
passive." (2) the L3 `adsOS` flag false-positives ordinary-listed foreign names (ARQQ is direct Nasdaq, not
ADS) → harmless (just an extra LLM call), note for later.

---

## 8. Extending the passive allowlist → a CIK-keyed global keep-registry (the headline ask)
**Question (user, 2026-06-25):** *"Could the global passive-holder allowlist be extended? Or even make a
global keep-list? Or something in that vein?"* Short answer: **yes — and the right generalization is not a
longer hand-typed list of names, but a CIK-keyed, two-sided, self-growing registry backed by the
enumerable 13F-filer universe. It preserves exact-float accuracy because it caches the *classification*
decision, never the share arithmetic.**

### 8.1 What the receipts actually show (measured, not guessed)
Parsed all **917 receipts** (`engine\data\_cache\receipts\*.json`): **1,668 "kept" holder entries**,
**1,746 "excluded"**. The KEEP decisions concentrate hard on the classic passive complex, exactly as
lever 7.4 supposed — recurring named keepers (count of receipts):
`BlackRock 120 · Vanguard 93 · FMR/Fidelity 27 · Dimensional 15 · T. Rowe 12 · Point72 11 · BVF 10 ·
Morgan Stanley 9 · Baker Bros 8 · RA Capital 5 · Deep Track 5 · …`. Note the **second tier is biotech-
specialist passive funds** (Baker Bros, RA Capital, Deep Track, BVF, Perceptive, Cormorant, Vivo, Soleus,
Venrock) — they recur because this momentum universe is biotech-heavy, and a generic BlackRock/Vanguard
list misses them.

Two honest caveats the data forced:
1. The receipt holder names are **noisy free text** (`"Kept=3.04M BlackRock(13G),2.50M D.E.Shaw(13G)"`,
   and the *same* manager appears as "BlackRock Inc." / "BlackRock Fund Advisors" / "BlackRock Institutional
   Trust"). A hand-name list will always under-match — a ~40-name seed list matched only ~18% of "kept"
   strings, but ~⅓ of the misses were unnamed aggregates ("Kept=27.5M") and most of the rest were parsing
   artifacts + the biotech tail, **not** a different population. The receipts were never built as a holder
   ledger.
2. There is a genuine **idiosyncratic tail** in the misses: foreign-IPO affiliate SPVs and family blocks
   (Feelux, Ewon, Nongae, RedPeony, "Chi Yuen Leong 122K", Kingston/Yunis …) — the irreducible
   control-judgment names.

**Conclusion the data points to:** key holder identity on **filer CIK**, not cover-page name strings, and
back the list with a *universe*, not hand curation.

### 8.2 The reframe: a registry, keyed on CIK, in three parts
The "allowlist" is really an **entity → classification cache**. Build it as three structured registries:

- **(A) Global KEEP registry (passive).** Keyed on **13G/13F filer CIK** (robust; join on the filing's
  filer CIK, not a fuzzy name). Seed from our receipts (the names above). Mark each `passive-always`.
- **(B) Per-company INSIDER set (exclude).** From Form 3/4/5 XML (7.9) — the issuer's own officers/
  directors, with their own CIKs and current holdings. This is the exclude side and it is *company-specific*
  by nature.
- **(C) The 13D-vs-13G form-type rule (exclude vs keep).** The primary signal for outside blocks: 13D =
  active/control (exclude), 13G = passive (keep). Free, structured, already in §1.

### 8.3 The real "extension": back the KEEP registry with the 13F-filer universe ✓ verified
Don't hand-curate 100 names — **every registered institutional manager files Form 13F-HR**, and that set is
**enumerable from EDGAR** (efts returned 1,209 13F-HR filings in a single week, each with a filer CIK). So:
*a 13G filed by an entity that is a registered 13F filer is passive by construction* → keep. That single
rule generalizes the ~40-name seed list to **thousands** of institutions for free, and it's exactly the
judgment the LLM was being paid to make. The hand list then only needs to cover the **non-13F passive
oddballs** (some family offices, sovereign/index vehicles) — a short, stable set.

### 8.4 Is a global *exclude* list the dual? Mostly no — and that's important.
A global **exclude** list is the wrong abstraction for most of the exclude side, because **control is
company-specific** (a company's own officers/directors — handled by (B), Form 3/4). The only
globally-reusable exclude entities are cross-ticker activists/sponsors (Armistice, Sabby, Hudson Bay,
GTCR-type PE) — and those **toggle 13D/13G by situation**, so hard-excluding them by name would *introduce*
errors. Correct handling: flag-for-LLM, not hard-exclude. So: **global KEEP list = high value; global
EXCLUDE list = small, risky → prefer form-type (C) + Form 3/4 (B).**

### 8.5 Self-maintaining (this is what "extend it" should mean operationally)
When a holder CIK appears that's on neither (A) nor (B) and isn't a 13F filer, the cascade classifies it
**once** and writes it to the registry with its CIK. Over a universe-year the registry **saturates**: the
long tail of one-off names shrinks each cycle (this is lever 7.5, LLM-as-compiler, applied to holder
identity). The registry *is* the growing allowlist — not a frozen 100 names.

### 8.6 Why this never costs accuracy
You still compute `free_float = current_O/S − Σ(actual excluded shares for THIS ticker)`. The registry only
answers the boolean *"is this holder a control-affiliate or a passive keeper?"* — the expensive judgment —
and caches it by CIK across tickers. The **share counts are always the real, point-in-time numbers** from
this ticker's filings. So the exact float is unchanged; only the per-name *classification* work is
amortized. That is precisely the lever that's compatible with the user's "every float exact" requirement.

### 8.7 Build order
(1) Add a `holders.csv` registry keyed `cik → {name, aliases, class: passive|control|judge, source}`,
seeded from the receipts' recurring keepers. (2) Add the 13F-filer-CIK membership test (cache the filer
list). (3) Wire (B) Form-3/4 insider sums and (C) 13D/13G form-type into `det_float.py` (§4). (4) Score
against the 1,025 labels with the §7.12 harness; whatever still misses is the genuine judgment tail → LLM.

---

## 9. Verified against live EDGAR + the API (2026-06-25)
So a future session trusts the claims above rather than re-checking:
- **XBRL O/S** — `companyconcept` for GOGO (CIK 1537054) returned **53 dated facts** of
  `dei:EntityCommonStockSharesOutstanding`, each with `form` + `filed`; point-in-time selection works
  (`filed ≤ as_of`). **✓ 7.1.**
- **Frames (whole universe, one call)** — `CY2025Q2I` returned **4,556 issuers** (matches the ~4–5k
  exchange-listed estimate in §5). **✓ 7.1.**
- **13F-HR filers enumerable** — efts returned **1,209** 13F-HR filings for one week (2025-08-01…07), each
  with a filer CIK → the passive-institution universe is fetchable. **✓ 8.3.**
- **Anthropic pricing** (claude-api skill) — **Batch −50%**; prompt-cache **read 0.1× / write 1.25× (5m)
  · 2× (1h)**, TTLs 5-min & 1-h; per-MTok **Haiku 4.5 $1/$5 · Sonnet 4.6 $3/$15 · Opus 4.8 $5/$25**;
  model IDs `claude-haiku-4-5` / `claude-sonnet-4-6` / `claude-opus-4-8`. **✓ 7.2.**
- **The honest floor (unchanged, and why tiering stays declined):** an irreducible few % — acting-in-
  concert family blocks, pre-IPO SPVs, ambiguous 10–20% strategics — needs real judgment (it's where DT
  itself errs); foreign-20F O/S without an XBRL tag keeps a regex/LLM path. **Trade-cohort tiering**
  (exact float only for the <20M cohort, O/S-bound estimate for the rest) is the single largest remaining
  saving — and the user has **declined it**, because every float must be exact. Noted, not pursued.

---

## 10. MEASURED: deterministic engine built + scored vs the labels (2026-06-25)
> The user asked to *prove what works / what doesn't* on **only enough compute** to demonstrate a system,
> then double-check against the full 1,025 + DT. Built `engine\det_float.py` (XBRL O/S leg 7.1 + the reused
> `_widen_probe` exclusion machinery — D&O group ex-options, >20%/affiliate strat with **13G kept**,
> foreign Item-7 register, reverse-split/ADS rescaling) and two harnesses (`engine\bench_os.py`,
> `engine\bench_full.py`) that score against the **point-in-time** `float_is.csv`. Ran on ~200 names
> (mostly cache → ≈$0). Scales to the full set by raising `K`; outputs `_bench_os.csv` / `_bench_full.csv`.

**O/S leg (foundation) — WORKS.** 108-name stratified sample: XBRL returned a value on **80%**, and was
within 1% on **65% of those** (vs regex 76% coverage / **24%** ≤1% — so XBRL ≫ regex on precision).
US-single-class **16/18 ≤1%**. XBRL coverage gaps + precision misses are concentrated exactly where
predicted: **multi-class** (flat `dei` concept can't pick the *listed* class) and **foreign/ADS** (IFRS
untagged; ordinary-vs-ADS units).

**Full float (O/S − exclusions) — gate WORKS, exact float DOESN'T (yet).** 90-name sample:
- **Gate (<20M): 89% of computed** (76% of all) — strong, and the strategy only needs the gate. Per
  archetype gate✓: IPO 14/14, foreign/ADS 10/10, split 13/14, US-single 14/15, SPAC 9/10, multi-class 9/14.
- **Exact float ≤5%: only 24% of computed** (median error 26%). Clean US-single names are near-exact
  (KSS 110.91→110.92, FULC 50.20→50.20, BLDE, VIGL exact), but the rest miss.

**Error census (77 computed-with-label rows) — this is the actionable part:**
| class | share | cause | fix |
|---|---|---|---|
| ≤5% exact (good) | **24%** | clean: O/S − D&O group | — |
| **UNDER-excluded** (det > label) | **41%** | missed a sub-20% **control/insider** block the proxy didn't total | **13D form-type fetch + Form 3/4 insiders** (§1, §7.9) — NOT yet wired in |
| OVER-excluded (det < label) | 23% | kept too little / double-count / treated a passive as control | **13G + 13F-filer keep rule** (§8) |
| O/S wrong (label float > our O/S) | 10% | multi-class wrong-class pick | per-class member / proxy, route to LLM |

**The decisive finding:** the **O/S foundation is solved** by XBRL; the bottleneck for *exact* float is
**holder classification** — under+over-exclusion together are **~64% of the error**, and that is precisely
the **13D-vs-13G form-type + Form-3/4 insider + 13F-passive** legs from §1 / §7.9 / §8 that `det_float.py`
does **not yet use** (it only excludes >20% / footnote-affiliates). Also: **of 58 misses, 32 already
self-flag** (`noderiv` / `multiclass` / regex-O/S) → the engine knows when it's unsure, so abstention-
routing (§7.11) cheaply hands those to the LLM.

**So the proven system shape:** XBRL O/S (deterministic, exact on clean) → deterministic exclusion with the
holder-classification legs added → **agreement-gate / abstain** on the self-flagged residual → LLM closes
the exact-float tail. The gate is already ~89% deterministically; exact float needs the holder leg built.

**▶ Next experiment (highest measured value):** wire the **13D/13G form-type fetch + Form-3/4 insider sums
+ 13F-filer passive keep** into `det_float.py`, re-run `bench_full.py` — this targets ~64% of the current
error — then double-check the winner against the **full 1,025 + DT** (`dt_os_float_2026-06-04.csv`) by
raising `K`. Until that leg exists, the deterministic engine is a **gate classifier + clean-name exact
float**, not an exact-float engine for the hard tail.

---

## 11. PRIOR ART — the sibling repo already ran this experiment to its conclusion (2026-06-25)
Read-only review of `..\claudebacktest_init2-2.4\` float docs (`FLOAT_HANDOFF_2026-06-18_K.md`,
`PHASE1/2/3`, `FLOAT_OOS30*_SCORECARD.md`, in the `claudebacktest - from estimated time sapi update mdi3\`
dir). It **independently confirms** §10 and reframes the build. The current `float/` engine code
(`_formula_probe.py`, `_widen_probe.py`, `_affil_probe.py`) was **copied from that work** — so the
machinery below already sits in our repo.

**The headline (matches §10 exactly):** their *predictive* deterministic engine (`_phase3_engine.py`)
**plateaus at ~18% within-5% of DT** — our independent run got 24%. Same wall, two ways. Their diagnosed
causes are our error census:
1. **Exclusion BASIS is stock-type-dependent** → needs a router (SPAC→`os−redeemable`, IPO→`os−offering`,
   foreign→major-holders/Item-7, else D&O group + holder rule). = our multi-class/SPAC/foreign misses.
2. **Holder classification from PARSED footnote tags is noisy both ways** — over-tags big 13F institutions
   DT keeps (= our 23% over-exclusion) and under-tags foreign control shells (= our 41% under-exclusion).
3. They concluded the residual is **irreducible per-name judgment** and **pivoted to LLM-in-the-loop** —
   which is the very tool that produced our 1,025 labels (~95% OOS / ~96% gate agreement vs DT).

**What this REFRAMES:** a pure-deterministic engine is **not** a path to *exact* floats for the hard tail —
that's a documented dead end, and it's why the LLM tool exists. The deterministic engine's real job is the
**cost stack (§7)**: do the gate + clean names + bulk cheaply, and route the flagged residual to the LLM.
The 1,025 exact labels are already the LLM tool's output; det_float exists to make *future* derivation
cheaper, not to re-derive them.

**The ONE lever they did NOT try — and it attacks their root cause:** §2/§8's **actual 13D-vs-13G FORM
TYPE** (free EDGAR, filed by the holder about the subject) + the **13F-filer universe**, instead of the
parser's noisy footnote tags. Form-type fixes over-exclusion directly (BlackRock filed 13G → keep, whatever
the footnote heuristic guessed) and under-exclusion (a 12%-holder that filed 13D → control). This is the
genuine, grounded refinement worth measuring.

**Reusable assets already in our repo (don't rebuild):**
- `_formula_probe.holders(text, gm, os_m, foreign)` → holder rows with feat flags `do/deemed/gt20/affil/
  shell/g13/preipo`.
- `_formula_probe.redeemable_shares` (SPAC), `ipo_offering_basis` (IPO), `basis_factor` / `stated_basis_factor`
  (reverse-split/ADS rescale) — the **basis router** primitives.
- `_phase3_engine.excl_holder(sh, os_, feat, foreign)` — the **induced rule**: 13G keep-override · ≥20%-of-O/S
  → exclude · affiliate ≥10% → exclude · foreign shell/preipo ≥10% → exclude. (PHASE2 stage-1.5/2.)
- **`control_named` matcher** (PHASE2 Stage-4): a holder's distinctive name token within ±130 chars of
  control language (`controlling shareholder|parent company|predecessor parent|we established|entrustment
  agreement|founder of our/the`) — **validated zero false positives** on Vanguard/Point72/BlackRock/Capital
  World. Catches the under-tagged foreign control shells (the 41% under-exclusion class). In their git
  `_enrich_probe.py` (step .20.7); the regex is documented in PHASE2 if not copied over.

**Metric correction (load-bearing, from PHASE3):** report exact-float error as **% of O/S, not % of float**.
Tiny-float names amplify float-% from small absolute misses (a metric artifact); the gate compares absolute
shares to 20M, so O/S-relative is the right real-use metric. Our §10 "median 26%" is float-relative and
over-penalizes — re-scored O/S-relative in §12.

## 12. Re-scored with the right metric (O/S-relative) — the wall is still real
Same `_bench_full.csv` rows, error as **% of O/S** instead of % of float:

| archetype | N | gate✓ | float≤5% | **O/S≤5%** | med O/S-err |
|---|---|---|---|---|---|
| IPO/offering | 14 | 14 | 8 | 9 | 1.2% |
| SPAC | 10 | 9 | 0 | 3 | 8.8% |
| US-single-class | 15 | 14 | 6 | 7 | 21.2% |
| foreign/ADS | 10 | 10 | 2 | 2 | 49.5% |
| multi-class | 14 | 9 | 0 | 0 | 75.6% |
| split/reverse | 14 | 13 | 3 | 3 | 16.9% |
| **TOTAL** | **77** | **69** | **19 (24%)** | **24 (31%)** | **13.4%** |

O/S-relative lifts exact-≤5% from 24%→**31%** — real but modest, because most of our error is **genuine
under/over-exclusion**, not tiny-float amplification. multi-class stays 0% (wrong-class O/S pick is an
absolute error), foreign/ADS stays poor (ADS ratio). So even with the correct metric the engine sits in the
sibling's documented **~18–31% plateau**. Confirms: the deterministic engine is a **gate + clean-name**
tool; exact float on the controlled/foreign/multi-class tail is genuine per-name judgment (→ the LLM, which
already produced the 1,025 labels). The 13D/13G-form-type + 13F lever (§2/§8/§11) is the one untried way to
push the holder-classification axis; the basis-router tail (SPAC/IPO/multi-class) needs `_formula_probe`'s
router wired in. Both are cost levers (more names resolved deterministically = fewer LLM calls), not a route
to a standalone exact-float engine.

---

# ★ SUMMARY & TARGET ARCHITECTURE (read this first; sections above are out of strict order) ★
> Built + measured over 2026-06-25. Code: `engine/det_float.py` (deterministic engine + XBRL O/S +
> 13D/13G leg + compressed-dossier builder + `is_confident`), harnesses `engine/bench_os.py`,
> `engine/bench_full.py`, `engine/ab_13dg.py`, recorder `record_llm.py`, scorer `score_llm.py`.
> Results: `_bench_os.csv`, `_bench_full.csv`, `_llm_tail_results.csv` (Sonnet), `_llm_tail_opus.csv`.

## Lever ledger (final status)
| # | Lever | Status | Verdict |
|---|---|---|---|
| 7.1 | XBRL O/S (`dei:EntityCommonStockSharesOutstanding`) | ✅ done | works (89% ≤1% clean); 2.7× more precise than regex; foundation |
| 7.2 | Batch −50% / prompt-cache −90% / Haiku | ✅ verified pricing | core cost levers for the LLM tail |
| L1 | 13D/13G form-type + control-add | ✅ built, A/B'd | net-negative as a deterministic exclude (noisy magnitude/dedup); **kept as LLM INPUT hint** |
| L2 | Basis router (SPAC redeemable / IPO offering) | ✅ wired | SPAC redeemable is recency-sensitive → abstain; IPO offering works |
| L3 | XBRL multi-class member / ADS divide | ✅ probed | low yield (most foreign trade ordinary; multi-class can't pick listed class) → abstain |
| L4 | Form-4 exact D&O | ✅ assessed, NOT built | D&O block already exact (g_exo≈recExcl); bottleneck is control blocks, not D&O |
| L5 | control_named matcher | ⛔ deprioritized | same plateaued axis as L1 |
| L6 | 13F-filer passive backstop | ⛔ deprioritized as deterministic; **revived for the registry (§16)** | the passive backbone |
| L7 | Confidence/abstention (`is_confident`) | ✅ done | canonical rule; **caps ~50% exact-on-confident** (missed control blocks invisible) |
| L8 | Staleness / XBRL-vs-regex O/S disagreement | ✅ done | `+stale` (>550d), `+osdisagree` (>30%); foreign/ADS guard |
| L9 | LLM tail (compressed dossier + cascade) | ✅ validated | **det→Sonnet→Opus: 10/12 within 10% on hardest tail, median 7%** |

## What's proven
- Deterministic engine **plateaus ~50% exact** (control judgment irreducible — triple-confirmed: sibling
  Phase-3, L1 A/B, L3/4/7/8). It is NOT a standalone exact-float engine.
- The **hybrid cascade works**: deterministic (free) builds a **compressed dossier** → **Sonnet** clears
  moderate names → **Opus** (escalation only) nails the hard control-judgment tail (and even surfaced 2
  likely LABEL errors: WHLR, TGEN — flag in `float_is.csv`).
- **Cost today (full non-OTC universe, ~40K derivations/yr): ~$2–4K/yr** vs naive all-LLM ~$15–20K. The
  doc's old "~$200 deterministic-only" target did NOT survive (LLM does the majority, not a thin tail).

## §16 — TARGET ARCHITECTURE: how to reach ~$200/yr (LLM-as-compiler)
The $200 is reachable, but NOT by removing the LLM — by making each judgment **persistent & amortized**
(pay once, reuse forever, re-touch only on a triggering filing). Almost every hard call is a judgment about
a **stable entity**, not a (ticker, day):
1. **Global holder registry, keyed by filer CIK.** Passive backbone = the enumerable **13F-filer universe**
   (free) + the §8 keep-list; control entities = LLM-classified **once** on first encounter, cached. Seed
   from the 1,025 receipts. Re-judge a holder only when it files a **new 13D/13G** (free form-type trigger).
2. **Per-ticker "float recipe" cache** — listed class, ADS ratio, dedup/acting-in-concert groups, basis
   type, control set. LLM once; deterministic (XBRL O/S − recipe-excluded) on every other day at ~$0.
3. **Event-driven recompute** (existing `manifests/`) — LLM fires **only** when a new O/S-relevant or 13D/13G
   filing changes the recipe. Most O/S-change events change a *number* (deterministic via XBRL), not the set.
4. **Residual on Haiku + Batch + cache** — the task shrinks to "classify ONE new holder/recipe given
   structured context" (a light extraction job).

**Math (~20× from today's ~$4K):** caching recipes/holders + event-driven cuts ~40K derivations → ~14K
judgment-touches/yr (~3×); the shrunk task drops ~$0.10 → ~$0.015/touch on Haiku+batch+cache (~6×). →
**~14K × $0.015 ≈ $200–300/yr steady state** (Year 1 higher = pay-as-you-go warmup; receipts pre-warm it).
Accuracy preserved: caches re-judge on the **right filing triggers**, never silently stale.

**▶ Highest-leverage next build:** the CIK-keyed **holder registry** (seed from receipts + 13F list), then
the per-ticker recipe cache + event-driven recompute. Plus: re-derive the 2 flagged labels (WHLR, TGEN).
