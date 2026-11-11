#!/usr/bin/env python3
"""work_history_check.py: a form's work-history description is the résumé's bullets for that role, never a summary.

Rule owner: knowledge-base/12-application-answers.md section 1b. This gate is its teeth.

What it checks: every work-history / position-description box read off a live form must be one role's résumé
bullets, verbatim: all of them, or (when the box has a character limit) whole bullets, at least two (one when the
role has one), in any order, nothing else added. An earlier title at the same employer may instead carry the
one-line pointer that `--print` shows.

Roles come from your own résumé (resume/resume.html, or the dossier's tailored copy with --resume), and from
knowledge-base/07-master-resume.md when the résumé is still the blank template. Nothing about any person is built in.

Usage:
    python3 scripts/work_history_check.py --live <dir-or-json> [...] [--resume <file>]   form_answers.js output
    python3 scripts/work_history_check.py --text <answer-file> [--resume <file>]         one drafted description
    python3 scripts/work_history_check.py --print [--resume <file>]                      the bullets each role must carry
    python3 scripts/work_history_check.py --selftest
Exit 0 = checked and clean; 1 = a finding; 3 = NOT CHECKED (no roles to compare with, or no box to check). 3 is never a pass.
"""
import contextlib
import html
import io
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESUME = REPO / "resume" / "resume.html"
KB07 = REPO / "knowledge-base" / "07-master-resume.md"

# A field that holds a role's description. The first form is a date row some forms print as the box's label.
STRONG_LABEL = re.compile(
    r"^\s*start date end date delete\s*$|work history|position description|job description|role description|"
    r"responsibilit|\bduties\b|describe (your|the) (role|position|work|job)", re.I)
BARE_LABEL = re.compile(r"^\s*description\s*\*?\s*$", re.I)
PLACEHOLDER = re.compile(r"\[|^\s*(employer name|previous employer|your title|project name|bullet\b|bullet one|bullet two|bullet three)", re.I)


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"(?m)^\s*[•\-*]\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def _title(fragment: str) -> str:
    return re.sub(r"\s+", " ", _text(fragment)).split(" · ")[0].strip()


def roles_from_html(s: str) -> list:
    """Each role in a résumé built on resume/resume.html: {employer, titles, bullets}. Templates yield nothing."""
    s = re.sub(r"<style.*?</style>|<!--.*?-->", "", s, flags=re.S)
    roles = []
    for block in re.split(r'<div class="job"[^>]*>', s)[1:]:
        block = re.split(r"<h2\b", block)[0]
        co = re.search(r'<span class="co">(.*?)</span>', block, re.S)
        if not co:
            continue
        employer = re.sub(r"\s+", " ", _text(co.group(1)))
        titles = [_title(t) for t in re.findall(r'<div class="role-title">(.*?)</div>', block, re.S)]
        if not titles:
            head = re.search(r'<div class="job-title">(.*?)</div>', block, re.S)
            tail = re.sub(r"\s+", " ", _text(head.group(1))).split(" · ", 1) if head else []
            titles = [tail[1].strip()] if len(tail) == 2 else []
        bullets = [norm(_text(b)) for b in re.findall(r"<li[^>]*>(.*?)</li>", block, re.S)]
        bullets = [b for b in bullets if b and not PLACEHOLDER.search(b)]
        if bullets and not PLACEHOLDER.search(employer):
            roles.append({"employer": employer, "titles": titles, "bullets": bullets})
    return roles


