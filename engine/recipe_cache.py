#!/usr/bin/env python3
"""§16 lever 2-3 — per-ticker float-recipe cache + event-driven recompute (the path to ~$200/yr).

A ticker's float "recipe" is STABLE between corporate events: the listed class, ADS ratio, basis
type, and the exclusion (D&O + control holders). Derive it ONCE (the LLM does the judgment), then
on every later day compute the float DETERMINISTICALLY:  float = current XBRL O/S - exclusion.
Re-fire the LLM ONLY when a new ownership/structure filing changes the recipe (is_stale).

Recipe (per ticker, in recipes.json):
  {cik, basis, ads_ratio, dno_M, control_M, control_holders[], os_at, float_at, derived_day,
   depends_on[], conf}
The exclusion (dno_M + control_M) is carried in SHARES — the LLM's judgment, held fixed against the
drifting O/S exactly as the labels are built (D&O constant between proxy filings). O/S is the only
thing re-fetched each day (anchored on os_at to reject misparses); a changed ownership source or a
new 13D/13G/proxy re-fires the LLM (proxy-changed / is_stale).
"""
import os, re, json, datetime as dt
import det_float as D
import float_gather as fg
import edgar

# reverse-split detection (the HUSA 899% lag: a split changes the share basis but XBRL keeps reporting
# the pre-split count until the next periodic, so a deterministic O/S re-fetch is stale mid-recipe).
# (F04) include the foreign 'consolidation'/'subdivision' vocabulary for reverse splits — but keep it
# SHARE/STOCK-qualified so it does NOT match the ubiquitous 'consolidated financial statements'.
_RS = re.compile(r"reverse\s+(?:stock\s+)?split"
                 r"|\b(?:share|stock|ordinary[ -]?share|capital)\s+consolidation\b"
                 r"|\bshare\s+subdivision\b", re.I)
_RS_RATIO = re.compile(r"\b(?:1[-\s]?for[-\s]?\d{1,3}|\d{1,3}[-\s]?for[-\s]?1|1[-:]\s?\d{1,3})\b", re.I)

RECIPES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recipes.json")
# filings that change the EXCLUSION STRUCTURE (control set / D&O). A new 13D/13G/proxy => re-judge.
STRUCT_FORMS = ["SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13G",
                "SCHEDULE 13D/A", "SCHEDULE 13G/A", "DEF 14A", "DEFM14A", "DEFM14C",
                "DEFR14A", "DEFA14A", "PRER14A",    # revised/additional proxies also update D&O
                "DEF 14C", "DEFR14C", "DEFA14C", "PRE 14C"]  # (F22) info statements: D&O/control by written consent
# O/S-EVENT forms: an offering/takedown CLOSES here and the XBRL O/S fact LAGS it (only refreshes at
# the next 10-Q/10-K), so a deterministic O/S re-fetch would be STALE (the AGEN/HUSA failure mode in
# the IS sim — frozen XBRL while a 424B issued shares). Treat as an event that needs the LLM to read
# the post-event share base. Reverse splits land in 8-K (too noisy to blanket-trigger); the 424B
# offering-close is the clean, targeted signal and is what actually moves O/S in this universe.
OS_EVENT_FORMS = ["424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8"]


def _load():
    """Recipes are VERSIONED / append-only: {ticker: [recipe, ... sorted by derived_day]}. A re-derive
    after a corporate event ADDS a version instead of overwriting, so every past (ticker, day) window
    stays free-replayable on later re-runs (historical repeatability; costs zero LLM — just disk).
    Auto-migrates the old {ticker: recipe} shape on read."""
    try:
        raw = json.load(open(RECIPES_PATH, encoding="utf-8"))
    except Exception:
        return {}
    return {t: (v if isinstance(v, list) else [v]) for t, v in raw.items()}


RECIPES = _load()


def _current(ticker, day):
    """The recipe version valid as of `day` — the latest derived_day <= day (no lookahead). None if
    no version was derived on/before `day`."""
    vs = [r for r in RECIPES.get(ticker, []) if r.get("derived_day", "9999") <= day]
    return max(vs, key=lambda r: r["derived_day"]) if vs else None


