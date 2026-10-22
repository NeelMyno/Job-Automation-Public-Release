#!/usr/bin/env python3
"""voice_check.py: the hard-fact and banned-phrase check on copy written as you.

How your writing SOUNDS is owned by knowledge-base/17-writing.md, and the real voice gate is the
read-aloud plus the fresh-reviewer pass that file describes ("How a piece of writing gets made").
This script is NOT a voice gate. Every writing-style detector it used to carry (hype, false modesty,
story shapes, the "too-neat mirror" family and its blanket ban on "already" / "exactly", rule of
three, antithesis, intensifiers and the rest) was retired: rounds of style detectors taught writers
to write to the checker, and the output passed while still reading like a machine. Passing this
says nothing about whether the voice is right.

What it still checks, and only this:
  - Dashes: em-dash, en-dash, spaced double-dash in outbound prose (17-writing.md, punctuation).
  - Over-confidence: a short built-in list of phrases that claim you have it all figured out
    ("that's exactly how I work", "perfect fit", "I know exactly how", "the same problem I solved").
  - A work-authorization or sponsorship mention nobody asked about. Your own answer bank
    (knowledge-base/02-work-authorization.md, "Default: silence", and
    knowledge-base/12-application-answers.md) says to answer it only where a form or a person asks.
    Turn this family off with WORK_AUTH_MENTION_CHECK = False in scripts/config.py.
  - YOUR never-say list: the facts and phrases YOU list in the "Never-say list" section of
    knowledge-base/17-writing.md (a date you never put in prose, a wrong fact about your own work
    that keeps creeping back, a phrase you hate). Ships empty; nothing personal is hardcoded here.

Give it the SENDABLE text, not a whole dossier file. Usage:
  python3 scripts/voice_check.py path/to/message.txt
  python3 scripts/voice_check.py --sendable path/to/cover-note.md
  python3 scripts/voice_check.py --text "the message"
  echo "the message" | python3 scripts/voice_check.py -
  python3 scripts/voice_check.py --selftest
Exit 0 = clean, 1 = findings, 2 = usage error.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRITING_KB = REPO / "knowledge-base" / "17-writing.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # every knob is optional; a missing config.py or a missing value falls back to the default
    import config as _config  # type: ignore
except Exception:  # pragma: no cover
    _config = None

DASH_CAT = "em/en-dash"          # hooks.py treats this category as advisory; keep the name stable
OVER_CAT = "over-confidence"
AUTH_CAT = "work-authorization mention (only when asked)"
NEVER_CAT = "never-say (your list, 17-writing.md)"

# (category, [patterns], why + the fix). Patterns are case-insensitive.
RULES: list[tuple[str, list[str], str]] = [
    (DASH_CAT, ["\u2014", "\u2013", r"(?<!\w)--(?!\w)"],
        "Em-dash, en-dash, or double-dash (17-writing.md, punctuation). Use a period or a comma. "
        "(Feed the SENDABLE prose, not a dossier file: markdown headers and date ranges use dashes "
        "structurally.)"),

    (OVER_CAT, [
        r"\bthat'?s exactly\b",
        r"\bexactly how I\b",
        r"\b(?:is|was) already how I\b",
        r"\bexactly (?:what|the kind of (?:thing|work|problem)) I(?:'ve| have)? "
        r"(?:do|did|done|build|built|work on|worked on)\b",
        r"\bthe (?:very |exact )?same problems? I(?:'ve| have)? "
        r"(?:solved|solve|worked on|work on|faced|face|tackled)\b",
        r"\bperfect fit\b",
        r"\bI know exactly how\b",
    ], "Over-confident: it sounds like you have it all figured out (17-writing.md, never "
       "over-confident). Say what you did and what about their work it made you think of, and let "
       "the reader make the link."),

    # First-person status claims only, so a note that documents the rule ("no work-authorization
    # content in the body") never fires. Off when the copy answers the question (_AUTH_ALLOW).
    (AUTH_CAT, [
        r"\bI(?:'m| am)\s+(?:currently\s+)?(?:on\s+an?\s+(?:\w+\s+)?visa|authori[sz]ed\s+to\s+work)\b",
        r"\bI\s+(?:do\s+not|don'?t|won'?t|will\s+not)\s+(?:need|require)\s+(?:any\s+)?(?:visa\s+)?sponsorship\b",
        r"\bmy\s+(?:visa|work\s+authori[sz]ation|work\s+permit|immigration)\b",
        r"\bno\s+sponsorship\s+(?:is\s+)?(?:needed|required)\b",
        r"\b(?:I|I'm|I'd|I'll|I've|me|my)\b[^.!?\n]{0,80}?\b(?:sponsorship|sponsor\s+me)\b",
        r"\bsponsorship\b[^.!?\n]{0,80}?\b(?:I|I'm|I'd|I'll|me|my)\b",
        r"(?:^|[.!?]\s+)(?:(?:will|would|'ll)\s+)?(?:need|require)s?\s+(?:an?\s+)?(?:visa\s+)?sponsorship\b",
    ], "A work-authorization or sponsorship claim nobody asked about (knowledge-base/02, 'Default: "
       "silence'). Cut it. If the text answers that question, keep the question in the same "
       "paragraph or mark the answer `voice:allow visa`."),
]

# The work-authorization family is off when the copy is ANSWERING that question: the question itself
# (with its "?") sits in the same paragraph, or the answer carries the visible marker.
_AUTH_ALLOW = re.compile(r"voice:allow\s+visa\b"
                         r"|\b(?:visa|sponsor\w*|authori[sz]ed\s+to\s+work|work[- ]authori[sz]ation|citizen\w*)"
                         r"\b[^?\n]{0,120}\?", re.I)


# Your never-say list
# Format, inside the "## Never-say list" section of knowledge-base/17-writing.md (HTML comments are
# ignored, so the shipped examples never fire):
#   - `a literal phrase` : why it is banned
#   - `re:a regular expression` : why
_NEVER_ITEM = re.compile(r"^\s*[-*]\s+`(?P<pat>[^`]+)`\s*(?:[:,]\s*(?P<why>.*))?$")


def parse_never_say(md: str) -> list[tuple[str, str]]:
    """[(regex, why)] from the Never-say section of a 17-writing.md text."""
    md = re.sub(r"<!--[\s\S]*?-->", "", md)
    m = re.search(r"(?im)^##\s+Never-say list\b.*$", md)
    if not m:
        return []
    rest = md[m.end():]
    nxt = re.search(r"(?m)^##\s", rest)
    section = rest[: nxt.start()] if nxt else rest
    out = []
    for ln in section.splitlines():
        im = _NEVER_ITEM.match(ln)
        if not im:
            continue
        raw = im.group("pat").strip()
        why = (im.group("why") or "").strip() or "on your never-say list"
        if raw.lower().startswith("re:"):
            pat = raw[3:].strip()
            try:
                re.compile(pat)
            except re.error:
                continue  # a broken pattern is skipped, never a crash
        else:
            pat = r"(?<!\w)" + re.escape(raw) + r"(?!\w)"
        if pat:
            out.append((pat, why))
    return out


_NEVER_CACHE: list[tuple[str, str]] | None = None


def never_say() -> list[tuple[str, str]]:
    global _NEVER_CACHE
    if _NEVER_CACHE is None:
        try:
            _NEVER_CACHE = parse_never_say(WRITING_KB.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            _NEVER_CACHE = []
    return _NEVER_CACHE


def _auth_check_on() -> bool:
    return bool(getattr(_config, "WORK_AUTH_MENTION_CHECK", True)) if _config else True


def sendable_prose(text: str) -> str:
    """The copy a reader actually receives, lifted out of a note or answer FILE.

    The text after the first `---` fence is copy: the segment right after it always, and each later
    fence-separated segment too (multi-answer files), EXCEPT a later segment that opens with a
    markdown heading, which is a notes section (a cover note's "## Why these specifics" and the
    like), not something sent. Inside what is kept, markdown headings, `**Label:**` metadata lines,
    table rows (`| a | b |`, including the `|---|---|` separator) and HTML comments are dropped.
    No fence at all means the whole text is copy. fill_ready.py reads a cover note through this
    same function, so the two gates can never disagree about what the letter is.
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    parts = re.split(r"(?m)^[ \t]*---[ \t]*$", text)
    if len(parts) >= 2:
        kept = [parts[1]]
        for seg in parts[2:]:
            first = next((ln for ln in seg.splitlines() if ln.strip()), "")
            if re.match(r"^\s*#", first):
                continue
            kept.append(seg)
        body = "\n".join(kept)
    else:
        body = text
    out = []
    for ln in body.splitlines():
        s = re.sub(r"^\s*>\s?", "", ln)
        if re.match(r"^\s*#", s):
            continue
        if re.match(r"^\s*\*\*[^*]+:\*\*", s):
            continue
        if re.match(r"^\s*\|.*\|\s*$", s):
            continue
        out.append(s)
    return "\n".join(out)


