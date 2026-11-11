#!/usr/bin/env python3
"""visa_gate.py: the work-authorization answer gate.

WHY THIS EXISTS
Work-authorization / sponsorship answers are the single highest-stakes category on a job
application: a wrong one isn't just a lost offer, it can be caught by a background check after
you've already started a job. Different employers phrase the same underlying question differently,
and the honest answer can differ by phrasing: "are you authorized to work without sponsorship"
and "will you ever need sponsorship" are not always the same yes/no for the same real person. Three
distinct question shapes recur across real ATS forms, and blurring them together is the defect this
gate exists to catch.

THE RULE IT ENFORCES (knowledge-base/12-application-answers.md §3)
This script reads your own answers from a fenced ```work-authorization``` block in that file; it
does not hardcode anyone's specific situation. Fill in that block once, honestly, and this gate
checks every dossier's recorded answers against it. If the block isn't filled in yet, the gate says
so plainly and checks nothing, rather than silently assuming a default that might be wrong for you.

The three question classes:
  1. "Are you legally authorized to work in the United States?"                  -> authorized-now
  2. "Do you require sponsorship TO BEGIN employment / now / at time of hire?"    -> sponsorship-to-begin
  3. "Will you NOW OR IN THE FUTURE require sponsorship?"                        -> sponsorship-now-or-future

A fourth class, "authorized to work WITHOUT RESTRICTION" (no sponsorship word, no timeframe word),
is a rephrasing of #1 whose honest answer depends on whether your authorization is itself tied to a
specific status/employer (see the `restricted-authorization` key in the same KB block); it is NOT
simply the opposite of your #1 answer, which is exactly the subtlety a naive "just invert it" rule
gets wrong for some users and not others.

TWO OPTIONAL MAPPINGS IN THE SAME BLOCK (both yours, both off until you write them)
  * `also-accept`: a third `|` field on a class line, e.g.
        sponsorship-now-or-future: NO | reason | also-accept: YES
    Your answer for that class changed, and you decided NOT to edit dossiers already built or forms
    already submitted. The gate then accepts the old answer on records, while the configured answer
    stays the one an agent types on every new form (the fill step's read-back enforces that).
  * `wording`: a question printed a particular way gets its own answer, because the honest answer
    follows the question AS PRINTED, e.g.
        wording: for any employer in the us; without employer support => YES | reason
    Phrases are separated by `;` and matched case-insensitively against the question text only. When
    one matches a work-authorization question, its answer is required there as printed (no polarity
    flip), and the plain class answer still governs every other wording.

CITIZENSHIP QUESTIONS ("Are you a U.S. citizen?")
  Your block has no citizenship line, so the gate works it out in this order:
    1. a `wording:` line naming the phrase the form printed wins. One line per status, because a
       person can be one and not the other (a permanent resident is not a citizen), e.g.
           wording: u.s. citizen; us citizen; citizen of the united states => NO | reason
           wording: permanent resident; green card => YES | reason
       A question naming both with "or" ("a citizen or permanent resident?") is Yes if either is. A bare
       "citizen" in such a question takes the answer of your line for U.S. citizen.
    2. if your answers show you are not one (you are not authorized now, you need sponsorship, or
       your authorization is restricted), the required answer is No;
    3. otherwise the gate cannot know, so the answer is UNVERIFIED (exit 1) until you add a line.
  An open "country of citizenship" field has no Yes or No and is left alone. A Yes or No answer to a
  question about citizenship of some OTHER country is UNVERIFIED unless a `wording:` line names it:
  the gate has no rule for it, and silence would read as a pass.

WHEN THE GATE IS NOT SURE WHAT IT READ
  The gate starts from what it can read, never from what it recognises as wrong. The topic test is wide:
  a line that mentions a visa, immigration, a petition, sponsorship, being authorized, eligibility or the
  right to work, work rights, accepting employment, legal status to work, being lawfully present,
  citizenship, permanent residence, a green card, a foreign or U.S. national, a work permit or a
  restriction is on the topic. The reading test is narrow: only a known question shape about YOU, read
  whole, is checked against your answers. "Are you authorized to work in the US without a visa?" is not
  the plain authorized question with words added; anything after the place name makes it UNVERIFIED.
  A conditional opener about an offer ("If we offer you a position, ...") is set aside before reading.
  The words "work status", "employer support" (with a work word on the line), "immigration support" and "work permit" put a line on the
  topic too, and "employer support for your work status" reads as the sponsorship question.

  THE WORK-AUTHORIZATION SECTION. Under a heading that names work authorization or sponsorship (to the
  next heading of its level), or under a list label that names it and ends in ':' (the template's
  "Work-authorization field(s), worded EXACTLY as the form printed them:", over the lines indented below
  it), every `- "<question>" -> <value>` line whose value holds a Yes or No is one of these answers by
  where it was written. It is read against your answers or it is UNVERIFIED; it is never silent. A line
  there with no Yes or No yet ("-> TBD", "-> [Yes/No]", no value) records no answer, so it is neither
  read nor counted; fill it in before you rely on the result. A question there with no rule at all
  ("Are you over 18?") is UNVERIFIED, not on the silence list: the person who wrote it filed it as a
  work-authorization answer, and only a person can say whether it belongs there.

  A FORM-INVENTORY LINE (the "## Form questions" list) that gives only the options, "(required; options:
  Yes, No)", "[Yes/No]", "(Yes / No)" or "options: Yes, No", records no answer yet. It is skipped, so it
  never makes a file CLEAN on its own (with nothing else read the file stays exit 3). A real answer after
  the list on the same line ("(options: Yes, No) -> No") is still read.

  SILENCE NEEDS A REASON. A line on the topic that holds the word Yes or No anywhere always ends as OK,
  WRONG or UNVERIFIED. It is silent only when: the Yes or No sits inside a pristine placeholder
  ("[Yes/No]", "(dropdown: Yes / No)") or a "<...>" template slot; the line is exactly the record that
  the form had no such question ("No visa question on this form"); or it is a plain sentence about the
  employer ("Globex offers no sponsorship for contract roles") with no question and no value. A Yes or
  No anywhere but the value slot is UNVERIFIED: "We answered Yes to ...", "No - <question>",
  "<question> (dropdown: Yes)", "<question> -> No (field note)", a second question before the answer. An answered line on the topic that is not on such a shape is
  UNVERIFIED (exit 1), never clean: a negated question ("Are you a non-U.S. citizen?"), one about
  somebody else ("the spouse of a U.S. citizen"), the past, another country named in a way it cannot
  place, a "now or ..." whose second half names no future, or any phrasing it has no rule for.
  To-begin is one of those readings: a question only counts as to-begin when it names the moment and
  nothing further. A `wording:` phrase applies only on a shape it can read, or when your phrase is the
  whole question after "Are you" or "Do you". To settle a line the gate cannot read, add the form's own
  words, the negation included: "wording: non-u.s. citizen => NO | reason".

NOT CONFIGURED YET (a fresh clone)
  The gate says so plainly and never crashes. When no file it was given records a
  work-authorization answer, it exits 3 (NOT CHECKED): nothing was verified, so it must never
  exit 0, which a reader or a hook would take as proof. If any file DOES record an answer, that
  answer cannot be checked, and the gate exits 1 (UNVERIFIED).

THE RECORD SHAPE (applications/TEMPLATE-company-role/application.md, .claude/rules/records-format.md §6)
    - "<question exactly as printed>" → Yes
  The gate does not interpret English. On a work-authorization line it concludes only from:
    1. a bare Yes or No as the whole value, with only markdown and punctuation around it (bold,
       backticks, a quote mark, a list dash, a trailing period, surrounding quotes, an arrow);
    2. exactly one option carrying a mark (`[x] Yes [ ] No`, or a checked box from Unicode) whose text
       is a bare Yes or No;
    3. a value exactly equal to a `wording:` phrase you recorded in the same block;
    4. a value exactly equal to your free-text answer: the body under "If the field is free text instead
       of yes/no" in the same §3. Compared after collapsing whitespace, trimming surrounding quotes,
       markdown and a trailing period, and ignoring case; one word different is not it. It reads as OK
       (your own words, pasted as is) only on a question that is not a yes/no class. On an authorized,
       sponsorship or citizenship question it is UNVERIFIED: that form offered a Yes or No, and the
       paragraph does not say which was picked. A body still in square brackets (the template's
       placeholder), an empty body or a missing heading records no free-text answer.
  Everything else is UNVERIFIED (exit 1): "N", "Not authorized", "Yes, but ...", "(No)", "[No]", a ticked
  statement, two options with no mark. The value may sit on the same line or on the next line of content
  (blank lines and `>` skipped). A placeholder (`[Yes/No]`, `TBD`) or nothing at all records no answer.
  Before any line is read, invisible format characters (Unicode Cf: soft hyphen, zero-width space and
  joiners, word joiner, byte-order mark, bidi marks) are removed and every other space character (Unicode
  Zs, such as the no-break space) becomes a plain space, in the question and the value alike.

USAGE
    python3 scripts/visa_gate.py                     # every applications/*/application.md
    python3 scripts/visa_gate.py <path> ...          # specific files (used by the hook)
    python3 scripts/visa_gate.py --selftest          # a fixed, fictional regression suite
Exit 0 = clean: at least one answer was read, and every recorded answer was checked against your
configured rule (the count is printed). Exit 1 = at least one wrong or missing answer, a recorded
answer whose Yes/No the gate cannot read (UNVERIFIED), or recorded answers that cannot be checked
because §3 is not filled in. Exit 3 = NOT CHECKED: no work-authorization answer was read at all
(§3 not filled in yet, no dossier, or dossiers with no answers yet, as on a fresh clone).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parents[1]
KB_ANSWERS = REPO / "knowledge-base" / "12-application-answers.md"

# question classification
# Order matters: FUTURE is tested first, because "now or in the future" also contains "now",
# and mis-routing #3 to the #2 rule is exactly the blur this gate exists to prevent.

FUTURE = re.compile(
    r"now\s*(?:,|/|\s)?\s*or\s*(?:at\s+any\s+point\s+)?in\s+the\s+future"
    r"|now\s*/\s*(?:some\s?day|later|future)"
    r"|(?:ever|at any (?:time|point))\s+(?:need|require)"
    r"|future\w*\s+(?:need|require|sponsor)"
    r"|(?:need|require)\w*[^.?\n]{0,40}(?:in\s+the\s+future|future\s+immigration)"
    # Any plain future word. "Do you currently, or will you in the future, require sponsorship?" has
    # a comma where the patterns above want a space, and fell through to the "currently" rule below.
    r"|\bfuture\b|\bgoing\s+forward\b|\beventually\b|\bat\s+(?:a\s+later\s+date|some\s+point)\b"
    # A word that reaches past today. "either now or later", "now or ever", "now or down the road".
    r"|\bever\b|\blater\b|\bdown\s+the\s+road\b|\bany\s?time\b|\bat\s+any\s+point\b|\bsome\s?day\b"
    r"|\bexpect\w*|\banticipat\w*",
    re.I,
)
# The words that actually name a moment. An inverted question ("work WITHOUT sponsorship") only
# counts as the to-begin question when one of these is present; see `classify`.
BEGIN_TIME = (r"to\s+begin|to\s+commence|to\s+start|\b(?:begin|start)\w*\s+work|\bstart\s+of\b|"
              r"at\s+(?:the\s+)?(?:time\s+of\s+hire|beginning)|at\s+hire|upon\s+(?:hire|hiring|start)|"
              r"first\s+day|day\s+one|currently|presently|right\s+now|at\s+this\s+time|\bnow\b|\btoday\b|"
              r"\bimmediately\b")
TIMEFRAME = re.compile(BEGIN_TIME, re.I)
# A moment joined to something further ("now or ...", "to begin or ..."). If a future word is named
# FUTURE has already taken the line; what reaches here names none, so to-begin cannot be assumed.
TIME_FURTHER = re.compile(
    r"(?:" + BEGIN_TIME + r")(?:[^?\n]*?\b(?:or|and|but)\b|\s*/\s*(?!\s*(?:" + BEGIN_TIME + r")))", re.I)
# "Employer support for your work status" is the sponsorship question in other words. Only that full
# phrase counts: "employer support" alone could mean a relocation budget or a training allowance.
EMPLOYER_SUPPORT = (r"\bemployer\s+support\s+(?:for|with)\s+(?:your\s+|my\s+)?"
                    r"(?:work|immigration|visa|employment)\s+(?:status|authori[sz]ation|eligibility)\b")
SPONSOR = re.compile(r"\bsponsor\w*|\bvisa\s+(?:status|support)|" + EMPLOYER_SUPPORT, re.I)
# The narrower word the classifier reads as a sponsorship question. "Do you need to change your visa
# status?" is on the topic, but it is not asking whether an employer has to sponsor you.
SPONSOR_ASK = re.compile(r"\bsponsor\w*|\bvisa\s+support\b|" + EMPLOYER_SUPPORT, re.I)
AUTHORIZED = re.compile(
    r"legally\s+authori[sz]|authori[sz]\w*\s+to\s+work|authori[sz]\w*\s+for\s+employment|work\s+authori[sz]"
    r"|\bright\s+to\s+work\b|\beligible\s+(?:to\s+work|for\s+employment)\b"
    r"|\b(?:legally|lawfully)\s+(?:\w+\s+){0,3}?(?:work|employ)"
    # "Can you work" and friends only count when the line is plainly about the legal right: "Can you
    # work weekends?" and "Are you able to work on site?" are not this question.
    r"|\b(?:can\s+you|could\s+you|able\s+to|permitted\s+to|allowed\s+to|entitled\s+to)\s+(?:\w+\s+){0,2}?work\b"
    r"(?=\s+(?:(?:legally|lawfully)\s+)?(?:in|within)\s+(?:the\s+)?"
    r"(?:(?-i:U\.?S\.?A?)\b|us\b|united\s+states|america\b|this\s+country)"
    r"|[^.?\n]*(?:legal|lawful|sponsor|restrict))",
    re.I,
)
NEED = re.compile(r"requir|need|\bmust\b|ha(?:ve|s)\s+to\b", re.I)
RESTRICT = re.compile(r"restrict|limitation|unlimited", re.I)
# "Without restriction" in its other spellings. Reads as the restricted-authorization answer.
RESTRICT_INVERTED = re.compile(
    r"\bunrestricted\b|\bunlimited\b|\bwithout\b[^.?\n]{0,60}\b(?:restrict|limitation)"
    r"|\bno\s+(?:\S+\s+){0,2}(?:restriction|limitation)s?\b|\bfree\s+(?:of|from)\s+(?:\S+\s+){0,2}restriction",
    re.I,
)
# Words that turn "are you authorized" into a different question: how long, on what terms.
AUTH_QUALIFIED = re.compile(
    r"\blimit|condition|temporar|expir|permanent|indefinite|ongoing|long[-\s]term|\bfuture\b|tied\s+to"
    r"|specific\s+employer|any\s+employer|end\s+date|\bonly\b", re.I)
# "Are you authorized to work, or do you need sponsorship?": Yes and No have no single meaning.
AUTH_OR_SPONSOR = re.compile(r"authori[sz]\w*\b[^?]*\b(?:or|and)\b[^?]*(?:requir|need)[^?]*sponsor", re.I)
# A line about the right to work that names neither of the patterns above.
WORK_LINE = re.compile(
    r"\b(?:work\w*|employ\w*|job)\b[^.?\n]*\b(?:restrict|authori[sz])|\b(?:restrict|authori[sz])\w*[^.?\n]*\b(?:work\w*|employ\w*|job)\b"
    r"|\bwork\s+permit\b|\bpermission\s+to\s+work\b|\bemployment\s+eligib",
    re.I)

# Readings the gate must not guess at. Each one means a Yes or No here is not what it looks like.
THIRD_PARTY = re.compile(
    r"\b(?:spouse|husband|wife|partner|fianc\w*|married|parents?|mother|father|child(?:ren)?|son|daughter"
    r"|sibling|brother|sister|relatives?|family|dependents?|guardian|household|someone|anyone"
    r"|another\s+person)\b", re.I)
PAST = re.compile(
    r"\b(?:have|has|had)\s+(?:you\s+)?(?:ever\s+|previously\s+)?(?:\w+\s+)?"
    r"(?:been|held|required|needed|received|had|sponsored|obtained)\b"
    r"|\bdid\s+you\b|\bwere\s+you\b|\bpreviously\b|\bin\s+the\s+past\b|\bprior\s+employer\b|\bformer(?:ly)?\b",
    re.I)
DOUBLE_NEGATIVE = re.compile(
    r"\b(?:unable|ineligible|unauthori[sz]ed|cannot|can\s+not|can['\u2019]t|could\s+not|couldn['\u2019]t|lack\w*"
    r"|false\s+that|untrue|not\s+true|never|no\s+longer)\b"
    r"|\bnot\s+(?:\w+\s+)?(?:authori[sz]ed|eligible|able|permitted|allowed|entitled)\b"
    r"|\bnot\s+in\s+the\s+future\b|\b(?:but|and|or)\s+not\b|\bnot\s+(?:now|currently|today|right\s+now|yet)\b", re.I)
# "Do you not require sponsorship?" is answered Yes by people who mean opposite things.
NEGATIVE_QUESTION = re.compile(
    r"\b(?:do|does|did|will|would|are|is|can|could|have|has|should)\s+(?:you|they)\s+not\b"
    r"|\b\w+n['\u2019]t\s+you\b", re.I)
# Work somewhere else ("authorized to work in Canada"): this gate's answers are about the US.
WORK_ELSEWHERE = re.compile(
    r"(?i:\b(?:work\w*|employ\w*|authori[sz]\w*|sponsor\w*)\s+in\s+(?:the\s+)?)"
    r"(?!(?i:united\s+states|u\.?s\.?a?\b|america\b|states?\b|this\b|that\b|our\b|your\b|any\b|all\b|each\b|one\b"
    r"|person\b|office\b|the\b|an?\b))[A-Z]"
    r"|(?i:\b(?:work\w*|employ\w*|authori[sz]\w*)\b[^?]*\b(?:outside|other\s+than)\b)")

# Multi-question lines are real and common: "Worked here before: **No** · Authorized: **Yes**".
# Matching across the whole line pairs the wrong question with the wrong answer. The `;` separator
# was added after a real multi-dropdown line: `"restrictions?"=**No**; **"...sponsorship...?" =
# "Yes,..."**; "country?"=**United States**` - split on nothing, so the cut-at-first-`?` landed on the
# RESTRICTIONS question and read its **No** as the sponsorship answer, a false violation on the
# highest-severity class.
SEGMENT = re.compile(r"\s+·\s+|\s*\|\s*|\s*;\s*|\.\s+(?=[\"“])")

# Conditional analysis is not a recorded answer. "If their form asks only about starting, my honest
# answer is **No**" is correct reasoning about a form, not a value that was submitted.
CONDITIONAL = re.compile(r"\bif\b[^.\n]{0,60}\b(?:asks?|uses?|phrases?|offers?|form)\b", re.I)


Q_AUTH, Q_BEGIN, Q_FUTURE = "authorized-now", "sponsorship-to-begin", "sponsorship-now-or-future"
Q_CITIZEN = "citizenship-status"
# A value exactly equal to your own `wording:` phrase on a prompt the gate cannot classify: read and
# counted, with nothing to compare it to.
Q_SETTLED = "settled-by-your-wording"
# About work authorization, sponsorship or citizenship, but the gate cannot say which question it is.
# An answer here is UNVERIFIED unless a `wording` line names the phrase as printed.
Q_UNSURE = "unclassified"
SEVERITY = {Q_AUTH: "HIGH", Q_BEGIN: "HIGH", Q_FUTURE: "CRITICAL", Q_CITIZEN: "HIGH", Q_UNSURE: "HIGH",
            Q_SETTLED: "HIGH"}

# Some employers ask the inverse: "Are you authorized to work WITHOUT sponsorship, now or in the
# future?" or "...without restriction?" A gate that demands a lie is worse than no gate at all, so
# every inverted phrasing is handled explicitly rather than assumed away.
INVERTED = re.compile(
    # "without [the need for] [any] [employer/visa] sponsorship" - a real employer's phrasing,
    # "without the need for sponsorship", slipped the earlier narrower regex (which only allowed
    # "without (requiring) (visa) sponsor"), so an honest No was flagged as a violation and the gate
    # demanded the answer be flipped to a lie.
    # "without employer-sponsored visa support" slipped it too: the hyphen in "employer-sponsored"
    # broke `employer\s+`, so an honest No read as the hard-stop question answered No.
    r"without\s+(?:\S+\s+){0,5}?(?:\S+-)?sponsor\w*"
    r"|without\s+(?:\S+\s+){0,2}?employer\s+support"
    r"|without\s+restriction"
    r"|fine\s+without\b"
    r"|(?:\bnot|n['\u2019]t)\s+(?:\S+\s+){0,2}?(?:require|need)\w*\s+(?:\S+\s+){0,3}?sponsor\w*"
    r"|sponsor\w*\s+(?:is\s+|are\s+)?not\s+(?:required|needed|necessary)"
    r"|\bno\s+(?:\S+\s+){0,2}?sponsor\w*",
    re.I,
)

# "The form never asked" is a RECORD, not a gap. A dossier that states plainly that no
# work-authorization question was on the form is reporting a positive, checkable fact about the
# form; treating that as a missing answer trains people to stop trusting the gate.
NO_QUESTION = re.compile(
    r"(?:\bno\b|\bnot\s+present\b|\bnone\b|\babsent\b|\bdid\s*n[o']?t\s+ask\b|\bdoes\s+not\s+ask\b)"
    r"[^.\n]{0,60}?"
    r"(?:visa|work[-\s]?auth\w*|sponsorship|immigration)"
    r"[^.\n]{0,40}?"
    r"(?:question|section|field|prompt|phrasing)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship)[^.\n]{0,30}?(?:question|section|field)(?:s|\(s\))?\s*[:\-][^.\n]{0,40}?"
    r"(?:\bnot\s+present\b|\bnone\b|\bno\b|\bn/a\b)"
    r"|(?:visa|work[-\s]?auth\w*|sponsorship|immigration)[^.\n]{0,30}?[:\-\u2014][^.\n]{0,20}?"
    r"(?:\bno\b|\bnone\b|\bwithout\b|\bnot\b)[^.\n]{0,20}?(?:question|section|field|prompt)",
    re.I,
)

# The citizenship phrasing of the same underlying question ("Are you a US Citizen or Green Card
# holder?") is a work-authorization record even though it names neither "visa" nor "sponsor".
CITIZENSHIP = re.compile(r"\bnon-?citizen\b|\b(?:u\.?s\.?\s+)?citizen(?:ship)?\b|\bgreen\s*card\b|\bpermanent\s+resident\b", re.I)
# An open field ("Country of citizenship", "Which country are you a citizen of?") has no Yes or No.
CITIZEN_OPEN_FIELD = re.compile(r"^\W*(?:what|which)\b|\bcountry\s+of\s+citizenship\b", re.I)
_US_NAME = r"(?:u\.?\s?s\.?a?\.?|united\s+states(?:\s+of\s+america)?|america)"
# Citizenship of somewhere ELSE has no fixed answer, and treating it as the claim below would demand
# a false one, so it is left alone. It has to be positively that: "other than" on its own is not
# ("Are you other than a U.S. citizen?" is the claim turned around).
CITIZEN_ELSEWHERE = re.compile(
    r"\bcitizen(?:ship)?\s+(?:of|in)\s+(?:an?|any|another|some)\s+(?:\w+\s+){0,2}?(?:country|nation)\b"
    r"|\bcitizen(?:ship)?\s+(?:\w+\s+)?outside\b"
    r"|\bcitizen(?:ship)?\s+of\s+(?:the\s+)?(?!" + _US_NAME + r"\b)(?-i:[A-Z][a-z]+)", re.I)
# The citizenship questions the gate can read for certain, whole: "Are you a U.S. citizen?", "Are you
# a citizen or lawful permanent resident of the U.S.?", "US Citizen or Green Card holder", "Do you
# hold a green card?". Anything else carrying these words is UNVERIFIED, because the words alone say
# nothing about who is being asked or which way ("Will you become", "live with", "on behalf of").
_US_ADJ = r"(?:u\.?\s?s\.?a?\.?|united\s+states|american)"
_CITIZEN_ITEM = r"(?:" + _US_ADJ + r"\s+)?citizen"
_RESIDENT_ITEM = (r"(?:(?:lawful|legal)\s+)?(?:" + _US_ADJ + r"\s+)?permanent\s+resident"
                  r"|(?:" + _US_ADJ + r"\s+)?green\s*card(?:\s+holder)?")
_STATUS_ITEM = r"(?:" + _CITIZEN_ITEM + r"|" + _RESIDENT_ITEM + r")"
_STATUS_OF_US = r"(?:\s+(?:of|in)\s+(?:the\s+)?" + _US_NAME + r")?"
_STATUS_LIST = (r"(?:an?\s+)?" + _STATUS_ITEM + _STATUS_OF_US
                + r"(?:\s*(?:(?:and\s*/\s*)?or|/)\s*(?:an?\s+)?" + _STATUS_ITEM + _STATUS_OF_US + r")*")
CITIZEN_SHAPE = re.compile(
    r"^(?:(?:are\s+you\s+(?:(?:currently|presently|now|legally)\s+)?|i\s+am\s+|i['\u2019]m\s+))?"
    + _STATUS_LIST + r"\.?$"
    r"|^do\s+you\s+(?:(?:currently|now)\s+)?(?:hold|have|possess)\s+" + _STATUS_LIST + r"\.?$", re.I)
STATUS_ITEM = re.compile(_STATUS_ITEM, re.I)
# Which of your wording phrases stands for each status when a form prints the bare word.
PLAIN_CITIZEN = re.compile(r"^(?:" + _US_ADJ + r"\s+)?citizen(?:\s+of\s+(?:the\s+)?" + _US_NAME + r")?$", re.I)
PLAIN_RESIDENT = re.compile(r"^(?:" + _RESIDENT_ITEM + r")$", re.I)
# Immediately before a phrase, these turn it around: "non-U.S. citizen", "not a U.S. citizen",
# "former permanent resident". The window stops at the clause, and at three words.
NEGATED_BEFORE = re.compile(
    r"(?:\bnon[-\s]*|\bex-|\b(?:not|no|never|neither|nor|without|former(?:ly)?|lack\w*|\w+n['\u2019]t)\b"
    r"(?:[\s-]+[\w.'\u2019-]+){0,3}[\s-]*)$", re.I)
# Citizenship claims that are not the plain "are you one": by birth, of two countries, or a list of
# statuses where the rule for one cannot settle the others.
CITIZEN_QUALIFIED = re.compile(
    r"\bdual\b|\bnaturali[sz]ed\b|\bborn\b|\bby\s+birth\b|\bnoncitizen\b|\bnon-citizen\b"
    r"|citizen\w*\s*,\s*(?!or\b)[^?]*\bor\b", re.I)


# an already-shipped answer you've decided not to correct
# This does NOT relax the gate and CANNOT be used to pre-authorize a wrong answer. It exists for
# one shape only: an application that is ALREADY SUBMITTED, whose recorded answer contradicts your
# own KB §3, where the only remaining question is whether to go back and correct the employer's
# record: a call that belongs to you and to nobody else.
#
# Four walls, each pinned by a selftest case:
#   1. The marker must name an ADR, so the decision is auditable and attached to a written record.
#   2. It only applies where the dossier records a SUBMITTED application; an unsent form's wrong
#      answer can never be pre-authorized.
#   3. It is LINE-SCOPED (the flagged line, or the line right after); it can never blanket a file.
#   4. The finding still PRINTS, as an acknowledged note carrying its ADR. Nothing goes silent.
#
#     <!-- visa:decided ADR-0007 - settled 2026-01-01: the posting closed, nothing left to change -->
DECIDED = re.compile(r"<!--\s*visa:decided\s+(ADR-\d{4})\s*(?:\u2014|--|-)\s*(.*?)\s*-->", re.I)
# A real submission record starts its own line: a `## SUBMITTED` heading, or a status line carrying a
# date. The word anywhere in prose is not one: the template's own instruction line mentions the
# `## SUBMITTED YYYY-MM-DD` heading, and "Status: NOT SUBMITTED" or a sibling role's date is no record.
SUBMITTED = re.compile(
    r"^[ \t>#*_\-\u2705]*(?:status\s*\**\s*[:\-]\s*[*_ \t\u2705]*)?"
    r"(?:submitted|applied(?:[_ ]on)?)\b[*_: \t\-\u2014]*(?:on\s+)?20\d\d-\d\d-\d\d"
    r"|^\#{1,6}[ \t\u2705]*(?-i:SUBMITTED)\b(?![ \t]+YYYY)"
    r"|\u2705[ \t]*(?-i:APPLIED|Applied|SUBMITTED)\b",
    re.I | re.M)


def is_submitted(text: str) -> bool:
    """Does this dossier record its own submission? An HTML comment is instructions, never a record."""
    return bool(SUBMITTED.search(re.sub(r"(?s)<!--.*?-->", "", text)))


def load_expected() -> dict | None:
    """Read your own EXPECTED/RATIONALE/restricted-authorization values from the KB file.

    Returns None if the file is missing or the fenced block isn't (fully) filled in yet; the
    caller must treat that as "not configured", never as license to guess a default.
    """
    if not KB_ANSWERS.is_file():
        return None
    text = KB_ANSWERS.read_text(encoding="utf-8", errors="replace")
    # An HTML comment is instructions, never an answer. A filled-in example inside one would otherwise
    # be read as yours. An unclosed comment hides the rest of the file, so it reads as not configured.
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.S)
    m = re.search(r"```work-authorization\n(.*?)```", text, re.S)
    if not m:
        return None
    expected: dict[str, str] = {}
    rationale: dict[str, str] = {}
    also: dict[str, set[str]] = {}
    wording: list[tuple[list[str], str, str]] = []
    restricted: bool | None = None
    key_map = {
        "authorized-now": Q_AUTH,
        "sponsorship-to-begin": Q_BEGIN,
        "sponsorship-now-or-future": Q_FUTURE,
    }
    placeholder = re.compile(r"^\[.*\]$")
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        if key == "wording":
            # wording: phrase one; phrase two => YES | reason
            lhs, arrow, rhs = rest.partition("=>")
            if not arrow:
                continue
            ans, _, why = rhs.strip().partition("|")
            ans = ans.strip().upper()
            phrases = [ph.strip().lower() for ph in lhs.split(";") if ph.strip()]
            if ans in ("YES", "NO") and phrases and not placeholder.match(lhs.strip()):
                wording.append((phrases, ans, why.strip() or "(no reason recorded)"))
            continue
        fields = [f.strip() for f in rest.split("|")]
        val = fields[0].upper()
        reason = fields[1] if len(fields) > 1 else ""
        extra = " ".join(fields[2:])
        if placeholder.match(val) or val not in ("YES", "NO"):
            continue  # still a template placeholder like "[YES/NO]", not filled in
        if key in key_map:
            expected[key_map[key]] = val
            rationale[key_map[key]] = reason or "(no reason recorded, add one in the KB file)"
            m_also = re.search(r"also-accept\s*:\s*(YES|NO)\b", extra, re.I)
            if m_also and m_also.group(1).upper() != val:
                also[key_map[key]] = {m_also.group(1).upper()}
        elif key == "restricted-authorization":
            restricted = val == "YES"
    if len(expected) < 3 or restricted is None:
        return None
    return {"expected": expected, "rationale": rationale, "restricted": restricted,
            "also": also, "wording": wording, "free_text": _free_text_answer(text)}


# The §3 heading over the one free-text answer, written once and pasted as is.
FREE_TEXT_HEADING = re.compile(r"^(#{1,6})\s+if\s+the\s+field\s+is\s+free\s+text\b.*$", re.I | re.M)


def _norm_free(value: str) -> str:
    """The comparison form of a free-text answer: outer markdown, quotes and a trailing period removed,
    whitespace collapsed, case folded. Nothing inside the words is touched."""
    return re.sub(r"\s+", " ", _clean(re.sub(r"\s+", " ", value))).casefold()


def _free_text_answer(text: str) -> str | None:
    """The body under the "If the field is free text instead of yes/no" heading, to the next heading of
    its level or higher, in comparison form. None when the heading is missing, the body is empty, or the
    body is still the template's placeholder (text in square brackets)."""
    m = FREE_TEXT_HEADING.search(text)
    if not m:
        return None
    level = len(m.group(1))
    body = []
    for line in text[m.end():].splitlines():
        h = re.match(r"^(#{1,6})\s", line)
        if h and len(h.group(1)) <= level:
            break
        if line.strip():
            body.append(line.strip())
    raw = " ".join(body).strip()
    if not raw or re.fullmatch(r"\[[^\]]*\]\.?", raw, re.S):
        return None
    norm = _norm_free(raw)
    return norm or None


