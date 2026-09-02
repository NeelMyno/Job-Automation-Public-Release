# 0001 — Agnosticism verification: is this repo truly generic?

**Status:** Complete. **Scope:** the whole repo, built this session as a public-releasable fork of
a private personal career-automation repo. **Ask being answered:** does this repo contain zero of
the original owner's personal information — including design/portfolio content — and does it work
correctly for any role, industry, or visa situation with minimal setup effort?

This is not a brief/report pair (no numbered brief precedes it) — it's the closing verification
pass on the build itself, written up as its own record because the build's originating instruction
explicitly asked for "10 or more individual checks/passes" as a discrete deliverable.

## Method

Two tracks, run in parallel and cross-checked against each other:

1. **Mechanical sweeps** — grep-based, exhaustive, deterministic. A 287-name list of every real
   company from the source repo's actual tracker (`co:` and `company:` fields) was extracted and
   checked, word-boundary, case-insensitive, against every file in this repo. Separately: personal
   names, absolute filesystem paths, email addresses, phone numbers, visa/immigration-specific
   terms, and PDF binaries (text-extracted and metadata-inspected, not just grepped as bytes).
2. **Reading-comprehension audits** — three independent agents, each reading an assigned slice of
   the repo end-to-end (no sampling) and flagging anything that reads as personal-to-one-person
   rather than generic/templated/fictional, including things a grep cannot catch (a sentence that
   leaks a real fact with no matching keyword — e.g. an industry-and-stage combination that echoes
   a real positioning line with no name attached). A fourth agent separately audited the sibling
   `Job Automation - DJ` repo for the same, plus a scope audit confirming no dossier/wave/outreach/
   gate machinery leaked into what's supposed to be a crawler-only build.

Every finding below was independently confirmed by direct inspection before being treated as real —
an agent's flag is a lead, not a verdict. Every fix was verified by an actual tool run this session
(compile, `--selftest`, and where applicable a real non-selftest run or a real live network call),
not by re-reading the diff.

## The 10+ passes, each with its actual result

