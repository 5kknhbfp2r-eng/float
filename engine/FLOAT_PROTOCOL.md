# FLOAT_PROTOCOL.md — how a Claude session computes a per-name float (STEP 2)

> The engine runs **Claude-in-the-loop** (no API key): a Claude session reads the dossier from
> `float_gather.py` and emits a **decision JSON**, which `float_score.py` turns into a float +
> sanity flags and (in dev) scores against DT. Work HARD per name — fetch more, re-read, try an
> alternate basis — because the backtester pulls only ~3 names/day, so per-name effort is cheap.

## The definition (lock to this)
`float = O/S − (officers + directors + control-affiliates + non-passive >20%-of-O/S holders)`
- **O/S** = current shares outstanding AS OF the as_of_date (use the cover-page / XBRL figure;
  reconcile with any post-proxy 8-K/6-K issuance — see basis "multidoc").
- **Exclude:** officers & directors (the "as-a-group" ex-options figure is the clean source);
  **control affiliates** (founder/parent/sponsor entities, board-nominee VCs, >20% control
  persons, BVI/holdco shells "wholly owned by [a person/insider]"); **>20%-of-O/S** holders that
  are NOT passive.
- **Keep (do NOT exclude):** passive institutions — 13G/index filers (BlackRock, Vanguard, T.
  Rowe, Renaissance, most hedge funds) — EVEN above 20%, unless they have a board seat/control.
- ">20%" is judged on **actual O/S fraction** (shares ÷ O/S), NOT the filing's beneficial %
  (which inflates via options/warrants/as-converted).

## Read the dossier, then pick the BASIS TYPE1. **normal** (mature proxy/20-F): float = O/S − D&O-group(ex-options) − rule-selected non-D&O
   holders. Dedup a holder appearing in several rows/footnotes (count once, largest real block).
2. **spac**: a "subject to possible redemption / redeemable" block ⇒ float ≈ the public
   redeemable shares. (If a de-SPAC business combination 8-K issued new shares before as_of,
   switch to multidoc with the new O/S.)
3. **ipo** (fresh listing; table says "owned after our IPO" / tiny public %): float = the IPO
   **offering size** ("offering of N ordinary/common/ADS" on the 424B), incl. greenshoe if
   "(or M shares assuming over-allotment)".
4. **multiclass_ads**: filing counts are in ordinary shares but O/S/float trade as ADS — find
   the ratio (ADS:ordinary, or "based on N ordinary shares" ÷ DT-O/S) and rescale every holder
   before subtracting. (HLG: founder 360M ord ÷16 = 22.5M ADS.)
5. **goprivate** (DEFM14A merger): exclude the **rollover / buyer-group** shareholders (they roll
   into the private parent), not just the named D&O. Find the rollover total in the merger doc.
6. **multidoc**: the proxy's O/S is stale — a later 8-K/6-K shows a PIPE / offering / split /
   business-combination. Use the **current O/S** and exclude affiliated PIPE/insider blocks.
   (TOP: founder 30M + PIPE 214.4M = excl 244.4M.)

## MANDATORY pre-flight checklist (do NOT emit a high/medium decision until all true)
You MUST satisfy these before a confident answer; if any fails, go fetch (below) until it
passes, or mark the name `low`/quarantine:
- [ ] **Current O/S confirmed** from a filing dated near as_of (not a stale proxy). If the
  ownership proxy is >~120d old OR its O/S conflicts with a later filing, fetch the latest
  10-Q/10-K (US) or 20-F (foreign) and use THAT O/S.
- [ ] **The ownership/D&O table was actually read** (not just a 5%-holders or TOC fragment).
- [ ] **Share basis reconciled**: if foreign-ADS, the ADS:ordinary ratio is resolved and
  applied; if a reverse/forward split post-dates the table, it's applied.
- [ ] **No unexplained gap**: if your excluded set is far from what a controlled name implies
  (e.g. D&O own ~0% but the name is clearly controlled), a holder is hiding in a 13D/G or
  prospectus — go find it.

## Odd / delisted / foreign ticker won't resolve? Use the robust resolver
If `gather()` says NO CIK, the DT ticker just isn't in SEC's static map (delisted, renamed, or a
DT-specific symbol). Call `float_gather.resolve_cik(ticker)` — it falls back to a sec-api
full-text search for the listing symbol ("Company (TICKER)") and returns the real CIK. (This is
how IMG resolved → "CIMG Inc. (IMG)" CIK 1527613, O/S 89.97M = DT exactly.) Only after this still
fails is a name truly unresolvable. Then list_filings/fetch_one work normally with that CIK.

