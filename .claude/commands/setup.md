---
description: First-run setup, agent-led. Asks the user a few short questions, reads their résumé, fills the four required knowledge-base files (plus your hard stops and voice samples if you give them) and the crawler config itself, finds job boards, runs the health check, and ends by offering /wave.
---

# /setup: from a fresh clone to a ready engine, with the user typing as little as possible

You do the setup. The user answers a few plain questions and hands over their résumé; you write
every file. Never tell the user to open or edit a file unless they say they want to. `SETUP.md` is
the manual version of the same path; this command replaces it for anyone who would rather talk.

## The walls (they hold for the whole command)

1. **Nothing invented.** `CLAUDE.md` §0.1 (the Grounding Law) and §5 apply to every line you write.
   Every fact goes in from one of two sources: the user's résumé, or the user's own words in this
   chat. If the résumé does not say it and the user has not said it, the field stays empty (or keeps
   its template text) and you list it as open. Never fill a gap with a plausible guess: no guessed
   dates, titles, degrees, GPA, numbers, or locations. Copy the résumé's own wording and numbers; do
   not upgrade "helped with" into "led", and do not round a number up.
2. **Work authorization is the highest-stakes answer in the repo.** You write it from the user's own
   words, then read it back and get a clear yes before it counts (step 4). If the user is unsure, it
   stays unfilled and form filling waits; `visa_gate.py` will say so. You never pick the answer.
3. **Fewest questions, plain words, one short batch at a time.** Ask only what the résumé cannot
   tell you. No jargon (say "the job titles you want", not "include_titles").
4. **Account safety.** Never open LinkedIn or any of the user's logged-in major accounts (email,
   social, job-board accounts) in any browser, for any reason. A LinkedIn URL from the résumé is a
   value to store, never a page to visit.
5. **Their data stays theirs.** The knowledge base now holds personal facts. Never push. If
   `git remote -v` points at a public repository, tell the user once, plainly, that pushing would
   publish their personal details, and suggest a private copy.
6. **Restartable.** If the user stops halfway, everything already written stays; running `/setup`
   again starts with `python3 scripts/doctor.py` and asks only what is still missing.

## Steps

### 0. See where things stand (no questions yet)

