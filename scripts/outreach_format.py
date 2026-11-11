#!/usr/bin/env python3
"""outreach_format.py: every person you are handed comes with every part that applies to them.

WHY THIS EXISTS
A half-finished handover (a name with a note but no message, or a message with no way to send it)
is what makes you have to ask an agent for the same format again and again. Prose instructions
don't execute reliably on their own; a check does.

THE THREE PARTS, and why each one is load-bearing
1. **The person's profile.** Without it you have to go find the person before you can act. The
   handover stops being actionable and becomes homework. A LinkedIn URL is the usual form. Plenty of
   people have none (an office manager at a small practice), so a `Profile:` line holding any other
   profile or staff-page URL counts, and so does `Profile: none found (where you looked)`. For
   those people the connection note and the InMail verdict do not apply, and this script names the
   LinkedIn gap so the handover says it out loud.
2. **The connection note** (under 300 chars). The free, always-available channel. Connection state
   is unknowable in advance, so this always ships.
3. **The direct message**, with an explicit `Use InMail: YES/NO` verdict. If you're already
   connected, it goes as a normal message; if not, it follows the accept. InMail credits are scarce
   and accounted (`pipeline/inmail-ledger.md`), so the verdict travels with the copy.

THE REFERENCE SHAPE
Per person, on disk, inside `## The messages`:

    ### N · Full Name: why them, in a few words
    **Profile: https://www.linkedin.com/in/handle**
    **Connection note (NNN chars):**
    > ...
    **Direct message · Use InMail: NO** (reason)
    > ...

and in chat, grouped by company, read verbatim off that file:

    ## COMPANY: Role
    **Name**, why · https://www.linkedin.com/in/handle · *ask = a referral*
    - **Note:** ...
    - **DM:**   ...

WHAT THIS DOES NOT CHECK, said out loud
It cannot read what an agent types into chat. It gates the FILE the chat is supposed to be read off.
If an agent invents copy in chat that is not on disk, that is a grounding failure and
`verify_claims.py`'s problem, not this one. It also does not judge whether the copy is any good;
`verify_claims.py` owns length and evidence, and `knowledge-base/17-writing.md` (the one owner of
voice) owns how it sounds, judged by a read-aloud and a fresh reviewer.

A person with NO parts drafted is research-stage and is skipped, deliberately: a roster of people to
research later is not outreach material. A person with SOME parts is the failure this catches.

USAGE
    python3 scripts/outreach_format.py            # every dossier -> exit 1 if any person is partial
    python3 scripts/outreach_format.py <path>...  # specific files (used by the PostToolUse hook)
    python3 scripts/outreach_format.py --selftest
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parents[1]

PROFILE = re.compile(r"linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)
# A person with no LinkedIn: any other URL on a `Profile:` line, or an explicit `Profile: none found`.
PROFILE_LINE = re.compile(r"\bProfile\*{0,2}\s*:\s*\*{0,2}\s*(?P<value>[^\n]*)", re.I)
PROFILE_NONE = re.compile(r"none found\b", re.I)
# A template slot such as [linkedin.com/in/... URL] is not a URL; a markdown link [text](url) is.
UNFILLED_SLOT = re.compile(r"\[[^\]]*\](?!\()")
# The posting has no req or job ID (a small employer's own site), recorded on its own line.
REQ_NONE = re.compile(r"^\s*[-*]?\s*\*{0,2}Req(?:/job ID)?\*{0,2}\s*:\s*\*{0,2}\s*none on posting\b", re.I | re.M)
PROFILE_PART = "the person's profile (a LinkedIn or other profile URL on a `Profile:` line, or `Profile: none found`)"
# A heading still holding the template's own slot, such as "[Name], [Role] at [Company]", is nobody.
PLACEHOLDER_HEADING = re.compile(r"^\[[^\]]*\]")
# An ordinal prefix is a real, common dossier convention ("**#1 Connection note (272 chars):**",
# "**#2 Direct message · Use InMail: NO**"). Without accounting for it these regexes go blind to a
# whole block, reporting "missing the connection note" while the note sits two lines below.
ORD = r"(?:#?\d+\s*[.):·-]?\s*)?"
NOTE = re.compile(r"^\s*[-*>]?\s*\*{0,2}" + ORD + r"(?:connection[ -]note|note)\b", re.I | re.M)
DM = re.compile(r"^\s*[-*>]?\s*\*{0,2}" + ORD + r"(?:direct[ -]message|DM|message)\b", re.I | re.M)
INMAIL = re.compile(r"use\s+inmail\s*:?\s*(yes|no)", re.I)

# A person heading inside `## The messages`: "### 1 · Jordan Rivera: the hiring manager"
PERSON = re.compile(r"^###\s+(?:\d+\s*[·.)-]\s*)?(?P<name>[^\n]+?)\s*$", re.M)

# Headings that are section furniture, not a person.
NOT_A_PERSON = re.compile(
    r"^(?:drafted|cards?\b|the messages|how to send|status|notes?\b|sources?\b|ask-shape|"
    r"none drafted|not drafted|research|template|format|context|summary|log\b)", re.I)

# An explicit, greppable statement that this person is deliberately not drafted yet.
NOT_DRAFTED = re.compile(r"NOT[ -]DRAFTED|no messages? (?:yet|drafted)|research(?:-| )stage|"
                         r"deliberately not drafted|do not send|skip\b", re.I)

# ALREADY SENT is not "about to be handed over".
# This gate exists to stop a HALF-FINISHED HANDOVER reaching you. Copy that already went to a real
# human cannot be fixed, and rewriting it would be dishonest about what was sent. Leaving it red
# forever recreates a worse defect: a permanently-on warning nobody reads, hiding the real finding
# inside the noise.
#
# The anti-suppression wall. This marker is deliberately narrow and greppable:
#   1. it must state a DATE, e.g. "SENT 2026-01-01", so it records history, not an opinion;
#   2. it is matched PER PERSON BLOCK, never per file, so it cannot blanket a dossier;
#   3. a block containing BOTH a sent marker and an unsent draft still fails (tested below),
#      because the sent line does not reach the newer copy underneath it.
# If you're tempted to add this marker to something that hasn't actually gone out, that is the
# sources/-forgery ban (CLAUDE.md §0.1 ban #5) in a new coat.
UNSENT_TAIL = re.compile(r"SEND THIS NOW|not yet sent|unsent|still to send|hold expired|send now", re.I)

# "NOT SENT 2026-01-01: the site asked for an email first" is the opposite of history, and the bare
# word SENT beside a date would read it as already sent and take that person out of every check. The
# lookbehinds refuse "not " and "never " directly in front of the word; "not yet sent" is UNSENT_TAIL's.
ALREADY_SENT = re.compile(
    r"(?:(?<!not )(?<!never )\bSENT\b|\bsent by (?:me|you)\b|✅\s*SENT)[^\n]{0,60}?"
    r"(?:20\d\d-\d\d-\d\d|\b\d{1,2}/\d{1,2}/20\d\d\b)"
    r"|(?:20\d\d-\d\d-\d\d)[^\n]{0,40}?(?<!not )(?<!never )\bSENT\b",
    re.I)


@dataclass
class Finding:
    path: str
    person: str
    missing: list[str]

    def render(self) -> str:
        return (f"  {self.path}\n"
                f"      {self.person} is missing: {', '.join(self.missing)}\n"
                f"      Every person handed over carries all three (CLAUDE.md §13.6). A "
                f"half-finished handover is what makes you have to ask for the format again.")


def person_blocks(text: str) -> list[tuple[str, str]]:
    """(name, block) for each `###` person section inside `## The messages`."""
    m = re.search(r"^##\s+The messages\s*$(.*?)(?=^##\s+(?!#)|\Z)", text, re.M | re.S)
    if not m:
        return []
    body = m.group(1)
    hits = list(PERSON.finditer(body))
    out = []
    for i, h in enumerate(hits):
        name = h.group("name").strip().strip("*_`")
        if NOT_A_PERSON.match(name) or PLACEHOLDER_HEADING.match(name):
            continue
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        # Include the heading LINE itself. Real dossiers sometimes put the profile URL on the
        # heading ("### Jordan Rivera: nurse manager · https://linkedin.com/in/…"), and slicing from
        # h.end() would report those as missing a URL that's sitting right there.
        out.append((name, body[h.start():end]))
    return out


# THE ACTION-POINT LADDER (CLAUDE.md §13.6), as a gate.
# The doctrine: every message carries a genuine, direct ask, and, IF you keep a portfolio or
# public page (set in knowledge-base/01 as "Portfolio / personal site"), a link to it, so the
# recipient has something to look at. A link with no ask is a brochure. Many people (a nurse, an
# electrician, a store manager) have no portfolio at all, so with none configured the link is
# never required and only the ask is checked. An ask is a request the reader can act on ("Can you
# forward this to the hiring lead?"). A closing like "Thanks for reading either way" is not: the
# reader can read it and correctly do nothing.
# Any link: a full URL, or a bare domain in any top-level domain ("samlee.org/rn", "sam.nyc").
ANY_URL = re.compile(
    r"https?://[^\s)>\]]+"
    r"|(?<![\w.@])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}\b(?!@)(?:/[^\s)>\]]*)?",
    re.I,
)
ACTION_ASK = re.compile(
    r"(?:could|can|would|will)\s+you\b"                    # "Could you forward this"
    r"|\bany chance you\b|\bare you open to\b|\bwould you be open\b"
    r"|\bi'?d\s+like\s+to\s+be\s+(?:considered|referred|in the mix)\b"
    r"|\bplease\s+(?:consider|refer|point|pass|forward|take a look)"
    r"|\b(?:refer|consider|route|point|put)\s+me\b"
    r"|\bpoint me (?:at|to|toward)\b|\bput me in front of\b"
    r"|\bif you'?d\s+(?:nudge|flag|forward|pass|refer|point)\b"
    r"|\bworth (?:a look|two minutes)\b.{0,80}\?"
    r"|\bis\s+(?:the|there)\b[^.?]{0,90}\?"               # "is there a person who handles this?"
    # Second-person imperatives are asks too, and arguably stronger than a modal question because
    # they name the act directly: "show me the schedule", "tell me who hires for this".
    r"|\b(?:tell|show|send|give|point|pass|flag|forward)\s+me\b"
    r"|\b(?:pull up|take a look at|look at|spend\s+\w+\s+minutes? on|have a look at)\b"
    r"|\bsay\s+(?:whether|if|so)\b|\bgive me your read\b|\byour read\b"
    r"|\bi'?d\s+ask\s+of\s+you\b|\bhere\s+is\s+my\s+ask\b|\btwo\s+asks\b"
    r"|\b(?:open|read|give|drop|check)\s+(?:it|the (?:work|portfolio|site))\b"
    r"|\bdrop it in front of\b|\bin front of whoever\b"
    r"|\banswer (?:one|a|this) question\b|\bi'?d\s+like\s+you\s+to\s+answer\b"
    r"|\bafter looking at\b|\bwhat does it read as to you\b"
    r"|\bname the team\b|\bname a team\b",
    re.I,
)


def portfolio_url() -> str | None:
    """The user's own portfolio/personal-site URL, read from knowledge-base/01. None if the line
    is missing or still the template placeholder; the DM then needs no link at all, because a
    link nobody configured cannot be required."""
    try:
        t = (REPO / "knowledge-base" / "01-profile-and-identity.md").read_text()
    except OSError:
        return None
    m = re.search(r"\*\*Portfolio / personal site:\*\*\s*(\S+)", t)
    if not m:
        return None
    url = m.group(1).strip()
    if url.startswith("[") or not re.search(r"[a-z0-9-]+\.[a-z]{2,}", url, re.I):
        return None
    return url


def _bare(url: str) -> str:
    """`https://www.samlee.org/rn/` -> `samlee.org/rn`, so the copy can write it either way."""
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", url.strip(), flags=re.I).rstrip("/")


def action_gaps(block: str, portfolio: str | None = "") -> list[str]:
    """What a drafted message is missing from the action-point ladder.

    Scoped to the DM specifically: a connection note that carries an ask doesn't cover for a DM
    that carries none. `portfolio=""` (the default) means "look it up from the KB each call";
    pass an explicit value (including None) to control it directly, as the selftest does.
    """
    gaps = []
    m = DM.search(block)
    scope = block[m.start():] if m else block
    body = "\n".join(re.findall(r"^>.*$|^```[\s\S]*?^```", scope, re.M))
    body = body or scope
    site = portfolio_url() if portfolio == "" else portfolio
    # A link is required only when you HAVE one configured; then it must be that one.
    if site and not re.search(re.escape(_bare(site)), body, re.I):
        gaps.append(f"the action item (a link to {_bare(site)}, your portfolio in knowledge-base/01)")
    if not ACTION_ASK.search(body):
        gaps.append("an explicit ask directed at THEM (a request they can act on, not a "
                    "closing line like \"Thanks for reading either way\")")
    return gaps


# SPECIFICITY: a role reference carries its req ID.
# Not a style preference: an actionability defect. A referral generally can't be submitted
# without a specific requisition number, so a message that references "a role that's open" with no
# ID asks the recipient to go do the search you didn't do. And any ID you DO print must be real: an
# invented req number is a fabrication the recipient can check in their own internal tool in
# seconds: the fastest possible way to be caught lying.
#
# TITLE matches a generic Title-Case phrase (2-5 capitalized words) rather than an enumerated list
# of job titles, so this works for any field (engineering, sales, security, whatever the user's
# own roles are) without needing its own vocabulary maintained per industry.
TITLE = r"[A-Z][A-Za-z0-9&/]*(?:\s+(?:of|the|and|for|&)?\s*[A-Z][A-Za-z0-9&/]*){0,4}"
OPENING_REF = re.compile(
    r"\bthere'?s? (?:a|an|some)\b[^.]{0,60}\b(?:req|role|opening|posting|position)\b"
    + r"|\b(?:a|the|that|this)\s+" + TITLE + r"\b[^.]{0,50}\b(?:req|role|opening|posting|position|is open|open)\b"
    + r"|\b(?:req|reqs|opening|openings|posting|postings)\b[^.]{0,40}\b(?:open|fits|reads|says|listed)\b"
    + r"|\ba few (?:open )?(?:roles|openings|positions)\b"
    + r"|\bapplied\s+(?:to|for)\b[^.]{0,70}?" + TITLE
    + r"|\bthe\s+(?:req|role|opening|posting|seat|position)\b[^.]{0,20}?\b(?:is|was)\b[^.]{0,40}?" + TITLE
    + r"|\bgoing after\b[^.]{0,50}?" + TITLE
    + r"|\baiming at\b[^.]{0,50}?" + TITLE,
    re.I,
)

# A PREFIXED requisition (e.g. a hyphenated "R-100234" or "O-1000000002") is ONE token, but reasoning
# about digit SUBSTRINGS breaks it: the leading letter-hyphen opens a word boundary right before the
# digits, so a bare `\b(\d{6,10})\b` alternative matches only the inner digits and the whole real req
# reads as invented. The prefixed alternative goes FIRST so finditer consumes the whole token at the
# letter and never re-reads its digits. Bounds fit real reqs (a 1-letter prefix like "R-"/"O-"; a
# 2-letter ATS prefix like "WD-"/"JR-"): the {1,2} cap, anchored at a word START, makes a 3+ letter
# prefix (an ADR-style reference, or ordinary hyphenated prose) un-matchable, and \d{4,10} (a 4-digit
# minimum) keeps it off short hyphenated tokens that are not requisitions at all.
JOB_ID = re.compile(
    r"\b([A-Za-z]{1,2}-\d{4,10})\b"                                # e.g. a prefixed req like R-100234
    r"|\b(R\d{4,6})\b"                                             # e.g. an R-prefixed req like R12345
    r"|\b(\d{6,10})\b"                                              # e.g. Greenhouse, Lever, Workday
    r"|\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"   # Ashby uuid
    r"|\b([0-9A-F]{10})\b",                                        # e.g. a Workable code like 1A2B3C4D5E
    re.I,
)


def _ids_in(text: str) -> set:
    """Every req identifier of any ATS shape, flattened out of JOB_ID's alternation groups."""
    return {g for m in JOB_ID.finditer(text) for g in m.groups() if g}


