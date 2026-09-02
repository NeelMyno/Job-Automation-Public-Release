#!/usr/bin/env python3
"""canon.py — the retired-claim checker. Guards the WELL, not just the door.

WHY THIS EXISTS
---------------
A career-automation repo generates outbound copy — resumes, cover letters, positioning notes —
from a knowledge base about you. When a fact changes (a project's real scope gets corrected, a
claim turns out to be an overclaim, a title turns out to map to the wrong job family), the fix
gets written in ONE place — a decision record, a knowledge-base file — and the retired wording is
expected to disappear everywhere else. It doesn't, by default. Markdown and HTML get copied,
pasted, and reworded constantly, and a retired claim has a way of surviving in a sibling file, a
stale bullet, or a résumé PDF nobody re-checked.

A checker that only reads outbound application copy is not enough, because that copy is
*generated from* the knowledge base. If the retired claim is still live at the source, a
per-dossier check just keeps catching the same defect at the door while the well stays poisoned.
This file checks the source surfaces directly — the knowledge base, the résumé, and this repo's
own instruction files.

THE HARD PART — assertion vs prohibition
----------------------------------------
A naive substring search is wrong, because the retired string appears constantly in CORRECT text
too: a prohibition ("never say X"), a documented correction ("X is retired; say Y instead"), a
historical record of the mistake itself. A checker that flags every occurrence fires mostly on
correct work — and a linter that cries wolf gets turned off within a week.

So every hit is classified:
  * NEGATED   — a negation marker sits in the line or the window immediately before it. The text
                is telling you NOT to say the thing. Allowed, silently.
  * ASSERTED  — no negation, or the line carries an assertion marker ("Résumé-ready:", "Say:",
                "Use this line") that OVERRIDES any nearby negation, because a line labelled as
                ready-to-paste copy is copy that WILL get pasted, whatever the surrounding prose
                warns.

THE OTHER HARD PART — one claim has infinite spellings
------------------------------------------------------
A line-oriented ASCII regex guards exactly one spelling of a claim. In ordinary use — no exotic
attack required — a retired claim keeps reappearing through mundane text transformations:

    line split          a claim that wraps across a markdown line break
    HTML interpolation  a bold/em/anchor tag landing mid-phrase
    HTML entity         `&nbsp;` where the source had a literal space
    unicode dashes      a smart editor substituting a hyphen for an en dash or non-breaking hyphen
    zero-width          an invisible character, pasted in from another document, sitting inside a word
    confusable letters  a Cyrillic or Greek letter that renders pixel-identical to its Latin lookalike
    fullwidth           a fullwidth punctuation mark from an IME or a paste from CJK-adjacent text
    whitespace slack    a doubled space, or a trailing "+" where the pattern expected bare digits

None of these is exotic. Every one is something a human, an editor, or a paste from another
document produces by accident. A checker that only guards the canonical spelling is a checker
that passes the moment the copy is touched — which is exactly when it matters most.

So every file is matched through a NORMALISED VIEW (see `normalise()`):
    * HTML tags stripped — inline tags (`<b>`, `<em>`, `<a>`) close up, block tags (`<li>`, `<p>`)
      become a space, so a word boundary at a block-tag join is preserved;
    * HTML entities decoded (`&nbsp;` -> space, `&amp;` -> `&`);
    * invisibles deleted (zero-width space/joiner, word joiner, BOM, soft hyphen);
    * every unicode dash -> `-`, every unicode space -> ` `, fullwidth ASCII -> ASCII;
    * confusable Cyrillic/Greek letters folded to Latin;
    * ALL whitespace — newlines included — collapsed to one space.

Every normalised character keeps a pointer back to its source offset, so a finding still reports
the ORIGINAL line number and the ORIGINAL text. The classification logic is unchanged by
normalisation:

    * the before-window still CLAMPS to the line the match starts on, and the after-window to the
      line it ends on. That clamp is load-bearing: collapsing newlines is what closes the
      line-split bypass, but letting the CONTEXT windows collapse across lines too would let an
      unrelated correction on a neighbouring line excuse an assertion on this one.
    * an ASSERTION label is read from the normalised text, so a marked-up "**Résumé-<b>ready</b>:**"
      still counts — but only on the lines the match itself spans, deliberately not extended to a
      preceding line, since "Use this line: ..." followed by "Never say ... on the next line" is a
      legitimate and common markdown shape.

SCOPE — stated out loud, because a silent scope is a lie by omission
--------------------------------------------------------------------
SCANNED (the live surfaces an agent generates copy from) — see `SCAN_GLOBS` below.
NOT SCANNED, deliberately:
    ops/**            immutable history. Decision records legitimately quote the strings they
                      retired, as part of documenting the retirement.
    applications/**   per-application outbound copy is a separate concern — a dedicated
                      claim-verification tool, if you have one, owns that surface. `sources/`
                      subfolders are verbatim snapshots, and editing one to make a check pass is
                      forgery.

USAGE
    python3 scripts/canon.py                # check every live surface   -> exit 1 on any finding
    python3 scripts/canon.py <path> ...     # check specific files (used by the PostToolUse hook)
    python3 scripts/canon.py --selftest     # prove the detection machinery still catches its
                                             # bypass classes, against fictional example claims
    python3 scripts/canon.py --list         # print the registry
"""

