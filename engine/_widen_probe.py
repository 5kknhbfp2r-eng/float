"""Widen + measure. Run (group ex-options) + (outside_holders: >20% + footnote-affiliates,
section-aware, value-deduped, reverse-split rescaled) over a sample, classify each name's
residual, report the error distribution (incl survivor/delisted split). Proxy-date basis, no
Form 4 rollforward (most proxies are Apr-2026 vs the Jun-2026 scrape -> small drift).

Hardened group matcher GROUP2 fixes the brittleness found while widening:
  & (ampersand), "(N people)", ", nominees,", and NO "(N persons)" count at all
  (anchored instead by a REQUIRED trailing share number, which also skips the prose
  'officers and directors as a group.' sentence), plus zero-width chars (U+200B).
Throwaway probe."""
import re, sys, random
from types import SimpleNamespace
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import float_from_filings as ff
import _affil_probe as ap
import _cik_probe as cikmap

DT = ap.DT
ZW = dict.fromkeys(map(ord, "​‌‍﻿"), None)

OFFS = (r"(?:current\s+)?(?:named\s+)?(?:executive\s+)?officers|NEOs?"
        r"|senior\s+management|corporate\s+auditors")
DIRS = (r"(?:current\s+)?(?:non-employee\s+|independent\s+|named\s+)?directors|trustees"
        r"|board\s+members|members\s+of\s+(?:our|the)\s+board(?:\s+of\s+directors)?")
MIDP = (r"(?:\s*\([^)]{0,40}\))?"                       # "(including independent directors)"
        r"(?:\s*,?\s*(?:director\s+)?(?:nominees?|appointees?))?")
NAME = (rf"(?:(?:{OFFS}){MIDP}\s*,?\s*(?:and|&|/)\s*(?:our\s+)?(?:the\s+)?(?:all\s+)?(?:{DIRS})"
        rf"|(?:{DIRS}){MIDP}\s*,?\s*(?:and|&|/)\s*(?:our\s+)?(?:the\s+)?(?:all\s+)?(?:{OFFS}))")
NPER = r"\(\s*(?:\d+|[a-z]+(?:-[a-z]+)?)\s*(?:persons?|people|individuals?)\s*\)"  # (6)/(eleven)
EXTRA = (r"(?:\s*,?\s*and\s+(?:certain\s+)?(?:former\s+|other\s+)?(?:executive\s+)?"
         r"(?:officers?|employees?))?")    # JANX "and certain former executive officers";
GROUP2 = re.compile(                       # CVV "and executive employees"
    r"(?:(?:all\s+)?(?:of\s+)?(?:our\s+)?(?:the\s+)?(?:compan(?:y'?s?)\s+)?(?:current\s+)?" + NAME +
    rf"(?:\s+of\s+(?:the\s+)?[A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*){{0,2}})?{EXTRA}"   # "of the Company"
    rf"\s*(?:{NPER})?\s*(?:and\s+the\s+sponsor\s*)?(?:,?\s+as\s+a\s+group|\s+combined)\s*(?:{NPER})?"
    rf"|total\s+(?:of\s+)?(?:all\s+)?(?:current\s+)?{NAME}\s*{NPER}"   # "Total Directors and
    r"|total,?\s+as\s+a\s+group)"          # Executive Officers (13 persons)" (MDXG); (WKEY)
    r"(?:\s*\((?:\d+|[a-z])\))*"
    r"(?:\s+(?:common|class\s+[a-z0-9]+|ordinary)\s+(?:stock|shares?))?"  # "Common Stock N" (TBI)
    r"(?=[\s:)]*(?:[—–-]\s*%?\s*)*[\d,]{4,}"                # 2nd alt, nil rows: lone dash (IOR),
    r"|[\s:)]*(?:(?:[—–-]|0(?:\.0+)?)\s*%?\s*){1,}"         # zeros "- 0.0 %" (PMI); 3rd alt: the
    r"|[\s:)]*(?:(?:5|five)\s*(?:%|percent)|principal|major))", re.I)   # next section header
                                                            # directly follows (STAK)
OPT = re.compile(r"([\d,]{4,})\s+(?:vested\s+|additional\s+|stock\s+)*(?:options|option)\b", re.I)
OPT2 = re.compile(r"([\d,]{4,})\s+shares?\s+(?:of\s+common\s+stock\s+)?"
                  r"(?:issuable|underlying|subject to|that may be acquired|purchasable)", re.I)
