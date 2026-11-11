#!/usr/bin/env python3
"""slop_check.py: points at the sentence shapes that make application writing read as machine-made.

What this is and is not. It is a backstop for a few shapes a regular expression can see. It is not
the voice test: that is knowledge-base/17-writing.md (the words come from your real material, you
read them out loud, then a fresh reviewer reads them). A long banned list teaches a writer to write
around the list, so a finding is fixed by saying the real thing plainly or by cutting the sentence,
never by rephrasing the same idea past the pattern.

Two kinds of finding:
  TO FIX          Two narrow shapes: handing the employer's own posting back as your reason for
                  applying, and claiming their way of working is already yours. These set exit 1.
  SECOND LOOK     Everything else. A person can write any of these and mean it, so they are printed
                  for a re-read and never change the exit code. A plain sentence that happens to use
                  one of these words is fine and stays as it is.

A sentence you wrote, or one that is true and is how you would say it, stays. Keep it with one line
in application.md or cover-note.md (the reason is required):
    <!-- slop:allow <family> | <reason> -->
Set SLOP_CHECK_BLOCKS = False in scripts/config.py to make every finding a second look.

Optional reference letter: a letter you wrote or approved, pasted between the two marker lines in
knowledge-base/17-writing.md. While that slot is empty it does nothing. When it is filled, any family
your own letter trips is switched off for you, and a cover letter is told when it copies eight or
more words in a row from it.

Usage:
    python3 scripts/slop_check.py applications/<dossier> [more ...]   cover note + free-text answers
    python3 scripts/slop_check.py --text <file or "the message">       one drafted answer or message
    python3 scripts/slop_check.py --letter <file>                      one drafted cover letter
    python3 scripts/slop_check.py --batch applications/<a> <b> ...     also lists phrases shared by 3+ dossiers
    python3 scripts/slop_check.py --live <dir>                         answers read off live forms (form_answers.js output)
    python3 scripts/slop_check.py --selftest
Exit: 0 = nothing to fix (second looks may be printed), 1 = a TO FIX finding, 2 = usage or unreadable
file, 3 = nothing was checked (no text found, or the dossier is already submitted).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parent.parent
WRITING_KB = REPO / "knowledge-base" / "17-writing.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # every knob is optional; a missing config.py or a missing value falls back to the default
    import config as _config  # type: ignore
except ImportError:  # no config.py: every default applies
    _config = None
except Exception as _exc:  # pragma: no cover
    _config = None
    print(f"slop_check: scripts/config.py has a problem ({type(_exc).__name__}); using the defaults.", file=sys.stderr)

FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|I'll|me|my|mine|we|we're|we've|our|us)\b")

_POSTING = r"(?:posting|post|job post|job description|job ad|ad|JD|listing|careers page|site|website)"
_MOTIVE = (r"(?:made|makes|drew|draws|caught|catches|stood out|stands out|struck|strikes|sold|convinced|"
           r"spoke|speaks|resonated|resonates|pulled|pulls|hooked)")

# id -> (pattern or None for a sentence-level check, what it is, how to fix it)
FAMILIES = {
    "posting-motive": (
        re.compile(
            rf"\b(?:the|a|one|that) (?:line|part|bit|sentence|phrase|section|paragraph|mention) "
            rf"(?:in|of|from|on|about) (?:your|the) {_POSTING}\b[^.!?\n]{{0,120}}\b{_MOTIVE}\b"
            rf"|\byour {_POSTING}(?:'s)?\b[^.!?\n]{{0,100}}\b(?:caught my (?:eye|attention)|stood out to me|"
            rf"made me (?:want|apply)|drew me|sold me|convinced me|spoke to me|resonated)\b", re.I),
        "hands their own posting back as the reason you applied",
        "say your real reason from knowledge-base/18-in-your-own-words.md, or leave the reason out"),
    "match-claim": (
        re.compile(
            r"\b(?:is|that's|that is|it's|this is) (?:close to|basically|already|exactly) how I "
            r"(?:work|think|operate|run|approach|handle|teach|lead|do)\b", re.I),
        "claims their way of working is already yours",
        "say what you did, with a place and a time, and let the reader make the link"),
    "posting-echo": (
        re.compile(
            rf"\byour (?:posting|job post|listing|JD|job description|job ad|ad|careers page) (?:says|said|mentions|"
            rf"talks about|describes|asks for|calls for|puts it)\b"
            rf"|\bas (?:your|the) (?:posting|job post|listing|JD|job description|ad|site) (?:says|puts it)\b"
            rf"|\byour (?:home ?page|site|website|blog|landing page) (?:says|shows|mentions|talks about|is about|describes)\b"
            rf"|\bthe \w+ (?:card|section|banner|panel|screen|tab) on your (?:home ?page|site|website|app)\b", re.I),
        "recites their posting or their site back to them",
        "if the fact answers something, keep it; if it is there to show you read the page, cut it"),
    "self-portrait": (
        re.compile(
            r"\bI'?m an? [a-z -]{0,30}\bwho\b"
            r"|\b(?:that's|that is|it's|this is) (?:close to|exactly|already|basically) what I\b", re.I),
        "describes what kind of person you are",
        "say what you did, with a place and a time, and stop"),
    "curious-closer": (
        re.compile(
            r"\bI'?m (?:really )?curious (?:whether|how|if|about|what|to (?:hear|know|learn))\b|\bI'?d be curious\b"
            r"|\bI'?d (?:love|like) to (?:hear|know|learn) (?:how|whether|what|more about how)\b", re.I),
        "a question asked to fill space",
        "ask only what you actually need answered, or end without a question"),
    "melodrama": (
        re.compile(
            r"\bcan'?t stop thinking about\b|\bkeeps? me up at night\b|\bobsessed (?:with|over)\b|\bI live for\b"
            r"|\bno \w+(?: \w+)?, no \w+(?: \w+)?, no\b", re.I),
        "performed feeling, or a dramatic 'no this, no that' list",
        "say it plainly, with no drama"),
    "motive-cleft": (
        re.compile(
            r"\b(?:is|was|are|were) (?:what|why|the reason) (?:that )?(?:made|makes|drew|draws|got|gets|pulled|pulls|"
            r"brought|brings|convinced|sold|pushed|led) me\b"
            r"|\bwhat (?:drew|draws|pulled|pulls|got|gets|brought|attracted|attracts|excites|excited|interests|interested) "
            r"me (?:to|about|here|in|most)\b"
            r"|\bthe (?:thing|part|bit) (?:that )?(?:drew|draws|caught|catches|pulled|pulls|excites|excited|struck|"
            r"strikes)\b", re.I),
        "a moment of being drawn in, as a set phrase; often invented",
        "if it is true and in your own material, say it plainly; if it is not, leave it out"),
    "statement": (
        None,   # sentence-level, see statement_hits()
        "a general truth about people or work, with no 'I' in it",
        "cut it; say what you did, saw or want instead"),
    "trend": (
        re.compile(
            r"\bused to be\b.{0,80}\b(?:is|are) now\b|\bmore and more\b|\bincreasingly\b|\bthe future of\b"
            r"|\bin (?:a|an|this|today's) (?:world|age|era|moment) (?:where|of|when)\b"
            r"|\bas (?:AI|technology|automation|the industry) (?:gets|becomes|changes|evolves|grows)\b", re.I),
        "a pronouncement about where the world is going",
        "drop the trend; say the specific thing"),
    "not-x-but-y": (
        re.compile(
            r"\bnot (?:just|only|merely|simply)\b[^.!?\n]{1,80}\bbut\b"
            r"|\bisn't (?:just |only )?[^.,;\n]{1,60}, (?:it's|it is)\b"
            r"|\bless (?:like )?(?:a |an )?\w+,? (?:and )?more (?:like )?\b|\bno \w+, no \w+, just\b", re.I),
        "corrective framing: 'not X but Y', 'less X, more Y'",
        "say the one thing you mean"),
    "wh-triple": (
        None,   # sentence-level, see wh_triple()
        "three parallel what/how/why clauses in one sentence",
        "keep the one that is true for you"),
    "importance-puff": (
        re.compile(
            r"\bday[- ]to[- ]day lives\b|\beveryday li(?:fe|ves)\b|\bmake (?:a|an) (?:real |lasting |meaningful )?impact\b"
            r"|\bmeaningful (?:impact|change|difference)\b|\bat the intersection of\b", re.I),
        "a general claim that something matters",
        "name the real thing or leave it out"),
    "fit-closer": (
        re.compile(
            r"\bthe (?:kind|sort|type) of (?:work|problem|problems|thing|things|team|place|role|company|challenge)s? "
            r"(?:I|that I)\b"
            r"|\bthat's where I(?:'d| would)\b|\band that's (?:what|where|why)\b", re.I),
        "a tidy closer pointing back at the point",
        "end on something plain: the next step, thanks, or nothing"),
    "stock-motive": (
        re.compile(
            r"\b(?:I am|I'm) (?:so |very |really )?(?:excited|thrilled|eager|delighted) to (?:apply|join|be (?:a )?part)\b"
            r"|\bexcites me\b|\bresonates?(?: deeply)? with me\b|\baligns? (?:closely |perfectly |well )?with (?:my|what I)\b"
            r"|\bpassionate about\b|\bspeaks to me\b|\bI'?m drawn to\b|\bI am writing to express\b", re.I),
        "stock application phrasing",
        "say it the way you would to a friend, or cut it"),
    "ai-vocab": (
        # Phrases, not single words: a landscaper's landscape, foster care, a journey-level electrician,
        # seamless gutters and a nurse navigator are ordinary work words and must not show up here.
        re.compile(
            r"\bdelv(?:e|es|ing) into\b|\brich tapestry\b|\ba testament to\b|\bever[- ]evolving\b|\bin today's\b"
            r"|\bgame[- ]changer\b|\bcutting[- ]edge\b|\bfoster(?:s|ing)? (?:a culture|collaboration|an environment)\b"
            r"|\bleverag(?:e|ing) my\b|\bunlock(?:s|ing)? (?:new |the |your )?(?:potential|value|growth)\b"
            r"|\bmy (?:professional |career )?journey\b(?!-)|\bnavigat(?:e|ing) the complexit(?:y|ies)\b"
            r"|\bthe (?:\w+ )?landscape of\b|\bsynergy\b|\bholistic approach\b|\bmeticulous attention\b", re.I),
        "machine vocabulary",
        "use the plain word"),
    "ing-tail": (
        re.compile(
            r", (?:highlighting|reflecting|underscoring|showcasing|fostering|empowering)\b", re.I),
        "a trailing -ing clause explaining why it matters",
        "end the sentence where the fact ends"),
    "reference-copy": (
        None,   # letter-level, see letter_hits()
        "eight or more words in a row copied from your reference letter",
        "keep the voice, find new words"),
}

# The only families that set exit 1. Everything else is printed and never blocks.
TO_FIX = {"posting-motive", "match-claim"}

_MARKERS = re.compile(r"<!-- reference-letter:start -->(.*?)<!-- reference-letter:end -->", re.S)


def reference_letter(md: str | None = None) -> str:
    """The reference letter in the writing file, or "" while the slot is empty or still a [placeholder]."""
    if md is None:
        try:
            md = WRITING_KB.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    m = _MARKERS.search(md)
    if not m:
        return ""
    body = re.sub(r"^> ?", "", m.group(1).strip(), flags=re.M).strip()
    return "" if re.fullmatch(r"\[[^\]]*\]|", body) else body


def _grams(text: str, n: int) -> set:
    w = re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def letter_hits(text: str, ref: str) -> list:
    """A cover letter only: words lifted from the reference letter. Empty reference, no check."""
    if not ref or " ".join(text.split()) == " ".join(ref.split()):
        return []
    shared = _grams(text, 8) & _grams(ref, 8)
    return [("reference-copy", sorted(shared)[0])] if shared else []


GENERIC_SUBJECT = re.compile(
    r"^(?:an?|the|any|every|most|good|great|the best)?\s*"
    r"(?:apps?|products?|tools?|software|ai|systems?|services?|people|users?|teams?|compan(?:y|ies)|businesses|"
    r"organi[sz]ations?|hospitals?|schools?|patients?|customers?|clients?|students?|parents?|drivers?|crews?|nurses?|"
    r"teachers?|managers?|leaders?|employees?|workers?|someone|somebody|everyone|nobody|no one|whoever|anything|"
    r"everything|it|this|that|there)\b", re.I)
MODAL = re.compile(r"\b(?:has to|have to|has got to|needs to|need to|must|should|ought to|deserves?|only works if|"
                   r"only works when|is only as good as|matters?)\b", re.I)


def sentences(text: str) -> list:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'“])", text)
    return [p.strip() for p in parts if p.strip()]


def statement_hits(sent: str) -> bool:
    """A sentence stating a general rule about the world: generic subject, a must/should, no I or we."""
    s = re.sub(r"^(?:hi|hello|dear)\b[^,]*,\s*", "", sent, flags=re.I)
    if FIRST_PERSON.search(s) or re.search(r"\d", s):   # a number makes it a fact about something, not a maxim
        return False
    return bool(GENERIC_SUBJECT.match(s.strip("\"'“” ")) and MODAL.search(s))


def wh_triple(sent: str) -> bool:
    return len(re.findall(r"(?:^|[,;:]\s*|\band\s+|\bor\s+)(what|how|why|when|where|whether)\b", sent, re.I)) >= 3


def check_text(text: str) -> list:
    """-> [(family, fragment)] for one piece of text, ignoring HTML comments."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).replace("’", "'")
    out = []
    for fam, (pat, _, _) in FAMILIES.items():
        if pat is not None:
            out += [(fam, m.group(0)) for m in pat.finditer(text)]
    for s in sentences(text):
        if statement_hits(s):
            out.append(("statement", s[:90]))
        if wh_triple(s):
            out.append(("wh-triple", s[:90]))
    return out


