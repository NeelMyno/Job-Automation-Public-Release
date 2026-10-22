#!/usr/bin/env python3
"""batch_voice_check.py: RETIRED as a gate; kept as the referrals.md message library.

This file used to hold the cross-file SAMENESS detectors (a shared opening skeleton, a verbatim
sentence reused across dossiers). They were removed along with every other writing-style check:
style detectors taught writers to write to the checker. How writing sounds is owned by
knowledge-base/17-writing.md, and its gate is a read-aloud plus a fresh-reviewer pass, not a script.

What stays, because other scripts use it and none of it is style:
  - referral_messages(text, dossier): every drafted note and DM in a referrals.md, with its sent state.
  - sent_kinds(block, person, dossier): which of a person's messages already LEFT (a dated in-block
    SENT marker, or a row in pipeline/sent-ledger.md).
  - changed_messages(path): the unsent messages this working tree wrote. scripts/hooks.py runs
    voice_check on these at PostToolUse and at Stop.
  - check(files): kept as a name for importers; it returns no findings.

Usage:
  python3 scripts/batch_voice_check.py [files...]   # prints "retired", exit 0
  python3 scripts/batch_voice_check.py --selftest
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# referrals.md message extraction: outreach_format's person grammar plus the body formats
# (inline after the label, a `>` blockquote, a fenced block, or a plain paragraph).
NOTE_MARK = re.compile(r"^\s*[-*>]?\s*\*{0,2}(?:#?\d+\s*[.):·-]?\s*)?(?:connection[ -]note|note)\b.*$", re.I | re.M)
DM_MARK = re.compile(r"^\s*[-*>]?\s*\*{0,2}(?:#?\d+\s*[.):·-]?\s*)?(?:direct[ -]message|DM|message)\b.*$", re.I | re.M)
# The SENT-marker grammar has ONE owner, outreach_format.py (§8: a rule lives in one file). It is
# imported here; the local copy exists only so this module still loads if the owner cannot be read.
try:
    from outreach_format import ALREADY_SENT, UNSENT_TAIL
except Exception:  # pragma: no cover
    UNSENT_TAIL = re.compile(r"SEND THIS NOW|not yet sent|unsent|still to send|hold expired|send now", re.I)
    ALREADY_SENT = re.compile(
        r"(?:(?<!not )(?<!never )\bSENT\b|\bsent by (?:me|you)\b|✅\s*SENT)[^\n]{0,60}?"
        r"(?:20\d\d-\d\d-\d\d|\b\d{1,2}/\d{1,2}/20\d\d\b)"
        r"|(?:20\d\d-\d\d-\d\d)[^\n]{0,40}?(?<!not )(?<!never )\bSENT\b", re.I)


def _extract_body(block: str, start_mark: re.Pattern, end_mark: re.Pattern | None) -> str | None:
    """Text of the message after start_mark: inline (after the colon), blockquote, fenced, or plain."""
    ms = start_mark.search(block)
    if not ms:
        return None
    mline = ms.group(0).lstrip("\n")
    body = re.sub(r"^.*?(?:connection[ -]note|direct[ -]message|\bDM\b|\bmessage\b)", "", mline, count=1, flags=re.I)
    body = re.sub(r"^\s*\*{0,2}\s*\([^)]*\)\s*", "", body)
    body = re.sub(r"^\s*·?\s*use\s+inmail\s*:?\s*(?:yes|no)\s*\*{0,2}", "", body, flags=re.I)
    body = re.sub(r"^\s*\([^)]*\)\s*", "", body)
    body = re.sub(r"^\s*[\*·:]+\s*", "", body).strip()
    inline = body if len(body) >= 15 else ""
    region = block[ms.end():]
    if end_mark:
        me = end_mark.search(region)
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
        elif started and ln.strip() == "":
            lines.append("")
        elif started:
            break
    while lines and lines[-1].strip() == "":
        lines.pop()
    bq = "\n".join(lines).strip("\n")
    if bq.strip():
        return bq
    if inline:
        return inline
    plain = re.sub(r"^[)\s:*]+", "", region).strip()
    plain = re.sub(r"^\([^)]*\)\s*:?\s*", "", plain).strip()
    if len(plain) >= 20 and re.match(r"(?i)^(hi|hey|hello|dear|thanks)\b", plain):
        return plain
    return None


# What actually LEFT, per message kind. Sent-ness is per KIND: a sent connection note does not make
# the pending DM history (the DM goes out after they accept, and it is the copy the gates exist for).
# Two sources, either one counts:
#   1. a dated SENT line inside the person's block (outreach_format's ALREADY_SENT grammar). The
#      line's own words say which kind: "connection note" means the note only; "DM", "direct
#      message", email or InMail means the DM only; neither named means both.
#   2. pipeline/sent-ledger.md, the append-only record of what left: a row whose message-ref names
#      this dossier (or whose company matches the dossier's slug) and whose recipient is this person.
LEDGER = REPO / "pipeline" / "sent-ledger.md"
_LEDGER_CACHE: dict[str, dict[str, set[str]]] | None = None
_DM_WORDS = re.compile(r"\bdm\b|direct message|\binmail\b|\bemail\b", re.I)
_INMAIL_NEGATED = re.compile(r"inmail\s*:?\s*no\b[^;,)]*|\bno inmail\b[^;,)]*|inmail\s+not\b[^;,)]*", re.I)


def _sent_kinds_from_text(s: str) -> set[str]:
    s = _INMAIL_NEGATED.sub(" ", s)          # "(free; InMail NO per pack)" names the channel NOT used
    has_note = "connection note" in s.lower() or re.search(r"\bnote\b", s, re.I) is not None
    has_dm = _DM_WORDS.search(s) is not None
    if has_note and not has_dm:
        return {"note"}
    if has_dm and not has_note:
        return {"dm"}
    return {"note", "dm"}


def person_name(heading: str) -> str:
    """'1 · Sam Lee, Charge Nurse · https://example.com' -> 'sam lee'."""
    h = re.sub(r"^\d+\s*[·.)\-]\s*", "", heading).strip("*_` ")
    h = re.split(r"\s+[\u2014\u2013·,]\s+|\s+-\s+|\s*\(|\s*[\u2014\u2013]", h, maxsplit=1)[0]
    return re.sub(r"\s+", " ", h).strip().lower()


def ledger_sent_kinds_map() -> dict[str, dict[str, set[str]]]:
    """{dossier-slug: {recipient (lowercased): {'note','dm'}}} from the sent-ledger. Cached per process."""
    global _LEDGER_CACHE
    if _LEDGER_CACHE is not None:
        return _LEDGER_CACHE
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    try:
        for ln in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.startswith("|") or ln.startswith("| date") or ln.startswith("|---"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue
            recipient = re.sub(r"\s*\(.*?\)\s*", " ", cells[1])
            recipient = re.sub(r"\s+", " ", recipient).strip().lower()
            kinds = _sent_kinds_from_text(cells[3])
            slugs = re.findall(r"applications/([^/`\s]+)/", cells[4])
            for slug in slugs:
                out[slug][recipient] |= kinds
            # A row whose message-ref names no dossier path is keyed by COMPANY too, so a dossier can
            # still find it by its slug prefix.
            ck = _company_key(cells[2])
            if ck:
                out["company:" + ck][recipient] |= kinds
    except OSError:
        pass
    _LEDGER_CACHE = {k: dict(v) for k, v in out.items()}
    return _LEDGER_CACHE


def _company_key(s: str) -> str:
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def ledger_sent_kinds(dossier: str, heading: str) -> set[str]:
    n = person_name(heading)
    if len(n) < 5:
        return set()
    m = ledger_sent_kinds_map()
    rows: dict[str, set[str]] = dict(m.get(dossier, {}))
    # Company fallback: the slug's leading tokens, longest first ("acme-staff-accountant" gives
    # "acmestaffaccountant", "acmestaff", "acme"); a ledger company key equal to one of them belongs here.
    toks = dossier.split("-")
    for i in range(len(toks), 0, -1):
        key = "company:" + "".join(toks[:i])
        if key in m:
            for r, ks in m[key].items():
                rows[r] = rows.get(r, set()) | ks
            break
    kinds: set[str] = set()
    for r, ks in rows.items():
        if n == r or n.startswith(r + " ") or r.startswith(n + " ") or (len(r) >= 5 and (n.startswith(r) or r.startswith(n))):
            kinds |= ks
    return kinds


def sent_kinds(block: str, person: str, dossier: str | None) -> set[str]:
    """Which of this person's messages already left: the in-block dated marker (per its wording) and/or
    the ledger. An explicit not-yet-sent declaration in the block outranks the in-block marker."""
    kinds: set[str] = set()
    m = ALREADY_SENT.search(block)
    if m and not UNSENT_TAIL.search(block):
        ls = block.rfind("\n", 0, m.start()) + 1
        le = block.find("\n", m.end())
        line = block[ls:(le if le != -1 else len(block))]
        # Only the SENTENCE that carries the marker says what left. "SENT 2026-01-05 (connection
        # note). DM: send after accept." names the DM in a different sentence, as still to go.
        at = m.start() - ls
        stop_ = re.search(r"[.!?](?:\s|$)", line[m.end() - ls:])
        clause = line[: (m.end() - ls) + stop_.start()] if stop_ else line
        kinds |= _sent_kinds_from_text(clause)
    if dossier:
        kinds |= ledger_sent_kinds(dossier, person)
    return kinds


def referral_messages(text: str, dossier: str | None = None) -> list[dict]:
    """Every drafted message in a referrals.md: [{person, kind: 'note'|'dm', body, sent: bool}].
    Uses outreach_format's person grammar (the owner). `sent` is per message KIND (see sent_kinds);
    pass `dossier` (the folder slug) so the sent-ledger counts too. Sent messages are still returned,
    so a caller can decide."""
    try:
        from outreach_format import person_blocks
    except Exception:
        return []
    out = []
    for person, block in person_blocks(text):
        kinds = sent_kinds(block, person, dossier)
        note = _extract_body(block, NOTE_MARK, DM_MARK)
        dm = _extract_body(block, DM_MARK, None)
        if note:
            out.append({"person": person, "kind": "note", "body": note, "sent": "note" in kinds})
        if dm:
            out.append({"person": person, "kind": "dm", "body": dm, "sent": "dm" in kinds})
    return out


def check(files: list[Path]) -> list[str]:
    """Retired: always returns no findings (see the module docstring)."""
    return []


def _base_text(path: Path) -> str | None:
    """The file as committed (HEAD), or None for a file git does not have yet (a brand-new dossier:
    every message is new)."""
    import subprocess
    try:
        rel = str(path.resolve().relative_to(REPO))
    except ValueError:
        return None
    for ref in ("HEAD",):
        try:
            r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO, capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        if r.returncode == 0:
            return r.stdout
    return None


def _norm_body(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def changed_messages(path: Path) -> list[dict]:
    """The UNSENT messages in this referrals.md whose text differs from the committed version: the copy
    this working tree WROTE. hooks.py blocks only on defects this session introduced, so an old pending
    DM in a file someone merely logged a reply into is not that session's defect, while every message
    a writer drafts or rewrites is checked. A new file: every unsent message."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    dossier = path.parent.name
    base = _base_text(path)
    old = set()
    if base is not None:
        old = {(person_name(m["person"]), m["kind"], _norm_body(m["body"])) for m in referral_messages(base, dossier)}
    return [m for m in referral_messages(text, dossier)
            if not m["sent"] and (person_name(m["person"]), m["kind"], _norm_body(m["body"])) not in old]


