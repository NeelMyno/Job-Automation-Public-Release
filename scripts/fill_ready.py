#!/usr/bin/env python3
"""fill_ready.py: a pre-fill readiness gate for an application's cover letter.

A cover-letter PDF should be mandatory in every application bundle, exactly
like the resume, and should travel with it. This gate exists because presence
alone turned out not to be enough: a stale-but-present cover letter (a PDF
that existed on disk but no longer matched its edited source note, carrying
banned phrasing, an em-dash, or otherwise off-voice copy) slipped through a
presence-only check and reached a live form before this freshness-and-content
check was added.

A presence-only check (does a cover PDF exist at all) is a weaker guarantee
than this one. This gate closes both holes: run it BEFORE opening the browser
to fill a dossier's form; a nonzero exit means DO NOT FILL until the cover is
rendered and content-clean.

What it checks, per dossier:
  1. A cover-letter PDF is PRESENT.                              else -> BLOCK
  2. The cover SOURCE note passes the content linter              else -> BLOCK
     (voice_check.py, pluggable; swap in your own).
  3. The cover PDF is not STALE vs the note (PDF mtime >= note).  else -> BLOCK

Exit codes:  0 = ready to fill · 2 = BLOCKED (one or more failures) · 3 = usage error.

Usage:
    python3 scripts/fill_ready.py "applications/<company>-<role>"
    python3 scripts/fill_ready.py --selftest
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VOICE_CHECK = REPO / "scripts" / "voice_check.py"

# Cover source notes are named a few ways across a dossier tree; the largest markdown
# file in cover-letter/ is treated as the sendable body when none of these match.
# "waas-message.md" is an example of a board-specific convention (originally named for
# a "Work at a Startup"-style job board). It is optional, not load-bearing; add or
# remove filenames here to match your own dossier naming.
NOTE_NAMES = ("cover-note.md", "cover-letter.md", "waas-message.md", "message.md")


def find_cover_note(cover_dir: Path):
    for name in NOTE_NAMES:
        p = cover_dir / name
        if p.is_file():
            return p
    # fall back to the largest .md that is not obviously a render artifact
    mds = [p for p in cover_dir.glob("*.md")]
    if mds:
        return max(mds, key=lambda p: p.stat().st_size)
    return None


def sendable_body(text: str) -> str:
    """The cover note's SENDABLE body is the text between the first pair of `---`
    fences (repo convention). The meta tables and JD-to-line map after them are
    internal doc, not shipped copy, so they are not voice-checked (em-dashes and
    `⌘K` legitimately appear there). If there are no fences, the whole text is the
    body (e.g. the synthetic selftest notes)."""
    parts = text.split("\n---\n")
    return parts[1].strip() if len(parts) >= 3 else text.strip()


def voice_clean(path: Path) -> bool:
    """True iff the SENDABLE body of the note passes voice_check.py (exit 0)."""
    body = sendable_body(path.read_text(encoding="utf-8", errors="replace"))
    r = subprocess.run(
        [sys.executable, str(VOICE_CHECK), "-"],
        input=body, capture_output=True, text=True,
    )
    return r.returncode == 0


def check_dossier(dossier: Path):
    """Return a list of failure strings (empty == ready to fill)."""
    fails = []
    cover_dir = dossier / "cover-letter"
    pdfs = list(cover_dir.glob("*.pdf")) if cover_dir.is_dir() else []

    if not pdfs:
        fails.append(
            "no cover-letter PDF in the bundle (a cover letter is mandatory and travels "
            "with the resume). Render + gate a cover BEFORE filling the form."
        )
        # No PDF: still report note voice state if a note exists, but the block stands.
        note = find_cover_note(cover_dir) if cover_dir.is_dir() else None
        if note and not voice_clean(note):
            fails.append(f"cover source {note.name} also fails the content linter (off-voice copy).")
        return fails

    cover_pdf = pdfs[0]
    note = find_cover_note(cover_dir)
    if note is None:
        fails.append(
            "cover-letter PDF present but no source note found to content-check "
            "(expected cover-note.md). Cannot confirm the copy is clean."
        )
        return fails

    if not voice_clean(note):
        fails.append(
            f"cover copy is STALE / off-voice: {note.name} fails the content linter "
            "(voice_check.py). Re-render clean copy before filling."
        )

    # staleness: the rendered PDF must be at least as new as its source note
    if cover_pdf.stat().st_mtime + 1 < note.stat().st_mtime:
        fails.append(
            f"cover PDF ({cover_pdf.name}) is OLDER than its note ({note.name}): "
            "the note was edited but not re-rendered. Re-render before filling."
        )
    return fails


def run(dossier_arg: str) -> int:
    dossier = Path(dossier_arg)
    if not dossier.is_absolute():
        dossier = REPO / dossier
    if not dossier.is_dir():
        print(f"fill_ready: usage error, no such dossier: {dossier_arg}")
        return 3
    fails = check_dossier(dossier)
    name = dossier.name
    if fails:
        print(f"fill_ready: BLOCKED, {name} is NOT ready to fill ({len(fails)} issue(s)). Do not open the browser.")
        for f in fails:
            print(f"  🔴 {f}")
        return 2
    print(f"fill_ready: OK, {name} has a present, voice-clean, current cover-letter PDF.")
    return 0


def selftest() -> int:
    """Build synthetic dossiers and assert the cover-readiness logic: an absent
    cover, a stale/off-voice cover, a cover PDF older than its source note, and
    a clean bundle that should pass."""
    clean_note = (
        "I build tools that turn a messy, manual process into something a small team can "
        "run without babysitting it. In my last role I rebuilt an internal reporting "
        "pipeline that used to take a full day of manual spreadsheet work each week; it "
        "now runs on a schedule and flags the two or three rows that actually need a "
        "human look. I like this kind of problem because the win is measurable and the "
        "team feels it immediately."
    )
    # Content designed to trip the content linter (an em-dash, here) rather than model
    # every possible failure: the point is exercising the "linter says no" path.
    stale_note = (
        "At my last company I owned the onboarding flow end to end — research, design, "
        "and the shipped implementation — and measured a drop in first-week support "
        "tickets after it launched."
    )
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def mk(name, *, pdf=True, note=None, pdf_older=False):
            d = root / name
            cov = d / "cover-letter"
            cov.mkdir(parents=True)
            if pdf:
                p = cov / "Cover Letter.pdf"
                p.write_bytes(b"%PDF-1.4 dummy")
            if note is not None:
                n = cov / "cover-note.md"
                n.write_text(note, encoding="utf-8")
                if pdf_older and pdf:
                    import os
                    # make the PDF two hours older than the note
                    st = n.stat()
                    os.utime(cov / "Cover Letter.pdf",
                             (st.st_mtime - 7200, st.st_mtime - 7200))
            return d

        cases = [
            ("clean bundle",             mk("clean", pdf=True, note=clean_note),   True),
            ("absent cover",             mk("absent", pdf=False, note=None),       False),
            ("stale / off-voice cover",  mk("stale", pdf=True, note=stale_note),   False),
            ("PDF older than note",      mk("older", pdf=True, note=clean_note, pdf_older=True), False),
        ]
        for label, dossier, want_ready in cases:
            fails = check_dossier(dossier)
            got_ready = not fails
            good = got_ready == want_ready
            ok = ok and good
            verdict = "PASS" if want_ready else "BLOCK"
            got = "PASS" if got_ready else "BLOCK"
            mark = "ok " if good else "FAIL"
            print(f"  [{mark}] got {got}, want {verdict}: {label}"
                  + ("" if good else f"  <-- fails={fails}"))
    print("fill_ready selftest", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) == 2:
        return run(argv[1])
    print(__doc__)
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
