#!/usr/bin/env python3
"""resume_gate.py — a rendered résumé is ONE page, and it FILLS that page.

WHY THIS EXISTS
---------------
Empty space on a one-page résumé is not restraint, it's unused evidence — and the failure mode
that motivated this gate was a résumé that dropped the current employer entirely, listing it only
as a line inside a projects section, so its Experience section read as though the person hadn't
worked in years. Nothing mechanical caught that until this gate existed.

WHAT THIS CHECKS
----------------
  1. PAGES == 1.  A second page is a hard fail.
  2. FILL >= 88%. The last line of text must reach at least 88% of the page height.
  3. EVERY EMPLOYMENT ENTRY IS PRESENT. Every employer listed under WORK EXPERIENCE in
     knowledge-base/07-master-resume.md must appear on the page, and the CURRENT one must sit
     beside a still-open date range ("Present") rather than only as a project credit.

     Detection is by date proximity, never by section order — résumé variants order their
     sections differently and an order-based check produces false positives when Education
     happens to sit above Experience in a particular layout.

WHAT THIS DOES NOT CHECK
------------------------
Whether the content is TRUE (canon.py and verify_claims.py own that), whether it is well written,
or whether it is tailored to the target. It measures shape and one structural omission.

    python3 scripts/resume_gate.py                      # every résumé PDF in the repo
    python3 scripts/resume_gate.py <path-or-dossier>    # one file or one dossier
    python3 scripts/resume_gate.py --selftest            # self-contained, no real résumé required
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

MIN_FILL = 88.0          # percent of page height the last line of text must reach
MAX_PAGES = 1

# "Listed as employment" is detected by PROXIMITY TO A CURRENT DATE RANGE, not by section order —
# a cut-at-the-next-heading approach false-positives whenever Education happens to sit above
# Experience in a given layout. A date range's position doesn't move with the layout.
PRESENT = re.compile(r"\bPresent\b", re.I)


@dataclass
class Finding:
    path: str
    problems: list[str]


def _parse_required_employment(text: str) -> list[tuple[str, str, bool]]:
    """Parse [(employer, start_date, is_current), ...] out of a WORK EXPERIENCE section's text.

    Only top-level `**Employer — Title** — dates` lines count — a blockquote or bullet line
    doesn't, which is what keeps a footnote about a *retired* employer claim from being read back
    in as a live requirement.
    """
    m = re.search(r"^###\s+WORK EXPERIENCE\s*$(.*?)(?=^###\s|\Z)", text, re.M | re.S)
    if not m:
        return []
    out: list[tuple[str, str, bool]] = []
    for line in m.group(1).splitlines():
        e = re.match(r"^\*\*([^*]+?)\*\*\s*[—-]\s*(.+)$", line.strip())
        if not e:
            continue
        employer = re.split(r"\s+[—-]\s+", e.group(1))[0]
        employer = re.sub(r"\s*\([^)]*\)\s*$", "", employer).strip().rstrip(".")
        start = re.match(r"\s*([A-Z][a-z]{2}\s+\d{4})", e.group(2))
        if employer and start:
            out.append((employer, start.group(1), bool(PRESENT.search(e.group(2)))))
    return out


def _parse_canonical_facts(text: str) -> dict[str, list[tuple[str, str]]]:
    """Parse {"never": [...], "number": [...], "exact": [...]} out of a ```canonical-facts``` block."""
    out: dict[str, list[tuple[str, str]]] = {"never": [], "number": [], "exact": []}
    m = re.search(r"```canonical-facts\n(.*?)```", text, re.S)
    if not m:
        return out
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, rest = line.partition(":")
        kind = kind.strip()
        if kind not in out:
            continue
        # Lines carry up to three pipe-separated fields: key | value | human note. Splitting on
        # only the first pipe swallows the note into the value and fails every résumé, including
        # a correctly-written one — a bug the selftest below pins permanently.
        parts = [x.strip() for x in rest.split("|")]
        key = parts[0] if parts else ""
        val = parts[1] if len(parts) > 1 else ""
        if key:
            out[kind].append((key, val))
    return out


def required_employment() -> list[tuple[str, str, bool]]:
    """The production entry point — always reads the real knowledge-base file.

    Never hardcoded: when the user changes jobs, this gate follows on the next KB edit with no
    code change.
    """
    kb = REPO / "knowledge-base" / "07-master-resume.md"
    try:
        return _parse_required_employment(kb.read_text())
    except OSError:
        return []


def canonical_facts() -> dict[str, list[tuple[str, str]]]:
    """The production entry point — always reads the real knowledge-base file."""
    try:
        return _parse_canonical_facts((REPO / "knowledge-base" / "07-master-resume.md").read_text())
    except OSError:
        return {"never": [], "number": [], "exact": []}


def _loose(token: str) -> str:
    """A regex for `token` that tolerates true spellings of the same fact.

    "1070" (no thousands comma), "April 2025" (month spelled out), and "Apr 2025 – Current" are
    all the same fact as "1,070" / "Apr 2025" / "Apr 2025 – Present" — a gate that fails honest
    copy trains people to ignore it, which costs more than the defect it was meant to catch.
    """
    MONTHS = {"Jan": "Jan(?:uary)?", "Feb": "Feb(?:ruary)?", "Mar": "Mar(?:ch)?",
              "Apr": "Apr(?:il)?", "May": "May", "Jun": "Jun(?:e)?", "Jul": "Jul(?:y)?",
              "Aug": "Aug(?:ust)?", "Sep": "Sep(?:t(?:ember)?)?", "Oct": "Oct(?:ober)?",
              "Nov": "Nov(?:ember)?", "Dec": "Dec(?:ember)?"}
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{4})$", token)
    if m and m.group(1) in MONTHS:
        return rf"\b{MONTHS[m.group(1)]}\.?\s+{m.group(2)}\b"
    if token.lower() == "present":
        return r"\b(?:Present|Current|Now|Ongoing)\b"
    if re.fullmatch(r"[\d,]+", token):                      # 1,070 == 1070
        return r"\b" + re.escape(token).replace(",", "[,\\s]?") + r"\b"
    return re.escape(token).replace(r"\ ", r"\s+")


def _near(flat: str, employer: str, token: str, span: int = 200) -> bool:
    """Does `token` sit within `span` characters of an occurrence of `employer`?"""
    pat = re.compile(_loose(token), re.I)
    for h in re.finditer(re.escape(employer), flat, re.I):
        if pat.search(flat[max(0, h.start() - span): h.end() + span]):
            return True
    return False


def measure(pdf: Path) -> tuple[int, float, str] | None:
    """(page_count, fill_percent, page1_text). None if the PDF cannot be read."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        doc = fitz.open(pdf)
    except Exception:
        return None
    if doc.page_count == 0:
        return None
    page = doc[0]
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    if not blocks:
        return doc.page_count, 0.0, ""
    # Fill is where the body ENDS, not where the lowest ink is — a naive max(bottom edge) reads a
    # near-empty page as full the moment a normal footer line sits near the bottom. Walk the
    # blocks top-down and stop at the first large vertical gap; content below a big hole isn't
    # part of the body.
    tops = sorted(blocks, key=lambda b: b[1])
    body_bottom = tops[0][3]
    GAP = 0.10 * page.rect.height          # a hole bigger than a tenth of the page ends the body
    for prev, nxt in zip(tops, tops[1:]):
        if nxt[1] - body_bottom > GAP:
            break
        body_bottom = max(body_bottom, nxt[3])
    fill = 100.0 * body_bottom / page.rect.height
    return doc.page_count, fill, page.get_text()


