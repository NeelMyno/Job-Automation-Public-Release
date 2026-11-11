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
assumed. Anything sensitive (especially work-authorization) quoted CHARACTER-FOR-CHARACTER.
One field per line: `- <question as printed> (required; options: Yes, No)`. This list holds no
answers; they go in the next section. -->

- [ ]

## Exact form answers (as filled, YYYY-MM-DD)

<!-- This section records the ANSWERS, not the method: keep it tight. -->

- [First/Last/Email/Phone as typed]
- Resume: [exact filename] ([bytes])
- Cover letter: [exact filename] ([bytes])
- [Long free-text field]: ([char count]) [one-line paraphrase; full text lives in cover-note.md]
- [Work-history entry, if the form has them]: [title, employer, dates as the résumé prints them; description = that role's bullets]
- 🔴 Work-authorization field(s), worded EXACTLY as the form printed them:
  - "[exact printed question]" → [Yes or No: the answer knowledge-base/12-application-answers.md §3
    gives for that exact wording]
  - One question per line, in this shape: `- "<question exactly as printed>" → Yes` (or `→ No`). The
    value is a bare Yes or No, or the exact wording recorded in §3. For a statement-style option,
    quote the statement and write what it means for you: `- "<statement as printed>" → No`.
    `scripts/visa_gate.py` reports anything else as UNVERIFIED, so a person looks at it.
  - A form that asked nothing about work authorization gets this one line, exactly:
    `- No work-authorization question on this form.`
- EEO/self-identification: [values used per §5b, or "not present on this form"]

## The single next action

[mirrors README. Once you have actually submitted, the agent adds a heading
`## SUBMITTED YYYY-MM-DD` (a local time with its zone may follow) with the on-screen confirmation
evidence under it; shape owned by `.claude/rules/records-format.md`]
