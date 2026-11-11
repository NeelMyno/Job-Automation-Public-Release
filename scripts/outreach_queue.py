#!/usr/bin/env python3
"""
outreach_queue.py: THE DERIVED OUTREACH QUEUE. Computed fresh from the shared records,
never maintained as a file.

Outreach runs in its own session type off ONE command, and deliberately does not maintain its
own records: every piece of state lives in one of the four shared surfaces below, updated the
same turn something changes. The failure this design kills: a hand-maintained "pending outreach"
file rots the moment any other session sends a message, since nothing keeps it in sync, and a stale
queue can still list an already-contacted person, with nothing standing between that and a
double-message except whoever happens to notice.

THE SSOT SURFACES (this script READS them; it never writes anything):
  pipeline/tracker.html          : APPLICATIONS (which dossiers are live) + NETWORK (people state)
  applications/*/referrals.md    : the per-company roster + drafted messages (outreach_format's grammar)
  pipeline/sent-ledger.md        : what actually left (append-only)
  pipeline/inmail-ledger.md      : the InMail balance

A "pending outreach" file is a defect by definition: the queue below is derivable, so any
maintained copy of it is a second source of truth that will drift. (Legacy queue files are
stamped OUTDATED and skipped by hooks.py's outreach_dupes.)

Ledger-parsing note: the sent-ledger's stated schema is date·recipient·company·… but in real use
rows get appended with those two columns flipped (date·company·recipient). The ledger is
append-only so such drift stays; this parser resolves each row by matching cells against the
known-people and known-company sets instead of trusting column position.

Not checked: a social platform's own connection/reply state (acceptance/replies are knowable
only from the ledger, tracker notes, or your own word), and message QUALITY (outreach_format.py +
verify_claims.py own that). FOLLOW-UP-DUE uses a 4-day/one-nudge default (config.py's
FOLLOWUP_DAYS; you can override per thread).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

if __name__ == "__main__" and "--selftest" in sys.argv:  # a throwaway copy that holds none of your files
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

import outreach_format  # person_blocks + scan_text: ONE owner of the person grammar (§8)

# scripts/config.py is optional. See that file's own docstring. Falls back to this script's
# historical defaults (4-day nudge threshold, 3/day small-basket cap) if it has never been created.
try:
    import config  # optional user knobs (scripts/config.py)
except Exception as _e:  # a missing file is fine; a file that will not load is named, never a traceback
    if not (isinstance(_e, ModuleNotFoundError) and _e.name == "config"):
        import traceback as _tb
        _line = _e.lineno if isinstance(_e, SyntaxError) else next(
            (f.lineno for f in reversed(_tb.extract_tb(_e.__traceback__)) if Path(f.filename).name == "config.py"), "?")
        _why = _e.msg if isinstance(_e, SyntaxError) else f"{type(_e).__name__}: {_e}"
        print(f"outreach_queue: not checked, scripts/config.py line {_line}: {_why}. Fix that line and run this again.")
        sys.exit(3)
    class config:  # type: ignore[no-redef]
        """Fallback when scripts/config.py has not been created yet (safe defaults only)."""
        FOLLOWUP_DAYS = 4
        SMALL_BASKET_CAP = 3

def _today() -> date:
    """Today in your configured time zone (scripts/config.py TIMEZONE, via local_now()), else this
    machine's date. A missing or broken config never breaks this script."""
    try:
        return config.local_now().date()  # type: ignore[union-attr]
    except Exception:
        return date.today()


FOLLOWUP_DAYS = getattr(config, "FOLLOWUP_DAYS", 4)      # silence threshold before the single permitted nudge
SMALL_BASKET_CAP = getattr(config, "SMALL_BASKET_CAP", 3)  # sends/company/day when company is small/unknown
LIVE = {"applied", "interview", "offer", "active"}
DEAD = {"rejected", "passed", "ghosted"}   # ghosted: no one is left to message about this role
REPLY_RE = re.compile(r"\brepl(?:y|ied|ies)\b|\bREPLIED\b", re.I)
FOLLOWUP_RE = re.compile(r"follow[- ]?up|nudge", re.I)

