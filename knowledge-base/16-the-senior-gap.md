<!--
Optional and advanced, like 13 and 14. Do this once you have a real portfolio and a few real
applications behind you, and revisit it only when something real changes (a new target company, a
new project, a year of experience gained). It is a research method, not a running fact file.

This file exists because a very common self-diagnosis is wrong in a specific, fixable way: "my
portfolio must read as junior, because I keep failing to clear interviews at senior-level
companies." Often the real story is smaller and much easier to fix than that: the person is a
year or two under a stated years-of-experience floor (a filter, not a quality verdict), and
separately, their case studies describe what they built without ever arguing for what they
decided. Two different problems, two different fixes, and conflating them wastes months solving
the wrong one. Work through the method below with your own targets and your own portfolio before
concluding which problem (if either) you actually have. Delete this comment block once you've run
it for real.
-->

# The Senior Gap: figuring out where you actually sit

## The mistake this file exists to prevent

A "senior" title at a given company is set by two different things that are easy to mistake for
each other: a **years-of-experience filter** (a number on the req), and a **quality bar** (what
the portfolio and the interview loop actually grade). Getting rejected can mean either one, and
they call for completely different responses. If it's the filter, the fix is patience, a referral
that overrides the filter, or a role at a company whose floor you already clear. If it's the bar,
the fix is the work itself: sharper case studies, stronger craft, a better-rehearsed interview. Do
not guess which one you're facing. Research both, separately, before you decide what to fix.

## The method

### 1. Build your own ladder table

For each company you actually care about, find out, from their own live postings (not a summary,
not a rumor): the senior-equivalent title, its stated years floor if one is published, and whether
the same title is posted at more than one band (a "Product Designer" req asking for 4+ years and a
different "Product Designer" req at the same company asking for 6+ years are not the same job, even
with an identical title). A third-party leveling site can help you map a title to a level once you
have the real posting in hand, but the posting is the primary source, not the site.

| Company | Senior-equivalent title | Stated years floor | Multiple bands under one title? | Source (URL + date) |
|---|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] | [ ] |

**Two traps to watch for while you do this:**
- **Don't read the responsibilities bullets to infer level.** Postings for adjacent levels at the
  same company often reuse nearly identical bullets. The band, and the language describing
  ambiguity and scope ("navigate complex, ambiguous problems," "mentor other designers"), are the
  more reliable tells than the day-to-day duties.
- **Check for a mid-level rung you might be skipping past.** It's easy to survey a set of postings,
  notice zero junior/entry-level openings, and conclude the only door in is "senior or nothing."
  That conclusion is often built on a census of *junior* roles when the real gap is one rung up: a
  mid-level band you qualify for today, sitting one step below the senior door you keep getting
  rejected from. Look specifically for it before assuming there's no rung under senior at all.

### 2. Work out your actual number, honestly

Count your real, defensible years of relevant professional experience: the same discipline, done
for pay, not a rough impression. Write down how you counted it (which roles, which date ranges,
whether you included part-time or overlapping stints) so you can defend the number if asked, and so
it's easy to update the next time it changes.

**Your number:** [ ] years, counted as: [ ]

Once you have it, put it in `scripts/config.py` as `YOUR_YEARS_OF_EXPERIENCE = [your number]`. That
one value is what `scripts/seniority_gate.py` compares against every JD's stated years floor, so
research done here turns directly into fewer senior-reach roles slipping into your pipeline.

### 3. Find out whether craft or metrics actually gates you, per target

"Should I become more of a numbers person, or focus on craft?" is usually a false choice, and the
honest answer is company-specific, not universal. Some companies name a measured outcome as a hard
requirement at your target level; others explicitly do not, and a few even push back against
metrics-flavored portfolios. Visual craft, by contrast, tends to be closer to a universal floor:
weak execution is a common, fast rejection reason almost everywhere, even at metrics-heavy
companies. Research each target directly (published career ladders, engineering/design blog posts,
interview-prep material from actual candidates) rather than assuming your last company's culture
generalizes.

| Company | Craft/portfolio-quality gate? | Quantified-outcome gate? | Source |
|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] |

### 4. Audit your own case studies for the argument, not just the inventory

