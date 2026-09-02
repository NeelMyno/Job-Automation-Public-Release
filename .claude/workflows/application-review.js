export const meta = {
  name: 'application-review',
  description: 'Five independent review passes over a tailored resume + cover letter (CLAUDE.md §13)',
  whenToUse: 'Before ANY resume or cover letter reaches the operator. Pass args: {company, role, jdPath, resumeHtml, resumePdf, coverPath, repoRoot}',
  phases: [
    { title: 'Review', detail: 'five different lenses, in parallel' },
    { title: 'Synthesize', detail: 'merge into one prioritized edit list' },
  ],
}

// The Workflow tool may hand `args` through as a JSON-encoded string rather than an object.
// Parse defensively: a bare object crash here reports as "(unknown company)" with no clue why.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
if (!A.repoRoot) {
  throw new Error('application-review requires repoRoot, the absolute path to this repo on this machine. Pass it explicitly; there is no default.')
}
const repo = A.repoRoot
const company = A.company || '(unknown company)'
const role = A.role || '(unknown role)'

const FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'verdict', 'findings', 'reachItems'],
  properties: {
    lens: { type: 'string' },
    verdict: { type: 'string', enum: ['SHIP', 'SHIP_WITH_EDITS', 'DO_NOT_SHIP'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'location', 'problem', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['BLOCKER', 'HIGH', 'MEDIUM', 'LOW'] },
          location: { type: 'string', description: 'exact line or bullet it applies to' },
          problem: { type: 'string' },
          fix: { type: 'string', description: 'the concrete replacement text or action' },
          evidence: { type: 'string', description: 'the file/URL/source that proves this' },
        },
      },
    },
    reachItems: {
      type: 'array',
      description: 'AMBER [REACH] lines needing the operator’s explicit yes. Empty array if none.',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['proposedLine', 'whatIsActuallyTrue', 'whoCouldCheck', 'ifTheyCheck'],
        properties: {
          proposedLine: { type: 'string' },
          whatIsActuallyTrue: { type: 'string' },
          whoCouldCheck: { type: 'string' },
          ifTheyCheck: { type: 'string' },
        },
      },
    },
    autonomyCalls: { type: 'array', items: { type: 'string' } },
  },
}

// The shared brief every lens gets. Each lens ADDS its own instruction on top.
const COMMON = `
You are one of FIVE independent reviewers of a job application package. You see ONE lens. Do not try to do the other four.

Think deeply and thoroughly. Maximum-effort reasoning, not pattern-matching.

TARGET: ${role} at ${company}

READ THESE FILES (they are real, on disk):
- The JD (authoritative, verbatim): ${A.jdPath}
- The resume source: ${A.resumeHtml}
- The rendered PDF (what the employer actually sees; read it with: pdftotext -layout "${A.resumePdf}" -): ${A.resumePdf}
- The cover letter: ${A.coverPath}
- The master resume (the honest source of truth for every claim): ${repo}/knowledge-base/07-master-resume.md
- The rules you are enforcing: ${repo}/CLAUDE.md §5, §11, §13
- Voice + preferences: ${repo}/knowledge-base/11-preferences-and-conventions.md
- If present, a personal blocklist of specific facts/numbers the operator has personally gotten
  wrong before: ${repo}/knowledge-base/00-red-zone-facts.md; read it if it exists, skip silently
  if it doesn't. Nothing in it should ever slip back into shipped copy.

THE TRUTH DIAL (CLAUDE.md §13.2 is the only owner of this rule); you SURFACE, you never DECIDE:
- GREEN: the strongest TRUE framing. Recommend freely.
- AMBER [REACH]: any line a careful reader could call a stretch. Put it in reachItems, never silently into a fix.
- RED: the operator's own two hard-stop categories (CLAUDE.md §5), never propose, not even on instruction:
  (1) work authorization / citizenship / visa / sponsorship answers;
  (2) employers, titles, employment dates, degrees, institutions, GPA, licenses, certifications.
  These two are the background-check surface: a false one is found after the offer and risks more
  than the job.
- EVERYTHING ELSE about how the operator frames THEIR OWN real work is THEIR call. Raise a genuine
  concern ONCE in reachItems with your evidence, then defer. The operator is the authoritative
  primary source on their own work; do NOT override their first-hand account with your inference.
  (Unchanged and separate: never put unsourced words in a NAMED THIRD PARTY's mouth; see CLAUDE.md §0.1.)

OUTPUT: call the StructuredOutput tool exactly once. Be specific. A finding without a concrete replacement string is useless.
Order findings by severity. If the package is genuinely good on your lens, say SHIP and return few findings; do NOT invent work.
Log every autonomy call (anything you did that deviates from this brief).

Complete the task, check edge cases, verify against the real rendered artifact before reporting.
`