# The warm-lead reminder engine. A NETWORK row carries an optional structured follow-up state so
# an owed action surfaces BY NAME every session instead of dissolving into a passive "N replied"
# count. Format: fu:"<state>|<YYYY-MM-DD>|<what>", state ∈ {me, them, rest}.
#   me   = you owe the next move (reply / send the referral details); ALWAYS surfaced, loud.
#   them = waiting on them; becomes a nudge after FOLLOWUP_DAYS of silence.
#   rest = the one permitted nudge is spent, or the thread is parked: tracked, never surfaced as
#          due (the one-nudge rule). It re-surfaces only by a reply flipping it back to "me".
#   closed = the thread is over: tracked, never surfaced. The grammar's owner is scripts/records.py;
#            the shape is owned by .claude/rules/records-format.md.
FU_RE = re.compile(r"^(me|them|rest|closed)\|([^|]+)\|(.*)$", re.S)  # date validated in build() so a bad one surfaces
def _fu_rank(what: str) -> int:
    """Sort owed replies by value: a referral you can't lose ranks above a generic thread."""
    w = what.lower()
    if "refer" in w: return 0
    if any(k in w for k in ("chat", "coffee", "call", "interview")): return 1
    if any(k in w for k in ("hiring", "flag", "consider", "push", "vouch", "intro")): return 2
    return 3
