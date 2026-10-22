#!/usr/bin/env python3
"""visa_gate.py: the work-authorization answer gate.

WHY THIS EXISTS
---------------
Work-authorization / sponsorship answers are the single highest-stakes category on a job
application: a wrong one isn't just a lost offer, it can be caught by a background check after
you've already started a job. Different employers phrase the same underlying question differently,
and the honest answer can differ by phrasing: "are you authorized to work without sponsorship"
and "will you ever need sponsorship" are not always the same yes/no for the same real person. Three
distinct question shapes recur across real ATS forms, and blurring them together is the defect this
gate exists to catch.

THE RULE IT ENFORCES (knowledge-base/12-application-answers.md §3)
--------------------------------------------------------------------
This script reads your own answers from a fenced ```work-authorization``` block in that file; it
does not hardcode anyone's specific situation. Fill in that block once, honestly, and this gate
checks every dossier's recorded answers against it. If the block isn't filled in yet, the gate says
so plainly and checks nothing, rather than silently assuming a default that might be wrong for you.

The three question classes:
  1. "Are you legally authorized to work in the United States?"                  -> authorized-now
  2. "Do you require sponsorship TO BEGIN employment / now / at time of hire?"    -> sponsorship-to-begin
  3. "Will you NOW OR IN THE FUTURE require sponsorship?"                        -> sponsorship-now-or-future

A fourth class, "authorized to work WITHOUT RESTRICTION" (no sponsorship word, no timeframe word),
is a rephrasing of #1 whose honest answer depends on whether your authorization is itself tied to a
specific status/employer (see the `restricted-authorization` key in the same KB block); it is NOT
simply the opposite of your #1 answer, which is exactly the subtlety a naive "just invert it" rule
gets wrong for some users and not others.

TWO OPTIONAL MAPPINGS IN THE SAME BLOCK (both yours, both off until you write them)
  * `also-accept`: a third `|` field on a class line, e.g.
        sponsorship-now-or-future: NO | reason | also-accept: YES
    Your answer for that class changed, and you decided NOT to edit dossiers already built or forms
    already submitted. The gate then accepts the old answer on records, while the configured answer
    stays the one an agent types on every new form (the fill step's read-back enforces that).
  * `wording`: a question printed a particular way gets its own answer, because the honest answer
    follows the question AS PRINTED, e.g.
        wording: renewal of your employment authorization; training plan => YES | reason
    Phrases are separated by `;` and matched case-insensitively against the question text only. When
    one matches a work-authorization question, its answer is required there as printed (no polarity
    flip), and the plain class answer still governs every other wording.

NOT CONFIGURED YET (a fresh clone)
  The gate says so plainly and never crashes. When no file it was given records a
  work-authorization answer, it exits 3 (NOT CHECKED): nothing was verified, so it must never
  exit 0, which a reader or a hook would take as proof. If any file DOES record an answer, that
  answer cannot be checked, and the gate exits 1 (UNVERIFIED).

THE RECORD SHAPE (applications/TEMPLATE-company-role/application.md, .claude/rules/records-format.md §6)
    - "<question exactly as printed>" → Yes
  Also read: `-> No`, `=> Yes`, `= No`, `: Yes`, a trailing bare `? Yes`, and `**Yes**`, bold or not.
  A question line under an answers heading, or one with an answer separator, whose Yes/No cannot be
  read is UNVERIFIED (exit 1), never clean.

USAGE
    python3 scripts/visa_gate.py                     # every applications/*/application.md
    python3 scripts/visa_gate.py <path> ...          # specific files (used by the hook)
    python3 scripts/visa_gate.py --selftest          # a fixed, fictional regression suite
Exit 0 = clean: every recorded answer was checked against your configured rule. Exit 1 = at least
one wrong or missing answer, a recorded answer whose Yes/No the gate cannot read (UNVERIFIED), or
recorded answers that cannot be checked because §3 is not filled in. Exit 3 = NOT CHECKED: §3 is not filled in yet and nothing recorded needs it (a fresh clone).
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
    # Present-tense / start-of-employment phrasings whose honest answer is typically No (many
    # statuses cover an immediate start at no extra cost to the employer). "to work for <company>"
    # and "at time of hire" (no "the") were originally missing, so present-tense questions like
    # "...to work for us now?" or "Do you now / at time of hire require sponsorship?" fell through
    # to the FUTURE hard-stop catch-all and a correct No was flagged as a violation. FUTURE is
    # tested first, so a question that also says "now or in the future" still routes to class 3.
    r"(?:to\s+begin|to\s+commence|to\s+start|at\s+(?:the\s+)?time\s+of\s+hire|at\s+hire|"
    r"for\s+this\s+(?:position|role)|currently|right\s+now|now\s+(?:require|need)\b|"
    r"to\s+work\s+for\b|to\s+be\s+employed|to\s+join)",
    # "now require/need" is the present-tense "Will you NOW require sponsorship?" (question class 2,
    # honest answer usually No). It cannot swallow the future question: FUTURE is tested first and
    # owns "now or in the future", and this pattern needs "now" immediately followed by require/need,
    # so "now or …" never matches it. Also fixes a table row where the "now" was bolded, which broke
    # once the classifier stopped reading the answer annotation that followed the question.
    re.I,
)
SPONSOR = re.compile(r"\bsponsor\w*|\bvisa\s+(?:status|support)|\bH-?1B\s+sponsor", re.I)
AUTHORIZED = re.compile(r"legally\s+authoriz|authoriz\w*\s+to\s+work|work\s+authoriz", re.I)

# An answer token, bound tightly to its question. A loose "any nearby yes/no" regex produces a lot
# of false positives against real dossier prose. Shapes that count as a recorded answer:
#   **Yes** / **No**                       the canonical bold token
#   **No.** / **Yes,**                     trailing punctuation inside the bold
#   **"Yes, work authorization on file"**  a QUALIFIED answer that leads with yes/no, common on
#                                          dropdowns that need a literal status name attached. A
#                                          dropdown OPTION LIST like `**"Yes"** / **"No"**` still
#                                          yields BOTH yes and no, which the contradictory-hits
#                                          check in `_answer_in` rejects as no unambiguous record.
#   Submitted answer: NO                   an explicit label
ANSWER = re.compile(
    # A bare, short bold answer, allowing trailing punctuation inside the bold (e.g. **No.**).
    # Kept short on purpose: it must NOT read "No" out of a bold RECORD like
    # **No work-authorization / visa / sponsorship question.** - there "No" is followed by a noun,
    # so `\s*[punct]*\s*\*\*` cannot reach the closing `**` and the match fails.
    r'\*\*\s*(yes|no)\s*[.,;:!?)\"“”\'’]*\s*\*\*'
    # A QUALIFIED/QUOTED answer whose yes/no sits right after the opening quote - the real shape
    # above, and the case where a WRONG hard-stop answer is written as a quoted option (e.g.
    # **"No, I will not need sponsorship"**). A quoted QUESTION (**"Do you require…?"**) does NOT
    # start with yes/no, so it is not read here.
    r'|\*\*\s*[\"“”\'’]\s*(yes|no)\b'
    r'|\b(?:answer|selected|submitted|chose|response)\b\s*[:\-]?\s*\*{0,2}[\"“”\'’]?\s*(yes|no)\b'
    # A separator answer: `"question?" → Yes`, `-> No`, `=> Yes`, `= No`, `: Yes`, bold or not. The
    # yes/no must end its phrase (end of text, punctuation, a bracket or a dash), so prose such as
    # "NOTE: no separate question" or "Yes / No" (an option list) is never read as an answer.
    r'|(?:→|->|=>|=|:)\s*\*{0,2}\s*[\"“”\'’]?\s*(yes|no)\b'
    r'(?=\s*(?:[.,;:!?)(\]\-\u2013\u2014*\"“”\'’|]|$))'
    # A trailing bare answer: `- Do you require sponsorship? Yes` (a table cell `| No |` too).
    r'|(?<![*\w])(yes|no)\s*[.!]?\s*\|?\s*$',
    re.I,
)

# A separator that says "the answer follows" (the template's canonical `"question" → answer` shape).
ANSWER_SLOT = re.compile(r"→|->|=>|\b(?:answer|selected|submitted|chose|response)\s*[:=]", re.I)
# A heading for the block of answers as filled. A question line under it is a recorded answer, so an
# answer the gate cannot read there is UNVERIFIED, never silently passed.
ANSWERS_HEADING = re.compile(r"^\s*#{1,6}\s.*\banswers?\b", re.I)

# Multi-question lines are real and common: "Worked here before: **No** · Authorized: **Yes**".
# Matching across the whole line pairs the wrong question with the wrong answer. The `;` separator
# was added after a real multi-dropdown line: `"restrictions?"=**No**; **"...sponsorship...?" =
# "Yes,..."**; "country?"=**United States**` - split on nothing, so the cut-at-first-`?` landed on the
# RESTRICTIONS question and read its **No** as the sponsorship answer, a false violation on the
# highest-severity class.
SEGMENT = re.compile(r"\s+·\s+|\s*\|\s*|\s*;\s*|\.\s+(?=[\"“])")

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
    # "without [the need for] [any] [employer/visa] sponsorship" - a real employer's phrasing,
    # "without the need for sponsorship", slipped the earlier narrower regex (which only allowed
    # "without (requiring) (visa) sponsor"), so an honest No was flagged as a violation and the gate
    # demanded the answer be flipped to a lie.
    # "without employer-sponsored visa support" slipped it too: the hyphen in "employer-sponsored"
    # broke `employer\s+`, so an honest No read as the hard-stop question answered No.
    r"without\s+(?:the\s+)?(?:need\s+for\s+)?(?:any\s+)?(?:requiring\s+)?(?:an?\s+)?(?:employer[\s-]+|visa[\s-]+)?sponsor\w*"
    r"|without\s+restriction"
    r"|fine\s+without\b"
    r"|(?:do\s+)?not\s+(?:require|need)\s+(?:visa\s+)?sponsor\w*"
    r"|no\s+need\s+for\s+(?:visa\s+)?sponsor\w*"
    r"|no\s+sponsorship\s+(?:is\s+)?(?:required|needed)",
    re.I,
)

# "The form never asked" is a RECORD, not a gap. A dossier that states plainly that no
# work-authorization question was on the form is reporting a positive, checkable fact about the
# form; treating that as a missing answer trains people to stop trusting the gate.
NO_QUESTION = re.compile(
    r"(?:\bno\b|\bnot\s+present\b|\bnone\b|\babsent\b|\bdid\s*n[o']?t\s+ask\b|\bdoes\s+not\s+ask\b)"
    r"[^.\n]{0,60}?"
    r"(?:visa|work[-\s]?auth\w*|sponsorship|immigration)"
    r"[^.\n]{0,40}?"
    r"(?:question|section|field|prompt|phrasing)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship)[^.\n]{0,30}?(?:question|section|field)s?\s*[:\-][^.\n]{0,40}?"
    r"(?:\bnot\s+present\b|\bnone\b|\bno\b|\bn/a\b)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship|immigration)[^.\n]{0,30}?[:\-\u2014][^.\n]{0,20}?"
    r"(?:\bno\b|\bnone\b|\bwithout\b|\bnot\b)[^.\n]{0,20}?(?:question|section|field|prompt)",
    re.I,
)

# The citizenship phrasing of the same underlying question ("Are you a US Citizen or Green Card
# holder?") is a work-authorization record even though it names neither "visa" nor "sponsor".
CITIZENSHIP = re.compile(r"\b(?:u\.?s\.?\s+)?citizen(?:ship)?\b|\bgreen\s*card\b|\bpermanent\s+resident\b", re.I)

# --- an already-shipped answer you've decided not to correct -------------------------------
# This does NOT relax the gate and CANNOT be used to pre-authorize a wrong answer. It exists for
# one shape only: an application that is ALREADY SUBMITTED, whose recorded answer contradicts your
# own KB §3, where the only remaining question is whether to go back and correct the employer's
# record: a call that belongs to you and to nobody else.
#
# Four walls, each pinned by a selftest case:
#   1. The marker must name an ADR, so the decision is auditable and attached to a written record.
#   2. It only applies where the dossier records a SUBMITTED application; an unsent form's wrong
#      answer can never be pre-authorized.
#   3. It is LINE-SCOPED (the flagged line, or the line right after); it can never blanket a file.
#   4. The finding still PRINTS, as an acknowledged note carrying its ADR. Nothing goes silent.
#
#     <!-- visa:decided ADR-0007 - my call 2026-01-01: not correcting the submitted answer -->
DECIDED = re.compile(r"<!--\s*visa:decided\s+(ADR-\d{4})\s*(?:\u2014|--|-)\s*(.*?)\s*-->", re.I)
SUBMITTED = re.compile(r"\b(?:SUBMITTED|✅\s*Applied|applied[_ ]on\s*:\s*20\d\d-)")


def load_expected() -> dict | None:
    """Read your own EXPECTED/RATIONALE/restricted-authorization values from the KB file.

    Returns None if the file is missing or the fenced block isn't (fully) filled in yet; the
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
    also: dict[str, set[str]] = {}
    wording: list[tuple[list[str], str, str]] = []
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
        if key == "wording":
            # wording: phrase one; phrase two => YES | reason
            lhs, arrow, rhs = rest.partition("=>")
            if not arrow:
                continue
            ans, _, why = rhs.strip().partition("|")
            ans = ans.strip().upper()
            phrases = [ph.strip().lower() for ph in lhs.split(";") if ph.strip()]
            if ans in ("YES", "NO") and phrases and not placeholder.match(lhs.strip()):
                wording.append((phrases, ans, why.strip() or "(no reason recorded)"))
            continue
        fields = [f.strip() for f in rest.split("|")]
        val = fields[0].upper()
        reason = fields[1] if len(fields) > 1 else ""
        extra = " ".join(fields[2:])
        if placeholder.match(val) or val not in ("YES", "NO"):
            continue  # still a template placeholder like "[YES/NO]", not filled in
        if key in key_map:
            expected[key_map[key]] = val
            rationale[key_map[key]] = reason or "(no reason recorded, add one in the KB file)"
            m_also = re.search(r"also-accept\s*:\s*(YES|NO)\b", extra, re.I)
            if m_also and m_also.group(1).upper() != val:
                also[key_map[key]] = {m_also.group(1).upper()}
        elif key == "restricted-authorization":
            restricted = val == "YES"
    if len(expected) < 3 or restricted is None:
        return None
    return {"expected": expected, "rationale": rationale, "restricted": restricted,
            "also": also, "wording": wording}


