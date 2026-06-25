#!/usr/bin/env python3
"""§16 lever 2-3 — per-ticker float-recipe cache + event-driven recompute (the path to ~$200/yr).

A ticker's float "recipe" is STABLE between corporate events: the listed class, ADS ratio, basis
type, and the exclusion (D&O + control holders). Derive it ONCE (the LLM does the judgment), then
on every later day compute the float DETERMINISTICALLY:  float = current XBRL O/S - exclusion.
Re-fire the LLM ONLY when a new ownership/structure filing changes the recipe (is_stale).

Recipe (per ticker, in recipes.json):
  {cik, basis, ads_ratio, exclusion_M, control_holders[], os_at, float_at, derived_day,
   depends_on[], conf}
exclusion_M is carried (the LLM's judgment); O/S is always re-fetched fresh (the thing that drifts).
"""
import os, json
import det_float as D
import float_gather as fg
import _widen_probe as wp
import edgar

RECIPES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recipes.json")
# filings that change the EXCLUSION STRUCTURE (control set / D&O). NOT periodics or offerings —
# those only move O/S, which replay re-fetches fresh. A new 13D/13G/proxy => re-judge with the LLM.
STRUCT_FORMS = ["SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13G",
                "SCHEDULE 13D/A", "SCHEDULE 13G/A", "DEF 14A", "DEFM14A", "DEFM14C"]


def _load():
    try:
        return json.load(open(RECIPES_PATH, encoding="utf-8"))
    except Exception:
        return {}


RECIPES = _load()


def save_recipe(ticker, cik, basis, derived_day, os_at, float_at, control_M,
                ads_ratio=1.0, control_holders=None, depends_on=None, conf="med"):
    """The LLM emits the dno/control SPLIT: replay re-fetches O/S + the D&O group deterministically
    and carries only control_M (the judgment). control_holders = the excluded control entities (for
    finer staleness + the registry)."""
    RECIPES[ticker] = {"cik": cik, "basis": basis, "ads_ratio": ads_ratio,
                       "control_M": round(control_M, 4), "control_holders": control_holders or [],
                       "os_at": round(os_at, 4), "float_at": round(float_at, 4),
                       "derived_day": derived_day, "depends_on": depends_on or [], "conf": conf}
    json.dump(RECIPES, open(RECIPES_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)


def is_stale(ticker, day, cik=None):
    """True if an EXCLUSION-changing filing was filed after the recipe's derived_day (<= day) —
    a new 13D/13G (control set), proxy (D&O), or offering/8-K (structure). A plain periodic that
    only updates O/S is NOT stale (we re-fetch O/S). True -> re-derive with the LLM."""
    r = RECIPES.get(ticker)
    if not r:
        return True
    cik = cik or r["cik"]
    for f in edgar.query(cik, STRUCT_FORMS, day, size=40):
        if r["derived_day"] < f["filedAt"][:10] <= day:
            return True
    return False


def replay(ticker, day, cik=None):
    """Deterministic float on a NEW day from the cached recipe (no LLM). Returns
    (status, float_M): status in {ok, stale, no-recipe, no-os}. 'stale' -> hand to the LLM."""
    r = RECIPES.get(ticker)
    if not r:
        return ("no-recipe", None)
    cik = cik or r["cik"]
    if is_stale(ticker, day, cik):
        return ("stale", None)
    x = D.xbrl_os(cik, day) or {}
    g = D.regex_os(cik, day) or {}
    xv, gv = x.get("val_M"), g.get("val_M")
    os_ = xv or gv
    if not os_:
        return ("no-os", None)
    # L8 O/S guard: never replay on an unreliable share base -> defer to the LLM instead of a wrong float.
    if xv and gv and abs(xv - gv) / max(xv, gv) > 0.30:
        return ("os-uncertain", None)                     # XBRL vs regex disagree (split/wrong-fact)
    if (x.get("n_at_pick") or 1) > 1:
        return ("os-multiclass", None)                    # flat XBRL can't pick the listed class
    if "control_M" not in r:
        return ("need-split", None)                       # old recipe lacks dno/control split -> re-derive
    if r["basis"] in ("spac", "ipo"):
        return ("ok", round(r["float_at"], 3))            # whole-float bases: carried (re-validate on event)
    # re-fetch the D&O group DETERMINISTICALLY (absorbs insider/Form-4 drift); carry only control_M.
    f = fg._pick_own(cik, day)
    if not f:
        return ("no-proxy", None)
    ge = wp.group_exoptions(fg._text(f).translate(wp.ZW), os_)
    dno = ge[0] if ge else None
    if dno is None:
        return ("no-dno", None)
    fl = os_ / (r["ads_ratio"] or 1.0) - dno - r["control_M"]
    if fl <= 0 or fl > os_ * 1.01:
        return ("implausible", None)
    return ("ok", round(fl, 3))


if __name__ == "__main__":
    import sys
    print(json.dumps(RECIPES.get(sys.argv[1], {}), indent=1) if len(sys.argv) > 1 else
          f"{len(RECIPES)} recipes cached")
