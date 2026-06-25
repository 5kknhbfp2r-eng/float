export const meta = {
  name: 'float-llm-tail-3x',
  description: 'LLM float derivation, THREE agents at a time (chunks of 3): each remaining abstained name -> Sonnet reads the compressed deterministic dossier, derives point-in-time free float, records durably to _llm_tail_results.csv (resume-safe, deduped).',
  phases: [{ title: 'LLM tail (3x)', detail: '3 agents at a time, Sonnet, records each' }],
}
const PY = '/c/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe'
const ROOT = '/c/Users/explo/claude2/float'
const ENG = ROOT + '/engine'
const REMAINING = [
  { t: 'WHLR', a: '2025-06-04', cik: 1527541, arch: 'split/reverse', label: 0.02 },
  { t: 'WKSP', a: '2025-05-15', cik: 1096275, arch: 'split/reverse', label: 4.95 },
  { t: 'ARQQ', a: '2025-05-19', cik: 1859690, arch: 'foreign/ADS', label: 6.53 },
  { t: 'NUKK', a: '2025-05-20', cik: 1787518, arch: 'multi-class', label: 3.35 },
  { t: 'MTR', a: '2025-06-17', cik: 313364, arch: 'SPAC', label: 1.86 },
  { t: 'DIST', a: '2025-06-11', cik: 1818605, arch: 'SPAC', label: 0.65 },
  { t: 'BBGI', a: '2025-06-20', cik: 1099160, arch: 'multi-class', label: 0.68 },
  { t: 'EMPG', a: '2025-08-29', cik: 2005569, arch: 'IPO/offering', label: 1.58 },
  { t: 'TGEN', a: '2025-07-18', cik: 1537435, arch: 'IPO/offering', label: 26.4 },
]
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    float_M: { type: 'number', description: 'free float in millions of shares' },
    os_M: { type: 'number', description: 'shares outstanding in millions' },
    conf: { type: 'string', description: 'high | med | low' },
    note: { type: 'string', description: 'one line: basis + what you excluded/kept' },
  },
  required: ['float_M', 'os_M', 'conf', 'note'],
}
function prompt(o) {
  return `Compute POINT-IN-TIME free float for a micro-cap backtest, DilutionTracker-style. EVERY float must
be exact (no <20M-gate shortcuts). float = current O/S - (officers + directors + control-affiliates +
non-passive >20% holders); KEEP passive 13G / index filers even if >20%. IGNORE anything dated after ${o.a}.

1) Get the pre-digested dossier (XBRL O/S + regex cross-check, the deterministic estimate + why it abstained,
   the 13D/13G blocks tagged CONTROL(13D)/passive-KEEP(13G), and the proxy ownership table):
   cd ${ENG} && PYTHONUTF8=1 ${PY} -c "import det_float as D; print(D.compressed_dossier('${o.t}','${o.a}',${o.cik})[0])"

2) Make the JUDGMENT the deterministic engine could not:
   - O/S: prefer the XBRL dei count; if the two O/S disagree, read the cover and pick the current
     listed-class count. ADS -> divide ordinary by the ratio. Reverse split/consolidation -> current O/S
     already reflects it (don't double-apply).
   - Holders: EXCLUDE control = D&O group (ex unexercised options) + 13D filers + board-linked / founder /
     parent / >20% control persons. DEDUP acting-in-concert (a founder + his fund/LP = ONE block). KEEP
     passive 13G / index funds. Do NOT over-exclude a passive 13G just because it is large.
   - SPAC -> float = public shares subject to redemption, net of redemptions to date. Fresh IPO -> float =
     the public offering size.
   If the dossier is insufficient, run the FULL dossier and/or fetch a filing:
     cd ${ENG} && PYTHONUTF8=1 ${PY} float_backtest.py dossier ${o.t} ${o.a}
     (import float_gather as fg; fg.list_filings('${o.t}','${o.a}'); fg.fetch_one('${o.t}', '<accession>', what='ownership'|'cover'|'full'))
   Read engine/FLOAT_PROTOCOL.md + FLOAT_PLAYBOOK.md ONCE if you need archetype guidance. Be token-economical.

3) RECORD your result durably (resume-safe), exactly once:
   cd ${ROOT} && PYTHONUTF8=1 ${PY} record_llm.py ${o.t} ${o.a} <float_M> <os_M> <high|med|low> sonnet "<one-line note>"

Then return float_M, os_M (millions), conf, and the note as your structured output.`
}
const out = []
for (let i = 0; i < REMAINING.length; i += 3) {
  const chunk = REMAINING.slice(i, i + 3)
  log(`chunk ${i / 3 + 1}: ${chunk.map(o => o.t).join(', ')}`)
  const r = await parallel(chunk.map(o => () =>
    agent(prompt(o), { label: `${o.t} ${o.arch}`, phase: 'LLM tail (3x)', model: 'sonnet', effort: 'medium', schema: SCHEMA })
      .then(x => ({ t: o.t, arch: o.arch, label: o.label, llm: x })).catch(() => null)))
  out.push(...r)
}
return out.filter(Boolean)