# The wide test: is this line about the right to work at all? It decides whether a line is looked
# at, never how it reads. A word on this list means the line must be read positively or be UNVERIFIED.
TOPIC = re.compile(
    r"\bvisas?\b|\bimmigra\w*|\bpetition\w*|\bsponsor\w*|\bauthori[sz]ed\b"
    r"|\b(?:work|employment)[-\s]+authori[sz]ation|\beligib\w*\s+(?:to|for)\s+(?:work|employ)"
    r"|\beligibility\s+to\s+work\b|\bemployment\s+eligib|\bright\s+to\s+(?:\w+\s+){0,3}?work\b"
    r"|\blive\s+and\s+work\b|\bwork\s+(?:visa|permit)\b|\brestrict\w*"
    r"|\bwork\s+rights?\b|\baccept\s+(?:\w+\s+){0,2}?employment\b|\blegal\s+status\b|\blawfully\s+present\b"
    r"|\beligible\s+to\s+work\b|\bright\s+to\s+work\b"
    r"|\b(?:non-?)?citizen\w*\b|\bpermanent\s+resident|\bgreen\s*card"
    r"|\b(?:foreign|american|united\s+states|u\.?\s?s\.?)\s+nationals?\b|\bnationals?\s+of\b"
    r"|\b(?:united\s+states|u\.?\s?s\.?)\s+persons?\b"
    # Plainer words for the same thing. Each makes a line looked at, never read a particular way.
    # "employer support" only with a work word on the line: alone it can mean relocation or training.
    r"|\bwork\s+status\b|\bemployer\s+support\b(?=[^\n]*\b(?:work|immigration|visa|employment)\b)"
    r"|\bimmigration\s+support\b|\bwork\s+permits?\b"
    # "Work eligibility", "Are you work eligible", "Eligibility status for employment", "Authorization status",
    # "the legal right to be employed": the same question in other words, so the line is looked at
    r"|\bwork[-\s]+eligib\w*|\beligib\w*\b(?=[^\n]*\b(?:work(?:ing)?|employment|employed)\b)"
    r"|\bauthori[sz]ation\b|\bright\s+to\s+(?:\w+\s+){0,3}?(?:be\s+employed|employment)\b"
    # "Will you now or in the future need <anything>?" is the sponsorship question whatever it names
    r"|\bnow\s+or\s+in\s+the\s+future\b"
    # A question about working plus a US place, "any employer", a status, a permit, a limit or proof
    # ("Can you work for any employer in the US?", "Is your ability to work in the US time-limited?",
    # "Do you hold a temporary status that limits your employers?", "Will you need us to support a status change?")
    # ("Current employment status" and "Are you currently employed?" name no right to work, so "employment" and
    # "employed" are not the work word here)
    r"|\b(?:work|working|be\s+employed)\b(?=[^\n]*\b(?:in\s+the\s+(?:u\.?\s?s\b|united\s+states)|any\s+employer|status"
    r"|permits?|time[- ]limited|documents?|documentation|proof|proving)\b)"
    r"|\b(?:status|temporary|time[- ]limited|documents?|proof)\b(?=[^\n]*\b(?:work|working|be\s+employed|employers?)\b)"
    r"|\bstatus\s+change\b"
    # a permit that an employer extends or renews, and a status transfer by shape (a code-style status token before "transfer", "visa transfer"):
    # a generic status-code token, never a list of programme names
    r"|\bpermits?\b(?=[^\n]*\b(?:employer|extend\w*|renew\w*)\b)|\b(?:extend\w*|renew\w*)\b(?=[^\n]*\bpermits?\b)"
    r"|\b[a-z]-?\d{1,2}[a-z]?\s+transfer\b|\b(?:visa|status|work)\s+transfer\b"
    r"|\btransfer\s+(?:of\s+)?(?:your\s+|my\s+)?(?:visa|status|petition|sponsorship)\b", re.I)
# The same words about something else, set aside before the test: a lifting restriction, a card brand,
# being authorized to drive a forklift. A line naming one of these and the real topic is still on it.
OFF_TOPIC = re.compile(
    r"\b(?:dietary|food|lifting|physical|medical|weight|shift|schedul\w*|non-?compete)\s+restrictions?\b"
    r"|\bvisa\s+(?:card|debit|credit|gift)\b|\b(?:credit|debit|gift)\s+cards?\b"
    r"|\bauthori[sz]ed\s+to\s+(?:drive|operate|sign|contact|release|administer|prescribe|handle|carry"
    r"|represent|dispense|lift|use|access)\b"
    r"|\bauthori[sz]ed\s+(?:signatory|representative|distributor|dealer|reseller|agent|user)\b"
    # an authorization that is a consent, not the right to work
    r"|\b(?:background|drug|credit|reference|payment|card|deposit|release|medical|parental|guardian|pre-?)\w*"
    r"(?:\s+(?:check|screen\w*|test\w*|deposit))?\s+authori[sz]ation\b"
    r"|\bauthori[sz]ation\s+(?:to|for)\s+(?:release|contact|run|conduct|perform|obtain|share|verify|charge|disclose"
    r"|background|drug|credit|references?|text|sms|email|call)\b", re.I)


def _on_topic(text: str) -> bool:
    t = OFF_TOPIC.sub(" ", text)
    return any(rx.search(t) for rx in (TOPIC, SPONSOR, AUTHORIZED, CITIZENSHIP, WORK_LINE))


APPLICANT_OPENER = re.compile(
    r"(?:^|:\s+[\"\u201c]?)(?:are|do|will|would|can|could|may|might|must|should|shall)\s+you\b", re.I)
# Openers about you that ask something else: what you know, want or plan, not what you need.
NOT_THE_QUESTION = re.compile(
    r"^(?:are|do|will|would|can|could|may|might|should)\s+you\s+(?:\w+\s+)?"
    r"(?:know|think|understand|agree|accept\b(?!\s+employment)|acknowledge|consent|certify|aware|familiar"
    r"|want|prefer|like|wish|willing|open|plan|intend|seek\w*|hope)\b", re.I)
# A bare label names the question and nothing else, so it has to start on the subject itself.
LABEL_START = re.compile(
    r"^(?:(?:your|my|applicant['\u2019]?s?|candidate['\u2019]?s?)\s+)?"
    r"(?:requires?|needs?|authori[sz]ed|authori[sz]ation|work|employment|sponsor\w*|visa|immigration|legal(?:ly)?"
    r"|lawful(?:ly)?|eligible|now|currently|right|citizen\w*|u\.?\s?s\.?a?\.?|united\s+states|american|permanent"
    r"|green|unrestricted|future)\b", re.I)


# Tick boxes. The option right after a mark is the answer; an option with an empty box is not.
MARK_ON = r"\[[xX\u2713\u2714]\]|\([xX\u2022]\)|[\u2611\u2612\u2713\u2714\u2705\u25c9\u25cf]"
MARK_OFF = r"\[\s?\]|\(\s\)|[\u2610\u25cb\u25ef]"
MARK_ANY = MARK_ON + "|" + MARK_OFF


def _core(q: str) -> str:
    """The question with its list marks, tick box, row numbers, quotes and closing punctuation gone."""
    s = re.sub(r"^[\W\d]+", "", re.sub(r"^[\W\d]*(?:" + MARK_ANY + r")\s*", "", q))
    s = re.sub(r"^q(?:uestion)?\s*(?:\d+\s*[.):\-]*|[.):\-]+)\s*", "", s, flags=re.I)
    return re.sub(r"[\s\"\u201c\u201d'\u2019?!:;,|]+$", "", re.sub(r"^[\W\d]+", "", s)).strip()


def _about_applicant(q: str) -> bool:
    """Positively a question to the applicant about the applicant, or a bare label naming the subject."""
    s = _core(q)
    if NOT_THE_QUESTION.search(s):
        return False
    if APPLICANT_OPENER.search(s) or re.match(r"i\b|i['\u2019]m\b", s, re.I):
        return True
    if re.search(r"\b(?:sponsor|hire|employ|petition\s+for)\s+you(?:r)?\b", s, re.I):
        return True
    if re.match(r"is\s+(?:\w+\s+){0,2}sponsorship\s+(?:required|needed|necessary)\s+for\s+you\b", s, re.I):
        return True
    return bool(LABEL_START.match(s))


# "If we offer you a position, ..." in front of a question. Set aside so the question itself is read;
# an opener that carries its own sponsorship, citizenship or negation words is never set aside.
COND_OPENER = re.compile(
    r"^\W*(?:if|once|when|should)\s+"
    r"(?![^,?]*\b(?:not|never|n['’]t|sponsor\w*|visa|citizen\w*|authori[sz]\w*|without|unless|restrict\w*)\b)"
    r"[^,?]{0,80}?\b(?:offer\w*|hired|hire|hiring|position|job|role)\b[^,?]{0,40},\s*", re.I)


def _question_text(segment: str) -> str:
    """The question only: everything up to the first '?', markdown emphasis and an offer opener removed."""
    q = re.sub(r"[*_`]", "", segment.split("?", 1)[0])
    opener = COND_OPENER.match(q)
    return q[opener.end():] if opener else q


def _negated_at(q: str, start: int) -> bool:
    """Is the phrase starting at `start` negated by the words right before it, in its own clause?"""
    return bool(NEGATED_BEFORE.search(re.split(r"[,;:()]", q[:start])[-1]))


def _citizen_doubt(q: str) -> bool:
    if CITIZENSHIP.search(q) and SPONSOR.search(q):
        return True  # two questions in one; a single Yes or No cannot answer both
    return bool(CITIZEN_QUALIFIED.search(q)) or any(_negated_at(q, m.start()) for m in CITIZENSHIP.finditer(q))


def _reading_doubtful(q: str) -> bool:
    return any(rx.search(q) for rx in (THIRD_PARTY, PAST, DOUBLE_NEGATIVE, NEGATIVE_QUESTION, WORK_ELSEWHERE))


def classify(question: str) -> tuple[str, bool] | None:
    """(question kind, inverted?), or None if this isn't a work-authorization question.

    `inverted` means the question asks the negative ("authorized WITHOUT sponsorship" / "WITHOUT
    restriction"), so the expected answer needs special handling: see `expected_answer()`.

    A line that IS about work authorization, sponsorship or citizenship but cannot be read with
    confidence comes back as (Q_UNSURE, False), and an answer on it is UNVERIFIED. It never falls
    through to None, because None reads as "nothing to check" and that is how a wrong answer passes.
    """
    # Classify on the QUESTION only, never on an answer/annotation that follows it. A dossier line is
    # often "<question>? -> **Yes** - maps to class 2 (...'sponsorship to begin/now'...)", and letting
    # the commentary's sponsorship words reach the classifier can misroute an AUTHORIZATION answer to
    # the hard-stop rule and flag a correct Yes. Polarity ("without sponsorship") is likewise a property
    # of the question, not the answer: an answer like **"No, I will not need sponsorship"** must not
    # flip the expected value. Markdown emphasis is stripped so a bolded timeframe (`Will you **now**
    # require sponsorship?`) still reads as "now require".
    q = _question_text(question)
    if not _on_topic(q):
        return None
    # The plain attestation the template's statement-style shape writes: "I am (legally) authorized to work in the
    # United States". Read as the right-to-work statement; anything more ("for any employer", which someone whose
    # right to work is tied to one employer answers differently) is not this shape, so it is UNVERIFIED.
    if re.fullmatch(r"(?:i\s+am|i['’]m)\s+(?:(?:currently|legally|lawfully)\s+){0,2}authori[sz]ed\s+to\s+work\s+in\s+"
                    r"(?:the\s+)?(?:u\.?\s?s\.?(?:a\.?)?|united\s+states(?:\s+of\s+america)?)",
                    _core(q).strip(" ."), re.I):
        return Q_AUTH, False
    has_sponsor = bool(SPONSOR_ASK.search(q))
    authorized = bool(AUTHORIZED.search(q))
    citizen = bool(CITIZENSHIP.search(q))
    unsure = (Q_UNSURE, False)
    if citizen and CITIZEN_OPEN_FIELD.search(q):
        return None
    if _reading_doubtful(q) or (citizen and _citizen_doubt(q)) or not _about_applicant(q):
        return unsure
    if citizen:
        if authorized and not re.search(r"\bor\b", q, re.I):
            return unsure  # "a citizen and authorized": only "or" lets one rule answer it
        if not authorized and CITIZEN_ELSEWHERE.search(q):
            return None
        if not (authorized or has_sponsor) and not CITIZEN_SHAPE.match(_core(q)):
            return unsure
    inv = bool(INVERTED.search(q))
    if authorized and RESTRICT_INVERTED.search(q):
        # "Without restriction" (with or without "or sponsorship" beside it) is the question about
        # whether your right to work has conditions on it, so `restricted-authorization` answers it.
        # Routing "without restriction or sponsorship" by its sponsorship word ignored that key.
        return Q_AUTH, True
    if RESTRICT.search(q):
        return unsure  # "are there restrictions on...": the opposite polarity, and no rule for it
    if authorized and not has_sponsor and AUTH_QUALIFIED.search(q):
        return unsure
    if not inv and AUTH_OR_SPONSOR.search(q):
        return unsure
    if has_sponsor:
        sp = re.search(r"sponsor", q, re.I)
        if not inv and sp and re.search(r"\b(?:without|no|not|never|none|free\s+(?:of|from)|exempt|absent)\b|n['’]t\b",
                                         q, re.I):
            # a negator before the sponsor word that INVERTED did not take ("without the need for current or future
            # sponsorship", "free of any sponsorship requirement"): the polarity is unknown, so never a confident read
            return unsure
        if not (inv or NEED.search(q)):
            return unsure  # "Are you seeking sponsorship?", "Will Acme sponsor you?": no rule for these
        if FUTURE.search(q):
            return Q_FUTURE, inv
        if TIME_FURTHER.search(q):
            return unsure  # "now or ..." with no future named: not to-begin, and nothing says it is future
        # To-begin only when the question names a moment. With no moment it is read as the strictest
        # question, so "Can you work in the US without sponsorship?" cannot pass a Yes, and "Do you
        # require sponsorship?" cannot pass a No, from someone who will need it.
        if not TIMEFRAME.search(q):
            return Q_FUTURE, inv
        # To-begin only when the WHOLE question is the moment and nothing further, the same closed-shape test
        # the authorized branch runs: "... including any extension", "... through 2030", "... for the full
        # contract term" and "... in the next 2 years" reach past the moment, so a Yes or No there is UNVERIFIED.
        return (unsure if _begin_leftover(q) else (Q_BEGIN, inv))
    if authorized:
        if re.search(r"\b(?:status|type|category|kind)\b", q, re.I):
            return unsure  # a prompt to pick from a list: a Yes or No says nothing here
        # The noun alone says nothing until the sentence says you hold it ("documentation of your ...").
        if re.search(r"\bwork\s+authori[sz]ation\b", q, re.I) and not re.search(r"\bauthori[sz]ed\b|\bright\s+to\s+work\b", q, re.I) \
                and not re.match(r"(?:do\s+you\s+(?:(?:currently|now)\s+)?(?:have|hold|possess)\b|work\s+authori)", _core(q), re.I):
            return unsure
        # The words before "authorized" are a closed list too: "Are you independently authorized", "Are you
        # always authorized" and "Will you be authorized" ask something else, so a Yes or No there is UNVERIFIED.
        auth = re.search(r"\bauthori[sz]ed\b", q, re.I)
        if auth:
            lead = _core(re.split(r"[:|]", q[:auth.start()])[-1] + " x")[:-1]  # after a label or "Q2.": "are you ..."
            if [w for w in re.findall(r"[a-z]+", lead.lower()) if w not in _AUTH_FRONT]:
                return unsure
        worked = AUTH_WORK_OBJECT.search(q)
        if auth and worked and worked.start() >= auth.end() and re.sub(r"\bto\b", "", q[auth.end():worked.start()]).strip():
            return unsure  # "authorized in your own right to work": something sits between the two
        if worked and not AUTH_WORK_READ.fullmatch(worked.group("rest")):
            return unsure  # "... overtime", "... in the US without a visa", "... through 2030": not this question
        return Q_AUTH, inv
    if citizen:
        return Q_CITIZEN, False
    return unsure


# The words a to-begin sponsorship question is made of. Anything else left in the question (a number, "including",
# "extension", "term", "through") asks something further, so the line is UNVERIFIED. A capitalised word is
# taken as the employer's or the place's name.
_BEGIN_WORD = re.compile(
    r"(?:do|does|did|will|would|could|can|are|is|am|be|been|you|your|yourself|we|us|i|currently|current|now|presently"
    r"|present|today|immediately|at|this|that|time|the|of|on|upon|when|first|day|date|hire|hiring|hired|start|starting"
    r"|begin|beginning|commence|commencing|to|employment|employ|employed|work|working|job|role|position|offer|offered"
    r"|any|an|a|immigration|visa|visas|employer|company|organi[sz]ation|sponsor\w*|requir\w*|need\w*|in|for|with"
    r"|united|states|u|s|usa|america|our|here|legally|lawfully|authori[sz]ed|authori[sz]ation|it|if|onboard\w*|join\w*"
    r"|status|support|petition|process|must|have|has|to|obtain|get|order|so|as|and|from|by|or|either|new|accept|accepting"
    r"|take|taking|up|point|moment|following|stage|right|without|able|start)", re.I)