def _person(n: int, person: str, note: str, dm: str, sent_line: str = "", fmt: str = "bq") -> str:
    head = f"### {n} · {person} · Shift Lead\n{sent_line}**Profile:** https://example.com/{n}\n\n"
    if fmt == "bq":
        nn = "\n".join("> " + l for l in note.splitlines())
        dd = "\n".join("> " + l for l in dm.splitlines())
        return head + f"**Connection note:**\n{nn}\n\n**Direct message:**\n{dd}\n\n"
    if fmt == "fence":
        return head + f"**Connection note:**\n```\n{note}\n```\n\n**DM (after accept):**\n```\n{dm}\n```\n\n"
    return head + f"**Connection note:** {note}\n\n**Direct message:** {dm}\n\n"


def _referrals(*people: str) -> str:
    return "# Northwind\n\n## The messages\n\n" + "".join(people)


def selftest() -> int:
    global _LEDGER_CACHE, _base_text
    passed = failed = 0

    def want(label, cond):
        nonlocal passed, failed
        passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
        print(f"  {'PASS' if cond else 'FAIL'} {label}")

    print("batch_voice_check.py selftest (message library; the sameness checks are retired)\n")
    for fmt in ("bq", "fence", "inline"):
        dm = "Hi Sam, a DM in one line." if fmt == "inline" else "Hi Sam,\n\nA DM in two paragraphs.\n\nAlex"
        ms = referral_messages(_referrals(_person(1, "Sam Lee", "Hi Sam, a short note.", dm, fmt=fmt)))
        want(f"referral_messages reads the {fmt} format (note + dm)",
             {m["kind"] for m in ms} == {"note", "dm"} and all(m["body"].startswith("Hi Sam") for m in ms))
    note_only = _referrals(_person(1, "Sam Lee", "Hi Sam, a short note.", "Hi Sam, a DM.",
                                   "SENT 2026-01-05 (connection note). DM: send after accept.\n"))
    want("a dated SENT line naming the connection note leaves the DM live",
         {m["kind"]: m["sent"] for m in referral_messages(note_only)} == {"note": True, "dm": False})
    both = _referrals(_person(1, "Sam Lee", "Hi Sam, a short note.", "Hi Sam, a DM.", "SENT 2026-01-05.\n"))
    want("a dated SENT line naming no kind marks both sent", all(m["sent"] for m in referral_messages(both)))
    saved = _LEDGER_CACHE
    _LEDGER_CACHE = {"umbrella-staff-accountant": {"sam lee": {"dm"}}, "company:hooli": {"sam lee": {"note"}}}
    try:
        plain = _referrals(_person(1, "Sam Lee", "Hi Sam, a short note.", "Hi Sam, a DM."))
        want("ledger: a direct-message row for this dossier marks the DM sent",
             {m["kind"]: m["sent"] for m in referral_messages(plain, "umbrella-staff-accountant")}
             == {"note": False, "dm": True})
        want("ledger: a row keyed by company is found by the dossier slug prefix",
             {m["kind"]: m["sent"] for m in referral_messages(plain, "hooli-store-manager")}
             == {"note": True, "dm": False})
        want("ledger: another dossier's rows do not apply",
             not any(m["sent"] for m in referral_messages(plain, "initech-teacher")))
    finally:
        _LEDGER_CACHE = saved
    want("person_name strips the number, the title and the URL",
         person_name("1 · Sam Lee · Charge Nurse · https://example.com") == "sam lee")

    import tempfile
    import shutil
    old = _referrals(_person(1, "Sam Lee", "Hi Sam, an old note.", "Hi Sam, an old pending DM."),
                     _person(2, "Alex Kim", "Hi Alex, an old note.", "Hi Alex, another old pending DM."))
    saved_base = _base_text
    td = Path(tempfile.mkdtemp())
    (td / "globex-dispatcher").mkdir()
    f = td / "globex-dispatcher" / "referrals.md"
    try:
        _base_text = lambda path: old
        f.write_text(old + "\nLogged a reply from Sam on 2026-01-06.\n", encoding="utf-8")
        want("changed_messages: a file with only a log line added has no changed message", changed_messages(f) == [])
        f.write_text(old.replace("an old pending DM", "a rewritten DM"), encoding="utf-8")
        want("changed_messages: the one rewritten DM is the only changed message",
             [(person_name(m["person"]), m["kind"]) for m in changed_messages(f)] == [("sam lee", "dm")])
        _base_text = lambda path: None
        want("changed_messages: a brand-new file returns every unsent message", len(changed_messages(f)) == 4)
    finally:
        _base_text = saved_base
        shutil.rmtree(td)
    want("check() is retired and returns no findings", check([Path("does-not-exist.md")]) == [])
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    print("batch_voice_check: retired as a gate; nothing checked. Voice is judged by a read-aloud and a "
          "fresh reviewer against knowledge-base/17-writing.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
