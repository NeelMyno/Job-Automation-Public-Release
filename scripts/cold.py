#!/usr/bin/env python3
"""cold.py: every class of item that can go cold, listed BY NAME, oldest first.

WHY THIS EXISTS
---------------
Ask a session to "surface everything I have let go cold" and it will find the items that already have
a loud, dated, by-name surface (an @OWED with a chase date) and miss almost everything else: the
follow-ups that are only a count ("78 follow-ups due"), the applications with no submit date, the
people messaged with no follow-up state, the connection notes nobody accepted, the parked threads, the
stale leads. So this script gives every class a derivation, a name list with ages, and the next
action. The session-start block prints each class with its oldest names, never a bare count.

    python3 scripts/cold.py              # every class, every item
    python3 scripts/cold.py --brief      # the session-start block
    python3 scripts/cold.py --selftest   # synthetic cases, one per class

THE CLASSES (thresholds live in scripts/config.py, with the defaults below):
  app-silent         applied, no @OWED, submitted COLD_APP_DAYS or more days ago (default 21)
  app-undated        applied, the submit date is not on record
  owed-reply         fu=me: you owe the move
  owed-overdue       an @OWED past its chase date
  owed-undated       an @OWED dated '?'
  interview-untracked  a live interview with no @OWED (commitments.py's CRITICAL)
  takehome-untracked   a take-home, assessment or exercise in a live row's next: with no @OWED naming it
  nudge-due          outreach quiet FOLLOWUP_DAYS+ days, nudge not sent (from outreach_queue)
  accept-stale       a connection note not accepted after COLD_ACCEPT_DAYS (default 14): try another
                     channel once, or close the thread
  parked             fu=rest older than COLD_REST_DAYS (default 30): revisit or close
  reply-untagged     a reply recorded in a note, no fu
  contacted-no-fu    the ledger shows a message, the person has no fu or no NETWORK row (records_check)
  ledger-unresolved  a sent-ledger row no script ties to a person
  lead-stale         a lead posted more than COLD_LEAD_DAYS ago (default 21), still a lead
  lead-undated       a lead whose posted date is unknown (cannot age)
  inmail-stale       the InMail balance was last counted before the latest refill (only when
                     config.INMAIL_REFILL_DAY is set)

NOT checked: anything no record holds (a reply you never logged is invisible here, and agents never
read LinkedIn or your logged-in accounts to find one). An item is listed from its record; whether it
is truly cold is your call.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import records as R  # noqa: E402

try:
    import config  # optional user knobs (scripts/config.py)
except ImportError:  # pragma: no cover
    config = None  # type: ignore[assignment]


def _knob(name: str, default):
    v = getattr(config, name, None) if config is not None else None
    return default if v is None else v


N_APP = int(_knob("COLD_APP_DAYS", 21))         # most rejections that ever arrive have arrived by about day 21
N_ACCEPT = int(_knob("COLD_ACCEPT_DAYS", 14))   # a connection note not accepted in two weeks
N_REST = int(_knob("COLD_REST_DAYS", 30))       # a parked thread comes back after a month
N_LEAD = int(_knob("COLD_LEAD_DAYS", 21))       # a lead older than this has had its decision window
REFILL_DAY = _knob("INMAIL_REFILL_DAY", None)   # day of month paid-message credits refill; None = class off
ASSIGN_RE = re.compile(r"take[- ]home|assignment|assessment|exercise|challenge|work sample|case study task", re.I)


@dataclass
class Item:
    name: str
    detail: str
    age: int | None      # days; None when the date is not on record


@dataclass
class Cold:
    key: str
    title: str
    action: str
    items: list = field(default_factory=list)

    def sort(self):
        self.items.sort(key=lambda i: (i.age is None, -(i.age or 0), i.name))
        return self


def _age(d: date | None, today: date) -> int | None:
    return (today - d).days if d else None


def _iso(s: str) -> date | None:
    try:
        return date.fromisoformat(s) if isinstance(s, str) and R.ISO.match(s) else None
    except ValueError:
        return None


def _last_refill(today: date, day: int) -> date:
    import calendar

    def clamp(y, m):
        return date(y, m, min(day, calendar.monthrange(y, m)[1]))
    this = clamp(today.year, today.month)
    if today >= this:
        return this
    return clamp(today.year - 1, 12) if today.month == 1 else clamp(today.year, today.month - 1)


def build(repo: Path = REPO, today: date | None = None, q=None) -> list:
    import commitments as cm
    import outreach_queue as oq
    import records_check as rc
    today = today or date.today()
    t = R.load_tracker(repo=repo)
    if q is None:
        q = oq.build(repo, today=today)
    C = {k: Cold(k, title, action) for k, title, action in (
        ("app-silent", f"Applied, no word in {N_APP}+ days", "chase once (the referral contact or the recruiter), or let it go"),
        ("app-undated", "Applied, submit date not on record", "find the date (the confirmation email) and set `applied`"),
        ("owed-reply", "You owe a reply", "reply"),
        ("owed-overdue", "@OWED past its chase date", "do it, or chase them"),
        ("owed-undated", "@OWED with no date", "give it a date"),
        ("interview-untracked", "Live interview with no tracked next step", "add the @OWED"),
        ("takehome-untracked", "Take-home or assessment with no @OWED", "add the @OWED with its due date"),
        ("nudge-due", f"Outreach quiet {oq.FOLLOWUP_DAYS}+ days, nudge not sent", "send the one nudge, or close the thread"),
        ("accept-stale", f"Connection note not accepted after {N_ACCEPT}+ days", "try another channel once, or close the thread"),
        ("parked", f"Parked thread older than {N_REST} days", "revisit, or close the thread"),
        ("reply-untagged", "Reply recorded, no follow-up state", "set fu (me if you owe, them if they do)"),
        ("contacted-no-fu", "Messaged, but no follow-up state on record", "add the NETWORK row's fu"),
        ("ledger-unresolved", "Sent-ledger row tied to no person", "fix the ledger row or the person's NETWORK row"),
        ("lead-stale", f"Lead posted {N_LEAD}+ days ago, no decision", "build it, or pass it"),
        ("lead-undated", "Lead with no posted date", "check the posting, or pass it"),
        ("inmail-stale", "Paid-message balance not counted since the last refill", "read the balance; one row in the ledger"),
    )}

    # applications
    for r in t.apps:
        st = R.s(r.get("status"))
        co, role = R.s(r.get("co")), R.s(r.get("role"))
        nxt = R.s(r.get("next"))
        owed = R.owed(co, nxt, "next")
        if st == "applied" and not owed:
            d, kind = R.applied_info(r.get("applied"))
            if kind in ("exact", "upper-bound"):
                a = _age(d, today)
                if a is not None and a >= N_APP:     # day N is cold: the title says "N+ days"
                    C["app-silent"].items.append(Item(f"{co}: {role}", ("submitted " if kind == "exact" else "submitted on or before ")
                                                      + d.isoformat(), a))
            elif kind in ("unknown", "missing", "bad"):
                C["app-undated"].items.append(Item(f"{co}: {role}", f"applied {r.get('applied')!r}", None))
        if st not in R.DEAD_APP and ASSIGN_RE.search(nxt) and not any(ASSIGN_RE.search(o.what) for o in owed):
            C["takehome-untracked"].items.append(Item(f"{co}: {role}", nxt[:120], None))
        if st == "lead":
            p = _iso(R.s(r.get("posted")))
            if p:
                a = _age(p, today)
                if a > N_LEAD:
                    C["lead-stale"].items.append(Item(f"{co}: {role}", f"posted {p.isoformat()}", a))
            else:
                C["lead-undated"].items.append(Item(f"{co}: {role}", "posted unknown", None))
    # @OWED and live interviews (owner: commitments.py)
    res = cm.build(t.html, today=today, check_calls=False)
    for o in res.overdue:
        C["owed-overdue"].items.append(Item(f"{o.co}", f"{o.owner} owes: {o.what[:110]} (chase {o.chase})", _age(o.chase, today)))
    for o in res.undated:
        C["owed-undated"].items.append(Item(f"{o.co}", f"{o.owner} owes: {o.what[:110]}", None))
    for co in res.missing_interviews:
        C["interview-untracked"].items.append(Item(co, "status interview/offer, no @OWED", None))
    # people (the derived outreach queue)
    for nm, co, since, days, what, _rank in q.owed_reply:
        C["owed-reply"].items.append(Item(f"{nm} ({co})", f"since {since}: {what[:100]}", days))
    for nm, co, last, days in q.followup_due:
        C["nudge-due"].items.append(Item(f"{nm} ({co})", f"last touch {last}", days))
    for nm, co, nd in q.fire_on_accept:
        a = _age(_iso(nd), today)
        if a is None or a >= N_ACCEPT:
            C["accept-stale"].items.append(Item(f"{nm} ({co})", f"note sent {nd}", a))
    for nm, co in q.untagged_reply:
        C["reply-untagged"].items.append(Item(f"{nm} ({co})", "REPLIED in the note, no fu", None))
    for person, co, why in q.unmatched:
        C["ledger-unresolved"].items.append(Item(f"{person} ({co})", why[:100], None))
    for n in t.net:
        f = R.parse_fu(n.get("fu"))
        if f and f.state == "rest":
            a = _age(f.since, today)
            if a is None or a > N_REST:
                C["parked"].items.append(Item(f"{R.s(n.get('name'))} ({R.s(n.get('company'))[:40]})",
                                              f"since {f.since.isoformat() if f.since else '?'}: {f.what[:100]}", a))
    F, _T = rc.run(files=["pipeline/sent-ledger.md"], repo=repo)
    for x in F:
        if "no `fu`" in x.problem or "no NETWORK row exists" in x.problem:
            C["contacted-no-fu"].items.append(Item(x.where.replace("NETWORK ", "").replace("(none) for ", ""), x.problem[:100], None))
    # paid-message credits (optional)
    ip = repo / "pipeline" / "inmail-ledger.md"
    if REFILL_DAY and ip.is_file():
        rows = re.findall(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(?:\*\*)?(\d+|unknown)(?:\*\*)?\s*\|", ip.read_text(errors="replace"), re.M)
        if rows:
            last = date.fromisoformat(rows[-1][0])
            refill = _last_refill(today, int(REFILL_DAY))
            if last < refill:
                C["inmail-stale"].items.append(Item(f"balance {rows[-1][1]} as of {rows[-1][0]}", f"refill {refill.isoformat()} has no row",
                                                    _age(last, today)))
    return [c.sort() for c in C.values()]


def _ages(it: Item) -> str:
    return f"{it.age}d" if it.age is not None else "undated"


def session_lines(classes: list, top: int = 3) -> list:
    live = [c for c in classes if c.items]
    n = sum(len(c.items) for c in live)
    if not live:
        return ["  GONE COLD: nothing (scripts/cold.py)"]
    L = [f"  GONE COLD: {n} item(s) in {len(live)} class(es), oldest first (scripts/cold.py):"]
    for c in live:
        head = "; ".join(f"{i.name[:44]} {_ages(i)}" for i in c.items[:top])
        more = f"; +{len(c.items) - top} more" if len(c.items) > top else ""
        L.append(f"     * {c.title} ({len(c.items)}): {head}{more} -> {c.action}")
    L.append("     The full lists: python3 scripts/cold.py")
    return L


def report(classes: list) -> str:
    L = ["cold.py: every class that can go cold, by name, oldest first",
         "  NOT checked: anything no record holds (an unlogged reply is invisible)", ""]
    for c in classes:
        L.append(f"[{c.key}] {c.title} ({len(c.items)}) -> {c.action}")
        for i in c.items:
            L.append(f"   {_ages(i):>8}  {i.name[:70]} . {i.detail[:110]}")
        L.append("")
    return "\n".join(L)


def selftest() -> int:
    import tempfile
    from datetime import timedelta
    global REFILL_DAY
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(("  PASS " if cond else "  FAIL ") + label)
    print("cold.py selftest (synthetic records)\n")
    today = date(2026, 3, 23)
    d = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731
    row = ('  {{co:"{co}", role:"{role}", status:"{st}", posted:"{posted}", source:"s", jd:"", apply:"", folder:"{folder}", '
           'refs:0, everify:"?",{applied} next:"{next}"}},\n')

    def app(co, st="applied", applied=None, nxt="x", posted="unknown", role="Analyst", folder=""):
        return row.format(co=co, role=role, st=st, posted=posted, folder=folder,
                          applied="" if applied is None else f' applied:"{applied}",', next=nxt)
    saved = REFILL_DAY
    REFILL_DAY = 7
    try:
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "pipeline").mkdir()
            (r / "applications" / "mirror-analyst").mkdir(parents=True)
            (r / "applications" / "fathom-analyst").mkdir(parents=True)
            (r / "applications" / "fathom-analyst" / "referrals.md").write_text(
                "## The messages\n\n### 2 · sam B. (Ads design)\n"
                "**Ask:** would you be open to referring me?\n\n**Connection note (241 chars):**\n> Hi Sam, a note.\n")
            html = ('<script>const APPLICATIONS = [\n'
                    + app("Acme", applied=d(63), nxt="waiting")
                    + app("Globex", applied=f"on or before {d(34)}")
                    + app("Fresh", applied=d(5))
                    + app("Owedco", applied=d(60), nxt=f"@OWED[them|{d(1)}|recruiter call]")
                    + app("Initech", st="interview", applied=d(20),
                          nxt=f"Riley will send a take-home @OWED[them|{d(-3)}|Riley: send the next round]")
                    + app("Mirror", applied=d(3), folder="applications/mirror-analyst")
                    + app("OldLead", st="lead", posted=d(40))
                    + app("Edge21", applied=d(21))
                    + app("Edge20", applied=d(20))
                    + '  {co:"NoDate", role:"Analyst", status:"applied", posted:"unknown", source:"s", jd:"", apply:"", folder:"", refs:0, everify:"?", next:"x"},\n'
                    + app("UnknownDate", applied="unknown")
                    + app("Northwind", st="active", posted=d(30), nxt="sent the DM @OWED[them|2026-03-01|reply to the DM]")
                    + app("Undatedco", st="lead", nxt="@OWED[you|?|decide whether to apply]")
                    + app("Panelco", st="interview", applied="2026-03-01", nxt="panel done, waiting")
                    + app("Fathom", applied=d(3), folder="applications/fathom-analyst")
                    + app("TakeHomeCo", st="applied", applied=d(2), nxt="they sent a take-home assignment, due Friday")
                    + '];\nconst NETWORK = [\n'
                    f'  {{name:"Quinn Quiet", company:"Acme", role:"r", status:"active", note:"x", fu:"them|{d(63)}|DM sent, no reply recorded"}},\n'
                    f'  {{name:"Nadia Note", company:"Acme", role:"r", status:"active", note:"x", fu:"them|{d(15)}|connection note sent, waiting on accept"}},\n'
                    f'  {{name:"Kai Parked", company:"Globex", role:"r", status:"active", note:"x", fu:"rest|{d(58)}|one nudge sent, no reply recorded"}},\n'
                    f'  {{name:"Jordan Rivera", company:"Initech", role:"r", status:"active", note:"x", fu:"me|{d(9)}|reply about the referral"}},\n'
                    f'  {{name:"Clara Closed", company:"Acme", role:"r", status:"active", note:"x", fu:"closed|{d(90)}|role closed"}},\n'
                    '  {name:"Rene Nofu", company:"Northwind", role:"r", status:"active", note:"Connection note sent"},\n'
                    '  {name:"Bea Replied", event:"meetup", role:"Analyst at Globex", status:"active", notes:"REPLIED with a good-luck note"},\n'
                    '];\nconst STATUS = {lead:{}, active:{}, applied:{}, interview:{}, offer:{}, rejected:{}, passed:{}};\n'
                    'const NET_STATUS = {lead:{}, active:{}, passed:{}};\nlet view="apps";</script>')
            (r / "pipeline" / "tracker.html").write_text(html)
            (r / "pipeline" / "sent-ledger.md").write_text(
                "| date | recipient | company | channel | message-ref | copy-state-at-send | sent-by |\n|---|---|---|---|---|---|---|\n"
                "| 2026-01-26 | Rene Nofu | Northwind | LinkedIn connection note | r | ok | me |\n"
                "| 2026-01-26 | Holly Ledger | Mirror | InMail | r | ok | me |\n")
            (r / "pipeline" / "inmail-ledger.md").write_text("## Current balance\n| As of | Credits left | Source |\n|---|---|---|\n"
                                                             "| 2026-01-20 | 2 | me |\n")
            (r / "applications" / "mirror-analyst" / "referrals.md").write_text(
                "## The messages\n\n### Ann Alpha \u2014 analyst · https://example.com/ann · *ask = refer*\n"
                "- **Note:** I read your work. Would you be open to referring me?\n")
            cl = {c.key: c for c in build(r, today)}
            names = {k: [i.name for i in c.items] for k, c in cl.items()}
            has = lambda k, s: any(s in n for n in names[k])  # noqa: E731
            check("app-silent: applied 63 days ago, no @OWED", has("app-silent", "Acme"))
            check("app-silent: an 'on or before' date ages the row (34 d)", has("app-silent", "Globex"))
            check("a 5-day application and an @OWED application are not cold",
                  not has("app-silent", "Fresh") and not has("app-silent", "Owedco"))
            check("app-silent: exactly day 21 is cold, day 20 is not", has("app-silent", "Edge21") and not has("app-silent", "Edge20"))
            check("app-undated: no `applied` key, and applied 'unknown'", has("app-undated", "NoDate") and has("app-undated", "UnknownDate"))
            check("nudge-due: a DM silent 63 days", has("nudge-due", "Quinn Quiet"))
            check("accept-stale: a connection note not accepted after 15 days", has("accept-stale", "Nadia Note"))
            check("parked: fu=rest at 58 days comes back", has("parked", "Kai Parked"))
            check("owed-reply: fu=me", has("owed-reply", "Jordan Rivera"))
            check("contacted-no-fu: ledgered, NETWORK row without fu", has("contacted-no-fu", "Rene Nofu"))
            check("contacted-no-fu: ledgered, no NETWORK row at all", has("contacted-no-fu", "Holly Ledger"))
            check("a closed thread never surfaces", not any("Clara Closed" in n for v in names.values() for n in v))
            check("takehome-untracked: a take-home in next: with no @OWED naming it",
                  has("takehome-untracked", "Initech") and has("takehome-untracked", "TakeHomeCo"))
            check("lead-stale: a lead posted 40 days ago", has("lead-stale", "OldLead"))
            check("lead-undated: a lead with posted unknown", has("lead-undated", "Undatedco"))
            check("owed-undated: an @OWED dated '?'", has("owed-undated", "Undatedco"))
            check("owed-overdue: a chase date in the past", has("owed-overdue", "Northwind"))
            check("interview-untracked: a live interview with no @OWED", has("interview-untracked", "Panelco"))
            check("reply-untagged: REPLIED in the notes, no fu", has("reply-untagged", "Bea Replied"))
            check("ledger-unresolved: drafted copy under a heading that is not a name", has("ledger-unresolved", "sam B."))
            check("inmail-stale: a balance from before the latest refill (the 7th)", names["inmail-stale"])
            import outreach_queue as oq
            qq = oq.build(r, today=today)
            check("a dossier's roster is read through its folder (Ann Alpha is in the queue)",
                  "Ann Alpha" in [x[0] for x in qq.ready + qq.needs_draft])
            lines = session_lines(list(cl.values()))
            check("the session block names items, never a bare count",
                  all(re.search(r"\(\d+\): \S", ln) for ln in lines if ln.startswith("     * ")))
            check("items are oldest first",
                  [i.age for i in cl["app-silent"].items] == sorted((i.age for i in cl["app-silent"].items), reverse=True))
            later = {c.key: c.items for c in build(r, date(2026, 3, 22) + timedelta(days=0))}
            nw = [i for i in later["owed-overdue"] if "Northwind" in i.name]
            check("owed-overdue carries its age in days (21 on 2026-03-22)", nw and nw[0].age == 21)
            early = {c.key: c.items for c in build(r, date(2026, 2, 27))}
            check("owed-overdue: the same @OWED is not overdue before its date",
                  not any("Northwind" in i.name for i in early["owed-overdue"]))
            REFILL_DAY = None
            check("inmail-stale is off when INMAIL_REFILL_DAY is not set",
                  not {c.key: c.items for c in build(r, today)}["inmail-stale"])
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "pipeline").mkdir()
            (r / "pipeline" / "tracker.html").write_text(
                '<script>const APPLICATIONS = [\n];\nconst NETWORK = [\n];\nlet view="apps";</script>')
            empty = build(r, today)
            check("an empty tracker with no ledger yields nothing cold", not any(c.items for c in empty)
                  and session_lines(empty)[0].endswith("nothing (scripts/cold.py)"))
    finally:
        REFILL_DAY = saved
    print("\nSELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    classes = build()
    print("\n".join(session_lines(classes)) if a.brief else report(classes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
