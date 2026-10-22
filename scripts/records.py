#!/usr/bin/env python3
"""records.py: ONE reader for the record surfaces (the tracker, the sent-ledger).

WHY THIS EXISTS
---------------
A tracker read by three different parsers (a status regex in one script, a regex that needed `{co:`
first and the `applications/` folder prefix in another, a brace walker in a third) tolerates three
different sets of defects. A row in a shape one parser did not know is neither surfaced nor counted,
so a session asked to "show me everything that went cold" quietly misses most of it. The same goes
for a follow-up state the parser does not recognise.

This module owns the GRAMMARS in code. The SHAPES are owned in prose by
`.claude/rules/records-format.md`; `scripts/records_check.py` is the gate that fails on any row out
of shape; `scripts/cold.py` lists every class of item that can go cold. The @OWED grammar stays with
its owner, scripts/commitments.py; it is re-exported here so callers import one module.

It reads only.

    from records import load_tracker, parse_fu, applied_info, ledger_rows
    python3 scripts/records.py              # what it reads from this repo's records
    python3 scripts/records.py --selftest
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EM_DASH = "\u2014"

# APPLICATIONS
APP_STATUSES = ("lead", "active", "applied", "interview", "offer", "rejected", "passed")
SUBMITTED = frozenset({"applied", "interview", "offer", "rejected"})
LIVE_APP = frozenset({"applied", "interview", "offer", "active"})
DEAD_APP = frozenset({"rejected", "passed"})
PRE_SUBMIT = frozenset({"lead", "active"})
UNKNOWN = "unknown"
# applied: the submit date. Exact, or an upper bound ("on or before": the submit happened that day or
# earlier, so the true age is at least the bound's age), or unknown. "none on record": the row reached
# interview or rejection and no record shows an application submit at all (an interview that came from
# outreach, an inbound process). It is never a cold application.
APPLIED_RE = re.compile(r"^(?:(\d{4}-\d{2}-\d{2})|on or before (\d{4}-\d{2}-\d{2})|unknown|none on record)$")
NO_SUBMIT = "none on record"
POSTED_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|unknown)$")

# NETWORK
NET_STATUSES = ("lead", "active", "passed")
# fu: state|YYYY-MM-DD or ?|what.
#   me     = you owe the next move. Always surfaced.
#   them   = waiting on them since the date. Cold after the nudge threshold (config.FOLLOWUP_DAYS).
#   rest   = the one nudge is spent, or the thread is parked. Cold again after a month (cold.py).
#   closed = the thread is over; nothing owed by anyone. Never surfaced.
FU_STATES = ("me", "them", "rest", "closed")
FU_RE = re.compile(r"^(me|them|rest|closed)\|(\d{4}-\d{2}-\d{2}|\?)\|(.+)$", re.S)
FU_LOOSE = re.compile(r"^([A-Za-z]+)\|([^|]*)\|(.*)$", re.S)


@dataclass
class Fu:
    state: str
    since: date | None   # None = '?' (not on record)
    what: str


def parse_fu(value) -> Fu | None:
    """The fu value as a Fu, or None when it is absent or out of shape (records_check names the latter)."""
    if not isinstance(value, str):
        return None
    m = FU_RE.match(value.strip())
    if not m:
        return None
    try:
        d = None if m.group(2) == "?" else date.fromisoformat(m.group(2))
    except ValueError:
        return None
    return Fu(m.group(1), d, m.group(3).strip())


def applied_info(value) -> tuple[date | None, str]:
    """(date, kind) for an APPLICATIONS `applied` value. kind: exact | upper-bound | unknown | none | missing | bad."""
    if value is None:
        return None, "missing"
    m = APPLIED_RE.match(str(value).strip())
    if not m:
        return None, "bad"
    try:
        if m.group(1):
            return date.fromisoformat(m.group(1)), "exact"
        if m.group(2):
            return date.fromisoformat(m.group(2)), "upper-bound"
    except ValueError:
        return None, "bad"
    return None, ("none" if str(value).strip() == NO_SUBMIT else "unknown")


# the tracker
@dataclass
class Tracker:
    html: str
    apps: list            # APPLICATIONS rows as dicts, in file order (holes dropped)
    net: list             # NETWORK rows as dicts
    app_spans: list       # (start, end) of each APPLICATIONS object in html, aligned with apps
    net_spans: list
    holes: dict           # {"A": n, "N": n}: empty array slots (`,,`)
    parser: str           # "node" | "brace walker"
    status_map: dict
    net_status_map: dict


def _array_region(html: str, name: str) -> tuple[int, int]:
    """(start, end) of the text between `const NAME = [` and its closing `];` line."""
    m = re.search(r"const " + name + r"\s*=\s*\[", html)
    if not m:
        return -1, -1
    e = re.compile(r"\n\s*\];").search(html, m.end())
    return m.end(), (e.start() if e else len(html))


def object_spans(html: str, start: int, end: int) -> tuple[list, int]:
    """Every top-level {...} in html[start:end] as (start, end) offsets, double-quote aware (the tracker's
    values are double-quoted with backslash escapes; keys are bare). Also counts holes: a comma that
    follows another comma with only whitespace between."""
    spans, holes = [], 0
    i = start
    last_comma = False
    while i < end:
        c = html[i]
        if c == "{":
            d, j, instr = 0, i, False
            while j < end:
                ch = html[j]
                if instr:
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == '"':
                        instr = False
                elif ch == '"':
                    instr = True
                elif ch == "{":
                    d += 1
                elif ch == "}":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            spans.append((i, j + 1))
            i = j + 1
            last_comma = False
            continue
        if c == ",":
            if last_comma:
                holes += 1
            last_comma = True
        elif c == "/" and html.startswith("//", i):      # a line comment between rows
            k = html.find("\n", i)
            i = end if k == -1 else k
            continue
        elif not c.isspace():
            last_comma = False
        i += 1
    return spans, holes


_VAL = r'("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|null|true|false)'


def _obj_fallback(text: str) -> dict:
    row = {}
    for km in re.finditer(r'(?:^|[{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*' + _VAL, text):
        v = km.group(2)
        if v.startswith('"'):
            try:
                row[km.group(1)] = json.loads(v)
            except ValueError:
                row[km.group(1)] = v[1:-1]
        elif v == "null":
            row[km.group(1)] = None
        elif v in ("true", "false"):
            row[km.group(1)] = v == "true"
        else:
            row[km.group(1)] = float(v) if "." in v else int(v)
    return row


def find_node() -> str | None:
    node = shutil.which("node")
    if not node:
        for cand in ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"):
            if Path(cand).is_file():
                return cand
    return node


def _node_eval(html: str) -> dict | None:
    """APPLICATIONS, NETWORK, STATUS, NET_STATUS exactly as the page's JS defines them, by node (the
    browser's own parser). None when node is absent or fails."""
    node = find_node()
    if not node:
        return None
    js = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
    i = js.find("const APPLICATIONS")
    if i == -1:
        return None
    k = js.find("\nlet view")
    code = js[i:(k if k != -1 else len(js))]
    names = [n for n in ("STATUS", "NET_STATUS") if re.search(rf"const {n}\s*=", code)]
    code += "\nprocess.stdout.write(JSON.stringify({A:APPLICATIONS,N:NETWORK" + \
        "".join(f",{n}:{n}" for n in names) + "}))"
    try:
        r = subprocess.run([node, "-"], input=code, capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def load_tracker(html: str | None = None, repo: Path = REPO, use_node: bool = True) -> Tracker:
    """The tracker's rows and each row's text span. Values come from node when it can run (exactly what
    the browser sees); otherwise from the brace walker. The spans always come from the walker, and the
    two must agree on the row count or the node values are not trusted."""
    if html is None:
        p = repo / "pipeline" / "tracker.html"
        html = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    sa, ea = _array_region(html, "APPLICATIONS")
    sn, en = _array_region(html, "NETWORK")
    a_sp, a_h = object_spans(html, sa, ea) if sa != -1 else ([], 0)
    n_sp, n_h = object_spans(html, sn, en) if sn != -1 else ([], 0)
    d = _node_eval(html) if use_node else None
    if d is not None:
        A = [x for x in (d.get("A") or []) if x]
        N = [x for x in (d.get("N") or []) if x]
        if len(A) == len(a_sp) and len(N) == len(n_sp):
            return Tracker(html, A, N, a_sp, n_sp, {"A": a_h, "N": n_h}, "node",
                           d.get("STATUS") or {}, d.get("NET_STATUS") or {})
    A = [_obj_fallback(html[s:e]) for s, e in a_sp]
    N = [_obj_fallback(html[s:e]) for s, e in n_sp]
    return Tracker(html, A, N, a_sp, n_sp, {"A": a_h, "N": n_h}, "brace walker", {}, {})


def s(v) -> str:
    """A tracker value as text ('' for null/absent)."""
    return v if isinstance(v, str) else ("" if v is None else str(v))


def folder_of(row: dict) -> str:
    """The row's dossier folder, always with the applications/ prefix, or ''."""
    f = s(row.get("folder")).strip().rstrip("/")
    if f and not f.startswith("applications/"):
        f = "applications/" + f
    return f


# the sent-ledger
LEDGER_COLS = ("date", "recipient", "company", "channel", "message-ref", "copy-state-at-send", "sent-by")
APPLICATION_RECIPIENT = EM_DASH + " (application form)"
NOTE_ONLY_RE = re.compile(r"connection note|connection request", re.I)
FOLLOWUP_RE = re.compile(r"follow[- ]?up|nudge", re.I)
REPLY_RE = re.compile(r"\brepl(?:y|ied|ies)\b|\bREPLIED\b", re.I)
NOT_SENT_RE = re.compile(r"COULD NOT SEND|NOT SENT\b|never sent|did not send", re.I)


def split_cells(line: str) -> list[str]:
    """The cells of one markdown table row; `\\|` inside a cell is an escaped pipe, not a separator."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


@dataclass
class LedgerRow:
    line: int             # 1-based line number in the file
    when: str             # the date cell as written
    recipient: str
    company: str
    channel: str
    ref: str
    state: str
    by: str
    cells: int            # how many cells the line has
    kind: str             # "send" | "application"

    @property
    def day(self) -> date | None:
        try:
            return date.fromisoformat(self.when) if ISO.match(self.when) else None
        except ValueError:
            return None

    @property
    def rest(self) -> str:
        return " ".join((self.ref, self.state, self.by))


def ledger_rows(text: str) -> list[LedgerRow]:
    """Every data row of pipeline/sent-ledger.md, read by POSITION in the canonical column order
    (records_check guards the order). The header row and the separator row are skipped."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.startswith("|"):
            continue
        c = split_cells(line)
        if not c or c[0].lower() == "date" or set(c[0]) <= set("-: "):
            continue
        c += [""] * (7 - len(c))
        kind = "application" if c[1].startswith(EM_DASH + " (application") else "send"
        out.append(LedgerRow(n, c[0], c[1], c[2], c[3], c[4], c[5], " | ".join(c[6:]).strip(" |"),
                             len(split_cells(line)), kind))
    return out


def norm(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip()).casefold()


CREDENTIAL = re.compile(r"^(?:PhD|MBA|MD|MS|MFA|Jr\.?|Sr\.?|II|III|CPA|PMP)$")


def person_key(name: str) -> str:
    """One key per person: the short name (outreach_queue.short_name) with bracketed asides and quoted
    nicknames removed ('Jordan Rivera (CEO)' and 'Jordan Rivera' are one person)."""
    import outreach_queue as oq
    sn = oq.short_name(name or "")
    sn = re.sub(r"\s*\([^)]*\)?", " ", sn)
    sn = re.sub(r'\s*"[^"]*"\s*', " ", sn)
    sn = re.sub(r"\s+'[^']*'\s+", " ", sn)          # Ann 'Annie' Alpha
    sn = re.sub(r",\s*(?:PhD|MBA|MD|MS|MFA|Jr\.?|Sr\.?|II|III|CPA|PMP)\b.*$", "", sn.strip())
    return norm(sn)


def person_keys(name: str) -> set:
    """Every key a name can be matched by: as written, its short name, and person_key."""
    import outreach_queue as oq
    return {k for k in (norm(name), norm(oq.short_name(name or "")), person_key(name)) if k}


# @OWED (owner: commitments.py)
def owed(co: str, text: str, fld: str):
    import commitments as cm
    return cm._parse_owed(co, text, fld)


def selftest() -> int:
    ok = True

    def c(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(("  PASS " if cond else "  FAIL ") + label)
    print("records.py selftest\n")
    c("fu me|date|what parses", (f := parse_fu("me|2026-01-05|reply to Jordan")) and f.state == "me"
      and f.since == date(2026, 1, 5))
    c("fu closed|?|what parses with an unknown date", (f := parse_fu("closed|?|role filled")) and f.since is None)
    c("fu with an unknown state is rejected", parse_fu("done|2026-01-05|x") is None)
    c("fu with a bad date is rejected", parse_fu("them|2026-13-45|x") is None and parse_fu("them|soon|x") is None)
    c("applied exact", applied_info("2026-01-02") == (date(2026, 1, 2), "exact"))
    c("applied upper bound", applied_info("on or before 2026-01-02") == (date(2026, 1, 2), "upper-bound"))
    c("applied unknown / none / missing / bad",
      [applied_info(v)[1] for v in ("unknown", "none on record", None, "last week")] == ["unknown", "none", "missing", "bad"])
    html = ('<script>const APPLICATIONS = [\n'
            '  {co:"Acme", role:"Analyst", status:"applied", folder:"acme-analyst", applied:"2026-01-02", next:"say \\"hi\\""},\n'
            '  // a comment between rows\n'
            '  {co:"Globex", role:"Engineer", status:"lead", folder:""},,\n'
            '];\nconst NETWORK = [\n'
            '  {name:"Jordan Rivera", company:"Initech", status:"active", fu:"them|2026-01-03|DM sent"},\n'
            '];\nconst STATUS = {lead:{}, applied:{}};\nconst NET_STATUS = {active:{}};\nlet view="apps";</script>')
    for use_node in (False, True):
        t = load_tracker(html, use_node=use_node)
        tag = f"[{t.parser}]"
        c(f"{tag} two APPLICATIONS rows and one NETWORK row", len(t.apps) == 2 and len(t.net) == 1)
        c(f"{tag} an empty array slot is counted", t.holes == {"A": 1, "N": 0})
        c(f"{tag} an escaped quote survives", t.apps[0].get("next") == 'say "hi"')
        c(f"{tag} folder_of adds the applications/ prefix", folder_of(t.apps[0]) == "applications/acme-analyst")
    if find_node():
        c("node reads the page's STATUS map", set(load_tracker(html).status_map) == {"lead", "applied"})
    else:
        print("  (node not found: the node path is skipped, the brace walker was tested)")
    led = ("| date | recipient | company | channel | message-ref | copy-state-at-send | sent-by |\n|---|---|---|---|---|---|---|\n"
           "| 2026-01-04 | Jordan Rivera | Initech | Email | r \\| s | ok | me |\n"
           f"| 2026-01-05 | {APPLICATION_RECIPIENT} | Acme | Greenhouse | submitted | x | me |\n")
    rows = ledger_rows(led)
    c("ledger: two data rows, an escaped pipe is not a separator", len(rows) == 2 and rows[0].cells == 7)
    c("ledger: the application row type is recognised", [r.kind for r in rows] == ["send", "application"])
    c("person_key strips a bracketed role and a credential",
      person_key("Jordan Rivera (CEO)") == person_key("Jordan Rivera") == person_key("Jordan Rivera, PhD"))
    c("@OWED is read through commitments.py",
      [(o.owner, o.what) for o in owed("Acme", "@OWED[them|2026-01-09|send the take-home]", "next")]
      == [("them", "send the take-home")])
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    t = load_tracker()
    print(f"records.py: tracker via {t.parser}: {len(t.apps)} APPLICATIONS, {len(t.net)} NETWORK, holes {t.holes}")
    led = (REPO / "pipeline" / "sent-ledger.md")
    rows = ledger_rows(led.read_text(encoding="utf-8", errors="replace")) if led.is_file() else []
    print(f"  sent-ledger: {len(rows)} rows ({sum(r.kind == 'application' for r in rows)} application rows)")
