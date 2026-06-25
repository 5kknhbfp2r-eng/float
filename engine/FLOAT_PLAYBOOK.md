# FLOAT_PLAYBOOK.md — archetype catalog distilled from the Phase-1 150-sample

> Read alongside `FLOAT_PROTOCOL.md`. This is the empirical playbook: every one of the 150
> Phase-1 names was solved by ONE of the archetypes below, with the basis + exclusion + any
> rescale shown. Match the dossier (`float_gather.py`) to an archetype, then apply its pattern.
> Distribution across the 150 → your PRIOR on which to try first.

## Decision order (priors from the 150)
1. **Is there a "subject to possible redemption / redeemable" block?** → **SPAC** archetype.
2. **Is the table framed "owned after our IPO" / is it a fresh-listing 424B?** → **IPO** archetype.
3. **Are the filing's share counts ≫ DT O/S (ADS) or is there a reverse/forward split?** → **RESCALE** first, then a basis below.
4. **Is it a 20-F with an Item-7 "major shareholders" whole-register %?** → **ITEM7**.
5. Else **NORMAL**: float = O/S − D&O-group(ex-options) − non-passive >20%/control blocks.
6. **Heavily controlled (named founders/parents/PIPE dominate)?** → **CONTROL-SUBSET** (no D&O group; the named blocks ARE the exclusion).

## The archetypes (with Phase-1 worked examples)

### A. NORMAL — D&O as-a-group, ex-options  (exo: 44/150 = 29%, the plurality)
float = O/S − (officers+directors "as a group" ex-options) − any non-passive >20%/affiliate block.
- `AMLX`: keep ALL 13G funds (FMR/BlackRock/Vanguard/…), exclude D&O ex-options ~8.2M → 0.1%.
- `CNCK`: D&O group + Monex Group (>20% parent, feat `>AS`) excluded.
- Sum the individual D&O rows instead if there's no group row (**dno: 13/150** — e.g. `MRT`: exclude Durgun/Oktem control + D&O).

### B. CONTROL-SUBSET — exclusion IS the named holder set  (none: 59/150 = 39%)
Heavily controlled; no D&O-group basis. Exclude the founder/parent/PIPE/shell blocks directly.
- `EM`: Taobao 76.4M + Xiaomi 47.0M (strategic >20%, feat `>AS`) … excluded.
- `BRLT`: Just Rocks 49.5M + Mainsail 31.8M (sponsor/PE control) excluded; keep passive.
- `TOP`: founder 30M + **PIPE 214.4M** (multidoc — later 6-K) → excl 244M.
- BVI founder-shell LADDER (e.g. LGCL out-of-sample): 11 entities each "wholly owned by [person]".

### C. SPAC — O/S − redeemable public shares  (osRedeem: 3/150)
float ≈ the "subject to possible redemption" block.
- `ENHA` → redeemable 20M = float (DT os=395M reflects a later de-SPAC issuance; the float is the public block).
- `PITA`, `MVLA` (MVLA also rescaled f0.31).

### D. IPO — float = the public offering size  (osOffering: 2/150)
- `MENS`: offering 2,666,667 = float (excl = O/S − offering).
- `WTF`: offering + greenshoe ("or M shares assuming over-allotment").

### E. ITEM7 — 20-F whole-register major-shareholder exclusion  (item7: 6/150)
- `AENZ` (clean), `CCG`, `RCT` — foreign; exclude the Item-7 major-holder register.

### F. MULTI-CLASS — per-class or absolute-count basis  (mcAbs/cls: ~6/150)
- `FEAM`: `mcAbs` (sum classes ≤ O/S; drop the as-converted/voting column) + Ascend (>20%).
- `GRAN`: exclude only ONE class (Class A), not the sum.
- `ITMR`: `cls0` × ADS factor.

### G. RESCALE overlay — ADS / split  (17/150 carry factor≠1)
Apply to ANY archetype when filing counts ≠ DT O/S basis. Factors actually seen in the 150:
- **ADS**: ÷16 (`HLG`, factor 0.063), ÷30 (`ITMR`, 0.033), ÷10–15 (0.068–0.103), ÷4 (`JFIN`, 0.25).
- **reverse split**: e.g. `SST` 1:10 (0.10); **forward split**: factor 85.4 (`SYT`, ordinary≫ADS the other way).
Ratio = (filing "based on N ordinary shares") ÷ (DT O/S), or the stated ADS:ordinary ratio.

## Holder classification (Phase-2 discriminators — apply within every archetype)
- **EXCLUDE**: officers, directors, **control affiliates** (founder/parent/sponsor; BVI/holdco
  "wholly owned by [insider]"; board-nominee VC/PE; >20%-of-O/S control person), pre-IPO insiders.
- **KEEP**: passive 13G/index/most hedge funds (BlackRock, Vanguard, FMR, T. Rowe, Renaissance,
  Janus, Perceptive…) — **even >20%**, unless they hold a board seat.
- ">20%" is judged on **actual O/S fraction** (shares ÷ O/S), not the filing's beneficial %.
- **Affiliate exclusion is size-gated** (Phase-1.5: excluded affiliates median ~15% vs kept ~4.5%) —
  a small footnote-tagged ≥5% institution is usually KEPT.
- **Foreign 20-F**: control shells / pre-IPO holders are excluded much more often than on US names.

## Coverage note
exo+dno+ben (D&O-group family) + none (control-subset) = ~62% of names use NORMAL/CONTROL-SUBSET;
SPAC/IPO/ITEM7/MULTI-CLASS/RESCALE are the structured minority but each has a clean rule above.
Anything you cannot place in an archetype, or where O/S can't be confirmed → confidence LOW (quarantine).