def off_for_you(ref: str) -> set:
    """Your own approved letter outranks this script: any family it trips is off. Empty reference, nothing off."""
    return {fam for fam, _ in check_text(ref)} if ref else set()


# Reading a dossier
LINE = re.compile(r"^\s*-\s+(.+?):(?:\s+(.*))?$")
SKIP_LABEL = re.compile(r"\b(?:url|link|linkedin|portfolio|website|github|email|phone|address|name|resume|cv|cover letter "
                        r"file|salary|compensation|comp|visa|sponsor|authori[sz]|citizen|eeo|gender|race|veteran|disabilit|"
                        r"pronoun|location|city|state|country|start date|notice|referr|source|how did you hear|"
                        r"years|degree|school|gpa|ats|account needed|req(?:uisition)?(?:/job)? id|posted|apply url)\b", re.I)


def current_answers(md: str) -> dict:
    """label -> (label, answer) for every free-text answer of 80+ chars; the last value for a label wins."""
    out: dict = {}
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m:
            continue
        raw, value = m.group(1).strip(), (m.group(2) or "").strip()
        indent = len(line) - len(line.lstrip())
        cont = []
        for nxt in lines[i + 1:]:
            st = nxt.strip()
            if not st:
                continue
            if len(nxt) - len(nxt.lstrip()) <= indent or st.startswith("- ") or st.startswith("#"):
                break
            if not re.match(r"^(?:BEGIN|END)(?: ANSWER)?$", st):
                cont.append(st)
        if cont:
            value = (value + " " + " ".join(cont)).strip()
        value = re.sub(r"^\(\d+( chars?)?\)\s*", "", value)
        if len(value) < 80 or SKIP_LABEL.search(raw[:80]) or re.match(r"^(?:YOU\b|LEFT|blank|N/A|https?://|\[)", value, re.I):
            continue
        if re.search(r"as prepared|prepared above|same as above", value, re.I):
            continue
        key = re.sub(r"\s+", " ", raw.replace("**", "").strip('"“” ')).lower()[:120]
        out[key] = (raw, value)
    return out


