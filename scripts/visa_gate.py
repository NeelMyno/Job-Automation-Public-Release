#!/usr/bin/env python3
"""visa_gate.py — the work-authorization answer gate.

WHY THIS EXISTS
---------------
Work-authorization / sponsorship answers are the single highest-stakes category on a job
application: a wrong one isn't just a lost offer, it can be caught by a background check after
you've already started a job. Different employers phrase the same underlying question differently,
and the honest answer can differ by phrasing — "are you authorized to work without sponsorship"
and "will you ever need sponsorship" are not always the same yes/no for the same real person. Three
distinct question shapes recur across real ATS forms, and blurring them together is the defect this
gate exists to catch.

THE RULE IT ENFORCES (knowledge-base/12-application-answers.md §3)
--------------------------------------------------------------------
This script reads your own answers from a fenced ```work-authorization``` block in that file — it
does not hardcode anyone's specific situation. Fill in that block once, honestly, and this gate
checks every dossier's recorded answers against it. If the block isn't filled in yet, the gate says
so plainly and checks nothing, rather than silently assuming a default that might be wrong for you.

The three question classes:
  1. "Are you legally authorized to work in the United States?"                  -> authorized-now
  2. "Do you require sponsorship TO BEGIN employment / now / at time of hire?"    -> sponsorship-to-begin
  3. "Will you NOW OR IN THE FUTURE require sponsorship?"                        -> sponsorship-now-or-future

A fourth class, "authorized to work WITHOUT RESTRICTION" (no sponsorship word, no timeframe word),
is a rephrasing of #1 whose honest answer depends on whether your authorization is itself tied to a
specific status/employer (see the `restricted-authorization` key in the same KB block) — it is NOT
simply the opposite of your #1 answer, which is exactly the subtlety a naive "just invert it" rule
gets wrong for some users and not others.

USAGE
    python3 scripts/visa_gate.py                     # every applications/*/application.md
    python3 scripts/visa_gate.py <path> ...          # specific files (used by the hook)
    python3 scripts/visa_gate.py --selftest          # a fixed, fictional regression suite
Exit 0 = clean (or not yet configured — see below). Exit 1 = at least one wrong or missing answer.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KB_ANSWERS = REPO / "knowledge-base" / "12-application-answers.md"

# --- question classification --------------------------------------------------------------
# Order matters: FUTURE is tested first, because "now or in the future" also contains "now",
# and mis-routing #3 to the #2 rule is exactly the blur this gate exists to prevent.

FUTURE = re.compile(
    r"now\s*(?:,|/|\s)?\s*or\s*(?:at\s+any\s+point\s+)?in\s+the\s+future"
    r"|now\s*/\s*(?:some\s?day|later|future)"
    r"|(?:ever|at any (?:time|point))\s+(?:need|require)"
    r"|future\w*\s+(?:need|require|sponsor)"
    r"|(?:need|require)\w*[^.?\n]{0,40}(?:in\s+the\s+future|future\s+immigration)",
    re.I,
)
BEGIN = re.compile(
    r"(?:to\s+begin|to\s+commence|to\s+start|at\s+the\s+time\s+of\s+hire|at\s+hire|"
    r"for\s+this\s+position|currently|right\s+now|to\s+work\s+for\s+us\s+now)",
    re.I,
)
SPONSOR = re.compile(r"\bsponsor\w*|\bvisa\s+(?:status|support)|\bH-?1B\s+sponsor", re.I)
AUTHORIZED = re.compile(r"legally\s+authoriz|authoriz\w*\s+to\s+work|work\s+authoriz", re.I)

# An answer token, bound tightly to its question. A loose "any nearby yes/no" regex produces a lot
# of false positives against real dossier prose, so only two shapes count as a recorded answer:
#   **Yes** / **No**              the canonical bold token
#   Submitted answer: NO          an explicit label
ANSWER = re.compile(
    r"\*\*(yes|no)\*\*"
    r"|\b(?:answer|selected|submitted|chose|response)\b\s*[:\-]?\s*\*{0,2}(yes|no)\b",
    re.I,
)

# Multi-question lines are real and common: "Worked here before: **No** · Authorized: **Yes**".
# Matching across the whole line pairs the wrong question with the wrong answer.
SEGMENT = re.compile(r"\s+·\s+|\s*\|\s*")

# Conditional analysis is not a recorded answer. "If their form asks only about starting, my honest
# answer is **No**" is correct reasoning about a form, not a value that was submitted.
CONDITIONAL = re.compile(r"\bif\b[^.\n]{0,60}\b(?:asks?|uses?|phrases?|offers?|form)\b", re.I)

# A bold token that is a QUOTED OPTION is the employer's wording, not your answer.
QUOTED_OPTION = re.compile(r"\*\*\s*[\"“]")

Q_AUTH, Q_BEGIN, Q_FUTURE = "authorized-now", "sponsorship-to-begin", "sponsorship-now-or-future"
SEVERITY = {Q_AUTH: "HIGH", Q_BEGIN: "HIGH", Q_FUTURE: "CRITICAL"}

# Some employers ask the inverse: "Are you authorized to work WITHOUT sponsorship, now or in the
# future?" or "...without restriction?" A gate that demands a lie is worse than no gate at all, so
# every inverted phrasing is handled explicitly rather than assumed away.
INVERTED = re.compile(
    r"without\s+(?:requiring\s+)?(?:visa\s+)?sponsor\w*"
    r"|without\s+restriction"
    r"|(?:do\s+)?not\s+(?:require|need)\s+(?:visa\s+)?sponsor\w*"
    r"|no\s+sponsorship\s+(?:is\s+)?(?:required|needed)",
    re.I,
)

# "The form never asked" is a RECORD, not a gap. A dossier that states plainly that no
# work-authorization question was on the form is reporting a positive, checkable fact about the
# form — treating that as a missing answer trains people to stop trusting the gate.
NO_QUESTION = re.compile(
    r"(?:\bno\b|\bnot\s+present\b|\bnone\b|\babsent\b|\bdid\s*n[o']?t\s+ask\b|\bdoes\s+not\s+ask\b)"
    r"[^.\n]{0,60}?"
    r"(?:visa|work[-\s]?auth\w*|sponsorship|immigration)"
    r"[^.\n]{0,40}?"
    r"(?:question|section|field|prompt)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship)[^.\n]{0,30}?(?:question|section|field)s?\s*[:\-][^.\n]{0,40}?"
    r"(?:\bnot\s+present\b|\bnone\b|\bno\b|\bn/a\b)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship|immigration)[^.\n]{0,30}?[:\-—][^.\n]{0,20}?"
    r"(?:\bno\b|\bnone\b|\bwithout\b|\bnot\b)[^.\n]{0,20}?(?:question|section|field|prompt)",
    re.I,
)

# The citizenship phrasing of the same underlying question — "Are you a US Citizen or Green Card
# holder?" — is a work-authorization record even though it names neither "visa" nor "sponsor".
CITIZENSHIP = re.compile(r"\b(?:u\.?s\.?\s+)?citizen(?:ship)?\b|\bgreen\s*card\b|\bpermanent\s+resident\b", re.I)

# --- an already-shipped answer you've decided not to correct -------------------------------
# This does NOT relax the gate and CANNOT be used to pre-authorize a wrong answer. It exists for
# one shape only: an application that is ALREADY SUBMITTED, whose recorded answer contradicts your
# own KB §3, where the only remaining question is whether to go back and correct the employer's
# record — a call that belongs to you and to nobody else.
#
# Four walls, each pinned by a selftest case:
#   1. The marker must name an ADR, so the decision is auditable and attached to a written record.
#   2. It only applies where the dossier records a SUBMITTED application — an unsent form's wrong
#      answer can never be pre-authorized.
#   3. It is LINE-SCOPED (the flagged line, or the line right after) — it can never blanket a file.
#   4. The finding still PRINTS, as an acknowledged note carrying its ADR. Nothing goes silent.
#
#     <!-- visa:decided ADR-0007 — my call 2026-01-01: not correcting the submitted answer -->
DECIDED = re.compile(r"<!--\s*visa:decided\s+(ADR-\d{4})\s*(?:—|--|-)\s*(.*?)\s*-->", re.I)
SUBMITTED = re.compile(r"\b(?:SUBMITTED|✅\s*Applied|applied[_ ]on\s*:\s*20\d\d-)")


def load_expected() -> dict | None:
    """Read your own EXPECTED/RATIONALE/restricted-authorization values from the KB file.

    Returns None if the file is missing or the fenced block isn't (fully) filled in yet — the
    caller must treat that as "not configured", never as license to guess a default.
    """
    if not KB_ANSWERS.is_file():
        return None
    text = KB_ANSWERS.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"```work-authorization\n(.*?)```", text, re.S)
    if not m:
        return None
    expected: dict[str, str] = {}
    rationale: dict[str, str] = {}
    restricted: bool | None = None
    key_map = {
        "authorized-now": Q_AUTH,
        "sponsorship-to-begin": Q_BEGIN,
        "sponsorship-now-or-future": Q_FUTURE,
    }
    placeholder = re.compile(r"^\[.*\]$")
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        val, _, reason = rest.strip().partition("|")
        val = val.strip().upper()
        reason = reason.strip()
        if placeholder.match(val) or val not in ("YES", "NO"):
            continue  # still a template placeholder like "[YES/NO]" — not filled in
        if key in key_map:
            expected[key_map[key]] = val
            rationale[key_map[key]] = reason or "(no reason recorded — add one in the KB file)"
        elif key == "restricted-authorization":
            restricted = val == "YES"
    if len(expected) < 3 or restricted is None:
        return None
    return {"expected": expected, "rationale": rationale, "restricted": restricted}


def classify(question: str) -> tuple[str, bool] | None:
    """(question kind, inverted?) or None if this isn't a work-authorization question.

    `inverted` means the question asks the negative ("authorized WITHOUT sponsorship" / "WITHOUT
    restriction"), so the expected answer needs special handling — see `expected_answer()`.
    """
    has_sponsor = bool(SPONSOR.search(question))
    inv = bool(INVERTED.search(question))
    if has_sponsor and FUTURE.search(question):
        return Q_FUTURE, inv
    if has_sponsor and BEGIN.search(question):
        return Q_BEGIN, inv
    if AUTHORIZED.search(question) and (not has_sponsor or inv):
        # "Authorized to work WITHOUT sponsorship" is the sponsorship question wearing an
        # authorization coat, so route it by its timeframe. But "authorized to work WITHOUT
        # RESTRICTION", with no sponsorship word and no timeframe, is the *authorization* question
        # itself, inverted — and its honest answer depends on whether your authorization is tied to
        # a specific status (see `restricted-authorization` in the KB block), not on flipping your
        # plain authorized-now answer.
        if inv and (has_sponsor or BEGIN.search(question)):
            return Q_BEGIN, True
        return Q_AUTH, inv
    if has_sponsor and re.search(r"require|need", question, re.I):
        # Sponsorship asked with no timeframe. Treat as the strictest question: the safe reading of
        # an ambiguous sponsorship question is the one that cannot become a lie.
        return Q_FUTURE, inv
    return None


def expected_answer(kind: str, inverted: bool, cfg: dict) -> str:
    """The honest answer for this (kind, inverted) pair, given the user's own configured facts."""
    if kind == Q_AUTH and inverted:
        # The "without restriction" phrasing — not a flip of the plain authorized-now answer, a
        # direct read of whether your authorization is itself restricted.
        return "NO" if cfg["restricted"] else "YES"
    want = cfg["expected"][kind]
    if inverted:
        want = "NO" if want == "YES" else "YES"
    return want


@dataclass
class Finding:
    path: str
    line_no: int
    kind: str
    got: str
    text: str
    expected: str
    rationale: str
    decided: tuple[str, str] | None = None

    def render(self) -> str:
        snippet = self.text.strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        if self.decided:
            adr, why = self.decided
            return (
                f"  [DECIDED] {self.path}:{self.line_no}  ({self.kind})\n"
                f"      recorded: {self.got}   rule says: {self.expected}\n"
                f"      line:     {snippet}\n"
                f"      decision: {adr} — {why}\n"
                f"      status:   already submitted; you've ruled on it. Not open work, and not a "
                f"precedent for any unsent form."
            )
        return (
            f"  [{SEVERITY[self.kind]}] {self.path}:{self.line_no}  ({self.kind})\n"
            f"      recorded: {self.got}   required: {self.expected}\n"
            f"      line:     {snippet}\n"
            f"      why:      {self.rationale}"
        )


def _answer_in(segment: str, is_continuation: bool = False) -> str | None:
    """The recorded answer inside ONE question segment, or None if this is not a record."""
    if CONDITIONAL.search(segment) or QUOTED_OPTION.search(segment):
        return None
    tail = segment
    if not is_continuation:
        q = segment.find("?")
        cut = q if q != -1 else segment.find(":")
        if cut != -1 and cut < len(segment) - 1:
            tail = segment[cut + 1:]
    hits = [next(g for g in m.groups() if g).upper() for m in ANSWER.finditer(tail)]
    if len(set(hits)) != 1:
        return None
    return hits[0]


def _decision_on(lines: list[str], i: int, is_submitted: bool) -> tuple[str, str] | None:
    if not is_submitted:
        return None
    for j in (i, i + 1):
        if 0 <= j < len(lines):
            m = DECIDED.search(lines[j])
            if m and m.group(2).strip() and _adr_exists(m.group(1)):
                return m.group(1).upper(), m.group(2).strip()
    return None


def _adr_exists(adr: str) -> bool:
    """The named ADR must actually be on disk — a well-formed but invented id must not count."""
    num = adr.split("-")[-1]
    return any((REPO / "ops" / "decisions").glob(f"{num}-*.md"))


def scan_text(rel: str, text: str, cfg: dict) -> list[Finding]:
    out: list[Finding] = []
    lines = text.splitlines()
    is_submitted = bool(SUBMITTED.search(text))
    for i, line in enumerate(lines):
        if not (SPONSOR.search(line) or AUTHORIZED.search(line)):
            continue
        segs = SEGMENT.split(line)
        if line.lstrip().startswith("|") and sum(1 for s in segs if classify(s)) <= 1:
            segs = [line]
        for seg in segs:
            c = classify(seg)
            if c is None:
                continue
            kind, inverted = c
            got = _answer_in(seg)
            if got is None:
                if seg.strip() == line.strip() and i + 1 < len(lines):
                    got = _answer_in(lines[i + 1], is_continuation=True)
            if got is None:
                continue
            want = expected_answer(kind, inverted, cfg)
            if got != want:
                out.append(Finding(rel, i + 1, kind, got, line, want, cfg["rationale"].get(kind, ""),
                                   _decision_on(lines, i, is_submitted)))
    return out


def coverage_gap(rel: str, text: str) -> str | None:
    """A submitted application with NO recorded work-authorization answer at all."""
    if not SUBMITTED.search(text):
        return None
    if SPONSOR.search(text) or AUTHORIZED.search(text):
        return None
    if NO_QUESTION.search(text):
        return None
    if CITIZENSHIP.search(text) and ANSWER.search(text):
        return None
    return f"  [HIGH] {rel}  (no-record)\n      This dossier records a SUBMITTED application and " \
           f"contains NO work-authorization answer at all. Unverifiable, and that's a defect on its own."


def targets() -> list[Path]:
    return sorted(REPO.glob("applications/*/application.md"))


# --- selftest -------------------------------------------------------------------------------
# A fixed, self-contained fictional configuration — the selftest never reads the real KB file, so
# it works identically on a fresh clone before anyone has filled in their own answers.
_TEST_CFG = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "YES"},
    "rationale": {
        Q_AUTH: "example: authorized to work today under the fixture's assumed status.",
        Q_BEGIN: "example: no sponsorship needed to start.",
        Q_FUTURE: "example: will need sponsorship eventually — this answer never flips.",
    },
    "restricted": True,
}

