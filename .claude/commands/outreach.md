---
description: THE outreach session pipeline, one command that derives all pending outreach + follow-ups from the shared records, researches, drafts, gates, and hands over. No arguments runs everything; "<person> <dossier>" runs one person.
argument-hint: [person-name-or-linkedin-url] [dossier-folder]
---

# /outreach: the outreach SESSION, end to end, off one command

Optional narrow-target: `$1` `$2` (a single person + dossier runs only stages 4-6 for them).

**What this is:** outreach runs in its OWN session type, the way applications run in `/wave`. You
initiate a fresh session, type `/outreach`, and the pipeline picks up every application whose
outreach is pending across ALL sessions, because the queue is **derived from the shared records,
never maintained**. Application sessions hand nodes over and STOP; this session does the outreach.

**THE SSOT LAW (the reason this command exists):** outreach state lives in exactly four shared
surfaces, and nowhere else:

| Surface | What it owns |
|---|---|
| `applications/<dossier>/referrals.md` | the roster + the gated copy, per company |
| `pipeline/sent-ledger.md` | what actually left (append-only) |
| `pipeline/tracker.html` NETWORK | relationship state (replied, active, dead) |
| `pipeline/inmail-ledger.md` | InMail credits, if you track them |

🔴 **Creating a queue/pending/send-sheet file is a DEFECT.** The queue is derivable
(`scripts/outreach_queue.py`), so any maintained copy is a second source of truth that will drift.
Working scratch goes to the session scratchpad; records go to the four surfaces, **in the same
turn as the event they record** (parallel sessions read them live; commit small and promptly,
CLAUDE.md §10).

## The pipeline (in this order)

**0. Resume point (≤5 min, fixed list; a wall, same as /wave).** `ops/HANDOFF.md` + `ops/STATE.md`,
then `python3 scripts/outreach_queue.py` and the reconcile: any handed-over-but-unledgered send from
a prior session becomes ONE direct question to the operator, never silence. Do not read predecessor
transcripts or legacy queue files (anything stamped OUTDATED is history, not work).

**1. Derive the queue.** `python3 scripts/outreach_queue.py` is the ONLY queue. Its sections are the
session's worklist, in this priority order: **REPLIED** threads needing the operator's next move
(surface them first: a live thread outranks every new send) → **FOLLOW-UP-DUE** →
**READY-TO-SEND** → **NEEDS-DRAFT** → **NO-ROSTER** → **FIRE-ON-ACCEPT** (hand the operator the
list to check acceptances; the DMs for accepted people ship this session).

**2. Holds and the go.** Typing `/outreach` IS the operator's go for the derived queue. The one
exception: hold stamps the script surfaces; quote them and get the hold lifted in turn one; the
agent never lifts a hold itself. Standing sub-holds (e.g. referral-before-application ordering on
specific reqs) bind until the recorded condition clears.

**3. Fill NO-ROSTER (research fan-out, parallel, background).** One agent per dossier: identify the
hiring node + 5-8 verified-real people (volume rule below), fetch their real work into `sources/`
(CLAUDE.md §0.1 in full: the brief carries the Grounding Law verbatim; a subagent that cannot cite
returns UNVERIFIED), write the roster skeleton into that dossier's `referrals.md`. Agents write ONLY
their own dossier's files. Drafting stays main-thread.

**4. Draft (main thread, per person: the standing doctrine, unchanged):**
- 🔴 **THE MANDATORY STRUCTURE:** every message carries, in order: **(1) one fetched, checkable
  observation about THE RECIPIENT'S OWN WORK first** (on disk in `sources/`, described truthfully;
  nothing personal found → say so in the pack and lead with the strongest true bridge); **(2) the
  action item: your portfolio HOME**, never a deep link unless a specific hook genuinely calls for
  it; **(3) the actionable ask, ALWAYS present**: default "would you be open to referring me?"; for
  the person who directly owns/decides THIS hire (founder/CEO applied-to, req-owning HM,
  pipeline-owning recruiter) the ask reshapes (never drops) to "be considered / put me in your
  process." Flag each such carve-out so the operator can flip it. A message that leads with you
  instead of the recipient is a defect. If two messages share a skeleton, both are wrong.
