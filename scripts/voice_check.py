#!/usr/bin/env python3
"""voice_check.py: the plain-voice gate.

Every piece of writing runs through this before it passes: outbound copy written as you (cover
notes, outreach, form free-text, portfolio, LinkedIn) and every reply written to you in chat. See
CLAUDE.md §11 (the plain-voice rule).

The target is PLAIN and NEUTRAL. AI-generated writing tends to fail from one of two directions:
over-selling (hype, superlatives, too-neat mirrors between you and the company, story shapes,
performed emotion, performed control) or, once corrected, over-apologizing (false modesty, naming
limitations/gaps, undercutting your own competence). This check flags both, register by register,
not just a list of banned words. It is MECHANICAL, so it is necessary-but-not-sufficient: after it
exits 0, still read the piece plainly out loud and ask whether it just states your work, or whether
it sells, narrates, or apologizes.

A caught detector should always widen to the whole synonym neighborhood, not just the one string
that got flagged: a fix that patches one literal phrase ships the same claim back a week later in a
slightly different shell. See knowledge-base/11-preferences-and-conventions.md for that principle.

Companion gate: scripts/batch_voice_check.py catches the sameness a single text can't see, the same
opening skeleton or the same sentence reused across many notes. Run both.

Give it the SENDABLE text, not a whole dossier file (process notes that quote the rules themselves
will trip it), or pass --sendable to have it strip a note's markdown scaffolding for you. Usage:
  python3 scripts/voice_check.py path/to/message.txt
  python3 scripts/voice_check.py --text "the message"
  echo "the message" | python3 scripts/voice_check.py -
  python3 scripts/voice_check.py --sendable path/to/cover-note.md
  python3 scripts/voice_check.py --selftest
Exit 0 = clean · 1 = findings · 2 = usage error.
"""
from __future__ import annotations
import re
import sys

