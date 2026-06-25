#!/usr/bin/env python3
"""Deterministic free-float engine — EXPERIMENT (prove what works / what doesn't).

Legs:
  (1) O/S   — XBRL dei:EntityCommonStockSharesOutstanding (point-in-time), regex fallback.
  (2) excl  — insiders (proxy "as a group" row) + control blocks (13D filers / >20% non-13G).
  passive  — 13G filers + registered 13F managers are KEPT even if >20%.

This file is import-safe and CLI-runnable. It reuses the existing engine
(resolve_cik / _current_os / edgar). Goal is MEASUREMENT against float_is.csv, not production.
"""
import os, re, json, time, sys
import requests
import edgar
import float_from_filings as ff
import float_gather as fg
import _formula_probe as fp

UA = edgar.UA
XBRL_CACHE = os.path.join(ff.DATA, "_cache", "xbrl")           # per-CIK companyconcept JSON
os.makedirs(XBRL_CACHE, exist_ok=True)
USE_13DG = False           # L1: net-negative as a deterministic exclusion (A/B'd) -> off for the
#                            deterministic emit. forms13() is still computed as LLM INPUT (hints).


# ----------------------------------------------------------------------------- XBRL O/S leg
def _xbrl_concept(cik, concept="dei/EntityCommonStockSharesOutstanding"):
    """Cached companyconcept fetch -> list of share facts (or [] if none/none-tagged)."""
    safe = concept.replace("/", "_")
    p = os.path.join(XBRL_CACHE, f"{int(cik)}_{safe}.json")
    if os.path.exists(p):
        d = json.load(open(p))
    else:
        ns, tag = concept.split("/")
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/{ns}/{tag}.json"
        r = edgar._get(url)
        d = r.json() if r else {"units": {}}
        json.dump(d, open(p, "w"))
    return d.get("units", {}).get("shares", [])


def xbrl_os(cik, asof):
    """Point-in-time cover-page O/S from XBRL.
    Returns dict {val_M, end, form, filed, n_at_pick, total_M} or None.
    Pick = fact with the largest filed<=asof, then largest 'end'; if several distinct vals share
    that (filed,end) it's a multi-class cover (flag) -> we report both the listed-pick and the sum."""
    facts = [f for f in _xbrl_concept(cik) if f.get("filed", "") <= asof and f.get("val")]
    if not facts:
        return None
    facts.sort(key=lambda f: (f["filed"], f["end"]))
    pick = facts[-1]
    same = [f for f in facts if f["filed"] == pick["filed"] and f["end"] == pick["end"]]
    vals = sorted({f["val"] for f in same})
    return {
        "val_M": pick["val"] / 1e6,                 # the single (or largest) class at the pick
        "max_M": max(vals) / 1e6,
        "sum_M": sum(vals) / 1e6,                    # all classes that filing tagged at that date
        "end": pick["end"], "form": pick.get("form"), "filed": pick["filed"],
        "n_at_pick": len(vals),
    }


# ----------------------------------------------------------------------------- regex O/S leg (reuse engine)
_NUM = re.compile(r"[\d,]{6,}")


def regex_os(cik, asof):
    """Max cover-page O/S candidate from the latest periodic <= asof (engine's _current_os)."""
    cur = fg._current_os(cik, asof)
    if not cur:
        return None
    nums = []
    for c in cur[2]:
        m = _NUM.search(c)
        if m:
            nums.append(int(m.group(0).replace(",", "")))
    if not nums:
        return None
    return {"val_M": max(nums) / 1e6, "form": cur[0], "filed": cur[1], "n": len(nums)}


# ----------------------------------------------------------------------------- archetype tag (for breakdown)
def archetype(basis, note):
    s = ((basis or "") + " | " + (note or "")).lower()
    if re.search(r"20-f|6-k|ordinary|\bads\b|depositary", s):
        return "foreign/ADS"
    if re.search(r"class [a-c]\b|multi-?class|dual.?class", s):
        return "multi-class"
    if re.search(r"split|consolidation|reverse|reorganiz", s):
        return "split/reverse"
    if re.search(r"spac|de-spac|redeem|trust", s):
        return "SPAC"
    if re.search(r"\bipo\b|s-1|424b|offering|prospectus", s):
        return "IPO/offering"
    return "US-single-class"