GROUP_RS = re.compile(r"as\s+a\s+group[,:]?\s+([\d,]{4,})\s+shares", re.I)  # unvested-RS summary (OSUR)


def group_exoptions(text, os_m):
    """(ex_options_M, beneficial_M, confidence, implied_os). US single-class: 1-col beneficial
    minus footnote options, or explicit 3-col ex-options. Foreign multi-class: sum the group's
    share counts across ALL classes (Class A + Class B + ...), detected by a % appearing
    between the first two share-count columns (vs US 3-col which is num num num %).
    implied_os = the proxy's own O/S basis, from shares/pct of the group row -- lets the
    caller detect (and rescale for) reverse splits between the proxy and the DT snapshot."""
    m = GROUP2.search(text)
    if not m:
        return None
    raw = text[m.end():m.end() + 260]
    w = re.search(r"[A-Za-z]{4,}", raw)               # the group's numeric row ends where words resume
    tail = raw[:w.start()] if w else raw
    toks = []                                         # ordered ('n', share_count) / ('p', pct)
    for mt in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(%?)", tail):
        v = mt.group(1).replace(",", "")
        if mt.group(2) == "%":
            toks.append(("p", float(v)))
        elif v.isdigit() and int(v) >= 1000:
            toks.append(("n", int(v)))
    nums = [v for ty, v in toks if ty == "n"]
    if not nums:
        if re.match(r"[\s:)]*(?:(?:[—–-]|0(?:\.0+)?)\s*%?\s*){1,}", raw) or \
                re.match(r"(?i)[\s:)]*(?:(?:5|five)\s*(?:%|percent)|principal|major)", raw):
            return 0.0, 0.0, "nil-group", None        # D&O hold nothing (MASK/CCHH foreign);
        return None                                   # exclusion comes from the holders leg
    ni = [i for i, (ty, _) in enumerate(toks) if ty == "n"]
    if len(nums) >= 3 and any(toks[j][0] == "p" for j in range(ni[0] + 1, ni[1])) \
            and abs(nums[-1] - sum(nums[:-1])) <= 0.015 * nums[-1]:
        toks = toks[:ni[-1]]          # multi-class row with a trailing TOTAL column (SEI:
        ni, nums = ni[:-1], nums[:-1]                 # 2.79M + 12.07M + 14.87M) -- drop it
    pairs = []                                        # each share count with ITS following pct
    for j, i0 in enumerate(ni):
        nxt = ni[j + 1] if j + 1 < len(ni) else len(toks)
        ps = [toks[k][1] for k in range(i0 + 1, nxt) if toks[k][0] == "p" and toks[k][1] > 0]
        pairs.append((toks[i0][1], ps[0] if ps else None))
    multiclass = len(ni) >= 2 and any(toks[j][0] == "p" for j in range(ni[0] + 1, ni[1]))
    if multiclass:
        if len(set(nums)) == 1:                       # same block under several % bases (MENS)
            s = nums[0]
            iosb = s / pairs[0][1] * 100 if pairs[0][1] else None
        else:
            s = sum(nums)
            if all(p for _, p in pairs):
                bases = [n / p * 100 for n, p in pairs]
                # per-class %s (DSP: bases differ -> sum) vs %-of-total on every class
                # (ABLV: bases agree -> that IS the total; summing would double-count)
                iosb = bases[0] if max(bases) / min(bases) < 1.25 else sum(bases)
            else:
                iosb = None
        lim = max(os_m * 1e6, iosb if iosb and iosb <= os_m * 1e6 * 25 else 0) * 1.02
        return s / 1e6, s / 1e6, ("misparse>OS" if s > lim else "multiclass"), iosb
    benef = nums[-1]
    iosb = benef / pairs[-1][1] * 100 if pairs[-1][1] else None
    if benef > max(os_m * 1e6, iosb if iosb and iosb <= os_m * 1e6 * 25 else 0) * 1.02:
        return benef / 1e6, benef / 1e6, "misparse>OS", iosb   # group can't exceed O/S basis
    if len(nums) >= 3:
        return nums[0] / 1e6, benef / 1e6, "3col", iosb   # explicit ex-options column
    sec = re.sub(r"(?i)excludes?\b.*?(?:\.\s|$)", " ", text[m.start():m.start() + 4000])
    opts = sum(int(x.replace(",", "")) for x in OPT.findall(sec)) + \
           sum(int(x.replace(",", "")) for x in OPT2.findall(sec))
    grs = GROUP_RS.search(sec)
    if grs:
        opts = max(opts, int(grs.group(1).replace(",", "")))
    opts = min(opts, benef)
    return (benef - opts) / 1e6, benef / 1e6, ("1col-deriv" if opts > 0 else "1col-noderiv?"), iosb