def roles_from_kb(s: str) -> list:
    """Each role in KB-07's WORK EXPERIENCE: **Employer, Title** (dates), then '- ' bullets. Templates yield nothing."""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    m = re.search(r"^### WORK EXPERIENCE\s*$(.*?)(?=^### |\Z)", s, re.S | re.M)
    if not m:
        return []
    roles, cur = [], None
    for line in m.group(1).splitlines():
        head = re.match(r"\s*\*\*(.+?)\*\*", line)
        if head:
            parts = head.group(1).split(",", 1)
            cur = {"employer": parts[0].strip(), "titles": [parts[1].strip()] if len(parts) == 2 else [], "bullets": []}
            roles.append(cur)
        elif cur is not None and re.match(r"\s*-\s+\S", line):
            b = norm(line)
            if not PLACEHOLDER.search(b):
                cur["bullets"].append(b)
    return [r for r in roles if r["bullets"] and not PLACEHOLDER.search(r["employer"])]


def load_roles(resume: Path = RESUME, kb: Path = KB07) -> tuple:
    """(roles, where they came from). ([], reason) when neither file has a real role yet."""
    if resume.exists():
        roles = roles_from_html(resume.read_text(errors="ignore"))
        if roles:
            return roles, str(resume)
    if kb.exists():
        roles = roles_from_kb(kb.read_text(errors="ignore"))
        if roles:
            return roles, str(kb)
    return [], f"no real role in {resume.name} or {kb.name} (still the blank template?)"


def earlier_line(role: dict) -> str:
    """The pointer an earlier title at the same employer carries (or the same bullets, when a form shows one entry)."""
    latest = role["titles"][0] if role["titles"] else "most recent"
    return f"Earlier title at {role['employer']}. The work is described in the {latest} entry."


def _strip_bullets(v: str, role: dict) -> tuple:
    rest, found = v, 0
    for b in sorted(role["bullets"], key=len, reverse=True):
        x = b.rstrip(".")
        if x and x in rest:
            rest, found = rest.replace(x, "", 1), found + 1
    return rest, found


def judge(value: str, roles: list, strong: bool = True) -> tuple:
    """('ok'|'fail'|'unsure', message). unsure = a bare 'Description' box that names no employer and holds no bullet."""
    v = norm(value)
    if not v:
        return "ok", ""
    for r in roles:
        if len(r["titles"]) > 1 and v == norm(earlier_line(r)):
            return "ok", ""
    best, best_found, best_rest = None, 0, v
    for r in roles:
        rest, found = _strip_bullets(v, r)
        if found > best_found:
            best, best_found, best_rest = r, found, rest
    if best is None:
        best = next((r for r in roles if re.search(r"(?<!\w)" + re.escape(r["employer"]) + r"(?!\w)", v)), None)
    if best is None:
        if strong:
            return "fail", ("this description matches no role's résumé bullets. Type one role's bullets verbatim "
                            "(knowledge-base/12 section 1b; --print shows them).")
        return "unsure", "a bare Description box that matches no role: read it by eye."
    need = min(2, len(best["bullets"]))
    if best_found >= need and not re.sub(r"[\s.'\"•*-]", "", best_rest):
        return "ok", ""
    return "fail", (f"{best['employer']}: the description is not the résumé's bullets for this role "
                    f"({len(v)} chars typed; the bullets are {len(' '.join(best['bullets']))} chars). "
                    "Type every bullet verbatim, or whole bullets when the box has a limit "
                    "(knowledge-base/12 section 1b; --print shows them).")


def load_form_json(text: str) -> dict:
    """form_answers.js output: raw JSON from filePath, or a tool's reply with the JSON in a fenced block."""
    m = re.search(r"```json\s*(.*?)```", text, re.S)
    return json.loads(m.group(1) if m else text[text.index("{"):])


def fields_of(path: Path):
    d = load_form_json(path.read_text())
    fl = d.get("fields") if isinstance(d, dict) else None
    if isinstance(fl, dict):
        fl = [{"label": k, "value": v} for k, v in fl.items()]
    for f in fl or []:
        if isinstance(f, dict) and isinstance(f.get("value"), str):
            yield d.get("url", path.name), f.get("label") or "", f["value"]


def not_checked(why: str) -> int:
    print(f"work_history_check: NOT CHECKED: {why}")
    return 3


