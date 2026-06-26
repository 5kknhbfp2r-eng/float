export const meta = {
  name: 'label-qc-disputes',
  description: 'Resolve float label-vs-agent disputes against primary SEC filings (investigate + adversarially verify)',
  phases: [
    { title: 'Investigate', detail: 'read primary filings, render an independent float verdict per ticker' },
    { title: 'Verify', detail: 'adversarial re-check of each verdict (high bar to overturn a label)' },
  ],
}

const ENGINE = 'C:/Users/explo/claude2/float/engine'
const PY = '"C:/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe"'

// Disputed (ticker, as_of) — label vs the wave agent's recipe. Investigators decide the TRUTH.
const ITEMS = [
  { t: 'ANNA', a: '2025-06-25', cik: 1845123, lf: 29.44, lo: 40.58, af: 3.53, ao: 40.66,
    d: "Agent excluded Wilder's FULL 30.48M beneficial ownership (Nautilus Resources LLC) + 6.66M Wilder Foundation as control (float 3.53). Label excluded only ~4.48M Wilder direct Class A, arguing the other ~26M is EXCHANGEABLE Class C/units NOT part of the 40.58M listed Class A common O/S (float 29.44). C. John Wilder Jr. filed a 13D. KEY: what is Wilder's actual LISTED Class A share count to exclude (not total beneficial ownership incl exchangeable units)?" },
  { t: 'ATNF', a: '2025-07-29', cik: 1690080, lf: 4.10, lo: 6.04, af: -0.59, ao: 6.039,
    d: "Agent excluded Elray Resources Inc. (13D, 47.8%) as control -> NEGATIVE float (-0.59), impossible. Label kept Elray, excluded only ~0.58M D&O direct (float 4.10). KEY: is Elray's 47.8% an actual block of OUTSTANDING common (exclude as control) or warrants/convertibles NOT in the 6.04M common O/S (keep)? Resolve the true control exclusion." },
  { t: 'BNGO', a: '2025-05-14', cik: 1411690, lf: 1.84, lo: 1.8654, af: 3.362, ao: 3.364,
    d: "Agent O/S 3.364M vs label 1.8654M (label cites the post-reverse-split 10-Q O/S 1,865,400). Bionano did a reverse split. KEY: what is the correct point-in-time LISTED common O/S as of 2025-05-14 (post-split)? The exclusion is tiny either way." },
  { t: 'ARBKL', a: '2025-07-11', cik: 1841675, lf: 71.00, lo: 71.95, af: 57.716, ao: 577.156,
    d: "Argo Blockchain plc; 1 ADS = 10 ordinary. Agent used 577.156M ordinary (=57.7M ADS); label used 719.47M ordinary (=71.95M ADS). Both ads_ratio=10. KEY: what is the correct ORDINARY share count as of 2025-07-11 (read the 20-F/6-K/cover)? Also: is Armistice's 57.7M ordinary (~8%) passive (keep) or control (exclude)?" },
  { t: 'BMGL', a: '2025-05-14', cik: 2004489, lf: 6.05, lo: 18.79, af: 8.581759, ao: 18.78575,
    d: "Basel Medical (BVI) fresh IPO Feb-2025, O/S 18.79M. Both excluded Rainforest Capital VCC ~10.17M (control SPV via AIP Investment Partners). Label float 6.05 vs agent 8.58 — label excluded ~2.5M MORE. KEY: what is the FULL control/affiliate + D&O exclusion (the ~2.5M the agent missed)?" },
  { t: 'WHLR', a: '2025-06-04', cik: 1527541, lf: 0.02, lo: 0.56, af: null, ao: null,
    d: "Wheeler REIT, death-spiral: SERIAL reverse splits (incl 1-for-7 on 5/21/2025) + continuous Series D preferred redemptions PAID IN COMMON (massive ongoing dilution). Label: common O/S ~558,209 (424B3), float ~0.02M (almost all held by/issued to preferred holders as control/affiliate?). KEY: verify the point-in-time common O/S AND why the float is so tiny (who is excluded). Flagged earlier as a likely error — confirm or correct." },
  { t: 'TGEN', a: '2025-07-18', cik: 1537435, lf: 26.40, lo: 28.49, af: null, ao: null,
    d: "Tecogen / Trean? (verify the issuer). Label float 26.40M of 28.49M O/S (D&O ex-options 2.08M; a new offering's public shares added to float). Flagged earlier as a likely label error (an Opus pass disagreed). KEY: verify the point-in-time O/S, the D&O/affiliate exclusion, and whether any control block or unvested/locked shares were wrongly counted as float." },
]