def check_pdf(pdf: Path, required: list | None = None, facts: dict | None = None) -> Finding | None:
    """Check one rendered PDF. `required`/`facts` default to the real KB; pass explicit fixture
    values (as the selftest does) to check against something other than the real repo state."""
    m = measure(pdf)
    if m is None:
        return Finding(str(pdf), ["could not be read as a PDF (is PyMuPDF installed?)"])
    pages, fill, text = m
    problems: list[str] = []

    if pages > MAX_PAGES:
        problems.append(f"{pages} pages. A résumé is ONE page.")

    if fill < MIN_FILL:
        blank = round((100 - fill) / 100 * 841.9)
        problems.append(
            f"fills only {fill:.1f}% of the page, about {blank}pt left blank at the bottom "
            f"(floor is {MIN_FILL:.0f}%). Empty space is unused evidence."
        )

    # An empty required-employment list must fail LOUD, never read as "nothing wrong" — a KB
    # heading rename or an unreadable file must never silently disable this whole check.
    if required is None:
        required = required_employment()
    if not required:
        problems.append(
            "the required-employment list is EMPTY, so the employment check did not run. "
            "knowledge-base/07-master-resume.md must contain a line exactly `### WORK EXPERIENCE` "
            "followed by `**Employer — Title** — Mon YYYY – …` entries. Fix the KB; do not trust "
            "this résumé until this line disappears."
        )

    # A4 is 595×842pt, US Letter 612×792pt. An A3 page is still "1 page" and prints as two sheets.
    try:
        import fitz as _fitz
        _pg = _fitz.open(pdf)[0].rect
        if not (560 <= _pg.width <= 640 and 770 <= _pg.height <= 860):
            problems.append(
                f"page is {_pg.width:.0f}×{_pg.height:.0f}pt, which is neither A4 (595×842) nor "
                f"US Letter (612×792). An oversized page is one page only in the file."
            )
    except Exception:
        pass

    # SAME TEXT BLOCK, not merely nearby: a real employment row renders as one text block
    # containing the employer and its dates together; a projects-section credit does not, even if
    # it happens to carry a date range too.
    blocks: list[str] = []
    try:
        import fitz as _f
        blocks = [b[4] for b in _f.open(pdf)[0].get_text("blocks") if b[4].strip()]
    except Exception:
        blocks = []

    # A match inside the PROJECTS section does not count as employment — only the PROJECTS
    # heading is used as the cut, never EDUCATION (cutting at EDUCATION false-positives whenever
    # a layout puts Education above Experience).
    _PROJ = re.compile(r"^\s*(SELECTED\s+PROJECTS|PROJECTS)\s*$", re.I | re.M)
    _proj_at = next((i for i, b in enumerate(blocks) if _PROJ.search(b)), None)
    _emp_blocks = blocks if _proj_at is None else blocks[:_proj_at]

    def _listed(emp: str, tok: str) -> bool:
        if blocks:
            return any(emp.lower() in b.lower() and re.search(_loose(tok), b, re.I)
                       for b in _emp_blocks)
        return _near(re.sub(r"\s+", " ", text), emp, tok)   # no block info: fall back, never skip

    if text:
        _flat = re.sub(r"\s+", " ", text)
        if facts is None:
            facts = canonical_facts()
        if not facts["never"] and not facts["number"]:
            problems.append(
                "the canonical-facts block in knowledge-base/07-master-resume.md is missing or "
                "unparseable, so none of your locked résumé decisions were checked. Restore the "
                "```canonical-facts``` block before trusting this résumé."
            )
        # Retired claims come from canon.py, the owner — never a second list here. Two lists is
        # how a mismatch starts. canon scopes its rules by path prefix, so it must be handed a
        # real repo-relative path — a bare "resume" string matches no scope and silently returns
        # zero findings.
        try:
            import canon as _canon
            _rel = str(pdf.relative_to(REPO)) if pdf.is_relative_to(REPO) else f"resume/{pdf.name}"
            for cf in _canon.scan_text(_rel, text):
                problems.append(
                    f"asserts a retired claim [{cf.rule_id}]: \"{cf.text.strip()[:90]}\". "
                    f"{cf.why} Instead: {cf.instead}"
                )
        except Exception as e:
            problems.append(
                f"could not load canon.py's retired-claim registry ({e}), so this résumé was NOT "
                f"checked against any retired claim. Fix the import before trusting this result."
            )
        for bad, why in facts["never"]:
            if re.search(re.escape(bad).replace(r"\ ", r"\s+"), _flat, re.I):
                problems.append(f"contains a retired string: \"{bad}\". {why}")

        # "email" / "portfolio" / "linkedin" have a genuinely universal shape, so they're checked
        # by finding what's actually on the page and comparing it to the canonical value — this
        # can catch a WRONG value, not just a missing one. "title" has no universal shape across
        # roles/industries, so it's checked as a direct presence test instead: is the canonical
        # title string found anywhere on the page? (A shape-based regex here would only ever
        # match one specific title pattern and silently do nothing for anyone else's.)
        _EXACT_SHAPE = {
            "email":     r"[\w.+-]+@[\w.-]+\.\w+",
            # (?<!@) and the negative lookbehind on the leading token stop this from matching the
            # DOMAIN half of an email address (e.g. "example.com" inside "you@example.com") as if
            # it were a portfolio URL — an email and a portfolio are usually different domains, and
            # without this a résumé's own contact line produces a false "wrong portfolio" finding.
            "portfolio": r"(?<![\w.@-])[\w-]+\.(?:in|com|dev|design|io)\b(?!/)",
            "linkedin":  r"linkedin\.com/in/[\w-]+",
        }
        for label, want in facts["exact"]:
            if not want:
                continue
            if label == "title":
                if not re.search(re.escape(want).replace(r"\ ", r"\s+"), _flat, re.I):
                    problems.append(
                        f"the canonical title {want!r} was not found anywhere on the page "
                        f"(knowledge-base/07-master-resume.md → canonical-facts)."
                    )
                continue
            pat = _EXACT_SHAPE.get(label)
            if not pat:
                continue
            found = [m.group(0) for m in re.finditer(pat, _flat, re.I)]
            if label == "portfolio":
                found = [x for x in found if "@" not in x and "linkedin" not in x.lower()]
            if found and not any(want.lower() in x.lower() or x.lower() in want.lower() for x in found):
                problems.append(
                    f"the {label} on this résumé is {found[0]!r}, but the canonical value is "
                    f"{want!r} (knowledge-base/07-master-resume.md → canonical-facts)."
                )
        # A number rule fires on a WRONG COUNT, never on the bare noun — only when a quantity sits
        # immediately before the noun is it graded, so ordinary prose mentioning the same noun
        # with no count claim never trips it.
        for trigger, required_value in facts["number"]:
            noun = re.escape(trigger).replace(r"\ ", r"\s+")
            for q in re.finditer(r"([\d][\d,\.]*\s*\+?|[Tt]en|[Tw]welve)\s*(?:\w+\s+){0,2}?" + noun,
                                 _flat, re.I):
                said = q.group(1).strip().rstrip("+").rstrip(".")
                want = required_value.strip()
                _s = said.replace(",", "").lower().rstrip("m+")
                _w = want.replace(",", "").lower().rstrip("m+")
                if _s == _w:
                    continue
                if re.fullmatch(r"[Tt]welve", said) and want == "12":
                    continue
                problems.append(
                    f"says \"{said} {trigger}\" but the canonical value is \"{want}\" "
                    f"(knowledge-base/07-master-resume.md → canonical-facts). Fix the résumé, "
                    f"or change the fact in the KB if the real number moved."
                )

    if text:
        for emp, start, is_current in required:
            if not _listed(emp, start):
                if is_current:
                    problems.append(
                        f"the CURRENT job ({emp}, {start} – Present) is not listed as employment. "
                        f"It reads as though you last worked years ago."
                    )
                else:
                    problems.append(
                        f"employment entry MISSING: {emp} ({start}). Every employer under WORK "
                        f"EXPERIENCE in knowledge-base/07-master-resume.md must be on the page "
                        f"beside its own dates. A tailored résumé re-emphasises; it never "
                        f"deletes a job."
                    )
            elif is_current and not _listed(emp, "Present"):
                problems.append(
                    f"the CURRENT employer ({emp}) is on the page but not beside an open date "
                    f"range. It must read as employment, not as a finished engagement."
                )

    return Finding(str(pdf.relative_to(REPO)) if pdf.is_relative_to(REPO) else str(pdf), problems) if problems else None


