#!/usr/bin/env python3
"""why_check.py: a "why do you want to join us?" answer is about THEM, never a recital of your own work.

Rule owner: knowledge-base/12-application-answers.md section 5.1a (why them) and 5.1b (why you). This gate is its teeth.

What it checks: in an application.md, the CURRENT answer to every why-them field (the last value written for that
label wins, so a later corrected block supersedes an older one) must not name your employers or projects, or recite
what you did. Your employers and projects are read at run time from your own résumé and knowledge-base/07; nothing
about any person is built in. A field that also asks about YOU ("Tell us about you and why ...", "why are you a good
fit", "why should we hire you") is not a why-them field and is not checked. Your own employer's name is allowed on
that employer's own application.

A posting that itself asks for your work inside a why box takes an explicit, greppable escape in application.md:
    <!-- why:allow <label start> | <reason> -->   (no reason, no escape)

Usage:
    python3 scripts/why_check.py applications/<dossier> [more ...]   check dossiers
    python3 scripts/why_check.py --live <dir>                         check form_answers.js output, write <dir>/REVIEW.md
    python3 scripts/why_check.py --text "<label>" <answer-file>       check one drafted answer
    python3 scripts/why_check.py --selftest
Exit 0 = checked and clean; 1 = a finding; 3 = NOT CHECKED (no why-them answer found, or your employers and projects
cannot be read yet). 3 is never a pass.
"""
import glob
import re
import sys
from pathlib import Path

from work_history_check import KB07, PLACEHOLDER, RESUME, load_form_json, load_roles

REPO = Path(__file__).resolve().parent.parent

# A field that asks why YOU want THEM.
WHY_THEM = re.compile(
    r"\bwhy\b.{0,60}\b(us|join|joining|apply|applying|work (for|at|with|here)|interested|excited|"
    r"this (company|role|team|position|job)|here)\b"
    r"|^\W*why [A-Z][\w.&' -]{1,40}\?"                # "Why Acme?" (anything may follow)
    r"|what (excites|draws|drew|attracts|interests|motivates|brings|brought) you"
    r"|gets you excited|\bresonates? with you|your interest|drew you to"
    r"|what (is it )?about .{1,40} (that )?(excites|interests|draws)"
    r"|\bmotivat\w* (you )?to (join|apply|work)",
    re.I)
# ...unless the same field also asks about you.
ABOUT_YOU = re.compile(
    r"about (you|yourself)\b|why (are you|you're|you are) (a )?(good|great|strong)? ?fit|why should we hire|"
    r"internal applicant|achievement|anything else|\bwhy you\b(?!'re| are| want| feel| wanna)|why (did|are) you leav|"
    r"right (person|fit|candidate)|(feel )?you are (a )?(good |great |strong )?fit|fit for (this|the) role|"
    r"best (person|fit|candidate)|your (experience|background|work)|what makes you",
    re.I)
# The same verbs in everyday use: "I ran into your manager", "I made a trip to your store", "I led my
# daughter's school tour". Running a relative's shop is still work, so a business word keeps the flag.
NOT_WORK = (
    r"(?!ran (?:into|across)\b|grew up\b|treated myself\b|made (?:sure|friends)\b|made up my mind\b|made my way\b"
    r"|made (?:a|the|one|my) (?:\w+ )?(?:trip|visit|stop|drive) (?:to|out|down|up|over|across|here|in|through|by)\b"
    r"|\w+ my (?:daughter|son|kids?|children|child|mother|mom|father|dad|parents?|husband|wife|grand\w+)\b"
    r"(?!(?:['\u2019]s?)? (?:store|shop|business|firm|practice|restaurant|farm|company|clinic|office|garage|bakery|salon)\b))"
)
# What a why-them answer must not carry, in any field of work. "I managed to" is not a recital.
RECITAL = re.compile(
    r"\bI " + NOT_WORK + r"(designed|built|shipped|redesigned|led|created|made|owned|managed|ran|taught|treated|installed|repaired|"
    r"sold|audited|supervised|trained|launched|implemented|developed|delivered|reduced|increased|grew|saved|"
    r"coordinated|negotiated|cut|closed)\b(?! to\b)|"
    r"\bI was the (only|sole|first|lead)\b|"
    r"\bmy (last|previous|current|former) (job|role|company|team|employer|position|school|hospital|clinic|store|firm|unit|district|shop)\b|"
    r"\bat my last\b|\bmy portfolio\b|\bmy r[eé]sum[eé]\b|\bcase stud(y|ies)\b",
    re.I)