# (category, [patterns], why + the fix). Patterns are case-insensitive.
RULES: list[tuple[str, list[str], str]] = [
    ("hype / superlative", [
        r"\bkiller\b", r"\bsuper[-\s]?powers?\b", r"\bexceptional\b", r"\bworld[-\s]?class\b",
        r"\bbest[-\s]?in[-\s]?class\b", r"\bunmatched\b", r"\bunrivall?ed\b", r"\bbull'?s?[-\s]?eye\b",
        r"\bgame[-\s]?changer\b", r"\bcutting[-\s]edge\b", r"\bseamless(ly)?\b", r"\belevate\b",
        r"\bsupercharge\b", r"\brock[-\s]?star\b", r"\b10x\b", r"\bnext[-\s]level\b",
        r"\btop[-\s]tier\b", r"\bstrongest\b", r"\bgod of \w+\b", r"\ba god\b",
        r"\bdoubly (urgent|important)\b", r"\bthe (entire|whole) point\b",
    ], "Selling or inflating. State the fact flat and stop; drop the superlative."),

    ("false modesty / naming a limitation", [
        r"\bcan'?t say for sure\b", r"\bnot sure I'?d be a good fit\b",
        r"\b(one )?gap I'?d flag\b", r"\bone gap\b", r"\bhonest gap\b",
        r"\b(have|need) to ramp\b", r"\bramp on\b", r"\bwould have to ramp\b",
        r"\bI'?m not (great|good) at\b", r"\bI struggle with\b",
        r"\bmy (one )?(weakness|limitation)\b", r"\bthat'?s a (weakness|limitation)\b",
    ], "Undercutting yourself or naming a limitation nobody asked about. State the work plainly "
       "and let it stand; you know what you're good at."),

    ("performed emotion", [
        r"\bcan'?t stop thinking about\b", r"\bkeeps me up at night\b", r"\bobsess(ed|ion)\b",
        r"\b(deeply|really)\s+passionate\b", r"\blights?\s+(me|him|her|them)\s+up\b",
    ], "Announced feeling. Show the specific thing plainly; do not name the emotion."),

    ("story-arc", [
        r"\bthe (hard|expensive) way\b", r"\band that'?s why\b", r"\bthat'?s when I\b",
        r"\bhere'?s the thing\b", r"\bit turns out\b", r"\blittle did I\b", r"\bwhat I realized\b",
    ], "Reads as a story (setup, lesson, turn). Skip the narrative arc; make it a plain statement."),

    ("too-neat mirror", [
        r"\balready\b", r"\bexactly\b",
        r"\bthe same (thing|fight|problem) I (deal|fight|face|work|live)\b",
        r"\breads like a description of my\b",
    ], "A too-neat mirror between the company and you, the JD's language handed back as if you "
       "already lived inside their exact framing. This is a BLANKET ban on the bare words "
       "'already' and 'exactly', not a pattern over specific noun phrases: a pattern-matched rule "
       "over specific shapes ('exactly how I work') missed the same claim wearing a different "
       "grammatical shell every time it was tightened ('is already my default', 'is already the "
       "world X operates in', 'I already work with the product': three distinct shells, same "
       "underlying claim, in one sweep). When a banned pattern keeps resurfacing in a new shape, "
       "the word itself is the tell, not the sentence shape around it. Any legitimate non-mirror "
       "use ('exactly 5 years', 'I have already relocated') is cheap to reword and loses nothing "
       "by dropping the word, and that trade beats missing a fourth variant."),

    ("em/en-dash", [r"—", r"–", r"(?<!\w)--(?!\w)"],
        "Em-dash, en-dash, or double-dash. Banned in shipped copy; use a period or a comma. "
        "(Feed this the SENDABLE prose, not a whole dossier file: markdown headers and date "
        "ranges use dashes structurally, and that is not what this rule is for.)"),

    ("antithesis", [
        r"\bit'?s not (just )?(about )?[^.,;]{1,30}[,;] it'?s\b",
        r"\bnot a \w+[.,;] (it'?s|but)\b",
    ], "'Not X, it's Y' antithesis. Symmetry is not insight; write the plain version."),

    ("performed / trying to impress", [
        r"\bno\s+[\w-]+,\s+no\s+[\w-]+,\s+no\s+[\w-]+",   # rhetorical negative list: "no feed, no streaks, no coach"
        r"\b(it|that|which)\s+refuses\s+to\b",             # anthropomorphized bold claim
        r"\bthe (overrated|obscure) one is\b",             # mic-drop framing of a hot take
    ], "Performing / trying to sound impressive (a rhetorical negative-list, an anthropomorphized "
       "bold claim, or a hot-take pronouncement). Keep a natural tone, no overconfident or bold "
       "statements a real person wouldn't actually say out loud."),

    # ── Register-level detectors. A keyword denylist keeps missing the CLAIM a person is actually
    # making when it's dressed in a synonym: "selling yourself as a god," the mirror wearing a
    # different word, the fit-sell, the performed setup, the reflexive triad. Each pattern below
    # catches the register SHELL, never a plain statement of the work, and each one has a selftest
    # proving both directions. Standing rule (knowledge-base/11): when a voice defect is caught, the
    # SAME change adds the WHOLE synonym neighborhood, not just the one string that tripped it, plus
    # a selftest that proves it fires. A one-string patch is not a fix.

    ("mirror-in-disguise (the claim is banned in any wording, not the word)", [
        r"\bthe (exact|same|very) (problem|thing|shape|muscle|challenge|tension|question|fight|work|kind of \w+)\b",
        r"\bthat'?s (exactly |just |precisely )?(what|how) I (do|work|operate|design|build|approach)\b",
        r"\bI (work|do|design|operate|build|ship) (that|this) way\b",
        r"\bI (build|do|design|ship|bring|catch) (that|this) kind of \w+\b",
        r"\bcomes? naturally to (me|him|her|them)\b",
        r"\bsecond nature\b",
        r"\b(this is|that'?s|it'?s) just how I (operate|work|do|think|design)\b",
    ], "The too-neat mirror wearing a synonym: the company's own framing mapped onto you as if it "
       "already described you before you ever read their posting. Banned in every wording, not "
       "just the literal words 'already' or 'exactly': 'the exact problem', 'I work that way "
       "already', 'comes naturally', 'second nature' all describe the same claim in a different "
       "shell. State partial overlap plainly ('close to what I've built'); never claim their "
       "framing was true of you before you read it."),

    ("building to a point (performed setup)", [
        r"\bhere'?s the (part|thing|bit)\b",
        r"\bthe (other )?part (that|which) stood out\b",
        r"\bwhat (really )?stood out\b",
    ], "A person answering a question does not build to a point. Drop the setup and say the thing. "
       "'Here's the part I care about most:' becomes stating it flat."),

    ("performed superlative", [
        # The tell is PERFORMED emphasis, not the plain factual "the hardest part was <fact>",
        # which is a fine, honest register on its own. Flagging the bare form is a false positive
        # on honest copy, so only the doubled / superlative-of-superlatives shapes are caught.
        r"\bhardest and most \w+\b",
        # "the single hardest/toughest" is performed; "the single biggest/best <cost/risk/line>" is
        # a plain factual comparison, so biggest/best are excluded from this pattern. The "... ever"
        # and "by far the ..." shapes stay performed for all four words.
        r"\bthe single (?:hardest|toughest)\b",
        # "the hardest thing I've ever built" is the performed tell; "the best turnout the event
        # ever had" is a plain external fact, so the "ever" shape anchors to the writer's own work.
        r"\b(?:hardest|toughest|biggest|best)\b[^.!?\n]{0,20}\bI'?ve ever\b",
        r"\b(?:hardest|toughest|biggest|best)\b[^.!?\n]{0,25}\bever (?:built|shipped|designed|made|done|worked)\b",
        r"\bby far the (?:hardest|toughest|best|most \w+)\b",
    ], "Performed emphasis dressing a plain fact ('the hardest AND MOST interesting part', 'by far "
       "the hardest', 'the single hardest'). State what it was, not how remarkable it was. A plain "
       "'the hardest part was <concrete fact>' is fine; that's the honest register, not a tell."),

    ("fit-sell / god-mode confidence", [
        # anchored to a candidate subject: "I'm a great fit" fires, but "the typeface was a great
        # fit for the tables" is a plain object description and must not.
        r"\b(?:I|I'?m|me|myself|candidate)\b[^.!?\n]{0,24}\b(?:perfect|ideal|strong|great|natural|obvious)\s+fit\b",
        r"\bideal candidate\b", r"\buniquely (positioned|qualified|suited)\b",
        r"\brare (combination|blend|mix)\b", r"\bone of the (very )?few\b",
        r"\bin my wheelhouse\b", r"\bmy sweet spot\b", r"\bright up my alley\b",
        r"\bproven track record\b", r"\bdeep expertise\b", r"\bbattle[- ]tested\b",
        r"\bI (thrive|excel)\b", r"\bhit the ground running\b",
        r"\b(day[- ]one|immediate|instant) impact\b",
        r"\bI'?ve figured (it|this|everything|it all) out\b",
        r"\bI don'?t just \w+,? I \w+\b",
    ], "Selling yourself as the perfect, rare, proven candidate who has it all figured out. State "
       "the real work flat and let the fit be inferred; never assert it."),

    ("announced passion / excitement", [
        r"\b(i'?m|i am|so|really|genuinely)\s+(excited|thrilled|pumped|energized)\b",
        r"\b(excited|thrilled|pumped|energized)\s+(to|about|for)\b",
        r"\bpassionate about\b", r"\beager to\b",
    ], "Announced feeling. Point 7 of §11 bans naming the emotion ('excited/passionate'). Show the "
       "specific thing plainly; do not declare the feeling."),

    ("forced-warmth idiom", [
        r"\bI'?d owe you one\b", r"\bowe you (one|big|big time)\b",
        r"\byou'?d be doing me a solid\b", r"\bforever grateful\b",
    ], "A performed-warmth idiom most people do not actually use in writing. The honest plain "
       "register: 'that would help a lot' / 'that would mean a lot' / 'I'd really appreciate it'."),

    ("reflexive triad (rule of three)", [
        r"\bI \w+,\s+I \w+,?\s+and I \w+\b",
        r"\b(\w+) the \w+,\s+\1 the \w+,?\s+and \1 the \w+\b",
    ], "A reflexive balanced triad ('I design, I build, and I ship' / 'draw the thing, build the "
       "thing, judge the thing'), the loudest AI fingerprint (§11 point 1). Use one, two, or an "
       "uneven list."),

    ("rinse-and-repeat template opener", [
        r"\bI saw the\b[^.]{0,60}\brole\b[^.]{0,15}\bthe line about\b",
    ], "A stock opener that turns up across many cover notes. The same first move every time reads "
       "as a template. Open on the one specific true thing about THIS role, in its own words. "
       "(Cross-note sameness is caught by scripts/batch_voice_check.py.)"),

    # §11 point 8 names these explicitly ("corporate connective tissue & intensifiers") but nothing
    # detected them mechanically before this pass. Scoped to the tell shapes (sentence-initial
    # connectives, the fixed phrases) so a legitimate mid-sentence "honestly" or a literal "at the
    # end of the day" time reference does not over-fire.
    ("corporate connective tissue / intensifier (§11 pt 8)", [
        r"(?:^|[.!?]\s+|\n)(?:Genuinely|Truly|Honestly|Frankly),",
        r"(?:^|[.!?]\s+|\n)That said,",
        r"(?:^|[.!?]\s+|\n)It'?s worth noting\b",
        r"\bneedless to say\b",
        r"\bI care deeply\b", r"\bdeeply care\b",
    ], "§11 point 8: corporate connective tissue and hollow intensifiers ('Genuinely,' 'Truly,' "
       "'That said,' 'It's worth noting,' 'I care deeply'). Cut the connective and state the thing "
       "plainly; the emphasis words add nothing a specific true detail would not."),

    # The existing "antithesis" rule catches "it's not X, it's Y." This adds the "it was never
    # about X, it's Y" mirror of the same move.
    ("antithesis (never about X, it was Y)", [
        r"\b(?:it|that)'?s?\s+(?:was\s+)?never\s+(?:been\s+)?(?:about|the point)\b[^.!?\n]{0,60}\bit'?s\b",
        r"\bnever\s+about\s+the\s+\w+[^.!?\n]{0,40},?\s+it'?s\s+about\b",
    ], "Antithesis porn: the 'it was never about X, it's Y' turn. Symmetry is not insight. Say the "
       "one thing plainly, without the mirrored setup."),

    # Overconfident-control tells that carry no hype word, so they slip past every other detector
    # while still reading as a flex: "on top of it the whole time," "on a short leash." This is the
    # same don't-inflate/no-performance register as the rest of §11, just without a superlative in
    # sight, which is exactly why a plain hype-word gate missed it.
    ("performed control / swagger", [
        r"\b(?:I'?m|I am|staying|I stay|keeping it|keep it)\s+on top of (?:it|them|everything|all of it)\b",
        r"\bon a short leash\b",
        # the swagger is "not babysitting every screen," not the plain "babysitting the deploy"
        # (require the every/each/the-<surface> object, or the "not ... babysit" shape).
        r"\bbabysit(?:ting)?\s+(?:every|each|the)\s+(?:screen|output|line|change|thing|pixel|step)\b",
        r"\bnot\s+(?:sitting there\s+)?babysit(?:ting)?\b",
        # the possessive FLOURISH ("the judgment, that stays with me"), never the plain "I keep the
        # design decisions," so it requires the "that/it ... stays/lives with me" shape.
        r"\b(?:that|it|the (?:judgment|call|taste|decision|say))\s+(?:part\s+)?(?:stays|lives)\s+with me\b",
    ], "Performed control or swagger: 'on top of it the whole time,' 'short leash,' 'not "
       "babysitting every screen,' 'that stays with me.' State what you do plainly ('I review the "
       "code and make the design calls'); drop the flex."),

    ("performed repetition (a beat for emphasis)", [
        # a word repeated after a full stop for a spoken flourish: "nobody used them. Like, nobody."
        r"\b(\w{3,})\b[^.!?\n]{0,30}[.!?]\s+(?:Like|Just|Really|Honestly),?\s+\1\b",
        # the bare doubled beat: "gone. Just gone." / "done. Actually done."
        r"\b(\w{3,})[.!]\s+(?:Just|Really|Actually|Like)\s+\1\b",
    ], "A word repeated for a performed beat ('nobody used them. Like, nobody.', 'gone. Just "
       "gone.'). It's a spoken-word flourish, not information. Say it once, plainly."),
]


