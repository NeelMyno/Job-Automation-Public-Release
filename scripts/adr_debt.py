#!/usr/bin/env python3
"""adr_debt.py: surface ADRs whose consequences are still unexecuted.

Scans a decisions folder (ops/decisions/*.md, or wherever your ADRs live) for
pending-consequence markers. An ADR that defers work can carry a
`Consequences-pending:` field until a LATER ADR clears it; decisions stay
append-only and immutable, but debt can still be tracked and retired instead
of silently rotting. A session-start hook is a natural place to run this:
nonzero output means there's real debt to surface before any task work.

TWO DEFECTS THIS SCRIPT WAS HARDENED AGAINST:

1. **A heading-form marker was invisible.** An early version of this script
   only matched a `Consequences-pending:` line written with a colon. When a
   decision instead wrote its debt as a markdown heading (`## Consequences-
   pending`), the gate silently missed it. A debt tracker that is itself
   quietly missing debt is worse than no tracker at all: it prints a number,
   the number gets believed, and nobody re-derives it.

2. **There was no way to clear a line.** ADRs are append-only and must never
   be edited, so a pending-consequence line could only ever be added, never
   retired, and a resolved one would then be re-reported at every run,
   forever, even after the work was done or the decision was superseded.

   So a later ADR now clears an earlier one by carrying:

       Consequences-cleared: ADR-0007 - <why, in one line>

   History stays intact, the ADR stays immutable, and the debt stops being
   broadcast. The clearing ADR is named in the output so the chain stays
   auditable.

Exit 1 if any UNCLEARED pending line is found, 0 clean.

WHY THIS HAS A SELFTEST
------------------------
This is typically the first check a session or CI run reads, so a false
negative here means unfinished work goes unreported indefinitely. Both
defects above were found by manual audit, not by the script catching itself:
exactly the failure mode a selftest exists to prevent.

    python3 scripts/adr_debt.py --selftest

Every fixture below is invented, generic ADR text (not real decision
content) chosen to exercise the same regex edge cases the real defects
above were found in.
"""

import re
import sys
from pathlib import Path

# Anchored to the start of the line (past any markdown decoration) so that a sentence *about*
# a pending line is not counted as one, e.g. a later ADR saying "ADR-0007's Consequences-pending
# line stays valid" is a reference, not a declaration; an unanchored match would double-count it.
PENDING = re.compile(r"^[\s>*_#\-]*Consequences-pending\b", re.I)
CLEARED = re.compile(r"Consequences-cleared\s*:\s*ADR-(\d{4})\s*(?:—|--|-)?\s*(.*)", re.I)


def scan(sources: dict[str, str]) -> tuple[list[tuple[str, str, int, str]],
                                           dict[str, tuple[str, str]]]:
    """Parse `{adr filename: text}` into (pending, cleared).

    Split out from `main()` so the parsing can be tested against fixtures instead of only against
    whatever happens to be on disk. Reading the real folder is not a test: it passes trivially on
    the day you write it and proves nothing about the shape you have not encountered yet.
    """
    pending: list[tuple[str, str, int, str]] = []   # (adr number, filename, lineno, text)
    cleared: dict[str, tuple[str, str]] = {}        # cleared ADR -> (clearing ADR, reason)

    for name in sorted(sources):
        num = name[:4]
        for lineno, line in enumerate(sources[name].splitlines(), 1):
            c = CLEARED.search(line)
            if c:
                cleared[c.group(1)] = (num, c.group(2).strip())
                continue
            if PENDING.search(line):
                # "Consequences-pending: none" is a declaration that there is no debt, not debt
                # itself. Counting it would make a clean bill of health look like an outstanding item.
                tail = PENDING.sub("", line).lstrip(" :*_-—")
                if re.match(r"^(none|n/?a|nil)\b", tail, re.I):
                    continue
                pending.append((num, name, lineno, line.strip()))
    return pending, cleared