Run `python3 scripts/doctor.py`. Read `knowledge-base/INDEX.md`, then the four required files:
`01-profile-and-identity.md`, `02-work-authorization.md`, `07-master-resume.md`,
`12-application-answers.md`. Each file's own comments say what belongs where; follow them, and keep
every landmark a script reads (the ```` ```canonical-facts ```` block, the `### WORK EXPERIENCE`
heading, the ```` ```work-authorization ```` block and its key names). Skip any step below that
`doctor.py` already shows as done.

Then greet the user in two sentences: what you are about to do, and that it takes a few short
questions.

### 1. First batch: the résumé and the search

Ask, in one message:
- "Please share your current résumé: a file path (PDF, Word, or text) or paste the text here."
- "What job titles are you looking for? Two to six is plenty."
- "Where are you based (city and state)? And which work do you want: remote, on-site or hybrid near
  you (which cities count as near), and would you relocate (where to)?"
- "How many years of professional experience do you have? A rough whole number is fine."
- "Any companies you already know you want? (Optional.)"

Read the résumé with your file tools. If a file cannot be read, ask for the text pasted instead.

### 2. Fill the profile and the résumé from what they gave you

From the résumé and the answers, write:
- **KB-01** (`01-profile-and-identity.md`): name, email, phone, location, willingness to relocate,
  links, education, and the "Who you are" lines, built only from what the résumé says. Leave the
  "internal only" section alone.
- **KB-07** (`07-master-resume.md`): the full résumé content, every employer, title, date range and
  bullet as written. In the canonical-facts block fill the `exact:` lines the résumé supports (email,
  title, and LinkedIn or portfolio only if the résumé has them; delete a line that does not apply).
  Leave `never:` and `number:` empty.
- **KB-12 §1 and §2** (`12-application-answers.md`): identity and links, the same values as KB-01.
- **`resume/resume.html`**: replace the template content with KB-07's, keeping the template's
  structure, classes and date format. Then render and check it:
  `weasyprint resume/resume.html resume/<first>_<last>_resume.pdf` and
  `python3 scripts/resume_gate.py`. If the page comes out short, ask the user for more real material
  (another project, a fuller bullet); never pad. If they have no more, the short page stays as it
  is: tell them what `resume_gate.py` reported, that the choice is theirs, and list it as an open
  item with that explanation. If weasyprint is not installed, say so and move on; `doctor.py`
  covers it.

Then ask only what is still missing, in one message. Typical: phone number (optional, they may
skip it), anything the résumé left ambiguous (an end date, the current title). Show what you
extracted in a short list (name, email, phone, location, current title and employer, years of
experience, and the time zone you take from their location, written as its IANA name, for example
"America/Denver") and ask "Is this right?" Fix what they correct. This is the same message as the
missing-facts question, so it adds no round trip.

Once they confirm, set two values in `scripts/config.py` (every other value there stays as it is):
- `YOUR_YEARS_OF_EXPERIENCE = <their number>`, exactly as they said it. Never work it out from the
  résumé dates on your own; if they skipped the question, leave it `None` and list it as open
  (`seniority_gate.py` then says it did not check, which is not a pass).
- `TIMEZONE = "<IANA name>"`, the zone they confirmed. If their location spans two zones or they
  live in one zone and work in another, ask which one; do not pick.

### 3. Point the crawler at their search

- Write their titles into `pipeline/job-crawler/filters.yaml`: replace the shipped
  `include_titles: []` with their titles as a list, in lowercase (the commented lines above it are
  only an example of the shape; leave them). Set `include_keywords` to `[]` unless they gave
  keywords. Leave `exclude_patterns` and `flag_patterns` alone unless the user asks; the file's
  comments explain why they depend on the person.
- Write where they will work into the location settings of the same file, read from what they said
  in step 1: remote or not, the cities they would work on-site or hybrid in, and whether and where
  they would relocate. The keys are `remote_ok` (true or false), `onsite_ok` (`anywhere`,
  `home_metros` or `none`) and `home_metros` (the place names that count, including any city they
  would relocate to). For example "remote, or on-site in Denver, no relocation" is
  `remote_ok: true`, `onsite_ok: home_metros`, `home_metros: ["denver"]`; "remote only" is
  `onsite_ok: none`. The file's comments are the full reference; never invent a key the crawler does
  not read. Anything they did not say stays at the file's default and goes in the hand-over list.
- Find job boards. `discover.py` is the tool; run `python3 pipeline/job-crawler/discover.py --help`
  once to confirm its flags. Tell the user first, in one line, that the first sweep is the slowest
  step of setup and may take a while. Then run both paths, every time, not one as a fallback for the
  other. Start the sweep in the background if your tools allow, and do the web-search path while it
  runs:
  1. The sweep: `python3 pipeline/job-crawler/discover.py --sweep`. It finds company boards in the
     free Common Crawl index and keeps the ones posting jobs that match the titles. That index is a
     free public service and is often slow or down; the sweep stops after its time budget and says
     so, and whatever it found by then is kept.
  2. The web-search path, alongside the sweep: research with your web search which companies hire
     for their titles in their location or remotely, and pass those names, plus every company the
     user named, to `python3 pipeline/job-crawler/discover.py --company "Name" ...`. Run
     `discover.py --queries`, run those searches, and feed the result URLs (and any careers-page URLs
     you or the user have), one per line on stdin, to `discover.py --urls -`.
  If the sweep ran out of time or the index did not answer, say so in one line and tell them the
  next `/wave` sweeps again and widens the list.
  Free job feeds (no key needed for most) are listed in `pipeline/job-crawler/sources.yaml`; leave
  them on.
- Show the result: `python3 pipeline/job-crawler/crawl.py --hours 720`. Tell the user in one or two
  lines how many matching postings came back and from how many companies. Zero is a finding, not a
  failure: say which of the three usual causes it looks like (titles phrased differently, too few
  boards, a narrow window) and fix it.

### 4. Second batch: work authorization (slow down here)

Ask exactly this, in plain words, and nothing else in the same message: "In your own words, what is
your situation for working in the US? For example: citizen, permanent resident, a visa or work
permit (which one, and until when), and whether you would ever need an employer to sponsor a visa."

Then:
- Write **KB-02** "Current status": their status in their own words, whether they need sponsorship
  now or ever, and any deadline they named. Fill the "hard filters" lines only from what they said;
  leave the rest as template text.
- Write **KB-12 §3**: the four `work-authorization` keys (`authorized-now`, `sponsorship-to-begin`,
  `sponsorship-now-or-future`, `restricted-authorization`), each `YES` or `NO` with a one-line reason
  in their words. Use the section's own comment to map their answer to each key. If any key does not
  follow clearly from what they said, ask that one question; do not resolve it yourself.
- **Read it back** as the four questions a form actually prints, each with the answer you recorded,
  word for word from what you just wrote in KB-12 §3 (the question as the section's comment phrases
  it, then the answer you recorded). Ask: "Are all four right?" Write nothing as final until they say yes. If they say they are not sure, leave §3
  unfilled, tell them form filling waits on it, and suggest they confirm with an immigration
  professional if the situation is complex. This repo is not legal advice.
- Run `python3 scripts/visa_gate.py`. With §3 confirmed it must exit 0; if it does not, fix what it
  names. If the user was not sure and §3 stays unfilled, it says so, and that is an open item with
  its reason, not a failure to hide.

### 5. Two short questions: hard stops and voice samples (both skippable)

Ask, in one message:
- "Two kinds of facts should never be entered wrong, even if a stretch would help, because a
  background check or a legal process checks them: (1) your work authorization, citizenship, visa and
  sponsorship answers, and (2) your employers, job titles, dates, degrees, schools, GPA, licenses and
  certifications. Should I lock those two as your hard stops? Add any of your own if you like."
- "Optional: paste two or three things you've written yourself (an email, a message, a cover letter).
  It's how I learn to sound like you. Skip it if you'd rather."

Record a yes (and any category they add) as a dated row in
`knowledge-base/11-preferences-and-conventions.md` ("Hard-stop categories: ..."; `CLAUDE.md` §5 owns
why). Paste each sample, lightly redacted if they ask, under "Your own voice samples" in
`knowledge-base/17-writing.md`. Write nothing they did not give you; a skipped question stays open
and goes in the hand-over list.

### 6. One optional question: commits

`CLAUDE.md` §10 asks for this once. Ask: "Should I save my work as I go? Pick one: commit locally as
I go (recommended), or don't commit. Either way I never push anywhere without asking you." Write the
choice they picked, word for word, with today's date, in the `Commits:` line of the Workflow section
of `knowledge-base/11-preferences-and-conventions.md`, plus a dated row in its decision log. If they
skip the question, write "commit locally as I go (default, not chosen)" with the date, so the record
says the default holds and that they did not pick it.

### 7. Health check, then fix what you can

Run `python3 scripts/doctor.py`, then `python3 scripts/doctor.py --fill`. For each line that is not
OK:
- Fix it yourself when it is a file you own here (a KB field, filters, boards).
- `pip install -r pipeline/job-crawler/requirements.txt`, or weasyprint when `doctor.py` says it is
  not installed at all: ask once ("Can I install these Python packages?") and run them on a yes.
  When `doctor.py` reports the `weasyprint` command as found, PDF rendering works; install nothing.
- Node.js missing or old, or the browser tool not connected: give the user the exact steps
  `doctor.py --fill` prints. Installing Node and approving the `chrome-devtools` server are theirs to
  do; say why in one line (it installs software on their machine, and the approval prompt is theirs
  to answer). After they restart the session, confirm the browser tool shows up in your tool list.

Run `python3 scripts/canon.py` as well; it must exit 0.

### 8. Hand over

Tell the user, in at most six short lines:
- what is set up (the four files, the résumé PDF if rendered, how many boards and matching postings);
- what is still open, by name, each with one plain line on why (a blank field, a skipped question,
  a short résumé page, a `doctor.py` warning, a gate that did not check);
- whether form filling is ready (`doctor.py --fill` exit code, quoted);
- the next step: "Run `/wave` and I'll pick the best matches, tailor your résumé and cover letter, and
  fill the application forms for you to review and submit."

Append one short entry to `ops/log/activity.md` (date, "setup", what was filled, what is open).
Commit locally only if the recorded choice from step 6 is to commit; never push.

## If the user wants their own extra tools (MCP servers)

The repo's `.mcp.json` holds only `chrome-devtools`, and it is shared with everyone who clones the
repo, so personal servers do not go there. In Claude Code the user adds one with
`claude mcp add <name> -- <command>`: the default "local" scope stores it in their own
`~/.claude.json` for this project only, outside the repo. A personal JSON file kept in the repo must
be named `.mcp.local.json` (gitignored) and loaded with `claude --mcp-config .mcp.local.json`. In
Codex: `codex mcp add <name> -- <command>` (stored in their own Codex config).

<!-- Sources, checked 2026-10-22: Claude Code MCP scopes and storage,
https://code.claude.com/docs/en/mcp ; Codex MCP config,
https://learn.chatgpt.com/docs/extend/mcp?surface=cli -->

## Done means

Every remaining open item is named and explained, and nothing is called done that a command did
not show this turn (`CLAUDE.md` "the definition of done"). For an honest user with everything
answered, that means `python3 scripts/doctor.py --fill`, `python3 scripts/canon.py` and
`python3 scripts/visa_gate.py` exit 0. Some items can stay open for honest reasons the user owns: a
work-authorization answer they are not sure of (form filling waits on it), a short résumé page
they have no more real material for, a question they skipped, Node or the browser tool still to be
installed or approved by them. Each of those is reported by name with its reason and what clears
it, never hidden and never forced to pass.
