---
name: application-review
description: Run the mandatory five-lens review of a tailored resume and cover letter before employer handoff. Use during $wave stage 6 or whenever an application package needs its required independent review.
---

# Application review

Read [the canonical five-pass workflow](../../../.claude/workflows/application-review.js) completely. The JavaScript is the single owner of the common brief, five lenses, finding schema, truth dial, and synthesis requirements.

Translate its orchestration to Codex without changing its review logic:

1. Resolve `company`, `role`, `jdPath`, `resumeHtml`, `resumePdf`, `coverPath`, and repository root from the active dossier. Stop if a required artifact is missing.
2. Spawn five distinct read-only reviewers, one per `LENSES` entry. Each reviewer receives the canonical `COMMON` brief plus only its own lens and returns the `FINDING_SCHEMA` JSON. Never let a reviewer edit files or cover another lens.
3. Respect the host's concurrency limit. If five cannot run together, run independent batches, preserving five distinct reviewers and lens isolation. This skill explicitly authorizes the review subagents when invoked.
4. The main agent deduplicates, resolves contradictions, preserves every AMBER item verbatim, and produces the canonical synthesis. Two agents agreeing is prioritization signal, never proof; verify load-bearing claims against the named source and rendered artifact yourself.
5. Integrate approved fixes, rerun the relevant gates, inspect the rendered PDF, and write the review record in the dossier's existing `review-passes.md` shape.

Do not silently decide an AMBER item or propose either RED category.