def save_recipe(ticker, cik, basis, derived_day, os_at, float_at, control_M,
                dno_M=0.0, ads_ratio=1.0, control_holders=None, depends_on=None, conf="med"):
    """The LLM emits the validated exclusion SPLIT (dno_M = officers/directors block; control_M =
    control affiliates). Replay carries BOTH in shares and re-fetches ONLY O/S — the labels hold
    the D&O block fixed between proxy filings (a new proxy trips proxy-changed -> re-judge), so
    re-deriving it deterministically only re-introduces the proxy's stale share basis (split bug).
    control_holders = the excluded control entities (for finer staleness + the registry).
    APPEND-ONLY: adds a version keyed by derived_day (re-deriving the SAME day replaces it -> idempotent);
    earlier versions are kept so historical re-runs replay free."""
    # (F17/F29) UNIT-CONVENTION guard: os_at is the issuer's NATIVE XBRL O/S (ordinary shares for an
    # ADS name); ads_ratio converts to the listed class; dno_M/control_M are carried in LISTED units;
    # so for a normal-basis recipe float_at must equal os_at/ads_ratio - dno_M - control_M. Warn loudly
    # if it doesn't — that means a wrong-unit emit (e.g. exclusion in ordinary, or os_at in ADS) that
    # would replay to a wrong float. (Cheap to catch at warm time; impossible to catch later.)
    if not (os_at and os_at > 0):
        print(f"  ! recipe {ticker} @ {derived_day}: non-positive os_at={os_at} -> will defer on replay")
    if basis == "normal":
        implied = os_at / (ads_ratio or 1.0) - dno_M - control_M
        if abs(implied - float_at) > 0.01 * max(1.0, os_at):
            print(f"  ! recipe {ticker} @ {derived_day}: float_at {float_at:.3f} != os/ads-excl "
                  f"{implied:.3f} (UNIT/identity mismatch — check ads_ratio & dno/control units)")
    rec = {"cik": cik, "basis": basis, "ads_ratio": ads_ratio,
           "control_M": round(control_M, 4), "dno_M": round(dno_M, 4),
           "control_holders": control_holders or [],
           "os_at": round(os_at, 4), "float_at": round(float_at, 4),
           "derived_day": derived_day, "depends_on": depends_on or [], "conf": conf}
    vs = [r for r in RECIPES.get(ticker, []) if r.get("derived_day") != derived_day]  # replace same-day
    vs.append(rec)
    vs.sort(key=lambda r: r["derived_day"])
    RECIPES[ticker] = vs
    json.dump(RECIPES, open(RECIPES_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)


def is_stale(ticker, day, cik=None):
    """True if an EXCLUSION-changing filing was filed after the recipe's derived_day (<= day) —
    a new 13D/13G (control set), proxy (D&O), or offering/8-K (structure). A plain periodic that
    only updates O/S is NOT stale (we re-fetch O/S). True -> re-derive with the LLM."""
    r = _current(ticker, day)
    if not r:
        return True
    cik = cik or r["cik"]
    for f in edgar.query(cik, STRUCT_FORMS + OS_EVENT_FORMS, day, size=60):
        if r["derived_day"] < f["filedAt"][:10] <= day:
            return True
    return False


_SPLIT_MEMO = {}


def _split_in_window(cik, derived_day, day, lookback=30):
    """True if a reverse-split / consolidation-announcing 8-K OR 6-K is filed in [derived_day-lookback,
    day] -> the share basis may change mid-recipe and XBRL lags it -> defer & re-derive (the HUSA 899%
    failure mode). The 30d look-back covers announcements that precede their effective date (HUSA:
    announced 14d before derivation, effective the next day).
      (F04) also scans 6-K — foreign issuers announce consolidations there, not in an 8-K.
      (F30) size=200 + the explicit date filter so a long recipe window isn't truncated by a fixed
            newest-N cap on an active filer.
      (F45) memoized per (cik, derived_day, day) so the FREE happy-path doesn't re-read 8-K bodies
            on every later replay day."""
    key = (int(cik), derived_day, day)
    if key in _SPLIT_MEMO:
        return _SPLIT_MEMO[key]
    lo = (dt.date.fromisoformat(derived_day) - dt.timedelta(days=lookback)).isoformat()
    hit = False
    for f in edgar.query(cik, ["8-K", "8-K/A", "6-K", "6-K/A"], day, size=200):
        if not (lo <= f["filedAt"][:10] <= day):
            continue
        try:
            t = fg._text(f)
        except Exception:
            continue
        if _RS.search(t) and _RS_RATIO.search(t):
            hit = True
            break
    _SPLIT_MEMO[key] = hit
    return hit


def replay(ticker, day, cik=None):
    """Deterministic float on a NEW day from the cached recipe (no LLM). Returns
    (status, float_M): status in {ok, stale, no-recipe, no-os}. 'stale' -> hand to the LLM.
    Uses the recipe VERSION valid as of `day` (no lookahead)."""
    r = _current(ticker, day)
    if not r:
        return ("no-recipe", None)
    cik = cik or r["cik"]
    if is_stale(ticker, day, cik):
        return ("stale", None)
    x = D.xbrl_os(cik, day) or {}
    g = D.regex_os(cik, day) or {}
    xv, gv, nclass = x.get("val_M"), g.get("val_M"), (x.get("n_at_pick") or 1)
    if not (xv or gv):
        return ("no-os", None)
    # L8 O/S guard — establish a trustworthy share base or defer to the LLM (never replay on a bad O/S).
    # The recipe's os_at is an LLM-VALIDATED magnitude anchor. A re-fetched O/S beyond ±30% of it is
    # NOT trustworthy to replay against the carried exclusion: it's either a regex MISPARSE
    # (authorized-shares / wrong class, ~30x off), a basis change (ADS-vs-ordinary, multi-class), or
    # a material dilution/split that needs the control set re-judged -> defer & re-derive. The ±30%
    # band was calibrated on the 236-ticker IS simulation: it removes ~30 of 52 >10% replay misses at
    # ZERO cost to accurate (<=5%) replays (those barely move O/S, ratio~1.0). Accuracy-safe by
    # construction: tightening the band only ever defers MORE, never emits a wrong float.
    anchor = r.get("os_at")
    if not (anchor and anchor > 0):
        return ("os-uncertain", None)                     # (F46) no positive magnitude anchor -> defer
    # (F06/F12) frozen-XBRL-fact staleness: a dei O/S whose `end` long predates `day` has missed an
    # IPO/offering/split the periodic cadence hasn't absorbed (MB/UBXG/MSW). Foreign (ads_ratio!=1)
    # filers disclose interim actions via 6-K that the annual dei count lags, so use a tighter bound.
    # calib_age knee: >300d general / >100d foreign catches the band-uncatchable misses; only defers.
    age_max = 100 if (r.get("ads_ratio") or 1) != 1 else 300
    if xv and x.get("end") and \
            (dt.date.fromisoformat(day) - dt.date.fromisoformat(x["end"])).days > age_max:
        return ("stale-osfact", None)
    sane = lambda v: anchor / 1.3 <= v <= 1.3 * anchor
    if nclass == 1 and xv and sane(xv):
        os_ = xv                                          # single-class XBRL, anchor-consistent -> gold
    elif nclass == 1 and xv and gv and not anchor and abs(xv - gv) / max(xv, gv) <= 0.30:
        os_ = xv                                          # NO anchor only: require XBRL/regex agreement
        # (with an anchor, agreement must NOT override sanity — else a stale wrong-class XBRL that the
        #  regex also reads agrees with itself and leaks past the band, e.g. METCB Class-A 44M vs the
        #  listed Class-B 10.7M anchor. A non-sane value falls through to os-uncertain -> LLM.)
    elif nclass > 1:
        return ("os-multiclass", None)                    # flat XBRL can't pick the listed class -> LLM
    elif gv and not xv and sane(gv):
        os_ = gv                                          # XBRL absent -> anchor-sane regex fallback
    else:
        return ("os-uncertain", None)                     # can't establish a trustworthy O/S -> LLM
    if r["basis"] in ("spac", "ipo"):
        # (F01) a carried whole-float (redeemable / offering size) is invalidated by the de-SPAC close,
        # redemptions, lock-up expiry, follow-on dilution or founder conversion — reported in 8-K (or
        # 6-K for foreign issuers, e.g. the live BMGL ipo recipe), which is_stale does NOT scan. Any
        # such filing after the recipe -> re-derive rather than carry a now-stale whole float.
        for f in edgar.query(cik, ["8-K", "8-K/A", "6-K", "6-K/A"], day, size=80):
            if r["derived_day"] < f["filedAt"][:10] <= day:
                return ("stale", None)
        return ("ok", round(r["float_at"], 3))            # whole-float bases: carried (re-validate on event)
    if "control_M" not in r or "dno_M" not in r:
        return ("need-split", None)                       # old recipe lacks the exclusion split -> re-derive
    # Carry the LLM-validated exclusion (D&O + control) in SHARES, held fixed against the drifting
    # O/S — exactly how the labels are built (D&O constant between proxies). Re-deriving the D&O
    # deterministically only re-reads the SAME proxy (no intra-proxy drift to capture) at the proxy's
    # stale share basis (the reverse-split bug). Guard: if the ownership source changed since the
    # recipe was derived, the block may have moved -> defer to the LLM.
    f_now, f_der = fg._pick_own(cik, day), fg._pick_own(cik, r["derived_day"])
    if not f_now or not f_der:
        return ("no-proxy", None)
    if f_now["filedAt"][:10] != f_der["filedAt"][:10]:
        return ("proxy-changed", None)                    # new D&O source -> re-judge with the LLM
    if _split_in_window(cik, r["derived_day"], day):
        return ("split", None)                            # reverse split mid-recipe (XBRL lags) -> LLM
    # UNIT CONVENTION: os_/os_at are native XBRL units (ordinary shares for an ADS name); ads_ratio
    # converts to the listed class; dno_M/control_M are carried in LISTED units; so the float below is
    # in listed units (save_recipe asserts float_at matches this identity at warm time — F17/F29).
    ads = r["ads_ratio"] or 1.0
    fl = os_ / ads - r["dno_M"] - r["control_M"]
    if fl <= 0 or fl > os_ / ads * 1.01:                  # (F47) plausibility cap in LISTED units, not raw os_
        return ("implausible", None)
    return ("ok", round(fl, 3))


if __name__ == "__main__":
    import sys
    print(json.dumps(RECIPES.get(sys.argv[1], []), indent=1) if len(sys.argv) > 1 else
          f"{len(RECIPES)} tickers / {sum(len(v) for v in RECIPES.values())} recipe versions cached")