def sendable_prose(text: str) -> str:
    """The copy a reader actually receives, lifted out of a note or answer FILE so the gate reads
    the words and not the scaffolding around them.

    Without this, running the gate on a real file drowns in false positives: a markdown `---` fence
    used as a section divider reads as an em-dash, a process note that quotes a banned phrase to
    document its own removal trips the detector on the very sentence recording the fix, and a
    metadata line can carry the job posting's own language verbatim. The convention this project
    uses across files like cover-note.md (and any similar single- or multi-answer note): the
    sendable copy sits between the first PAIR of `---` fences, or AFTER the first fence when there
    is no closing one. No fence at all means the whole text is copy.
    """
    parts = re.split(r"(?m)^[ \t]*---[ \t]*$", text)
    # ALL copy after the first fence, not just the first section: a multi-answer file (Q1 --- Q2 ---
    # Q3) should have every answer checked, not just the first one, and joining the tail also keeps
    # a single-answer file (two parts: metadata, answer) correct.
    body = "\n".join(parts[1:]) if len(parts) >= 2 else text
    out = []
    for ln in body.splitlines():
        s = re.sub(r"^\s*>\s?", "", ln)               # drop a blockquote marker first, so a
        if re.match(r"^\s*#", s):                     # metadata line written as "> **Source:** ..."
            continue                                  # is dropped too (a quoted job-posting
        if re.match(r"^\s*\*\*[^*]+:\*\*", s):         # excerpt should not be checked as your prose)
            continue
        out.append(s)
    return "\n".join(out)


