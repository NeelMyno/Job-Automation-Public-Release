# Application Playbook — the tailoring methodology

This file is different from the rest of the knowledge base: it ships **filled in**, not blank. It's
the *logic* that acts on your facts (in `07-master-resume.md` and elsewhere), not a fact file itself.
Read it, don't skip it — it's what actually makes tailoring happen instead of just having data lying
around. Edit it freely once you've used it a few times and have your own opinions.

## Résumé methodology

- **The two-reader model.** Every résumé is read twice: once by an ATS parser (which cares about
  keyword presence and clean structure, not prose), and once by a human skimming for six seconds.
  Optimize for both — never stuff keywords in a way a human would notice, never write prose so dense
  an ATS parser mis-reads the structure.
- **ATS rules.** Single column. Standard section headings. No tables, text boxes, or graphics in the
  parse path — anything decorative sits outside what a parser reads. Contact info as real text, not
  an image.
- **Length rule.** One page, unless you have 15+ years of directly relevant experience and can fill
  a second page with real substance rather than padding.
- **The bullet formula.** `[Verb] [what you did] [the result, with a real number when you have one]`.
  A bullet with no verb at the start, or no concrete outcome, is a placeholder, not a finished bullet.
- **The defendability rule.** Every claim on the résumé should survive an interviewer asking "tell me
  more about that" in real detail. If it wouldn't, it's a stretch — flag it, don't ship it (see the
  truth dial in `CLAUDE.md` §13.2).

## The four tailoring dials

You have a **fixed reservoir** of real experience (in `04-experience-detail.md`,
`06-projects-portfolio.md`, `05-skills-competencies.md`) and exactly **four dials** to turn per
application — never invent new content, only select and reframe what's real:

1. **Emphasis** — which 3-4 bullets, out of everything true, lead the page for this specific JD.
2. **Vocabulary** — borrowing the JD's own terms for work you genuinely did (not padding with terms
   for work you didn't do).
3. **Ordering** — which employer/project sits first when you have more than one strong candidate.
4. **Omission** — real work that doesn't serve this particular application gets left off, not forced
   in. A résumé that tries to be relevant to everyone is compelling to no one.

Worked example of the shape (write your own once you have real applications going through this):
tailoring for a role that emphasizes "cross-functional leadership" means pulling your most
collaborative project to the top bullet, not fabricating a leadership title you never held.

## Cover-letter methodology

A five-step shape, each step doing one job:

1. **JD-matched open.** The first sentence should make it obvious you read *this* posting, not a
   generic one — reference something specific from it.
2. **An earned opinion.** One sentence that shows you've actually thought about their product/space,
   not just that you want a job.
3. **1-2 real builds**, mapped directly to what the JD is actually asking for.
4. **A live artifact link**, if you have one relevant to the role.
5. **A close** that names the action you want (an interview, a conversation) without begging for it.

**Honesty wall:** no work-authorization claims in the letter body, ever — that belongs on the form,
not in prose (`CLAUDE.md` §14 rule 2). **Voice:** run every draft through `scripts/voice_check.py`
before it ships. **Deliverable:** `applications/<company>-<role>/cover-letter/cover-note.md` →
rendered to `cover-letter.html` → rendered to the PDF.

## JD scanner — five checks before you tailor anything

1. **Go/no-go gates.** Does the posting rule you out on something genuinely non-negotiable (location,
   clearance, a hard skill you don't have at all)? Check this before spending an hour tailoring.
2. **Work-authorization/sponsorship posture.** What does the posting say, if anything? Cross-check
   against `02-work-authorization.md`.
3. **Start-date fit.** Does the posting name a start date that conflicts with your own?
4. **Keyword extraction, four buckets:** must-have skills, nice-to-have skills, tools/platforms
   named, and culture/values language (useful for the cover letter, not the résumé).
5. **The honest fit read.** After the above, write one sentence: is this a strong, medium, or weak
   fit — and why? This becomes the dossier's `README.md` "why strong" line.

## Pre-send lint — a running list of past mistakes never to repeat

<!-- Start this list empty. Every time you (or an agent) catch a real mistake before it ships, add
one line here. This is how a one-time correction becomes a permanent habit instead of a thing you
have to remember to check for manually. -->

- [ ]

## Interview prep framework

- **Anchor stories.** Map your real STAR stories (`15-interview-story-bank.md`) to the questions a
  role is likely to ask, before the interview, not during it.
- **The "why this company" four-beat.** What they build → why it matters to you specifically → what
  you'd bring → what you want to learn from them.
- **A rehearsed strength/weakness answer** that's honest, not a humble-brag ("my weakness is I care
  too much").
- **A signature technique or story** you can reach for when a question doesn't map cleanly to
  anything you prepared.
- **A close-the-loop follow-up sequence:** a specific plan for what you send after the interview and
  when.

## Open items

<!-- Anything about this methodology you're still figuring out for yourself. -->

## Related

- `knowledge-base/07-master-resume.md` — what gets tailored
- `knowledge-base/09-current-search.md` — the live context this methodology is currently applied to
- `.claude/workflows/application-review.js` — the five-pass review that checks the result