def cover_body(path: Path) -> str:
    """The sendable note: the text between the first two '---' lines of cover-note.md."""
    parts = re.split(r"^---\s*$", path.read_text(encoding="utf-8", errors="replace"), flags=re.M)
    return parts[1].strip() if len(parts) >= 3 else ""


def allowed(md_text: str) -> set:
    """Families kept by <!-- slop:allow <family> | <reason> -->. No reason, no escape."""
    return {f for f, _ in re.findall(r"<!--\s*slop:allow\s+([\w-]+)\s*\|\s*(\S.+?)\s*-->", md_text)}


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def units(dossier: Path) -> list:
    """-> [(where, label, text)]: the cover note and every current free-text answer."""
    out = []
    cn = dossier / "cover-letter" / "cover-note.md"
    if cn.exists() and cover_body(cn):
        out.append((_rel(cn), "cover note", cover_body(cn)))
    app = dossier / "application.md"
    if app.exists():
        for raw, value in current_answers(app.read_text(encoding="utf-8", errors="replace")).values():
            out.append((_rel(app), raw, value))
    return out


def skip_reason(dossier: Path) -> str:
    """Why a dossier is not checked at all, or ""."""
    if not dossier.is_dir():
        return "no such folder"
    if dossier.name.startswith("TEMPLATE-"):
        return "template"
    app = dossier / "application.md"
    if app.exists() and re.search(r"^## SUBMITTED", app.read_text(encoding="utf-8", errors="replace"), re.M):
        return "already submitted"
    if not units(dossier):
        return "no cover note or free-text answer yet"
    return ""