def live_debt(pending: list, cleared: dict) -> list:
    """The pending lines no later ADR has cleared. Order-independent: `cleared` is fully built
    before this runs, so a clearing ADR works whichever order the files were read in."""
    return [p for p in pending if p[0] not in cleared]


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()

    decisions = Path(__file__).resolve().parent.parent / "ops" / "decisions"
    if not decisions.is_dir():
        print(f"adr_debt: no decisions folder at {decisions}")
        return 1

    sources = {p.name: p.read_text(encoding="utf-8")
               for p in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md"))}
    pending, cleared = scan(sources)
    live = live_debt(pending, cleared)

    if cleared:
        print(f"adr_debt: {len(cleared)} debt(s) cleared by a later ADR "
              f"({', '.join(f'{k}←{v[0]}' for k, v in sorted(cleared.items()))})")

    if live:
        print(f"adr_debt: {len(live)} pending consequence(s); review before continuing:")
        for _, name, lineno, line in live:
            print(f"  {name}:{lineno}  {line}")
        return 1

    print(f"adr_debt: clean; no ADR carries an uncleared Consequences-pending "
          f"({len(pending)} recorded, {len(cleared)} cleared)")
    return 0


# --------------------------------------------------------------------------------------
# Self-test. Every fixture below is invented, generic ADR text, not real decision content.
# Both defects this script was hardened against (the invisible heading form, the
# un-clearable line) are pinned, and so is every wording that must NOT be counted,
# because the failure mode of a debt tracker is symmetrical: miss a real item and work is
# lost; count a false one and the noise trains the reader to skip the whole report.
# --------------------------------------------------------------------------------------

_P07 = ('Consequences-pending: re-run the board sweep after adding a new data source; the last '
        'sweep only covered 3 of the 9 known feeds and the remaining 6 are unconfirmed.')
_P11 = "## Consequences-pending"                                # DEFECT #1 shape: the heading form
_P13 = ("**Consequences-pending:** the cold-start benchmark (no cache warmed, single region) "
        "remains **unrun**.")

# (label, {filename: text}, expected LIVE debt, expected CLEARED count)
CASES: list[tuple[str, dict[str, str], int, int]] = [
    ("the plain colon form is caught",
     {"0007-data-source-sweep.md": _P07}, 1, 0),

    ("🔴 the HEADING form is caught: the shape that was invisible before hardening",
     {"0011-cache-warming-strategy.md": _P11}, 1, 0),

    ("the bold-colon form is caught",
     {"0013-cold-start-benchmark.md": _P13}, 1, 0),

    ("all three forms together = 3 live items",
     {"0007-a.md": _P07, "0011-b.md": _P11, "0013-c.md": _P13}, 3, 0),

    # --- mentions. A sentence ABOUT debt is not debt. ---
    ("a mid-sentence mention is NOT debt",
     {"0009-sweep-still-valid-note.md":
      "- ADR-0007's Consequences-pending line stays valid (the sweep is still worth running), "
      "but its\n  first clause is now false."}, 0, 0),

    ("backticked / mid-line mentions of the field are NOT debt",
     {"0015-debt-tracker-postmortem.md":
      "edited, so `Consequences-pending:` was a one-way door. ADR-0007's line says *\"the sweep "
      "is\nnow optional\"*\n"
      "`adr_debt.py` was also **missing real debt**: it matched `Consequences-pending:` with a "
      "colon only,\n"
      "so ADR-0011's `## Consequences-pending` heading was invisible. It reported 1 when the "
      "truth was 2."}, 0, 0),

    ("`Consequences-pending: none` is a clean bill of health, not debt",
     {"0017-clearing-mechanism-unused.md":
      "- **Consequences-pending:** none. The clearing mechanism is live but deliberately unused."},
     0, 0),

    # --- clearing. The mechanism is exercised end to end. ---
    ("🔴 a later ADR CLEARS an earlier one",
     {"0007-data-source-sweep.md": _P07,
      "0019-sweep-complete.md": "Consequences-cleared: ADR-0007 - the sweep finished; all 9 "
                                "feeds are confirmed."},
     0, 1),

    ("clearing one ADR does NOT clear another's debt",
     {"0007-data-source-sweep.md": _P07,
      "0013-cold-start-benchmark.md": _P13,
      "0019-sweep-complete.md": "Consequences-cleared: ADR-0007 - superseded by the automated "
                                "sweep."},
     1, 1),

    ("the `ADR-NNNN` FORMAT TEMPLATE is not a real clear",
     {"0021-template-example.md":
      "Consequences-cleared: ADR-NNNN - <why, in one line>"}, 0, 0),
]


def selftest() -> int:
    passed = failed = 0
    print("adr_debt.py selftest: fixtures are invented, generic ADR text\n")
    for label, sources, want_live, want_cleared in CASES:
        pending, cleared = scan(sources)
        live = live_debt(pending, cleared)
        ok = len(live) == want_live and len(cleared) == want_cleared
        if ok:
            passed += 1
            print(f"  ✓ {label}")
        else:
            failed += 1
            print(f"  ✗ {label}\n      expected live={want_live} cleared={want_cleared}, "
                  f"got live={len(live)} cleared={len(cleared)}")
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} cases wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed} "
          f"({sum(1 for c in CASES if c[2]) } debt-detected cases, "
          f"{sum(1 for c in CASES if not c[2])} must-not-count controls)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
