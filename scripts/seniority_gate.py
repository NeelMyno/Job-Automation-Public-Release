#!/usr/bin/env python3
"""
seniority_gate.py -- the years-of-experience gate.

THE ROOT CAUSE THIS CLOSES
--------------------------
Seniority exclusion tends to start as a one-time MANUAL human review: someone sweeps the open
applications and hand-flags the ones asking for more years than they actually have. A manual
review is a snapshot. It cannot catch a JD that gets built AFTER it runs, and nothing else in a
typical pipeline checks a JD's stated years requirement against the candidate's own years. So a
role requiring, say, 8+ years for someone with 5 gets tailored, reviewed, and handed over exactly
like any other role, because nothing mechanical ever compared the two numbers. A rule that lives
only as a one-time human pass, not a gate that runs on every dossier forever, rots the moment new
work is built past it. This script makes the comparison mechanical.

THE RULE
--------
If an UNSUBMITTED job's JD requires materially more years of experience than you actually have,
it gets flagged, never silently filled and handed over.

  DROP   : required-years floor > your configured years of experience.
  REVIEW : floor equals your own years with a range ceiling well above it, OR a Staff/Principal/
           Lead/Head/Director/Architect title with no explicit years bar, OR the only floor above
           yours is stated as "preferred/nice-to-have". Surfaced to you, never auto-acted.
  PASS   : floor at or below your own years, and not a senior-plus title with a high ceiling.

Only the ROLE'S REQUIREMENT counts. Your OWN tenure (e.g. "~5 years", "5 years total across three
jobs") must never read as a requirement, so a bare "N years" is suppressed on any line carrying a
tenure/annotation marker, and the primary signal is requirement-shaped phrasing only ("N+ years",
"at least N years", "N-M years").

CONFIGURATION (optional -- see scripts/config.py)
--------------------------------------------------
Set `YOUR_YEARS_OF_EXPERIENCE = <a number>` in scripts/config.py to enable this gate for your own
setup. Left unset (the default), the gate is a documented no-op: it never crashes and never fires
a false DROP, it just has nothing to compare a JD against yet. This mirrors every other optional
value in config.py (see that file's own docstring).

USAGE
-----
  seniority_gate.py --selftest                 # must stay green (built from real defect shapes)
  seniority_gate.py <dossier_dir>              # one dossier, verbose evidence
  seniority_gate.py --all                      # every applications/* dossier (a table)
  seniority_gate.py --all --unsubmitted        # only not-yet-applied dossiers (the action list)
  seniority_gate.py --all --unsubmitted --drops-only   # just the DROP folder paths, one per line

EXIT: 0 = no UNSUBMITTED drop found (or the gate is unconfigured). 1 = at least one unsubmitted
DROP (the thing to fix).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPS = REPO / "applications"
TRACKER = REPO / "pipeline" / "tracker.html"

# scripts/config.py is optional (see that file's own docstring); this gate stays a safe no-op if
# it has never been created, or if it exists but has never had YOUR_YEARS_OF_EXPERIENCE added to
# it -- hence getattr with a None default rather than a bare attribute access either way.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import config
except ImportError:
    class config:  # type: ignore[no-redef]
        """Fallback when scripts/config.py has not been created yet: safe defaults only."""
        OPERATOR_NAME = None
        YOUR_YEARS_OF_EXPERIENCE = None

YEARS_OF_EXPERIENCE = getattr(config, "YOUR_YEARS_OF_EXPERIENCE", None)
# DROP_FLOOR is the first year-count that counts as "materially more than you have". None means
# "not configured yet" -- every function below degrades gracefully rather than guessing a number
# that would be true for nobody in particular.
DROP_FLOOR: int | None = (YEARS_OF_EXPERIENCE + 1) if isinstance(YEARS_OF_EXPERIENCE, (int, float)) else None
# How far above your own years a range's CEILING has to reach before a "floor matches you exactly"
# line is worth a human REVIEW rather than an automatic PASS (a JD stating "5-8 years" when you
# have 5 is a different animal from one stating "5-6 years").
CEILING_SPREAD_FOR_REVIEW = 3

SENIOR_TITLES = ("staff", "principal", "lead ", "head of", "director", "architect", "sr. staff", "senior staff")

# EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (verify_claims.py's own fixture, and the blank
# starter copy-from), never a real application. A years-of-experience sweep must skip these or it
# reports noise on a fresh clone for work nobody ever intended to submit.
SCAFFOLD_DOSSIER_PREFIXES = ("EXAMPLE-", "TEMPLATE-")


def is_scaffold_dossier(folder_name: str) -> bool:
    return folder_name.startswith(SCAFFOLD_DOSSIER_PREFIXES)


# A "years" mention that is really about cadence/tenure/other, not an experience requirement.
NON_REQUIREMENT = ("per year", "times a year", "times per year", "/year", "a year to", "year-over-year",
                   "years ago", "last year", "next year", "this year", "each year", "years old")
PREFERRED = ("preferred", "nice to have", "nice-to-have", "bonus", "a plus", "ideally", "would be great", "not required")

NUM_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}

# 'years','year','yrs','yr' are the SAME requirement. A regex that only matches 'years?' misses a
# JD that writes its bar as "8+ yrs" -- it registers no floor at all and silently passes, which is
# exactly the class of miss this gate exists to catch. `_MORE` adds "8 or more"/"8 plus" to the
# "+" sign so "six or more years" is a floor too.
YR = r"(?:years?|yrs?)"
_MORE = r"(?:\+|\s*or\s+more|\s*or\s+greater|\s*plus)"
# A real, scraped JD range ("5-8 years") sometimes carries an en dash or em dash instead of a
# plain hyphen, copied over from whatever word processor or ATS formatted it. Built via chr()
# rather than typed literally, so no such character sits in this file's own source.
_EN_DASH = chr(0x2013)
_EM_DASH = chr(0x2014)
_RANGE_SEP = r"(?:-|" + _EN_DASH + r"|" + _EM_DASH + r"|to)"
_DASH_CLASS = r"\-" + _EN_DASH + _EM_DASH


def _tenure_markers() -> tuple[str, ...]:
    """Phrases that mean 'this line is talking about YOUR OWN tenure or this repo's own notes
    about you', never a role requirement, even though it contains a number followed by 'years'.
    Kept deliberately narrow: broad words that show up in real JDs ('resume', 'candidate has',
    'reach') are NOT markers here, because suppressing a real '>=N years' requirement is the exact
    failure this gate exists to prevent. Extend this list with your own past employer names (in
    scripts/config.py, or directly below) if your own dossier notes keep tripping the gate."""
    markers = ["knowledge-base", "kb-", "the senior gap", "honest reach", "years total"]
    name = getattr(config, "OPERATOR_NAME", None)
    if name:
        markers.append(name.lower())
    if YEARS_OF_EXPERIENCE is not None:
        markers.append(f"~{YEARS_OF_EXPERIENCE}")
        markers.append(f"~ {YEARS_OF_EXPERIENCE}")
    return tuple(markers)


def _mentions(line: str):
    """Yield (needed_floor, ceiling_or_None, is_preferred) for each experience-requirement
    mention in one line. Requirement-shaped phrasings only; tenure/cadence lines suppressed."""
    l = line.lower()
    if any(m in l for m in NON_REQUIREMENT):
        # The line is about cadence/age/ago -- but it could still hold a real "N+ years"
        # elsewhere. Only bail if it has no requirement-shaped token at all.
        if not re.search(r"\d\s*\+\s*" + YR + r"|\b" + YR + r"\s+of\b"
                         r"|\d\s*" + _RANGE_SEP + r"\s*\d\s*" + YR + r"|at least|minimum", l):
            return
    if any(m in l for m in _tenure_markers()):
        return  # your own tenure, or this repo's own notes about you -- never a role requirement
    if not re.search(r"\byears?\b|\byrs?\b", l):
        return
    pref = any(p in l for p in PREFERRED)

    # Range: "5-8 years", "6 to 9 yrs"  -> floor = first, ceiling = second
    for m in re.finditer(r"(\d{1,2})\s*" + _RANGE_SEP + r"\s*(\d{1,2})\s*\+?\s*" + YR, l):
        yield (int(m.group(1)), int(m.group(2)), pref)
    # "N+ years" / "N or more years" / "N plus years"  -> floor N (drop the sign)
    for m in re.finditer(r"(\d{1,2})\s*" + _MORE + r"\s*" + YR, l):
        yield (int(m.group(1)), None, pref)
    # "at least / minimum (of) N years"
    for m in re.finditer(r"(?:at least|minimum(?:\s+of)?|min\.?)\s*(\d{1,2})\s*\+?\s*" + YR, l):
        yield (int(m.group(1)), None, pref)
    # spelled: "eight+ years", "six or more years", "eight years of experience"
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}(?:\s*\+|\s+or\s+more|\s+or\s+greater|\s+plus)?\s*{YR}", l):
            yield (n, None, pref)
    # bare "N years of experience / of product design" -- allowed ONLY on a clean line
    # (tenure markers already excluded above); still require an experience anchor.
    if re.search(r"\b" + YR + r"\s+of\s+(?:experience|product|design|professional|industry|relevant|engineering)", l) \
            or re.search(r"\b" + YR + r"\s+(?:designing|building|shipping|leading|of\s+experience)", l):
        for m in re.finditer(r"(?<![\d." + _DASH_CLASS + r"])(\d{1,2})\s+" + YR + r"\b", l):
            # skip if this same number was already a "+"/range/at-least/"or more" match (handled above)
            if re.search(rf"{m.group(1)}\s*(?:\+|" + _DASH_CLASS + r"|to|or\s+more)", l):
                continue
            yield (int(m.group(1)), None, pref)


def analyze_jd(text: str):
    """Return dict: floor, ceiling, preferred_only, evidence (list of (floor, line))."""
    req = []          # non-preferred mentions
    pref_only = []    # preferred mentions
    evidence = []
    for raw in re.split(r"[\n]", text):
        line = raw.strip()
        if not line:
            continue
        for floor, ceil, is_pref in _mentions(line):
            if floor is None:
                continue
            (pref_only if is_pref else req).append((floor, ceil))
            evidence.append((floor, ceil, is_pref, re.sub(r"\s+", " ", line)[:180]))
    floor = max((f for f, _ in req), default=None)
    ceiling = None
    # capture the ceiling associated with the binding floor, if any
    for f, c in req:
        if f == floor and c is not None:
            ceiling = max(ceiling or 0, c)
    pref_floor = max((f for f, _ in pref_only), default=None)
    return {"floor": floor, "ceiling": ceiling, "pref_floor": pref_floor, "evidence": evidence}


def title_of(dossier: Path) -> str:
    readme = dossier / "README.md"
    if readme.exists():
        first = readme.read_text(errors="ignore").splitlines()
        for ln in first[:3]:
            if ln.startswith("# "):
                return ln[2:].strip()
    return dossier.name.replace("-", " ")


def is_senior_title(title: str) -> bool:
    t = title.lower()
    return any(s in t for s in SENIOR_TITLES)


def verdict_for(dossier: Path):
    """Return (verdict, bar, reason, evidence_lines). verdict is one of DROP/REVIEW/PASS/NO-JD, or
    UNCONFIGURED when YOUR_YEARS_OF_EXPERIENCE has never been set in scripts/config.py."""
    jds = sorted(dossier.glob("jd-*.md"))
    if not jds:
        return ("NO-JD", None, "no jd-*.md file in dossier", [])
    if DROP_FLOOR is None:
        return ("UNCONFIGURED", None, "YOUR_YEARS_OF_EXPERIENCE is not set in scripts/config.py", [])
    your_years = DROP_FLOOR - 1
    text = "\n".join(p.read_text(errors="ignore") for p in jds)
    a = analyze_jd(text)
    floor, ceiling, pref_floor = a["floor"], a["ceiling"], a["pref_floor"]
    title = title_of(dossier)
    senior = is_senior_title(title)
    ev = [e for e in a["evidence"] if e[0] >= DROP_FLOOR] or a["evidence"][:2]

    if floor is not None and floor >= DROP_FLOOR:
        return ("DROP", floor, f"JD requires {floor}+ years (you have {your_years})", ev)
    if floor == your_years and ceiling and ceiling >= your_years + CEILING_SPREAD_FOR_REVIEW:
        return ("REVIEW", your_years, f"JD says {your_years}-{ceiling} years -- floor matches you but ceiling reaches senior", ev)
    if pref_floor and pref_floor >= DROP_FLOOR and (floor is None or floor < DROP_FLOOR):
        return ("REVIEW", pref_floor, f"{pref_floor}+ years is 'preferred', floor is {floor if floor is not None else 'unstated'}", ev)
    if senior and (floor is None or floor <= your_years):
        title_tail = title.split(":")[-1].strip()[:40]
        return ("REVIEW", floor, f"'{title_tail}' is a senior-plus title, years bar {floor if floor is not None else 'unstated'}", ev)
    return ("PASS", floor, f"floor {floor if floor is not None else 'unstated'} <= {your_years}", ev)


# ---------- tracker parse (brace-balanced, quote-aware) ----------
def folder_status_map() -> dict[str, str]:
    if not TRACKER.exists():
        return {}
    html = TRACKER.read_text(errors="ignore")
    out: dict[str, str] = {}
    i = 0
    n = len(html)
    while i < n:
        if html[i] == "{":
            depth, j, instr, q = 0, i, False, ""
            while j < n:
                c = html[j]
                if instr:
                    if c == q and html[j - 1] != "\\":
                        instr = False
                elif c in "\"'":
                    instr, q = True, c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            obj = html[i:j + 1]
            fo = re.search(r'folder:"([^"]*)"', obj)
            st = re.search(r'status:"([^"]*)"', obj)
            if fo and st:
                out[fo.group(1).strip().rstrip("/")] = st.group(1).strip()
            i = j + 1
        else:
            i += 1
    return out


# A dossier is "handled" (no longer an OPEN drop) if it was submitted OR you already dropped it:
# tracker status "passed", or a DROP_BANNER prepended to its README. Without "passed" here the gate
# would re-flag every already-dropped role forever.
HANDLED_STATUSES = {"applied", "interview", "offer", "rejected", "passed"}
DROP_BANNER = "DROPPED: seniority gate"


def is_handled(dossier: Path, fmap: dict[str, str]) -> bool:
    rel = f"applications/{dossier.name}"
    st = fmap.get(rel) or fmap.get(rel + "/")
    if st in HANDLED_STATUSES:
        return True
    rdme = dossier / "README.md"
    if rdme.exists() and DROP_BANNER in rdme.read_text(errors="ignore")[:800]:
        return True
    app = dossier / "application.md"
    if app.exists():
        head = app.read_text(errors="ignore")[:1200]
        # Matches this repo's own established "was this actually sent" convention
        # (see throughput.py's SUBMITTED detector): the word SUBMITTED, or a checkmark.
        if re.search(r"\bSUBMITTED\b|✅", head, re.I):
            return True
    return False


# ------------------------------- selftest -------------------------------
def selftest() -> int:
    print("seniority_gate.py selftest\n")
    ok = True

    def check(desc, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        mark = "✓" if good else "✗"
        print(f"  {mark} {desc}: got {got!r} want {want!r}")

    # A JD stating an explicit high floor -- this is why the gate exists.
    senior_jd = "- 8+ years of product design experience, with a proven track record of shipping complex products from concept to launch. We care more about staff-level impact than years on a resume"
    a = analyze_jd(senior_jd)
    check("'8+ years of product design experience' -> floor 8", a["floor"], 8)

    # A role the fictional candidate genuinely fits -- must PASS.
    check("'5+ years of product design experience' -> floor 5", analyze_jd("5+ years of product design experience")["floor"], 5)

    # Cadence line must NOT register as a requirement.
    check("'travel up to six times per year' -> no floor",
          analyze_jd("Ability to travel up to six times per year for team meetings")["floor"], None)

    # A candidate's own tenure, stated inside a dossier note, must NEVER read as a requirement.
    check("'Jordan has ~5 years total across three jobs' -> no floor",
          analyze_jd("Jordan has ~5 years total across three jobs")["floor"], None)

    # Requirement variants.
    check("'at least 7 years' -> floor 7", analyze_jd("We want at least 7 years of experience")["floor"], 7)
    check("'6-9 years' -> floor 6", analyze_jd("6-9 years of experience designing product")["floor"], 6)
    check("'10+ years' -> floor 10", analyze_jd("10+ years of experience")["floor"], 10)
    check("'3+ years' -> floor 3", analyze_jd("3+ years of experience in product design")["floor"], 3)

    # The abbreviation / 'or more' / spelled forms that a naive `years?`-only regex would miss.
    # A JD writing its bar as "8+ yrs" must still register a floor, never silently pass.
    check("'8+ yrs of product design experience' -> floor 8 (abbreviation form)",
          analyze_jd("8+ yrs of product design experience")["floor"], 8)
    check("'6+ yrs product design' -> floor 6", analyze_jd("6+ yrs product design")["floor"], 6)
    check("'six or more years of experience' -> floor 6",
          analyze_jd("We want six or more years of experience")["floor"], 6)
    check("'Minimum 7 yrs of experience' -> floor 7", analyze_jd("Minimum 7 yrs of experience")["floor"], 7)
    check("'at least 8 yrs designing product' -> floor 8", analyze_jd("at least 8 yrs designing product")["floor"], 8)
    # and the abbreviation still PASSES a role the candidate fits.
    check("'5+ yrs of product design' -> floor 5 (candidate fits)", analyze_jd("5+ yrs of product design")["floor"], 5)

    # End-to-end verdicts on synthetic dossiers, with a fixed fictional configuration: the test
    # candidate has 5 years, so DROP_FLOOR is 6 -- independent of whatever a real user's own
    # scripts/config.py says (or doesn't say).
    global DROP_FLOOR
    saved_drop_floor = DROP_FLOOR
    DROP_FLOOR = 6
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-staff-product-designer"
            d.mkdir()
            (d / "README.md").write_text("# Acme Corp: Staff Product Designer\n")
            (d / "jd-acme.md").write_text(senior_jd)
            v = verdict_for(d)
            check("senior-shaped dossier -> DROP", v[0], "DROP")

            d2 = Path(td) / "beta-senior-product-designer"
            d2.mkdir()
            (d2 / "README.md").write_text("# Beta Inc: Senior Product Designer\n")
            (d2 / "jd-beta.md").write_text("5+ years of product design experience in B2B SaaS")
            check("5+ senior dossier -> PASS", verdict_for(d2)[0], "PASS")

            d3 = Path(td) / "gamma-staff-designer"
            d3.mkdir()
            (d3 / "README.md").write_text("# Gamma Corp: Staff Product Designer\n")
            (d3 / "jd-gamma.md").write_text("We value impact over tenure. Strong portfolio required.")
            check("Staff title, no years stated -> REVIEW", verdict_for(d3)[0], "REVIEW")

            # End-to-end: a JD that states its bar ONLY as "8+ yrs" must still DROP.
            d4 = Path(td) / "delta-staff-product-designer"
            d4.mkdir()
            (d4 / "README.md").write_text("# Delta LLC: Staff Product Designer\n")
            (d4 / "jd-delta.md").write_text("You have 8+ yrs of product design experience shipping at scale.")
            check("a JD stating its bar only as '8+ yrs' -> DROP (abbreviation form)", verdict_for(d4)[0], "DROP")
    finally:
        DROP_FLOOR = saved_drop_floor

    # Unconfigured mode: with YOUR_YEARS_OF_EXPERIENCE never set, the gate must degrade to a
    # documented no-op rather than crash or guess a number.
    saved_drop_floor = DROP_FLOOR
    DROP_FLOOR = None
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-unconfigured"
            d.mkdir()
            (d / "jd-acme.md").write_text(senior_jd)
            check("unconfigured gate -> UNCONFIGURED, never a crash or a guess", verdict_for(d)[0], "UNCONFIGURED")
    finally:
        DROP_FLOOR = saved_drop_floor

    print("\nSELFTEST OK" if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


# ------------------------------- runners -------------------------------
def _warn_unconfigured() -> None:
    print("seniority_gate: YOUR_YEARS_OF_EXPERIENCE is not set in scripts/config.py.")
    print("This gate has nothing to compare a JD's stated years requirement against, so it is")
    print("skipped (not a failure). Add e.g. `YOUR_YEARS_OF_EXPERIENCE = 5` to scripts/config.py")
    print("to enable it for your own setup.")


def run_all(only_unsubmitted: bool, drops_only: bool) -> int:
    if DROP_FLOOR is None:
        if not drops_only:
            _warn_unconfigured()
        return 0
    fmap = folder_status_map()
    rows = []
    for d in sorted(APPS.iterdir()):
        if not d.is_dir() or is_scaffold_dossier(d.name):
            continue
        verdict, bar, reason, ev = verdict_for(d)
        if verdict in ("PASS", "NO-JD", "UNCONFIGURED"):
            continue
        handled = is_handled(d, fmap)
        if only_unsubmitted and handled:
            continue
        rows.append((d.name, verdict, bar, handled, reason, ev))

    drops = [r for r in rows if r[1] == "DROP"]
    reviews = [r for r in rows if r[1] == "REVIEW"]

    if drops_only:
        for name, verdict, bar, handled, reason, ev in drops:
            print(f"applications/{name}")
        return 1 if any(not r[3] for r in drops) else 0

    print(f"seniority_gate -- {'actionable (unhandled) only' if only_unsubmitted else 'all dossiers'}\n")
    print(f"\U0001F534 DROP (JD requires {DROP_FLOOR}+ years, you have {DROP_FLOOR - 1}): {len(drops)}")
    for name, verdict, bar, handled, reason, ev in sorted(drops, key=lambda r: (-(r[2] or 0), r[0])):
        tag = "  [already handled]" if handled else ""
        print(f"  {bar}+ yr  applications/{name}{tag}")
        if ev:
            print(f"           └─ {ev[0][3]}")
    print(f"\n\U0001F7E1 REVIEW (surface to you, not auto-dropped): {len(reviews)}")
    for name, verdict, bar, handled, reason, ev in sorted(reviews, key=lambda r: r[0]):
        tag = "  [handled]" if handled else ""
        print(f"  applications/{name}{tag} -- {reason}")

    open_drops = [r for r in drops if not r[3]]
    print(f"\n=> {len(open_drops)} UNHANDLED dossier(s) still to drop (senior-reach + not yet passed/submitted).")
    return 1 if open_drops else 0


def run_one(path: str) -> int:
    d = Path(path)
    if not d.is_absolute():
        d = REPO / path
    if not d.is_dir():
        print(f"not a dossier dir: {path}")
        return 2
    verdict, bar, reason, ev = verdict_for(d)
    if verdict == "UNCONFIGURED":
        _warn_unconfigured()
        return 0
    fmap = folder_status_map()
    handled = is_handled(d, fmap)
    icon = {"DROP": "\U0001F534", "REVIEW": "\U0001F7E1", "PASS": "\U0001F7E2", "NO-JD": "⚪"}.get(verdict, "?")
    print(f"{icon} {verdict}  --  {d.name}")
    print(f"   title   : {title_of(d)}")
    print(f"   reason  : {reason}")
    print(f"   handled : {handled} (submitted or already dropped/passed)")
    if ev:
        print("   evidence :")
        for floor, ceil, is_pref, line in ev[:4]:
            print(f"     - [{floor}{'+' if ceil is None else f'-{ceil}'}{' pref' if is_pref else ''}] {line}")
    return 0 if verdict in ("PASS", "NO-JD") or handled else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    if "--all" in args:
        sys.exit(run_all("--unsubmitted" in args, "--drops-only" in args))
    positional = [a for a in args if not a.startswith("--")]
    if positional:
        sys.exit(run_one(positional[0]))
    print(__doc__)
    sys.exit(2)