def _begin_leftover(q: str) -> list[str]:
    """Words in a to-begin sponsorship question that are not part of that question's closed shape."""
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"[*_`]", "", q))
    later = [w for w in words[1:] if w[0].isalpha()]
    # In a Title Case or ALL CAPS label every word is capitalised, so a capital says nothing about a name there:
    # read every word against the list (a real name then counts as extra, which is the safe side).
    names_marked = sum(w[0].isupper() for w in later) * 2 < len(later)
    return [w for i, w in enumerate(words)
            if not _BEGIN_WORD.fullmatch(w) and not (names_marked and i > 0 and w[0].isupper() and not w.isdigit())]


# What may come before "authorized" in the right-to-work question: "Are you (currently / legally) authorized".
_AUTH_FRONT = frozenset("are you currently presently now legally lawfully at this time today".split())


# What may follow "work" for a line to be the right-to-work question. The WHOLE rest must fit: a place,
# an employer, a moment, and nothing after. "in the US without a visa", "for the next 3 years" and
# "through 2030" ask something narrower, so a Yes or No there is UNVERIFIED, never checked as this class.
AUTH_WORK_OBJECT = re.compile(
    r"\b(?:to\s+)?(?:(?:legally|lawfully)\s+)?(?:work|accept\s+(?:\w+\s+)?employment|be\s+employed)\b"
    r"(?![-\s]+(?:authori|permit|visa|eligib|rights?\b))\s*(?:(?:legally|lawfully)\b\s*)?(?P<rest>[^?\n]*)", re.I)
_AUTH_WHEN = r"(?:today|now|currently|presently|immediately|here|at\s+this\s+time)"
AUTH_WORK_READ = re.compile(
    r"(?:(?:in|within)\s+(?:the\s+)?(?:" + _US_NAME + r"|this\s+country)"
    r"|for\s+(?:this\s+(?:employer|company|organi[sz]ation|role|position|job)|an?\s+employer|employment|us"
    r"|(?-i:[A-Z])[\w&'-]*(?:\s+(?-i:[A-Z])[\w&'-]*){0,2})"
    r"|" + _AUTH_WHEN + r")?"
    r"(?:\s*,?\s*" + _AUTH_WHEN + r")?[\s.,\"'“”]*", re.I)



def _question_body(q: str) -> str:
    """The question after its opener and article, lower-cased: what a whole-question wording must equal."""
    s = re.sub(r"^(?:(?:are|do|will|would|can|could)\s+you\s+|i\s+am\s+)", "", _core(q), flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"^(?:an?|the)\s+", "", s, flags=re.I)).lower().rstrip(".")


def _wording_read(question: str, cfg: dict) -> tuple[list[tuple[str, str]], bool]:
    """(your wording lines this question prints, doubted?). A phrase matches from the start of a word
    and only as written: "u.s. citizen" inside "non-U.S. citizen" or "not a U.S. citizen" is the
    opposite claim, and inside "the spouse of a U.S. citizen" it is about someone else. `doubted`
    means a mapping would otherwise apply here, so the line is UNVERIFIED rather than mapped."""
    q = _question_text(question)
    found = []  # (index of the wording line, span, negated?)
    for idx, (phrases, _ans, _why) in enumerate(cfg.get("wording", [])):
        for ph in phrases:
            pat = r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(w) for w in ph.split())
            found += [(idx, m.span(), _negated_at(q, m.start())) for m in re.finditer(pat, q, re.I)]
    if not found:
        return [], False
    # A mapping only applies on a shape the gate can read about you, or when the phrase you wrote is
    # the whole question. "other than a U.S. citizen" and "Will you become a U.S. citizen" print your
    # phrase and ask something else.
    c = classify(question)
    body = _question_body(q)
    whole = any(re.sub(r"\s+", " ", ph).rstrip(".") == body for ph, _a, _w in
                ((p, a, w) for ps, a, w in cfg.get("wording", []) for p in ps))
    if not whole and c is not None and c[0] == Q_UNSURE:
        return [(cfg["wording"][i][1], cfg["wording"][i][2]) for i in sorted({f[0] for f in found})], True
    accepted = [f for f in found if not f[2]]
    inside = lambda span: any(a[1][0] <= span[0] and span[1] <= a[1][1] for a in accepted)
    doubted = any(f[2] and not inside(f[1]) for f in found)
    # A phrase you wrote out with its own negation or third party has settled that part, so only that
    # part is set aside. A plain phrase stays visible: it can still be one item in a list of statuses.
    masked = list(q)
    for _i, (start, end), _n in accepted:
        if _reading_doubtful(q[start:end]) or _citizen_doubt(q[start:end]):
            masked[start:end] = " " * (end - start)
    rest = "".join(masked)
    doubted = doubted or (bool(accepted) and (_reading_doubtful(rest) or _citizen_doubt(rest)))
    lines = cfg["wording"]
    return [(lines[i][1], lines[i][2]) for i in sorted({f[0] for f in accepted})], doubted


STATUS_DOUBT = ("?", "")


def _status_answer(question: str, cfg: dict) -> tuple[str, str] | None:
    """The answer to a positively read citizenship question, from your wording lines, status by status.
    "Are you a citizen or permanent resident?" is Yes if you are either. None means your lines say
    nothing here; STATUS_DOUBT means they cannot settle it, so the line is UNVERIFIED."""
    core = _core(_question_text(question))
    if not CITIZEN_SHAPE.match(core):
        return None
    # An "of the U.S." tail reads as part of the status it follows, so it is never a status of its own.
    items = [m.group(0) for m in STATUS_ITEM.finditer(core)]
    per_status: list[tuple[str, str] | None] = []
    for item in items:
        plain = PLAIN_RESIDENT if PLAIN_RESIDENT.match(item) else PLAIN_CITIZEN
        lines = [(a, w) for phrases, a, w in cfg.get("wording", []) if any(plain.match(p) for p in phrases)]
        if len({a for a, _ in lines}) > 1:
            return STATUS_DOUBT  # two of your lines disagree about this one status
        per_status.append(lines[0] if lines else None)
    known = [p for p in per_status if p]
    if not known:
        return None
    yes = next((p for p in known if p[0] == "YES"), None)
    if yes:
        return yes
    if len(known) == len(per_status):
        return known[0]
    # Every status you named is No, and one you did not name is left: only your own answers can close it.
    if cfg.get("expected") and citizenship_answer(cfg) == "NO":
        return known[0]
    return STATUS_DOUBT


def wording_override(question: str, cfg: dict) -> tuple[str, str] | None:
    """(answer, reason) when your `wording` mapping names a phrase this question prints, else None."""
    status = _status_answer(question, cfg)
    if status is STATUS_DOUBT:
        return None
    if status:
        return status
    hits, doubted = _wording_read(question, cfg)
    if not hits or doubted:
        return None
    if len({ans for ans, _ in hits}) > 1:
        if not re.search(r"\bor\b", _question_text(question), re.I):
            return None  # two of your lines disagree and nothing says either one is enough
        return next(h for h in hits if h[0] == "YES")  # "a citizen or permanent resident?": either makes it true
    return hits[0]


def wording_doubted(question: str, cfg: dict) -> bool:
    """A wording phrase appears here, but negated, about someone else, or with your lines in conflict."""
    if _status_answer(question, cfg) is STATUS_DOUBT:
        return True
    hits, doubted = _wording_read(question, cfg)
    return doubted or (bool(hits) and wording_override(question, cfg) is None)


# What the gate tells you to add. One line per status: the answers can differ.
CITIZEN_WORDING_HINT = (
    "wording: u.s. citizen; us citizen; united states citizen; citizen of the united states => [YES/NO] | [one-line reason]",
    "wording: permanent resident; green card => [YES/NO] | [one-line reason]",
)


def citizenship_answer(cfg: dict) -> str | None:
    """"NO" when your own answers show you are not a citizen, else None (the gate cannot know).

    A citizen is authorized now, never needs sponsorship and has no restriction, so any answer that
    says otherwise settles it. The reverse does not hold: needing no sponsorship is not citizenship.
    """
    e = cfg["expected"]
    if e[Q_AUTH] == "NO" or e[Q_BEGIN] == "YES" or e[Q_FUTURE] == "YES" or cfg["restricted"]:
        return "NO"
    return None


def accepted_answers(kind: str, inverted: bool, cfg: dict) -> set[str]:
    """Every answer the record may hold: the configured one plus any `also-accept` (flipped the
    same way when the question is inverted)."""
    want = expected_answer(kind, inverted, cfg)
    out = {want}
    if not (kind == Q_AUTH and inverted):
        for a in cfg.get("also", {}).get(kind, set()):
            out.add(("NO" if a == "YES" else "YES") if inverted else a)
    return out


def expected_answer(kind: str, inverted: bool, cfg: dict) -> str:
    """The honest answer for this (kind, inverted) pair, given the user's own configured facts."""
    if kind == Q_AUTH and inverted:
        # The "without restriction" phrasing is not a flip of the plain authorized-now answer; it's a
        # direct read of whether your authorization is itself restricted.
        return "NO" if cfg["restricted"] else "YES"
    want = cfg["expected"][kind]
    if inverted:
        want = "NO" if want == "YES" else "YES"
    return want


@dataclass
class Finding:
    path: str
    line_no: int
    kind: str
    got: str
    text: str
    expected: str
    rationale: str
    decided: tuple[str, str] | None = None

    def render(self) -> str:
        snippet = self.text.strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        if self.decided:
            adr, why = self.decided
            return (
                f"  [DECIDED] {self.path}:{self.line_no}  ({self.kind})\n"
                f"      recorded: {self.got}   rule says: {self.expected}\n"
                f"      line:     {snippet}\n"
                f"      decision: {adr} ({why})\n"
                f"      status:   already submitted; you've ruled on it. Not open work, and not a "
                f"precedent for any unsent form."
            )
        return (
            f"  [{SEVERITY[self.kind]}] {self.path}:{self.line_no}  ({self.kind})\n"
            f"      recorded: {self.got}   required: {self.expected}\n"
            f"      line:     {snippet}\n"
            f"      why:      {self.rationale}"
        )




def _adr_exists(adr: str) -> bool:
    """The named ADR must actually be on disk; a well-formed but invented id must not count."""
    num = adr.split("-")[-1]
    return any((REPO / "ops" / "decisions").glob(f"{num}-*.md"))


def _decision_on(lines: list[str], i: int, is_submitted: bool) -> tuple[str, str] | None:
    if not is_submitted:
        return None
    for j in (i, i + 1):
        if 0 <= j < len(lines):
            m = DECIDED.search(lines[j])
            if m and m.group(2).strip() and _adr_exists(m.group(1)):
                return m.group(1).upper(), m.group(2).strip()
    return None


# THE STRICT READER. It does not interpret English. A value counts only if it is:
#   1. a bare Yes or No, after stripping markdown and punctuation around it;
#   2. exactly one option carrying a real mark, whose text is a bare Yes or No;
#   3. exactly a `wording:` phrase you recorded in the knowledge base.
# Anything else on a work-authorization line is UNVERIFIED. Parentheses and square brackets are not
# stripped: "(No)" and "[No]" are not a bare No.
HEADING_LINE = re.compile(r"^\s*(#{1,6})\s+(.*)$")
_QUOTE_MARK = re.compile(r"^\s*(?:>\s?)+")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_STOP_LINE = re.compile(r"^(?:#{1,6}\s|```|~~~|[-*_]{3,}\s*$)")
_TABLE_RULE = re.compile(r"^\|?[\s:|-]*-[\s:|-]*$")
_ARROW = re.compile(r"\u2192|->|=>")
_EQUALS = re.compile(r"(?<![=<>!])=(?![=>])")
_OUTER = " \t*_`\"'\u201c\u201d\u2018\u2019"
_LEAD = re.compile(r"^(?:>\s*|[-+]\s+|\u2192\s*|->\s*|=>\s*|=\s*|:\s*)")
_YES_NO = re.compile(r"yes|no", re.I)
_BOX = re.compile(MARK_ANY)
_BOX_ON = re.compile(MARK_ON)
_LEADING_MARK = re.compile(r"(?:(?P<on>" + MARK_ON + r")|" + MARK_OFF + r")\s*")
_OPTION_LINE = re.compile(r"(?:(?P<on>" + MARK_ON + r")|" + MARK_OFF + r")?\s*(?P<text>[\W_]*(?:yes|no)\b.*)$", re.I)
# A field description after the question, never the answer: "(required)", "(dropdown: Yes / No)".
_NOTE = re.compile(r"^[\s*_\"'\u201d\u2019]*\([^)]*\b(?:required|optional|mandatory|dropdown|select|choose|pick|radio"
                   r"|checkbox|options?|choices?)\b[^)]*\)", re.I)
_BOLD_LABEL = re.compile(r"^\*\*(.+?)\*\*[\s:]*([A-Z\[(\u2610-\u2714*\"\u201c`].*)$")
# Nothing recorded yet. A bracket counts only when it lists both options or names what to fill in.
_PLACEHOLDER = re.compile(
    r"tb[da]|todo"
    r"|[\[(<{](?=[^\])>}]*\byes\b)(?=[^\])>}]*\bno\b)[^\])>}]*[\])>}]"
    r"|[\[<{][^\]>}]*\b(?:answer|fill|pending|your|value|exact|choose|select)\b[^\]>}]*[\]>}]", re.I)
_SNAKE_KEY = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)+", re.I)
_OTHER_FIELD = re.compile(r"^[A-Za-z][\w /&-]{0,30}:\s")
_PROSE_START = re.compile(r"(?:the|this|these|those|see|its|their|our|they|we|he|she|per|note|answers?)\b", re.I)
_FIRST_PERSON = re.compile(r"i\b|i['\u2019]m\b", re.I)
_ANSWER_LAST = re.compile(r"(?<![\w/-])(?:yes|no)[\W_]*$", re.I)
SHORT_VALUE_WORDS = 5
LABEL_MAX_WORDS = 8

# Clearly about the employer, not the applicant: never an answer.
_EMPLOYER_SUBJECT = re.compile(r"\b(?:subject\s+employer|employer|company|posting|jd|job\s+(?:description|ad))\b", re.I)
_EMPLOYER_SPONSORS = re.compile(
    r"\bthey\s+(?:\w+\s+)?sponsor\b|\b(?:does|do|did|will|would)\s+not\s+sponsor\b"
    r"|\b(?:doesn|don|didn|won)['\u2019]t\s+sponsor\b"
    r"|^\W*(?:does|did|will|would|can|has)\s+(?!you\b)(?:[\w&.'-]+\s+){1,3}?sponsor\b"
    r"|^\W*(?-i:[A-Z])[\w&.'-]*\s+sponsors\b", re.I)


# The word Yes or No anywhere. A line on the topic that holds one is never silent without a reason
# from the closed list in `_must_speak`.
_YN_WORD = re.compile(r"\b(?:yes|no)\b", re.I)
# A pristine placeholder listing both options, and a "<...>" template slot: nothing recorded yet.
# A form-inventory line lists the options too: "(required; options: Yes, No)". That is the question
# not answered yet, never an answer, so it is set aside like a placeholder.
_OPTIONS_LIST = (r"(?:(?:required|optional|mandatory)\s*[;,:]?\s*)?"
                 r"(?:(?:dropdown|select|radio|options?|choices?|choose|pick)\s*:?\s*)?"
                 r"(?:yes\s*(?:/|or|\||,)\s*no|no\s*(?:/|or|\||,)\s*yes)")
_PRISTINE = re.compile(r"[\[(<{]\s*" + _OPTIONS_LIST + r"\s*[\])>}]", re.I)
# The same list with no bracket, as the whole value: "options: Yes, No".
_BARE_OPTIONS = re.compile(r"(?:options?|choices?)\s*:\s*(?:yes\s*(?:/|or|\||,)\s*no|no\s*(?:/|or|\||,)\s*yes)", re.I)
_ANGLE_SLOT = re.compile(r"<[A-Za-z][^<>\n]*>")
# The explicit record that the form had no such question, and nothing else on the line.
_NO_Q_RECORD = re.compile(
    r"(?:there\s+(?:was|is)\s+)?no\s+(?:visa|work[-\s]?authori[sz]ation|sponsorship|immigration|citizenship)"
    r"(?:\s*/\s*[\w-]+)*\s+(?:question|field|section|prompt)s?"
    r"(?:\s+(?:was\s+|is\s+)?(?:on|in)\s+(?:this|the)\s+(?:form|application|page))?", re.I)
# A plain sentence whose subject is the employer: "We sponsor ...", "The company does not sponsor ...",
# "Acme offers no sponsorship ...". Silent only with no question and no value on the line.
_EMPLOYER_SENTENCE = re.compile(
    r"(?!(?:yes|no|i|you|your|my|are|do|will|would|can|could|is|does)\b)"
    r"(?:we|they|the\s+(?:company|employer|firm|organi[sz]ation|hospital|school|store|team|clinic)"
    r"|(?-i:[A-Z])[\w&'-]*(?:\s+(?-i:[A-Z])[\w&'-]*){0,2})"
    r"\s+(?:(?:does|do|did|will|would|can|cannot|may|might)\s+(?:not\s+)?|(?:doesn|don|didn|won|can)['’]t\s+)?"
    r"(?:sponsor\w*|(?:offer|provide)\w*\s+(?:no\s+|any\s+)?(?:visa\s+)?sponsor\w*)\b", re.I)


def _must_speak(text: str) -> bool:
    """True when this on-topic text holds a Yes or No and none of the closed reasons for silence applies.
    The reasons: no Yes or No outside a pristine placeholder or template slot; exactly the record that
    the form had no such question; a plain sentence about the employer with no question and no value."""
    if not _YN_WORD.search(text) or not _on_topic(text):
        return False
    if not _YN_WORD.search(_ANGLE_SLOT.sub(" ", _PRISTINE.sub(" ", _BARE_OPTIONS.sub(" ", _OPTIONS_INVENTORY.sub(" ", text))))):
        return False
    plain = re.sub(r"[*_`]", "", text).strip()
    plain = _LIST_MARK.sub("", _QUOTE_MARK.sub("", plain)).strip(" \t\"'“”.!")
    if _NO_Q_RECORD.fullmatch(plain):
        return False
    emp = _EMPLOYER_SENTENCE.match(plain)
    if emp and not re.search(r"[?:=]|→|->", plain) and not _ANSWER_LAST.search(plain) \
            and not _YN_WORD.search(plain[emp.end():]):
        return False  # silent only when no Yes or No at all follows the employer phrase (R25: no phrase reading)
    return True


def _records_no_question(text: str) -> bool:
    """Does this file hold the exact record that the form had no work-authorization question? A line in
    code quotes is the template's example of that record, not the record."""
    for line in text.splitlines():
        if "`" in line:
            continue
        plain = re.sub(r"[*_]", "", line).strip()
        plain = _LIST_MARK.sub("", _QUOTE_MARK.sub("", plain)).strip(" \t\"'“”.!")
        if plain and _NO_Q_RECORD.fullmatch(plain):
            return True
    return False


_NOT_ANSWERED = re.compile(r"(?:tbd|tba|pending|to\s+be\s+(?:decided|confirmed)|unknown|unsure|not\s+sure|\?+|n/?a)?", re.I)


def unanswered_lines(text: str) -> list[tuple[int, str]]:
    """Work-authorization lines in the section whose value is not filled in yet ("-> TBD", "-> ?", nothing after
    the arrow). They record no answer, so the gate reads none; they are named so a CLEAN never hides them."""
    lines = re.sub(r"(?s)<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), _plain_chars(text)).splitlines()
    out = []
    for i in sorted(_wa_sections(lines)):
        arrow = _ARROW.search(lines[i])
        if arrow and "`" not in lines[i]:
            v = re.sub(r"[*_`\"'“”]", "", lines[i][arrow.end():]).strip(" \t.")
            if _NOT_ANSWERED.fullmatch(v) or re.fullmatch(r"\[[^\]]*\]", v):
                out.append((i + 1, lines[i]))
    return out


def noq_contradiction(text: str) -> list[tuple[int, str]]:
    """The answers record "No work-authorization question on this form." while the form-questions list shows one."""
    if not _records_no_question(text):
        return []
    lines = re.sub(r"(?s)<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), _plain_chars(text)).splitlines()
    out, inside = [], False
    for i, ln in enumerate(lines):
        if re.match(r"^\s*##\s", ln):
            inside = bool(re.match(r"^\s*##\s+form\s+questions\b", ln, re.I))
            continue
        body = _LIST_MARK.sub("", ln).strip()
        if inside and body and not re.fullmatch(r"\[[^\]]*\]", body) and _on_topic(body):
            out.append((i + 1, ln))
    return out


def _yn_below(lines: list[str], i: int) -> bool:
    """Does the next line of content after line i hold a Yes or No?"""
    for later in lines[i + 1:]:
        s = _QUOTE_MARK.sub("", later).strip()
        if s:
            plain = _LIST_MARK.sub("", re.sub(r"[*_]", "", s)).strip(" \t\"'“”.!")
            if _NO_Q_RECORD.fullmatch(plain):
                return False  # "No work-authorization question on this form." under a label is the record, not a No
            return bool(_YN_WORD.search(s))
    return False


def _strip_note(value: str) -> str:
    """A field description after the question is set aside, unless it carries one answer: "(dropdown:
    Yes / No)" describes the field, "(dropdown: Yes)" or "(required: No)" is an answer out of its slot."""
    note = _NOTE.match(value)
    if not note:
        # An options list on its own ("(Yes / No)", "[Yes/No]", "options: Yes, No") is set aside the same
        # way, so a real answer after it ("(options: Yes, No) -> Yes") is still read in its own slot.
        bare = re.match(r"[\s*_\"'”’]*(?:" + _PRISTINE.pattern + r"|" + _BARE_OPTIONS.pattern + r")",
                        value, re.I)
        return value[bare.end():] if bare else value
    if len({w.lower() for w in _YN_WORD.findall(note.group(0))}) == 1:
        return value
    return value[note.end():]


def _about_employer(q: str, text: str) -> bool:
    core = _core(_question_text(q))
    if APPLICANT_OPENER.search(core) or re.search(r"\b(?:sponsor|hire|employ|petition\s+for)\s+you(?:r)?\b", core, re.I):
        return False
    if _EMPLOYER_SPONSORS.search(_core(text)):
        return True
    return bool(_EMPLOYER_SUBJECT.search(core)) and not NEED.search(core)


def _clean(value: str) -> str:
    """The value with only markdown and punctuation around it removed."""
    prev = None
    v = value
    while v != prev:
        prev = v
        v = _LEAD.sub("", v.strip(_OUTER))
        if v.endswith(".") and not v.endswith(".."):
            v = v[:-1]
    return v.strip()


def _pick(options: list[tuple[bool, str]]) -> str | None:
    """YES or NO when exactly one option carries a real mark and its text is a bare Yes or No."""
    marked = [_clean(text) for on, text in options if on]
    if len(marked) == 1 and _YES_NO.fullmatch(marked[0]):
        return marked[0].upper()
    return None


def _wording_value(value: str, cfg: dict | None) -> str | None:
    """The answer of the `wording:` phrase this value exactly equals, or None. A status phrase mapped
    to No cannot be a value: "U.S. citizen" written by someone whose line says No claims the opposite."""
    norm = re.sub(r"\s+", " ", value).lower()
    answers = {a for phrases, a, _w in (cfg or {}).get("wording", []) for p in phrases
               if re.sub(r"\s+", " ", _clean(p)).lower() == norm}
    if len(answers) != 1:
        return None
    answer = next(iter(answers))
    return None if answer == "NO" and CITIZENSHIP.search(value) else answer


def _read_value(value: str, cfg: dict | None) -> tuple[str, str | None]:
    """The one place a value becomes an answer: (answer | wording | placeholder | unread, YES or NO)."""
    v = _clean(value)
    if _PLACEHOLDER.fullmatch(v):
        return "placeholder", None
    marks = list(_BOX.finditer(v))
    if marks:
        if marks[0].start() or _BOX.fullmatch(v[marks[-1].start():].rstrip(_OUTER + ".")):
            return "unread", None  # text before the first box, or the box after its option
        ends = [m.start() for m in marks[1:]] + [len(v)]
        got = _pick([(bool(_BOX_ON.fullmatch(m.group(0))), v[m.end():end]) for m, end in zip(marks, ends)])
        return ("answer", got) if got else ("unread", None)
    if _YES_NO.fullmatch(v):
        return "answer", v.upper()
    got = _wording_value(v, cfg)
    if got:
        return "wording", got
    if _free_text_value(v, cfg):
        return "freetext", FREE_TEXT_GOT
    return "unread", None


# What a line holding your §3 free-text answer records: the paragraph, not a Yes or No.
FREE_TEXT_GOT = "FREE-TEXT"
# The classes a Yes or No is compared against. Your paragraph on one of these is UNVERIFIED: the form
# offered a Yes or No, and the paragraph does not say which was picked.
YES_NO_CLASSES = {Q_AUTH, Q_BEGIN, Q_FUTURE, Q_CITIZEN}


def _free_text_value(value: str, cfg: dict | None) -> bool:
    """Is this value exactly the free-text answer you recorded in §3 (see `_norm_free`)?"""
    want = (cfg or {}).get("free_text")
    return bool(want) and _norm_free(value) == want


def _split(piece: str) -> tuple[str, str, bool]:
    """(question or label, the value written after it, was there an arrow?)."""
    s = piece.strip()
    arrow = _ARROW.search(s)
    mark = s.find("?")
    if mark != -1 and (not arrow or mark < arrow.start()):
        return s[:mark + 1], s[mark + 1:], bool(arrow)
    if arrow:
        return s[:arrow.start()], s[arrow.end():], True
    bold = _BOLD_LABEL.match(s)
    if bold and len(bold.group(2).split()) <= SHORT_VALUE_WORDS:
        return bold.group(1), bold.group(2), False
    box = _BOX.search(s)
    if box and box.start() and _on_topic(s[:box.start()]):
        return s[:box.start()], s[box.start():], False
    for found in (_EQUALS.search(s), re.search(":", s)):
        if found and _on_topic(s[:found.start()].replace("_", " ")):
            return s[:found.start()], s[found.end():], False
    return s, "", False


def _pieces(body: str) -> list[str]:
    """One line carrying several question-and-value pairs splits only when every piece is such a pair.
    "Authorized: No; see note" stays whole, so its value is "No; see note", not a bare No."""
    parts = [p for p in SEGMENT.split(body) if p.strip()]
    return parts if len(parts) > 1 and all(_clean(_split(p)[1]) for p in parts) else [body]


def _table_pairs(body: str, lines: list[str], i: int) -> tuple[list[tuple[str, str, bool]], str]:
    """((question, value, arrow) per question in a table row, the cells before the first question).
    A header row and the rule under it are skipped."""
    if _TABLE_RULE.match(body) or (i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1].strip())):
        return [], ""
    cells = [c.strip() for c in body.strip().strip("|").split("|")]
    first = next((n for n, c in enumerate(cells) if "?" in c or classify(_split(c)[0]) is not None), None)
    if first is None:
        return [], body
    heads = [first] + [n for n in range(first + 1, len(cells)) if "?" in cells[n]]
    pairs = []
    for at, end in zip(heads, heads[1:] + [len(cells)]):
        q, value, arrow = _split(cells[at])
        if not _clean(value):
            filled = [c for c in cells[at + 1:end] if c]
            # A Yes or No in any later cell joins the value, so it is never left outside the slot.
            several = any(_YN_WORD.search(c) or _BOX.search(c) for c in filled[1:])
            value = " ".join(filled) if several else (filled[0] if filled else "")
        pairs.append((q, value, arrow))
    return pairs, " | ".join(cells[:first])