def live(paths, roles) -> int:
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    total, boxes, unreadable = 0, 0, 0
    for f in files:
        try:
            rows = list(fields_of(f))
        except OSError:
            unreadable += 1
            print(f"  could not read {f}: no such file, or it can't be opened")
            continue
        except ValueError:
            unreadable += 1
            print(f"  could not read {f}: not form_answers.js output")
            continue
        for url, label, value in rows:
            strong = bool(STRONG_LABEL.search(label))
            # A section label can join every field's text; the field under a summary label is not a role description.
            if not (strong or BARE_LABEL.search(label)) or re.search(r"summary", label, re.I) or len(label) > 120:
                continue
            boxes += 1
            verdict, msg = judge(value, roles, strong)
            if verdict == "fail":
                total += 1
                print(f"FAIL {f.name} {url[:70]}\n  typed: {value[:160]}\n  {msg}")
            elif verdict == "unsure":
                print(f"READ BY EYE {f.name} [{label[:40]}] {value[:100]}")
    print(f"work_history_check --live: {len(files) - unreadable} form(s) read, {boxes} box(es) checked, {unreadable} unreadable, {total} finding(s)")
    if total:
        return 1
    if not boxes:
        return not_checked("no work-history box in what was read. Fine for a form that has none; it is still not a pass.")
    return 0


SAMPLE = """<style>li{}</style>
<!-- <div class="job"><span class="co">Commented Out</span><li>never read</li></div> -->
<h2>Experience</h2>
<div class="job"><div class="job-head"><div class="job-title"><span class="co">Northwind Clinic</span> · Springfield</div></div>
<div class="role"><div class="role-title">Charge Nurse · Full-time</div><div class="job-dates">2023 to 2025</div></div>
<div class="role"><div class="role-title">Staff Nurse · Full-time</div><div class="job-dates">2020 to 2023</div></div>
<ul><li>Ran the night shift for a 24-bed unit.</li><li>Trained eleven new nurses on the charting system.</li><li>Cut medication errors on the unit by a third.</li></ul></div>
<div class="job"><div class="job-head"><div class="job-title"><span class="co">Initech School District</span> · Math Teacher</div><div class="job-dates">2018 to 2020</div></div>
<ul><li>Taught algebra to five sections of ninth graders.</li></ul></div>
<div class="job"><div class="job-head"><div class="job-title"><span class="co">Globex Freight</span> · Dock Lead</div></div>
<ul><li>Scheduled 40 inbound trucks a day.</li><li>Rebuilt the cycle count so it matched the system.</li></ul></div>
<h2>Selected Projects</h2><ul><li class="proj"><b>Project name, role.</b> Not a job.</li></ul>
"""
TEMPLATE = """<div class="job"><div class="job-title"><span class="co">Employer Name</span> · Your Title</div>
<ul><li>Bullet one: verb-first.</li><li>Bullet.</li></ul></div>"""
KB_FILLED = """<!-- **Employer, Title** (dates) in a comment is never read -->
### WORK EXPERIENCE

**Hooli Accounting, Senior Bookkeeper** (Mar 2021 - Present)
- Closed the books for 14 clients every month.
- Moved payroll onto one system.

### KEY PROJECTS
"""
KB_TEMPLATE = """### WORK EXPERIENCE

**[Employer Name], [Your Title]** ([Mon YYYY] - Present)
- [Bullet 1: start with a verb]
"""


