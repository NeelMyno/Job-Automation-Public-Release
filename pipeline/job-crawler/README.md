# Job crawler

Finds fresh, real job postings for **any role, in any industry, at any company**, the day they go up.
It is not tied to a fixed list of companies or job boards. It searches three kinds of free source and
filters all of them by the same rules (`filters.yaml`):

1. **Company job boards** on six public ATS platforms (Greenhouse, Lever, Ashby, SmartRecruiters,
   Workable, Workday), listed in `boards.yaml`. You don't hand-list these: `discover.py` finds them
   and checks each one live before adding it (see "Finding company boards" below).
2. **Free job APIs**, set up in `sources.yaml` (see "Built-in sources").
3. **Hacker News "Ask HN: Who is hiring?"**, the monthly thread.

**$0. No login. No scraping of any login-walled platform (no account-ban risk).** It reads public
JSON that companies and job sites publish. The only key anywhere is the optional free USAJOBS key,
read from your environment, never from a file.

**ATS coverage, plainly.** `discover.py --sweep` and `--company` find boards on Greenhouse, Lever,
Ashby, SmartRecruiters and Workable. Workday boards are read too, but only after you give
`discover.py --urls` a Workday careers URL. iCIMS, Taleo, Oracle and SuccessFactors are not read
directly, and many employers (hospitals, schools, government, retailers) use systems like those.
For them, search the web: `discover.py --queries` prints the queries, including plain ones such as
"registered nurse jobs columbus" built from your `home_metros`. Any result URL on a supported ATS
can go into `discover.py --urls -`; add the rest as lead rows in `pipeline/tracker.html` and apply
there (the agent fills those forms too). When a crawl finds 3 matches or fewer, its `hints` say
this too.

Also included: **`liveness.py`**, a clean-room ghost-job re-checker. Re-verify a lead is still live
before spending time tailoring or applying to it: `python3 liveness.py --url <URL>` or `--tracker`.
Greenhouse, Lever and Ashby postings are checked against the board's public API (the job id is on
the board or it isn't). SmartRecruiters, Workable, Workday and every other URL get a page check: the
page is fetched and read conservatively, so a closed posting there may come back `uncertain` rather
than `dead`.

## What it is (and isn't)

**Honest by construction:** the crawler and discovery only *select real postings and copy their real
fields*. They never invent, embellish, or rank by anything but the real signal. A board is added to
`boards.yaml` only after its own public API answered with real postings.

## Setup

```
python3 -m pip install -r requirements.txt
```

Then set your role titles in **`filters.yaml` `include_titles`** (any role: "data analyst",
"registered nurse", "mechanical engineer", ...). It ships empty, and `crawl.py` will not run until
it has at least one title; it says so in one sentence. That file also holds optional keyword
boosts, the location gate, and any hard/soft rules of your own (read its comments: what belongs in
`exclude_patterns` vs `flag_patterns` depends entirely on your own situation, so both ship empty).

Then grow your board list (next section). The crawler already works without it: on a fresh clone
with an empty `boards.yaml`, it searches the job APIs and Hacker News and suggests a sweep.

## Finding company boards (`discover.py`)

```
python3 pipeline/job-crawler/discover.py --sweep                       # the default way
python3 pipeline/job-crawler/discover.py --company "Acme" "Globex"     # named companies
python3 pipeline/job-crawler/discover.py --urls - < urls.txt           # any job/careers URLs
python3 pipeline/job-crawler/discover.py --queries                     # web-search queries to run
```

