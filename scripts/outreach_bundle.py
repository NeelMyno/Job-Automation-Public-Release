#!/usr/bin/env python3
"""outreach_bundle.py: the copy-paste outreach files, compiled from the record, gated on the way out.

Outreach is worked from Markdown files: per company, per person, a connection note and a DM, each in
its own fenced block so a paste keeps the paragraph breaks (the locked layout,
`.claude/outreach-handover-format.md`). This script is the one generator, so no session rebuilds it in
a scratchpad.

What it does, in order:
  1. SCOPE, derived, never maintained (the SSOT law, `.claude/commands/outreach.md`): every dossier the
     derived queue (`outreach_queue.build()`) lists as READY-TO-SEND, plus every dossier where a
     connection note left on/after --since and that person's DM has not (the on-accept DMs), minus any
     dossier whose application is at interview/offer or dead (a live process is your own thread, not
     a cold send) and any --hold slug. `--dossiers-file` overrides the derivation with an explicit list.
  2. PER-DOSSIER GATES, run this minute, never trusted from a report: `outreach_format` exit 0,
     `verify_claims` with ZERO findings on referrals.md, and `voice_check` clean on every message that
     would be handed over (hard facts, your never-say list, over-confidence phrases, dashes). A dossier
     that fails is left OUT and listed under NOT READY with the reason. How the writing sounds is
     knowledge-base/17-writing.md's read-aloud review, not a detector.
  3. WRITE two gitignored, disposable files (the source of truth stays each dossier's `referrals.md`,
     read VERBATIM): `pipeline/outreach-bundle-<date>.md` = connection notes ONLY, for people nobody
     has contacted yet, and `pipeline/outreach-bundle-dms-on-accept.md` = every DM still to send,
     handed over when you report who accepted.

Usage:
  python3 scripts/outreach_bundle.py                      # derive scope, gate, write
  python3 scripts/outreach_bundle.py --status             # gate and report only; write nothing
  python3 scripts/outreach_bundle.py --since 2026-01-05   # how far back an already-sent note still owes a DM
  python3 scripts/outreach_bundle.py --hold acme-staff-engineer globex-analyst
  python3 scripts/outreach_bundle.py --dossiers-file list.txt --out x.md --dms-out dms.md
  python3 scripts/outreach_bundle.py --selftest
Exit 0 = written (or --status with nothing failing). 1 = a gate failed or nothing ready. 2 = usage.

Company size (the big/small pacing basket, CLAUDE.md §13.7) comes from scripts/config.py
`BIG_COMPANIES` (optional; empty means every company is paced as small, the safe default).
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import config  # optional user knobs
except ImportError:  # pragma: no cover
    config = None  # type: ignore[assignment]

BIG = {re.sub(r"[^a-z0-9]", "", c.lower()) for c in (getattr(config, "BIG_COMPANIES", None) or [])}
SMALL_CAP = getattr(config, "SMALL_BASKET_CAP", 3) if config else 3

PROFILE = re.compile(r"https?://[A-Za-z.]*linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)
INMAIL = re.compile(r"use\s+inmail\s*:?\s*\**\s*(yes|no)", re.I)
ASKSHAPE = re.compile(r"ask\s*=\s*([^)\n*]+)", re.I)
NOT_DRAFTED = re.compile(r"NOT[ -]DRAFTED|no messages? (?:yet|drafted)|research(?:-| )stage|deliberately not drafted|"
                         r"do not send|do-not-contact", re.I)
FIRST_DEGREE = re.compile(r"\b1st°|\b1st[- ]degree\b|already connected", re.I)
NOTE_MARK = re.compile(r"^\s*[-*>]?\s*\*{0,2}(?:#?\d+\s*[.):·-]?\s*)?(?:connection[ -]note|note)\b.*$", re.I | re.M)
DM_MARK = re.compile(r"^\s*[-*>]?\s*\*{0,2}(?:#?\d+\s*[.):·-]?\s*)?(?:direct[ -]message|DM|message)\b.*$", re.I | re.M)
_DM_WORDS = re.compile(r"\bdm\b|direct message|\binmail\b|\bemail\b", re.I)
_INMAIL_NEGATED = re.compile(r"inmail\s*:?\s*no\b[^;,)]*|\bno inmail\b[^;,)]*|inmail\s+not\b[^;,)]*", re.I)
DMS_FILE = "outreach-bundle-dms-on-accept.md"
DASHES = re.compile("[\u2013\u2014]")

try:  # the SENT-marker grammar has one owner, outreach_format.py; fall back only if it can't load
    from outreach_format import ALREADY_SENT, UNSENT_TAIL, person_blocks
except Exception:  # pragma: no cover
    print("outreach_bundle: scripts/outreach_format.py could not be imported", file=sys.stderr)
    raise


# parse
def _sent_kinds_from_text(s: str) -> set[str]:
    """Which message kinds a SENT line or a ledger channel cell names: 'note', 'dm', or both."""
    s = _INMAIL_NEGATED.sub(" ", s)
    has_note = "connection note" in s.lower() or re.search(r"\bnote\b", s, re.I) is not None
    has_dm = _DM_WORDS.search(s) is not None
    if has_note and not has_dm:
        return {"note"}
    if has_dm and not has_note:
        return {"dm"}
    return {"note", "dm"}


def _person_key(heading: str) -> str:
    h = re.sub(r"^\d+\s*[·.)\-]\s*", "", heading).strip("*_` ")
    h = re.split(r"\s+[·,:]\s+|\s+-\s+|\s*\(|\s*:\s|\s*\u2014", h, maxsplit=1)[0]
    return re.sub(r"\s+", " ", h).strip().lower()


def ledger_kinds(ledger_text: str) -> dict[str, dict[str, set[str]]]:
    """{dossier-slug: {recipient: {'note','dm'}}} from pipeline/sent-ledger.md rows whose message-ref
    names an applications/<slug>/ path. Ledger schema: date | recipient | company | channel | message-ref | ..."""
    out: dict[str, dict[str, set[str]]] = {}
    for ln in ledger_text.splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.match(r"\d{4}-\d\d-\d\d$", cells[0]):
            continue
        who = re.sub(r"\s+", " ", re.sub(r"\s*\(.*?\)\s*", " ", cells[1])).strip().lower()
        for slug in re.findall(r"applications/([^/`\s]+)/", cells[4]):
            out.setdefault(slug, {}).setdefault(who, set()).update(_sent_kinds_from_text(cells[3]))
    return out


def _extract_body(block: str, start: re.Pattern, end: re.Pattern | None) -> str:
    """The message text after its marker: fenced, blockquoted, or inline after the marker."""
    ms = start.search(block)
    if not ms:
        return ""
    region = block[ms.end():]
    if end:
        me = end.search(region)
        if me:
            region = region[:me.start()]
    fen = re.search(r"```[a-z]*\n([\s\S]*?)\n```", region)
    if fen and fen.group(1).strip():
        return fen.group(1).strip("\n")
    lines, started = [], False
    for ln in region.splitlines():
        if ln.lstrip().startswith(">"):
            started = True
            lines.append(re.sub(r"^\s*>\s?", "", ln))
        elif started and not ln.strip():
            lines.append("")
        elif started:
            break
    while lines and not lines[-1].strip():
        lines.pop()
    if "\n".join(lines).strip():
        return "\n".join(lines).strip("\n")
    inline = re.sub(r"^.*?(?:connection[ -]note|direct[ -]message|\bDM\b|\bmessage\b)", "", ms.group(0), count=1, flags=re.I)
    inline = re.sub(r"^\s*\*{0,2}\s*(?:\([^)]*\)\s*)?(?:·?\s*use\s+inmail\s*:?\s*(?:yes|no))?\s*\**\s*(?:\([^)]*\)\s*)?[:·*\s]*",
                    "", inline, flags=re.I).strip()
    return inline if len(inline) >= 15 else ""


def sent_kinds(block: str, person: str, slug: str, ledger: dict) -> set[str]:
    """What already left for this person: the dated in-block SENT marker (only the sentence carrying it
    says which kind) and/or the sent-ledger."""
    kinds: set[str] = set()
    m = ALREADY_SENT.search(block)
    if m and not UNSENT_TAIL.search(block):
        ls = block.rfind("\n", 0, m.start()) + 1
        le = block.find("\n", m.end())
        line = block[ls:(le if le != -1 else len(block))]
        stop = re.search(r"[.!?](?:\s|$)", line[m.end() - ls:])
        kinds |= _sent_kinds_from_text(line[:(m.end() - ls) + stop.start()] if stop else line)
    key = _person_key(person)
    for who, ks in ledger.get(slug, {}).items():
        if len(key) >= 4 and (who == key or who.startswith(key + " ") or key.startswith(who + " ")):
            kinds |= ks
    return kinds


def parse_people(text: str, slug: str, ledger: dict | None = None) -> list[dict]:
    """Everyone in this referrals.md who still has something to send, copy VERBATIM."""
    ledger = ledger or {}
    people = []
    for raw, block in person_blocks(text):
        if NOT_DRAFTED.search(block):
            continue
        kinds = sent_kinds(block, raw, slug, ledger)
        note = _extract_body(block, NOTE_MARK, DM_MARK)
        dm = _extract_body(block, DM_MARK, None)
        connected = bool(FIRST_DEGREE.search(block))
        to_note = bool(note) and "note" not in kinds and not connected
        to_dm = bool(dm) and "dm" not in kinds
        if not (to_note or to_dm):
            continue
        name = re.sub(r"^\d+\s*[·.)\-]\s*", "", raw).strip("*_` ")
        why = ""
        seps = [s for s in (" \u2014 ", " - ", " · ", ", ", ": ") if s in name]
        if seps:
            at, sep = min((name.find(s), s) for s in seps)
            name, why = name[:at], name[at + len(sep):]
        why = PROFILE.sub("", re.sub(r"·?\s*Profile:\s*", "", why)).strip(" ·()")
        prof, ask, inm = PROFILE.search(block), ASKSHAPE.search(block), INMAIL.search(block)
        people.append(dict(
            name=name.strip(), why=why, profile=prof.group(0) if prof else "",
            note=note if to_note else "", dm=dm if to_dm else "",
            note_sent=bool(note) and "note" in kinds, connected=connected,
            inmail=(inm.group(1).upper() if inm else "NO"), ask=(ask.group(1).strip() if ask else "")))
    return people


def voice_problems(people: list[dict]) -> list[str]:
    import voice_check
    out = []
    for p in people:
        for kind in ("note", "dm"):
            if p[kind]:
                bad = voice_check.check(p[kind])
                if bad:
                    out.append(f"{p['name']} · {kind}: [{bad[0][0]}] \"{bad[0][1][:40]}\"")
    return out


def dossier_gates(slug: str) -> tuple[int, int]:
    """(outreach_format exit code, verify_claims findings that sit on referrals.md), run now."""
    ofx = subprocess.run([sys.executable, "scripts/outreach_format.py", f"applications/{slug}/referrals.md"],
                         cwd=REPO, capture_output=True, text=True)
    vc = subprocess.run([sys.executable, "scripts/verify_claims.py", f"applications/{slug}"],
                        cwd=REPO, capture_output=True, text=True)
    return ofx.returncode, len(re.findall(r"^\s*\[R\d+\]\s+referrals\.md", vc.stdout, re.M))


# scope (derived)
def derive_scope(since: date, hold: set[str], ledger_text: str) -> tuple[list[str], list[str]]:
    import outreach_queue
    q = outreach_queue.build()
    slugs = {str(d).rstrip("/").split("/")[-1] for _p, d in q.ready}
    for ln in ledger_text.splitlines():  # a note that left on/after `since` still owes its DM
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.match(r"\d{4}-\d\d-\d\d$", cells[0]) and \
                date.fromisoformat(cells[0]) >= since and _sent_kinds_from_text(cells[3]) == {"note"}:
            slugs.update(re.findall(r"applications/([^/`\s]+)/", cells[4]))
    held = set(hold)
    tracker = REPO / "pipeline" / "tracker.html"
    apps = outreach_queue.tracker_rows(tracker.read_text(errors="ignore"))[0] if tracker.exists() else []
    co_of = {}
    for a in apps:
        if a.get("folder"):
            s = a["folder"].rstrip("/").split("/")[-1]
            co_of[s] = a.get("co", "")
            if a.get("status") in ("interview", "offer", "rejected", "passed", "withdrawn"):
                held.add(s)
    live = sorted(s for s in slugs if s not in held and (REPO / "applications" / s / "referrals.md").exists())
    # An active thread is a judgment call, so it is surfaced, never auto-held.
    for person, company, _since, days, _what, _rank in q.owed_reply:
        key = re.sub(r"\s*\(.*", "", company).strip().lower()
        for s in live:
            if key and key == co_of.get(s, "").strip().lower():
                print(f"  ! active thread at {co_of[s]}: you owe {person} a reply ({days}d). "
                      f"Cold notes to their colleagues are your call; to leave it out: --hold {s}")
    return live, sorted(slugs & held)


# render (the locked layout)
def clean_title(t: str) -> tuple[str, str, str]:
    t = re.sub(r"\breferral pack\b", "", t, flags=re.I).strip(" ·-:\u2014")
    t = re.sub(r"^Referrals?\s*(?:\u2014|-|for|:|,)\s*", "", t, flags=re.I).strip()
    parts = re.split(r"\s+[\u2014·:]\s+|:\s+", t, maxsplit=1)
    company = parts[0].strip() if parts else t
    role = parts[1].strip() if len(parts) > 1 else ""
    rm = re.search(r"\(([^)]*(?:job|req|greenhouse|ashby|lever|id)[^)]*)\)", t, re.I)
    return company, re.sub(r"\s*\([^)]*\)\s*$", "", role).strip(), (rm.group(1).strip() if rm else "")


def basket(company: str, slug: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", company.lower())
    if key in BIG or slug.split("-")[0] in BIG:
        return "big: send everyone the same day (no daily cap)"
    return f"small: up to {SMALL_CAP}/company/day, hiring node first"


def fence(txt: str) -> str:
    return "```\n" + txt.strip("\n") + "\n```"


def _person_head(p: dict) -> list[str]:
    L = [f"## {p['_i']}. {p['name']}" if "_i" in p else f"### {p['name']}"]
    if p["profile"]:
        L.append(f"**Profile:** {p['profile']}")
    why = [x for x in (p["why"], f"ask = {p['ask']}" if p["ask"] else "") if x]
    if why:
        L.append(f"**Why:** {' · '.join(why)}")
    if p["inmail"] == "YES":
        L.append("🔴 **InMail: YES**")
    return L


def render(compiled: list[dict], today: str) -> str:
    """The SEND file: connection notes only. A person whose note already left is not in it, and no DM
    is in it, except a 1st-degree contact, whose DM is the only message there is to send."""
    blocks, n_people = [], 0
    for c in sorted(compiled, key=lambda c: c["title"].lower()):
        ps = [p for p in c["people"] if p["note"] or (p["connected"] and p["dm"])]
        if not ps:
            continue
        company, role, req = clean_title(c["title"])
        B = ["---", "", f"# {company}" + (f": {role}" if role else ""),
             " · ".join(([f"**{req}**"] if req else []) + [basket(company, c["slug"])]), ""]
        for i, p in enumerate(ps, 1):
            B += _person_head(dict(p, _i=i))
            if p["connected"]:
                B += ["*(1st-degree: no connection request needed; send this as a normal message now)*", "",
                      "**Message:**", fence(p["dm"]), ""]
            else:
                B += ["", "**Connection note:**", fence(p["note"]), ""]
        blocks += B + [""]
        n_people += len(ps)
    n_co = sum(1 for ln in blocks if ln.startswith("# "))
    head = [f"# Connection notes ({today})", "",
            f"**{n_co} companies · {n_people} people. Connection notes only.**", "",
            "- Everyone here is someone the records say you haven't sent a note to yet.",
            "- **Note** = the free connection request. Copy the block as is; the code fence keeps the paragraph breaks.",
            f"- **The DMs are not in this file.** They're in `pipeline/{DMS_FILE}`. When people accept, tell me who and I'll hand you their DMs.",
            "- **InMail:** default is NO. A block marked `InMail: YES` says why.",
            f"- **Pacing:** big company = everyone the same day; small = up to {SMALL_CAP} per company per day, hiring node first.",
            "- As you send, tell me who got a note and I'll log it.", ""]
    return "\n".join(head + blocks)


def render_dms(compiled: list[dict], today: str, notes_file: str) -> str:
    """The HOLD file: every DM still to send. Part 1 = the note already left; Part 2 = the note is in
    the send file. Copy is verbatim, never re-typed."""
    parts: dict[int, list[str]] = {1: [], 2: []}
    counts = {1: 0, 2: 0}
    for c in sorted(compiled, key=lambda c: c["title"].lower()):
        company, role, _req = clean_title(c["title"])
        for k in (1, 2):
            ps = [p for p in c["people"]
                  if p["dm"] and not p["connected"] and (p["note_sent"] or not p["note"]) == (k == 1)]
            if not ps:
                continue
            parts[k] += [f"## {company}" + (f": {role}" if role else ""), ""]
            for p in ps:
                parts[k] += _person_head(p) + ["", "*Your note already went out.*" if k == 1 else
                                               "*Note not sent yet (it is in the send file).*", "", "**DM:**", fence(p["dm"]), ""]
            counts[k] += len(ps)
    head = [f"# DMs for after people accept ({today})", "",
            "**Not for sending now.** When people accept your connection request, tell me who and I'll hand you their DMs.", "",
            f"- **Part 1: your note already went out ({counts[1]} people).** Waiting on them to accept.",
            f"- **Part 2: not contacted yet ({counts[2]} people).** Their notes are in `{notes_file}`.",
            "- DMs you've already sent are not here. Every DM is copied word for word from the dossier's `referrals.md`.", "",
            "---", "", "# Part 1: note already sent, waiting on accept", ""]
    return "\n".join(head + parts[1] + ["---", "", "# Part 2: not contacted yet (send the note first)", ""] + parts[2]) + "\n"


# run
def run(argv: list[str]) -> int:
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default
    try:
        since = date.fromisoformat(opt("--since", (date.today() - timedelta(days=14)).isoformat()))
    except ValueError:
        print("usage: --since YYYY-MM-DD", file=sys.stderr)
        return 2
    hold: set[str] = set()
    if "--hold" in argv:
        for a in argv[argv.index("--hold") + 1:]:
            if a.startswith("-"):
                break
            hold.add(a)
    today = date.today().isoformat()
    ledger_path = REPO / "pipeline" / "sent-ledger.md"
    ledger_text = ledger_path.read_text(encoding="utf-8", errors="replace") if ledger_path.exists() else ""
    ledger = ledger_kinds(ledger_text)
    out_path = Path(opt("--out", str(REPO / "pipeline" / f"outreach-bundle-{today}.md")))
    dfile = opt("--dossiers-file")
    if dfile:
        slugs = [ln.strip().rstrip("/").split("/")[-1] for ln in Path(dfile).read_text().splitlines() if ln.strip()]
        held = sorted(set(slugs) & hold)
        slugs = [s for s in slugs if s not in hold]
    else:
        slugs, held = derive_scope(since, hold, ledger_text)
    print(f"scope: {len(slugs)} dossiers (derived from the queue + notes sent since {since})"
          + (f" · held out: {', '.join(held)}" if held else ""))

    compiled, not_ready = [], []
    for slug in slugs:
        ref = REPO / "applications" / slug / "referrals.md"
        if not ref.exists():
            not_ready.append((slug, "no referrals.md"))
            continue
        text = ref.read_text(encoding="utf-8", errors="replace")
        people = parse_people(text, slug, ledger)
        if not people:
            continue
        ofx, refs = dossier_gates(slug)
        vp = voice_problems(people)
        if ofx != 0:
            not_ready.append((slug, f"outreach_format exit {ofx}: run it on the dossier for the exact lines"))
        elif refs:
            not_ready.append((slug, f"verify_claims: {refs} finding(s) on referrals.md"))
        elif vp:
            not_ready.append((slug, f"voice_check ({len(vp)}): {vp[0]}"))
        else:
            h1 = re.search(r"^#{1,2}\s+(.+)$", text, re.M)
            compiled.append(dict(slug=slug, title=(h1.group(1).strip() if h1 else slug), people=people))

    print(f"READY: {len(compiled)} companies · {sum(len(c['people']) for c in compiled)} people")
    print(f"NOT READY: {len(not_ready)} (left out; copy that has not passed is never handed over; fix and re-run)")
    for slug, why in not_ready:
        print(f"  - {slug}  [{why}]")
    if "--status" in argv:
        return 1 if not_ready else 0
    if not compiled:
        print("\nNOT WRITTEN: nothing is ready.")
        return 1
    out_path.write_text(render(compiled, today), encoding="utf-8")
    dms_path = Path(opt("--dms-out", str(out_path.parent / DMS_FILE)))
    try:
        rel = out_path.resolve().relative_to(REPO)
    except ValueError:
        rel = out_path
    dms_path.write_text(render_dms(compiled, today, str(rel)), encoding="utf-8")
    print(f"\nWROTE {out_path}  (connection notes only)")
    print(f"WROTE {dms_path}  (the DMs, held until you report who accepted)")
    return 1 if not_ready else 0


def selftest() -> int:
    passed = failed = 0

    def want(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
        print(f"  {'PASS' if cond else 'FAIL'} {label}")

    doc = ("# Acme: Staff Engineer (req 4417) · referral pack\n\n## The messages\n\n"
           "### 1 · Pat Probe: Engineering Lead\n✅ SENT 2026-01-05 (connection note, by me). DM: send after accept.\n"
           "**Profile: https://www.linkedin.com/in/patprobe/**\n\n**Connection note:**\n> Hi Pat, a note that already left.\n\n"
           "**Direct message · Use InMail: NO**\n> Thanks for connecting.\n>\n> Second paragraph about the req.\n\n"
           "### 2 · Jordan Rivera, Engineer · Profile: https://www.linkedin.com/in/jordanrivera\n\n"
           "**Connection note:**\n```\nHi Jordan, a fenced note.\n```\n\n**DM (after accept):**\n```\nHi Jordan,\n\nA fenced DM.\n\nSam\n```\n\n"
           "### 3 · Gone Person: Recruiter\n**Profile: https://www.linkedin.com/in/gone**\n\n"
           "**Connection note:**\n> Hi Gone, sent long ago.\n\n**Direct message · Use InMail: NO**\n> Hi Gone, also sent long ago.\n\n"
           "### 4 · First Degree: Manager (1st-degree)\n**Profile: https://www.linkedin.com/in/firstdeg**\n\n"
           "**Connection note:**\n> Hi First, not needed.\n\n**Direct message · Use InMail: YES** (decision node)\n> Hi First, a DM for you.\n")
    ledger = ledger_kinds("| date | recipient | company | channel | message-ref |\n|---|---|---|---|---|\n"
                          "| 2025-12-01 | Gone Person | Acme | connection note + DM | applications/acme-staff-engineer/referrals.md |\n")
    want("ledger: a note+DM row marks both kinds sent", ledger.get("acme-staff-engineer", {}).get("gone person") == {"note", "dm"})
    want("sent-kinds: 'connection note' alone is the note only", _sent_kinds_from_text("connection note (InMail NO)") == {"note"})
    people = parse_people(doc, "acme-staff-engineer", ledger)
    by = {p["name"]: p for p in people}
    want("a person whose NOTE left keeps only the DM, marked note_sent",
         "Pat Probe" in by and by["Pat Probe"]["note"] == "" and by["Pat Probe"]["dm"].startswith("Thanks")
         and by["Pat Probe"]["note_sent"])
    want("a fenced note + DM parse verbatim, paragraphs kept", "Jordan Rivera" in by and "\n\nA fenced DM." in by["Jordan Rivera"]["dm"])
    want("the profile URL is lifted off the heading when it lives there", by["Jordan Rivera"]["profile"].endswith("/jordanrivera"))
    want("a person the ledger shows fully sent is dropped", "Gone Person" not in by)
    want("a 1st-degree person gets the DM only, and InMail YES is carried",
         by["First Degree"]["note"] == "" and by["First Degree"]["connected"] and by["First Degree"]["inmail"] == "YES")
    comp = [dict(slug="acme-staff-engineer", title="Acme: Staff Engineer (req 4417) · referral pack", people=people)]
    md = render(comp, "2026-01-10")
    dms = render_dms(comp, "2026-01-10", "pipeline/outreach-bundle-2026-01-10.md")
    want("send file: notes only; a person whose note left is not in it", "Pat Probe" not in md and "Hi Jordan, a fenced note." in md)
    want("send file: no after-accept DM in it", "A fenced DM." not in md and "Thanks for connecting" not in md)
    want("send file: a 1st-degree person gets the DM as the one message", "Hi First, a DM for you." in md and "1st-degree" in md)
    want("DM file: sent-note person in Part 1, unsent one in Part 2",
         dms.index("Pat Probe") < dms.index("# Part 2") < dms.index("Jordan Rivera"))
    want("every message sits in its own fence", md.count("```") == 4 and dms.count("```") == 4)
    want("render: company header carries the role and the req", "# Acme: Staff Engineer" in md and "req 4417" in md)
    want("no em or en dash in either rendered file", not DASHES.search(md) and not DASHES.search(dms))
    global BIG
    saved, BIG = BIG, {"globex"}
    want("basket: a company in BIG_COMPANIES is big, anything else small",
         basket("Globex", "globex-analyst").startswith("big") and basket("Initech", "initech-x").startswith("small"))
    BIG = saved
    want("basket: with BIG_COMPANIES unset everything is small (the safe default)",
         not BIG or basket("Northwind", "northwind-x").startswith("small"))
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run(sys.argv[1:]))