REFERENCE = re.compile(r"prepared above|as prepared|retyped as prepared|typed as prepared|the prepared answer|same as above", re.I)
NOT_AN_ANSWER = re.compile(r"^(LEFT\b|blank\b|N/A\b|not applicable|\(blank|\[\s*\])", re.I)
LINE = re.compile(r"^\s*-\s+(.+?):(?:\s+(.*))?$")
ALLOW = re.compile(r"<!--\s*why:allow\s+(.+?)\s*\|\s*(\S.+?)\s*-->")
SUFFIX = re.compile(r"[,\s]+(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|co\.|plc|llp|lp)\s*$", re.I)


def core_name(name: str) -> str:
    name = re.sub(r"\s*\(.*?\)", "", name).strip()
    while SUFFIX.search(name):
        name = SUFFIX.sub("", name).strip()
    return name


def projects_from_html(s: str) -> list:
    return [re.sub(r"<[^>]+>", "", m).split(",")[0].strip()
            for m in re.findall(r'<li class="proj"[^>]*>\s*<b>(.*?)</b>', re.sub(r"<!--.*?-->", "", s, flags=re.S), re.S)]


def projects_from_kb(s: str) -> list:
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    m = re.search(r"^### KEY PROJECTS\s*$(.*?)(?=^#{2,3} |\Z)", s, re.S | re.M)
    return [p.strip() for p in re.findall(r"^\s*-\s+(.+?):", m.group(1), re.M)] if m else []


def own_names() -> list:
    """Your employers and projects, from your own files. [] while they are still the blank templates."""
    roles, _ = load_roles()
    names = [r["employer"] for r in roles]
    for path, reader in ((RESUME, projects_from_html), (KB07, projects_from_kb)):
        if path.exists():
            names += reader(path.read_text(errors="ignore"))
    return sorted({core_name(n) for n in names if not PLACEHOLDER.search(n) and len(core_name(n)) >= 3})


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def without_own(names, *contexts) -> list:
    """A name the application itself is about (the dossier, the question, the form's URL) is not a recital."""
    ctx = _squash(" ".join(contexts))
    return [n for n in names if _squash(n) not in ctx]


def norm_label(label: str) -> str:
    label = label.replace("**", "").strip().strip('"“”\'').strip()
    if "?" in label:                       # the question ends at its "?"; whatever follows is a note
        label = label[: label.index("?") + 1]
    label = re.sub(r"\((required|optional|[^)]*chars?[^)]*)\)", "", label, flags=re.I)
    label = label.replace("**", "").strip().strip('"“”\'').strip()
    return re.sub(r"\s+", " ", label).lower().rstrip("*: ")


def is_why_them(label: str) -> bool:
    label = re.sub(r"\s+", " ", label)
    return bool(WHY_THEM.search(label)) and not ABOUT_YOU.search(label)


def is_mixed(label: str) -> bool:
    """Asks why-them AND about you ("Why this company / why you"): your work is allowed."""
    label = re.sub(r"\s+", " ", label)
    return bool(WHY_THEM.search(label)) and bool(ABOUT_YOU.search(label)) and not re.search(r"right (person|fit|candidate)|good fit|\bleav(e|ing)\b", label, re.I)


def answer_text(value: str) -> str:
    return re.sub(r"^\(\d+( chars?)?\)\s*", "", value.strip())


