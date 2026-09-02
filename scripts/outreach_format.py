#!/usr/bin/env python3
"""outreach_format.py: every person you are handed comes with all three parts. No exceptions.

WHY THIS EXISTS
---------------
A half-finished handover (a name with a note but no message, or a message with no way to send it)
is what makes you have to ask an agent for the same format again and again. Prose instructions
don't execute reliably on their own; a check does.

THE THREE PARTS, and why each one is load-bearing
--------------------------------------------------
1. **The LinkedIn profile URL.** Without it you have to go find the person before you can act. The
   handover stops being actionable and becomes homework.
2. **The connection note** (under 300 chars). The free, always-available channel. Connection state
   is unknowable in advance, so this always ships.
3. **The direct message**, with an explicit `Use InMail: YES/NO` verdict. If you're already
   connected, it goes as a normal message; if not, it follows the accept. InMail credits are scarce
   and accounted (`pipeline/inmail-ledger.md`), so the verdict travels with the copy.

THE REFERENCE SHAPE
--------------------
Per person, on disk, inside `## The messages`:

    ### N · Full Name: why them, in a few words
    **Profile: https://www.linkedin.com/in/handle**
    **Connection note (NNN chars):**
    > ...
    **Direct message · Use InMail: NO** (reason)
    > ...

and in chat, grouped by company, read verbatim off that file:

    ## COMPANY: Role
    **Name**, why · https://www.linkedin.com/in/handle · *ask = be considered*
    - **Note:** ...
    - **DM:**   ...

WHAT THIS DOES NOT CHECK, said out loud
----------------------------------------
It cannot read what an agent types into chat. It gates the FILE the chat is supposed to be read off.
If an agent invents copy in chat that is not on disk, that is a grounding failure and
`verify_claims.py`'s problem, not this one. It also does not judge whether the copy is any good;
`verify_claims.py` owns length, voice and evidence.

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

REPO = Path(__file__).resolve().parents[1]

PROFILE = re.compile(r"linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)
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

# ── ALREADY SENT is not "about to be handed over". ────────────────────────────
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

ALREADY_SENT = re.compile(
    r"(?:\bSENT\b|\bsent by (?:me|you)\b|✅\s*SENT)[^\n]{0,60}?"
    r"(?:20\d\d-\d\d-\d\d|\b\d{1,2}/\d{1,2}/20\d\d\b)"
    r"|(?:20\d\d-\d\d-\d\d)[^\n]{0,40}?\bSENT\b",
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
        if NOT_A_PERSON.match(name):
            continue
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        # Include the heading LINE itself. Real dossiers sometimes put the profile URL on the
        # heading ("### Jordan Rivera: designer · https://linkedin.com/in/…"), and slicing from
        # h.end() would report those as missing a URL that's sitting right there.
        out.append((name, body[h.start():end]))
    return out


# ── THE ACTION-POINT LADDER (CLAUDE.md §13.6), as a gate. ────────────────────────────
# The doctrine: every message hands the recipient an action item (by default your own portfolio
# or public work, something they can look at), paired with a genuine, direct ask. A link with no
# ask is a brochure; an ask with no link is homework. Calibrated against real messages: the ones
# that convert end in a direct second-person request ("Could you consider me for one of these, or
# route me to whoever owns them?"); the ones that don't read as a shrug ("I'd rather know than
# guess" is grammatically a preference, not a request, so the recipient can correctly do nothing).
ANY_URL = re.compile(
    r"https?://[^\s)>\]]+"
    r"|(?<![\w.@])[a-z0-9-]+\.(?:com|io|dev|design|in|me|xyz|so|app|co)(?:/[^\s)>\]]*)?",
    re.I,
)
ACTION_ASK = re.compile(
    r"(?:could|can|would|will)\s+you\b"                    # "Could you consider me"
    r"|\bany chance you\b|\bare you open to\b|\bwould you be open\b"
    r"|\bi'?d\s+like\s+to\s+be\s+(?:considered|referred|in the mix)\b"
    r"|\bplease\s+(?:consider|refer|point|pass|forward|take a look)"
    r"|\b(?:refer|consider|route|point|put)\s+me\b"
    r"|\bpoint me (?:at|to|toward)\b|\bput me in front of\b"
    r"|\bif you'?d\s+(?:nudge|flag|forward|pass|refer|point)\b"
    r"|\bworth (?:a look|two minutes)\b.{0,80}\?"
    r"|\bis\s+(?:the|there)\b[^.?]{0,90}\?"               # "is the X track the right door?"
    # Second-person imperatives are asks too, and arguably stronger than a modal question because
    # they name the act directly: "Pull up my site and say whether…", "send me one name".
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
    """The user's own portfolio/personal-site URL, read from knowledge-base/01. None if it's
    still an unfilled template placeholder; the action-link check then falls back to accepting
    any URL, rather than falsely requiring a specific link nobody has configured."""
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
    link_ok = (site and re.search(re.escape(site), body, re.I)) or (not site and ANY_URL.search(body))
    if not link_ok:
        gaps.append(f"the action item ({'a link to ' + site if site else 'a link the recipient can act on'})")
    if not ACTION_ASK.search(body):
        gaps.append("an explicit ask directed at THEM (a request they can act on, not a "
                    "statement of preference like \"I'd rather know than guess\")")
    return gaps


# ── SPECIFICITY: a role reference carries its req ID. ─────────────────────────────────
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

JOB_ID = re.compile(
    r"\b(\d{6,10})\b"                                              # e.g. Amazon, Greenhouse, Lever
    r"|\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"   # Ashby uuid
    r"|\b(R\d{4,6})\b"                                             # e.g. Datadog-style R20051
    r"|\b([0-9A-F]{10})\b",                                        # e.g. Workable 7D5CF84724
    re.I,
)


def _ids_in(text: str) -> set:
    """Every req identifier of any ATS shape, flattened out of JOB_ID's alternation groups."""
    return {g for m in JOB_ID.finditer(text) for g in m.groups() if g}


