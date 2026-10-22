# Tooling Stack: what powers the crawl and the research

This file is different from most of the knowledge base: it ships **filled in**, not blank. It
documents the engine's own architecture (what already works with zero setup, versus what you could
optionally add), not a fact about you. Edit it whenever you actually add or remove a tool, so it
stays true instead of aspirational.

## The one rule that governs everything (account safety)

`CLAUDE.md` §0.2 (the Account Law) owns this rule; this is what it means for tools. No agent, script
or tool in this repo touches LinkedIn by any route: no browser, no page read, no fetch, no proxy, no
scraper, not even one "read-only" page. No agent drives your other logged-in major accounts (email,
social, job-board accounts that ban automation) in any browser either. Logged-out public web search
and the official command-line tools you set up yourself, at normal volume, are fine. If a tool's
setup asks for your LinkedIn password or session, or offers to read LinkedIn for you, it doesn't
belong in this file.

The one carve-out: filling, never submitting, a public job application form (Greenhouse, Lever,
Ashby, Workable, SmartRecruiters, a Workday form you sign into yourself), in the browser tool's own
separate window. `.claude/rules/application-protocol.md` §14 bounds it.

## What this repo already uses, no setup required

The job crawler (`pipeline/job-crawler/`) is free and needs no login. It is **not a fixed list of
boards or sources**: the agent adds company boards and switches sources on as your search needs
them, and the latest crawl's own JSON `sources` list is the only true answer to "what did it
search". The crawler reads three kinds of source, and the agent's web search adds a fourth:

1. **Company job boards on six applicant tracking systems (ATSes)**: Greenhouse, Lever, Ashby,
   SmartRecruiters, Workable and Workday, each through its own public JSON endpoint. The boards live
   in `boards.yaml`, and `discover.py` fills it:
   - `--sweep` finds companies on the first five ATSes in the free Common Crawl URL index and keeps
     only those with open postings matching your titles;
   - `--company "Name"` guesses and checks a named company's board on those five;
   - `--urls -` takes any job or careers links (all six ATSes, Workday included) and adds the live
     boards;
   - `--queries` prints web-search queries for your titles; the agent runs them and pipes the
     result links into `--urls -`.
2. **Free job APIs** in `sources.yaml`. On by default: Himalayas, Jobicy, Remotive, Remote OK
   (remote jobs). On once you set a free key in your environment: USAJOBS (US federal jobs).
   Off by default: The Muse (its docs ask for registration beyond testing) and We Work Remotely
   (its terms haven't been read). Each source keeps the minimum interval its own terms ask for.
3. **The monthly Hacker News "Who is hiring?" thread**, through the free public Algolia API.

**Coverage, plainly.** Workday boards can't be guessed, so they come in only through `--urls`
links. iCIMS, Taleo, Oracle, SuccessFactors and other systems are not read directly. For an employer
on one of those, the agent finds the posting by web search, adds it to `pipeline/tracker.html` as an
APPLICATIONS `lead` row (shape: `.claude/rules/records-format.md` §1), ranks it with the crawled
jobs, and still fills that employer's application form for you. In many fields (healthcare,
teaching, trades, retail, government, local employers) most postings sit on those systems, and the
free feeds above are mostly remote jobs, heavy on tech. So web search ("<title> jobs <city>", the
employers' own career pages) is a fourth source in its own right, not a fallback. `pipeline/job-crawler/README.md` has the full detail and how to add a new
ATS or source.

## Optional: deepens research if you add it

Everything below is an option, not a requirement; the crawler and the tailoring engine both work
with none of it. Add a row only once you've actually installed and configured the thing; an entry
here that isn't real yet belongs in "Considered & deferred," not this table.

| Stage | Tool | Why you'd add it | Auth needed |
|---|---|---|---|
| Company/market research | A web-search MCP server | Pulls recent news, funding, and culture context beyond what a JD alone tells you | Usually an API key |
| Finding referral nodes | A people-search tool | Surfaces real names and titles at a target company worth researching before outreach, though never a substitute for confirming the person is real | Usually an API key, often paid |
| Rendering the résumé/cover letter | A local HTML-to-PDF renderer | Turns `resume/resume.html` into the actual PDF you attach; see `resume/README.md` for the exact `weasyprint` command this repo uses | None, local install only |

## Considered & deferred

<!-- Start this empty. Every time you look at a tool and decide not to add it, log one line here:
what it was, and why you passed. That turns a one-time evaluation into a permanent record, so a
future session doesn't burn an hour re-researching the same option. -->

- [ ]

## Install scope

This file describes what's *possible*, not what's *installed*. Keep those two facts from blurring
together, or a fresh session will assume a tool exists that was only ever discussed here. Before
relying on anything from the table above, confirm it's real: check for its entry in your MCP config,
or run it and see if it actually resolves.

| Tool | Actually installed? | Config lives at |
|---|---|---|
| [ ] | [ ] | [ ] |

## Related

- `knowledge-base/12-application-answers.md`: the rule that no tool, however good its research, ever
  gets to type a value that isn't traceable to a knowledge-base file
- `knowledge-base/09-current-search.md`: where a lead the crawler or a research tool surfaces
  actually gets recorded
- `pipeline/job-crawler/README.md`: the crawler this file's second section documents
- `resume/README.md`: the PDF-rendering command referenced in the table above
