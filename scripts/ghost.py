#!/usr/bin/env python3
"""ghost.py: marks an application `ghosted` when the company has gone silent.

WHY THIS EXISTS
A job search produces companies that simply stop answering. With no finished state for that, the row
stays `interview` or `applied` forever, its @OWED[them] stays open, and every view keeps listing it as
live. So a company still silent GHOST_DAYS after its chase date is marked ghosted by itself. If it
replies, the agent reopens the row (.claude/rules/records-format.md section 1).

THE RULE (every condition must hold; any doubt leaves the row alone)
  - status applied, interview or offer;
  - its newest open @OWED[them] chase date is GHOST_DAYS (scripts/config.py, default 14) or more days past;
  - no open @OWED[you] on the row, and no NETWORK person at that company with fu "me|...";
  - the row's `next` does not say "no auto-ghost" (your switch to keep a row live);
  - nothing dated after that chase date: no correspondence/ or calls/ file in any dossier at that company,
    no sent-ledger row, no paid-message ledger row, no NETWORK fu at that company, no ISO date in the row's
    own `next` text.
Companies match by records.co_key ("Acme (Series B)" is "Acme").

WHAT A GHOSTING DOES (ghost_html)
  - status becomes ghosted; `next` gains a leading "GHOSTED <date>: <why>." sentence;
  - every open @OWED[...] on the row becomes @OWED-closed[...], its text kept, "; ghosted <date>" appended;
  - every open fu at that company is closed, unless the company has another live application row: then the
    thread may be that row's, and it stays open and is reported as held.

WHERE IT RUNS: `scripts/hooks.py --session-start` calls session_lines(). It re-reads the tracker just before
writing, never runs in a linked git worktree, and never pushes. When your recorded choice is to commit (the
default, CLAUDE.md section 10) it commits its own change, and refuses to write over uncommitted edits to the
tracker or the activity log, saying so at session start. With "don't commit" recorded in knowledge-base/11, or
in a folder that is not a git repository, it writes the change and leaves committing alone.

    python3 scripts/ghost.py --dry-run        # who would be ghosted, and why each other candidate is not
    python3 scripts/ghost.py --apply          # write, activity line, commit if your choice is to commit
    python3 scripts/ghost.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

if __name__ == "__main__" and "--selftest" in sys.argv:  # a throwaway copy that holds none of your files
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

import records as R  # noqa: E402

try:
    import config  # optional user knobs (scripts/config.py)
except Exception as _e:  # a missing file is fine; a file that will not load is named, never a traceback
    if not (isinstance(_e, ModuleNotFoundError) and _e.name == "config"):
        import traceback as _tb
        _line = _e.lineno if isinstance(_e, SyntaxError) else next(
            (f.lineno for f in reversed(_tb.extract_tb(_e.__traceback__)) if Path(f.filename).name == "config.py"), "?")
        _why = _e.msg if isinstance(_e, SyntaxError) else f"{type(_e).__name__}: {_e}"
        print(f"ghost: not checked, scripts/config.py line {_line}: {_why}. Fix that line and run this again.")
        sys.exit(3)
    config = None  # type: ignore[assignment]


def _knob_days() -> int:
    """GHOST_DAYS from scripts/config.py; a missing, broken or non-positive value means the default."""
    try:
        n = int(getattr(config, "GHOST_DAYS", 14))
    except (TypeError, ValueError):
        return 14
    return n if n >= 1 else 14


N_DAYS = _knob_days()
OWED_TOKEN = re.compile(r"@OWED\[\s*(them|you)\s*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|\?)\s*\|\s*([^\]]*?)\s*\]")
ISO_ANY = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
KEEP_LIVE = re.compile(r"\bno[- ]auto[- ]ghost\b", re.I)   # your "keep it live": the row's next carries "no auto-ghost"
NO_COMMIT = re.compile(r"^\s*-\s*\*\*Commits:\*\*\s*(?:don['’]?t|do not)\s+commit\b", re.I | re.M)
TRACKER = "pipeline/tracker.html"
NO_TRACKER = f"ghost.py: no tracker yet ({TRACKER}): not checked."
ACTIVITY = "ops/log/activity.md"
KB11 = "knowledge-base/11-preferences-and-conventions.md"


def _today() -> date:
    """Today in your configured time zone (scripts/config.py TIMEZONE, via local_now()), else this
    machine's date. A missing or broken config never breaks this script."""
    try:
        return config.local_now().date()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        return date.today()