def _read_after(lines: list[str], i: int, cfg: dict | None) -> tuple[str, str | None, str, int]:
    """What the first line of content after line i holds, blank lines and quote marks skipped:
    (answer | wording | placeholder | none | text, YES or NO, its text, its index). Lines listing
    options one per line are read as a list: the first of them is never taken as the answer."""
    j = i + 1
    while j < len(lines) and not _QUOTE_MARK.sub("", lines[j]).strip():
        j += 1
    if j >= len(lines):
        return "none", None, "", j
    s = _QUOTE_MARK.sub("", lines[j]).strip()
    if _STOP_LINE.match(s) or "?" in s or s.startswith("|"):
        return "none", None, "", j
    body = _LIST_MARK.sub("", s).strip()
    options: list[tuple[bool, str]] = []
    for later in lines[j:]:
        t = _LIST_MARK.sub("", _QUOTE_MARK.sub("", later).strip()).strip()
        if not t:
            continue
        m = _OPTION_LINE.match(t)
        if not m:
            break
        options.append((bool(m.group("on")), m.group("text")))
    if len(options) > 1:
        got = _pick(options)
        return ("answer" if got else "text"), got, body, j
    q, value, _arrow = _split(body)
    if _clean(value) and classify(q) is not None:
        return "none", None, "", j  # the next line is a question and value of its own
    state, got = _read_value(body, cfg)
    return ("text" if state == "unread" else state), got, body, j


# The template's form-questions list line: "- <question as printed> (required; options: A, B, C)". It lists the
# choices the form offered, never the one picked.
_OPTIONS_INVENTORY = re.compile(r"\(\s*(?:(?:required|optional|mandatory)\s*[;,]\s*)?(?:options?|choices?|dropdown|select"
                                r"|radio|checkbox(?:es)?)\s*:[^()\n]*\)\s*\.?", re.I)


def _read_pair(lines: list[str], i: int, q: str, value: str, arrow: bool, may_look_below: bool,
               checked: bool, cfg: dict | None,
               in_section: bool = False) -> tuple[str, str, bool, str | None, bool] | None:
    """One question or label and its value: (question, kind, inverted, answer or None, unreadable?),
    or None when the line records nothing to check. `in_section` means the line sits under a
    work-authorization heading or label, where every recorded question is read or UNVERIFIED."""
    value = _strip_note(value)
    if _OPTIONS_INVENTORY.fullmatch(str(value or "").strip()):
        return None  # "(required; options: U.S. Citizen, Permanent Resident, Other)": the form-questions list, no answer
    text = f"{q} {value}"
    # These guards may silence a line only when no Yes or No is on it (or right below a bare question).
    # With one present they step aside: the question is read as usual, and whatever is not read here is
    # reported UNVERIFIED by `_walk` through `_must_speak`.
    guarded = bool(NO_QUESTION.search(text) or NO_QUESTION.search(f"{q}: {value}")
                   or CONDITIONAL.search(text) or _about_employer(q, text))
    if guarded and not _YN_WORD.search(text) and (_clean(value) or not _yn_below(lines, i)):
        return None
    core = _core(_question_text(q))
    key = q.strip(_OUTER + ":")
    if _SNAKE_KEY.fullmatch(key) and _on_topic(key.replace("_", " ")):
        return (q, Q_UNSURE, False, None, True) if _clean(value) else None  # a config key, not a form label
    has_value = bool(_clean(value))
    c = classify(q)
    if c is None and cfg and CITIZENSHIP.search(q) and wording_override(q, cfg):
        c = (Q_CITIZEN, False)
    if c is None and arrow and has_value and not _on_topic(q) \
            and (_on_topic(value) or _wording_value(_clean(value), cfg) or _free_text_value(value, cfg)):
        c = (Q_UNSURE, False)
    # Under a work-authorization heading or label, a recorded `"<question>" → <value>` line is one of
    # those answers by where it was written. A question the gate has no rule for ("Are you over 18?")
    # is UNVERIFIED there, never silent: move it out of that section if it is not about the right to work.
    if c is None and in_section and arrow and has_value and _RECORD_SHAPE.match(q.strip()):
        c = (Q_UNSURE, False)
    if c is None:
        return None
    kind, inverted = c
    asked = _about_applicant(_question_text(q))
    short_label = len(core.split()) <= LABEL_MAX_WORDS

    def done(state: str, got: str | None):
        # Your exact wording settles a line the gate cannot classify: read, with nothing to compare it to.
        # Your §3 free-text answer does the same on a question that is not a yes/no class; on a yes/no
        # class it is UNVERIFIED, because the paragraph does not say which option was picked.
        if state == "freetext":
            return (q, kind, inverted, None, True) if kind in YES_NO_CLASSES else (q, Q_SETTLED, False, got, False)
        return (q, Q_SETTLED, False, got, False) if state == "wording" and kind == Q_UNSURE \
            else (q, kind, inverted, got, False)

    if has_value:
        state, got = _read_value(value, cfg)
        if state == "placeholder":
            return None
        if state != "unread":
            return done(state, got)
        return (q, kind, inverted, None, True) if arrow or (asked and ("?" in q or short_label)) else None
    if checked and _FIRST_PERSON.match(core):
        return q, kind, inverted, None, True  # a ticked statement with no Yes or No
    if asked and _ANSWER_LAST.search(core):
        return q, kind, inverted, None, True  # a Yes or No with nothing separating it from the question
    is_question = "?" in q or bool(APPLICANT_OPENER.search(core))
    if not may_look_below or not (is_question or (asked and short_label)):
        return None
    nxt = next((x for x in lines[i + 1:] if x.strip()), "")
    if _NO_Q_RECORD.fullmatch(_LIST_MARK.sub("", re.sub(r"[*_`]", "", _QUOTE_MARK.sub("", nxt))).strip(" \t\"'“”.!")):
        return None  # a label over "No work-authorization question on this form.": the record, not an answer
    state, got, body, at = _read_after(lines, i, cfg)
    if state in ("answer", "wording", "freetext"):
        return done(state, got)
    if state != "text" or not asked:
        return None
    if is_question:
        below = _LIST_MARK.match(lines[at])
        sibling = bool(_LIST_MARK.match(lines[i]) and below) and len(lines[at]) - len(lines[at].lstrip()) <= \
            len(lines[i]) - len(lines[i].lstrip())
        return None if sibling else (q, kind, inverted, None, True)
    # A label over a line of text: an answer if it could be one, a note if it plainly reads as a note.
    plain = _clean(body)
    if _PROSE_START.match(plain) or _OTHER_FIELD.match(plain) or _about_employer(q, plain):
        return None
    could_be_answer = len(plain.split()) <= SHORT_VALUE_WORDS or _on_topic(plain) or bool(re.match(r"(?:yes|no)\b", plain, re.I))
    return (q, kind, inverted, None, True) if could_be_answer else None


# A heading or a list label that names the work-authorization section, like the template's
# "- Work-authorization field(s), worded EXACTLY as the form printed them:".
_WA_TITLE = re.compile(r"work[-\s]*authori[sz]ation|sponsorship", re.I)
# The template's record shape: a quoted question, then the arrow. A bracket or "<...>" slot as the
# question is the template's own placeholder, not a recorded question.
_RECORD_SHAPE = re.compile(r"^[\"“](?![\s\[<])[^\"”]*\S")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _wa_sections(lines: list[str]) -> set[int]:
    """Indexes of the lines inside a work-authorization section. A heading naming it runs to the next
    heading of the same or a higher level; a list item naming it and ending in ':' runs over the lines
    indented deeper than it."""
    inside: set[int] = set()
    head_level = None
    label_indent = None
    for i, raw in enumerate(lines):
        body = _QUOTE_MARK.sub("", raw)
        heading = HEADING_LINE.match(body)
        if heading:
            label_indent = None
            level = len(heading.group(1))
            if head_level is not None and level <= head_level:
                head_level = None
            if head_level is None and _WA_TITLE.search(heading.group(2)):
                head_level = level
            continue
        if label_indent is not None and body.strip() and _indent(body) <= label_indent:
            label_indent = None
        if head_level is not None or label_indent is not None:
            inside.add(i)
        item = _LIST_MARK.match(body)
        if label_indent is None and item and _WA_TITLE.search(body) and body.rstrip().endswith(":"):
            label_indent = _indent(body)
    return inside


def _plain_chars(text: str) -> str:
    """Every invisible format character (Unicode category Cf: soft hyphen, zero-width space, joiner and
    non-joiner, word joiner, byte-order mark, bidi marks) removed, and every other space character
    (category Zs: no-break space and the rest) made a plain space. A soft hyphen inside "sponsorship"
    hid a whole line from every pattern, so a wrong answer read as CLEAN. Newlines are untouched, so
    line numbers hold."""
    if text.isascii():
        return text
    return "".join("" if unicodedata.category(ch) == "Cf" else " " if unicodedata.category(ch) == "Zs" else ch
                   for ch in text)


def _walk(text: str, cfg: dict | None = None):
    """Yield (line index, line, question, kind, inverted, answer or None, unreadable?) for every
    work-authorization question or label that records a value. One reading path for every shape:
    plain, bold, heading, quoted, table row or list item, value on the same line or the next."""
    text = _plain_chars(text)
    # A commented-out line is not an answer. Blank the comment, keep its newlines, so line numbers hold.
    lines = re.sub(r"(?s)<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text).splitlines()
    sections = _wa_sections(lines)
    for i, raw in enumerate(lines):
        body = _QUOTE_MARK.sub("", raw)
        heading = HEADING_LINE.match(body)
        body = _LIST_MARK.sub("", heading.group(2) if heading else body).strip()
        lead = ""
        if body.startswith("|"):
            found, lead = _table_pairs(body, lines, i)
            pairs = [(q, v, a, False, False) for q, v, a in found]
        else:
            tick = _LEADING_MARK.match(body)
            if tick:
                body = body[tick.end():]
            pieces = _pieces(body)
            pairs = [(*_split(p), len(pieces) == 1 and not tick, bool(tick and tick.group("on"))) for p in pieces]
        # Silence needs a reason: a Yes or No left outside the value slot of a line on the topic is
        # UNVERIFIED, whatever guard or shape let it through unread.
        if _YN_WORD.search(lead) and _must_speak(body):
            yield (i, raw, body, Q_UNSURE, False, None, True)
            continue
        for q, value, arrow, may_look_below, checked in pairs:
            read = _read_pair(lines, i, q, value, arrow, may_look_below, checked, cfg, i in sections)
            if read:
                yield (i, raw, *read)
            elif _must_speak(f"{q} {value}") or _statement_answer(q, value) or _answer_below(lines, i, q, value):
                yield (i, raw, q, Q_UNSURE, False, None, True)


# A chosen statement as the answer ("I am authorized to work in the U.S. and will not require sponsorship",
# "Require sponsorship"): it holds no bare Yes or No, but it is an answer about the right to work, so it is
# UNVERIFIED, never silent.
_STATEMENT_WORDS = re.compile(r"\b(?:sponsor\w*|authori[sz]\w*|citizen\w*|visas?|work\s+permits?|permanent\s+resident"
                              r"|green\s*card|immigration|eligible\s+to\s+work)\b", re.I)


def _statement_answer(q, value) -> bool:
    if not str(value or "").strip():  # "Please select your status: **Require sponsorship**": the value after the label
        m = re.search(r":\s*(\S.*)$", str(q or ""))
        value, q = (m.group(1), q[:m.start()]) if m else ("", q)
    v = re.sub(r"[*_`]", "", str(value or "")).strip(" \t.\"'“”")
    if (not v or re.fullmatch(r"\[[^\]]*\]", v) or _ANGLE_SLOT.fullmatch(v) or _PRISTINE.search(v) or _BARE_OPTIONS.search(v)
            or _OPTIONS_INVENTORY.fullmatch(v)):
        return False
    emp = _EMPLOYER_SENTENCE.match(v)
    if emp and not _YN_WORD.search(v[emp.end():]):
        return False  # "Acme does not sponsor": a note about the employer, not your answer
    return bool(_STATEMENT_WORDS.search(v)) and _on_topic(f"{q} {v}")


_ANSWER_LINE = re.compile(r"^[\s>*_\-•]*(?:a|answer|response|reply)\s*[:.)]", re.I)


def _answer_below(lines, i, q, value) -> bool:
    """A question on the topic with its answer on the next line, written "A: No" or "Answer: Yes"."""
    if str(value or "").strip(" \t\"'“”*_") or "?" not in str(q) or not _on_topic(q):
        return False  # (a closing quote left after the question mark is no value)
    for later in lines[i + 1:]:
        if later.strip():
            return bool(_ANSWER_LINE.match(re.sub(r"[*_`]", "", later))) and bool(_YN_WORD.search(later))
    return False


def recorded_answers(text: str, cfg: dict | None = None) -> list[tuple[int, str, str, str, bool, str]]:
    """Every recorded work-authorization answer: (line index, line, question segment, kind,
    inverted, answer). Needs no configuration, so an unconfigured gate can still tell "nothing
    recorded" from "recorded but unverifiable"."""
    return [(i, line, seg, kind, inv, got)
            for i, line, seg, kind, inv, got, _ in _walk(text, cfg) if got is not None]


def unreadable_answers(text: str, cfg: dict | None = None) -> list[tuple[int, str]]:
    """(line number, line) of every recorded work-authorization answer whose yes/no the gate cannot
    read. Such a line is UNVERIFIED: the gate exits non-zero, it never reports it as clean."""
    return [(i + 1, line) for i, line, _s, _k, _v, got, bad in _walk(text, cfg) if bad]


def scan_text(rel: str, text: str, cfg: dict) -> list[Finding]:
    text = _plain_chars(text)
    out: list[Finding] = []
    lines = text.splitlines()
    submitted = is_submitted(text)
    for i, line, seg, kind, inverted, got in recorded_answers(text, cfg):
        if kind == Q_SETTLED:
            continue
        override = wording_override(seg, cfg)
        if override:
            accepted, want, why = {override[0]}, override[0], f"your wording mapping: {override[1]}"
        elif kind == Q_UNSURE or wording_doubted(seg, cfg):
            continue  # unclassified_answers() reports this one as UNVERIFIED
        elif kind == Q_CITIZEN:
            want = citizenship_answer(cfg)
            if want is None:
                continue  # citizenship_unknown() reports this one as UNVERIFIED
            accepted, why = {want}, "your own §3 answers show you are not a citizen."
        else:
            accepted = accepted_answers(kind, inverted, cfg)
            want, why = expected_answer(kind, inverted, cfg), cfg["rationale"].get(kind, "")
        if got not in accepted:
            out.append(Finding(rel, i + 1, kind, got, line, want, why,
                               _decision_on(lines, i, submitted)))
    return out


def citizenship_unknown(text: str, cfg: dict) -> list[tuple[int, str]]:
    """(line number, line) of each citizenship answer your §3 cannot settle: UNVERIFIED, never clean."""
    if citizenship_answer(cfg) is not None:
        return []
    return [(i + 1, line) for i, line, seg, kind, _v, _g in recorded_answers(text, cfg)
            if kind == Q_CITIZEN and not wording_override(seg, cfg) and not wording_doubted(seg, cfg)]


def unclassified_answers(text: str, cfg: dict) -> list[tuple[int, str]]:
    """(line number, line) of each answer on a line the gate cannot read with confidence: UNVERIFIED."""
    return [(i + 1, line) for i, line, seg, kind, _v, _g in recorded_answers(text, cfg)
            if kind != Q_SETTLED and not wording_override(seg, cfg)
            and (kind == Q_UNSURE or wording_doubted(seg, cfg))]


def coverage_gap(rel: str, text: str) -> str | None:
    """A submitted application with NO recorded work-authorization answer at all."""
    text = _plain_chars(text)
    if not is_submitted(text):
        return None
    if SPONSOR.search(text) or AUTHORIZED.search(text):
        return None
    if NO_QUESTION.search(text):
        return None
    if CITIZENSHIP.search(text) and recorded_answers(text):
        return None
    return f"  [HIGH] {rel}  (no-record)\n      This dossier records a SUBMITTED application and " \
           f"contains NO work-authorization answer at all. Unverifiable, and that's a defect on its own."


# EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (the selftest fixture and the blank starter), never
# a real application. The template's own instructions mention a `## SUBMITTED` heading, so sweeping
# it would report a "submitted with no answer" defect on every fresh clone.
SCAFFOLD_PREFIXES = ("EXAMPLE-", "TEMPLATE-")


def targets(root: Path | None = None) -> list[Path]:
    root = REPO if root is None else root
    return sorted(p for p in root.glob("applications/*/application.md")
                  if not p.parent.name.startswith(SCAFFOLD_PREFIXES))


# selftest
# A fixed, self-contained fictional configuration: the selftest never reads the real KB file, so
# it works identically on a fresh clone before anyone has filled in their own answers.
_TEST_CFG = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "YES"},
    "rationale": {
        Q_AUTH: "example: authorized to work today under the fixture's assumed status.",
        Q_BEGIN: "example: no sponsorship needed to start.",
        Q_FUTURE: "example: the fixture assumes sponsorship is needed later on.",
    },
    "restricted": True,
}

CASES: list[tuple[str, str, bool]] = [
    ("hard-stop answered correctly",
     "- Will you now or in the future require sponsorship for employment visa status? **Yes**", False),
    ("hard-stop flipped to No: a false answer",
     "- Will you now or in the future require sponsorship for employment visa status? **No**", True),
    ("'to begin' answered No: correct and must NOT fire",
     "- Do you require sponsorship to begin employment with us? **No**", False),
    ("'to begin' answered Yes: screens you out for nothing",
     "- Do you require sponsorship to begin employment? **Yes**", True),
    ("'at the time of hire' answered No: correct",
     "- Will you require visa sponsorship at the time of hire? **No**", False),
    ("authorized-now answered Yes: correct",
     "- Are you legally authorized to work in the United States? **Yes**", False),
    ("authorized-now answered No: false per the fixture config",
     "- Are you legally authorized to work in the United States? **No**", True),
    ("bare sponsorship question with no timeframe answered No: read as the hard stop",
     "- Do you require sponsorship? **No**", True),
    ("a prose mention with no recorded answer must NOT fire here",
     "The hospital's careers page has a long section on sponsorship questions.", False),
    ("the correct three-way summary line must NOT fire",
     "- Authorized to work in the US? **Yes** · Require sponsorship now/future? **Yes**", False),
    ("a correct answer in the 2nd segment of a multi-question line",
     "- Prior Umbrella employee: **No** · Authorized to work today: **Yes**", False),
    ("conditional analysis of what a form might ask, not a submitted value",
     'Should the Northwind form limit itself to **day one**, the reply is **No**. Should it say '
     '**"now or in the future"**, then **Yes** is right.', False),
    ("a stray ': no' inside a trailing quoted note, never an answer",
     '- Work authorization (one combined dropdown): **"my status needs an employer to sponsor it '
     'now or in the future"** (accurate). NOTE: no second question about this on the Acme form.', False),
    ("the employer's quoted option text is not the candidate's answer",
     '| 9 | "Your authorization to work..." | **"I hold a permit that lets me work here and no '
     'employer has to sponsor it"** |', False),
    ("an honest free-text paragraph containing the words 'no sponsorship'",
     "> On the old Hooli contract there was no sponsorship budget for trade licences, so I paid for "
     "mine.", False),
    ("prose describing what the form does NOT ask",
     'The Globex portal skips the standard "are you authorized to work in the United States?" and '
     "offers a list of statements instead.", False),
    ("inverted question, honest answer No given restricted=True: must NOT fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **No**", False),
    ("inverted question answered Yes: MUST fire",
     "- Are you authorized to work in the US **without sponsorship**, now or in the future? **Yes**", True),
    ("inverted 'without restriction' answered No: matches restricted=True, must NOT fire",
     "- Are you authorized to work in the U.S. without restriction? **No**", False),
    ("inverted 'without restriction' answered Yes: contradicts restricted=True, MUST fire",
     "- Are you authorized to work in the U.S. without restriction? **Yes**", True),
    ("inverted, to-begin timeframe, honest Yes: must NOT fire",
     "- Can you begin work without requiring sponsorship? **Yes**", False),
    ("a wrong answer inside a markdown table row must fire",
     "| 7 | Will you now or in the future require sponsorship? | **No** |", True),
    ("a right answer inside a markdown table row must NOT fire",
     "| 7 | Will you now or in the future require sponsorship? | **Yes** |", False),

    # Harder phrasing shapes. What a dropdown's answer says after the leading yes/no is not
    # load-bearing here, only the position of the yes/no at the front of the quoted answer.
    ("a semicolon-separated multi-question line - a bare sponsorship Yes is right, must NOT fire",
     '- Selects: "relocating?"=**No**; **"Will you now or in the future require sponsorship?" = '
     '"Yes"**; "state?"=**Ohio**', False),
    ("a semicolon-separated multi-question line - a bare sponsorship No is wrong, MUST fire",
     '- Selects: "relocating?"=**No**; **"Will you now or in the future require sponsorship?" = '
     '"No"**; "state?"=**Ohio**', True),
    ("inverted 'without the need for sponsorship' answered No: must NOT fire",
     "- Are you authorized to work without the need for sponsorship, now or in the future? **No**", False),
    ("the hard-stop answered **No.** (a period inside the bold): MUST fire",
     "- Will you now or in the future require sponsorship? **No.**", True),
    ("inverted 'without employer-sponsored status support' answered No: must NOT fire",
     '- "Are you legally authorized to work in the United States without employer-sponsored status '
     'support now or in the future?": **No**', False),
    ("the same hyphenated inverted question answered Yes: MUST fire",
     '- "Are you legally authorized to work in the United States without employer-sponsored status '
     'support now or in the future?": **Yes**', True),

    # the template's own shapes. Before this fix the gate read only bold **Yes**/**No**, so a
    # wrong answer written the way the template shows it passed as CLEAN.
    ("template arrow shape, hard-stop flipped to No: MUST fire",
     '- "Will you now or in the future require sponsorship for employment visa status?" → No', True),
    ("template arrow shape, honest Yes: must NOT fire",
     '- "Will you now or in the future require sponsorship for employment visa status?" → Yes', False),
    ("ascii arrow, to-begin answered Yes: MUST fire",
     '- "Do you require sponsorship to begin employment?" -> Yes', True),
    ("colon shape, plain text, authorized-now answered No: MUST fire",
     "- Are you legally authorized to work in the United States: No", True),
    ("trailing bare answer after the question mark, wrong: MUST fire",
     "- Will you now or in the future require sponsorship? No", True),
    ("trailing bare answer in a plain table cell, wrong: MUST fire",
     "| 4 | Will you now or in the future require sponsorship? | No |", True),
    ("an option list after a colon is not an answer: must NOT fire",
     '- "Do you require sponsorship to begin employment?" (dropdown: Yes / No)', False),

    # Round 9: "employer support for your work status" is the sponsorship question in plainer words.
    ("employer support for your work status, now or in the future, answered No: MUST fire",
     '- "Will you now or in the future require employer support for your work status?" → No', True),
    ("the same question answered Yes: must NOT fire",
     '- "Will you now or in the future require employer support for your work status?" → Yes', False),
    ("a form-inventory options list is not an answer, and the answer after it is read: MUST fire",
     "- Are you legally authorized to work in the US? (options: Yes, No) → No", True),
]