FN = r"\((?:\d{1,2}|[a-z])\)"          # footnote ref: (7) or (d); LWAY uses letters
HOLDER = re.compile(rf"([A-Z][A-Za-zÀ-ÿ0-9 ./,&'\-]{{4,45}}?)"
                    rf"(?:\s*\([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .,&'\-]{{2,28}}\))*"   # "(Limited
                    rf"\s*(?:{FN}|\d{{1,2}})?(?:\s*{FN})*"   # Partnership)", "(Grupo Crédito)"
                    rf"\s+(?:[—–-]\s+%?\s*){{0,4}}([\d,]{{6,}})\s*"   # interstitial nil multi-class
                    rf"(?:(?:{FN}|[—–-])\s*)*(\d{{1,3}}(?:\.\d+)?)\s*%")   # columns (LGCL '3,920,000 — 9.2 %')
BAD = re.compile(r"(?i)plan|total|dilution|as\s+a\s+group|outstanding|aggregate|award|reserved"
                 r"|\bothers?\b")    # "Other Shareholders" = the float itself (AENZ)
# NB: not \bgroup\b -- foreign entity holders are often "... Group Ltd." (SELX Clariscope)
OWN_HDR = re.compile(
    r"(?i)security ownership|(?:name\s+(?:and address\s+)?of\s+)?beneficial owner|"
    r"principal (?:stock|share)holders|major shareholders|"
    r"5\s*%\s+(?:or\s+(?:more|greater)\s+)?(?:beneficial\s+)?(?:stock|share)?holders")
AFTER_GROUP = 3500           # 5%-holder sections often CONTINUE past the group row (RBBN, DSP)
FN_ZONE = 9000               # footnotes live within this span after the group row
FN_END = re.compile(r"(?i)related part|certain relationships|item\s+\d")  # past-the-footnotes guard
AFFIL = re.compile(          # holder's principal is a director/officer OF THE COMPANY
    r"(?i)member of (?:our|the company'?s?) board"
    r"|member of the board of directors of the (?:company|registrant)"
    r"|(?:chairman|chair) of (?:our|the company'?s?) board"
    r"|director of the (?:company|registrant)")
SEC_DO = re.compile(         # table-section markers: rows under D&O are inside the group
    rf"(?i)(?:{NAME})\s*:?|\bNEOs\b")     # total; reuse GROUP2's officer/director synonym
                                          # classes (SYT: "Named Directors, and Corporate
                                          # Auditors" was unmatched -> CEO row got excluded)
SEC_5P = re.compile(          # the (?!...and Schedules) guards a common boilerplate prose
    r"(?i)(?:5|five)\s*(?:%|percent)\s*(?:or\s+(?:greater|more)|stock|share|bene|hold|own)"
    r"|greater\s+than\s+5\s*%"   # ("...supplied by officers, directors and principal
    r"|principal\s+(?:stock|share)holders(?!\s+and\s+Schedules?\b)"   # stockholders and
    r"|major\s+(?:stock|share)holders?(?!\s+and\s+Schedules?\b)")     # Schedules 13D/13G") (ZYXI)
STOPW = {"the", "and", "our", "ltd", "limited", "inc", "incorporated", "co", "corp",
         "corporation", "company", "holdings", "holding", "group", "capital", "management",
         "partners", "partnership", "investment", "investments", "fund", "funds", "trust",
         "international", "technology", "ventures", "global", "mr", "mrs", "ms", "dr",
         # ownership-table vocabulary (D&O-section tokens are mined as person names)
         "ordinary", "shares", "share", "common", "class", "stock", "beneficial", "owner",
         "owned", "ownership", "percentage", "percent", "number", "name", "address",
         "officers", "officer", "directors", "director", "executive", "executives", "named",
         "senior", "auditors", "chairman", "chief", "president", "secretary", "treasurer",
         "vice", "total", "less", "than", "board", "members", "member", "all", "each",
         "person", "persons", "five", "holders", "voting", "power",
         "greater", "shareholders", "stockholders", "principal", "major", "more",
         "sec", "llc", "llp", "lp", "plc", "bvi", "prc", "ads", "adr", "usa", "us", "uk"}


