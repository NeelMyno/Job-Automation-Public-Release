<!--
This is file ★3 of 4, and the single most mechanically important file in the whole repo. Two exact
landmarks below are read by scripts/resume_gate.py — do not rename or restructure them:
  1. The fenced block that opens with the literal line ```canonical-facts
  2. The heading that reads exactly: ### WORK EXPERIENCE

Everything else in this file is normal prose you write freely. This is the ONE canonical résumé —
every tailored per-application version starts as a copy of this, with small deltas. Keep this one
true and complete; let the deltas live in each application's resume/tailoring.md instead.
-->

# Master Résumé

**Status:** [source of truth · last updated YYYY-MM-DD]
**Page-size target:** [US Letter / A4 — pick one and stay consistent]

---

[Your Full Name]
[Your Title / Headline]
[email] · [phone] · [portfolio URL] · [LinkedIn URL] · [City, State]

### EDUCATION

**[Degree] — [Institution]** — [YYYY–YYYY]
[GPA if you list it, honors, relevant coursework — keep this tight, one or two lines]

### SKILLS

[Category 1]: [comma-separated list]
[Category 2]: [comma-separated list]
[Category 3]: [comma-separated list]

## 🔴 CANONICAL FACTS

<!--
This fenced block is parsed by scripts/resume_gate.py on every rendered résumé — it's the mechanism
that stops a fabricated or stale claim from surviving a copy-paste into a new version. Three line
types, one per line, pipe-separated:

  never: <a string that must NEVER appear on your résumé> | <why>
  number: <a phrase that precedes a number> | <the exact correct number> | <note>
  exact: <one of: email | portfolio | linkedin | title> | <the exact required string>

Start this block genuinely empty (as below) and add a `never:` line the moment you catch yourself
(or an agent) about to ship something untrue — that's the whole point of the mechanism: it turns a
one-time correction into a permanent, mechanically-enforced guardrail. Fill in the four `exact:`
lines now, since those are just your real contact facts.
-->

```canonical-facts
exact: email | [your real email]
exact: portfolio | [your real portfolio URL, or delete this line if you don't have one]
exact: linkedin | [your real LinkedIn URL]
exact: title | [your real current title, exactly as you want it to appear]
```

### WORK EXPERIENCE

**[Employer Name] — [Your Title]** — [Mon YYYY] – Present
- [Bullet 1 — start with a verb, be specific, a real number beats a vague adjective every time]
- [Bullet 2]
- [Bullet 3]

**[Previous Employer] — [Your Title]** — [Mon YYYY] – [Mon YYYY]
- [Bullet 1]
- [Bullet 2]

<!--
Add one block per employer, most recent first. If an employer turned out to be something you can't
honestly claim (never existed, or you're not sure it should be listed) — don't just delete the
block silently. Note it here as a permanent record of what you decided and why, the same way you'd
want a "never:" line in the block above to remember a correction. An engine that can quietly forget
its own past mistakes is more dangerous than one that has none yet.
-->

### KEY PROJECTS

<!-- Optional. Bulleted, each honestly attributed to what you actually did versus a team effort. -->

- [Project name] — [one or two sentences, honest about scope]

### LICENSES & CERTIFICATIONS

[List, or delete this section if none]

### LEADERSHIP & COMPETITIONS

[List, or delete this section if none]

---

## Honesty & sourcing

<!--
For anything on this résumé that's a specific claim (a metric, a scale number, an outcome) — trace
it here to how you know it's true. This is the file a reviewer reads during the honesty-audit lens
of the five-pass review (CLAUDE.md §13.1) to confirm every number is real, not just plausible.
-->

- [Claim] → [how you know / where it's documented]

## Not on the résumé (by choice)

<!-- Things that are true but you've decided not to include, and why — keeps a future tailoring pass from re-adding something you deliberately cut. -->

## Related

- `knowledge-base/04-experience-detail.md` — the deeper reservoir this résumé's bullets get pulled from
- `knowledge-base/08-application-playbook.md` — how to tailor this per application
- `scripts/resume_gate.py` — the script that checks every rendered PDF against this file
