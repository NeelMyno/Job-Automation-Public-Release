#!/usr/bin/env python3
"""batch_voice_check.py: the CROSS-FILE voice linter (the rinse-and-repeat gate).

`voice_check.py` reads ONE text at a time, so the loudest tell it can never see by construction is
the SAME opener showing up in note after note. This reads a BATCH of sendable copy at once and
flags two forms of sameness:
  1. an OPENING SKELETON shared across >=2 notes (role/company/quote/number masked, so only the
     template structure remains);
  2. a full sendable SENTENCE (>=10 words) repeated VERBATIM across >=2 different dossiers.

Usage:
  python3 scripts/batch_voice_check.py                    # every applications/*/cover-letter/cover-note.md
  python3 scripts/batch_voice_check.py <file> <file> ...  # explicit files
  python3 scripts/batch_voice_check.py --selftest
Exit 0 = no cross-file sameness. 1 = sameness found. 2 = usage error.

Complement, not replacement: voice_check.py still gates each note's own register; this gates
the batch. Neither is sufficient alone.
"""
from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OPENER_WORDS = 8      # how many masked opening words define the "template"
MIN_SENTENCE_WORDS = 10   # a shared sentence this long is a real duplicate, not a stock phrase
GREETING = re.compile(r"^\s*(hi|hey|hello|dear)\b[^,\n]{0,40},?\s*", re.I)


def _body(text: str) -> str:
    """The SENDABLE letter only. cover-note.md wraps the letter between the first `---` and the
    next `---`; a metadata heading, a draft-status process note, or a "why these specifics" mapping
    table lives OUTSIDE that fence and must NOT count toward sameness (that scaffolding is
    identical boilerplate by design). Falls back to the whole text when there is no fence."""
    parts = re.split(r"^\s*---\s*$", text, flags=re.M)
    letter = parts[1] if len(parts) >= 3 else text
    out = []
    for ln in letter.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|"):
            continue
        if s.startswith("**") and s.endswith("**"):   # a bold label line, not prose
            continue
        out.append(s)
    return " ".join(out).strip()


def skeleton(text: str) -> str:
    """The opening template: first OPENER_WORDS words with names/quotes/numbers masked."""
    body = GREETING.sub("", text.strip())
    first = re.split(r"(?<=[.?!])\s+", body, 1)[0] if body else ""
    s = re.sub(r"[\"“”'’][^\"“”'’]{2,}[\"“”'’]", " Q ", first)      # quoted phrases vary
    s = re.sub(r"\b[A-Z][a-zA-Z0-9.]+(?:\s+[A-Z][a-zA-Z0-9.]+)*\b", " N ", s)  # Title-Case runs
    s = re.sub(r"\d[\d,.]*", " D ", s)
    s = re.sub(r"[^a-zA-Z ]", " ", s.lower())
    words = [w for w in s.split() if w]
    return " ".join(words[:OPENER_WORDS])


def sentences(text: str) -> list[str]:
    body = _body(text)
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", body) if len(s.split()) >= MIN_SENTENCE_WORDS]


def check(files: list[Path]) -> list[str]:
    """Return human-readable findings (empty = clean)."""
    findings: list[str] = []
    by_skel: dict[str, list[str]] = defaultdict(list)
    by_sentence: dict[str, set[str]] = defaultdict(set)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = f.parent.parent.name if f.name == "cover-note.md" else f.stem
        sk = skeleton(_body(text))
        if len(sk.split()) >= 4:          # ignore trivially short openers
            by_skel[sk].append(name)
        for sent in sentences(text):
            by_sentence[re.sub(r'\s+', ' ', sent.lower())].add(name)

    for sk, names in sorted(by_skel.items(), key=lambda kv: -len(kv[1])):
        uniq = sorted(set(names))
        if len(uniq) >= 2:
            findings.append(
                f"  [same-opener] {len(uniq)} notes share the opening template \"{sk} ...\":\n"
                f"      {', '.join(uniq[:12])}{' …' if len(uniq) > 12 else ''}")
    for sent, names in sorted(by_sentence.items(), key=lambda kv: -len(kv[1])):
        uniq = sorted(names)
        if len(uniq) >= 2:
            findings.append(
                f"  [verbatim-sentence] repeated across {len(uniq)} dossiers ({', '.join(uniq[:8])}):\n"
                f"      \"{sent[:120]}{'…' if len(sent) > 120 else ''}\"")
    return findings


def default_files() -> list[Path]:
    return sorted(REPO.glob("applications/*/cover-letter/cover-note.md"))


def render(findings: list[str], n_files: int) -> str:
    if not findings:
        return (f"batch_voice_check: CLEAN across {n_files} notes: no shared opener, no verbatim "
                f"sentence reuse.\n  (The register of each note is voice_check.py's job; this only "
                f"gates cross-file sameness.)")
    head = (f"batch_voice_check: {len(findings)} cross-file sameness finding(s) across {n_files} "
            f"notes: rinse-and-repeat. Rewrite so each opens on its own specific true thing.\n")
    return head + "\n".join(findings)


def selftest() -> int:
    same_a = "Hi Sam, I saw the Senior Product Designer role, and the line about owning a product area stuck with me."
    same_b = "Hi Dana, I saw the Staff AI Interaction Designer role, and the line about shipping fast stuck with me."
    diff_c = "Hi Lee, Owning a payments surface end to end is the part of your posting I can speak to directly."
    dupe_sentence = "I built the design system solo so the coding agents read the tokens straight off an internal server."

    def run(pairs):  # pairs: list of (name, text) -> findings via temp files
        import tempfile
        fs = []
        td = tempfile.mkdtemp()
        for i, (nm, tx) in enumerate(pairs):
            d = Path(td) / f"app{i}-{nm}" / "cover-letter"
            d.mkdir(parents=True)
            (d / "cover-note.md").write_text(tx, encoding="utf-8")
            fs.append(d / "cover-note.md")
        try:
            return check(fs)
        finally:
            import shutil
            shutil.rmtree(td)

    passed = failed = 0

    def want(label, cond):
        nonlocal passed, failed
        passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
        print(f"  {'✓' if cond else '✗'} {label}")

    f_same = run([("a", same_a), ("b", same_b)])
    want("two notes with the SAME opener template are flagged",
         any("same-opener" in x for x in f_same))
    f_diff = run([("a", same_a), ("c", diff_c)])
    want("a genuinely different opener is NOT flagged as same-opener",
         not any("same-opener" in x for x in f_diff))
    f_dupe = run([("a", "Hi Sam. " + dupe_sentence + " I work on trust."),
                  ("b", "Hi Dana. " + dupe_sentence + " Different tail here entirely.")])
    want("a verbatim sentence repeated across two dossiers is flagged",
         any("verbatim-sentence" in x for x in f_dupe))
    f_one = run([("a", same_a)])
    want("a single note is never a same-opener finding", not f_one)

    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    files = [Path(a) for a in argv if not a.startswith("-")] or default_files()
    findings = check(files)
    print(render(findings, len(files)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
