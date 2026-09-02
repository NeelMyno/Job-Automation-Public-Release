# Preferences & Conventions

This file is where every preference you ever state gets logged, so an agent never has to be told
the same thing twice. `CLAUDE.md` §7 rule 5 makes this a standing requirement: if you state a
preference, or make a taste call or a decision, it gets written here in the same session, not left
to live only in that session's chat history. Session context disappears; this file doesn't.

It ships close to empty on purpose. Nobody's preferences transfer to you, so the value here isn't
inherited content, it's the organizing pattern: fixed sections so an agent always knows where to
look, and one running log at the bottom that only ever grows. Fill in the sections below as you
actually form opinions, not all at once on day one.

## Communication

How you like updates from an agent working in this repo: length, tone, format (chat prose versus a
file it hands you), how much it checks in mid-task versus just finishing and reporting back.

[Nothing logged yet. State a preference once, here, and it applies from then on.]

## Résumé writing

The baseline is already set: every number must be real and sourced (`CLAUDE.md` §0.1 and §5), and
every résumé and cover letter gets five independent review passes before you see it (§13.1). This
section is only for anything you would add on top of that default: a personal formatting
preference, a section you always want kept or dropped, a tone note specific to your field.

[Nothing added yet.]

## Cover letters & outreach voice

The voice rules (plain, no em-dashes, no rule-of-three, the rest of the banned-tells list) live in
`CLAUDE.md` §11 and apply to everything written on your behalf. This section is for what makes your
own voice sound like you specifically: 2-3 real quirks, a phrase you actually use, a rhythm you
naturally write in, something a friend would recognize as sounding like you.

[Nothing logged yet.]

## Design & UI

If you keep a design-taste doc, a moodboard, or standing design instructions somewhere outside this
repo, point to it here so an agent knows to load it before producing anything visual: a portfolio
page, a rendered résumé, a dashboard. If you don't have one, this section stays empty and an agent
falls back to its own general design judgment.

[No external design reference recorded yet.]

## Workflow

`CLAUDE.md` §10 asks you to decide two things and record the answer here: whether the agent should
commit automatically after each milestone, and whether it should push automatically or always ask
first. Until you answer below, the safe default holds: commit locally, never push without asking.

- **Auto-commit:** [yes / no]
- **Auto-push:** [always / ask me first / depends on: describe]

## Ratified decisions & taste-call log

This is the spine of the file. Every time you make a real call an agent should remember, whether
it's a locked decision or just a taste preference, it gets one row here. Append-only: add new rows,
don't edit or delete old ones. If a later decision supersedes an earlier one, add a new row that
says so instead of rewriting history.

| Date | Decision | Why |
|---|---|---|
| 2026-01-15 | **[EXAMPLE, keep or delete]** Never use a two-column résumé layout, even if a template defaults to it | An ATS parser reads two columns out of order, and a recruiter screen reads a wall of text that looks generic |

## Related

- `knowledge-base/INDEX.md`: the map this file is part of, and the other required files it points
  to
- `knowledge-base/01-profile-and-identity.md`: where facts about you live, as opposed to
  preferences about how those facts get used
- `knowledge-base/09-current-search.md`: the file whose update cadence and format your
  Communication preferences above actually govern