# A second fictional configuration that exercises the two optional mappings: the future answer
# changed from YES to NO with the old YES still accepted on records (also-accept), and a question
# that names any employer in the US is answered YES as printed (wording).
_TEST_CFG_MAP = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "NO"},
    "rationale": {Q_AUTH: "example.", Q_BEGIN: "example.", Q_FUTURE: "example: changed answer."},
    "restricted": True,
    "also": {Q_FUTURE: {"YES"}},
    "wording": [(["for any employer in the us", "without employer support"], "YES",
                 "example: that wording asks about every employer, not this one.")],
}

MAP_CASES: list[tuple[str, str, bool]] = [
    ("also-accept: the new configured No on the future question is accepted",
     "- Will you now or in the future require sponsorship? **No**", False),
    ("also-accept: the old Yes on a built record is accepted too",
     "- Will you now or in the future require sponsorship? **Yes**", False),
    ("also-accept never widens another class: to-begin answered Yes still fires",
     "- Do you require sponsorship to begin employment? **Yes**", True),
    ("also-accept flips with polarity: inverted future question answered No (old) is accepted",
     "- Are you authorized to work in the US without sponsorship, now or in the future? **No**", False),
    ("also-accept flips with polarity: inverted future question answered Yes (new) is accepted",
     "- Are you authorized to work in the US without sponsorship, now or in the future? **Yes**", False),
    ("wording: a question naming any employer in the US is answered as printed, Yes accepted",
     "- Do you now, or will you in the future, require sponsorship to work for any employer in the US? "
     "**Yes**", False),
    ("wording: the same printed question answered No fires (the mapping says Yes)",
     "- Do you now, or will you in the future, require sponsorship to work for any employer in the US? "
     "**No**", True),
    ("wording: a negated phrase inside the question does not trigger the mapping",
     '- "Will you now or in the future require sponsorship (no need for any employer in the US)?" '
     '\u2192 **No**', False),
]

_CITIZEN_YES_MAP = {
    **_TEST_CFG_MAP, "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "NO"}, "restricted": False, "also": {},
    "wording": [(["u.s. citizen", "permanent resident"], "YES", "example: holds that status.")],
}
_CITIZEN_NO_MAP = {**_CITIZEN_YES_MAP,
                   "wording": [(["u.s. citizen", "permanent resident"], "NO", "example: does not hold that status."),
                               (["other than"], "YES", "example: holds another citizenship.")]}

_PERMANENT_RESIDENT_MAP = {**_CITIZEN_YES_MAP,
                           "wording": [(["u.s. citizen"], "NO", "example: not a citizen."),
                                       (["permanent resident"], "YES", "example: holds that status.")]}
_CITIZEN_ONLY_MAP = {**_CITIZEN_YES_MAP,
                     "wording": [(["u.s. citizen"], "YES", "example: a citizen."),
                                 (["permanent resident"], "NO", "example: a citizen, so not this.")]}

# The wording line wins over every inference, in both directions.
CITIZEN_WORDING_CASES: list[tuple[str, dict, str, bool]] = [
    ("one line per status: a permanent resident claiming citizenship fires", _PERMANENT_RESIDENT_MAP,
     '- "Are you a U.S. citizen?" \u2192 Yes', True),
    ("one line per status: a permanent resident answering that question Yes is accepted", _PERMANENT_RESIDENT_MAP,
     '- "Are you a lawful permanent resident?" \u2192 Yes', False),
    ("one line per status: a citizen answering No to permanent resident is accepted", _CITIZEN_ONLY_MAP,
     '- "Are you a lawful permanent resident?" \u2192 No', False),
    ("a question naming both with 'or' is Yes if either is", _PERMANENT_RESIDENT_MAP,
     '- "Are you a U.S. citizen or permanent resident?" \u2192 Yes', False),
    ("a question naming both, answered No by someone who is one, fires", _CITIZEN_ONLY_MAP,
     '- "Are you a U.S. citizen or permanent resident?" \u2192 No', True),
    ("a commented-out wrong answer is not an answer", _PERMANENT_RESIDENT_MAP,
     '<!-- - "Are you a U.S. citizen?" \u2192 Yes -->', False),
    ("a wrong answer beside a closed comment still fires", _PERMANENT_RESIDENT_MAP,
     '<!-- note --> - "Are you a U.S. citizen?" \u2192 Yes', True),
    ("wording YES: answered Yes is accepted", _CITIZEN_YES_MAP, '- "Are you a U.S. citizen?" → Yes', False),
    ("wording YES: answered No fires", _CITIZEN_YES_MAP, '- "Are you a U.S. citizen?" → No', True),
    ("wording NO: answered Yes fires", _CITIZEN_NO_MAP, '- "Are you a U.S. citizen?" → Yes', True),
    ("wording NO: answered No is accepted", _CITIZEN_NO_MAP, '- "Are you a U.S. citizen?" → No', False),
    ("wording on a phrase left unclassified: a wrong answer fires", _CITIZEN_NO_MAP,
     "- Are you a citizen of a country other than the United States? **No**", True),
    ("wording beats the inference from a sponsorship answer", {**_CITIZEN_YES_MAP, "restricted": True},
     '- "Are you a U.S. citizen?" → Yes', False),
]

# Real-looking questions read by two people: one authorized today who will need sponsorship later
# (_TEST_CFG) and one with no conditions at all (_NO_CONDITIONS). Each row is (question, right answer
# for the first, right answer for the second). "?" means the gate must say UNVERIFIED for either
# answer, and "-" means this is not a work-authorization question at all.
_NO_CONDITIONS = {
    "expected": {Q_AUTH: "YES", Q_BEGIN: "NO", Q_FUTURE: "NO"},
    "rationale": {Q_AUTH: "example.", Q_BEGIN: "example.", Q_FUTURE: "example."},
    "restricted": False,
}
PHRASING_TABLE: list[tuple[str, str, str]] = [
    # Inverted, with "restrict" beside or instead of "sponsor".
    ("Are you authorized to work in the US without restriction or sponsorship?", "No", "Yes"),
    ("Do you have the unrestricted right to work in the United States?", "No", "Yes"),
    ("Do you have unrestricted work authorization in the US?", "No", "Yes"),
    ("Are you free of any restriction on your right to work in the United States?", "No", "Yes"),
    # Can / able / eligible, with no timeframe: read as the strictest question.
    ("Can you work in the US without sponsorship?", "No", "Yes"),
    ("Are you able to work in the United States without visa sponsorship?", "No", "Yes"),
    ("Are you eligible to work in the United States without sponsorship?", "No", "Yes"),
    ("Can you work in the US with no sponsorship?", "No", "Yes"),
    ("Can you work for Acme without employer sponsorship?", "No", "Yes"),
    ("Are you authorized to work for Globex without sponsorship?", "No", "Yes"),
    ("Will you be able to work in the United States without needing sponsorship now or in the future?", "No", "Yes"),
    ('Sponsorship is not required for me to work in the US', "No", "Yes"),
    ('I do not need sponsorship now or in the future', "No", "Yes"),
    # Inverted, and naming a moment.
    ("Are you currently authorized to work without sponsorship?", "Yes", "Yes"),
    ("Can you start work today without sponsorship?", "Yes", "Yes"),
    # The plain right to work.
    ("Are you legally eligible to work in the United States?", "Yes", "Yes"),
    ("Do you have the legal right to work in the United States?", "Yes", "Yes"),
    ("Can you legally work in the US?", "Yes", "Yes"),
    ("Are you permitted to work in the United States?", "Yes", "Yes"),
    ("Are you authorised to work in the United States?", "Yes", "Yes"),
    ("Are you legally able to accept employment in the US?", "Yes", "Yes"),
    # Require now or in future, in the spellings forms actually use.
    ("Will you now or will you in the future require sponsorship?", "Yes", "No"),
    ("Do you now, or will you in the future, require visa sponsorship to work here?", "Yes", "No"),
    ("Do you currently, or will you in the future, require sponsorship?", "Yes", "No"),
    ("Do you require sponsorship now or at any point in the future?", "Yes", "No"),
    ("Do you now require sponsorship, or will you require it later on in the future?", "Yes", "No"),
    ("Will you ever need an employer to sponsor you?", "Yes", "No"),
    ("Will you require sponsorship at a later date?", "Yes", "No"),
    ("Would Northwind have to sponsor you to keep you on staff?", "Yes", "No"),
    # Require, present tense only.
    ("Do you require sponsorship now?", "No", "No"),
    ("Would you require sponsorship on your first day?", "No", "No"),
    # Negated, double-negative, or with Yes and No that mean two things.
    ("Are you unable to work in the US without sponsorship?", "?", "?"),
    ("Are you not authorized to work in the United States?", "?", "?"),
    ("Do you not require sponsorship?", "?", "?"),
    ("Will you not need sponsorship now or in the future?", "?", "?"),
    ("Is it false that you will need sponsorship?", "?", "?"),
    ("Do you require sponsorship now but not in the future?", "?", "?"),
    ("Are you authorized to work in the US or will you require sponsorship?", "?", "?"),
    # Conditions, the past, someone else, somewhere else, or no rule at all.
    ("Do you have any restrictions on your work authorization?", "?", "?"),
    ("Is your work authorization temporary?", "?", "?"),
    ("Have you ever required sponsorship?", "?", "?"),
    ("Are you currently sponsored by an employer?", "?", "?"),
    ("Is your spouse authorized to work in the United States?", "?", "?"),
    ("Will your parent require sponsorship now or in the future?", "?", "?"),
    ("Are you authorized to work in Canada?", "?", "?"),
    ("Are you seeking sponsorship?", "?", "?"),
    ("Are you authorised to work in the United Kingdom?", "?", "?"),
    ("Do you hold a valid work permit for the United States?", "?", "?"),
    ("Are you authorized to work in the U.S. for any employer?", "?", "?"),
    ("Can you verify your employment eligibility?", "?", "?"),
    # On the topic, but not a shape the gate can read for certain.
    ("Are you a senior citizen?", "?", "?"),
    ("Are you other than a U.S. citizen?", "?", "?"),
    ("Are you a citizen or permanent resident of Canada?", "?", "?"),
    ("Do you know if Acme requires sponsorship?", "?", "?"),
    ("Does Acme require sponsorship for all hires?", "?", "?"),
    ("Do you need to change your visa status?", "?", "?"),
    # No moment named, so read as the strictest question: a false No cannot pass.
    ("Do you require sponsorship for this position?", "Yes", "No"),
    ("Do you need sponsorship now? Or in the future?", "?", "?"),
    ("Are you authorized to work overtime?", "?", "?"),
    ("Are you able to provide documentation of your work authorization?", "?", "?"),
    ("Is visa sponsorship needed for you to work here?", "Yes", "No"),
    ("Is sponsorship required?", "?", "?"),
    ("Are you authorized to work in the pharmacy?", "?", "?"),
    # Citizenship of somewhere else: no rule for it, so an answer is UNVERIFIED, never silent.
    ("Are you a citizen of the United Kingdom?", "?", "?"),
    # Ordinary questions that must stay out of it.
    ("Do you have any dietary restrictions?", "-", "-"),
    ("Are you authorized to drive a forklift?", "-", "-"),
    ("Have you served in the National Guard?", "-", "-"),
    ("Can you work weekends?", "-", "-"),
    ("Are you able to work on site three days a week?", "-", "-"),
    ("Can you work for us on short notice?", "-", "-"),
    ("Will you need employer support for relocation?", "-", "-"),
    ("Do you expect employer support for a training course?", "-", "-"),
    ("Will you need employer support to work in the US?", "?", "?"),
]

# Your wording lines, read against phrases that only look like them.
_NEGATED_WORDING = {**_TEST_CFG_MAP, "also": {}, "wording": [
    (["u.s. citizen"], "NO", "example: not a citizen."),
    (["permanent resident"], "YES", "example: holds that status."),
]}
_EXPLICIT_WORDING = {**_NEGATED_WORDING, "wording": _NEGATED_WORDING["wording"] + [
    (["non-u.s. citizen"], "YES", "example: the form's own words."),
    (["spouse of a u.s. citizen"], "NO", "example: the form's own words."),
]}
_SHORT_WORDING = {**_TEST_CFG_MAP, "also": {}, "wording": [(["us citizen"], "YES", "example.")]}
WORDING_DOUBT_CASES: list[tuple[str, dict, str, str, str]] = [
    # (label, config, question, verdict on Yes, verdict on No)
    ("non-U.S. citizen, a mapped phrase inside it", _NEGATED_WORDING, "Are you a non-U.S. citizen?", "?", "?"),
    ("not a U.S. citizen", _NEGATED_WORDING, "Are you not a U.S. citizen?", "?", "?"),
    ("a conditional on not being one", _NEGATED_WORDING,
     "If you are not a U.S. citizen, are you a permanent resident?", "?", "?"),
    ("the spouse of a citizen", _NEGATED_WORDING, "Are you the spouse of a U.S. citizen?", "?", "?"),
    ("married to a permanent resident", _NEGATED_WORDING, "Are you married to a permanent resident?", "?", "?"),
    ("a dependent of a citizen", _NEGATED_WORDING, "Are you a dependent of a U.S. citizen?", "?", "?"),
    ("a parent who is a citizen", _NEGATED_WORDING, "Is your parent a U.S. citizen?", "?", "?"),
    ("a former permanent resident", _NEGATED_WORDING, "Are you a former permanent resident?", "?", "?"),
    ("naturalized, a narrower claim", _NEGATED_WORDING, "Are you a naturalized U.S. citizen?", "?", "?"),
    ("a list of statuses one rule cannot settle", _NEGATED_WORDING,
     "Are you a U.S. citizen, national, or permanent resident?", "?", "?"),
    ("citizen or sponsorship, two questions", _NEGATED_WORDING,
     "Are you a U.S. citizen or will you require sponsorship?", "?", "?"),
    ("the plain question still maps", _NEGATED_WORDING, "Are you a U.S. citizen?", "WRONG", "OK"),
    ("the plain second status still maps", _NEGATED_WORDING, "Are you a permanent resident?", "OK", "WRONG"),
    ("a line naming the negation itself settles it", _EXPLICIT_WORDING, "Are you a non-U.S. citizen?", "OK", "WRONG"),
    ("a line naming the third party itself settles it", _EXPLICIT_WORDING,
     "Are you the spouse of a U.S. citizen?", "WRONG", "OK"),
    ("a phrase never matches inside a word, and the rest is no known shape", _SHORT_WORDING,
     "Are you a famous citizen?", "?", "?"),
]

# Through main() on a copy of the shipped template, for each kind of person. Each row is (the line
# after the template's label, then the verdict per person): OK, WRONG or "?" for UNVERIFIED.
_TEMPLATE_LABEL = "- \U0001F534 Work-authorization field(s), worded EXACTLY as the form printed them:"
_NEEDS_LATER_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: YES | example
restricted-authorization: YES | example
wording: u.s. citizen; us citizen; united states citizen; citizen of the united states => NO | example
wording: permanent resident; green card => NO | example
```
"""
_CITIZEN_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: NO | example
restricted-authorization: NO | example
wording: u.s. citizen; us citizen; united states citizen; citizen of the united states => YES | example
wording: permanent resident; green card => NO | example
```
"""
_RESIDENT_KB = _CITIZEN_KB.replace("united states => YES", "united states => NO").replace("green card => NO", "green card => YES")


# A fictional §3 free-text answer for the round 11 rows.
_FREE_TEXT = "I can work for any employer here and need no paperwork from the employer, now or later."


def _ask(q: str, ans: str) -> str:
    return f'  - "{q}" \u2192 {ans}'


# (question, right answer for the person who will need sponsorship, right answer for the citizen).
TEMPLATE_QUESTIONS: list[tuple[str, str, str]] = [
    # Finding: "now or <further>" names a future, or nothing can be said.
    ("Will you need sponsorship, either now or later?", "Yes", "No"),
    ("Will you require sponsorship now or ever?", "Yes", "No"),
    ("Do you need sponsorship now or at any time?", "Yes", "No"),
    ("Will you need sponsorship now or down the road?", "Yes", "No"),
    ("Do you need sponsorship today or later?", "Yes", "No"),
    ("Do you currently, or will you ever, require sponsorship?", "Yes", "No"),
    ("Do you currently need or expect to need sponsorship?", "Yes", "No"),
    ("Do you require sponsorship now or for a promotion?", "?", "?"),
    ("Do you require sponsorship to begin or continue employment?", "?", "?"),
    ("Do you require sponsorship now?", "No", "No"),
    ("Do you require sponsorship to begin employment?", "No", "No"),
    # Finding: a visa, a petition, the right to live and work, a national: no shape it can read.
    ("Do you need a visa to work in the US?", "?", "?"),
    ("Do you need a work visa", "?", "?"),
    ("Are you free of any visa restrictions?", "?", "?"),
    ("Will Acme need to file a petition on your behalf?", "?", "?"),
    ("Will you require immigration support?", "?", "?"),
    ("Can you provide proof of eligibility to work in the United States?", "?", "?"),
    ("Do you have the right to live and work in the United States?", "?", "?"),
    ("Are you a foreign national?", "?", "?"),
    ("Are you a U.S. national?", "?", "?"),
    ("Do you hold a valid work visa?", "?", "?"),
    # Finding: a wording phrase printed inside something that asks something else.
    ("Are you other than a U.S. citizen?", "?", "?"),
    ("Are you applying on behalf of a U.S. citizen?", "?", "?"),
    ("Do you live with a U.S. citizen?", "?", "?"),
    ("Will you become a U.S. citizen?", "?", "?"),
    # Finding: bare "citizen or ..." with the two wording lines setup writes.
    ("Are you a citizen or permanent resident?", "No", "Yes"),
    ("Are you a citizen or permanent resident of the United States?", "No", "Yes"),
    ("Are you a citizen or green card holder?", "No", "Yes"),
    ("Are you a citizen or lawful permanent resident of the U.S.?", "No", "Yes"),
    ("Are you a citizen?", "No", "Yes"),
    ("Are you a U.S. citizen?", "No", "Yes"),
    # Finding (round 9): plainer words for sponsorship were silent, so a wrong answer read as nothing.
    ("Will you now or in the future require employer support for your work status?", "Yes", "No"),
    ("Do you require employer support for your work status to begin employment?", "No", "No"),
    ("Are you authorized to work in the US without employer support for your work status?", "No", "Yes"),
    # Under the template's work-authorization label every recorded question is read or UNVERIFIED. One
    # with no rule (it is not about the right to work) is UNVERIFIED there, so a person moves it out.
    ("Are you over 18?", "?", "?"),
    ("Can you lift 25 pounds?", "?", "?"),
    ("Do you have a work permit?", "?", "?"),
]
# Statement options are not a bare Yes or No, whatever Yes/No is written beside them. Each row is
# (line, verdict for the person who will need sponsorship, verdict for the citizen).
TEMPLATE_OPTIONS: list[tuple[str, str, str]] = [
    ('  - "Please select your work authorization status" \u2192 "I do not require sponsorship" (= No)', "?", "?"),
    ('  - "Please select your work authorization status" \u2192 "I do not require sponsorship" (= Yes)', "?", "?"),
    ('  - "Please select your work authorization status" \u2192 "I will require sponsorship now or in the future" (= Yes)', "?", "?"),
    ('  - "Please select your work authorization status" \u2192 "I will require sponsorship now or in the future" (= No)', "?", "?"),
    ('  - "Please select your work authorization status" \u2192 "Something else entirely" (= No)', "?", "?"),
    ('  - "Select the option that applies" \u2192 "I do not require sponsorship" (= No)', "?", "?"),
    ('  - "Will you now or in the future require sponsorship?" \u2192 "I do not require sponsorship" (= Yes)', "?", "?"),
]
_RIGHT_LINES = "\n".join([
    _ask("Are you legally authorized to work in the United States?", "Yes"),
    _ask("Do you require sponsorship to begin employment?", "No"),
])
_UNCONFIGURED_KB = """# answers
```work-authorization
authorized-now: [YES/NO] | [one-line reason]
sponsorship-to-begin: [YES/NO] | [one-line reason]
sponsorship-now-or-future: [YES/NO] | [one-line reason]
restricted-authorization: [YES/NO] | [one-line reason]
```
"""
_NO_SPONSOR_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: NO | example
restricted-authorization: NO | example
```
"""
_SPONSOR_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: YES | example
restricted-authorization: YES | example
```
"""
_NO_CITIZEN_LINE_KB = _NO_SPONSOR_KB
_CITIZEN_WORDING_KB = _NO_SPONSOR_KB.replace(
    "restricted-authorization: NO | example\n",
    "restricted-authorization: NO | example\nwording: u.s. citizen; permanent resident => NO | not a citizen\n")
_MAPPED_KB = """# answers
```work-authorization
authorized-now: YES | example
sponsorship-to-begin: NO | example
sponsorship-now-or-future: NO | example, changed | also-accept: YES
restricted-authorization: YES | example
wording: for any employer in the us; without employer support => YES | example
```
"""

# The shipped application.md template's own instruction text, word for word.
_TEMPLATE_NOTE = ("[mirrors README. Once you have actually submitted, the agent adds a heading\n"
                  "`## SUBMITTED YYYY-MM-DD` (a local time with its zone may follow) with the on-screen confirmation\n"
                  "evidence under it; shape owned by `.claude/rules/records-format.md`]\n")

