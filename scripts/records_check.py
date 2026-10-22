#!/usr/bin/env python3
"""records_check.py: the format gate. Every record row in the shape `.claude/rules/records-format.md` owns.

WHY THIS EXISTS
---------------
A row in the wrong shape is a cold item nobody will see: a contacted person with no `fu`, a follow-up
state the parser does not know, a ledger whose columns flipped halfway down, a dossier folder written
without its `applications/` prefix, a submitted application with no submit date anywhere. Each such
row is invisible to some script, so a "show me everything that went cold" sweep misses it. This gate
refuses those rows. Run it at session start, and at the end of any turn that changed a record file
(`--files`), and treat a finding like any other failing gate: fix the row, never this checker.

    python3 scripts/records_check.py                 # every surface; exit 1 on any finding
    python3 scripts/records_check.py --summary       # units and conforming counts per surface
    python3 scripts/records_check.py --files A B     # only the surfaces those files belong to (the end-of-turn gate)
    python3 scripts/records_check.py --selftest

Surfaces: pipeline/tracker.html (APPLICATIONS and NETWORK rows), pipeline/sent-ledger.md,
pipeline/inmail-ledger.md (optional), applications/<slug>/application.md of every submitted row, and
file names under applications/<slug>/correspondence/ and calls/.

NOT checked: whether a value is TRUE (only its shape); the referrals.md person grammar
(scripts/outreach_format.py owns it); the @OWED-on-interview rule (scripts/commitments.py owns it).
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import records as R  # noqa: E402

ROOT = REPO  # the tree being checked; run() sets it (the selftest checks a temp tree)

OWED_OPEN = re.compile(r"@OWED\[")
OWED_OK = re.compile(r"@OWED\[\s*(them|you)\s*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|\?)\s*\|\s*([^\]]*?)\s*\]")
APP_REQUIRED = ("co", "role", "status", "posted", "source", "jd", "apply", "folder", "refs", "everify", "next")
NET_REQUIRED = ("name", "role", "status")
DATED_FILE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|undated)-[a-z0-9][a-z0-9.-]*\.[A-Za-z0-9]+$")
TIME = r"(?: ~?\d{1,2}:\d{2} ?[AP]M(?: [A-Z]{2,5})?| \d{1,2}:\d{2}(?: [A-Z]{2,5})?)?"
SUBMITTED_HEAD = re.compile(
    r"^## SUBMITTED (?:\d{4}-\d{2}-\d{2}" + TIME + r"|on or before \d{4}-\d{2}-\d{2}|\(date not recorded\))(?=$|[ ,.;:])", re.M)
NO_SUBMIT_HEAD = re.compile(r"^## NO SUBMIT ON RECORD\b", re.M)
ANSWERS_HEAD = re.compile(
    r"^## Exact form answers \((?:as filled, (?:\d{4}-\d{2}-\d{2}|date not recorded)(?:[,;:] [^\n]*)?|not recorded)\)\s*$",
    re.M)
INMAIL_ROW = re.compile(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(?:\d+|unknown)\s*\|\s*[^|]+\|\s*$")
PLACEHOLDER_ROW = re.compile(r"^\|\s*\[[^\]]*\]\s*\|")      # a template row: | [YYYY-MM-DD] | [N] | ... |
NOT_A_PERSON = re.compile(r"\bteam\b|recruiting|talent acquisition|hiring|no-?reply|careers|jobs@|@|\bform\b|^" + R.EM_DASH,
                          re.I)


@dataclass
class Finding:
    surface: str
    where: str
    problem: str

    def __str__(self):
        return f"  [{self.surface}] {self.where}: {self.problem}"


@dataclass
class Tally:
    units: collections.Counter = field(default_factory=collections.Counter)
    bad: collections.Counter = field(default_factory=collections.Counter)


def _person_parts(recipient: str) -> list[str]:
    """The people a ledger recipient cell names ('Ann Alpha + Bob Beta', 'Ann Alpha, Bob Beta')."""
    import outreach_queue as oq
    cell = re.sub(r"\s*\((?:addressed|cc|surname|\+)[^)]*\)?", "", recipient or "")
    parts = []
    for p in re.split(r"\s+\+\s+|\s+&\s+|,\s+(?=[A-Z])", cell):
        if not p.strip():
            continue
        if parts and R.CREDENTIAL.match(p.strip()):      # "MJ Lee, PhD": a credential, not a second person
            continue
        parts.append(p)
    return [oq.short_name(p) for p in parts]


def is_person(name: str) -> bool:
    import outreach_queue as oq
    n = name.strip()
    return bool(n) and not NOT_A_PERSON.search(n) and oq.is_queue_person(n)


def net_index(t: R.Tracker) -> dict:
    """Every person key of every NETWORK row -> that row."""
    idx = {}
    for r in t.net:
        for k in R.person_keys(R.s(r.get("name"))):
            idx.setdefault(k, r)
    return idx


def ledger_people(rows: list) -> dict:
    """person key -> [LedgerRow] for every send row (application rows and unsent rows excluded)."""
    out: dict = {}
    for lr in rows:
        if lr.kind != "send":
            continue
        if R.NOT_SENT_RE.search(lr.state + " " + lr.by):
            continue
        for p in _person_parts(lr.recipient):
            if is_person(p):
                out.setdefault(R.person_key(p), []).append(lr)
    return out


# surfaces
def check_tracker(t: R.Tracker, led: list, F: list, T: Tally) -> None:
    S = set(t.status_map) or set(R.APP_STATUSES)
    if t.holes["A"] or t.holes["N"]:
        F.append(Finding("tracker", "arrays", f"empty array slot(s) `,,`: APPLICATIONS {t.holes['A']}, NETWORK {t.holes['N']}"))
    for r in t.apps:
        where = f"APPLICATIONS {R.s(r.get('co'))[:40]} | {R.s(r.get('role'))[:50]}"
        pr = []
        for k in APP_REQUIRED:
            if k not in r:
                pr.append(f"missing `{k}`")
        st = R.s(r.get("status"))
        if st not in S:
            pr.append(f"status {st!r} not in the page's STATUS map")
        if not R.POSTED_RE.match(R.s(r.get("posted"))):
            pr.append(f"posted {r.get('posted')!r} is not YYYY-MM-DD or unknown")
        f = r.get("folder")
        if not isinstance(f, str):
            pr.append("folder is not a string (null)")
        elif f and not f.startswith("applications/"):
            pr.append(f"folder {f!r} lacks the applications/ prefix")
        elif f and not (ROOT / f.rstrip("/")).is_dir():
            pr.append(f"folder {f!r} does not exist")
        if st in R.SUBMITTED:
            _, kind = R.applied_info(r.get("applied"))
            if kind == "missing":
                pr.append("submitted row with no `applied` date field")
            elif kind == "bad":
                pr.append(f"applied {r.get('applied')!r} is not YYYY-MM-DD, 'on or before YYYY-MM-DD', unknown or 'none on record'")
        elif "applied" in r and R.applied_info(r.get("applied"))[1] == "bad":
            pr.append(f"applied {r.get('applied')!r} out of shape")
        nxt = R.s(r.get("next"))
        if len(OWED_OPEN.findall(nxt)) != len(OWED_OK.findall(nxt)):
            pr.append("next: malformed @OWED token")
        if "note" in r:
            pr.append("`note` key (APPLICATIONS uses `notes`)")
        for k in r:
            if k[:1].isupper():
                pr.append(f"capitalised key `{k}`")
        T.units["tracker APPLICATIONS"] += 1
        if pr:
            T.bad["tracker APPLICATIONS"] += 1
            F.extend(Finding("tracker", where, p) for p in pr)
    NS = set(t.net_status_map) or set(R.NET_STATUSES)
    sent_to = ledger_people(led)
    for r in t.net:
        nm = R.s(r.get("name"))
        where = f"NETWORK {nm[:40]} | {R.s(r.get('company'))[:40]}"
        pr = []
        for k in NET_REQUIRED:
            if k not in r:
                pr.append(f"missing `{k}`")
        if "event" not in r and "howMet" not in r and "company" not in r:
            pr.append("missing `company`")
        if R.s(r.get("status")) not in NS:
            pr.append(f"status {r.get('status')!r} not in the page's NET_STATUS map")
        fu = r.get("fu")
        if fu is not None:
            if R.parse_fu(fu) is None:
                m = R.FU_LOOSE.match(R.s(fu))
                pr.append(f"fu {R.s(fu)[:40]!r}: " + (f"state {m.group(1)!r} is not me|them|rest|closed"
                                                      if m and m.group(1) not in R.FU_STATES else
                                                      "not state|YYYY-MM-DD or ?|what"))
            if len(OWED_OPEN.findall(R.s(fu))) != len(OWED_OK.findall(R.s(fu))):
                pr.append("fu: malformed @OWED token")
        elif R.person_keys(nm) & set(sent_to):
            pr.append("the sent-ledger shows a message to this person; the row has no `fu`")
        T.units["tracker NETWORK"] += 1
        if pr:
            T.bad["tracker NETWORK"] += 1
            F.extend(Finding("tracker", where, p) for p in pr)
    idx = net_index(t)
    for p, lrs in sorted(sent_to.items()):
        if p not in idx:
            F.append(Finding("tracker", f"NETWORK (none) for {lrs[0].recipient[:50]}",
                             f"the sent-ledger shows a message (line {lrs[0].line}) and no NETWORK row exists"))
            T.bad["ledgered people with no NETWORK row"] += 1
        T.units["ledgered people with no NETWORK row"] += 1


def check_ledger(text: str, t: R.Tracker, F: list, T: Tally) -> list:
    rows = R.ledger_rows(text)
    people = set(net_index(t))
    companies = {R.norm(R.s(r.get("co"))) for r in t.apps} | {R.norm(R.s(r.get("company"))) for r in t.net}
    companies -= people
    for lr in rows:
        pr = []
        if not R.ISO.match(lr.when):
            pr.append(f"date {lr.when!r} is not YYYY-MM-DD")
        if lr.cells != 7:
            pr.append(f"{lr.cells} cells, the schema has 7")
        if lr.kind == "application":
            if lr.recipient != R.APPLICATION_RECIPIENT:
                pr.append(f"application row recipient {lr.recipient!r} is not exactly {R.APPLICATION_RECIPIENT!r}")
        else:
            rc, co = R.norm(lr.recipient), R.norm(lr.company)
            if "(application)" in lr.company or lr.company.startswith(R.EM_DASH):
                pr.append("an application submit written in the send shape (company in the recipient cell)")
            elif rc in companies and co in people:
                pr.append("flipped columns: company in the recipient cell, person in the company cell")
            elif re.search(r"APPLICATION SUBMITTED", lr.channel) and (rc == co or lr.recipient.startswith(R.EM_DASH)):
                pr.append("an application submit written as a send row")
        T.units["sent-ledger"] += 1
        if pr:
            T.bad["sent-ledger"] += 1
            F.extend(Finding("sent-ledger", f"line {lr.line}", p) for p in pr)
    return rows


def check_inmail(text: str | None, F: list, T: Tally) -> None:
    """The InMail ledger is optional (only for a paid tier with a monthly allotment). Template rows in
    square brackets are skipped; a filled row must be in shape."""
    if not text:
        return
    m = re.search(r"^## Current balance[^\n]*\n(?:[ \t]*\n)*((?:\|.*\n?)+)", text, re.M)
    if not m:
        F.append(Finding("inmail-ledger", "balance table", "no '## Current balance' table"))
        return
    for line in m.group(1).splitlines()[2:]:
        if PLACEHOLDER_ROW.match(line):
            continue
        T.units["inmail-ledger"] += 1
        if not INMAIL_ROW.match(line):
            T.bad["inmail-ledger"] += 1
            F.append(Finding("inmail-ledger", line[:60], "not | YYYY-MM-DD | <credits> or unknown | <source> |"))


def submitted_folders(t: R.Tracker) -> dict:
    out: dict = {}
    for r in t.apps:
        if R.s(r.get("status")) in R.SUBMITTED:
            f = R.folder_of(r)
            if f:
                out.setdefault(f, []).append(r)
    return out


def check_dossiers(t: R.Tracker, F: list, T: Tally, only: set | None = None) -> None:
    for f, rows in sorted(submitted_folders(t).items()):
        if only is not None and f not in only:
            continue
        a = ROOT / f / "application.md"
        T.units["application.md (submitted)"] += 1
        pr = []
        if not a.is_file():
            pr.append("submitted row, no application.md")
        else:
            txt = a.read_text(encoding="utf-8", errors="replace")
            if all(R.applied_info(r.get("applied"))[1] == "none" for r in rows):
                if not NO_SUBMIT_HEAD.search(txt):
                    pr.append("applied is 'none on record', and there is no '## NO SUBMIT ON RECORD' heading")
                elif SUBMITTED_HEAD.search(txt):
                    pr.append("applied is 'none on record', yet a '## SUBMITTED' heading asserts a submit")
            elif not SUBMITTED_HEAD.search(txt):
                pr.append("no '## SUBMITTED <date | on or before date | (date not recorded)>' heading")
            if not ANSWERS_HEAD.search(txt) and not NO_SUBMIT_HEAD.search(txt):
                pr.append("no '## Exact form answers (as filled, <date>)' or '(not recorded)' heading")
        if pr:
            T.bad["application.md (submitted)"] += 1
            F.extend(Finding("application.md", f + "/application.md", p) for p in pr)
    apps_dir = ROOT / "applications"
    if not apps_dir.is_dir():
        return
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir() or (only is not None and f"applications/{d.name}" not in only):
            continue
        if d.name.startswith(("TEMPLATE-", "EXAMPLE-")):
            continue
        for sub in ("correspondence", "calls"):
            sd = d / sub
            if not sd.is_dir():
                continue
            for x in sorted(sd.iterdir()):
                if x.name.startswith(".") or x.name == "README.md":
                    continue
                T.units["correspondence/ and calls/ names"] += 1
                if x.is_dir() or not DATED_FILE.match(x.name):
                    T.bad["correspondence/ and calls/ names"] += 1
                    F.append(Finding("file name", f"applications/{d.name}/{sub}/{x.name}",
                                     "not YYYY-MM-DD-<lowercase-slug>.<ext> or undated-<slug>.<ext>"))


# run
SURFACE_OF = (
    (re.compile(r"^pipeline/tracker\.html$"), {"tracker", "dossiers"}),
    (re.compile(r"^pipeline/sent-ledger\.md$"), {"ledger", "tracker"}),
    (re.compile(r"^pipeline/inmail-ledger\.md$"), {"inmail"}),
    (re.compile(r"^applications/[^/]+/"), {"dossiers"}),
)


def surfaces_for(files: list) -> tuple[set, set]:
    want, folders = set(), set()
    for f in files:
        for rx, ss in SURFACE_OF:
            if rx.search(f):
                want |= ss
        m = re.match(r"^(applications/[^/]+)/", f)
        if m:
            folders.add(m.group(1))
    return want, folders


def run(files: list | None = None, repo: Path = REPO) -> tuple[list, Tally]:
    global ROOT
    ROOT = repo
    F: list = []
    T = Tally()
    want = {"tracker", "ledger", "inmail", "dossiers"}
    only = None
    if files is not None:
        want, folders = surfaces_for(files)
        if "dossiers" in want and not any(f == "pipeline/tracker.html" for f in files):
            only = folders
        if not want:
            return F, T

    def read(rel):
        p = repo / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    t = R.load_tracker(repo=repo) if want & {"tracker", "ledger", "dossiers"} else None
    led = []
    if want & {"ledger", "tracker"}:
        led_text = read("pipeline/sent-ledger.md") or ""
        led = check_ledger(led_text, t, F, T) if "ledger" in want else R.ledger_rows(led_text)
    if "tracker" in want:
        check_tracker(t, led, F, T)
    if "inmail" in want:
        check_inmail(read("pipeline/inmail-ledger.md"), F, T)
    if "dossiers" in want:
        check_dossiers(t, F, T, only)
    return F, T


def summary(T: Tally) -> str:
    L = ["records_check.py: units per surface (conforming / total)"]
    for k in sorted(T.units):
        n = T.units[k]
        L.append(f"  {k:<40} {n - T.bad[k]:>5} / {n:<5}" + (f"  ({T.bad[k]} out of shape)" if T.bad[k] else ""))
    return "\n".join(L)


def selftest() -> int:
    import tempfile
    ok = True

    def c(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(("  PASS " if cond else "  FAIL ") + label)
    print("records_check.py selftest (synthetic records)\n")
    D = R.EM_DASH
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir()
        (r / "applications" / "acme-analyst" / "correspondence").mkdir(parents=True)
        (r / "applications" / "northwind-analyst").mkdir(parents=True)
        (r / "applications" / "TEMPLATE-company-role" / "correspondence").mkdir(parents=True)
        (r / "applications" / "TEMPLATE-company-role" / "correspondence" / "README.md").write_text("x")
        (r / "applications" / "TEMPLATE-company-role" / "correspondence" / "Notes.md").write_text("x")
        html = ('<script>const APPLICATIONS = [\n'
                '  {co:"Acme", role:"Analyst", status:"applied", posted:"2026-01-01", source:"s", jd:"", apply:"", '
                'folder:"applications/acme-analyst", refs:0, everify:"?", next:"x"},\n'
                '  {co:"Globex", role:"Analyst", status:"lead", posted:"~1 month ago", source:"s", jd:"", apply:"", folder:null, '
                'refs:0, everify:"?", next:"x"},,\n'
                '  {co:"Initech", role:"Analyst", status:"rejected", posted:"unknown", source:"s", jd:"", apply:"", '
                'folder:"initech-analyst", refs:0, everify:"?", applied:"on or before 2026-01-01", next:"@OWED[them|2026-01-09|x"},\n'
                '  {co:"Northwind", role:"Analyst", status:"interview", posted:"unknown", source:"s", jd:"", apply:"", '
                'folder:"applications/northwind-analyst", refs:0, everify:"?", applied:"2026-01-03", '
                'next:"@OWED[you|2026-01-20|send availability]"},\n'
                '];\nconst NETWORK = [\n'
                '  {name:"Ann Alpha", company:"Acme", role:"r", status:"active", note:"n", fu:"done|2026-01-07|x"},\n'
                '  {name:"Bob Beta", company:"Acme", role:"r", status:"active", note:"n"},\n'
                '  {name:"Cara Cee", company:"Acme", role:"r", status:"active", note:"n", fu:"closed|?|thread over"},\n'
                '  {name:"Jordan Rivera", company:"Fathom", role:"r", status:"active", note:"n", fu:"me|2026-01-08|reply"},\n'
                '];\nconst STATUS = {lead:{}, active:{}, applied:{}, interview:{}, offer:{}, rejected:{}, passed:{}};\n'
                'const NET_STATUS = {lead:{}, active:{}, passed:{}};\nlet view="apps";</script>')
        (r / "pipeline" / "tracker.html").write_text(html)
        (r / "pipeline" / "sent-ledger.md").write_text(
            "| date | recipient | company | channel | message-ref | copy-state-at-send | sent-by |\n|---|---|---|---|---|---|---|\n"
            "| 2026-01-02 | Bob Beta | Acme | LinkedIn connection note | r | ok | me |\n"
            "| 2026-01-03 | Acme | Ann Alpha | DM | r | ok | me |\n"
            f"| 2026-01-04 | Acme | {D} (application) | Greenhouse | SUBMITTED | x |\n"
            "| 2026-01-05 | Dee Delta | Mirror | DM | r \\| s | ok | me |\n"
            f"| 2026-01-06 | {D} (application form) | Acme | Greenhouse | SUBMITTED | x | me |\n"
            "| 2026-01-07 | Jordan Rivera (CEO) | Fathom | Email | r | ok | me |\n")
        (r / "pipeline" / "inmail-ledger.md").write_text(
            "## Current balance and refill schedule\n\n| As of | Credits left | Source |\n|---|---|---|\n"
            "| [YYYY-MM-DD] | [N] | [how you know] |\n| 2026-01-01 | **2** | me |\n| 2026-01-10 | 12 | me, first-hand |\n\n")
        (r / "applications" / "acme-analyst" / "application.md").write_text("# Acme\n**Status: SUBMITTED 2026-01-06**\n")
        (r / "applications" / "northwind-analyst" / "application.md").write_text(
            "# Northwind\n## SUBMITTED 2026-01-03 9:04 PM CST, from the agent-filled tab\n"
            "## Exact form answers (as filled, 2026-01-03)\n- x\n")
        (r / "applications" / "acme-analyst" / "correspondence" / "2026-01-09-ann-nudge-DRAFT.md").write_text("x")
        (r / "applications" / "acme-analyst" / "correspondence" / "undated-reply.md").write_text("x")
        F, T = run(repo=r)
        txt = "\n".join(str(f) for f in F)
        c("an empty array slot is named", "empty array slot" in txt)
        c("a submitted row with no applied field is named", "Acme | Analyst: submitted row with no `applied`" in txt)
        c("'on or before' is a valid applied value", "applied 'on or before" not in txt)
        c("free-text posted is named", "posted '~1 month ago'" in txt)
        c("null folder and a bare folder are named", "folder is not a string" in txt and "lacks the applications/ prefix" in txt)
        c("a malformed @OWED is named", "malformed @OWED" in txt)
        c("a well-formed @OWED[you|...] passes", "Northwind" not in txt)
        c("fu state 'done' is named (only me|them|rest|closed)", "state 'done'" in txt)
        c("fu 'closed|?|...' is valid", "Cara Cee" not in txt)
        c("a ledgered person with no fu is named (Bob Beta)", "Bob Beta | Acme: the sent-ledger shows a message" in txt)
        c("a ledgered person with no NETWORK row is named (Dee Delta)", "NETWORK (none) for Dee Delta" in txt)
        c("'Jordan Rivera (CEO)' in the ledger is the Jordan Rivera row", "Jordan" not in txt)
        c("flipped ledger columns are named", "line 4: flipped columns" in txt)
        c("an application row in the send shape is named",
          "line 5: an application submit written in the send shape" in txt or "line 5: 6 cells" in txt)
        c("an escaped pipe is not a cell separator (line 6 has 7 cells)", "[sent-ledger] line 6:" not in txt)
        c("a canonical application row passes", "[sent-ledger] line 7:" not in txt)
        c("a bold inmail balance is out of shape, a plain one and a template row pass",
          "| 2026-01-01 | **2**" in txt and "| 2026-01-10 | 12" not in txt and "[YYYY-MM-DD]" not in txt)
        c("a non-heading SUBMITTED line is named", "acme-analyst/application.md: no '## SUBMITTED" in txt)
        c("a missing answers heading is named", "acme-analyst/application.md: no '## Exact form answers" in txt)
        c("a SUBMITTED heading with a local time and free text passes", "northwind-analyst/application.md" not in txt)
        c("an uppercase -DRAFT name is named, undated- passes",
          "nudge-DRAFT.md" in txt and "undated-reply.md" not in txt)
        c("TEMPLATE- and EXAMPLE- folders are not records", "TEMPLATE-company-role" not in txt)
        F2, _ = run(files=["pipeline/inmail-ledger.md"], repo=r)
        c("--files limits the check to the surfaces those files belong to",
          F2 and all(f.surface == "inmail-ledger" for f in F2))
        F3, _ = run(files=["scripts/x.py"], repo=r)
        c("a non-record file checks nothing", not F3)
        (r / "pipeline" / "inmail-ledger.md").unlink()
        F4, _ = run(files=["pipeline/inmail-ledger.md"], repo=r)
        c("a missing (optional) InMail ledger is not a finding", not F4)
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir()
        (r / "pipeline" / "tracker.html").write_text(
            '<script>const APPLICATIONS = [\n];\nconst NETWORK = [\n];\nconst STATUS = {lead:{}};\n'
            'const NET_STATUS = {lead:{}};\nlet view="apps";</script>')
        F5, _ = run(repo=r)
        c("an empty tracker with no ledger is CLEAN", not F5)
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--limit", type=int, default=60, help="findings to print (0 = all)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    F, T = run(a.files)
    if a.summary:
        print(summary(T))
    if F:
        by = collections.Counter(f.surface for f in F)
        print(f"records_check: {len(F)} finding(s): " + ", ".join(f"{k} {v}" for k, v in by.most_common()))
        for f in (F if not a.limit else F[:a.limit]):
            print(f)
        if a.limit and len(F) > a.limit:
            print(f"  ... +{len(F) - a.limit} more (--limit 0 prints all)")
        print("  Shapes: .claude/rules/records-format.md. Fix the row, never this checker.")
        return 1
    print("records_check: CLEAN" + ("" if a.summary else f" ({sum(T.units.values())} units)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
