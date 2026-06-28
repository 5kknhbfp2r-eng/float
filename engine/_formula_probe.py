"""PHASE 1 — per-ticker formula recovery (CLAUDE.md TEMP INSTRUCTIONS).
For each ticker, DTexcl = os - float is known EXACTLY. Parse all candidate SEC numbers
(group ex-options/beneficial, every holder row + its features, share classes), rescale
to DT's O/S basis (reverse-split / ADS), and find the subset (group basis + holder
subset) that reproduces DTexcl near-exact. Record the formula + features. Prefer the
minimal/explained subset; FLAG ambiguity; never accept a coincidental fit.
ISOLATED per ticker -- no global model, no sentinels. Writes a JSON formula DB for
Phase 2. Usage: python _formula_probe.py [TICKER...]   (no args = 150-sample)
"""
import re, sys, json, itertools
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import float_from_filings as ff
import _affil_probe as ap
import _cik_probe as cm
import _widen_probe as wp

HEADWORDS = {"beneficially", "percentage", "percent", "number", "security", "stockholders",
             "shareholders", "holders", "officers", "directors", "common", "ordinary",
             "shares", "total", "principal", "major", "each", "name", "amount", "title",
             "class", "voting", "aggregate", "executive", "applicable", "based", "all",
             "greater", "more", "owners", "owner", "owned", "of", "and", "or", "the", "5"}


def strip_head(nm):
    """Drop leading header-word / punctuation tokens so a prose-PREFIXED holder name keeps
    its real holder ('5% Stockholders - Hunniwell' -> 'Hunniwell', 'Beneficially Owned The
    Capri Family Foundation' -> 'Capri Family Foundation'). Returns '' if nothing real left."""
    toks = nm.replace("-", " ").split()
    while toks and (toks[0].lower().strip(".,") in HEADWORDS or not toks[0][:1].isalpha()):
        toks.pop(0)
    return " ".join(toks) if toks and toks[0][:1].isupper() else ""
SHELL = re.compile(r"(?i)(?:wholly[\s-]+|jointly\s+)?(?:owned|controlled|held)\s+"
                   r"(?:as\s+to\s+[\d.]+%\s+)?by\s+(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*"
                   r"[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){1,3}\b")
IDX = re.compile(r"(?i)blackrock|vanguard|dimensional|state street|geode|"
                 r"\bSSgA\b|northern trust|charles schwab|invesco|fmr\b|fidelity")


def holders(text, gm, os_m, foreign):
    """All candidate holder rows (name, shares_M, pct, features). No exclusion decision."""
    hd = list(wp.OWN_HDR.finditer(text, max(0, gm.start() - 6000), gm.start()))
    start = hd[0].end() if hd else max(0, gm.start() - 4000)
    span = text[start:gm.end() + wp.AFTER_GROUP]
    g0, g1 = gm.start() - start, gm.end() - start
    zone = text[gm.end():gm.end() + wp.FN_ZONE]
    fn_txt, fnm = {}, [f for f in re.finditer(r"\((\d{1,2}|[a-z])\)", zone)
                       if re.match(r"\s+[A-Z]", zone[f.end():f.end() + 4])]
    for i, f in enumerate(fnm):
        seg = zone[f.end():fnm[i + 1].start() if i + 1 < len(fnm) else f.end() + 800][:800]
        e = wp.FN_END.search(seg)
        fn_txt[f.group(1)] = seg[:e.start()] if e else seg
    gvals = set()
    graw = span[g1:g1 + 260]
    gw = re.search(r"[A-Za-z]{4,}", graw)
    for n in re.findall(r"[\d,]{4,}", graw[:gw.start()] if gw else graw):
        if (v := int(n.replace(",", ""))) >= 1000:
            gvals.add(v)
    marks = sorted([(m.start(), "5p") for m in wp.SEC_5P.finditer(span)] +
                   [(m.start(), "do") for m in wp.SEC_DO.finditer(span) if not (g0 <= m.start() < g1)])
    dno_tok = set()
    for p, k in marks:
        if k == "do":
            nxt = min([q for q, _ in marks if q > p] + [g0 if g0 > p else len(span)] + [len(span)])
            dno_tok |= wp._caps(span[p:nxt])
    rows, prev = [], 0
    for m in wp.HOLDER.finditer(span):
        if g0 <= m.start() < g1:
            continue
        nm, sh, pct = strip_head(m.group(1).strip()), int(m.group(2).replace(",", "")), float(m.group(3))
        row = span[max(prev, m.start() - 200):m.end()]; prev = m.end()
        if pct > 100 or sh > os_m * 1e6 * 1.01 or not nm or wp.BAD.search(nm):  # prose-prefixed
            continue                                          # name -> strip header words first
        sec = max([(p, k) for p, k in marks if p <= m.start()], default=(0, "5p"))[1]
        nmt = wp._caps(nm)
        bods = [b for b in fn_txt.values() if nmt and nmt <= wp._caps(b)]
        refs = set(re.findall(r"\((\d{1,2}|[a-z])\)", row))
        feat = dict(do=(sec == "do"), gt20=(pct > 20 or sh > 0.20 * os_m * 1e6),
                    affil=any(wp.AFFIL.search(fn_txt.get(r, "")) for r in refs)
                          or any(wp._caps(b) & dno_tok for b in bods),
                    shell=any(SHELL.search(b) for b in bods),
                    g13=any(re.search(r"(?i)\b13G\b", b) for b in bods) or bool(IDX.search(nm)),
                    deemed=(sh in gvals))
        rows.append([nm[:24], sh / 1e6, pct, feat])
        for b in bods + [fn_txt.get(r, "") for r in refs]:   # ex-derivative BASIC figure: DT may
            mb = re.search(r"(?i)\(a\)\s+([\d,]{4,})\s+(?:common|ordinary)\s+shares?", b)  # use a
            if mb and 0 < (bv := int(mb.group(1).replace(",", ""))) < sh:   # holder's "(a) X common
                rows.append([nm[:18] + "~basic", bv / 1e6, pct, feat]); break  # shares" ex-warrants
        #   -- footnote found by NAME (bods) or by the row's (n) marker (refs): SALP cites itself
        #   as "SALP", so name-match fails; the (1) marker still reaches its footnote (LMNL)
    return rows


PROS_FORMS = ["424B4", "424B1", "424B3", "F-1", "F-1/A", "S-1", "S-1/A"]  # 424B3 = de-SPAC resale
PROS_HDR = re.compile(r"(?i)principal\s+(?:and selling\s+)?(?:stock|share)holders"
                      r"|beneficial\s+owner|major\s+shareholders")