CASES: list[tuple[str, str, bool]] = [
    ("hard-stop answered correctly",
     "- Will you now or in the future require sponsorship for employment visa status? **Yes**", False),
    ("hard-stop flipped to No — the lie this gate exists to stop",
     "- Will you now or in the future require sponsorship for employment visa status? **No**", True),
    ("'to begin' answered No — correct and must NOT fire",
     "- Do you require sponsorship to begin employment with us? **No**", False),
    ("'to begin' answered Yes — the self-inflicted knockout",
     "- Do you require sponsorship to begin employment? **Yes**", True),
    ("'at the time of hire' answered No — correct",
     "- Will you require visa sponsorship at the time of hire? **No**", False),
    ("authorized-now answered Yes — correct",
     "- Are you legally authorized to work in the United States? **Yes**", False),
    ("authorized-now answered No — false per the fixture config",
     "- Are you legally authorized to work in the United States? **No**", True),
    ("bare sponsorship question with no timeframe answered No — read as the hard stop",
     "- Do you require sponsorship? **No**", True),
    ("answer on the following line",
     "- Will you now or in the future require sponsorship?\n  Submitted answer: No", True),
    ("a prose mention with no recorded answer must NOT fire here",
     "Read your own KB before filling in any sponsorship question.", False),
    ("the correct three-way summary line must NOT fire",
     "- Authorized to work in the US? **Yes** · Require sponsorship now/future? **Yes**", False),
    ("a correct answer in the 2nd segment of a multi-question line",
     "- Worked here before: **No** · Currently authorized to work: **Yes**", False),
    ("conditional analysis of what a form might ask, not a submitted value",
     'If the form asks only about **starting**, the honest answer is **No**. If it uses the '
     '**"now or in the future"** phrasing, the honest **Yes** applies instead.', False),
    ("a stray ': no' inside a trailing quoted note, never an answer",
     '- Work authorization (single merged question): **"my status requires a renewal or sponsorship '
     'now or in the future"** — exactly true. NOTE: no separate authorized-now/sponsorship pair '
     "on this form.", False),
    ("the employer's quoted option text is not the candidate's answer",
     '| 9 | "Your authorization to work..." | 🔴 **"I am authorized to work in the country '
     'based on a valid work permit and do not need a company to sponsor my visa"** |', False),
    ("an honest free-text paragraph containing the words 'no sponsorship'",
     "> I am authorized to work in the US now, with no sponsorship or cost to you, and can start "
     "immediately.", False),
    ("prose describing what the form does NOT ask",
     'This ATS does **not** ask the usual "are you authorized to work in the United States?" It asks '
     "you to pick the closest statement.", False),
    ("inverted question, honest answer No given restricted=True — must NOT fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **No**", False),
    ("inverted question answered Yes — this IS the lie and MUST fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **Yes**", True),
    ("inverted 'without restriction' answered No — matches restricted=True, must NOT fire",
     "- Are you authorized to work in the U.S. without restriction? **No**", False),
    ("inverted 'without restriction' answered Yes — contradicts restricted=True, MUST fire",
     "- Are you authorized to work in the U.S. without restriction? **Yes**", True),
    ("inverted, to-begin timeframe, honest Yes — must NOT fire",
     "- Can you begin work without requiring sponsorship? **Yes**", False),
    ("a wrong answer inside a markdown table row must fire",
     "| 7 | Will you now or in the future require sponsorship? | **No** |", True),
    ("a right answer inside a markdown table row must NOT fire",
     "| 7 | Will you now or in the future require sponsorship? | **Yes** |", False),
]

