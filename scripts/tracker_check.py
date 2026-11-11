#!/usr/bin/env python3
"""tracker_check.py -- verify pipeline/tracker.html actually RENDERS (its embedded JS parses).

ROOT CAUSE THIS CLOSES
A stray unescaped double-quote inside a row's `next:` field (e.g. an already-escaped quote pair
immediately followed by a bare, un-escaped one) terminates that JS string early and throws a
SyntaxError that kills the whole <script>, so the tracker renders BLANK -- not "missing a row", the
entire page. Nothing else catches this, because every other tool that reads the tracker (a
throughput-style gate, a session-start hook, this repo's own other gate scripts) parses it with
TOLERANT regex / brace parsers that shrug off a JS syntax error. The browser does not shrug. This
runs the real embedded JS through `node --check` -- the same thing the browser's parser does.

Usage:  tracker_check.py [--selftest]
Exit 0 = valid. 2 = broken (prints the line). 3 = not checked (node is not installed); 3 is never a pass.
"""
import contextlib
import io
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
    """(ok, message). Uses `node --check`, the authoritative syntax check. ok is None when node
    is missing: nothing was checked, so it is neither a pass nor a failure."""
    node = shutil.which("node")
    if not node:
        return (None, "node not found (install Node.js from nodejs.org to enable this check)")
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

    # Runs with or without node: pretend node is gone and read what the gate says.
    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "tracker.html"
        page.write_text("<script>var A=[];</script>")
        real_which, shutil.which = shutil.which, lambda _name: None
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = run(page)
        finally:
            shutil.which = real_which
    said = out.getvalue()
    c("no node: exit 3, never a pass", code, 3)
    c("no node: says not checked", "not checked: node not found" in said, True)
    c("no node: no checkmark, no 'valid'", "\u2705" in said or "valid" in said, False)

    if not shutil.which("node"):
        print("\nSELFTEST OK (only the no-node path ran: node not found, so the two JavaScript syntax "
              "cases did not run)" if ok else "\nSELFTEST FAILED")
        return 0 if ok else 1

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


def run(tracker: Path) -> int:
    if not tracker.exists():
        print("❌ no pipeline/tracker.html")
        return 2
    ok, msg = check_js(extract_js(tracker.read_text(errors="ignore")))
    if ok is None:
        print(f"tracker_check: not checked: {msg}")
        return 3
    print(("✅ tracker JS valid -- " if ok else "❌ tracker JS BROKEN (renders blank in the browser) -- ") + msg)
    return 0 if ok else 2


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run(TRACKER))