def classify(question: str) -> tuple[str, bool] | None:
    """(question kind, inverted?) or None if this isn't a work-authorization question.

    `inverted` means the question asks the negative ("authorized WITHOUT sponsorship" / "WITHOUT
    restriction"), so the expected answer needs special handling: see `expected_answer()`.
    """
    # Classify on the QUESTION only, never on an answer/annotation that follows it. A dossier line is
    # often "<question>? -> **Yes** - maps to class 2 (…'sponsorship to begin/now'…)", and letting the
    # commentary's sponsorship words reach the classifier can misroute an AUTHORIZATION answer to the
    # hard-stop rule and flag a correct Yes. The question ends at the first '?'. Polarity ("without
    # sponsorship") is likewise a property of the question, not the answer: an answer like
    # **"No, I will not need sponsorship"** must not flip the expected value. Strip markdown emphasis
    # so a bolded timeframe (`Will you **now** require sponsorship?`) still reads as "now require" -
    # a real table row bolds the "now" inside a present-tense question.
    q = re.sub(r"[*_`]", "", question.split("?", 1)[0])
    has_sponsor = bool(SPONSOR.search(q))
    inv = bool(INVERTED.search(q))
    if has_sponsor and FUTURE.search(q):
        return Q_FUTURE, inv
    if has_sponsor and BEGIN.search(q):
        return Q_BEGIN, inv
    if AUTHORIZED.search(q) and (not has_sponsor or inv):
        # "Authorized to work WITHOUT sponsorship" is the sponsorship question wearing an
        # authorization coat, so route it by its timeframe. But "authorized to work WITHOUT
        # RESTRICTION", with no sponsorship word and no timeframe, is the *authorization* question
        # itself, inverted, and its honest answer depends on whether your authorization is tied to
        # a specific status (see `restricted-authorization` in the KB block), not on flipping your
        # plain authorized-now answer.
        if inv and (has_sponsor or BEGIN.search(q)):
            return Q_BEGIN, True
        return Q_AUTH, inv
    if has_sponsor and re.search(r"require|need", q, re.I):
        # Sponsorship asked with no timeframe. Treat as the strictest question: the safe reading of
        # an ambiguous sponsorship question is the one that cannot become a lie.
        return Q_FUTURE, inv
    return None


