# SETUP — from a fresh clone to your first application

This repo does nothing useful until you tell it who you are. This document is the whole path from
"I just cloned this" to "the pipeline is running against my own job search." It should take
20-40 minutes for the minimum, more if you fill in the optional depth too.

## 0. What you're setting up

An AI agent (Claude Code or Codex) that reads a `knowledge-base/` of your real facts and uses it to
crawl job boards, tailor résumés and cover letters, research companies, draft outreach, and fill
(never submit) application forms — all checked by scripts, not by the agent remembering to be
careful. See `README.md` for the full picture and `CLAUDE.md` for the operating rules the agent
follows every session.

**Nothing here is specific to any one role, industry, or visa situation.** Every example in this
repo uses a placeholder — you provide the real content.

## 1. Prerequisites

- **Claude Code or Codex**, whichever agent you're using this with.
- **Python 3.9+** with `pip`.
- **`pip install -r pipeline/job-crawler/requirements.txt`** (just PyYAML — the crawler's one
  dependency).
- **`pip install weasyprint`** (renders your résumé/cover-letter HTML to PDF). If you hit a system
  dependency issue, see [weasyprint's install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) —
  it needs a couple of system libraries (Pango, Cairo) on some platforms.
- **Optional, for form-filling only:** `chrome-devtools-mcp` — copy `.mcp.json.example` to
  `.mcp.json` (already gitignored) and keep the `chrome-devtools` entry. It's a public npm package,
  no account needed. You don't need this to draft résumés/cover letters/outreach — only to have the
  agent open and fill a real application form for you to review and submit.

## 2. The four required files (do this first, in order)

Everything else in `knowledge-base/` is optional depth. These four are the true minimum — with just
these filled in, the tailoring engine, every honesty gate, and form autofill all work end to end.

1. **`knowledge-base/01-profile-and-identity.md`** — your name, contact info, education,
   positioning. ~10 minutes.
2. **`knowledge-base/02-work-authorization.md`** — your legal work-eligibility status, in your own
   words. Read the file's own instructions carefully; this is the highest-stakes file in the repo.
   ~10 minutes, more if your situation is complex (talk to an immigration professional if so).
3. **`knowledge-base/07-master-resume.md`** — your résumé content, including the
   `` ```canonical-facts``` `` block (fill in the 4 `exact:` lines with your real contact info; leave
   `never:`/`number:` empty for now, you'll add to them as you go). ~15-20 minutes if you're
   starting from an existing résumé.
4. **`knowledge-base/12-application-answers.md`** — the autofill source of truth. §0-§2 are quick.
   **§3 (work authorization) is the one to slow down on** — it has to exactly match what you wrote
   in file 2, phrased for the three ways forms actually ask. ~10-15 minutes.

**Check your work:**
```
python3 scripts/canon.py            # should exit 0
python3 scripts/resume_gate.py --selftest    # should print SELFTEST OK regardless of your progress
python3 scripts/visa_gate.py        # tells you plainly if §3 isn't filled in yet, or checks it if it is
```

## 3. Fill in your résumé's source file

`resume/resume.html` is a placeholder résumé matching your `knowledge-base/07-master-resume.md`
content. Edit it directly (it's plain HTML/CSS, no build step beyond rendering), or treat KB-07 as
the source of truth and hand-copy from there — whichever you find easier, just keep them in sync.

Render it:
```
weasyprint resume/resume.html resume/your_name_resume.pdf
python3 scripts/resume_gate.py      # must exit 0 — one page, ≥88% filled, current employer listed
```

If it fails on page-fill, you probably need more content, not smaller margins — see
`resume/README.md`.

## 4. Point the crawler at your own search

Two files, both under `pipeline/job-crawler/`:

- **`filters.yaml`** — edit `include_titles` to your own role titles. This is the field that
  actually targets the crawler; everything else in that file is optional refinement. Read the
  file's own comments before touching `exclude_patterns`/`flag_patterns` — what belongs in each
  depends on your own situation, not a universal answer.
- **`boards.yaml`** — add your target companies. Each line needs a company name + which ATS they
  use (Greenhouse/Lever/Ashby) + their board slug — the file's own comments show you how to find
  each company's slug from their careers page URL.

Try it:
```
python3 pipeline/job-crawler/crawl.py --hours 720   # a wide window, so you see something on a fresh setup
```
You should get real, live postings back as JSON. If you get zero, either your window is too narrow,
your `include_titles` don't match how these companies phrase the role, or a board slug is wrong
(check the `errors` array in the output).

## 5. Optional depth (do these as you go, not all at once)

- `knowledge-base/03-career-narrative.md` — your real voice, for cover letters/outreach that sound
  like you.
- `knowledge-base/04-, 05-, 06-` — deeper experience/skills/projects reservoirs the résumé pulls
  from.
- `knowledge-base/08-application-playbook.md` — ships filled in already; read it, don't skip it.
- `knowledge-base/10-tooling-stack.md` — ships mostly filled in; add anything extra you use.
- `knowledge-base/11-preferences-and-conventions.md` — **do this one early**, even briefly: it's
  where you decide things like "should the agent auto-push commits" (see `CLAUDE.md` §10) so the
  agent isn't guessing at your preferences session after session.
- `knowledge-base/13-`, `14-`, `15-` — advanced/optional, useful once the basics are working.

## 6. Run your first wave

From a Claude Code or Codex session in this repo:
```
/wave
```
This runs the full pipeline: rank targets from what the crawler found, research each one, tailor
your résumé and cover letter, run the five-pass review, and open the filled (never submitted) form
for you to check and send. See `.claude/commands/wave.md` for the full procedure, and `CLAUDE.md`
§13-14 for the rules it follows.

For outreach (referrals, follow-ups), run `/outreach` in a **separate** session — the two are kept
deliberately apart (see `CLAUDE.md` §13.8 wall #5 and `.claude/commands/outreach.md`).

## 7. Confirm everything is healthy

```
python3 scripts/verify_claims.py --selftest
python3 scripts/canon.py --selftest
python3 scripts/visa_gate.py --selftest
python3 scripts/check_law.py --selftest
python3 scripts/resume_gate.py --selftest
python3 scripts/voice_check.py --selftest
python3 scripts/subject_check.py --selftest
python3 scripts/outreach_format.py --selftest
python3 scripts/throughput.py --selftest
python3 scripts/injection_scan.py --selftest
python3 scripts/adr_debt.py --selftest
python3 scripts/fill_ready.py --selftest
python3 scripts/presubmit_check.py --selftest
python3 scripts/codex_hook_adapter.py --selftest
python3 scripts/hooks.py --selftest
cd pipeline/job-crawler && python3 test_liveness.py
```
Every one of these should pass on a fresh clone, before you've written a single real fact about
yourself — they're built from fully synthetic fixtures. If one fails on a completely fresh clone,
that's a bug in the repo, not something wrong with your setup.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'yaml'`** → `pip install PyYAML` (or
  `pip install -r pipeline/job-crawler/requirements.txt`).
- **`weasyprint` fails to import or render** → it needs Pango/Cairo/GDK-PixBuf on your system; see
  its install docs linked above. On macOS: `brew install pango`. On Ubuntu/Debian:
  `apt install libpango-1.0-0 libpangocairo-1.0-0`.
- **The crawler returns 0 matches** → widen `--hours`, check your `include_titles` actually match
  how these companies phrase the role, check `boards.yaml` slugs are correct (the JSON output's
  `errors` array names any that failed).
- **`visa_gate.py` says "not filled in yet"** → that's correct behavior, not a bug, until you finish
  `knowledge-base/12-application-answers.md` §3.
- **A gate fails on your real content** → read what it says; every gate here explains exactly what's
  wrong and points at the file to fix, not just a pass/fail.
