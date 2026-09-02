# Job crawler

Pulls fresh postings straight from your target companies' public ATS boards (Greenhouse / Lever /
Ashby), the day they post, plus the monthly Hacker News "Ask HN: Who is hiring?" thread.

**$0. No API keys. No login. No scraping of any login-walled platform (no account-ban risk).** It
reads the public ATS JSON that companies already publish for their own careers pages.

Also included: **`liveness.py`**, a clean-room ghost-job re-checker. Re-verify a lead is still
live before spending time tailoring or applying to it. `python3 liveness.py --url <URL>` or
`--tracker`.

## What it is (and isn't)

**Honest by construction:** the crawler only *selects real postings and copies their real
fields*. It never invents, embellishes, ranks by anything but the real signal, or writes a word
that isn't true about a posting.

## Setup

```
pip install -r requirements.txt
```

Then edit the two files that actually target the crawler at your own search:
- **`boards.yaml`**: your target companies (see "Add a company" below).
- **`filters.yaml`**: your role titles (`include_titles`, the field that actually matters),
  optional keyword boosts, and any hard/soft rules of your own (see the comments in that file;
  what belongs in `exclude_patterns` vs `flag_patterns` depends entirely on your own situation,
  so both ship empty).

## Sponsorship / work-authorization: hard walls vs soft flags

`filters.yaml` splits work-authorization-adjacent language into two very different buckets, and
the crawler treats them differently. **This split exists because the right answer depends on your
own situation, not on any universal rule**; see `knowledge-base/02-work-authorization.md` before
deciding what goes where:

- **Soft "won't sponsor" postings can be KEPT and flagged, never dropped**, if a "we don't offer
  sponsorship" line doesn't actually rule you out (e.g. you're already authorized to work without
  needing anything from the employer). The crawler surfaces them and marks them `⚠ no-sponsor` in
  the feed's Flag column. These phrases live in `filters.yaml` under `flag_patterns`, empty by
  default. Pass `--hide-no-sponsor` to exclude them from a run instead.
- **Hard legal walls belong in `exclude_patterns`** if they're genuine dead ends for you: a
  citizenship-only requirement, a clearance you don't hold, an ITAR restriction, whatever actually
  applies to your situation. Empty by default; add your own.

A posting that trips both a wall and a soft flag is dropped (the wall always wins). Don't merge
the two buckets together: the split is what lets each user configure this correctly for
themselves instead of inheriting someone else's answer.

## Use it

```
python3 pipeline/job-crawler/crawl.py --write      # fresh (72h) -> feed + tracker
python3 pipeline/job-crawler/crawl.py              # JSON only, writes nothing
python3 pipeline/job-crawler/crawl.py --hours 168  # widen to a week
python3 pipeline/job-crawler/crawl.py --company acme
python3 pipeline/job-crawler/crawl.py --all        # ignore the time window
python3 pipeline/job-crawler/crawl.py --hide-no-sponsor  # drop "won't sponsor" postings too (default: keep + flag)
```
Or from a Claude Code / Codex session in this repo: `/wave crawl`.

Outputs (with `--write`):
- **`pipeline/job-feed.md`**: a scannable table of the fresh matches (rewritten each run).
- **`pipeline/tracker.html`**: new matches added as deduped `lead` rows (existing rows untouched,
  dedup on the job URL).

Without `--write`, `crawl.py` prints its matches as JSON to stdout and touches nothing else. This
is useful if you just want the job list and plan to handle the rest yourself (see the companion
crawler-only release of this repo, if that's all you need).

## Files

- `crawl.py`: the crawler (Python stdlib + PyYAML only).
- `hn.py`: the HN "Who's Hiring" collector, used by `crawl.py`.
- `liveness.py` / `test_liveness.py`: the ghost-job re-checker and its offline test suite.
- `boards.yaml`: target companies → ATS + slug. **Add companies here.**
- `filters.yaml`: the title cluster to keep, the patterns to drop or flag, and the location gate.
  **Tune what counts as a match here.**
- `requirements.txt`: the one dependency (PyYAML).

## Add a company

Open its careers page and read the URL:
- `boards.greenhouse.io/<slug>` → `ats: greenhouse`
- `jobs.lever.co/<slug>`         → `ats: lever`
- `jobs.ashbyhq.com/<slug>`      → `ats: ashby`

Add one line to `boards.yaml`. A wrong slug is harmless: the crawler skips it and lists it under
`errors`.

## Not covered (yet)

- **Workday / Rippling / SmartRecruiters** boards: the free ATS trio above covers a large share
  of postings; add another provider's fetcher to `crawl.py` if a target you care about needs it.
- **LinkedIn**: intentionally excluded (scraping risks an account ban).
