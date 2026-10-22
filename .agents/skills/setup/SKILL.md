---
name: setup
description: First-run setup, led by the agent. Use when the operator has just cloned the repo, asks to set it up or get started, the knowledge base is still the empty template, scripts/doctor.py reports blockers, or the operator explicitly invokes $setup.
---

# Setup

Read [the canonical setup workflow](../../../.claude/commands/setup.md) completely before acting. It remains the single owner of the questions, the order, the walls, and the done bar. Treat the text following `$setup` as the workflow arguments.

Codex mappings:

- `/setup` references inside the canonical file mean this `$setup` skill in Codex, and `/wave` means `$wave`.
- The browser tool is the `[mcp_servers.chrome-devtools]` table in `.codex/config.toml`. Codex reads that file only for a trusted project. If `python3 scripts/doctor.py --fill` reports the browser tool missing, give the operator its printed Codex steps (trust the project, or `codex mcp add chrome-devtools -- npx -y chrome-devtools-mcp@1.10.1`) and confirm the server appears after the session restarts. Never use or attach to the operator's main browser profile.
- Read the operator's résumé with your own file tools; use `$pdf` or `$documents` when the file is a PDF or Word document and plain reading fails.
- Ask for approval before installing Python packages, exactly as the canonical file says.

Do not run `$wave` or `$outreach` from inside this skill. End by offering `$wave`.
