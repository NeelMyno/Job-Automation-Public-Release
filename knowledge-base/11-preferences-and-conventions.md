# Preferences & Conventions

This file is where every preference you ever state gets logged, so an agent never has to be told
the same thing twice. `CLAUDE.md` §7 (the record reflex) makes this a standing requirement: if you state a
preference, or make a taste call or a decision, it gets written here in the same session, not left
to live only in that session's chat history. Session context disappears; this file doesn't.

It ships close to empty on purpose. Nobody's preferences transfer to you, so the value here isn't
inherited content, it's the organizing pattern: fixed sections so an agent always knows where to
look, and one running log at the bottom that only ever grows. Fill in the sections below as you
actually form opinions, not all at once on day one.

## Communication

How you like updates from an agent working in this repo: length, format (chat prose versus a
file it hands you), how much it checks in mid-task versus just finishing and reporting back.

[Nothing logged yet. State a preference once, here, and it applies from then on.]

## Résumé writing

The baseline is already set: every number must be real and sourced (`CLAUDE.md` §0.1 and §5), and
every résumé and cover letter gets five independent review passes before you see it (§13.1). This
section is only for anything you would add on top of that default: a personal formatting
preference, or a section you always want kept or dropped. How the lines sound is owned by
`knowledge-base/17-writing.md`.

[Nothing added yet.]

## Writing voice

Not here. How anything you send sounds (cover letters, outreach, form answers, emails, the résumé's
wording, chat replies to you) is owned by one file, `knowledge-base/17-writing.md`. Your voice
samples, your own writing rules and your never-say list all go there, not in this file, so there is
never a second copy to drift out of date.

## Look and feel of what the agent renders

If you have standing preferences for how rendered documents should look (your résumé, cover letters,
anything visual), or a style guide you keep outside this repo, point to it here so an agent loads it
before producing anything visual. If you don't have one, this section stays empty and an agent falls
back to its own general judgment.

[No external style reference recorded yet.]

## Workflow

`CLAUDE.md` §10 asks you to decide two things and record the answer here: whether the agent should
commit locally as it goes, and whether it should push automatically or always ask first. Until you
answer below, the default holds: commit locally, never push without asking. Whatever you choose is
written here word for word, with the date, and the agent follows it.

- **Commits:** [commit locally as I go (recommended) / don't commit] (chosen on: [date])
- **Push:** [ask me first (default) / always / depends on: describe]

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
- `knowledge-base/17-writing.md`: the one owner of how your writing sounds
- `knowledge-base/09-current-search.md`: the file whose update cadence and format your
  Communication preferences above actually govern
