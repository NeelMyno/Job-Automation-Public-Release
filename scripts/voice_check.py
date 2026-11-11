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
    ("perfect fit", "I know exactly how").
  - A work-authorization or sponsorship mention nobody asked about. Your own answer bank
    (knowledge-base/02-work-authorization.md, "Default: silence", and
    knowledge-base/12-application-answers.md) says to answer it only where a form or a person asks.
    Turn this family off with WORK_AUTH_MENTION_CHECK = False in scripts/config.py.
  - A filler question: a process question or curious closer nobody needs answered ("what this
    round covers", "so I can prepare"). If you really do want the answer, keep it and mark the text
    `voice:allow filler`.
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


def _config():
    """config.py, or None. Read only when a check needs it, so `import voice_check` alone (which
    every --selftest entry does) never touches your settings. Every knob is optional; a missing
    config.py or a missing value falls back to the default."""
    try:
        import config  # type: ignore
        return config
    except Exception:  # pragma: no cover
        return None


# Every --selftest runs here. A selftest proves the gate works; it must never depend on what you
# have written into this copy, or filling in your own files turns it red (one word on your never-say
# list used to do it). So the entry points re-run themselves inside a temporary copy holding only the
# scripts and the synthetic fixture dossier, with a config.py that sets nothing. Your knowledge base,
# tracker, ledgers, résumé, claims manifest and settings are not in it and cannot be read.
SANDBOX_MARK = ".selftest-sandbox"
SANDBOX_SHIPPED = ("applications/EXAMPLE-fixture-selftest", "applications/TEMPLATE-company-role")
SANDBOX_EMPTY_DIRS = ("knowledge-base", "pipeline", "resume", "projects", "ops", "applications")
SANDBOX_CONFIG = """# Written by voice_check.selftest_in_sandbox: no settings, so every knob is at its default.
def local_now():
    from datetime import datetime
    return datetime.now().astimezone()


def local_stamp():
    t = local_now()
    return f"{t:%Y-%m-%d} {t.strftime('%I:%M %p').lstrip('0')} {t.tzname() or ''}".rstrip()
"""


def build_sandbox(repo: Path, dest: Path) -> None:
    """Fill the empty folder `dest` with the shipped code and fixtures only."""
    import shutil
    import subprocess
    shutil.copytree(repo / "scripts", dest / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "config.py"))
    (dest / "scripts" / "config.py").write_text(SANDBOX_CONFIG, encoding="utf-8")
    for rel in SANDBOX_EMPTY_DIRS:
        (dest / rel).mkdir(parents=True, exist_ok=True)
    for rel in SANDBOX_SHIPPED:
        if (repo / rel).is_dir():
            shutil.copytree(repo / rel, dest / rel)
    (dest / SANDBOX_MARK).write_text("", encoding="utf-8")
    try:  # the Stop-hook cases read `git status`; a copy downloaded as a ZIP has no .git of its own
        subprocess.run(["git", "init", "-q"], cwd=dest, capture_output=True, env=_clean_env(), timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


def _clean_env() -> dict:
    """os.environ minus GIT_*: run from inside a git hook, those would aim git at your real repo."""
    import os
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def selftest_in_sandbox(script: str) -> None:
    """Re-run `script --selftest` in a throwaway copy and exit with its result. Returns only when
    already inside one, and the selftest then runs as normal."""
    import subprocess
    import tempfile
    path = Path(script).resolve()
    repo = path.parents[1]
    if (repo / SANDBOX_MARK).is_file():
        return
    try:
        with tempfile.TemporaryDirectory(prefix="selftest-") as td:
            dest = Path(td).resolve()
            build_sandbox(repo, dest)
            rc = subprocess.run([sys.executable, str(dest / "scripts" / path.name)] + sys.argv[1:],
                                cwd=dest, env=_clean_env()).returncode
    except OSError as e:
        print(f"SELFTEST CANNOT RUN: could not build its temporary copy ({e}). The gate is UNVERIFIED.")
        rc = 1
    sys.exit(rc)

DASH_CAT = "em/en-dash"          # hooks.py treats this category as advisory; keep the name stable
OVER_CAT = "over-confidence"
AUTH_CAT = "work-authorization mention (only when asked)"
NEVER_CAT = "never-say (your list, 17-writing.md)"
FILLER_CAT = "filler question (17-writing.md)"   # hooks.py treats this category as advisory; keep the name stable

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

    (FILLER_CAT, [
        r"\bwhat (?:this|the|that|the next) (?:round|call|interview|conversation|step|meeting|chat) "
        r"(?:will )?(?:covers?|looks? like|involves?|entails?|is about)\b",
        r"\bwho I(?:['\u2019]ll| will) be (?:talking|speaking|meeting|chatting) (?:with|to)\b",
        r"\bwho I(?:['\u2019]m| am) (?:meeting|talking|speaking) with\b",
        r"\b(?:so (?:that )?I can|I['\u2019]d like to|I would like to|to help me) prepare\b",
        r"\bprepare (?:accordingly|properly|ahead of time)\b",
        r"\banything (?:specific )?I should (?:prepare|know|review|bring|look at)\b",
        r"\bI(?:['\u2019]m| am|['\u2019]d| would) (?:be )?curious (?:whether|how|if|what|to hear|about)\b",
    ], "A filler question: it asks something you don't need answered, just to fill space (17-writing.md). "
       "Cut it. If you really do want the answer, keep it and mark the text `voice:allow filler`."),
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
    return bool(getattr(_config(), "WORK_AUTH_MENTION_CHECK", True))


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
    # Comments are not copy, but a voice:allow marker inside one has to survive or it could never work here.
    text = re.sub(r"<!--.*?-->",
                  lambda c: " ".join(f"<!-- voice:allow {k} -->" for k in re.findall(r"voice:allow\s+(\w+)", c.group(0))),
                  text, flags=re.S)
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
    allow_filler = bool(re.search(r"voice:allow\s+filler\b", text, re.I))
    rules = list(RULES) + [(NEVER_CAT, [p], f"On your never-say list: {why}") for p, why in never]
    for cat, pats, why in rules:
        if cat == AUTH_CAT and (allow_auth or not auth_on):
            continue
        if cat == FILLER_CAT and allow_filler:
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
                "unasked work-authorization mention, a filler question, your never-say list).\n"
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
    want("dash: em-dash flagged", DASH_CAT in cats("Two of the vans \u2014 the white ones \u2014 need tires."))
    want("dash: en-dash flagged", DASH_CAT in cats("Two of the vans \u2013 the white ones \u2013 need tires."))
    want("dash: spaced double-dash flagged", DASH_CAT in cats("Two of the vans -- the white ones -- need tires."))
    want("dash: a hyphenated word is clean", DASH_CAT not in cats("A part-time, well-paid post at a two-story clinic."))

    # over-confidence
    for txt in ["That's exactly the wrench the crew needed.", "A warehouse recount is exactly how I spent last spring.",
                "Double-entry reconciliation was already how I closed the books.",
                "The Hooli loading dock has the very same problem I faced at Umbrella.",
                "Your bakery has the same problems I tackled at Northwind.",
                "A night-shift cashier job would be a perfect fit.", "I know exactly how your stockroom should run.",
                "Reworking a bus route is exactly what I did at Initech."]:
        want(f"over-confidence flagged: {txt!r}", OVER_CAT in cats(txt))
    for txt in ["We tried a paper sign-in sheet at Globex and dropped it after a month.",
                "The lease ran for exactly nine months.", "I've already moved my tools to the new shop.",
                "I don't know how your crews divide the weekend calls."]:
        want(f"over-confidence clean: {txt!r}", OVER_CAT not in cats(txt))

    # work-authorization mention only when asked
    want("auth: unasked line in a cover body flagged",
         AUTH_CAT in cats("References attached. I am authorized to work here."))
    want("auth: 'won't require sponsorship' flagged", AUTH_CAT in cats("I won't require sponsorship for this post."))
    want("auth: 'my visa' flagged", AUTH_CAT in cats("My visa paperwork is with the consulate this month."))
    want("auth: 'I'd need sponsorship later' flagged",
         AUTH_CAT in cats("The ward rota suits me, though I'd need sponsorship next year."))
    want("auth: subjectless 'Will need sponsorship later.' flagged",
         AUTH_CAT in cats("Weekends are fine. Will need sponsorship after June."))
    want("auth: an answer to the question in the same paragraph is clean",
         AUTH_CAT not in cats("Will you now or in the future require sponsorship? No. I won't require sponsorship."))
    want("auth: a question in a LATER notes paragraph does not switch it off",
         AUTH_CAT in cats("I'm authorized to work in the US.\n\n"
                          "- Form: \"Will you now or in the future require sponsorship?\" -> No"))
    want("auth: the voice:allow visa marker clears it",
         AUTH_CAT not in cats("I'm authorized to work in the US. <!-- voice:allow visa: the form asked -->"))
    want("auth: 'I opt for' (the verb) is clean", AUTH_CAT not in cats("I opt for the ferry over the bridge."))
    want("auth: a note documenting the rule is clean", AUTH_CAT not in cats("- Keep sponsorship out of the cover letter body."))
    want("auth: config off turns the family off",
         AUTH_CAT not in cats("I won't require sponsorship for this post.", auth=False))

    # filler questions
    for txt in ["Before the panel, could you tell me what the next interview involves?",
                "Could you let me know who I'll be speaking with at the depot?",
                "Please send the audit scope so I can prepare.",
                "Is there anything specific I should review before the classroom visit?",
                "I'm curious whether your drivers bid on routes."]:
        want(f"filler flagged: {txt!r}", FILLER_CAT in cats(txt))
    for txt in ["Thursday at 3 works for me. Should I bring my nursing license or will HR copy it online?",
                "My shift ends at 4, so any time after that is fine.",
                "I prepared the quarter-end schedules for Umbrella."]:
        want(f"filler clean: {txt!r}", FILLER_CAT not in cats(txt))
    want("filler: the voice:allow filler marker clears it",
         FILLER_CAT not in cats("Please send the audit scope so I can prepare. <!-- voice:allow filler -->"))
    want("filler: a voice:allow marker survives sendable_prose",
         FILLER_CAT not in cats(sendable_prose("# Q\n---\nPlease send the scope so I can prepare.\n"
                                                "<!-- voice:allow filler: I need the file list -->\n---\n")))
    want("auth: a voice:allow visa marker survives sendable_prose",
         AUTH_CAT not in cats(sendable_prose("# Q\n---\nI'm authorized to work in the US.\n"
                                              "<!-- voice:allow visa: the recruiter asked -->\n---\n")))
    want("sendable_prose: other comments are still dropped",
         "hidden" not in sendable_prose("# Q\n---\nPlain answer. <!-- hidden note -->\n---\n"))

    # the never-say list, parsed from a synthetic 17-writing.md
    kb = ("# 17 Writing\n\n## Never-say list\n\n<!--\n- `example phrase` : an example that must not fire\n-->\n\n"
          "- `Bay 7 forklift` : that certification lapsed\n"
          "- `re:\\bfour[- ]year degree\\b` : I finished two years\n"
          "- `re:([unclosed` : a broken pattern is skipped\n\n## Next section\n\n- `not in the list` : x\n")
    ns = parse_never_say(kb)
    want("never-say: two valid items parsed (comment, broken regex and next section ignored)", len(ns) == 2)
    want("never-say: literal phrase flagged", NEVER_CAT in cats("I ran the Bay 7 forklift at Acme.", ns))
    want("never-say: regex item flagged", NEVER_CAT in cats("I hold a four-year degree.", ns))
    want("never-say: commented example does not fire", NEVER_CAT not in cats("an example phrase here", ns))
    want("never-say: an item after the section does not fire", NEVER_CAT not in cats("not in the list", ns))
    want("never-say: an empty list flags nothing", NEVER_CAT not in cats("Bay 7 forklift", []))
    want("never-say: no section means no items", parse_never_say("# x\n\n- `a` : b\n") == [])

    # the retired style shapes are NOT flagged any more
    for txt in ["Dental hygienists like me keep a spare mirror.",
                "The fence isn't cedar but pine.",
                "Sweep, mop, lock up.",
                "We were thrilled and honored to host the bake sale.",
                "The bakery makes a killer, world-class rye.",
                "We already swapped the filters, exactly on schedule.",
                "I counted pallets. I taped boxes. I drove the forklift. I went home."]:
        want(f"retired shape no longer flagged: {txt!r}", not check(txt, never=[], auth_check=True))

    plain = ("Hello Jordan, the Acme posting says the bookkeeper closes the month alone. I did that at "
             "Globex for three years with two part-time clerks. I can send a sample reconciliation on Monday.")
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
         DASH_CAT not in cats(sendable_prose("# Q\n---\n> **Source:** posting \u2014 quoted\nMy answer is plain.\n")))

    print("voice_check.py selftest (hard facts and named phrases only)\n")
    # The sandbox every --selftest runs in: it must hold none of the user's files, and a real run must
    # still read the never-say list (the sandbox hides it from selftests, never from a real check).
    want("sandbox: this selftest sees an empty never-say list", never_say() == [])
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        user, box = Path(td) / "user", Path(td) / "box"
        box.mkdir()
        files = {"knowledge-base/17-writing.md": "## Never-say list\n\n- `the` : a word nobody can avoid\n- `re:.` : everything\n",
                 "knowledge-base/12-application-answers.md": "my answers", "pipeline/tracker.html": "my tracker",
                 "pipeline/sent-ledger.md": "my ledger", "resume/Sam Lee.pdf": "my resume",
                 "projects/CLAIMS-MANIFEST.md": "my manifest", "scripts/config.py": "SETTING = 'mine'\n",
                 "applications/acme-role/application.md": "my dossier",
                 "applications/EXAMPLE-fixture-selftest/application.md": "shipped fixture"}
        for rel, body in files.items():
            (user / rel).parent.mkdir(parents=True, exist_ok=True)
            (user / rel).write_text(body, encoding="utf-8")
        (user / "scripts" / "voice_check.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
        build_sandbox(user, box)
        want("sandbox: holds no knowledge base, tracker, ledger, resume, manifest or dossier of the user's",
             not any((box / rel).exists() for rel in files
                     if rel != "scripts/config.py" and "EXAMPLE" not in rel))
        want("sandbox: the shipped fixture dossier is there", (box / "applications/EXAMPLE-fixture-selftest").is_dir())
        want("sandbox: config.py is the empty stand-in, not the user's",
             "SETTING" not in (box / "scripts" / "config.py").read_text(encoding="utf-8"))
        script = user / "scripts" / "voice_check.py"
        real = subprocess.run([sys.executable, str(script), "-"], input="Hello there.", capture_output=True,
                              text=True, timeout=60)
        want("sandbox: a REAL run still applies the user's never-say list", real.returncode != 0 and NEVER_CAT in real.stdout)
    # A selftest that adopts the sandbox after it imports config has already read your settings. These
    # few open no file of yours (audited), so they need none; a new script has to pick a side here.
    no_read = {"adr_debt.py", "doctor.py", "open_tab_sweep.py", "presubmit_check.py", "render_cover.py",
               "subject_check.py", "tracker_check.py", "why_check.py", "work_history_check.py"}
    boxed, bad = 0, []
    for f in sorted(Path(__file__).resolve().parent.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        if '"--selftest"' not in src or f.name == "voice_check.py" or f.name in no_read:
            continue
        first_config = re.search(r"(?m)^\s*(?:import config\b|from config import\b)", src)
        at = src.find("selftest_in_sandbox(__file__)")
        boxed += at >= 0
        if at < 0 or (first_config and first_config.start() < at):
            bad.append(f.name)
    want(f"sandbox: every selftest enters it before importing config ({boxed} scripts): bad={bad}", boxed >= 20 and not bad)
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
        selftest_in_sandbox(__file__)
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
