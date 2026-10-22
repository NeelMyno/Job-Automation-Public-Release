---
paths:
  - "pipeline/**"
  - "applications/**"
  - "ops/DEBT.md"
  - "ops/HANDOFF.md"
  - "knowledge-base/11-preferences-and-conventions.md"
---
<!--
The one shape for every record surface. Claude Code loads this file by itself the moment a chat opens
a record file; Codex reads it before writing one. This file owns SHAPES only. Meanings stay with their
owners: what to record and where (CLAUDE.md, the tracker section), @OWED (scripts/commitments.py), the
cold classes (scripts/cold.py). The grammars in code: scripts/records.py. The gate:
scripts/records_check.py, which runs at session start and at the end of any turn that changed a record
file, and fails on any row out of shape.
-->

# Record formats

Why one format: a row in a shape no script recognises is a row no script surfaces. A contacted person
with no follow-up state, a submitted application with no submit date, a ledger whose columns flipped
halfway down: each one is a cold item nobody sees. So every record row has exactly one shape, written
down here, and a gate that refuses anything else.

Rules for every surface: dates are `YYYY-MM-DD`. A time, when one exists, is your own local time with
its zone label (`2:05 PM CST`); the zone is whatever you set up, never a fixed one. An unknown is written
as the surface's unknown marker below, never left out and never guessed. Check before you finish:
`python3 scripts/records_check.py` exits 0.

## 1. `pipeline/tracker.html`: APPLICATIONS row

