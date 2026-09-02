#!/usr/bin/env python3
"""presubmit_check.py: the blocking-actions gate.

A dossier's review-passes.md records mandatory operator actions as:

    ## OPERATOR ACTIONS
    - [ ] BLOCKING: <action>

An unchecked BLOCKING line means a review found something that MUST happen before
submit and it has not happened. This script exits 2 naming each unchecked item;
the fill/submit stage refuses to open the browser on exit 2. Checked lines
(`- [x] BLOCKING:`) pass. This gate exists because an unenforced checklist item
once reached a live form before this gate existed; nothing was reading
review-passes.md. Now something does.

Usage:
    python3 scripts/presubmit_check.py "applications/<company>-<role>"
    python3 scripts/presubmit_check.py --selftest
"""

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s")
# Real headings vary ("## A8. 🔴 OPERATOR ACTIONS before submit"), so match by
# containment, not exact string.
SECTION_MARK = "OPERATOR ACTIONS"
UNCHECKED_RE = re.compile(r"^\s*-\s\[ \]\sBLOCKING:\s*(.+)$")


def scan_text(text, label):
    """Return [(label, lineno, item_text)] for unchecked BLOCKING lines under an
    OPERATOR ACTIONS heading."""
    hits = []
    in_section = False
    section_level = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if SECTION_MARK in line.upper():
                in_section = True
                section_level = level
            elif in_section and level <= section_level:
                in_section = False
        elif in_section:
            u = UNCHECKED_RE.match(line)
            if u:
                hits.append((label, lineno, u.group(1).strip()))
    return hits


def scan_dossier(dossier):
    root = Path(dossier)
    if not root.is_dir():
        print(f"presubmit_check: no such dossier folder: {dossier}")
        return 2
    files = sorted(set(root.rglob("review-passes.md")))
    if not files:
        print(f"presubmit_check: OK. No review-passes.md in {dossier} (nothing to block on)")
        return 0
    hits = []
    for f in files:
        hits.extend(scan_text(f.read_text(encoding="utf-8"), str(f)))
    if hits:
        print(f"presubmit_check: BLOCKED. {len(hits)} unchecked BLOCKING item(s). Do not open the browser.")
        for label, lineno, item in hits:
            print(f"  {label}:{lineno}  - [ ] BLOCKING: {item}")
        return 2
    scanned = ", ".join(str(f) for f in files)
    print(f"presubmit_check: OK. No unchecked BLOCKING items ({scanned})")
    return 0


FIXTURE_UNCHECKED = """# review passes
## OPERATOR ACTIONS
- [ ] BLOCKING: clear the retracted answer from the form field
Some prose.
## Another section
- [ ] BLOCKING: outside the section, must NOT count
"""

FIXTURE_CHECKED = """# review passes
## A8. 🔴 OPERATOR ACTIONS before submit
- [x] BLOCKING: re-upload the resume (done)
- [x] BLOCKING: correct the time zone answer (done)
"""


def selftest():
    failures = []
    hits = scan_text(FIXTURE_UNCHECKED, "fixture-unchecked")
    if len(hits) != 1 or "retracted answer" not in hits[0][2]:
        failures.append(f"fixture-unchecked: expected exactly 1 hit inside the section, got {hits}")
    if scan_text(FIXTURE_CHECKED, "fixture-checked"):
        failures.append("fixture-checked: checked items must not fire")
    if failures:
        print("presubmit_check --selftest: FAIL")
        for f in failures:
            print(f"  {f}")
        return 1
    print("presubmit_check --selftest: PASS (unchecked fixture would exit 2; checked fixture exits 0)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "--selftest":
        sys.exit(selftest())
    sys.exit(scan_dossier(sys.argv[1]))