COVERAGE_CASES: list[tuple[str, str, bool]] = [
    ("a SUBMITTED dossier with no work-authorization answer at all",
     "# Some Co: Some Role\nStatus: SUBMITTED 2026-01-01\nResume: resume.pdf\n", True),
    ("a not-yet-applied dossier with no answer is fine",
     "# Some Co\nStatus: dossier built, NOT APPLIED\n", False),
    ("a SUBMITTED dossier that records the answers is fine",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- Require sponsorship now or in the future? **Yes**\n", False),
    ("the form carried no work-authorization question, and the dossier says so",
     "**SUBMITTED 2026-01-01.** Confirmation email arrived.\n"
     "- **No visa question on this form.**\n", False),
    ("the same declaration, colon form",
     "- **Status:** **SUBMITTED 2026-01-01** (thank-you page shown).\n"
     "- Visa/EEO questions: **not present on this form**\n", False),
    ("the CITIZENSHIP phrasing of the question, answered honestly",
     "- **Status:** **SUBMITTED 2026-01-01**.\n"
     "- Are you a US Citizen or Green Card holder? **No**\n", False),
    ("a SUBMITTED dossier merely CONTAINING the word visa is still a gap",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- The bakery's visa page was down that week.\n", True),
    ("an unanswered citizenship mention is still a gap",
     "# Co\nStatus: SUBMITTED 2026-01-01\n- Citizenship might come up later in the hiring packet.\n", True),

    # What counts as a submission record. The first is the shipped template's own instruction text.
    ("the template's instruction naming the heading is not a submission",
     _TEMPLATE_NOTE, False),
    ("the placeholder heading at the start of a line is not a submission",
     "## SUBMITTED YYYY-MM-DD\n", False),
    ("'Status: NOT SUBMITTED' is not a submission", "# Co\nStatus: NOT SUBMITTED\n", False),
    ("a sibling opening's date in prose is not a submission",
     "The day shift at Acme was SUBMITTED 2031-03-04, and this one is still a draft.\n", False),
    ("a heading inside an HTML comment is not a submission", "<!-- ## SUBMITTED 2031-03-04 -->\n", False),
    ("a dated heading with no answer is a gap", "## SUBMITTED 2031-03-04\nResume: resume.pdf\n", True),
    ("a heading with a check mark and a note is a gap", "## \u2705 SUBMITTED 2031-03-04 by hand\n", True),
    ("an 'Applied on' line with no answer is a gap", "**Applied on:** 2031-03-04\n", True),
    ("an applied_on field with no answer is a gap", "applied_on: 2031-03-04\n", True),
]

# Citizenship, against the fixture that needs sponsorship (so it is not a citizen).
CITIZEN_CASES: list[tuple[str, str, bool]] = [
    ("'Are you a U.S. citizen?' answered Yes by someone who needs sponsorship: MUST fire",
     '- "Are you a U.S. citizen?" → Yes', True),
    ("the same question answered No: must NOT fire", '- "Are you a U.S. citizen?" → No', False),
    ("the bold shape answered Yes: MUST fire", "- Are you a US citizen? **Yes**", True),
    ("citizen or permanent resident answered Yes: MUST fire",
     "- Are you a citizen or permanent resident of the United States? **Yes**", True),
    ("citizen of the United States answered Yes: MUST fire", "- Are you a citizen of the United States? **Yes**", True),
    ("citizenship of another country answered Yes: must NOT fire",
     "- Are you a citizen of a country other than the United States? **Yes**", False),
    ("citizenship held outside the country answered Yes: must NOT fire",
     "- Do you hold citizenship outside the United States? **Yes**", False),
    ("a citizen of a named other country answered Yes: must NOT fire", "- Are you a citizen of Canada? **Yes**", False),
    ("an open country field is not a yes/no question: must NOT fire",
     '- "Country of citizenship" → Canada', False),
    ("a prose mention with no answer: must NOT fire", "The Hooli packet covers citizenship later on.", False),
]

_WRONG_Q = "- **Does Hooli need to sponsor your work authorization now or in the future? NO**"
_MARK = "<!-- visa:decided ADR-0001 - settled 2026-01-01: the posting closed, nothing left to change -->"

DECISION_CASES: list[tuple[str, str, bool, bool]] = [
    ("a wrong-answer line, SUBMITTED + marked -> still found, downgraded to DECIDED",
     f"Status: SUBMITTED 2026-01-01\n{_WRONG_Q}\n{_MARK}\n", True, True),
    ("the marker on the SAME line also works",
     f"Status: SUBMITTED 2026-01-01\n{_WRONG_Q} {_MARK}\n", True, True),
    ("WALL 2, NOT submitted: the marker is ignored and it stays a full finding",
     f"Status: dossier built, not yet applied\n{_WRONG_Q}\n{_MARK}\n", True, False),
    ("WALL 1, no ADR named: not a decision, stays a full finding",
     "Status: SUBMITTED 2026-01-01\n" + _WRONG_Q +
     "\n<!-- visa:decided no reason on file -->\n", True, False),
    ("WALL 1, an ADR but no reason: stays a full finding",
     f"Status: SUBMITTED 2026-01-01\n{_WRONG_Q}\n<!-- visa:decided ADR-0001 -  -->\n", True, False),
    ("WALL 3, line-scoped: a marker up top does NOT cover a wrong answer further down",
     f"Status: SUBMITTED 2026-01-01\n{_MARK}\n\n- Filler line.\n- Filler line.\n{_WRONG_Q}\n", True, False),
    ("a correct answer with a marker present is still no finding at all",
     f"Status: SUBMITTED 2026-01-01\n- Now or in the future require sponsorship? **Yes**\n{_MARK}\n",
     False, False),
    ("WALL 1b: an INVENTED ADR id must not satisfy the wall",
     f"Status: SUBMITTED 2026-01-01\n{_WRONG_Q}\n<!-- visa:decided ADR-9999 - made up -->\n", True, False),
]


_Q_FUTURE_TEXT = "Will you now or in the future require sponsorship?"
_Q_AUTH_TEXT = "Are you legally authorized to work in the United States?"
# Every shape a question and its answer can take. {q} is the question, {a} the answer, {o} the other option.
ANSWER_SHAPES: list[tuple[str, str]] = [
    ("heading, answer quoted", "### {q} (required)\n\n> {a}."),
    ("heading, plain answer on the next line", "### {q}\n{a}"),
    ("numbered heading", "### Q2. {q} (required)\n\n> {a}."),
    ("heading under an answers heading", "## Exact form answers (as filled)\n\n### {q}\n\n{a}"),
    ("bold question, answer on the next line", "**{q}**\n{a}"),
    ("bold question, blank line, answer", "- **{q}**\n\n  **{a}**"),
    ("plain question, blank line, answer", "{q}\n\n{a}"),
    ("quoted question and answer", "> {q}\n>\n> {a}"),
    ("arrow, box before the chosen option", '- "{q}" \u2192 [x] {a} [ ] {o}'),
    ("capital X", '- "{q}" \u2192 [X] {a} [ ] {o}'),
    ("the empty box first", '- "{q}" \u2192 [ ] {o} [x] {a}'),
    ("plain, trailing period", "- {q} {a}."),
    ("bold, trailing period inside", "- {q} **{a}.**"),
    ("backticks", "- {q} `{a}`"),
    ("quoted value", '- "{q}" \u2192 "{a}"'),
    ("ascii arrow", '- "{q}" -> {a}'),
    ("double arrow", '- "{q}" => {a}'),
    ("equals sign", '- "{q}" = {a}'),
    ("heading level one", "# {q}\n{a}"),
    ("heading level six, quoted answer", "###### {q}\n\n> {a}"),
    ("heading, list dash", "## {q}\n- {a}"),
    ("table row, no number column", "| {q} | {a} |"),
    ("table row, bold", "| {q} | **{a}** |"),
    ("table row, a note column", "| 3 | {q} | {a} | as printed |"),
    ("quoted line, value same line", "> {q} {a}"),
    ("mark, no empty option", '- "{q}" \u2192 [x] {a}'),
    ("one mark, the other option has no box", "{q}\n- [x] {a}\n- {o}"),
    ("Unicode boxes", "- {q} \u2611 {a} \u2610 {o}"),
    ("Unicode box with an X in it", "- {q} \u2612 {a} \u2610 {o}"),
    ("table row with boxes", "| 3 | {q} | [x] {a} [ ] {o} |"),
    ("boxes on the lines below", "{q}\n- [ ] {o}\n- [x] {a}"),
    ("heading, boxes below", "### {q}\n\n- [x] {a}\n- [ ] {o}"),
]
# Recorded, and no answer the gate can positively read: UNVERIFIED for anyone, whichever way they would answer.
UNREAD_SHAPES: list[tuple[str, str]] = [
    ("heading, a value it cannot read", "### {q}\n\nNot sure yet"),
    ("heading, an answer written as a sentence", "### {q}\n\nMy papers let me work for most employers here without trouble."),
    ("bold question, a value it cannot read", "**{q}**\nDepends on the role"),
    ("plain question, blank line, a value it cannot read", "{q}\n\nSee the portal"),
    ("both options, no mark, trailing", "- {q} Yes / No"),
    ("both options, no mark, arrow", '- "{q}" \u2192 Yes / No'),
    ("both boxes empty", "- {q} [ ] Yes [ ] No"),
    ("table row with both options", "| 3 | {q} | Yes / No |"),
    ("the box after its option", "- {q} Yes [x] No [ ]"),
    ("both options on the lines below", "### {q}\n- Yes\n- No"),
    ("a ticked statement with no Yes or No", "- [x] I will require sponsorship now or in the future"),
    ("a plain question and a sentence below it", "{q}\n\nThe form puts this on the second page of the application."),
    ("both options, one per line, words saying which", "{q}\n- Yes\n- No (selected)"),
    ("both options, plain lines, an arrow saying which", "{q}\nYes\nNo <- selected"),
    ("heading, both options, words saying which", "### {q}\n\n- No (selected)\n- Yes"),
    ("two marks on the lines below", "{q}\n- [x] Yes\n- [x] No"),
    ("two marks on one line", '- "{q}" \u2192 [x] Yes [x] No'),
    ("a mark on a statement", "{q}\n- [x] I will not need it\n- [ ] I will need it"),
    ("a label answer on the following line", "{q}\n  Submitted answer: No"),
    ("a quoted option leading with No", '- {q} **"No, I will not need sponsorship"**'),
    ("a quoted option leading with Yes", '- {q} **"Yes, papers on file"**'),
    ("a bare answer with a note in parentheses", "- {q} **No** (no letter needed)"),
    ("a bare answer, then a semicolon note", '- "{q}" \u2192 No; see the note'),
    ("statement option with its meaning written beside it", '- "{q}" \u2192 "I do not require it" (= No)'),
    # About the employer, but a question or label with a Yes or No value: silence needs a reason, and
    # a value is not one.
    ("a research question about the employer, answered", "### Does Acme sponsor visas?\nYes"),
    ("the employer, as a label", "- Company visa policy: No"),
    ("the employer, named as the subject", "- Subject employer sponsorship stance: Yes"),
    ("the posting", "- Posting mentions sponsorship: Yes"),
]
# Nothing recorded, or nothing about you: never an answer and never a new defect.
NOT_AN_ANSWER: list[tuple[str, str]] = [
    ("a heading with a placeholder", "### {q}\n\n> [Yes/No]"),
    ("a heading with TBD", "### {q}\n\nTBD"),
    ("a heading with nothing under it", "### {q}\n\n### Why Hooli?\n\nThe night shift."),
    ("a heading at the end of the file", "### {q}\n"),
    ("a topic heading over its questions", "## Work authorization\n\nThe answers are below."),
    ("a research heading and a note", "### Sponsorship policy\n\nGlobex sponsors some roles, per its careers page."),
    ("a research question about the employer, with a note", "### Does Acme sponsor visas?\n\nIts careers page is silent."),
    ("the next bullet of a list", "- {q}\n- Wants a day shift"),
    ("prose quoting the question", 'Initech asks "{q}" on page two.\n\nNo'),
    ("a to-do about the answers, ticked", "- [x] Confirm the work authorization answers"),
    ("an unticked statement", "- [ ] I will require sponsorship now or in the future"),
    ("options described in brackets", '- "{q}" (dropdown: Yes / No)'),
    ("notes under a sub-heading of the answers", "## Exact form answers\n\n### Notes\n\nNorthwind sponsors some roles, per its site."),
    ("a placeholder after the arrow", '- "{q}" \u2192 [Yes/No]'),
    ("TBD after the arrow", '- "{q}" \u2192 TBD'),
    ("nothing after the arrow", '- "{q}" \u2192'),
    ("an empty table cell", "| 3 | {q} |  |"),
    ("a to-do off the topic, ticked", "- [x] Attach the cover letter"),
    ("the JD", "- JD on sponsorship: not stated"),
    ("they sponsor", "- Sponsorship: they sponsor most hires"),
    ("does not sponsor", "- Sponsorship: Acme does not sponsor"),
    ("ordinary prose", "Visa rules differ by state, and Globex has offices in several."),
]
LABEL_SHAPES: list[tuple[str, str, str]] = [
    ("topic heading, bare answer below", "### Work authorization\n\n{a}", "auth"),
    ("label heading, bare answer below", "### Require sponsorship now or in the future\n\n{a}", "future"),
    ("bold label, ticked box below", "**Work authorization**\n- [x] {a}\n- [ ] {o}", "auth"),
    ("label and colon", "- Work authorization: {a}", "auth"),
    ("bold label and colon", "**Work authorization:** {a}", "auth"),
    ("bold label, bold value", "**Work authorization** **{a}**", "auth"),
    ("label in a table row", "| Work authorization | {a} |", "auth"),
    ("label and colon, sponsorship", "- Require sponsorship now or in the future: {a}", "future"),
    ("label, quoted value below", "> Work authorization\n>\n> {a}", "auth"),
]

# The owner's list, each one on a work-authorization line in every shape: never read, always UNVERIFIED.
STRICT_VALUES: list[str] = [
    "N", "Y", "Not authorized", "Negative", "Will need sponsorship", "true", "false", "True", "False",
    "Yes, but only for now", "No, but later", "Yes but it may change", "(No)", "(Yes)", "[No]", "[Yes]",
    "authorized_to_work: no", "authorized_to_work: yes",
]
_STRICT_SHAPES: list[str] = [
    '- "{q}" \u2192 {v}', "- {q} {v}", "- {q} **{v}**", "### {q}\n\n{v}", "# {q}\n{v}", "###### {q}\n\n> {v}",
    "**{q}**\n{v}", "- **{q}**\n\n  {v}", "{q}\n\n{v}", "> {q}\n>\n> {v}", "| 1 | {q} | {v} |", "| {q} | **{v}** |",
]
_STRICT_LABEL_SHAPES: list[str] = [
    "- Work authorization: {v}", "**Work authorization:** {v}", "### Work authorization\n\n{v}",
    "**Work authorization**\n{v}", "| Work authorization | {v} |", "> Work authorization\n>\n> {v}",
    "- Require sponsorship now or in the future: {v}", "### Require sponsorship now or in the future\n{v}",
]
_MUTATED_NEGATIVES: list[str] = [
    "Nope", "Never", "Not at this time", "None needed", "Not required", "Does not apply",
    "Absolutely not", "I am not", "Cannot", "Declined", "Not eligible", "No way",
]
_MUTATED_POSITIVES: list[str] = [
    "Yep", "Yeah", "Sure", "Affirmative", "Correct", "I am", "I do", "Authorized",
    "Absolutely", "OK", "Eligible", "Yes indeed",
]
# Ticked statements, and options with no real mark, on any question.
_STRICT_OPTION_ROWS: list[str] = [
    "- [x] I am authorized to work in the United States", "- [X] I do not need sponsorship",
    '- "{q}" \u2192 Yes / No', "- {q} [ ] Yes [ ] No", "- {q} [x] Yes [x] No", "{q}\nYes\nNo <- selected",
    "{q}\n- Yes\n- No (selected)",
]
_STATEMENT = "I do not require sponsorship"
_WORDING_VALUE_CFG = {"wording": [([_STATEMENT.lower()], "NO", "example: that option means No.")]}
_STATUS_YES = {"wording": [(["u.s. citizen"], "YES", "example: holds that status.")]}
_STATUS_NO = {"wording": [(["u.s. citizen"], "NO", "example: does not hold that status.")]}
# (label, config, text, verdict): rule 3, a value exactly equal to a wording you recorded.
RECORDED_WORDING_CASES: list[tuple[str, dict, str, str]] = [
    ("exact wording, the question's rule says No", {**_NO_CONDITIONS, **_WORDING_VALUE_CFG},
     f'- "{_Q_FUTURE_TEXT}" \u2192 "{_STATEMENT}"', "OK"),
    ("exact wording, case and period aside", {**_NO_CONDITIONS, **_WORDING_VALUE_CFG},
     f'- "{_Q_FUTURE_TEXT}" \u2192 "{_STATEMENT.upper()}."', "OK"),
    ("exact wording on the next line", {**_NO_CONDITIONS, **_WORDING_VALUE_CFG}, f"### {_Q_FUTURE_TEXT}\n\n> {_STATEMENT}", "OK"),
    ("exact wording, the question's rule says Yes: wrong", {**_TEST_CFG, **_WORDING_VALUE_CFG},
     f'- "{_Q_FUTURE_TEXT}" \u2192 "{_STATEMENT}"', "WRONG"),
    ("exact wording on a generic prompt settles the line", {**_NO_CONDITIONS, **_WORDING_VALUE_CFG},
     f'- "Select the option that applies" \u2192 "{_STATEMENT}"', "OK"),
    ("one word added is not the wording", {**_NO_CONDITIONS, **_WORDING_VALUE_CFG},
     f'- "{_Q_FUTURE_TEXT}" \u2192 "{_STATEMENT} now"', "?"),
    ("with no such wording recorded", _NO_CONDITIONS, f'- "{_Q_FUTURE_TEXT}" \u2192 "{_STATEMENT}"', "?"),
    ("a status you hold, on a status field", {**_NO_CONDITIONS, **_STATUS_YES}, '- "Citizenship status" \u2192 "U.S. citizen"', "OK"),
    ("a status your line says you do not hold", {**_NO_CONDITIONS, **_STATUS_NO}, '- "Citizenship status" \u2192 "U.S. citizen"', "?"),
]


# Silence needs a reason, and only a whole question is read. Each row is (text with {a} for the answer,
# what it reads as): "F", "A" or "B" = read as that class and checked; "?" = UNVERIFIED for either
# answer; "S" = silent by a reason on the closed list. Run under a Yes and a No persona, both answers.
_FQ = "Will you now or in the future require sponsorship?"
_AQ = "Are you legally authorized to work in the United States?"
STRUCTURE_ROWS: list[tuple[str, str]] = [
    # B: a Yes or No outside the value slot.
    (f'- We answered {{a}} to "{_FQ}"', "?"),
    (f"- {{a}} - {_FQ}", "?"),
    (f"- [x] {{a}}: {_FQ}", "?"),
    (f'Answer to "{_FQ}" was {{a}}', "?"),
    (f'- "{_FQ}" (dropdown: {{a}})', "?"),
    (f'- "{_FQ}" (required: {{a}})', "?"),
    (f'- "{_FQ}" (radio: {{a}})', "?"),
    (f'- "{_FQ}" (select {{a}})', "?"),
    (f'- "{_FQ}" → {{a}} (sponsorship field)', "?"),
    ("- Sponsorship question → {a} (sponsorship field)", "?"),
    (f"- Are you over 18? {_FQ} {{a}}", "?"),
    (f'- "{_AQ}" (dropdown: {{a}})', "?"),
    (f"- {{a}} - {_AQ}", "?"),
    # C: words after the place name, or after "without".
    ('- "Are you authorized to work in the US without a visa?" → {a}', "?"),
    ('- "Can you work in the US without a visa?" → {a}', "?"),
    ('- "Are you authorized to work in the US for the next 3 years?" → {a}', "?"),
    ('- "Are you authorized to work in the US through 2030?" → {a}', "?"),
    ('- "Will you be able to work in the US without a visa?" → {a}', "?"),
    ('- "Are you authorized to work in the United States, and do you hold a forklift licence?" → {a}', "?"),
    ('- "Are you authorized to work without a visa?" → {a}', "?"),
    ('- "Are you able to accept employment in the US without a visa?" → {a}', "?"),
    # D: the wider topic, read only when the class fits exactly.
    ('- "Do you have work rights in the US?" → {a}', "?"),
    ('- "Are you able to accept employment in the US?" → {a}', "?"),
    ('- "Do you have legal status to work in the US?" → {a}', "?"),
    ('- "Are you lawfully present in the United States?" → {a}', "?"),
    ('- "Are you eligible to work in the US?" → {a}', "A"),
    ('- "Do you have the right to work in the US?" → {a}', "A"),
    # E: must stay read, in the template's shape.
    ('- "If we offer you a position, will you now or in the future require visa sponsorship?" → {a}', "F"),
    ('"If we were to offer you this job, would you need sponsorship?" → {a}', "F"),
    ('- "If an offer is extended, will you require sponsorship to begin employment?" → {a}', "B"),
    ('- "If you receive an offer, are you legally authorized to work in the United States?" → {a}', "A"),
    ('- "Authorized to work for this employer" → {a}', "A"),
    ("- Eligible to work for this employer: {a}", "A"),
    ("- Employer sponsorship: {a}", "?"),
    ("- Sponsorship from this employer: {a}", "?"),
    ("Sponsorship by employer: {a}", "?"),
    ("- Authorized to work for this company: {a}", "A"),
    # A conditional opener that carries its own negation is not set aside.
    ('- "If we offer you a role without sponsorship, will you accept?" → {a}', "?"),
    # A: the closed list of reasons for silence.
    ("- Work-authorization field(s): not present on this form", "S"),
    ("- No visa question on this form.", "S"),
    ("- **No sponsorship question on this form.**", "S"),
    ("- No visa question on this form, so I put {a}.", "?"),
    ("Globex offers no sponsorship for contract roles.", "S"),
    # a Yes or No word anywhere after the employer phrase leaves it for a person (R25: the design working)
    ("We do not sponsor, and there are no exceptions.", "?"),
    ("The company does not sponsor visas, so the answer is {a}.", "?"),
    (f'- "{_FQ}" → [Yes/No]', "S"),
    (f'- "{_FQ}" (dropdown: Yes / No)', "S"),
    (f'- "{_FQ}" (I picked {{a}} at first)', "?"),
    ('- "Are you a citizen of Canada?" → {a}', "?"),
]
_STRUCT_CLASS = {"F": Q_FUTURE, "A": Q_AUTH, "B": Q_BEGIN}


def _structure_want(kind: str, cfg: dict, ans: str) -> str:
    if kind in ("?", "S"):
        return "?" if kind == "?" else "OK"
    return "OK" if cfg["expected"][_STRUCT_CLASS[kind]].capitalize() == ans else "WRONG"


# The meta-test: on-topic lines holding a Yes or No in odd positions. None has a bare answer in the
# value slot of a question that fits a class exactly, so each must be UNVERIFIED: never silent, never OK.
ODD_POSITION_LINES: list[str] = [
    f"Yes - {_FQ}", f"- {_FQ} - answered Yes", f"- (Yes) {_FQ}", f"- {_FQ} (Yes)", f"- {_FQ} Yes, see notes",
    f"- {_FQ} I said No", f"- {_FQ} -- No", f"- {_FQ} No?", "- Sponsorship (No) needed now or in the future?",
    "- No sponsorship needed now or in the future? Yes", f"- {_AQ} [Yes]", f"- {_AQ} **Yes** (for now)",
    f"- {_AQ} Yes/No: Yes", f"- Re: No to {_AQ}",f'> I put No for "{_AQ}"', f"- {_AQ} → No, then changed to Yes",
    f'- {_AQ} → "No" (draft)', f"- {_AQ} → N/A (No)", f"- [ ] Yes [x] {_AQ}",
    "- Authorized to work in the US (Yes)", "- Work authorization: see form (No)", f"| {_AQ} | see notes, Yes |",
    f"| Yes | {_AQ} |", f"| {_AQ} | Yes | No idea |", f"Yes: {_AQ}", f"**Yes** {_AQ}", f"- {_AQ} ~~No~~ Yes",
    f"- {_AQ} No (crossed out) Yes", f"- {_FQ} → Yes → No", f'- "{_FQ}": "No" / "Yes"',
    "- Sponsorship? No; authorized? Yes", f"- {_FQ} Answer: No", f"- {_FQ} (No - see note)",
    f'- {_FQ} "Yes" was the default, changed', "- Sponsorship needed in future? No comment",
    "- If asked about sponsorship, answer No", f'- The form asked "{_FQ}" and I chose Yes', f"- {_FQ}... No",
    f"- {_AQ} YES!!", f"- {_FQ}\n  ^ No", "- Are you a citizen of Canada? Yes",
    "- Do you have work rights in the US? No", "- Can you work in the US without a visa? Yes",
]
# Controls: a bare answer in the value slot of a question that fits a class exactly is read.
READ_CONTROLS: list[str] = [f"- {_FQ} No", f'- "{_AQ}" → Yes', f"| {_FQ} | **Yes** |", f"- {_AQ} **No**"]


def _shape_rows():
    """(label, config, text, verdict wanted) for the shape tables, under a Yes and a No person."""
    people = (("future Yes", _TEST_CFG), ("future No", _NO_CONDITIONS))
    other = {"Yes": "No", "No": "Yes"}
    for who, cfg in people:
        right = cfg["expected"][Q_FUTURE].capitalize()
        for label, shape in ANSWER_SHAPES:
            for a, want in ((right, "OK"), (other[right], "WRONG")):
                yield f"[{who}] {label}, {a}", cfg, shape.format(q=_Q_FUTURE_TEXT, a=a, o=other[a]), want
        for label, shape in UNREAD_SHAPES:
            yield f"[{who}] {label}", cfg, shape.format(q=_Q_FUTURE_TEXT), "?"
        for label, shape in NOT_AN_ANSWER:
            yield f"[{who}] {label}", cfg, shape.format(q=_Q_FUTURE_TEXT), "OK"
        for label, shape, q_kind in LABEL_SHAPES:
            r = "Yes" if q_kind == "auth" else right
            for a, want in ((r, "OK"), (other[r], "WRONG")):
                yield f"[{who}] {label}, {a}", cfg, shape.format(a=a, o=other[a]), want
    # The question that is Yes for both people, so a wrong No is caught whichever way future goes.
    for who, cfg in people:
        for label, shape in ANSWER_SHAPES:
            for a, want in (("Yes", "OK"), ("No", "WRONG")):
                yield f"[{who}] authorized, {label}, {a}", cfg, shape.format(q=_Q_AUTH_TEXT, a=a, o=other[a]), want


def _verdict(text: str, cfg: dict) -> str:
    """What the gate says about this text: WRONG, UNVERIFIED (as "?") or OK."""
    if scan_text("t.md", text, cfg):
        return "WRONG"
    if unreadable_answers(text, cfg) or citizenship_unknown(text, cfg) or unclassified_answers(text, cfg):
        return "?"
    return "OK"


def selftest() -> int:
    passed = failed = 0
    print("visa_gate.py selftest: a fixed fictional configuration, independent of any real KB file\n")
    for label, text, should in CASES:
        got = bool(scan_text("t.md", text, _TEST_CFG))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    for label, text, should in COVERAGE_CASES:
        got = coverage_gap("t.md", text) is not None
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    for label, text, should in CITIZEN_CASES:
        got = bool(scan_text("t.md", text, _TEST_CFG))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    for label, cfg, text, should in CITIZEN_WORDING_CASES:
        got = bool(scan_text("t.md", text, cfg))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    for question, needs_later, no_conditions in PHRASING_TABLE:
        for cfg, right, who in ((_TEST_CFG, needs_later, "needs it later"), (_NO_CONDITIONS, no_conditions, "no conditions")):
            for ans in ("Yes", "No"):
                want = "?" if right == "?" else "OK" if right in ("-", ans) else "WRONG"
                got = _verdict(f'- "{question}" \u2192 {ans}', cfg)
                ok = got == want
                passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                if not ok:
                    print(f"  \u2717 PHRASING  [{who}] {question} -> {ans}: got {got}, want {want}")
    print(f"  phrasing table: {len(PHRASING_TABLE)} questions, two people, both answers")
    shape_rows = 0
    for label, cfg, text, want in _shape_rows():
        got = _verdict(text, cfg)
        ok = got == want
        shape_rows += 1
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if not ok:
            print(f"  \u2717 SHAPE     {label}: got {got}, want {want}")
    print(f"  question-and-answer shapes: {shape_rows} rows, two people")
    strict_rows = 0
    for who, cfg in (("future Yes", _TEST_CFG), ("future No", _NO_CONDITIONS)):
        for q in (_Q_FUTURE_TEXT, _Q_AUTH_TEXT):
            for shape in _STRICT_SHAPES:
                for v in STRICT_VALUES:
                    text, got = shape.format(q=q, v=v), None
                    got = _verdict(text, cfg)
                    strict_rows += 1
                    passed, failed = (passed + 1, failed) if got == "?" else (passed, failed + 1)
                    if got != "?":
                        print(f"  \u2717 STRICT    [{who}] {text!r}: got {got}, want ?")
                for v in _MUTATED_NEGATIVES + _MUTATED_POSITIVES:
                    text = shape.format(q=q, v=v)
                    got = _verdict(text, cfg)
                    strict_rows += 1
                    passed, failed = (passed + 1, failed) if got != "OK" else (passed, failed + 1)
                    if got == "OK":
                        print(f"  \u2717 MUTATION  [{who}] {text!r}: read as a clean answer")
            for shape in _STRICT_OPTION_ROWS:
                text = shape.format(q=q)
                got = _verdict(text, cfg)
                strict_rows += 1
                passed, failed = (passed + 1, failed) if got == "?" else (passed, failed + 1)
                if got != "?":
                    print(f"  \u2717 OPTIONS   [{who}] {text!r}: got {got}, want ?")
        for shape in _STRICT_LABEL_SHAPES:
            for v in STRICT_VALUES:
                text = shape.format(v=v)
                got = _verdict(text, cfg)
                strict_rows += 1
                passed, failed = (passed + 1, failed) if got == "?" else (passed, failed + 1)
                if got != "?":
                    print(f"  \u2717 STRICT    [{who}] {text!r}: got {got}, want ?")
            for v in _MUTATED_NEGATIVES + _MUTATED_POSITIVES:
                text = shape.format(v=v)
                got = _verdict(text, cfg)
                strict_rows += 1
                passed, failed = (passed + 1, failed) if got != "OK" else (passed, failed + 1)
                if got == "OK":
                    print(f"  \u2717 MUTATION  [{who}] {text!r}: read as a clean answer")
    print(f"  strict allowlist: {strict_rows} rows, two people")
    for label, cfg, text, want in RECORDED_WORDING_CASES:
        got = _verdict(text, cfg)
        ok = got == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} RECORDED  {label}: {got}" + ("" if ok else f" (want {want})"))
    for label, cfg, question, on_yes, on_no in WORDING_DOUBT_CASES:
        for ans, want in (("Yes", on_yes), ("No", on_no)):
            got = _verdict(f'- "{question}" \u2192 {ans}', cfg)
            ok = got == want
            passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
            print(f"  {'✓' if ok else '✗'} WORDING   {label} -> {ans}: {got}" + ("" if ok else f" (want {want})"))
    struct_rows = 0
    for who, cfg in (("future Yes", _TEST_CFG), ("future No", _NO_CONDITIONS)):
        for text, kind in STRUCTURE_ROWS:
            for ans in ("Yes", "No"):
                want = _structure_want(kind, cfg, ans)
                got = _verdict(text.format(a=ans), cfg)
                struct_rows += 1
                passed, failed = (passed + 1, failed) if got == want else (passed, failed + 1)
                if got != want:
                    print(f"  ✗ STRUCTURE [{who}] {text.format(a=ans)!r}: got {got}, want {want}")
        for text in ODD_POSITION_LINES:
            got = _verdict(text, cfg)
            struct_rows += 1
            passed, failed = (passed + 1, failed) if got == "?" else (passed, failed + 1)
            if got != "?":
                print(f"  ✗ META      [{who}] {text!r}: got {got}, want ? (never silent, never OK)")
        for text in READ_CONTROLS:
            got = _verdict(text, cfg)
            struct_rows += 1
            passed, failed = (passed + 1, failed) if got in ("OK", "WRONG") else (passed, failed + 1)
            if got not in ("OK", "WRONG"):
                print(f"  ✗ META      [{who}] control {text!r}: got {got}, want it read")
    # Every odd line is on the topic and holds a Yes or No, or the meta-test proves nothing.
    meta_real = all(_on_topic(t) and _YN_WORD.search(t) for t in ODD_POSITION_LINES) and len(ODD_POSITION_LINES) >= 40
    passed, failed = (passed + 1, failed) if meta_real else (passed, failed + 1)
    print(f"  {'✓' if meta_real else '✗'} META      {len(ODD_POSITION_LINES)} odd-position lines, each on the topic "
          f"with a Yes or No")
    print(f"  silence-needs-a-reason and whole-question rows: {struct_rows}, two people")
    print()
    # The ADR named by the fixture sits in a throwaway folder, so these cases never depend on what a
    # copy keeps under ops/decisions.
    import tempfile as _tf
    global REPO
    saved_repo = REPO
    with _tf.TemporaryDirectory() as td:
        REPO = Path(td)
        (REPO / "ops" / "decisions").mkdir(parents=True)
        (REPO / "ops" / "decisions" / "0001-example.md").write_text("# example\n", encoding="utf-8")
        try:
            for label, text, want_find, want_decided in DECISION_CASES:
                fs = scan_text("t.md", text, _TEST_CFG)
                got_find = bool(fs)
                got_decided = bool(fs and fs[0].decided)
                ok = got_find == want_find and got_decided == want_decided
                passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                if ok:
                    mark = "✓ DECIDED " if want_decided else ("✓ CAUGHT  " if want_find else "✓ allowed ")
                else:
                    mark = "✗ WRONG   "
                print(f"  {mark}  {label}")
        finally:
            REPO = saved_repo
    print()
    for label, text, should in MAP_CASES:
        got = bool(scan_text("t.md", text, _TEST_CFG_MAP))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()
    # Parsing and the unconfigured path, against throwaway KB files and dossiers.
    import contextlib
    import io
    import tempfile
    global KB_ANSWERS, targets
    saved_kb = KB_ANSWERS
    rec = "- Will you now or in the future require sponsorship? **Yes**\n"
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        try:
            KB_ANSWERS = tdp / "kb.md"
            KB_ANSWERS.write_text(_MAPPED_KB, encoding="utf-8")
            cfg = load_expected() or {}
            parse_ok = (cfg.get("also") == {Q_FUTURE: {"YES"}}
                        and [w[0] for w in cfg.get("wording", [])] == [["for any employer in the us", "without employer support"]])
            KB_ANSWERS.write_text(_UNCONFIGURED_KB, encoding="utf-8")
            unconf_none = load_expected() is None
            example = _NO_SPONSOR_KB.replace("# answers\n", "")
            KB_ANSWERS.write_text(f"<!--\n{example}-->\n" + _UNCONFIGURED_KB, encoding="utf-8")
            comment_above_none = load_expected() is None
            KB_ANSWERS.write_text(f"<!--\n{example}-->\n" + _MAPPED_KB, encoding="utf-8")
            comment_real = (load_expected() or {}).get("restricted") is True
            KB_ANSWERS.write_text(_NO_SPONSOR_KB.replace("```work-authorization\n", "```work-authorization\n<!--\n")
                                  .replace("example\n```", "example\n-->\n```"), encoding="utf-8")
            comment_inside_none = load_expected() is None
            KB_ANSWERS.write_text(f"<!-- never closed\n{example}", encoding="utf-8")
            comment_open_none = load_expected() is None
            (tdp / "with.md").write_text(rec, encoding="utf-8")
            (tdp / "without.md").write_text("# A dossier with no answers yet\n", encoding="utf-8")
            with_buf = io.StringIO()
            with contextlib.redirect_stdout(with_buf):
                rc_with = main([str(tdp / "with.md")])
            with contextlib.redirect_stdout(io.StringIO()):
                rc_without = main([str(tdp / "without.md")])
            KB_ANSWERS = tdp / "missing.md"
            with contextlib.redirect_stdout(io.StringIO()):
                rc_missing = main([str(tdp / "with.md")])
            # The two observed false-CLEANs, through main(), against a KB that needs no sponsorship.
            KB_ANSWERS = tdp / "kb-none.md"
            KB_ANSWERS.write_text(_NO_SPONSOR_KB, encoding="utf-8")
            shapes = {
                "arrow": '- "Will you now or in the future require sponsorship for employment visa '
                         'status?" → Yes\n',
                "plain": "- Will you now or in the future require sponsorship? Yes\n",
                "unreadable": '## Exact form answers (as filled, 2026-01-01)\n\n- "Will you now or '
                              'in the future require sponsorship?" → I selected the second option\n',
                "unreadable_slot": '- "Do you require sponsorship to begin employment?" → see notes\n',
                "listing": '## Form questions\n\n- "Will you now or in the future require '
                           'sponsorship?" (dropdown: Yes / No)\n',
                "right": '## Exact form answers (as filled, 2026-01-01)\n\n- "Will you now or in the '
                         'future require sponsorship?" → No\n',
            }
            rcs = {}
            for name, body in shapes.items():
                (tdp / f"{name}.md").write_text(body, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    rcs[name] = main([str(tdp / f"{name}.md")])
            # The citizenship question through main(), one KB shape at a time.
            claim = tdp / "claim.md"
            claim.write_text('- "Are you a U.S. citizen?" → Yes\n', encoding="utf-8")
            denial = tdp / "denial.md"
            denial.write_text('- "Are you a U.S. citizen?" → No\n', encoding="utf-8")
            template_note = tdp / "template-note.md"
            template_note.write_text(_TEMPLATE_NOTE, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc_note = main([str(template_note)])
            # A line the gate cannot read must fail the run and print no CLEAN, configured or not.
            doubt = tdp / "doubt.md"
            doubt.write_text('- "Are you unable to work in the US without sponsorship?" \u2192 No\n', encoding="utf-8")
            KB_ANSWERS.write_text(_SPONSOR_KB, encoding="utf-8")
            doubt_buf = io.StringIO()
            with contextlib.redirect_stdout(doubt_buf):
                rc_doubt = main([str(doubt)])
            KB_ANSWERS.write_text(_UNCONFIGURED_KB, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc_doubt_unconf = main([str(doubt)])
            KB_ANSWERS.write_text(_NO_SPONSOR_KB, encoding="utf-8")
            cit = {}
            for name, body in (("sponsor", _SPONSOR_KB), ("none", _NO_CITIZEN_LINE_KB), ("wording", _CITIZEN_WORDING_KB)):
                KB_ANSWERS.write_text(body, encoding="utf-8")
                for fname, path in (("claim", claim), ("denial", denial)):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        rc = main([str(path)])
                    cit[name, fname] = (rc, "UNVERIFIED" in out.getvalue(), "CLEAN" in out.getvalue())
        finally:
            KB_ANSWERS = saved_kb
    for label, good in [
        ("CONFIG    also-accept and wording lines parse from the block", parse_ok),
        ("CONFIG    an unfilled template block reads as NOT configured", unconf_none),
        ("CONFIG    a filled example inside an HTML comment is never read as the answer", comment_above_none),
        ("CONFIG    the real block is read past a commented example", comment_real),
        ("CONFIG    answer lines commented out inside the block are not read", comment_inside_none),
        ("CONFIG    an unclosed comment hides what follows it", comment_open_none),
        ("CONFIG    unconfigured + a recorded answer exits 1 (UNVERIFIED, never a pass)", rc_with == 1),
        ("CONFIG    ... and tags the file [UNVERIFIED], so the Stop hook blocks on it",
         re.search(r"^  \[UNVERIFIED\] \S*with\.md\b", with_buf.getvalue(), re.M) is not None),
        ("CONFIG    unconfigured + nothing recorded exits 3 (not checked), never 0", rc_without == EXIT_NOT_CHECKED),
        ("CONFIG    a missing answers file behaves the same as unconfigured (no crash)", rc_missing == 1),
        ("SHAPE     template arrow answer, wrong vs KB, exits 1 (was CLEAN)", rcs["arrow"] == 1),
        ("SHAPE     plain-text trailing answer, wrong vs KB, exits 1 (was CLEAN)", rcs["plain"] == 1),
        ("SHAPE     an unreadable answer under an answers heading exits 1 (UNVERIFIED)", rcs["unreadable"] == 1),
        ("SHAPE     an unreadable answer after an arrow exits 1 (UNVERIFIED)", rcs["unreadable_slot"] == 1),
        ("SHAPE     a question listing with its options is not an answer: nothing read, exits 3",
         rcs["listing"] == EXIT_NOT_CHECKED),
        ("SHAPE     the right answer in the canonical shape exits 0", rcs["right"] == 0),
        ("SHAPE     the template's instruction text alone: no defect, nothing read, exits 3",
         rc_note == EXIT_NOT_CHECKED),
        ("UNSURE    a line it cannot read exits 1, says UNVERIFIED, prints no CLEAN",
         rc_doubt == 1 and "UNVERIFIED" in doubt_buf.getvalue() and "CLEAN" not in doubt_buf.getvalue()),
        ("UNSURE    the same line with section 3 unfilled exits 1, never 3", rc_doubt_unconf == 1),
        ("CITIZEN   needs sponsorship, records Yes: exit 1 (was CLEAN)", cit["sponsor", "claim"][0] == 1),
        ("CITIZEN   needs sponsorship, records No: exit 0", cit["sponsor", "denial"] == (0, False, True)),
        ("CITIZEN   wording line says NO, records Yes: exit 1 (was ignored)", cit["wording", "claim"][0] == 1),
        ("CITIZEN   wording line says NO, records No: exit 0", cit["wording", "denial"] == (0, False, True)),
        ("CITIZEN   nothing settles it, Yes: UNVERIFIED exit 1, never CLEAN", cit["none", "claim"] == (1, True, False)),
        ("CITIZEN   nothing settles it, No: UNVERIFIED exit 1, never CLEAN", cit["none", "denial"] == (1, True, False)),
    ]:
        passed, failed = (passed + 1, failed) if good else (passed, failed + 1)
        print(f"  {'✓' if good else '✗'} {label}")
    # The default sweep skips scaffold dossiers (S5): a TEMPLATE- dossier whose instructions name a
    # `## SUBMITTED YYYY-MM-DD` heading must never read as a submitted application.
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for name in ("TEMPLATE-company-role", "EXAMPLE-fixture", "acme-security-engineer"):
            (tdp / "applications" / name).mkdir(parents=True)
            (tdp / "applications" / name / "application.md").write_text(
                "Write `## SUBMITTED YYYY-MM-DD` here once sent.\n", encoding="utf-8")
        got = [p.parent.name for p in targets(tdp)]
    skip_ok = got == ["acme-security-engineer"]
    passed, failed = (passed + 1, failed) if skip_ok else (passed, failed + 1)
    print(f"  {'✓' if skip_ok else '✗'} SWEEP     TEMPLATE-/EXAMPLE- dossiers are skipped; a real one is not")
    # A scaffold named outright is skipped too: the fixture's sample answer is nobody's real answer.
    saved_kb = KB_ANSWERS
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "EXAMPLE-fixture").mkdir()
        fixture = tdp / "EXAMPLE-fixture" / "application.md"
        fixture.write_text("### Q2. Are you authorized to work in this country? (required)\n\n> No.\n", encoding="utf-8")
        try:
            KB_ANSWERS = tdp / "kb.md"
            KB_ANSWERS.write_text(_SPONSOR_KB, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc_scaffold = main([str(fixture)])
        finally:
            KB_ANSWERS = saved_kb
    named_ok = rc_scaffold == EXIT_NOT_CHECKED
    passed, failed = (passed + 1, failed) if named_ok else (passed, failed + 1)
    print(f"  {'✓' if named_ok else '✗'} SWEEP     a scaffold named on the command line is skipped (exit {rc_scaffold})")
    # A commented-out block is blanked, not removed: the real answer below it keeps its true line number.
    found = scan_text("t.md", '<!-- old\n- "Are you a U.S. citizen?" \u2192 No\n-->\n- "Are you a U.S. citizen?" \u2192 Yes',
                      _PERMANENT_RESIDENT_MAP)
    line_ok = [f.line_no for f in found] == [4]
    passed, failed = (passed + 1, failed) if line_ok else (passed, failed + 1)
    print(f"  {'✓' if line_ok else '✗'} COMMENT   a multi-line comment is skipped and line numbers hold")
    # The line the gate tells you to add must be one status per line, and must parse once filled in.
    saved_kb = KB_ANSWERS
    with tempfile.TemporaryDirectory() as td:
        try:
            KB_ANSWERS = Path(td) / "kb.md"
            filled = "\n".join(h.replace("[YES/NO]", a).replace("[one-line reason]", "example")
                               for h, a in zip(CITIZEN_WORDING_HINT, ("NO", "YES")))
            KB_ANSWERS.write_text(_NO_SPONSOR_KB.replace("restricted-authorization:", filled + "\nrestricted-authorization:", 1),
                                  encoding="utf-8")
            hint_cfg = load_expected()
        finally:
            KB_ANSWERS = saved_kb
    one_each = all(("citizen" in h) != ("permanent resident" in h) for h in CITIZEN_WORDING_HINT)
    hint_ok = one_each and bool(hint_cfg) and [w[1] for w in hint_cfg.get("wording", [])] == ["NO", "YES"]
    passed, failed = (passed + 1, failed) if hint_ok else (passed, failed + 1)
    print(f"  {'✓' if hint_ok else '✗'} HINT      the suggested wording lines are one status each and parse when filled in")
    # A filled-in section 3 with no dossier yet says so, instead of a CLEAN over zero files.
    saved_kb, saved_targets = KB_ANSWERS, targets
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        try:
            KB_ANSWERS = tdp / "kb.md"
            KB_ANSWERS.write_text(_NO_SPONSOR_KB, encoding="utf-8")
            targets = lambda root=None: []
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc_none = main([])
            with contextlib.redirect_stdout(io.StringIO()):
                rc_gone = main([str(tdp / "no-such-file.md")])
        finally:
            KB_ANSWERS, targets = saved_kb, saved_targets
    none_ok = rc_none == EXIT_NOT_CHECKED and "no work-authorization answer was read" in buf.getvalue() \
        and "CLEAN" not in buf.getvalue()
    gone_ok = rc_gone == EXIT_NOT_CHECKED
    for label, good in [("SWEEP     filled-in section 3, no dossier: exit 3, says nothing was read, no CLEAN", none_ok),
                        ("SWEEP     a named path that is not a file exits 3 (not checked), never CLEAN", gone_ok)]:
        passed, failed = (passed + 1, failed) if good else (passed, failed + 1)
        print(f"  {'✓' if good else '✗'} {label}")
    # The template, through main(): pristine it is not a defect, filled it reads only its answers.
    def _template() -> str:
        path = REPO / "applications" / "TEMPLATE-company-role" / "application.md"
        body = path.read_text(encoding="utf-8") if path.is_file() else ""
        return body if _TEMPLATE_LABEL in body else f"## Exact form answers (as filled)\n\n{_TEMPLATE_LABEL}\n"

    def _run(kb: str, body: str, td: Path) -> str:
        global KB_ANSWERS
        KB_ANSWERS = td / "kb.md"
        KB_ANSWERS.write_text(kb, encoding="utf-8")
        (td / "application.md").write_text(body, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([str(td / "application.md")])
        text = out.getvalue()
        if rc == 0 and "CLEAN" in text and "UNVERIFIED" not in text:
            return "OK"
        if rc == 1 and "WRONG ANSWER" in text and "UNVERIFIED" not in text:
            return "WRONG"
        if rc == 1 and "UNVERIFIED" in text and "CLEAN" not in text and "WRONG ANSWER" not in text:
            return "?"
        if rc == EXIT_NOT_CHECKED and "no work-authorization answer was read" in text and "CLEAN" not in text:
            return "NONE"
        return f"rc={rc}"

    saved_kb = KB_ANSWERS
    template = _template()
    filled_in = template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + _RIGHT_LINES)
    rows = 0
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        try:
            people = [("needs later", _NEEDS_LATER_KB), ("citizen", _CITIZEN_KB)]
            for who, kb in people + [("resident", _RESIDENT_KB)]:
                # Pristine: no defect and nothing read, so exit 3 (never a CLEAN over zero answers).
                for name, body, want in (("pristine", template, "NONE"), ("filled", filled_in, "OK")):
                    got = _run(kb, body, tdp)
                    ok = got == want
                    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                    print(f"  {'✓' if ok else '✗'} TEMPLATE  {name} copy, {who}: {got}")
            KB_ANSWERS = tdp / "kb.md"
            KB_ANSWERS.write_text(_UNCONFIGURED_KB, encoding="utf-8")
            (tdp / "application.md").write_text(template, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc_blank = main([str(tdp / "application.md")])
            ok = rc_blank == EXIT_NOT_CHECKED
            passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
            print(f"  {'✓' if ok else '✗'} TEMPLATE  pristine copy, section 3 unfilled: exit {rc_blank}")
            for q, later, citizen in TEMPLATE_QUESTIONS:
                for (who, kb), right in zip(people, (later, citizen)):
                    for ans in ("Yes", "No"):
                        want = "?" if right == "?" else "OK" if right == ans else "WRONG"
                        line = _ask(q, ans)
                        got = _run(kb, template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + line), tdp)
                        ok = got == want
                        rows += 1
                        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                        if not ok:
                            print(f"  \u2717 TEMPLATE  [{who}] {q} -> {ans}: got {got}, want {want}")
            for q in ("Are you a citizen or permanent resident?", "Are you a citizen or green card holder?",
                      "Are you a citizen or lawful permanent resident of the U.S.?"):
                for ans, want in (("Yes", "OK"), ("No", "WRONG")):
                    got = _run(_RESIDENT_KB, template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + _ask(q, ans)), tdp)
                    ok = got == want
                    rows += 1
                    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                    if not ok:
                        print(f"  \u2717 TEMPLATE  [resident] {q} -> {ans}: got {got}, want {want}")
            for line, later, citizen in TEMPLATE_OPTIONS:
                for (who, kb), want in zip(people, (later, citizen)):
                    got = _run(kb, template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + line), tdp)
                    ok = got == want
                    rows += 1
                    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                    if not ok:
                        print(f"  \u2717 TEMPLATE  [{who}] {line.strip()}: got {got}, want {want}")
            # Round 9. A form-inventory line listing the options is the question not answered yet: it never
            # reads as UNVERIFIED and never makes a file CLEAN by itself. Each row: (body, verdict per person).
            inventory = "## Form questions\n\n- Are you legally authorized to work in the US? (required; options: Yes, No)\n" \
                        "- Do you require sponsorship to begin employment? [Yes/No]\n" \
                        "- Will you now or in the future require sponsorship? options: Yes, No\n"
            work_status = _ask("Will you now or in the future require employer support for your work status?", "Yes")
            r9_rows = [
                ("inventory lines only: nothing read", template.replace("## Form questions", inventory, 1),
                 "NONE", "NONE"),
                ("inventory lines beside right answers: the answers decide",
                 filled_in.replace("## Form questions", inventory, 1), "OK", "OK"),
                ("the work-status line beside a right answer is read, not silent",
                 template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + _RIGHT_LINES + "\n" + work_status),
                 "OK", "WRONG"),
                ("an off-topic question outside the section stays silent",
                 filled_in + '\n## Other questions\n\n- "Are you over 18?" \u2192 Yes\n', "OK", "OK"),
                ("a heading naming work authorization is a section too",
                 '# Acme\n\n## Work authorization answers\n\n- "Are you over 18?" \u2192 Yes\n', "?", "?"),
                ("a heading section ends at the next heading of its level",
                 '# Acme\n\n## Sponsorship\n\n' + _ask("Are you legally authorized to work in the United States?", "Yes")
                 + '\n\n## Other\n\n- "Are you over 18?" \u2192 Yes\n', "OK", "OK"),
            ]
            for label, body, later, citizen in r9_rows:
                for (who, kb), want in zip(people, (later, citizen)):
                    got = _run(kb, body, tdp)
                    ok = got == want
                    rows += 1
                    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                    print(f"  {'✓' if ok else '✗'} ROUND9    [{who}] {label}: {got}" + ("" if ok else f" (want {want})"))
            # Round 11. Shape 4: the §3 free-text answer, recorded exactly, reads OK on a question that is
            # not a yes/no class. Each row: (label, KB, the line after the template's label, verdict).
            def _with_free(kb: str, body: str) -> str:
                return kb + "\n### If the field is free text instead of yes/no\n\n" + body + "\n\n### Start date\n\nAny day.\n"
            filled_kb = _with_free(_CITIZEN_KB, _FREE_TEXT)
            describe = "Please describe your work authorization."
            r11_rows = [
                ("placeholder free-text section: the paragraph is UNVERIFIED",
                 _with_free(_CITIZEN_KB, "[Your honest one-line answer, written once here and pasted as is.]"),
                 _ask(describe, _FREE_TEXT), "?"),
                ("empty free-text section: the paragraph is UNVERIFIED", _with_free(_CITIZEN_KB, ""),
                 _ask(describe, _FREE_TEXT), "?"),
                ("no free-text section at all: the paragraph is UNVERIFIED", _CITIZEN_KB, _ask(describe, _FREE_TEXT), "?"),
                ("filled section, the exact paragraph: OK", filled_kb, _ask(describe, _FREE_TEXT), "OK"),
                ("filled section, quotes, case, spacing and period aside: OK", filled_kb,
                 _ask(describe, '"' + _FREE_TEXT.upper().replace(" ", "  ").rstrip(".") + '"'), "OK"),
                ("filled section, one word changed: UNVERIFIED", filled_kb,
                 _ask(describe, _FREE_TEXT.replace("any employer", "one employer")), "?"),
                ("filled section, one word added: UNVERIFIED", filled_kb,
                 _ask(describe, _FREE_TEXT.rstrip(".") + " today."), "?"),
                ("filled section, the paragraph on a yes/no class question: UNVERIFIED", filled_kb,
                 _ask("Are you legally authorized to work in the United States?", _FREE_TEXT), "?"),
                ("filled section, the paragraph on the future-sponsorship question: UNVERIFIED", filled_kb,
                 _ask("Will you now or in the future require sponsorship?", _FREE_TEXT), "?"),
                ("filled section, the paragraph beside right Yes/No answers: OK", filled_kb,
                 _RIGHT_LINES + "\n" + _ask(describe, _FREE_TEXT), "OK"),
                ("filled section, the paragraph beside a wrong answer: still WRONG", filled_kb,
                 _ask("Are you legally authorized to work in the United States?", "No") + "\n" + _ask(describe, _FREE_TEXT),
                 "WRONG"),
                ("a paragraph in an HTML comment is not the answer", _with_free(_CITIZEN_KB, f"<!-- {_FREE_TEXT} -->"),
                 _ask(describe, _FREE_TEXT), "?"),
            ]
            for label, kb, line, want in r11_rows:
                got = _run(kb, template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + line), tdp)
                ok = got == want
                rows += 1
                passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                print(f"  {'✓' if ok else '✗'} ROUND11   {label}: {got}" + ("" if ok else f" (want {want})"))
            # Round 11. An invisible format character inside a word hid the whole line, so a wrong answer
            # read as CLEAN. Person: authorized now Yes, future sponsorship Yes.
            shy, zw = "­", "​"
            hidden = [
                ("soft hyphens in the future question", f'- "Will you now or in the future require spon{shy}sor{shy}ship?" → No'),
                ("zero-width spaces in the future question", f'- "Will you now or in the future require spon{zw}sor{zw}ship?" → No'),
                ("soft hyphens in the authorized question", f'- "Are you legally au{shy}thor{shy}ized to work in the US?" → No'),
                ("zero-width joiner and word joiner in the question",
                 f'- "Will you now or in the fu‍ture re⁠quire sponsorship?" → No'),
                ("soft hyphen in the question and the value", f'- "Will you now or in the future require spon{shy}sorship?" → N{shy}o'),
                ("zero-width space in the question and the value",
                 f'- "Are you legally authorized to work in the US?" → N{zw}o\n- "Will you now or in the fu{zw}ture require sponsorship?" → N{zw}o'),
                ("no-break spaces and a byte-order mark",
                 '- "Will you now or in the future require ﻿sponsorship?" → No'),
            ]
            for label, line in hidden:
                body = template.replace(_TEMPLATE_LABEL, _TEMPLATE_LABEL + "\n" + line)
                got = (_verdict(line, _TEST_CFG), _run(_NEEDS_LATER_KB, body, tdp))
                ok = got == ("WRONG", "WRONG")
                rows += 1
                passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
                print(f"  {'✓' if ok else '✗'} ROUND11   {label}: {got[1]}" + ("" if ok else f" (got {got}, want WRONG twice)"))
            KB_ANSWERS.write_text(_UNCONFIGURED_KB, encoding="utf-8")
            (tdp / "application.md").write_text(template.replace("## Form questions", inventory, 1), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc_inv_blank = main([str(tdp / "application.md")])
            ok = rc_inv_blank == EXIT_NOT_CHECKED
            passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
            print(f"  {'✓' if ok else '✗'} ROUND9    inventory lines only, section 3 unfilled: exit {rc_inv_blank}")
        finally:
            KB_ANSWERS = saved_kb
    print(f"  template copy through main(): {rows} answered lines read")
    # Round 9: the shipped examples carry no one person's visa programme. The words are built from
    # pieces so this check does not find itself.
    own = Path(__file__).read_text(encoding="utf-8").lower()
    banned = ["re" + "newal", "extension " + "of your", "training " + "plan", "site " + "letter",
              "employment authorization " + "document"]
    clean_src = not [w for w in banned if w in own] and not re.search(r"\be" r"ad\b", own)
    passed, failed = (passed + 1, failed) if clean_src else (passed, failed + 1)
    print(f"  {'✓' if clean_src else '✗'} SOURCE    no example names one visa programme's paperwork")
    # Round 14: the same question in other words is looked at, so a flat wrong answer cannot pass unread;
    # a consent that happens to say "authorization" is not.
    for text, want in (('- "Work eligibility" → No', True), ('- "U.S. work eligibility" → No', True),
                       ('- "Work eligibility status" → No', True), ('- "Are you work eligible in the US?" → No', True),
                       ('- "Authorization status" → No', True), ('- "Eligibility status for employment" → No', True),
                       ('- "Do you currently have the legal right to be employed in the US?" → No', True),
                       ('- "Background check authorization" → Yes', False),
                       ('- "Authorization to contact references" → Yes', False),
                       ('- "Drug test authorization" → Yes', False),
                       ('- "Are you eligible for the employee discount?" → Yes', False),
                       ('- "Will you now or in the future need a work permit of any kind?" → No', True),
                       ('- "Will you now or in the future require us to file paperwork for you?" → No', True)):
        ok = _on_topic(text) is want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} TOPIC     {'looked at' if want else 'set aside'}: {text}")
    # Round 17: the words before "authorized" and between it and "work" are a closed list too
    for q, want in (("Are you independently authorized to work in the US?", Q_UNSURE),
                    ("Are you always authorized to work in the US?", Q_UNSURE),
                    ("Are you still authorized to work in the US?", Q_UNSURE),
                    ("Will you be authorized to work in the US?", Q_UNSURE),
                    ("Are you authorized in your own right to work in the US?", Q_UNSURE),
                    ("Are you legally authorized to work in the United States?", Q_AUTH),
                    ("Work authorization: are you authorized to work in the US?", Q_AUTH),
                    ("Q2. Are you currently authorized to work in the US?", Q_AUTH),
                    ("I am authorized to work in the United States", Q_AUTH),
                    ("I am legally authorized to work in the U.S.", Q_AUTH),
                    ("I am legally authorized to work in the U.S. for any employer", Q_UNSURE),
                    ("I am authorized to work in the United States for this employer only", Q_UNSURE)):
        got = (classify(q) or (None,))[0]
        ok = got == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} AUTH      {q} -> {got} (want {want})")
    # Round 19: a negator before the sponsor word that the inverted shapes do not take is never read with a polarity
    for q in ("Are you authorized to work in the US without the need for current or future sponsorship?",
              "Can you work in the US without the need for current or future sponsorship?",
              "Can you work here with no requirement for visa sponsorship now or in the future?",
              "Can you work here free of any sponsorship requirement now or in the future?",
              "Sponsorship: not required now or in the future", "Visa sponsorship: not needed, now or in the future",
              "Sponsorship (now or in the future): not required"):
        got = classify(q)
        ok = got is not None and (got[0] == Q_UNSURE or got[1] is True)
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} INVERT    {q} -> {got}")
    # Round 20: a shortened section label over the no-question record is no answer
    short = "# A\n\n## Exact form answers (as filled, 2026-01-02)\n\n- 🔴 Work-authorization field(s):\n  - No work-authorization question on this form.\n"
    ok = not list(_walk(short, None)) and _records_no_question(short)
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓' if ok else '✗'} NOQ       a shortened label over the no-question line reads as no answer")
    # Round 22: an unanswered line is named; a no-question record that contradicts the form-questions list is flagged
    tbd = ('## Exact form answers (as filled, 2026-01-02)\n\n- 🔴 Work-authorization field(s), worded EXACTLY as the form '
           'printed them:\n  - "Will you now or in the future require sponsorship?" → TBD\n')
    ok = len(unanswered_lines(tbd)) == 1
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓' if ok else '✗'} UNANSWERED a '→ TBD' line in the section is named")
    contra = ("## Form questions\n\n- Will you now or in the future require sponsorship? (required; options: Yes, No)\n\n"
              "## Exact form answers (as filled, 2026-01-02)\n\n- No work-authorization question on this form.\n")
    plain = "## Form questions\n\n- Desired start date\n\n## Exact form answers (as filled, 2026-01-02)\n\n- No work-authorization question on this form.\n"
    ok = len(noq_contradiction(contra)) == 1 and not noq_contradiction(plain)
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"  {'✓' if ok else '✗'} CONTRADICT a no-question record beside a listed sponsorship question is flagged")
    # Round 22: a form-questions list line with any options is no answer
    for text in ("- What is your work authorization status? (required; options: U.S. Citizen, Permanent Resident, Other)",
                 "- Do you require visa sponsorship? (required; options: No, Yes - now, Yes - in the future)"):
        ok = not list(_walk(text, None))
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} INVENTORY {text[:70]!r} reads as no answer")
    # Round 18: a chosen statement, or an answer on the next line, is looked at; an employer note is not
    for text, want in (("- Which best describes your work authorization? **I am authorized to work in the U.S. and will "
                        "not require sponsorship now or in the future**", True),
                       ("- Which describes you? **I require sponsorship**", True),
                       ("- Please select your status: **Require visa sponsorship**", True),
                       ("- **Q:** Are you legally authorized to work in the United States?\n- **A:** No", True),
                       ('- 🔴 Work-authorization field(s), worded EXACTLY as the form printed them:\n  - "Will you now or in the '
                        'future require sponsorship?"\n  - Answer: No', True),
                       ("- Sponsorship: Acme does not sponsor", False),
                       ("- Globex does not sponsor, so we answered No to the future sponsorship question", True),
                       ("- The hospital does not sponsor, and the user said No to needing it in the future", True),
                       ("- The clinic will not sponsor anyone, and No was selected for needing sponsorship later", True),
                       ("- The hospital does not sponsor visas.", False),
                       ("- Globex does not sponsor, so I told them yes, I will need it.", True),
                       ("- Globex does not sponsor, so yes, I will need sponsorship later.", True),
                       ("- Globex does not sponsor, so I told them no, I will not need it.", True),
                       ("- Do you have a valid driver license? **Yes**", False)):
        got = any(row[3] == Q_UNSURE for row in _walk(text, None))
        ok = got is want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} STATEMENT {'UNVERIFIED' if want else 'silent'}: {text[:70]!r}")
    # Round 20: a question about working plus a US place, any employer, a status, a permit, a limit or proof is on
    # the topic wherever it is written; ordinary questions about work are not
    for q, want in (("Can you work for any employer in the US?", True), ("Is your ability to work in the US time-limited?", True),
                    ("Do you hold a temporary status that limits your employers?", True),
                    ("Can you provide documents proving you may work in the US?", True),
                    ("Will you need us to support a status change?", True), ("Current employment status", False),
                    ("Are you currently employed?", False), ("Can you work weekends?", False),
                    ("Are you willing to work overtime with limited notice?", False), ("Is this a temporary position?", False),
                    ("What is your marital status?", False),
                    ("Will your permit need to be extended by an employer?", True),
                    ("Will you need an X-9 transfer later?", True), ("Will you need a visa transfer later?", True), ("Will you need to transfer locations?", False),
                    ("Do you have a valid driving permit?", False)):
        ok = _on_topic(q) is want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} TOPIC     {'looked at' if want else 'set aside'}: {q}")
    # Round 15: a to-begin question that reaches past the moment is not that question, so it is UNVERIFIED
    for q, want in (("Do you currently need sponsorship, including for an extension?", Q_UNSURE),
                    ("Do you require sponsorship to begin employment, including any extension?", Q_UNSURE),
                    ("Do you require sponsorship at the time of hire, including a transfer?", Q_UNSURE),
                    ("Do you currently require sponsorship to work here through 2030?", Q_UNSURE),
                    ("Do you currently require sponsorship to work here for the full contract term?", Q_UNSURE),
                    ("Do you require sponsorship to begin employment in the next 2 years?", Q_UNSURE),
                    ("Do you require sponsorship at the time of hire?", Q_BEGIN),
                    ("Will you require sponsorship to begin employment at Acme Health?", Q_BEGIN),
                    ("Do You Currently Require Sponsorship, Including Any Extension?", Q_UNSURE),
                    ("Do You Currently Require Sponsorship Through The End Of The Contract?", Q_UNSURE),
                    ("DO YOU CURRENTLY REQUIRE SPONSORSHIP, INCLUDING ANY EXTENSION?", Q_UNSURE),
                    ("Do You Currently Require Visa Sponsorship?", Q_BEGIN),
                    ("Will you require sponsorship to start work in the US now?", Q_BEGIN)):
        got = (classify(q) or (None,))[0]
        ok = got == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'✓' if ok else '✗'} BEGIN     {q} -> {got} (want {want})")
    # Configuration-loading itself, independent of the fixed test config above.
    load_ok = load_expected() is None or isinstance(load_expected(), dict)
    passed, failed = (passed + 1, failed) if load_ok else (passed, failed + 1)
    print(f"  {'✓' if load_ok else '✗'} CONFIG    load_expected() runs cleanly on the real repo "
          f"(configured or not; both are valid states)")
    if failed:
        print(f"\nSELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"\nSELFTEST OK: {passed}/{passed + failed}")
    return 0


EXIT_NOT_CHECKED = 3


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("-")]
    paths = [Path(a) if Path(a).is_absolute() else REPO / a for a in args] if args else targets()
    # A scaffold is never a real application, named or swept: the fixture's own sample answer is not yours.
    paths = [p for p in paths if not p.parent.name.startswith(SCAFFOLD_PREFIXES)]

    cfg = load_expected()
    if cfg is None:
        print("visa_gate.py: not checked: knowledge-base/12-application-answers.md §3 is not filled in yet.")
        print("  Fill in the ```work-authorization``` block in that file (run /setup, or see SETUP.md)")
        print("  before relying on this gate.")
        unverifiable = []
        for p in paths:
            if not p.is_file():
                continue
            body = p.read_text(encoding="utf-8", errors="replace")
            rec = recorded_answers(body) + unreadable_answers(body)
            if rec:
                try:
                    rel = str(p.resolve().relative_to(REPO))
                except ValueError:
                    rel = str(p)
                unverifiable.append((rel, len(rec)))
        if not unverifiable:
            print("  No application record carries a work-authorization answer yet.")
            print("  This is NOT a pass (exit 3): nothing was verified.")
            return EXIT_NOT_CHECKED
        print(f"\nUNVERIFIED: {len(unverifiable)} file(s) record work-authorization answers that cannot be")
        print("checked until §3 is filled in. This is not a pass:")
        # One tagged line per file, the same tag as every other per-file finding, so a hook that blocks
        # on `[UNVERIFIED]` blocks here too.
        for rel, n in unverifiable:
            print(f"  [UNVERIFIED] {rel}  ({n} recorded answer(s); §3 not filled in)")
        return 1

    findings: list[Finding] = []
    gaps: list[str] = []
    unreadable: list[tuple[str, int, str]] = []
    unknown_citizen: list[tuple[str, int, str]] = []
    unclassified: list[tuple[str, int, str]] = []
    checked = 0
    n_read = 0
    n_noq = 0
    unanswered: list[tuple[str, int, str]] = []
    contradictions: list[tuple[str, int, str]] = []
    for p in paths:
        if not p.is_file():
            continue
        checked += 1
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        n_read += len(recorded_answers(text, cfg))
        n_noq += _records_no_question(text)
        unanswered.extend((rel, n, ln) for n, ln in unanswered_lines(text))
        contradictions.extend((rel, n, ln) for n, ln in noq_contradiction(text))
        findings.extend(scan_text(rel, text, cfg))
        unreadable.extend((rel, n, ln) for n, ln in unreadable_answers(text, cfg))
        unknown_citizen.extend((rel, n, ln) for n, ln in citizenship_unknown(text, cfg))
        unclassified.extend((rel, n, ln) for n, ln in unclassified_answers(text, cfg))
        g = coverage_gap(rel, text)
        if g:
            gaps.append(g)

    if checked == 0:
        if args:
            print("visa_gate.py: not checked: none of the paths given is an application record.")
            return EXIT_NOT_CHECKED
        print("visa_gate.py: knowledge-base/12-application-answers.md §3 is filled in, and no application "
              "records exist yet.")
        print("  NOT CHECKED: no work-authorization answer was read. This is not a pass (exit 3).")
        print("  Once a dossier records its answers, this checks them.")
        return EXIT_NOT_CHECKED

    print(f"visa_gate.py: checked {checked} file(s) against knowledge-base/12-application-answers.md §3")
    print(f"  authorized-now = {cfg['expected'][Q_AUTH]} · sponsorship-to-begin = {cfg['expected'][Q_BEGIN]} "
          f"· now-or-in-the-future = {cfg['expected'][Q_FUTURE]}")
    for k, extra in cfg.get("also", {}).items():
        print(f"  also accepted on records for {k}: {', '.join(sorted(extra))} (your also-accept)")
    if cfg.get("wording"):
        print(f"  wording mappings: {len(cfg['wording'])} (a question printed that way gets its own answer)")
    print("  NOT checked: what was actually clicked in the browser. This reads the RECORD only;")
    print("               a correct record and a wrong radio button still diverge.")
    decided = [f for f in findings if f.decided]
    open_findings = [f for f in findings if not f.decided]

    if unanswered:
        print(f"\n{len(unanswered)} WORK-AUTHORIZATION LINE(S) NOT ANSWERED YET (no Yes or No recorded, so not read):")
        for rel, n, ln in unanswered:
            print(f"  {rel}:{n}  {ln.strip()[:150]}")
    if not open_findings and not gaps and not unreadable and not unknown_citizen and not unclassified and not contradictions:
        if n_read == 0:
            if n_noq:
                print(f"\nNOT CHECKED: {n_noq} of {checked} file(s) record that the form asked no work-authorization")
                print("question, so there is nothing to check there. That record is right; exit 3 means only that")
                print("no answer was read, not that anything is wrong.")
            if checked > n_noq:
                print(f"\nNOT CHECKED: no work-authorization answer was read in {checked - n_noq} file(s). This is not")
                print("a pass (exit 3): nothing was verified. Record each answer as")
                print('  - "<question exactly as printed>" → Yes   (or → No)')
                print("or, when the form asked nothing about it, the one line")
                print("  - No work-authorization question on this form.")
            return EXIT_NOT_CHECKED
        print(f"\nCLEAN: {n_read} work-authorization answer(s) read; every one matches your configured rule.")
        if decided:
            print(f"\n{len(decided)} ANSWER(S) ALREADY SUBMITTED AND RULED ON "
                  f"(shown for the record; not open work):\n")
            for f in decided:
                print(f.render())
                print()
        return 0
    if open_findings:
        print(f"\n{len(open_findings)} WRONG ANSWER(S):\n")
        for f in sorted(open_findings, key=lambda x: 0 if SEVERITY[x.kind] == "CRITICAL" else 1):
            print(f.render())
            print()
    if decided:
        print(f"{len(decided)} ALREADY SUBMITTED AND RULED ON (not open work):\n")
        for f in decided:
            print(f.render())
            print()
    if unreadable:
        print(f"{len(unreadable)} UNVERIFIED ANSWER(S): the value on this work-authorization line is not one the")
        print("gate accepts. It does not try to work out what a phrase means. Write one of these instead:")
        print('  - a bare Yes or No:  - "<question exactly as printed>" → Yes   (or → No)')
        print("  - one marked option whose text is Yes or No:  [x] Yes [ ] No")
        print("  - the exact words of a `wording:` line you recorded in the ```work-authorization``` block")
        print("If the line is a research note and not an answer, write it as a full sentence, or put it in")
        print("an HTML comment, so it no longer reads as a question or label with a value.\n")
        for rel, n, ln in unreadable:
            snippet = ln.strip()
            print(f"  [UNVERIFIED] {rel}:{n}\n      line:     {snippet[:157] + '...' if len(snippet) > 160 else snippet}\n")
    if unknown_citizen:
        print(f"{len(unknown_citizen)} UNVERIFIED CITIZENSHIP ANSWER(S): your §3 answers do not say whether you are a")
        print("citizen, so the gate cannot check these. Ask the user (never pick it yourself), then add their answer to the ```work-authorization``` block:")
        for hint in CITIZEN_WORDING_HINT:
            print(f"  {hint}")
        print()
        for rel, n, ln in unknown_citizen:
            snippet = ln.strip()
            print(f"  [UNVERIFIED] {rel}:{n}\n      line:     {snippet[:157] + '...' if len(snippet) > 160 else snippet}\n")
    if unclassified:
        print(f"{len(unclassified)} UNVERIFIED QUESTION(S): an answer is recorded on a line about work authorization,")
        print("sponsorship or citizenship that the gate cannot read with confidence (negated, about someone else,")
        print("or a phrasing it has no rule for). Never pick the answer yourself: ask the user for the honest answer")
        print("to the question exactly as the form printed it. Then add the whole question, after \"Are you\" or")
        print("\"Do you\", with the user's own answer, to the ```work-authorization``` block:")
        print("  wording: <the words the form printed> => [YES/NO] | [one-line reason]")
        print("A question that is not about the right to work (\"Are you over 18?\") but sits under a")
        print("work-authorization heading or label is listed here too: move it out of that section.\n")
        for rel, n, ln in unclassified:
            snippet = ln.strip()
            print(f"  [UNVERIFIED] {rel}:{n}\n      line:     {snippet[:157] + '...' if len(snippet) > 160 else snippet}\n")
    if contradictions:
        print(f"{len(contradictions)} UNVERIFIED RECORD(S): the answers say the form asked no work-authorization question,")
        print("but its form-questions list shows one. Record that question's answer, or correct the list:\n")
        for rel, n, ln in contradictions:
            print(f"  [UNVERIFIED] {rel}:{n}\n      line:     {ln.strip()[:157]}\n")
    if gaps:
        print(f"{len(gaps)} SUBMITTED APPLICATION(S) WITH NO RECORDED ANSWER:\n")
        for g in gaps:
            print(g)
            print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
