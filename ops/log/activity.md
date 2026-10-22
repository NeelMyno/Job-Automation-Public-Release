# Activity Log: append-only, newest entries at the bottom

Every working session where something real happened adds one entry before it ends: the date, what the
session focused on, what actually shipped, the commit SHA if there is one, and what's next. Keep each
entry to 5 lines or fewer. Never edit or delete a past entry; if something in it turns out to be
wrong, say so in a new one instead.

## 2026-01-01: Repo template created

Built out the `knowledge-base/` template set, the gate scripts and their `--selftest` fixtures, the
job-crawler pipeline, and this `ops/` system of record (the ADR ledger, the briefs/reports/notes
pointers, this log). Next: fill in your own `knowledge-base/` files per `SETUP.md`, then run each gate
script's own `--selftest` on your clone before you send anything real.