def _caps(s):                    # proper-name tokens only: prose words ("sole", "unless")
    return {w.lower() for w in   # poison person-name matching (ABLV fn6 "sole owner")
            re.findall(r"\b[A-Z][a-z]{2,}\b|\b[A-Z]{2,}\b", s)} - STOPW   # "SY Co." = 2 caps


def _tokmatch(a, b):
    """Name-identity between two cap-token sets, judged on the INTERSECTION: TRUE only on >=2 shared
    tokens, or a single shared token of length>=6 (a distinctive surname). So a coincidental common
    surname (Wang/Li/Zhang) is NOT identity. (Unlike det_float._nmatch this does NOT treat subset as a
    match, because in the F21 call site one operand is the WHOLE D&O subsection's token set.)"""
    sh = a & b
    return len(sh) >= 2 or (len(sh) == 1 and len(next(iter(sh))) >= 6)


def outside_holders(text, gm, os_m, foreign=False):
    """Strategic-holder exclusion (DT doc: '>20% shareholders' + 'affiliates of the company').
    Scans the ownership table BOTH sides of the group row (5%-holder sections often follow it),
    skipping rows in the Directors-&-Officers subsection (already inside the as-a-group total).
    US: excludes a 5%-section row when (a) shares > 20% of O/S, or (b) its footnote shows a
    company director/officer behind the holder (affiliate), the block is >=1% of O/S, and no
    similar-magnitude individual row exists (else it's inside a person's row -> in the group).
    foreign (20-F): excludes EVERY major-shareholder row -- 20-F Item 6E/7A tables list
    strategic/pre-IPO blocks, not 13G institutions (GMHS and SELX sum EXACTLY to DT's
    exclusion); rows are multi-class (sum each row's distinct class counts -- equal counts =
    same block under two % bases, count once).
    Dedups by exact share value (same block attributed to fund + deemed-owner + group classes);
    a value-colliding row whose footnote names NO D&O person is a distinct holder with a
    coincidentally equal count, not a dup (GMHS: Jintou=Carmira, Ningbo=DWC).
    Returns (excluded_M, dno_rows_M) -- the latter backs the nil-group case (SAGT: group row
    is dashes while the chairman's D&O row holds 8.5M)."""
    hd = list(OWN_HDR.finditer(text, max(0, gm.start() - 6000), gm.start()))
    start = hd[0].end() if hd else max(0, gm.start() - 4000)   # FIRST header in range: the 5%
    # table can be a separate table well before the D&O one (TUSK's MAJOR STOCKHOLDERS)
    # Footnote bodies usually live AFTER the group row, but when the 5%/principal-stockholder table
    # PRECEDES the D&O group row (TUSK-style layout) its footnotes sit before gm.start() too (F20).
    # Scan the pre-group region FIRST, then the post-group zone — so a genuine post-group body still
    # WINS on a ref-label collision (preserves the 'real bodies overwrite inline row refs' semantics).
    affil_fns, fn_txt = set(), {}
    for zstart, zend in ((start, gm.start()), (gm.end(), gm.end() + FN_ZONE)):
        zone = text[zstart:zend]
        fnm = [f for f in re.finditer(r"\((\d{1,2}|[a-z])\)", zone)   # a footnote BODY starts with
               if re.match(r"\s+[A-Z]", zone[f.end():f.end() + 4])]   # a capitalized word; inline
        for i, f in enumerate(fnm):                                   # "(a)"/row refs do not, and
            # must not truncate the body before its principal's name (GMHS Funtery/Feng Xie)
            seg = zone[f.end():fnm[i + 1].start() if i + 1 < len(fnm) else f.end() + 800][:800]
            e = FN_END.search(seg)
            seg = seg[:e.start()] if e else seg
            fn_txt[f.group(1)] = seg     # refs inside table rows are overwritten by the real
            if AFFIL.search(seg):        # footnote bodies that follow them
                affil_fns.add(f.group(1))
    span = text[start:gm.end() + AFTER_GROUP]
    g0, g1 = gm.start() - start, gm.end() - start     # group row, in span coordinates
    marks = sorted([(m.start(), "5p") for m in SEC_5P.finditer(span)] +
                   [(m.start(), "do") for m in SEC_DO.finditer(span) if not (g0 <= m.start() < g1)])
    taken = set()                                     # the group row's own class/benef numbers
    graw = span[g1:g1 + 260]
    gw = re.search(r"[A-Za-z]{4,}", graw)             # group numbers end where words resume
    for n in re.findall(r"([\d,]{4,})", graw[:gw.start()] if gw else graw):
        if (v := int(n.replace(",", ""))) >= 1000:
            taken.add(v)
    gvals = set(taken)            # the group's per-class totals (containment test below)
    rows, prev_end = [], 0                            # (name, pct, fn_refs, section, counts)
    for m in HOLDER.finditer(span):
        if g0 <= m.start() < g1:
            continue
        nm, sh, pct = m.group(1).strip(), int(m.group(2).replace(",", "")), float(m.group(3))
        row = span[max(prev_end, m.start() - 200):m.end()]     # THIS row only, not predecessors
        prev_end = m.end()
        if pct > 100 or sh > os_m * 1e6 * 1.01 or BAD.search(nm):
            continue
        counts = [sh]
        if foreign:                                   # row continues across class columns
            raw = span[m.end():m.end() + 160]
            w = re.search(r"[A-Za-z]{4,}", raw)
            for n in re.findall(r"[\d,]{4,}", raw[:w.start()] if w else raw):
                v = int(n.replace(",", ""))
                if v >= 1000 and v not in counts and v <= os_m * 1e6 * 1.01:
                    counts.append(v)                  # distinct count = another class's shares
        if foreign:           # (F11) the >88% drop targets FOREIGN multi-class voting/as-converted
            counts = [c for c in counts if c <= 0.88 * os_m * 1e6]   # artifacts (EEX/TOP). For a US
            if not counts:    # single-class filer a >88% count is a REAL controlling block -> keep it
                continue      # for the >20% exclusion below; dropping it would over-state the float.
        sec = max([(p, k) for p, k in marks if p <= m.start()], default=(0, "5p"))[1]
        rows.append((nm, pct, set(re.findall(r"\((\d{1,2}|[a-z])\)", row)), sec, counts))
    allsh = [c for _, _, _, _, counts in rows for c in counts]
    dno_vals, dno_tok = set(), set()
    for p, k in marks:            # mine D&O person names from the whole D&O subsection --
        if k == "do":             # dash-only rows never match HOLDER (SELX's Dr. Chang)
            nxt = min([q for q, _ in marks if q > p] + [x for x in (g0,) if x > p] + [len(span)])
            dno_tok |= _caps(span[p:nxt])
    dno_rows = []                 # (name tokens, row total) for per-person containment
    for nm, _, _, sec, counts in rows:
        if sec == "do":           # a person's row is inside the group total; the same block
            dno_vals.update(counts)                   # often reappears as a 5%-entity row
            taken.update(counts)                      # (deemed ownership) -> never re-add
            dno_tok |= _caps(nm)
            dno_rows.append((_caps(nm), sum(counts)))
    out = 0
    for nm, pct, fns, sec, counts in rows:
        if sec == "do":
            continue
        if foreign:
            new = [c for c in counts if c not in taken]
            if not new:
                continue                              # re-attributed block (deemed ownership)
            sh_new = sum(new)
            # an affiliate ENTITY: some footnote body names BOTH this holder (every name
            # token -- one shared surname is not identity, HXHX Zhao) AND a D&O person
            # (any body -- row->note refs are off-by-one in sloppy filings, SELX)
            nmt = _caps(nm)
            bods = [b for b in fn_txt.values() if nmt and nmt <= _caps(b)]
            linked = any(_tokmatch(_caps(b), dno_tok) for b in bods)   # (F21) >=2 / long token, not any
            lp = [v for toks, v in dno_rows                   # the LINKED persons' own row
                  if any(_tokmatch(toks, _caps(b)) for b in bods)]     # totals bound what can be a
            cap = max(lp) if lp else (max(gvals) if gvals else 0)     # re-listed block
            if linked and sh_new <= cap:
                continue          # a D&O's vehicle that FITS inside the linked person's row
                                  # = re-listed deemed block (TGHL/TOP/GMM, SYT's SY Co.);
                                  # one EXCEEDING it sits outside the group (SELX Vienna,
                                  # AACG's Joingear > Jun Zhang's own row)
            spons = re.search(r"(?i)\bsponsor\b", nm) or \
                any(re.search(r"(?i)\bsponsor\b", b) for b in
                    [fn_txt.get(r, "") for r in fns] + bods)      # SPAC sponsors = affiliates
            if sh_new > 0.20 * os_m * 1e6 or pct > 20.0 or spons or \
                    (linked and sh_new >= 0.01 * os_m * 1e6):     # pct: >20% of ITS class
                out += sh_new
            continue
        sh = counts[0]
        if sh in taken:
            continue
        if sh > 0.20 * os_m * 1e6:
            out += sh; taken.add(sh)
        else:
            # (F10) a footnote makes THIS holder an affiliate only if the matched affil body actually
            # NAMES it — a generic "a director of the company ..." note attached elsewhere must not
            # exclude a passive fund. Require the holder's own name tokens to be in the affil body.
            nmt = _caps(nm)
            named_affil = nmt and any(r in affil_fns and nmt <= _caps(fn_txt.get(r, "")) for r in fns)
            if named_affil and sh >= 0.01 * os_m * 1e6 and \
                    not any(sh < o <= sh * 1.35 for o in allsh):
                out += sh; taken.add(sh)              # affiliate block NOT inside a person's row
    return out / 1e6, sum(dno_vals) / 1e6


