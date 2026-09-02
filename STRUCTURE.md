# STRUCTURE — how this repo stays organized (the organization law)

**Read this before you create a file or a folder.** It is the law for humans and for agents. If a
file has no obvious home below, it is not dropped in a folder root — find its home, or ask.

---

## Top-level map

| Folder | What it holds | Touched |
|---|---|---|
| `.codex/` | Codex repository config, lifecycle hooks, and command policy. `CLAUDE.md` remains the instruction owner. | when agent infrastructure changes |
| `.agents/skills/` | Thin Codex workflow adapters. Canonical application/outreach workflow content stays in `.claude/`. | when a workflow is added or its tool mapping changes |
| `knowledge-base/` | Canonical facts about **you** — the distilled, trustworthy layer. Read before any career task. Ships empty. | every session |
| `ops/` | This repo's system of record: `STATE.md` (live status, gitignored), `HANDOFF.md` (session-resume digest — read first when resuming), `log/activity.md` (append-only), `decisions/` (immutable ADRs), `briefs/` `reports/` `notes/`. | every session |
| `applications/` | **Active** per-job dossiers — one folder per job, `<company>-<role>/`. Copy `TEMPLATE-company-role/` to start one. | constantly |
| `resume/` | The current résumé: `resume.html` (source) → the built PDF, `fonts/`. | per application |
| `pipeline/` | Engine output + live SSOT: `tracker.html`, `sent-ledger.md`, `inmail-ledger.md`, `target-list.md`, `job-feed.md`, `job-crawler/`. | when crawling |
| `scripts/` | Repo tooling. `verify_claims.py` is the grounding gate (§0.1 of `CLAUDE.md`) — nothing ships until it exits 0. | rarely |
| `docs/` | This document set — design notes for anything the repo renders (e.g. the tracker dashboard). | rarely |
| root files | `CLAUDE.md` (operating manual, read first), `SETUP.md` (onboarding), `README.md` (human overview), `STRUCTURE.md` (this). | — |

> **Gitignored / transient — real on disk but deliberately not tracked, so not mapped above:**
> `.claude/tmp/` (session scratch), `ops/STATE.md` (live working file), and anything you add to
> `.gitignore` for your own personal working files.

---

## The naming rule (one rule, two earned exceptions)

**Folders and files are kebab-case, semantic, and carry no number prefix.**
`acme-staff-engineer/`, `company-research.md`. No spaces, no `Title Case`, no vague names, no emoji
in names.

The two exceptions, because each earns its scheme:

1. **`knowledge-base/`** keeps its `NN-name.md` numbering — it is a *reading order* (01 identity → 02
   work-auth → …), not an arbitrary bucket. Documented in `knowledge-base/INDEX.md`. Its numbering is
   also load-bearing: `12-application-answers.md`'s internal `§`-sections are read by exact number
   from several scripts — see that file's own header before renumbering it.
2. **`ops/`** keeps its `NNNN-slug.md` sequence per subfolder — a chronological record.

---

## Where does X go? (decision table)

| You have… | It goes in… |
|---|---|
| A durable fact about you (role, date, metric, work-auth, positioning) | the right `knowledge-base/NN-*.md` (+ update its INDEX line) |
| A decision that is now locked | a new ADR in `ops/decisions/` (append-only) + one line in `ops/decisions/INDEX.md` |
| A research dossier, probe, or thinking note | `ops/notes/NNNN-slug.md` |
| A session status update | overwrite `ops/STATE.md`; append ≤5 lines to `ops/log/activity.md` |
| Anything about ONE specific job (JD, tailored résumé, research, referrals, correspondence) | `applications/<company>-<role>/` |
| Crawler output, the tracker, the target list | `pipeline/` |
| A preference or convention you stated | `knowledge-base/11-preferences-and-conventions.md` |
| A temp / scratch / probe file | the session scratchpad, NOT the repo. If it must live here, use **`.claude/tmp/`** — the gitignored path. |
| Codex project configuration, hooks, or command policy | `.codex/` — tracked; keep transient state outside the repo |
| A Codex adapter for an existing workflow | `.agents/skills/<skill-name>/SKILL.md` — point to the canonical owner instead of copying it |

---

## The per-job dossier

`applications/<company>-<role>/` — e.g. `acme-staff-engineer/`. Fixed shape:

- **root:** `README.md` (index + status + apply link + next action), `jd-<slug>.md`, `application.md`,
  `company-research.md`, `referrals.md`, `interview-prep.md`, **`pre-send-check.md`** (required —
  gate rule R8 reads it; the six-item checklist before anything ships).
- `resume/` — the tailored résumé (`resume.html`, the built PDF, **`tailoring.md`** — required, which
  "cards" you played and why — and `review-passes.md`).
- `cover-letter/` — mirrors `resume/`: `cover-note.md` (the sendable note), `cover-letter.html`, the
  rendered PDF. **Mandatory in every bundle — never optional, exactly like the résumé.**
- `sources/` — verbatim page snapshots for every quoted real person; the grounding gate reads these.
- `correspondence/` — evidence of an external event (an email screenshot, a `.eml`, a short note),
  filed as `YYYY-MM-DD-<description>.<ext>`.
- `calls/` — call transcripts.
- **Optional, produced only when the work calls for them (document, never force):**
  `form-answers-paste-kit.md` (a paste-kit route when browser automation is blocked),
  `research-report.md` (a deeper research pass), `referral-<name>.md` + `referral-resumes/`
  (per-referrer tailoring), `video-slides/` (a walkthrough deck).

Loose emails, screenshots, and call notes NEVER sit in the dossier root — they go in
`correspondence/`, `sources/`, or `calls/`.

---

## Keep-it-tidy rules (the standing housekeeping law — `CLAUDE.md` §12)

1. **Every file has a home; nothing loose accumulates in a folder root.**
2. **Supersede → archive or delete, in the same change.** A stale doc beside current work is worse
   than a missing one.
3. **Gitignore what must never publish or bloat git:** secrets (`.env`, `.mcp.json`), `ops/STATE.md`,
   `.DS_Store`, large binaries. Never `git add -A` blind — stage only what belongs.
4. **Leave every folder tidier than you found it.**
5. **Moving or renaming files:** use `git mv` (preserves history). In the SAME commit, grep every live
   reference and update it — `CLAUDE.md`, `scripts/`, `pipeline/tracker.html`, `.claude/`,
   `.gitignore`, live `knowledge-base/`. Leave `ops/notes/`, `ops/log/`, and `ops/decisions/`
   untouched: they are immutable historical snapshots that legitimately name old paths.

---

## For agents specifically

- **Read `CLAUDE.md` §6 and this file before you touch the tree.**
- **Never** drop a loose file in a root, or add a new top-level folder without a reason recorded here.
- **When you rename or move, fix references atomically** (rule 5 above) and confirm the gate still
  runs: `python3 scripts/check_law.py`.
- **When you add a genuinely new kind of thing**, add a row to the decision table here so the next
  agent inherits the rule.
