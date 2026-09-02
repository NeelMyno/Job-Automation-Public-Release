#!/usr/bin/env python3
"""subject_check.py — the founder-email SUBJECT-LINE gate.

Founder-direct emails are a common cap-bypass channel. The subject line must give THIS
recipient a reason to open: the role, plus a short TRUE slice of your background that maps
to what they build. A bare "Role at Company" with no hook reads as a template, so a hook
is required. This makes the rule MECHANICAL so it cannot rot into prose.

The LOCKED template (KB-11 §ratified-log is the owner — do not restate the rule elsewhere):

    <Role> at <Company> | <2-8 word TRUE domain hook>

  e.g.  Founding Product Designer at Acme | Freight & logistics product design
        Founding Product Designer at Globex | AI product design for GTM teams

BANNED and why:
  - a bare "Role at Company" with no ` | hook`   → reads like a template, no reason to open
  - hype / superlatives in the hook              → §11 plain voice
  - a "found a bug / redesign / mistake in your
    product" hook                                → reads as generic and rinse-and-repeat
  - em-dash / en-dash / "!"                      → §11 house style

This gates the SUBJECT ONLY. The email BODY still runs voice_check.py. The hook must be TRUE
and grounded (§0.1) — the gate cannot verify truth, only shape; that stays on the author.

Usage:
  python3 scripts/subject_check.py --text "Founding Product Designer at Acme | Freight & logistics product design"
  python3 scripts/subject_check.py path/to/subjects.txt   # one subject per non-blank line
  echo "..." | python3 scripts/subject_check.py -
  python3 scripts/subject_check.py --selftest
Exit 0 = clean · 1 = findings · 2 = usage error.
"""
from __future__ import annotations
import re
import sys

HYPE = [
    r"\bbest\b", r"\btop\b", r"\bexceptional\b", r"\bworld[-\s]?class\b", r"\bexpert\b",
    r"\bleading\b", r"\bproven\b", r"\bkiller\b", r"\bsuper[-\s]?powers?\b", r"\b10x\b",
    r"\bguru\b", r"\brock\s?star\b", r"\bninja\b", r"\bunmatched\b", r"\bunparalleled\b",
    r"\bpassionate\b", r"\bobsessed\b", r"\bgenius\b", r"\bstrongest\b",
    r"\bperfect\b", r"\bgod\b", r"\bwizard\b", r"\belite\b",
]
BUG_HOOK = [
    r"\bfound a bug\b", r"\bnoticed a\b", r"\bspotted a\b", r"\bredesign your\b",
    r"\bfix your\b", r"\bmistake\b", r"\bbroke\b", r"\bbroken\b", r"\bissue (?:in|with) your\b",
    r"\bproblem (?:in|with) your\b", r"\byour .* is (?:slow|broken|confusing|off)\b",
    r"\bimprove your\b", r"\bwhat'?s wrong with\b",
]


