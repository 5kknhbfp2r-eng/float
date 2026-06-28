export const meta = {
  name: 'float-is-finish-parallel',
  description: 'PARALLEL (12 agents at a time) finish of ALL remaining in-sample floats (72 July + 200 Aug = 272): 90 hard->Opus, 182 easy->Sonnet, from _rem_hard.txt / _rem_easy.txt. record.py (skip-existing, resume-safe) + receipts; carry-forward for recurring tickers.',
  phases: [{ title: 'IS finish (parallel x12)', detail: '272 names, 12 agents/wave' }],
}

const PY = '/c/Users/explo/claude2/claudebacktest_init2-2.4/.venv/Scripts/python.exe'
const ROOT = '/c/Users/explo/claude2/float'
const HARD_N = (args && args.hardN) || 90
const EASY_N = (args && args.easyN) || 182
const HCHUNK = (args && args.hchunk) || 6
const ECHUNK = (args && args.echunk) || 9
const MAXCONC = (args && args.maxconc) || 12

function prompt(file, start, end) {
  return `You derive POINT-IN-TIME free float from SEC EDGAR filings for a backtest. Float is PER (ticker, day) — point-in-time (filings <= as_of). Work through your slice; be token-economical (read FLOAT_PROTOCOL.md + FLOAT_PLAYBOOK.md ONCE; only fetch extra docs when the dossier is insufficient; one-sentence notes).

Get YOUR exact work list (each line 'TICKER AS_OF'; ignore any trailing '# ...'):
  PYTHONUTF8=1 ${PY} -c "print(chr(10).join(' '.join(l.split()[:2]) for l in open('${ROOT}/${file}').read().splitlines()[${start}:${end}] if l.strip()))"

Runtime: Python full path ${PY} (bare python broken; prefix PYTHONUTF8=1). Engine dir (EDGAR-only): ${ROOT}/engine/ . NEVER modify /c/Users/explo/claude2/claudebacktest_init2-2.4/ (read-only). Read engine/FLOAT_PROTOCOL.md + FLOAT_PLAYBOOK.md ONCE.

For EACH (TICKER, AS_OF):
A) CARRY-FORWARD: PYTHONUTF8=1 ${PY} -c "import csv; rs=[(r['as_of'],r['float_M'],r['os_M']) for r in csv.DictReader(open('${ROOT}/float_is.csv')) if r['ticker']=='TICKER' and r['as_of']<'AS_OF']; print(rs[-3:])". If a prior date exists, run the dossier for AS_OF and use fg.list_filings('TICKER','AS_OF') to check for any NEW O/S- OR OWNERSHIP-relevant filing between the prior date and AS_OF — i.e. periodic / 424B / S-1 / 8-K (issuance or Item 5.01 change-of-control) / reverse-split, OR any SC 13D/13G (incl. /A), DEF 14A/DEFM14A proxy, SC TO / SC 14D9, or Form 3/4 (the control/D&O exclusion can change with O/S flat — a new activist 13D, a control holder exiting, a fresh proxy D&O total). Carry forward ONLY if NONE of these appears AND current O/S is unchanged -> record the SAME float_M & os_M, NOTE="carried from <prior date>; no intervening O/S or ownership change". Else derive fresh.
B) Dossier: cd ${ROOT}/engine && PYTHONUTF8=1 ${PY} float_backtest.py dossier TICKER AS_OF (cover O/S by class; RECONCILIATION = CURRENT O/S from latest periodic <= as_of + split/ADS/dilution; ownership table; footnotes; filings <= as_of). Foreign 20-F O/S in Item 7 -> fg.fetch_one('TICKER','<acc>', what='full') + search "shares outstanding". Use fg.list_filings('TICKER','AS_OF').
C) Derive: free_float = current_O/S - (officers+directors+control-affiliates+non-passive >20%). KEEP passive 13G/index even if >20%. Multi-class -> listed class only. ADS -> divide ordinary by ratio (verify not a false positive — many Israeli/Canadian names trade ordinary directly). Reverse/forward split/consolidation -> current O/S already reflects it (scale a pre-split proxy table; watch serial splits). Fresh China/foreign IPO -> exclude pre-IPO affiliate SPVs (float=public offering). D&O group ex unexercised options/RSUs. MILLIONS (16,019,787 -> 16.02). DT anchor ${ROOT}/dt_os_float_2026-06-04.csv (2026 snapshot, gross-error check); if >2x off, re-check split/ADS/class/offering-size.
D) RECORD: cd ${ROOT} && PYTHONUTF8=1 ${PY} record.py TICKER AS_OF FLOAT_M OS_M CONF "BASIS" "NOTE" (CONF=high|med|low; EXACTLY 7 args after record.py — NO under_20M arg). If it errors "already recorded", skip that name.
E) RECEIPT: PYTHONUTF8=1 ${PY} save_receipt.py TICKER AS_OF "OS_SOURCE filing+date+acc:number" "Excluded=sharesM|..." "Kept=sharesM|..."

NO-DROP: never skip; can't pin -> CONF=low + best estimate + blocker in NOTE. Obviously >20M float -> FLOAT_M may be "" with only OS_M. Return a compact table ticker|as_of|float_M|os_M|under_20M|conf, flag low-confidence / DT-off names.`
}

const tasks = []
for (let s = 0; s < HARD_N; s += HCHUNK) tasks.push({ file: '_rem_hard.txt', s, e: Math.min(HARD_N, s + HCHUNK), model: 'opus', kind: 'hard' })
for (let s = 0; s < EASY_N; s += ECHUNK) tasks.push({ file: '_rem_easy.txt', s, e: Math.min(EASY_N, s + ECHUNK), model: 'sonnet', kind: 'easy' })

const res = []
for (let i = 0; i < tasks.length; i += MAXCONC) {
  const wave = tasks.slice(i, i + MAXCONC)
  log(`IS finish: wave ${Math.floor(i / MAXCONC) + 1}/${Math.ceil(tasks.length / MAXCONC)} — ${wave.length} agents (${wave.filter(t => t.kind === 'hard').length} Opus / ${wave.filter(t => t.kind === 'easy').length} Sonnet)`)
  const out = await parallel(wave.map(t => () =>
    agent(prompt(t.file, t.s, t.e), { label: `is-fin ${t.kind} ${t.s}-${t.e}`, phase: 'IS finish (parallel x12)', model: t.model })))
  res.push(...out)
}
return { tasks: tasks.length, completed: res.filter(Boolean).length }