def current_answers(md: str) -> dict:
    """label -> (raw label, current answer). Later lines win; an 'as prepared' reference keeps the earlier text."""
    out: dict = {}
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m:
            continue
        raw, value = m.group(1), answer_text(m.group(2) or "")
        # A long answer is often written on the indented lines under its label (BEGIN ANSWER ... END): read those too.
        indent = len(line) - len(line.lstrip())
        cont = []
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if not s:
                continue
            if len(nxt) - len(nxt.lstrip()) <= indent or s.startswith("- ") or s.startswith("#"):
                break
            if not re.match(r"^(BEGIN|END)( ANSWER)?$", s):
                cont.append(s)
        if cont:
            value = (value + " " + " ".join(cont)).strip()
        label = raw.strip('"“” ')
        if not (is_why_them(label) or is_mixed(label)):
            continue
        key = norm_label(raw)
        if REFERENCE.search(value) and key in out:
            continue
        if NOT_AN_ANSWER.match(value) or len(value) < 20:
            continue
        out[key] = (raw, value)
    return out


def findings_for_text(label: str, text: str, names=()) -> list:
    if not is_why_them(label) or is_mixed(label):
        return []
    hits = [m.group(0) for m in RECITAL.finditer(text)]
    for n in names:                        # case-sensitive: an employer called Umbrella is not the word "umbrella"
        if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text):
            hits.append(n)
    return hits


def check_dossier(path: Path, names) -> tuple:
    """(findings, how many why-them answers were read)."""
    md_path = path / "application.md" if path.is_dir() else path
    if not md_path.exists():
        return [], 0
    res = []
    md_text = md_path.read_text(errors="ignore")
    allowed = [norm_label(a) for a, _ in ALLOW.findall(md_text)]
    answers = current_answers(md_text)
    for key, (raw, value) in answers.items():
        if any(key.startswith(a) for a in allowed):
            continue
        hits = findings_for_text(raw.strip('"“” '), value, without_own(names, md_path.parent.name, raw))
        if hits:
            res.append((str(md_path.relative_to(REPO)) if md_path.is_relative_to(REPO) else str(md_path), raw, hits, value))
    return res, len(answers)


def live(dirpath: str, names) -> int:
    """Check every answer read off the live forms (scripts/form_answers.js output) against the question and help text
    the FORM prints, not what a dossier recorded. Writes <dir>/REVIEW.md: every question beside its answer, which the
    agent and a fresh reviewer read in full before handover, because no pattern can tell whether an answer answers."""
    total, rows, unreadable, tabs = 0, [], 0, 0
    allowed = []
    for app in (REPO / "applications").glob("*/application.md"):
        allowed += [norm_label(x) for x, _ in ALLOW.findall(app.read_text(errors="ignore"))]
    for f in sorted(glob.glob(str(Path(dirpath) / "*.json")), key=lambda x: int(re.sub(r"\D", "", Path(x).stem) or 0)):
        try:
            d = load_form_json(Path(f).read_text())
        except (OSError, ValueError):
            unreadable += 1
            print(f"  could not read {f}: not form_answers.js output")
            continue
        if d.get("submitted"):
            continue
        tabs += 1
        for fl in d.get("fields") or []:
            v = (fl.get("value") or "").strip()
            label, help_text = fl.get("label") or "", fl.get("help") or ""
            if len(v) < 20 or re.match(r"^https?://\S+$", v):
                continue
            q = (label + " " + help_text).strip()
            hits = findings_for_text(q, v, without_own(names, d.get("url", ""), label))
            if hits and any(norm_label(label).startswith(a) for a in allowed):
                hits = []
            rows.append((Path(f).stem, d.get("url", ""), label, help_text, v, hits))
            total += bool(hits)
    if Path(dirpath).is_dir():
        with open(Path(dirpath) / "REVIEW.md", "w") as o:
            for tab, url, l, h, v, hits in rows:
                o.write(f"### tab {tab} {url}\nQ: {l[:200]}\nHELP: {h[:300]}\nA ({len(v)}): {v}\nGATE: {hits or 'clean'}\n\n")
    for tab, url, l, h, v, hits in rows:
        if hits:
            print(f"  tab {tab} [{l[:60]}] pitches: {', '.join(dict.fromkeys(hits))}")
    print(f"why_check --live: {len(rows)} answers read off {tabs} form(s), {unreadable} file(s) unreadable, {total} flagged. "
          f"Now read {dirpath}/REVIEW.md in full: does each answer answer the question printed above it?")
    if total:
        return 1
    if not rows:
        return not_checked(f"no filled free-text answer in {dirpath}.")
    if not names:
        return not_checked(NO_NAMES)
    return 0