# An optional, manually-recorded allowlist of req IDs verified live but that this repo's OWN
# tracker capture cannot see, for example a dossier built entirely outside pipeline/tracker.html's
# write scope (a separate crawl pass, a one-off manual verification). Empty by default: nothing is
# "pre-known good" out of the box. Add an entry here only for an ID you have personally verified
# against the employer's own posting, with a comment naming how and when it was checked, exactly
# the same discipline the tracker capture below applies automatically.
MANUALLY_VERIFIED_REQS: set[str] = set()


def repo_verified_reqs() -> set:
    """Every req ID this repo can vouch for: MANUALLY_VERIFIED_REQS, plus every ID this repo has
    ITSELF recorded, read from pipeline/tracker.html's apply/jd URLs.

    The tracker capture is never a plausible-shape regex: an ID counts only if this repo already
    recorded it as the apply or jd URL of a row it built a dossier for. An invented number is in
    neither set and always fails; a real one becomes known the moment the crawler or a dossier
    records it, or the moment it is added to MANUALLY_VERIFIED_REQS above.
    """
    try:
        t = (REPO / "pipeline" / "tracker.html").read_text()
    except OSError:
        return set(MANUALLY_VERIFIED_REQS)
    out = set(MANUALLY_VERIFIED_REQS)
    for m in re.finditer(r'(?:apply|jd|link):"([^"]+)"', t):
        out.update(_ids_in(m.group(1)))
    out.update(re.findall(r"\b(R\d{4,6})\b", t))
    return out


