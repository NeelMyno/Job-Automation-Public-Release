---
name: wave
description: Run the application lane end to end, or its crawl, cover-letter, and form-fill modes. Use when the operator asks to find, rank, prepare, review, fill, or hand over job applications, or explicitly invokes $wave.
---

# Wave

Read [the canonical wave workflow](../../../.claude/commands/wave.md) completely before acting. It remains the single owner of the sequence, walls, gates, and handoff format. Treat the text following `$wave` as the workflow arguments.

Codex mappings:

- When the canonical workflow calls for research agents, use Codex collaboration agents in bounded batches that respect the current concurrency limit. Give each agent one dossier, the Grounding Law from `CLAUDE.md` section 0.1, explicit writable paths, and a deny-list on everything outside its own dossier. This skill explicitly authorizes that bounded research fan-out when `$wave` is invoked.
- Invoke `$application-review` for stage 6. Do not collapse the five independent lenses into one review.
- For form filling, use the `browser:control-in-app-browser` skill and the in-app automation browser. Never use or attach to the operator's main browser profile. Preserve the canonical ATS routing, injection scan, DOM verification, CAPTCHA, credential, and never-submit walls.
- Use `$pdf` or `$documents` when their render-and-verify workflow applies to a generated artifact.
- `/wave` references inside the canonical file mean this `$wave` skill in Codex.

Do not execute outreach in this workflow. Do not mark an application submitted until the operator submits it and the resulting state is observed this turn.