def check_dossier(dossier: Path, ref: str) -> list:
    """-> [(where, label, hits)]. Applies the dossier's escapes and the families your own letter switches off."""
    if skip_reason(dossier):
        return []
    esc = off_for_you(ref)
    for f in (dossier / "application.md", dossier / "cover-letter" / "cover-note.md"):
        if f.exists():
            esc |= allowed(f.read_text(encoding="utf-8", errors="replace"))
    res = []
    for where, label, text in units(dossier):
        found = check_text(text) + (letter_hits(text, ref) if label == "cover note" else [])
        hits = [(fam, frag) for fam, frag in found if fam not in esc]
        if hits:
            res.append((where, label, hits))
    return res


SHARED_N = 6
_BORING = re.compile(r"^(?:i |thanks|hi |the |a |and )")


def shared_phrases(dossiers: list, min_dossiers: int = 3) -> dict:
    """Six-word phrases in the cover notes and answers of 3+ dossiers: one template, many letters."""
    seen = defaultdict(set)
    for d in dossiers:
        if skip_reason(d):
            continue
        grams = set()
        for _, _, text in units(d):
            grams |= _grams(text, SHARED_N)
        for g in grams:
            seen[g].add(d.name)
    return {g: s for g, s in seen.items() if len(s) >= min_dossiers and not _BORING.match(g)}


