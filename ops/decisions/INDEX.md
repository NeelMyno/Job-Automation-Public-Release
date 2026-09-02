# Decisions (ADR) Index

Immutable, append-only. Each ADR is a locked decision; supersede it with a new one, never rewrite it.

**Status values:** `Accepted` (locked, currently in force) · `Accepted (partial-supersession note)`
(still locked, but a later ADR narrowed or corrected one specific part, noted inline) · `Superseded
by ADR-NNNN` (fully replaced by a later ADR, kept for history, no longer in force).

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-example-starter-decision.md) | **Worked example for this ledger, and a real fixture.** Every locked decision gets its own numbered, append-only file (`NNNN-slug.md`, sequential, never reused); a changed decision is never edited in place, a new ADR supersedes it instead; work a decision leaves owed carries a `Consequences-pending` line until a later ADR clears it. `scripts/visa_gate.py --selftest` checks against this exact ADR number, so leave it in place and add your own ADRs after it. | Accepted | 2026-01-01 |
