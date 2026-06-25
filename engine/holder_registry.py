#!/usr/bin/env python3
"""§16 lever 1 — persistent holder-classification registry (the path to ~$200/yr).

The expensive LLM judgment is "is this holder a control affiliate (exclude) or passive (keep)?"
That judgment is about a STABLE ENTITY, reusable across every stock it appears in -> classify ONCE,
cache forever. Three free/structured sources before the LLM:
  1. registry  — already-classified entity (cached, keyed on CIK when known else normalized name).
  2. keep-list — the recurring passive complex (index funds + biotech-specialist passives, from §8.1).
  3. 13F-filer — a registered 13F-HR manager that filed a 13G is passive by construction (the §8.3
     generalization: backs the keep-list with the whole institutional universe, for free).
Anything else -> "judge" (the LLM classifies it once; the result is written back to the registry).
"""
import os, re, json
import edgar
import float_from_filings as ff

UA = edgar.UA
REG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "holder_registry.json")
F13_CACHE = os.path.join(ff.DATA, "_cache", "_13f_lookup.json")   # gitignored EDGAR-lookup cache

# the recurring passive complex (§8.1): index/quant + biotech-specialist passives that show up everywhere
KEEPLIST = [r"black\s*rock", r"vanguard", r"state\s*street", r"\bfmr\b|fidelity", r"geode",
            r"dimensional|\bdfa\b", r"invesco", r"northern\s*trust", r"t\.?\s*rowe", r"\bssga\b",
            r"charles\s*schwab|\bschwab\b", r"morgan\s*stanley", r"goldman\s*sachs", r"jpmorgan|j\.?p\.?\s*morgan",
            r"bank\s+of\s+america", r"wellington", r"nuveen|tiaa", r"\bbny\b|mellon", r"capital\s+(world|research|group)",
            r"susquehanna", r"renaissance\s+tech", r"two\s*sigma", r"d\.?\s*e\.?\s*shaw", r"millennium\s+management",
            r"citadel", r"point\s*72", r"jane\s*street",
            # biotech-specialist passives recurring in this universe (§8.1 second tier)
            r"baker\s+bro", r"\bra\s+capital", r"deep\s*track", r"\bbvf\b", r"perceptive", r"cormorant",
            r"\bvivo\b", r"soleus", r"venrock", r"adage", r"alyeska", r"wellington"]


def norm(name):
    """Distinctive lowercased token key for a holder name (drops corp suffixes / generic words)."""
    toks = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.&'-]+", name or "")
    drop = {"the", "inc", "inc.", "llc", "l.l.c.", "lp", "l.p.", "ltd", "ltd.", "limited", "co", "co.",
            "corp", "corp.", "corporation", "company", "holdings", "holding", "group", "capital",
            "management", "mgmt", "partners", "partnership", "advisors", "advisers", "fund", "funds",
            "trust", "international", "and", "of", "&"}
    keep = [t.lower().strip(".") for t in toks if t.lower().strip(".") not in drop and len(t) > 1]
    return " ".join(keep)


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


REGISTRY = _load(REG_PATH, {})           # key -> {name, cik, class, source}
_F13 = _load(F13_CACHE, {})              # normname -> {is_13f, cik}


def _save_registry():
    json.dump(REGISTRY, open(REG_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)


def _save_f13():
    os.makedirs(os.path.dirname(F13_CACHE), exist_ok=True)
    json.dump(_F13, open(F13_CACHE, "w", encoding="utf-8"))


def keeplist_passive(name):
    return any(re.search(p, name, re.I) for p in KEEPLIST)


def lookup_13f(name):
    """Is `name` itself a registered 13F-HR filer (institutional manager => passive on a 13G)?
    -> (is_13f, cik). Cached. Uses EDGAR full-text search of 13F-HR filings and requires the
    matched FILER's name to share a distinctive token with the holder — so a 13F manager that
    merely HOLDS a Hatsopoulos-linked stock does NOT make 'Hatsopoulos' a 13F filer."""
    k = norm(name)
    if not k:
        return (False, None)
    if k in _F13:
        v = _F13[k]
        return (v["is_13f"], v["cik"])
    # (a) resolve the holder's CIK: full-text search any filing, take a hit whose FILER name matches.
    qtok = "+".join(k.split()[:3])
    r = edgar._get(f"https://efts.sec.gov/LATEST/search-index?q=%22{qtok}%22")
    cik, ktok = None, set(k.split())
    if r is not None and r.status_code == 200:
        try:
            hits = r.json().get("hits", {}).get("hits", [])
        except Exception:
            hits = []
        for h in hits:
            src = h.get("_source", {})
            for j, dn in enumerate(src.get("display_names", [])):
                if set(norm(dn).split()) >= ktok or (set(norm(dn).split()) & ktok and len(ktok) >= 2):
                    cks = src.get("ciks", [])
                    if cks:
                        try:
                            cik = int(str(cks[min(j, len(cks) - 1)]).lstrip("0") or 0) or None
                        except Exception:
                            pass
                    break
            if cik:
                break
    # (b) DEFINITIVE check: does that CIK's OWN submissions include a 13F-HR? (institutional manager)
    is13f = bool(cik) and any("13F" in f["formType"] for f in edgar._assemble(cik))
    _F13[k] = {"is_13f": is13f, "cik": cik}
    _save_f13()
    return (is13f, cik)


def classify(name, form_type=None, use_edgar=True):
    """Return (class, source): class in {passive, control, judge}. 'judge' -> hand to the LLM,
    then call set_class() to cache the verdict. form_type 13D leans control / 13G leans passive,
    but is only a hint (per the MTR lesson: a passive adviser can file 13D)."""
    k = norm(name)
    if k in REGISTRY:
        return (REGISTRY[k]["class"], "registry")          # cached LLM/manual verdict wins
    if form_type and "13D" in form_type.upper():
        return ("judge", "13D-active")                     # active stake -> never auto-passive (MTR/CFSB/RILYT)
    if keeplist_passive(name):
        return ("passive", "keeplist")
    if use_edgar:
        is13f, cik = lookup_13f(name)
        if is13f:
            REGISTRY[k] = {"name": name[:40], "cik": cik, "class": "passive", "source": "13F-filer"}
            _save_registry()
            return ("passive", "13F-filer")
    return ("judge", "unknown")


def set_class(name, cls, cik=None, source="llm"):
    """Persist an LLM (or manual) verdict so the entity is never re-judged."""
    k = norm(name)
    if not k:
        return
    REGISTRY[k] = {"name": name[:40], "cik": cik, "class": cls, "source": source}
    _save_registry()


if __name__ == "__main__":
    tests = [("BlackRock, Inc.", "13G"), ("The Vanguard Group", "13G"), ("Baker Bros. Advisors", "13G"),
             ("Soros Fund Management LLC", "13G"), ("A. Gile & Co. LLC", "13D/A"),
             ("Beach Bancorp MHC", "SCHEDULE 13D"), ("Bryant R. Riley", "13D")]
    for nm, ft in tests:
        print(f"  {str(classify(nm, ft)):28} [{ft:13}] {nm}")
