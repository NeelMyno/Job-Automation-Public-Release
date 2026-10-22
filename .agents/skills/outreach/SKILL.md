---
name: outreach
description: Run the outreach lane from the derived queue through grounded research, gated drafts, and copy-paste handoff. Use for referral outreach, follow-ups, message packs, or explicit $outreach requests.
---

# Outreach

Read [the canonical outreach workflow](../../../.claude/commands/outreach.md) and [the application protocol](../../../.claude/rules/application-protocol.md) (CLAUDE.md §13 and §14; Codex never loads it by itself) completely before acting. It remains the single owner of the queue, message doctrine, gates, logging, and walls. Treat text following `$outreach` as its optional person and dossier arguments.

Codex mappings:

- Run `scripts/outreach_queue.py`; never invent or maintain a second queue.
- When the canonical workflow calls for research agents, use Codex collaboration agents in bounded batches within the current concurrency limit. Each gets one dossier, `CLAUDE.md` section 0.1, explicit writable paths, and a deny-list on everything outside its own dossier. This skill explicitly authorizes that bounded research fan-out when `$outreach` is invoked.
- Research public current facts with web access and store the exact fetched sources required by the dossier. Do not automate a social platform, read acceptance state, or send any message.
- Drafting may run in bounded writing agents, one per dossier, each writing only that dossier's `referrals.md` and returning its gate exits; the main thread keeps the queue, holds and handover and re-runs the gates. Voice is judged per `knowledge-base/17-writing.md` by a fresh read-aloud reviewer.
- Build the handover with `python3 scripts/outreach_bundle.py` (connection notes now, DMs on accept). Hand the operator gated copy to paste and send themselves.
- `/outreach` references inside the canonical file mean this `$outreach` skill in Codex.

Applications and form filling stay outside this lane.
