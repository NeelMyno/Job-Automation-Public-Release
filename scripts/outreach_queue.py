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

Ledger-parsing note: the sent-ledger's stated schema is date·recipient·company·… but rows
appended 2026-07-25 onward flipped the two columns (date·company·recipient). The ledger is
append-only so the drift stays; this parser resolves each row by matching cells against the
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
import outreach_format  # person_blocks + scan_text: ONE owner of the person grammar (§8)

# scripts/config.py is optional. See that file's own docstring. Falls back to this script's
# historical defaults (4-day nudge threshold, 3/day small-basket cap) if it has never been created.
try:
    import config
except ImportError:
    class config:  # type: ignore[no-redef]
        """Fallback when scripts/config.py has not been created yet (safe defaults only)."""
        FOLLOWUP_DAYS = 4
        SMALL_BASKET_CAP = 3

FOLLOWUP_DAYS = config.FOLLOWUP_DAYS      # silence threshold before the single permitted nudge
SMALL_BASKET_CAP = config.SMALL_BASKET_CAP  # sends/company/day when company is small/unknown
LIVE = {"applied", "interview", "offer", "active"}
DEAD = {"rejected", "passed"}
REPLY_RE = re.compile(r"\brepl(?:y|ied|ies)\b|\bREPLIED\b", re.I)
FOLLOWUP_RE = re.compile(r"follow[- ]?up|nudge", re.I)