def wording_override(question: str, cfg: dict) -> tuple[str, str] | None:
    """(answer, reason) when your `wording` mapping names a phrase this question prints, else None."""
    q = re.sub(r"[*_`]", "", question.split("?", 1)[0]).lower()
    for phrases, ans, why in cfg.get("wording", []):
        if any(ph in q for ph in phrases):
            return ans, why
    return None


def accepted_answers(kind: str, inverted: bool, cfg: dict) -> set[str]:
    """Every answer the record may hold: the configured one plus any `also-accept` (flipped the
    same way when the question is inverted)."""
    want = expected_answer(kind, inverted, cfg)
    out = {want}
    if not (kind == Q_AUTH and inverted):
        for a in cfg.get("also", {}).get(kind, set()):
            out.add(("NO" if a == "YES" else "YES") if inverted else a)
    return out


def expected_answer(kind: str, inverted: bool, cfg: dict) -> str:
    """The honest answer for this (kind, inverted) pair, given the user's own configured facts."""
    if kind == Q_AUTH and inverted:
        # The "without restriction" phrasing is not a flip of the plain authorized-now answer; it's a
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
                f"      decision: {adr} ({why})\n"
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
    # QUOTED_OPTION is no longer an early-return: the broadened ANSWER regex reads a qualified
    # quoted answer (`**"Yes, work authorization on file"**` -> YES), while a true option LIST
    # (`**"Yes"** / **"No"**`) still yields contradictory hits below and is rejected. Suppressing
    # every quoted token here made a real qualified answer unreadable, after which the next-line
    # fallback grabbed an unrelated **No** and reported a false violation.
    if CONDITIONAL.search(segment):
        return None
    tail = segment
    if not is_continuation:
        q = segment.find("?")
        if q != -1:
            cut = q
        else:
            cut = segment.find(":")
            # Do NOT cut at a ':' that closes an ANSWER LABEL ("Answer:", "Response:"): that discards
            # the value and can leave a stray 'no' from later analysis prose ("Do not answer No") as
            # the sole read. Keeping the whole segment then reads BOTH the real Yes and the warned-
            # against No, which cancel as contradictory (None) rather than flag a false violation.
            if cut != -1 and re.search(r"(?:answer|response|submitted|selected|chose)\s*$",
                                       segment[:cut], re.I):
                cut = -1
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
    """The named ADR must actually be on disk; a well-formed but invented id must not count."""
    num = adr.split("-")[-1]
    return any((REPO / "ops" / "decisions").glob(f"{num}-*.md"))