const INV_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['correct_os_M', 'correct_float_M', 'verdict', 'holder_resolution', 'evidence', 'confidence'],
  properties: {
    correct_os_M: { type: 'number', description: 'correct point-in-time LISTED-class O/S, millions' },
    correct_float_M: { type: 'number', description: 'your independently-derived free float, millions' },
    verdict: { type: 'string', enum: ['label-correct', 'agent-correct', 'both-wrong', 'uncertain'] },
    holder_resolution: { type: 'string', description: 'how the disputed holder/issue was resolved + why (listed shares vs exchangeable/convertible/warrants; split; ADS)' },
    evidence: { type: 'string', description: 'specific filing(s) + share counts + reasoning that nails it' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}
const VER_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['agrees', 'final_float_M', 'final_os_M', 'final_verdict', 'note', 'confidence'],
  properties: {
    agrees: { type: 'boolean', description: 'does the primary evidence support the investigator verdict?' },
    final_float_M: { type: 'number' }, final_os_M: { type: 'number' },
    final_verdict: { type: 'string', enum: ['label-correct', 'agent-correct', 'both-wrong', 'uncertain'] },
    note: { type: 'string', description: 'refutation or confirmation, citing the primary filing' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

const tools = (it) => `Read PRIMARY filings point-in-time (only filings filed <= ${it.a}; no lookahead) with the Bash tool:
  cd ${ENGINE} && PYTHONUTF8=1 ${PY} -c "import det_float as D; t,_=D.compressed_dossier('${it.t}','${it.a}'); print(t)"   # summary + 13D/13G blocks + ownership table
  cd ${ENGINE} && PYTHONUTF8=1 ${PY} dump_filing.py ${it.cik} "DEF 14A" ${it.a}     # proxy ownership table + footnotes (exchangeable/convertible units!)
  ...also "SC 13D" / "SC 13D/A" (reporting-person aggregate + % + nature), "10-Q"/"10-K"/"20-F" (listed-class cover O/S), "424B4"/"424B3" (offering), "8-K".
FLOAT RULE: free float = LISTED-class O/S - (officers + directors + control-affiliates' LISTED shares + non-passive >20%). KEEP passive 13G/index/13F even >20%.
PITFALLS that caused the disputes: (1) exclude only a holder's LISTED-class OUTSTANDING shares — NOT exchangeable/convertible units or warrants that are in their "beneficial ownership" but NOT in the listed O/S; (2) use the POST-reverse-split O/S; (3) ADS: count in ADS units (ordinary / ratio); (4) a 13D proves control INTENT but the excluded amount is still only their listed outstanding shares.`

const invPrompt = (it) => `Independently determine the correct POINT-IN-TIME free float for ${it.t} as_of ${it.a} from primary SEC filings, then judge the dispute.
DISPUTE: ${it.d}
LABEL says float=${it.lf}M (O/S ${it.lo}M). AGENT says float=${it.af}M (O/S ${it.ao}M).
${tools(it)}
Return: correct_os_M, correct_float_M (your independent numbers), verdict (label-correct | agent-correct | both-wrong | uncertain), holder_resolution (how you treated the disputed holder + why), evidence (filing + exact share counts), confidence. Be exact — this may correct a benchmark.`

const verPrompt = (it, inv) => `ADVERSARIALLY verify this float verdict for ${it.t} as_of ${it.a}. Re-read the PRIMARY filings yourself and try to REFUTE it; only confirm if the evidence is solid. A verdict that OVERTURNS the label changes a benchmark — hold it to a HIGH bar.
DISPUTE: ${it.d}
LABEL float=${it.lf}M os=${it.lo}M | AGENT float=${it.af}M os=${it.ao}M
INVESTIGATOR verdict: ${inv.verdict}, float=${inv.correct_float_M}M os=${inv.correct_os_M}M, conf=${inv.confidence}
  holder_resolution: ${inv.holder_resolution}
  evidence: ${inv.evidence}
${tools(it)}
Return: agrees, final_float_M, final_os_M, final_verdict, note (cite the filing that confirms/refutes), confidence.`

const CONC = 6                                              // agents at a time (CLAUDE.md cap)
// Phase 1 — investigate
phase('Investigate')
const inv = []
for (let i = 0; i < ITEMS.length; i += CONC) {
  const chunk = ITEMS.slice(i, i + CONC)
  const r = await parallel(chunk.map((it) => () =>
    agent(invPrompt(it), { label: `inv:${it.t}`, phase: 'Investigate', schema: INV_SCHEMA })
      .then((x) => ({ it, inv: x }))))
  inv.push(...r.filter(Boolean))
  log(`investigated ${inv.length}/${ITEMS.length}`)
}

// Phase 2 — adversarial verify
phase('Verify')
const out = []
for (let i = 0; i < inv.length; i += CONC) {
  const chunk = inv.slice(i, i + CONC)
  const r = await parallel(chunk.map((e) => () =>
    e.inv
      ? agent(verPrompt(e.it, e.inv), { label: `ver:${e.it.t}`, phase: 'Verify', schema: VER_SCHEMA })
          .then((v) => ({ t: e.it.t, a: e.it.a, label: { f: e.it.lf, o: e.it.lo }, agent: { f: e.it.af, o: e.it.ao }, inv: e.inv, ver: v }))
      : Promise.resolve(null)))
  out.push(...r.filter(Boolean))
  log(`verified ${out.length}/${inv.length}`)
}
return out