def _iso(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


@dataclass
class Candidate:
    idx: int                 # index into Tracker.apps
    co: str
    role: str
    status: str
    chase: date
    blocks: list = field(default_factory=list)   # why it is NOT ghosted; empty = ghost it

    @property
    def ok(self) -> bool:
        return not self.blocks


def _dated_names(d: Path) -> list:
    out = []
    for sub in ("correspondence", "calls"):
        sd = d / sub
        if sd.is_dir():
            for x in sd.iterdir():
                m = re.match(r"^(\d{4}-\d{2}-\d{2})-", x.name)
                day = _iso(m.group(1)) if m else None
                if day:
                    out.append((day, f"{sub}/{x.name}"))
    return out


def _inmail_rows(text: str) -> list:
    """(date, context) for every dated table row of the optional paid-message ledger. A balance row names no
    company, so it can never hold a row back."""
    out = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        c = R.split_cells(line)
        day = _iso(c[0]) if len(c) >= 3 and R.ISO.match(c[0]) else None
        if day:
            out.append((day, c[1] + " " + c[2]))
    return out


def _names_company(text: str, co: str) -> bool:
    base = re.sub(r"\s*[(\[].*$", "", co).strip()
    return bool(base) and re.search(r"(?<![A-Za-z0-9])" + re.escape(base) + r"(?![A-Za-z0-9])", text, re.I) is not None


def candidates(repo: Path = REPO, today: date | None = None, t: R.Tracker | None = None) -> list:
    """Every applied/interview/offer row whose newest open @OWED[them] is N_DAYS or more past, with its blocks."""
    today = today or _today()
    t = t or R.load_tracker(repo=repo)
    led_p = repo / "pipeline" / "sent-ledger.md"
    ledger = R.ledger_rows(led_p.read_text(encoding="utf-8", errors="replace")) if led_p.is_file() else []
    im_p = repo / "pipeline" / "inmail-ledger.md"
    inmail = _inmail_rows(im_p.read_text(encoding="utf-8", errors="replace")) if im_p.is_file() else []
    out = []
    for i, r in enumerate(t.apps):
        st = R.s(r.get("status"))
        if st not in ("applied", "interview", "offer"):
            continue
        co, nxt = R.s(r.get("co")), R.s(r.get("next"))
        owed = OWED_TOKEN.findall(nxt)
        them = sorted(d for d in (_iso(x) for o, x, _w in owed if o == "them" and x != "?") if d)
        if not them or (today - them[-1]).days < N_DAYS:
            continue
        chase = them[-1]
        c = Candidate(i, co, R.s(r.get("role")), st, chase)
        if KEEP_LIVE.search(nxt):
            c.blocks.append("the row says no auto-ghost (you keep it live)")
        if any(o == "them" and d == "?" for o, d, _w in owed):
            c.blocks.append("an undated @OWED[them|?] is open")
        if any(o == "you" for o, _d, _w in owed):
            c.blocks.append("an @OWED[you] is open on the row")
        later = sorted({d for d in ISO_ANY.findall(nxt) if d > chase.isoformat()})
        if later:
            c.blocks.append("the row's next names a later date: " + ", ".join(later[:3]))
        # a reply can land in ANY dossier of the same company (a second role, a recruiter's thread): read them all
        folders = sorted({R.folder_of(a) for a in t.apps if R.same_company(R.s(a.get("co")), co) and R.folder_of(a)})
        files = [f"{fo}/{n}" if fo != R.folder_of(r) else n for fo in folders if (repo / fo).is_dir()
                 for d, n in _dated_names(repo / fo) if d > chase]
        if files:
            c.blocks.append("dossier file dated after the chase date: " + ", ".join(sorted(files)[:3]))
        rows = [lr for lr in ledger if lr.day and lr.day > chase and R.same_company(lr.company, co)]
        if rows:
            c.blocks.append("sent-ledger row(s) after the chase date: line " + ", ".join(str(x.line) for x in rows[:3]))
        ims = [d for d, ctx in inmail if d > chase and _names_company(ctx, co)]
        if ims:
            c.blocks.append("paid-message ledger row after the chase date: " + ims[0].isoformat())
        for n in t.net:
            if not R.same_company(R.s(n.get("company")), co):
                continue
            fu = R.parse_fu(n.get("fu"))
            if fu and fu.state == "me":
                c.blocks.append(f"{R.s(n.get('name'))} at this company has fu me (you owe a move)")
            elif fu and fu.state != "closed" and fu.since and fu.since > chase:
                c.blocks.append(f"{R.s(n.get('name'))}'s fu is dated {fu.since} (after the chase date)")
        out.append(c)
    return out


# the edit
def _js(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _field_span(obj: str, key: str):
    """(start, end) of the double-quoted value of `key` in one tracker object, or None."""
    m = re.search(r"(?:^|[{,\s])" + key + r'\s*:\s*("(?:[^"\\]|\\.)*")', obj)
    return (m.start(1), m.end(1)) if m else None


def _close_owed(text: str, when: str, status: str = "ghosted") -> tuple[str, int]:
    n = 0

    def rep(m):
        nonlocal n
        n += 1
        what = m.group(3).replace("]", ")")
        return f"@OWED-closed[{m.group(1)}|{m.group(2)}|{what}; {status} {when}]"
    return OWED_TOKEN.sub(rep, text), n


def _other_live_rows(t: R.Tracker, idx: int, company: str) -> list:
    """The application rows at `company`, other than idx, that are not dead (rejected, passed, ghosted)."""
    return [j for j, a in enumerate(t.apps) if j != idx and R.same_company(R.s(a.get("co")), company)
            and R.s(a.get("status")) not in R.DEAD_APP]


def ghost_html(html: str, t: R.Tracker, idx: int, when: str, why: str, status: str = "ghosted") -> tuple[str, dict]:
    """The tracker text with application idx set to `status` (ghosted; or passed for a row never applied to,
    which `ghosted` cannot be) and every open @OWED on it and every open thread at its company closed. Edits
    are applied back to front so earlier offsets stay valid."""
    edits = []
    s0, e0 = t.app_spans[idx]
    obj = html[s0:e0]
    co = R.s(t.apps[idx].get("co"))
    st = _field_span(obj, "status")
    if not st:
        raise ValueError(f"{co}: no status field")
    edits.append((s0 + st[0], s0 + st[1], _js(status)))
    nx = _field_span(obj, "next")
    old_next = R.s(t.apps[idx].get("next"))
    new_next, closed = _close_owed(old_next, when, status)
    new_next = f"{status.upper()} {when}: {why}. " + new_next
    if nx:
        edits.append((s0 + nx[0], s0 + nx[1], _js(new_next)))
    people, held = [], []
    for n, (ns, ne) in zip(t.net, t.net_spans):
        if not R.same_company(R.s(n.get("company")), co):
            continue
        fu = R.parse_fu(n.get("fu"))
        if not fu or fu.state == "closed":
            continue
        # only a thread tied to THIS application closes. A person at a company that still has another live row
        # may be that row's thread: left open.
        if _other_live_rows(t, idx, R.s(n.get("company"))):
            held.append(R.s(n.get("name")))
            continue
        was = f"{fu.state} since {fu.since.isoformat() if fu.since else '?'}: {fu.what}"
        was = was.replace("@OWED[", "@OWED-closed[").replace("|", "/")
        sp = _field_span(html[ns:ne], "fu")
        if sp:
            edits.append((ns + sp[0], ns + sp[1], _js(f"closed|{when}|application {status} {when}; was {was}")))
            people.append(R.s(n.get("name")))
    for a, b, v in sorted(edits, reverse=True):
        html = html[:a] + v + html[b:]
    return html, {"co": co, "owed_closed": closed, "people": people, "held": held}


# apply (the session-start path)
def _git(repo: Path, *args) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(e))


def in_git(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--git-dir").returncode == 0


def is_main_checkout(repo: Path) -> bool:
    g = _git(repo, "rev-parse", "--git-dir").stdout.strip()
    c = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    return bool(g) and os.path.realpath(os.path.join(repo, g)) == os.path.realpath(os.path.join(repo, c))


def commits_on(repo: Path) -> bool:
    """False when knowledge-base/11 records "don't commit" (CLAUDE.md section 10). The default is to commit."""
    try:
        return not NO_COMMIT.search((repo / KB11).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return True


def apply(repo: Path = REPO, today: date | None = None) -> tuple[list, str]:
    """Ghost every candidate that clears every guard. Returns (ghosted names, one status line)."""
    git = in_git(repo)
    if git and not is_main_checkout(repo):
        return [], "auto-ghost: skipped (not the main checkout)"
    today = today or _today()
    when = today.isoformat()
    t = R.load_tracker(repo=repo)          # re-read just before writing
    cands = [c for c in candidates(repo, today, t) if c.ok]
    if not cands:
        return [], "auto-ghost: nothing to ghost"
    commit = git and commits_on(repo)
    paths = [TRACKER, ACTIVITY]
    if commit and _git(repo, "status", "--porcelain", "--", *paths).stdout.strip():
        return [], (f"auto-ghost: {len(cands)} row(s) ready but skipped: {TRACKER} or {ACTIVITY} has uncommitted "
                    "edits. Commit them, or run python3 scripts/ghost.py --apply after.")
    html = t.html
    done = []
    for c in sorted(cands, key=lambda c: -c.idx):   # back to front: spans stay valid
        t = R.load_tracker(html=html, repo=repo)
        why = f"ghosted automatically: silent {N_DAYS} days past the chase date {c.chase.isoformat()}"
        html, info = ghost_html(html, t, c.idx, when, why)
        done.append((c, info))
    (repo / TRACKER).write_text(html, encoding="utf-8")
    bullets = "\n".join(
        f"- {c.co}, {c.role} ({c.status} to ghosted): silent {N_DAYS} days past the chase date "
        f"{c.chase.isoformat()}. Closed {info['owed_closed']} @OWED; threads closed: {', '.join(info['people']) or 'none'}"
        + (f"; left open (another live row at the company): {', '.join(info['held'])}" if info.get("held") else "") + "."
        for c, info in reversed(done))
    (repo / ACTIVITY).parent.mkdir(parents=True, exist_ok=True)
    with open(repo / ACTIVITY, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {when}: Auto-ghost (scripts/ghost.py)\n\n{bullets}\n")
    names = [c.co for c, _ in reversed(done)]
    line = "auto-ghost: ghosted " + ", ".join(names)
    if commit:
        msg = (f"Auto-ghost: {', '.join(names)} marked ghosted (silent {N_DAYS}+ days past the chase date)\n\n"
               + "\n".join(f"{c.co}: newest @OWED[them] chase {c.chase.isoformat()}, nothing recorded since; "
                           f"{info['owed_closed']} @OWED closed; threads closed: {', '.join(info['people']) or 'none'}."
                           for c, info in reversed(done))
               + "\n\nscripts/ghost.py at session start. A reply reopens it (records-format.md section 1).\n")
        _git(repo, "add", "--", *paths)
        r = _git(repo, "commit", "-m", msg, "--", *paths)
        line += ", committed" if r.returncode == 0 else f", commit failed: {(r.stderr or r.stdout).strip()[:120]}"
    return names, line


def session_lines(repo: Path = REPO, today: date | None = None) -> list:
    """For the session-start readout: each auto-ghost by name, or the reason ready rows were left alone.
    Fail-open: this never blocks a session. JOB_GHOST_NO_APPLY=1 (hooks.py sets it in its selftest) writes nothing."""
    if os.environ.get("JOB_GHOST_NO_APPLY"):
        return []
    if not (repo / TRACKER).is_file():
        return [f"  {NO_TRACKER}"]
    try:
        names, line = apply(repo, today)
    except Exception as e:  # noqa: BLE001
        return [f"  ! auto-ghost unavailable ({type(e).__name__}: {e}); run scripts/ghost.py --dry-run by hand."]
    if names:
        return [f"  {line}; each is named in {ACTIVITY}. If one of them replies, reopen it (records-format.md section 1)."]
    if "ready but skipped" in line:
        return [f"  {line}"]
    return []


# report / selftest
def report(cands: list) -> str:
    go = [c for c in cands if c.ok]
    L = [f"ghost.py --dry-run: {len(go)} to ghost, {len(cands) - len(go)} candidate(s) held by a guard "
         f"(newest @OWED[them] {N_DAYS}+ days past)"]
    for c in go:
        L.append(f"  GHOST  {c.co}: {c.role} ({c.status}), chase {c.chase.isoformat()}")
    for c in cands:
        if not c.ok:
            L.append(f"  hold   {c.co}: {c.role} ({c.status}), chase {c.chase.isoformat()}: " + " | ".join(c.blocks))
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
    global N_DAYS, config
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("  PASS " if cond else "  FAIL ") + label + (f"  :: {detail}" if detail and not cond else ""))

    class _FakeCfg:
        GHOST_DAYS = 9

        @staticmethod
        def local_now():
            from datetime import datetime as _dt
            return _dt(2031, 7, 4, 23, 30)

    class _BadCfg:
        GHOST_DAYS = "soon"

    saved_days, saved_cfg = N_DAYS, config
    config = _FakeCfg()
    try:
        check("today comes from the configured zone (config.local_now), not the machine clock", _today() == date(2031, 7, 4))
        check("GHOST_DAYS comes from config", _knob_days() == 9)
        config = _BadCfg()
        check("a broken GHOST_DAYS falls back to 14", _knob_days() == 14)
        config = None
        check("no config at all still means 14", _knob_days() == 14)
        N_DAYS = 14
        print("ghost.py selftest (synthetic records)\n")
        os.environ.pop("JOB_GHOST_NO_APPLY", None)
        return _cases(check, lambda: ok, tempfile)
    finally:
        N_DAYS, config = saved_days, saved_cfg


def _build_repo(r: Path) -> str:
    (r / "pipeline").mkdir()
    (r / "ops" / "log").mkdir(parents=True)
    (r / "knowledge-base").mkdir()
    for d in ("quiet-rn", "replied-rn", "owes-disp", "fresh-sm", "ledger-sm", "north-acct", "text-elec", "paid-acct",
              "lab-contract", "lab-tech"):
        (r / "applications" / d / "correspondence").mkdir(parents=True)
    (r / "applications" / "replied-rn" / "correspondence" / "2030-05-12-their-reply.png").write_text("x")
    (r / "applications" / "quiet-rn" / "correspondence" / "2030-04-01-note-sent.md").write_text("x")
    # the reply landed in the company's OTHER dossier
    (r / "applications" / "lab-tech" / "correspondence" / "2030-05-13-recruiter-reply.png").write_text("x")

    def row(co, role, folder, nxt, st="interview"):
        return (f'  {{co:"{co}", role:"{role}", status:"{st}", posted:"unknown", source:"s", jd:"", apply:"", '
                f'folder:"applications/{folder}", refs:0, applied:"2030-03-01", next:{_js(nxt)}}},\n')
    html = ('<script>const APPLICATIONS = [\n'
            + row("Acme Nursing", "Charge Nurse", "quiet-rn", "@OWED[them|2030-05-01|Acme Nursing: decision] Earlier: @OWED-closed[them|2030-04-01|x]")
            + row("Acme Dental", "Hygienist", "replied-rn", "@OWED[them|2030-04-30|decision]")
            + row("Globex Freight", "Dispatcher", "owes-disp", "@OWED[them|2030-04-30|decision] @OWED[you|2030-06-05|send references]")
            + row("Globex Retail", "Store Manager", "fresh-sm", "@OWED[them|2030-05-10|decision]")
            + row("Initech Retail", "Buyer", "ledger-sm", "@OWED[them|2030-04-30|decision]", st="applied")
            + row("Northwind (Series B)", "Bookkeeper", "north-acct", "@OWED[them|2030-04-29|Jordan: reply]")
            + row("Umbrella Electric", "Electrician", "text-elec", "@OWED[them|2030-04-29|decision] FOLLOW-UP SENT 2030-05-13.")
            + row("Hooli Bank", "Teller", "paid-acct", "@OWED[them|2030-04-29|decision]")
            + row("Hooli Schools", "Teacher", "quiet-rn", "@OWED[them|2030-04-29|decision] @OWED[them|?|recruiter call]")
            + row("Umbrella Logistics", "Forklift Operator", "quiet-rn", "Keep this one, no auto-ghost (2030-04-23). @OWED[them|2030-04-29|decision]")
            + row("Initech Sales", "Account Executive", "quiet-rn", "@OWED[them|2030-04-01|x]", st="rejected")
            + row("Acme Labs (contract via Globex)", "Lab Tech", "lab-contract", "@OWED[them|2030-04-29|agency: decision]", st="applied")
            + row("Acme Labs", "Lab Tech", "lab-tech", "applied; waiting", st="applied")
            + row("Hooli Cloud", "Developer", "quiet-rn", "@OWED[them|2030-13-45|a date that does not exist]")
            + '];\nconst NETWORK = [\n'
            '  {name:"Sam Lee", company:"Acme Nursing", role:"r", status:"active", note:"n", fu:"them|2030-04-25|@OWED[them|2030-05-01|reply] waiting"},\n'
            '  {name:"Alex Kim", company:"Acme Nursing", role:"r", status:"active", note:"n", fu:"closed|2030-04-01|over"},\n'
            '  {name:"Jordan Rivera", company:"Northwind", role:"r", status:"active", note:"n", fu:"me|2030-04-22|reply to them"},\n'
            '  {name:"Sam Lee", company:"Acme Nursing Home", role:"r", status:"active", note:"n", fu:"them|2030-04-25|x"},\n'
            '  {name:"Alex Kim", company:"Acme Labs", role:"r", status:"active", note:"n", fu:"them|2030-04-25|about the lab role"},\n'
            '];\nconst STATUS = {lead:{}, active:{}, applied:{}, interview:{}, offer:{}, rejected:{}, passed:{}, ghosted:{}};\n'
            'const NET_STATUS = {lead:{}, active:{}, passed:{}};\nlet view="apps";</script>')
    (r / TRACKER).write_text(html)
    (r / "pipeline" / "sent-ledger.md").write_text(
        "| date | recipient | company | channel | message-ref | copy-state-at-send | sent-by |\n|---|---|---|---|---|---|---|\n"
        "| 2030-05-04 | Sam Lee | Initech Retail | email | follow-up | ok | me |\n")
    (r / "pipeline" / "inmail-ledger.md").write_text(
        "## Current balance\n| As of | Credits left | Source |\n|---|---|---|\n| 2030-05-15 | 3 | me |\n\n"
        "## Usage\n| Date sent | To | Company/Role context | Why | Replied |\n|---|---|---|---|---|\n"
        "| 2030-05-05 | Alex Kim | Hooli Bank / Teller | x | awaiting |\n")
    (r / ACTIVITY).write_text("# log\n")
    return html


def _cases(check, verdict, tempfile) -> int:
    T = date(2030, 5, 20)
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        html = _build_repo(r)
        cs = {c.co: c for c in candidates(r, T)}
        check("candidates are applied/interview/offer rows 14+ days past their newest @OWED[them]; a 10-day row and a "
              "date that does not exist are not",
              set(cs) == {"Acme Nursing", "Acme Dental", "Globex Freight", "Initech Retail", "Northwind (Series B)",
                          "Umbrella Electric", "Hooli Bank", "Hooli Schools", "Umbrella Logistics",
                          "Acme Labs (contract via Globex)"}, sorted(cs))
        check("a clean row clears every guard (a file BEFORE the chase date and a closed thread do not hold it)",
              cs["Acme Nursing"].ok, cs["Acme Nursing"].blocks)
        check("a correspondence file dated after the chase date holds it",
              not cs["Acme Dental"].ok and "2030-05-12-their-reply.png" in " ".join(cs["Acme Dental"].blocks))
        check("an open @OWED[you] holds it", any("@OWED[you]" in b for b in cs["Globex Freight"].blocks))
        check("a sent-ledger row after the chase date holds it", any("sent-ledger" in b for b in cs["Initech Retail"].blocks))
        check("a NETWORK person with fu me holds it; 'Northwind (Series B)' matches 'Northwind'",
              any("Jordan Rivera" in b for b in cs["Northwind (Series B)"].blocks))
        check("a later date in the row's own next holds it", any("later date" in b for b in cs["Umbrella Electric"].blocks))
        check("a paid-message ledger row naming the company holds it (a balance row does not)",
              any("paid-message" in b and "2030-05-05" in b for b in cs["Hooli Bank"].blocks))
        check("an undated @OWED[them|?] holds it", any("undated" in b for b in cs["Hooli Schools"].blocks))
        check("'no auto-ghost' in the row's next holds it", any("no auto-ghost" in b for b in cs["Umbrella Logistics"].blocks))
        check("a correspondence file in ANOTHER dossier of the same company holds it",
              any("lab-tech/correspondence/2030-05-13-recruiter-reply.png" in b
                  for b in cs["Acme Labs (contract via Globex)"].blocks), cs["Acme Labs (contract via Globex)"].blocks)
        tm = R.load_tracker(repo=r)
        new_m, info_m = ghost_html(tm.html, tm, cs["Acme Labs (contract via Globex)"].idx, "2030-05-20", "x")
        mp = next(n for n in R.load_tracker(html=new_m, repo=r).net if R.s(n["company"]) == "Acme Labs")
        check("ghosting one row never closes a thread at a company with another live row",
              mp["fu"] == "them|2030-04-25|about the lab role" and info_m["people"] == [] and info_m["held"] == ["Alex Kim"],
              (mp["fu"], info_m))
        t = R.load_tracker(repo=r)
        quiet = cs["Acme Nursing"]
        new, info = ghost_html(t.html, t, quiet.idx, "2030-05-20", "ghosted automatically: silent 14 days past the chase date 2030-05-01")
        t2 = R.load_tracker(html=new, repo=r)
        q = next(a for a in t2.apps if a["co"] == "Acme Nursing")
        qp = next(n for n in t2.net if n["name"] == "Sam Lee" and n["company"] == "Acme Nursing")
        oc = next(n for n in t2.net if n["company"] == "Acme Nursing Home")
        check("the row is ghosted, its next leads with GHOSTED and the reason, its @OWED is closed with its text kept",
              q["status"] == "ghosted" and q["next"].startswith("GHOSTED 2030-05-20: ghosted automatically")
              and "@OWED-closed[them|2030-05-01|Acme Nursing: decision; ghosted 2030-05-20]" in q["next"]
              and not OWED_TOKEN.search(q["next"]) and info["owed_closed"] == 1, q["next"][:200])
        check("the open thread closes and its @OWED becomes closed text; another company's thread is untouched",
              qp["fu"].startswith("closed|2030-05-20|application ghosted 2030-05-20; was them since 2030-04-25:")
              and "@OWED[" not in qp["fu"] and oc["fu"] == "them|2030-04-25|x" and info["people"] == ["Sam Lee"], qp["fu"])
        check("nothing else in the file changed (the other rows byte for byte)",
              len(t2.apps) == len(t.apps)
              and [a for a in t2.apps if a["co"] != "Acme Nursing"] == [a for a in t.apps if a["co"] != "Acme Nursing"])
        new_p, _ = ghost_html(t.html, t, quiet.idx, "2030-05-20", "never applied", status="passed")
        qq = next(a for a in R.load_tracker(html=new_p, repo=r).apps if a["co"] == "Acme Nursing")
        check("the status parameter writes passed into status, the next prefix and the closed @OWED",
              qq["status"] == "passed" and qq["next"].startswith("PASSED 2030-05-20:") and "decision; passed 2030-05-20]" in qq["next"])
        import records_check as rc
        (r / TRACKER).write_text(new)
        F, _ = rc.run(files=[TRACKER], repo=r)
        check("records_check finds no currency defect on the ghosted row or its thread",
              not any("Acme Nursing" in f.where and ("open" in f.problem) for f in F), [str(f) for f in F if "Acme Nursing" in f.where])
        # a folder that is not a git repository (a downloaded ZIP) still works, and commits nothing
        (r / TRACKER).write_text(html)
        names, line = apply(r, T)
        check("outside git: apply writes the change and does not try to commit",
              names == ["Acme Nursing"] and "commit" not in line
              and R.load_tracker(repo=r).apps[quiet.idx]["status"] == "ghosted" and "Auto-ghost" in (r / ACTIVITY).read_text(), line)
        os.environ["JOB_GHOST_NO_APPLY"] = "1"
        (r / TRACKER).write_text(html)
        before = (r / TRACKER).read_text()
        check("JOB_GHOST_NO_APPLY writes nothing and says nothing",
              session_lines(r, T) == [] and (r / TRACKER).read_text() == before)
        os.environ.pop("JOB_GHOST_NO_APPLY", None)
    with tempfile.TemporaryDirectory() as td:
        # a real main checkout, the default commit choice
        r = Path(td) / "main"
        r.mkdir()
        _build_repo(r)
        (r / KB11).write_text("- **Commits:** [commit locally as I go (recommended) / don't commit] (chosen on: [date])\n")
        _git(r, "init", "-q")
        _git(r, "config", "user.email", "t@example.com")
        _git(r, "config", "user.name", "t")
        _git(r, "add", "-A")
        _git(r, "commit", "-qm", "init")
        wt = Path(td) / "wt"
        _git(r, "worktree", "add", "-q", str(wt))
        names, line = apply(wt, T)
        check("a linked worktree is left alone", names == [] and "not the main checkout" in line, line)
        _git(r, "worktree", "remove", "--force", str(wt))
        with open(r / ACTIVITY, "a") as fh:
            fh.write("\n")
        names, line = apply(r, T)
        check("default choice: uncommitted edits to the activity log refuse the write, and the line says so",
              names == [] and "ready but skipped" in line and "uncommitted" in line, line)
        check("session_lines surfaces that refusal instead of staying silent",
              any("ready but skipped" in x for x in session_lines(r, T)))
        _git(r, "commit", "-qam", "x")
        names, line = apply(r, T)
        log = _git(r, "log", "-1", "--format=%s%n%b").stdout
        check("default choice: apply ghosts exactly the clean row, writes the activity line, commits its own change",
              names == ["Acme Nursing"] and "committed" in line and "Auto-ghost: Acme Nursing" in log
              and "silent 14 days past the chase date 2030-05-01" in (r / ACTIVITY).read_text()
              and not _git(r, "status", "--porcelain").stdout.strip(), (line, log))
        check("the commit carries no AI attribution", "co-authored" not in log.lower() and "claude" not in log.lower())
        names, line = apply(r, T)
        check("a second run finds nothing to ghost", names == [] and "nothing" in line, line)
    with tempfile.TemporaryDirectory() as td:
        # the user recorded "don't commit": a dirty tracker is normal there, and no commit is made
        r = Path(td)
        _build_repo(r)
        (r / KB11).write_text("- **Commits:** don't commit (chosen on: 2030-01-02)\n")
        _git(r, "init", "-q")
        _git(r, "config", "user.email", "t@example.com")
        _git(r, "config", "user.name", "t")
        _git(r, "add", "-A")
        _git(r, "commit", "-qm", "init")
        with open(r / TRACKER, "a") as fh:
            fh.write("\n")
        head = _git(r, "rev-parse", "HEAD").stdout
        names, line = apply(r, T)
        check("\"don't commit\" recorded: it writes past a dirty tracker and makes no commit",
              names == ["Acme Nursing"] and "commit" not in line and _git(r, "rev-parse", "HEAD").stdout == head, line)
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir()
        (r / TRACKER).write_text('<script>const APPLICATIONS = [\n];\nconst NETWORK = [\n];\nlet view="apps";</script>')
        names, line = apply(r, T)
        check("an empty tracker has nothing to ghost and writes nothing",
              names == [] and "nothing" in line and not (r / ACTIVITY).exists(), line)
    import contextlib
    import io
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--dry-run", "--repo", td])
        check("no tracker: says not checked and exits 3, never '0 to ghost'",
              rc == 3 and "no tracker yet" in buf.getvalue() and "not checked" in buf.getvalue() and "to ghost" not in buf.getvalue(),
              f"rc={rc} {buf.getvalue()!r}")
        check("no tracker: the session line says not checked, no traceback text",
              session_lines(Path(td)) == [f"  {NO_TRACKER}"], str(session_lines(Path(td))))
    for _label, _ok in _config_guard_cases():
        check(_label, _ok)
    ok = verdict()
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list) -> int:
    if "--selftest" in argv:
        return selftest()
    repo = REPO
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()
    today = date.fromisoformat(argv[argv.index("--today") + 1]) if "--today" in argv else None
    if not (repo / TRACKER).is_file():
        print(NO_TRACKER)
        return 3
    if "--apply" in argv:
        names, line = apply(repo, today)
        print(line)
        return 0
    print(report(candidates(repo, today)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