def _walk(text: str):
    """Yield (line index, line, segment, kind, inverted, answer or None, unreadable?) for every
    work-authorization question segment. `unreadable` is True when the segment is plainly a recorded
    answer (an answer separator such as `→` follows the question, or it sits under an answers
    heading) but no yes/no can be read from it."""
    lines = text.splitlines()
    under_answers = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*#{1,6}\s", line):
            under_answers = bool(ANSWERS_HEADING.match(line))
            continue
        if not (SPONSOR.search(line) or AUTHORIZED.search(line)):
            continue
        segs = SEGMENT.split(line)
        if line.lstrip().startswith("|") and sum(1 for s in segs if classify(s)) <= 1:
            segs = [line]
        for seg in segs:
            # A segment that RECORDS the form carried no such question ("This form has no 'now or in
            # the future' sponsorship question", "No 'sponsorship to begin/now' phrasing appears") is
            # a record of absence, not an answer - reading its emphatic **no**/**Yes** as the answer
            # is a false positive. `coverage_gap` already treats these as records; `scan_text` must too.
            if NO_QUESTION.search(seg):
                continue
            c = classify(seg)
            if c is None:
                continue
            kind, inverted = c
            got = _answer_in(seg)
            if got is None:
                # Fall back to the next line only when the question segment IS the whole line AND it
                # carries no bold token of its own - the "question on one line, answer on the next"
                # shape. If the line HAS a `**…**` token that failed to parse (a qualified answer or a
                # contradictory option list), grabbing the next line's answer is a real bug: it pulls
                # an unrelated **No** off the following line and reports a false violation on the
                # hard-stop question.
                if seg.strip() == line.strip() and "**" not in seg and i + 1 < len(lines):
                    got = _answer_in(lines[i + 1], is_continuation=True)
            unreadable = False
            if got is None and not CONDITIONAL.search(seg):
                after = seg.split("?", 1)[1] if "?" in seg else seg
                unreadable = bool(ANSWER_SLOT.search(after)) or under_answers
            yield i, line, seg, kind, inverted, got, unreadable


