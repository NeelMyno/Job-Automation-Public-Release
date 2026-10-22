# SETUP: from a fresh clone to your first application

This repo does nothing useful until it knows who you are and what you're looking for. There are two
ways to get there. Both end in the same place.

## The fast way: let the agent do it (about 15 minutes)

1. Install the prerequisites below.
2. Open the repo in Claude Code (`claude` in this folder) or Codex (`codex` in this folder).
3. Type **`/setup`** (Codex: **`$setup`**).

The agent asks a few short questions (your résumé, the job titles you want, where you're based, your
work-authorization situation in your own words, and two optional ones: your hard stops and a few
samples of your own writing), then writes every file itself: the knowledge
base, your résumé source, the crawler settings. It finds company job boards that match your titles,
runs a health check, fixes what it can, and tells you plainly what is still open. You never have to
edit a file by hand unless you want to.

Then type **`/wave`** (Codex: `$wave`) and it finds the best matches, tailors your résumé and cover
letter, and fills the application forms for you to review and submit.

## 0. What you're setting up

An AI agent (Claude Code or Codex) that reads a `knowledge-base/` of your real facts and uses it to
find jobs, tailor résumés and cover letters, research companies, draft outreach, and fill (never
submit) application forms: all of it checked by scripts, not by the agent remembering to be careful.
See `README.md` for the full picture and `CLAUDE.md` for the operating rules the agent follows every
session.

**Nothing here is specific to any one role, industry, or visa situation.** Every example in this
repo uses a placeholder; you provide the real content.

## 1. Prerequisites

- **Get the repo onto your computer.** On this repo's GitHub page, click the green **Code** button: copy the URL
  and run `git clone <that URL>`, or pick **Download ZIP** and unzip it. Your job-search facts will live in this
  folder, so keep your copy private (a private fork or just a local folder); never push your filled-in
  copy to a public repo. Open a terminal (macOS: Terminal; Windows: PowerShell) and `cd` into the
  folder. Every command in this guide runs from there. On Windows, type `py` where this guide says
  `python3`.