# ----------------------------------------------------------------------------- full deterministic float
# Point-in-time port of _widen_probe.measure(): swap (a) DT-current os -> XBRL point-in-time os,
# (b) latest ownership filing -> point-in-time _pick_own(cik, asof), (c) DT float -> caller compares
# to the label. Reuses ALL the exclusion machinery (group ex-options, >20%/affiliate strat with 13G
# kept, foreign item7 register, reverse-split/ADS rescaling) verbatim.
import _widen_probe as wp
import datetime as _dt

IPO_FORMS = ["424B4", "424B1", "424B3"]
_IPO_RE = re.compile(r"(?i)initial\s+public\s+offering\s+of\s+([\d,]{6,})\s+(?:ordinary|common)\s+shares")


def basis_route(cik, asof, os_):
    """Structured BASIS ROUTER (L2): detect SPAC / fresh-IPO from filings and return the
    whole-float basis, bypassing the D&O+holders path that fails on these archetypes.
      SPAC  -> float = public shares 'subject to possible redemption' (os - founder).
      IPO   -> float = the public offering size (os - all pre-IPO holders).
    Returns (basis, float_M) or (None, None). EDGAR-only (the sibling's ipo_offering_basis
    still called the retired sec-api; this repoints it to edgar.query)."""
    # SPAC: redeemable public shares on the latest periodic cover (10-Q/10-K, not the proxy)
    for f in fg._query(cik, fg.PERIODIC, asof, size=2):
        red = [r for r in fp.redeemable_shares(fg._text(f).translate(wp.ZW))
               if 0.15 * os_ * 1e6 <= r <= 1.02 * os_ * 1e6]
        if red:
            return "spac", max(red) / 1e6
    # fresh IPO: a final prospectus (424B) filed within ~15 months before as_of
    for f in fg._query(cik, IPO_FORMS, asof, size=3, order="desc"):
        filed = f["filedAt"][:10]
        if (_dt.date.fromisoformat(asof) - _dt.date.fromisoformat(filed)).days > 460:
            continue
        m = _IPO_RE.search(fg._text(f).translate(wp.ZW)[:8000])
        if m:
            off = int(m.group(1).replace(",", "")) / 1e6
            if 0 < off < os_:
                return "ipo", off
    return None, None


# ----------------------------------------------------------------------------- L1: 13D/13G form-type leg
SC13_FORMS = ["SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A",
              "SCHEDULE 13D", "SCHEDULE 13G", "SCHEDULE 13D/A", "SCHEDULE 13G/A"]
_LABEL = re.compile(r"(?i)name[s]?\s+of\s+reporting\s+person")
_SUB = re.compile(r"(?i)\(?\s*entities\s+only\s*\)?|i\.?r\.?s\.?\s+identification\s+nos?\.?\s+of\s+above"
                  r"\s+persons?|s\.s\.\s+or\s+i\.r\.s\.[^\n]*|\(see\s+instructions?\)")
_AGG = re.compile(r"(?i)aggregate\s+amount\s+beneficially\s+owned\s+by\s+each\s+reporting\s+person"
                  r"[\s\S]{0,220}?([\d]{1,3}(?:,\d{3}){1,4}|\b\d{4,}\b)")


def _rp_name(t, pos):
    win = _SUB.sub(" ", re.sub(r"(?i)^[^a-z]*?name[s]?\s+of\s+reporting\s+person[s]?", "", t[pos:pos + 300], count=1))
    m = re.search(r"([A-Z][A-Za-zÀ-ÿ0-9.,&'/\- ]{2,60})", win)
    if not m:
        return None
    nm = re.split(r"(?i)\s*(?:\b\d|check\b|\(2\)|2\.|s\.s\.|page\b)", m.group(1))[0]
    return " ".join(nm.split()).strip(" .,-") or None


def forms13(cik, asof, os_):
    """L1: {tokenset_key: {name, cls(13D/13G), shares_M, date, caps}} for every 13D/13G filed
    ABOUT this subject <= as_of (they live in the subject's own submissions feed). Latest filing
    per reporting person wins (/A supersedes). Form type = the classification (13D control / 13G
    passive). Shares capped at O/S."""
    out = {}
    for f in edgar.query(cik, SC13_FORMS, asof, size=16, order="desc"):
        try:
            t = fg._text(f).translate(wp.ZW)
        except Exception:
            continue
        lm = _LABEL.search(t)
        nm = _rp_name(t, lm.start()) if lm else None
        if not nm:
            continue
        caps = wp._caps(nm)
        if not caps:
            continue
        key = " ".join(sorted(caps))
        if key in out:                       # already have a later filing for this person
            continue
        ag = _AGG.search(t)
        sh = int(ag.group(1).replace(",", "")) / 1e6 if ag else None
        if sh and sh > os_ * 1.02:
            sh = None                        # misparse (exceeds O/S)
        out[key] = {"name": nm[:26], "cls": "13D" if "13D" in f["formType"] else "13G",
                    "shares_M": sh, "date": f["filedAt"][:10], "caps": caps}
    return out


