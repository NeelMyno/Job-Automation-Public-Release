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

**The bar, and it is mechanical:** `python3 scripts/resume_gate.py` must exit 0.

1. **Exactly one page.** Two is a hard fail.
2. **Fill ≥ 88% of the page height.** Empty space on a one-page résumé isn't restraint, it's
   unused evidence.
3. **Every employment entry is on the page**: every employer under `### WORK EXPERIENCE` in
   `knowledge-base/07-master-resume.md`, each beside its own start date, and the current one
   beside a still-open date range rather than demoted to a project credit. The required set is
   read from the KB at run time, so a job change updates the gate with no code edit.

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
python3 scripts/resume_gate.py applications/<dossier>      # must exit 0
```

Copying the whole file (and its fonts) and applying one delta is what keeps every résumé variant
honest and complete. An agent that opens a blank file and authors a résumé fresh for each target
is the failure mode this rule exists to prevent: independent authoring passes lose content that
copying never would.