- 🔴 **Lead with your real differentiator, never the commodity mechanism.** Define, once, in
  `knowledge-base/11-preferences-and-conventions.md`, what your own single non-commodity strength
  is (the thing that isn't trivially interchangeable with anyone else who has similar tools).
  Anchor every message in a SPECIFIC real decision or outcome, not an adjective. `voice_check.py`
  gates the generic AI-slop tells; it can't gate a positioning choice only you can make: make it
  once, in writing, so every draft after that pulls from the same real answer instead of guessing.
- **Both messages, every person:** connection note under 300 chars + DM headed `Use InMail:
  YES/NO` with the one-line reason (balance from the InMail ledger if you track one). 1st-degree
  contacts: DM only.
- **Shape:** paragraphed to the reference shape in `.claude/outreach-handover-format.md`; **every
  referenced opening carries its exact title + req ID**, and never an invented one.
- **Register is human:** reads like a person typed it; uneven sentences; the read-aloud test
  governs. CLAUDE.md §11 detectors apply. **The card rule** (§13.2): name cards-in/cards-out in the
  dossier.
- **Volume:** 5-8 verified-real people per company where they exist; an empty slot is a correct
  answer; never invent a person.
- **Facts current:** tenure math and every biographical number comes from `knowledge-base/07` at
  draft time, not from a frozen earlier draft.
- All copy is written INTO the dossier's `referrals.md` (`## The messages` → `### Person` blocks,
  following `outreach_format.py`'s grammar). That file is the record; chat is read off it.

**5. Follow-ups (same doctrine, smaller ask).** Default: **one nudge after 4+ days of silence, one
ever** (the operator can override per thread). A nudge is two or three sentences anchored to the
original thread, no new ask escalation. REPLIED threads never get automated nudges; surface them
to the operator with a drafted reply instead.

**6. Gates, per touched dossier.** `python3 scripts/outreach_format.py "<dossier>/referrals.md"` →
exit 0, and `python3 scripts/verify_claims.py "<dossier>"` → exit 0, quoting the `NOT checked:`
line verbatim in the handover.

**7. Hand over: the locked format, and no other.** State each company's basket (a common
default: big/established company = no daily cap; small/startup = 3 sends/company/day counted off
today's ledger rows; unsure = treat as small) so the operator can self-pace. InMail YES
recommendations name why. **Deliver in the locked copy-paste format**
(`.claude/outreach-handover-format.md`): a scratchpad `.md`, per-person connection note + DM each
in its OWN fenced code block (blank-line paragraphs preserved so a LinkedIn paste keeps the
breaks), sent as a file the operator can open directly. If the operator wants the format changed,
update that template and follow it onward; don't reinvent the shape session to session.

**8. Log as they send: same turn, every time.** Their "sent" → ledger row (schema: `date ·
recipient · company · channel · message-ref · copy-state-at-send · sent-by`; recipient BEFORE
company; rows are append-only, a wrong row gets a correcting row) + tracker NETWORK update +
InMail ledger if a credit moved. A screenshot of a reply → `sources/` snapshot + NETWORK note (that
is what makes REPLIED detection work). Commit each batch (push per your own §10 preference).

**9. Close.** Re-run `outreach_queue.py` (the after-photo goes in the handoff), overwrite
`ops/HANDOFF.md` + STATE top block, one activity.md line, commit.

## The walls (violations, learned the expensive way)

1. **A real social platform is NEVER automated.** Fetching public surfaces account-safely is fine;
   the operator's own login, sends, and acceptance-state reads are their hands only.
2. **Tooling freeze while the queue is open** (same as `/wave` wall #1): gate/script/tracker-schema
   work goes to `ops/DEBT.md` unless it makes an outgoing message false (fix that instance, ≤15 min).
3. **No new queue files, ever** (the SSOT law above). Superseding a legacy queue file = stamp it
   OUTDATED in its first lines (`hooks.py` treats that as consumed).
4. **Dead dossiers are read-only** (§13.8 wall #3): no outreach for rejected/withdrawn/passed roles.
5. **Applications are out of scope here.** A form to fill goes to a `/wave` session; this session's
   deliverable is HANDED-OVER MESSAGES + a reconciled ledger (the mirror of `/wave`'s own wall,
   pointed the other way).
6. **Don't stack extra exhaustive-audit modes on this**: the pipeline already encodes the depth.