def specificity_gaps(block: str, known: set | None = None) -> list[str]:
    """A role reference must name its req, and every req named must be real.

    `known=None` (the default) means "look up `repo_verified_reqs()` live"; pass an explicit set
    to control it directly, as the selftest does.
    """
    gaps = []
    m = DM.search(block)
    scope = block[m.start():] if m else block
    body = "\n".join(re.findall(r"^>.*$|^```[\s\S]*?^```", scope, re.M)) or scope
    ids = _ids_in(body)
    if OPENING_REF.search(body) and not ids and not REQ_NONE.search(_outside_copy(block)):
        gaps.append("the req/job ID for the opening it points at (a referral generally can't be "
                    "submitted without one; the referrer needs a specific requisition). If the "
                    "posting has none, record `Req: none on posting` on its own line")
    known_ids = repo_verified_reqs() if known is None else known
    bogus = sorted(i for i in ids if i not in known_ids)
    if bogus:
        gaps.append(f"a job ID that is NOT in the verified board capture: {', '.join(bogus)} "
                    f"(an invented req number is a fabrication the recipient can check instantly)")
    return gaps


# PARAGRAPHING. A wall of text does not get read.
# A single unbroken block over ~500 characters renders in a DM pane as a grey slab, and the ask
# gets buried in the middle of it. The recipient doesn't need to dislike the message to skip it,
# they just need to not see where it goes.
#
# The check is deliberately structural, not stylistic: a real blank-line break between blocks, and
# no single block so long it becomes the wall again. What goes in each paragraph, and how it sounds,
# is owned by knowledge-base/17-writing.md, not by this script.
MIN_PARAS = 4
MAX_PARA_CHARS = 620
WALL_THRESHOLD = 500   # below this a message is not a wall and needs no enforced breaks