def _nmatch(a, b):
    """Token-overlap name match between a holder row and a 13D/13G reporting person."""
    sh = a & b
    if not sh:
        return False
    if a <= b or b <= a or len(sh) >= 2:
        return True
    return len(sh) == 1 and len(next(iter(sh))) >= 6      # one distinctive surname (rosenbach)


def strat_13dg(text, gm, os_, foreign, f13, asof):
    """Strategic/control exclusion using ACTUAL 13D/13G form type (L1) instead of noisy parser
    tags. Itemizes proxy holders (fp.holders), then: matched 13G -> KEEP (override); matched 13D
    -> EXCLUDE (control, any %); unmatched -> induced rule (>=20% / affiliate>=10% / foreign
    shell>=10%, 13G-keep). PLUS control-adds: recent 13D filers (<=18mo, >=2% O/S) absent from the
    proxy table AND not in the D&O group -> add (the under-tagged control block, e.g. CFSB Beach MHC).
    Returns (excluded_M, info)."""
    rows = fp.holders(text, gm, os_, foreign)
    dno_caps = set()
    for nm, sh, pct, feat in rows:
        if feat.get("do") or feat.get("deemed"):
            dno_caps |= wp._caps(nm)
    best, used13 = {}, set()
    for nm, sh, pct, feat in rows:           # one row per holder (largest block), drop D&O/deemed
        if feat.get("do") or feat.get("deemed"):
            continue
        k = " ".join(sorted(wp._caps(nm))) or nm
        if k not in best or sh > best[k][1]:
            best[k] = (nm, sh, pct, feat)
    excl = 0.0
    kept13g = added = matched13d = ruled = 0
    for nm, sh, pct, feat in best.values():
        caps = wp._caps(nm)
        hit = next((v for v in f13.values() if _nmatch(caps, v["caps"])), None)
        if hit:
            used13.add(" ".join(sorted(hit["caps"])))
            if hit["cls"] == "13G":
                kept13g += 1; continue                       # passive -> KEEP (fixes over-excl)
            excl += sh; matched13d += 1; continue            # 13D control -> EXCLUDE (any %)
        # unmatched: induced rule on actual O/S fraction; 13G heuristic still keeps
        frac = sh / os_ if os_ else 0
        if feat.get("g13"):
            continue
        if frac >= 0.20 or (feat.get("affil") and frac >= 0.10) or \
                ((feat.get("shell") or feat.get("preipo")) and foreign and frac >= 0.10):
            excl += sh; ruled += 1
    # control-adds: 13D filers not in the proxy table, not in D&O. No tight staleness window —
    # structural control (MHC / founder / parent shell) doesn't expire; latest-filing-per-person
    # (a holder who exited files a 13G/13D-A) + the O/S cap + abstain-if-excl>O/S bound the risk.
    cutoff = (_dt.date.fromisoformat(asof) - _dt.timedelta(days=1460)).isoformat()
    for key, v in f13.items():
        if v["cls"] != "13D" or key in used13 or not v["shares_M"]:
            continue
        if v["date"] < cutoff or v["shares_M"] < 0.02 * os_:
            continue
        if _nmatch(v["caps"], dno_caps):
            continue                                          # already inside the D&O group
        excl += v["shares_M"]; added += 1
    return excl, {"kept13g": kept13g, "matched13d": matched13d, "added": added, "ruled": ruled,
                  "n13": len(f13)}