from __future__ import annotations

import bisect
import html as _html
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------------------
# THE REGISTRY
# --------------------------------------------------------------------------------------
# One entry per retired claim about YOU — a fact, framing, or number that used to be true (or used
# to be your best phrasing) and has since been corrected. `pattern` is a case-insensitive regex,
# matched against the NORMALISED view of the text (see `normalise()` below), so it catches the
# claim however it's spelled, tagged, or pasted.
#
# Entry schema:
#   {
#       "id":       "short-kebab-id",     # stable identifier; referenced by canon:allow escapes
#       "pattern":  r"...",                # case-insensitive regex, matched against normalised text
#       "why":      "...",                 # the decision that retired this claim
#       "instead":  "...",                 # the wording that IS true — a rule that says "no"
#                                           # without saying "what then" just gets argued with
#       "scope":     "substring",          # optional — only checked on paths containing this
#       "scope_any": ("a/", "b/"),         # optional — only checked on paths containing ANY of these
#   }
#
# TO ADD ONE: the moment you correct or retire a claim about yourself, add an entry here IN THE
# SAME COMMIT as the correction. That is the whole point of this file — the registry is how a
# decision propagates instead of quietly evaporating everywhere except the one place you fixed it.

RETIRED: list[dict] = []

# --------------------------------------------------------------------------------------
# Context classification
# --------------------------------------------------------------------------------------

# Negation must be ABOUT the retired string, not merely on the same line. The first draft of this
# file matched any "not" anywhere in the line and therefore MISSED real defects where the "not"
# belonged to a different clause than the one asserting the retired claim:
#   "E-Verify is now a HARD FILTER, not a preference"   <- "not" negates *preference*, and the
#                                                          sentence asserts the retired rule
#   "Title reflects current reality (Product Design Engineer, not "Co-Op Intern")"
#   "human taste vs AI slop ("un-slopping the AI slop"), builder, not engineer"
# All three were suppressed by a "not" belonging to a different clause. Hence: a window, not a line.
LOOKBACK_CHARS = 80   # "never say X", "Drop X", "they are NOT X", "Delete X everywhere"
LOOKAHEAD_CHARS = 40  # only for strong retirement verbs: "X is RETIRED", "X — superseded"

NEGATION = re.compile(
    # Plain "no" earns its place: `- No "un-slopping the AI slop" slogan.` is a prohibition, and
    # the 80-char before-window keeps it from excusing unrelated prose.
    # The lookarounds exclude hyphen-joined compounds: `builder-not-engineer` is an identity, not a
    # negation, and its embedded "not" hid a real slogan survivor from this checker.
    r"(?<![-\w])(?:never|not|no|no longer|nowhere|drop(?:ped|s)?|delete[sd]?|retire[sd]?|forbidden|"
    r"banned?|blocklist(?:ed)?|avoid|instead of|rather than|supersed(?:e|ed|es)|"
    r"correct(?:s|ed|ion)?|wrong|incorrect|do not|don't|must not|cannot|false|fabricat\w*|"
    # "old" is narrowed to old *wording*, never old *things*. A bare "the old" once suppressed a
    # real fabrication ("The old tracking page guessed at delivery times") — the artifact was
    # genuinely old; the claim about it was invented.
    r"stop saying|off the r[ée]sum[ée]|old (?:figure|number|line|wording|framing|metric|claim)s?|"
    r"former|previously|used to)(?![-\w])|[⛔❌]|~~",
    re.I,
)
# 🔴 is deliberately NOT a negation marker. This repo may use it as an ALERT/emphasis marker on a
# line that emphasises a *retired* rule itself — treating it as negation would hide exactly that.