def prospectus_candidates(cik, os_m, asof="2026-06-04"):
    """Pre-IPO holder rows from the IPO prospectus (424B4/F-1) -- the holders DT excludes
    that the later 20-F/proxy omits. Tagged 'preipo' (an excludable feature)."""
    import requests
    ft = ",".join(f'"{x}"' for x in PROS_FORMS)
    q = f"cik:{int(cik)} AND formType:({ft}) AND filedAt:[2018-01-01 TO {asof}T23:59:59]"
    body = {"query": q, "from": "0", "size": "10", "sort": [{"filedAt": {"order": "asc"}}]}
    try:
        r = requests.post("https://api.sec-api.io", json=body, headers=ff.HDR, timeout=60)
        fl = [f for f in r.json().get("filings", []) if f["formType"] in PROS_FORMS]
    except Exception:
        return []
    if not fl:
        return []
    text = ff.fetch_text(fl[0]["linkToFilingDetails"], fl[0]["accessionNo"]).translate(wp.ZW)
    iss = issuance_blocks(text, os_m)         # affiliate share ISSUANCES (de-SPAC/direct-listing
    best, bestn = None, 0                     # Organization Transactions: AIAI 27.5M+25.1M+16.3M)
    for h in wp.OWN_HDR.finditer(text):       # broad: "Security Ownership" / "Principal and
        n = len(list(wp.HOLDER.finditer(text, h.end(), h.end() + 2800)))   # Registered..." (AIAI)
        if n > bestn:
            best, bestn = h, n
    if not best:
        return iss                            # no %-table (AIAI selling list): issuances only
    rows, seen = [], set()
    for m in wp.HOLDER.finditer(text, best.end(), best.end() + 2800):
        nm, sh, pct = strip_head(m.group(1).strip()), int(m.group(2).replace(",", "")), float(m.group(3))
        if pct > 100 or sh > os_m * 1e6 * 1.01 or not nm or wp.BAD.search(nm) or sh in seen:
            continue
        seen.add(sh)
        rows.append([nm[:24], sh / 1e6, pct,
                     dict(do=False, gt20=(pct > 20), affil=False, shell=True, g13=False,
                          deemed=False, preipo=True)])
    if len(rows) < 2:                         # no-% prospectus register: self-validating loose
        for m in LOOSE_ROW.finditer(text, best.end(), best.end() + 2800):
            nm, sh, pct = strip_head(m.group(1).strip()), int(m.group(2).replace(",", "")), float(m.group(3))
            if wp.BAD.search(nm) or not nm or sh in seen \
                    or sh > os_m * 1e6 * 1.01 or not 0 < pct <= 100:
                continue
            if abs(sh / (os_m * 1e6) * 100 - pct) <= 0.30 * max(pct, 1):
                seen.add(sh)
                rows.append([nm[:24], sh / 1e6, pct, dict(do=False, gt20=(pct > 20),
                             affil=False, shell=True, g13=False, deemed=False, preipo=True)])
    return rows + [r for r in iss if round(r[1] * 1e6) not in seen]


ISSUE = re.compile(r"(?i)(?:issued|(?<!authorized\sto\s)issue|consideration\s+paid[^.]{0,40}?was"
                   r"|aggregate\s+of(?:\s+up\s+to)?)\s+(?:[A-Z][A-Za-z0-9]+\s+){0,2}([\d,]{7,})"
                   r"\s+shares\s+of\s+(?:our\s+)?(?:Class\s+[AB]\s+)?common\s+stock")


def issuance_blocks(text, os_m):
    """Big affiliate share ISSUANCES stated in a de-SPAC / direct-listing prospectus's
    'Organization Transactions' (acquisitions, license, preferred exchange) -- the blocks DT
    excludes that aren't in the selling-shareholder table as one row. AIAI: 27,472,430 +
    25,137,000 + 16,300,000 = 68.91M = its excl. Each DISTINCT count in (5%, 60%] of O/S
    (drops 'authorized to issue' capital and the grand-total), tagged affiliate; the solver
    sums the subset. Returns [] for an ordinary IPO (no such blocks)."""
    out, seen = [], set()
    for m in ISSUE.finditer(text):
        sh = int(m.group(1).replace(",", ""))
        if 0.05 * os_m * 1e6 < sh <= 0.60 * os_m * 1e6 and round(sh / 1e3) not in seen:
            seen.add(round(sh / 1e3))
            out.append([f"issued {sh/1e6:.2f}M", sh / 1e6, sh / (os_m * 1e6) * 100,
                        dict(do=False, gt20=(sh > 0.20 * os_m * 1e6), affil=True, shell=False,
                             g13=False, deemed=False, preipo=True)])
    return out


LOOSE_ROW = re.compile(rf"([A-Z][A-Za-zÀ-ÿ0-9 ./,&'\-]{{4,45}}?)\s*"
                       rf"(?:\([A-Za-zÀ-ÿ][^)]{{0,28}}\))*\s*(?:{wp.FN}|\d{{1,2}})?(?:\s*{wp.FN})*"
                       rf"\s+([\d,]{{6,}})\s*(?:(?:{wp.FN}|[—–-])\s*)*(\d{{1,3}}(?:\.\d+)?)\s*%?(?=\s)")


MULTICOL = re.compile(r"([A-Z][A-Za-zÀ-ÿ0-9 .,&'()-]{4,45}?)\s*(?:\((\d+)\))?\s+"
                      r"([\d,]{5,})\s+(?:[\d,]{5,}|[—–-])\s+([\d,]{5,})\s+"
                      r"([\d.]+)\s*%\s+[\d.]+\s*%")


def multicol_holders(text, gm, os_m):
    """Foreign 20-F 'shares | options | total | own% | vote%' principal-shareholders layout
    (BNR) that holders() can't read (3 numbers + 2 percents per row). Capture each holder's
    ex-options SHARES (col 1 = the O/S basis DT excludes), in the FILING's basis (caller
    rescales by f). Returns [] unless >=2 such rows are found, so single-column tables are
    untouched."""
    rows = []
    for m in MULTICOL.finditer(text[gm.end():gm.end() + 2500]):
        nm = strip_head(m.group(1).strip())
        sh, pct = int(m.group(3).replace(",", "")), float(m.group(5))
        if nm and not wp.BAD.search(nm) and 0 < pct <= 100:
            rows.append([nm[:24], sh / 1e6, pct,
                         dict(do=False, gt20=(pct > 20), affil=False, shell=False,
                              g13=bool(IDX.search(nm)), deemed=False)])
    return rows if len(rows) >= 2 else []