def paragraph_gaps(block: str) -> list[str]:
    """A DM must be broken into readable paragraphs."""
    gaps = []
    m = DM.search(block)
    scope = block[m.start():] if m else block
    fen = re.search(r"```\n([\s\S]*?)\n```", scope)
    body = fen.group(1) if fen else "\n".join(
        re.sub(r"^>\s?", "", l) for l in re.findall(r"^>.*$", scope, re.M))
    if not body.strip():
        return gaps
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(body) < WALL_THRESHOLD:
        return gaps
    if len(paras) < MIN_PARAS:
        gaps.append(f"paragraph breaks (the DM is {len(paras)} block(s); a message this long reads "
                    f"as a wall and the ask disappears inside it)")
    longest = max((len(p) for p in paras), default=0)
    if longest > MAX_PARA_CHARS:
        gaps.append(f"a break inside its longest paragraph ({longest} chars, over {MAX_PARA_CHARS})")
    return gaps


def _outside_copy(block: str) -> str:
    """The block without its quoted or fenced message text: a marker only counts as a record line,
    so "my profile: example.com" inside a message is not a profile on file."""
    return re.sub(r"^>.*$", "", re.sub(r"^```[\s\S]*?^```", "", block, flags=re.M), flags=re.M)


def profile_state(block: str) -> str:
    """'linkedin', 'other' (another URL on a Profile: line), 'none' (`Profile: none found`) or ''."""
    if PROFILE.search(block):
        return "linkedin"
    for m in PROFILE_LINE.finditer(_outside_copy(block)):
        value = UNFILLED_SLOT.sub("", m.group("value")).strip(" *_")
        if PROFILE_NONE.match(value):
            return "none"
        if re.search(r"https?://\S", value) or ANY_URL.match(value):
            return "other"
    return ""


