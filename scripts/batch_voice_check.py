#!/usr/bin/env python3
"""batch_voice_check.py: RETIRED as a gate. Kept so old pointers and hooks do not dangle.

This file used to hold the cross-file SAMENESS detectors (a shared opening skeleton, a verbatim
sentence reused across dossiers). They were removed along with every other writing-style check:
style detectors taught writers to write to the checker, and the output passed while still reading
like a machine. How writing sounds is owned by knowledge-base/17-writing.md. Its gate is a
read-aloud plus a fresh-reviewer pass, not a script. Sameness across a batch is now a rule in that
file: every message is written fresh, even when several go out the same day, and the reviewer reads
the batch side by side.

check(files) is kept as a name for importers and returns no findings.

Usage:
  python3 scripts/batch_voice_check.py [files...]   # prints "retired", exit 0
  python3 scripts/batch_voice_check.py --selftest
"""
from __future__ import annotations
import sys
from pathlib import Path


def check(files: list[Path]) -> list[str]:
    """Retired: always returns no findings (see the module docstring)."""
    return []


def selftest() -> int:
    ok = check([]) == [] and check([Path("does-not-exist.md")]) == []
    print("batch_voice_check.py selftest (retired stub)\n")
    print(f"  {'PASS' if ok else 'FAIL'} check() is retired and returns no findings")
    print()
    print("SELFTEST OK: 1/1" if ok else "SELFTEST FAILED: 1 of 1 wrong")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    print("batch_voice_check: retired; nothing checked. Voice is judged by a read-aloud and a fresh "
          "reviewer against knowledge-base/17-writing.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