STRONG_RETIREMENT = re.compile(
    r"\b(?:retired?|superseded?|forbidden|banned|deprecated|removed|dead|obsolete|"
    r"fabricat\w*|not real|no CI runner|historical record)\b|[⛔❌]|~~", re.I
)

# The explicit escape hatch. Heuristics handle the ordinary "never say X" idioms; this covers the
# rest — a section-level supersession banner too far above to see, a quotation of the retired claim
# in a record, a legitimate homonym. It is deliberately NOT a bare "ignore":
#   * it must NAME the rule it silences, so it cannot blanket-suppress a future rule; and
#   * it must carry a reason, because a silent suppression is the same lie by omission this whole
#     file exists to stop.
# Audit every escape in the repo with:  grep -rn 'canon:allow' --include=*.md .
ALLOW = re.compile(r"<!--\s*canon:allow\s+([a-z0-9-]+)\s*(?:—|--|-)\s*(.+?)-->", re.I)

# ...UNLESS the line is labelled as copy meant to be used. A line that says "Résumé-ready:" is a
# line an agent will paste, no matter what the paragraph above it warns. This override is the
# specific thing that catches a retired claim hiding on an assertion-labelled line.
ASSERTION = re.compile(
    r"(?:r[ée]sum[ée][- ]ready|resume[- ]ready|ready to use|use this line|copy this|"
    r"the line to (?:use|print)|say\s*:)",
    re.I,
)

# --------------------------------------------------------------------------------------
# NORMALISATION — guard the CLAIM, not one spelling of it. See the module docstring for the
# eight bypass classes this normalisation closes.
#
# Design constraint: every normalised character must remember where it came from, because a
# finding that cannot name the ORIGINAL line number is not actionable. So this is a hand-rolled
# left-to-right pass rather than `unicodedata.normalize` + `html.unescape` — those give you a
# string with no offset map, and a finding at "normalised offset 4127" is useless to a human.
# --------------------------------------------------------------------------------------

# Inline tags close up (`<b>Wid</b>get` IS "Widget"); everything else becomes a space, so
# `<li>2019</li><li>75 million users` keeps the `\b` in front of 75. An unknown tag is treated as
# block-level — the conservative choice, since joining across it could destroy a word boundary.
INLINE_TAGS = {
    "a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn", "em", "font",
    "i", "ins", "kbd", "mark", "q", "rp", "rt", "ruby", "s", "samp", "small", "span", "strike",
    "strong", "sub", "sup", "time", "tt", "u", "var", "wbr",
}
TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)[^<>]*>")
# `&nbsp;` `&#8209;` `&#x2011;` `&amp;`. The trailing `;` is required, so "R&D" is left alone.
ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")

# Invisible. Deleted outright — that is what a reader sees, so it is what the checker must see.
# Written as escapes, not glyphs, because a table of invisible characters that you cannot see in
# the source is a table nobody can audit.
INVISIBLE = set(
    "​"   # ZERO WIDTH SPACE            <- the proven `CI-ga​ted` bypass
    "‌‍⁠﻿"               # ZWNJ, ZWJ, WORD JOINER, BOM
    "­"   # SOFT HYPHEN (renders as nothing except at a line break)
    "͏᠎⁡⁢⁣⁤"
)
# Every dash a word processor, a smart-quote setting, or a paste from Word can produce.
DASHES = set(
    "‐"   # HYPHEN                      <- proven bypass
    "‑"   # NON-BREAKING HYPHEN         <- proven bypass
    "–"   # EN DASH                     <- proven bypass
    "‒—―"                     # FIGURE DASH, EM DASH, HORIZONTAL BAR
    "−⁃˗֊᠆"         # MINUS SIGN, HYPHEN BULLET, MODIFIER, ARMENIAN, MONGOLIAN
    "﹘﹣－"                     # SMALL EM DASH, SMALL HYPHEN-MINUS, FULLWIDTH HYPHEN
)
QUOTES = {**{c: "'" for c in "‘’‚‛′‵´"},
          **{c: '"' for c in "“”„‟″‶«»"}}