def full(ticker, asof, cik=None):
    """Returns dict with float_det (millions) + diagnostics, or {'cls': <fail>}."""
    cik = cik or fg.resolve_cik(ticker, asof)
    if not cik:
        return {"cls": "no-cik"}
    x = xbrl_os(cik, asof)
    g = regex_os(cik, asof)
    os_ = (x or {}).get("val_M") or (g or {}).get("val_M")
    os_src = "xbrl" if x else ("regex" if g else None)
    if not os_:
        return {"cls": "no-os", "cik": cik}
    # L8: XBRL-vs-regex O/S disagreement = unreliable share base (stale fact / wrong class / wrong
    # entity, e.g. ARBKL 9x) -> abstain. A cheap, strong accuracy guard from two free sources.
    osflag = ""
    if x and g and x.get("val_M") and g.get("val_M"):
        # large disagreement = wrong-entity / wrong-class (ARBKL 9x), not minor XBRL-vs-regex noise
        # (XBRL is the more precise source, so a small gap means XBRL is fine -> don't abstain)
        if abs(x["val_M"] - g["val_M"]) / max(x["val_M"], g["val_M"]) > 0.30:
            osflag += "+osdisagree"
    # L2 basis router: SPAC / fresh-IPO are whole-float bases, not D&O+holders
    broute, bfloat = basis_route(cik, asof, os_)
    if broute:
        return {"cls": "ok", "float_det": bfloat, "os": os_, "os_src": os_src,
                "form": broute.upper(), "g_exo": os_ - bfloat, "strat": 0.0,
                "conf": broute + osflag, "factor": 1.0, "xbrl_n": (x or {}).get("n_at_pick", "")}
    f = fg._pick_own(cik, asof)
    if not f:
        return {"cls": "no-proxy", "cik": cik, "os": os_}
    form, filed = f["formType"], f["filedAt"][:10]
    text = fg._text(f).translate(wp.ZW)
    foreign = form in ("20-F", "20-F/A")
    # L8: very stale ownership filing (the ALCE lesson — holders likely diluted since)
    if (_dt.date.fromisoformat(asof) - _dt.date.fromisoformat(filed)).days > 550:
        osflag += "+stale"
    # L3: true ADS (ratio>1.5) — units ambiguity (ordinary vs ADS); the LLM rescales these well
    r_ads = wp.ads_ratio(text)
    if r_ads and r_ads > 1.5 and (foreign or "depositary" in text[:60000].lower()):
        osflag += "+adsOS"

    ge = wp.group_exoptions(text, os_)
    strat_pre = None
    if not ge:
        i7 = wp.item7_holders(text, os_) if form == "20-F" else None
        if i7 is not None:
            g_exo = benef = i7
            conf, iosb = "item7", None
        else:
            gm2 = wp.table_anchor(text)
            s2, dno2 = wp.outside_holders(text, gm2, os_, form == "20-F") if gm2 else (0.0, 0.0)
            if dno2 > 0:
                g_exo = benef = dno2
                conf, iosb, strat_pre = "nogroup", None, s2
            elif s2 > 0:
                g_exo = benef = 0.0
                conf, iosb, strat_pre = "nogroup", None, s2
            else:
                return {"cls": "parse-fail", "os": os_, "os_src": os_src, "form": form}
    else:
        g_exo, benef, conf, iosb = ge
    if conf == "misparse>OS":
        return {"cls": "multiclass?", "os": os_, "os_src": os_src, "form": form}

    basis, factor = os_, 1.0
    if iosb and os_ * 1e6 / iosb <= 0.77 and iosb <= os_ * 1e6 * 25:
        basis, factor = iosb / 1e6, os_ * 1e6 / iosb
        conf += "+scaled"
    elif iosb and (rat := os_ * 1e6 / iosb) >= 3:
        r = wp.ads_ratio(text)
        if r and r < 1 and abs(rat * r - 1) <= 0.4:
            basis, factor = iosb / 1e6, rat
            conf += "+ads"
    if conf == "item7":
        strat = 0.0
    elif strat_pre is not None:
        strat = strat_pre
    else:
        gm = wp.GROUP2.search(text)
        f13 = forms13(cik, asof, basis) if (USE_13DG and gm) else {}
        if f13:
            strat, i13 = strat_13dg(text, gm, basis, form == "20-F", f13, asof)
            conf += f"+13dg[{i13['matched13d']}x{i13['added']}+{i13['kept13g']}k]"
            if i13["added"]:                 # control-add = a guessed block (stale/dup risk) -> abstain
                conf += "+addrisk"
        else:
            strat, dno = wp.outside_holders(text, gm, basis, form == "20-F")
            if conf.startswith("nil-group") and dno > 0:
                g_exo = benef = dno
                conf = "nil-group+do"
    float_det = os_ - (g_exo + strat) * factor
    return {"cls": "ok", "float_det": float_det, "os": os_, "os_src": os_src, "form": form,
            "g_exo": g_exo * factor, "strat": strat * factor, "conf": conf + osflag,
            "factor": factor, "xbrl_n": (x or {}).get("n_at_pick", "")}