def recorded_answers(text: str) -> list[tuple[int, str, str, str, bool, str]]:
    """Every recorded work-authorization answer: (line index, line, question segment, kind,
    inverted, answer). Needs no configuration, so an unconfigured gate can still tell "nothing
    recorded" from "recorded but unverifiable"."""
    return [(i, line, seg, kind, inv, got)
            for i, line, seg, kind, inv, got, _ in _walk(text) if got is not None]


def unreadable_answers(text: str) -> list[tuple[int, str]]:
    """(line number, line) of every recorded work-authorization answer whose yes/no the gate cannot
    read. Such a line is UNVERIFIED: the gate exits non-zero, it never reports it as clean."""
    return [(i + 1, line) for i, line, _s, _k, _v, got, bad in _walk(text) if bad]


def scan_text(rel: str, text: str, cfg: dict) -> list[Finding]:
    out: list[Finding] = []
    lines = text.splitlines()
    is_submitted = bool(SUBMITTED.search(text))
    for i, line, seg, kind, inverted, got in recorded_answers(text):
        override = wording_override(seg, cfg)
        if override:
            accepted, want, why = {override[0]}, override[0], f"your wording mapping: {override[1]}"
        else:
            accepted = accepted_answers(kind, inverted, cfg)
            want, why = expected_answer(kind, inverted, cfg), cfg["rationale"].get(kind, "")
        if got not in accepted:
            out.append(Finding(rel, i + 1, kind, got, line, want, why,
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


# EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (the selftest fixture and the blank starter), never
# a real application. The template's own instructions mention a `## SUBMITTED` heading, so sweeping
# it would report a "submitted with no answer" defect on every fresh clone.
SCAFFOLD_PREFIXES = ("EXAMPLE-", "TEMPLATE-")


def targets(root: Path | None = None) -> list[Path]:
    root = REPO if root is None else root
    return sorted(p for p in root.glob("applications/*/application.md")
                  if not p.parent.name.startswith(SCAFFOLD_PREFIXES))


# --- selftest -------------------------------------------------------------------------------
# A fixed, self-contained fictional configuration: the selftest never reads the real KB file, so
# it works identically on a fresh clone before anyone has filled in their own answers.
_TEST_CFG = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "YES"},
    "rationale": {
        Q_AUTH: "example: authorized to work today under the fixture's assumed status.",
        Q_BEGIN: "example: no sponsorship needed to start.",
        Q_FUTURE: "example: will need sponsorship eventually; this answer never flips.",
    },
    "restricted": True,
}