```
{co:"...", role:"...", loc:"...", comp:"...", compK:N, status:"<status>", fit:"...", spon:"...", posted:"<posted>",
 source:"...", jd:"<url>", apply:"<url>", folder:"applications/<slug>"|"", refs:N, everify:"...", applied:"<applied>",
 next:"...", notes:"...", link:"..."},
```
- `everify` is optional: leave it out if E-Verify does not matter to you. When present it is a string.
- `status`: `lead`, `active`, `applied`, `interview`, `offer`, `rejected`, `passed` (the page's STATUS map).
- `applied`, required on every `applied`, `interview`, `offer` and `rejected` row: `YYYY-MM-DD` (the submit
  date from a dated record, such as the confirmation email), `on or before YYYY-MM-DD` (no dated record; the
  first day the tracker showed it submitted, so the submit was that day or earlier), `unknown`, or
  `none on record` (the row reached interview or rejection and no record shows any application submit,
  for example an interview that came from outreach). Set it the same turn the row flips to `applied`.
- `posted`: `YYYY-MM-DD` or `unknown`. Anything looser (an approximate date, "about a month ago") goes into
  `notes` as `posted (as recorded): ...`.
- `folder`: `applications/<slug>` of a folder that exists, or `""`. Never `null`, never without the prefix.
- `next`: free text, newest first, carrying `@OWED[...]` tokens (section 4). No empty slots in the array (`,,`).
- Keys are lower case. APPLICATIONS uses `notes`, never `note`.

## 2. `pipeline/tracker.html`: NETWORK row

```
{name:"...", company:"...", role:"...", status:"lead|active|passed", note:"...", link:"...", fu:"<state>|<YYYY-MM-DD or ?>|<what>"},
```
- **Every person the sent-ledger shows a message to has a NETWORK row, and that row carries `fu`.** Write
  both the same turn the ledger row is written.
- `fu` states, four and only four:
  - `me`: you owe the next move. Always surfaced.
  - `them`: waiting on them since the date. Due for the one nudge after `FOLLOWUP_DAYS` (scripts/config.py).
    A connection note still waiting on an accept is never nudged; it goes cold after `COLD_ACCEPT_DAYS`.
  - `rest`: the one nudge is spent, or the thread is parked. Cold again after `COLD_REST_DAYS`.
  - `closed`: the thread is over, nothing owed by anyone (the role closed, the person declined, the talk
    ended). Never surfaced.
- `?` in the date slot means the date is not on record.
- Personal-network rows may use their own keys (`event`, `howMet`, `ask`, `contact`, `next`, `notes`) in
  place of `company`; the same `fu` rule applies.

## 3. `pipeline/sent-ledger.md`: one row per message that left

`| YYYY-MM-DD | <recipient> | <company> | <channel> | <message-ref> | <copy-state-at-send> | <sent-by> |`
- Always 7 cells, recipient before company. A pipe inside a cell is written `\|`. A cell with nothing on
  record says `not recorded`.
- An application form submit is its own row type: the recipient cell is exactly an em dash followed by
  ` (application form)`, and the company goes in the company cell.
- A message that could not be sent is not a send: say `COULD NOT SEND` in the copy-state cell.
- Append only. A wrong row is corrected by a later row.

## 4. `@OWED` token (inside APPLICATIONS `next:` or NETWORK `fu:` only)

`@OWED[them|you | YYYY-MM-DD|? | <what, no ]>]`. Required on every interview and offer row
(scripts/commitments.py). A take-home, assessment or deadline named in `next:` carries one.

## 5. `pipeline/inmail-ledger.md`: balance table (optional)

Only if you use a paid tier with a monthly message allotment. Under `## Current balance`:
`| YYYY-MM-DD | <credits>|unknown | <source> |`, one row on every count change and every refill. A row in
square brackets is the template's placeholder and is skipped. Set `INMAIL_REFILL_DAY` in
scripts/config.py and `scripts/cold.py` will flag a balance not counted since the last refill.

## 6. `applications/<slug>/application.md` of a submitted row

- A heading `## SUBMITTED <when>`, optionally followed by free text (`, from the agent-filled tab`). `<when>`
  is `YYYY-MM-DD` (a local time may follow: `2026-01-19 9:04 PM CST`), `on or before YYYY-MM-DD`, or
  `(date not recorded)`.
- An answers heading: `## Exact form answers (as filled, YYYY-MM-DD)` or `(as filled, date not recorded)`,
  a note may follow the date after a comma; or `## Exact form answers (not recorded)` for a submit whose
  answers no record holds. A prepared or intended block is not an as-filled block.
- A row whose `applied` is `none on record` carries `## NO SUBMIT ON RECORD` instead, and no SUBMITTED heading.
- Each work-authorization answer under the answers heading is one line: `- "<question exactly as printed>"
  → Yes` (or `→ No`). A statement-style option: `- "<question>" → "<option text>" (= No)`.
  `scripts/visa_gate.py` also reads `-> No`, `: Yes`, a trailing `? Yes` and `**Yes**`, and reports any
  answer it cannot read as UNVERIFIED (exit 1).

## 7. `applications/<slug>/referrals.md`

The person blocks that `scripts/outreach_format.py` reads. It holds the drafted copy only: what was sent
lives in the sent-ledger alone.

## 8. File names in `applications/<slug>/correspondence/` and `calls/`

`YYYY-MM-DD-<lowercase-kebab-slug>.<ext>` (`2026-01-06-connection-note-to-jordan-sent.md`); a draft ends
`-draft`, a sent copy `-sent`. No date on record: `undated-<slug>.<ext>`. The `TEMPLATE-` and `EXAMPLE-`
folders are scaffolding, not records, and are not checked.

## 9. `ops/DEBT.md` row

`| YYYY-MM-DD | <owner> | <item> | OPEN |`, one row per item, inside the table. The owner is `agent` or
`you` (or your name). Close a row by changing its status to `CLOSED YYYY-MM-DD: <what fixed it>`; never
delete it. No item written as a heading.

## 10. `knowledge-base/11` ratified-decisions row

One row per decision in the table under `## Ratified decisions`: a `YYYY-MM-DD` date first, and the same
number of cells as the table's header (`| Date | Decision | Why |` as shipped). Append only.

## 11. `ops/HANDOFF.md`

One block, the `/wave` close template (`.claude/commands/wave.md`), overwritten at each close. Never a
second top-level `# ` block stacked under the first.