## Pick the RIGHT filing per situation (a fixed rule is NOT enough — choose by filer type)
- **Current O/S:** US filer → latest **10-Q/10-K** cover; foreign filer → latest **20-F** (its
  6-K usually has NO O/S). SPAC/recent dilution → the **8-K** for the event.
- **Ownership/D&O table:** US → **DEF 14A** (NOT the 10-K); foreign → **20-F** Item 6/7.
- **Hidden ≥5% holder:** the **13D/13G** (`form-13d-13g`) or the IPO **prospectus**.
- **ADS ratio:** the 20-F cover / "each ADS represents N ordinary".
- **Split ratio:** the 8-K / proxy "X-for-Y reverse split".
If after the right fetches DT still can't be matched and your number is internally sound, DT is
likely wrong (e.g. CIIT: current 10-Q O/S ~25M vs DT 3.62M) — emit your number + flag DT-divergent.

## Pull MORE filings on demand (agentic retrieval — use freely; throughput is low)
The starting dossier from `gather()` is a head-start, not the limit. If anything is missing or
stale, get the rest yourself — do NOT settle for an incomplete picture:
- `float_gather.list_filings(ticker, as_of)` → the cheap filing INDEX (types/dates/accession,
  filedAt ≤ as_of). Browse it to find what you need.
- `float_gather.fetch_one(ticker, accession, what=)` → pull ONE filing focused:
  `what='os'` (O/S candidates + ADS note), `'ownership'` (table), `'cover'`, or `'full'`.
- **Always do this when:** the ownership proxy is STALE (grab the latest 10-Q/10-K for current
  O/S — this caught ALCE, whose real O/S is ~4M while DT's 600M was the *authorized* count, a DT
  error); O/S sources conflict; a SPAC/PIPE/offering/split post-dates the proxy; the D&O table
  looks suspiciously empty (a control block may be in a 13D/G or prospectus).
- Do NOT dump whole filings indiscriminately — fetch the specific ones the index tells you you
  need (full texts are ~1MB and bury the signal). Index first, then targeted fetches.