def check_html(src: Path) -> Finding | None:
    """The employment-completeness half, run on the HTML *before* anything is rendered."""
    try:
        raw = src.read_text()
    except OSError:
        return None
    body = re.sub(r"<style.*?</style>", "", raw, flags=re.S)
    body = re.sub(r"<(script|head)[\s\S]*?</\1>", "", body)
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
    problems: list[str] = []
    for emp, start, is_current in required_employment():
        if not _near(flat, emp, start):
            problems.append(
                f"{'the CURRENT job' if is_current else 'employment entry'} MISSING: {emp} "
                f"({start}). Copy resume/resume.html and apply only the delta noted in this "
                f"dossier's tailoring.md — don't author a résumé from scratch per application."
            )
    rel = str(src.relative_to(REPO)) if src.is_relative_to(REPO) else str(src)
    return Finding(rel, problems) if problems else None


def targets(args: list[str]) -> list[Path]:
    if not args:
        # EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (verify_claims.py's own fixture, and the
        # blank starter copy-from), never a real outbound résumé — sweeping them here would fail
        # this gate forever on every fresh clone, for a PDF nobody is about to send to an employer.
        real_dossier_pdfs = [
            p for p in REPO.glob("applications/*/resume/*.pdf")
            if not p.relative_to(REPO).parts[1].startswith(("EXAMPLE-", "TEMPLATE-"))
        ]
        return sorted(REPO.glob("resume/*.pdf")) + sorted(real_dossier_pdfs)
    out: list[Path] = []
    for a in args:
        p = Path(a) if Path(a).is_absolute() else REPO / a
        if p.is_dir():
            out += sorted(p.glob("**/*.pdf")) + sorted(p.glob("**/resume*.html"))
        elif p.suffix.lower() in (".pdf", ".html"):
            out.append(p)
    return out


