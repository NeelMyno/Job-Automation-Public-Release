#!/usr/bin/env python3
"""tracker_check.py -- verify pipeline/tracker.html actually RENDERS (its embedded JS parses).

ROOT CAUSE THIS CLOSES
-----------------------
A stray unescaped double-quote inside a row's `next:` field (e.g. an already-escaped quote pair
immediately followed by a bare, un-escaped one) terminates that JS string early and throws a
SyntaxError that kills the whole <script>, so the tracker renders BLANK -- not "missing a row", the
entire page. Nothing else catches this, because every other tool that reads the tracker (a
throughput-style gate, a session-start hook, this repo's own other gate scripts) parses it with
TOLERANT regex / brace parsers that shrug off a JS syntax error. The browser does not shrug. This
runs the real embedded JS through `node --check` -- the same thing the browser's parser does.

Usage:  tracker_check.py [--selftest]
Exit 0 = valid (or node unavailable -- reported, never a false fail). 2 = broken (prints the line).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRACKER = REPO / "pipeline" / "tracker.html"


def extract_js(html: str) -> str:
    return "\n;\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))


def check_js(js: str):
    """(ok, message). Uses `node --check`, the authoritative syntax check, when node exists."""
    node = shutil.which("node")
    if not node:
        return (True, "node not found -- skipped (install node to enable render checking)")
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
            path = f.name
        p = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=25)
        if p.returncode == 0:
            return (True, "valid")
        err = [l.strip() for l in p.stderr.splitlines() if "SyntaxError" in l or re.search(r"\.js:\d+", l)]
        return (False, " | ".join(err[:2]) or (p.stderr[:200].strip()))
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def selftest() -> int:
    print("tracker_check.py selftest\n")
    ok = True

    def c(desc, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'} {desc}: got {got} want {want}")

    if not shutil.which("node"):
        print("  (node not on PATH -- cannot run selftest assertions; the gate degrades to a no-op)")
        print("\nSELFTEST OK (skipped, node absent)")
        return 0

    # A valid row with properly escaped quotes must pass.
    good = 'var A=[{co:"Acme Corp", next:"APPLIED, said \\"hello\\" and moved on"}];'
    # The exact failure shape this gate exists to catch: an escaped-quote pair immediately
    # followed by a bare, UNescaped quote plus more text -- the string ends early and the parser
    # throws.
    bad = 'var A=[{co:"Acme Corp", next:"applied \\"ok\\""unable to apply... later"}];'
    c("valid escaped-quote row passes", check_js(good)[0], True)
    c("stray unescaped quote is caught", check_js(bad)[0], False)

    print("\nSELFTEST OK" if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if not TRACKER.exists():
        print("❌ no pipeline/tracker.html")
        sys.exit(2)
    ok, msg = check_js(extract_js(TRACKER.read_text(errors="ignore")))
    print(("✅ tracker JS valid -- " if ok else "❌ tracker JS BROKEN (renders blank in the browser) -- ") + msg)
    sys.exit(0 if ok else 2)
