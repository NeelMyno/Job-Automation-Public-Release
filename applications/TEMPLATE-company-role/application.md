# Application: Company · Role Title

**Status: dossier built; form NOT filled, NOT submitted.**

## Apply / Core facts

- Apply URL: [ ]
- ATS: [name] (public/no-login, embedded widget, or any quirks)
- Req/job ID: [ ] (or "none (own-site form); never invent one")
- Posted/liveness date + how corroborated: [ ]
- Location/remote policy: [ ]
- Comp: [as stated, or "not stated"; never volunteer a number]

## Form questions

<!-- Filled in once you've actually opened the form. Every field the form asks, fetched live, not
assumed. Anything sensitive (especially work-authorization) quoted CHARACTER-FOR-CHARACTER. -->

- [ ]

## Exact form answers (as filled, YYYY-MM-DD)

<!-- This section records the ANSWERS, not the method: keep it tight. -->

- [First/Last/Email/Phone as typed]
- Resume: [exact filename] ([bytes])
- Cover letter: [exact filename] ([bytes])
- [Long free-text field]: ([char count]) [one-line paraphrase; full text lives in cover-note.md]
- 🔴 Work-authorization field(s), worded EXACTLY as the form printed them:
  - "[exact printed question]" → [Yes or No: the answer knowledge-base/12-application-answers.md §3
    gives for that exact wording]
  - One question per line, in this shape: `- "<question exactly as printed>" → Yes` (or `→ No`). For
    a statement-style option, quote the option and add the Yes/No it means:
    `- "<question>" → "<option text>" (= No)`. `scripts/visa_gate.py` reads this shape and reports
    any answer it cannot read as UNVERIFIED.
- EEO/self-identification: [values used per §5b, or "not present on this form"]

## The single next action

[mirrors README. Once you have actually submitted, the agent adds a heading
`## SUBMITTED YYYY-MM-DD` (a local time with its zone may follow) with the on-screen confirmation
evidence under it; shape owned by `.claude/rules/records-format.md`]