def repo_verified_reqs() -> set:
    """Every req ID this repo has ITSELF recorded, read from pipeline/tracker.html's apply/jd URLs.

    This is a CAPTURE, never a plausible-shape regex: an ID counts only if this repo already
    recorded it as the apply or jd URL of a row it built a dossier for. There is no pre-seeded
    "known good" list: an invented number is never in this set and always fails, and a real one
    becomes known the moment the crawler or a dossier records it.
    """
    try:
        t = (REPO / "pipeline" / "tracker.html").read_text()
    except OSError:
        return set()
    out = set()
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
    if OPENING_REF.search(body) and not ids:
        gaps.append("the req/job ID for the opening it points at (a referral generally can't be "
                    "submitted without one; the referrer needs a specific requisition)")
    known_ids = repo_verified_reqs() if known is None else known
    bogus = sorted(i for i in ids if i not in known_ids)
    if bogus:
        gaps.append(f"a job ID that is NOT in the verified board capture: {', '.join(bogus)} "
                    f"(an invented req number is a fabrication the recipient can check instantly)")
    return gaps


# ── PARAGRAPHING. A wall of text does not get read. ────────────────────────────────────
# A single unbroken block over ~500 characters renders in a DM pane as a grey slab, and the ask
# gets buried in the middle of it. The recipient doesn't need to dislike the message to skip it,
# they just need to not see where it goes.
#
# THE REFERENCE SHAPE, a well-paragraphed real message, roughly: greeting on its own line, a
# one-line opener saying why you're writing, who you are and what you do, the specific req in its
# own paragraph, the ask in its own paragraph, a graceful out, sign-off on its own line.
#
# The check is deliberately structural, not stylistic: a real blank-line break between blocks, and
# no single block so long it becomes the wall again.
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


def scan_text(rel: str, text: str, known_ids: set | None = None, portfolio: str | None = "") -> list[Finding]:
    out: list[Finding] = []
    for name, block in person_blocks(text):
        if NOT_DRAFTED.search(block):
            continue  # explicitly research-stage; a roster is not outreach material
        if ALREADY_SENT.search(block) and not UNSENT_TAIL.search(block):
            continue  # it went to a real person on a real date; history, not a handover
        # A connection note is a connection REQUEST: you can't send one to someone you're already
        # connected to, so a block that records 1st-degree is complete without it.
        already_connected = re.search(r"\b1st°|\b1st\s*degree|already connected", block, re.I)
        has = {
            "the LinkedIn profile URL": bool(PROFILE.search(block)),
            "the connection note": bool(NOTE.search(block)) or bool(already_connected),
            "the direct message": bool(DM.search(block)),
        }
        if not any(has.values()):
            continue  # nothing drafted for this person at all (research stage)
        missing = [k for k, v in has.items() if not v]
        if has["the direct message"] and not INMAIL.search(block):
            missing.append("the `Use InMail: YES/NO` verdict on the DM")
        if has["the direct message"]:
            missing.extend(action_gaps(block, portfolio=portfolio))
            missing.extend(specificity_gaps(block, known=known_ids))
            missing.extend(paragraph_gaps(block))
        if missing:
            out.append(Finding(rel, name, missing))
    return out