def has_to_fix(found: list) -> bool:
    return any(fam in TO_FIX for _, _, hits in found for fam, _ in hits)


def report(found: list) -> None:
    for where, label, hits in found:
        fams = defaultdict(list)
        for fam, frag in hits:
            fams[fam].append(frag)
        print(f"  {where} [{label[:50]}]")
        for fam, frags in fams.items():
            kind = "TO FIX" if fam in TO_FIX else "second look"
            print(f"      {kind}: {fam}: {FAMILIES[fam][1]}: \"{frags[0][:80]}\"  -> {FAMILIES[fam][2]}")


def finish(found: list, blocks: bool) -> int:
    """Print the summary line and return the exit code for a set of checked texts."""
    report(found)
    n = sum(1 for _, _, hits in found for fam, _ in hits if fam in TO_FIX)
    looks = sum(len(hits) for _, _, hits in found) - n
    if not found:
        print("slop_check: CLEAN of the shapes it knows. This says nothing about the voice; read it out loud.")
        return 0
    print(f"slop_check: {n} to fix, {looks} second look(s). Second looks never block; a plain, true sentence stays as it is.")
    if n:
        print("  If a TO FIX sentence is true and is how you would say it, keep it: "
              "<!-- slop:allow <family> | <reason> --> in application.md or cover-note.md.")
    return 1 if (n and blocks) else 0


def run_paths(paths: list, batch: bool, ref: str, blocks: bool) -> int:
    dossiers = []
    for a in paths:
        p = Path(a)
        dossiers.append(p if p.is_absolute() else REPO / p)
    checked, found = [], []
    for d in dossiers:
        why = skip_reason(d)
        if why:
            print(f"  not checked: {_rel(d)} ({why})")
            continue
        checked.append(d)
        found += check_dossier(d, ref)
    if not checked:
        print("slop_check: NOT CHECKED, no dossier here had text to read.")
        return 3
    rc = finish(found, blocks)
    if batch:
        sh = shared_phrases(checked)
        for g, s in sorted(sh.items(), key=lambda x: -len(x[1]))[:40]:
            print(f"  second look: shared by {len(s)} dossiers: \"{g}\"  ({', '.join(sorted(s)[:4])})")
    return rc


