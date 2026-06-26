#!/usr/bin/env python3
"""Build the recipe-emit worklist (turnkey input for the paid LLM recipe-emit run).

For every multi-day IS ticker, emit {ticker, asof=earliest labeled day, cik, archetype, label_os,
label_float}. An LLM agent reads det_float.compressed_dossier(ticker, asof) and returns a recipe
{basis, dno_M, control_M, ads_ratio, control_holders[], passive_holders[], float_M, os_M, conf};
the emitter appends it to _recipes_emitted.json (resume-safe), then validate_recipes.py replays the
later days deterministically and scores. The replay engine already has the full $0 guard stack
(band, 424B/proxy staleness, reverse-split defer), so a real recipe carries the ADS ratio + basis
that the label-stand-in sim couldn't — closing the foreign/ADS residual.

Usage:
  python emit_worklist.py                 # build _emit_worklist.json (all) + print strata + first wave
  python emit_worklist.py wave 30         # print a stratified N-ticker first-wave ticker list
  python emit_worklist.py dossier TICKER  # preview the exact agent input for that ticker's earliest day
"""
import os, sys, csv, json, collections
import det_float as D, float_gather as fg

# The structured recipe an emit agent returns (appended to _recipes_emitted.json as
# {"t","a","cik","recipe":{...}}). validate_recipes.py save_recipe()s + replays + scores it.
RECIPE_SCHEMA = {
    "basis": "normal|spac|ipo  (normal D&O+holders; spac/ipo carry the whole public float)",
    "os_M": "point-in-time O/S in millions (the LISTED class; read the 20-F/6-K for foreign filers)",
    "float_M": "your derived free float in millions",
    "dno_M": "officers+directors block in millions (the proxy 'as a group' row, ex-options, listed-class)",
    "control_M": "control affiliates in millions (13D filers / >20% non-passive / founder SPVs / parents)",
    "ads_ratio": "ordinary-per-listed-unit (1 for US; e.g. 8 if 1 ADS = 8 ordinary); float=os/ads-excl",
    "control_holders": ["excluded control entity names (for staleness + the registry)"],
    "passive_holders": ["KEPT passive 13G/index/13F names (warms the registry)"],
    "conf": "high|med|low",
}
# The emit prompt = the dossier (det_float.compressed_dossier) + FLOAT_PROTOCOL (already appended to it)
# + "return the RECIPE_SCHEMA as strict JSON". The §16 split matters: dno_M and control_M are carried in
# shares and replayed deterministically; ads_ratio closes the foreign/ADS residual the sim couldn't.
EMIT_PROMPT = ("Derive the point-in-time free-float RECIPE for {ticker} as_of {asof} from the dossier "
               "below. Apply FLOAT_PROTOCOL (keep passive 13G/index even >20%; exclude officers, "
               "directors, control affiliates, non-passive >20%). For foreign filers read the listed-"
               "class O/S from the 20-F Item 7 / 6-K (XBRL dei is often a stale annual ordinary count). "
               "Return ONLY strict JSON matching this schema: {schema}\n\n{dossier}")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
by = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(ROOT, "float_is.csv"), encoding="utf-8")):
    if r["float_M"].strip() and r["os_M"].strip():
        by[r["ticker"]].append((r["as_of"][:10], float(r["float_M"]), float(r["os_M"]),
                                r.get("basis", ""), r.get("note", "")))
multi = {t: sorted(v) for t, v in by.items() if len(v) >= 2}


def _row(t):
    d0, fl0, os0, basis0, note0 = multi[t][0]
    return {"ticker": t, "asof": d0, "cik": fg.resolve_cik(t, d0),
            "archetype": D.archetype(basis0, note0), "label_os": os0, "label_float": fl0,
            "later_days": [d for d, *_ in multi[t][1:]]}


def stratified(n):
    """Round-robin across archetypes so a first wave spans the hard types (foreign/ADS, multi-class,
    split, SPAC, IPO) not just the easy US-single-class majority."""
    buckets = collections.defaultdict(list)
    for t in sorted(multi):
        d0, fl0, os0, basis0, note0 = multi[t][0]
        buckets[D.archetype(basis0, note0)].append(t)
    order = sorted(buckets, key=lambda k: -len(buckets[k]))
    out, i = [], 0
    while len(out) < n and any(buckets[k] for k in order):
        k = order[i % len(order)]
        if buckets[k]:
            out.append(buckets[k].pop(0))
        i += 1
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "dossier":
        t = sys.argv[2]
        d0 = multi[t][0][0]
        txt, det = D.compressed_dossier(t, d0)
        print(txt)
    elif len(sys.argv) >= 2 and sys.argv[1] == "wave":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        print(" ".join(stratified(n)))
    else:
        work = [_row(t) for t in sorted(multi)]
        json.dump(work, open(os.path.join(ROOT, "_emit_worklist.json"), "w"), indent=1)
        strata = collections.Counter(w["archetype"] for w in work)
        print(f"multi-day tickers: {len(work)} -> _emit_worklist.json")
        print("archetype strata:", dict(strata.most_common()))
        print(f"no-CIK (need EFTS/manual): {sum(1 for w in work if not w['cik'])}")
        print(f"\nstratified 30-ticker first wave:\n  {' '.join(stratified(30))}")