def targets() -> list[Path]:
    return sorted(REPO.glob("applications/*/referrals.md")) + \
           sorted(REPO.glob("pipeline/outreach-*.md"))


# ── selftest fixtures: every name, handle, and company below is invented. ──────────────
_KNOWN = {"5735407004", "2412e9c2-fdd4-43d6-bd13-7345e82c9ec7", "7D5CF84724", "R20051"}

CASES: list[tuple[str, str, bool]] = [
    ('a GREENHOUSE 10-digit req id is a real id',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, job ID 5735407004.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', False),
    ('an ASHBY uuid req is a real id',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, Ashby req 2412e9c2-fdd4-43d6-bd13-7345e82c9ec7.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', False),
    ('a WORKABLE code is a real id',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, Workable posting 7D5CF84724.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', False),
    ('an R-prefixed requisition is a real id',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, req R20051.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', False),
    ('an INVENTED numeric req must still be caught',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, job ID 99999999.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', True),
    ('an INVENTED ashby uuid must still be caught',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, Ashby req deadbeef-0000-0000-0000-000000000000.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', True),
    ('an opening named with NO id at all must still be caught',
     '## The messages\n### 1 · Req Person: a designer\n**Profile: https://www.linkedin.com/in/reqperson**\n**#1 Connection note (20 chars):**\n> Hi there.\n**#2 Direct message · Use InMail: NO**\n> Hi,\n\n> The Staff Engineer role is open, remote in the US.\n\n> Open example.com and tell me whether it fits?\n\n> Jordan\n', True),
    ("an ORDINAL-PREFIXED note + DM is seen", """## The messages
### 1 · Ordinal Person: a designer
**Profile: https://www.linkedin.com/in/ordinalperson**
**#1 Connection note (40 chars):**
> Hi, quick hello.
**#2 Direct message · Use InMail: NO**
> Hi,

> Would you look at example.com and tell me whether req 5735407004 is the right door?
""", False),
    ("an ordinal-prefixed DM with NO connection note must still FAIL", """## The messages
### 1 · Half Person: a designer
**Profile: https://www.linkedin.com/in/halfperson**
**#2 Direct message · Use InMail: NO**
> Hi, would you look at example.com and tell me if req 5735407004 is the right door?
""", True),
    ("already-SENT copy with a DATE is history, not a handover", """## The messages
### 1 · Gone Person: a designer
**Profile: https://www.linkedin.com/in/goneperson**
> **SENT LOG (2026-01-01):** sent the connection note.
**#1 Connection note (40 chars):**
> Hi, hello.
**#2 Direct message · Use InMail: NO**
> Hi, no ask here and one giant block.
""", False),
    ("a SENT marker must NOT hide a newer UNSENT draft in the same block", """## The messages
### 1 · Mixed Person: a designer
**Profile: https://www.linkedin.com/in/mixedperson**
> **SENT LOG (2026-01-01):** sent the connection note.
**#1 Connection note (40 chars):**
> Hi, hello.
**#3 Email · SEND THIS NOW. Use InMail: NO**
> Hi, still no ask in here.
""", True),
    ("an UNDATED 'SENT' must not suppress: the marker records history or nothing", """## The messages
### 1 · Vague Person: a designer
**Profile: https://www.linkedin.com/in/vagueperson**
> **SENT LOG:** sent at some point.
**#1 Connection note (40 chars):**
> Hi, hello.
**#2 Direct message · Use InMail: NO**
> Hi, no ask here at all.
""", True),
    ("a DM with no ACTION ITEM: no link to act on", """## The messages
### 1 · Test Person: a manager
**Profile: https://www.linkedin.com/in/testperson**
**Connection note (40 chars):**
> Hi, your work on X was interesting. Could you take a look at my work?
**Direct message · Use InMail: NO**
> Hi, I design products and ship the front end. Could you point me at the right door?
""", True),
    ("a DM with a link but NO ASK: a real rejected shape", """## The messages
### 1 · Test Person: a manager
**Profile: https://www.linkedin.com/in/testperson**
**Connection note (40 chars):**
> Hi, your work on X was interesting. Would you take a look? example.com
**Direct message · Use InMail: NO**
> Hi, I design products and ship the front end. My work is at example.com. If this is not the right door, I would rather know than guess.
""", True),
    ("all three parts present, well-formed", """## The messages
### 1 · Sam Okafor: the hiring manager, DMs invited
**Profile: https://www.linkedin.com/in/samokafor**
**Connection note (60 chars):**
> Hi Sam, saw your post and applied through your link.
**Direct message · Use InMail: NO for now** (ledger balance unknown)
> Hi Sam, your Staff Engineer post looks for people who sit at the intersection of design and code.
> Work is at example.com. Could you consider me for it?
""", False),
    ("a profile and a note but NO message: the half-handover", """## The messages
### 1 · Robin Ashworth: growth lead
**Profile: https://www.linkedin.com/in/robinashworth**
**Connection note (60 chars):**
> Hi Robin, your post about the redesign made me smile.
""", True),
    ("both messages but NO profile URL: the recipient can't be found", """## The messages
### 1 · Robin Ashworth: growth lead
**Connection note (40 chars):**
> Hi Robin, your line made me smile.
**Direct message · Use InMail: NO**
> Hi Robin, I applied to the Growth role.
""", True),
    ("a DM with no InMail verdict: the channel decision is missing", """## The messages
### 1 · Robin Ashworth: growth lead
**Profile: https://www.linkedin.com/in/robinashworth**
**Connection note (40 chars):**
> Hi Robin.
**Direct message**
> Hi Robin, I applied.
""", True),
    ("a research-stage roster with nothing drafted is NOT a failure", """## The messages
### 1 · Someone To Research: found via the board sweep
Profile research pending; hooks not fetched yet.
""", False),
    ("an explicit NOT DRAFTED marker is respected", """## The messages
### 1 · Priya Nair: founding engineer, reports-to for this req
**Profile: https://www.linkedin.com/in/priyanair**
NOT DRAFTED: deliberately left for the outreach pass so it passes the gate.
""", False),
    ("section furniture is not read as a person", """## The messages
### Drafted 2026-01-01 (day-1 batch)
**Cards for this audience**: IN = systems depth.
""", False),
    ("a 1st-degree contact needs no connection REQUEST: must not be flagged", """## The messages
### 3 · Chloe Marsh: "Visual Designer at Acme Studio" (1st°, viewed ~2w ago), DAY 3
- Profile: https://www.linkedin.com/in/chloemarsh-example/
- **Use InMail: NO** (1st-degree).
**DM (607 chars):**
> Hi Chloe, I am reaching out about the Interaction Designer opening, job 5735407004.
> My work is at example.com. Would you point me at the right person?
""", False),
    ("a profile URL on the HEADING line counts", """## The messages
### Noah Bergstrom: designer at Globex · https://www.linkedin.com/in/noahbergstrom-example
**Connection note (60 chars):**
> Hi Noah, I applied to the Senior role.
**Direct message · Use InMail: NO**
> Hi Noah, I applied and would love your read on it.
> My work is at example.com. Would you point me at the right person?
""", False),
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
    print()
    # portfolio_url() itself must run cleanly against the real repo (configured or not).
    p = portfolio_url()
    print(f"  ✓ CONFIG    portfolio_url() runs cleanly on the real repo (currently: {p or 'not configured'})")
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
    checked = 0
    for p in paths:
        if not p.is_file():
            continue
        checked += 1
        try:
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        findings.extend(scan_text(rel, p.read_text(encoding="utf-8", errors="replace")))

    print(f"outreach_format.py: checked {checked} file(s) for the three-part handover (CLAUDE.md §13.6)")
    print("  every person: the LinkedIn profile URL · the connection note · the DM + its InMail verdict")
    print("  NOT checked: whether the copy is good (verify_claims.py owns voice, length and evidence),")
    print("               and what an agent types into chat; this gates the FILE the chat is read off.")
    if checked == 0:
        print("\n🔴 CHECKED NOTHING: this is a FAILURE, not a pass.", file=sys.stderr)
        if missing:
            print(f"   paths that do not exist: {', '.join(missing)}", file=sys.stderr)
        print("   Pass a dossier directory, a referrals.md, or no argument at all to sweep the repo.",
              file=sys.stderr)
        return 2
    if not findings:
        print(f"\nCLEAN: every drafted person in {checked} file(s) carries all three parts.")
        return 0
    print(f"\n{len(findings)} HALF-FINISHED HANDOVER(S):\n")
    for f in findings:
        print(f.render())
        print()
    print("Fill the missing parts, or mark the person NOT DRAFTED if they are research-stage.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