# Confusable folding. These are the codepoints that render identically to a Latin letter in the
# fonts this repo's files are read in — `СI-gated` (Cyrillic Es) is invisible to a human reviewer
# AND to an ASCII regex, which is the worst combination a checker can have.
_CYR_UP, _LAT_UP = "АВЕКМНОРСТУХІЈЅԚԜЁ", "ABEKMHOPCTYXIJSQWE"
_CYR_LO, _LAT_LO = "аеорсухіјѕԛԝё", "aeopcyxijsqwe"
_GRK_UP, _GLAT_UP = "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABEZHIKMNOPTYX"
_GRK_LO, _GLAT_LO = "αορικντυχε", "aopikvtuxe"
CONFUSABLE = {}
for _src, _dst in ((_CYR_UP, _LAT_UP), (_CYR_LO, _LAT_LO), (_GRK_UP, _GLAT_UP), (_GRK_LO, _GLAT_LO)):
    assert len(_src) == len(_dst), "confusable table is misaligned"
    CONFUSABLE.update(dict(zip(_src, _dst)))


def _map_char(c: str) -> str | None:
    """One source character -> its normalised form, or None to delete it."""
    if c in INVISIBLE:
        return None
    if c.isspace():
        return " "          # collapsed downstream; newlines included, which is the point
    o = ord(c)
    if 0xFF01 <= o <= 0xFF5E:
        return chr(o - 0xFEE0)   # fullwidth ASCII: `example．com` -> `example.com`
    if c in DASHES:
        return "-"
    return QUOTES.get(c) or CONFUSABLE.get(c) or c


def normalise(text: str) -> tuple[str, list[int]]:
    """Return (normalised text, src[i] = source offset of normalised char i).

    `src` is monotonically non-decreasing, which is what lets `bisect` map a match back to its
    original line. Deleted characters emit nothing; expanded ones (an entity decoding to several
    characters) all point at the entity's own start offset.
    """
    out: list[str] = []
    src: list[int] = []

    def emit(s: str, at: int) -> None:
        for ch in s:
            if ch == " ":
                if not out or out[-1] == " ":
                    continue     # collapse runs, and never lead with whitespace
                out.append(" ")
            else:
                out.append(ch)
            src.append(at)

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "<":
            # Comment delimiters vanish but the comment BODY is still scanned. Dropping the body
            # would quietly stop guarding it, and a retired claim parked in a comment is one
            # uncomment away from being asserted.
            if text.startswith("<!--", i):
                i += 4
                continue
            m = TAG.match(text, i)
            if m:
                if m.group(1).lower() not in INLINE_TAGS:
                    emit(" ", i)
                i = m.end()
                continue
        elif c == "-" and text.startswith("-->", i):
            i += 3
            continue
        elif c == "&":
            m = ENTITY.match(text, i)
            if m:
                emit("".join(_map_char(x) or "" for x in _html.unescape(m.group(0))), i)
                i = m.end()
                continue
        mapped = _map_char(c)
        if mapped is not None:
            emit(mapped, i)
        i += 1
    return "".join(out), src


def line_starts(text: str) -> list[int]:
    """Source offset of every line start. `text.split('\\n')` indexes 1:1 against this."""
    starts = [0]
    pos = text.find("\n")
    while pos != -1:
        starts.append(pos + 1)
        pos = text.find("\n", pos + 1)
    return starts


SCAN_GLOBS = [
    "knowledge-base/**/*.md",
    "resume/*.html",
    "resume/*.md",
    "CLAUDE.md",
    "STRUCTURE.md",
    "README.md",
    "docs/DESIGN.md",
    ".claude/commands/*.md",
    ".claude/workflows/*.js",
]

# Never scanned. See the module docstring for why each is here.
EXCLUDE_PARTS = ("/ops/", "/applications/", "/source-material/", "/projects/", "/archive/", "/.git/")

# Employer-authored text that happens to live inside a scanned folder — e.g. a saved JD or a
# tracker file that quotes a company's own listing verbatim. A rule about how YOU describe your
# own work must never fire on how a company describes theirs. Starts empty; add a file here the
# moment you find one that needs the exclusion.
EXCLUDE_FILES: tuple[str, ...] = ()


@dataclass
class Finding:
    path: str
    line_no: int
    rule_id: str
    text: str
    why: str
    instead: str

    def render(self) -> str:
        snippet = self.text.strip()
        if len(snippet) > 150:
            snippet = snippet[:147] + "..."
        return (
            f"  {self.path}:{self.line_no}  [{self.rule_id}]\n"
            f"      says:    {snippet}\n"
            f"      why:     {self.why}\n"
            f"      instead: {self.instead}"
        )