# ── selftest: a fully self-contained fictional fixture, independent of any real résumé ──
#
# Everything below is generated from FIXTURE_KB — never from the real knowledge-base/07 file —
# so `--selftest` passes on a fresh clone before anyone has written a real résumé.
FIXTURE_KB = """
### WORK EXPERIENCE

**Acme Robotics — Staff Product Designer** — Mar 2024 – Present
- Led the redesign of the fleet-ops console end to end.

**Globex Analytics — Senior Product Designer** — Jun 2021 – Feb 2024
- Shipped a self-serve dashboard used by every enterprise account.

## 🔴 CANONICAL FACTS

```canonical-facts
exact: email | jordan.rivera@example.com
exact: portfolio | jordanrivera.example
exact: linkedin | linkedin.com/in/jordanrivera
exact: title | Staff Product Designer
number: DTCG tokens | 1,070 | the live design-token count
```
"""
FIXTURE_EDUCATION_DECOY = "State University"  # same name as an employer that must never exist here


def selftest() -> int:
    import tempfile
    ok = True
    try:
        import fitz
    except ImportError:
        print("SELFTEST SKIPPED — PyMuPDF not available")
        return 0

    required = _parse_required_employment(FIXTURE_KB)
    facts = _parse_canonical_facts(FIXTURE_KB)
    if not required:
        print("SELFTEST FAILED — the fixture's own WORK EXPERIENCE section didn't parse. This is a "
              "bug in this file, not in any real résumé.")
        return 1
    all_emps = [e for e, _, _ in required]

    def synth(lines: int, pages: int = 1, employers: list[str] | None = None,
              education_name: str | None = None) -> Path:
        """employers=None means 'every required one'. Pass a subset to simulate a deletion.

        education_name re-prints a name under EDUCATION with a DIFFERENT date — the decoy that
        defeats a name-only presence check (the job must be gone from Experience even though the
        same string survives under Education).
        """
        emps = all_emps if employers is None else employers
        d = fitz.open()
        for pg in range(pages):
            page = d.new_page(width=595, height=842)
            y = 60
            if pg == 0:
                page.insert_text((50, y), "JORDAN RIVERA", fontsize=16); y += 30
                page.insert_text((50, y), "EXPERIENCE", fontsize=11); y += 20
                for e, start, cur in required:
                    if e not in emps:
                        continue
                    end = "Present" if cur else "Feb 2024"
                    page.insert_text((50, y), f"{e} - Staff Product Designer  {start} - {end}", fontsize=8); y += 13
                for i in range(lines):
                    page.insert_text((50, y), f"a line of resume content number {i}", fontsize=9); y += 14
                page.insert_text((50, y), "SELECTED PROJECTS", fontsize=11); y += 18
                page.insert_text((50, y), "Fleet console v2, solo design and build", fontsize=9); y += 16
                if education_name:
                    page.insert_text((50, y), "EDUCATION", fontsize=11); y += 16
                    page.insert_text((50, y), f"{education_name} - MS HCI  Aug 2019 - May 2021", fontsize=8)
        f = Path(tempfile.mkstemp(suffix=".pdf")[1]); d.save(f); return f

    current = [e for e, _, c in required if c]
    past = [e for e, _, c in required if not c]

    def _t(label: str, cond: bool, why: str = "") -> bool:
        print(f"  {'✓' if cond else '✗✗'} {label}")
        if not cond and why:
            print(f"       {why}")
        return cond

    def _check(path: Path) -> Finding | None:
        return check_pdf(path, required=required, facts=facts)

    cases = [
        ("a 62%-fill page must FAIL", synth(8), True),
        ("a page filled to the floor with every job listed must PASS", synth(42), False),
        ("TWO pages must FAIL", synth(42, pages=2), True),
        ("current employer only under PROJECTS must FAIL",
         synth(42, employers=past), True),
        ("a PAST employer deleted must FAIL",
         synth(42, employers=current + past[1:]), True),
        ("job deleted while the same NAME survives under EDUCATION must still FAIL",
         synth(42, employers=[e for e in all_emps if e != past[0]],
               education_name=past[0]), True),
    ]
    for label, path, want_fail in cases:
        got = _check(path) is not None
        mark = "✓" if got == want_fail else "✗✗"
        if got != want_fail:
            ok = False
            f = _check(path)
            print(f"  {mark} {label}  -> {f.problems if f else 'passed'}")
        else:
            print(f"  {mark} {label}")
        path.unlink(missing_ok=True)

    ok &= _t("[facts] the fixture's canonical-facts block parses and is not empty",
             bool(facts["number"]) and bool(facts["exact"]),
             "the fixture text at the top of this file failed to parse — a bug in this script, "
             "not in any real résumé.")

    # ── END-TO-END: every rule must be provably ALIVE, on a synthetic fixture built entirely
    # in this function — never on whatever resume.html the real user has (or hasn't) written yet.
    import subprocess
    FIXTURE_HTML = f"""<html><body style="font-size:10pt; line-height:1.4; font-family:sans-serif;">
<h1>Jordan Rivera</h1>
<p>jordan.rivera@example.com · linkedin.com/in/jordanrivera · jordanrivera.example</p>
<h2>SKILLS</h2>
<p>Design systems, prototyping, accessibility, user research, cross-functional collaboration,
information architecture, interaction design, usability testing, stakeholder communication.</p>
<h2>EXPERIENCE</h2>
<div class="job"><b>{current[0]} — Staff Product Designer</b> — Mar 2024 – Present
<p>Shipped the fleet-ops console redesign, moving 1,070 DTCG tokens into one system.
Led the cross-functional discovery process, ran usability testing with 12 operators, and
partnered with engineering to ship the redesign in three phases. Reduced the average
time-to-complete a dispatch task by rebuilding the console's information architecture around
real operator workflows rather than the underlying data model. Established a weekly design
critique that raised the team's shipped-quality bar and cut rework by consolidating early
feedback before engineering handoff.</p></div>
<div class="job"><b>{past[0]} — Senior Product Designer</b> — Jun 2021 – Feb 2024
<p>Shipped a self-serve dashboard used across every enterprise account. Owned the design system
that kept the product consistent as the team scaled from 3 to 11 designers. Ran quarterly design
reviews and mentored two junior designers through their first shipped features. Partnered
directly with sales engineering to turn recurring customer feedback into a prioritized,
quarterly roadmap that closed the team's three largest usability gaps.</p></div>
<h2>SELECTED PROJECTS</h2>
<p>Fleet console v2, solo design and build. A side project exploring real-time collaborative
editing patterns for operational dashboards, built end to end over six weekends, from initial
research through a working prototype tested with five real operators.</p>
<h2>EDUCATION</h2>
<p>State University — B.A. Design, 2017–2021.</p>
<h2>CERTIFICATIONS</h2>
<p>Example Certification Body — Advanced Product Design, 2023. Second Certification Body —
Accessibility Fundamentals, 2022.</p>
<h2>ADDITIONAL</h2>
<p>Conference speaker, regional design meetup (2023, 2024). Volunteer design mentor, community
bootcamp program (2022–present).</p>
</body></html>"""
    # A regex-bounded removal of the WHOLE current-employer <div class="job">...</div> block, so
    # this stays correct even as the bullet text above changes — a fragile exact-string .replace()
    # on that prose silently matched nothing the first time this fixture's copy was edited, which
    # made this case pass for the wrong reason (nothing was removed, so of course nothing fired).
    project_credit_html = re.sub(
        rf'<div class="job"><b>{re.escape(current[0])}.*?</div>\s*', "", FIXTURE_HTML, count=1, flags=re.S
    ).replace(
        "<p>Fleet console v2, solo design and build.",
        f'<p>Fleet console v2 · {current[0]} · Mar 2024 &ndash; Present · solo build.',
    )
    e2e = [
        ("[e2e] a WRONG canonical number is CAUGHT",
         FIXTURE_HTML.replace("1,070 DTCG tokens", "900 DTCG tokens", 1)),
        ("[e2e] a WRONG exact value (email) is CAUGHT",
         FIXTURE_HTML.replace("jordan.rivera@example.com", "someone.else@example.org", 1)),
        ("[e2e] current job only as a dated PROJECT credit is CAUGHT",
         project_credit_html),
    ]
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for label, html in e2e:
            (tdp / "r.html").write_text(html)
            r = subprocess.run(["weasyprint", str(tdp / "r.html"), str(tdp / "r.pdf")],
                               capture_output=True)
            if r.returncode != 0:
                print(f"  · {label}  -> SKIPPED (weasyprint not available)")
                continue
            ok &= _t(label, _check(tdp / "r.pdf") is not None,
                     "This rule is DEAD: a résumé that violates it passed check_pdf.")
        (tdp / "ok.html").write_text(FIXTURE_HTML)
        r = subprocess.run(["weasyprint", str(tdp / "ok.html"), str(tdp / "ok.pdf")],
                           capture_output=True)
        if r.returncode == 0:
            ok &= _t("[e2e] the untouched fixture stays CLEAN through check_pdf",
                     _check(tdp / "ok.pdf") is None,
                     "The gate now fails honest copy, which trains people to ignore it.")

            try:
                import fitz as _fz

                def _synth(w, h, emps, pad_to=0.93):
                    d2 = _fz.open(); pg2 = d2.new_page(width=w, height=h); yy = 50
                    for _e, _s2, _c in emps:
                        pg2.insert_text((40, yy), f"{_e} - Designer  {_s2} - "
                                        f"{'Present' if _c else 'Feb 2024'}", fontsize=8); yy += 12
                    while yy < h * pad_to:
                        pg2.insert_text((40, yy), "body content line", fontsize=8); yy += 12
                    f2 = tdp / f"s{w}x{h}{len(emps)}.pdf"; d2.save(str(f2)); return f2

                ok &= _t("[e2e] a FULL A3 page is CAUGHT by page size alone",
                         _check(_synth(842, 1191, required)) is not None,
                         "The A4/Letter page-size rule is dead: an A3 prints as two sheets.")
                ok &= _t("[e2e] a FULL page missing the current job is CAUGHT by the employment rule",
                         _check(_synth(595, 842, [x for x in required if not x[2]])) is not None,
                         "The employment rule is dead on an otherwise-passing page.")

                def _footer_trick():
                    d4 = _fz.open(); pg4 = d4.new_page(width=595, height=842); yy = 50
                    for _e, _s4, _c in required:
                        pg4.insert_text((40, yy), f"{_e} - Designer  {_s4} - "
                                        f"{'Present' if _c else 'Feb 2024'}", fontsize=8); yy += 12
                    while yy < 842 * 0.65:
                        pg4.insert_text((40, yy), "body content line", fontsize=8); yy += 12
                    pg4.insert_text((40, 828), "References available on request", fontsize=7)
                    f4 = tdp / "footer.pdf"; d4.save(str(f4)); return f4

                ok &= _t("[e2e] a footer near the page bottom does NOT fake a full page",
                         _check(_footer_trick()) is not None,
                         "Fill is being measured from the lowest ink instead of where the body "
                         "ends, so one footer line makes a two-thirds-empty page read as full.")

                def _proj_only():
                    d3 = _fz.open(); pg3 = d3.new_page(width=595, height=842); yy = 50
                    for _e, _s3, _c in required:
                        if _c:
                            continue
                        pg3.insert_text((40, yy), f"{_e} - Designer  {_s3} - Feb 2024", fontsize=8); yy += 12
                    while yy < 842 * 0.80:
                        pg3.insert_text((40, yy), "body content line", fontsize=8); yy += 12
                    pg3.insert_text((40, yy), "SELECTED PROJECTS", fontsize=10); yy += 14
                    cur = next((x for x in required if x[2]), None)
                    if cur:
                        pg3.insert_text((40, yy), f"Fleet console · {cur[0]} · {cur[1]} - Present · solo build",
                                        fontsize=8); yy += 12
                    while yy < 842 * 0.93:
                        pg3.insert_text((40, yy), "more project detail", fontsize=8); yy += 12
                    f3 = tdp / "projonly.pdf"; d3.save(str(f3)); return f3

                ok &= _t("[e2e] a FULL page with the current job ONLY under SELECTED PROJECTS is CAUGHT",
                         _check(_proj_only()) is not None,
                         "The projects-scoping rule is dead: a dated project credit again counts as "
                         "employment.")

                ok &= _t("[e2e] an EMPTY required-employment list fails LOUD, never vacuously",
                         check_pdf(_synth(595, 842, required), required=[], facts=facts) is not None,
                         "A KB heading change silently disables the employment check entirely.")
            except ImportError:
                pass
        else:
            print("  · [e2e] fixture-based PDF checks  -> SKIPPED (weasyprint not available)")

    # A bonus, non-blocking check: if the user has already written a real résumé, prove it passes
    # its own gate too. This never gates selftest pass/fail — a fresh clone has no résumé yet.
    for candidate in sorted(REPO.glob("resume/*.pdf")):
        if candidate.is_file():
            f = check_pdf(candidate)
            if f:
                print(f"  · (bonus, non-blocking) your real résumé {candidate.name} currently fails "
                      f"this gate -> {f.problems}")
            else:
                print(f"  · (bonus, non-blocking) your real résumé {candidate.name} passes this gate")
            break

    print(f"\n{'SELFTEST OK' if ok else 'SELFTEST FAILED'} — {len(cases) + 1}+ cases, fully self-contained")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    paths = targets(args)
    print(f"resume_gate.py — {len(paths)} résumé PDF(s): one page, filled to {MIN_FILL:.0f}%, current employer listed as employment")
    print("  NOT checked: whether the content is TRUE (canon.py / verify_claims.py own that),")
    print("               whether it reads well, or whether it is tailored to the target.\n")
    if not paths:
        print("no résumé PDFs found")
        return 2
    findings = [f for f in ((check_html(p) if p.suffix.lower() == ".html" else check_pdf(p))
                            for p in paths) if f]
    if not findings:
        print(f"CLEAN — all {len(paths)} résumé(s) are one full page.")
        return 0
    print(f"{len(findings)} RÉSUMÉ(S) WASTING THE PAGE OR MISSING THE CURRENT JOB:\n")
    for f in findings:
        print(f"  {f.path}")
        for p in f.problems:
            print(f"      {p}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
