# ADR-0001: This is a worked example; read it, then write your own real ADRs the same way

**Date:** 2026-01-01 · **Status:** Accepted · **Decider:** you

## Context

`ops/decisions/` is where a locked decision gets recorded permanently, so a future session (yours
or an agent's) doesn't have to re-litigate something you already decided. This file exists as a
worked example of the shape (three sections, nothing more) and as a real fixture some of the
repo's own gate scripts test against (see `scripts/visa_gate.py`'s `--selftest`, which references
this exact ADR number). Leave it in place; add your own ADRs after it rather than replacing it.

## Decision

1. Every locked decision gets its own numbered file here: `NNNN-slug.md`, sequential, never reused.
2. ADRs are **append-only**: if a decision changes, write a NEW ADR that supersedes the old one
   (its own `Status:` line becomes `Superseded by ADR-NNNN`); never edit history in place.
3. A decision that's still open, or that creates follow-up work, carries a
   `Consequences-pending: <what's still owed>` line; `scripts/adr_debt.py` surfaces any of these
   older than a week at every session start, so debt can't quietly rot.

## Consequences

- `ops/decisions/INDEX.md` gets one line added, in the same commit, whenever a new ADR is added.
- Nothing else in the repo restates a locked decision's content; every other file just points here
  (`CLAUDE.md` §8, enforced by `scripts/check_law.py`).

Consequences-pending: none.
