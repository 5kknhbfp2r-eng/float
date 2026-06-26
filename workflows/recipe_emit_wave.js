export const meta = {
  name: 'recipe-emit-wave30',
  description: 'Emit 30 point-in-time free-float recipes (stratified IS wave) for the §16 recipe cache',
  phases: [{ title: 'Emit', detail: '30 tickers, 3 agents at a time, one structured recipe each' }],
}

// Stratified IS first wave (5 per archetype). Each agent self-fetches its dossier (no big args).
const ITEMS = [
  { t: 'ADPT', a: '2025-05-02' }, { t: 'ACOG', a: '2025-05-16' }, { t: 'ATNF', a: '2025-07-29' },
  { t: 'ANNA', a: '2025-06-25' }, { t: 'AAOI', a: '2025-06-18' }, { t: 'DAIC', a: '2025-07-01' },
  { t: 'AEHR', a: '2025-07-22' }, { t: 'ADUR', a: '2025-05-08' }, { t: 'ATYR', a: '2025-06-03' },
  { t: 'ASST', a: '2025-05-08' }, { t: 'ADN', a: '2025-08-15' }, { t: 'FOXX', a: '2025-07-17' },
  { t: 'AEVA', a: '2025-05-06' }, { t: 'APLM', a: '2025-07-09' }, { t: 'AVTX', a: '2025-07-17' },
  { t: 'BBGI', a: '2025-06-20' }, { t: 'ARAI', a: '2025-05-28' }, { t: 'LIMN', a: '2025-06-04' },
  { t: 'AGEN', a: '2025-06-03' }, { t: 'ARBKL', a: '2025-07-11' }, { t: 'BGLC', a: '2025-07-01' },
  { t: 'BKKT', a: '2025-05-13' }, { t: 'AUUD', a: '2025-06-27' }, { t: 'MARPS', a: '2025-06-13' },
  { t: 'ALMU', a: '2025-06-02' }, { t: 'ARQQ', a: '2025-05-16' }, { t: 'BNGO', a: '2025-05-14' },
  { t: 'BMBL', a: '2025-05-08' }, { t: 'BMGL', a: '2025-05-14' }, { t: 'MTR', a: '2025-06-13' },
]

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['basis', 'os_M', 'float_M', 'dno_M', 'control_M', 'ads_ratio',
    'control_holders', 'passive_holders', 'conf'],
  properties: {
    basis: { type: 'string', enum: ['normal', 'spac', 'ipo'] },
    os_M: { type: 'number', description: 'point-in-time O/S of the LISTED class, in millions' },
    float_M: { type: 'number', description: 'derived free float, in millions' },
    dno_M: { type: 'number', description: 'officers+directors group (ex-options, listed class), millions' },
    control_M: { type: 'number', description: 'control affiliates (13D control / >20% non-passive / founder SPV / parent), millions' },
    ads_ratio: { type: 'number', description: 'ordinary per listed ADS (1 if trades ordinary/US); float = os/ads - excl' },
    control_holders: { type: 'array', items: { type: 'string' }, description: 'excluded control entity names' },
    passive_holders: { type: 'array', items: { type: 'string' }, description: 'KEPT passive 13G/index/13F names' },
    conf: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

const PY = '"C:/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe"'
const prompt = (it) => `Derive the POINT-IN-TIME free-float RECIPE for ${it.t} as_of ${it.a} (only filings <= as_of; no lookahead).

STEP 1 — get the pre-built dossier by running this EXACT command with the Bash tool and reading its full output:
  cd C:/Users/explo/claude2/float/engine && PYTHONUTF8=1 ${PY} emit_worklist.py dossier ${it.t}
It prints the XBRL/regex O/S, a deterministic estimate, the 13D/13G blocks, and the proxy ownership table.

STEP 2 — derive per FLOAT_PROTOCOL: free float = O/S - (officers + directors + control-affiliates + non-passive >20% holders). KEEP passive 13G / index / registered-13F filers even if >20%. The 13D/13G tags are HINTS, not verdicts — a passive adviser can file a 13D, so judge each. Rescale any holder share-count for splits since its filing date.
- FOREIGN filers: read the LISTED-class O/S from the 20-F Item 7 / 6-K. The XBRL dei figure is often a STALE annual ordinary-share count — do not trust it blindly. Set ads_ratio = ordinary shares per listed ADS (1 if it trades ordinary directly on the US exchange).
- SPAC: float = public shares subject to redemption (basis 'spac'); fresh IPO: float = the public offering size (basis 'ipo'); otherwise basis 'normal'.
You MAY run additional read-only Bash commands (e.g. EDGAR fetches via the same python) if the dossier is insufficient.

STEP 3 — return the recipe via the structured-output tool: os_M and float_M in millions (listed class); dno_M = the proxy "as a group" officer+director block (ex-options, listed class) in millions; control_M = control affiliates in millions; ads_ratio; control_holders = excluded control entity names; passive_holders = the KEPT passive names; conf = high|med|low. dno_M + control_M is the exclusion the cache replays deterministically, so split it correctly.`

phase('Emit')
const out = []
for (let i = 0; i < ITEMS.length; i += 3) {                 // 3 agents at a time (hard cap per CLAUDE.md)
  const chunk = ITEMS.slice(i, i + 3)
  const recipes = await parallel(chunk.map((it) => () =>
    agent(prompt(it), { label: `emit:${it.t}`, phase: 'Emit', schema: SCHEMA })
      .then((r) => (r ? { t: it.t, a: it.a, recipe: r } : null))
  ))
  out.push(...recipes.filter(Boolean))
  log(`emitted ${out.length}/${ITEMS.length}`)
}
return out
