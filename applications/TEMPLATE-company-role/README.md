# Company: Role Title

**Status:** dossier built end-to-end; form NOT filled, NOT submitted.
**Apply:** [URL] ([ATS name], req/posting id if one exists)
**Single next action:** [one imperative sentence, never a list]

- **Role:** [what it is, team, reporting line, remote/location, years floor/ceiling if stated]
- **Comp:** [band, or "not stated"]
- **Company:** [stage, funding, size, one-line what-they-do]
- **Work authorization:** [posture, framed honestly: verified / not-found-inconclusive / offered]
- **Why strong:** [the honest fit read, 1-3 sentences]
- **Honest gap:** [optional: the counter-read, when one genuinely exists]

## Files
- `jd-<slug>.md`: the verbatim posting
- `application.md`: exact form answers + status
- `company-research.md`: what they build, funding, culture
- `referrals.md`: ranked warm-contact list + drafted outreach
- `interview-prep.md`: likely questions mapped to your real stories
- `pre-send-check.md`: the six-item gate, before anything ships
- `resume/`, `cover-letter/`: the tailored bundle
- `sources/`: verbatim snapshots for anything said about a real person

## Gates
- [ ] `python3 scripts/verify_claims.py "applications/<this-dossier>"` → exit 0
- [ ] `python3 scripts/resume_gate.py "applications/<this-dossier>"` → exit 0
- [ ] `python3 scripts/visa_gate.py` → exit 0 (or your answer is intentionally decided, see the file)

<!--
When this dossier is dead (rejected/withdrawn), replace the H1 above with a loud banner and make
the file read-only forever. Copy this shape:

# ⛔ REJECTED <date>: this dossier is READ-ONLY FOREVER

> One or two sentences: what happened, evidence pointer, and an explicit "do NOT re-open" note if
> a stale next-action existed before rejection.

---

# Company: Role Title
**Status:** ...
-->
