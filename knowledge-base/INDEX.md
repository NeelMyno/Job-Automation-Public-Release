# Knowledge Base — Index

This folder is the single source of truth about **you.** Every résumé, cover letter, outreach
message, and form-fill this engine produces traces back to a file here. It ships empty. Fill it in
once, following `SETUP.md`, and every session after that starts grounded instead of guessing.

## Read order

- **Every session, always:** this file + `11-preferences-and-conventions.md`.
- **For a résumé or cover letter:** `01-profile-and-identity.md`, `02-work-authorization.md`,
  `07-master-resume.md`, `08-application-playbook.md`.
- **For an application form:** all of the above + `12-application-answers.md`.
- **For interview prep:** `03-career-narrative.md`, `04-experience-detail.md`,
  `06-projects-portfolio.md`, `15-interview-story-bank.md`.
- **For positioning / getting found:** `14-positioning-and-visibility.md`.

## Files — the true minimum is marked ★

| # | File | What it holds | Required to get the pipeline working |
|---|---|---|---|
| ★ | `01-profile-and-identity.md` | Name, contact, education, self-positioning | **Yes — fill this first** |
| ★ | `02-work-authorization.md` | Your legal work-eligibility status, in your own words | **Yes** |
| — | `03-career-narrative.md` | Story material, your real voice, an origin story | Recommended — powers cover letters/outreach that sound like you, not a template |
| — | `04-experience-detail.md` | Deep per-employer work history, more granular than the résumé | Optional — a reservoir the résumé can pull from |
| — | `05-skills-competencies.md` | Skills/tools, bucketed by how defendable each one is | Recommended |
| — | `06-projects-portfolio.md` | Case studies / project write-ups | Recommended if your field uses a portfolio |
| ★ | `07-master-resume.md` | The single source of truth for résumé content — **includes a machine-checked "canonical facts" block scripts verify every rendered résumé against** | **Yes** |
| — | `08-application-playbook.md` | The tailoring methodology — ships pre-filled, not blank; read it, don't skip it | Ships ready to use |
| — | `09-current-search.md` | Your live targets and situational context right now | Optional, changes constantly |
| — | `10-tooling-stack.md` | What tools/MCP servers power your crawl + research | Optional — the crawler works without any of these |
| ★ | `11-preferences-and-conventions.md` | How you like things done, your ratified-decision log | **Yes — do this during setup, it decides several defaults for you** |
| ★ | `12-application-answers.md` | THE AUTOFILL SOURCE OF TRUTH — every exact value an agent may type into a real form | **Yes, before any form-filling** |
| — | `13-strengths-and-market-position.md` | A one-time adversarial audit of what's genuinely rare about you | Optional, advanced |
| — | `14-positioning-and-visibility.md` | How to get *found*, not just apply — referrals, visible work | Optional, high-value once the basics work |
| — | `15-interview-story-bank.md` | Your reusable STAR-format interview stories | Recommended once you have a real interview scheduled |

**The four ★ files are the true minimum.** With just those four filled in, the résumé/cover-letter
tailoring engine, the honesty gates, and the form-fill autofill all work end to end. Everything else
deepens the output; nothing else is required to start.

## 🔴 Read first (edit this section yourself once you've made a decision)

Nothing yet — this is where you'll log corrections to your own knowledge base as you make them, the
same way a decision log works anywhere else in the repo. See `ops/decisions/` for the heavier,
locked-decision version of the same idea.

## ⚠ Open questions

Nothing yet. When a fact about you is genuinely unresolved (a number you haven't confirmed, a story
you haven't decided how to tell), list it here rather than letting an agent guess at it.

## Maintenance rule

When a fact about you changes — a new role, a new project, an update to your work-authorization
status — update the relevant file **the same session you learn it**, and update this table's
one-line description if the file's scope changed. A knowledge base that's a week stale produces a
résumé that's a week stale.