def check(text: str, never: list[tuple[str, str]] | None = None,
          auth_check: bool | None = None) -> list[tuple[str, str, str]]:
    """[(category, matched fragment, why)]. `never` defaults to your 17-writing.md list and
    `auth_check` to config.py; the selftest passes both explicitly."""
    findings: list[tuple[str, str, str]] = []
    never = never_say() if never is None else never
    auth_on = _auth_check_on() if auth_check is None else auth_check
    allow_auth = bool(re.search(r"voice:allow\s+visa\b", text, re.I))
    rules = list(RULES) + [(NEVER_CAT, [p], f"On your never-say list: {why}") for p, why in never]
    for cat, pats, why in rules:
        if cat == AUTH_CAT and (allow_auth or not auth_on):
            continue
        seen = set()
        for p in pats:
            for m in re.finditer(p, text, re.I):
                if cat == AUTH_CAT:
                    # asked = the question (with its "?") in the SAME paragraph as the claim, so a
                    # quoted form question in a notes section never switches the check off above it
                    a = text.rfind("\n\n", 0, m.start())
                    b = text.find("\n\n", m.end())
                    if _AUTH_ALLOW.search(text[a + 1 if a >= 0 else 0: b if b >= 0 else len(text)]):
                        continue
                frag = m.group(0).strip()
                key = (cat, frag.lower())
                if key in seen:
                    continue
                seen.add(key)
                findings.append((cat, frag, why))
    return findings