def _excluded(p: Path) -> bool:
    s = "/" + str(p).replace("\\", "/").lstrip("/")
    if any(part in s for part in EXCLUDE_PARTS):
        return True
    return any(s.endswith("/" + f) for f in EXCLUDE_FILES)


def scan_text(rel: str, text: str) -> list[Finding]:
    """Classify every retired-string hit in one file as NEGATED (fine) or ASSERTED (a finding).

    Matching happens against `normalise(text)` — a whitespace-collapsed, tag-stripped,
    unicode-folded view — so a claim is caught however it is spelled. Every window the
    classification uses is then mapped back onto the ORIGINAL lines, so nothing about the
    assertion-vs-prohibition logic changed shape.
    """
    out: list[Finding] = []
    lines = text.split("\n")          # split, not splitlines: indexes 1:1 against `starts`
    norm, src = normalise(text)
    starts = line_starts(text)

    def line_of(offset: int) -> int:
        return bisect.bisect_right(starts, offset) - 1

    def norm_at(offset: int) -> int:
        """First normalised index whose source offset is >= `offset` (src is monotone)."""
        return bisect.bisect_left(src, offset)

    for entry in RETIRED:
        scope = entry.get("scope")
        if scope and scope not in rel:
            continue
        scope_any = entry.get("scope_any")
        if scope_any and not any(s in rel for s in scope_any):
            continue
        rx = re.compile(entry["pattern"], re.I)
        reported: set[int] = set()    # one finding per (rule, line), as before

        for m in rx.finditer(norm):
            # Map the match back onto the original file.
            first = line_of(src[m.start()])
            last = line_of(src[m.end() - 1]) if m.end() > m.start() else first
            if first in reported:
                continue
            spanned = lines[first:last + 1]

            # The line window, in normalised coordinates. 🔴 The before-window CLAMPS to the line
            # the match starts on and the after-window to the line it ends on. Collapsing newlines
            # is what closes the line-split bypass, but letting the windows collapse with them
            # would hand the previous line's vocabulary an excuse for this line's claim.
            lo = norm_at(starts[first])
            hi = norm_at(starts[last + 1]) if last + 1 < len(starts) else len(norm)

            # Explicit, named, reasoned escape — checked before anything else. See ALLOW.
            # Read from the RAW lines: the escape is a literal comment a human wrote, and it is
            # honoured on any line the match touches.
            if any((a := ALLOW.search(rl)) and a.group(1).lower() == entry["id"] for rl in spanned):
                continue

            # An "assertion" label beats every excuse: a line marked Résumé-ready is copy meant
            # to be pasted, whatever the paragraph around it warns. Read from the NORMALISED text,
            # so `**Résumé-<b>ready</b>:**` still counts.
            if ASSERTION.search(norm[lo:hi]):
                out.append(Finding(rel, first + 1, entry["id"], " ⏎ ".join(spanned),
                                   entry["why"], entry["instead"]))
                reported.add(first)
                continue

            # (1) Negation immediately BEFORE the match — "never say X", "Drop X", "NOT X".
            before = norm[max(lo, m.start() - LOOKBACK_CHARS):m.start()]
            # (2) A STRONG retirement verb just AFTER — "X is RETIRED", "X — superseded".
            #     Generic "not" is deliberately excluded here: "HARD FILTER, not a preference"
            #     negates *preference* and asserts the retired rule.
            #
            #     🔴 The window STOPS at the first clause boundary, and that is not a nicety.
            #     A retirement verb 40 chars later can belong to a COMPLETELY DIFFERENT retired
            #     claim, inside a parenthetical — excusing THIS claim on THAT verb's word alone
            #     is adjacent-verification laundering performed by the tool built to prevent it.
            #     A retirement verb only excuses the claim it is attached to, so a new clause ends
            #     its reach.
            after_raw = norm[m.end():min(hi, m.end() + LOOKAHEAD_CHARS)]
            # A retirement verb in the trailing text excuses this claim ONLY if that text is about
            # THIS claim. The discriminator: does the trailing text name a DIFFERENT retired claim?
            names_other = any(
                re.search(o["pattern"], after_raw, re.I)
                for o in RETIRED if o["id"] != entry["id"]
            )
            after = "" if names_other else after_raw
            # (3) A correction banner on one of the two preceding non-blank lines.
            #     A TABLE ROW is never a banner for the row beneath it — it is a sibling record
            #     about a different subject.
            in_table = lines[first].lstrip().startswith("|")
            banner = ""
            j, taken = first - 1, 0
            while j >= 0 and taken < 2:
                if lines[j].strip():
                    if not (in_table and lines[j].lstrip().startswith("|")):
                        banner += lines[j] + "\n"
                    taken += 1
                j -= 1

            # The banner must be a genuine CORRECTION banner, not merely a nearby word. A bare
            # "removed" or "NOT real" on a neighbouring line — about a completely different
            # subject — can excuse a real defect if allowed to. So a banner now also needs an ADR
            # reference or a date: the shape of an actual correction note, not an accident of
            # vocabulary.
            banner_ok = bool(STRONG_RETIREMENT.search(banner)) and bool(
                re.search(r"ADR-\d{4}|20\d\d-\d\d-\d\d", banner)
            )
            excused = (
                NEGATION.search(before)
                or STRONG_RETIREMENT.search(after)
                or banner_ok
            )
            if excused:
                continue  # documenting the ban, not committing it
            out.append(Finding(rel, first + 1, entry["id"], " ⏎ ".join(spanned),
                               entry["why"], entry["instead"]))
            reported.add(first)
    return out


