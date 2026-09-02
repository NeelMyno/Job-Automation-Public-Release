#!/usr/bin/env python3
"""
verify_claims.py: the grounding gate.

WHY THIS EXISTS
---------------
A false claim in outbound copy is exactly as easy to write as a true one: a fabricated quote, a
stretched framing of your own past work, or a rounded-up metric all read as well-formed, confident
prose. None of them look different from something true, which is what makes them dangerous, and
what makes "I re-read it and it seemed fine" an unreliable check: a plausible sentence does not
announce itself as invented.

So this is a MECHANICAL gate, not an editorial one. It checks specific, falsifiable properties:
does this quotation exist in a file you actually fetched, is it tied to the person the copy says
said it, has this exact phrasing already been corrected once before, rather than asking an agent
to "be careful," which is not a check.

WHAT IT ENFORCES
----------------
On every piece of OUTBOUND copy in an application dossier (the referral messages, the sendable
cover-letter body, the form answers):

  R0  STRUCTURE     `referrals.md` must exist, stored sources must exist, and `## The
                     messages` must be locatable.
  R1  QUOTATION      Every quoted string must appear verbatim in a file under `sources/`,
                     and, when the copy attributes it to a PERSON, in a file that
                     plausibly belongs to THAT person. A job posting may never source a
                     human being's speech; a posting is the company's words, not a
                     person's. (See THE OWNERLESS HAYSTACK below.)
  R2  ATTRIBUTION    Any sentence that attributes speech, belief, or authorship to the
                     recipient must carry a sourced quotation (one that is not sourced
                     only to the posting), or the section must carry an explicit
                     `OPERATOR-VERIFY:` line naming what you must confirm yourself.
  R3  REGRESSION     A claim you have already corrected once may never reappear, anywhere,
                     in any wording. Populate `RETRACTED` below the first time you catch one.
  R4  LENGTH         LinkedIn connection notes stay under 300 characters.
  R5  VOICE          No em-dashes, no performed emotion (see your own voice rules).
  R6  NUMBERS        A metric you have already proven fabricated and purged may never
                     reappear. Populate `RETRACTED_NUMBERS` below the first time.
  R7  DEFAULT DENY   Any person's section carrying messages must have EITHER a sourced
                     quotation OR an `OPERATOR-VERIFY:` line. Silence is not evidence:
                     you only cold-message someone because you claim to know something
                     about them, so that something must be checkable.
  R8  PRE-SEND GATE  `pre-send-check.md` must exist with all six items genuinely marked:
                     FULL-TEXT · MEDIA · NO-ANSWERED-QUESTIONS · PERSON · COMPANY ·
                     ABSENCE-CLAIMS. Born from a real miss where the answer to a question
                     the copy asked was sitting in the posting's own attached image.
  R9  RESUME RETIRED `resume/resume.html` must not contain a string you have explicitly
                     retired from your résumé (a former employer you decided not to list,
                     a title correction). Populate `RESUME_RETIRED` below. This rule also
                     imports `canon.py`'s retired-claims registry and applies it to the
                     dossier's résumé and cover letter (R9b): a decision recorded only in
                     a knowledge base and never applied to the actual outbound document is
                     not a decision that shipped.
  R10 LINK-CLAIM     Every portfolio link in a sendable block or a résumé entry is checked
                     against `projects/CLAIMS-MANIFEST.md`: a term from the slug's
                     `never-claim-here:` list in the same block/entry = RED; a work-claim
                     noun near the link absent from its `shows:` = AMBER; an unknown slug
                     = RED. Exists because a claim can be true about your career and still
                     false about the specific link sitting next to it; every rule above
                     sails past that gap, because every clause in the sentence is
                     individually true.
  R11 CARD RULE      `resume/tailoring.md` declares which real strengths ("cards") you led
                     with and which you held back for this application. A card marked IN
                     must APPEAR in the shipped copy; a card marked OUT must be ABSENT from
                     every artifact, résumé bullets included. Exists because a tailoring
                     record that just states an intent, with nothing checking it against
                     what actually shipped, silently drifts from the truth.
  R12 CORE FACTS     Your OWN load-bearing facts (who you worked for, what that work
                     actually was) have a grounded truth, and a false framing of them must
                     never appear in outbound copy even when every individual word in the
                     sentence is common English. Populate `CORE_FACTS` below the first time
                     a false framing of your own work reaches a draft. Every pattern must
                     be ANCHORED to your own employer/domain, so this rule never fires on a
                     TARGET company that is truthfully described the same way.

THE BIGGEST SCOPE GAP, NAMED: THIS GATE READS ONLY WHAT `sendable_blocks()` COLLECTS:
referrals.md, cover-letter/cover-note.md, and application.md form answers, plus, for R9/R10/R12,
the résumé and cover-letter files themselves. Anything outside those files is invisible to it.
Automated coverage of the primary artifacts narrows this gap; it does not close it. A human
review pass remains the only thing that catches general semantic drift in a sentence that touches
none of the above.

SCOPE LIMIT, STATED PLAINLY: R1/R2/R4/R7 sweep `referrals.md` ONLY. R3/R5/R6/R10/R12 sweep the
wider sendable set (cover-note body + application.md answers + résumé/cover-letter artifacts). So
an invented quotation inside `cover-letter/cover-note.md` is NOT currently matched against
`sources/`. That is a real hole in the surface this gate is trusted to cover, documented rather
than silently carried; closing it means widening the R1/R2 scope.

THE OWNERLESS HAYSTACK, AND WHY OWNERSHIP MATTERS.
A naive version of this gate concatenates every stored source into ONE flat string and asks only
"do these words exist SOMEWHERE in the pile?". That check is not enough: a quotation put in person
A's mouth would pass if the words merely lived in person B's profile, or in the job posting. A
posting's own boilerplate ("we're looking for someone who thinks like X and ships like Y") is
real, verbatim, stored text; it is also never something a human being said to you personally, and
attributing it to them by name is exactly how a fabricated quote gets built out of entirely
genuine material.

So sources are kept as an INDEX (`Sources`), one entry per file, and every match carries its
owner. When the copy attributes a quotation to a PERSON, R1 additionally asks WHOSE file it came
from:
  · sourced only to a posting/JD-class file      -> RED. A posting is the company's words.
  · sourced only to files that cannot be tied to that person -> reported, named, and the
    reviewer sees "sourced, but to a DIFFERENT file than this person's".
  · attributed to a DOCUMENT instead ("the posting says", "your listing describes", "the job
    description asks for") -> the posting is the right source and the gate stays quiet. That
    is not a loophole, it is the honest way to quote a posting.
The flat-haystack answer is kept as the lower-severity signal underneath the ownership answer, so
no coverage is lost by adding this, only gained.

THE ANNOTATION EXEMPTIONS, AND WHY THEY ARE NARROW.
`OPERATOR-VERIFY:` and a `SENT LOG` prefix mark a block as something other than a fresh outbound
draft: a record of something already sent, or a flag that a fact needs your own eyes before it
ships. Either one COULD be used as a kill switch: prefix anything with `SENT LOG:` and the whole
block goes invisible to every rule. That is worse than no gate, because the reviewer sees a clean
PASS and trusts it.

So an annotation may silence ONLY the rule class it is actually ABOUT (see ANNOTATION_EXEMPTIONS):
a note that says "I have not independently verified this claim" speaks to whether a claim is
PROVEN (R1/R2/R7), never to whether the copy is honest (R3/R6), in voice (R5), inside LinkedIn's
cap (R4), or truthful about a portfolio link (R10/R12). And every block an annotation silences is
COUNTED AND NAMED in the `NOT checked:` line, because a gate that turns itself off without saying
so is worse than one that was never built: the PASS is trusted.

The split that matters is PREFIX, not SUBSTRING:
  · The marker PREFIXES the block -> the block IS a record addressed to you, not copy for a
    recipient, so length/voice rules do not apply. THE TRUTH ALARMS STILL RUN (R3/R6/R10/R12):
    a retracted fabrication inside a "sent" record means it REACHED A REAL PERSON, which is the
    single most important thing this gate can discover.
  · The marker sits INSIDE a real draft -> the block IS outbound copy that happens to carry an
    annotation. It gets ONLY the evidence-class exemption; voice, length, retracted claims,
    purged metrics, and link claims all still run on it.

`sources/*.md` files hold VERBATIM fetched page text with a `url:` and `fetched:` header. Editing
a source file so a quote passes is forgery. It is the one thing this system exists to prevent, and
the one thing this script cannot detect. Don't.

USAGE
-----
    python3 scripts/verify_claims.py "applications/<company>-<role>"
    python3 scripts/verify_claims.py --selftest      # asserts the gate catches every rule

Exit 0 = clean. Exit 1 = something unsourced is about to be sent to a real human.
"""

from __future__ import annotations
import re
import sys
import unicodedata
from pathlib import Path

# ── Rule 3: fabrications this repo has already corrected. ──────────────────────────
# Ships EMPTY. Add an entry the moment you catch a claim being corrected: once a
# wording has been retracted, it must never be able to silently resurface, in this
# wording or a paraphrase of it. `pattern` is a regex, matched case-insensitively
# against the normalized block text.
#
# Shape of each entry:
#   {"pattern": r"a regex matching the retracted wording",
#    "why":     "why this was retracted, so a future reader understands the correction",
#    "instead": "what to say instead"}
RETRACTED: list[dict] = []

# ── Rule 12: the core-facts guard. ──────────────────────────────────────────────────
# R3 above catches corrected claims and retired phrasings in general. This catches
# FABRICATED FRAMINGS OF YOUR OWN load-bearing facts specifically: your own employer,
# your own past work, which nothing else in this gate is positioned to catch, because
# R1/R2 guard OTHER people's words, not your own.
#
# Ships EMPTY. Each entry carries `truth` (the grounded descriptor to reach for instead)
# and `banned` (compiled regexes for the FALSE framings, ANCHORED to your own
# employer/domain). The anchor is the whole discipline: a false framing of YOUR employer
# must never be confused with a TRUE statement about a target company that happens to
# share the same words. A blanket ban with no anchor would fire on every honest dossier
# and get switched off within a week. `[^.\n]{0,N}` keeps each match inside one clause so
# it cannot span a paragraph and misfire.
#
# Shape of each entry:
#   {"id": "short-slug", "truth": "the grounded descriptor",
#    "banned": [(re.compile(r"...", re.I), "human-readable label for this false framing"), ...]}
CORE_FACTS: list[dict] = []

# ── Rule 6: metrics you have proven fabricated and purged. ─────────────────────────
# Ships EMPTY. Add a string here the moment a fabricated or wrong number gets caught,
# so it can never silently resurface in outbound copy.
RETRACTED_NUMBERS: list[str] = []

# ── Rule 9: strings you have explicitly RETIRED FROM THE RÉSUMÉ. ───────────────────
# Not fabrications: real facts you decided not to list (a former employer you no
# longer name, a title correction). Ships EMPTY. The gate enforces the decision so it
# cannot ship logged-but-unexecuted: a change recorded only in a knowledge base and
# never applied to the actual résumé file is not a change that happened.
#
# Shape: {"the retired string": "why it was retired, so a future reader understands"}
RESUME_RETIRED: dict[str, str] = {}

# ── Rule 10: the claims manifest. ───────────────────────────────────────────────────
# `projects/CLAIMS-MANIFEST.md` records, per published portfolio route, what the
# deployed artifact actually presents (`shows:`) and the known traps
# (`never-claim-here:`). The manifest is data, this gate is the teeth. A missing
# manifest is a loud failure in check_dossier, never a silent skip.
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "projects" / "CLAIMS-MANIFEST.md"

# The portfolio domain itself is READ FROM THE MANIFEST, not hardcoded here. A public
# release must not assume any one person's domain: `load_manifest()` parses a
# `domain: <your-domain>` header line from the top of the manifest file, and
# `get_link_re()` (below) compiles the link-matching regex from it at runtime, cached
# alongside the rest of the manifest. Fail-safe: if the manifest is missing, or carries
# no `domain:` line, `get_link_re()` returns None and R10 simply finds no links to
# check for that dossier, identical in effect to today's behavior for a link on any
# domain the manifest does not recognize.
_LINK_RE_CACHE: re.Pattern | None = None
_LINK_RE_LOADED = False


def get_link_re() -> re.Pattern | None:
    """The `<your-domain>/<slug>` matcher, built from the manifest's `domain:` line.

    Cached alongside `_MANIFEST_CACHE` for the life of the process (mirrors
    `load_manifest()`'s own caching; both are re-read once, on first use).
    """
    global _LINK_RE_CACHE, _LINK_RE_LOADED
    if _LINK_RE_LOADED:
        return _LINK_RE_CACHE
    _LINK_RE_LOADED = True
    manifest = load_manifest()
    domain = manifest.get("domain") if manifest else None
    _LINK_RE_CACHE = re.compile(re.escape(domain) + r"/([a-z0-9-]+)") if domain else None
    return _LINK_RE_CACHE


