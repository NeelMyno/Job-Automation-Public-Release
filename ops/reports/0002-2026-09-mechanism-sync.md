# 0002. Mechanism sync: bringing the public fork current with the private source repo

**Status:** Complete. **Scope:** the whole gate/harness/crawler mechanism, synced from the private
source repo's state at commit `f1982c09` (2026-09-04, the previous sync point) forward to its state
as of this session. **Ask being answered:** does this public fork still reflect the private repo's
current mechanism (the gates, the harness wiring, the crawler), with the same agnosticism guarantee
report 0001 established, given that the private repo has since gone through a substantial hardening
pass?

The private repo's `f1982c09..HEAD` diff was 5,246 insertions across 48 files: 4 brand-new gate
scripts, major rewrites to 12 more, a large `pipeline/tracker.html` expansion, and three new ATS
fetchers in the job crawler. This report records what was ported, what was deliberately left out
(and why), and the verification that closed the pass.

## Method

Eight parallel, file-disjoint workstreams, each briefed with the same genericization contract (no
real names, companies, incidents, or numbers; port mechanism, not data; match this repo's existing
fictional-fixture conventions; no em/en-dashes in authored prose; no commits until everything
verified). One item (`CLAUDE.md`/`.gitignore`, a small judgment-heavy diff) was hand-ported directly
rather than delegated. After all eight landed: a mechanical repo-wide sweep (personal name, real
company names, absolute paths, secrets, em/en-dashes), a full `--selftest` run across every script,
a live integrated `hooks.py --session-start` run, real (non-selftest) runs of `canon.py`/
`check_law.py`/`throughput.py`, and a fresh-context adversarial audit (an agent with no knowledge of
the porting work, told only to find problems) before anything was committed.

## What was ported

- **New gates** (did not exist in this repo before this session): `scripts/seniority_gate.py`
  (flags a JD asking for materially more years of experience than you have),
  `scripts/commitments.py` (an interview `status:` row must carry a dated owed next-step, or it's
  flagged), `scripts/tracker_check.py` (catches a JS-broken `tracker.html` before it ships blank),
  `scripts/batch_voice_check.py` (catches a rinse-and-repeat opener reused across multiple dossiers,
  which a single-file voice check can't see), and `knowledge-base/16-the-senior-gap.md` (a template
  for researching the seniority bar at your own target companies).
- **Rebuilt gates**: `scripts/voice_check.py` (12 register-aware detectors, up from a keyword
  denylist), `scripts/visa_gate.py` (4 real bug fixes: a false-CRITICAL phrasing shape, backwards
  polarity reading on inverted questions, a silently-skipped quoted-wrong-answer, and a markdown-bold
  parsing gap), `scripts/canon.py` and `scripts/verify_claims.py` (assertion-vs-negation parsing
  hardening, a six-shape message-body parser, a fail-closed check for an unparseable message
  section), `scripts/throughput.py` (a dossier-dedup key that no longer collides on a shared login
  wall or generic careers URL, a bidirectional self-contradiction check, an optional live-résumé
  drift check).
- **Harness wiring**: `scripts/hooks.py` now surfaces all 13 selftested gates at session start
  (up from 9), flushes its output incrementally so a timeout can't silently discard it, and sees
  work already committed within the same session. `scripts/adr_debt.py`, `scripts/
  codex_hook_adapter.py`, `scripts/injection_scan.py` each got smaller, real bug fixes.
- **Crawler**: three new ATS fetchers, `from_workday`, `from_smartrecruiters`, `from_workable`,
  added to `pipeline/job-crawler/crawl.py` and verified live against real public boards (Workday
  163 jobs, SmartRecruiters 300, Workable 6). Ported to both this repo and the sibling
  `Job-Automation-Crawler-Module`.
- **Config**: `scripts/config.py` gained `YOUR_YEARS_OF_EXPERIENCE` (read by `seniority_gate.py`)
  and `LIVE_RESUME_URL` (read by `throughput.py`'s drift check), both optional and both no-ops when
  unset, matching this file's existing "everything here is optional" contract.
- **Docs**: `CLAUDE.md`, `README.md`, `SETUP.md`, `.claude/commands/wave.md`, and the crawler's own
  `README.md` updated to describe the current gate count and ATS coverage accurately.

## What was deliberately NOT ported

- `pipeline/tracker.html`'s 1,113-line private-repo diff turned out, on inspection, to be entirely
  new/changed data rows (real applications and contacts), not new schema or rendering code. Nothing
  to port; this repo's `APPLICATIONS`/`NETWORK` arrays remain empty, as designed.
- Every retired-claim registry entry, real company name, real incident, and real session number
  that appeared in the private repo's comments, docstrings, or selftest fixtures was rewritten as a
  generic description of the failure class, or dropped. `scripts/canon.py`'s and `scripts/
  verify_claims.py`'s registries of retired claims remain empty by design, as they were before this
  sync.
- `pipeline/job-crawler/boards.yaml` and `filters.yaml`'s real target-company/role-title data was
  never touched; only their schema documentation (new ATS URL formats) was ported.
- A citizenship-validation feature added to the private repo's `visa_gate.py` on 2026-09-16, after
  the main hardening pass this sync targeted, was deliberately left out: it wasn't part of the
  scoped revamp and would have introduced a new answer category without a corresponding review.
  Worth a deliberate follow-up sync if useful.

## Verification

- All 21 scripts in `scripts/` that ship a `--selftest` pass, run individually, this session.
- `python3 scripts/hooks.py --session-start` runs clean end to end, reporting all 13 gates green.
- `python3 scripts/canon.py`, `python3 scripts/check_law.py`, `python3 scripts/throughput.py`
  (real, non-selftest runs) all exit 0 against this repo's own current state.
- `python3 pipeline/job-crawler/crawl.py --hours 720` runs live in both this repo and
  `Job-Automation-Crawler-Module`, with all three new ATS fetchers confirmed working against real
  public company boards.
- A repo-wide mechanical sweep (personal name, `warp`, `umich`, `/Users/` paths, non-placeholder
  emails) across every file changed this session returned zero hits in both repos.
- A fresh-context adversarial audit (blind to the porting work) read every changed/new file in both
  repos, re-ran every verification above independently, and returned a verdict of **zero blockers,
  safe to push**. It found four minor items, all fixed in this same session: a stale crawler README
  that hadn't caught up to the three new ATS fetchers (fixed in both repos, plus the matching stale
  line in `Job-Automation-Public-Release/SETUP.md` and `Job-Automation-Crawler-Module/README.md`),
  a `hooks.py` advisory display that undercounted visa severity by only counting `[CRITICAL]` and
  missing `[HIGH]` findings (the actual enforcement gate in `stop()` was already correct; only the
  earlier heads-up line was fixed to match), and two dangling `knowledge-base/` references in
  `Job-Automation-Crawler-Module/pipeline/job-crawler/filters.yaml` (that repo ships no
  `knowledge-base/`, since it's crawler-only by design; reworded to not point at a file that doesn't
  exist there).

## Final state at close of this pass

- `Job-Automation-Public-Release`: 29 files changed (7 new), all selftests green, live gates clean,
  adversarial audit passed.
- `Job-Automation-Crawler-Module`: 4 files changed, crawler verified live, adversarial audit passed.
- Both repos committed and pushed to their public GitHub remotes at the close of this session (see
  `ops/log/activity.md` for the commit SHAs).