SKIPPED: list[str] = []   # files handed to us that we could NOT read. Never silently.


def scan_paths(paths: list[Path]) -> list[Finding]:
    """Scan the readable files, and RECORD the ones we could not read.

    Printing "CLEAN — no retired claim is asserted" for a file this checker silently refused to
    open manufactures exactly the false confidence it exists to end. It cannot read a PDF — that
    is fine and honest — but it must say so, not report CLEAN for a file it never opened.
    """
    global SKIPPED
    SKIPPED = []
    findings: list[Finding] = []
    for p in paths:
        if _excluded(p):
            continue
        if not p.is_file():
            SKIPPED.append(f"{p} (not a file)")
            continue
        if p.suffix.lower() not in (".md", ".html", ".js", ".txt", ".py"):
            SKIPPED.append(f"{p} ({p.suffix or 'no extension'} is not a text format this reads)")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        findings.extend(scan_text(rel, text))
    return findings


def live_surface() -> list[Path]:
    seen: dict[str, Path] = {}
    for g in SCAN_GLOBS:
        for p in REPO.glob(g):
            if p.is_file() and not _excluded(p):
                seen[str(p.resolve())] = p
    return sorted(seen.values())


# --------------------------------------------------------------------------------------
# Self-test — every rule must catch the claim it exists for, and must NOT fire on the correct
# wording that legitimately sits beside it. A test that only proves the happy path is not a test;
# a rule with no negative control is a false-positive generator.
#
# RETIRED ships EMPTY (above) — there is nothing of yours to test until you add your own entries.
# To prove the DETECTION MACHINERY itself still works — normalisation, the eight unicode-bypass
# classes, the assertion/negation/banner classifier — the selftest below temporarily registers a
# handful of CLEARLY FICTIONAL example claims, runs CASES against them, then restores RETIRED to
# empty. These example entries are never present outside `--selftest`.
# --------------------------------------------------------------------------------------

_EXAMPLE_RETIRED: list[dict] = [
    {
        "id": "example-solo-build",
        "pattern": r"built\s+the\s+entire\s+platform\s+solo",
        "why": "(fictional, --selftest only) a corrected overclaim — the platform had a team.",
        "instead": "describe the specific piece you actually owned",
    },
    {
        "id": "example-user-count",
        "pattern": r"\b1\s*million\s*\+?\s*active\s*users\b",
        "why": "(fictional, --selftest only) a corrected/fabricated metric.",
        "instead": "the real, sourced number, or no number claim at all",
    },
    {
        "id": "example-auto-deploy",
        "pattern": r"\bauto-deploy\b",
        "why": "(fictional, --selftest only) a retired feature name.",
        "instead": "the current, correct feature name",
    },
    {
        "id": "example-old-codename",
        "pattern": r"\bProject Nightingale\b",
        "scope_any": ("case-studies/", "portfolio/"),
        "why": "(fictional, --selftest only) an internal codename retired from public-facing "
               "surfaces only; it may still appear in private planning notes.",
        "instead": "the shipped product name",
    },
]