# Work-claim nouns R10 verifies against a linked slug's `shows:` list. Deliberately
# distinctive product nouns, not generic craft words ("research", "prototype" appear in
# every honest sentence and would only make the gate cry wolf). Generic across any
# product; not tied to any one person's work, so this list ships populated rather than
# empty; trim or extend it for your own domain.
WORK_CLAIM_NOUNS = [
    "login", "onboarding", "checkout", "upi", "funnel", "cart abandonment",
    "dispatcher", "theming layer", "multi-brand", "more than one brand", "second brand",
    "recommender", "recommendation", "knowledge graph", "capstone",
    "design system", "lint", "tokens", "operator console", "dashboard",
    "tracking page", "alerts", "triage", "queue",
    "downloads", "installs", "gmv", "adoption", "conversion",
    "transactional emails", "notifications", "conversational",
    "delivery date", "scheduler", "storefront",
]

_MANIFEST_CACHE: dict | None = None


def load_manifest() -> dict | None:
    """Parse projects/CLAIMS-MANIFEST.md once. None = missing/empty (a loud R10 failure).

    Returns {"sections": {slug: sec}, "aliases": {alias_or_slug: canonical_slug},
    "domain": str | None}. Each sec: shows (normed haystack), never ([(term, lineno)]),
    source, link_only, shows_line (first `shows:` line number, for AMBER messages that
    name the line).
    """
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    if not MANIFEST_PATH.is_file():
        return None
    sections: dict = {}
    domain: str | None = None
    cur = None
    for lineno, raw in enumerate(MANIFEST_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if raw.startswith("## "):
            slug = raw[3:].strip().lower()
            cur = {"shows_parts": [], "never": [], "aliases": [], "link_only": False,
                   "source": "", "shows_line": lineno}
            sections[slug] = cur
            continue
        # The top-level `domain:` header line, read wherever it sits (normally before
        # any `## ` section). First one wins; checked before the `cur is None: continue`
        # skip below so it is captured even though it lives outside any section.
        if domain is None:
            dm = re.match(r"domain:\s*(.+)", raw.strip(), re.I)
            if dm:
                domain = dm.group(1).strip()
                continue
        if cur is None:
            continue
        m = re.match(r"(aliases|scope-line|shows|never-claim-here|source-of-truth|check):\s*(.*)", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "aliases":
            cur["aliases"] += [norm(a) for a in val.split(",") if a.strip()]
        elif key in ("scope-line", "shows"):
            cur["shows_parts"].append(norm(val))
            if key == "shows" and "_first_shows" not in cur:
                cur["_first_shows"] = True
                cur["shows_line"] = lineno  # AMBER messages point at the first shows: line
        elif key == "never-claim-here":
            cur["never"] += [(norm(t), lineno) for t in val.split(",") if t.strip()]
        elif key == "source-of-truth":
            cur["source"] = val
        elif key == "check" and val == "link-only":
            cur["link_only"] = True
    if not sections:
        return None
    aliases: dict = {}
    for slug, sec in sections.items():
        sec["shows"] = " ; ".join(sec.pop("shows_parts"))
        aliases[slug] = slug
        for a in sec["aliases"]:
            aliases[a] = slug
    _MANIFEST_CACHE = {"sections": sections, "aliases": aliases, "domain": domain}
    return _MANIFEST_CACHE


def check_link_claims(where: str, block: str, findings: list, entry_scope: bool = False) -> None:
    """R10: every `<domain>/<slug>` in a block/entry is checked against the manifest.

    RED  (1) any `never-claim-here:` term for that slug anywhere in the same block/entry
         (a claim placed one clause away from the link is still beside it; block scope is
         what catches that proximity laundering); (3) an unknown slug (forces manifest
         upkeep when a new case study deploys).
    AMBER(2) a work-claim noun near the link (its own sentence for prose blocks, the
         whole entry for a résumé <li> when `entry_scope=True`), absent from the slug's
         `shows:` list. Names the manifest line so the fix is a lookup, not a hunt.
    """
    link_re = get_link_re()
    if link_re is None:
        return  # no manifest, or no `domain:` line; nothing to check (fail-safe)
    nb = norm(block)
    slugs = list(dict.fromkeys(link_re.findall(nb)))  # ordered, deduped
    if not slugs:
        return
    manifest = load_manifest()
    if manifest is None:
        return  # check_dossier already raised the loud MISSING finding once
    domain = manifest.get("domain") or "your-domain"
    sentences = re.split(r"(?<=[.!?])\s+", nb)
    for raw_slug in slugs:
        slug = manifest["aliases"].get(raw_slug)
        if slug is None:
            findings.append(Finding(
                "R10", where,
                f"RED: unknown slug '{domain}/{raw_slug}': no section in "
                "projects/CLAIMS-MANIFEST.md. Either the link is wrong (a 404 in copy a "
                "real person will click), or a new case study deployed and the manifest "
                "was not updated. Fix the link or add the section; never ignore this."))
            continue
        sec = manifest["sections"][slug]
        if sec["link_only"]:
            continue
        never_hay = " ; ".join(t for t, _ in sec["never"])
        # (1) RED: never-claim terms anywhere in the same block/entry.
        for term, lineno in sec["never"]:
            if term in nb:
                findings.append(Finding(
                    "R10", where,
                    f"RED: '{term}' appears in the same block/entry as a {domain}/{raw_slug} "
                    f"link, and the published artifact does not support it "
                    f"(projects/CLAIMS-MANIFEST.md:{lineno}, never-claim-here). The claim may be "
                    f"career-true, but next to THIS link it is false about the link. "
                    f"Source of truth: {sec['source']}.",
                    block[:120] + ("…" if len(block) > 120 else "")))
        # (2) AMBER: work-claim nouns near the link, absent from shows.
        if entry_scope:
            scopes = [nb]
        else:
            scopes = [s for s in sentences if f"{domain}/{raw_slug}" in s]
        for scope in scopes:
            for noun in WORK_CLAIM_NOUNS:
                if noun in scope and noun not in sec["shows"] and noun not in never_hay:
                    findings.append(Finding(
                        "R10", where,
                        f"AMBER: work-claim noun '{noun}' sits next to the {domain}/{raw_slug} "
                        f"link but is not in that slug's shows: list "
                        f"(projects/CLAIMS-MANIFEST.md:{sec['shows_line']}). Either the claim does "
                        f"not belong beside this link, or the manifest is stale; reconcile "
                        f"against {sec['source']} before shipping.",
                        scope[:120] + ("…" if len(scope) > 120 else "")))


# ── Rule 5: anti-slop voice check. ──────────────────────────────────────────────────
BANNED_WORDS = [
    "passionate", "passion for", "excited to", "thrilled", "delighted",
    "obsessed with", "seamless", "pixel-perfect", "geek out",
    "stuck with me", "the right kind of weird",
]

# ── Rule 2: phrases that put words, beliefs, or authorship onto the recipient. ─────
# If any of these appear in a message, the message must quote them from a stored source,
# or the section must carry an OPERATOR-VERIFY line.
ATTRIBUTION_TRIGGERS = [
    # speech / belief
    "you said", "you say", "you wrote", "you argue", "you argued", "you called",
    "you mentioned", "you talk about", "you framed", "you think", "you believe",
    "you want", "you look for", "you hire for", "the bit about",
    "your point about", "your line about", "your bio says", "your post",
    # authorship / role
    "you lead", "you built", "you build", "you created", "you own", "you run",
    "you head", "you architected", "you designed",
    # biography (cannot be fetched from an auth-walled profile you must not scrape)
    "you joined", "you moved", "your jump from", "your path",
]

OPERATOR_MARK = "OPERATOR-VERIFY:"

# Prefix labels that mark a quote-block as an INTERNAL RECORD for you rather than copy
# addressed to a recipient. Must appear at the START of the block (see
# internal_record_mark) so outbound copy cannot go dark by mentioning one mid-sentence.
INTERNAL_RECORD_MARKS = ("SENT LOG", "RETRACTED", "DO NOT SEND", "NOT SENT")

# ── WHAT AN ANNOTATION MAY SILENCE (narrow by design; see the module docstring). ──
# An annotation may silence only the rule class it is ABOUT, and every block it
# silences is counted and named in the `NOT checked:` line.
#
# The rule classes:
#   R1/R2/R7      "is this PROVEN?"          : an annotation about evidence may speak here
#   R3/R6         "is this TRUE?"            : a retracted claim, or a purged metric
#   R4            "does LinkedIn accept it?" : only meaningful for copy actually being sent
#   R5            "is it in your voice?"     : likewise
#   R10/R12       "is it true about the LINK / about your own facts?"
#
# THE SPLIT THAT MATTERS is PREFIX, NOT SUBSTRING. Two different things wear the same
# words.
#   · The marker PREFIXES the block  -> the block IS a record addressed to you. It is
#     not copy for a recipient, so the "is this good copy" rules (R4 length, R5 voice)
#     do not apply, and neither do the evidence rules, since the record's whole content
#     is what you saw with your own eyes and no agent can fetch.
#     THE TRUTH ALARMS STILL RUN: R3 (retracted claim), R6 (purged metric) and R10/R12
#     (false about a portfolio link / your own facts). A hit there means it REACHED A
#     REAL PERSON, which is the single most important discovery this gate can make.
#   · The marker sits INSIDE a real draft -> the block IS outbound copy that happens to
#     carry an annotation. It gets ONLY the evidence-class exemption. Voice, length,
#     retracted claims, purged metrics and link claims all still run on it.
# Collapsing those two is measurably worse: it puts real dossiers red over an em-dash
# inside an operator note that no human will ever receive. A gate that cries wolf gets
# disabled.
_RECORD = frozenset({"R1", "R2", "R7", "R4", "R5"})   # a note to you, not copy
ANNOTATION_EXEMPTIONS: dict[str, frozenset[str]] = {
    # A record of copy ALREADY SENT. It legitimately quotes what you saw on a profile,
    # and its length and voice are history. R3/R6 stay live: see above.
    "SENT LOG": _RECORD,
    # "I must confirm this with my own eyes", written as its own note. Same shape.
    # If such a note genuinely needs to NAME a retracted phrase, `RETRACTED` is the
    # label that exists for that; OPERATOR-VERIFY does not get to hold one silently.
    "OPERATOR-VERIFY prefix": _RECORD,
    # A draft explicitly held back. Not addressed to anyone, so voice, length and link
    # claims are moot, but a fabrication in a held draft is still a fabrication that a
    # later session can pick up and send, so R3 and R6 stay live.
    "DO NOT SEND": _RECORD,
    "NOT SENT": _RECORD,
    # A killed phrase, preserved so it cannot be reused. R3 MUST be silent here or the
    # repo's own memory trips the gate, and the fix an agent reaches for under pressure
    # is to DELETE the record: the wrong direction, since the record is the honest
    # part. The ONE row that silences the truth alarms, and it should stay narrow in
    # practice: this label has to be typed on purpose.
    "RETRACTED": _RECORD | frozenset({"R3", "R6", "R10", "R12"}),
    # THE NARROWING. An `OPERATOR-VERIFY:` line trailing a real draft annotates the
    # EVIDENCE for a claim: the documented escape hatch for facts an agent cannot
    # fetch. It says nothing whatever about whether the copy is honest, in voice, or
    # inside the 300-character cap, and it may not pretend otherwise.
    "OPERATOR-VERIFY inline": frozenset({"R1", "R2", "R7"}),
}

# Every block an annotation silenced on the last check_dossier() run:
# (where, mark, rules). Printed into the NOT-checked line with a count, because a gate
# that turns itself off without saying so is worse than no gate: the PASS is trusted.
_SUPPRESSED: list[tuple[str, str, tuple[str, ...]]] = []

# ── Rule 8: the pre-send research gate. ─────────────────────────────────────────────
# Before ANY outbound copy ships, the dossier must carry pre-send-check.md with every
# item below marked [x]. A dossier whose outbound was sent before this rule existed
# carries SENT-BEFORE-RULE with the send date instead.
PRESEND_ITEMS = [
    ("FULL-TEXT", "the primary posting's full text is stored under sources/ and was read"),
    ("MEDIA", "every image/video attached to the posting was VIEWED WITH EYES and stored (or 'none attached' stated after checking)"),
    ("NO-ANSWERED-QUESTIONS", "every question in the outbound copy was checked against the full posting INCLUDING its media; none asks what the posting already answers"),
    ("PERSON", "the recipient's profile AND their public WORK (portfolio, posts, writing) were hunted, fetched, and stored under sources/, or a per-person NOTHING-FOUND is recorded; messages may reference only fetched work"),
    ("COMPANY", "the company's official site and careers/ATS surface were checked this session"),
    ("ABSENCE-CLAIMS", "every 'not stated / does not exist' claim names exactly which surfaces were checked"),
]
GRANDFATHER_MARK = "SENT-BEFORE-RULE"


def norm(s: str) -> str:
    """Fold the typography that makes verbatim matching fail for cosmetic reasons."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("—", " "), ("–", "-"), (" ", " ")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


_HISTORY_SKIPPED: list[str] = []

_DEAD_STATUSES = ("rejected", "passed", "withdrawn")


def _dossier_status_if_dead(folder: Path) -> str | None:
    """Return the tracker status if this dossier is dead (rejected/passed/withdrawn), else None.

    Authority is pipeline/tracker.html, which only your real outcomes update, so a dossier can
    never mark ITSELF dead to dodge a gate. A read failure returns None: the gate stays ON. That
    direction is deliberate: an unreadable tracker must never silently exempt a live dossier.
    """
    try:
        t = (Path(__file__).resolve().parents[1] / "pipeline" / "tracker.html").read_text(encoding="utf-8")
    except Exception:
        return None
    for m in re.finditer(r'\{co:"[^"]+"[^}]*\}', t):
        s = m.group(0)
        if re.search(r'folder:"applications/' + re.escape(folder.name) + r'/?"', s):
            st = re.search(r'status:"([a-z]+)"', s)
            return st.group(1) if st and st.group(1) in _DEAD_STATUSES else None
    return None


class Finding:
    def __init__(self, rule: str, where: str, detail: str, evidence: str = ""):
        self.rule, self.where, self.detail, self.evidence = rule, where, detail, evidence

    def __str__(self) -> str:
        line = f"  [{self.rule}] {self.where}\n        {self.detail}"
        if self.evidence:
            line += f"\n        > {self.evidence}"
        return line


# A job posting is the COMPANY's words. It may source a claim about the role; it may
# NEVER source a human being's speech. Detected by filename, because a posting does not
# always live at `jd-*.md`; other stored postings under sources/ carry names like
# `sources/<company>-jd-<role>.md` or `sources/posting-<role>.md`. Deliberately NOT
# matching bare "post": `<person>-linkedin-post.md` is a person's own writing and is
# exactly the file that SHOULD source their speech.
JD_FILENAME_RE = re.compile(r"(?:^|[-_])(jd|job|jobs|jobdesc|posting|postings|req|requisition)(?:[-_]|$)")

# How much of a file counts as its "header" for the does-this-belong-to-them test: the
# `url:` / `fetched:` block plus the page title and opening content.
HEADER_CHARS = 2000
# How far from a quotation the person's name may sit and still count as attribution
# inside the source itself. This is what makes a shared page (a team page, a company
# blog carrying several people's quotes) able to legitimately source one person.
NEIGHBOURHOOD_CHARS = 500


class SourceFile:
    """One stored primary source, kept SEPARATE from every other one.

    The whole point: a match must carry its owner. Concatenating these was the bug.
    """

    __slots__ = ("name", "text", "is_jd")

    def __init__(self, name: str, text: str):
        self.name = name
        self.text = norm(text)
        stem = Path(name).name.rsplit(".", 1)[0].lower()
        self.is_jd = bool(JD_FILENAME_RE.search(stem))

    @property
    def filename_words(self) -> str:
        return re.sub(r"[-_.]+", " ", Path(self.name).name.rsplit(".", 1)[0].lower())

    def carries(self, nquote: str) -> bool:
        return bool(nquote) and nquote in self.text

    def mentions(self, needle: str, nquote: str = "") -> bool:
        """Does this file tie `needle` (a person's name) to itself, or to `nquote`?

        Three acceptance paths, cheapest first:
          1. the FILENAME says so  (`person-name-linkedin.md`, `namewhatever-profile.md`)
          2. the HEADER says so    (the `url:`/`fetched:` block and the page title)
          3. the name sits within NEIGHBOURHOOD_CHARS of the quotation IN THE FILE,
             which is the strongest signal of all, and the one that lets a team page
             or a multi-quote article correctly source the person it attributes to.
        """
        if not needle:
            return False
        if needle in self.filename_words or needle in self.text[:HEADER_CHARS]:
            return True
        if nquote:
            i = self.text.find(nquote)
            if i >= 0:
                lo = max(0, i - NEIGHBOURHOOD_CHARS)
                hi = i + len(nquote) + NEIGHBOURHOOD_CHARS
                return needle in self.text[lo:hi]
        return False


class Sources:
    """The per-file index that replaced the ownerless haystack (see the module docstring).

    `.haystack` is preserved so the ORIGINAL "does it exist anywhere" answer stays
    available as the lower-severity signal underneath the ownership answer. Coverage
    was added, never traded away.
    """

    def __init__(self, files: list[SourceFile]):
        self.files = files
        self.haystack = " \n ".join(f.text for f in files)

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.files]

    def __bool__(self) -> bool:
        return bool(self.files)

    def owners(self, quote: str) -> list[SourceFile]:
        """EVERY file carrying this quotation, so the caller can ask WHOSE it is."""
        nq = norm(quote)
        return [f for f in self.files if f.carries(nq)]


def load_sources(folder: Path) -> Sources:
    """Index every stored primary source, ONE ENTRY PER FILE.

    Two kinds count as primary:
      sources/*.md  : verbatim fetched page text (a person's own words)
      jd-*.md       : the verbatim job posting, pulled from the ATS with its URL and date
    Nothing else. A claim is not sourced because another file in this repo repeats it,
    and a person's claim is not sourced because the COMPANY's posting happens to
    contain the same sentence.
    """
    files: list[SourceFile] = []
    sdir = folder / "sources"
    if sdir.is_dir():
        for f in sorted(sdir.glob("*.md")):
            files.append(SourceFile(f"sources/{f.name}", f.read_text(encoding="utf-8", errors="replace")))
    for f in sorted(folder.glob("jd-*.md")):
        files.append(SourceFile(f.name, f.read_text(encoding="utf-8", errors="replace")))
    return Sources(files)


# ── WHO is this quotation attributed to? ───────────────────────────────────────────
# The load-bearing question, and the one that decides whether a posting may source it.
# Both detectors are PROXIMITY-BOUND to the quotation (the window below), never
# block-wide, because a block-wide detector produces false positives on an honest
# posting quote whose "you wrote" trigger sits several paragraphs away. A gate that
# cries wolf gets disabled.
ATTRIBUTION_WINDOW = 150

# The copy names a DOCUMENT as the speaker. Then a posting/JD-class source is exactly
# right, and R1's ownership test must stay quiet: "the job description can say ...",
# "the posting describes ...", "your listing says ...".
DOCUMENT_SPEAKER_RE = re.compile(
    r"\b(job description|jd|job ad|job post|posting|listing|req|requisition|"
    r"role description|the description|careers page|the ad|the spec|"
    r"the site|the website|the page|the docs|documentation|readme|changelog|"
    r"press release|announcement|the manifesto|the handbook)\b")

# The copy names the PERSON as the speaker. Second-person forms dominate here because
# every one of these messages is addressed to the person it quotes.
PERSON_SPEECH_RE = re.compile(
    r"\b(you (?:said|say|told|wrote|write|argued|argue|called|call|mentioned|framed|"
    r"described|describe|noted|asked|posted|put it|think|believe)|"
    r"in your words|as you put it|the bit about|"
    r"your (?:[\w'-]+ ){0,4}"
    r"(?:post|posts|note|thread|comment|essay|piece|article|talk|interview|writing|"
    r"words|line|point|bio|profile|newsletter|blog|video|podcast|answer|reply|tweet))\b")

# `<Somebody> said "..."`: third-person speech verb immediately before the quotation.
NEAR_SPEECH_VERB_RE = re.compile(
    r"\b(said|says|say|wrote|writes|told|argued|argues|puts? it|called|calls|"
    r"describ\w+|framed|frames|noted|notes|mentioned|mentions|asked|posted|quote[ds]?)\b")


def quote_attribution(block: str, quote: str) -> str:
    """'person' | 'document' | '': who the COPY says these words belong to.

    Proximity-bound: only the ATTRIBUTION_WINDOW characters immediately before the
    quotation are read. '' means the copy claims no speaker at all, in which case the
    original flat-haystack answer is the only one R1 asks (coverage preserved).
    """
    nb, nq = norm(block), norm(quote)
    i = nb.find(nq)
    if i < 0:
        i = nb.find(nq[:40])
    if i < 0:
        return ""
    pre = nb[max(0, i - ATTRIBUTION_WINDOW):i]
    # Person wins over document: "your listing" is still the recipient's listing, but
    # "you said" beats a stray "the page" every time.
    if PERSON_SPEECH_RE.search(pre):
        return "person"
    if DOCUMENT_SPEAKER_RE.search(pre):
        return "document"
    if NEAR_SPEECH_VERB_RE.search(pre[-90:]):
        return "person"
    return ""


# Headings under `## The messages` that are NOT a person. Ownership FAILS OPEN on these
# (checks skip): the cost of a wrong "not a person" is zero, the cost of a wrong
# "is a person" is a false positive, so this list is deliberately generous.
NON_PERSON_HEADINGS = {
    "none", "no", "not", "ruled", "unified", "drafted", "additional", "backup", "other",
    "others", "more", "how", "what", "why", "the", "notes", "note", "operator", "day",
    "wave", "pack", "misc", "tbd", "unknown", "remaining", "extra", "warm", "cold",
    "status", "summary", "index", "plan", "next", "sent", "retracted", "all", "everyone",
    "team", "people", "contacts", "nodes", "node", "hiring", "recruiters", "alumni",
    "ranked", "candidates", "targets", "pending", "open", "also", "first", "second",
    "third", "fourth", "fifth", "message", "messages", "draft", "drafts", "who", "where",
    "when", "which", "if", "after", "before", "optional", "bonus", "appendix", "honest",
    "gaps", "everyone", "nobody", "todo", "unsent", "held", "skip", "skipped",
}


def person_name_tokens(heading: str) -> list[str] | None:
    """Name tokens for a `### ` heading, or None when it is not confidently a person.

    Real headings this must survive:
        ### 1 · A Person, "a role at a company" (1st°, viewed ~2w ago)
        ### 1. A Person, Head of Product (THE hiring node) · **url**
        ### A Person, SHORT variant (253 chars, fits LinkedIn's 300-char note)
        ### 4. A B (Middle) Person, designer at a company · https://...
        ### 1. A Person (recruiter who owns the req)
    and must REFUSE, so ownership fails open rather than crying wolf:
        ### None drafted yet · ### Ruled out / honest gaps · ### Unified pack (pointer)
        ### 4 · DJ, the warm lane      (a nickname; no file could ever match it)
    """
    h = re.sub(r"^\s*[#\s]*\d+\s*[.)·\-–—]\s*", "", heading.strip())
    # Drop multi-word parentheticals ("(recruiter who owns the req)"); KEEP a
    # single-token one, which is how a second given name is written: "A (Middle) Person".
    h = re.sub(r"\(([^)]*)\)", lambda m: m.group(1) if len(m.group(1).split()) == 1 else " ", h)
    h = re.split(r"[—–·|]|\s-\s|https?:|[\"“”]|:|,", h)[0]
    h = re.sub(r"[^\w\s'.\-]", " ", h)
    toks: list[str] = []
    for raw in h.split():
        t = raw.strip("().,'\"").rstrip(".")
        if not t or not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", t):
            break
        toks.append(t)
    if not toks or len(toks) > 4:
        return None
    if toks[0].lower() in NON_PERSON_HEADINGS:
        return None
    if not any(len(t) >= 3 and t[0].isupper() for t in toks):
        return None  # "DJ" and other initials-only nicknames: unmatchable, so skip
    return [t.lower() for t in toks]


def source_belongs_to(sf: SourceFile, tokens: list[str], quote: str) -> bool:
    """Does this source file plausibly belong to the person named by `tokens`?

    Full name OR surname, matched as a SUBSTRING so a concatenated filename style
    (`namehandle-linkedin-profile.md`) and a surname-only style
    (`person-surname-linkedin.md`) both resolve.
    """
    nq = norm(quote)
    full = " ".join(tokens)
    if sf.mentions(full, nq):
        return True
    surname = tokens[-1]
    if len(surname) >= 4 and sf.mentions(surname, nq):
        return True
    return False


def sendable_blocks(folder: Path) -> list[tuple[str, str, frozenset[str]]]:
    """(where, text, exempt_rules) for EVERY string a real human will actually read.

    This is deliberately narrow. A markdown blockquote in a documentation section is
    not sendable copy, and a linter that flags it will be turned off within a week.

    `exempt_rules` is empty for everything except an ANNOTATED referral block, and even
    there it is now a narrow row of ANNOTATION_EXEMPTIONS rather than "all of them".
    """
    out: list[tuple[str, str, frozenset[str]]] = []

    ref = folder / "referrals.md"
    if ref.exists():
        for person, section in extract_referral_sections(ref.read_text(encoding="utf-8")):
            for kind, msg, exempt in message_blocks(section):
                where = f"referrals.md · {person} · {kind}"
                _record_suppression(where, annotation_exemption(msg)[0], exempt)
                out.append((where, msg, exempt))

    cover = folder / "cover-letter" / "cover-note.md"
    if not cover.exists():
        cover = folder / "cover-note.md"          # backward-compat: an older dossier shape
    if cover.exists():
        parts = cover.read_text(encoding="utf-8").split("\n---\n")
        if len(parts) >= 3:  # the sendable letter lives between the first pair of fences
            out.append(("cover-note.md · the sendable letter", parts[1], frozenset()))

    app = folder / "application.md"
    if app.exists():
        t = app.read_text(encoding="utf-8")
        # `Q\d` (single digit) would make every form answer from Q10 onward invisible to
        # the gate. `Q\d+` covers any question number; long ATS forms routinely run past
        # ten questions, so this matters on exactly the dossiers with the most typed-in
        # free text.
        for m in re.finditer(r"### Q\d+\..*?\n((?:>.*\n|\n)+)", t):
            body = "\n".join(l.lstrip("> ") for l in m.group(1).splitlines() if l.startswith(">"))
            if body.strip():
                out.append(("application.md · a form answer", body, frozenset()))

    return out


def extract_referral_sections(text: str) -> list[tuple[str, str]]:
    """Return (person_heading, section_body) for each numbered person in referrals.md.

    The sendable zone is everything after `## The messages` UP TO THE NEXT LEVEL-2
    HEADING, whatever it is named. An earlier version of this cut at one specific
    hardcoded heading name, which meant any dossier that closed `## The messages` with
    a differently-named (or absent) trailing heading had its trailing prose swept in as
    if it were outbound copy: a real false-positive risk, since that trailing prose is
    exactly where documentation/process notes tend to live. Cutting at the next `## `
    heading generically closes that regardless of what the heading is called.
    """
    if "## The messages" not in text:
        return []
    body = text.split("## The messages", 1)[1]
    body = re.split(r"\n## ", body, 1)[0]
    parts = re.split(r"\n### ", body)
    return [(p.split("\n", 1)[0].strip(), p) for p in parts[1:]]


def quoted_strings(s: str) -> list[str]:
    """Double-quoted spans of 3+ words. Short quotes are usually product names, not claims."""
    out = []
    for m in re.findall(r'"([^"]{6,300})"', s):
        if len(m.split()) >= 3:
            out.append(m)
    return out


def internal_record_mark(body: str) -> str:
    """The internal-record label PREFIXING this block, or '', rather than a bool.

    Every quote-block in a person's section counts as sendable copy by default, which is
    right for catching unlabelled drafts but would misfire on internal records that
    legitimately live in the same section: a `SENT LOG` recording what you confirmed
    with your own eyes on a profile, and a `RETRACTED` note preserving a killed phrase
    so it cannot be reused. Both quote a third party, so R1 would flag them as unsourced
    quotations, and the fix an agent reaches for under pressure is to DELETE the record.
    That is the wrong direction: the record is the honest part.

    The marker must PREFIX the block, so it is a deliberate label rather than a word
    buried in prose. That keeps the R8 hole shut: outbound copy cannot go dark by
    mentioning "sent log" mid-sentence.

    Returning the mark instead of True/False is what lets the exemption be NARROWED: the
    label no longer deletes the block from the gate, it selects a row of
    ANNOTATION_EXEMPTIONS (see the module docstring).
    """
    for mark in INTERNAL_RECORD_MARKS:
        if block_head(body).startswith(mark):
            return mark
    return ""


def block_head(body: str) -> str:
    """The block's opening, stripped of quoting, emphasis and status emoji, upper-cased.

    One helper for both marker families, so `**SENT LOG (date):**` and
    `⚠ **OPERATOR-VERIFY:** confirm ...` resolve by the same prefix law.
    """
    return body.lstrip("*_>#~ \t\n").lstrip("⚠🔴🟠🟡🟢✅⛔❌📌 ").lstrip("*_ ").upper()


def annotation_exemption(body: str) -> tuple[str, frozenset[str]]:
    """(label, rules this annotation may silence) for one quote-block. ('', empty) = none.

    PREFIX means the block IS a record for you. INLINE means real outbound copy that
    carries an annotation, and it gets the evidence-class exemption only.
    """
    mark = internal_record_mark(body)
    if mark:
        return mark, ANNOTATION_EXEMPTIONS[mark]
    if block_head(body).startswith("OPERATOR-VERIFY"):
        return "OPERATOR-VERIFY prefix", ANNOTATION_EXEMPTIONS["OPERATOR-VERIFY prefix"]
    if OPERATOR_MARK in body:
        return "OPERATOR-VERIFY inline", ANNOTATION_EXEMPTIONS["OPERATOR-VERIFY inline"]
    return "", frozenset()


def _record_suppression(where: str, mark: str, rules: frozenset[str]) -> None:
    """Remember a silenced block so the NOT-checked line can name it."""
    if not mark:
        return
    entry = (where, mark, tuple(sorted(rules)))
    if entry not in _SUPPRESSED:
        _SUPPRESSED.append(entry)


def message_blocks(section: str) -> list[tuple[str, str, frozenset[str]]]:
    """(kind, text, exempt_rules) for the sendable quote-blocks in a person's section.

    Annotated blocks are not DROPPED: they are returned with the set of rules their
    annotation may legitimately silence, and every rule outside that set still runs on
    them. See ANNOTATION_EXEMPTIONS.

    Any contiguous `> ` quote-block inside a person's section counts as sendable copy;
    the bold markers (`**Connection note**`, `**First DM**` / `**Direct message**`) only
    refine the kind label, so a draft written without them is still swept.

    DM IS MATCHED FIRST, DELIBERATELY. A DM label routinely explains its InMail verdict
    by naming the alternative, e.g. `**First DM (Use InMail: NO, free connection note
    is available...)**`, so a loose connection-note pattern would happily claim the
    DM's body and then R4 would cap a legitimately long DM at 300 characters. Matching
    DM first, and skipping bodies already claimed, is what keeps the two kinds apart.
    """
    blocks = []
    seen = set()
    for kind, pat in [("DM",
                       r"\*\*[^*\n]*?(?:First DM|Direct message)[^*\n]*?\*\*[^\n]*\n((?:> ?.*\n)+)"),
                      ("connection note",
                       r"\*\*(?![^*\n]*(?:First DM|Direct message))[^*\n]*?[Cc]onnection note[^*\n]*?\*\*[^\n]*\n((?:> ?.*\n)+)")]:
        for m in re.finditer(pat, section):
            body = "\n".join(l[2:] if l.startswith("> ") else l.lstrip(">")
                             for l in m.group(1).strip().splitlines())
            if norm(body) in seen:
                continue
            blocks.append((kind, body, annotation_exemption(body)[1]))
            seen.add(norm(body))
    for m in re.finditer(r"((?:^> ?.*\n?)+)", section, re.M):
        body = "\n".join(l[2:] if l.startswith("> ") else l.lstrip(">") for l in m.group(1).strip().splitlines())
        if body.strip() and norm(body) not in seen:
            blocks.append(("message", body, annotation_exemption(body)[1]))
            seen.add(norm(body))
    return blocks


# ────────────────────────────────────────────────────────────────────────────────────
# R11: THE CARD RULE, AS A GATE.
#
# A tailoring record kept as prose alone (in `resume/tailoring.md`) is enforced by
# nothing, and prose drifts from reality in both directions at once: a card can be
# marked "OUT" while still shipping in the cover letter, and a card can be marked "IN"
# while never actually appearing anywhere a recipient reads. Either way, the record
# itself becomes false, which is worse than no record, because the next session trusts
# it. So: a card marked IN must APPEAR in the shipped copy, and a card marked OUT must
# be ABSENT from every artifact, résumé bullets included.
# ────────────────────────────────────────────────────────────────────────────────────

# name -> (regex that detects the card in copy, regex that detects it in a declaration)
# Ships EMPTY. This is for R11's "which real strengths did you lead with vs. hold back
# per application" check; add your own entries once you have real positioning facts
# worth tracking (a scale metric, a specific past role, a specific technical claim).
CARD_SIGNATURES: dict[str, tuple[str, str]] = {}

# Artifacts a human actually receives. resume.html is INCLUDED on purpose: a card
# rechecked only against the cover letter and the form, and never against the résumé
# itself, would miss the exact surface most likely to carry it by default.
def _card_artifacts(folder: Path) -> list[tuple[str, str]]:
    out = []
    for rel in ("resume/resume.html", "cover-letter/cover-note.md", "application.md"):
        f = folder / rel
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        if rel.endswith(".html"):
            txt = re.sub(r"<[^>]+>", " ", txt)
        elif rel.endswith("cover-note.md"):
            # ONLY the sendable body, which sits between the first pair of --- fences.
            # The rest of the file is process commentary a recipient never sees;
            # matching a card there is a false positive, and a gate that cries wolf
            # gets ignored.
            parts = txt.split("\n---\n")
            if len(parts) >= 3:
                txt = parts[1]
        out.append((rel, txt))
    return out


def check_card_rule(folder: Path, findings: list) -> None:
    """R11: reconcile resume/tailoring.md's declared cards against the real artifacts."""
    tf = folder / "resume" / "tailoring.md"
    if not tf.exists():
        # Deliberately silent. A dossier built before R11 existed (or a dead one, which
        # stays read-only forever) has no declaration, and nagging about it would make
        # every historical dossier red, and a gate that is always red gets ignored. R11's
        # job is to catch a declaration that CONTRADICTS the artifacts, not to demand
        # the file.
        return

    decl = tf.read_text(encoding="utf-8", errors="replace")
    def _seg(label: str) -> str:
        m = re.search(rf"\*\*Cards {label}:\*\*(.*?)(?=\*\*Cards |\n## |\Z)", decl, re.S | re.I)
        return m.group(1) if m else ""
    seg_in, seg_out = _seg("IN"), _seg("OUT")
    if not seg_in and not seg_out:
        findings.append(Finding("R11", "resume/tailoring.md",
            "No '**Cards IN:**' / '**Cards OUT:**' declaration found, so the card rule is unenforceable here."))
        return

    artifacts = _card_artifacts(folder)
    # An OUT declaration may legitimately mean "out of the cover and form answers, but
    # retained in the résumé bullet", because the résumé is one fixed page. The gate
    # accepts that ONLY when the declaration says it in words; an unqualified OUT that
    # is contradicted by the artifacts stays a failure.
    retention_declared = bool(re.search(r"retained in the r[eé]sum", seg_out, re.I))
    for card, (copy_rx, decl_rx) in CARD_SIGNATURES.items():
        declared_in  = bool(re.search(decl_rx, seg_in, re.I))
        declared_out = bool(re.search(decl_rx, seg_out, re.I))
        if declared_in and declared_out:
            findings.append(Finding(
                "R11", "resume/tailoring.md",
                f"Card '{card}' is named in BOTH the IN and OUT declarations, so the card rule "
                f"cannot be enforced for it. Say which one it is. A silent skip here is exactly "
                f"how a contradictory declaration stays invisible."))
            continue
        if not declared_in and not declared_out:
            continue  # simply not declared for this target
        present = [rel for rel, txt in artifacts if re.search(copy_rx, txt, re.I)]
        # The résumé is a fixed one-page document whose bullets are the same for every
        # target by design; "OUT" there would mean rewriting it per application. So OUT
        # is ENFORCED on the persuasion surfaces the tailoring step actually controls
        # (the cover note and the form's free-text), and a card left standing in the
        # résumé is reported separately so the RECORD stays true either way.
        persuasion = [r for r in present if r != "resume/resume.html"]
        resume_only = present and not persuasion
        if declared_out and persuasion:
            findings.append(Finding(
                "R11", "resume/tailoring.md",
                f"Card '{card}' is declared **OUT** but still appears in: {', '.join(persuasion)}. "
                f"Either cut it from those artifacts or correct the declaration. A tailoring "
                f"record that misstates what shipped is worse than none."))
        elif declared_out and resume_only and not retention_declared:
            findings.append(Finding(
                "R11", "resume/tailoring.md",
                f"Card '{card}' is declared **OUT** but is retained in resume/resume.html. That is "
                f"legitimate (the résumé bullets are fixed), but the declaration must SAY so: write "
                f"'OUT of the cover and form answers; retained in the résumé bullet'. An unqualified "
                f"OUT is a false record."))
        if declared_in and not present:
            findings.append(Finding(
                "R11", "resume/tailoring.md",
                f"Card '{card}' is declared **IN** but appears in NO outbound artifact "
                f"({', '.join(rel for rel, _ in artifacts) or 'none found'}). Recording the "
                f"intent is not executing it."))


# Which rules actually got to run on the last check_dossier() call. The banner used to build its
# "checked:" line from the static rule registry in this module's docstring, so it would claim
# R0-R12 had run even when R0 short-circuited and only R0 had. That is a lie by omission inside the
# honesty gate: the exact "verdict without its blind spots" failure the scope line exists to
# prevent.
_RULES_SKIPPED: list[str] = []


def check_dossier(folder: Path) -> list[Finding]:
    global _RULES_SKIPPED
    _RULES_SKIPPED = []
    _SUPPRESSED.clear()
    _HISTORY_SKIPPED.clear()
    findings: list[Finding] = []
    sources = load_sources(folder)

    # R10 precondition: the manifest must exist. A missing manifest is a LOUD failure
    # on every dossier, never a silent skip: a gate that silently stops reading its
    # data file is how "logged-but-unexecuted" happens.
    if load_manifest() is None:
        findings.append(Finding(
            "R10", "projects/CLAIMS-MANIFEST.md",
            "The claims manifest is MISSING or empty, so the link-claim gate cannot run. "
            "Nothing ships until it is restored. It maps each published portfolio route "
            "to what the artifact actually shows."))

    ref = folder / "referrals.md"
    if not ref.exists():
        findings.append(Finding("R0", str(folder), "referrals.md is missing. Every application needs one."))
        # Everything below reads referrals.md. Record that they did NOT run, so the banner cannot
        # claim they did.
        _RULES_SKIPPED = ["R1", "R2", "R4", "R5", "R6", "R7"]
        globals()["_RULES_SKIPPED"] = _RULES_SKIPPED
        return findings

    if not sources:
        findings.append(Finding("R0", "sources/", "No stored sources. Any quotation in a message is unverifiable by construction."))

    text = ref.read_text(encoding="utf-8")
    sections = extract_referral_sections(text)
    if not sections:
        findings.append(Finding("R0", "referrals.md", "Could not locate the '## The messages' section."))

    for person, section in sections:
        has_operator_mark = OPERATOR_MARK in section
        # None = the heading is not confidently a person (a pointer, a nickname, a
        # "Ruled out" bucket). Ownership then FAILS OPEN: the flat-haystack answer is
        # the only one asked.
        ptokens = person_name_tokens(person)
        blocks = message_blocks(section)

        for kind, msg, exempt in blocks:
            where = f"referrals.md · {person} · {kind}"
            _record_suppression(where, annotation_exemption(msg)[0], exempt)
            nmsg = norm(msg)

            # R1: every quotation must exist in a stored source, and must belong to
            # whoever the copy says said it.
            if "R1" not in exempt:
                for q in quoted_strings(msg):
                    owners = sources.owners(q)
                    if not owners:
                        findings.append(Finding(
                            "R1", where,
                            "Quoted string is not present in any file under sources/. "
                            "Either it was invented, or the source was never stored.",
                            f'"{q}"'))
                        continue
                    # Sourced somewhere. Now: sourced to WHOM? Only asked when the copy
                    # itself claims a PERSON said it; a quotation attributed to the
                    # posting ("the JD asks for ...") or to nobody keeps the original
                    # flat-haystack verdict.
                    if quote_attribution(msg, q) != "person" or ptokens is None:
                        continue
                    owner_names = ", ".join(o.name for o in owners)
                    if all(o.is_jd for o in owners):
                        findings.append(Finding(
                            "R1", where,
                            f"RED: this quotation is attributed to {person.split('—')[0].strip()} "
                            f"by the copy itself, but the ONLY file carrying it is a JOB "
                            f"POSTING ({owner_names}). A posting is the COMPANY's words, never a "
                            f"person's: this is exactly how a fabricated quote gets built out of "
                            f"real, verbatim material (see THE OWNERLESS HAYSTACK in the module "
                            f"docstring). Fix by fetching and storing THEIR source, or, if you "
                            f"mean the posting, say so in the copy (\"the posting asks for ...\"), "
                            f"which this gate accepts.",
                            f'"{q}"'))
                        continue
                    if not any(source_belongs_to(o, ptokens, q) for o in owners):
                        findings.append(Finding(
                            "R1", where,
                            f"Sourced, but to a DIFFERENT file than this person's: the words are "
                            f"stored in {owner_names}, and nothing ties that file to "
                            f"{person.split('—')[0].strip()} (their name is not in its filename, "
                            f"not in its header, and not near the quotation inside it). The copy "
                            f"says THEY said it. Confirm the words are theirs and store the source "
                            f"under a name that says whose it is (sources/person-<name>-<what>.md), "
                            f"or cut the attribution. Sourced-somewhere is not sourced-to-them.",
                            f'"{q}"'))

            # R2: attribution to the recipient needs a sourced quote, or an operator flag.
            # A posting-only quotation is not accepted as that evidence: the company's
            # posting says nothing about what this person said or believes.
            if "R2" not in exempt:
                hit = next((t for t in ATTRIBUTION_TRIGGERS if t in nmsg), None)
                if hit:
                    sourced_quote = any(
                        (own := sources.owners(q)) and not all(o.is_jd for o in own)
                        for q in quoted_strings(msg))
                    if not sourced_quote and not has_operator_mark:
                        findings.append(Finding(
                            "R2", where,
                            f'Attributes something to the recipient ("{hit}") with no sourced quotation '
                            f"and no {OPERATOR_MARK} line in the section. "
                            "Quote them verbatim from sources/, or mark what you must confirm by hand.",
                            msg[:110] + ("…" if len(msg) > 110 else "")))

            # R4: LinkedIn's cap.
            if "R4" not in exempt and kind == "connection note" and len(msg) > 300:
                findings.append(Finding("R4", where, f"Connection note is {len(msg)} chars; LinkedIn caps at 300."))

        # R7: DEFAULT DENY, per person.
        #
        # R2's trigger list is a blocklist, and a blocklist always has a hole: a note
        # can assert unverifiable biography about the recipient with no trigger phrase
        # at all. You only cold-message someone because you know something about them.
        # So invert it: every person's section must carry EITHER a quotation traceable
        # to sources/, OR an explicit OPERATOR-VERIFY line naming what you must confirm
        # with your own eyes.
        #
        # R7 DELIBERATELY KEEPS THE FLAT-HAYSTACK EVIDENCE TEST. Tightening it the way
        # R2 is tightened ("a posting-only quotation is not evidence about a person")
        # would put an honest dossier red on a message that says only "the job
        # description can say '...' and mean it", which asserts nothing about the
        # recipient at all, so R7's premise never fires. R7 is an UNTRIGGERED
        # default-deny backstop; the ownership question belongs to R1 and R2, which are
        # trigger-gated and ask it properly. Widening a backstop until it fires on
        # honest copy is how a gate gets switched off.
        section_quotes = [q for _, m, ex in blocks if "R7" not in ex for q in quoted_strings(m)]
        has_sourced_quote = any(norm(q) in sources.haystack for q in section_quotes)
        unexempt_blocks = [b for b in blocks if "R7" not in b[2]]
        if unexempt_blocks and not has_sourced_quote and not has_operator_mark:
            findings.append(Finding(
                "R7", f"referrals.md · {person}",
                "No sourced quotation and no OPERATOR-VERIFY line. Every message to a real "
                "person asserts something about them. Prove it from sources/, or name what "
                "you must check yourself. Silence is not evidence."))

    # R8: the pre-send research gate. Fires only when the dossier actually carries
    # sendable copy: a dossier with nothing to send has nothing to research-gate.
    if sendable_blocks(folder):
        psc = folder / "pre-send-check.md"
        if not psc.exists():
            findings.append(Finding(
                "R8", str(folder),
                "pre-send-check.md is missing. Outbound copy exists, so the pre-send research "
                "audit must be completed and recorded before anything ships: "
                + ", ".join(k for k, _ in PRESEND_ITEMS) + "."))
        else:
            pt = psc.read_text(encoding="utf-8")
            if GRANDFATHER_MARK not in pt:
                for key, meaning in PRESEND_ITEMS:
                    if not re.search(r"\[x\]\s*" + key, pt, re.I):
                        findings.append(Finding(
                            "R8", "pre-send-check.md",
                            f"Mandatory item '{key}' is not checked [x]. It means: {meaning}. "
                            "Do the check for real, then mark it. Never mark without doing."))

    # R3/R5/R6/R10/R12: sweep ONLY what a real human will read. Documentation about a
    # correction is how the repo remembers; it must not trip the gate that prevents it.
    for where, block, exempt in sendable_blocks(folder):
        if "R10" not in exempt:
            check_link_claims(where, block, findings)
        nb = norm(block)
        if "R3" not in exempt:
            for entry in RETRACTED:
                if re.search(entry["pattern"], nb, re.I):
                    # A retracted claim inside a SENT LOG is the single most important
                    # thing this gate can find: it means it REACHED A REAL PERSON. Which
                    # is why SENT LOG cannot silence R3.
                    findings.append(Finding(
                        "R3", where,
                        f"Retracted claim reappeared. {entry['why']} Instead: {entry['instead']}",
                        block[:120]))
        if "R6" not in exempt:
            for n in RETRACTED_NUMBERS:
                if n.lower() in block.lower():
                    findings.append(Finding("R6", where, f"Retracted metric '{n}' is in copy a human will read."))
        if "R12" not in exempt:
            for fact in CORE_FACTS:
                for rx, label in fact["banned"]:
                    m = rx.search(block)
                    if m:
                        findings.append(Finding(
                            "R12", where,
                            f"Fabricated framing of a core fact ({label}). {fact['truth']}",
                            m.group(0)))
                        break  # one hit per fact is enough; don't stack near-duplicates
        if "R5" not in exempt:
            if "—" in block:
                findings.append(Finding("R5", where, "Em-dash in sendable copy."))
            for w in BANNED_WORDS:
                if w in nb:
                    findings.append(Finding("R5", where, f"Banned phrase '{w}'."))

    # R9: THE RÉSUMÉ ENTERS THE GATE.
    #
    # The résumé is the primary artifact an employer receives. A decision you locked
    # about it (drop a former employer, correct a title) that sits recorded only in a
    # knowledge base and never touches the actual résumé file is not a decision that
    # shipped. So: a small, exact blocklist of strings you have retired FROM THE
    # RÉSUMÉ. This reads resume.html (the PDF is built from it), not just the copy the
    # other rules sweep. Add a string here the moment you retire one.
    rhtml = folder / "resume" / "resume.html"

    # A MISSING SOURCE IS A FINDING, NOT SILENCE. Every résumé rule below used to hang
    # off `if rhtml.exists()`. Rename or delete that one file and R9, R9b, R10-on-the-
    # résumé and the cover-letter scan all disappear with no notice, while the report
    # still prints "checked: ... R9 resume retired". A gate that can be switched off by
    # a filename must at least say it was switched off.
    if not rhtml.exists():
        rdir = folder / "resume"
        if rdir.is_dir() and any(rdir.glob("*.pdf")):
            findings.append(Finding(
                "R9", "resume/",
                "this dossier holds a résumé PDF but has NO resume.html source, so the retired-claim "
                "and link-claim rules could not read it. Add the source (copy resume/resume.html and "
                "apply the tailoring delta): a résumé nothing can read is a résumé nothing is "
                "guarding."))

    if rhtml.exists():
        rt = rhtml.read_text(encoding="utf-8")
        for bad, why in RESUME_RETIRED.items():
            if bad.lower() in rt.lower():
                findings.append(Finding(
                    "R9", "resume/resume.html",
                    f"Retired-from-resume string present. {why} "
                    "This is the resume's background-check surface; the decision to remove it is "
                    "locked, so its presence is a defect, not a choice."))

        # R9b: THE FULL RETIRED REGISTRY, applied to the DOSSIER's résumé.
        #
        # RESUME_RETIRED above is a small, hand-maintained list. `canon.py` owns the
        # fuller retired-claims registry and the assertion-vs-prohibition logic, but a
        # knowledge-base-wide scan by design excludes the applications/ folder, so
        # nothing else reads a dossier's own résumé for a claim retired there. Between
        # them: canon has the knowledge and does not look at applications/; R9 looks and
        # does not have the knowledge. This closes that gap by importing canon's
        # registry and pointing it at the one surface it does not scan on its own.
        #
        # canon.py stays the single owner of the registry; this does not restate it,
        # it imports it.
        #
        # DEAD DOSSIERS ARE EXEMPT, VISIBLY. A rejected/passed/withdrawn dossier is
        # never sent to anyone again, and it stays read-only forever as a preserved
        # record of what WAS actually sent, often built before a claim was retired.
        # Rewriting it would destroy the record; leaving it permanently red would train
        # the next agent to scroll past this gate, which is the "warning nobody reads"
        # failure this whole gate exists to avoid.
        #
        # The exemption is narrow and cannot be self-granted: it reads
        # pipeline/tracker.html, which only your real outcomes update. A live dossier
        # can never reach this branch.
        #
        # R10 on the résumé, through the same surface R9 reads. The unit is one <li>
        # (a selected-projects entry or an experience bullet): its visible text plus
        # its href URLs, tags stripped. This is exactly the surface where a career-true
        # claim next to the wrong link is most likely to ship, because a résumé bullet
        # is dense and rarely re-read line by line once it is set.
        lre = get_link_re()
        for li in re.findall(r"<li\b[^>]*>(.*?)</li>", rt, flags=re.S | re.I):
            entry = re.sub(r"<[^>]+>", " ", li) + " " + " ".join(re.findall(r'href="([^"]+)"', li))
            if lre and lre.search(entry):
                check_link_claims("resume/resume.html · a linked entry", entry,
                                  findings, entry_scope=True)

    dead = _dossier_status_if_dead(folder)
    if dead:
        _HISTORY_SKIPPED.append(
            f"the retired-claim registry on {folder.name}/resume/resume.html: that dossier is "
            f"'{dead}' per pipeline/tracker.html, so its résumé is a read-only record of what was "
            f"sent, not a sendable artifact")
    else:
        # The résumé AND the cover letter. Both are artifacts an employer receives, and
        # the same hole covers both; scanning only the résumé would leave exactly half
        # the outbound surface unguarded.
        targets = ([("resume/resume.html", rt)] if rhtml.exists() else [])
        for cl in sorted((folder / "cover-letter").glob("*")):
            if cl.suffix.lower() in (".md", ".html"):
                try:
                    targets.append((f"cover-letter/{cl.name}", cl.read_text(encoding="utf-8")))
                except OSError:
                    pass
        # AND THE RENDERED PDFs: the files an employer actually receives. Scanning
        # only the HTML source assumes the PDF was rebuilt from it, which is exactly
        # the assumption that leaves a stale, already-corrected PDF unguarded.
        for sub in ("resume", "cover-letter"):
            for doc in sorted((folder / sub).glob("*.pdf")):
                try:
                    import fitz as _fitz
                    targets.append((f"{sub}/{doc.name}",
                                    "\n".join(pg.get_text() for pg in _fitz.open(doc))))
                except Exception:
                    pass
        try:
            import canon as _canon
            for where, body in targets:
                for cf in _canon.scan_text(f"{folder.name}/{where}", body):
                    findings.append(Finding(
                        "R9", where,
                        f"Retired claim [{cf.rule_id}] asserted on this dossier's outbound copy. "
                        f"{cf.why} Instead: {cf.instead}",
                        cf.text.strip()[:180]))
        except Exception as e:
            # A broken import must never silently soften the gate; say so loudly instead.
            findings.append(Finding(
                "R9", "resume/resume.html",
                f"could not load canon.py's retired-claim registry ({e}), so this résumé and "
                f"cover letter were NOT checked against it. Fix the import before trusting "
                f"this PASS."))


    # R11: the card rule, reconciled against the artifacts rather than trusted as prose.
    check_card_rule(folder, findings)

    return findings


# ────────────────────────────────────────────────────────────────────────────────────
# THE SELF-TEST.
#
# A test that only proves the happy path proves nothing. Each case below asserts a rule
# CATCHES the exact shape of mistake it exists to catch, using synthetic, fully
# fictional content (see applications/EXAMPLE-fixture-selftest/) so this runs clean on a
# fresh clone with no real user data.
#
# THE REGISTRIES ABOVE SHIP EMPTY (RETRACTED, CORE_FACTS, RETRACTED_NUMBERS,
# RESUME_RETIRED, CARD_SIGNATURES): that is the correct state for a fresh clone with no
# real corrections recorded yet. But an empty registry has nothing for R3/R6/R9/R11/R12
# to catch, so the selftest SEEDS them with a few invented, clearly-fictional entries
# before running its cases (see _seed_fixture_registries() below), proving the
# MECHANISM works without needing real content. This mutation is process-local and
# `selftest()` is terminal, and nothing else runs in this process afterward, so it never
# leaks into a real dossier check.
# ────────────────────────────────────────────────────────────────────────────────────

SELFTEST_CASES = [
    ("R3", "a corrected claim reappearing, verbatim",
     '> Hi Jordan, your talk stuck with me, especially since you solved onboarding overnight for that client.'),
    ("R1", "an invented quotation with no stored source",
     '> Hi Jordan, you told them "velocity is the only moat that compounds" and I agree.'),
    ("R2", "attribution with no quote and no operator flag",
     '> Hi Sam, you lead the whole design org and I admire how you run it.'),
    ("R5", "performed emotion",
     '> Hi Jordan, I am so excited to apply and passionate about design systems.'),
    # Guards the hole the internal-record exemption could open: a SENT LOG in the same
    # section must NOT make the real outbound copy invisible.
    ("R1", "poison hiding BEHIND a SENT LOG block in the same section",
     '> **SENT LOG (2024-01-02):** Sent the note; profile reads "founding designer @somewhere".\n'
     '\n'
     '> Hi Jordan, you told them "velocity is the only moat that compounds" and I agree.'),
    # R4 fires only on the exact label `**Connection note**` unless it is also taught
    # the alternate house format some drafts use; the poison below is 300+ chars in
    # that second format.
    ("R4", "an over-length note written in the `#N Connection note (N chars):` format",
     '**#1 Connection note (999 chars):**\n'
     '> Hi Jordan, ' + ('this note runs deliberately past the three hundred character cap '
                       'LinkedIn enforces on connection requests, and it must be caught no '
                       'matter which house label format it happens to carry. ') * 2 + 'Thanks'),
    # Every claim below is worded to be individually plausible; the RED trigger is the
    # never-claim-here terms sitting in the SAME block as the link, exactly the kind of
    # proximity laundering that reads fine sentence-by-sentence.
    ("R10", "career-plausible claims on a link that carries never-claim-here terms",
     '> Closest thing I have is a design system where I was the sole engineer and solo '
     'founder end to end, at example.com/example-case-study'),
    # A single work-claim noun near the link, absent from that slug's shows: list,
    # the AMBER path, distinct from the RED never-claim-here path above.
    ("R10", "a work-claim noun near the link that the manifest does not support",
     '> I have spent the last year on an internal dashboard for admins; the case study '
     'is at example.com/example-case-study'),
    # A retired overclaim resurfacing in a different wording than the first R3 case,
    # guarding that the registry catches a phrase, not just one exact sentence.
    ("R3", "the same retired overclaim in a different wording",
     '> the review record is the real artifact, and a bot that auto-fixes on every save '
     'so nobody has to check it by hand.'),

    # ── ATTRIBUTION-OWNERSHIP CASES. Each one exited 0 before ownership was checked. ──
    #
    # HOLE 1. The quotation is real, stored, and verbatim: it is the JOB POSTING'S OWN
    # BOILERPLATE, put in the recipient's mouth in a note addressed to them. The old
    # flat haystack asked only "do these words exist somewhere in this dossier?", so it
    # said yes. A posting is the COMPANY's words, never a person's.
    ("R1", "a quote attributed to a PERSON that is really the job posting's boilerplate",
     '> Hi Jordan, you said "thinks like a builder, ships like an engineer, and treats '
     'feedback as fuel" when we spoke.'),
    # HOLE 2. The retracted claim, four characters away from invisible. Prefixing a
    # block `SENT LOG:` used to delete it from EVERY rule; now the label may excuse the
    # evidence rules and the copy rules, never the truth alarms, and a retracted claim
    # inside a SENT LOG is the worst news the gate can carry, because it means it
    # REACHED A REAL PERSON.
    ("R3", "a retracted claim hiding behind a `SENT LOG:` prefix (the block-wide kill switch, narrowed)",
     '> **SENT LOG (2024-01-02):** Hi Jordan, your talk stuck with me, especially since '
     'you solved onboarding overnight for that client.'),
    # HOLE 2, the other marker: an `OPERATOR-VERIFY:` line appended to real outbound
    # copy is an annotation about EVIDENCE. It never licensed a fabrication, and now it
    # cannot silence one.
    ("R3", "a retracted claim with an inline `OPERATOR-VERIFY:` appended",
     '> Hi Jordan, your talk stuck with me, especially since you solved onboarding '
     'overnight for that client. OPERATOR-VERIFY: check this.'),
    # HOLE 2, the metric alarm: a purged number behind the same prefix. R6 stays live
    # on a record for the same reason R3 does.
    ("R6", "a purged metric hiding behind a `SENT LOG:` prefix",
     '> **SENT LOG (2024-01-02):** Hi Jordan, the redesign lifted conversion 300% and '
     'cut support tickets 150%.'),
    # R6 in ordinary outbound copy.
    ("R6", "a retracted metric in an ordinary connection note",
     '> Hi Jordan, at Globex I shipped a console that moved adoption 450% in a quarter.'),
    # R12: a false framing of your OWN employer, anchored to it by name, mirroring the
    # exact shape a corrected framing takes: true individual words, false as a whole.
    ("R12", "your own past employer mischaracterized as a developer-tools company",
     '> At Globex I was the design lead at a developer-tools company that felt like a '
     'terminal for engineers, so I already speak your language.'),
]


# ────────────────────────────────────────────────────────────────────────────────────
# THE HARNESS, AND WHY IT COUNTS RULES INSTEAD OF CASES.
#
# A green selftest that only counts `passed == total` proves nothing about coverage:
# neuter a rule, delete its case, and both sides of that equation shrink together. So
# the run derives its denominator from the cases it actually ran, holds a hard floor
# under that count so cases cannot be quietly deleted, and REFUSES to pass unless every
# rule id this module can emit was fired and asserted by at least one POSITIVE case.
# Negative cases prove a rule stays quiet; only a positive case proves it still has
# teeth, so only positives count toward coverage.
# ────────────────────────────────────────────────────────────────────────────────────

# Ratchet. Raise it when you add cases; never lower it to make a run pass: that is the
# denominator-shrinking this whole section exists to make impossible.
MIN_SELFTEST_CASES = 33


def implemented_rules() -> set[str]:
    """Every rule id this module can actually EMIT, read from the code, not a list.

    Union of (a) every `Finding("Rn", ...)` construction in this file and (b) the rule
    registry in the module docstring. Reading the source is what makes a NEW rule
    arrive already-uncovered and therefore already-failing, instead of arriving silent.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    ids = set(re.findall(r'Finding\(\s*"(R\d+)"', src))
    ids |= set(re.findall(r"^\s{2}(R\d+)\s", __doc__ or "", re.M))
    return ids


class _Harness:
    """Collects every case result and the set of rules a POSITIVE case actually fired."""

    def __init__(self) -> None:
        self.rows: list[bool] = []
        self.covered: set[str] = set()

    def expect(self, rule: str, name: str, findings: list, note: str = "") -> bool:
        """POSITIVE: `rule` MUST fire. The only thing that counts toward coverage."""
        caught = any(f.rule == rule for f in findings)
        self.rows.append(caught)
        if caught:
            self.covered.add(rule)
        print(f"  {'PASS' if caught else 'FAIL'}  [{rule}] {name}")
        if not caught:
            print(f"        NOT CAUGHT. The gate is broken. {note}")
        return caught

    def refuse(self, rule: str, name: str, findings: list) -> bool:
        """NEGATIVE: `rule` must stay QUIET. A gate that cries wolf gets switched off."""
        hits = [f for f in findings if f.rule == rule]
        ok = not hits
        self.rows.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  [{rule}-neg] {name}")
        if hits:
            print(f"        FALSE POSITIVE: {hits[0].detail[:110]}")
        return ok

    def assert_true(self, name: str, ok: bool, why: str = "") -> bool:
        self.rows.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok and why:
            print(f"        {why}")
        return ok

    @property
    def passed(self) -> int:
        return sum(self.rows)

    @property
    def total(self) -> int:
        return len(self.rows)


def _seed_fixture_registries() -> None:
    """Populate the empty-by-default registries with invented, clearly-fictional
    content, so the selftest can prove R3/R6/R9/R11/R12 catch what they exist to catch
    without needing any real user data. Every string here is fictional and matches
    nothing in applications/EXAMPLE-fixture-selftest/'s baseline content.
    """
    RETRACTED.extend([
        {"pattern": r"solved onboarding overnight",
         "why": "TEST FIXTURE: nobody said this; an earlier draft invented it as a compliment.",
         "instead": "Quote only what is verifiably sourced."},
        {"pattern": r"auto-fixes on every save",
         "why": "TEST FIXTURE: overclaims automated enforcement that does not exist.",
         "instead": "Say the checks run when invoked, not that they run automatically."},
    ])
    RETRACTED_NUMBERS.extend(["300%", "450%"])
    RESUME_RETIRED.update({
        "Ferrovia Labs": "TEST FIXTURE: never a real employer; retired from the résumé.",
        "Assistant Product Designer": "TEST FIXTURE: retired title; the real title was Product Designer.",
    })
    CORE_FACTS.extend([
        {
            "id": "example-employer-true-nature",
            "truth": "TEST FIXTURE: Globex is a seed-stage veterinary-software startup, not a "
                     "developer-tools company. Mirrors the real registry's shape and anchoring "
                     "discipline; replace with your own facts once you have a framing worth "
                     "guarding.",
            "banned": [
                (re.compile(r"\bglobex\b[^.\n]{0,80}\bdeveloper[- ]?tools?\b", re.I), "Globex called developer tools"),
                (re.compile(r"\bglobex\b[^.\n]{0,80}\bterminal\b", re.I), "Globex called a terminal"),
            ],
        },
    ])
    CARD_SIGNATURES.update({
        "mentor-program": (r"mentored\s+\d+\s+junior\s+designers", r"mentor"),
        "platform-migration": (r"migrated\s+the\s+platform\s+to\s+a\s+new\s+stack",
                               r"platform[-\s]migration|migrated the platform"),
    })
    import canon as _canon_seed
    _canon_seed.RETIRED.append({
        "id": "example-retired-claim",
        "pattern": r"runs itself with zero maintenance",
        "why": "TEST FIXTURE: overclaims full automation with no human review; nothing in this "
               "fixture runs itself with zero maintenance.",
        "instead": "Say what actually still requires a human step.",
    })


def _poisoned(real: Path, tmp: Path, poison: str) -> Path:
    """Copy the fixture and inject `poison` as the first person's connection note."""
    import shutil
    shutil.copytree(real, tmp)
    ref = tmp / "referrals.md"
    t = ref.read_text(encoding="utf-8")
    t = t.replace("**Connection note**\n> Hi Jordan,",
                  f"**Connection note**\n{poison}\n\n**Connection note (real)**\n> Hi Jordan,", 1)
    ref.write_text(t, encoding="utf-8")
    return tmp


def _selftest_r11(h: _Harness) -> None:
    """R11: the card-rule failure, both directions, as permanent cases."""
    import tempfile, shutil
    base = Path(__file__).resolve().parents[1] / "applications" / "EXAMPLE-fixture-selftest"
    if not base.exists():
        # No silent skip. The MIN_SELFTEST_CASES floor turns a vanished fixture into a
        # loud failure, exactly as a vanished referrals.md already is.
        print("  ⚠ R11 cases SKIPPED (fixture dossier absent): the case floor will fail this run")
        return
    cases = [
        ("a card declared OUT while the cover letter still carries it",
         "**Cards OUT:** the mentor-program card (no longer part of the pitch)\n\n",
         "mentor-program"),
        ("a card declared IN that appears in NO outbound artifact",
         None, "platform-migration"),
    ]
    for name, out_line, card in cases:
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "fixture"
            shutil.copytree(base, dst)
            tf = dst / "resume" / "tailoring.md"
            s = tf.read_text(encoding="utf-8")
            # Set BOTH segments, so each case tests exactly one direction unambiguously.
            if out_line is not None:
                s = re.sub(r"\*\*Cards IN:\*\*.*?(?=\n\*\*|\n## |\Z)",
                           "**Cards IN:** the design-system-and-code card\n\n", s, flags=re.S)
                s = re.sub(r"\*\*Cards OUT:\*\*.*?(?=\n\*\*|\n## |\Z)", out_line, s, flags=re.S)
            else:
                s = re.sub(r"\*\*Cards IN:\*\*.*?(?=\n\*\*|\n## |\Z)",
                           "**Cards IN:** the platform-migration card\n\n", s, flags=re.S)
                s = re.sub(r"\*\*Cards OUT:\*\*.*?(?=\n\*\*|\n## |\Z)",
                           "**Cards OUT:** nothing declared out for this fixture\n\n", s, flags=re.S)
            tf.write_text(s, encoding="utf-8")
            hits = [f for f in check_dossier(dst) if f.rule == "R11" and card in f.detail]
            h.rows.append(bool(hits))
            if hits:
                h.covered.add("R11")
            print(f"  {'PASS' if hits else 'FAIL'}  [R11] {name}")


def selftest() -> int:
    import shutil, tempfile
    root = Path(__file__).resolve().parents[1]
    # The fixture must be a CLEAN, LIVE dossier: every rule below is tested by poisoning
    # it, so a baseline that is already dirty makes the whole selftest unreadable. It is
    # fully synthetic (see applications/EXAMPLE-fixture-selftest/), so this runs clean
    # on a fresh clone with no real user data.
    real = root / "applications/EXAMPLE-fixture-selftest"
    if not real.is_dir():
        # Exit 1, not 0. A vanished fixture must never read as a passing gate: any CI
        # or agent checking only the exit code would take "skipped" for "green" and ship.
        print("SELFTEST CANNOT RUN: the fixture dossier is not on disk.")
        print("The gate is UNVERIFIED. Restore applications/EXAMPLE-fixture-selftest/ before trusting it.")
        return 1

    _seed_fixture_registries()

    print("SELFTEST: the gate must CATCH each shape of mistake it exists to prevent.\n")
    h = _Harness()
    for rule, name, poison in SELFTEST_CASES:
        with tempfile.TemporaryDirectory() as td:
            found = check_dossier(_poisoned(real, Path(td) / "dossier", poison))
            h.expect(rule, name, found, f"Poison: {poison[:80]}")

    # R8: structural, so its poison is a deletion, not an injection: remove the
    # pre-send research audit and the gate must refuse to let the outbound copy ship.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        (tmp / "pre-send-check.md").unlink(missing_ok=True)
        h.expect("R8", "outbound copy with no pre-send research audit",
                 check_dossier(tmp))

    # R9: the résumé enters the gate. Inject a retired employer string into a copy of
    # the fixture's resume.html and assert R9 fires. This is the guard that would catch
    # a retired employer name shipping logged-but-unexecuted.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        rdir = tmp / "resume"; rdir.mkdir(exist_ok=True)
        (rdir / "resume.html").write_text(
            '<div class="job-title"><span class="co">Ferrovia Labs</span> · UI/UX Designer</div>',
            encoding="utf-8")
        h.expect("R9", "a retired-from-resume employer in resume.html",
                 check_dossier(tmp), "The resume is outside the gate again.")

    # R0: STRUCTURAL. Delete referrals.md: every application needs one, and every rule
    # underneath it reads that file, so the run must also RECORD that they never ran
    # (that is what keeps the `checked:` banner from claiming coverage it does not
    # have: the gate lying about itself).
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        (tmp / "referrals.md").unlink(missing_ok=True)
        h.expect("R0", "a dossier with no referrals.md at all",
                 check_dossier(tmp))
        h.assert_true("[R0] the rules that could not run are RECORDED, not claimed as checked",
                      set(_RULES_SKIPPED) >= {"R1", "R2", "R7"},
                      f"_RULES_SKIPPED was {_RULES_SKIPPED!r}; the banner would claim coverage it lacks.")

    # R7: DEFAULT DENY. A person section carrying a message but no sourced quotation
    # and no OPERATOR-VERIFY line must be refused: you only cold-message someone
    # because you claim to know something about them.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        ref = tmp / "referrals.md"
        t = ref.read_text(encoding="utf-8").replace(
            "## The messages",
            "## The messages\n\n### Casey Nolan, Staff Designer\n\n"
            "> Hi Casey, I applied to the Design Lead role and would value your read on it.\n", 1)
        ref.write_text(t, encoding="utf-8")
        h.expect("R7", "a person section with a message, no sourced quote and no OPERATOR-VERIFY",
                 check_dossier(tmp))

    # A NEGATIVE case: the gate must NOT fire. A DM label routinely explains its
    # InMail verdict by naming the free alternative ("...free connection note is
    # available"), so a loose connection-note pattern would happily claim the DM's
    # body and then R4 would cap a legitimately long DM at 300 characters. A false
    # positive is not a harmless gate: it teaches the next agent that a red gate means
    # "trim the message", and real copy gets mangled to satisfy a rule that never
    # applied.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        ref = tmp / "referrals.md"
        t = ref.read_text(encoding="utf-8")
        long_dm = "> Hi Jordan, " + ("a long but perfectly legitimate direct message. " * 12) + "Thanks"
        t = t.replace("**Connection note**\n> Hi Jordan,",
                      "**First DM (Use InMail: NO - a free connection note is available)**\n"
                      f"{long_dm}\n\n**Connection note**\n> Hi Jordan,", 1)
        ref.write_text(t, encoding="utf-8")
        h.refuse("R4", "a long DM whose label mentions 'connection note' is NOT capped",
                 check_dossier(tmp))

    # ── THE THREE NEGATIVES THAT KEEP THE OWNERSHIP HARDENING HONEST. ─────────────
    # Each guards a false positive that a naive tightening would introduce. A noisy
    # gate gets disabled, and a disabled gate catches nothing at all.
    ownership_negatives = [
        # 1. Quoting the POSTING, attributed to the posting. The posting is the RIGHT
        #    source for it, so R1 must stay quiet: this is the line between the
        #    ownership check and cargo-culting it.
        ("R1", "a posting quote openly attributed to the job posting is NOT flagged",
         '> Hi Jordan, Acme\'s posting says "thinks like a builder, ships like an engineer, and '
         'treats feedback as fuel" and that is how I already work.'),
        # 2. A real quotation from the person's OWN stored source, attributed to them.
        #    This proves source_belongs_to actually resolves an owner rather than the
        #    ownership check being vacuously strict.
        ("R1", "a verbatim quote from the person's OWN stored source is NOT flagged",
         '> Hi Jordan, you said "Loved your talk on design systems" and that means a lot '
         'coming from you.'),
        # 3. An em-dash inside a SENT LOG record. A record is a note to you, not copy
        #    for a recipient, so the voice rules do not apply to it. Collapsing that
        #    distinction puts real dossiers red during a build for no honesty reason.
        ("R5", "an em-dash inside a SENT LOG record is NOT flagged as sendable copy",
         '> **SENT LOG (2024-01-02):** Sent the note — invite pending, no InMail spent.'),
    ]
    for rule, name, good in ownership_negatives:
        with tempfile.TemporaryDirectory() as td:
            h.refuse(rule, name, check_dossier(_poisoned(real, Path(td) / "dossier", good)))

    # ── R12 NEGATIVES: the anchor is the whole point, so it is tested from both sides. ──
    # A blanket ban on "developer tools" would red every honest dossier applying to an
    # actual developer-tools company, get switched off, and catch nothing. These prove
    # R12 fires ONLY on your own employer/domain, never on a TRUE statement about a
    # target or the corrected copy.
    core_facts_negatives = [
        # 1. A TARGET truthfully called developer tools. The note describes THEM,
        #    mentions no Globex, and must sail through.
        ("R12", "a target company truthfully called a developer-tools product is NOT flagged",
         '> Hi Jordan, Acme Corp\'s own product is exactly the kind of developer-tools platform '
         'I want to design for.'),
        # 2. The CORRECTED framing. "Globex" is present, but next to its grounded
        #    descriptor, not "terminal" or "developer tools": this is what the fix
        #    writes, so it must pass or the gate would block its own remedy.
        ("R12", "the corrected 'Globex, a seed-stage veterinary-software startup' framing is NOT flagged",
         '> At Globex, a seed-stage veterinary-software startup, I was the design lead: I built the '
         'design system in code and shipped my own front end.'),
    ]
    for rule, name, good in core_facts_negatives:
        with tempfile.TemporaryDirectory() as td:
            h.refuse(rule, name, check_dossier(_poisoned(real, Path(td) / "dossier", good)))

    # A FOURTH ownership negative, guarding the acceptance path the baseline fixture
    # does not exercise on its own, which is exactly why it would rot unnoticed. A
    # SHARED source (a team page, a multi-quote article) is named after the COMPANY,
    # so neither the filename nor the header names the person; ownership has to
    # resolve through their name sitting beside the quotation INSIDE the file. If that
    # path ever breaks, the first symptom is a false positive on honest outbound copy,
    # and by then the gate is already being ignored. The padding is deliberate: it
    # pushes the name past the HEADER_CHARS window so this really tests the
    # neighbourhood path and not the header.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossier"
        shutil.copytree(real, tmp)
        pad = "Filler about the company, its history and its offices. " * 60
        (tmp / "sources").mkdir(exist_ok=True)
        (tmp / "sources" / "company-team-page.md").write_text(
            "---\nurl: https://example.com/team\nfetched: 2024-01-02\n---\n\n" + pad +
            "\n\nAda Whitfield, Staff Design Engineer, on how the team works: "
            '"we ship the front end ourselves and hold the bar in code".\n',
            encoding="utf-8")
        ref = tmp / "referrals.md"
        t = ref.read_text(encoding="utf-8").replace(
            "## The messages",
            "## The messages\n\n### Ada Whitfield, Staff Design Engineer\n\n"
            '> Hi Ada, you said "we ship the front end ourselves and hold the bar in code" '
            "and that is how I work too.\n", 1)
        ref.write_text(t, encoding="utf-8")
        h.refuse("R1", "a quote from a SHARED source resolves by the person's name beside "
                       "it IN the file (not the filename, not the header)",
                 check_dossier(tmp))

    # HOLE 2, second half: a gate that turns itself off must SAY SO. Assert the
    # annotation-silenced blocks are named and counted on the NOT-checked line, not
    # merely handled internally; an unreported suppression is the same failure in a
    # quieter coat, because the PASS is what gets trusted.
    with tempfile.TemporaryDirectory() as td:
        tmp = _poisoned(real, Path(td) / "dossier",
                        '> **SENT LOG (2024-01-02):** Sent it; his profile reads '
                        '"founding designer at somewhere".')
        import io, contextlib
        buf, argv = io.StringIO(), sys.argv
        sys.argv = ["verify_claims.py", str(tmp)]
        try:
            with contextlib.redirect_stdout(buf):
                main()
        finally:
            sys.argv = argv
        out = buf.getvalue()
        reported = "NOT checked:" in out and "🔇" in out and "SENT LOG" in out and "silences" in out
        h.assert_true("[report] every annotation-silenced block is named + counted in NOT-checked",
                      reported, "The gate silenced a block without saying so. That is the worse failure: "
                                "an unreported suppression makes the PASS a lie.\n"
                                f"        NOT-checked line was: {out[out.find('NOT checked:'):][:200]!r}")

    # ── R9b: the retired-claim registry on a DOSSIER's résumé ─────────────────────────────
    # Three properties, because the exemption for dead dossiers is a suppression vector and must
    # be proven not to leak.
    with tempfile.TemporaryDirectory() as td:
        import shutil
        live = Path(td) / "live-dossier"
        shutil.copytree(real, live)
        rh = live / "resume" / "resume.html"
        if rh.exists():
            base = rh.read_text(encoding="utf-8")
            # (a) a retired claim on a LIVE dossier's résumé must FAIL
            rh.write_text(base.replace("</body>", "<p>This tool runs itself with zero maintenance.</p></body>", 1)
                          if "</body>" in base else base + "\n<p>This tool runs itself with zero maintenance.</p>",
                          encoding="utf-8")
            hits = [f for f in check_dossier(live) if f.rule == "R9" and "zero maintenance" in f.detail]
            h.assert_true("[R9b] a retired claim on a LIVE dossier's résumé is CAUGHT",
                          bool(hits),
                          "canon.py's registry is not reaching dossier résumés. This is exactly the "
                          "hole that would let a corrected overclaim sit on a SUBMITTED résumé at exit 0.")
            # (b) a dossier the tracker calls dead is exempt AND the exemption is NAMED.
            #     Run the gate on a real dead dossier, then read what it recorded. Choose one
            #     from the tracker rather than hardcoding, so a status change cannot rot this.
            dead_dir = next((d for d in sorted((root / "applications").iterdir())
                             if d.is_dir() and (d / "resume" / "resume.html").exists()
                             and _dossier_status_if_dead(d)), None)
            if dead_dir is None:
                h.assert_true("[R9b] the dead-dossier exemption is NAMED, never silent", True)
            else:
                check_dossier(dead_dir)          # populates _HISTORY_SKIPPED for THAT dossier
                h.assert_true("[R9b] the dead-dossier exemption is NAMED, never silent",
                              any("retired-claim registry" in s for s in _HISTORY_SKIPPED),
                              f"{dead_dir.name} was exempted without the note. An unreported "
                              "suppression makes the PASS unsizeable.")
            # (c) the exemption must NOT be self-grantable: a temp copy has no tracker row,
            #     so it is treated as LIVE. If this ever flips, any dossier could dodge R9b.
            h.assert_true("[R9b] a dossier with no tracker row is treated as LIVE, not dead",
                          _dossier_status_if_dead(live) is None,
                          "An unknown dossier was treated as dead. The exemption must fail CLOSED.")
            # (d) DELETING resume.html must not silently disable the résumé + cover-letter rules.
            #     Renaming one file must not turn R9, R9b, R10-on-the-résumé and the cover-letter
            #     scan off while the report still claims to have checked them.
            rh.write_text(base, encoding="utf-8")
            (live / "resume" / "resume.html").unlink()
            h.assert_true("[R9b] a résumé PDF with NO resume.html source is a FINDING, not silence",
                          any(f.rule == "R9" and "NO resume.html" in f.detail
                              for f in check_dossier(live)),
                          "The gate went quiet when its input file vanished. A rule that can be "
                          "switched off by a filename must say it was switched off.")
            # (e) the RENDERED PDF is scanned, not just the HTML. The PDF is the uploaded file.
            try:
                import fitz as _fz
                for _p in (live / "resume").glob("*.pdf"):
                    _p.unlink()
                _d = _fz.open(); _pg = _d.new_page(width=595, height=842)
                _pg.insert_text((50, 80), "This tool runs itself with zero maintenance.", fontsize=10)
                _d.save(str(live / "resume" / "only.pdf"))
                h.assert_true("[R9b] a retired claim in the rendered PDF alone is CAUGHT",
                              any(f.rule == "R9" and "zero maintenance" in f.detail
                                  for f in check_dossier(live)),
                              "Only the HTML was read, not the rendered artifact the employer "
                              "actually receives.")
            except ImportError:
                pass

    # TWO R10 NEGATIVE cases: the gate must NOT fire on the true claim+link pairs.
    # A false positive here teaches the next agent that a red R10 means "strip the
    # claim", and honest copy gets mangled to satisfy a rule that never applied.
    r10_negatives = [
        # The claim matches the manifest's own shows: list, so R10 must stay quiet.
        ("a claim matching the manifest's shows: list is NOT flagged",
         '> Hi Jordan, closest thing I have is a design system with real shared tokens '
         'behind it, at example.com/example-case-study'),
        # A second true claim+link pair, phrased differently, to prove the negative
        # is not an accident of one specific sentence shape.
        ("a second true claim+link pair, differently phrased, is NOT flagged",
         '> Hi Sam, my closest work is a design system I built, tokens and all, with '
         'the case study at example.com/example-case-study'),
    ]
    for name, good in r10_negatives:
        with tempfile.TemporaryDirectory() as td:
            h.refuse("R10", name, check_dossier(_poisoned(real, Path(td) / "dossier", good)))

    # And the real dossier, unpoisoned, must be clean.
    live = check_dossier(real)
    clean = len(live) == 0
    h.assert_true("[live] the real dossier is clean", clean)
    if not clean:
        for f in live:
            print(f); print()
    _selftest_r11(h)

    # ── THE TWO ASSERTIONS THAT MAKE A GREEN RUN MEAN SOMETHING. ───────────────────
    # A count alone proves nothing: neuter a rule, delete its case, and `passed ==
    # total` still holds. So the run is also refused when a rule this module can EMIT
    # was never fired by a positive case, and when the case count drops below its
    # ratchet. Both name what is missing, loudly, rather than printing OK.
    uncovered = sorted(implemented_rules() - h.covered,
                       key=lambda r: int(r[1:]))
    covered_ok = not uncovered
    if not covered_ok:
        print("\n  🔴 RULE COVERAGE FAILURE: these rules are IMPLEMENTED but NO positive")
        print("     selftest case fires them, so nothing here proves they still work:")
        for r in uncovered:
            print(f"       · {r}: add a case to SELFTEST_CASES (or a structural case) that MUST trip {r}")
        print("     A rule with no case is a rule that can be neutered silently.")
    floor_ok = h.total >= MIN_SELFTEST_CASES
    if not floor_ok:
        print(f"\n  🔴 CASE FLOOR FAILURE: {h.total} cases ran, but MIN_SELFTEST_CASES is "
              f"{MIN_SELFTEST_CASES}.")
        print("     Cases were deleted, or a fixture dossier vanished. Never lower the floor")
        print("     to make a run pass: shrinking the denominator is the exact failure this")
        print("     assertion exists to prevent. Restore the case or the fixture.")

    ok = h.passed == h.total and clean and covered_ok and floor_ok
    print(f"\n{'SELFTEST OK' if ok else 'SELFTEST FAILED'}: {h.passed}/{h.total} cases, "
          f"{len(h.covered)}/{len(implemented_rules())} rules exercised by a positive case, "
          f"live dossier {'clean' if clean else 'DIRTY'}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if len(sys.argv) < 2:
        print(__doc__); return 2

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Not a directory: {folder}"); return 2

    findings = check_dossier(folder)
    suppressed = list(_SUPPRESSED)          # snapshot: check_dossier clears it on entry
    srcs = load_sources(folder).names

    print(f"verify_claims: {folder.name}")
    print(f"  sources on disk: {len(srcs)} ({', '.join(srcs) if srcs else 'NONE'})\n")

    # The verdict travels with its scope. "Gate-green" must never be read as
    # "send-ready" on its own: the gate's blind spots must ride on the same line as its
    # verdict, derived from the rule registry in this file's own docstring so the list
    # cannot silently rot apart from the rules.
    rules = re.findall(r"^\s{2}(R\d+)\s+([A-Z-]+(?: [A-Z-]+)*?)(?=\s{2}|\s[^A-Z])", __doc__ or "", re.M)
    # Subtract the rules that were structurally PREVENTED from running. Listing a rule as
    # "checked" when R0 short-circuited before it is the gate lying about its own coverage:
    # the same defect the NOT-checked line exists to prevent, committed by the NOT-checked line.
    skipped = set(_RULES_SKIPPED)
    checked = ", ".join(f"{rid} {label.strip().lower()}" for rid, label in rules
                        if rid not in skipped)
    # A dead dossier's résumé is exempted from the retired-claim registry. That exemption is
    # NAMED here rather than being silent, for the same reason the annotation suppressions
    # below are: a gate that turns part of itself off without saying so produces a PASS
    # nobody can size.
    hist = ("📕 " + " · ".join(_HISTORY_SKIPPED) + " · ") if _HISTORY_SKIPPED else ""
    not_checked = (hist + "unlinked semantic drift (a human review pass only) · quotations "
                   "inside cover-note.md vs sources (a documented R1/R2 hole) · live-site drift "
                   "(the manifest reads the in-repo deployed sources) · anything edited or "
                   "sent after this run")
    # Every block an annotation silenced, NAMED and COUNTED. A gate that turns itself
    # off without saying so is worse than no gate, because the PASS is trusted.
    if suppressed:
        def _short(w: str) -> str:
            """`referrals.md · <person> · <kind>`, trimmed to stay readable.

            The person heading contains ` · ` itself, so the file is the FIRST field and
            the kind is the LAST; everything between is the person. Naming the wrong
            field here would defeat the whole point: a NOT-checked line nobody can act on
            protects nobody.
            """
            parts = [p.strip() for p in w.split(" · ")]
            if len(parts) < 3:
                return w[:70]
            who = " · ".join(parts[1:-1])
            who = re.sub(r"^\s*\d+\s*[.)·\-–—]\s*", "", who)     # drop the ordinal
            who = re.split(r"[—–(;\"]", who)[0].strip()[:34]      # drop the title tail
            return f"{parts[0]} · {who or parts[1]} · {parts[-1]}"
        detail = " ; ".join(f"{_short(w)} [{m} silences {'+'.join(r)}]"
                            for w, m, r in suppressed[:6])
        if len(suppressed) > 6:
            detail += f" ; …and {len(suppressed) - 6} more"
        not_checked = (f"🔇 {len(suppressed)} block(s) partially silenced by an annotation: "
                       f"{detail}. Every OTHER rule still ran on them, including R3/R6/R10, "
                       f"the truth alarms. Read those blocks yourself for what their "
                       f"annotation covers. · " + not_checked)
    if skipped:
        skipped_labels = ", ".join(f"{rid} {label.strip().lower()}" for rid, label in rules
                                   if rid in skipped)
        not_checked = (f"🔴 {skipped_labels}: these NEVER RAN: R0 failed on structure and every "
                       f"rule below it reads the file that is missing. A green line above does not "
                       f"cover them. · " + not_checked)
    scope_line = f"  checked: {checked}\n  NOT checked: {not_checked}\n"

    if not findings:
        print("PASS. Every quotation traces to a stored source. Nothing unsourced is addressed to a real person.")
        print(scope_line)
        print("PASS is not send-ready by itself: the NOT-checked surfaces above are yours.")
        return 0

    print(f"FAIL: {len(findings)} finding(s). Nothing ships until these are zero.\n")
    print(scope_line)
    for f in findings:
        print(f); print()
    print("Fix by: quoting the person verbatim from a stored source, storing the source you")
    print("used, adding an `OPERATOR-VERIFY: <what you must confirm>` line to the section,")
    print("or deleting the sentence. Never by editing a source file.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