def check_subject(s: str) -> list[str]:
    """Return a list of finding strings for one subject line ([] = clean)."""
    findings: list[str] = []
    raw = s.strip()
    if not raw:
        return findings  # blank lines are skipped by the caller

    if "—" in raw or "–" in raw:
        findings.append("R6 em/en-dash — house style forbids it (§11). Use a plain pipe ` | `.")
    if "!" in raw:
        findings.append("R6 exclamation mark — subjects stay flat, no punch (§11).")

    # R1 STRUCTURE — exactly one ` | `, both sides non-empty.
    parts = raw.split("|")
    if len(parts) != 2:
        findings.append(
            "R1 structure — need exactly one ` | ` separator. Template: "
            "`<Role> at <Company> | <2-8 word true domain hook>`. "
            "A bare `Role at Company` with no hook reads like a template, not a reason to open."
        )
        return findings  # nothing else is meaningful without the split
    left, hook = parts[0].strip(), parts[1].strip()
    if not left:
        findings.append("R1 structure — the left of ` | ` (role at company) is empty.")
    if not hook:
        findings.append("R1 structure — the hook (right of ` | `) is empty; give a real reason to open.")

    # R2 LEFT — must read "<Role> at <Company>".
    if left and " at " not in f" {left} ":
        findings.append("R2 left side must read `<Role> at <Company>` (missing ` at `).")

    # R3 HOOK LENGTH — 2..8 words, a phrase not a sentence.
    if hook:
        n = len(hook.split())
        if n < 2:
            findings.append(f"R3 hook is {n} word — too thin; give a 2-8 word domain slice.")
        elif n > 8:
            findings.append(f"R3 hook is {n} words — too long; tighten to a 2-8 word phrase, not a sentence.")

    low = raw.lower()
    for pat in HYPE:
        if re.search(pat, low):
            findings.append(f"R4 hype/superlative in the subject (`{pat}`) — plain voice only (§11).")
            break
    for pat in BUG_HOOK:
        if re.search(pat, low):
            findings.append(
                f"R5 'found-a-bug / fix-your-product' hook (`{pat}`) — too lame and rinse-and-repeat. "
                "Lead with your real matching experience, never their flaw."
            )
            break
    return findings


def run(subjects: list[str]) -> int:
    any_fail = False
    checked = 0
    for s in subjects:
        if not s.strip():
            continue
        checked += 1
        fs = check_subject(s)
        if fs:
            any_fail = True
            print(f"FAIL — {s.strip()!r}")
            for f in fs:
                print(f"    - {f}")
        else:
            print(f"OK   — {s.strip()!r}")
    if checked == 0:
        print("subject_check: no subject lines to check.")
        return 0
    if any_fail:
        print("\nsubject_check: FAIL. Fix the subject(s) before sending (owner: KB-11).")
        return 1
    print(f"\nsubject_check: {checked} subject(s) OK — role-first + true domain hook, no hype, no flaw-hook.")
    return 0


SELFTEST = [
    # (subject, should_pass)
    ("Founding Product Designer at Acme | Freight & logistics product design", True),
    ("Product Designer at Globex | AI product design for GTM teams", True),
    ("Design Engineer at Initech | Design systems + production front-end", True),
    ("Founding Product Designer at Acme | 3 years designing freight & logistics products", True),
    # a bare subject with no hook:
    ("Founding Product Designer role at Acme", False),
    ("Product Designer at Globex", False),
    # hype:
    ("Founding Product Designer at Acme | The best freight designer around", False),
    # found-a-bug / fix-your-product hook:
    ("Product Designer at Fabrikam | I noticed a problem in your onboarding", False),
    ("Design Engineer at Contoso | let me redesign your dashboard", False),
    # em-dash instead of pipe:
    ("Founding Product Designer at Acme — Freight & logistics product design", False),
    # hook too long (a sentence, not a phrase):
    ("Product Designer at Northwind | I build design systems and ship the front end by directing agents", False),
]


def selftest() -> int:
    ok = True
    for subj, should_pass in SELFTEST:
        passed = len(check_subject(subj)) == 0
        good = passed == should_pass
        ok = ok and good
        tag = "ok " if good else "XX "
        verdict = "PASS" if passed else "FAIL"
        want = "PASS" if should_pass else "FAIL"
        print(f"  [{tag}] got {verdict}, want {want}: {subj!r}")
    if ok:
        print("subject_check selftest OK")
        return 0
    print("subject_check selftest FAILED — a real protection just broke.")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--selftest":
        return selftest()
    if argv[1] == "--text":
        if len(argv) < 3:
            print("usage: --text \"<subject>\"", file=sys.stderr)
            return 2
        return run([argv[2]])
    if argv[1] == "-":
        return run(sys.stdin.read().splitlines())
    try:
        with open(argv[1], encoding="utf-8") as fh:
            return run(fh.read().splitlines())
    except OSError as e:
        print(f"cannot read {argv[1]}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