- **Claude Code or Codex**, whichever agent you use.
- **Python 3.9+** (from [python.org](https://www.python.org/downloads/) if `python3 --version` fails)
  with `pip`.
- **Python packages, one line:**
  `python3 -m pip install -r pipeline/job-crawler/requirements.txt weasyprint pymupdf`
  - PyYAML (from `requirements.txt`) is the crawler's one dependency.
  - weasyprint renders your résumé and cover letter to PDF. It needs a couple of system libraries
    on some platforms; see
    [weasyprint's install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation).
  - PyMuPDF (`pymupdf`) lets the résumé gate and the grounding gate read the rendered PDFs. Without
    it `resume_gate.py` fails and `verify_claims.py` refuses any dossier that holds a PDF.
- **Optional: `pdftotext`** (part of poppler: macOS `brew install poppler`, Ubuntu/Debian
  `apt install poppler-utils`). The five-pass review reads your PDF with it; without it the
  reviewers read the PDF another way.
- **Node.js 20.19+ or 22.12+** (from [nodejs.org](https://nodejs.org/)) **and Google Chrome**
  (from [google.com/chrome](https://www.google.com/chrome/)). Node runs the browser tool the agent
  uses to fill application forms, and that tool drives Google Chrome (it needs the current stable
  Chrome and does not install it). The repo already ships the tool's settings (`.mcp.json` for
  Claude Code, `.codex/config.toml` for Codex); the first time you open the repo, your agent asks
  you to approve the `chrome-devtools` server. Say yes. The first start downloads the tool with
  `npx`, so it needs internet and can take a minute. It opens its own separate Chrome window with its
  own profile, never your everyday browser.
- **About usage statistics.** The browser tool (`chrome-devtools-mcp`) sends usage statistics to
  Google by default (tool success rates, latency, environment details; see its
  [README](https://github.com/ChromeDevTools/chrome-devtools-mcp#usage-statistics)). The Codex
  config here turns that off with `--no-usage-statistics`. For Claude Code, add the same flag to
  the `args` list in `.mcp.json`, so it reads
  `"args": ["-y", "chrome-devtools-mcp@1.10.1", "--no-usage-statistics"]`, or set the environment
  variable `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1`.

Check everything at once, any time:
```
python3 scripts/doctor.py          # every check, each with a plain fix line
python3 scripts/doctor.py --fill   # only what form filling needs
```

## 2. The by-hand way: the files the agent would fill for you

Files 1 to 4 are required; files 5 and 6 are strongly recommended (`/setup` fills both when you
answer its two optional questions). Everything else in `knowledge-base/` is optional depth.

1. **`knowledge-base/01-profile-and-identity.md`**: your name, contact info, education, positioning.
2. **`knowledge-base/02-work-authorization.md`**: your legal work-eligibility status, in your own
   words. Read the file's own instructions carefully; this is the highest-stakes file in the repo.
   Talk to an immigration professional if your situation is complex. This repo is not legal advice.
3. **`knowledge-base/07-master-resume.md`**: your résumé content, including the
   `` ```canonical-facts``` `` block (fill in the `exact:` lines with your real contact info; leave
   `never:`/`number:` empty for now).
4. **`knowledge-base/12-application-answers.md`**: the autofill source of truth. §0-§2 are quick.
   **§3 (work authorization) is the one to slow down on**: it must match what you wrote in file 2,
   phrased the ways forms actually ask.
5. **`knowledge-base/11-preferences-and-conventions.md`** (strongly recommended): your two hard-stop
   categories (`CLAUDE.md` §5) and a few defaults you decide once, such as "commit locally as I go"
   or "don't commit" (`CLAUDE.md` §10).
6. **`knowledge-base/17-writing.md`** (strongly recommended): two or three things you wrote yourself,
   and any phrase you never use. This is how the agent learns to sound like you.

Check your work:
```
python3 scripts/doctor.py
python3 scripts/canon.py            # should exit 0
python3 scripts/visa_gate.py        # says plainly if §3 isn't filled in yet, or checks it if it is
```

## 3. Your résumé's source file

`resume/resume.html` is a placeholder résumé matching `knowledge-base/07-master-resume.md`. Edit it
directly (plain HTML/CSS) or let the agent do it from KB-07. Render it:
```
weasyprint resume/resume.html resume/your_name_resume.pdf
python3 scripts/resume_gate.py      # one page, filled, current employer listed
```
If it reports a short page, you probably need more real content, not smaller margins. If you have no
more, never pad: keep the short page, and the result stays an open item you decide on. See
`resume/README.md`.

## 4. Where jobs come from (and how to widen it)

Jobs come from four places, and none of them is a fixed list. The crawler reads the first three;
the agent's own web search covers the fourth:

1. **Company job boards** on Greenhouse, Lever, Ashby, SmartRecruiters, Workable and Workday. You
   don't type these in. The agent finds them:
   ```
   python3 pipeline/job-crawler/discover.py --sweep             # finds companies posting your titles
   python3 pipeline/job-crawler/discover.py --company "Acme"    # a company you name
   python3 pipeline/job-crawler/discover.py --urls -            # any job or careers links, one per line
   ```
   The sweep uses the free Common Crawl index to find companies on those systems, then keeps only
   the ones with open postings matching your titles, and writes them to `boards.yaml`. The first
   sweep is the slowest step and may take a while. The index is a free public service and is often
   slow or down; the sweep stops after its time budget and says so. So run the web-search path
   every time as well, not only when the sweep fails: search the web for companies hiring for your
   titles where you want to work, pass them to `--company`, and feed the results of
   `discover.py --queries` to `--urls -`. `/setup` and `/wave` do both for you.
2. **Free job APIs** listed in `pipeline/job-crawler/sources.yaml` (several remote-job feeds on by
   default, others you can switch on, including a free-key one for US federal jobs).
3. **The monthly Hacker News "Who is hiring" thread.**
4. **Any posting found by web search.** Workday boards come in only through links (`--urls`).
   iCIMS, Taleo, Oracle, SuccessFactors, hospital and school-district career sites and other systems
   aren't read directly. For those employers the agent finds the posting by web search, adds it to
   your tracker as a `lead` row, ranks it with everything else, and still fills the application form
   for you.

The one setting that really matters is **`pipeline/job-crawler/filters.yaml` `include_titles`**: the
job titles you want, in plain words. Where you'll work goes in the same file: `remote_ok`
(true/false), `onsite_ok` (`anywhere`, `home_metros` or `none`) and `home_metros` (the cities that
count), for example `remote_ok: true`, `onsite_ok: home_metros`, `home_metros: ["denver"]`. Read that
file's comments before touching `exclude_patterns`/`flag_patterns`: what belongs in each depends on
your own situation.

Try it:
```
python3 pipeline/job-crawler/crawl.py --hours 720   # a wide window, so a fresh setup shows results
```
The JSON output lists every source that ran, how many jobs each returned, and anything skipped and
why. `pipeline/job-crawler/README.md` has the full detail.

## 5. Optional depth (do these as you go, not all at once)

- `knowledge-base/03-career-narrative.md`: your story material.
- `knowledge-base/04-`, `05-`, `06-`: deeper experience, skills and projects the résumé pulls from.
- `knowledge-base/08-application-playbook.md`: ships filled in already; read it, don't skip it.
- `knowledge-base/10-tooling-stack.md`: ships mostly filled in; add anything extra you use.
- `knowledge-base/13-` to `16-`: advanced, useful once the basics work.
- `scripts/config.py`: optional settings (your time zone, follow-up pacing, years of experience for
  the seniority check, extra sites the account guard should block). Every value has a safe default.
  `/setup` sets `TIMEZONE` and `YOUR_YEARS_OF_EXPERIENCE` from your answers; until the years are set,
  `seniority_gate.py` says it did not check, which is not a pass. If you keep your own private copy
  of this repo on GitHub, set `PUSH_REMOTE` to that remote's name and `throughput.py` will remind you
  about commits you haven't pushed there.

## 6. Run your first wave

```
/wave
```
It picks the best matches from what the crawler found, researches each one, tailors your résumé and
cover letter, runs the five-pass review, then **fills each application form in its browser window
and hands it to you to check and submit.** See `.claude/commands/wave.md` for the procedure and
`.claude/rules/application-protocol.md` for the rules it follows.

For outreach (referrals, follow-ups), run `/outreach` in a **separate** session; see
`.claude/commands/outreach.md`.

## 7. Confirm everything is healthy

```
python3 scripts/doctor.py
python3 scripts/hooks.py --session-start
for f in scripts/*.py; do python3 "$f" --selftest >/dev/null 2>&1 && echo "ok   $f" || echo "FAIL $f"; done
(cd pipeline/job-crawler && for t in test_*.py; do python3 "$t"; done; for s in discover locations sources titles; do python3 "$s.py" --selftest; done)
```
Every selftest passes on a fresh clone, before you've written a single real fact about yourself;
they're built from fully synthetic fixtures. A failure on a completely fresh clone is a bug in the
repo, not something wrong with your setup.

## Troubleshooting

- **The agent says it can't fill the form and asks you to do it.** It shouldn't. Run
  `python3 scripts/doctor.py --fill`: it names what's missing (usually Node.js or Chrome) and always
  prints the steps to turn the browser tool on. If it says all OK and the agent still has no
  browser tool, you probably said no at the approval prompt: type `/mcp` in Claude Code and enable
  `chrome-devtools`, or quit, run `claude mcp reset-project-choices`, start `claude` again and
  approve it. Then restart the agent session. You finish a form yourself only for a named reason
  (a CAPTCHA, a login only you may do, a site whose terms ban automation, a site that rejects an
  automated submit, LinkedIn Easy Apply, or an apply-by-email posting; the full list is in
  `.claude/rules/application-protocol.md` §14). Even then the agent fills everything up to that
  point and says which reason applies.
- **The agent says it only searches certain job boards.** It shouldn't. Ask it to run
  `discover.py --sweep`, name companies you want, or ask it to web-search for postings anywhere
  (it adds them to your tracker as leads). Any company, board or posting can be added. The crawl's
  JSON output shows exactly which sources ran.
- **The crawler returns 0 matches.** In many fields (nursing, teaching, trades, retail, government,
  local employers) the usual cause is that the employers post on systems the crawler can't read, and
  the free feeds are mostly remote jobs, heavy on tech. The fix is web search: ask the agent to search
  "<title> jobs <city>" and the employers' own career pages and add each live posting as a lead row;
  it then fills those forms like any other. Also check `include_titles` matches how employers phrase
  the role, widen `--hours`, run `discover.py --sweep` for more boards, and read the JSON's `errors`
  array.
- **`ModuleNotFoundError: No module named 'yaml'`** → `python3 -m pip install PyYAML`.
- **`weasyprint` fails to import or render** → PDFs are rendered with the `weasyprint` command, so
  a working command on your PATH is enough even if `import weasyprint` fails in your Python
  (`doctor.py` says which you have). If the command fails, it needs Pango/Cairo/GDK-PixBuf: on macOS
  `brew install pango` (or `brew install weasyprint` for the command alone), on Ubuntu/Debian
  `apt install libpango-1.0-0 libpangocairo-1.0-0`.
- **`visa_gate.py` says "not filled in yet"** → correct until you finish
  `knowledge-base/12-application-answers.md` §3.
- **A gate fails on your real content** → read what it says; every gate here names the file to fix.
- **The agent won't open LinkedIn for you.** That's on purpose (`CLAUDE.md` §0.2): automated
  activity can get your account restricted. It writes the messages; you send them.
