# Job Search Engine

An agent-run career engine, supported in Claude Code and Codex, that turns a job description into
a tailored résumé + cover letter, discovers new postings automatically, preps you for interviews, and
drafts warm outreach. **Built for any role, any industry, anywhere in the US.**

![How the engine works: a one-time setup feeds a knowledge base, which feeds a discovery track and a build track; both converge on a grounding gate that checks this dossier's own content and, in a second row, the repo itself every session; a passing draft reaches one of two points where you, not the agent, click Submit or Send; and ops/ carries session memory across the whole thing.](docs/architecture.svg)

One-time setup, a gate that checks both this dossier and the repo itself, session memory that
carries across a fresh clone's sessions, and two feedback loops that keep the whole thing honest.

New here? Read [`SETUP.md`](SETUP.md) first: it's the whole onboarding walkthrough, start to finish.

## How it works

Everything stands on a **knowledge base** (`knowledge-base/`): a distilled, always-accurate picture
of your profile, experience, projects, career narrative, and work-authorization situation. It ships
**empty**: you fill it in once during setup, and every output after that is grounded in your real
facts instead of a guess. The agent reads that knowledge base before every task.

The agent operates with the research + reasoning depth of a sharp career advisor (search-first,
self-critical, honest), but with a builder's hands: it edits files, renders documents, and drives a
browser to fill (never submit) real forms. See `CLAUDE.md` for the full operating rules.

## The gates: why this repo can be trusted

Everything an employer sees is checked by a script, not by an agent remembering to be careful.
The diagram above shows the checks a single dossier's résumé, cover letter, and outreach draft
must clear before a human ever sees them (`verify_claims`, `canon`, `visa_gate`, plus `resume_gate`
and the voice/subject checks). The full repo-wide gate suite is wider than that and includes the
rules and the goal themselves, not just one dossier's content. Five of those gates, each with a
self-test that runs clean out of the box on a fresh clone:

```
python3 scripts/verify_claims.py "applications/<company>-<role>"   # outbound copy
python3 scripts/canon.py            # the knowledge base: no retired claim may be asserted
python3 scripts/visa_gate.py        # work-authorization answers (the highest-stakes surface)
python3 scripts/check_law.py        # the rules themselves: one owner per rule, no dangling refs
python3 scripts/throughput.py       # the goal itself: finished work sitting unsent, a dossier
                                    # contradicting itself, commits held back
```

They also run from the harness (`.claude/settings.json`): true state is printed at session start,
every file written is checked, and a turn that introduces a defect is **blocked**.

## Layout

- `CLAUDE.md`: the operating manual the agent reads first. Start here (after `SETUP.md`).
- `SETUP.md` covers onboarding: what to fill in, in what order, and how much is truly required.
- `.codex/`: Codex configuration, lifecycle-hook wiring, and repository command policy. Loads
  `CLAUDE.md` directly rather than duplicating it.
- `.agents/skills/`: Codex adapters for the canonical `/wave`, `/outreach`, and review workflows.
- `STRUCTURE.md`: where every file goes and how things are named.
- `knowledge-base/`: canonical knowledge about *you*. `INDEX.md` maps it. Ships empty.
- `scripts/`: the gates above, plus the session hooks.
- `.claude/`: the two lane commands (`/wave` for applications, `/outreach` for networking), the
  five-pass review workflow, and `settings.json` (the hooks).
- `ops/` is this repo's own session record: `STATE.md`, `HANDOFF.md`, `decisions/` (an immutable ADR
  ledger), `log/activity.md`, `notes/`.
- `docs/`: the architecture diagram at the top of this file.
- `applications/`: active per-job dossiers, one folder per job. Copy `TEMPLATE-company-role/` to
  start one.
- `resume/`: your current résumé (source, built PDF, fonts).
- `pipeline/`: the job crawler (100% free, public, keyless ATS APIs), the live status tracker, send
  + InMail ledgers.

## Typical asks

- "Here's a job description; make me a tailored résumé and cover letter."
- "I have an interview with X; prep me."
- "Crawl the boards for anything new that fits."
- "Research this company / role / comp band / work-authorization posture."
- "Draft an outreach message to this person."

## What this is not

This is not a mass-application spray tool, and it isn't built to be one. The single highest-leverage
move in most job searches is a warm referral, not application volume (see `CLAUDE.md` §5). Form-fill
automation exists to buy back the time that goes into research and outreach, not to replace them.