CASES: list[tuple[str, str, str, bool]] = [
    # (label, fake-path, text, should_flag)

    # --- the assertion override ---
    ("an assertion label overrides a nearby warning",
     "knowledge-base/06-projects-portfolio.md",
     '- **Résumé-ready:** "Built the entire platform solo, end to end."', True),

    # --- the banner mechanism: a genuine dated correction excuses the line below it, but an
    # unrelated strong word does NOT (it needs an ADR/date to count as an actual correction) ---
    ("a dated correction banner two lines up excuses the bare claim below it",
     "knowledge-base/06-projects-portfolio.md",
     "> Corrected 2025-01-01 (ADR-0001): this framing is retired.\n"
     "The team page still describes it as: built the entire platform solo.", False),
    ("an unrelated strong word nearby must NOT excuse it without an ADR/date",
     "knowledge-base/08-application-playbook.md",
     "Employee turnover was high and several old features were removed last quarter.\n"
     "The team page still says: built the entire platform solo.", True),
    ("a table row above must not excuse a table row below (sibling rows, not a banner)",
     "knowledge-base/INDEX.md",
     "| `02-work-auth.md` | Visa and authorization details |\n"
     "| `03-narrative.md` | The story arc; says the founder built the entire platform solo |", True),

    # --- controls: prohibitions, marked-up or not, must never fire ---
    ("a prohibition that is itself marked up must still be allowed",
     "resume/resume.html",
     'Never say <b>"built the entire platform solo"</b> in outbound copy.', False),
    ("a plain-prose prohibition must not fire (the false-positive-proof case)",
     "knowledge-base/11-preferences-and-conventions.md",
     "The launch is described as a team effort, never framed as having built the entire platform "
     "solo.", False),
    ("a named, reasoned canon:allow escape survives the normalised view",
     "CLAUDE.md",
     'This paragraph is the historical record of the fictional overclaim, kept for reference: '
     '"built the entire platform solo." '
     '<!-- canon:allow example-solo-build — this line IS the canonical record of the retired '
     'claim and must stay verbatim -->', False),
    ("a canon:allow escape naming the WRONG id must NOT excuse the finding",
     "CLAUDE.md",
     'Kept for the record: "built the entire platform solo." '
     '<!-- canon:allow example-user-count — wrong id, must not excuse example-solo-build -->', True),

    # --- scope / scope_any narrowing ---
    ("scope_any narrows to specific folders — a non-matching path is not flagged",
     "knowledge-base/03-narrative.md",
     "Internally this was called Project Nightingale before it shipped.", False),
    ("scope_any matches on its SECOND option too",
     "portfolio/case-study.md",
     "Internally this was called Project Nightingale before it shipped.", True),

    # --- same-line retirement verb, and the "different claim nearby" guard ---
    ("a retirement verb attached to THIS claim, on the same line, still excuses it",
     "knowledge-base/06-projects-portfolio.md",
     '"built the entire platform solo" is retired wording.', False),
    ("a correction about a DIFFERENT claim nearby must not excuse THIS one",
     "knowledge-base/06-projects-portfolio.md",
     'The launch page says the founder built the entire platform solo (auto-deploy is retired '
     'wording — say "automatic deploys").', True),

    # ==================================================================================
    # THE EIGHT UNICODE-BYPASS CLASSES — each one character or one tag away from a string the
    # registry already knows. A rule that guards a single spelling is a rule that expires the
    # first time someone edits the sentence.
    # ==================================================================================

    # --- 1. line split: the claim wraps across a markdown line break ---
    ("BYPASS line-split: the claim wraps across a markdown line break",
     "knowledge-base/06-projects-portfolio.md",
     "- Built the entire platform\n  solo, from data model to deploy.", True),

    # --- 2. HTML interpolation: an inline tag lands mid-phrase ---
    ("BYPASS html-inline: a <b> tag lands mid-phrase",
     "resume/resume.html",
     "<li>She built the entire <b>platform</b> solo, end to end.</li>", True),
    ("BYPASS html-inline: <b>Auto</b>-deploy inside a compound word",
     "resume/resume.html",
     "<li>Shipped the <b>Auto</b>-deploy pipeline before it was renamed.</li>", True),
    ("GUARD html-block: adjacent block tags must still leave a word boundary before the number",
     "resume/resume.html",
     "<li>2024</li><li>1 million active users this year</li>", True),

    # --- 3. HTML entity ---
    ("BYPASS html-entity: a non-breaking space via &nbsp;",
     "resume/resume.html",
     "<li>Reached 1&nbsp;million active users in year one.</li>", True),

    # --- 4. unicode dash variants ---
    ("BYPASS unicode: auto‑deploy (U+2011 non-breaking hyphen)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old auto‑deploy step.", True),
    ("BYPASS unicode: auto‐deploy (U+2010 hyphen)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old auto‐deploy step.", True),
    ("BYPASS unicode: auto–deploy (U+2013 en dash)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old auto–deploy step.", True),

    # --- 5. zero-width / invisible ---
    ("BYPASS unicode: auto-​deploy (U+200B zero-width space inside the word)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old auto-​deploy step.", True),

    # --- 6. confusable letters ---
    ("BYPASS unicode: аuto-deploy (U+0430 Cyrillic а, renders as Latin a)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old аuto-deploy step.", True),

    # --- 7. fullwidth ASCII ---
    ("BYPASS unicode: auto－deploy (U+FF0D fullwidth hyphen-minus)",
     "knowledge-base/06-projects-portfolio.md",
     "The pipeline still runs the old auto－deploy step.", True),

    # --- 8. whitespace slack ---
    ("BYPASS slack: doubled internal space",
     "resume/resume.html",
     "<li>The app reached 1  million active users within a year.</li>", True),
    ("BYPASS slack: a '+' right after the number, which a bare \\s+ pattern would miss",
     "resume/resume.html",
     "<li>Reached 1 million+ active users by launch.</li>", True),

    # --- the replacement wording must not fire ---
    ("the correct replacement wording must NOT fire",
     "knowledge-base/06-projects-portfolio.md",
     "A three-person team built the platform; each owned one layer of the stack.", False),
]