def check(text: str) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    for cat, pats, why in RULES:
        seen = set()
        for p in pats:
            for m in re.finditer(p, text, re.I):
                frag = m.group(0).strip()
                key = (cat, frag.lower())
                if key in seen:
                    continue
                seen.add(key)
                findings.append((cat, frag, why))
    return findings


def render(findings: list[tuple[str, str, str]]) -> str:
    if not findings:
        return ("voice_check: CLEAN of the mechanical tells (necessary, NOT sufficient: exit 0 is "
                "not permission to ship).\n"
                "  This gate cannot see: confidence-at-100% with no banned word, a mirror claim in "
                "a phrasing it hasn't learned yet, or the SAME opener reused across many notes "
                "(that is scripts/batch_voice_check.py's job).\n"
                "  Still required: read it plainly out loud. Does it just state the work, or does "
                "it sell, narrate, or apologize? Plain and neutral is the bar, neither pitch nor "
                "hedge (CLAUDE.md §11).")
    out = [f"voice_check: {len(findings)} finding(s). Rewrite before this passes.\n"]
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

    def cats(t):
        return {c for c, _, _ in check(t)}

    # Over-SELLING: a hype-and-mirror-heavy draft, caught on multiple axes.
    hype = ("Because the thing Mirror is actually solving is the thing I can't stop thinking about. "
            "That's the same fight I'm in every day. Most software looks the same now, and that's "
            "exactly how I work: I keep the judgment. Mirror is a bet that the specific human signal "
            "is the entire point. That's the exact muscle Mirror needs. It's your strongest, killer fit.")
    hf = cats(hype)
    want("catches performed emotion (can't stop thinking about)", "performed emotion" in hf)
    want("catches too-neat mirror (exactly how I / same fight)", "too-neat mirror" in hf)
    want("catches hype (strongest / killer / the entire point)", "hype / superlative" in hf)

    story = "I learned it the hard way, and that's why now I keep the judgment on what ships."
    want("catches story-arc (the hard way / and that's why)", "story-arc" in cats(story))

    # Three distinct grammatical shells for the same underlying claim, found in one real sweep:
    # a pattern-matched rule over specific phrases missed the second and third shell entirely,
    # which is exactly why this rule is now a blanket ban on the bare words, not a phrase list.
    already_mirror = ("I'm applying for the Design Engineer role. The line about owning the design "
                       "system across Figma and code is already how I work.")
    want("catches 'is already how I work' (not just 'exactly')",
         "too-neat mirror" in cats(already_mirror))

    synonym_mirror = ("A designer who ships his own production front end, with an AI-native workflow, "
                       "is already the world Fathom operates in.")
    want("catches 'is already the world X operates in' (the copula shell)",
         "too-neat mirror" in cats(synonym_mirror))

    no_copula_mirror = ("I use Northwind every working day, so the honest version of why I'm applying "
                         "is that I already work with the product all day.")
    want("catches 'I already work' (no copula, the blanket-word fix)",
         "too-neat mirror" in cats(no_copula_mirror))

    want("catches em-dash", "em/en-dash" in cats("I ship the front end — all of it."))
    want("catches en-dash (U+2013)", "em/en-dash" in cats("I ship the front end – all of it."))

    # A plain "the hardest part was <fact>" must not flag; the DOUBLED form still must.
    want("plain 'the hardest part was <fact>' is NOT flagged as a performed superlative",
         "performed superlative" not in cats(
             "The hardest part was the billing: a race where a cancelled order could still charge a card."))
    want("the DOUBLED 'hardest and most' IS still caught",
         "performed superlative" in cats("The hardest and most interesting part was the sync."))

    want("catches §11-pt8 intensifier ('It's worth noting')",
         "corporate connective tissue / intensifier (§11 pt 8)" in cats(
             "It's worth noting that I ship the front end myself."))
    want("catches antithesis 'it was never about X, it's Y'",
         "antithesis (never about X, it was Y)" in cats(
             "It was never about the volume, it's about the one right answer."))

    perf = "It does one thing, and it refuses to do anything else. No feed, no streaks, no coach."
    pf = cats(perf)
    want("catches performed negative-list (no X, no Y, no Z)", "performed / trying to impress" in pf)
    want("catches anthropomorphized 'it refuses to'", "performed / trying to impress" in pf)

    # Over-APOLOGIZING: false modesty / naming a limitation must be caught.
    modest = ("Honestly, I can't say for sure I'd be a good fit. One gap I'd flag: my stack is React "
              "and Tailwind, not deep Next.js server components, so that is something I would have "
              "to ramp on.")
    mf = cats(modest)
    want("catches false modesty ('can't say for sure I'd be a good fit')",
         "false modesty / naming a limitation" in mf)
    want("catches naming a limitation ('gap I'd flag' / 'ramp on')",
         "false modesty / naming a limitation" in mf)

    # ── Register-level detectors. Each catches a real tell that a plain keyword gate misses; the
    # must-NOT set below (the plain rewrite + the approved DM control) proves the patterns catch
    # the register shell, not a plain statement of the work.
    want("mirror-in-disguise: 'the exact problem I've been working on'",
         "mirror-in-disguise (the claim is banned in any wording, not the word)" in cats(
             "That's the exact problem I've been working on at my current company."))
    want("mirror-in-disguise: 'comes naturally to me' (a synonym a phrase-list rule would miss)",
         "mirror-in-disguise (the claim is banned in any wording, not the word)" in cats(
             "It comes naturally to me."))
    want("mirror-in-disguise: 'second nature'",
         "mirror-in-disguise (the claim is banned in any wording, not the word)" in cats(
             "That is second nature to me."))
    want("building-to-a-point: 'Here's the part I care about most'",
         "building to a point (performed setup)" in cats(
             "Here's the part of this work I care about most: judgment."))
    want("performed superlative: 'the hardest and most interesting part'",
         "performed superlative" in cats("It was the hardest and most interesting part of building it."))
    want("fit-sell: 'strong fit'", "fit-sell / god-mode confidence" in cats("I'm a strong fit for this role."))
    want("fit-sell: 'proven track record'",
         "fit-sell / god-mode confidence" in cats("I have a proven track record of shipping product."))
    want("fit-sell: 'I don't just design, I ship'",
         "fit-sell / god-mode confidence" in cats("I don't just design, I ship."))
    want("announced passion: 'excited about'",
         "announced passion / excitement" in cats("I'm excited about this role."))
    want("forced-warmth: 'I'd owe you one'",
         "forced-warmth idiom" in cats("If you can refer me, I'd owe you one."))
    want("reflexive triad: 'I design, I build, and I ship'",
         "reflexive triad (rule of three)" in cats("I design, I build, and I ship."))
    want("rinse-and-repeat opener",
         "rinse-and-repeat template opener" in cats(
             "I saw the Senior Product Designer role, and the line about owning a product area."))

    # 🔴 MUST NOT FLAG: an approved plain-register DM. If a new detector trips this, it's too broad;
    # this is the exact tone this project's plain-voice bar is aiming for.
    alex_dm = ("Hey Alex, thanks for the add. Your post about letting the model decide what "
               "actually serves the query stuck with me. I've been making that same bet, just from "
               "the design side. At Fathom I built the design system solo, and the whole reason it "
               "exists is so the coding agents read the tokens and component contracts straight off "
               "an internal server instead of guessing. I design the product, then ship the front "
               "end myself the same way. And honestly, seeing a CEO credit his designer the way you "
               "do is half of why I applied. The application's in for the product design role. "
               "Casey's got a note from me too, so this isn't me sneaking in a side door. Work's at "
               "example.com. Worth a look? Jordan")
    alex_findings = check(alex_dm)
    want(f"the approved plain-register DM stays CLEAN (got: {[c for c, _, _ in alex_findings]})",
         not alex_findings)

    # The plain, neutral, confident rewrite must be CLEAN.
    plain = ("Here is how I work. I design products for dense, complex work and make them clear and "
             "fast to use. I built our design system at Fathom on my own, so the whole front end "
             "pulls from one source of truth. I take the design to production myself, which means "
             "what ships is what I decided. The part I care about most is judgment: what is actually "
             "worth building and what to cut. Mirror interests me because you are keeping a real "
             "person's voice inside a product, which is close to what I have built.")
    plain_findings = check(plain)
    want(f"the plain rewrite is CLEAN (got: {[c for c,_,_ in plain_findings]})", not plain_findings)

    # ── Performed control / swagger + performed repetition. The exact tells this project's plain
    # voice bar names; the plain statement of the same fact is NOT flagged.
    want("swagger: 'I'm on top of it the whole time'",
         "performed control / swagger" in cats(
             "The AI writes the code and I'm on top of it the whole time."))
    want("swagger: 'keep it on a short leash'",
         "performed control / swagger" in cats("I use AI a lot but I keep it on a short leash."))
    want("swagger: 'not babysitting every screen'",
         "performed control / swagger" in cats("So I'm not sitting there babysitting every screen."))
    want("swagger: 'the judgment, that stays with me'",
         "performed control / swagger" in cats("Let it build, but the judgment, that stays with me."))
    want("repetition: 'nobody used them. Like, nobody.'",
         "performed repetition (a beat for emphasis)" in cats(
             "We shipped fast and nobody used them. Like, nobody."))
    want("🔴 the PLAIN control statement is NOT swagger (must not flag)",
         "performed control / swagger" not in cats(
             "The AI writes most of the code, and I go through it and make the design decisions."))

    # ── Anchoring checks: object-agnostic patterns must not fire on plain facts that are not about
    # you, while the self-referential tell still fires.
    want("🔴 'the typeface was a great fit' is NOT fit-sell (plain object)",
         "fit-sell / god-mode confidence" not in cats(
             "The Inter typeface was a great fit for the dense tables."))
    want("fit-sell still fires on 'I'm a great fit'",
         "fit-sell / god-mode confidence" in cats("I'm a great fit for this role."))
    want("🔴 'best turnout the event ever had' is NOT a performed superlative",
         "performed superlative" not in cats("It was the best turnout the event ever had."))
    want("performed superlative still fires on 'the hardest thing I've ever built'",
         "performed superlative" in cats("That was the hardest thing I've ever built."))
    want("🔴 'babysitting the overnight deploy' is NOT swagger (plain usage)",
         "performed control / swagger" not in cats(
             "I was babysitting the overnight deploy when it failed."))
    want("swagger still fires on 'not babysitting every screen'",
         "performed control / swagger" in cats("So I'm not sitting there babysitting every screen."))

    # ── sendable_prose(): multi-section files, blockquoted metadata, and documenting-a-fix text.
    want("sendable_prose checks EVERY answer, not just the first (a later 'hard way' is caught)",
         "story-arc" in cats(sendable_prose(
             "# Q\n**note:** x\n---\nAnswer one is plain.\n---\nAnd that's why I learned it the hard way.\n")))
    want("sendable_prose drops a `> **Source:**` quoted line",
         "performed / trying to impress" not in cats(sendable_prose(
             "# Q\n---\n> **Source:** posting says 'no feed, no streaks, no coach'\nMy answer is plain.\n")))

    # The metadata that DOCUMENTS a removed tell (a note about a dropped "learned it the hard way"
    # story arc) sits BEFORE the fence and must be dropped, or the gate false-fires on the very
    # sentence recording the fix. Only the fenced copy is what gets checked.
    narration = ('# Q3 narration\n**v3 note:** v1 had a "learned it the hard way" story arc; removed.\n'
                 '---\nYeah. I use AI on the build side. I write tests for the things that matter.\n')
    want("sendable_prose drops the metadata 'hard way' (checks only the fenced copy)",
         "story-arc" not in cats(sendable_prose(narration)))
    want("sendable_prose still catches a tell INSIDE the fenced copy",
         "story-arc" in cats(sendable_prose(
             "# Q\n**note:** x\n---\nAnd that's why I learned it the hard way, honestly.\n")))

    print("voice_check.py selftest\n")
    for label, ok in results:
        print(f"  {'✓' if ok else '✗'} {label}")
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    # --sendable: read a FILE (or stdin with -) but check only its SENDABLE copy: the fenced body,
    # with metadata and markdown structure stripped. This is how a Stop hook can read a note file
    # without false-positiving on its own scaffolding.
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
