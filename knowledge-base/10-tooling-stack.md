# Tooling Stack — what powers the crawl and the research

This file is different from most of the knowledge base: it ships **filled in**, not blank. It
documents the engine's own architecture (what already works with zero setup, versus what you could
optionally add), not a fact about you. Edit it whenever you actually add or remove a tool, so it
stays true instead of aspirational.

## The one rule that governs everything (account safety)

Never let automation touch your personal LinkedIn login, or the login of any other personal account,
directly. Concretely: no script or agent should ever type your password into a login form, hold your
session cookie, or click "Connect" / "Send" / "Message" on your behalf through a browser session
that's logged in as you.

Read-only research through a proxy or a public API is fine — looking up a public profile, a company
page, a posting. **Sending, connecting, or posting through automation is not**, no matter how much
time it would save. This is the same logic as the global safety gates the rest of this repo inherits:
entering credentials and sending irreversible external messages are never things an agent does
quietly on your behalf, only things it prepares for you to do, or asks you before doing. If a tool's
setup instructions ask you to hand over your personal LinkedIn password, that tool doesn't belong in
this file.

The one carve-out the rest of this repo already scopes carefully: filling, never submitting, a real
job application form, inside a dedicated browser profile that holds none of your personal logins. See
`CLAUDE.md` §14 for exactly how that's bounded and why it's a different thing from the rule above.

## What this repo already uses, no setup required

The job crawler runs entirely on free, public, keyless JSON APIs — zero keys, zero auth, nothing to
sign up for:

- **Greenhouse, Ashby, and Lever's own public board endpoints.** Most companies using these Applicant
  Tracking Systems expose their open roles as a plain JSON feed, built to be read by software. No key,
  no login.
- **The Hacker News "who's hiring" thread**, pulled through the free public Algolia search API that
  already indexes Hacker News.

That's the whole crawler, out of the box, before you add anything below. See
`pipeline/job-crawler/README.md` for exactly which boards it checks and how to add a new company.

## Optional — deepens research if you add it

Everything below is an option, not a requirement — the crawler and the tailoring engine both work
with none of it. Add a row only once you've actually installed and configured the thing; an entry
here that isn't real yet belongs in "Considered & deferred," not this table.

| Stage | Tool | Why you'd add it | Auth needed |
|---|---|---|---|
| Company/market research | A web-search MCP server | Pulls recent news, funding, and culture context beyond what a JD alone tells you | Usually an API key |
| Finding referral nodes | A people-search tool | Surfaces real names and titles at a target company worth researching before outreach — never a substitute for confirming the person is real | Usually an API key, often paid |
| Rendering the résumé/cover letter | A local HTML-to-PDF renderer | Turns `resume/resume.html` into the actual PDF you attach — see `resume/README.md` for the exact `weasyprint` command this repo uses | None, local install only |

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

- `knowledge-base/12-application-answers.md` — the rule that no tool, however good its research, ever
  gets to type a value that isn't traceable to a knowledge-base file
- `knowledge-base/09-current-search.md` — where a lead the crawler or a research tool surfaces
  actually gets recorded
- `pipeline/job-crawler/README.md` — the crawler this file's second section documents
- `resume/README.md` — the PDF-rendering command referenced in the table above