def selftest() -> int:
    global RETIRED
    saved = RETIRED
    RETIRED = _EXAMPLE_RETIRED
    passed = failed = 0
    try:
        print("canon.py selftest — the detection machinery against fictional example claims\n")
        for label, path, text, should in CASES:
            got = bool(scan_text(path, text))
            ok = got == should
            if ok:
                passed += 1
                mark = "✓ CAUGHT " if should else "✓ allowed"
            else:
                failed += 1
                mark = "✗ MISSED " if should else "✗ FALSE-POSITIVE"
            print(f"  {mark}  {label}")
    finally:
        RETIRED = saved
    print()
    if failed:
        print(f"SELFTEST FAILED — {failed} of {passed + failed} cases wrong")
        return 1
    print(f"SELFTEST OK — {passed}/{passed + failed} "
          f"({sum(1 for c in CASES if c[3])} bypass/defect cases caught, "
          f"{sum(1 for c in CASES if not c[3])} correct-wording controls not flagged)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--list" in argv:
        print(f"canon registry — {len(RETIRED)} retired claims\n")
        for e in RETIRED:
            print(f"  [{e['id']}]{'  scope=' + e['scope'] if e.get('scope') else ''}")
            print(f"      why:     {e['why']}")
            print(f"      instead: {e['instead']}\n")
        if not RETIRED:
            print("  (empty — add your own entries to RETIRED as you retire claims about yourself)")
        return 0

    args = [a for a in argv if not a.startswith("-")]
    if args:
        paths = [Path(a) if Path(a).is_absolute() else REPO / a for a in args]
        where = f"{len(paths)} path(s)"
    else:
        paths = live_surface()
        where = f"{len(paths)} live-surface files"

    findings = scan_paths(paths)

    print(f"canon.py — checked {where} against {len(RETIRED)} retired claims")
    print("  scanned:     knowledge-base/, resume/, CLAUDE.md, STRUCTURE.md, README.md, "
          "docs/DESIGN.md, .claude/commands|workflows")
    print("  NOT checked: ops/ (immutable history), applications/ (a dedicated per-application "
          "claim checker, if you have one, owns that surface)")
    if SKIPPED:
        print(f"  🔴 NOT READ ({len(SKIPPED)}) — a verdict below does NOT cover these:")
        for s in SKIPPED[:8]:
            print(f"       {s}")
        if len(SKIPPED) > 8:
            print(f"       …and {len(SKIPPED) - 8} more")

    if not findings:
        scope = "the files it read" if SKIPPED else "any live surface"
        print(f"\nCLEAN — no retired claim is asserted on {scope}.")
        return 1 if SKIPPED and args else 0
    print(f"\n{len(findings)} RETIRED CLAIM(S) ASSERTED:\n")
    for f in findings:
        print(f.render())
        print()
    print("Each is a decision that was made and never propagated. Fix the wording, or — if the "
          "decision itself changed — update the registry entry in the same commit.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