COVERAGE_CASES: list[tuple[str, str, bool]] = [
    ("a SUBMITTED dossier with no work-authorization answer at all",
     "# Some Co — Some Role\nStatus: SUBMITTED 2026-01-01\nResume: resume.pdf (241kb)\n", True),
    ("a not-yet-applied dossier with no answer is fine",
     "# Some Co\nStatus: dossier built, NOT APPLIED\n", False),
    ("a SUBMITTED dossier that records the answers is fine",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- Require sponsorship now or in the future? **Yes**\n", False),
    ("the form carried no work-authorization question, and the dossier says so",
     "**✅ SUBMITTED 2026-01-01.** Success panel seen.\n"
     "- **No visa question on this form.** No EEO/demographic section either.\n", False),
    ("the same declaration, colon form",
     "- **Status:** **SUBMITTED 2026-01-01** — success banner seen.\n"
     "- Visa/EEO questions: **not present on this form**\n", False),
    ("the CITIZENSHIP phrasing of the question, answered honestly",
     "- **Status:** **SUBMITTED 2026-01-01**.\n"
     "- Are you a US Citizen or Green Card holder? **No**\n", False),
    ("a SUBMITTED dossier merely CONTAINING the word visa is still a gap",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- Their visa policy is described on the careers page.\n", True),
    ("an unanswered citizenship mention is still a gap",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- The form may ask about citizenship.\n", True),
]

_GOOD_Q = "- **Require this employer to sponsor work authorization now/someday? Submitted answer: NO**"
_MARK = "<!-- visa:decided ADR-0001 — my call 2026-01-01: not correcting the submitted answer -->"

DECISION_CASES: list[tuple[str, str, bool, bool]] = [
    ("a wrong-answer line, SUBMITTED + marked -> still found, downgraded to DECIDED",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n{_MARK}\n", True, True),
    ("the marker on the SAME line also works",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q} {_MARK}\n", True, True),
    ("WALL 2 — NOT submitted: the marker is ignored and it stays a full finding",
     f"Status: dossier built, not yet applied\n{_GOOD_Q}\n{_MARK}\n", True, False),
    ("WALL 1 — no ADR named: not a decision, stays a full finding",
     "Status: SUBMITTED 2026-01-01\n" + _GOOD_Q +
     "\n<!-- visa:decided because I said so -->\n", True, False),
    ("WALL 1 — an ADR but no reason: stays a full finding",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n<!-- visa:decided ADR-0001 —  -->\n", True, False),
    ("WALL 3 — line-scoped: a marker up top does NOT cover a wrong answer further down",
     f"Status: SUBMITTED 2026-01-01\n{_MARK}\n\n- Filler line.\n- Filler line.\n{_GOOD_Q}\n", True, False),
    ("a correct answer with a marker present is still no finding at all",
     f"Status: SUBMITTED 2026-01-01\n- Now or in the future require sponsorship? **Yes**\n{_MARK}\n",
     False, False),
    ("WALL 1b — an INVENTED ADR id must not satisfy the wall",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n<!-- visa:decided ADR-9999 — made up -->\n", True, False),
]


def selftest() -> int:
    passed = failed = 0
    print("visa_gate.py selftest — a fixed fictional configuration, independent of any real KB file\n")
    for label, text, should in CASES:
        got = bool(scan_text("t.md", text, _TEST_CFG))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    for label, text, should in COVERAGE_CASES:
        got = coverage_gap("t.md", text) is not None
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    for label, text, want_find, want_decided in DECISION_CASES:
        fs = scan_text("t.md", text, _TEST_CFG)
        got_find = bool(fs)
        got_decided = bool(fs and fs[0].decided)
        ok = got_find == want_find and got_decided == want_decided
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if ok:
            mark = "✓ DECIDED " if want_decided else ("✓ CAUGHT  " if want_find else "✓ allowed ")
        else:
            mark = "✗ WRONG   "
        print(f"  {mark}  {label}")
    print()
    # Configuration-loading itself, independent of the fixed test config above.
    load_ok = load_expected() is None or isinstance(load_expected(), dict)
    passed, failed = (passed + 1, failed) if load_ok else (passed, failed + 1)
    print(f"  {'✓' if load_ok else '✗'} CONFIG    load_expected() runs cleanly on the real repo "
          f"(configured or not — both are valid states)")
    if failed:
        print(f"\nSELFTEST FAILED — {failed} of {passed + failed} wrong")
        return 1
    print(f"\nSELFTEST OK — {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    paths = [Path(a) if Path(a).is_absolute() else REPO / a for a in args] if args else targets()

    cfg = load_expected()
    if cfg is None:
        print("visa_gate.py — knowledge-base/12-application-answers.md §3 is not filled in yet.")
        print("  Nothing was checked. Fill in the ```work-authorization``` block in that file before")
        print("  relying on this gate — see SETUP.md.")
        return 0

    findings: list[Finding] = []
    gaps: list[str] = []
    checked = 0
    for p in paths:
        if not p.is_file():
            continue
        checked += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        findings.extend(scan_text(rel, text, cfg))
        g = coverage_gap(rel, text)
        if g:
            gaps.append(g)

    print(f"visa_gate.py — checked {checked} file(s) against knowledge-base/12-application-answers.md §3")
    print(f"  authorized-now = {cfg['expected'][Q_AUTH]} · sponsorship-to-begin = {cfg['expected'][Q_BEGIN]} "
          f"· now-or-in-the-future = {cfg['expected'][Q_FUTURE]}")
    print("  NOT checked: what was actually clicked in the browser. This reads the RECORD only —")
    print("               a correct record and a wrong radio button still diverge.")
    decided = [f for f in findings if f.decided]
    open_findings = [f for f in findings if not f.decided]

    if not open_findings and not gaps:
        print("\nCLEAN — every recorded work-authorization answer matches your configured rule.")
        if decided:
            print(f"\n{len(decided)} ANSWER(S) ALREADY SUBMITTED AND RULED ON "
                  f"(shown for the record; not open work):\n")
            for f in decided:
                print(f.render())
                print()
        return 0
    if open_findings:
        print(f"\n{len(open_findings)} WRONG ANSWER(S):\n")
        for f in sorted(open_findings, key=lambda x: 0 if SEVERITY[x.kind] == "CRITICAL" else 1):
            print(f.render())
            print()
    if decided:
        print(f"{len(decided)} ALREADY SUBMITTED AND RULED ON (not open work):\n")
        for f in decided:
            print(f.render())
            print()
    if gaps:
        print(f"{len(gaps)} SUBMITTED APPLICATION(S) WITH NO RECORDED ANSWER:\n")
        for g in gaps:
            print(g)
            print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