ITEM7 = re.compile(r"(?i)major\s+shareholders|security\s+ownership|beneficial\s+ownership\s+of")

WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "fifty": 50,
         "hundred": 100, "half": 2, "third": 3, "quarter": 4, "fourth": 4, "fifth": 5,
         "eighth": 8, "tenth": 10, "twentieth": 20, "fortieth": 40, "hundredth": 100}


def _num(w):
    w = w.lower().strip()
    if w.replace(".", "").isdigit():
        return float(w)
    m = re.fullmatch(r"(?:one[ -])?one[ -](\w+?)s?", w)    # "one one-hundredth" = 1/100
    if m and m.group(1) in WORDN:
        return 1 / WORDN[m.group(1)]
    return WORDN.get(w)


def ads_ratio(text):
    """Ordinary-shares-per-ADS from the cover/Item-12 language; None if not stated.
    SYT: 'each 100 ADSs represent one common share' -> 0.01."""
    m = re.search(r"(?i)each\s+(\d+|[a-z]+)\s+ADSs?\s+represents?\s+(\d+|[a-z]+)\s+"
                  r"(?:common|ordinary)", text)
    if m and _num(m.group(1)) and _num(m.group(2)) is not None:
        return _num(m.group(2)) / _num(m.group(1))
    m = re.search(r"(?i)ADSs?\s*[,)]?\s+each\s+represent(?:s|ing)\s+(?:the\s+right\s+to\s+"
                  r"receive\s+)?((?:one[ -])?one[ -][a-z]+?s?|\d+(?:\.\d+)?|[a-z]+)\s+"
                  r"(?:of\s+one\s+)?(?:our\s+)?(?:common|ordinary|class\s+[ab])", text)
    if m:
        return _num(m.group(1))
    return None