CASES: list[tuple[str, str, bool]] = [
    ("hard-stop answered correctly",
     "- Will you now or in the future require sponsorship for employment visa status? **Yes**", False),
    ("hard-stop flipped to No: the lie this gate exists to stop",
     "- Will you now or in the future require sponsorship for employment visa status? **No**", True),
    ("'to begin' answered No: correct and must NOT fire",
     "- Do you require sponsorship to begin employment with us? **No**", False),
    ("'to begin' answered Yes: the self-inflicted knockout",
     "- Do you require sponsorship to begin employment? **Yes**", True),
    ("'at the time of hire' answered No: correct",
     "- Will you require visa sponsorship at the time of hire? **No**", False),
    ("authorized-now answered Yes: correct",
     "- Are you legally authorized to work in the United States? **Yes**", False),
    ("authorized-now answered No: false per the fixture config",
     "- Are you legally authorized to work in the United States? **No**", True),
    ("bare sponsorship question with no timeframe answered No: read as the hard stop",
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
     'now or in the future"** (exactly true). NOTE: no separate authorized-now/sponsorship pair '
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
    ("inverted question, honest answer No given restricted=True: must NOT fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **No**", False),
    ("inverted question answered Yes: this IS the lie and MUST fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **Yes**", True),
    ("inverted 'without restriction' answered No: matches restricted=True, must NOT fire",
     "- Are you authorized to work in the U.S. without restriction? **No**", False),
    ("inverted 'without restriction' answered Yes: contradicts restricted=True, MUST fire",
     "- Are you authorized to work in the U.S. without restriction? **Yes**", True),
    ("inverted, to-begin timeframe, honest Yes: must NOT fire",
     "- Can you begin work without requiring sponsorship? **Yes**", False),
    ("a wrong answer inside a markdown table row must fire",
     "| 7 | Will you now or in the future require sponsorship? | **No** |", True),
    ("a right answer inside a markdown table row must NOT fire",
     "| 7 | Will you now or in the future require sponsorship? | **Yes** |", False),

    # --- a family of real phrasing shapes found in a live audit. The selftest suite was fully green
    # while every one of these produced a WRONG verdict against a real dossier - proof a green
    # selftest alone is not a sound gate. Each below is a minimal reproduction of the shape that
    # failed, genericized: the specific status name a dropdown required is not load-bearing here,
    # only its position (leading the quoted answer) is. ---
    ("a qualified dropdown answer that leads with yes/no - honest Yes, must NOT fire",
     '- Will you now or in the future require sponsorship? **"Yes, work authorization on file"**', False),
    ("a semicolon-separated multi-question line - the sponsorship Yes is honest, must NOT fire",
     '- Dropdowns: "restrictions?"=**No**; **"Will you now or in the future require sponsorship?" = '
     '"Yes, work authorization on file"**; "country?"=**United States**', False),
    ("inverted 'without the need for sponsorship' answered No - honest, must NOT fire",
     "- Are you authorized to work without the need for sponsorship, now or in the future? **No**", False),
    ("a wrong hard-stop answer written as a quoted option - the lie, MUST fire",
     '- Will you now or in the future require sponsorship? **"No, I will not need sponsorship"**', True),
    ("the hard-stop answered **No.** (a period inside the bold) - the lie, MUST fire",
     "- Will you now or in the future require sponsorship? **No.**", True),
    ("inverted 'without employer-sponsored visa support' answered No - honest, must NOT fire",
     '- "Are you legally authorized to work in the United States without employer-sponsored visa '
     'support now or in the future?": **No**', False),
    ("the same hyphenated inverted question answered Yes - the lie, MUST fire",
     '- "Are you legally authorized to work in the United States without employer-sponsored visa '
     'support now or in the future?": **Yes**', True),

    # --- the template's own shapes. Before this fix the gate read only bold **Yes**/**No**, so a
    # wrong answer written the way the template shows it passed as CLEAN. ---
    ("template arrow shape, hard-stop flipped to No: MUST fire",
     '- "Will you now or in the future require sponsorship for employment visa status?" → No', True),
    ("template arrow shape, honest Yes: must NOT fire",
     '- "Will you now or in the future require sponsorship for employment visa status?" → Yes', False),
    ("ascii arrow, to-begin answered Yes: MUST fire",
     '- "Do you require sponsorship to begin employment?" -> Yes', True),
    ("colon shape, plain text, authorized-now answered No: MUST fire",
     "- Are you legally authorized to work in the United States: No", True),
    ("trailing bare answer after the question mark, wrong: MUST fire",
     "- Will you now or in the future require sponsorship? No", True),
    ("trailing bare answer in a plain table cell, wrong: MUST fire",
     "| 4 | Will you now or in the future require sponsorship? | No |", True),
    ("an option list after a colon is not an answer: must NOT fire",
     '- "Do you require sponsorship to begin employment?" (dropdown: Yes / No)', False),
]

# A second fictional configuration that exercises the two optional mappings: the future answer
# changed from YES to NO with the old YES still accepted on records (also-accept), and a question
# that names a renewal or a training plan is answered YES as printed (wording).
_TEST_CFG_MAP = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "NO"},
    "rationale": {Q_AUTH: "example.", Q_BEGIN: "example.", Q_FUTURE: "example: changed answer."},
    "restricted": True,
    "also": {Q_FUTURE: {"YES"}},
    "wording": [(["renewal of your", "training plan"], "YES", "example: that wording asks about a renewal.")],
}

MAP_CASES: list[tuple[str, str, bool]] = [
    ("also-accept: the new configured No on the future question is accepted",
     "- Will you now or in the future require sponsorship? **No**", False),
    ("also-accept: the old Yes on a built record is accepted too",
     "- Will you now or in the future require sponsorship? **Yes**", False),
    ("also-accept never widens another class: to-begin answered Yes still fires",
     "- Do you require sponsorship to begin employment? **Yes**", True),
    ("also-accept flips with polarity: inverted future question answered No (old) is accepted",
     "- Are you authorized to work in the US without sponsorship, now or in the future? **No**", False),
    ("also-accept flips with polarity: inverted future question answered Yes (new) is accepted",
     "- Are you authorized to work in the US without sponsorship, now or in the future? **Yes**", False),
    ("wording: a question naming a renewal is answered as printed, Yes accepted",
     "- Do you now, or will you in the future, require sponsorship or a renewal of your employment "
     "authorization? **Yes**", False),
    ("wording: the same printed question answered No fires (the mapping says Yes)",
     "- Do you now, or will you in the future, require sponsorship or a renewal of your employment "
     "authorization? **No**", True),
    ("wording: a phrase in the ANSWER annotation does not trigger the mapping",
     "- Will you now or in the future require sponsorship? **No** (no training plan needed)", False),
]