def major_holders(text, os_m, foreign):
    """Holders from a separate principal/major-shareholders table (often far from the
    D&O group row, outside the group-region scan -- EM's Taobao, JFIN's Sunshinewoods)."""
    from types import SimpleNamespace
    best, bestn = None, 0
    for h in wp.OWN_HDR.finditer(text):
        n = len(list(wp.HOLDER.finditer(text, h.end(), h.end() + 2800)))
        if n > bestn:
            best, bestn = h, n
    if best:
        p = best.end()
        gm = SimpleNamespace(start=lambda p=p: p, end=lambda p=p: p)
        return holders(text, gm, os_m, foreign)
    # no %-bearing table found: try a SELF-VALIDATING loose scan (no '%' sign on rows,
    # CYPH) -- accept a row only when its trailing number == shares/os*100 (+-30%), which
    # prose ("Beneficially Owned ... 123") fails, so no false matches
    for h in wp.OWN_HDR.finditer(text):
        rows = []
        zone = text[h.end():h.end() + 5000]                # footnote bodies for ex-derivative
        fnmap = {}                                         # (a) X common shares (LMNL's SALP)
        for fm in re.finditer(r"\((\d{1,2}|[a-z])\)\s+(?=[A-Z])", zone):
            fnmap.setdefault(fm.group(1), zone[fm.end():fm.end() + 300])
        for m in LOOSE_ROW.finditer(text, h.end(), h.end() + 2800):
            nm, sh, pct = strip_head(m.group(1).strip()), int(m.group(2).replace(",", "")), float(m.group(3))
            if wp.BAD.search(nm) or not nm or sh > os_m * 1e6 * 1.01 or not 0 < pct <= 100:
                continue
            imp = sh / (os_m * 1e6) * 100
            if abs(imp - pct) <= 0.30 * max(pct, 1):       # trailing number IS this row's %
                feat = dict(do=False, gt20=(pct > 20), affil=False, shell=False,
                            g13=bool(IDX.search(nm)), deemed=False)
                rows.append([nm[:24], sh / 1e6, pct, feat])
                mk = re.search(r"\((\d{1,2}|[a-z])\)", m.group(0))   # ex-derivative BASIC figure
                mb = re.search(r"(?i)\(a\)\s+([\d,]{4,})\s+(?:common|ordinary)\s+shares?",
                               fnmap.get(mk.group(1), "")) if mk else None
                if mb and 0 < (bv := int(mb.group(1).replace(",", ""))) < sh:
                    rows.append([nm[:18] + "~basic", bv / 1e6, pct, feat])
        if len(rows) >= 2:
            return rows
        if len(rows) == 1 and rows[0][2] >= 5 and \
                abs(rows[0][1] / os_m * 100 - rows[0][2]) <= 0.08 * rows[0][2]:
            return rows                # lone TIGHTLY self-validating >=5% holder (HLG: only Mr.
        #   Feng is numeric; every D&O row is "— —") -- safe: a prose number can't match its %
    return []


def ipo_offering_basis(cik, os_, asof="2026-06-04"):
    """A FRESH IPO's float = the shares actually offered to the public; DT excludes ALL
    pre-IPO holders (not just the 5%-table). Read 'initial public offering of N ordinary/
    common shares' off the final prospectus cover (MENS=Jyong 2,666,667 = its float exactly;
    excl = os - offering). float may be the offering WITH over-allotment exercised -- the
    cover also states "(or M ... shares, assuming ... over-allotment)" (WTF=Waton 5,031,250 =
    4.375M base + 15% greenshoe = its float). Returns both os-N (base) and os-M (full) bases."""
    import requests
    ft = ",".join(f'"{x}"' for x in ["424B4", "424B1", "424B3"])
    q = f"cik:{int(cik)} AND formType:({ft}) AND filedAt:[2018-01-01 TO {asof}T23:59:59]"
    body = {"query": q, "from": "0", "size": "5", "sort": [{"filedAt": {"order": "desc"}}]}
    try:
        fl = [f for f in requests.post("https://api.sec-api.io", json=body, headers=ff.HDR,
              timeout=60).json().get("filings", []) if f["formType"] in ("424B4", "424B1", "424B3")]
        if not fl:
            return []
        text = ff.fetch_text(fl[0]["linkToFilingDetails"], fl[0]["accessionNo"]).translate(wp.ZW)
    except Exception:
        return []
    m = re.search(r"(?i)initial\s+public\s+offering\s+of\s+([\d,]{6,})\s+(?:ordinary|common)\s+shares",
                  text[:8000])
    if not m:
        return []
    out, ns = [], {int(m.group(1).replace(",", ""))}
    mo = re.search(r"(?i)\(or\s+([\d,]{6,})\s+(?:ordinary|common)\s+shares,?\s+assuming[^.]{0,40}"
                   r"over-?allot", text)  # offering WITH over-allotment exercised (WTF greenshoe,
    #   stated in the "Shares offered by us" summary deep in the doc, not the cover)
    if mo:
        ns.add(int(mo.group(1).replace(",", "")))
    for n in ns:
        v = os_ - n / 1e6
        if 0 < v < os_:
            out.append(("osOffering", v))
    return out


def redeemable_shares(text):
    """SPAC public shares 'subject to possible redemption' (the float; DT excludes the
    rest). Returns candidate redeemable counts. float ~ redeemable -> excl ~ os-redeemable."""
    out = set()
    for m in re.finditer(r"(?:excluding\s+)?([\d,]{6,})\s+(?:and\s+nil\s+)?"
                         r"(?:Class\s+[A-Z]\s+)?(?:ordinary\s+|common\s+)?shares?"
                         r"[A-Za-z ,]{0,25}?subject to possible redemption", text, re.I):
        out.add(int(m.group(1).replace(",", "")))
    for m in re.finditer(r"subject to possible redemption[^.]{0,40}?([\d,]{6,})\s+shares", text, re.I):
        out.add(int(m.group(1).replace(",", "")))
    return out


