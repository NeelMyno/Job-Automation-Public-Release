#!/usr/bin/env python3
"""records_check.py: the format gate. Every record row in the shape `.claude/rules/records-format.md` owns.

WHY THIS EXISTS
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
pipeline/inmail-ledger.md (optional), applications/<slug>/application.md of every submitted row,
file names under applications/<slug>/correspondence/ and calls/, ops/DEBT.md rows, the ratified-decisions
table in knowledge-base/11-preferences-and-conventions.md, and ops/HANDOFF.md (one block).

NOT checked: whether a value is TRUE (only its shape); the referrals.md person grammar
(scripts/outreach_format.py owns it); the @OWED-on-interview rule (scripts/commitments.py owns it).
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import records as R  # noqa: E402

try:
    import config as _config_probe  # optional user knobs (scripts/config.py)
except Exception as _e:  # a missing file is fine; a file that will not load is named, never a traceback
    if not (isinstance(_e, ModuleNotFoundError) and _e.name == "config"):
        import traceback as _tb
        _line = _e.lineno if isinstance(_e, SyntaxError) else next(
            (f.lineno for f in reversed(_tb.extract_tb(_e.__traceback__)) if Path(f.filename).name == "config.py"), "?")
        _why = _e.msg if isinstance(_e, SyntaxError) else f"{type(_e).__name__}: {_e}"
        print(f"records_check: not checked, scripts/config.py line {_line}: {_why}. Fix that line and run this again.")
        sys.exit(3)
    _config_probe = None

ROOT = REPO  # the tree being checked; run() sets it (the selftest checks a temp tree)

OWED_OPEN = re.compile(r"@OWED\[")
OWED_OK = re.compile(r"@OWED\[\s*(them|you)\s*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|\?)\s*\|\s*([^\]]*?)\s*\]")
APP_REQUIRED = ("co", "role", "status", "posted", "source", "jd", "apply", "folder", "refs", "next")
NET_REQUIRED = ("name", "role", "status")
DATED_FILE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|undated)-[a-z0-9][a-z0-9.-]*\.[A-Za-z0-9]+$")
TIME = r"(?: ~?\d{1,2}:\d{2} ?[AP]M(?: [A-Z]{2,5})?| \d{1,2}:\d{2}(?: [A-Z]{2,5})?)?"
SUBMITTED_HEAD = re.compile(
    r"^## SUBMITTED (?:\d{4}-\d{2}-\d{2}" + TIME + r"|on or before \d{4}-\d{2}-\d{2}|\(date not recorded\))(?=$|[ ,.;:])", re.M)
NO_SUBMIT_HEAD = re.compile(r"^## NO SUBMIT ON RECORD\b", re.M)
ANSWERS_HEAD = re.compile(
    r"^## Exact form answers \((?:as filled, (?:\d{4}-\d{2}-\d{2}|date not recorded)(?:[,;:] [^\n]*)?|not recorded)\)\s*$",
    re.M)
DEBT_ROW = re.compile(r"^\|\s*(\d{4}-\d\d-\d\d)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*([^|]*?)\s*\|\s*$")
DEBT_STATUS = re.compile(r"^(?:OPEN|CLOSED \d{4}-\d\d-\d\d: \S.*)$")
INMAIL_ROW = re.compile(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(?:\d+|unknown)\s*\|\s*[^|]+\|\s*$")
CLOSED_NEXT = re.compile(r"^\s*CLOSED\b")
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
TRACKING_KEYS = {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "gh_src", "lever-source",
                 "lever-origin", "ref", "referrer", "src", "trk", "_hsenc", "_hsmi"}


def role_key(role: str) -> str:
    """One key per role title: lower case, letters and digits only, any bracketed aside dropped
    ('Line Cook (nights)' and 'line cook' are one role; 'Line Cook' and 'Server' are two)."""
    base = re.sub(r"\s*[(\[].*$", "", (role or "").strip())
    return re.sub(r"[^a-z0-9]+", "", base.casefold())


def posting_key(url: str) -> str:
    """A URL reduced to what names the posting, the same reduction the crawler's dedup uses
    (pipeline/job-crawler/crawl.py same_posting_key): no scheme, host lower-cased without `www.`,
    no trailing slash, no fragment, no `utm_*` or other tracking keys, the rest sorted."""
    from urllib.parse import urlsplit, parse_qsl, urlencode
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "//" + u.lstrip("/")
    p = urlsplit(u)
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    q = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
               if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS)
    return host + p.path.rstrip("/") + ("?" + urlencode(q) if q else "")


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
        # the currency gate: a dead thread cannot hold an open action
        open_owed = OWED_OK.findall(nxt)
        if st in R.DEAD_APP and open_owed:
            pr.append(f"{len(open_owed)} open @OWED on a {st} row: close each as @OWED-closed[...] in the same edit")
        elif CLOSED_NEXT.match(nxt) and any(o[0] == "you" for o in open_owed):
            pr.append("next begins CLOSED yet holds an open @OWED[you|...]: close it as @OWED-closed[...]")
        if "note" in r:
            pr.append("`note` key (APPLICATIONS uses `notes`)")
        for k in r:
            if k[:1].isupper():
                pr.append(f"capitalised key `{k}`")
        T.units["tracker APPLICATIONS"] += 1
        if pr:
            T.bad["tracker APPLICATIONS"] += 1
            F.extend(Finding("tracker", where, p) for p in pr)
    # one posting, one row (records-format section 1): two rows with the same `link` (the crawler's per-posting
    # URL), or the same `jd`/`apply` URL and the same role. One careers page can list two roles: that is two rows.
    seen_url: dict = {}
    for r in t.apps:
        here = f"{R.s(r.get('co'))[:40]} | {R.s(r.get('role'))[:50]}"
        role = role_key(R.s(r.get("role")))
        kinds: dict = {}
        for f in ("jd", "apply", "link"):
            k = posting_key(R.s(r.get(f)))
            if k:
                kinds.setdefault(k, set()).add("link" if f == "link" else "page")
        for k in sorted(kinds):
            earlier = seen_url.setdefault(k, [])
            match = next((e for e in earlier
                          if "link" in kinds[k] or "link" in e[2] or (role and role == e[1])), None)
            if match:
                F.append(Finding("tracker", f"APPLICATIONS {here}",
                                 f"same posting as the row {match[0]} (jd/apply/link {k}): one posting gets one row"))
            earlier.append((here, role, kinds[k]))
    co_states: dict = {}
    for r in t.apps:
        k = R.co_key(R.s(r.get("co")))
        if k:
            co_states.setdefault(k, set()).add(R.s(r.get("status")))
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
            f = R.parse_fu(fu)
            sts = co_states.get(R.co_key(R.s(r.get("company"))))
            if f and f.state != "closed" and sts and sts <= R.DEAD_APP:
                pr.append(f"fu {f.state!r} is open while every application at this company is "
                          f"{'/'.join(sorted(sts))}: close the thread (fu closed) in the same edit")
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


def check_debt(text: str | None, F: list, T: Tally) -> None:
    """ops/DEBT.md: every item is one table row `| YYYY-MM-DD | owner | item | OPEN |`, closed by
    changing the status to `CLOSED YYYY-MM-DD: <what fixed it>`. An item written as a heading or in
    another row shape is invisible to the aging check at session start."""
    if not text:
        return
    for n, line in enumerate(text.splitlines(), 1):
        h = re.match(r"^#{2,6}\s+(.*)", line)
        if h:
            if re.match(r"^\[?20\d\d-\d\d-\d\d", h.group(1)):
                T.units["ops/DEBT.md"] += 1
                T.bad["ops/DEBT.md"] += 1
                F.append(Finding("DEBT", f"line {n}", "a debt item written as a heading; it belongs in a table row"))
            continue
        if not line.startswith("|") or re.match(r"^\|\s*(Opened|-|:)", line):
            continue
        T.units["ops/DEBT.md"] += 1
        m = DEBT_ROW.match(line)
        pr = []
        if not m:
            pr.append("table row is not | YYYY-MM-DD | owner | item | OPEN or CLOSED YYYY-MM-DD: what |")
        else:
            if not m.group(2).strip("* "):
                pr.append("owner cell is empty")
            if not DEBT_STATUS.match(m.group(4).strip()):
                pr.append(f"status cell {m.group(4).strip()[:30]!r} is not OPEN or 'CLOSED YYYY-MM-DD: <what>'")
        if pr:
            T.bad["ops/DEBT.md"] += 1
            F.extend(Finding("DEBT", f"line {n}", p) for p in pr)


def check_kb11(text: str | None, F: list, T: Tally) -> None:
    """knowledge-base/11: every row of the ratified-decisions table has a YYYY-MM-DD date and the same
    number of cells as the table's own header (the shipped table has Date | Decision | Why)."""
    if not text:
        return
    m = re.search(r"^## Ratified decisions.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    width = None
    for line in (m.group(1) if m else "").splitlines():
        if not line.startswith("|"):
            continue
        cells = R.split_cells(line)
        if re.match(r"^\|\s*Date\b", line):
            width = len(cells)
            continue
        if re.match(r"^\|\s*:?-", line):
            continue
        T.units["KB-11 decisions"] += 1
        pr = []
        if not cells or not R.ISO.match(cells[0]):
            pr.append("date cell is not YYYY-MM-DD")
        if width is not None and len(cells) != width:
            pr.append(f"{len(cells)} cells, the table has {width}")
        if pr:
            T.bad["KB-11 decisions"] += 1
            F.extend(Finding("KB-11", line[:60], x) for x in pr)


def check_handoff(text: str | None, F: list, T: Tally) -> None:
    """ops/HANDOFF.md is ONE pointer block, overwritten at each close (the /wave template). A second
    top-level `# ` block means an old handoff was stacked instead of replaced, and a block stamped
    OUTDATED, superseded or CLOSED is a dead handoff left where the next session resumes from."""
    if text is None:
        return
    T.units["ops/HANDOFF.md"] += 1
    body = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    blocks = re.findall(r"^# (.+)$", body, re.M)
    pr = []
    if len(blocks) > 1:
        pr.append(f"{len(blocks)} top-level blocks; it is one block, overwritten at each close")
    if re.search(r"^# .*\b(?:CLOSED|OUTDATED|superseded)\b", body, re.M | re.I):
        pr.append("a block stamped CLOSED, OUTDATED or superseded sits in the resume pointer; overwrite it")
    if pr:
        T.bad["ops/HANDOFF.md"] += 1
        F.extend(Finding("HANDOFF", "ops/HANDOFF.md", x) for x in pr)


# run
SURFACE_OF = (
    (re.compile(r"^pipeline/tracker\.html$"), {"tracker", "dossiers"}),
    (re.compile(r"^pipeline/sent-ledger\.md$"), {"ledger", "tracker"}),
    (re.compile(r"^pipeline/inmail-ledger\.md$"), {"inmail"}),
    (re.compile(r"^applications/[^/]+/"), {"dossiers"}),
    (re.compile(r"^ops/DEBT\.md$"), {"debt"}),
    (re.compile(r"^knowledge-base/11-preferences-and-conventions\.md$"), {"kb11"}),
    (re.compile(r"^ops/HANDOFF\.md$"), {"handoff"}),
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
    want = {"tracker", "ledger", "inmail", "dossiers", "debt", "kb11", "handoff"}
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
    if "debt" in want:
        check_debt(read("ops/DEBT.md"), F, T)
    if "kb11" in want:
        check_kb11(read("knowledge-base/11-preferences-and-conventions.md"), F, T)
    if "handoff" in want:
        check_handoff(read("ops/HANDOFF.md"), F, T)
    return F, T


def summary(T: Tally) -> str:
    L = ["records_check.py: units per surface (conforming / total)"]
    for k in sorted(T.units):
        n = T.units[k]
        L.append(f"  {k:<40} {n - T.bad[k]:>5} / {n:<5}" + (f"  ({T.bad[k]} out of shape)" if T.bad[k] else ""))
    return "\n".join(L)


def _config_guard_cases() -> list:
    """Run a copy of this script beside a config.py that will not load: plain words, its line, exit 3."""
    import shutil
    import subprocess
    import tempfile
    here = Path(__file__).resolve()
    out = []
    for kind, body, word in (("a syntax error", "X = 1\nX = = 2\n", "invalid syntax"),
                             ("a raise at import", "X = 1\nraise RuntimeError('boom')\n", "boom")):
        with tempfile.TemporaryDirectory() as td:
            for p in here.parent.glob("*.py"):
                if p.name != "config.py":
                    shutil.copy(p, td)
            (Path(td) / "config.py").write_text(body, encoding="utf-8")
            r = subprocess.run([sys.executable, str(Path(td) / here.name)], capture_output=True, text=True, timeout=60)
        out.append((f"broken config.py ({kind}): names the line, exit 3, no traceback",
                    r.returncode == 3 and "scripts/config.py line 2" in r.stdout and word in r.stdout
                    and "Traceback" not in r.stdout + r.stderr))
    return out


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
                'folder:"applications/acme-analyst", refs:0, next:"x"},\n'
                '  {co:"Globex", role:"Analyst", status:"lead", posted:"~1 month ago", source:"s", jd:"", apply:"", folder:null, '
                'refs:0, next:"x"},,\n'
                '  {co:"Initech", role:"Analyst", status:"rejected", posted:"unknown", source:"s", jd:"", apply:"", '
                'folder:"initech-analyst", refs:0, applied:"on or before 2026-01-01", next:"@OWED[them|2026-01-09|x"},\n'
                '  {co:"Northwind", role:"Analyst", status:"interview", posted:"unknown", source:"s", jd:"", apply:"", '
                'folder:"applications/northwind-analyst", refs:0, applied:"2026-01-03", '
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
        (r / "pipeline" / "tracker.html").unlink()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([], repo=r)
        c("no tracker: says not checked and exits 3, never CLEAN", (rc, buf.getvalue().strip()) == (3, NO_TRACKER))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--repo", str(r)])
        c("--repo checks that checkout, not this one", (rc, buf.getvalue().strip()) == (3, NO_TRACKER))
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir()
        (r / "ops").mkdir()
        (r / "knowledge-base").mkdir()
        (r / "pipeline" / "tracker.html").write_text(
            '<script>const APPLICATIONS = [\n'
            '  {co:"Umbrella", role:"Charge Nurse", status:"lead", posted:"unknown", source:"s", jd:"", apply:"", '
            'folder:"", refs:0, next:"x"},\n'
            '  {co:"Hooli", role:"Store Manager", status:"lead", posted:"unknown", source:"s", jd:"", apply:"", '
            'folder:"", refs:0, next:"x"},\n'
            '];\nconst NETWORK = [\n];\nconst STATUS = {lead:{}};\nconst NET_STATUS = {lead:{}};\nlet view="apps";</script>')
        (r / "ops" / "DEBT.md").write_text(
            "# Known defects\n\n| Opened | Owner | Item | Status |\n|---|---|---|---|\n"
            "| 2026-01-02 | agent | a gate misreads a dropdown | OPEN |\n"
            "| 2026-01-03 | you | a stale tracker row | CLOSED 2026-01-04: row fixed |\n"
            "| 2026-01-05 | agent | a third item | done |\n"
            "| Jan 6 | agent | a fourth item | OPEN |\n"
            "## 2026-01-07 a prose item\n")
        (r / "knowledge-base" / "11-preferences-and-conventions.md").write_text(
            "## Ratified decisions & taste-call log\n\n| Date | Decision | Why |\n|---|---|---|\n"
            "| 2026-01-15 | one page | screeners skim |\n| 2026-01-16 | only two |\n| soon | x | y |\n\n## Related\n")
        (r / "ops" / "HANDOFF.md").write_text("# HANDOFF, written at close\n## Next\n- x\n\n# HANDOFF, older block\n")
        F6, _ = run(repo=r)
        t6 = "\n".join(str(f) for f in F6)
        c("DEBT: OPEN and 'CLOSED <date>: <what>' rows pass", "line 5" not in t6 and "line 6" not in t6)
        c("DEBT: a 'done' status, an undated row and a heading item are named",
          "line 7: status cell 'done'" in t6 and "line 8: table row is not" in t6 and "line 9: a debt item written as a heading" in t6)
        c("KB-11: a row matching the header width passes", "one page" not in t6)
        c("KB-11: a short row and an undated row are named",
          "2 cells, the table has 3" in t6 and "[KB-11] | soon" in t6)
        c("HANDOFF: two top-level blocks are named", "[HANDOFF]" in t6)
        (r / "ops" / "HANDOFF.md").write_text("# HANDOFF, written at close\n```\n# a fenced example\n```\n## Next\n")
        F7, _ = run(files=["ops/HANDOFF.md"], repo=r)
        c("HANDOFF: one block (a fenced example does not count) passes, --files scopes to it", not F7)
        (r / "ops" / "HANDOFF.md").write_text("# HANDOFF, written by session 12 at 2026-01-05 3:04 PM CST\n## Next\n")
        F71, _ = run(files=["ops/HANDOFF.md"], repo=r)
        c("HANDOFF: the /wave template heading (it names a session) passes", not F71)
        (r / "ops" / "HANDOFF.md").write_text("# HANDOFF, OUTDATED: superseded by the next one\n## Next\n")
        F72, _ = run(files=["ops/HANDOFF.md"], repo=r)
        c("HANDOFF: a single block stamped OUTDATED is named", any("stamped" in f.problem for f in F72))
        F8, _ = run(files=["ops/DEBT.md"], repo=r)
        c("--files ops/DEBT.md checks only DEBT", F8 and all(f.surface == "DEBT" for f in F8))
    with tempfile.TemporaryDirectory() as td:
        # the currency gate: a dead thread cannot hold an open action
        r = Path(td)
        (r / "pipeline").mkdir()
        (r / "applications" / "hooli-nurse").mkdir(parents=True)
        def row(co, role, st, nxt, applied=""):
            ap = f'applied:"{applied}", ' if applied else ""
            return (f'  {{co:"{co}", role:"{role}", status:"{st}", posted:"unknown", source:"s", jd:"", apply:"", folder:"", '
                    f'refs:0, {ap}next:"{nxt}"}},\n')
        def person(nm, co, fu):
            return f'  {{name:"{nm}", company:"{co}", role:"r", status:"active", note:"n", fu:"{fu}"}},\n'
        (r / "pipeline" / "tracker.html").write_text(
            '<script>const APPLICATIONS = [\n'
            + row("Hooli", "Charge Nurse", "ghosted",
                  "@OWED[them|2026-02-01|the panel decision] @OWED-closed[them|2026-01-01|first reply; ghosted 2026-01-20]", "2026-01-02")
            + row("Umbrella", "Electrician", "lead", "CLOSED 2026-01-05: posting gone. @OWED[you|2026-01-08|fill the form]")
            + row("Northwind", "Teacher", "lead", "CLOSED 2026-01-05. @OWED[them|2026-01-08|their reply] @OWED-closed[you|2026-01-02|done]")
            + row("Globex", "Accountant", "rejected", "REJECTED 2026-01-03", "2026-01-01")
            + row("Globex", "Controller", "applied", "waiting", "2026-01-01")
            + row("Initech", "Buyer", "rejected", "@OWED[them|2026-01-09|x", "2026-01-01")
            + row("Acme", "Driver", "ghosted", "GHOSTED 2026-02-20: silent. @OWED-closed[them|2026-02-01|y; ghosted 2026-02-20]", "2026-01-01")
            + '];\nconst NETWORK = [\n'
            + person("Jordan Rivera", "Hooli (Series B)", "them|2026-01-22|message sent")
            + person("Sam Lee", "Hooli", "closed|2026-01-23|ghosted")
            + person("Alex Kim", "Globex", "them|2026-01-22|waiting")
            + person("Alex Kim", "Hooli Bank", "them|2026-01-22|waiting")
            + person("Sam Lee", "Initech", "rest|2026-01-22|parked")
            + '];\nconst STATUS = {lead:{}, active:{}, applied:{}, interview:{}, offer:{}, rejected:{}, passed:{}, ghosted:{}};\n'
            'const NET_STATUS = {lead:{}, active:{}, passed:{}};\nlet view="apps";</script>')
        F9, _ = run(files=["pipeline/tracker.html"], repo=r)
        t9 = "\n".join(str(f) for f in F9)
        c("ghosted is a known status and a submitted one (its applied date is read)",
          "Hooli | Charge Nurse: status" not in t9 and "Hooli | Charge Nurse: submitted row" not in t9)
        c("currency: an open @OWED on a ghosted row is named; an @OWED-closed is not counted",
          "Hooli | Charge Nurse: 1 open @OWED on a ghosted row" in t9)
        c("currency: a ghosted row whose every token is closed passes", "Acme | Driver" not in t9)
        c("currency: a malformed token on a rejected row is the shape finding, not an open @OWED",
          not any("Initech | Buyer" in f.where and "open @OWED" in f.problem for f in F9))
        c("currency: CLOSED plus an open @OWED[you] is named; CLOSED with only @OWED[them] is not this rule",
          "Umbrella | Electrician: next begins CLOSED" in t9 and "Northwind | Teacher: next begins CLOSED" not in t9)
        c("currency: an open fu at a company whose every application is dead is named (a bracketed name matches)",
          "Jordan Rivera | Hooli (Series B): fu 'them' is open" in t9 and "Sam Lee | Initech: fu 'rest' is open" in t9)
        c("currency: a closed fu, a company with one live row, and a person with no application row are not named",
          "Sam Lee | Hooli:" not in t9 and "Alex Kim | Globex" not in t9 and "Alex Kim | Hooli Bank" not in t9)
    with tempfile.TemporaryDirectory() as td:
        # one posting, one row: the same jd/link URL on two rows is named, with both rows
        r = Path(td)
        (r / "pipeline").mkdir()
        x = "https://jobs.umbrella.example/req/3310-staff-accountant"
        def app(co, role, jd, extra=""):
            return (f'  {{co:"{co}", role:"{role}", status:"lead", posted:"unknown", source:"s", jd:"{jd}", '
                    f'apply:"{jd}", folder:"", refs:0, next:"x"{extra}}},\n')
        (r / "pipeline" / "tracker.html").write_text(
            '<script>const APPLICATIONS = [\n'
            + app("Umbrella", "Staff Accountant", x)
            + app("Umbrella", "Staff Accountant (crawler)", "", f', link:"http://www.{x[8:]}/?utm_source=feed#top"')
            + app("Initech", "Line Cook", "https://initech.example/careers/88")
            + app("Initech", "Prep Cook", "https://initech.example/careers/89")
            + app("Hooli", "Cashier", "") + app("Hooli", "Stocker", "")
            + app("Northwind", "Line Cook", "https://northwind.example/jobs")
            + app("Northwind", "Server", "https://northwind.example/jobs/")
            + app("Globex", "Bank Teller", "https://globex.example/careers")
            + app("Globex", "bank teller (part time)", "https://globex.example/careers?utm_source=feed")
            + app("Acme", "Warehouse Associate", "", ', link:"https://acme.example/p/551"')
            + app("Acme", "Forklift Driver", "", ', link:"https://acme.example/p/551"')
            + '];\nconst NETWORK = [\n];\nconst STATUS = {lead:{}};\nconst NET_STATUS = {lead:{}};\nlet view="apps";</script>')
        F10, _ = run(files=["pipeline/tracker.html"], repo=r)
        t10 = "\n".join(str(f) for f in F10)
        c("one posting: a web-search row and a crawler row for one URL are named, both rows given",
          "Umbrella | Staff Accountant (crawler): same posting as the row Umbrella | Staff Accountant " in t10)
        c("one posting: two different URLs and two blank jd fields are clean",
          "Initech" not in t10 and "Hooli" not in t10)
        c("one posting: one careers page, two roles is clean (jd/apply match needs the same role)",
          "Northwind" not in t10)
        c("one posting: one careers page, the same role is named",
          "Globex | bank teller (part time): same posting as the row Globex | Bank Teller " in t10)
        c("one posting: the same crawler link is named whatever the role",
          "Acme | Forklift Driver: same posting as the row Acme | Warehouse Associate " in t10)
        c("one posting: exactly the three duplicates are named", len(F10) == 3)
    for _label, _ok in _config_guard_cases():
        c(_label, _ok)
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


NO_TRACKER = "records_check: no tracker yet: not checked (pipeline/tracker.html is missing)"


def main(argv: list, repo: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--limit", type=int, default=60, help="findings to print (0 = all)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--repo", help="check the records of another checkout (default: this one)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.repo:
        repo = Path(a.repo).resolve()
    needs_tracker = a.files is None or surfaces_for(a.files)[0] & {"tracker", "ledger", "dossiers"}
    if needs_tracker and not (repo / "pipeline" / "tracker.html").is_file():
        print(NO_TRACKER)
        return 3
    F, T = run(a.files, repo=repo)
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