def _is_history(block: str) -> bool:
    """Research-stage on purpose, or already sent to a real person on a real date."""
    return bool(NOT_DRAFTED.search(block)
                or (ALREADY_SENT.search(block) and not UNSENT_TAIL.search(block)))


def linkedin_gaps(text: str) -> list[str]:
    """Everyone with drafted copy and no LinkedIn on record. Allowed, and said out loud."""
    return [name for name, block in person_blocks(text)
            if not _is_history(block) and profile_state(block) in ("other", "none")
            and (NOTE.search(block) or DM.search(block))]


def scan_text(rel: str, text: str, known_ids: set | None = None, portfolio: str | None = "") -> list[Finding]:
    out: list[Finding] = []
    for name, block in person_blocks(text):
        if _is_history(block):
            continue  # research-stage (a roster is not outreach material), or it already went out
        # A connection note is a connection REQUEST: you can't send one to someone you're already
        # connected to, so a block that records 1st-degree is complete without it.
        already_connected = re.search(r"\b1st°|\b1st\s*degree|already connected", block, re.I)
        profile = profile_state(block)
        no_linkedin = profile in ("other", "none")  # no connection request or InMail can reach them
        has = {
            PROFILE_PART: bool(profile),
            "the connection note": bool(NOTE.search(block)) or bool(already_connected) or no_linkedin,
            "the direct message": bool(DM.search(block)),
        }
        if not (profile in ("linkedin", "other") or NOTE.search(block) or DM.search(block) or already_connected):
            continue  # nothing drafted for this person at all (research stage)
        missing = [k for k, v in has.items() if not v]
        if has["the direct message"] and not no_linkedin and not INMAIL.search(block):
            missing.append("the `Use InMail: YES/NO` verdict on the DM")
        if has["the direct message"]:
            missing.extend(action_gaps(block, portfolio=portfolio))
            missing.extend(specificity_gaps(block, known=known_ids))
            missing.extend(paragraph_gaps(block))
        if missing:
            out.append(Finding(rel, name, missing))
    return out


def targets(root: Path = REPO) -> list[Path]:
    """Every real handover file. A TEMPLATE-* folder ships as blank slots and is nobody's dossier."""
    return [p for p in sorted(root.glob("applications/*/referrals.md"))
            if not p.parent.name.startswith("TEMPLATE-")] + \
           sorted(root.glob("pipeline/outreach-*.md"))


# selftest fixtures: every name, handle, and company below is invented.
_KNOWN = {"1000000001", "a1b2c3d4-0000-4000-8000-000000000001", "1A2B3C4D5E", "R12345", "R-100234"}


def _req(line: str) -> str:
    """A complete, well-formed handover whose second paragraph is the line under test."""
    return ("## The messages\n### 1 · Sam Lee: the site supervisor\n"
            "**Profile: https://www.linkedin.com/in/samlee-example**\n"
            "**#1 Connection note (20 chars):**\n> Hello from Globex.\n"
            "**#2 Direct message · Use InMail: NO**\n> Hello,\n\n"
            f"> {line}\n\n"
            "> My references are at example.com. Can you pass them to the hiring lead?\n\n> Alex\n")


_SMALL = """## The messages
### 1 · Jordan Rivera: office manager at Acme Dental
{profile}
{req}
**Direct message · no LinkedIn, send through the practice's contact page**
> Hello Jordan, the Dental Assistant opening on your site is the one I mean.
> My certificate is at example.com. Can you pass it to the dentist who hires?
"""
_TEAM = "**Profile: https://acme-dental.example/team**"
_NO_REQ = "Req: none on posting"
_UNTOUCHED = """## The messages
### 1 · [Name], [Role] at [Company]

Profile: [linkedin.com/in/... URL] · why them: [one line]

**Connection note** ([char count], under 300):
```
[under ~300 chars, one paragraph]
```

**Direct message · Use InMail: [YES/NO]** ([one-line reason])
```
Hi [Name],
```

### 2 · [Name], NOT DRAFTED (research-stage)

[reason]
"""

