# Résumé: source of truth and how to rebuild it

**Source:** `resume.html` (this folder). Content comes from `knowledge-base/07-master-resume.md`.

🔴 **Every locked fact (the banned strings and the canonical numbers) lives in ONE place: the
```canonical-facts``` block in `knowledge-base/07-master-resume.md`.** `scripts/resume_gate.py`
parses that block and grades every résumé against it, so changing a fact there re-checks every
résumé automatically. Never restate those values anywhere else; point here.

## Rebuild

```
pip install weasyprint
weasyprint resume.html your_name_resume.pdf
```

Fonts: Inter (this folder's `fonts/`), referenced by a **relative** path in the HTML. This is
what makes the same file render correctly on any machine, unlike an absolute path. A4, 1 page,
ATS-safe single column.

## 🔴 ONE PAGE, AND THE WHOLE PAGE

**The bar, and it is mechanical:** `python3 scripts/resume_gate.py` exits 0. Its exit codes:
0 passes, 1 is a hard failure, 2 means no résumé was found, and 3 is an OPEN ITEM (rule 2 below)
that waits on your decision.

1. **Exactly one page.** Two is a hard fail.
2. **Fill ≥ 88% of the page height.** Empty space on a one-page résumé isn't restraint, it's
   unused evidence. **A near-miss is an ADVISORY, not a fail:** a fill within a few points of the
   floor (`FILL_ADVISORY_MARGIN` in the script) on an otherwise complete, one-page résumé that
   carries every employer is reported without failing. Closing that last line (one more real
   bullet, or a layout tweak) is your content call, not the gate's. Without this, an honest master
   résumé that runs one line short reads red, and every batch stops to ask about a cosmetic gap.
   **Further below the floor is an OPEN ITEM (exit 3), not a failure.** A real résumé can be short
   because the history behind it is short, and padding it with anything untrue is never the fix.
   The gate names three honest options: add real material you left out, adjust the layout within
   readable limits, or record your decision in the ```canonical-facts``` block of
   `knowledge-base/07-master-resume.md` as `accept: short-page | <lowest fill % you accept> | <why>`.
   With that line, a page at or above your number passes with an advisory; a copy that falls below
   it (a tailored variant that lost content) is an open item again. Large emptiness that comes from
   a cut job is still a hard fail, through rule 3.
3. **Every employment entry is on the page**: every employer under `### WORK EXPERIENCE` in
   `knowledge-base/07-master-resume.md`, each beside its own start date, and the current one
   beside a still-open date range rather than demoted to a project credit. The required set is
   read from the KB at run time, so a job change updates the gate with no code edit.

**Why rule 3 is in a page-fill gate.** The two defects travel together. The classic shape: a
tailored variant fills about two thirds of the page AND has dropped the current employer (or kept it
only as a line under Selected Projects), so its Experience section ends years ago and the reader
sees someone who has not worked since. The blank third of the page is the visible symptom; the cut
employer is the defect. Rule 3 catches the omission directly, whatever the fill.

**When tailoring, cut nothing structural.** Tailoring is emphasis and ordering. If a variant ends
up shorter than the canonical page, that's not tailoring, it's loss.

## 🔴 A TAILORED RÉSUMÉ IS DERIVED, NEVER WRITTEN FRESH

**Copy `resume/resume.html`, apply the one delta `tailoring.md` records, render. That is the whole
procedure.**

```
cp resume/resume.html applications/<dossier>/resume/resume.html
cp -r resume/fonts applications/<dossier>/resume/fonts
#   apply ONLY the delta recorded in that dossier's tailoring.md
weasyprint applications/<dossier>/resume/resume.html applications/<dossier>/resume/<name>.pdf
python3 scripts/resume_gate.py applications/<dossier>      # exit 0, or 3 for an open item you decide
```

Copying the whole file (and its fonts) and applying one delta is what keeps every résumé variant
honest and complete. An agent that opens a blank file and authors a résumé fresh for each target
is the failure mode this rule exists to prevent: independent authoring passes lose content that
copying never would.

**Why copying, measured.** Run several résumé builds in parallel, each authored fresh, and they
tend to lose the SAME content independently (an employment entry, a dated role), even when every
`tailoring.md` records one intended change and nobody decided to cut anything. Authoring is lossy;
copying is not. Run `python3 scripts/resume_gate.py` across every résumé PDF in the repo after a
batch, not just the one you touched.

## A line ruled not yours never comes back

When a résumé line is corrected because the work, the number or the authorship was not yours, it
goes into the `never:` list of the ```canonical-facts``` block in `knowledge-base/07-master-resume.md`
(and, if it can show up in other copy, the retired-claim registry in `scripts/canon.py`) in the same
change. It is never offered back "for a tailoring where it would help". A note here that says
"add it back for X" is a stale rule waiting to ship the claim again.
