<!--
Optional and advanced, like 13 and 14. Do this once you have a few real applications behind you,
and revisit it only when something real changes (a new target company, a new piece of work, a year
of experience gained). It is a research method, not a running fact file.

This file exists because a very common self-diagnosis is wrong in a specific, fixable way: "my
experience must read as too junior, because I keep failing to clear the senior-level roles I apply
to." Often the real story is smaller and easier to fix: the person is a year or two under a stated
years-of-experience floor (a filter, not a quality verdict), and separately, their résumé and
interview stories describe what they did without ever showing what they decided. Two different
problems, two different fixes, and mixing them up wastes months on the wrong one. Work through the
method below with your own targets before concluding which problem (if either) you have. Delete
this comment block once you've run it for real.
-->

# The Senior Gap: figuring out where you actually sit

## The mistake this file exists to prevent

A "senior" title at a given employer is set by two different things that are easy to mistake for
each other: a **years-of-experience filter** (a number on the posting), and a **quality bar** (what
the screen and the interview loop actually grade). A rejection can mean either one, and they call
for different responses. If it's the filter, the fix is patience, a referral that overrides the
filter, or a role at an employer whose floor you already clear. If it's the bar, the fix is the
work itself: stronger evidence of your judgment, a sharper story, a better-rehearsed interview. Do
not guess which one you're facing. Research both, separately, before you decide what to fix.

## The method

### 1. Build your own ladder table

For each employer you actually care about, find out from their own live postings (not a summary,
not a rumor): the senior-equivalent title, its stated years floor if one is published, and whether
the same title is posted at more than one band. Two "Operations Analyst" postings at the same
employer, one asking for 3+ years and one for 6+, are not the same job, even with the same title.
A third-party leveling site can help you map a title to a level once you have the real posting in
hand, but the posting is the primary source, not the site.

| Employer | Senior-equivalent title | Stated years floor | Multiple bands under one title? | Source (URL + date) |
|---|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] | [ ] |

Example of a filled row (made up, delete it): Acme · Senior Operations Analyst · 5+ years · yes,
a second posting asks 7+ · the employer's careers page, with the date you read it.