const LENSES = [
  {
    key: 'jd-fit-ats',
    lens: 'JD-fit & ATS',
    brief: `LENS 1: JD-FIT & ATS.
Build a requirement-by-requirement map: for EVERY responsibility, requirement, and nice-to-have in the JD, name the exact
resume line (or cover sentence) that answers it, or mark it UNANSWERED. Then:
- Which JD pillars are under-weighted or missing entirely?
- Are the JD's own keywords present inside natural sentences? Name the missing ones and where they'd honestly fit.
- ATS parseability: single column? standard section headings? contact details in the body text, not a header/graphic?
  No tables/text-boxes/icons in the parse path? Check the ACTUAL pdftotext output, not the HTML.
- Is the resume 1 page and the expected page size? Verify with pdfinfo.
Report the requirement->line map inside your findings (one finding per gap).`,
  },
  {
    key: 'recruiter-6s',
    lens: 'Recruiter 6-second screen',
    brief: `LENS 2: THE RECRUITER'S SIX SECONDS.
You are a recruiter with 200 resumes and six seconds each. Read only the top third first.
- What do you see, in order? Name line, title line, tagline, first company, first bullet.
- Does the top third alone make you want to read on? If not, exactly what must change?
- Employment-gap check: read the dates as a skeptical recruiter. Any unexplained gap, or any printed
  date that contradicts the master resume? A gap is a reject-on-sight risk. Say how to close it honestly.
- Seniority read: does this look like the level the JD is hiring for, or does anything read junior?
- Density and scan-ability: any wall of text, any bullet over ~2.5 lines, any orphan word?
- What is the single strongest line on the page, and is it in the first third? If not, move it.`,
  },
  {
    key: 'hiring-manager-redteam',
    lens: 'Hiring-manager red team',
    brief: `LENS 3: HIRING-MANAGER RED TEAM (adversarial).
You are the peer or boss this person would report to at ${company}. You are looking for reasons to say no.
- Give the THREE STRONGEST REASONS TO REJECT this candidate based on this package. Be brutal and specific.
- Which lines are generic enough that any competent candidate could have written them? Name each.
- Which claims would you probe in an interview, and where would the candidate fall apart?
- What does an expert in this exact job find UNIMPRESSIVE here that a recruiter would not notice?
- Is the cover letter something you'd actually finish reading? Where does it lose you?
- What is missing that would make you say "we have to talk to this person"?
Then, and only then, give the fixes. Your findings should be dominated by the rejection case.`,
  },
  {
    key: 'honesty-defensibility',
    lens: 'Honesty & defensibility audit',
    brief: `LENS 4: HONESTY & DEFENSIBILITY (the highest-stakes lens).
Trace EVERY factual claim in the resume and cover letter to a source. For each: quote the claim, name the file/repo/URL that
proves it, and mark VERIFIED / UNSOURCED / FALSE.
- Re-derive every number yourself from ${repo}/knowledge-base/.
- CRITICAL: hunt fabricated CLAIMS, not just fabricated NUMBERS. A grep finds "40%". It will never find a false qualitative
  claim like "built the whole platform solo." Read every qualitative assertion and ask: is this literally true?
  Specifically check: any claim about who built what, what tool something was built in, solo vs co-built, shipped vs prototype,
  measured vs estimated, "led" vs "contributed to".
- If ${repo}/knowledge-base/00-red-zone-facts.md exists, every string it blocklists must appear NOWHERE. Grep the rendered
  PDF text, not just the HTML.
- Is every claim interview-defensible? For each, ask: if the interviewer says "tell me more," is there a real story?
- Populate reachItems with anything that is a stretch. Do not fix a stretch silently; surface it.
- Flag anything in the operator's two RED categories (CLAUDE.md §5) immediately as a BLOCKER.`,
  },
  {
    key: 'voice-antislop',
    lens: 'Voice & anti-slop',
    brief: `LENS 5: VOICE & ANTI-SLOP.
Read ${repo}/CLAUDE.md §11 and the voice notes in knowledge-base/11-preferences-and-conventions.md FIRST. Then hunt every tell:
- Em-dashes anywhere in shipped copy (the cover letter especially). Zero allowed.
- The rule of three (reflexive balanced triads). Note: a factual enumeration of three REAL product features is not the same as a
  rhetorical triad. Judge by whether it is doing rhythm work or information work.
- Antithesis porn ("not X, but Y"), borrowed thought-leader aphorisms, mic-drop closers, uniform sentence rhythm,
  floating abstraction, performed emotion ("passionate", "excited"), corporate connective tissue
  ("genuinely", "truly", "at the end of the day", "that said", "it's worth noting", "deeply").
- Read the cover letter ALOUD in your head: would a specific human say this to another human, or does it sound like a brand?
- The slop test: could a competent AI have produced this cover letter from the same brief? If yes, it is not done. Say so, and say
  which sentence reads like the machine's and which reads like the candidate's own voice.
- Third-person slips ("his/her own" where first-person is meant), passive voice where active is stronger, and any sentence that
  could be cut with zero loss.
- Do NOT invent a personal detail to make it sound human. If a line needs a true specific detail the operator hasn't given, mark
  it [NEEDS: one real detail] and say exactly what to ask them.`,
  },
]