def selftest() -> int:
    ok = True

    def expect(name, cond):
        nonlocal ok
        if not cond:
            ok = False
            print("SELFTEST FAIL:", name)

    roles = roles_from_html(SAMPLE)
    by = {r["employer"]: r for r in roles}
    nurse, teach, dock = by.get("Northwind Clinic"), by.get("Initech School District"), by.get("Globex Freight")
    expect("three roles parsed, the commented one ignored", len(roles) == 3 and "Commented Out" not in by)
    expect("a two-title employer keeps both titles", nurse and nurse["titles"] == ["Charge Nurse", "Staff Nurse"])
    expect("a one-title employer reads its title", teach and teach["titles"] == ["Math Teacher"])
    expect("a blank template has no roles", roles_from_html(TEMPLATE) == [] and roles_from_kb(KB_TEMPLATE) == [])
    kb = roles_from_kb(KB_FILLED)
    expect("KB-07 parsed", len(kb) == 1 and kb[0]["employer"] == "Hooli Accounting" and len(kb[0]["bullets"]) == 2)

    def verdict(v, strong=True):
        return judge(v, roles, strong)[0]

    all_n = nurse["bullets"]
    expect("a summary naming the employer fails", verdict("Charge nurse at Northwind Clinic, leading a busy unit.") == "fail")
    expect("a summary naming no employer fails", verdict("Cared for patients on a busy medical floor.") == "fail")
    expect("the same on a bare Description box is read by eye", verdict("Cared for patients.", strong=False) == "unsure")
    expect("all bullets pass", verdict("\n".join("• " + x for x in all_n)) == "ok")
    expect("first two bullets pass", verdict("\n\n".join(all_n[:2])) == "ok")
    expect("one bullet of a three-bullet role fails", verdict(all_n[0]) == "fail")
    expect("reordered bullets pass", verdict(" ".join(reversed(all_n))) == "ok")
    expect("bullets plus an added sentence fail", verdict(" ".join(all_n) + " I also ran the holiday party.") == "fail")
    expect("a one-bullet role passes on its bullet", verdict(teach["bullets"][0]) == "ok")
    expect("the pointer passes for a two-title employer", verdict(earlier_line(nurse)) == "ok")
    expect("the pointer fails for a one-title employer", verdict(earlier_line(teach)) == "fail")
    expect("a curly apostrophe and a dash still match",
           judge("Ran the night\u2013shift", [{"employer": "Umbrella Retail", "titles": [], "bullets": ["Ran the night-shift"]}])[0] == "ok")
    expect("dock bullets pass", verdict(" ".join(dock["bullets"])) == "ok")
    expect("the date row is a strong label", bool(STRONG_LABEL.search("Start date End date Delete")))
    expect("a summary label is not a description label", not STRONG_LABEL.search("Experience Summary*") and not BARE_LABEL.search("Experience Summary*"))
    expect("fenced tool output parses", load_form_json('Ran:\n```json\n{"fields":[]}\n```') == {"fields": []})
    with tempfile.TemporaryDirectory() as td:
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = live([str(Path(td) / "absent.json")], roles)
    expect("a path that does not exist is not counted as a form read, and is not a pass",
           code == 3 and "0 form(s) read" in said.getvalue() and "1 unreadable" in said.getvalue())
    print("work_history_check selftest", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv) -> int:
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest()
    resume = RESUME
    if "--resume" in args:
        i = args.index("--resume")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        resume = Path(args[i + 1])
        resume = resume if resume.is_absolute() else REPO / resume
        del args[i:i + 2]
    if not args or args[0] not in ("--print", "--live", "--text") or (args[0] != "--print" and len(args) < 2):
        print(__doc__)
        return 2
    roles, src = load_roles(resume)
    if not roles:
        return not_checked(src + ". Fill in your résumé or run /setup, then run this again.")
    if args[0] == "--print":
        for r in roles:
            print(f"== {r['employer']}" + (f" ({', '.join(r['titles'])})" if r["titles"] else ""))
            print("\n".join("• " + x for x in r["bullets"]))
            if len(r["titles"]) > 1:
                print(f"Earlier titles here carry this line, or the same bullets:\n{earlier_line(r)}")
            print()
        return 0
    if args[0] == "--live":
        return live(args[1:], roles)
    verdict, msg = judge(Path(args[1]).read_text(), roles)
    print(msg or "clean")
    return 1 if verdict == "fail" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
