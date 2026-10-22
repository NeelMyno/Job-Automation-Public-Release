# Job Search Engine

An agent-run career engine, supported in Claude Code and Codex. It finds new postings for the roles
you want, turns each job description into a tailored résumé and cover letter, fills the application
form for you to review and submit, preps you for interviews, and drafts warm outreach. **Built for
any role, any industry, anywhere in the US.**

![How the engine works: a one-time setup feeds a knowledge base, which feeds a discovery track and a build track; both converge on a grounding gate that checks this dossier's own content and, in a second row, the repo itself every session; a passing draft reaches one of two points where you, not the agent, click Submit or Send; and ops/ carries session memory across the whole thing.](docs/architecture.svg)

One-time setup, a gate that checks both this dossier and the repo itself, session memory that
carries across a fresh clone's sessions, and two feedback loops that keep the whole thing honest.

New here? Open the repo in Claude Code or Codex and type **`/setup`** (Codex: `$setup`). The agent
asks a few short questions, reads your résumé and sets everything up. [`SETUP.md`](SETUP.md) is the
same path by hand, plus prerequisites and troubleshooting.

## How it works

Everything stands on a **knowledge base** (`knowledge-base/`): a distilled, always-accurate picture
of your profile, experience, projects, career narrative, and work-authorization situation. It ships
**empty**: `/setup` fills it from your résumé and a few answers, and every output after that is
grounded in your real facts instead of a guess. The agent reads that knowledge base before every task.

**Where jobs come from.** Not a fixed list. The crawler reads the public job boards of any company on
Greenhouse, Lever, Ashby, SmartRecruiters, Workable or Workday (the agent finds the companies that
post your titles, using the free Common Crawl index, and adds any company you name), free public job
APIs, and the Hacker News hiring thread. No keys and no logins are needed. Any board or source can
be added. Employers on other systems (iCIMS, Taleo, Oracle, SuccessFactors and the rest) aren't read
directly: the agent finds their postings by web search and still fills the application form.

**Who fills the forms.** The agent does. The repo ships the browser tool it uses (`.mcp.json` for
Claude Code, `.codex/config.toml` for Codex): it fills every field, checks each one in the page,
attaches your résumé and cover letter, and leaves the form open for you to review and click Submit.

The agent operates with the research + reasoning depth of a sharp career advisor (search-first,
self-critical, honest), but with a builder's hands: it edits files, renders documents, and drives a
browser to fill (never submit) real forms. It never touches LinkedIn or your logged-in accounts
(`CLAUDE.md` §0.2): it writes those messages, you send them. See `CLAUDE.md` for the full rules.

## The gates: why this repo can be trusted

Everything an employer sees is checked by a script, not by an agent remembering to be careful.
The diagram above shows the checks a single dossier's résumé, cover letter, and outreach draft
must clear before a human ever sees them. The full repo-wide gate suite is wider than that and
includes the rules, your records and the goal itself, not just one dossier's content. Every script
in `scripts/` ships its own `--selftest`, green out of the box on a fresh clone. The ones you'll run
by hand most often:

```
python3 scripts/doctor.py           # is everything set up? each problem comes with its fix
python3 scripts/verify_claims.py "applications/<company>-<role>"   # outbound copy
python3 scripts/canon.py            # the knowledge base: no retired claim may be asserted
python3 scripts/visa_gate.py        # work-authorization answers (the highest-stakes surface)
python3 scripts/check_law.py        # the rules themselves: one owner per rule, no dangling refs
python3 scripts/throughput.py       # the goal itself: finished work sitting unsent, a dossier
                                    # contradicting itself, commits held back
```

They also run from the harness (`.claude/settings.json`): true state, including every live-interview
next-step, is printed at session start, every file written is checked, and a turn that introduces a
defect is **blocked**.

## Layout

- `CLAUDE.md`: the operating manual the agent reads first. Start here (after `SETUP.md`).
- `SETUP.md`: prerequisites, the by-hand version of `/setup`, and troubleshooting.
- `.codex/`: Codex configuration, lifecycle-hook wiring, and repository command policy. Loads
  `CLAUDE.md` directly rather than duplicating it.
- `.agents/skills/`: Codex adapters for the canonical `/setup`, `/wave`, `/outreach`, and review
  workflows.
- `.mcp.json`: the one browser tool form filling needs (no keys).
- `STRUCTURE.md`: where every file goes and how things are named.
- `knowledge-base/`: canonical knowledge about *you*. `INDEX.md` maps it. Ships empty.
- `scripts/`: the gates above, the session hooks, the account guard, `doctor.py`, and `config.py`
  (your optional settings).
- `.claude/`: the commands (`/setup` to get started, `/wave` for applications, `/outreach` for
  networking), `rules/` (the application protocol and the record formats), the five-pass review
  workflow, and `settings.json` (the hooks).
- `ops/` is this repo's own session record: `STATE.md`, `HANDOFF.md`, `decisions/` (an immutable ADR
  ledger), `log/activity.md`, `notes/`.
- `docs/`: the architecture diagram at the top of this file.
- `applications/`: active per-job dossiers, one folder per job. Copy `TEMPLATE-company-role/` to
  start one.
- `resume/`: your current résumé (source, built PDF, fonts).
- `pipeline/`: the job crawler (`job-crawler/`: crawl, discover, free sources; no keys), the live
  status tracker, and the send ledgers.

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
