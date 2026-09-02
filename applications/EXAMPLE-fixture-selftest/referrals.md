# Acme Corp: Design Lead · referral pack (SELFTEST FIXTURE)

**This whole dossier is synthetic.** Every name, company, and quote below is invented, built only
so `python3 scripts/verify_claims.py --selftest` has something to run against on a fresh clone with
no real user data. No person named here is real. Copy `applications/TEMPLATE-company-role/` to
start a real dossier. Never this one.

---

## The ranked list

| # | Name | Title | Why them |
|---|---|---|---|
| 1 | **Jordan Rivera** | Design Lead, Acme Corp | Owns the team this role reports into. |
| 2 | **Sam Okafor** | Engineering Manager, Acme Corp | Cross-functional partner on the same team. |

## The messages (ready to paste)

### 1. Jordan Rivera, Design Lead at Acme Corp

**Profile:** https://example.com/in/jordan-rivera-fixture

**Connection note**
> Hi Jordan, applying for the Design Lead role at Acme Corp. I build design systems and ship the front end myself.

**Direct message (Use InMail: NO, because a free connection note is available)**
> Thanks for connecting. You said "Loved your talk on design systems, especially the bit about shared tokens across three product lines" after the meetup, which is why I wanted to reach out directly. I'm applying for the Design Lead role and would value your read on the team.

### 2. Sam Okafor, Engineering Manager at Acme Corp

> OPERATOR-VERIFY: this note assumes Sam has been on Acme Corp's design-adjacent team for about
> two years, based on an unconfirmed profile read. Confirm before sending.

**Connection note**
> Hi Sam, applying for the Design Lead role and would value a referral if my background fits the team's bar.

---

## Appendix: how this fixture works (not sendable copy)

This section sits after the level-2 heading that follows `## The messages`, so
`extract_referral_sections()` must exclude it from the sendable sweep once that section ends. It
exists to prove the split is a general "stop at the next `## ` heading," not a hardcoded name: an
earlier version of this parser only stopped at one specific hardcoded heading, so trailing prose in
any dossier that used a different closing heading (or none) leaked through as if it were outbound
copy.

As a live check of that: the line below is deliberately unsourced and must never be read as
sendable copy.

> Note to whoever edits this fixture: "there is no stored source for this sentence anywhere in this
> dossier," and if `--selftest`'s "[live] the real dossier is clean" assertion ever goes red because
> of this paragraph, the regression is in the next-heading cut inside `extract_referral_sections()`,
> not in this file.