**Two traps to watch for while you do this:**
- **Don't read the duties bullets to infer level.** Postings for neighboring levels at the same
  employer often reuse nearly identical bullets. The band, and the language about ambiguity and
  scope ("owns decisions with incomplete information", "mentors others", "sets direction for a
  team"), are better tells than the day-to-day duties.
- **Check for a mid-level rung you might be skipping.** It's easy to survey postings, see no
  entry-level openings, and conclude the only door is "senior or nothing". Often the real gap is one
  rung lower: a mid-level band you qualify for today, one step below the senior door you keep
  getting turned away from. Look for it before assuming there's no rung under senior.

### 2. Work out your actual number, honestly

Count your real, defensible years of relevant professional experience: the same kind of work, done
for pay, not a rough impression. Write down how you counted it (which roles, which date ranges,
whether you included part-time or overlapping stints) so you can defend the number if asked, and
update it easily when it changes.

**Your number:** [ ] years, counted as: [ ]

Once you have it, put it in `scripts/config.py` as `YOUR_YEARS_OF_EXPERIENCE = [your number]`. That
one value is what `scripts/seniority_gate.py` compares against every posting's stated years floor,
so the research here turns directly into fewer over-reach roles slipping into your pipeline.

### 3. Find out what the quality bar actually grades, per target

"Should I show more measured results, or more depth in the work itself?" is usually a false choice,
and the honest answer depends on the employer. Some name a measured outcome as a hard requirement at
your target level; others care more about how you reason through a hard problem. Research each
target directly (published career ladders, the employer's own blog or careers pages, interview-prep
material from people who went through the loop) rather than assuming your last employer's culture
holds everywhere.

| Employer | What the senior bar names (outcomes, scope, judgment, a credential) | Source |
|---|---|---|
| [ ] | [ ] | [ ] |

### 4. Audit your own evidence for the argument, not just the inventory

Read your résumé bullets and your interview stories (`15-interview-story-bank.md`) as a skeptical
stranger would. For each one, count how often you state a decision and its reasoning ("I chose X
over Y because Z", a named tradeoff, an option you rejected, something you deliberately did not do
and why) versus how often you just describe what exists ("I managed a team of six", "I ran the
weekly report"). Evidence that is all inventory and no argument reads as execution-level even when
the work was genuinely senior, because "senior" is largely a claim about judgment, and judgment
only shows when you show your reasoning.

- **Story or bullet 1:** decisions with stated reasoning: [ ] · pure inventory statements: [ ]
- **Story or bullet 2:** decisions with stated reasoning: [ ] · pure inventory statements: [ ]
- **The honest read:** [ ]

A related trap: over-correcting into constant disclaimers about what a piece of work *wasn't* ("to
be clear, this was a small project") can read as anxious rather than honest. State a real limit
once, plainly, and move on.

### 5. Check that what you're claiming is your own work

If your strongest examples lean on work that was mostly a teammate's, a vendor's, a template's or a
tool's, that's worth knowing before an interviewer's follow-up questions find it for you. Shared
work is normal; the question is whether you can say plainly which part was yours. Go through your
strongest examples and write down your own part in one line each.

- **Example:** [ ] · **What was genuinely mine:** [ ]

### 6. Learn what the actual interview loop grades, not what you assume it grades

Look up, for each real target, what its interview loop actually consists of: how much is behavioral
versus technical or role-specific, whether there's a live exercise, a case, a work sample or a
presentation, and who is in the room. Many people spend months polishing the wrong artifact when
the loop that matters grades a rehearsed story and live problem-solving. Don't guess; many employers
publish what they expect candidates to prepare.

| Employer | Loop format (rounds, live exercises, behavioral weight) | Source |
|---|---|---|
| [ ] | [ ] | [ ] |

### 7. Run one honest, unassisted skill test

Pick one small, real exercise typical of your target role (a short case, a problem set, a written
plan, a sample task from a published interview guide), give yourself a fixed time limit, and do it
alone with no AI help and no reference material. This is the cheapest way to see where your raw
skill stands today, apart from any tool or any story you tell about it. If you've been avoiding
this test, that's information too.

**Result and honest self-grade:** [ ]

## What to do next (rank these for yourself)

Once you've run the method above, you'll have evidence instead of a guess. Rank your next actions by
leverage, cheapest and highest-impact first. A rough shape to start from:

1. [ ] Fix anything you found that's flatly wrong or misleading on a live surface (§0.1-style
   honesty issues always come first).
2. [ ] Add the missing reasoning to résumé bullets and stories that are inventory-only (§4). Usually
   days of work, and often the single highest-leverage fix here.
3. [ ] Rebalance which employers get your effort, toward those whose stated floor you already
   clear, or where a referral can override the filter (§1, §2).
4. [ ] Prepare the specific thing the loop actually grades, if you don't have it yet (§6).
5. [ ] Close any real skill gap the unassisted test surfaced (§7).

## Honest limits of this analysis

- This file is a method, not a verdict. Every conclusion is only as good as the research you
  actually did to fill the tables. An empty bracket is an honest "not yet researched", not a
  finding.
- A stated years floor and a published loop format can both change; re-check anything you
  researched more than a few months ago.
- Nobody but you can honestly grade your own raw skill (§7). If you skip that step, don't let the
  rest of this file stand in for it.

## Related

- `07-master-resume.md`: where your real years and roles are the canonical source of truth
- `13-strengths-and-market-position.md`: the adversarial self-audit this file's questions overlap
  with
- `14-positioning-and-visibility.md`: what to do with the gap once you've measured it
- `15-interview-story-bank.md`: the stories §4 audits
- `scripts/seniority_gate.py`: reads `YOUR_YEARS_OF_EXPERIENCE` from `scripts/config.py` (§2 above)
  to flag a posting asking for materially more years than you have