def item7_holders(text, os_m):
    """20-F with NO as-a-group row: the exclusion IS the Item 7A/6E Major-Shareholders
    table (DT excludes every named row there -- AENZ matches exactly, incl 9-17%
    pension funds; float = the 'Other Shareholders' remainder). Returns the excluded
    FRACTION of the table's own implied O/S basis: DT's os may be in ADS units
    (AENZ 15:1) and a fraction transfers across units. None when no table parses."""
    for h in ITEM7.finditer(text):
        win = text[h.end():h.end() + 3500]
        rows, seen = [], set()
        for m in HOLDER.finditer(win):
            nm, sh, pct = m.group(1).strip(), int(m.group(2).replace(",", "")), float(m.group(3))
            if pct > 100 or BAD.search(nm) or sh in seen:   # dup value = deemed re-listing
                continue
            seen.add(sh)
            rows.append((sh, pct))
        if not rows or sum(p for _, p in rows) < 5:         # a TOC entry or prose mention,
            continue                                        # not the ownership table
        imp = sorted(sh / p * 100 for sh, p in rows if p)
        basis = imp[len(imp) // 2]                          # median implied O/S of the table
        tot = sum(sh for sh, _ in rows)
        r = os_m * 1e6 / basis
        if r >= 2:                        # a per-class sub-table (SPHL) or runaway dilution:
            continue                      # this table can't be trusted against DT's os
        if r <= 0.5:                      # DT os in AGGREGATED units: must be an integer
            n = basis / (os_m * 1e6)      # ADS ratio (AENZ 15:1), else it's a sub-table
            if abs(n - round(n)) > 0.03 * n:
                continue
            excl = tot / basis * os_m     # transfer the FRACTION
        else:                             # same units: issuance since the filing dilutes
            excl = tot / 1e6              # but holders keep absolute counts (SHMD)
        if 0.02 * os_m <= excl <= 1.02 * os_m:
            return min(excl, os_m)
    return None


def table_anchor(text):
    """Pseudo group-match at the first ownership header followed by holder rows, for
    tables with NO as-a-group row -- lets outside_holders scan them (its do-section
    machinery then sums the individual D&O rows as the group)."""
    for h in OWN_HDR.finditer(text):
        if len(list(HOLDER.finditer(text, h.end(), h.end() + 3000))) >= 1:
            p = h.end()
            return SimpleNamespace(start=lambda p=p: p, end=lambda p=p: p)
    return None


def measure(t):
    fl, os_ = DT[t]
    excl = os_ - fl
    cik = cikmap.cik_of(t)
    if not cik:
        return dict(t=t, cls="no-cik")
    fil = ap.latest_ownership_filing(cik)
    if not fil:
        return dict(t=t, cls="no-proxy")
    pdate, form = fil["filedAt"][:10], fil["formType"]
    text = ff.fetch_text(fil["linkToFilingDetails"], fil["accessionNo"]).translate(ZW)
    ge = group_exoptions(text, os_)
    strat_pre = None
    if not ge:
        i7 = item7_holders(text, os_) if form == "20-F" else None
        if i7 is not None:                            # 20-F register table: whole-table
            g_exo = benef = i7                        # exclusion (ADS-safe fraction
            conf, iosb = "item7", None                # inside; basis-sanity gated)
        else:
            gm2 = table_anchor(text)                  # table with NO as-a-group row: the
            s2, dno2 = outside_holders(text, gm2, os_, form == "20-F") if gm2 else (0.0, 0.0)
            if dno2 > 0:                              # summed D&O-section rows ARE the
                g_exo = benef = dno2                  # group (MRLN/TOPP/SST/MDXG-class)
                conf, iosb, strat_pre = "nogroup", None, s2
            elif s2 > 0:                              # no D&O rows at all, but >20%/affil
                g_exo = benef = 0.0                   # holders exist (FRTX: sole director
                conf, iosb, strat_pre = "nogroup", None, s2           # owns nothing)
            else:
                return dict(t=t, cls="parse-fail", pdate=pdate)
    else:
        g_exo, benef, conf, iosb = ge
    if conf == "misparse>OS":
        return dict(t=t, cls="multiclass?", pdate=pdate)
    basis, factor = os_, 1.0                          # proxy predates a reverse split: its share
    if iosb and os_ * 1e6 / iosb <= 0.77 and iosb <= os_ * 1e6 * 25:    # counts need rescaling
        basis, factor = iosb / 1e6, os_ * 1e6 / iosb
        conf += "+scaled"
    elif iosb and (rat := os_ * 1e6 / iosb) >= 3:     # DT os in ADS units, many per share
        r = ads_ratio(text)                           # (SYT 100:1) -- only when the stated
        if r and r < 1 and abs(rat * r - 1) <= 0.4:   # ratio CONFIRMS it's not just dilution
            basis, factor = iosb / 1e6, rat
            conf += "+ads"
    opts = (benef - g_exo) * factor
    if conf == "item7":
        strat, dno = 0.0, 0.0
    elif strat_pre is not None:
        strat, dno = strat_pre, 0.0
    else:
        strat, dno = outside_holders(text, GROUP2.search(text), basis, form == "20-F")
    if conf.startswith("nil-group") and dno > 0:      # group row is dashes but named D&O rows
        g_exo = benef = dno                           # hold shares (SAGT) -> they ARE the group
        conf = "nil-group+do"
    fest = os_ - (g_exo + strat) * factor
    if fest <= 0:                                     # exclusions exceed O/S -> a leg misparsed
        return dict(t=t, cls="strat>OS?", pdate=pdate)
    err = fest - fl
    ep = err / fl * 100 if fl else 0
    if abs(ep) <= 1.5:
        cls = "CLEAN"
    elif err > 0 and opts > 0.02 and abs(err - opts) < 0.35 * opts:
        cls = "opts-quirk?"
    elif conf.startswith("1col-noderiv?") and err > 0.5:
        cls = "lowconf-noderiv"
    elif err > 0:
        cls = "under(affil/13G?)"
    else:
        cls = "over(13D-drift/split?)"
    return dict(t=t, cls=cls, conf=conf, form=form, excl=excl, g_exo=g_exo, opts=opts,
                strat=strat, fest=fest, fl=fl, err=err, ep=ep, pdate=pdate)


def insample(n_per=30):
    """Random stratified sample over ALL DT names (by float/os), reproducible seed."""
    random.seed(42)
    buckets = {}
    for t, (fl, os_) in DT.items():
        if fl is not None and os_ and os_ > 0:
            buckets.setdefault(min(int(fl / os_ / 0.2), 4), []).append(t)
    out = []
    for b in sorted(buckets):
        lst = sorted(buckets[b]); random.shuffle(lst); out += lst[:n_per]
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or insample()
    rows, counts = [], {}
    for t in names:
        if t not in DT:
            r = dict(t=t, cls="not-in-scrape")
        else:
            try:
                r = measure(t)
            except Exception as e:
                r = dict(t=t, cls=f"ERR:{str(e)[:30]}")
        rows.append(r)
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
        if "err" in r:
            print(f"{r['t']:6} {r['cls']:22} DTexcl {r['excl']:7.3f} | g_exo {r['g_exo']:7.3f} "
                  f"opts {r['opts']:6.3f} strat {r['strat']:7.3f} | fest {r['fest']:8.3f} "
                  f"vs {r['fl']:8.3f}  err {r['err']:+7.3f} ({r['ep']:+5.1f}%) {r['pdate']}")
        else:
            print(f"{r['t']:6} {r['cls']:22} {r.get('pdate','')}")
    print("\n=== residual census ===")
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3}  {c}  ({n/len(names)*100:.0f}%)")
    N = len(names)
    parsed = [r for r in rows if "err" in r]
    foreign = sum(1 for r in rows if r.get("form") == "20-F")
    print(f"\n=== COVERAGE x ACCURACY  (N={N}) ===")
    print(f"  parsed(computed a float): {len(parsed)}/{N} = {len(parsed)/N*100:.1f}%   "
          f"foreign-20F: {foreign}/{N} = {foreign/N*100:.1f}%")
    for thr in (1.5, 3, 5, 10):
        acc = [r for r in parsed if abs(r["ep"]) <= thr]
        print(f"  |err|<={thr:>4}%: {len(acc):3}/{N} = {len(acc)/N*100:4.1f}% of ALL   "
              f"({len(acc)}/{len(parsed)} of parsed)")
    if parsed:
        import statistics
        print(f"  median |err%| on parsed: {statistics.median(sorted(abs(r['ep']) for r in parsed)):.2f}")
    print("\n=== SURVIVOR vs DELISTED (in/not-in current SEC ticker map) ===")
    for label, grp in (("survivor", [r for r in rows if r["t"] in cikmap.MAP]),
                       ("delisted", [r for r in rows if r["t"] not in cikmap.MAP])):
        p = [r for r in grp if "err" in r]
        acc = [r for r in p if abs(r["ep"]) <= 5]
        dates = sorted(r["pdate"] for r in grp if r.get("pdate"))
        med = dates[len(dates) // 2] if dates else "-"
        n = len(grp) or 1
        print(f"  {label:8} N={len(grp):3}  parsed {len(p):3} ({len(p)/n*100:4.1f}%)  "
              f"|err|<=5%: {len(acc):3} ({len(acc)/n*100:4.1f}%)  median filing date: {med}")