# The warm-lead reminder engine. A NETWORK row carries an optional structured follow-up state so
# an owed action surfaces BY NAME every session instead of dissolving into a passive "N replied"
# count. Format: fu:"<state>|<YYYY-MM-DD>|<what>", state ∈ {me, them, rest}.
#   me   = you owe the next move (reply / send the referral details); ALWAYS surfaced, loud.
#   them = waiting on them; becomes a nudge after FOLLOWUP_DAYS of silence.
#   rest = the one permitted nudge is spent, or the thread is parked: tracked, never surfaced as
#          due (the one-nudge rule). It re-surfaces only by a reply flipping it back to "me".
FU_RE = re.compile(r"^(me|them|rest)\|([^|]+)\|(.*)$", re.S)  # date validated in build() so a bad one surfaces
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
    ("Ann Alpha — designer · https://… · *ask = refer*"); the ledger and tracker carry just
    "Ann Alpha". Split on the first em-dash/middot to compare like with like. A trailing
    UNCLOSED paren is a role descriptor cut mid-way ("Chris Dzoba (peer engineer") and gets
    trimmed; a balanced paren is a nickname ("Jonathan (Jonny) Summers-Muir") and stays."""
    n = re.split(r"\s+—\s+|\s+·\s+|\s+-\s+", heading.strip(), maxsplit=1)[0].strip().strip("*_`")
    if n.count("(") > n.count(")"):
        n = n[:n.rindex("(")].strip()
    return n


# Real referrals.md files carry `###` headings that are records, not people ("✅ EMAIL",
# "Honest gaps", "Unified pack (pointer)", "Connection note: NOT SENDABLE…"). The live run of
# 2026-07-27 leaked seven of these into the queue as sendable people; this is the filter.
NOT_A_QUEUE_PERSON = re.compile(
    r"[:✅⏳🔴]|^(?:if|none|not |no |honest|unified|connection|dm\b|email\b|inmail|sent|blocked|"
    r"pending|update|status|the |a |an )", re.I)


def is_queue_person(name: str) -> bool:
    n = name.strip()
    return bool(n) and not NOT_A_QUEUE_PERSON.search(n) and n[0].isupper() and len(n.split()) <= 5


# ── tracker ──────────────────────────────────────────────────────────────────────────────
def tracker_rows(tracker_text: str) -> tuple[list[dict], list[dict]]:
    """APPLICATIONS rows (co,status,folder) and NETWORK rows (name,company,status,note)."""
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


# ── sent-ledger ──────────────────────────────────────────────────────────────────────────
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


# ── inmail balance ───────────────────────────────────────────────────────────────────────
def inmail_balance(text: str) -> str:
    rows = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\*{0,2}(\d+)\*{0,2}\s*\|", text)
    return f"{rows[-1][1]} (as of {rows[-1][0]})" if rows else "UNKNOWN: read pipeline/inmail-ledger.md"


# ── the queue itself ─────────────────────────────────────────────────────────────────────
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


def build(repo: Path = REPO, today: date | None = None) -> Queue:
    today = today or date.today()
    q = Queue()
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

    ledger_p = repo / "pipeline" / "sent-ledger.md"
    sends = parse_ledger(ledger_p.read_text(errors="ignore"), known_people, known_companies) \
        if ledger_p.exists() else []
    by_person: dict[str, list[Send]] = {}
    for s in sends:
        nn = _norm(s.person)
        if nn not in known_people:
            # Ledger rows decorate names ('Fei H. (surname unverified — addressed as "Fei")');
            # unresolved, that decoration made Fei look never-contacted: a double-message risk.
            prefix = _norm(short_name(s.person))
            if prefix in known_people:
                nn = prefix
            elif nn in known_companies or not is_queue_person(short_name(s.person)):
                q.unmatched.append((s.person, s.company, "row cells did not resolve to a known person"))
                continue
            else:
                q.unmatched.append((s.person, s.company, "ledgered but rostered nowhere live"))
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

    # ── the warm-lead reminder engine: make an owed action surface BY NAME ──
    # Dropping every replied person into a passive count and treating the thread as "live, no
    # action needed" is exactly how a real warm lead quietly goes cold: nothing distinguishes a
    # thread where you owe the next move from one where you're just waiting. The fu field makes
    # the owed move explicit, dated and value-ranked so it can never dissolve into "N replied".
    for n in net:
        m = FU_RE.match((n.get("fu") or "").strip())
        if m:
            state, since_s, what = m.group(1), m.group(2), m.group(3).strip()
            try:
                days = (today - date.fromisoformat(since_s)).days
            except ValueError:
                q.unmatched.append((n["name"], n["company"], f"fu date not ISO: {since_s!r}"))
                continue
            if state == "me":
                q.owed_reply.append((n["name"], n["company"], since_s, days, what, _fu_rank(what)))
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


# ── selftest: every protection gets a case, built from the real failure shapes ──────────
def selftest() -> int:
    import tempfile
    ok = True
    def check(label, cond):
        nonlocal ok
        print(("  ✓ " if cond else "  ✗ ") + label)
        ok = ok and cond
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "pipeline").mkdir(); (r / "applications" / "acme-designer" / ".").mkdir(parents=True)
        (r / "applications" / "beta-designer").mkdir(parents=True)
        (r / "pipeline" / "tracker.html").write_text(
            '{co:"Acme", role:"d", status:"applied", folder:"applications/acme-designer"},\n'
            '{co:"Beta", role:"d", status:"applied", folder:"applications/beta-designer"},\n'
            '{co:"Dead", role:"d", status:"rejected", folder:"applications/dead-designer"},\n'
            '{name:"Riya Rep", company:"Acme", status:"active", note:"REPLIED 07-20"},\n'
            # the warm-lead reminder engine: fu-tagged NETWORK rows
            '{name:"Ref Refnandez", company:"Acme", status:"active", note:"REPLIED", fu:"me|2026-07-20|agreed to refer, the big one", link:"x"},\n'
            '{name:"Chat Chatterjee", company:"Acme", status:"active", note:"REPLIED", fu:"me|2026-07-26|offered a coffee chat"},\n'
            '{name:"Quiet Quinn", company:"Acme", status:"active", note:"DM sent", fu:"them|2026-07-20|asked for resume then quiet"},\n'
            '{name:"Fresh Fields", company:"Acme", status:"active", note:"DM sent", fu:"them|2026-07-26|just messaged, waiting"},\n'
            '{name:"Bad Date", company:"Acme", status:"active", note:"x", fu:"me|not-a-date|broken"},\n'
            '{name:"Rest Restman", company:"Acme", status:"active", note:"nudged", fu:"rest|2026-07-10|the one nudge is spent, awaiting reply"},\n')
        def block(nm, handle):
            return (f"### {nm} — designer · https://www.linkedin.com/in/{handle} · *ask = refer*\n"
                    f"- **Note:** I read your work, {nm.split()[0]}. My work is at example.com. Would you be open to referring me?\n"
                    f"- **DM:** Use InMail: NO (free path).\n\n"
                    f"Hi {nm.split()[0]}, I read your case study on onboarding and the retention detail stuck with me.\n\n"
                    f"My work is at example.com.\n\nWould you be open to referring me? A no with a reason helps too.\n\nJordan\n")
        (r / "applications" / "acme-designer" / "referrals.md").write_text(
            "## The messages\n\n" + block("Ann Alpha", "ann") + "\n" + block("Bob Beta", "bob")
            + "\n" + block("Cara Gamma", "cara") + "\n" + block("Riya Rep", "riya")
            + "\n" + block("Dee Delta", "dee"))
        today = date(2026, 7, 27)
        old = (today - timedelta(days=5)).isoformat()
        (r / "pipeline" / "sent-ledger.md").write_text(
            "| date | recipient | company | channel | ref | state | by |\n|---|---|---|---|---|---|---|\n"
            f"| {old} | Bob Beta | Acme | LinkedIn connection note (free) | x | ok | Jordan |\n"          # schema order
            f"| {old} | Acme | Cara Gamma | LinkedIn DIRECT DM | x | ok | Jordan |\n"                      # FLIPPED order
            f"| {today.isoformat()} | Acme | Riya Rep | EMAIL | x | she REPLIED same day | Jordan |\n"    # reply + today count
            f'| {old} | Dee Delta (surname unverified — addressed as "Dee") | Acme | LinkedIn DIRECT DM | x | ok | Jordan |\n'  # decorated name
            f"| {old} | Acme | Zzz Unknown Corp | LinkedIn DM | x | ok | Jordan |\n")                     # unresolvable row
        (r / "pipeline" / "inmail-ledger.md").write_text("| As of | Credits left | Source |\n|---|---|---|\n| 2026-07-20 | **2** | Jordan |\n")
        (r / "pipeline" / "old-queue.md").write_text("# ⏸️ ON HOLD: do not send\nstuff\n")
        q = build(r, today=today)
        check("no-roster catches the live dossier with no referrals.md (and not the dead one)",
              [x[1] for x in q.no_roster] == ["Beta"])
        check("ready-to-send = the never-contacted person only", [x[0] for x in q.ready] == ["Ann Alpha"])
        check("note-only send parses in SCHEMA order -> fire-on-accept",
              [x[0] for x in q.fire_on_accept] == ["Bob Beta"])
        check("FLIPPED-column DM row still resolves to the person -> follow-up due at 5d",
              "Cara Gamma" in [x[0] for x in q.followup_due])
        check("decorated ledger name ('Dee Delta (surname unverified…)') resolves -> NOT ready, follow-up due",
              "Dee Delta" not in [x[0] for x in q.ready] and "Dee Delta" in [x[0] for x in q.followup_due])
        check("unresolvable row surfaces in UNRESOLVED, never silently dropped",
              len(q.unmatched) >= 1)
        check("a live REPLIED row with no fu tag is caught by the safety net, not hidden",
              all("Riya" not in str(x) for x in q.ready + q.followup_due + q.fire_on_accept)
              and any("Riya" in x[0] for x in q.untagged_reply))
        # ── the warm-lead reminder engine ──
        check("fu=me surfaces as an owed reply, sorted refer-first (the lead you can't lose)",
              [x[0] for x in q.owed_reply] == ["Ref Refnandez", "Chat Chatterjee"])
        check("fu=them past the silence threshold becomes a nudge (followup_due)",
              "Quiet Quinn" in [x[0] for x in q.followup_due])
        check("fu=them under the threshold is NOT yet due",
              "Fresh Fields" not in [x[0] for x in q.followup_due])
        check("an fu-tagged owed person is not also double-counted in the passive replied tally",
              all("Ref Refnandez" not in str(x) for x in q.replied))
        check("a malformed fu date surfaces in UNRESOLVED, never silently dropped",
              any("Bad Date" in u[0] for u in q.unmatched))
        check("fu=rest is parked: never surfaced as due even past the threshold (one-nudge rule)",
              "Rest Restman" not in [x[0] for x in q.followup_due]
              and "Rest Restman" not in [x[0] for x in q.owed_reply])
        check("today's sends count toward the per-company budget", q.budget.get("Acme") == 1)
        check("hold stamp surfaced", any("old-queue.md" in h[0] for h in q.holds))
        check("InMail balance read", q.inmail.startswith("2 "))
        check("record-shaped headings never queue as people",
              not any(is_queue_person(x) for x in
                      ["✅ EMAIL", "Honest gaps", "Unified pack (pointer)", "None. No recipient exists yet",
                       "Connection note: NOT SENDABLE (invite already pending)",
                       "If LinkedIn will not let a second message through", "Not found / honest gaps"])
              and all(is_queue_person(x) for x in ["Ann Alpha", "Fei H.", "Jonathan (Jonny) Summers-Muir",
                                                   'Elizabeth "Lizzy" Nammour']))
        q2 = build(r, today=today + timedelta(days=1))
        (r / "pipeline" / "sent-ledger.md").write_text(
            (r / "pipeline" / "sent-ledger.md").read_text() +
            f"| {today.isoformat()} | Acme | Cara Gamma | LinkedIn DM (follow-up) | x | nudge | Jordan |\n")
        q3 = build(r, today=today + timedelta(days=9))
        check("one nudge maximum: after a follow-up row the person never re-queues",
              all("Cara" not in x[0] for x in q3.followup_due))
        _ = q2
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    print(report(build()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