def run_text(path: str, letter: bool, ref: str, blocks: bool) -> int:
    """`path` is a file, or the message itself (anything with a space that is not a file)."""
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        if not re.search(r"\s", path.strip()):
            print(f"slop_check: cannot read {path}: {e}", file=sys.stderr)
            return 2
        txt, path = path, "message"
    if not txt.strip():
        print(f"slop_check: NOT CHECKED, {path} is empty.")
        return 3
    esc = off_for_you(ref) | allowed(txt)
    hits = [(f, x) for f, x in check_text(txt) + (letter_hits(txt, ref) if letter else []) if f not in esc]
    return finish([(path, "text", hits)] if hits else [], blocks)


def run_live(dirpath: str, ref: str, blocks: bool) -> int:
    files = sorted(Path(dirpath).glob("*.json"), key=lambda x: int(re.sub(r"\D", "", x.stem) or 0))
    esc = off_for_you(ref)
    found, read, unreadable = [], 0, []
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"```json\s*(.*?)```", txt, re.S)
        try:
            d = json.loads(m.group(1) if m else txt[txt.index("{"):])
            fields = d["fields"]
        except (ValueError, KeyError, TypeError):
            unreadable.append(f.name)
            continue
        read += 1
        if d.get("submitted"):
            continue
        for fl in fields:
            v = str(fl.get("value", "")).strip()
            if len(v) < 80 or re.match(r"^https?://\S+$", v):
                continue
            hits = [(a, b) for a, b in check_text(v) if a not in esc]
            if hits:
                found.append((f"tab {f.stem} {str(d.get('url', ''))[:60]}", str(fl.get("label", "")), hits))
    for name in unreadable:
        print(f"  not checked: {name} (not form_answers.js output)")
    if not read:
        print(f"slop_check --live: NOT CHECKED, no readable form output in {dirpath}.")
        return 3
    return finish(found, blocks)


