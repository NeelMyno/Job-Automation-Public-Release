#!/usr/bin/env python3
"""subject_check.py: RETIRED. Kept so old pointers and hooks do not dangle.

This was the founder-email subject-line style gate (a locked "<Role> at <Company> | <hook>"
template). It was retired with every other writing-style check: how writing sounds, subject lines
included, is owned by knowledge-base/17-writing.md and judged by a read-aloud and a fresh reviewer.
The email body still runs scripts/voice_check.py for hard facts and banned phrases.

It checks nothing and always exits 0.

Usage:
  python3 scripts/subject_check.py [anything]   # prints "retired", exit 0
  python3 scripts/subject_check.py --selftest
"""
import sys


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        print("subject_check.py selftest (retired stub)\n")
        print("  PASS retired; nothing to check\n")
        print("SELFTEST OK: 1/1")
        return 0
    print("subject_check: retired; nothing checked (see knowledge-base/17-writing.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