def pipe_blocks(cik, os_, asof="2026-06-04"):
    """A large PRIVATE-PLACEMENT / PIPE block issued AFTER the latest proxy/20-F (6-K/8-K
    'issuance and sale of N units/shares' under a securities purchase agreement) -- a
    >20%-of-O/S block DT excludes that the ownership table predates (TOP=214,431,222-unit
    PIPE to non-U.S. investors). Returns candidate counts (absolute, in millions)."""
    import requests
    body = {"query": f'cik:{int(cik)} AND formType:("6-K" OR "8-K") AND '
                     f'filedAt:[2024-01-01 TO {asof}T23:59:59]',
            "from": 0, "size": 15, "sort": [{"filedAt": {"order": "desc"}}]}
    try:
        fl = requests.post("https://api.sec-api.io", json=body, headers=ff.HDR,
                           timeout=60).json().get("filings", [])
    except Exception:
        return []
    out = set()
    for fobj in fl[:8]:
        try:
            text = ff.fetch_text(fobj["linkToFilingDetails"], fobj["accessionNo"]).translate(wp.ZW)
        except Exception:
            continue
        out |= set(pipe_in_text(text, os_))
    return [v for v in out]


PIPE_TXT = re.compile(r"(?i)(?:issued|issue|sold|sell|sale|issuance(?:\s+and\s+sale)?)\s+"
                      r"(?:of\s+)?(?:up\s+to\s+)?(?:an?\s+aggregate\s+of\s+)?([\d,]{7,})\s+"
                      r"(?:units|(?:Class\s+[A-Z]\s+)?ordinary\s+shares|shares)")


def pipe_in_text(text, os_):
    """Large PIPE/private-placement issuance stated IN a filing's text ('issued N Class A
    Ordinary Shares', 'sell up to an aggregate of N units') -- a >20%-of-O/S block DT
    excludes (CCHH's 18,000,000-share SPA to non-U.S. investors, in its 20-F). Returns counts
    (absolute, in millions). Used on already-fetched text (no extra request)."""
    out = set()
    for m in PIPE_TXT.finditer(text):
        n = int(m.group(1).replace(",", ""))
        if 0.20 * os_ * 1e6 < n <= os_ * 1e6 * 1.01:
            out.add(n / 1e6)
    return list(out)


def thirteen_dg_candidates(cik, os_m, asof="2026-06-04"):
    """Each DISTINCT 13D/13G block per holder ACROSS amendments (aggregateAmountOwned) as
    candidates -- DT may use an OLDER block (OBAS = Capri's older 13D 4.097M, not its
    current 5.039M). 13D->activist (excludable), 13G->passive (tag g13). Raw sums are
    unreliable (E§6); add each distinct historical block and let the solver pick."""
    import requests
    body = {"query": f"filers.cik:{int(cik)} AND filedAt:[2015-01-01 TO {asof}T23:59:59]",
            "from": 0, "size": 50, "sort": [{"filedAt": {"order": "desc"}}]}
    try:
        j = requests.post("https://api.sec-api.io/form-13d-13g", headers=ff.HDR,
                          json=body, timeout=90).json()
    except Exception:
        return []
    blocks = {}                  # nm -> {rounded_shares: is13g}  (distinct across amendments)
    for fobj in j.get("filings") or []:
        names = [x.get("name", "") for x in (fobj.get("filers") or [])
                 if "Subject" not in (x.get("name") or "")]
        nm = names[0] if names else "?"
        is13g = "13G" in (fobj.get("formType") or "").upper()
        for o in (fobj.get("owners") or []):
            a = o.get("aggregateAmountOwned")
            if isinstance(a, (int, float)) and a > 0:
                blocks.setdefault(nm, {}).setdefault(round(a / 1e3), (a, is13g))
    out = []
    for nm, amap in blocks.items():
        for _, (sh, is13g) in amap.items():
            if 0 < sh <= os_m * 1e6 * 1.01:
                out.append([nm[:24], sh / 1e6, sh / (os_m * 1e6) * 100,
                            dict(do=False, gt20=(sh > 0.20 * os_m * 1e6), affil=not is13g,
                                 shell=False, g13=is13g, deemed=False)])
    return out


def form4_candidates(cik, os_m, asof="2026-06-04"):
    """Latest Form 3/4 holding per insider (sharesOwnedFollowingTransaction / holdings) as
    candidates -- catches a control person's block the proxy 5%-table omits. Raw sums are
    unreliable (E6); add each owner's single latest holding and let the solver pick."""
    import requests
    try:
        j = requests.post("https://api.sec-api.io/insider-trading", headers=ff.HDR,
                          json={"query": f"issuer.cik:{int(cik)}", "from": 0, "size": 50},
                          timeout=90).json()
    except Exception:
        return []
    recs = sorted((j.get("transactions") or j.get("data") or []),
                  key=lambda f: f.get("filedAt") or "", reverse=True)   # latest first (no API sort)
    latest = {}
    for f in recs:
        if (f.get("filedAt") or "")[:10] > asof:           # cap <= 6/4 in code
            continue
        nm = (f.get("reportingOwner") or {}).get("name") or f.get("reportingOwnerName") or "?"
        if nm in latest:
            continue
        rel = (f.get("reportingOwner") or {}).get("relationship") or {}
        is_do = bool(rel.get("isDirector") or rel.get("isOfficer"))
        amts = []
        for tbl in ("nonDerivativeTable", "derivativeTable"):
            for tr in ((f.get(tbl) or {}).get("transactions") or []) + \
                      ((f.get(tbl) or {}).get("holdings") or []):
                v = (tr.get("postTransactionAmounts") or {}).get("sharesOwnedFollowingTransaction")
                if v is not None:
                    amts.append(v if isinstance(v, (int, float)) else (v or {}).get("value"))
        amts = [a for a in amts if isinstance(a, (int, float))]
        if amts:
            latest[nm] = (max(amts), is_do)
    out, do_sum = [], 0.0
    for nm, (sh, is_do) in latest.items():
        if is_do:
            do_sum += sh / 1e6
        if 0 < sh <= os_m * 1e6 * 1.01:
            out.append([nm[:24], sh / 1e6, sh / (os_m * 1e6) * 100,
                        dict(do=False, gt20=(sh > 0.20 * os_m * 1e6), affil=True,
                             shell=False, g13=False, deemed=False)])
    return out, do_sum             # do_sum = D&O actual (ex-options) holdings -> a group basis