def selftest() -> int:
    """Synthetic only. Every reference letter and dossier here is made up, so filling in your own files changes nothing."""
    results = []

    def want(label, cond):
        results.append((label, bool(cond)))

    def fams(t):
        return {f for f, _ in check_text(t)}

    for t in ["The part of your job description on charting support is what made me want to apply.",
              "Your ad's mention of a mentoring program for new hires caught my eye right away.",
              "The section of your listing on apprenticeship pay sold me on this opening."]:
        want(f"posting-motive to fix: {t[:50]}", "posting-motive" in fams(t))
    for t in ["Your rotating charge schedule is close to how I work.",
              "That's basically how I run a warehouse shift.",
              "This is already how I teach long division."]:
        want(f"match-claim to fix: {t[:50]}", "match-claim" in fams(t))

    for fam, t in [("posting-echo", "Your job description says the clinic is growing."),
                   ("self-portrait", "I'm a shift supervisor who keeps every dock moving."),
                   ("curious-closer", "I'd love to hear how your audit team splits the close."),
                   ("melodrama", "I can't stop thinking about your classroom model."),
                   ("motive-cleft", "What drew me to Northwind is its delivery network."),
                   ("statement", "Every patient deserves a nurse with time to listen."),
                   ("trend", "More and more retailers run stores with two people."),
                   ("not-x-but-y", "Bookkeeping is not just data entry but judgment."),
                   ("wh-triple", "What crews need, how they plan, and why jobs slip all interest me."),
                   ("importance-puff", "I want to make a real impact at the intersection of sales and service."),
                   ("fit-closer", "That's the kind of team I want to join."),
                   ("stock-motive", "I am so excited to apply and passionate about logistics."),
                   ("ai-vocab", "I would delve into the ever-evolving world of tax."),
                   ("ing-tail", "I closed the books a week early, showcasing my discipline.")]:
        want(f"{fam} second look", fam in fams(t) and fam not in TO_FIX)

    fine = [
        "I worked nights on a cardiac step-down unit at Globex for six years, and I want to stay on nights because my kids are in school during the day.",
        "Your posting says a Class A license is required. I've held mine since 2018 and my record is clean.",
        "I do foster care placements on the side, and I've kept my journey-level electrician card current in two states.",
        "Our landscape crew installed seamless gutters on forty homes last spring, and I ran the schedule.",
        "As a nurse navigator I helped patients leverage their benefits, and I can unlock the med room on my badge.",
        "I teach seventh grade math at Initech Academy. A parent told me her son finally asked for homework, so I kept doing the Friday problem sets.",
        "I reconciled the Umbrella accounts each month, and when the bank feed broke I rebuilt the sheet by hand so the close stayed on time.",
        "I've sold copiers for five years at Hooli. My best quarter came after I stopped cold calling and started asking existing customers who else they knew.",
        "I'd rather work the early shift than the late one, if you have both open.",
        "Thanks for the call today. Tuesday at 2 works for me, and I'll bring my certifications.",
        "I fixed the checkout bug at Acme by reading the logs with the store manager on the phone.",
    ]
    for t in fine:
        want(f"fine answer has nothing to fix: {t[:50]}", not (fams(t) & TO_FIX))
    for t in fine[2:5]:
        want(f"ordinary work words are not machine vocabulary: {t[:40]}", "ai-vocab" not in fams(t))

    want("no sentence-length check exists", "choppy" not in FAMILIES)
    want("short sentences raise nothing", not check_text("I'm applying for the dispatcher job. I ran dispatch at Northwind. I know the routes. Thanks."))
    want("only two families can block", TO_FIX == {"posting-motive", "match-claim"})

    # The reference-letter slot: inert while empty, in every shape an unfilled file can take.
    empty = "x\n<!-- reference-letter:start -->\n\n<!-- reference-letter:end -->\n"
    want("reference: empty slot reads as nothing", reference_letter(empty) == "")
    want("reference: placeholder reads as nothing", reference_letter(empty.replace("\n\n<", "\n[Paste it here.]\n<")) == "")
    want("reference: no markers reads as nothing", reference_letter("# no slot") == "")
    want("reference: empty slot checks nothing", letter_hits("any letter text at all goes here today and more words", "") == [])
    want("reference: empty slot switches nothing off", off_for_you("") == set())
    letter = ("Hi Sam,\n\nWhat drew me to nursing was my aunt, who ran a rural clinic out of her garage for eleven winters. "
              "I'd like to do that work with your team in the valley.\n\nThanks,\nJordan")
    filled = empty.replace("\n\n<", "\n> " + letter.replace("\n", "\n> ") + "\n<", 1)
    want("reference: a filled slot is read back without quote marks", reference_letter(filled).startswith("Hi Sam,") and "> " not in reference_letter(filled))
    want("reference: a family the letter trips is off", "motive-cleft" in off_for_you(letter))
    want("reference: the letter itself is not a copy", letter_hits(letter, letter) == [])
    copied = "Hi Lee, my aunt, who ran a rural clinic out of her garage for eleven winters, taught me."
    want("reference: eight words in a row are noticed", [f for f, _ in letter_hits(copied, letter)] == ["reference-copy"])
    want("reference: reference-copy never blocks", "reference-copy" not in TO_FIX)

    # Dossiers, in a temp folder outside the repo.
    tmp = Path(tempfile.mkdtemp())
    try:
        def make(name, cover=None, app=None):
            d = tmp / name
            (d / "cover-letter").mkdir(parents=True)
            if cover is not None:
                (d / "cover-letter" / "cover-note.md").write_text(f"# Note\n\n---\n{cover}\n---\n\n## Notes\n", encoding="utf-8")
            if app is not None:
                (d / "application.md").write_text(app, encoding="utf-8")
            return str(d)

        def quiet(fn, *a):
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return fn(*a)

        bad = "Hi,\n\nThe part of your posting on weekend coverage is what made me want to apply. I've covered weekends at Acme.\n\nThanks"
        ok_note = "Hi,\n\nI've covered weekends at the Acme pharmacy for three years and I'd like to keep doing that closer to home.\n\nThanks"
        soft = "Hi,\n\nI am so excited to apply. I've covered weekends at the Acme pharmacy for three years.\n\nThanks"
        want("dossier: a to-fix shape exits 1", quiet(run_paths, [make("a", bad)], False, "", True) == 1)
        want("dossier: a plain note exits 0", quiet(run_paths, [make("b", ok_note)], False, "", True) == 0)
        want("dossier: a second look alone exits 0", quiet(run_paths, [make("c", soft)], False, "", True) == 0)
        want("dossier: the knob off exits 0", quiet(run_paths, [make("d", bad)], False, "", False) == 0)
        want("dossier: slop:allow with a reason releases it",
             quiet(run_paths, [make("e", bad + "\n<!-- slop:allow posting-motive | I said this and mean it -->")], False, "", True) == 0)
        want("dossier: slop:allow with no reason does not",
             quiet(run_paths, [make("f", bad + "\n<!-- slop:allow posting-motive -->")], False, "", True) == 1)
        want("dossier: nothing to read exits 3", quiet(run_paths, [make("g")], False, "", True) == 3)
        want("dossier: a missing folder exits 3", quiet(run_paths, [str(tmp / "nope")], False, "", True) == 3)
        want("dossier: a submitted one exits 3",
             quiet(run_paths, [make("h", bad, "# App\n\n## SUBMITTED 2026-01-05\n")], False, "", True) == 3)
        want("dossier: a template is skipped", quiet(run_paths, [make("TEMPLATE-x", bad)], False, "", True) == 3)
        answer = ("- Why do you want this job: The sentence in your listing about night differentials is what made me "
                  "want to apply, and I have worked nights for a long time now.\n- Apply URL: https://example.com/job\n")
        want("dossier: a free-text answer is read", quiet(run_paths, [make("i", None, answer)], False, "", True) == 1)
        sh = [make(f"s{i}", "Hi,\n\nMy forklift ticket renews every spring in Dayton and I have driven nights.\n\nThanks") for i in "123"]
        want("batch: a shared phrase is listed and never blocks", quiet(run_paths, sh, True, "", True) == 0
             and shared_phrases([Path(p) for p in sh]))

        note = tmp / "m.txt"
        note.write_text("That's basically how I run a warehouse shift.", encoding="utf-8")
        want("text: a to-fix shape exits 1", quiet(run_text, str(note), False, "", True) == 1)
        want("text: the message itself can be passed",
             quiet(run_text, "That's basically how I run a warehouse shift.", False, "", True) == 1)
        want("text: a missing file exits 2", quiet(run_text, str(tmp / "no.txt"), False, "", True) == 2)
        empty_file = tmp / "e.txt"
        empty_file.write_text("  \n", encoding="utf-8")
        want("text: an empty file exits 3", quiet(run_text, str(empty_file), False, "", True) == 3)

        live = tmp / "live"
        live.mkdir()
        long_bad = "The part of your job description on charting support is what made me want to apply to this hospital."
        (live / "1.json").write_text(json.dumps({"url": "https://example.com", "submitted": False,
                                                 "fields": [{"label": "Why us", "help": "", "value": long_bad}]}), encoding="utf-8")
        want("live: a to-fix answer exits 1", quiet(run_live, str(live), "", True) == 1)
        (live / "1.json").write_text(json.dumps({"url": "https://example.com", "submitted": True,
                                                 "fields": [{"label": "Why us", "help": "", "value": long_bad}]}), encoding="utf-8")
        want("live: a submitted form is skipped", quiet(run_live, str(live), "", True) == 0)
        (live / "2.json").write_text("not json at all", encoding="utf-8")
        want("live: a broken file does not crash", quiet(run_live, str(live), "", True) == 0)
        (live / "1.json").unlink()
        want("live: nothing readable exits 3", quiet(run_live, str(live), "", True) == 3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad_results = [lbl for lbl, ok in results if not ok]
    for lbl in bad_results:
        print(f"  FAIL {lbl}")
    print(f"SELFTEST {'FAILED' if bad_results else 'OK'}: {len(results) - len(bad_results)}/{len(results)}")
    return 1 if bad_results else 0


def main(argv: list) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    ref = reference_letter()
    blocks = bool(getattr(_config, "SLOP_CHECK_BLOCKS", True)) if _config else True
    if len(argv) == 3 and argv[1] == "--live":
        return run_live(argv[2], ref, blocks)
    if len(argv) == 3 and argv[1] in ("--text", "--letter"):
        return run_text(argv[2], argv[1] == "--letter", ref, blocks)
    batch = len(argv) > 1 and argv[1] == "--batch"
    paths = argv[2:] if batch else argv[1:]
    if not paths or any(p.startswith("--") for p in paths):
        print(__doc__)
        return 2
    return run_paths(paths, batch, ref, blocks)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
