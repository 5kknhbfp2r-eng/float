export const meta = {
  name: 'recipe-emit-full236',
  description: 'Emit point-in-time free-float recipes (a batch of the 236 multi-day IS tickers) for the §16 recipe cache',
  phases: [{ title: 'Emit', detail: 'a [{t,a}] batch via args, 12 agents at a time, one structured recipe each' }],
}

// ITEMS come from the Workflow `args` (a [{t,a}] batch of the 236 multi-day tickers). Each agent
// self-fetches its own dossier (no big args). Resume after a stop = recompute remaining (worklist
// minus what's already in _recipes_emitted.json) and pass the next batch via args.
const ITEMS = Array.isArray(args) ? args : []
if (!ITEMS.length) throw new Error('recipe-emit: pass a non-empty [{t,a}] batch via Workflow args')

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['basis', 'os_M', 'float_M', 'dno_M', 'control_M', 'ads_ratio',
    'control_holders', 'passive_holders', 'conf'],
  properties: {
    basis: { type: 'string', enum: ['normal', 'spac', 'ipo'] },
    os_M: { type: 'number', description: 'point-in-time O/S in the issuer NATIVE share units — the SAME basis XBRL dei / the cover-page total reports (ORDINARY shares for a foreign/ADS issuer), in millions. NOT the ADS count.' },
    float_M: { type: 'number', description: 'derived free float in LISTED-class units, millions (must equal os_M/ads_ratio - dno_M - control_M)' },
    dno_M: { type: 'number', description: 'officers+directors group (ex-options) in LISTED-class units, millions' },
    control_M: { type: 'number', description: 'control affiliates (13D control / >20% non-passive / founder SPV / parent) in LISTED-class units, millions' },
    ads_ratio: { type: 'number', description: 'NATIVE (ordinary) shares per listed unit/ADS; 1 if it trades natively on the US exchange. float = os_M/ads_ratio - dno_M - control_M' },
    control_holders: { type: 'array', items: { type: 'string' }, description: 'excluded control entity names' },
    passive_holders: { type: 'array', items: { type: 'string' }, description: 'KEPT passive 13G/index/13F names' },
    conf: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

const PY = '"C:/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe"'
const prompt = (it) => `Derive the POINT-IN-TIME free-float RECIPE for ${it.t} at its EARLIEST labeled trading day — the as_of printed in the dossier header you fetch in STEP 1 (only filings <= that day; no lookahead). This recipe is the ANCHOR every later day replays from, so it MUST be derived at that earliest day.

STEP 1 — get the pre-built dossier by running this EXACT command with the Bash tool and reading its full output:
  cd C:/Users/explo/claude2/float/engine && PYTHONUTF8=1 ${PY} emit_worklist.py dossier ${it.t}
It prints the as_of, the XBRL/regex O/S, a deterministic estimate, the 13D/13G blocks, and the proxy ownership table.

STEP 2 — derive per FLOAT_PROTOCOL: free float = O/S - (officers + directors + control-affiliates + non-passive >20% holders). KEEP passive 13G / index / registered-13F filers even if >20%. The 13D/13G tags are HINTS, not verdicts — a passive adviser can file a 13D, so judge each. Rescale any holder share-count for splits since its filing date.
- UNITS (critical — the cache replays your formula verbatim): os_M is the issuer NATIVE O/S, the SAME basis the XBRL dei figure / cover-page total uses (ORDINARY shares for a foreign/ADS issuer), NOT the ADS count. Put the ordinary->listed conversion in ads_ratio (ordinary per ADS; 1 for a US-native listing). dno_M, control_M and float_M are in LISTED-class units, and the identity float_M = os_M/ads_ratio - dno_M - control_M MUST hold (each later day the cache re-fetches the native O/S and replays exactly this).
- FOREIGN filers: take os_M as the ordinary-share count from the 20-F Item 7 / cover / 6-K; the XBRL dei is often a STALE annual ordinary count — sanity-check it. Set ads_ratio = ordinary shares per listed ADS.
- SPAC: float = public shares subject to redemption (basis 'spac'); fresh IPO: float = the public offering size (basis 'ipo'); otherwise basis 'normal'.
You MAY run additional read-only Bash commands (e.g. EDGAR fetches via the same python) if the dossier is insufficient.

STEP 3 — return the recipe via the structured-output tool (see each field's description). dno_M + control_M is the exclusion the cache replays deterministically, so split it correctly, and verify float_M = os_M/ads_ratio - dno_M - control_M.

STEP 4 — durably record the SAME recipe so a usage-credit stop never discards your paid work (the run's resume source). Run, substituting YOUR values (JSON on ONE line):
  cd C:/Users/explo/claude2/float/engine && PYTHONUTF8=1 ${PY} record_recipe.py ${it.t} ${it.a} <<'JSON'
{"basis":"normal","os_M":0,"float_M":0,"dno_M":0,"control_M":0,"ads_ratio":1,"control_holders":[],"passive_holders":[],"conf":"med"}
JSON
It writes engine/data/_cache/emitted/${it.t}.json (idempotent).`

phase('Emit')
const CONC = 12                                              // agents at a time (CLAUDE.md cap)
const out = []
for (let i = 0; i < ITEMS.length; i += CONC) {
  const chunk = ITEMS.slice(i, i + CONC)
  const recipes = await parallel(chunk.map((it) => () =>
    // (F25) pin Opus + high effort: the recipe is the anchor every later day replays from, and the
    // hard archetypes (foreign/ADS, multi-class, split) are exactly where the weaker tier mis-derives.
    agent(prompt(it), { label: `emit:${it.t}`, phase: 'Emit', schema: SCHEMA, model: 'opus', effort: 'high' })
      .then((r) => (r ? { t: it.t, a: it.a, recipe: r } : null))
  ))
  out.push(...recipes.filter(Boolean))
  log(`emitted ${out.length}/${ITEMS.length}`)
}
return out