NO_NAMES = ("your employers and projects cannot be read yet (resume/resume.html and knowledge-base/07 are still the "
            "blank templates), so only the first-person recital shapes were checked. Run /setup.")


def not_checked(why: str) -> int:
    print(f"why_check: NOT CHECKED: {why}")
    return 3


def selftest() -> int:
    ok = True
    names = ["Northwind", "Hooli", "Umbrella", "Night Float Handoff"]
    cases = [
        # A recital in a why-them box, across fields.
        ("Why Acme?", "Your clinics serve people who drive an hour for care. At Northwind I ran the night shift.", True),
        ("Why do you want to work for us?", "I treated patients on a cardiac floor for six years.", True),
        ("What excites you most about this role?", "I taught algebra to five sections of ninth graders.", True),
        ("Why do you want to work here?", "I installed commercial HVAC across three counties.", True),
        ("Why Initech?", "In my last role I closed the books for 14 clients.", True),
        ("Why Globex?", "My previous employer gave me a warehouse to run and I liked it.", True),
        ("Why Acme?", "Hooli gave me my start in bookkeeping and I would like more of that work.", True),
        ("What  interests you most about Globex?", "At Night Float Handoff we changed how shifts end.", True),  # double space in the label
        ('Why Acme?" (optional long text)', "I sold more than anyone in the district.", True),
        ('Message to the Hiring Team (Let the company know about your interest working there)',
         "Hi team, at Northwind I built the schedule.", True),                                           # "about your" is not "about you"
        # About them: clean.
        ("Why Acme?", "You run the only pediatric clinic in the county, and I want to work somewhere people depend on.", False),
        ("Why Acme?", "I managed to visit one of your stores last month and the staff knew every regular by name.", False),   # "managed to"
        ("Why Acme?", "I ran into your district manager at a food drive and she knew every volunteer.", False),
        ("Why Globex?", "I made a trip to your Dayton store and the floor was calm at the worst hour of the day.", False),
        ("Why Initech?", "I led my daughter's school tour here and your staff answered every question she had.", False),
        ("Why Acme?", "I grew up two streets from your first clinic.", False),
        ("Why Globex?", "I ran the Dayton store for three years.", True),                            # still work
        ("Why Globex?", "I made a trip planner for our drivers.", True),                             # "trip" as a thing built
        ("Why Initech?", "I led a team of six line cooks.", True),
        ("Why Acme?", "I ran my father's shop through two recessions.", True),                       # a relative's business is work
        ("Why Acme?", "I managed a warehouse crew of twelve.", True),
        ("Why Globex?", "I'd like to work under one umbrella with the people who plan the routes.", False),   # the word, not the employer
        # About you: not a why-them field.
        ("Tell us about you and why you're excited to apply", "At Northwind I ran the night shift.", False),
        ("Why are you a good fit for this role?", "At Northwind I ran the night shift.", False),
        ("Why are you the right person for Acme?", "At Northwind I ran the night shift.", False),
        ("Biggest professional failure", "At Northwind I cut the wrong budget line.", False),
        # Asks both: your work is allowed.
        ("Why this company / why you", "I like small towns. At Northwind I ran the night shift.", False),
        ("Additional Information Please share anything else, such as achievements, your motivation to apply",
         "At Northwind I ran the night shift.", False),
    ]
    for label, text, want in cases:
        got = bool(findings_for_text(label, text, names))
        if got != want:
            ok = False
            print(f"  FAIL: {label!r} expected {'finding' if want else 'clean'}")

    def expect(name, cond):
        nonlocal ok
        if not cond:
            ok = False
            print("  FAIL:", name)

    long_bad = "Your clinics serve people who drive an hour for care. At Northwind I ran the night shift."
    md = '- "Why Acme?": ' + long_bad + "\n- Why Acme?: (429 chars) as prepared above\n"
    expect("an 'as prepared' reference keeps the earlier text",
           len(current_answers(md)) == 1 and findings_for_text("Why Acme?", list(current_answers(md).values())[0][1], names))
    md3 = '- "Why Globex?" (optional long text):\n  BEGIN ANSWER\n  At Northwind I ran the night shift for years.\n  END ANSWER\n'
    expect("a multi-line answer under its label is read", any(findings_for_text("Why Globex?", v, names) for _, v in current_answers(md3).values()))
    md2 = md + "- Why Acme?: You run the only pediatric clinic in the county and I want to be part of that.\n"
    expect("a later corrected answer supersedes", not any(findings_for_text("Why Acme?", v, names) for _, v in current_answers(md2).values()))
    expect("a blank template answer is not an answer", current_answers("- Why Acme?: [ ]\n") == {})
    expect("your own employer's own form may name it", without_own(names, "northwind-charge-nurse") == ["Hooli", "Umbrella", "Night Float Handoff"])
    expect("legal suffixes are cut", core_name("Hooli Accounting, Inc.") == "Hooli Accounting" and core_name("Acme (Series B)") == "Acme")
    expect("projects read from a résumé", projects_from_html('<li class="proj"><b>Night Float Handoff, lead (2024).</b> x</li>') == ["Night Float Handoff"])
    expect("projects read from KB-07", projects_from_kb("### KEY PROJECTS\n\n- Night Float Handoff: a thing\n") == ["Night Float Handoff"])
    print("why_check selftest", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    names = own_names()
    if len(argv) == 3 and argv[1] == "--live":
        return live(argv[2], names)
    if len(argv) == 4 and argv[1] == "--text":
        if not (is_why_them(argv[2]) or is_mixed(argv[2])):
            return not_checked(f"{argv[2]!r} does not ask why you want them.")
        hits = findings_for_text(argv[2], Path(argv[3]).read_text(), names)
        if hits:
            print(f"why_check: the answer to {argv[2]!r} pitches your own work: {', '.join(dict.fromkeys(hits))}. "
                  "A why-them answer is about the company and why you want to be there (knowledge-base/12 section 5.1a).")
            return 1
        if not names:
            return not_checked(NO_NAMES)
        print("why_check: CLEAN")
        return 0
    if len(argv) < 2 or argv[1].startswith("--"):
        print(__doc__)
        return 2
    total, read = 0, 0
    for a in argv[1:]:
        p = Path(a)
        p = p if p.is_absolute() else REPO / p
        if not p.is_dir():
            return not_checked(f"no such folder: {a}")
        res, n = check_dossier(p, names)
        read += n
        for rel, raw, hits, _ in res:
            total += 1
            print(f"  {rel}  [{raw.strip()[:60]}]  pitches: {', '.join(dict.fromkeys(hits))}")
    if total:
        print(f"why_check: {total} why-them answer(s) recite your own work instead of saying why you want them (knowledge-base/12 section 5.1a).")
        return 1
    if not read:
        return not_checked("no why-them answer recorded in application.md yet.")
    if not names:
        return not_checked(NO_NAMES)
    print(f"why_check: CLEAN ({read} why-them answer(s) read)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