# ----------------------------------------------------------------------------- compressed LLM dossier
def compressed_dossier(ticker, asof, cik=None):
    """Pre-digested input for the LLM tail: the deterministic engine's structured outputs +
    the key filing windows, so a cheaper/faster agent adjudicates a summary instead of reading
    raw filings. Returns (text, det_result)."""
    cik = cik or fg.resolve_cik(ticker, asof)
    d = full(ticker, asof, cik)
    L = [f"== FLOAT DOSSIER {ticker} as_of {asof} (point-in-time; filings <= as_of) =="]
    x, g = xbrl_os(cik, asof), regex_os(cik, asof)
    if x:
        L.append(f"O/S (XBRL dei): {x['val_M']:.3f}M  (as-of {x['end']}, {x['form']} filed {x['filed']}"
                 + (f", {x['n_at_pick']} classes at this date!)" if x.get('n_at_pick', 1) > 1 else ")"))
    if g:
        L.append(f"O/S (regex cross-check, latest periodic): {g['val_M']:.3f}M  [{g['form']} {g['filed']}]")
    if d.get("cls") == "ok":
        L.append(f"DETERMINISTIC: float~{d['float_det']:.2f}M = O/S {d['os']:.2f} - D&O {d['g_exo']:.2f} "
                 f"- control {d['strat']:.2f}   conf={d['conf']}")
        L.append(f"  -> {'CONFIDENT (verify)' if is_confident(d) else 'ABSTAINED (you decide): ' + d['conf']}")
    else:
        L.append(f"DETERMINISTIC: could not compute ({d.get('cls')})")
    # 13D/13G form-type blocks — the control(13D)/passive(13G) hints
    try:
        f13 = forms13(cik, asof, d.get("os") or (x or {}).get("val_M") or 1e9)
    except Exception:
        f13 = {}
    if f13:
        L.append("13D/13G BLOCKS (a HINT, not a verdict — 13D = active >5% stake (usually control: "
                 "activist/founder/parent; but a passive adviser/fund can also file 13D — JUDGE it); "
                 "13G = passive (usually keep). Counts are as-of each filing's date — rescale for any split since.")
        for v in sorted(f13.values(), key=lambda v: -(v["shares_M"] or 0)):
            tag = "13D: judge control-vs-passive" if v["cls"] == "13D" else "13G: usually keep"
            L.append(f"  {v['cls']:4} {v['name']:26} {('%.2fM' % v['shares_M']) if v['shares_M'] else '   ?':>8}"
                     f"  ({v['date']})  [{tag}]")
    # the proxy ownership window (the table the agent adjudicates)
    f = fg._pick_own(cik, asof)
    if f:
        t = fg._text(f).translate(wp.ZW)
        w = wp._own_window(t) if hasattr(wp, "_own_window") else fg._own_window(t)
        if w:
            L.append(f"\nOWNERSHIP TABLE ({f['formType']} {f['filedAt'][:10]}):\n" + w[0][:2200])
    L.append("\nApply FLOAT_PROTOCOL: float = O/S - (officers+directors+control-affiliates+non-passive "
             ">20%); KEEP passive 13G/index even if >20%. Use the 13D/13G tags above. Return float_M, os_M, conf.")
    return "\n".join(L), d


# ----------------------------------------------------------------------------- L7: abstention rule
# Single canonical definition of "trust the deterministic float" — used by the benchmark AND the
# future LLM router. Accuracy is preserved by abstaining on EVERY uncertain signal -> the LLM.
ABSTAIN_TOKENS = ("multiclass", "nogroup", "misparse", "nil-group", "item7", "spac",
                  "scaled", "ads", "addrisk", "osdisagree", "stale")


def is_confident(d):
    """True -> emit the deterministic float; False -> route this (ticker, day) to the LLM."""
    if d.get("cls") != "ok":
        return False
    if d.get("os_src") != "xbrl":                 # no clean structured O/S
        return False
    if d.get("xbrl_n") not in ("", 1, None):      # multi-class O/S (wrong-class risk)
        return False
    fd, os_ = d.get("float_det"), d.get("os")
    if fd is None or os_ is None or fd <= 0 or fd > os_ * 1.01:
        return False
    return not any(t in d.get("conf", "") for t in ABSTAIN_TOKENS)


if __name__ == "__main__":
    # quick single-name probe: det_float.py TICKER AS_OF [CIK]
    t, asof = sys.argv[1], sys.argv[2]
    cik = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print("XBRL:", xbrl_os(cik, asof) if cik else None)
    print("FULL:", full(t, asof, cik))