def render(findings: list[tuple[str, str, str]]) -> str:
    if not findings:
        return ("voice_check: CLEAN of the hard facts and banned phrases (dashes, over-confidence, an "
                "unasked work-authorization mention, your never-say list).\n"
                "  This says nothing about the voice. Read it out loud as yourself, to this one person, "
                "and have a fresh reviewer read it against knowledge-base/17-writing.md.")
    out = [f"voice_check: {len(findings)} finding(s), fix before this passes.\n"]
    for cat, frag, why in findings:
        out.append(f"  [{cat}] “{frag}”\n      {why}")
    return "\n".join(out)


def selftest() -> int:
    passed = failed = 0
    results = []

    def want(label, cond):
        nonlocal passed, failed
        passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
        results.append((label, cond))

    def cats(t, never=(), auth=True):
        return {c for c, _, _ in check(t, never=list(never), auth_check=auth)}

    # dashes
    want("dash: em-dash flagged", DASH_CAT in cats("I reorganized the stockroom \u2014 all of it."))
    want("dash: en-dash flagged", DASH_CAT in cats("I reorganized the stockroom \u2013 all of it."))
    want("dash: spaced double-dash flagged", DASH_CAT in cats("I reorganized the stockroom -- all of it."))
    want("dash: a hyphenated word is clean", DASH_CAT not in cats("It was a long-running, part-time role."))

    # over-confidence
    for txt in ["That's exactly how I work.", "that is exactly how I approach a month-end close.",
                "Owning the system end to end is already how I work.",
                "It's the same problem I solved at Globex.", "This is the same problem I worked on last year.",
                "I think I'm a perfect fit for the role.", "I know exactly how to fix that schedule.",
                "That is exactly what I built at Initech."]:
        want(f"over-confidence flagged: {txt!r}", OVER_CAT in cats(txt))
    for txt in ["Your patient intake form reminded me of a problem we had at Globex.",
                "It took exactly five years.", "I have already relocated to the city.",
                "I'm not sure yet how your team splits that work, so I'd like to ask."]:
        want(f"over-confidence clean: {txt!r}", OVER_CAT not in cats(txt))

    # work-authorization mention only when asked
    want("auth: unasked line in a cover body flagged",
         AUTH_CAT in cats("My work is linked below. I'm authorized to work in the US and can start."))
    want("auth: 'don't need sponsorship' flagged", AUTH_CAT in cats("I don't need sponsorship to start."))
    want("auth: 'my visa' flagged", AUTH_CAT in cats("Happy to talk about my visa timeline on a call."))
    want("auth: 'I'd need sponsorship later' flagged",
         AUTH_CAT in cats("I can start right away, and I'd need sponsorship later."))
    want("auth: subjectless 'Will need sponsorship later.' flagged",
         AUTH_CAT in cats("Open to relocating. Will need sponsorship later."))
    want("auth: an answer to the question in the same paragraph is clean",
         AUTH_CAT not in cats("Will you now or in the future require sponsorship? No. I don't need sponsorship."))
    want("auth: a question in a LATER notes paragraph does not switch it off",
         AUTH_CAT in cats("I'm authorized to work in the US.\n\n"
                          "- Form: \"Will you now or in the future require sponsorship?\" -> No"))
    want("auth: the voice:allow visa marker clears it",
         AUTH_CAT not in cats("I'm authorized to work in the US. <!-- voice:allow visa: recruiter asked -->"))
    want("auth: 'I opt for' (the verb) is clean", AUTH_CAT not in cats("I opt for the early shift when I can."))
    want("auth: a note documenting the rule is clean", AUTH_CAT not in cats("- No sponsorship content in the body."))
    want("auth: config off turns the family off",
         AUTH_CAT not in cats("I don't need sponsorship to start.", auth=False))

    # the never-say list, parsed from a synthetic 17-writing.md
    kb = ("# 17 Writing\n\n## Never-say list\n\n<!--\n- `example phrase` : an example that must not fire\n-->\n\n"
          "- `March 2024 to present` : never put my Acme dates in prose\n"
          "- `re:\\bonly one (?:AI )?feature\\b` : the Northwind tool has several\n"
          "- `re:([unclosed` : a broken pattern is skipped\n\n## Next section\n\n- `not in the list` : x\n")
    ns = parse_never_say(kb)
    want("never-say: two valid items parsed (comment, broken regex and next section ignored)", len(ns) == 2)
    want("never-say: literal phrase flagged", NEVER_CAT in cats("I was at Acme from March 2024 to present.", ns))
    want("never-say: regex item flagged", NEVER_CAT in cats("We shipped only one AI feature.", ns))
    want("never-say: commented example does not fire", NEVER_CAT not in cats("an example phrase here", ns))
    want("never-say: an item after the section does not fire", NEVER_CAT not in cats("not in the list", ns))
    want("never-say: an empty list flags nothing", NEVER_CAT not in cats("March 2024 to present", []))
    want("never-say: no section means no items", parse_never_say("# x\n\n- `a` : b\n") == [])

    # the retired style shapes are NOT flagged any more
    for txt in ["I'm a charge nurse who runs the whole floor myself.",
                "It's not a draft, but a real budget people use.",
                "I plan, I teach, and I grade.",
                "I'm so excited and passionate about this role.",
                "It's the strongest, killer, world-class work I've done.",
                "I already did that, and exactly that.",
                "I did the count. I made the plan. I'd trained the crew. I've closed it out."]:
        want(f"retired shape no longer flagged: {txt!r}", not check(txt, never=[], auth_check=True))

    plain = ("Hi Jordan, I saw your clinic is moving to evening hours. At Globex I ran the front desk "
             "through the same change, and what we learned is that the first two weeks are mostly about "
             "the phone queue, not the schedule. Happy to talk if that's useful. Talk soon")
    want("a plain human message is clean on every family", not check(plain, never=[], auth_check=True))

    # sendable_prose
    want("sendable_prose checks every answer after the first fence",
         DASH_CAT in cats(sendable_prose("# Q\n**note:** x\n---\nAnswer one.\n---\nAnswer two \u2014 later.\n")))
    want("sendable_prose drops metadata before the fence",
         DASH_CAT not in cats(sendable_prose("# Q \u2014 title\n**v3 note:** a \u2014 b\n---\nPlain answer.\n")))
    _cover = ("# Cover note: Acme\n<!-- split on a bare --- line -->\n\n---\nHi,\n\nPlain letter.\n"
              "---\n\n## Why these specifics\n\n| Line | Pillar |\n|---|---|\n| a | b |\n\n"
              "## Deliberately NOT said\n- held back \u2014 a note to self\n")
    want("sendable_prose: a cover note's table separator and notes sections are not copy (S6)",
         cats(sendable_prose(_cover)) == set())
    want("sendable_prose: a dash inside the letter itself is still caught",
         DASH_CAT in cats(sendable_prose(_cover.replace("Plain letter.", "Plain \u2014 letter."))))
    want("sendable_prose drops a `> **Source:**` line",
         DASH_CAT not in cats(sendable_prose("# Q\n---\n> **Source:** JD \u2014 quoted\nMy answer is plain.\n")))

    print("voice_check.py selftest (hard facts and named phrases only)\n")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    sendable = False
    if argv and argv[0] == "--sendable":
        sendable = True
        argv = argv[1:]
    if len(argv) >= 2 and argv[0] == "--text":
        text = argv[1]
    elif argv and argv[0] == "-":
        text = sys.stdin.read()
    elif argv:
        try:
            text = open(argv[0], encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"voice_check: cannot read {argv[0]}: {e}", file=sys.stderr)
            return 2
    else:
        print(__doc__)
        return 2
    if sendable:
        text = sendable_prose(text)
    findings = check(text)
    print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
