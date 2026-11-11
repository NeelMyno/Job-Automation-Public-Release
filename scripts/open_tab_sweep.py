#!/usr/bin/env python3
"""Label a list of open browser tabs against your records, so a submitted form is never filled twice.

This script only reads text. It never opens, reads or closes a browser. The agent gets the tab list
from the form-filling browser tool (`list_pages`), passes it here, and closes the flagged tabs itself
with that same tool (`close_page`). Your own everyday browser is never involved.

Labels
  SUBMITTED  the tab is a job whose tracker row is applied/interview/offer/rejected/ghosted, or whose
             dossier has a "## SUBMITTED" heading. Close it; never fill it again.
  CLOSED     every matching tracker row is "passed": the posting was dropped or is gone. Close it.
  OPEN       a tracked job still to do. If a different role at that company went in, the line says
             so, so the two can be told apart.
  NO MATCH   nothing in the tracker points at this tab.

A tab matches a tracker row by a job id in its URL, or by the same page address as a URL on the row,
so any hiring system works, including ones whose URLs carry no long id.

  python3 scripts/open_tab_sweep.py --file tabs.txt     # one URL per line, or pasted tool output
  <tool output> | python3 scripts/open_tab_sweep.py -   # or on stdin, only with an explicit -
  python3 scripts/open_tab_sweep.py --selftest

Exit 0 = no submitted tab open. 1 = a submitted tab is open. 3 = not checked (no tab list or no tracker).
"""
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = os.path.join(ROOT, "pipeline", "tracker.html")
SUBMITTED_STATES = {"applied", "interview", "offer", "rejected", "ghosted"}
URL = re.compile(r"""https?://[^\s"'<>`\]\)]+""", re.I)
# Tail segments that are steps of one posting: the form and its parent are the same job.
FORM_TAILS = {"application", "apply", "applications", "thanks", "thank-you", "confirmation"}


def tab_urls(text):
    """Every URL in the input, in order. Takes a plain list or the browser tool's output as it comes."""
    return [u.rstrip(".,;") for u in URL.findall(text or "")]


def job_ids(url):
    out = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", url))
    out |= set(re.findall(r"(?<![0-9A-Za-z])\d{6,}(?![0-9])", url))
    out |= set(re.findall(r"am9icG9zdD[A-Za-z0-9_-]{10,}", url))  # Gem: the full id, never the shared prefix
    out |= set(re.findall(r"/p/([0-9a-f]{8,}[^/?#]*)", url))      # Breezy
    return out