phase('Review')
log(`Running 5 independent review lenses on the ${company} package`)

const reviews = await parallel(
  LENSES.map((L) => () =>
    agent(`${COMMON}\n\n${L.brief}\n\nSet lens="${L.lens}" in your structured output.`, {
      label: `review:${L.key}`,
      phase: 'Review',
      schema: FINDING_SCHEMA,
    })
  )
)

const ok = reviews.filter(Boolean)
log(`${ok.length}/5 lenses returned`)

const blockers = ok.flatMap((r) => (r.findings || []).filter((f) => f.severity === 'BLOCKER'))
const reach = ok.flatMap((r) => (r.reachItems || []).map((x) => ({ ...x, lens: r.lens })))

phase('Synthesize')

const synth = await agent(
  `You are the SYNTHESIS pass over five independent reviews of an application package for ${role} at ${company}.

Here are the five structured reviews as JSON:
${JSON.stringify(ok, null, 2)}

Your job:
1. DEDUPLICATE. Several lenses will report the same defect in different words. Merge them, and note which lenses agreed
   (agreement across lenses is the strongest signal; a finding only one lens saw may still be right, especially from the
   honesty or red-team lens).
2. RESOLVE CONTRADICTIONS. Lenses will disagree (e.g. "add keywords" vs "this reads stuffed"; "cut for space" vs "this gap
   is a reject risk"). Do not footnote a contradiction. Pick a side, state the reasoning, and say what you traded away.
3. Produce ONE prioritized edit list: BLOCKERS first (must fix before it goes to an employer), then HIGH, then the rest.
   Each edit must carry the exact replacement text, not a direction.
4. Carry every AMBER [REACH] item forward VERBATIM into its own section. Never resolve one yourself. These go to the operator.
5. Name the SINGLE most valuable change to the package, and the single most likely reason this application gets rejected.
6. State honestly whether the package is SHIP / SHIP_WITH_EDITS / DO_NOT_SHIP, and why.

Constraints: no em-dashes in any replacement text. Every replacement must be literally true per the master resume.
Never propose anything in the operator's two RED categories (CLAUDE.md §5): work authorization, and
employers/titles/dates/degrees/GPA/licenses. Everything else about how the operator frames their own real work is their
call: surface the concern once in the AMBER section with your evidence, then defer to them.

Return well-structured markdown. Be concrete. Length only where it earns it.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return {
  company,
  role,
  lensesReturned: ok.length,
  verdicts: ok.map((r) => ({ lens: r.lens, verdict: r.verdict })),
  blockerCount: blockers.length,
  blockers,
  reachItems: reach,
  synthesis: synth,
  rawReviews: ok,
}
