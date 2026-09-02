---
name: outreach
description: Run the outreach lane from the derived queue through grounded research, gated drafts, and copy-paste handoff. Use for referral outreach, follow-ups, message packs, or explicit $outreach requests.
---

# Outreach

Read [the canonical outreach workflow](../../../.claude/commands/outreach.md) completely before acting. It remains the single owner of the queue, message doctrine, gates, logging, and walls. Treat text following `$outreach` as its optional person and dossier arguments.

Codex mappings:

- Run `scripts/outreach_queue.py`; never invent or maintain a second queue.
- When the canonical workflow calls for research agents, use Codex collaboration agents in bounded batches within the current concurrency limit. Each gets one dossier, `CLAUDE.md` section 0.1, explicit writable paths, and a deny-list on everything outside its own dossier. This skill explicitly authorizes that bounded research fan-out when `$outreach` is invoked.
- Research public current facts with web access and store the exact fetched sources required by the dossier. Do not automate a social platform, read acceptance state, or send any message.
- Drafting and synthesis remain in the main thread. Hand the operator gated copy to paste and send themselves.
- `/outreach` references inside the canonical file mean this `$outreach` skill in Codex.

Applications and form filling stay outside this lane.