_UNCONFIGURED_KB = """# answers
```work-authorization
authorized-now: [YES/NO] | [one-line reason]
sponsorship-to-begin: [YES/NO] | [one-line reason]
sponsorship-now-or-future: [YES/NO] | [one-line reason]
restricted-authorization: [YES/NO] | [one-line reason]
```
"""
_NO_SPONSOR_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: NO | example
restricted-authorization: NO | example
```
"""
_MAPPED_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: NO | example, changed | also-accept: YES
restricted-authorization: YES | example
wording: renewal of your; training plan => YES | example
```
"""

COVERAGE_CASES: list[tuple[str, str, bool]] = [
    ("a SUBMITTED dossier with no work-authorization answer at all",
     "# Some Co: Some Role\nStatus: SUBMITTED 2026-01-01\nResume: resume.pdf (241kb)\n", True),
    ("a not-yet-applied dossier with no answer is fine",
     "# Some Co\nStatus: dossier built, NOT APPLIED\n", False),
    ("a SUBMITTED dossier that records the answers is fine",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- Require sponsorship now or in the future? **Yes**\n", False),
    ("the form carried no work-authorization question, and the dossier says so",
     "**✅ SUBMITTED 2026-01-01.** Success panel seen.\n"
     "- **No visa question on this form.** No EEO/demographic section either.\n", False),
    ("the same declaration, colon form",
     "- **Status:** **SUBMITTED 2026-01-01** (success banner seen).\n"
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
_MARK = "<!-- visa:decided ADR-0001 - my call 2026-01-01: not correcting the submitted answer -->"

DECISION_CASES: list[tuple[str, str, bool, bool]] = [
    ("a wrong-answer line, SUBMITTED + marked -> still found, downgraded to DECIDED",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n{_MARK}\n", True, True),
    ("the marker on the SAME line also works",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q} {_MARK}\n", True, True),
    ("WALL 2, NOT submitted: the marker is ignored and it stays a full finding",
     f"Status: dossier built, not yet applied\n{_GOOD_Q}\n{_MARK}\n", True, False),
    ("WALL 1, no ADR named: not a decision, stays a full finding",
     "Status: SUBMITTED 2026-01-01\n" + _GOOD_Q +
     "\n<!-- visa:decided because I said so -->\n", True, False),
    ("WALL 1, an ADR but no reason: stays a full finding",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n<!-- visa:decided ADR-0001 -  -->\n", True, False),
    ("WALL 3, line-scoped: a marker up top does NOT cover a wrong answer further down",
     f"Status: SUBMITTED 2026-01-01\n{_MARK}\n\n- Filler line.\n- Filler line.\n{_GOOD_Q}\n", True, False),
    ("a correct answer with a marker present is still no finding at all",
     f"Status: SUBMITTED 2026-01-01\n- Now or in the future require sponsorship? **Yes**\n{_MARK}\n",
     False, False),
    ("WALL 1b: an INVENTED ADR id must not satisfy the wall",
     f"Status: SUBMITTED 2026-01-01\n{_GOOD_Q}\n<!-- visa:decided ADR-9999 - made up -->\n", True, False),
]


def selftest() -> int:
    passed = failed = 0
    print("visa_gate.py selftest: a fixed fictional configuration, independent of any real KB file\n")
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
    for label, text, should in MAP_CASES:
        got = bool(scan_text("t.md", text, _TEST_CFG_MAP))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    # Parsing and the unconfigured path, against throwaway KB files and dossiers.
    import tempfile
    global KB_ANSWERS
    saved_kb = KB_ANSWERS
    rec = "- Will you now or in the future require sponsorship? **Yes**\n"
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        try:
            KB_ANSWERS = tdp / "kb.md"
            KB_ANSWERS.write_text(_MAPPED_KB, encoding="utf-8")
            cfg = load_expected() or {}
            parse_ok = (cfg.get("also") == {Q_FUTURE: {"YES"}}
                        and [w[0] for w in cfg.get("wording", [])] == [["renewal of your", "training plan"]])
            KB_ANSWERS.write_text(_UNCONFIGURED_KB, encoding="utf-8")
            unconf_none = load_expected() is None
            (tdp / "with.md").write_text(rec, encoding="utf-8")
            (tdp / "without.md").write_text("# A dossier with no answers yet\n", encoding="utf-8")
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                rc_with = main([str(tdp / "with.md")])
                rc_without = main([str(tdp / "without.md")])
            KB_ANSWERS = tdp / "missing.md"
            with contextlib.redirect_stdout(io.StringIO()):
                rc_missing = main([str(tdp / "with.md")])
            # The two observed false-CLEANs, through main(), against a KB that needs no sponsorship.
            KB_ANSWERS = tdp / "kb-none.md"
            KB_ANSWERS.write_text(_NO_SPONSOR_KB, encoding="utf-8")
            shapes = {
                "arrow": '- "Will you now or in the future require sponsorship for employment visa '
                         'status?" → Yes\n',
                "plain": "- Will you now or in the future require sponsorship? Yes\n",
                "unreadable": '## Exact form answers (as filled, 2026-01-01)\n\n- "Will you now or '
                              'in the future require sponsorship?" → I selected the second option\n',
                "unreadable_slot": '- "Do you require sponsorship to begin employment?" → see notes\n',
                "listing": '## Form questions\n\n- "Will you now or in the future require '
                           'sponsorship?" (dropdown: Yes / No)\n',
                "right": '## Exact form answers (as filled, 2026-01-01)\n\n- "Will you now or in the '
                         'future require sponsorship?" → No\n',
            }
            rcs = {}
            for name, body in shapes.items():
                (tdp / f"{name}.md").write_text(body, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    rcs[name] = main([str(tdp / f"{name}.md")])
        finally:
            KB_ANSWERS = saved_kb
    for label, good in [
        ("CONFIG    also-accept and wording lines parse from the block", parse_ok),
        ("CONFIG    an unfilled template block reads as NOT configured", unconf_none),
        ("CONFIG    unconfigured + a recorded answer exits 1 (UNVERIFIED, never a pass)", rc_with == 1),
        ("CONFIG    unconfigured + nothing recorded exits 3 (not checked), never 0", rc_without == EXIT_NOT_CHECKED),
        ("CONFIG    a missing answers file behaves the same as unconfigured (no crash)", rc_missing == 1),
        ("SHAPE     template arrow answer, wrong vs KB, exits 1 (was CLEAN)", rcs["arrow"] == 1),
        ("SHAPE     plain-text trailing answer, wrong vs KB, exits 1 (was CLEAN)", rcs["plain"] == 1),
        ("SHAPE     an unreadable answer under an answers heading exits 1 (UNVERIFIED)", rcs["unreadable"] == 1),
        ("SHAPE     an unreadable answer after an arrow exits 1 (UNVERIFIED)", rcs["unreadable_slot"] == 1),
        ("SHAPE     a question listing with its options is not an answer, exits 0", rcs["listing"] == 0),
        ("SHAPE     the right answer in the canonical shape exits 0", rcs["right"] == 0),
    ]:
        passed, failed = (passed + 1, failed) if good else (passed, failed + 1)
        print(f"  {'✓' if good else '✗'} {label}")
    # The default sweep skips scaffold dossiers (S5): a TEMPLATE- dossier whose instructions name a
    # `## SUBMITTED YYYY-MM-DD` heading must never read as a submitted application.
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for name in ("TEMPLATE-company-role", "EXAMPLE-fixture", "acme-security-engineer"):
            (tdp / "applications" / name).mkdir(parents=True)
            (tdp / "applications" / name / "application.md").write_text(
                "Write `## SUBMITTED YYYY-MM-DD` here once sent.\n", encoding="utf-8")
        got = [p.parent.name for p in targets(tdp)]
    skip_ok = got == ["acme-security-engineer"]
    passed, failed = (passed + 1, failed) if skip_ok else (passed, failed + 1)
    print(f"  {'✓' if skip_ok else '✗'} SWEEP     TEMPLATE-/EXAMPLE- dossiers are skipped; a real one is not")
    # Configuration-loading itself, independent of the fixed test config above.
    load_ok = load_expected() is None or isinstance(load_expected(), dict)
    passed, failed = (passed + 1, failed) if load_ok else (passed, failed + 1)
    print(f"  {'✓' if load_ok else '✗'} CONFIG    load_expected() runs cleanly on the real repo "
          f"(configured or not; both are valid states)")
    if failed:
        print(f"\nSELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"\nSELFTEST OK: {passed}/{passed + failed}")
    return 0


EXIT_NOT_CHECKED = 3


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    paths = [Path(a) if Path(a).is_absolute() else REPO / a for a in args] if args else targets()

    cfg = load_expected()
    if cfg is None:
        print("visa_gate.py: not checked: knowledge-base/12-application-answers.md §3 is not filled in yet.")
        print("  Fill in the ```work-authorization``` block in that file (run /setup, or see SETUP.md)")
        print("  before relying on this gate.")
        unverifiable = []
        for p in paths:
            if not p.is_file():
                continue
            body = p.read_text(encoding="utf-8", errors="replace")
            rec = recorded_answers(body) + unreadable_answers(body)
            if rec:
                try:
                    rel = str(p.resolve().relative_to(REPO))
                except ValueError:
                    rel = str(p)
                unverifiable.append((rel, len(rec)))
        if not unverifiable:
            print("  No application record carries a work-authorization answer yet.")
            print("  This is NOT a pass (exit 3): nothing was verified.")
            return EXIT_NOT_CHECKED
        print(f"\nUNVERIFIED: {len(unverifiable)} file(s) record work-authorization answers that cannot be")
        print("checked until §3 is filled in. This is not a pass:")
        for rel, n in unverifiable:
            print(f"  {rel}  ({n} recorded answer(s))")
        return 1

    findings: list[Finding] = []
    gaps: list[str] = []
    unreadable: list[tuple[str, int, str]] = []
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
        unreadable.extend((rel, n, ln) for n, ln in unreadable_answers(text))
        g = coverage_gap(rel, text)
        if g:
            gaps.append(g)

    print(f"visa_gate.py: checked {checked} file(s) against knowledge-base/12-application-answers.md §3")
    print(f"  authorized-now = {cfg['expected'][Q_AUTH]} · sponsorship-to-begin = {cfg['expected'][Q_BEGIN]} "
          f"· now-or-in-the-future = {cfg['expected'][Q_FUTURE]}")
    for k, extra in cfg.get("also", {}).items():
        print(f"  also accepted on records for {k}: {', '.join(sorted(extra))} (your also-accept)")
    if cfg.get("wording"):
        print(f"  wording mappings: {len(cfg['wording'])} (a question printed that way gets its own answer)")
    print("  NOT checked: what was actually clicked in the browser. This reads the RECORD only;")
    print("               a correct record and a wrong radio button still diverge.")
    decided = [f for f in findings if f.decided]
    open_findings = [f for f in findings if not f.decided]

    if not open_findings and not gaps and not unreadable:
        print("\nCLEAN: every recorded work-authorization answer matches your configured rule.")
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
    if unreadable:
        print(f"{len(unreadable)} UNVERIFIED ANSWER(S): a work-authorization answer is recorded here but")
        print("the gate cannot read its Yes/No. Rewrite it in the one shape:")
        print('  - "<question exactly as printed>" → Yes   (or → No)\n')
        for rel, n, ln in unreadable:
            snippet = ln.strip()
            print(f"  [UNVERIFIED] {rel}:{n}\n      line:     {snippet[:157] + '...' if len(snippet) > 160 else snippet}\n")
    if gaps:
        print(f"{len(gaps)} SUBMITTED APPLICATION(S) WITH NO RECORDED ANSWER:\n")
        for g in gaps:
            print(g)
            print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