def latest_periodic(cik, asof="2026-06-04"):
    """Most recent 10-K/20-F/10-Q <= 6/4 (for redeemable / cover-page numbers the latest
    PROXY lacks -- AMCI's redeemable count is in its 10-Q, not its DEF 14A)."""
    import requests
    for forms in (["10-K", "10-K/A", "20-F", "20-F/A"], ["10-Q"]):
        ft = ",".join(f'"{x}"' for x in forms)
        q = f"cik:{int(cik)} AND formType:({ft}) AND filedAt:[2022-01-01 TO {asof}T23:59:59]"
        body = {"query": q, "from": "0", "size": "1", "sort": [{"filedAt": {"order": "desc"}}]}
        try:
            r = requests.post("https://api.sec-api.io", json=body, headers=ff.HDR, timeout=60)
            fl = [f for f in r.json().get("filings", []) if f["formType"] in forms]
        except Exception:
            fl = []
        if fl:
            return fl[0]
    return None


def supplementary_bases(cik, os_):
    """Extra group-basis candidates from the latest periodic filing: SPAC redeemable
    float (excl = os - redeemable)."""
    fil = latest_periodic(cik)
    if not fil:
        return []
    try:
        text = ff.fetch_text(fil["linkToFilingDetails"], fil["accessionNo"]).translate(wp.ZW)
    except Exception:
        return []
    out = []
    for r in redeemable_shares(text):
        v = os_ - r / 1e6
        if 0 < v < os_:
            out.append(("osRedeemX", v))
    return out


def group_numbers(text, gm):
    """Raw per-class share counts in the group row (filing basis) -- lets the solver try
    a single LISTED class as the group basis (GRAN: DT excludes only Class A, not the sum)."""
    raw = text[gm.end():gm.end() + 260]
    w = re.search(r"[A-Za-z]{4,}", raw)
    tail = raw[:w.start()] if w else raw
    nums = []
    for mt in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(%?)", tail):
        v = mt.group(1).replace(",", "")
        if mt.group(2) != "%" and v.isdigit() and int(v) >= 1000:
            nums.append(int(v))
    return nums


STATED_BASIS = re.compile(r"(?i)(?:on\s+the\s+basis\s+of|on\s+there\s+being|based\s+on)\s+"
                          r"([\d,]{7,})\s+(?:ordinary|common)\s+shares?\s*(?:\(being|out|iss)")
# US dual-class proxies phrase it differently: "based on N shares of Class A Common Stock
# and M shares of Class C Common Stock" -- the basis is the SUM (SST=System1 75.18M+18.70M
# pre-1:10-split vs 9.94M O/S). Capture up to 3 class counts.
CLASS_BASIS = re.compile(r"(?i)(?:on\s+the\s+basis\s+of|based\s+on)\s+([\d,]{7,})\s+shares?\s+"
                         r"of\s+(?:our\s+)?(?:Class\s+[A-Z]\s+)?common\s+stock"
                         r"(?:\s+and\s+([\d,]{6,})\s+shares?\s+of\s+(?:our\s+)?(?:Class\s+[A-Z]\s+)?"
                         r"common\s+stock)?(?:\s+and\s+([\d,]{6,})\s+shares?\s+of\s+(?:our\s+)?"
                         r"(?:Class\s+[A-Z]\s+)?common\s+stock)?")


def stated_basis_factor(text, os_):
    """A 20-F/proxy table states '...calculated on the basis of N ordinary shares
    outstanding'. When that explicit percentage basis N is far ABOVE DT's O/S, the table's
    share counts are in N's basis, not DT's: ADS-denominated names (ITMR 491.6M ordinary vs
    16.4M ADS O/S, ~30:1) or a pre-reverse-split table. Return (factor=os/N, N) so the
    holder rows are capped/parsed in N's basis then rescaled to DT's. (1.0, None) if N/os<3."""
    m = STATED_BASIS.search(text)
    b = int(m.group(1).replace(",", "")) if m else 0
    if not b:
        mc = CLASS_BASIS.search(text)                 # dual-class "N shares of Class A ... and M"
        if mc:
            b = sum(int(g.replace(",", "")) for g in mc.groups() if g)
    if b and b / (os_ * 1e6) >= 3:
        return os_ * 1e6 / b, b
    return 1.0, None


def basis_factor(text, os_, ge):
    """Rescale factor: filing share-counts -> DT O/S basis (reverse split / ADS)."""
    if not ge:
        return 1.0
    iosb = ge[3]
    if iosb and os_ * 1e6 / iosb <= 0.77 and iosb <= os_ * 1e6 * 25:
        return os_ * 1e6 / iosb
    if iosb and (rat := os_ * 1e6 / iosb) >= 3:
        r = wp.ads_ratio(text)
        if r and r < 1 and abs(rat * r - 1) <= 0.4:
            return rat
    return 1.0


def score(combo, cand):
    """Lower = better formula: prefer fewer holders, and holders that LOOK excludable."""
    s = len(combo) * 0.5
    for i in combo:
        f = cand[i][3]
        if not (f["gt20"] or f["affil"] or f["shell"]):
            s += 1.0           # an untagged inclusion is "unexplained" -> less plausible
        if f["g13"]:
            s += 1.5           # 13G/index are normally KEPT -> excluding one is suspicious
    return s


def solve(excl, gopts, cand, tol):
    """Best (group, holder-subset) fit to excl. Returns (best, ambiguous, n_within_tol).
    best minimizes err, then prefers group=exo, then the explained/minimal subset."""
    vals = [c[1] for c in cand]      # caller pre-sorts cand by size so the >17 cap keeps the
    if len(vals) > 17:               # largest (a big control block must survive -- CYPH)
        vals = vals[:17]; cand = cand[:17]

    # (F07/F37) one holder can appear as several candidate rows (13D/13G amendment blocks, a Form-4
    # holding, the '~basic' ex-warrant variant). The solver may CHOOSE which single block to use, but
    # must NEVER SUM two rows of the SAME holder. Key each candidate by its name tokens (stripping the
    # '~basic' and '(Filed by ...)' suffixes) and skip any combo that selects a duplicate identity.
    def _idkey(c):
        nm = re.sub(r"~basic$", "", c[0])
        nm = re.sub(r"\s*\(filed by.*", "", nm, flags=re.I)
        return frozenset(wp._caps(nm))
    keys = [_idkey(c) for c in cand]

    def _dup(combo):
        seen = set()
        for i in combo:
            kk = keys[i]
            if kk:
                if kk in seen:
                    return True
                seen.add(kk)
        return False

    all_sols, within = [], []
    for gi, (gname, g) in enumerate(gopts):
        for k in range(0, len(vals) + 1):
            for combo in itertools.combinations(range(len(vals)), k):
                if _dup(combo):
                    continue                         # never sum two rows of the same holder
                err = abs(g + sum(vals[i] for i in combo) - excl)
                all_sols.append((err, gi, gname, combo))
                if err <= tol:
                    within.append((err, gi, gname, combo))
    pool = within or all_sols
    pool.sort(key=lambda x: (round(x[0], 3), x[1] != 0, score(x[3], cand), len(x[3])))
    best = pool[0]
    bset = set(best[3])
    # ambiguous only if a DIFFERENT holder-set fits about as exactly (not just within the
    # loose tol) -- avoids a coincidental looser subset demoting a clean group-only solve
    amb = any(set(s[3]) != bset and s[0] <= best[0] + 0.03 for s in within[1:]) \
        if within else False
    return best, amb, len(within)


