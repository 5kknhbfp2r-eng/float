export const meta = {
  name: 'float-llm-opus-escalate',
  description: 'Escalation pass: the 6 worst Sonnet misses re-derived by OPUS on the SAME compressed dossier, 3 agents at a time, recorded to _llm_tail_opus.csv. Tests whether the hard tail needs Opus (model tier) vs is genuine label ambiguity.',
  phases: [{ title: 'Opus escalate', detail: '6 worst misses, Opus, 3 at a time' }],
}
const PY = '/c/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe'
const ROOT = '/c/Users/explo/claude2/float'
const ENG = ROOT + '/engine'
const MISSES = [
  { t: 'WHLR', a: '2025-06-04', cik: 1527541, arch: 'split/reverse', label: 0.02, sonnet: 0.44 },
  { t: 'ARQQ', a: '2025-05-19', cik: 1859690, arch: 'foreign/ADS', label: 6.53, sonnet: 1.67 },
  { t: 'TGEN', a: '2025-07-18', cik: 1537435, arch: 'IPO/offering', label: 26.4, sonnet: 19.49 },
  { t: 'SATL', a: '2025-05-02', cik: 1874315, arch: 'foreign/ADS', label: 48.63, sonnet: 34.49 },
  { t: 'BRLS', a: '2025-06-11', cik: 1852973, arch: 'US-single-class', label: 5.28, sonnet: 8.82 },
  { t: 'MTR', a: '2025-06-17', cik: 313364, arch: 'SPAC', label: 1.86, sonnet: 1.60 },
]
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    float_M: { type: 'number' }, os_M: { type: 'number' },
    conf: { type: 'string' }, note: { type: 'string' },
  },
  required: ['float_M', 'os_M', 'conf', 'note'],
}
function prompt(o) {
  return `Compute POINT-IN-TIME free float for a micro-cap backtest, DilutionTracker-style. EVERY float must
be EXACT. float = current O/S - (officers + directors + control-affiliates + non-passive >20% holders); KEEP
passive 13G / index filers even if >20%. IGNORE anything dated after ${o.a}. This is a HARD name a weaker
model got wrong - reason carefully.

1) Get the pre-digested dossier:
   cd ${ENG} && PYTHONUTF8=1 ${PY} -c "import det_float as D; print(D.compressed_dossier('${o.t}','${o.a}',${o.cik})[0])"
   It has XBRL O/S (+ regex cross-check), the 13D/13G blocks tagged CONTROL(13D)/passive-KEEP(13G), and the
   proxy ownership table.

2) Judge carefully:
   - O/S: pick the correct current listed-class count (XBRL preferred; reconcile ADS ratio / reverse split /
     multi-class; a 13D filer's share count is as-of ITS filing date - rescale for any split since).
   - Holders: a 13D filing means a >5% stake but is NOT automatically a control EXCLUSION - judge whether the
     filer is actually a control affiliate (activist/founder/parent/board-linked) vs a passive-ish investor
     the strategy keeps. DEDUP acting-in-concert. KEEP genuine passive 13G/index. Do not blindly exclude
     every 13D, and do not blindly keep every 13G.
   - Near-zero float / SPAC / fresh-IPO: handle the redemption/offering basis precisely.
   FETCH what you need - the FULL dossier and specific filings are allowed and encouraged for these hard names:
     cd ${ENG} && PYTHONUTF8=1 ${PY} float_backtest.py dossier ${o.t} ${o.a}
     (import float_gather as fg; fg.list_filings('${o.t}','${o.a}'); fg.fetch_one('${o.t}','<acc>',what='ownership'|'cover'|'full'))
   Read engine/FLOAT_PROTOCOL.md + FLOAT_PLAYBOOK.md if useful.

3) RECORD durably to the OPUS file (note the trailing _llm_tail_opus.csv arg):
   cd ${ROOT} && PYTHONUTF8=1 ${PY} record_llm.py ${o.t} ${o.a} <float_M> <os_M> <high|med|low> opus "<one-line note>" _llm_tail_opus.csv

Return float_M, os_M, conf, note.`
}
const out = []
for (let i = 0; i < MISSES.length; i += 3) {
  const chunk = MISSES.slice(i, i + 3)
  log(`opus chunk ${i / 3 + 1}: ${chunk.map(o => o.t).join(', ')}`)
  const r = await parallel(chunk.map(o => () =>
    agent(prompt(o), { label: `${o.t} ${o.arch}`, phase: 'Opus escalate', model: 'opus', effort: 'high', schema: SCHEMA })
      .then(x => ({ t: o.t, arch: o.arch, label: o.label, sonnet: o.sonnet, opus: x })).catch(() => null)))
  out.push(...r)
}
return out.filter(Boolean)
