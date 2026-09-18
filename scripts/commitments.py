#!/usr/bin/env python3
"""commitments.py -- surface owed / awaited next-steps so a commitment can never hide in a
transcript again.

ROOT CAUSE THIS CLOSES
-----------------------
A live interview round produces a real commitment -- the interviewer says they'll recommend
advancing you, or that someone on their side will send a take-home, or that they'll get back to
you by a certain day. That commitment is easy to write down in a call-notes file and easy to never
look at again, because nothing structured carries it and nothing at the next session start
surfaces it. The person, not the tool, ends up being the one who remembers to chase it -- which
means the single most valuable thing a job search produces (a live interview's next step) has no
mechanical guard at all. This script is that guard.

THE MECHANISM
-------------
An owed/awaited action is marked inline, inside the tracker fields that already exist, with a token:

    @OWED[<owner>|<chase-date>|<what>]

  owner      = them | you           (who owes the next move -- the token's own two literal
                                      values, kept short and stable)
  chase-date = YYYY-MM-DD | ?       (when to chase it / expect it; ? = undated, itself a flag)
  what       = free text, no ']'    (the concrete action)

The token lives inside an APPLICATIONS row's `next:` field, or a NETWORK row's `fu:` field. It is
human-readable in the tracker AND machine-parseable here -- one field, no second file to drift (a
maintained side-file is its own anti-pattern: it rots the moment anything else changes state).

THE TEETH
---------
  1. EVERY status:"interview" (or "offer") APPLICATIONS row MUST carry >=1 @OWED[...] in `next:`.
     Missing  ->  CRITICAL "LIVE INTERVIEW, NO TRACKED NEXT-STEP" (the exact failure this exists
     to catch).
  2. An @OWED whose chase-date is in the past and still open  ->  OVERDUE (act now).
  3. chase-date '?'  ->  UNDATED (give it a date so it can go overdue).
  4. Soft net: a live (interview/offer) row whose dossier has a `calls/` folder but no @OWED on
     its row  ->  REVIEW "a call is logged; its owed action is not tracked."

Session-start prints a loud, un-ignorable block (see session_lines). Wiring this into your own
harness's session-start hook is a separate step; this script only computes and prints.

Usage:  commitments.py [--selftest]
Exit 0 = clean.  2 = at least one CRITICAL (a live interview with no tracked next-step) exists.
"""
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRACKER = REPO / "pipeline" / "tracker.html"

OWED_RE = re.compile(r"@OWED\[\s*(them|you)\s*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|\?)\s*\|\s*([^\]]*?)\s*\]")
LIVE_STATUSES = ("interview", "offer")  # an APPLICATIONS row that has a live owed next-step