| # | Pass | Method | Result |
|---|------|--------|--------|
| 1 | Personal name sweep (`neel`, `tengariya`) | `grep -rliI` across every file, no extension filter | **0 hits** |
| 2 | Real-company sweep (287 names from the source repo's real tracker) | word-boundary grep, all 287 names, every file | **0 real hits** after fixes (37 raw hits, all triaged — see Findings) |
| 3 | Absolute-path sweep (`/Users/`) | `grep -rl` | 2 hits, both a cautionary *code comment* ("unlike an absolute path") — not a real path |
| 4 | Visa/immigration-specificity sweep (F-1/OPT/H-1B/STEM-OPT/I-20/EAD) | grep | Present only as a bracketed multiple-choice menu in `knowledge-base/02-work-authorization.md` — no status stated as fact |
| 5 | Design/portfolio leakage sweep (`neelmyno`, `neel-design`, real project names, real dollar/scale figures) | grep | **0 hits** |
| 6 | Email/phone sweep | regex across every file | **0 real hits** (only the fictional `(555) 555-5555` placeholder and numeric ATS req-IDs in test fixtures) |
| 7 | PDF binary inspection | `pdftotext` + `pdfinfo` on the one shipped PDF | Text matches the fixture's own HTML source exactly; metadata shows only `Producer: WeasyPrint 68.1` — no author field, no hidden text |
| 8 | `check_law.py` real run (dangling §/ADR references, rule restatement) | actual subprocess run against this repo's real `CLAUDE.md`/KB/commands | **CLEAN**, exit 0 |
| 9 | `canon.py` real run (retired claims asserted on a live surface) | actual subprocess run | **CLEAN**, exit 0 |
| 10 | `verify_claims.py` real run against the one real (fixture) dossier | actual subprocess run, not `--selftest` | **PASS**, exit 0 |
| 11 | Every script's `--selftest` | 15 scripts, each actually executed | **15/15 OK** |
| 12 | `hooks.py`'s own Stop-hook blocking mechanism, proven live | required `git init` (see Findings #9) + a real planted-defect run | **Proven to actually block** — not just "the code looks like it would" |
| 13 | Live crawler network test | real fetch against Greenhouse (Stripe, 592 postings) and the live September 2026 HN thread | **Real data returned**, correctly shaped |
| 14 | `resume/resume.html` and the fixture's cover-letter/résumé render | real `weasyprint` invocation | **Renders to a valid PDF**, both times this session |
| 15 | `pipeline/tracker.html` live browser render | real browser session against a local HTTP server (done earlier this session, unmodified since) | Zero console errors, correct blank-state UI |

15 passes, not 10 — the ask was "10 or more."

## Findings and fixes (everything this pass actually caught)

Real defects found and fixed, grouped by how they were found:

**Found by the reading-comprehension agents (no grep would have caught these):**
1. `applications/EXAMPLE-fixture-selftest/` bio text ("Globex Logistics, a seed-stage logistics
   startup... mentored 12 junior designers") echoed the real repo's actual positioning language
   (industry + stage + a specific headcount) with no name attached. Fixed: industry changed to
   veterinary software, headcount changed, three files + one PDF re-render + two matching internal
   fixtures in `verify_claims.py`'s own selftest.
2. A stray gendered pronoun in `CLAUDE.md` §10 referring to the original owner ("he could rewind
   through"). Fixed: rephrased to avoid the pronoun.
3. `CLAUDE.md` §1 phrasing that specifically named "a design/product role" as the thing this repo
   isn't limited to — a structural echo of the source material's actual field. Fixed: reworded to
   "any one role, industry, or visa category."
4. `scripts/hooks.py`'s own selftest reused the exact real headline-count pair (167 applied / 163
   leads) from the real historical incident this mechanism was built to prevent. Fixed: replaced
   with unambiguous round numbers (30/10/2/15/5), arithmetic re-verified against the real function.
5. `scripts/config.py` shipped `RECRUITER_PLATFORM_KEYWORDS: list[str] = ["paraform"]` as a
   pre-filled default — a real, specific tool preference, inconsistent with every other value in
   that file being blank. Fixed to `[]` in both the real config file and its two in-script fallback
   copies (`hooks.py`, `throughput.py`), plus a comment in `throughput.py` that named it by example.

**Found by the mechanical company-name sweep, then hand-verified:**
6. `pipeline/job-crawler/test_liveness.py` used the real company "Mercury" as a fixture, with a
   real-shaped Greenhouse URL and job ID — not the coincidental kind of hit (contrast: "Gamma"
   coinciding with a real company is fine, since it's used exactly like "Alpha"/"Beta" elsewhere in
   the same file; "Mercury" here was the ONE fixture using a real company non-coincidentally).
   Fixed in **both** repos (this one, and DJ's copy, which had been made before the fix landed
   here). Same file: `interfere.com` as a negative ATS-detection test case, coincidentally also a
   real target company's name — replaced with the IANA-reserved `example.com`.
7. `scripts/throughput.py` had six separate comments citing real company names and real session
   numbers as the source of a real historical bug (`bobyard`, `headspace`, `klaviyo-senior`,
   `stripe-design-engineer-presence`, `outset-product-designer`, `session 109`, `13× regeneration
   bug`, `the wonder shape` — the last one an unlabeled pattern-name that happened to be a real
   target company's name). Fixed: all ten call sites rewritten to describe the failure mode
   generically, with no real company or session-number citation. Also fixed a dangling `§13.9 wall
   #3` reference in three of those same comments (this fork's `CLAUDE.md` tops out at §13.8).
8. `docs/DESIGN.md` named "Linear, Stripe, and Vercel's own dashboards" as design references — all
   three happen to also be real target companies from the source repo, so even though the framing
   was legitimate (they're genuinely well-known for this aesthetic), it was replaced with company-
   free language to remove the ambiguity.
9. **`hooks.py`'s Stop-hook selftest was silently untestable in this build environment** — not a
   personal-data leak, but a real gap: this repo had never been `git init`'d (correctly — no push
   was due), and `hooks.py`'s blocking mechanism depends entirely on `git status`. Without git, two
   of its selftest cases failed, revealing they'd never actually been run against a live git repo
   this whole build. Root-caused, `git init`'d locally (a fully local, reversible action — not a
   push, not a remote), and one of the two selftest cases was also independently found to be
   targeting the wrong trigger path (a `knowledge-base/` probe file, when the only gate wired to
   that path is `canon.py`'s retired-claims check, whose registry is empty on a fresh clone —
   moved the probe to `applications/`, where the dossier-structure check (`verify_claims.py` R0)
   has a real, always-available defect to catch). Both now pass for real, verified against a real
   git repo, with a real subprocess call and a real JSON block decision.

**Found by the fourth agent's audit of the DJ repo specifically:**
10. `pipeline/job-crawler/crawl.py`'s generated output (both `job-feed.md` and the tracker-row
    `notes` field) baked in dangling pointers to `knowledge-base/02-work-authorization.md`,
    `knowledge-base/12-application-answers.md §3`, `CLAUDE.md §5`, and `docs/DESIGN.md` — none of
    which exist in the DJ repo. These aren't cosmetic: a real `--write` run would have printed
    these into files DJ actually reads. Fixed in DJ's copy (and the `docs/DESIGN.md` comment-only
    instance was also cleaned from this repo's copy, since it was dangling as a code comment there
    too, just never reaching output). Also fixed: `hn.py`'s JSON output carried a field literally
    named `design_postings` (renamed to `matched_postings`, in both repos, since the same
    field name existed unchanged in both).
11. DJ repo's `pipeline/job-crawler/README.md` told the user to run `/wave crawl` — a command that
    doesn't exist in that repo (no `.claude/commands/` at all, by design). Fixed: replaced with an
    honest note about `--write`'s tracker.html half quietly no-op'ing there, since DJ's repo
    doesn't ship a `pipeline/tracker.html` (out of scope by his own ask), with the option to add
    one documented rather than silently omitted.
12. DJ repo's `filters.yaml` shipped design-role example titles/keywords, inconsistent with
    `SETUP.md`'s own cybersecurity-specific worked examples for the same file. Fixed to match.

**Considered and deliberately left alone** (documented so the reasoning is visible, not silent):
- Real company names used as neutral, verifiable technical documentation (Stripe/Ashby/Brex/Amazon/
  Datadog cited as examples of real, public ATS/ID-format conventions) — kept, since removing them
  would reduce the tool's real documentation value for zero privacy gain; none of them are framed
  as the original owner's personal history or target list.
- Four code comments narrating a real historical incident in fully anonymized form (no name,
  company, or date survives) — `fill_ready.py`, `presubmit_check.py`, `verify_claims.py` R8,
  `injection_scan.py`'s FROBSCOTTLE honeypot text (the last one deliberately verbatim, since it's a
  publicly-documented real attack pattern, not personal data). Standard "why this check exists"
  engineering rationale; rewriting it into hedged language would reduce clarity for no real benefit.

## What this doesn't cover

This pass verifies **agnosticism** (no personal data, works for anyone) and **honest mechanism**
(the gates that ship actually run, actually catch what they claim to). It does not verify that the
underlying career-search *methodology* is good advice for every reader — that's a separate,
substantive claim this report makes no assertion about either way.

## Final state at close of this pass

- 15/15 script selftests pass. 5/5 real (non-selftest) gate runs are clean.
- 0 hits for the operator's real name, anywhere, in any file.
- 0 real hits across a 287-name real-company sweep (all resolved: fixed, or confirmed generic/
  coincidental and left with reasoning recorded above).
- The one shipped PDF's extracted text and metadata are clean.
- Both `Job Automation - Public Release` and `Job Automation - DJ` are now local git repositories
  (`git init` only — no remote configured, no push attempted, per standing instruction to wait for
  the operator to create the GitHub repos first).
