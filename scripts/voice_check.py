#!/usr/bin/env python3
"""voice_check.py: the plain-voice gate.

Every piece of writing runs through this before it passes: outbound copy written as you (cover
notes, outreach, form free-text, portfolio, LinkedIn) and every reply written to you in chat. See
CLAUDE.md §11 (the plain-voice rule).

The target is PLAIN and NEUTRAL. AI-generated writing tends to fail from one of two directions:
over-selling (hype, superlatives, too-neat mirrors between you and the company, story shapes,
performed emotion) or, once corrected, over-apologizing (false modesty, naming limitations/gaps,
undercutting your own competence). This check flags both. It is MECHANICAL, so it is
necessary-but-not-sufficient: after it exits 0, still read the piece plainly out loud and ask
whether it just states your work, or whether it sells, narrates, or apologizes.

Give it the SENDABLE text, not a whole dossier file (process notes that quote the rules themselves
will trip it). Usage:
  python3 scripts/voice_check.py path/to/message.txt
  python3 scripts/voice_check.py --text "the message"
  echo "the message" | python3 scripts/voice_check.py -
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
        r"\bdoubly (urgent|important)\b", r"\bthe (entire|whole) (point|reason)\b",
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

    ("em-dash", [r"—", r"(?<!\w)--(?!\w)"],
        "Em-dash or double-dash. Banned in shipped copy; use a period or a comma."),

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
]


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
        return ("voice_check: CLEAN of the mechanical tells.\n"
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

    # Over-SELLING: a hype-and-mirror-heavy draft, caught on multiple axes.
    hype = ("Because the thing Mirror is actually solving is the thing I can't stop thinking about. "
            "That's the same fight I'm in every day. Most software looks the same now, and that's "
            "exactly how I work: I keep the judgment. Mirror is a bet that the specific human signal "
            "is the entire point. That's the exact muscle Mirror needs. It's your strongest, killer fit.")
    hf = {c for c, _, _ in check(hype)}
    want("catches performed emotion (can't stop thinking about)", "performed emotion" in hf)
    want("catches too-neat mirror (exactly how I / same fight)", "too-neat mirror" in hf)
    want("catches hype (strongest / killer / the entire point)", "hype / superlative" in hf)

    story = "I learned it the hard way, and that's why now I keep the judgment on what ships."
    want("catches story-arc (the hard way / and that's why)", "story-arc" in {c for c, _, _ in check(story)})

    # Three distinct grammatical shells for the same underlying claim, found in one real sweep:
    # a pattern-matched rule over specific phrases missed the second and third shell entirely,
    # which is exactly why this rule is now a blanket ban on the bare words, not a phrase list.
    already_mirror = ("I'm applying for the Design Engineer role. The line about owning the design "
                       "system across Figma and code is already how I work.")
    want("catches 'is already how I work' (not just 'exactly')",
         "too-neat mirror" in {c for c, _, _ in check(already_mirror)})

    synonym_mirror = ("A designer who ships his own production front end, with an AI-native workflow, "
                       "is already the world Fathom operates in.")
    want("catches 'is already the world X operates in' (the copula shell)",
         "too-neat mirror" in {c for c, _, _ in check(synonym_mirror)})

    no_copula_mirror = ("I use Northwind every working day, so the honest version of why I'm applying "
                         "is that I already work with the product all day.")
    want("catches 'I already work' (no copula, the blanket-word fix)",
         "too-neat mirror" in {c for c, _, _ in check(no_copula_mirror)})

    want("catches em-dash", "em-dash" in {c for c, _, _ in check("I ship the front end — all of it.")})

    perf = "It does one thing, and it refuses to do anything else. No feed, no streaks, no coach."
    pf = {c for c, _, _ in check(perf)}
    want("catches performed negative-list (no X, no Y, no Z)", "performed / trying to impress" in pf)
    want("catches anthropomorphized 'it refuses to'", "performed / trying to impress" in pf)

    # Over-APOLOGIZING: false modesty / naming a limitation must be caught.
    modest = ("Honestly, I can't say for sure I'd be a good fit. One gap I'd flag: my stack is React "
              "and Tailwind, not deep Next.js server components, so that is something I would have "
              "to ramp on.")
    mf = {c for c, _, _ in check(modest)}
    want("catches false modesty ('can't say for sure I'd be a good fit')",
         "false modesty / naming a limitation" in mf)
    want("catches naming a limitation ('gap I'd flag' / 'ramp on')",
         "false modesty / naming a limitation" in mf)

    # The plain, neutral, confident rewrite must be CLEAN.
    plain = ("Here is how I work. I design products for dense, complex work and make them clear and "
             "fast to use. I built our design system at Fathom on my own, so the whole front end "
             "pulls from one source of truth. I take the design to production myself, which means "
             "what ships is what I decided. The part I care about most is judgment: what is actually "
             "worth building and what to cut. Mirror interests me because you are keeping a real "
             "person's voice inside a product, which is close to what I have built.")
    plain_findings = check(plain)
    want(f"the plain rewrite is CLEAN (got: {[c for c,_,_ in plain_findings]})", not plain_findings)

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
    findings = check(text)
    print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