def page_key(url):
    """Host plus path, without the query, a trailing slash or a form-step tail. None for a bare site root."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    segs = [s for s in parts.path.split("/") if s]
    while segs and segs[-1].lower() in FORM_TAILS:
        segs.pop()
    return f"{host}/{'/'.join(segs)}".lower() if host and segs else None


def tracker_rows(text):
    """The APPLICATIONS rows only; NETWORK rows are people, not jobs."""
    m = re.search(r"const APPLICATIONS\s*=\s*\[(.*?)\n\s*\];", text, re.S)
    if not m:
        return []
    rows = []
    for r in re.findall(r"\{\s*co:.*?(?=\n\s*\{\s*co:|\Z)", m.group(1), re.S):
        co = re.search(r'co:\s*"([^"]*)"', r)
        st = re.search(r'status:\s*"([^"]*)"', r)
        role = re.search(r'role:\s*"([^"]*)"', r)
        folder = re.search(r'folder:\s*"(?:applications/)?([^"]+)"', r)
        rows.append({
            "co": co.group(1) if co else "?",
            "role": role.group(1) if role else "?",
            "status": st.group(1) if st else "?",
            "folder": folder.group(1) if folder else None,
            "urls": URL.findall(r),   # ids are matched only here: a long number in a note is not a job id
            "pages": {k for k in (page_key(u) for u in URL.findall(r)) if k},
        })
    return rows


def has_submitted_heading(folder):
    if not folder:
        return False
    p = os.path.join(ROOT, "applications", folder, "application.md")
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return "\n## SUBMITTED" in "\n" + f.read()
    except OSError:
        return False


def _id_in(job_id, text):
    return re.search(r"(?<![0-9A-Za-z])" + re.escape(job_id) + r"(?![0-9A-Za-z])", text) is not None


def classify(url, rows, heading=has_submitted_heading):
    ids = job_ids(url)
    key = page_key(url)
    hits = [r for r in rows if any(_id_in(i, " ".join(r["urls"])) for i in ids) or (key and key in r["pages"])]
    if any(r["status"] in SUBMITTED_STATES or heading(r["folder"]) for r in hits):
        return "SUBMITTED", hits
    if hits and all(r["status"] == "passed" for r in hits):
        return "CLOSED", hits
    return ("OPEN" if hits else "NO MATCH"), hits


def _company(row):
    return row["co"].split(" (")[0].strip().lower()


def report(tabs, rows, out=print, heading=has_submitted_heading):
    """Prints one line per tab and returns the number of submitted tabs."""
    submitted_cos = {}
    for r in rows:
        if r["status"] in SUBMITTED_STATES:
            submitted_cos.setdefault(_company(r), []).append(r["role"])
    n_sub = n_closed = 0
    for n, url in enumerate(tabs, 1):
        kind, hits = classify(url, rows, heading)
        label = "; ".join(f'{h["co"]} / {h["role"]} / {h["status"]}' for h in hits)
        if kind == "SUBMITTED":
            n_sub += 1
        elif kind == "CLOSED":
            n_closed += 1
        extra = ""
        if kind == "OPEN":
            others = [role for role in submitted_cos.get(_company(hits[0]), []) if role != hits[0]["role"]]
            if others:
                extra = f" (a different role at this company went in: {'; '.join(others)})"
        out(f"{n:3} {kind:9} {label or '-'}{extra} | {url[:100]}")
    out(f"open_tab_sweep: {len(tabs)} tabs, {n_sub} submitted, {n_closed} closed posting.")
    if n_sub or n_closed:
        out("Close the SUBMITTED and CLOSED tabs with the browser tool (close_page). Never fill one of them again.")
    return n_sub


def _read_input(argv):
    if "--file" in argv:
        i = argv.index("--file")
        if i + 1 >= len(argv):
            return None, "--file needs a path."
        try:
            with open(argv[i + 1], encoding="utf-8", errors="replace") as f:
                return f.read(), None
        except OSError as e:
            return None, f"cannot read {argv[i + 1]}: {e.strerror or e}"
    # Never read stdin unasked: an agent's shell can leave it open with nothing coming, and that hangs.
    if "-" not in argv or sys.stdin is None or sys.stdin.isatty():
        return None, ("no tab list given. List the tabs with the browser tool, then run "
                      "open_tab_sweep.py --file <path>, or pipe them in and add - to read stdin.")
    return sys.stdin.read(), None


def selftest():
    tracker = (
        'const APPLICATIONS = [\n'
        '  {co:"Northwind Health", role:"Registered Nurse, ICU", status:"applied", '
        'apply:"https://job-boards.greenhouse.io/northwind/jobs/7700112233", folder:"applications/a"},\n'
        '  {co:"Northwind Health", role:"Charge Nurse", status:"lead", '
        'apply:"https://job-boards.greenhouse.io/northwind/jobs/7700445566", folder:"applications/b"},\n'
        '  {co:"Initech", role:"Staff Accountant", status:"passed", '
        'apply:"https://jobs.ashbyhq.com/initech/1a2b3c4d-1111-4222-8333-444455556666"},\n'
        '  {co:"Acme Schools", role:"Math Teacher", status:"lead", '
        'apply:"https://jobs.gem.com/acme/am9icG9zdDrAAAABBBBCCCCDDDDEEEE", folder:"applications/c"},\n'
        '  {co:"Globex Logistics", role:"Dispatcher", status:"ghosted", '
        'apply:"https://careers.example.com/globex/dispatcher-days/", next:"called 555123 twice", folder:""},\n'
        '  {co:"Hooli Retail", role:"Store Manager", status:"lead", apply:"https://www.example.org/", folder:""},\n'
        '];\n'
        'const NETWORK = [\n'
        '  {co:"Umbrella", name:"Sam Lee", status:"sent", note:"https://careers.example.com/umbrella/electrician"},\n'
        '];\n')
    rows = tracker_rows(tracker)
    no = lambda f: False
    bad = []

    def expect(name, got, want):
        if got != want:
            bad.append((name, got, want))
            print("FAIL", name, "got", got, "want", want)

    expect("only APPLICATIONS rows are read", len(rows), 6)
    for name, url, want in (
        ("a submitted job", "https://job-boards.greenhouse.io/northwind/jobs/7700112233#app", "SUBMITTED"),
        ("another role at that company is still open", "https://job-boards.greenhouse.io/northwind/jobs/7700445566", "OPEN"),
        ("a passed posting, on its form step",
         "https://jobs.ashbyhq.com/initech/1a2b3c4d-1111-4222-8333-444455556666/application", "CLOSED"),
        ("a shared Gem prefix alone is no match", "https://jobs.gem.com/other/am9icG9zdDqZZZZYYYYXXXXWWWW", "NO MATCH"),
        ("a hiring system with no long id matches by page, on its apply step",
         "https://CAREERS.example.com/globex/dispatcher-days/apply?src=board", "SUBMITTED"),
        ("a number inside a note is not a job id", "https://example.net/jobs/555123", "NO MATCH"),
        ("a site root never matches", "https://www.example.org/", "NO MATCH"),
        ("a NETWORK row is not a job", "https://careers.example.com/umbrella/electrician", "NO MATCH"),
        ("a blank tab", "about:blank", "NO MATCH"),
    ):
        expect(name, classify(url, rows, no)[0], want)
    expect("a SUBMITTED heading in the dossier counts",
           classify("https://jobs.gem.com/acme/am9icG9zdDrAAAABBBBCCCCDDDDEEEE", rows, lambda f: f == "c")[0], "SUBMITTED")
    expect("an empty tracker has no rows", tracker_rows("const APPLICATIONS = [\n];\nconst NETWORK = [\n];\n"), [])

    pasted = ("## Pages\n1: https://job-boards.greenhouse.io/northwind/jobs/7700112233 [selected]\n"
              '{"url": "https://careers.example.com/globex/dispatcher-days/"}\nabout:blank\n')
    expect("reads the tool's output as it comes", tab_urls(pasted),
           ["https://job-boards.greenhouse.io/northwind/jobs/7700112233", "https://careers.example.com/globex/dispatcher-days/"])

    lines = []
    n = report(tab_urls(pasted) + ["https://job-boards.greenhouse.io/northwind/jobs/7700445566"], rows, lines.append, no)
    expect("report counts submitted tabs", n, 2)
    expect("report names the different role that went in",
           any("different role" in l and "Registered Nurse" in l for l in lines), True)
    expect("report tells the agent to close with the browser tool", any("close_page" in l for l in lines), True)
    lines = []
    expect("no flagged tab asks for no close", (report(["https://example.net/x"], rows, lines.append, no),
                                                any("close_page" in l for l in lines)), (0, False))

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "tabs.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("https://example.net/a\n")
        expect("--file reads the list", _read_input(["--file", p]), ("https://example.net/a\n", None))
        expect("--file on a missing file says so", _read_input(["--file", os.path.join(td, "nope")])[0], None)
    expect("--file with no path says so", _read_input(["--file"])[1], "--file needs a path.")

    class _OpenPipe:
        """A stdin left open with nothing coming: any read is the hang this guards against."""
        read_called = False

        def isatty(self):
            return False

        def read(self):
            _OpenPipe.read_called = True
            return "https://example.net/from-stdin\n"

    saved_stdin = sys.stdin
    sys.stdin = _OpenPipe()
    try:
        got = _read_input([])
        expect("no argument on an open stdin: usage, and stdin is never read",
               (got[0], "--file <path>" in (got[1] or ""), _OpenPipe.read_called), (None, True, False))
        expect("an explicit - reads stdin", _read_input(["-"]), ("https://example.net/from-stdin\n", None))
    finally:
        sys.stdin = saved_stdin
    print("open_tab_sweep selftest:", "FAIL" if bad else "OK")
    return 1 if bad else 0


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if "--close" in argv:
        print("open_tab_sweep never closes tabs. Close the flagged ones with the browser tool (close_page).")
    if not os.path.isfile(TRACKER):
        print("open_tab_sweep: not checked, there is no pipeline/tracker.html.")
        return 3
    text, err = _read_input(argv)
    if err:
        print("open_tab_sweep: not checked, " + err)
        return 3
    tabs = tab_urls(text)
    if not tabs:
        print("open_tab_sweep: not checked, the input had no web addresses in it.")
        return 3
    with open(TRACKER, encoding="utf-8", errors="replace") as f:
        rows = tracker_rows(f.read())
    return 1 if report(tabs, rows) else 0


if __name__ == "__main__":
    sys.exit(main())