def resolve_cik_relaxed(t):
    """sec-api mapping with a one-suffix tolerance: DT's ticker may now carry a Q
    (bankruptcy) / W (warrant) / F (foreign) suffix for the SAME company (TWNP->TWNPQ,
    PITA->PITAW, ETAO->ETAOF). Accept a hit whose ticker == t or t+<one suffix char>,
    only if the resolved CIK is unique (KA -> AKA/AKAM/AKAN are different cos -> skip)."""
    import requests
    try:
        r = requests.get(f"https://api.sec-api.io/mapping/ticker/{t}?token={ff.KEY}", timeout=20)
        hits = r.json() if r.ok else []
    except Exception:
        return None
    ciks = set()
    for h in hits:
        ht, c = (h.get("ticker") or "").upper(), h.get("cik")
        if c and (ht == t.upper() or ht[:-1] == t.upper()):
            ciks.add(str(c).lstrip("0"))
    return ciks.pop() if len(ciks) == 1 else None


def ticker_match_ciks(t):
    """All CIKs whose CURRENT sec-api ticker == t or t+<one suffix char> (same logic as
    resolve_cik_relaxed but returns the whole set, for the stale-mapping guard)."""
    import requests
    try:
        r = requests.get(f"https://api.sec-api.io/mapping/ticker/{t}?token={ff.KEY}", timeout=20)
        hits = r.json() if r.ok else []
    except Exception:
        return set()
    return {str(h["cik"]).lstrip("0") for h in hits
            if h.get("cik") and (h.get("ticker") or "").upper() in (t.upper(), )
            or (h.get("cik") and (h.get("ticker") or "").upper()[:-1] == t.upper())}


def older_ownership_text(cik, asof="2026-06-04"):
    """Most recent proxy/20-F/10-K back to 2014 (latest_ownership_filing's 2022 floor
    misses a DEREGISTERED foreign name's last 20-F -- HLG). Per the stale rule that older
    filing is still SEC-derived; parse its major-shareholders/group."""
    import requests
    for forms in ap.OWN_FORMS:
        ft = ",".join(f'"{x}"' for x in forms)
        q = f"cik:{int(cik)} AND formType:({ft}) AND filedAt:[2014-01-01 TO {asof}T23:59:59]"
        body = {"query": q, "from": "0", "size": "1", "sort": [{"filedAt": {"order": "desc"}}]}
        try:
            fl = [f for f in requests.post("https://api.sec-api.io", json=body, headers=ff.HDR,
                  timeout=60).json().get("filings", []) if f["formType"] in forms]
        except Exception:
            fl = []
        if fl:
            try:
                return ff.fetch_text(fl[0]["linkToFilingDetails"], fl[0]["accessionNo"]).translate(wp.ZW)
            except Exception:
                return None
    return None


def solve_from_sources(t, cik, os_, excl, text, fallback):
    """Solve a ticker with NO usable as-a-group row (no-proxy / parse-fail) from the other
    SEC sources: the filing's major-shareholders table (if text given) + IPO prospectus
    + 13D/13G blocks + SPAC redeemable + an OLDER ownership filing's register. group
    basis = none/supplementary/redeemable."""
    if text is None:
        text = older_ownership_text(cik)              # deregistered foreign: older 20-F
    f4, f4do = form4_candidates(cik, os_)
    cand = (major_holders(text, os_, False) if text else []) + \
        prospectus_candidates(cik, os_) + thirteen_dg_candidates(cik, os_) + f4
    seen, dedup = set(), []
    for c in cand:                                    # value-dedup across sources
        if round(c[1], 2) not in seen:
            seen.add(round(c[1], 2)); dedup.append(c)
    cand = dedup
    if not cand:
        return dict(t=t, status=fallback, excl=round(excl, 3))
    tol = max(0.05, min(0.015 * abs(excl), 0.025 * abs(os_ - excl)))  # cap by 2.5% of
    #   float so a small-excl/large-float 'clean' must also reproduce DT's FLOAT closely (TOP)
    gopts = [("none", 0.0)] + [(l, v) for l, v in supplementary_bases(cik, os_)]
    if 0 < f4do <= os_ * 1.02:
        gopts.append(("f4do", f4do))         # D&O actual (ex-options) holdings as the group
    if text:
        for r in redeemable_shares(text):
            gopts.append(("osRedeem", os_ - r / 1e6))
    cand = sorted(cand, key=lambda c: -c[1])
    (err, gi, gname, combo), amb, nsol = solve(excl, gopts, cand, tol)
    st = "clean" if err <= tol and not amb else ("weak" if err <= tol
         else "near" if err <= max(0.30, 0.15 * abs(excl)) else "no-fit")
    ff2 = lambda d: "".join(c for c, k in [(">", "gt20"), ("A", "affil"), ("S", "shell"),
                            ("G", "g13"), ("P", "preipo")] if d.get(k)) or "-"
    return dict(t=t, form="sources", excl=round(excl, 3), os=os_, status=st,
                err=round(err, 4), group=gname, gval=round(gopts[gi][1], 3), nholders=len(cand),
                resid=round(excl - (gopts[gi][1] + sum(cand[i][1] for i in combo)), 3),
                formula=[dict(name=cand[i][0], sh=round(cand[i][1], 3), pct=cand[i][2],
                              feat=ff2(cand[i][3])) for i in combo])


# Tickers sec-api's mapping CANNOT resolve (substring search returns noise, the one-suffix
# relaxer misses a 2+-char suffix change): the company's CIK + all data are 100% SEC/EDGAR,
# only the ticker->CIK bridge is supplied (which DT has internally). KA = Kineta Inc (now
# trades as "KANT" -- a 2-char suffix; /mapping/ticker/KA never returns it).
ALIAS = {"KA": "1445283"}


