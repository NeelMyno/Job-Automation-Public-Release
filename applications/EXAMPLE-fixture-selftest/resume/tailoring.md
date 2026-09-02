# Tailoring record — EXAMPLE-fixture-selftest (SELFTEST FIXTURE)

**Cards IN:** the design-system-and-code card (documented in the cover note)

**Cards OUT:** nothing declared out for this fixture

**Honesty note:** synthetic content only. Exercises R11 (`scripts/verify_claims.py`), which
reconciles this declaration against what actually ships in resume.html, cover-note.md, and
application.md. `--selftest` also copies this file into a temp dossier and edits these two
declarations directly to exercise both failure directions — see `_selftest_r11()`.