## Before you EVER write UNRESOLVED — exhaust the filing search (mandatory ladder)
"Can't find it" is almost always "didn't look hard enough." Run the FULL ladder first:
1. `resolve_cik(ticker)` (delisted/renamed/foreign — IMG→CIMG).
2. `list_filings(ticker, as_of, limit=40)` — the WHOLE index, ALL form types (not just proxy/10-K).
   Pull the current O/S from the latest 10-Q/10-K/20-F; pull **13D/13D-A** for control blocks the
   ownership table omits (SORA's control holders); pull **8-K/6-K** for splits/PIPEs/redemptions;
   pull the **F-1/424B pre-IPO holder list + lock-up** for fresh IPOs whose excl exceeds the named
   D&O+>5% set.
3. Reconcile splits / ADS ratios / ATM-or-PIPE share growth so O/S matches the as_of date.

Only after the ladder fails, classify the UNRESOLVED reason — and these two are a TRUE
SEC-data boundary (not an engine failure; DT's number, if any, is non-SEC-sourced or stale):
- **DEREGISTERED**: a Form 15 (15-12B/15-12G) with no later company filing (PIXY/ShiftPixy,
  deregistered 2024 — no O/S after).
- **PRIVATE / Form-D-only**: the entity files only Form D exempt-offering notices, no
  10-K/20-F/S-1/proxy (OSN Technologies) — there is no public ownership disclosure to derive.
Report these as `UNRESOLVED: data-boundary (deregistered | private)`. A name that merely needs a
doc you haven't fetched is NOT a boundary — go fetch it.

## Delisted / deregistered / acquired is NOT a dead end — fall back to the last filing
SEC never removes filings. If the ticker was a public SEC filer that later deregistered/was
acquired (Form 15), DO NOT return UNRESOLVED: fetch its **last ownership filing of ANY date ≤
as_of** (the pre-Form-15 10-K/proxy/DEFM14A — always on EDGAR) and the **latest periodic
(10-Q/10-K) ≤ as_of** for the then-current O/S, and compute float from those. Verified: SAL/CTEK
reproduce DT's O/S exactly from their last DEFM14A; KDNY/HCDI need the last 10-Q for current O/S.
**Backtest framing (critical, avoids lookahead bias):** `as_of` = the TRADING date. At a trading
date when the company was live, all its filings exist → fully resolvable. Never treat a company
as untradeable because it *later* delisted — that is lookahead bias; the future Form 15 is simply
≥ as_of and ignored. The ONLY genuine UNRESOLVED is an entity that was NEVER a public SEC filer
(pure Form-D private, e.g. a shell that reused a ticker) — and you would not be backtesting a
never-public name anyway (no price history).

## Noisy / multi-event names (splits + ADS + offerings stacked) — DO NOT give up
The hardest names stack several transforms; work them in this fixed order (the `⚠ RECONCILIATION`
block in the dossier surfaces each signal). NEVER conclude "self-contradicting / unresolvable" just
because the ownership filing shows conflicting counts — that almost always means an unreconciled
transform, not a dead end (this is the AZI failure):
1. **CURRENT O/S first.** Use the latest periodic's count (10-Q/10-K/20-F/6-K ≤ as_of), NOT a
   number from a months-old proxy. Splits and offerings are ALREADY baked into the current count.
2. **Split/consolidation** — if detected, the current O/S already reflects it; do not double-apply.
   A "45.5M (preamble) vs 1.9M (cover)" conflict is just pre- vs post-consolidation — use current.
3. **ADS ratio** — if ADS-listed, DT's O/S is in **ADS**. Find "each ADS = N ordinary" (check the
   F-1/424B/deposit agreement if not in the 20-F) OR infer it (ordinary_O/S ÷ ADS_O/S ≈ a clean
   integer). Convert EVERY ordinary holder block by ÷N before subtracting. (AZI: 44.89M ordinary
   ÷ 10 = 4.49M ADS = DT's basis exactly — the agent that called AZI "unresolvable" simply never
   did this division.)
4. **Post-filing dilution** — offerings/PIPEs filed after the ownership filing grew O/S; the
   current-periodic count already includes them.
Then float = (current ordinary O/S − control ordinary) ÷ ADS_ratio.

## NEVER DROP — UNRESOLVED means ESCALATE, not skip (critical for a noisy-name strategy)
A name you can't pin is **flagged for second-pass / review**, NEVER silently dropped. Emit a
best-estimate float + `confidence: low` + the exact blocker (e.g. "ADS ratio not found", "O/S
sources conflict"). The harness routes low/unresolved names to a MUST-REVIEW queue and re-runs
them with this noisy-name procedure; a name is abandoned only after a second human/LLM pass also
fails. Dropping a noisy name is the worst outcome — those are the targets. For a <20M-float
cutoff, also emit the threshold side even when the exact float is fuzzy (often the decision is
unambiguous — e.g. AZI ~3–4M ADS is clearly <20M regardless of the exact count).

## Self-verification (REQUIRED before emitting)
- O/S used matches the cover-page / XBRL figure (cross-check the candidates list); if a recent
  8-K changed it, reconcile and say so.
- 0 ≤ float ≤ O/S; float not absurd (e.g. ~0 only if genuinely ~100% controlled).
- Every excluded holder's block ≤ O/S; no holder double-counted across rows.
- Passive 13G/index holders are NOT in the excluded set unless they hold a board seat.
- If two readings are plausible (e.g. is a VC a control affiliate?), pick the better-supported,
  LOWER-confidence, and note the alternative.

## Confidence rubric
- **high**: clean D&O-group + obvious control holders; O/S confirmed; one basis clearly applies.
- **medium**: a judgment call on one holder, or a rescale/multidoc reconciliation you're fairly
  sure of.
- **low**: ambiguous control classification, O/S sources conflict, exotic structure, or the
  dossier is missing a number you need (say what you'd fetch next). The backtester should
  quarantine/skip/hand-check **low**.

## Decision JSON (emit EXACTLY this; float_score.py consumes it)
```json
{
  "ticker": "HLG",
  "as_of": "2026-06-04",
  "basis_type": "multiclass_ads",
  "os_shares": 25780000,
  "os_source": "412,450,256 ordinary ÷ 16 ADS ratio = 25.78M ADS",
  "excluded": [
    {"name": "Hailiang Feng", "shares": 22500000, "reason": "founder/control (BVI trusts), 87% — rescaled to ADS"}
  ],
  "kept_notable": [],
  "float_shares": 3280000,
  "confidence": "high",
  "notes": "ADS rescale ÷16; no passive institutions present"
}
```
`float_shares` must equal `os_shares − Σ excluded[].shares` for basis normal/multiclass/goprivate/
multidoc; for **spac** set `float_shares` = redeemable public shares; for **ipo** = offering size
(put the rationale in `os_source`/`notes`). float_score.py re-derives and FLAGS any mismatch.