def recover(t):
    cik = cm.cik_of(t) or resolve_cik_relaxed(t) or ALIAS.get(t.upper())
    if not cik:
        return dict(t=t, status="no-cik")
    rec = _recover(t, cik)
    if rec.get("status") in ("no-fit", "parse-fail", "no-proxy"):  # primary CIK didn't fit: the
        for alt in ticker_match_ciks(t) - {str(cik)}:  # SAPI cache may have mapped a homonym
            alt_rec = _recover(t, alt)                  # (AMBI->Ambit not Ambipar; XONE->a
            if alt_rec.get("err", 9e9) < rec.get("err", 9e9):  # BondBloxx ETF not ExOne) -> try
                rec = alt_rec                          # every same-ticker CIK, keep the BEST fit.
    #   Gated on the primary FAILING + the alt fitting BETTER (different company = different
    #   shares, can't reproduce DT's exact excl by chance) -> a name that fits on its own
    #   primary (HLG/OBAS/ETAO, even if delisted) is never touched.
    return rec


def _recover(t, cik):
    fl, os_ = ap.DT[t]; excl = os_ - fl
    fil = ap.latest_ownership_filing(cik)
    if not fil:
        return solve_from_sources(t, cik, os_, excl, None, "no-proxy")
    form = fil["formType"]
    text = ff.fetch_text(fil["linkToFilingDetails"], fil["accessionNo"]).translate(wp.ZW)
    gm = wp.GROUP2.search(text)
    anchored = not gm
    if anchored:                              # no as-a-group row: anchor at the ownership
        gm = wp.table_anchor(text)            # header (D&O-section rows become the group)
        if not gm:                            # no parseable group at all: solve from the
            return solve_from_sources(t, cik, os_, excl, text, "parse-fail")  # other sources
        ge, f, g_exo, g_ben = None, 1.0, 0.0, 0.0
    else:
        ge = wp.group_exoptions(text, os_)
        f = basis_factor(text, os_, ge)
        g_exo = (ge[0] if ge else 0.0) * f
        g_ben = (ge[1] if ge else 0.0) * f
    sb_f, _ = stated_basis_factor(text, os_)            # ADS / pre-split table basis (ITMR/HLG)
    os_cap = os_                                         # only the EXPLICIT "...basis of N shares"
    if f == 1.0 and sb_f != 1.0:                         # signal widens the cap to the table's
        f, os_cap = sb_f, os_ / sb_f                     # basis (Feng's 360M ord row passes, THEN
    #   rescaled by f to 22.5M ADS = HLG's excl). basis_factor's heuristic f (LITB) is NOT
    #   trusted to widen the cap -- doing so admitted spurious ordinary rows that broke its group.
    hrows = holders(text, gm, os_cap, form == "20-F")
    for r in hrows:
        r[1] *= f
    gmax = max(g_exo, g_ben, 0.01)                      # a D&O-section row BIGGER than the
    cand = [r for r in hrows if (not r[3]["do"] and not r[3]["deemed"])   # whole group total
            or (r[3]["do"] and not r[3]["deemed"] and r[1] > gmax * 1.1)]  # can't be inside it
    # (F36) a big D&O row kept as a standalone candidate above must NOT also be summed into the 'dno'
    # group basis, or selecting group='dno' + that candidate double-counts the holder. Exclude the
    # big-standalone do-rows from dno_sum so each holder is counted by exactly one leg.
    dno_sum = sum(r[1] for r in hrows
                  if r[3]["do"] and not (not r[3]["deemed"] and r[1] > gmax * 1.1))
    mh = major_holders(text, os_cap, form == "20-F")    # separate major-shareholders table
    if form == "20-F":                                  # foreign shares|options|total|own%|vote%
        mh += multicol_holders(text, gm, os_)           # layout holders() can't read (BNR's VCs)
    for r in mh:
        r[1] *= f
    ex0 = {round(c[1], 2) for c in cand} | {round(g_exo, 2), round(g_ben, 2)}
    cand += [r for r in mh if not r[3]["do"] and round(r[1], 2) not in ex0]
    tol = max(0.05, min(0.015 * abs(excl), 0.025 * abs(os_ - excl)))  # cap by 2.5% of
    #   float so a small-excl/large-float 'clean' must also reproduce DT's FLOAT closely (TOP)
    gopts = [("exo", g_exo), ("ben", g_ben), ("none", 0.0)]
    seen = {round(g_exo, 3), round(g_ben, 3), 0.0}
    gnums = group_numbers(text, gm) if not anchored else []
    for label, v in [("dno", dno_sum)] + [(f"cls{i}", n / 1e6 * f) for i, n in enumerate(gnums)]:
        if round(v, 3) not in seen and 0 < v <= os_ * 1.02:
            gopts.append((label, v)); seen.add(round(v, 3))
    mc_abs = sum(n for n in gnums if n <= os_ * 1e6) / 1e6   # multi-class group at ABSOLUTE
    if len([n for n in gnums if n <= os_ * 1e6]) >= 2 and round(mc_abs, 3) not in seen \
            and 0 < mc_abs <= os_ * 1.02:                   # counts (drop an as-converted/voting
        gopts.append(("mcAbs", mc_abs)); seen.add(round(mc_abs, 3))   # column > O/S): TOP's
    #   Class A 20.068M + Class B 10M = 30.068M, NOT rescaled (the 520M voting col is excluded)
    i7 = wp.item7_holders(text, os_) if form == "20-F" else None
    if i7 is not None and round(i7, 3) not in seen:     # 20-F whole-register exclusion
        gopts.append(("item7", i7))
    for r in redeemable_shares(text):                   # SPAC: excl = os - redeemable float
        v = os_ - r / 1e6
        if 0 < v < os_ and round(v, 3) not in seen:
            gopts.append(("osRedeem", v)); seen.add(round(v, 3))
    cand = sorted(cand, key=lambda c: -c[1])     # largest first so the >17 cap keeps big blocks
    (err, gi, gname, combo), amb, nsol = solve(excl, gopts, cand, tol)
    near_thr = max(0.30, 0.10 * abs(excl))
    used_preipo = False
    if err > tol:                                     # not EXACT -> widen SEC sources (incl.
        #   the f4do ex-options group / Form-4 holdings, which can tighten a precision "near")
        gopts2, cand2 = gopts, cand
        xtra = supplementary_bases(cik, os_)
        if fl < 0.30 * os_:                  # tiny float => fresh-IPO / controlled signature:
            xtra += ipo_offering_basis(cik, os_)   # float = IPO offering (MENS). Gated so the
        for label, v in xtra:                      # extra prospectus fetch is only for these.
            if round(v, 3) not in seen:                   # latest 10-K/10-Q SPAC redeemable
                gopts2 = gopts2 + [(label, v)]; seen.add(round(v, 3))
        # add holder sources whenever the fit is poor -- in EITHER direction (an
        # over-fit may need a smaller/older block, e.g. OBAS group=none + Capri's older 13D)
        ex = {round(c[1], 2) for c in cand}
        pc = prospectus_candidates(cik, os_)
        if f != 1.0:                       # ADS/reverse-split: the prospectus shares are in
            pc = [[p[0], p[1] * f, p[2], p[3]] for p in pc]   # the same basis -> rescale (SYT)
        if excl > 0.80 * os_:              # VERY heavily-excluded (controlled / PIPE-diluted): a
            for p in set(pipe_in_text(text, os_)) | set(pipe_blocks(cik, os_)):  # big private
                pc.append([f"PIPE {p:.1f}M", p, p / os_ * 100,   # placement DT excludes -- in the
                           dict(do=False, gt20=True, affil=True, shell=False, g13=False, deemed=False)])
        #   filing text itself (CCHH's 18M SPA) or a post-proxy 6-K (TOP's 214.4M) -- ABSOLUTE, no f
        extra = [p for p in pc if round(p[1], 2) not in ex]
        ex |= {round(p[1], 2) for p in extra}
        f4, f4do = form4_candidates(cik, os_)
        for src in (thirteen_dg_candidates(cik, os_), f4):
            extra += [p for p in src if round(p[1], 2) not in ex]
            ex |= {round(p[1], 2) for p in extra}
        if 0 < f4do <= os_ * 1.02 and round(f4do, 3) not in seen:   # D&O ex-options group
            gopts2 = gopts2 + [("f4do", f4do)]; seen.add(round(f4do, 3))
        cand2 = sorted(cand + extra, key=lambda c: -c[1])
        if len(gopts2) > len(gopts) or len(cand2) > len(cand):
            b2 = solve(excl, gopts2, cand2, tol)
            if b2[0][0] < err - 0.01:
                cand, gopts = cand2, gopts2
                (err, gi, gname, combo), amb, nsol = b2
                used_preipo = any(cand[i][3].get("preipo") for i in combo)
    rec = dict(t=t, form=form, excl=round(excl, 3), os=os_, factor=round(f, 3),
               g_exo=round(g_exo, 3), g_ben=round(g_ben, 3), nholders=len(cand),
               preipo=used_preipo)
    # an "unexplained" inclusion = a holder DT normally KEEPS (no >20%/affil/shell tag,
    # or a 13G/index) -- needing it to hit the sum means the fit is coincidental, not DT's
    unexpl = any(not (cand[i][3]["gt20"] or cand[i][3]["affil"] or cand[i][3]["shell"])
                 or cand[i][3]["g13"] for i in combo)
    # group-ONLY solves (no holders) -> residual is pure group-parse precision (wider band);
    # also float-relative: the user's metric is "close to DT's float", so a residual within
    # ~4% of FLOAT counts as near even if large vs a tiny excl (TBI 0.73M = 2.5% of float)
    nearlim = max(0.30, (0.20 if not combo else 0.10) * abs(excl), 0.04 * abs(os_ - excl))
    if err <= tol and not unexpl and not amb:
        rec["status"] = "clean"
    elif err <= tol:
        rec["status"] = "weak"               # fits, but via untagged/13G holders or ambiguous
    elif err <= nearlim:
        rec["status"] = "near"               # group-anchored: structure recovered, the
        #   residual is group-parse precision (options/RSU/rounding), not a missing holder
    else:
        rec["status"] = "no-fit"             # big residual: activist / prospectus / parse / stale
    rec["err"] = round(err, 4)
    rec["resid"] = round(excl - (gopts[gi][1] + sum(cand[i][1] for i in combo)), 3)
    rec["group"] = gname
    rec["gval"] = round(gopts[gi][1], 3)
    fstr = lambda d: "".join(c for c, k in [(">", "gt20"), ("A", "affil"), ("S", "shell"),
                             ("G", "g13"), ("P", "preipo")] if d.get(k)) or "-"
    rec["formula"] = [dict(name=cand[i][0], sh=round(cand[i][1], 3), pct=cand[i][2],
                           feat=fstr(cand[i][3])) for i in combo]
    rec["kept"] = [dict(name=c[0], sh=round(c[1], 3), pct=c[2], feat=fstr(c[3]))
                   for j, c in enumerate(cand) if j not in set(combo)]
    return rec