- **`--sweep`** harvests company board names for Greenhouse, Lever, Ashby, SmartRecruiters and
  Workable from the free [Common Crawl](https://index.commoncrawl.org) URL index, then reads each
  board's public API and adds only companies with at least one open posting that matches your
  titles **and** passes your location settings (the same rule `crawl.py` applies, in
  `locations.py`), so a board hiring only abroad, or only onsite somewhere you won't move to, is not
  added.
  **How long it takes.** Each run stops after `--max-minutes` (3 by default; `0` means no limit) and
  the next run continues where it stopped, down to the index page. The first run is the slowest: it
  reads the index before it can check any board, and on a slow day that takes a few 3-minute runs.
  Later runs reuse the harvest and check up to `--limit` boards (150 by default; `--limit` does not
  bound the index harvest, `--max-minutes` does), typically in 1 to 3 minutes, with a few polite
  workers and progress cached under `cache/` (gitignored). When your titles or location settings
  change, boards that had no match are checked again. The Common Crawl index is often overloaded
  (HTTP 5xx): an index domain is skipped for the run after a few failures in a row, and the moment
  that happens the sweep prints what to do instead (`--company "Name"`, or `--queries` then
  `--urls -`), which works without the index.
- **`--company "Name" ...`** guesses each company's board name on the five guessable ATSes, checks
  every guess, adds the hits, and lists the misses. A board whose API names a different company is
  not added. Workday boards can't be guessed (they need tenant, host and site), so use `--urls`.
- **`--urls FILE|-`** takes any text containing job or careers URLs (search results, a pasted list),
  works out the ATS and board for all six ATSes (Workday included), checks the board is live,
  skips ones already listed, and adds the rest. URLs that aren't on a supported ATS are listed.
- **`--queries`** prints web-search queries for your titles (`site:jobs.lever.co "<title>"` and so
  on). Some search tools ignore `site:`, so it also prints plain `"<title>" jobs <company> careers`
  forms (pass `--company` names to get those). Run them, then pipe the result URLs into `--urls -`.

Options: `--dry-run` (show what would be added, change nothing), `--json`, `--limit N`,
`--max-minutes M`,
`--workers N`, `--ats greenhouse,lever`, `--refresh-index`. `python3 discover.py --selftest` runs an
offline check.

Rows discovery adds look like
`- {company: "Acme", ats: greenhouse, slug: "acme", source: "discover:sweep", added: "2026-01-31"}`.
The `source:` field tells them apart from rows you wrote; discovery never edits or removes a row.

## Built-in sources

| Source | On by default | Coverage | Limits the crawler keeps |
|---|---|---|---|
| Company ATS boards (`boards.yaml`) | yes | any company on Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday | one read per board per run |
| Himalayas | yes | remote jobs, title search, `country: US` | one fetch an hour |
| Jobicy | yes | remote jobs, `geo: usa`, keyword tag | one pass an hour (its terms) |
| Remotive | yes | remote jobs (a short list, about 10 recent jobs, unless you set one title) | one call per run, at most every 6 hours (its terms) |
| Remote OK | yes | remote jobs, one recent feed | one fetch an hour |
| USAJOBS | when `USAJOBS_API_KEY` and `USAJOBS_EMAIL` are set | US federal jobs, any occupation | one fetch an hour |
| The Muse | no: its docs ask you to register beyond testing | US onsite and remote | one fetch an hour |
| We Work Remotely | no: its terms have not been read | remote jobs (RSS) | one fetch an hour |
| Hacker News "Who is hiring?" | yes (`--no-hn` to skip) | startups, mixed | one thread a run |

Each job keeps its original link, and the feed names its source on every row and credits the job
sites it used, as their terms ask. Inside a source's minimum interval the crawler does not call it
again; it reuses the jobs from the last good fetch and says so. The feed is for your own use: several
of these terms forbid re-posting the jobs on another site. `sources.yaml` holds each source's terms
summary in comments.

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
python3 pipeline/job-crawler/crawl.py --no-api     # skip the job APIs (boards + HN only)
python3 pipeline/job-crawler/crawl.py --no-hn      # skip Hacker News
python3 pipeline/job-crawler/crawl.py --hide-no-sponsor  # drop "won't sponsor" postings too (default: keep + flag)
```
Or from a Claude Code / Codex session in this repo: `/wave crawl`.

The JSON output always carries a **`sources`** list: every source, whether it ran, was served from
its cache, was skipped or failed, how many jobs it returned and matched, and the reason for any skip.
Read that list before saying what the crawler searched.
It also carries **`dropped`**: how many postings each rule turned away (`title`, `wall`,
`location`, `age`, `no_sponsor_hidden`, each explained in `dropped_reasons`), so a thin run says
which rule removed the rest. When `remote_ok` is false but most jobs came from sources that list remote
jobs only and no company board was read, `hints` says so and points at `discover.py --sweep`.

Outputs (with `--write`):
- **`pipeline/job-feed.md`**: a scannable table of the fresh matches (rewritten each run), with a
  Source column on every row.
- **`pipeline/tracker.html`**: new matches added as deduped `lead` rows (existing rows untouched,
  dedup on the job URL).

**Ranking.** Matches are sorted by keyword hits (`score`, from `include_keywords`), then title
fit (`title_fit`: 3 = the title is exactly one of yours, 2 = contains one as whole words, 1 = part
of a word), then newest. With `include_keywords` empty every score is 0 and only title fit and
freshness rank; the JSON `ranking` field says which applies.

Without `--write`, `crawl.py` prints its matches as JSON to stdout and touches nothing else. This
is useful if you just want the job list and plan to handle the rest yourself (see the companion
crawler-only release of this repo, if that's all you need).

## Files

- `crawl.py`: the crawler (Python stdlib + PyYAML only).
- `discover.py`: finds company boards and adds the checked ones to `boards.yaml`.
- `sources.py` / `sources.yaml`: the free job APIs and their settings. **Turn sources on or off here.**
- `hn.py`: the HN "Who's Hiring" collector, used by `crawl.py`.
- `http_util.py`: the shared URL reader (gzip, retry on a cut-off read).
- `liveness.py` / `test_liveness.py`: the ghost-job re-checker and its offline test suite.
- `test_discover.py`, `test_sources.py`: offline tests for discovery, the job APIs and the crawl
  report. No network.
- `boards.yaml`: company boards (ATS + slug). Filled by `discover.py`; you can add rows by hand.
- `filters.yaml`: your titles, the patterns to drop or flag, and the location gates (`require_us`
  for the region; `remote_ok`, `onsite_ok`, `home_metros` for where you can work).
- `locations.py`: the location rule `crawl.py` and `discover.py` share (`--selftest` runs offline).
- `titles.py`: the title rule `crawl.py` and `discover.py` share. A title term matches as a substring,
  except a term of 3 characters or fewer ("rn", "qa", "pm"), which must be a whole word so it never
  matches inside another word (`--selftest` runs offline).
  **Tune what counts as a match here.**
- `cache/`: local state (fetch times, harvested index, sweep progress). Gitignored; safe to delete.
- `requirements.txt`: the one dependency (PyYAML).

## Add a board or a source

**A board by hand:** open the company's careers page and read the URL, or just paste the URL into
`discover.py --urls -`, which does this for you and checks it.
- `boards.greenhouse.io/<slug>` or `job-boards.greenhouse.io/<slug>` → `ats: greenhouse`
- `jobs.lever.co/<slug>`                     → `ats: lever`
- `jobs.ashbyhq.com/<slug>`                  → `ats: ashby`
- `jobs.smartrecruiters.com/<slug>`          → `ats: smartrecruiters` (slug is case-sensitive)
- `apply.workable.com/<slug>`                → `ats: workable`
- `<tenant>.<host>.myworkdayjobs.com/<site>` → `ats: workday`, slug = `"tenant/host/site"`

A wrong slug is harmless: the crawler skips it and lists it under `errors`. Workday has no "list
everything" mode, so it's queried with your own `include_titles` directly.

**A new job API:** write a `fetch_<name>()` in `sources.py` that returns jobs in the shared shape
(company, title, location, url, posted_at, remote, description, source), register it in `FETCHERS`,
`LABELS`, `HOMEPAGES` and `FLOOR_MINUTES` (the minimum minutes between calls its terms allow), add a
block to `sources.yaml` with its terms summary, and add a fixture to `test_sources.py`. Read the
source's terms first; leave it `enabled: false` if they don't allow personal automated use.

**A new ATS:** add a `from_<ats>()` fetcher in `crawl.py`, a probe and URL pattern in `discover.py`,
and fixtures in its selftest.

## Not covered (yet)

- **iCIMS, Taleo, Oracle, SuccessFactors, Rippling**: not read directly. Find those employers'
  postings with a web search (`discover.py --queries`), pipe any URLs that sit on a supported ATS into
  `discover.py --urls -`, and add the rest as lead rows in `pipeline/tracker.html` to apply there.
  Add a fetcher if a target you care about needs one.
- **LinkedIn, Indeed, Glassdoor**: intentionally excluded. LinkedIn's terms forbid automated
  crawling, and driving any of these job-board accounts with a script risks a ban; you use them by hand.
- **Adzuna, Jooble**: free keys exist, but their US endpoint, limits and terms were not confirmed,
  so they are not built in.
