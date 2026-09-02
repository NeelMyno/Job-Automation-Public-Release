# ops/ — Index (read this first for re-orientation)

This is the session record for this repo's own operation, not about you. The canonical knowledge
about **you** lives in `../knowledge-base/`; this folder tracks the work done *on* the repo itself —
decisions, sessions, open threads.

**Orientation order for a new session:** `../CLAUDE.md` → `../knowledge-base/INDEX.md` → this file →
`HANDOFF.md` (if present) → `STATE.md` (if present).

- **STATE.md** — living status, overwritten in place every time it changes, so it stays current and
  never grows. Gitignored: a live working file, not part of committed history. Read it after this
  file, when it exists — a fresh clone won't have one yet.
- **HANDOFF.md** — the session-resume digest, written at the end of a `/wave` or `/outreach` session
  so the next session can pick up without re-reading the whole repo (`CLAUDE.md` §13.8). Read it
  first when you're resuming one of those sessions, before `STATE.md`.
- **decisions/** — the immutable, append-only ADR ledger. A locked decision gets one numbered file
  here and is never edited again; if it changes, a new ADR supersedes it instead. `decisions/INDEX.md`
  lists every one with its status. An ADR that leaves work owed carries a `Consequences-pending:` line
  until a later ADR clears it with `Consequences-cleared: ADR-NNNN` — `scripts/adr_debt.py` surfaces
  any uncleared line at every session start, so owed work stays visible without a separate tracking
  file to maintain.
- **briefs/** — work orders, for whenever you delegate a piece of work to a subagent or hand it to a
  separate session. A brief names the mission, what to read first, the phases of the work, and exactly
  what its completion report has to contain. `briefs/INDEX.md` lists them.
- **reports/** — completion reports, one per brief, sharing its number. Records what actually shipped,
  what deviated from the brief, and what's still open. `reports/INDEX.md` lists them.
- **notes/** — numbered research and thinking scratch: a probe, a research outcome, a dossier audit.
  Not canonical and not binding on anything else in the repo — just the working trail. `notes/INDEX.md`
  lists them.
- **log/activity.md** — the append-only chronological session log. Every working session where
  something real happened adds one short entry before it ends.

**Naming rule:** every sequenced file in `ops/` is `NNNN-slug.md` — a 4-digit zero-padded number plus
a lowercase-kebab slug. `decisions/`, `briefs/`, `reports/`, and `notes/` each keep their own running
sequence starting at `0001`; a brief and the report that closes it share a number. The fixed
structural files keep bare names: `INDEX.md`, `STATE.md`, `HANDOFF.md`, `decisions/INDEX.md`,
`log/activity.md`.