if __name__ == "__main__":
    names = sys.argv[1:] or wp.insample()
    db, counts = [], {}
    for t in names:
        if t not in ap.DT:
            continue
        try:
            r = recover(t)
        except Exception as e:
            r = dict(t=t, status=f"ERR:{str(e)[:40]}")
        db.append(r)
        counts[r["status"].split(":")[0]] = counts.get(r["status"].split(":")[0], 0) + 1
        if r["status"] in ("clean", "weak", "near", "no-fit"):
            g = f"{r['group']}={r.get('gval',0):.2f}" if r["group"] != "none" else "none"
            print(f"{r['t']:6} {r['status']:6} excl{r['excl']:8.2f} = group[{g}] "
                  f"+ {len(r['formula'])}h err{r['err']:.3f} resid{r['resid']:+.2f}  IN:" +
                  " ".join(f"{h['name'][:9]}({h['pct']:.0f}%{h['feat']})" for h in r["formula"][:5]))
        else:
            print(f"{r['t']:6} {r['status'][:18]:18} excl{r.get('excl',0):8.2f} nh={r.get('nholders','-')}")
    json.dump(db, open("_formula_db.json", "w"), indent=0)
    N = len(db)
    print(f"\n=== PHASE-1 COVERAGE (N={N}) ===")
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4} {c}  ({n/N*100:.0f}%)")
    clean = counts.get("clean", 0)
    ff2 = clean + counts.get("weak", 0) + counts.get("near", 0)
    print(f"  --> CLEAN formula: {clean}/{N} = {clean/N*100:.1f}%   "
          f"any formula (clean+weak+near): {ff2}/{N} = {ff2/N*100:.1f}%")
    # the user's metric: |fest - DT float| / DT float -- "close to DT's number"
    for thr in (1, 3, 5):
        n = sum(1 for r in db if "err" in r and r.get("os") and
                abs(r["err"]) <= thr / 100 * max(r["os"] - r["excl"], 0.01))
        print(f"  float reproduced within {thr}% of DT: {n}/{N} = {n/N*100:.1f}%")