Read your own portfolio as a skeptical stranger would. For each case study, count how many times
you actually state a decision and its reasoning ("I chose X over Y because Z," a named tradeoff, a
rejected alternative, a thing you deliberately did not build and why) versus how many times you
just describe what exists ("I designed a dashboard with 12 components"). A portfolio that is all
inventory and no argument reads as executional even when the underlying work was genuinely senior,
because "senior" is largely a claim about judgment, and judgment only shows up on the page when you
show your reasoning, not just your output.

- **Case study 1:** decisions with stated reasoning: [ ] · pure inventory statements: [ ]
- **Case study 2:** decisions with stated reasoning: [ ] · pure inventory statements: [ ]
- **The honest read:** [ ]

A related trap: over-correcting into constant disclaimers about what a project *isn't* ("to be
clear, this was a small feature, not a redesign") can read as anxious rather than honest. State a
real limit once, plainly, and move on, rather than repeating it.

### 5. Check what you're actually exhibiting is your own original work

If a case study's strongest visuals were substantially AI-generated, copied from a reference, or
built on someone else's design system with minimal original work layered on top, that's worth
knowing before a portfolio review finds it for you. This isn't a honesty problem if it's disclosed;
it's a positioning problem if your best-looking evidence isn't actually evidence of your own
design ability. Go through your strongest pieces and be honest about which parts were genuinely
yours.

- **Piece:** [ ] · **Genuinely original design work, or reference/AI-assisted/borrowed system?** [ ]

### 6. Learn what the actual interview loop grades, not what you assume it grades

Look up, for each real target, what its design/engineering interview loop actually consists of:
a live narrative deck versus a portfolio-site walkthrough, how much time is behavioral versus
portfolio versus a live exercise, whether there's an unfamiliar-product critique or a timed
whiteboard round. Many people spend months polishing a personal website when the loop that matters
grades a rehearsed narrative deck and live improvisation instead. Don't guess this; multiple
companies publish exactly what they expect candidates to bring.

| Company | Loop format (deck vs. site walkthrough, live exercises, behavioral weight) | Source |
|---|---|---|
| [ ] | [ ] | [ ] |

### 7. Run one honest, unassisted craft test

Pick one small, real exercise (one component from a written spec, or one screen from a blank
canvas), give yourself a fixed time limit, and do it alone with no AI assistance and no reference
material. This is the cheapest way to find out what your raw craft actually looks like today,
independent of any tool, any template, or any story you tell about your own ability. If you've been
avoiding this test, that avoidance is itself information.

**Result and honest self-grade:** [ ]

## What to do next (rank these for yourself)

Once you've run the method above, you'll have real evidence instead of a guess. Rank your own next
actions by leverage, cheapest and highest-impact first. A rough shape to start from:

1. [ ] Fix anything you found that's flatly wrong or misleading on a live surface (§0.1-style
   honesty issues always outrank everything else).
2. [ ] Add the missing argument to case studies that are inventory-only (§4) -- usually days of
   work, and often the single highest-leverage fix here.
3. [ ] Rebalance which companies you're spending effort on, toward the ones whose stated floor you
   already clear, or where a referral can override the filter (§1-2).
4. [ ] Build the specific artifact the loop actually grades, if you don't have it yet (§6).
5. [ ] Close any real craft gap the unassisted test surfaced (§7).

## Honest limits of this analysis

- This file is a method, not a verdict. Every conclusion above is only as good as the research you
  actually did to fill in the tables -- an empty bracket is an honest "not yet researched," not a
  finding.
- A stated years floor and a published loop format can both change; re-check before relying on
  something you researched more than a few months ago.
- Nobody but you can honestly grade your own raw craft (§7). If you skip that step, don't let the
  rest of this file substitute for it.

## Related

- `07-master-resume.md`: where your real years and roles are the canonical source of truth
- `13-strengths-and-market-position.md`: the adversarial self-audit this file's craft/argument
  questions overlap with
- `14-positioning-and-visibility.md`: what to do with the gap once you've actually measured it
- `scripts/seniority_gate.py`: reads `YOUR_YEARS_OF_EXPERIENCE` from `scripts/config.py` (§2 above)
  to mechanically flag a JD asking for materially more years than you have
