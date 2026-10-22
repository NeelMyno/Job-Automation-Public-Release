---
name: wave
description: Run the application lane end to end, or its crawl, cover-letter, and form-fill modes. Use when the operator asks to find, rank, prepare, review, fill, or hand over job applications, or explicitly invokes $wave.
---

# Wave

Read [the canonical wave workflow](../../../.claude/commands/wave.md) and [the application protocol](../../../.claude/rules/application-protocol.md) (CLAUDE.md §13 and §14; Codex never loads it by itself) completely before acting. It remains the single owner of the sequence, walls, gates, and handoff format. Treat the text following `$wave` as the workflow arguments.

Codex mappings:

- When the canonical workflow calls for research agents, use Codex collaboration agents in bounded batches that respect the current concurrency limit. Give each agent one dossier, the Grounding Law from `CLAUDE.md` section 0.1, explicit writable paths, and a deny-list on everything outside its own dossier. This skill explicitly authorizes that bounded research fan-out when `$wave` is invoked.
- Invoke `$application-review` for stage 6. Do not collapse the five independent lenses into one review.
- If the knowledge base is still the empty template (the workflow's step 0a check), stop and offer `$setup` (the Codex form of `/setup`) instead of running the pipeline.
- For the crawl stage, run `discover.py --sweep`, then `--queries` with Codex web search feeding every result URL back through `discover.py --urls -`, and `--company` for any company the operator names, before `crawl.py --write`. Report the sources and counts from the crawl's own JSON, never a fixed list, and tell the operator any company or board can be added. Add each live posting found by web search that the crawler did not return (iCIMS, Taleo, a hospital or government careers site, and the like) as a tracker `lead` row per the canonical step 1, rank it with the rest, and fill that employer's form like any other. A thin crawl usually means the employers post elsewhere, so search wider ("<title> jobs <city>", employer career pages).
- For form filling, the agent fills the form. Start with `python3 scripts/doctor.py --fill` and use the first available browser automation tool in the canonical order (`chrome-devtools-mcp` from the repo's `.mcp.json`, Playwright MCP, Claude in Chrome, then any other browser tool your session has). Never use or attach to the operator's own logged-in browser profile unless they choose it. If none is available, give the steps `doctor.py --fill` prints under "If your tool list has no browser tool" (for Codex: trust the project, or `codex mcp add chrome-devtools -- npx -y chrome-devtools-mcp@1.10.1`, then restart) and stop at the form; once the session restarts, fill it. Never ask the operator to fill the form by hand. A green `doctor.py --fill` does not prove the tool is loaded; check your own tool list. Preserve the canonical ATS routing, paste-kit-only-for-a-named-reason rule, injection scan, DOM verification, CAPTCHA, credential, and never-submit walls.
- When a pre-fill gate refuses, say exactly what to fix, offer to fix it, and re-run it.
- Use `$pdf` or `$documents` when their render-and-verify workflow applies to a generated artifact.
- `/wave` references inside the canonical file mean this `$wave` skill in Codex.

Do not execute outreach in this workflow. Do not mark an application submitted until the operator submits it and the resulting state is observed this turn.