NOTE_ONLY_RE = re.compile(r"connection note|connection request", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def short_name(heading: str) -> str:
    """outreach_format.person_blocks returns the WHOLE `###` heading line as the name
    ("Sam Lee, then a dash, then the role, a link and the ask"); the ledger and tracker carry just
    "Sam Lee". Split on the first em-dash/middot to compare like with like. A trailing
    UNCLOSED paren is a role descriptor cut mid-way ("Sam Lee (shift lead") and gets
    trimmed; a balanced paren is a nickname ("Alexander (Alex) Kim") and stays."""
    # ...and on the first comma: "Alex Lee, Regional Dispatch Supervisor, named on this
    # posting" is a common heading style. Without the comma split the "name" runs to a dozen words,
    # is_queue_person() refuses it, and the person silently vanishes from every bucket.
    n = re.split(r"\s+\u2014\s+|\s+·\s+|\s+-\s+|,\s+", heading.strip(), maxsplit=1)[0].strip().strip("*_`")
    n = re.sub(r"^\d+\s*[·.)]\s*", "", n)
    if n.count("(") > n.count(")"):
        n = n[:n.rindex("(")].strip()
    return n


# Real referrals.md files carry `###` headings that are records, not people (a status emoji,
# "Honest notes", "Unified list", "Connection request: on hold"). A real defect this
# guards against: without it, such headings leak into the queue as sendable people.
NOT_A_QUEUE_PERSON = re.compile(
    r"[:✅⏳🔴]|^(?:if|none|not |no |honest|unified|connection|dm\b|email\b|inmail|sent|blocked|"
    r"pending|update|status|the |a |an )", re.I)


def is_queue_person(name: str) -> bool:
    n = name.strip()
    return bool(n) and not NOT_A_QUEUE_PERSON.search(n) and n[0].isupper() and len(n.split()) <= 5


# tracker
def tracker_rows(tracker_text: str) -> tuple[list[dict], list[dict]]:
    """APPLICATIONS rows (co,status,folder) and NETWORK rows (name,company,status,note,fu), read by
    scripts/records.py (node, the browser's parser), so a folder written without its applications/
    prefix or a key in an unusual position no longer hides a row. The regex reader below is the
    fallback when records.py cannot read the text (a fragment, as in the selftest)."""
    try:
        import records as _R
        t = _R.load_tracker(tracker_text)
        if t.apps or t.net:
            apps = [{"co": _R.s(a.get("co")), "status": _R.s(a.get("status")), "folder": _R.folder_of(a) or None}
                    for a in t.apps]
            net = [{"name": _R.s(n.get("name")), "company": _R.s(n.get("company")), "status": _R.s(n.get("status")),
                    "note": _R.s(n.get("note")) or _R.s(n.get("notes")), "fu": n.get("fu")}
                   for n in t.net if n.get("name")]
            return apps, net
    except Exception:  # noqa: BLE001 (fall back to the tolerant regex reader)
        pass
    apps, net = [], []
    for m in re.finditer(r'\{co:"(?P<co>[^"]+)"[^}]*?status:"(?P<st>[^"]+)"[^}]*?\}', tracker_text):
        obj = m.group(0)
        fm = re.search(r'folder:"(applications/[^"]+?)/?"', obj)
        apps.append({"co": m.group("co"), "status": m.group("st"),
                     "folder": fm.group(1).rstrip("/") if fm else None})
    # Match the whole NETWORK object so a fu: field found anywhere in it (before or after note:)
    # is captured. Fields are extracted by name, not position, which is robust to extra keys (reply:, note2:).
    for m in re.finditer(r'\{name:"(?P<name>[^"]+)"[^}]*?\}', tracker_text):
        obj = m.group(0)
        co = re.search(r'company:"([^"]*)"', obj)
        st = re.search(r'status:"([^"]*)"', obj)
        if not (co and st):
            continue  # skip personal-network rows with a different schema (event:/ask:/notes:)
        note = re.search(r'note:"([^"]*)"', obj)
        fu = re.search(r'fu:"([^"]*)"', obj)
        net.append({"name": m.group("name"), "company": co.group(1), "status": st.group(1),
                    "note": note.group(1) if note else "", "fu": fu.group(1) if fu else None})
    return apps, net


# sent-ledger
@dataclass
class Send:
    when: date | None
    person: str
    company: str
    channel: str
    rest: str


def parse_ledger(text: str, known_people: set[str], known_companies: set[str]) -> list[Send]:
    sends = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in ("date", "---"):
            continue
        dm = re.match(r"(\d{4})-(\d{2})-(\d{2})", cells[0])
        if not dm:
            continue
        # an application submit is its own row type, not a message to a person; a row that records
        # a message that could not be sent is not a send
        if any(c.startswith("\u2014 (application") for c in cells[1:3]) or \
                re.search(r"COULD NOT SEND", " ".join(cells[4:]), re.I):
            continue
        when = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        a, b = _norm(cells[1]), _norm(cells[2])
        # Resolve the flipped-column drift by evidence, not position (see module docstring).
        if a in known_people or (b in known_companies and a not in known_companies):
            person, company = cells[1], cells[2]
        elif b in known_people or a in known_companies:
            person, company = cells[2], cells[1]
        else:
            person, company = cells[1], cells[2]  # stated schema order as the fallback
        sends.append(Send(when, person, company, cells[3] if len(cells) > 3 else "",
                          " ".join(cells[4:])))
    return sends


# inmail balance
def inmail_balance(text: str) -> str:
    rows = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\*{0,2}(\d+)\*{0,2}\s*\|", text)
    return f"{rows[-1][1]} (as of {rows[-1][0]})" if rows else "UNKNOWN: read pipeline/inmail-ledger.md"


# the queue itself
@dataclass
class Queue:
    no_roster: list = field(default_factory=list)      # (dossier, co, status)
    needs_draft: list = field(default_factory=list)    # (person, dossier, first finding)
    ready: list = field(default_factory=list)          # (person, dossier)
    fire_on_accept: list = field(default_factory=list) # (person, company, note_date)
    followup_due: list = field(default_factory=list)   # (person, company, last_date, days)
    owed_reply: list = field(default_factory=list)     # (person, company, since, days, what, rank): YOU owe the move
    untagged_reply: list = field(default_factory=list) # (person, company): REPLIED note, no fu tag (safety net)
    replied: list = field(default_factory=list)        # (person, company)
    unmatched: list = field(default_factory=list)      # (person, company, why): reconcile surface
    holds: list = field(default_factory=list)          # (file, first hold line)
    budget: dict = field(default_factory=dict)         # company -> sends today
    inmail: str = ""


class NoTracker(FileNotFoundError):
    """There is no tracker to derive a queue from, so nothing was checked."""


def build(repo: Path = REPO, today: date | None = None) -> Queue:
    today = today or _today()
    q = Queue()
    if not (repo / "pipeline" / "tracker.html").is_file():
        raise NoTracker("no tracker yet (pipeline/tracker.html): not checked.")
    tracker = (repo / "pipeline" / "tracker.html").read_text(errors="ignore")
    apps, net = tracker_rows(tracker)

    # roster: every LIVE application dossier's referrals.md people
    people_by_dossier: dict[str, list[tuple[str, str]]] = {}
    known_people = {_norm(n["name"]) for n in net}
    known_companies = {_norm(a["co"]) for a in apps} | {_norm(n["company"]) for n in net}
    live_apps = [a for a in apps if a["status"] in LIVE and a["folder"]]
    for a in live_apps:
        f = repo / a["folder"] / "referrals.md"
        if not f.exists():
            q.no_roster.append((a["folder"], a["co"], a["status"]))
            continue
        blocks = outreach_format.person_blocks(f.read_text(errors="ignore"))
        if not blocks:
            q.no_roster.append((a["folder"], a["co"], a["status"]))
            continue
        people_by_dossier[a["folder"]] = blocks
        known_people |= {_norm(short_name(n)) for n, _ in blocks}

    # one identity per person across the tracker, the rosters and the ledger (records.person_keys):
    # "Jordan Rivera (CEO)", "Samantha 'Sam' Lee" and "A.J. Kim, RN" each resolve to their row
    import records as _R
    import records_check as _rc
    alias: dict = {}
    for n in net:
        for k in _R.person_keys(n["name"]):
            alias.setdefault(k, _norm(n["name"]))
    for blocks in people_by_dossier.values():
        for raw, _b in blocks:
            for k in _R.person_keys(short_name(raw)):
                alias.setdefault(k, _norm(short_name(raw)))
    known_people |= set(alias)
    fu_people = {_norm(n["name"]) for n in net if n.get("fu")}
    ledger_p = repo / "pipeline" / "sent-ledger.md"
    sends = parse_ledger(ledger_p.read_text(errors="ignore"), known_people, known_companies) \
        if ledger_p.exists() else []
    split = []
    for s in sends:   # a row to two people is a send to each ("Sam Lee + Alex Kim")
        parts = _rc._person_parts(s.person)
        split += [Send(s.when, p, s.company, s.channel, s.rest) for p in parts] if len(parts) > 1 else [s]
    sends = split
    by_person: dict[str, list[Send]] = {}
    for s in sends:
        nn = _norm(s.person)
        hit = next((alias[k] for k in _R.person_keys(s.person) if k in alias), None)
        if hit:
            nn = hit
        elif not _rc.is_person(short_name(s.person)):
            continue  # a team mailbox (careers@, no-reply@) is not a thread with a person
        if nn not in known_people:
            # Ledger rows decorate names ('Alex K. (surname unverified, addressed as "Dee")');
            # unresolved, that decoration made Dee look never-contacted: a double-message risk.
            prefix = _norm(short_name(s.person))
            if prefix in known_people:
                nn = prefix
            elif nn in known_companies or not is_queue_person(short_name(s.person)):
                q.unmatched.append((s.person, s.company, "row cells did not resolve to a known person"))
                continue
            elif nn not in fu_people:
                q.unmatched.append((s.person, s.company, "ledgered, rostered nowhere live, and no fu on a NETWORK row"))
        by_person.setdefault(nn, []).append(s)

    # reply evidence: ledger rest-text or NETWORK note
    replied_people = {p for p, rows in by_person.items() if any(REPLY_RE.search(r.rest) for r in rows)}
    for n in net:
        if REPLY_RE.search(n["note"] or ""):
            replied_people.add(_norm(n["name"]))
            q.replied.append((n["name"], n["company"]))

    # classify every rostered person
    for dossier, blocks in people_by_dossier.items():
        rel = f"{dossier}/referrals.md"
        findings = outreach_format.scan_text(rel, (repo / rel).read_text(errors="ignore"))
        flagged = {_norm(short_name(getattr(x, "person", "") or "")) for x in findings}
        for raw_name, _block in blocks:
            name = short_name(raw_name)
            if not is_queue_person(name):
                # A record heading (a status emoji, "Honest notes") is rightly skipped. A block that carries a
                # drafted note or DM is a PERSON whose heading this parser could not read: surface it,
                # never drop it silently.
                if re.search(r"(?im)^\s*[-*>]?\s*\*{0,2}(?:#?\d+\s*[.):·-]?\s*)?(?:connection[ -]note|direct[ -]message|note|dm)\b", _block) \
                        and not NOT_A_QUEUE_PERSON.search(name):
                    q.unmatched.append((raw_name[:70], dossier, "drafted copy under a heading that did not resolve to a person's name"))
                continue
            nn = _norm(name)
            rows = by_person.get(nn, [])
            if not rows:
                if nn in flagged:
                    q.needs_draft.append((name, dossier, "outreach_format finding on this block"))
                else:
                    q.ready.append((name, dossier))
                continue
            if nn in replied_people:
                continue  # thread is live; next move is yours/theirs, not a queue item
            last = max((r.when for r in rows if r.when), default=None)
            note_only = all(NOTE_ONLY_RE.search(r.channel) for r in rows)
            had_followup = any(FOLLOWUP_RE.search(r.channel + " " + r.rest) for r in rows)
            if note_only:
                q.fire_on_accept.append((name, rows[0].company, str(last or "?")))
            elif last and (today - last).days >= FOLLOWUP_DAYS and not had_followup:
                q.followup_due.append((name, rows[0].company, str(last), (today - last).days))

    # the warm-lead reminder engine: make an owed action surface BY NAME
    # Dropping every replied person into a passive count and treating the thread as "live, no
    # action needed" is exactly how a real warm lead quietly goes cold: nothing distinguishes a
    # thread where you owe the next move from one where you're just waiting. The fu field makes
    # the owed move explicit, dated and value-ranked so it can never dissolve into "N replied".
    for n in net:
        m = FU_RE.match((n.get("fu") or "").strip())
        if m:
            state, since_s, what = m.group(1), m.group(2), m.group(3).strip()
            if state == "closed":
                continue  # the thread is over: tracked, never surfaced
            try:
                days = (today - date.fromisoformat(since_s)).days
            except ValueError:
                q.unmatched.append((n["name"], n["company"], f"fu date not on record or not ISO: {since_s!r}"))
                continue
            if state == "me":
                q.owed_reply.append((n["name"], n["company"], since_s, days, what, _fu_rank(what)))
            elif state == "them" and NOTE_ONLY_RE.search(what) and re.search(r"accept", what, re.I) \
                    and not re.search(r"\baccepted\b", what, re.I):
                # a connection note not yet accepted cannot be nudged; the DM waits on the accept (cold.py ages it)
                q.fire_on_accept.append((n["name"], n["company"], since_s))
            elif state == "them" and days >= FOLLOWUP_DAYS:
                q.followup_due.append((n["name"], n["company"], since_s, days))
            # state == "rest": nudge spent / parked (tracked, never surfaced as due)
        elif n["status"] == "active" and REPLY_RE.search(n.get("note") or ""):
            q.untagged_reply.append((n["name"], n["company"]))  # replied, no fu tag: never let it hide

    # pacing budget: today's per-company send counts (small-basket cap, config.SMALL_BASKET_CAP)
    for s in sends:
        if s.when == today:
            q.budget[s.company] = q.budget.get(s.company, 0) + 1

    # holds: any pipeline file whose first lines carry a hold stamp. A hold is the operator's word
    # and survives the file being OUTDATED as a queue; only they lift it (strike the line / say so).
    for f in sorted((repo / "pipeline").glob("*.md")):
        head = "\n".join(f.read_text(errors="ignore").splitlines()[:10])
        if re.search(r"ON HOLD", head, re.I) and not re.search(r"HOLD LIFTED|~~.*ON HOLD.*~~", head, re.I):
            q.holds.append((f.name, next(l for l in head.splitlines() if re.search(r"ON HOLD", l, re.I))[:100]))

    im = repo / "pipeline" / "inmail-ledger.md"
    q.inmail = inmail_balance(im.read_text(errors="ignore")) if im.exists() else "no ledger"

    # owed first by value then staleness; nudges deduped by name; the passive 'replied' count
    # sheds anyone now carried by an actionable bucket, so nobody is both a chore and a tally.
    q.owed_reply.sort(key=lambda r: (r[5], -r[3]))
    _seen: set = set()
    q.followup_due = [r for r in q.followup_due if not (_norm(r[0]) in _seen or _seen.add(_norm(r[0])))]
    _acc: set = set()
    q.fire_on_accept = [r for r in q.fire_on_accept if not (_norm(r[0]) in _acc or _acc.add(_norm(r[0])))]
    _due = {_norm(r[0]) for r in q.followup_due}
    q.fire_on_accept = [r for r in q.fire_on_accept if _norm(r[0]) not in _due]
    _hot = ({_norm(r[0]) for r in q.owed_reply} | {_norm(r[0]) for r in q.followup_due}
            | {_norm(r[0]) for r in q.untagged_reply})
    q.replied = [r for r in q.replied if _norm(r[0]) not in _hot]
    return q


def report(q: Queue) -> str:
    L = ["outreach_queue.py: the DERIVED queue (SSOT: tracker + referrals.md + sent-ledger + inmail-ledger)",
         "  never maintained as a file; re-derive every run",
         "  NOT checked: a social platform's own connection/reply state, and message quality (outreach_format/verify_claims own it)", ""]
    def sec(title, rows, fmt):
        L.append(title if rows else title + " none")
        L.extend(fmt(r) for r in rows)
        L.append("")
    if q.owed_reply:
        L.append(f"🔴🔴 YOU OWE A REPLY: warm leads going cold, act NOW ({len(q.owed_reply)}):")
        L.extend(f"   • {nm} ({co}): {what} (owed {days}d, since {since})"
                 for nm, co, since, days, what, _rank in q.owed_reply)
        L.append("")
    sec(f"🔴 NO-ROSTER: live application, zero outreach people ({len(q.no_roster)}):", q.no_roster,
        lambda r: f"   {r[1]} [{r[2]}]: {r[0]} has no referrals.md people; research + roster first")
    sec(f"✍️ NEEDS-DRAFT: rostered, message incomplete ({len(q.needs_draft)}):", q.needs_draft,
        lambda r: f"   {r[0]}: {r[1]} ({r[2]})")
    sec(f"📮 READY-TO-SEND: gated copy exists, never contacted ({len(q.ready)}):", q.ready,
        lambda r: f"   {r[0]}: {r[1]}")
    sec(f"⏳ FIRE-ON-ACCEPT: note sent, DM waits on their accept ({len(q.fire_on_accept)}):", q.fire_on_accept,
        lambda r: f"   {r[0]} ({r[1]}): note {r[2]}; if accepted, the DM goes")
    sec(f"⏰ FOLLOW-UP-DUE: ≥{FOLLOWUP_DAYS} days silent, no nudge yet, max one ever ({len(q.followup_due)}):",
        q.followup_due, lambda r: f"   {r[0]} ({r[1]}): last touch {r[2]}, {r[3]}d ago")
    sec(f"✅ REPLIED: live threads, next move is theirs/yours ({len(q.replied)}):", q.replied,
        lambda r: f"   {r[0]} ({r[1]})")
    sec(f"⚠️ UNTAGGED REPLIES: a live thread replied but has no fu state; triage it ({len(q.untagged_reply)}):",
        q.untagged_reply, lambda r: f'   {r[0]} ({r[1]}): set fu:"me|<date>|<what>" (you owe) or "them|<date>|<what>"')
    sec(f"❓ UNRESOLVED LEDGER ROWS: reconcile by hand, never silently ({len(q.unmatched)}):", q.unmatched,
        lambda r: f"   {r[0]} ({r[1]}): {r[2]}")
    if q.holds:
        L.append("⏸️ HOLD STAMPS FOUND (you lift these, never the agent):")
        L.extend(f"   {f}: {h}" for f, h in q.holds)
        L.append("")
    if q.budget:
        L.append(f"📊 SENDS TODAY (small-basket cap {SMALL_BASKET_CAP}/company/day):")
        L.extend(f"   {c}: {n}" for c, n in sorted(q.budget.items()))
        L.append("")
    L.append(f"💳 InMail balance: {q.inmail}")
    return "\n".join(L)


# selftest: every protection gets a case, built from the real failure shapes
def selftest() -> int:
    """The fixture's messages link example.com, so the fixture carries its own portfolio value.
    The live knowledge-base/01 is the user's file and must never decide this selftest."""
    saved = outreach_format.portfolio_url
    outreach_format.portfolio_url = lambda: "example.com"
    try:
        return _selftest_body()
    finally:
        outreach_format.portfolio_url = saved


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


def _selftest_body() -> int:
    import tempfile
    ok = True
    def check(label, cond):
        nonlocal ok
        print(("  ✓ " if cond else "  ✗ ") + label)
        ok = ok and cond

    class _FakeCfg:
        @staticmethod
        def local_now():
            from datetime import datetime as _dt
            return _dt(2031, 7, 4, 23, 30)
    global config
    _saved_cfg = config
    config = _FakeCfg()
    try:
        _zone_ok = _today() == date(2031, 7, 4)
    finally:
        config = _saved_cfg
    check("today comes from the configured zone (config.local_now), not the machine clock", _zone_ok)
    check("the fixture's portfolio value is its own, never the user's knowledge-base/01",
          outreach_format.portfolio_url() == "example.com")
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir(); (r / "applications" / "acme-charge-nurse" / ".").mkdir(parents=True)
        (r / "applications" / "initech-charge-nurse").mkdir(parents=True)
        (r / "pipeline" / "tracker.html").write_text(
            '{co:"Acme", role:"rn", status:"applied", folder:"applications/acme-charge-nurse"},\n'
            '{co:"Initech", role:"rn", status:"applied", folder:"applications/initech-charge-nurse"},\n'
            '{co:"Northwind", role:"rn", status:"rejected", folder:"applications/northwind-charge-nurse"},\n'
            '{co:"Umbrella", role:"rn", status:"ghosted", folder:"applications/umbrella-charge-nurse"},\n'
            '{name:"Alex Rivera", company:"Acme", status:"active", note:"REPLIED by phone"},\n'
            # the warm-lead reminder engine: fu-tagged NETWORK rows
            '{name:"Jordan Kim", company:"Acme", status:"active", note:"REPLIED", fu:"me|2031-05-20|said she would refer me to the unit director", link:"x"},\n'
            '{name:"Sam Hooli", company:"Acme", status:"active", note:"REPLIED", fu:"me|2031-05-26|suggested a call after her shift"},\n'
            '{name:"Alex Hooli", company:"Acme", status:"active", note:"DM sent", fu:"them|2031-05-20|wanted my license number, nothing since"},\n'
            '{name:"Jordan Hooli", company:"Acme", status:"active", note:"DM sent", fu:"them|2031-05-26|emailed her this morning"},\n'
            '{name:"Sam Initech", company:"Acme", status:"active", note:"x", fu:"me|not-a-date|broken"},\n'
            '{name:"Alex Initech", company:"Acme", status:"active", note:"nudged", fu:"rest|2031-05-10|second email went out, leaving it there"},\n'
            # the record format: shapes an older cold sweep could not see
            '{name:"Jordan Initech", company:"Acme", status:"active", note:"DM sent", fu:"closed|2031-05-10|posting came down"},\n'
            '{name:"Sam Umbrella", company:"Acme", status:"active", note:"x", fu:"them|2031-05-01|connection request out, no accept yet"},\n'
            '{name:"Jordan Rivera", company:"Globex", status:"active", note:"x", fu:"them|2031-05-01|wrote to the owner directly"},\n')
        def block(nm, handle):
            first = nm.split()[0]
            return (f"### {nm} \u2014 charge nurse · https://www.linkedin.com/in/{handle} · *ask = refer*\n"
                    f"- **Note:** {first}, both our units moved to bedside shift report this year. Samples: example.com. Could you refer me to the hiring lead?\n"
                    f"- **DM:** Use InMail: NO (free path).\n\n"
                    f"{first}, your post on bedside shift report made me redo how my floor runs handoffs.\n\n"
                    f"Samples of my charting audits sit at example.com.\n\nCould you refer me to the hiring lead? Either answer is fine.\n\nJordan\n")
        comma = block("Alex Lee", "eve").replace(
            "### Alex Lee \u2014 charge nurse", "### 6 · Alex Lee, Regional Dispatch Supervisor, named on this posting", 1)
        odd = block("Sam Rivera", "zed").replace(
            "### Sam Rivera \u2014 charge nurse", "### Whoever Picks Up The Phone At The Front Desk On A Slow Monday", 1)
        (r / "applications" / "acme-charge-nurse" / "referrals.md").write_text(
            "## The messages\n\n" + block("Sam Lee", "ann") + "\n" + block("Alex Kim", "bob")
            + "\n" + block("Jordan Lee", "cara") + "\n" + block("Alex Rivera", "riya")
            + "\n" + block("Sam Kim", "dee") + "\n" + comma + "\n" + odd)
        today = date(2031, 5, 27)
        old = (today - timedelta(days=5)).isoformat()
        (r / "pipeline" / "sent-ledger.md").write_text(
            "| date | recipient | company | channel | ref | state | by |\n|---|---|---|---|---|---|---|\n"
            f"| {old} | Alex Kim | Acme | LinkedIn connection note (free) | x | ok | Jordan |\n"          # schema order
            f"| {old} | Acme | Jordan Lee | LinkedIn DIRECT DM | x | ok | Jordan |\n"                      # FLIPPED order
            f"| {today.isoformat()} | Acme | Alex Rivera | EMAIL | x | REPLIED before lunch | Jordan |\n"    # reply + today count
            f'| {old} | Sam Kim (last name off a badge photo \u2014 greeted as "Sam") | Acme | LinkedIn DIRECT DM | x | ok | Jordan |\n'  # decorated name
            f"| {old} | Acme | Hooli Freight Partners | LinkedIn DM | x | ok | Jordan |\n"                      # unresolvable row
            f"| {old} | \u2014 (application form) | Acme | Greenhouse form | SUBMITTED by the user | x | Jordan |\n"  # an application row
            f"| {old} | Jordan Rivera (CEO) | Globex | Email | x | ok | Jordan |\n")                    # a role in brackets
        (r / "pipeline" / "inmail-ledger.md").write_text("| As of | Credits left | Source |\n|---|---|---|\n| 2031-05-20 | **2** | Jordan |\n")
        (r / "pipeline" / "old-queue.md").write_text("# ON HOLD: wait for the agency reply\nrest of the list\n")
        q = build(r, today=today)
        check("ghosted is dead for outreach, never live", "ghosted" in DEAD and "ghosted" not in LIVE)
        check("no-roster catches the live dossier with no referrals.md (and not the dead one)",
              [x[1] for x in q.no_roster] == ["Initech"])
        untouched = "## The messages\n\n### 1 · [Name], [Role] at [Company]\n\n**Connection note:**\n```\n[x]\n```\n"
        check("a heading still holding [Name] is nobody: no roster, so the dossier counts as NO-ROSTER",
              outreach_format.person_blocks(untouched) == []
              and not any("[Name]" in str(u) for u in q.unmatched + q.ready + q.needs_draft))
        check("ready-to-send = the never-contacted people only, INCLUDING a 'Name, Title, ...' comma heading",
              [x[0] for x in q.ready] == ["Sam Lee", "Alex Lee"])
        check("drafted copy under a heading that is not a name SURFACES, never vanishes",
              any("Whoever Picks Up" in u[0] for u in q.unmatched))
        check("note-only send parses in SCHEMA order -> fire-on-accept",
              [x[0] for x in q.fire_on_accept if x[0] != "Sam Umbrella"] == ["Alex Kim"])
        check("FLIPPED-column DM row still resolves to the person -> follow-up due at 5d",
              "Jordan Lee" in [x[0] for x in q.followup_due])
        check("decorated ledger name ('Sam Kim (last name off a badge photo…)') resolves -> NOT ready, follow-up due",
              "Sam Kim" not in [x[0] for x in q.ready] and "Sam Kim" in [x[0] for x in q.followup_due])
        check("unresolvable row surfaces in UNRESOLVED, never silently dropped",
              len(q.unmatched) >= 1)
        check("a live REPLIED row with no fu tag is caught by the safety net, not hidden",
              all("Alex Rivera" not in str(x) for x in q.ready + q.followup_due + q.fire_on_accept)
              and any("Alex Rivera" in x[0] for x in q.untagged_reply))
        # the warm-lead reminder engine
        check("fu=me surfaces as an owed reply, sorted refer-first (the lead you can't lose)",
              [x[0] for x in q.owed_reply] == ["Jordan Kim", "Sam Hooli"])
        check("fu=them past the silence threshold becomes a nudge (followup_due)",
              "Alex Hooli" in [x[0] for x in q.followup_due])
        check("fu=them under the threshold is NOT yet due",
              "Jordan Hooli" not in [x[0] for x in q.followup_due])
        check("an fu-tagged owed person is not also double-counted in the passive replied tally",
              all("Jordan Kim" not in str(x) for x in q.replied))
        check("a malformed fu date surfaces in UNRESOLVED, never silently dropped",
              any("Sam Initech" in u[0] for u in q.unmatched))
        check("fu=rest is parked: never surfaced as due even past the threshold (one-nudge rule)",
              "Alex Initech" not in [x[0] for x in q.followup_due]
              and "Alex Initech" not in [x[0] for x in q.owed_reply])
        check("fu=closed is tracked, never surfaced and never unresolved",
              all("Jordan Initech" not in str(x) for x in q.followup_due + q.owed_reply + q.unmatched + q.fire_on_accept))
        check("fu=them on an unaccepted connection note waits on the accept; it is never a nudge",
              "Sam Umbrella" in [x[0] for x in q.fire_on_accept] and "Sam Umbrella" not in [x[0] for x in q.followup_due])
        check("an application row in the ledger is not a person and never unresolved",
              all("application" not in x[0] for x in q.unmatched))
        check("'Jordan Rivera (CEO)' in the ledger is the 'Jordan Rivera' row, never unresolved",
              all("Jordan Rivera" not in x[0] for x in q.unmatched))
        check("today's sends count toward the per-company budget", q.budget.get("Acme") == 1)
        check("hold stamp surfaced", any("old-queue.md" in h[0] for h in q.holds))
        check("InMail balance read", q.inmail.startswith("2 "))
        check("record-shaped headings never queue as people",
              not any(is_queue_person(x) for x in
                      ["✅ PHONE", "Honest notes on this list", "Unified list (see above)", "None found so far",
                       "Connection request: ON HOLD until the posting reopens",
                       "If the first note goes unanswered", "Not reachable by mail"])
              and all(is_queue_person(x) for x in ["Sam Lee", "Alex K.", "Alexander (Alex) Kim",
                                                   'Samantha "Sam" Rivera']))
        q2 = build(r, today=today + timedelta(days=1))
        (r / "pipeline" / "sent-ledger.md").write_text(
            (r / "pipeline" / "sent-ledger.md").read_text() +
            f"| {today.isoformat()} | Acme | Jordan Lee | LinkedIn DM (follow-up) | x | nudge | Jordan |\n")
        q3 = build(r, today=today + timedelta(days=9))
        check("one nudge maximum: after a follow-up row the person never re-queues",
              all("Jordan Lee" not in x[0] for x in q3.followup_due))
        _ = q2
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main([])  # the selftest's temporary copy has no tracker
    check("no tracker: says not checked and exits 3, no FileNotFoundError",
          rc == 3 and "no tracker yet" in buf.getvalue() and "not checked" in buf.getvalue())
    for _label, _ok in _config_guard_cases():
        check(_label, _ok)
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    try:
        print(report(build()))
    except NoTracker as e:
        print(f"outreach_queue.py: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