# A JD-embedded application_deadline is invisible to any tracker status/next sweep: a dossier can
# be built end-to-end, never filled, with a real close date sitting unread inside its own JD file,
# while the tracker still shows a `next:` field written as if the dossier were unbuilt. This
# catches that class: an ISO deadline on a not-yet-submitted dossier, within DEADLINE_WINDOW_DAYS.
DEADLINE_RE = re.compile(r"application[ _]deadline[^0-9\n]{0,40}?([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
DEADLINE_WINDOW_DAYS = 30
# Statuses where the form has NOT gone out yet. This MUST match whatever your own throughput-style
# gate treats as pre-submit (this repo's own convention: lead/active, not yet applied). Getting
# this wrong in either direction is a real regression class: excluding "active" (the dominant
# built/fill-ready pre-submit status) silently misses a built-but-unsent dossier with an imminent
# deadline; including "interview" (already submitted and advanced) nags to "fill or drop" something
# already sent.
NOT_SUBMITTED = ("lead", "sponsor", "active")


class Owed:
    def __init__(self, co, owner, chase, what, field):
        self.co = co
        self.owner = owner          # "them" | "you" (the token's literal owner values)
        self.chase = chase          # date | None (None == undated '?')
        self.what = what
        self.field = field          # "next" | "fu"

    def state(self, today):
        if self.chase is None:
            return "undated"
        if self.chase < today:
            return "overdue"
        if (self.chase - today).days <= 2:
            return "due-soon"
        return "scheduled"

    def days_over(self, today):
        return (today - self.chase).days if self.chase and self.chase < today else 0


class Result:
    def __init__(self):
        self.interviews = []            # (co, [Owed,...])  -- every live interview row, with its owed items
        self.missing_interviews = []    # co -- live interview/offer row with NO @OWED  (CRITICAL)
        self.overdue = []               # [Owed]
        self.due_soon = []              # [Owed]
        self.undated = []               # [Owed]
        self.review_calls = []          # co -- live row whose dossier has calls/ but no @OWED
        self.all_owed = []              # every Owed parsed (incl. network fu)

    @property
    def critical(self):
        return bool(self.missing_interviews)


def _objects(js: str):
    """Yield each top-level {...} object string from a JS array body (tolerant, quote-aware)."""
    i, n = 0, len(js)
    while i < n:
        if js[i] == "{":
            d = 0
            j = i
            instr = False
            q = ""
            while j < n:
                c = js[j]
                if instr:
                    if c == q and js[j - 1] != "\\":
                        instr = False
                elif c in "\"'":
                    instr = True
                    q = c
                elif c == "{":
                    d += 1
                elif c == "}":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            yield js[i:j + 1]
            i = j + 1
        else:
            i += 1


def _field(obj: str, name: str):
    m = re.search(name + r'\s*:\s*"((?:[^"\\]|\\.)*)"', obj)
    return m.group(1) if m else ""


def _parse_owed(co, text, field):
    out = []
    for owner, chase, what in OWED_RE.findall(text or ""):
        cd = None
        if chase != "?":
            try:
                cd = datetime.strptime(chase, "%Y-%m-%d").date()
            except ValueError:
                cd = None
        out.append(Owed(co, owner, cd, what.strip(), field))
    return out


def build(html: str = None, today: date = None, check_calls: bool = True) -> Result:
    if html is None:
        html = TRACKER.read_text(errors="ignore") if TRACKER.exists() else ""
    if today is None:
        today = date.today()
    r = Result()

    # APPLICATIONS array (its rows carry status + next:)
    am = re.search(r"APPLICATIONS\s*=\s*\[(.*?)\n\s*\];", html, re.S) or \
        re.search(r"APPLICATIONS\s*=\s*\[(.*)\]", html, re.S)
    app_body = am.group(1) if am else ""
    for obj in _objects(app_body):
        co = _field(obj, "co")
        status = _field(obj, "status")
        nxt = _field(obj, "next")
        owed = _parse_owed(co, nxt, "next")
        r.all_owed.extend(owed)
        if status in LIVE_STATUSES:
            r.interviews.append((co, owed))
            if not owed:
                r.missing_interviews.append(co)
                if check_calls:
                    folder = _field(obj, "folder")
                    if folder and (REPO / folder / "calls").is_dir():
                        r.review_calls.append(co)

    # NETWORK array (fu: can also carry an @OWED -- e.g. a warm node awaiting a specific action)
    nm = re.search(r"NETWORK\s*=\s*\[(.*?)\n\s*\];", html, re.S) or \
        re.search(r"NETWORK\s*=\s*\[(.*)\]", html, re.S)
    net_body = nm.group(1) if nm else ""
    for obj in _objects(net_body):
        nm_name = _field(obj, "name")
        fu = _field(obj, "fu")
        r.all_owed.extend(_parse_owed(nm_name, fu, "fu"))

    for o in r.all_owed:
        st = o.state(today)
        if st == "overdue":
            r.overdue.append(o)
        elif st == "due-soon":
            r.due_soon.append(o)
        elif st == "undated":
            r.undated.append(o)

    r.overdue.sort(key=lambda o: -o.days_over(today))
    return r


class Deadline:
    def __init__(self, co, folder, when, jd):
        self.co = co
        self.folder = folder
        self.when = when
        self.jd = jd

    def days_left(self, today):
        return (self.when - today).days


def deadlines(html: str = None, today: date = None, window: int = DEADLINE_WINDOW_DAYS) -> list:
    """Imminent JD `application_deadline` on a built-but-UNSENT dossier -- the class the tracker's
    status/next fields are structurally blind to. Reads each not-yet-submitted dossier's jd-*.md."""
    if html is None:
        html = TRACKER.read_text(errors="ignore") if TRACKER.exists() else ""
    if today is None:
        today = date.today()
    am = re.search(r"APPLICATIONS\s*=\s*\[(.*?)\n\s*\];", html, re.S) or \
        re.search(r"APPLICATIONS\s*=\s*\[(.*)\]", html, re.S)
    body = am.group(1) if am else ""
    out = []
    for obj in _objects(body):
        if _field(obj, "status") not in NOT_SUBMITTED:
            continue
        folder = _field(obj, "folder").replace("applications/", "").strip("/")
        if not folder:
            continue
        d = REPO / "applications" / folder
        if not d.is_dir():
            continue
        for jd in sorted(d.glob("jd-*.md")):
            try:
                m = DEADLINE_RE.search(jd.read_text(errors="ignore"))
            except OSError:
                continue
            if not m:
                continue
            try:
                when = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if today <= when <= today + timedelta(days=window):
                out.append(Deadline(_field(obj, "co"), folder, when, str(jd.relative_to(REPO))))
            break  # the first jd file carrying a deadline is enough
    out.sort(key=lambda x: x.when)
    return out


def session_lines(today: date = None) -> list:
    """The loud, un-ignorable block for the session-start readout. Interviews first -- a live
    interview's next step is, by design, the single most valuable line this script can print."""
    try:
        r = build(today=today)
    except Exception as e:  # noqa: BLE001 -- a bug here must never block a session from starting
        return [f"  ⚠ commitments unavailable ({type(e).__name__}: {e}) -- run scripts/commitments.py by hand."]
    t = today or date.today()
    out = []
    if r.interviews:
        out.append("")
        out.append(f"  \U0001F3AF\U0001F3AF LIVE INTERVIEWS -- DO NOT DROP THESE ({len(r.interviews)}):")
        for co, owed in r.interviews:
            if not owed:
                out.append(f"     • {co} -- \U0001F534\U0001F534 NO TRACKED NEXT-STEP (a commitment may already be lost -- add @OWED[...] to its next:)")
                continue
            for o in owed:
                st = o.state(t)
                if st == "overdue":
                    tag = f"\U0001F534 OVERDUE {o.days_over(t)}d"
                elif st == "due-soon":
                    tag = f"⏰ due by {o.chase}"
                elif st == "undated":
                    tag = "⚠ UNDATED (give it a chase date)"
                else:
                    tag = f"chase by {o.chase}"
                who = "THEY owe" if o.owner == "them" else "\U0001F7E2 YOU owe"
                out.append(f"     • {co} -- {tag} · {who}: {o.what}")
    if r.missing_interviews:
        out.append(f"  \U0001F534\U0001F534\U0001F534 {len(r.missing_interviews)} LIVE INTERVIEW(S) WITH NO TRACKED NEXT-STEP "
                   f"(exactly the failure this script exists to catch): {', '.join(r.missing_interviews)} -- add @OWED[owner|date|what] now.")
    # Owed items OUTSIDE the interview rows that are overdue/due-soon (network nodes, etc.)
    extra_over = [o for o in r.overdue if o.co not in {c for c, _ in r.interviews}]
    if extra_over:
        head = "; ".join(f"{o.co}: {o.what} ({o.days_over(t)}d over)" for o in extra_over[:4])
        more = f" +{len(extra_over) - 4} more" if len(extra_over) > 4 else ""
        out.append(f"  ⏰ {len(extra_over)} OTHER owed item(s) OVERDUE: {head}{more}")
    if r.review_calls:
        out.append(f"  ⚠ {len(r.review_calls)} live dossier(s) have a logged call but no tracked owed-action: "
                   f"{', '.join(r.review_calls)} -- mine the call for its commitment.")
    try:
        dls = deadlines(today=t)
    except Exception:  # noqa: BLE001
        dls = []
    if dls:
        out.append(f"  ⏳ APPLICATION DEADLINE(S) on built-but-UNSENT dossiers ({len(dls)}) -- fill or drop before they close:")
        for d in dls:
            out.append(f"     • {d.co} -- closes {d.when} ({d.days_left(t)}d) · {d.folder}")
    return out


def selftest() -> int:
    print("commitments.py selftest\n")
    ok = True

    def c(desc, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'} {desc}: got {got!r} want {want!r}")

    T = date(2026, 1, 15)

    # (a) A live interview row WITH a valid future-dated @OWED -- clean, no CRITICAL.
    good = ('var APPLICATIONS=[{co:"Globex", status:"interview", '
            'next:"Interview round done 01-14. @OWED[them|2026-01-30|Riley to send the design take-home]", '
            'folder:"applications/zzz-nope"}];\nvar NETWORK=[];')
    rg = build(good, today=T, check_calls=False)
    c("valid interview @OWED -> no CRITICAL", rg.critical, False)
    c("valid interview @OWED -> not overdue", len(rg.overdue), 0)

    # (b) THE exact failure this exists to catch: a live interview row with NO @OWED -> CRITICAL fires.
    bad = ('var APPLICATIONS=[{co:"Globex", status:"interview", '
           'next:"Interview round done 01-14, strongly positive, take-home next", '
           'folder:"applications/zzz-nope"}];\nvar NETWORK=[];')
    rb = build(bad, today=T, check_calls=False)
    c("interview with NO @OWED -> CRITICAL", rb.critical, True)
    c("  and names the company", rb.missing_interviews, ["Globex"])

    # (c) An overdue @OWED is caught.
    od = ('var APPLICATIONS=[{co:"Initech", status:"interview", '
          'next:"@OWED[them|2025-12-28|round-2 decision]", folder:"applications/zzz"}];\nvar NETWORK=[];')
    ro = build(od, today=T, check_calls=False)
    c("past-dated @OWED -> overdue", len(ro.overdue), 1)
    c("  overdue day-count correct", ro.overdue[0].days_over(T), 18)

    # (d) An undated @OWED ('?') is flagged undated, not crashed.
    un = ('var APPLICATIONS=[{co:"Umbrella", status:"interview", '
          'next:"@OWED[them|?|reschedule times]", folder:"applications/zzz"}];\nvar NETWORK=[];')
    ru = build(un, today=T, check_calls=False)
    c("undated @OWED -> undated bucket", len(ru.undated), 1)
    c("undated @OWED -> not CRITICAL (it IS tracked)", ru.critical, False)

    # (e) A rejected/dead row with no @OWED is NOT a CRITICAL (only live statuses are required).
    dead = ('var APPLICATIONS=[{co:"Wonka", status:"rejected", next:"REJECTED"}];\nvar NETWORK=[];')
    rd = build(dead, today=T, check_calls=False)
    c("dead row with no @OWED -> no CRITICAL", rd.critical, False)

    # (f) Deadline regex: pull the ISO date next to application_deadline; ignore none/null/past-format.
    m_dl = DEADLINE_RE.search("**Application deadline:** 2026-02-02 (`application_deadline` in the API)")
    c("deadline regex pulls the ISO date", m_dl.group(1) if m_dl else None, "2026-02-02")
    c("deadline regex ignores 'none listed'", bool(DEADLINE_RE.search("application_deadline: none listed")), False)
    c("deadline regex ignores null", bool(DEADLINE_RE.search("application_deadline: null (none set)")), False)
    c("deadline regex ignores a non-ISO placeholder", bool(DEADLINE_RE.search("accepted until {7/10/2026}")), False)

    # (g) Deadline STATUS SCOPING, driven end-to-end through deadlines() with real jd files. An
    #     'active' (built, fill-ready) dossier with an imminent deadline MUST surface; an
    #     'interview' (already submitted + advanced) dossier must NOT. Getting this backwards is a
    #     real regression class -- see NOT_SUBMITTED's own comment above.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for nm in ("acme-active", "beta-interview"):
            dd = tdp / "applications" / nm
            dd.mkdir(parents=True)
            (dd / "jd-x.md").write_text("**Application deadline:** 2026-01-20\n")
        dl_html = ('var APPLICATIONS=['
                   '{co:"AcmeActive", status:"active", next:"tailor, apply", folder:"applications/acme-active"},'
                   '{co:"BetaInterview", status:"interview", next:"@OWED[them|2026-01-30|x]", folder:"applications/beta-interview"}'
                   '];\nvar NETWORK=[];')
        global REPO, TRACKER
        _saved_repo, _saved_tracker = REPO, TRACKER
        REPO = tdp
        TRACKER = tdp / "pipeline" / "tracker.html"
        try:
            cos = {d.co for d in deadlines(dl_html, today=T, window=30)}
            c("an ACTIVE dossier w/ imminent deadline SURFACES", "AcmeActive" in cos, True)
            c("an INTERVIEW dossier (already submitted) does NOT surface", "BetaInterview" in cos, False)
        finally:
            REPO, TRACKER = _saved_repo, _saved_tracker

    print("\nSELFTEST OK" if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    r = build()
    t = date.today()
    lines = session_lines(t)
    if lines:
        print("\n".join(l for l in lines if l.strip()))
    else:
        print("No live interviews or owed items tracked.")
    if r.critical:
        print(f"\n❌ CRITICAL: {len(r.missing_interviews)} live interview(s) with no tracked next-step: "
              f"{', '.join(r.missing_interviews)}")
        sys.exit(2)
    print(f"\n✅ {len(r.interviews)} live interview(s) tracked · {len(r.overdue)} overdue · "
          f"{len(r.due_soon)} due-soon · {len(r.undated)} undated")
    sys.exit(0)