CASES: list[tuple[str, str, bool]] = [
    ("a staff-page profile plus a recorded no-req marker is a complete handover (no LinkedIn needed)",
     _SMALL.format(profile=_TEAM, req=_NO_REQ), False),
    ("the marker in bold on its own line counts", _SMALL.format(profile=_TEAM, req="**Req: none on posting**"), False),
    ("`Profile: none found` is a complete profile line",
     _SMALL.format(profile="Profile: none found (searched the practice site)", req=_NO_REQ), False),
    ("a markdown link on the Profile line counts",
     _SMALL.format(profile="Profile: [team page](https://acme-dental.example/team)", req=_NO_REQ), False),
    ("a bare domain on the Profile line counts",
     _SMALL.format(profile="Profile: acme-dental.example/team", req=_NO_REQ), False),
    ("an opening with no ID and no marker is still caught", _SMALL.format(profile=_TEAM, req=""), True),
    ("the words 'none on posting' inside the message do not count as the marker",
     _SMALL.format(profile=_TEAM, req="").replace("> Hello Jordan,", "> Req: none on posting\n> Hello Jordan,"), True),
    ("the no-req marker never excuses an invented ID",
     _SMALL.format(profile=_TEAM, req=_NO_REQ).replace("opening on your site", "opening, job 77777777,"), True),
    ("no Profile line at all is still caught", _SMALL.format(profile="", req=_NO_REQ), True),
    ("a Profile line still holding the template slot is still caught",
     _SMALL.format(profile="Profile: [linkedin.com/in/... URL] · why them: [one line]", req=_NO_REQ), True),
    ("a URL after 'profile:' inside the message is not a profile on file",
     _SMALL.format(profile="", req=_NO_REQ).replace("> Hello Jordan,", "> My profile: https://acme.example/me\n> Hello Jordan,"), True),
    ("`Profile: none found` with nothing drafted is research-stage", """## The messages
### 1 · Sam Lee: warehouse lead
Profile: none found (the depot has no staff page)
""", False),
    ("a staff page with no message drafted is still half a handover", """## The messages
### 1 · Sam Lee: warehouse lead
Profile: https://northwind.example/staff
""", True),
    ("a LinkedIn person still needs the InMail verdict", """## The messages
### 1 · Sam Lee: warehouse lead
Profile: https://www.linkedin.com/in/samlee-example
**Connection note (20 chars):**
> Hello Sam.
**Direct message**
> Hello Sam. My forklift card is at example.com. Can you pass it to the shift manager?
""", True),
    ("the untouched template is nobody: no finding", _UNTOUCHED, False),
    ("a real name with leftover slots in the heading stays a person", """## The messages
### 1 · Jordan Rivera, [Role] at [Company]
**Connection note (20 chars):**
> Hello Jordan.
""", True),
    ("a 10-digit Greenhouse-style id is a real id", _req("The Payroll Clerk opening lists job ID 1000000001."), False),
    ("an Ashby-style uuid is a real id",
     _req("The Line Cook posting carries Ashby id a1b2c3d4-0000-4000-8000-000000000001."), False),
    ("a Workable-style code is a real id", _req("The Forklift Operator opening is Workable code 1A2B3C4D5E."), False),
    ("an R-prefixed requisition is a real id", _req("The Store Manager role is listed as R12345."), False),
    # A HYPHENATED requisition is ONE token, not a digit substring: "R-100234" must pass whole,
    # never be misread as the bare digits "100234" and flagged invented.
    ("a hyphenated requisition is a real, verified req (whole token, not the substring after the hyphen)",
     _req("The Dental Hygienist role is req R-100234."), False),
    ("an INVENTED hyphenated req must still be caught (whole-token, still gated)",
     _req("The Bus Driver role is req R-777777."), True),
    ("an INVENTED numeric req must still be caught", _req("The Substitute Teacher role is job 77777777."), True),
    ("an INVENTED uuid must still be caught",
     _req("The Electrician posting carries Ashby id cafef00d-0000-0000-0000-000000000000."), True),
    ("an opening named with NO id at all must still be caught",
     _req("The Phlebotomist opening is at the downtown lab."), True),
    ("an ORDINAL-PREFIXED note + DM is seen", """## The messages
### 1 · Sam Lee: the shift lead
**Profile: https://www.linkedin.com/in/samlee-example**
**#1 Connection note (40 chars):**
> Hello from the Acme depot.
**#2 Direct message · Use InMail: NO**
> Hello,

> My shift log is at example.com. Can you send it to whoever reviews req 1000000001?
""", False),
    ("an ordinal-prefixed DM with NO connection note must still FAIL", """## The messages
### 1 · Sam Lee: the shift lead
**Profile: https://www.linkedin.com/in/samlee-example**
**#2 Direct message · Use InMail: NO**
> Hello, my shift log is at example.com. Can you send it to whoever reviews req 1000000001?
""", True),
    ("already-SENT copy with a DATE is history, not a handover", """## The messages
### 1 · Alex Kim: the buyer
**Profile: https://www.linkedin.com/in/alexkim-example**
> **SENT LOG (2026-01-01):** sent the connection note.
**#1 Connection note (40 chars):**
> Hello from Northwind.
**#2 Direct message · Use InMail: NO**
> Hello, this has no request in it at all.
""", False),
    ("a SENT marker must NOT hide a newer UNSENT draft in the same block", """## The messages
### 1 · Alex Kim: the buyer
**Profile: https://www.linkedin.com/in/alexkim-example**
> **SENT LOG (2026-01-01):** sent the connection note.
**#1 Connection note (40 chars):**
> Hello from Northwind.
**#3 Email · SEND THIS NOW. Use InMail: NO**
> Hello, the invoices went out on Friday.
""", True),
    ("'NOT SENT <date>' is the opposite of history and must not suppress", """## The messages
### 1 · Alex Kim: the buyer
**Profile: https://www.linkedin.com/in/alexkim-example**
NOT SENT 2026-01-01: the site asked for an email address first.
**#1 Connection note (40 chars):**
> Hello from Northwind.
""", True),
    ("'never sent' with a date after it must not suppress either", """## The messages
### 1 · Alex Kim: the buyer
**Profile: https://www.linkedin.com/in/alexkim-example**
Never sent, checked 2026-01-01.
**#1 Connection note (40 chars):**
> Hello from Northwind.
""", True),
    ("an UNDATED 'SENT' must not suppress: the marker records history or nothing", """## The messages
### 1 · Alex Kim: the buyer
**Profile: https://www.linkedin.com/in/alexkim-example**
> **SENT LOG:** went out some time ago.
**#1 Connection note (40 chars):**
> Hello from Northwind.
**#2 Direct message · Use InMail: NO**
> Hello, the invoices went out on Friday.
""", True),
    ("a DM with an ask but no link, when a portfolio is configured", """## The messages
### 1 · Jordan Rivera: the office manager
**Profile: https://www.linkedin.com/in/jordanrivera-example**
**Connection note (40 chars):**
> Hello, we met at the Acme job fair.
**Direct message · Use InMail: NO**
> Hello, I keep the books for three dental offices. Can you pass this to whoever hires for finance?
""", True),
    ("a DM with a link but NO ASK: the reader has nothing to do", """## The messages
### 1 · Jordan Rivera: the depot manager
**Profile: https://www.linkedin.com/in/jordanrivera-example**
**Connection note (40 chars):**
> Hello, I saw the Northwind fleet news.
**Direct message · Use InMail: NO**
> Hello, I drive a 26-foot box truck out of the Northwind depot. My safety record is at example.com. Thanks for reading either way.
""", True),
    ("all three parts present, well-formed", """## The messages
### 1 · Jordan Rivera: the practice manager
**Profile: https://www.linkedin.com/in/jordanrivera-example**
**Connection note (60 chars):**
> Hello Jordan, we met at the Acme job fair.
**Direct message · Use InMail: NO for now** (ledger balance unknown)
> Hello Jordan, the clinic's evening roster needs a second medical assistant, and I hold that certificate.
> A copy is at example.com. Can you forward it to the practice owner?
""", False),
    ("a profile and a note but NO message: the half-handover", """## The messages
### 1 · Alex Kim: produce manager
**Profile: https://www.linkedin.com/in/alexkim-example**
**Connection note (60 chars):**
> Hello Alex, the new Hooli store layout looks good.
""", True),
    ("both messages but NO profile URL: the recipient can't be found", """## The messages
### 1 · Alex Kim: produce manager
**Connection note (40 chars):**
> Hello Alex.
**Direct message · Use InMail: NO**
> Hello Alex, my application is in.
""", True),
    ("a DM with no InMail verdict: the channel decision is missing", """## The messages
### 1 · Alex Kim: produce manager
**Profile: https://www.linkedin.com/in/alexkim-example**
**Connection note (40 chars):**
> Hello Alex.
**Direct message**
> Hello Alex, my application is in.
""", True),
    ("a research-stage roster with nothing drafted is NOT a failure", """## The messages
### 1 · Sam Lee: name from a staff page
Contact details still to find.
""", False),
    ("an explicit NOT DRAFTED marker is respected", """## The messages
### 1 · Sam Lee: warehouse lead
**Profile: https://www.linkedin.com/in/samlee-example**
NOT DRAFTED: waiting on the shift schedule.
""", False),
    ("section furniture is not read as a person", """## The messages
### Drafted 2026-01-01
**Talking points**: none yet.
""", False),
    ("a 1st-degree contact needs no connection REQUEST: must not be flagged", """## The messages
### 3 · Alex Kim: "Support Lead at Acme" (1st°)
- Profile: https://www.linkedin.com/in/alexkim-example/
- **Use InMail: NO** (1st-degree).
**DM (90 chars):**
> Hello Alex, the Help Desk Technician opening is job 1000000001.
> My certificates are at example.com. Can you send them to the team lead?
""", False),
    ("a portfolio is configured but the DM carries no link to it: flagged", """## The messages
### 1 · Jordan Rivera: the head teacher
**Profile: https://www.linkedin.com/in/jordanrivera-example**
**Connection note (40 chars):**
> Hello Jordan, we spoke at the district open day.
**Direct message · Use InMail: NO**
> Hello Jordan, my application is in. Can you forward it to the department chair?
""", True),
    ("a profile URL on the HEADING line counts", """## The messages
### Sam Lee: foreman at Globex · https://www.linkedin.com/in/samlee-example
**Connection note (60 chars):**
> Hello Sam, we spoke at the union hall.
**Direct message · Use InMail: NO**
> Hello Sam, my application is in.
> Site photos are at example.com. Can you show them to the project manager?
""", False),
]


# The link rule both ways: required only when a portfolio is configured, any top-level domain.
_NO_LINK_DM = """## The messages
### 1 · Alex Kim: the clinic manager
**Profile: https://www.linkedin.com/in/alexkim-example**
**Connection note (40 chars):**
> Hello Alex, my application is in.
**Direct message · Use InMail: NO**
> Hello Alex, the Charge Nurse role is job 1000000001, and I hold a current state license. Can you forward my name to the nurse manager?
"""
_ORG_LINK_DM = _NO_LINK_DM.replace("state license.", "state license. A copy is at samlee.org/rn.")
LINK_CASES: list[tuple[str, str, str | None, bool]] = [
    ("no portfolio configured: a DM with an ask and no link is NOT flagged", _NO_LINK_DM, None, False),
    ("a .org portfolio configured: a DM linking samlee.org/rn passes", _ORG_LINK_DM, "samlee.org/rn", False),
    ("a portfolio configured with https://www.: the bare form in the DM still counts", _ORG_LINK_DM,
     "https://www.samlee.org/rn/", False),
    ("a .org portfolio configured: a DM with no link IS flagged", _NO_LINK_DM, "samlee.org/rn", True),
]


def selftest() -> int:
    passed = failed = 0
    print("outreach_format.py selftest: a fixed fictional configuration, independent of any real repo state\n")
    for label, text, should in CASES:
        got = bool(scan_text("t/referrals.md", text, known_ids=_KNOWN, portfolio="example.com"))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    for label, text, site, should in LINK_CASES:
        got = bool(scan_text("t/referrals.md", text, known_ids=_KNOWN, portfolio=site))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    for text, want in (("see samlee.org/rn", True), ("at sam.nyc", True), ("portfolio.cs.stateu.edu", True),
                       ("mail sam.lee@acme.example", False), ("no link here at all", False)):
        ok = bool(ANY_URL.search(text)) == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓ url     ' if ok else '✗ URL     '}  ANY_URL on {text!r} -> {want}")
    gaps = linkedin_gaps(_SMALL.format(profile=_TEAM, req=_NO_REQ))
    ok = gaps == ["Jordan Rivera: office manager at Acme Dental"]
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓ gap     ' if ok else '✗ GAP     '}  a person with no LinkedIn is named as a LinkedIn gap")
    ok = linkedin_gaps(_req("The Payroll Clerk opening lists job ID 1000000001.")) == []
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓ gap     ' if ok else '✗ GAP     '}  a person with a LinkedIn URL is not a gap")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for folder in ("TEMPLATE-company-role", "acme-clerk"):
            (root / "applications" / folder).mkdir(parents=True)
            (root / "applications" / folder / "referrals.md").write_text(_UNTOUCHED, encoding="utf-8")
        ok = [p.parent.name for p in targets(root)] == ["acme-clerk"]
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓ template' if ok else '✗ TEMPLATE'}  the sweep skips a TEMPLATE-* folder and keeps a copied dossier")
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as td:
        small = Path(td) / "referrals.md"
        small.write_text(_SMALL.format(profile=_TEAM, req=_NO_REQ), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(small)])
    said = out.getvalue()
    ok = "LINKEDIN GAP" in said and "CLEAN:" in said and "all three parts" not in said
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓ clean   ' if ok else '✗ CLEAN   '}  a clean run naming a LinkedIn gap never claims all three parts")
    print()
    # portfolio_url() itself must run cleanly against the real repo (configured or not).
    p = portfolio_url()
    print(f"  ✓ CONFIG    portfolio_url() runs cleanly on the real repo (currently: {p or 'not configured'})")

    # A PREFIXED requisition is read as ONE TOKEN, never split into its digit substring. Pins the
    # tokenization directly (not just the pass/fail classification above), so the regression can
    # never come back even if the classification set changes.
    for text, want in (("point at req R-100234", {"R-100234"}),
                       ("a hyphenated req O-1000000002", {"O-1000000002"}),
                       ("an R-prefixed req R12345", {"R12345"}),
                       ("Greenhouse job 1000000001", {"1000000001"})):
        got_ids = _ids_in(text)
        ok = got_ids == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓ token   ' if ok else '✗ TOKEN   '}  _ids_in({text!r}) == {sorted(want)} (got {sorted(got_ids)})")
    if failed:
        print(f"\nSELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"\nSELFTEST OK: {passed}/{passed + failed} "
          f"({sum(1 for c in CASES if c[2])} half-handovers caught, "
          f"{sum(1 for c in CASES if not c[2])} legitimate shapes not flagged)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    raw = [Path(a) if Path(a).is_absolute() else REPO / a for a in args] if args else targets()

    # Every other gate in this repo is invoked with a DOSSIER DIRECTORY, and a directory hitting
    # is_file() -> False must never silently mean "checked 0, found 0, print CLEAN".
    paths: list[Path] = []
    for p in raw:
        if p.is_dir():
            hits = sorted(p.glob("referrals.md")) + sorted(p.glob("outreach-*.md"))
            if not hits:
                print(f"outreach_format.py: {p} has no referrals.md to check", file=sys.stderr)
            paths.extend(hits)
        else:
            paths.append(p)

    missing = [str(p) for p in paths if not p.is_file()]

    findings: list[Finding] = []
    no_linkedin: list[str] = []
    checked = 0
    for p in paths:
        if not p.is_file():
            continue
        checked += 1
        try:
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        text = p.read_text(encoding="utf-8", errors="replace")
        findings.extend(scan_text(rel, text))
        no_linkedin.extend(f"{rel}: {name}" for name in linkedin_gaps(text))

    print(f"outreach_format.py: checked {checked} file(s) for the three-part handover (CLAUDE.md §13.6)")
    print("  every person: a profile (LinkedIn, another URL, or `Profile: none found`) · the connection note "
          "· the DM + its InMail verdict")
    print("  NOT checked: whether the copy is good (knowledge-base/17-writing.md owns voice;"
          " verify_claims.py owns length and evidence),")
    print("               and what an agent types into chat; this gates the FILE the chat is read off.")
    if checked == 0:
        print("\n🔴 CHECKED NOTHING: this is a FAILURE, not a pass.", file=sys.stderr)
        if missing:
            print(f"   paths that do not exist: {', '.join(missing)}", file=sys.stderr)
        print("   Pass a dossier directory, a referrals.md, or no argument at all to sweep the repo.",
              file=sys.stderr)
        return 2
    if no_linkedin:
        print(f"\nLINKEDIN GAP, {len(no_linkedin)} person(s). Say this in the handover: no LinkedIn on record, so no "
              "connection note or InMail; the message goes by another route (email, the employer's contact page).")
        for line in no_linkedin:
            print(f"  {line}")
    if not findings:
        print(f"\nCLEAN: every drafted person in {checked} file(s) carries every part that applies to them.")
        return 0
    print(f"\n{len(findings)} HALF-FINISHED HANDOVER(S):\n")
    for f in findings:
        print(f.render())
        print()
    print("Fill the missing parts, or mark the person NOT DRAFTED if they are research-stage.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
