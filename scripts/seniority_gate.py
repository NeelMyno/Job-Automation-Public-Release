#!/usr/bin/env python3
"""
seniority_gate.py -- the years-of-experience gate.

THE ROOT CAUSE THIS CLOSES
Seniority exclusion tends to start as a one-time MANUAL human review: someone sweeps the open
applications and hand-flags the ones asking for more years than they actually have. A manual
review is a snapshot. It cannot catch a JD that gets built AFTER it runs, and nothing else in a
typical pipeline checks a JD's stated years requirement against the candidate's own years. So a
role requiring, say, 10+ years for someone with 3 gets tailored, reviewed, and handed over exactly
like any other role, because nothing mechanical ever compared the two numbers. A rule that lives
only as a one-time human pass, not a gate that runs on every dossier forever, rots the moment new
work is built past it. This script makes the comparison mechanical.

THE RULE
If an UNSUBMITTED job's JD requires materially more years of experience than you actually have, it
gets flagged, never silently filled and handed over. A DROP holds the job for your yes: /wave shows you
the requirement and your years and marks it passed only when you say skip it, because a posting can welcome
people below its bar in words no gate knows. A DROP is still rare, and it does not interpret English. Every count of years in a sentence lands one way:

  DROP   : the sentence, as a whole, is one plain unconditional shape, and the count is above your years:
             [lead-in] N, N+ or N to M years of [up to six words] experience [required | minimum | in X | as a X]
           A range ("6-8 years", "8 to 10 years") is read on its floor N, so it DROPs when N is above your years.
           The lead-ins are Requires, Required:, Must have, You have, You bring, We require, We need, We are
           looking for someone with, each optionally followed by Minimum of or At least, and those two
           alone. Spelled numbers count, and "N+ years experience" with no "of". With no lead-in and no
           closing "required" or "minimum", the line must sit under a requirements heading. The sentence
           is not the shape if it holds an alternative, a condition, a hedge, a degree or credential word,
           a label before the count, or a neighbouring line offering an alternative or an equivalent, or
           inviting people short of the bar: a line naming the shortfall ("less experience", "don't meet every
           requirement") and inviting them ("apply anyway", "encouraged to apply", "still want to hear from
           you"). "We encourage you to apply even if ..." waives only when its "if" names that shortfall.
           Requirements end at any heading that is not a requirements heading, including a bullet with no
           number that ends in ":", is wholly bold, or is a known preferred label ("- Good to have:",
           "* Ways to stand out"); "- Must have:" keeps them.
  REVIEW : every other count of years or decades tied to work: experience, work, employment, work history,
           track record, career, "N years in X", "N years of service" asked of you ("Must have 8 years of
           service as a firefighter"), label forms such as "Nursing: 8 years (Required)" and the same label
           in a two-cell table row ("| Years of experience | 8 |"), degree
           paths, "or equivalent", exclusions ("less than 8 years ... will not be considered"). It shows
           the lowest number offered and is raised when any number on the line is above your years. Also
           a floor equal to your years with a range ceiling well above it, and a Staff, Principal, Lead,
           Head, Director or Architect title with no years bar above yours. A title alone never DROPs.
           Surfaced to you, never auto-acted: not a pass and not a drop, and it does not change the exit code.
  Nothing: only the short list of things that are not experience: a person's age ("years old", "of age",
           "18 years or older", "Must be over 18 years."), schooling length, records
           and lookbacks (driving record, MVR, background or criminal check, residency, credit), pay, a
           contract or lease term, a warranty, retention or tenure promised by the employer (a benefit after
           N years of employment or service: "Pension after 10 years of service"), company history (also
           under a requirements heading: "Serving the community for 25 years", "Acme has been a trusted name
           for 20+ years", "We have been in business for 30 years", with no "you" or candidate in the line),
           other parties (vendors, subcontractors, suppliers, clients, patients, students, and a manager,
           mentor, lead, supervisor, team or coworker you report to or work with), and a plain
           statement that the years are not needed. A real work phrase beats a list word: "8+ years of
           contract management experience" and "Contract drafting: 8 years (Required)" are work.
  PASS   : nothing above your years, and not a senior-plus title.

THE BACKSTOP (runs after every other decision, before a count may be silent)
A count is looked at in its OWN clause: from the count to the next ";", sentence end, pay or label phrase after a
comma, or the next count (so "18 years of age with 8 years ..." and "of age and have 5 years" are two clauses). If a
work anchor follows the count there (experience, expertise, background in/as, a "-ing" word with an object such as
"serving customers" or "driving trucks", "as a/an <noun>", "in the <field> field", "in <field> roles"), the count is
silent only for a reason about that same count: plain negation of it, a clear other party owning it (the closed
subject list, the company, a named person or firm), or a pay, benefit or tenure phrase whose quantity it is ("a
raise after 5 years of service"). Any other silence reason on the line (an age, a record, a contract, schooling, a
list word) belongs to a different count and never silences this one: it is a REVIEW, or a DROP when the plain shape
fits. A singular "year" describing a noun ("a 2 year teaching commitment") is a term, so there only the word
experience is an anchor.

Only the ROLE'S REQUIREMENT counts, and every line of a jd-*.md file is the posting's: no line is skipped
as "your own note" before it is read, and no heading (an "About ..." section included) hides a line. A
line naming years tied to work is always read; only the closed list above silences it.

CONFIGURATION (optional -- see scripts/config.py)
Set `YOUR_YEARS_OF_EXPERIENCE = <a number>` in scripts/config.py to enable this gate for your own
setup. Left unset (the default), the gate checks NOTHING and says so: it prints "not checked: set
YOUR_YEARS_OF_EXPERIENCE" and exits 3, never 0, so an unset gate can never be read as "0
unhandled". It never crashes and never guesses a number.

USAGE
  seniority_gate.py --selftest                 # must stay green (built from real defect shapes)
  seniority_gate.py <dossier_dir>              # one dossier, verbose evidence
  seniority_gate.py --all                      # every applications/* dossier (a table)
  seniority_gate.py --all --unsubmitted        # only not-yet-applied dossiers (the action list)
  seniority_gate.py --all --unsubmitted --drops-only   # just the DROP folder paths, one per line

EXIT: 0 = checked, no UNSUBMITTED drop found. 1 = at least one unsubmitted DROP (the thing to fix).
2 = usage error. 3 = NOT CHECKED: YOUR_YEARS_OF_EXPERIENCE is unset, scripts/config.py has an error in it,
the one dossier asked for has no jd-*.md, or (--all) an unsubmitted dossier has no jd-*.md and none DROPs (a warning,
never a pass). An unhandled DROP's exit 1 outranks 3; a REVIEW never sets the exit code.
"""
from __future__ import annotations
import re
import sys
import unicodedata
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parent.parent
APPS = REPO / "applications"
TRACKER = REPO / "pipeline" / "tracker.html"

# scripts/config.py is optional (see that file's own docstring); this gate stays a safe no-op if
# it has never been created, or if it exists but has never had YOUR_YEARS_OF_EXPERIENCE added to
# it -- hence getattr with a None default rather than a bare attribute access either way. A config.py
# with a mistake in it is the user's to fix, so it gets one plain line, never a traceback.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _config_problem(e: Exception) -> str:
    """Which line of scripts/config.py is wrong, in plain words."""
    line, msg = getattr(e, "lineno", None), getattr(e, "msg", None) or f"{type(e).__name__}: {e}"
    tb = e.__traceback__
    while tb is not None:
        if Path(tb.tb_frame.f_code.co_filename).name == "config.py":
            line = tb.tb_lineno
        tb = tb.tb_next
    return f"scripts/config.py{f' line {line}' if line else ''}: {msg}"


CONFIG_ERROR = None
try:
    import config
except Exception as _e:  # noqa: BLE001, the file is the user's and can raise anything
    if not (isinstance(_e, ModuleNotFoundError) and _e.name == "config"):
        CONFIG_ERROR = _config_problem(_e)

    class config:  # type: ignore[no-redef]
        """Fallback when scripts/config.py is missing or cannot be loaded: safe defaults only."""
        YOUR_YEARS_OF_EXPERIENCE = None

YEARS_OF_EXPERIENCE = getattr(config, "YOUR_YEARS_OF_EXPERIENCE", None)
# DROP_FLOOR is the first year-count that counts as "materially more than you have". None means
# "not configured yet" -- every function below degrades gracefully rather than guessing a number
# that would be true for nobody in particular.
DROP_FLOOR: int | None = (YEARS_OF_EXPERIENCE + 1) if isinstance(YEARS_OF_EXPERIENCE, (int, float)) else None
# How far above your own years a range's CEILING has to reach before a "floor matches you exactly"
# line is worth a human REVIEW rather than an automatic PASS (a JD stating "5-8 years" when you
# have 5 is a different animal from one stating "5-6 years").
CEILING_SPREAD_FOR_REVIEW = 3

# Senior-plus titles. A word on this list only counts where it names a senior rung: plenty of fields
# use the same word for an ordinary job. "Staff" and "Lead" are senior rungs only on a technical
# ladder (Staff Nurse, Staff Accountant, Lead Teacher, Lead Cashier and Lead Line Cook are the ordinary
# titles in those fields). "Architect" is senior only as a technology role, since an Architect or
# Landscape Architect in building design is the profession itself. "Principal", "Head of" and
# "Director" are senior by default (Director of Nursing, School Principal), minus the listed titles
# that are ordinary jobs. A title that lands here is a REVIEW for a person, never a drop.
_LADDER_ROLE = (r"(?:engineer|scientist|designer|developer|researcher|swe|sre"
                r"|engineering manager|product manager|program manager)")
_GAP = r"(?:[\w+/&.-]+\s+){0,3}?"
_STAFF_LADDER = re.compile(rf"\bstaff\s+{_GAP}{_LADDER_ROLE}\b")
_LEAD_LADDER = re.compile(
    rf"\blead\s+(?!gen(?:eration)?\b){_GAP}(?:{_LADDER_ROLE}|data analyst)\b"
    r"|\b(?:engineer|engineering|designer|design|developer|scientist|product|data|software|tech|technical"
    r"|platform|research|qa|ml|ai|devops|infrastructure|frontend|backend|ux|ui)\b[\s,/()-]*(?:team\s+)?lead\b"
    r"|\bteam\s+lead\b.*\b(?:engineer\w*|software|design\w*|developer|data|product|platform|research\w*"
    r"|tech|technical|technology)\b")
# The same role words in a trade or craft ("Stationary Engineer", "Interior Designer") are not that ladder.
_TRADE_ROLE = re.compile(
    r"\b(?:maintenance|stationary|sanitation|facilit(?:y|ies)|building|boiler|operating|locomotive|custodial|hvac"
    r"|refrigeration|field\s+service)\s+engineer(?:ing)?\b"
    r"|\b(?:interior|fashion|floral|kitchen|landscape|costume|hair|nail)\s+design(?:er|ers)?\b")
_SENIOR_WORD = re.compile(
    r"\bprincipal\b|\bhead of\b|\bdirector\b"
    r"|\b(?:software|solutions?|enterprise|cloud|systems?|data|security|technical|infrastructure|platform"
    r"|network|application|integration|ai|ml)\s+architect\b")
_ORDINARY_TITLE = re.compile(
    r"\b(?:assistant|vice|deputy)\s+principal\b"
    r"|\bprincipal\s+(?:clerk|cashier|secretary|dancer|singer|player|musician|cellist|violinist|flutist|oboist)\b"
    r"|\bhead of (?:year|department|house|housekeeping)\b"
    r"|\b(?:funeral|activity|activities|art|music|choir|band|camp|casting|cruise|assistant)\s+director\b"
    r"|\bdirector of (?:photography|activities|music)\b")

# EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (verify_claims.py's own fixture, and the blank
# starter copy-from), never a real application. A years-of-experience sweep must skip these or it
# reports noise on a fresh clone for work nobody ever intended to submit.
SCAFFOLD_DOSSIER_PREFIXES = ("EXAMPLE-", "TEMPLATE-")


def is_scaffold_dossier(folder_name: str) -> bool:
    return folder_name.startswith(SCAFFOLD_DOSSIER_PREFIXES)


# A count of years is read here, one sentence at a time, by _read_sentence(): _is_plain_requirement() is
# the only road to a DROP, and _is_work() decides whether any other count is a REVIEW or nothing at all.
PREFERRED = ("preferred", "nice to have", "nice-to-have", "bonus", "a plus", "ideally", "would be great", "not required",
             "desired", "desirable", "helpful", "an asset", "advantageous")

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
             "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30}
_W = "(?:" + "|".join(NUM_WORDS) + ")"

# 'years','year','yrs','yr' are the SAME requirement.
YR = r"(?:years?|yrs?)"
# A scraped range ("5-8 years") sometimes carries an en dash or em dash. Built via chr() rather than
# typed literally, so no such character sits in this file's own source.
_EN_DASH = chr(0x2013)
_EM_DASH = chr(0x2014)
_RANGE_SEP = r"(?:-|" + _EN_DASH + r"|" + _EM_DASH + r"|to)"
_N = r"(\d{1,2}(?:\.\d+)?|\b" + _W + r"\b)"
# Every mention: "7 years", "8+ yrs.", "5-8+ years", "four to seven years", "six or more years",
# "Ten-plus years", "10 years'", "7-year".
_MENTION = re.compile(
    r"(?<![\d.,$/])(?:~\s*)?" + _N + r"(?:\s*" + _RANGE_SEP + r"\s*~?\s*" + _N + r")?"
    r"(\s*\+|\s*or\s+more|\s*or\s+greater|\s*-?\s*plus)?\s*-?\s*(years?|yrs?)\b\.?(\+|\s+or\s+more\b)?(?:['’]s\b|['’])?")
# "60 months of experience". Read only when the word experience follows, so a 36 month warranty is nothing.
_MONTHS = re.compile(
    r"(?<![\d.,$/])(\d{1,3}|\b" + _W + r"\b)(?:\s*" + _RANGE_SEP + r"\s*(\d{1,3}|\b" + _W + r"\b))?"
    r"(\s*\+|\s*or\s+more)?\s*-?\s*(?:months?|mos)\b\.?")
_DECADE = re.compile(
    r"\b(nearly |almost |roughly |about |around |over |more than |at least )?"
    r"(?:((?:a\s+)?half[- ](?:a\s+)?)|(a|one|two|three|\d)\s+)decades?\b(?:\s+or\s+more\b)?")
_FLOOR_WORD = re.compile(r"(?:at least|minimum(?:\s+of)?|min\.?|no less than|not less than|no fewer than|not fewer than)\s*$")
# Quantity words that can sit between a verb and the number.
_Q = (r"(?:(?:over|more\s+than|nearly|almost|about|around|roughly|approximately|an?\s+average\s+of|average\s+of"
      r"|a\s+combined|combined|at\s+least|a\s+minimum\s+of)\s+)*")

# Ages: "3-5 year olds", "ages 6 to 12 years", "aged 6-12 years", "at least 18 years old".
# "18 years of age" ends there or hands off ("or older", "and up", "by start date"); "8 years of age-appropriate
# teaching" and "of age appropriate lesson planning" are work
_AGE_AFTER = re.compile(r"\s*-?\s*olds?\b|\s+of\s+age(?=\s*$|\s*[,.;:)!|]|\s+(?:or|and|with|minimum|required|by|at|as|on|before"
                        r"|to|upon|prior|plus|\+)\b)")
# "18 years or older", "21 years or over": an age only with no work word in the sentence ("Experience: 8 years
# or above" is a bar), and "or over/above" only with an age cue too: "be" before the count, or a count of 16+.
_AGE_OR_OVER = re.compile(r"\s+or\s+(older|over|above)\b")
_AGE_WORK_CUE = re.compile(r"\b(?:experience[ds]?|work(?:s|ed|ing)?|employ\w*|careers?|service|roles?|positions?|jobs?"
                           r"|tenure)\b")
_AGE_TASK_CUE = re.compile(r"\b(?:teach|coach|instruct|tutor|caring|care\s*giv|nurs|supervis|counsel|mentor|lead|manag)\w*")
_AGE_WORK_TAIL = re.compile(r"\s+or\s+(?:over|above)\s+(?:in|as\s+an?)\s+\w")
# "Must be over 18 years." A person "is" an age; nobody "is" a count of experience. Only with nothing after
# the count, so "Must be 8 years into a nursing career" is still read, and only with no work word in the
# sentence ("Nursing experience must be at least 8 years" is a bar).
_BE_AGE_BEFORE = re.compile(r"\b(?:be|is|are)\s+(?:at\s+least\s+|over\s+|older\s+than\s+|aged?\s+)?$")


def _is_age(before: str, tail: str, low) -> bool:
    """Is this count a person's age? A real work word in the count's own sentence always beats an age reading."""
    if _AGE_AFTER.match(tail):
        return True
    sentence = re.split(r"[.;!?]\s", before)[-1] + " " + re.split(r"[.;!?](?:\s|$)", tail)[0]
    if _AGE_BEFORE.search(before):
        # "children ages 6 to 12 years" is an age; "Teaching children ages 3-5: 6 years" is a work count
        return not (_AGE_WORK_CUE.search(sentence) or _AGE_TASK_CUE.search(sentence))
    if _AGE_WORK_CUE.search(sentence):
        return False
    be = bool(_BE_AGE_BEFORE.search(before))
    over = _AGE_OR_OVER.match(tail)
    if over:
        if over.group(1) == "older":
            return True
        return be or (not _AGE_WORK_TAIL.match(tail) and isinstance(low, (int, float)) and low >= 16)
    return be and bool(_NOTHING_AFTER.match(tail))
_NOTHING_AFTER = re.compile(r"[\s.!;,)]*$")
# "ages 6 to 12 years" is an age; "18 years of age with 8 years" and "of age and have 5 years" hand the second
# count to a new phrase, so a "with", "and", "have" or "plus" between "age" and the count ends the age reading.
_AGE_BEFORE = re.compile(r"\bage[sd]?\b(?:(?!\b(?:with|and|have|has|plus|having)\b)[^.;,]){0,20}$"
                         r"|\b(?:children|kids|toddlers|infants|students|learners|pupils|campers)\s+(?:from\s+|between\s+)?$")
# Words just before the number that make it a span of time rather than a bar.
_NOT_A_BAR_BEFORE = re.compile(
    r"\b(?:next|last|past|first|coming|after|within|during|throughout|every|each|per|in|by|until|the|our|its"
    r"|their|these|those|this)\s+$")
_FOR_SPAN = re.compile(r"\bfor\s+(?:over\s+|more\s+than\s+)?$")
_FOR_SPAN_ANY = re.compile(r"\bfor\s+" + _Q + r"$")
# Pay lines: "Teachers with 10 years of experience earn $70,000", "Pay: $25/hr with 3 years experience".
_PAY_AFTER = re.compile(r"\b(?:earn|earns|earning|make|makes|are paid|is paid|get paid|receive|receives|start at"
                        r"|starts at|qualify for|qualifies for|eligible for)\b[^.;]*(?:\$|\bsalary\b|\bpay\b|\bbonus\b|\brate\b|\bstep\b|\d)")
_PAY_BEFORE = re.compile(r"(?:\b(?:pay|salary|wage|rate|stipend|bonus|compensation|earn|earns)\b|\$\s*\d)[^.;]*"
                         r"\b(?:with|after|at|for)\s+" + _Q + r"$")
# Things kept for a length of time: records, documents, warranties, contracts.
_RETAINED = re.compile(
    # "stored" only: the noun "store" ("Store manager with 8 years") is a workplace, not records kept.
    r"\b(?:retain\w*|kept|keep\w*|stored|archiv\w*|preserv\w*)\b[^.;,]{0,40}$"
    r"|\b(?:records?|documents?|files|logs?|receipts?)\b[^.;,]{0,40}\b(?:for|of)\s+" + _Q + r"$"
    r"|\b(?:warrant\w*|guarantee\w*|contract|lease|term|commitment|agreement)\b\s+(?:[\w-]+\s+){0,2}?"
    r"(?:of|for|is|lasts|runs|period|length|covers)\b[^.;,]{0,30}$")
# Someone holding a status for a time. A person should read these.
_HOLD_FOR = re.compile(r"\b(?:held|holding|licensed|certified|employed|worked|working|served|serving|registered"
                       r"|practic\w+)\b[^.;]{0,40}\bfor\s+" + _Q + r"$")
# The applicant doing a job for a time, with the applicant as the subject: the sentence opens on the verb,
# on "Has", or on "Must (have)" ("Worked for 8 years in retail", "Must have taught high school for 8 years",
# "Must hold a license for 8 years"). A company sentence ("Acme has operated here for 8 years") opens on
# its own name, so it never fits.
_APPLICANT_HOLD = re.compile(
    r"^[\s\-*>#•_]*(?:(?:you|candidates?|applicants?)\s+)?(?:(?:must|should|shall|will\s+need\s+to|need\s+to)\s+)?"
    r"(?:(?:have|has)\s+)?(?:\w+ed|taught|held|hold|holds|led|run|ran|been|done|spent|kept|driven|drove|built|sold"
    r"|worked|work|managed|supervised|served)\b[^.;]{0,50}\bfor\s+" + _Q + r"$")
# A sentence that asks something of the applicant from its first words. Under one of these, or under a
# requirements heading, a count of years tied to nothing on the short list is at least a REVIEW.
_APPLICANT_LEAD = re.compile(
    r"^[\s\-*>#•_]*(?:requires?\b|required\b|must\b|minimum\b|at\s+least\b"
    r"|you\s+(?:have|bring|must|need|should|will\s+need)\b|we\s+(?:require|need)\b|we(?:\s+are|['’]re)\s+(?:looking|seeking)\b"
    r"|(?:candidates?|applicants?)\s+(?:must|should|need|will|shall)\b|(?:seeking|looking\s+for|hiring)\b)")
_MUST_BEFORE = re.compile(r"\b(?:must\s+have|requires?|required|needs?)\s+$")
# A count of something other than experience, where the first word alone cannot tell: "5 years
# program management" and "6 years high school teaching" are work, "a program" and "high school math"
# are not.
_WORK_WORD = r"(?:teach|coach|counsel|instruct|admin|advis|recruit|nurs|athletic|professor|faculty|lectur)"
_NOT_EXPERIENCE_TAIL = re.compile(
    r"\s+(?:of\s+)?(?:"
    # "history" is a record only after a record word ("7 years of address history", "credit history"); "a 5-year
    # history of progressive responsibility in accounting" and "5 years of sales history" are the applicant's work
    r"(?:[\w/&-]+\s+){0,2}commitment\b"
    r"|(?:[\w/&-]+\s+)?(?:credit|address|residen\w*|driving|criminal|rental|payment|medical|salary|tax"
    r"|immunization|vaccination|claims?)\s+history\b(?=\s*(?:$|[,.;:)!?]|(?:check|checks|verification|report|reports|record|records|required|preferred|lookback|on\s+file)\b))"
    r"|program(?:me)?s?\b(?!\s+(?:manag|coordinat|direct|develop|lead|administ|evaluat|analy|plann|specialist|experience))"
    r"|criminal\b|credit\b(?!\s+(?:analy|risk|underwrit|union|manag|experience"
    r"|history\s+(?!(?:check|checks|verification|review|report|reports|required|on\s+file)\b)[a-z]))"
    # "4 years of job security" is a promise to the hire, not a bar; "8 years of security experience" is read.
    r"|(?:job|employment|income)\s+(?:security|stability)\b"
    r")")
_EDU_PREFIX = (r"\s*(?:of\s+|in\s+)?(?:(?:post-?secondary|undergraduate|graduate|accredited|full[- ]time|community"
               r"|technical|trade|vocational|medical|nursing|law|dental|formal|some)\s+)*")
_EDUCATION = re.compile(
    _EDU_PREFIX + r"(?:(?:college|university|high\s+school|school|schooling|coursework|courses?|credits|credit\s+hours?|tuition"
    r"|diploma|degrees?|bachelor\w*|apprenticeships?|residency)\b(?!\s+(?:[\w-]+\s+)?" + _WORK_WORD + r")"
    # it heads its phrase: "4 years of college", "college coursework", "high school math". As a modifier it names a
    # line of work ("8 years of college teaching", "school bus driving", "university admissions", "college-level")
    r"(?=\s*(?:$|[,.;:)(/*_]|(?:or|and|in|at|from|with|required|preferred|minimum|completed|level\b(?!\s*[a-z])|degree"
    r"|education|coursework|credits?|hours?|study|studies|is|are|will|may|can|plus|courses?|classes"
    r"|math\w*|science|english|history|chemistry|biology|physics|spanish|french|algebra|languages?|equivalent)\b))"
    r"|(?:education|training|study|studies)\b(?!\s+(?:[\w-]+\s+)?(?:experience|" + _WORK_WORD + r")))")
# "5 years in education" names the field a teacher works in. Only "of education" or a degree word is schooling.
_IN_EDUCATION_FIELD = re.compile(r"\s*in\s+(?:[\w-]+\s+){0,2}?education\b")
_TRACK_RECORD = re.compile(r"\s*(?:of\s+)?(?:[\w-]+\s+)?track\s+record\b")
_TRACK_RECORD_BEFORE = re.compile(r"\btrack\s+record\s+of\s+" + _Q + r"$")
_OWN_TRACK_RECORD = re.compile(r"\b(?:our|its|their)\b[^,.;]*\btrack\s+record\b")
_EXPERIENCE_SOON = re.compile(r"\s+(?:of\s+)?(?:[\w/&-]+\s+){0,3}experience\b")
_PREPOSITION = frozenset("of in on at as with".split())
# "with the", "in a", "of the": skipped to reach the first real word after the number.
_FIRST_WORD = re.compile(r"\s*(?:(?:of|in|on|at|as|with)\s+)?(?:(?:an?|the)\s+)?([a-z][\w/&-]*)")
# What can follow "N years" without naming a line of work, even when the line asks for it.
_NOT_WORK = frozenset("""
    ago old olds age later from before after to until since per straight running total row making
    business operation operations existence future market service growth runway focus
    innovation excellence trust trusted success vesting warranty contract term commitment lease
    guarantee guaranteed free paid tuition college school university education schooling study studies
    data records record mvr retention support coverage hire hiring graduation start us we company
    degree degrees diploma bachelor coursework apprenticeship apprenticeships residency address clean
""".split())
# The words on that list that map to a closed-list reason. Under a requirements heading on a line with a work word
# only these still silence ("8+ years of success in retail management" is read): age, contract term, schooling,
# records, benefit tenure, and the company's own history or the company itself.
_NOT_WORK_CLOSED = frozenset("""
    ago old olds age warranty contract term commitment lease guarantee guaranteed tuition college school university
    education schooling study studies degree degrees diploma bachelor coursework apprenticeship apprenticeships
    residency graduation data records record mvr clean address vesting retention business operation operations
    existence trusted trust us we company
""".split())
# No word that names work a person does (serving, teaching, driving, nursing, selling, cooking, managing, caring,
# making, running, hiring) sits on either list as a silence word on its own: "10 years serving customers" is work.
# "making", "running" and "hiring" stay only as standalone phrases ("20 years in the making", "3 years running").
# Words on that list that also open the name of a line of work: "8+ years data engineering", "8+ years
# business development", "8+ years records management". Each silences the count only when it stands alone.
_FIELD_NOUN = frozenset("""
    data business operation operations market service records record school support hiring contract growth
    running making college university schooling residency age
""".split())
_NEXT_WORD = re.compile(r"\s+([a-z][\w/&-]*)")


def _standalone_field(tail: str, word_match) -> bool:
    """Is this list word the whole phrase ("8 years of service") rather than the start of a job ("8 years
    of service desk support")? Only a following word that is itself neither small nor on the list makes a job."""
    if word_match.group(1) not in _FIELD_NOUN:
        return True
    nxt = _NEXT_WORD.match(tail, word_match.end())
    return not nxt or nxt.group(1) in _FUNCTION_WORD or nxt.group(1) in _NOT_WORK


# Small words that name no work by themselves ("8+ years and a CDL").
_FUNCTION_WORD = frozenset("""
    and or with at as is are was were you they it this that the but so if when while then a an into
    over under now by for
""".split())
_ANCHOR_WORDS = ("experience", "expertise", "background")
# Words that end the phrase between the number and "experience": past one of these, the experience
# word belongs to something else ("a 4 year accounting degree and experience with...").
_GAP_STOP = frozenset("""degree diploma license licence certificate certification commitment""".split())


def _anchored(tail: str) -> bool:
    """Is this count of years followed by the word experience, expertise or background, in the same clause?"""
    clause = re.split(r"[.;:()]", tail, maxsplit=1)[0]
    words = [w.strip(",'\"\u2019*_") for w in clause.split()]
    for i, w in enumerate(words[:11]):
        if w in _ANCHOR_WORDS:
            if w == "background" and words[i + 1:i + 2] and words[i + 1] in ("check", "checks", "screen", "screening", "investigation"):
                return False
            return not any(g in _GAP_STOP or any(c.isdigit() for c in g) for g in words[:i])
    return False


def _adjective_use(tail: str, unit: str, low: int) -> bool:
    """"a 4 year degree", "a clean 5 year record", "10 year anniversary": "year" in the singular
    describing a following noun. A preposition after it means an ordinary count ("5 year in sales")."""
    if unit not in ("year", "yr") or low < 2 or _EXPERIENCE_SOON.match(tail):
        return False
    m = re.match(r"\s*-?\s*([a-z][\w/&-]*)", tail)
    # "8 year minimum in nursing" names the bar itself, not a thing that lasts 8 years.
    return bool(m) and m.group(1) not in _PREPOSITION and m.group(1) not in _BAR_NOUN


_BAR_NOUN = frozenset("minimum min requirement required experience exp".split())


# Label lines. "Experience: 7 years", "Nursing: 7 years (Required)", "Years of Experience: 7".
_BULLET = r"^[\s\-*>#•_]*"
_EXPERIENCE_LABEL = re.compile(
    _BULLET + r"(?:[a-z]+\s+){0,3}?(?:years?\s+of\s+)?experience(?:\s+(?:required|needed|level))?[*_\s]*[:=][*_\s]*$")
_YEARS_LABEL = re.compile(
    _BULLET + r"(?:(?:minimum|min\.?|required)\s+)?(?:years?|yrs?)\.?\s+(?:of\s+)?(?:[\w-]+\s+){0,2}?experience"
    r"(?:\s+(?:required|needed))?[*_\s]*[:=][*_\s]*~?" + _N + r"(?:\s*" + _RANGE_SEP + r"\s*~?" + _N + r")?")
# A bare number under an experience or years label: "Experience Required: 8+", "Years required: 8",
# "Yrs exp: 8+". The number has to end the line, so "Experience: 2 references" is nothing. "level" is left
# out: "Experience level: 3" is a grade.
_BARE_LABEL = re.compile(
    _BULLET + r"(?:(?:minimum|min\.?|required|total|relevant)\s+)?"
    r"(?:(?:years?|yrs?)\.?(?:\s+of)?(?:\s+(?:experience|exp)\b\.?)?|(?:experience|exp)\b\.?)"
    r"(?:\s+(?:required|needed|minimum|min\.?))?[*_\s]*[:=][*_\s]*~?" + _N
    + r"(?:\s*" + _RANGE_SEP + r"\s*~?" + _N + r")?\s*\+?[*_\s.]*$")
# "Nurse (8 years)": a job title with the count beside it in brackets.
_TITLE_PAREN = re.compile(_BULLET + r"([a-z][\w /&,.'-]{0,40}?)\s*\(\s*(?:at\s+least\s+|min(?:imum)?\.?\s+)?$")
_FIELD_LABEL = re.compile(r"(?:" + _BULLET + r"|:[*_\s]*)([a-z][\w /&,.'-]{0,40}?)\s*(?::|\s-\s)[*_\s]*$")
# "Experience of 8 years", "Minimum experience 7 years". Someone's own experience is not a reading.
_EXPERIENCE_OF = re.compile(
    r"(?<!\bour )(?<!\bits )(?<!\btheir )(?<!\bhis )(?<!\bher )\bexperience\s*(?:\(|(?:of|is|=)\s)\s*" + _Q + r"$"
    r"|\b(?:minimum|min\.?|required)\s+(?:[\w-]+\s+)?(?:experience|exp\b\.?)\s*[:=-]?\s*" + _Q + r"$")
_REQUIRED_MARK = re.compile(r"\s*\(\s*(?:required|preferred|req'?d|minimum)\s*\)")


# An explicit statement about the person being hired.
_CANDIDATE_SUBJECT = (r"(?:you|candidates?|applicants?"
                      r"|(?:ideal|successful|right|qualified)\s+(?:[\w-]+\s+)?(?:person|hire|candidate|applicant|individual))")
_CANDIDATE_STATEMENT = re.compile(
    r"\b" + _CANDIDATE_SUBJECT + r"\b(?:\s+(?:must|should|shall|will|need\s+to|needs\s+to|(?:are|is)\s+required\s+to"
    r"|(?:are|is)\s+expected\s+to))?(?:\s+(?:also|already|ideally))?\s+(?:have|has|bring|brings|possess|possesses|need|needs"
    r"|require|requires|hold|holds|demonstrate|demonstrates|offer|offers)\b(?:\s+[\w'-]+){0,7}?\s*$")
_SEEKING_WITH = re.compile(r"\b(?:seeking|hiring|looking\s+for|need|needs|want|wants)\s+(?:an?\s+|someone\b|people\b|candidates?\b)"
                           r"[^.;]{0,50}?\bwith\s+" + _Q + r"$")
# Cue that the sentence asks something of the candidate. A bare "we", "our" or "us" is not one.
_CANDIDATE_CUE = re.compile(
    r"\byou\b|\byour\b|\byou'll\b|\byou've\b|\bcandidate|\bapplicant|\brequire|\bmust\b"
    r"|\bminimum\b|\bat least\b|\bpreferred\b|\bor more\b|\bqualif|\bideal\b|\bneed"
    r"|\bshould\b|\blooking for\b|\bseeking\b|\bsomeone\b|\bhire\b|\bhiring\b")
_PERSON_CUE = re.compile(r"\byou\b|\byour\b|\bcandidate|\bapplicant|\brequire|\bmust\b|\bminimum\b|\bat least\b")

# Somebody else's years: "The partner has 20 years", "Our nurses have an average of 15 years",
# "Globex has 40 years". The verb's subject decides; "You must have", "A nurse who has" and a bullet
# opening with "Has" stay with the candidate.
_HAS_BEFORE = re.compile(r"\b(?:has|have|brings?|averages?|averaging|boasts?|holds?|carr(?:y|ies))\s+"
                         r"(?:an?\s+(?:[\w-]+\s+){0,2}?track\s+record\s+of\s+)?" + _Q + r"$")
_SUBJECT_IS_CANDIDATE = re.compile(
    r"(?:\byou|\bcandidates?|\bapplicants?|\bhires?|\bhirees?|\bsomeone|\bperson|\bpeople|\bwho|\bmust|\bshould"
    r"|\bshall|\bwill)(?:\s+(?:also|already|ideally))?\s*$")
_SUBJECT_IS_COMPANY = re.compile(r"\b(?:we|our|is|are|was|were)\b")


# The applicant under another name: "You'll", "You'd", "The ideal teammate", "Our next store manager",
# "Successful candidates typically". A subject like these is never somebody else.
_APPLICANT_SUBJECT = re.compile(
    r"(?:^|[\s(])(?:you(?:['’](?:ll|d|re))?(?:\s+(?:will|would))?"
    r"|(?:(?:the|an?|our|your)\s+)?(?:ideal|successful|qualified|strong|right|perfect|best|top|future)\s+(?:[\w-]+\s+){0,2}?[\w-]+"
    r"|(?:the|our|your)\s+(?:next|new)\s+(?:[\w-]+\s+){0,2}?[\w-]+)"
    r"(?:\s+(?:typically|usually|often|generally|normally|ideally|also|already|will|would|should))*$")
# Under a requirements heading only a clear other party keeps its own years: the company, "we" or "our" and a
# staff noun, a manager, mentor, lead, supervisor, team, coworker or partner, or a named third person or firm
# (one to three words with no article: "Globex", "Sam Lee").
_OTHER_PARTY = re.compile(
    r"(?:^|[\s(])(?:we|our\s+(?!next\b|new\b|future\b|ideal\b)(?:[\w-]+\s+){0,2}?[\w-]+"
    r"|(?:(?:the|this|our|your|a|an)\s+)?(?:[\w-]+\s+)?(?:company|firm|organi[sz]ation|business|agency|practice|hospital"
    r"|clinic|school|district|brand|group|partners?|founders?|owners?|leadership)"
    # a manager, mentor, lead, supervisor, team or coworker only as yours, or one you report to or work with:
    # "Store Manager has 8 years" names the role being hired
    r"|(?:the|our|your)\s+(?:[\w-]+\s+)?(?:team|manager|mentor|lead|supervisor|co-?worker|colleague)s?"
    r"(?:\s+(?:you|who)\s+(?:will\s+)?(?:report|work)\w*\s+(?:to|with|alongside|under))?"
    r"|(?:the|an?|your)\s+(?:[\w-]+\s+)?(?:team|manager|mentor|lead|supervisor|co-?worker|colleague)s?"
    r"\s+(?:you|who)\s+(?:will\s+)?(?:report|work)\w*\s+(?:to|with|alongside|under))$"
    )
# A named third person: two or three capitalised words in the original text ("Sam Lee", "Jordan Rivera"),
# never one word ("Electrician") and never a capitalised job title ("Store Manager").
_NAMED_PERSON = re.compile(r"(?:^|[\s(\-*])([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){1,2})\s+(?:has|have|brings?|holds?)\b")
_TITLE_END = re.compile(r"\b(?:manager|director|nurse|engineer|technician|electrician|associate|specialist|analyst|lead"
                        r"|supervisor|assistant|clerk|driver|teacher|accountant|representative|rep|coordinator|officer|agent"
                        r"|cook|chef|server|cashier|paralegal|attorney|developer|designer|planner|consultant|advisor)s?$")


def _named_person(subject: str, orig: str) -> bool:
    for m in _NAMED_PERSON.finditer(orig or ""):
        name = m.group(1)
        if name.lower() == subject.strip().lower() and not _TITLE_END.search(name.lower()):
            return True
    return False


def _someone_elses(before: str, in_req: bool = False, orig: str = "") -> bool:
    m = _HAS_BEFORE.search(before)
    if not m:
        return False
    subject = before[:m.start()].strip(" \t-*>:#~•")
    if not subject or _SUBJECT_IS_CANDIDATE.search(subject) or _APPLICANT_SUBJECT.search(subject):
        return False
    if in_req and not (_OTHER_PARTY.search(subject) or _named_person(subject, orig)):
        return False  # under Requirements an unknown subject is the applicant's: at least a REVIEW
    if re.search(r"\bto$", subject) and re.match(r"\b(?:have|bring|hold|carry)\b", m.group(0)):
        return False  # "expected to have 5 years"; "the manager you report to has 15 years" is someone else
    if re.search(r"\band$", subject):
        return not re.search(r"\byou\b|\bcandidate|\bapplicant", subject) and bool(_SUBJECT_IS_COMPANY.search(subject))
    return True


# A "20+ years" whose subject is the COMPANY, matched against the text just before the number. A
# "leader" counts only as a market or industry leader: "a people leader with 8+ years" is a bar.
_COMPANY_AGE = re.compile(
    r"(?:\b(?:company|firm|organi[sz]ation|business|brand|agency|group|marketplace|platform|practice"
    r"|hospital|clinic|school|district|retailer|manufacturer|contractor|carrier|dealership"
    r"|(?:market|industry|sector|category|global)\s+leader)\s+with\s+"
    r"|\bwe\s+(?:have|bring|'ve|’ve)\s+(?:had\s+|spent\s+)?)"
    r"(?:over\s+|more\s+than\s+|nearly\s+|almost\s+)?$")
# "for over 20 years" names no subject, so it is the company's only when no person is being asked for.
_FOR_OVER = re.compile(r"\bfor\s+(?:over|more\s+than)\s+$")


def _company_age(l: str, before: str) -> bool:
    window = before[-60:]
    return bool(_COMPANY_AGE.search(window)) or (bool(_FOR_OVER.search(window)) and not _PERSON_CUE.search(l))


# The company speaking about itself, which counts only when the sentence names no candidate bar.
_COMPANY_VOICE = re.compile(
    r"\bwe(?:'ve| have)\s+(?:had|been|spent|built|served|earned)\b|\bcelebrat|\bfor (?:over|more than)\b"
    # Company shapes only: "in business development" is work.
    r"|\b(?:has|have) served\b|\bin business\s+(?:for|since)\b|\bfounded\s+(?:in\s+)?(?:19|20)\d\d\b|\bsince (?:19|20)\d\d\b"
    r"|^[\s\-*>•]*with\s+" + _Q + r"(?:\d{1,2}|" + _W + r")\s*\+?\s*" + YR + r"\b[^,]*,")
_GROUP_WITH = re.compile(r"\b(?:team|staff|crew|partners|founders|leadership|experts|professionals|veterans)\s+with\s+" + _Q + r"$")
_BACKED = re.compile(r"\b(?:backed|led|built|powered|driven|supported|informed|shaped|guided|founded|drawing|based"
                     r"|thanks|celebrating|proud|boasting|offering)\b(?:\s+\w+){0,2}?\s+" + _Q + r"$")
_OWN_TAIL = re.compile(r"\b(?:our|us|we)\b|\bcombined\s+(?:[\w-]+\s+)?experience\b")

# Headings that open a section about the company, a closed list: "About us", "About <Company>", "Who we are",
# "Our story/company/mission/history", "Company overview". "About <words>" is the company's only when none of the
# words names the candidate, the applicant, you, the role, job, position, work, opportunity, hire or team. The
# section is only a label: its lines are read like any other line, so company history is silenced by
# _company_history's closed shapes inside _is_work and never by the heading (round 12).
_ABOUT_NOT_COMPANY = (r"(?![\w .&'-]*\b(?:candidates?|applicants?|you|your|role|job|position|work|opportunit(?:y|ies)"
                      r"|hire|team|teammates?|person|individual|people|requirements?|qualifications?)\b)")
_ABOUT_HEADING = re.compile(
    r"(?:#+\s*)?(?:about\s+us|about\s+" + _ABOUT_NOT_COMPANY + r"[\w .&'-]{1,40}|who we are"
    r"|our (?:story|company|mission|history)|company overview)\s*:?", re.I)
_ANY_HEADING = re.compile(r"#+\s*\S.*|[A-Za-z][\w ,&/'()-]{1,50}:")
_REQ_HEADING = re.compile(
    r"(?:#+\s*)?(?:requirements?|qualifications?|minimum qualifications|preferred qualifications"
    r"|what you(?:'ll)? (?:bring|need|have)|who you are|about you|you have|must haves?|nice to haves?"
    r"|skills|experience|responsibilities|the role|about the role|what we(?:'re)? look(?:ing)? for)\s*:?", re.I)


_DEMAND_LABEL = re.compile(r"^[\s\-*>#\u2022_]*(?:mandatory|essential)\s*[:=-]\s*")
_PAY_CLAUSE = re.compile(
    r"\bstep\s*\d|\bsalary\s+(?:schedule|scale|grid|table|placement)\b|\bpay\s+(?:schedule|scale|grid|table|band|step)\b"
    r"|\blongevity\b|\bdifferential\b|\b(?:additional|extra)\s+(?:vacation|pto|leave|days?|week)\b|\bvacation\b|\bpto\b"
    r"|\bpaid\s+time\s+off\b|=\s*\$")
_BENEFIT_TAIL = re.compile(r"(?<!\bto )(?<!\bto be )\b(?:receive[sd]?|earn(?:s|ed)?|eligible\s+for|qualif(?:y|ies)\s+for|entitled\s+to)\b")
_PAY_NEXT = re.compile(r"\s*[:=]\s*\$")


def _clause(text: str, last: bool = False) -> str:
    parts = re.split(r"[,;]|\bbut\b", text)
    return parts[-1] if last else parts[0]


# Which section a heading opens. Only a section that plainly lists what the applicant must have can turn
# a bare line into a requirement; a Preferred section can only ever make it preferred.
_APPLICANT_HEADING = re.compile(
    r"(?:(?:job|role|position|minimum|basic|required|key|core|essential|candidate|education and|skills and|experience and)\s+)*"
    r"(?:requirements?|qualifications?)(?:\s*(?:and|&)\s*(?:requirements?|qualifications?|skills|experience))?"
    r"(?:\s+for\s+(?:this|the)\s+(?:role|job|position))?"
    r"|required(?:\s+(?:skills|experience|education))?|experience required|must[- ]haves?"
    r"|what you(?:'ll| will)? (?:bring|need|have)(?: to (?:the|this) (?:role|team|table))?"
    r"|what we(?:'re| are)? look(?:ing)? for|what we need|who we(?:'re| are) looking for"
    r"|who you are|about you|about the (?:ideal )?(?:candidate|applicant)|you have|you bring"
    r"|your (?:background|experience|qualifications)")
_PREFERRED_HEADING = re.compile(
    r"(?:preferred|desired|desirable|additional|bonus|nice[- ]to[- ]have)(?:\s+(?:qualifications?|requirements?|skills|experience|points?))?"
    r"|nice[- ]to[- ]haves|pluses|extra credit|even better(?: if.*)?|it(?:'s| is) a plus if.*|bonus if.*|bonus points?(?: if.*)?"
    r"|(?:good|great)[- ]to[- ]have|plus if you (?:have|bring).*|ways to stand out|what (?:would )?sets? you apart"
    r"|(?:what )?we(?:'d| would) love to see|would love to see")
_PREFERRED_WORD = re.compile(r"\b(?:preferred|preference|desired|desirable|nice[- ]to[- ]haves?|bonus|assets?|optional"
                             r"|helpful|pluses?|advantageous)\b")
# A list item: a bullet, or a number with a point. "**Bold**" is not a bullet.
_LIST_ITEM = re.compile(r"^\s*(?:[-+•·▪◦‣" + _EN_DASH + r"]|\*(?=\s)|\d{1,2}[.)](?=\s))")
_KEEP_SECTION_HEADING = re.compile(r"education|experience|licen[sc]es?(?:ure)?|certifications?|skills|knowledge|abilities")
_CLOSING_HEADING = re.compile(
    r"benefits?|perks|compensation|pay|salary|what we offer|what you get|why (?:join|work).*|responsibilities|duties"
    r"|what you(?:'ll| will) do|the role|about the role|equal opportunity.*|how to apply")
_BOLD_HEADING = re.compile(r"(?:\*\*|__).+(?:\*\*|__):?")


def _section_of(line: str):
    """'requirements', 'preferred', 'about', 'keep', 'other', or None when the line is no heading."""
    bare = line.strip().lstrip("#*_>-\u2022\t ").rstrip(":*_\t ").strip().replace("\u2019", "'")
    low = bare.lower()
    if not low or len(low) > 60 or re.search(r"\d\s*\+?\s*(?:years?|yrs?)\b", low):
        return None
    if _PREFERRED_HEADING.fullmatch(low):
        return "preferred"
    # Any short line naming a preference is a preferred heading, colon or not ("Experience Preferred",
    # "Preferred Knowledge, Skills and Abilities", "Assets"). A list item is one only when it ends in a colon.
    if ((not _LIST_ITEM.match(line) or line.rstrip(" *_").endswith(":")) and not re.search(r"\d", low)
            and len(low.split()) <= 8 and _PREFERRED_WORD.search(low)):
        return "preferred"
    if _APPLICANT_HEADING.fullmatch(low):
        return "requirements"
    if _ABOUT_HEADING.fullmatch(bare):
        return "about"
    if _KEEP_SECTION_HEADING.fullmatch(low):
        return "keep"
    if (_CLOSING_HEADING.fullmatch(low) or _REQ_HEADING.fullmatch(line) or _ANY_HEADING.fullmatch(line)
            or _BOLD_HEADING.fullmatch(line)):
        return "other"
    return None


def _bullet_label(line: str):
    """A list item that is a sub-heading, not a requirement: no number, and it ends in ":", is wholly bold, or is
    a known preferred label ("- Good to have:", "- **Good to have**", "* Ways to stand out"). Returns the section
    it opens, or None when the item is an ordinary bullet ("- 8+ years in one of:" carries a number, so it stays)."""
    m = _LIST_ITEM.match(line)
    if not m:
        return None
    body = line[m.end():].strip()
    if not body or re.search(r"\d", body):
        return None
    bare = body.strip("*_ \t").rstrip(":*_ \t").strip().replace("’", "'").lower()
    if not (body.rstrip(" *_").endswith(":") or _BOLD_HEADING.fullmatch(body) or _PREFERRED_HEADING.fullmatch(bare)):
        return None
    kind = _section_of(body)
    return kind if kind in ("requirements", "keep", "preferred") else "other"


def _field_bar(l: str, before: str) -> bool:
    """Is the bare "N years <field>" asked of the candidate? It needs a candidate cue in the sentence,
    a lead-in like "with" or "and", or the number opening the line (a bullet in a list)."""
    if _FOR_SPAN.search(before) and not _PERSON_CUE.search(l):
        return False
    return bool(_CANDIDATE_CUE.search(l) or _DEMAND_LABEL.search(before)
                or re.search(r"\b(?:with|and|have|needs?)\s+$", before)
                or not re.sub(_Q + r"$", "", before).strip(" \t-*>:#~•"))


# THE ONE SHAPE THAT CAN DROP. The whole sentence has to be this and nothing else, so nothing here reads
# English: a sentence with an alternative, a condition, a hedge or a second clause simply does not fit.
_NUM = r"(?:\d{1,2}(?:\.\d+)?|" + _W + r")"
_FREE_WORD = r"[a-z][\w/&'’.+#-]*"
_PLAIN_SHAPE = re.compile(
    r"[\s\-*>#•_]*"
    r"(?P<lead>(?:(?:requires|required\s*:|must\s+have|you\s+have|you\s+bring|we\s+require|we\s+need"
    r"|we(?:\s+are|['’]re)\s+looking\s+for\s+someone\s+with)\s+)?"
    r"(?:(?:a\s+)?minimum\s+of\s+|at\s+least\s+)?)"
    r"~?\s*" + _NUM + r"(?:\s*" + _RANGE_SEP + r"\s*~?\s*" + _NUM + r")?\s*\+?\s*-?\s*(?:years?|yrs?)\b\.?\+?(?:['’]s?)?\s+"
    r"(?:of\s+(?:" + _FREE_WORD + r"\s+){0,6}?)?experience\b"
    r"(?P<tail>(?:\s+(?:in|as)\s+(?:" + _FREE_WORD + r"\s*){1,5}?)?)"
    r"(?P<mark>,?\s*\(?\s*(?:required|minimum)\s*\)?)?[\s.!_]*")
# The short "in X" / "as a X" after "experience" names a field or a job and nothing else. A hedge or a verb in
# it ("in hospital nursing recommended", "in retail is beneficial") makes the sentence something else. Any
# "-ed" word counts as a verb there, apart from the few that name a field ("in a related field").
_HEDGE_WORD = re.compile(
    r"\b(?:is|are|be|been|was|were|would|will|should|can|could|recommended|encouraged|beneficial|valued|welcomed?"
    r"|ideal|advantage\w*|helpful|plus|desired|preferred|considered|appreciated|assets?|bonus|strongly|highly|great"
    r"|optional|wanted|useful|good|best)\b")
# Field words that end in -ed but name the work, not a hedge ("as a registered nurse"). Licence and
# certificate words stay out: _NOT_PLAIN reads them as a possible other path, so a person looks.
_FIELD_ED = frozenset("related advanced regulated specialized specialised applied automated integrated managed skilled "
                      "registered chartered".split())


def _hedged_tail(tail: str) -> bool:
    return bool(_HEDGE_WORD.search(tail)) or any(w not in _FIELD_ED for w in re.findall(r"\b([a-z]+ed)\b", tail))
# Inside that shape, any of these means it is not one plain unconditional requirement.
_NOT_PLAIN = re.compile(
    r"\b(?:or|otherwise|equivalent|combination|preferred|preferably|ideally|plus|bonus|nice"
    r"|degrees?|diplomas?|ged|bachelor\w*|master['’]?s|associate['’]?s|doctora\w+|ph\.?d\w*|mba|bsn|msn"
    r"|licen[sc]\w*|certif\w*|credentials?"
    r"|with|without|if|unless|not|no|never|under|from|for|less\s+than|fewer\s+than"
    r"|other|many|most|some|unlike|normally|typically|usually|often|generally|formerly|may|might"
    r"|about|around|roughly|approximately|desired|desirable|helpful|advantageous|guidelines?|flexible|negotiable"
    r"|contracts?|lease|warrant\w*|retention|tenure|credit|criminal|records?"  # a short-list word: a person reads it
    r"|our|their|his|her|who|whose|which|that|when|while|after|before)\b|:")
# An invitation to apply below the bar. It waives the bar wherever it sits in the posting, because postings put
# "apply anyway" in a closing paragraph far below the list it answers.
# "All levels encouraged to apply" invites an applicant below the bar, so the bar is for a person to read;
# "coach staff at all levels of the store" names no applicant and no invitation, so it waives nothing.
_ALL_LEVELS = (r"\b(?:all|any)\s+(?:experience\s+|skill\s+|career\s+)?levels?\b[^.\n]{0,40}?"
               r"\b(?:encouraged|welcomed?|invited|(?:to|may|can|should)\s+apply)\b")
# A line that names a shortfall ("less experience", "less experienced candidates", "fewer years", "not quite 8
# years", "don't meet every requirement", "don't meet 100% of", "not sure you meet all", "even if you have less")
# and is not a refusal ("need not apply", "should not apply", "will not be considered"). "We encourage you to apply
# even if you have never worked in a hospital" names no shortfall, so the bar still drops; "Mentor less
# experienced nurses" is a duty, not a waiver.
_SHORTFALL = (
    r"^(?=[^\n]*(?:\bless\s+experience(?:d)?\b|\bfewer\s+years\b(?!\s+than)"
    r"|\bnot\s+quite\s+(?:\d{1,2}|" + _W + r")\s*\+?\s*(?:years?|yrs?)\b"
    r"|\b(?:don['’]?t|do\s+not|doesn['’]?t|does\s+not)\s+(?:yet\s+)?(?:meet|match|check|have|tick)\s+"
    r"(?:(?:every|all|each)\b|100\s*%)"
    r"|\b(?:not\s+sure|unsure)\b[^.\n]{0,30}?\b(?:meet|match|have|tick)\s+(?:(?:every|all|each)\b|100\s*%)"
    r"|\beven\s+if\s+you\s+(?:only\s+)?(?:have\s+)?(?:less|fewer)\b"
    r"|\bany\s+one\s+of\s+the\s+above\b))"
    r"(?![^\n]*\b(?:need\s+not|should\s+not|shouldn['’]?t|must\s+not|(?:will|would|shall)\s+not\s+be\s+considered"
    r"|won['’]?t\s+be\s+considered|not\s+be\s+considered|(?:do\s+not|don['’]?t|please\s+do\s+not)\s+apply)\b)"
    r"(?![^\n]*\b(?:mentor|train|coach|guid|supervis|lead|support|develop|onboard)\w*\s+(?:[\w-]+\s+)?less\s+experienced\b)")
# A substitution or waiver clause answers the whole bar, wherever it sits ("Equivalent combinations of education
# and experience will be considered", "A master's degree may substitute for two years", "may be waived").
# A bare "or equivalent" beside a degree is not on it: it swaps the degree, not the years.
_SUBSTITUTION = (r"\bsubstitut(?!\w*\s+(?:teach|position|staff|nurse|pool|list|role))\w*|\bin\s+lieu\b|\bwaive[ds]?\b|\bwaiver\b"
                 r"|\bequivalent\s+combinations?\b|\bcombination\s+of\s+(?:education|training|schooling)\s+and\s+experience\b"
                 r"|\bequivalent\b[^.\n]{0,60}?\b(?:will|may|can|could)\s+(?:also\s+)?be\s+(?:considered|accepted)\b")
# The years called a guideline anywhere in the posting ("The years requirement is a guideline", "flexible on years",
# "*Years may be reduced for ...") leave every bar for a person to read.
_YEARS_HEDGE = (r"\b(?:years?|experience\s+requirements?)\b[^.\n]{0,60}?\b(?:guidelines?|flexible|negotiable|reduced"
                r"|lowered|not\s+a\s+hard|can\s+be\s+(?:lower|less|fewer))\b|\bflexible\s+(?:on|about)\s+(?:the\s+)?(?:years|experience)\b")
# The posting says its requirements are not hard ("These are not hard requirements", "No experience required",
# "Requirements are flexible", "Experience preferred but not required", "We value potential over years").
# "No travel required" names no requirement of experience, so it waives nothing.
_NOT_HARD = (r"\b(?:no|not|n['’]t|never)\s+(?:a\s+)?(?:hard|strict|firm|rigid|absolute|set)\s+(?:requirements?|minimums?|rules?|must)\b"
             r"|\bnone\s+of\s+(?:the\s+above|these|them)\b[^.\n]{0,40}\b(?:requirements?|required|mandatory|musts?)\b"
             r"|\b(?:requirements?|qualifications?|experience|years\s+of\s+experience|the\s+above|these)\b[^.\n]{0,40}?"
             r"\b(?:not|isn['’]t|aren['’]t)\s+(?:strictly\s+|absolutely\s+|always\s+)?(?:required|necessary|needed|mandatory"
             r"|hard|strict|firm|rigid|a\s+(?:hard\s+|strict\s+|firm\s+)?(?:requirement|rule|must))\b"
             r"|\bno\s+(?:prior\s+|previous\s+|minimum\s+|formal\s+)?(?:experience|years)\s+(?:is\s+)?(?:necessary|required|needed"
             r"|minimum|requirement)\b|\bno\s+minimum\s+(?:experience|years)\b|\bno\s+experience\s*[?!]"
             r"|\b(?:requirements?|qualifications?|years(?:\s+of\s+experience)?|experience)\b[^.\n]{0,30}?\b(?:are|is)\s+"
             r"(?:a\s+|just\s+a\s+|only\s+a\s+)?(?:flexible|negotiable|guides?|guidelines?|suggestions?)\b"
             r"|\bpotential\s+over\s+(?:years|experience|tenure)\b")
# THE OPEN-DOOR RULE (round 18). Rounds 13 to 18 each found new wording for "people below the bar may apply" that a
# phrase list missed ("New grads welcome!", "Trade school counts toward experience", "First-year teachers are
# welcome to apply"). So a DROP needs the whole posting to be unambiguous: any line anywhere with a word that opens
# the door (welcome, encourage, invite, consider, counts toward, substitute, equivalent, waive, flexible, guideline,
# junior, entry level, new or recent graduate, apprentice, trainee, first-year, new teacher or nurse, a level number
# after a title such as "Electrician II") turns every DROP into a REVIEW, unless that line is a refusal ("will not
# be considered", "need not apply"). A REVIEW costs the user one line to read; a wrong DROP costs a job.
_OPEN_DOOR = (r"^(?=[^\n]*\b(?:welcom\w*|encourag\w*|invit\w*|consider\w*|counts?\s+(?:toward|towards|as|for)"
              r"|experience\s+(?:also\s+|all\s+)?counts?\b|(?:also|all)\s+counts?\b"
              r"|substitut(?!\w*\s+(?:teach|position|staff|nurse|pool|list|role))\w*|equivalen\w*|waiv\w*|flexib\w*|guidelines?|negotiable|junior|jr\.|entry[- ]level"
              r"|(?:new|recent)\s+grad\w*|graduates?|apprentic\w*|trainees?|first[- ]year|new\s+(?:teachers?|nurses?|hires?"
              r"|to\s+the\s+(?:field|trade|industry))|[a-z]{2,}\s+(?:ii|iii|iv)\b|level\s+(?:[ivx]+|\d)\b"
              r"|[a-z]{2,}\s+[1-4]\s+(?:through|to|or|and|-)\s+(?:[a-z]{2,}\s+)?[1-5]\b"
              r"|(?:don['’]?t|do\s+not)\s+(?:need\s+to|have\s+to)\s+(?:meet|have|check)\b"
              r"|missing\s+(?:a\s+few|some|one\s+or\s+two)\s+(?:years|requirements|qualifications|boxes)\b"
              r"|(?:fellowship|residency|training|development|apprenticeship|associate|trainee)\s+(?:track|program|role|path)\b))"
              r"(?![^\n]*\b(?:need\s+not|should\s+not|shouldn['’]?t|must\s+not|(?:will|would|shall)\s+not\s+be\s+considered"
              r"|won['’]?t\s+be\s+considered|not\s+be\s+considered|(?:do\s+not|don['’]?t|please\s+do\s+not)\s+apply"
              r"|not\s+(?:be\s+)?(?:eligible|accepted|substituted)|cannot\s+be\s+(?:substituted|waived)|no\s+substitut\w*)\b)")
# What the posting says about who it hires: experience, levels, qualifications, requirements, potential, applying.
# "No travel required", "Mentor less experienced nurses" and "coach staff at all levels of the store" say nothing
# about the applicant's bar, so plain "required", "experienced" and "levels of" are not on it.
_OTHER_VOICE = re.compile(r"\b(?:experience\b|levels?\b(?!\s+of\b)|qualif\w*|requirements\b|potential\b|candidates?\b"
                          r"|apply(?:ing)?\b|applicants?\b|close\b|case[- ]by[- ]case|seniority\b)"
                          # "Five years is preferred but not required": the years themselves called optional
                          r"|\b(?:years?|yrs?)\b[^\n]*\b(?:required|mandatory|preferred|ideal|optional)\b", re.I)
_REFUSAL = re.compile(r"\b(?:need\s+not|should\s+not|shouldn['’]?t|must\s+not|(?:will|would|shall)\s+not\s+be\s+considered"
                      r"|won['’]?t\s+be\s+considered|not\s+be\s+considered|(?:do\s+not|don['’]?t|please\s+do\s+not)\s+apply)\b",
                      re.I)
_INVITE = re.compile(_ALL_LEVELS + "|" + _SHORTFALL + "|" + _SUBSTITUTION + "|" + _YEARS_HEDGE + "|" + _NOT_HARD
                     + "|" + _OPEN_DOOR, re.I | re.M)
# A level offered with its own count ("Junior: 1+ years", "the Associate level (2+ years)", "Internal candidates:
# 4+ years"). analyze_jd compares the count with the bar: a lower one means the posting hires below the bar.
_LOWER_BAR = re.compile(
    r"\b(?:junior|jr\.?|mid[- ]level|mid(?=\s*[:(-])|associate|entry[- ]level|entry|internal\s+candidates?|apprentice"
    r"|trainee|level\s+(?:[ivx]+|\d)|tier\s+\d|grade\s+\d)\b[^\n\d]{0,30}?(?<![\d.,$/])(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
# An alternative stated beside the sentence, on the same line or the next bullet, leaves it for a person.
_WAIVER = re.compile(
    r"\bequivalent\b|\bsubstitut(?!\w*\s+(?:teach|position|staff|nurse|pool|list|role))|\bin\s+lieu\b|\bwaive|^[\s\-*>#•_]*or\b|\bor[\s*_]*$"
    r"|\balternative(?:ly|s)?\b|\b(?:also|will|may|might|can|could|gladly|happily)\s+consider\b|(?<!not be )\bconsidered\b"
    r"|\bexceptions?\b|\bnew\s+grad(?:uate)?s?\b|\bentry[- ]level\b"
    # a conditional heading such as "Without a degree:" or "With a BSN:" splits the bar into paths
    r"|^[\s\-*>#•_]*(?:without|with|if|for\s+(?:those|candidates|applicants)|absent)\b[^.\n]{0,50}:[\s*_]*$"
    r"|" + _ALL_LEVELS + "|" + _SHORTFALL,
    re.I | re.M)


# Another number offered as an alternative, which may have no "years" of its own.
_OR_OFFER = re.compile(r"\bor\b[^.;]*?(?<![\d.,$/])(\d{1,2}(?:\.\d+)?|\b" + _W + r"\b)(?=\s*\+?\s*-?\s*(?:years?\b|yrs?\b|with\b|and\b|if\b))")


# A last word in the "in X / as a X" slot that comments on the requirement instead of naming a field or a job:
# "... as a dispatcher helps", "... in dispatch maybe", "... in retail matters", any "-ly" word, "and up".
_TAIL_QUALIFIER = re.compile(r"\b(?:[a-z]+ly|helps?|matters?|counts?|maybe|perhaps|sometimes|typical|ideal|works?|up"
                             r"|more|less|so|ok|okay|fine|good|great|best|useful|valuable|welcome[ds]?|wanted"
                             r"|appreciated|considered|accepted|encouraged|important|key|essential)\W*$")


def _is_plain_requirement(l: str, raw: str, in_req: bool) -> bool:
    """The DROP decision. One sentence, as a whole, in the one plain shape, asked of the applicant by a
    lead-in, a closing "required" or "minimum", or its place under a requirements heading."""
    shape = _PLAIN_SHAPE.fullmatch(l.replace("*", ""))
    if not shape or re.search(r"\bor\b", raw) or _NOT_PLAIN.search(l.replace("*", "")[shape.end("lead"):]):
        return False
    if _HEDGE_WORD.search(l.replace("*", "")[shape.end("lead"):]) or _hedged_tail(shape.group("tail")):
        return False
    if _TAIL_QUALIFIER.search(shape.group("tail").strip()):
        return False
    return bool(shape.group("lead").strip() or shape.group("mark") or in_req)


# THE SHORT LIST. These counts are not experience, so they get no floor and no REVIEW.
_NOT_NEEDED_BEFORE = re.compile(
    r"\bno\s+(?:need|requirement|necessity)\b|\bneed\s+not\b"
    r"|\bnot\s+(?:requir\w+|need\w*|necessary|ask\w+\s+for|look\w+\s+for|seek\w+|expect\w*)"
    r"|\b(?:do|does|did|will|would)\s+not\s+(?:require|need|expect|ask\s+for|look\s+for)"
    r"|n['’]t\s+(?:require|need|expect|ask\s+for|look\s+for)")
_NOT_NEEDED_TAIL = re.compile(r"^[^,;]*\b(?:not|isn['’]?t|aren['’]?t)\s+(?:strictly\s+|necessarily\s+)?"
                              r"(?:required|necessary|needed|mandatory|a\s+requirement)\b")
_PARTY = r"(?:vendors?|subcontractors?|suppliers?|clients?|patients?|students?)"
_PARTY_BEFORE = re.compile(
    r"^[\s\-*>#•_]*(?:for\s+)?(?:(?:our|all|any|the|its)\s+)?(?:(?![a-z]+ing\b)[\w-]+\s+)?" + _PARTY
    + r"\s*(?:[:,]|(?:must|should|shall|need|needs|are|have|will)\b)"
    # ...unless the party is hiring the applicant: "Our client, a regional hospital, requires 6+ years" and
    # "Students will benefit from a teacher with 6+ years" are the applicant's count, not the party's
    # (an active hiring verb only: "Subcontractors are required to have 7 years" is still the party's own count)
    + r"(?![^.;]*\b(?:requires|requiring|seeks|seeking|needs|wants|looking\s+for|hiring|hires|recruiting"
    r"|searching\s+for)\b)"
    + r"(?![^.;]*\b(?:an?|one)\s+(?:[\w-]+\s+){1,3}(?:with|having|who\s+(?:has|have|brings?))\s*$)"
    r"|\b(?:require|requires|need|needs|ask|asks|expect|expects)\s+(?:(?:our|all|any|that|its)\s+)+(?:[\w-]+\s+)?" + _PARTY + r"\b"
    r"|\b" + _PARTY + r"\s+with\s+" + _Q + r"$")
_PARTY_TAIL = re.compile(r"\s*(?:of\s+)?(?:[\w/&-]+\s+){0,5}?(?:experience|expertise)\s+(?:from|of|by)\s+(?:(?:our|all|any|its|their|the)\s+)+"
                         r"(?:[\w-]+\s+)?" + _PARTY + r"\b")
_LOOKBACK = re.compile(
    r"\bdriving\s+record\b|\bmvr\b|\bmotor\s+vehicle\s+record\b|\b(?:accident|violation|incident)[- ]free\b|\bmoving\s+violations?\b"
    r"|\bbackground\s+(?:check|screen\w*|investigation)s?\b|\bcriminal\b|\bconvictions?\b|\bfelon\w*\b"
    r"|\bclean\s+(?:\w+\s+)?(?:record|driving|history)\b|\bcredit\s+(?:history|check|report)\b"
    r"|\b(?:residency|residence|address)\s+history\b|\bresid(?:ed|ing)\b|\blived\b|\blook[- ]?back\b|\bdrug[- ]free\b"
    # driver records: "No DUI in the past 10 years", "No at-fault accidents in the last 3 years", "No suspensions"
    r"|\bdu[il]s?\b|\bdwis?\b|\b(?:at[- ]fault\s+|preventable\s+|chargeable\s+)?accidents?\b|\bsuspensions?\b"
    r"|\breckless\s+driving\b")
# The records that may sit AFTER a count or end a label ("7 years clean driving record", "a 10-year lookback",
# "Background check: 7 years"). "criminal", "felony", "background screening" and "investigation" are not on it:
# after a count they name a field of work ("6 years in criminal investigations", "6 years in background
# screening"), so only the lookback shapes BEFORE a count ("no felony convictions in the last 7 years") silence.
_RECORD_NOUN = (r"(?:(?:clean|good|safe|satisfactory|acceptable)\s+)?(?:driving\s+(?:record|history)|mvr|motor\s+vehicle\s+record"
                r"|(?:accident|violation|incident)[- ]free|clean\s+(?:\w+\s+)?(?:record|driving|history)"
                r"|credit\s+(?:history|report)(?!\s+(?!(?:check|checks|verification|required|on\s+file)\b)[a-z])"
                r"|(?:residency|residence|address)\s+history|look[- ]?back|drug[- ]free"
                r"|background\s+checks?|(?:with\s+)?(?:no|without\s+(?:a\s+|any\s+)?)\s*(?:convictions?|felon\w*|(?:moving\s+)?violations?|accidents?))\b")
_RECORD_HISTORY = re.compile(r"[\s,]*(?:of\s+)?(?:[\w/&-]+\s+)?(?:credit|address|residen\w*|driving|criminal|rental|payment"
                             r"|medical|salary|tax|immunization|vaccination|claims?)\s+history\b(?=\s*(?:$|[,.;:)!?]|(?:check|checks|verification|report|reports|record|records|required|preferred|lookback|on\s+file)\b))")
_RETENTION = re.compile(r"\b(?:average|employee|staff|team|our)\s+tenure\b|\bretention\b")
_COMPANY_OPENING = re.compile(r"^[\s\-*>#•_]*with\s+" + _Q + r"$")
_TURN_TO_APPLICANT = re.compile(r"\byou\b|\byour\b|\bcandidates?\b|\bapplicants?\b|\bmust\b|\bshould\b|\brequired\b")
_OWN_BEFORE = re.compile(r"\b(?:our|its|their)\s+$")
_NOT_A_SKILL_LABEL = re.compile(
    r"^(?:contract|lease|terms?|warranty|retention|tenure|duration|length|commitment|age|founded|history|vesting|residence|residency"
    r"|in\s+business|citizen\w*|visa)(?:\s+(?:term|length|duration|period))?$|^clean\b(?!\s+room)")
_WORK_TAIL = re.compile(
    r"\s*(?:of\s+)?(?:[\w/&-]+\s+){0,3}?(?:work|working|employment|career|tenure|track\s+record|under\s+(?:your|the)\s+belt)\b"
    r"(?!\s+(?:permit|visa|authori[sz]ation|eligib\w*))")


# "Years of service" asked of the applicant is work; with a benefit cue anywhere in the sentence it is tenure.
_SERVICE_BAR = re.compile(r"\s*(?:of\s+)?service\b(?!\s+(?:commitment|agreement|contract|obligation|award|pin|anniversary"
                          r"|credit|area|charge|fee|plan)\b)")
_SERVICE_BENEFIT = re.compile(r"\bafter\b|\breceiv\w*|\beligib\w*|\bvest\w*|\bearn\w*|\baccru\w*|\bpension\b|\bsabbatical\b"
                              r"|\bretire\w*|\banniversar\w*")
# A benefit the employer gives after N years of employment or service: pay and tenure, not a bar.
_AFTER_COUNT = re.compile(r"\bafter\s+" + _Q + r"$")
_TENURE_TAIL = re.compile(
    r"\s*(?:of\s+)?(?:(?:qualifying|continuous|consecutive|full[- ]time|eligible|uninterrupted)\s+)?(?:employment|service)\b"
    r"|\s*(?:with|at)\s+(?:the|our)\s+(?:company|firm|district|organi[sz]ation)\b")
_BENEFIT_WORD = re.compile(r"\b(?:eligib\w*|vest\w*|match\w*|pension|retire\w*|forgiv\w*|benefits?|bonus|sabbatical|leave"
                           r"|pto|vacation|plan|receiv\w*|earn\w*|accru\w*|qualif\w*|loan|insurance|stipend|raise)\b")
# Someone the applicant reports to or works with, holding the years: "Report to a manager with 15 years",
# "work with mentors who have 10+ years". Only these nouns and only after one of these verbs, so "Mentored by a
# lead with 18 years" and "Seeking a team lead who has 8 years" are still read.
_PEER_BEFORE = re.compile(
    r"\b(?:report(?:s|ing)?\s+(?:directly\s+)?to|work(?:s|ing)?\s+(?:closely\s+)?(?:with|alongside|beside|under)"
    r"|partner(?:s|ing)?\s+with|collaborat\w+\s+with)\s+(?:(?:an?|the|your|our|other|fellow|experienced|senior|seasoned)\s+)*"
    r"(?:[\w-]+\s+)?(?:manager|mentor|lead|supervisor|team|coworker|co-worker|colleague|teammate)s?\s+"
    r"(?:with|who\s+(?:have|has|bring|brings))\s+" + _Q + r"$")


def _after_tenure(l: str, before: str, tail: str) -> bool:
    return bool(_AFTER_COUNT.search(before) and _TENURE_TAIL.match(tail) and _BENEFIT_WORD.search(l))


def _before_clause(before: str) -> str:
    return re.split(r"[,;:(]|\s-\s|\bbut\b", before)[-1]


def _years_not_needed(before: str, tail: str) -> bool:
    """A plain statement that the years are not needed. It governs only its own clause."""
    return (bool(_NOT_NEEDED_BEFORE.search(_before_clause(before))) or bool(_NOT_NEEDED_TAIL.search(tail))
            or (bool(re.search(r"\bno\s+$", before)) and bool(re.search(r"\b(?:required|needed)\b", tail))))


# The clause that holds the count. A ";" or a sentence end always closes it; so does ", " when a pay, benefit or
# label phrase follows ("8+ years of experience, $20 an hour", "..., Shift: nights"). A "." inside "$20.50" does not.
_CLAUSE_END = re.compile(r";|[.!?](?=\s|$)")
_PAY_OR_LABEL_NEXT = re.compile(
    r",\s*(?=\$|\d+(?:\.\d+)?\s*/\s*h|(?:pay|paid|salary|wages?|rate|stipend|bonus|compensation|benefits?|earn\w*|starts?"
    r"|starting|eligible|we\s+(?:pay|offer)|you(?:['’]ll|\s+will)?\s+(?:earn|receive|get)|plus|pto|vacation|401\(?k)\b"
    r"|[a-z][\w /&-]{0,25}:)")
# What may carry a pay reading across a comma from a pay phrase before the count: "Pay: $20/hr, rising after 3 years".
_PAY_GOES_ON = re.compile(r"^\s*(?:(?:and\s+)?(?:rising|increasing|going\s+up|growing|moving|stepping|raised|bumped)\b"
                          r"|(?:with|after|at|for)\s+" + _Q + r"$)")


def _count_clause(before: str, tail: str) -> tuple:
    """The text of the count's own clause: (before, tail) cut at the clause marks around the count."""
    b = _CLAUSE_END.split(before)[-1]
    t = _CLAUSE_END.split(tail)[0]
    cut = _PAY_OR_LABEL_NEXT.search(t)
    return b, (t[:cut.start()] if cut else t)


def _pay_or_benefit(before: str, tail: str) -> bool:
    """The count is itself the pay, benefit or tenure quantity ("Teachers with 10 years of experience earn
    $70,000", "A $2 raise after 5 years"), judged inside the count's own clause only. A pay word in another
    clause of the line ("8+ years of experience; pay starts at $20") never silences the count."""
    before, tail = _count_clause(before, tail)
    pay_before = _PAY_BEFORE.search(before)
    if pay_before:
        # the pay phrase must reach the count inside one comma clause, or carry on across it ("..., rising after")
        last = before.rsplit(",", 1)
        pay_before = len(last) == 1 or _PAY_BEFORE.search(last[1]) or _PAY_GOES_ON.match(last[1])
    return (bool(_PAY_AFTER.search(tail)) or bool(pay_before) or bool(_PAY_NEXT.match(tail))
            or bool(_PAY_CLAUSE.search(_clause(before, True) + " " + _clause(tail))) or bool(_BENEFIT_TAIL.search(_clause(tail))))


def _companys_own(l: str, before: str, tail: str, in_req: bool = False, strict: bool = False, orig: str = "") -> bool:
    if strict or in_req:  # under a requirements heading "Led crews for 5 years" has no company subject: closed shapes only
        # Under a requirements heading with a work word, only a clear other party in its closed shape: a named
        # subject on the closed list, "a company with 20 years" / "we have 20 years", "our/its 30 years", or a
        # team or staff "with" its years. A "we" after the count ("the tools we use"), "based" or "driven"
        # before it, or the company's voice is never enough there.
        return bool(_someone_elses(before, True, orig) or _COMPANY_AGE.search(before[-60:]) or _OWN_BEFORE.search(before)
                    or (_GROUP_WITH.search(before) and not _CANDIDATE_CUE.search(l)))
    if _someone_elses(before, in_req, orig) or _company_age(l, before) or _OWN_BEFORE.search(before):
        return True
    if _COMPANY_OPENING.search(before) and "," in tail and not _TURN_TO_APPLICANT.search(tail.split(",", 1)[1]):
        return True  # "With two decades of experience serving Ohio, Acme is hiring"
    # A line under a requirements heading is never read as the company talking about itself by its voice alone.
    return not _CANDIDATE_CUE.search(l) and bool((not in_req and _COMPANY_VOICE.search(l)) or _GROUP_WITH.search(before)
                                                 or _BACKED.search(before) or _OWN_TAIL.search(tail)
                                                 or _ACCOLADE.search(before) or _third_person_hold(before))


# Company history, in its own closed shapes, read the same under a requirements heading: a sentence that opens on
# "Serving" a place or people (not "Serving as" a job), or a subject that "has been" a name, a leader, around or
# in business. A candidate cue anywhere ("You have been serving customers for 8 years") keeps it the applicant's.
_SERVING_OPEN = re.compile(r"(?:^[\s\-*>#•_]*|^[^,]{2,60},\s*)(?:(?:proudly|happily|faithfully)\s+)?serving\s+(?!as\b)([^.;]{0,50}?)\s*\bfor\s+"
                           + _Q + r"$")
# The object served must be a place or a community: "the community", "the greater Dayton area", or a capitalised
# place name ("Ohio"). Never people served at work ("customers", "patients") or a job ("in a supervisory role").
_PLACE_OBJECT = re.compile(
    r"^(?:(?:the|our|its|local|greater|surrounding|entire|whole|wider|rural|urban|all\s+of)\s+)*(?:[\w-]+\s+){0,2}?"
    r"(?:communit(?:y|ies)|areas?|regions?|cit(?:y|ies)|count(?:y|ies)|states?|neighbou?rhoods?|nations?|countr(?:y|ies))"
    r"(?:\s+(?:of|in|across|throughout)\s+[\w\s-]{1,30})?$")
_SERVED_AT_WORK = re.compile(r"\b(?:customers?|clients?|patients?|guests?|members?|users?|tables?|accounts?|students?"
                             r"|roles?|positions?|capacity)\b|^(?:in|as|at|on|with)\b")
_CAPITAL_PLACE = re.compile(r"\b[Ss]erving\s+(?:the\s+|greater\s+|Greater\s+)?((?:[A-Z][\w'-]*)(?:\s+[A-Z][\w'-]*){0,2})\s+for\b")


def _serves_a_place(obj: str, orig: str) -> bool:
    obj = obj.strip()
    if not obj or _SERVED_AT_WORK.search(obj):
        return False
    if _PLACE_OBJECT.match(obj):
        return True
    m = _CAPITAL_PLACE.search(orig)
    return bool(m) and m.group(1).lower() == re.sub(r"^(?:the|greater)\s+", "", obj)
_COMPANY_RUN = re.compile(
    r"\b(?:has|have|['’]ve)\s+been\s+(?:(?:an?|the)\s+(?:[\w-]+\s+){0,2}?(?:name|leader|fixture|staple|institution|presence"
    r"|household\s+name)\b|around\b|in\s+business\b|in\s+operation\b|family[- ]owned\b)[^.;]{0,50}\bfor\s+" + _Q + r"$"
    # "We have proudly served the Tulsa community for 40 years": the company's own run, with a word of pride in it
    r"|\b(?:has|have|['’]ve)\s+(?:(?:proudly|happily|faithfully|successfully|been)\s+)+serv(?:ed|ing)\b[^.;]{0,60}"
    r"\bfor\s+" + _Q + r"$")


def _company_history(l: str, before: str, orig: str = "") -> bool:
    if _CANDIDATE_CUE.search(l):
        return False
    serving = _SERVING_OPEN.search(before)
    if serving and _serves_a_place(serving.group(1), orig):
        return True
    m = _COMPANY_RUN.search(before)
    if not m:
        return False
    subject = before[:m.start()].strip(" \t-*>:#~•")
    return bool(subject) and not _SUBJECT_IS_CANDIDATE.search(subject) and not re.search(r"\b(?:who|that|which)$", subject)


# "Globex has been named a best place to work for 7+ years": an award's run, not a bar.
_ACCOLADE = re.compile(r"\b(?:named|recogni[sz]ed|ranked|voted|awarded|honou?red|listed|certified\s+as)\b[^.;]{0,80}\bfor\s+"
                       + _Q + r"$")
_HAS_BEEN_DOING = re.compile(r"\b(?:has|had)\s+(?:been\s+)?\w+(?:ed|ing)\b[^.;]{0,60}\bfor\s+" + _Q + r"$")


def _third_person_hold(before: str) -> bool:
    """"Sam Lee ... has been teaching middle school for 8+ years": a named third person's run. A bullet
    opening with "Has" ("Has worked for 8 years as a nurse") is the applicant, so it needs a subject first."""
    m = _HAS_BEEN_DOING.search(before)
    if not m:
        return False
    subject = before[:m.start()].strip(" \t-*>:#~•")
    return bool(subject) and not _SUBJECT_IS_CANDIDATE.search(subject)


def _lookback(before: str, tail: str) -> bool:
    """A record or lookback is the subject only when it sits against the count, in the count's own clause, and
    no experience or expertise word follows the count there ("5 years of background investigation experience"
    is work; "No felony convictions in the last 7 years" and "a 10-year driving record lookback" are records)."""
    if _EXPERIENCE_ANCHOR.match(_own_tail(before, tail)):
        return False
    clause, last = _before_clause(before), None
    for last in _LOOKBACK.finditer(clause):
        pass
    if last and not re.search(r"\band\b", clause[last.end():]):
        return True
    return bool(re.match(r"[\s,]*(?:of\s+)?" + _RECORD_NOUN, tail))


# A work word on a line under a requirements heading: on such a line silence needs a closed-list shape.
_REQ_WORK_WORD = re.compile(r"\b(?:experience[ds]?|expertise|work(?:s|ed|ing)?|employment|employed|careers?|service|roles?"
                            r"|positions?)\b|\bas\s+an?\s+[a-z]|\bin\s+(?:(?:the|our|an?|their|its)\s+)?[a-z]")
# Under that rule the only span words that still silence are a lookback: "in the last 8 years", "within 7 years".
_LOOKBACK_SPAN = re.compile(r"\b(?:last|past|within|during|throughout)\s+$")


# THE BACKSTOP (round 12). Rounds 9 to 12 kept finding one class: a silence word or shape somewhere else on the
# line beat a clear work count ("Must be 18 years of age with 8 years of experience as an electrician"). So after
# every other decision, a count that would be silent is looked at in its OWN clause: from the count to the next
# clause mark (";", a sentence end, a pay or label phrase after a comma: _count_clause) or the next count, so
# " and have 5 years" or " with 8 years" starts a new count's clause. If a work anchor follows the count there,
# it may stay silent only for a reason that is about that same count: plain negation of it, a clear other party
# owning it (the closed subject list, the company, a named person), or a pay, benefit or tenure phrase whose
# quantity it is. Every other reason (age, records, schooling, a list word, a span word) belongs to a different
# count or clause and never silences this one: it becomes a REVIEW, or a DROP when the plain shape fits.
_NEXT_COUNT = re.compile(r"(?<![\d.,$/])(?:\d{1,2}(?:\.\d+)?|\b" + _W + r"\b)(?:\s*" + _RANGE_SEP + r"\s*\S+)?\s*\+?\s*-?\s*"
                         r"(?:years?|yrs?|months?|decades?)\b|\b(?:a|one|two|three)\s+decades?\b")
# The words between the count and "experience" name its field; past "and", "or", "but" or a credential word the
# experience belongs to something else ("a 4 year degree and experience with ...").
_EXPERIENCE_ANCHOR = re.compile(r"[\s'’+.]*(?:of\s+)?(?:(?!(?:and|or|but|plus|" + "|".join(sorted(_GAP_STOP)) + r")\b)"
                                r"[\w/&'’-]+\s+){0,5}?(?:experience|expertise)\b"
                                r"|[\s'’+.]*(?:of\s+)?(?:[\w/&-]+\s+){0,2}?background\s+(?:in|as)\b")
# "-ing" words that name no work: a span, an order, a residence or a state.
_NOT_WORK_ING = frozenset("""
    preceding following including beginning starting ending remaining pending according regarding being having
    going coming living residing during prior standing counting ongoing outstanding long lasting
""".split())
# What an "-ing" word can modify without naming work: a record ("driving record"), or a thing held or kept for a
# term ("a 2 year teaching commitment", "a four year accounting program").
_NOT_WORK_OBJECT = frozenset("""
    record records history violations violation offenses offences convictions incidents accidents lookback check checks
    commitment commitments contract degree degrees diploma license licence certificate certification apprenticeship
    program programme programs course courses school plan agreement term
""".split())
# The subject of the count's own clause, before a verb that gives it the years ("Sam Lee spent 11 years ...",
# "Globex spent the last ten years ..."). It is another party only when it is on the closed list or a proper name.
_SUBJECT_VERB = re.compile(r"^(.*?)\s*\b(?:(?:has|have|had)\s+)?(?:spent|has|have|had|brings?|holds?)\s+"
                           r"(?:(?:the|its|their|our|a|an)\s+)?(?:(?:last|past|first)\s+)?" + _Q + r"$")
_PROPER_NAME = re.compile(r"(?:^|[\s(\-*])((?:[A-Z][\w'&-]*)(?:\s+[A-Z][\w'&-]*){0,2})\s+(?:(?:has|have|had)\s+)?"
                          r"(?:spent|has|have|had|brings?|holds?)\b")


def _named_other(b: str, orig: str) -> bool:
    """The count's own subject is a clear other party: the closed subject list, or a proper name (a firm or a
    person) that is not a job title and not the applicant."""
    m = _SUBJECT_VERB.search(b)
    if not m:
        return False
    subject = m.group(1).strip(" \t-*>:#~•")
    if not subject or _SUBJECT_IS_CANDIDATE.search(subject) or _APPLICANT_SUBJECT.search(subject) or _CANDIDATE_CUE.search(b):
        return False
    if _OTHER_PARTY.search(subject) or subject.lower() in ("we", "our team", "our company", "our firm", "our store"):
        return True  # "We have a 40-year track record": the employer speaking about itself
    return any(n.group(1).lower() == subject.lower() and not _TITLE_END.search(n.group(1).lower())
               for n in _PROPER_NAME.finditer(orig or ""))
_ING_ANCHOR = re.compile(r"[\s'’+.]*(?:of\s+)?([a-z]+ing)\s+(?:(?:and|or|&)\s+[a-z]+ing\s+)?(?:(?:as|in|with|for|at|on|to|under)\s+)?(?:(?:an?|the|our|your)\s+)?"
                         r"([a-z][\w/&-]*)")
_ROLE_ANCHOR = re.compile(r"[\s'’+.]*(?:of\s+)?(?:(?:work|working|employment|service)\s+)?as\s+an?\s+[a-z]"
                          r"|[\s'’+.]*in\s+(?:the\s+|an?\s+)?(?:[\w/&-]+\s+){0,3}?(?:field|roles?|positions?|capacity)\b"
                          r"|[\s'’+.]*in\s+(?!(?:an?\s+row|business|operation\b|the\s+making|age|prison|jail|total|advance|addition"
                          r"|length|duration|good\s+standing|(?:the\s+)?(?:last|past|prior|previous|next|first)|this|that|these|those"
                          r"|the\s+(?:u\.?s\.?|united|country|state|area|city|county|region|community|military)\b|(?:the\s+)?u\.?s\b"
                          r"|college|university|(?:high\s+|grad(?:uate)?\s+|trade\s+|nursing\s+|law\s+|medical\s+)?school|schooling"
                          r"|an?\s+(?:program|programme|apprenticeship|degree)|residency|service\s+to|which|order"
                          r"|(?:the|our|your|a)\s+(?:plan|pension|401\(?k\)?|retirement|benefits?)|(?:a\s+)?(?:plan|pension))\b)"
                          r"(?:the\s+)?[a-z][\w/&-]*")


def _own_tail(before: str, tail: str) -> str:
    """The text after the count, up to its clause mark or the next count."""
    t = _count_clause(before, tail)[1]
    nxt = _NEXT_COUNT.search(t)
    return t[:nxt.start()] if nxt else t


def _work_anchor(before: str, tail: str, unit: str = "years", low=2, applicant: bool = True) -> bool:
    """Is a work anchor right after this count, in its own clause? experience, expertise, background in/as,
    "<verb>ing + object" (serving customers, driving trucks), "as a/an <noun>", "in the <field> field / roles".
    A singular "year" describing a noun ("a 2 year teaching commitment") is a term, so only experience counts there."""
    t = _own_tail(before, tail)
    if _EXPERIENCE_ANCHOR.match(t):
        return True
    if re.match(r"[\s'’+.-]*(?:proven\s+|successful\s+|demonstrated\s+)?(?:history|track\s+record)\s+(?:of|in|as)\b", t):
        # "a 5-year history of increasing responsibility in nursing" under Requirements is the applicant's own record
        # of work; "With a 50-year history of serving Ohio families" outside it is the company's history
        return applicant
    if isinstance(low, (int, float)) and _adjective_use(t, unit, low):
        return False
    ing = _ING_ANCHOR.match(t)
    if (ing and ing.group(1) not in _NOT_WORK_ING and ing.group(2) not in _NOT_WORK_OBJECT
            and ing.group(2) not in _FUNCTION_WORD):
        return True
    return bool(_ROLE_ANCHOR.match(t))


def _same_count_silence(l: str, before: str, tail: str, in_req: bool, strict: bool, orig: str) -> bool:
    """The only reasons a count with a work anchor may stay silent, each judged on that count's own clause."""
    b, t = _count_clause(before, tail)
    clause_l = b + " _ " + t  # the count's own clause, standing in for the line
    if _years_not_needed(before, tail):
        return True  # plain negation of this count
    if (_someone_elses(b, in_req, orig) or _named_other(b, orig) or _PARTY_BEFORE.search(b) or _PARTY_TAIL.match(t)
            or _PEER_BEFORE.search(b) or _OWN_TRACK_RECORD.search(b)
            or _companys_own(clause_l, b, t, in_req, strict, orig) or _company_history(clause_l, b, orig)):
        return True  # a clear other party owns this count
    return bool(_pay_or_benefit(before, tail) or _after_tenure(clause_l, b, t) or _RETENTION.search(_before_clause(b)))


_APPLICANT_WHO = re.compile(r"\b(?:someone|somebody|a\s+person|candidates?|applicants?|individuals?|professionals?"
                            r"|an?\s+[a-z]+(?:\s+[a-z]+)?)\s+(?:who|that)\s+(?:has|have|brings?|holds?)\b(?:(?!\b(?:who|that)\b).)*$")


def _is_work(l: str, before: str, tail: str, shaped: bool, unit: str, low: int, in_req: bool = False,
             orig: str = "") -> bool:
    """_is_work_core, then the backstop: a silent count with a work anchor in its own clause is work unless a
    reason about that same count silences it."""
    if _is_work_core(l, before, tail, shaped, unit, low, in_req, orig):
        return True
    if _APPLICANT_WHO.search(before) and not _years_not_needed(before, tail):
        return True  # "We want someone who has been nursing for 8 years": the applicant, whatever the opener
    applicant = in_req or bool(_APPLICANT_LEAD.search(l)) or bool(re.search(r"\byou(?:['’]ll|['’]d|['’]ve)?\b", before))
    if not _work_anchor(before, tail, unit, low, applicant):
        return False
    strict = in_req and bool(_REQ_WORK_WORD.search(l))
    return not _same_count_silence(l, before, tail, in_req, strict, orig)


def _is_work_core(l: str, before: str, tail: str, shaped: bool, unit: str, low: int, in_req: bool = False,
                  orig: str = "") -> bool:
    """Is this count of years tied to the applicant's work? The short list first; then a real work phrase
    beats any list word ("8+ years of contract management experience"); then everything else that names work.
    Silence needs a reason from the short list: under a requirements heading or an applicant lead-in, a count
    that no listed reason claims is at least a REVIEW.

    Every path that returns silence, and the one closed-list reason it maps to:
      _is_age                                   age
      _years_not_needed                         plain negation
      _pay_or_benefit, _after_tenure, _RETENTION  pay or benefit tenure
      _PARTY_BEFORE, _PARTY_TAIL, _PEER_BEFORE  a clear other party (vendors, clients; a manager you report to)
      _companys_own                             a clear other party (closed subject list, company age, "our N years")
      _company_history                          company history, in its two closed shapes
      _lookback, _LOOKBACK_SPAN                 records or lookback
      _NOT_A_SKILL_LABEL label                  contract term, age, records, residence
      _NOT_EXPERIENCE_TAIL                      contract term, records, schooling length, job security (benefit)
      _EDUCATION, _adjective_use                schooling length; a "5 year plan" is no count of work
      _RETAINED                                 records or contract term
      _NOT_WORK list word                       per word, _NOT_WORK_CLOSED
    Under a requirements heading, on a line with a work word (_REQ_WORK_WORD), `strict` holds: the company's voice,
    a "we/our/us" after the count, "based/driven/backed" before it, a span word that is not a lookback, and a list
    word outside _NOT_WORK_CLOSED no longer silence, so the line is at least a REVIEW."""
    strict = in_req and bool(_REQ_WORK_WORD.search(l))
    if (_is_age(before, tail, low)
            or _years_not_needed(before, tail) or _pay_or_benefit(before, tail)
            or _PARTY_BEFORE.search(before) or _PARTY_TAIL.match(tail) or _companys_own(l, before, tail, in_req, strict, orig)
            or _company_history(l, before, orig)
            or _RETENTION.search(_before_clause(before)) or _after_tenure(l, before, tail) or _PEER_BEFORE.search(before)
            or _RECORD_HISTORY.match(tail)
            or re.search(r"\b(?:degree|bachelor\w*|master\w*|associate\w*|diploma|program(?:me)?|course(?:work)?)['’]?s?\s*\(\s*$",
                         before)):  # "Bachelor's degree (4 years)": the schooling length in brackets
        return False
    if _anchored(tail) or _EXPERIENCE_OF.search(before) or _EXPERIENCE_LABEL.search(before):
        return True
    if _lookback(before, tail):
        return False
    if _WORK_TAIL.match(tail) or (_TRACK_RECORD_BEFORE.search(before) and not _OWN_TRACK_RECORD.search(before)):
        return True
    label = _FIELD_LABEL.search(before) or (_TITLE_PAREN.search(before) if re.match(r"\s*\)", tail) else None)
    if label and (_REQUIRED_MARK.match(tail) or not tail.strip(" .*_)")):
        # judge only the label's own clause: "Clean record, retail experience: 8 years" is labelled "retail experience"
        name = re.split(r"[,;]\s*|[.!?]\s+|\s+(?:and|or|but)\s+|\s-\s", label.group(1).strip())[-1].strip()
        if strict and _REQ_WORK_WORD.search(name):
            return True  # a work word in the label itself ("Clean nursing experience: 8 years") is never a closed label
        return not (_NOT_A_SKILL_LABEL.search(name) or re.search(_RECORD_NOUN + r"\s*$", name))
    in_education = bool(_IN_EDUCATION_FIELD.match(tail))
    if _NOT_EXPERIENCE_TAIL.match(tail) or (_EDUCATION.match(tail) and not in_education) or _adjective_use(tail, unit, low):
        return False
    if _RETAINED.search(before) or (_NOT_A_BAR_BEFORE.search(before) and not strict) or (strict and _LOOKBACK_SPAN.search(before) and _LOOKBACK.search(l)):
        return False
    word_match = _FIRST_WORD.match(tail)
    word = word_match.group(1) if word_match else None
    forced = in_req or bool(_APPLICANT_LEAD.search(l))
    if (word == "service" and _SERVICE_BAR.match(tail) and not _SERVICE_BENEFIT.search(l)
            and (forced or _MUST_BEFORE.search(before) or _CANDIDATE_STATEMENT.search(before))):
        return True  # "Must have 8 years of service as a firefighter": asked of the applicant, no benefit
    if word == "total":
        # "7 years total in skilled trades", "10 years total, 5 in a supervisory role": a total of the applicant's
        # years, read like the same line without "total". Only a closed-list tail after it silences.
        rest = re.sub(r"^\s*total\b\s*,?", " ", tail)
        if _NOT_EXPERIENCE_TAIL.match(rest) or (_EDUCATION.match(rest) and not _IN_EDUCATION_FIELD.match(rest)):
            return False
        return forced or _field_bar(l, before)
    if (word in _NOT_WORK and not in_education and _standalone_field(tail, word_match)
            and (not strict or word in _NOT_WORK_CLOSED)):
        return False
    if (_CANDIDATE_STATEMENT.search(before) or _SEEKING_WITH.search(before) or shaped or (label and not tail.strip())
            or _APPLICANT_HOLD.search(before)):
        return True
    if word and word not in _FUNCTION_WORD:
        return forced or _field_bar(l, before)
    return bool(forced or _HOLD_FOR.search(before) or _MUST_BEFORE.search(before))


def _digits_for_compounds(line: str) -> str:
    """"Twenty-five years" as "25 years", so its hyphen is never read as the dash of a range."""
    line = re.sub(r"\b(twenty|thirty)[- ](one|two|three|four|five|six|seven|eight|nine)\b",
                  lambda m: str(NUM_WORDS[m.group(1).lower()] + NUM_WORDS[m.group(2).lower()]), line, flags=re.I)
    line = re.sub(r"\b(\d{2})\s*\(\1\)", r"\1", line)
    def small_range(m):  # "3 or 4 years" is one loose bar; "Level 2 or 8 years" is a license and a count
        if int(m.group(1)) >= int(m.group(2)) or re.search(r"(?:level|grade|tier|class|step|type|part|phase|stage)\s*$", line[:m.start()], re.I):
            return m.group(0)
        return f"{m.group(1)}-{m.group(2)}"
    return re.sub(r"\b(\d{1,2})\s+or\s+(\d{1,2})(?=\+?\s*(?:years?|yrs?)\b)", small_range, line, flags=re.I)


def _sentences(line: str) -> list:
    """One line of a posting, split into sentences, so "Over 40 years of history. You will..." does
    not lend the second sentence's "you" to the first. Abbreviations and "OR" alternatives stay whole."""
    out = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'*~-])(?!OR\b|Or\b)", line):
        if out and re.search(r"(?:\b[a-z]\.){1,3}$|\b(?:ph\.d|yrs?|min|approx|inc|st|dr|mr|mrs|ms|no|vs|e\.g|i\.e)\.$", out[-1], re.I):
            out[-1] += " " + part
        else:
            out.append(part)
    return out


def _number(token: str):
    if token in NUM_WORDS:
        return NUM_WORDS[token]
    value = float(token)
    return int(value) if value.is_integer() else value


def _work_counts(l: str, in_req: bool = False, orig: str = ""):
    """Yield (floor, ceiling) for each count of years in this sentence that is tied to work."""
    label = _YEARS_LABEL.search(l) or _BARE_LABEL.match(l)
    if label:  # "Years of Experience: 7" and "Experience Required: 8+" have no "years" after the number
        yield (_number(label.group(1)), _number(label.group(2)) if label.group(2) else None)
    for m in _MENTION.finditer(l):
        low, high = _number(m.group(1)), _number(m.group(2)) if m.group(2) else None
        before = l[:m.start()]
        shaped = bool(m.group(3)) or bool(m.group(5)) or high is not None or bool(_FLOOR_WORD.search(before))
        if _is_work(l, before, l[m.end():], shaped, m.group(4), low, in_req, orig):
            yield (low, high)
    # "60 months of experience" = 5 years. A month count is read only with the word experience after it.
    for m in _MONTHS.finditer(l):
        tail = l[m.end():]
        if _anchored(tail) and _is_work(l, l[:m.start()], tail, True, "months", 2, in_req, orig):
            low, high = _number(m.group(1)) / 12, (_number(m.group(2)) / 12 if m.group(2) else None)
            yield (int(low) if float(low).is_integer() else low,
                   int(high) if high is not None and float(high).is_integer() else high)
    # "a decade of experience" = 10 years ("nearly"/"almost" = 9). Same decision as any number.
    for m in _DECADE.finditer(l):
        before = l[:m.start()] + (m.group(1) or "")
        if not _is_work(l, before, l[m.end():], False, "years", 10, in_req, orig):
            continue
        if _FOR_SPAN_ANY.search(before) and not _PERSON_CUE.search(l):
            continue  # "Serving families for two decades" is a span of time with no applicant in it
        count = m.group(3)
        tens = 10 * (0 if count is None else int(count) if count.isdigit() else NUM_WORDS.get(count, 1))
        yield (5 if m.group(2) else tens - 1 if (m.group(1) or "").strip() in ("nearly", "almost") else tens, None)


def _normalized(text: str) -> str:
    """Lower case, "Twenty-five" as 25, "Nine (9)" as 9: the text every reading works on."""
    low = re.sub(r"\b" + _W + r"\s*\((\d{1,2})\)", r"\1", _digits_for_compounds(text).lower())
    # "8 (eight) years" and "10 (10) years" as 8 and 10; a bracketed count alone, "(8) years", as 8.
    low = re.sub(r"(?<![\d.,$/])(\d{1,2})\s*\(\s*(?:\d{1,2}|" + _W + r")\s*\)(?=\s*\+?\s*-?\s*(?:years?|yrs?)\b)", r"\1", low)
    low = re.sub(r"(?<![\w)])\(\s*(\d{1,2})\s*\)(?=\s*\+?\s*-?\s*(?:years?|yrs?)\b)", r"\1", low)
    low = re.sub(r"\byoe\b", "years of experience", low)  # "5+ YOE" is "5+ years of experience"
    # "6y+", "3y experience", "6+ y experience": a bare "y" right after a digit count is years (digits only)
    low = re.sub(r"(?<![\w.,$/])(\d{1,2})\s*y(\+?)(?![a-z])", r"\1\2 years", low)
    low = re.sub(r"(?<![\w.,$/])(\d{1,2})(\s*\+)\s*y(?![a-z])", r"\1\2 years", low)
    low = re.sub(r"\b((?:years?|yrs?)\.?\s*)min\b\.?", r"\1minimum", low)  # "8 yrs min." is "8 yrs minimum"
    # "Six full years", "5 total years", "six consecutive years": one word between the count and "years" that
    # only stresses the count is dropped, so the count is read like "six years"
    return re.sub(r"(?<![\d.,$/])(\d{1,2}|" + _W + r")(\s*\+?)\s+(?:full|total|consecutive|continuous|straight|solid"
                  r"|complete|cumulative|combined|additional|progressive|plus)\s+(?=(?:years?|yrs?)\b)", r"\1\2 ", low)


# The fallback for a label line no shape above reads: an experience word, a years word, a separator and a bare
# number ("Experience (years): 6", "Years of experience - 6", "Experience, years: 6+"). It is never a DROP,
# only a REVIEW, so a label wording nobody listed is read by a person instead of passing in silence.
_LABEL_FALLBACK = re.compile(
    r"^(?=[^\n]*\b(?:experience|exp)\b)(?=[^\n]*(?<![a-z])(?:years?|yrs?)\b)(?![^\n]*\b(?:age|old)\b)"
    r"[^\n]*?\b(?:experience|exp|years?|yrs?)\b\.?[^0-9\n]{0,30}?(?:[:=|]|\s-\s|\))[^0-9\n]{0,12}?"
    r"(?<![\d.,$#/])(\d{1,2})(?![\d.,%])\s*\+?"
    r"(?!\s*-?\s*(?:years?|yrs?|months?|mos|decades?|hours?|hrs?|days?|weeks?|am|pm|lbs?|pounds?)\b)")


_LAST_NET_COUNT = re.compile(r"(?<![\d.,$/])(\d{1,2}|" + _W + r")\s*\+?\s*(?:years?|yrs?)\b")
# The net reads LABEL layouts only: the clause opens with a work label and a separator ("Experience: 8 years",
# "Experience (Nursing): 8 years", "Experience - Nursing (8 years)", a table cell). A sentence keeps every closed-list
# decision above ("Your manager has 15 years of experience" stays someone else's).
_LAST_NET_WORK = re.compile(
    r"^[\s\-*>#•_|]*(?:[a-z]+\s+)?(?:experience|exp|work\s+history|employment\s+history|background|expertise|skills?)"
    r"(?:\s+(?:level|required|needed|minimum))?\s*(?:\([^)]{0,40}\))?\s*(?:[:=|(]|[-\u2013\u2014]\s)")
# The closed list for the net, each reason TIED TO THE COUNT (a word anywhere in the clause is not enough: "6 years of
# school counseling", "of credit underwriting", "in our industry" are work). N = the count of years.
_N_YRS = r"(?:\d{1,2}|" + _W + r")\s*\+?\s*(?:years?|yrs?)"
_LAST_NET_CLOSED = re.compile(
    _N_YRS + r"\s+(?:of\s+age|old)\b"                                                    # age: "N years of age / old"
    r"|\b(?:in|within|over|during|for)\s+the\s+(?:last|past|prior|previous)\s+" + _N_YRS   # lookback: "in the last N years"
    + r"|\b(?:after|following|upon|at)\s+" + _N_YRS + r"|\bvest\w*\s+(?:after|over|in)\s+" + _N_YRS  # pay/benefit tenure
    + r"|^[^:]*?\b(?:we|our|we['’]ve|the\s+company)\b[^:]*$"                             # the company is the subject
    r"|" + _N_YRS + r"\s+(?:accident|violation|incident)[- ]free\b|" + _N_YRS + r"\s+(?:clean\s+)?(?:driving|mvr)\b"
    r"|" + _N_YRS + r"\s+of\s+(?:college|school|schooling|university|high\s+school)\b(?!\s+[a-z]+(?:ing|ion)\b)"
    r"|\b(?:an?\s+)?(?:\d|" + _W + r")[- ]year\s+(?:degree|diploma|program)\b"                # schooling length
    r"|\bcontract\s+term\b|\bterm\s*:", re.I)
# A work label with a count of years after it, in any shape no listed one reads: "Experience: Nursing (8 years)",
# "Skills: QuickBooks (8 years)", "Work history: accounting, 8 years", "Experience Level: Mid (5 years)".
# Never a DROP, only a REVIEW, so a person reads it instead of it passing in silence.
_WORK_LABEL_COUNT = re.compile(
    r"^(?![^\n]*\b(?:of\s+age|years?\s+old|age\b|ago\b|lookback|in\s+the\s+(?:last|past)))"
    r"[\s\-*>#•_]*(?:[a-z]+\s+)?(?:experience|exp|work\s+history|employment\s+history|background|skills?|expertise"
    r"|qualifications?|requirements?)(?:\s+(?:level|required|needed|minimum))?[*_\s]*[:=][^\n]{0,60}?"
    r"(?<![\d.,$/])(\d{1,2}|" + _W + r")\s*\+?\s*(?:years?|yrs?)\b", re.I)


def _read_sentence(sentence: str, in_req: bool, in_pref: bool, waived: bool):
    """One row for a sentence, (floor, ceiling, is_preferred, is_review, top), or None when no count in
    it is tied to work. floor is the lowest number offered; top is the highest floor on the line."""
    raw = sentence.lower()
    l = _normalized(sentence)
    hours = re.search(r"(?<![\d.,$/])(\d{1,3}(?:,\d{3})+|\d{3,5})\s*\+?\s*(?:[a-z]+\s+){0,2}?(?:hours?|hrs?)\s+(?:of|in)\b", l)
    if (hours and in_req and (_REQ_WORK_WORD.search(l) or re.search(r"\b(?:apprentic|journey|training|on[- ]the[- ]job)", l))
            and not re.search(r"(?<![a-z])(?:years?|yrs?)\b", l)):
        # "8,000 hours of documented electrical work": a trade bar in hours is read for a person, never dropped
        n = round(int(hours.group(1).replace(",", "")) / 2000, 1)
        return (n, None, in_pref or any(p in l for p in PREFERRED), True, n)
    if not (re.search(r"(?<![a-z])(?:years?|yrs?|months?|mos)\b|\bdecades?\b", l)  # "5yrs" has no \b before the y
            or _BARE_LABEL.match(l)):
        return None
    counts = list(dict.fromkeys(_work_counts(l, in_req, sentence)))
    if not counts:
        fallback = _LABEL_FALLBACK.search(l) or _WORK_LABEL_COUNT.search(l)
        if not fallback:
            return None
        n = _number(fallback.group(1))
        return (n, None, in_pref or any(p in l for p in PREFERRED), True, n)
    counts += [(_number(n), None) for n in _OR_OFFER.findall(l)]  # "(or 5 with a degree)": the lowest offer is shown
    lowest = min(counts, key=lambda c: c[0])
    preferred = in_pref or any(p in l for p in PREFERRED)
    firm = len(counts) == 1 and not preferred and not waived and _is_plain_requirement(l, raw, in_req)
    return (lowest[0], lowest[1], preferred, not firm, max(c[0] for c in counts))


# A two-cell table row, "| Years of experience | 8+ |", is read as its label form "Years of experience: 8+".
_TABLE_ROW = re.compile(r"^\|\s*([^|]*?[^|\s][^|]*?)\s*\|\s*([^|]*?[^|\s][^|]*?)\s*\|?\s*$")


def _table_row(line: str) -> str:
    m = _TABLE_ROW.match(line)
    return f"{m.group(1)}: {m.group(2)}" if m else line


def _plain_text(text: str) -> str:
    """The posting as plain characters, before anything reads it: compatibility forms folded (NFKC, so a
    fullwidth or superscript plus is "+"), every invisible format character (category Cf: soft hyphen,
    zero-width space, word joiner, bidi marks) removed, and every other space (category Zs) a plain space.
    Scraped postings carry these, and "8\u200b+ years" or "ye\u00adars" hid a plain bar from every pattern."""
    if text.isascii():
        return text
    text = unicodedata.normalize("NFKC", text)
    return "".join("" if unicodedata.category(ch) == "Cf" else " " if unicodedata.category(ch) == "Zs" else ch
                   for ch in text)


def analyze_jd(text: str):
    """Return floor and ceiling (from plain requirements only), weak (every (floor, ceiling) a person
    should read), weak_floor, and evidence, a list of (floor, ceiling, is_preferred, is_review, sentence, top).

    Every place on the way here that could drop a line naming years before _is_work / _work_counts reads it
    (round 12), and what each one does now:
      1. Blank lines are filtered from the line list: they hold no text, so no count is lost.
      2. A heading line (_section_of / _bullet_label) only sets the section and is still read; _section_of never
         takes a line with "N years" in it as a heading, so a count cannot hide inside one.
      3. An About heading and its section: removed as a skip (was: the heading `continue`, and every About line
         with no candidate cue skipped, so "About the Candidate / 8+ years ... nurse" was PASS). Its lines are now
         read; company history is silenced only by _company_history's closed shapes inside _is_work.
      4. The "your own notes" skip (KB-N, knowledge-base/, a configured name, "N years total"): removed. Every
         line of a jd-*.md file is the posting's, so "7 years total in skilled trades" is read.
      5. _read_sentence returns None for a sentence with no years/months/decade word and no bare label: it has
         no count to read. Every other sentence goes to _work_counts, and so to _is_work, whatever the section.
    There is no other `continue`, early return or line filter before _is_work."""
    evidence = []
    section = None    # the heading this line sits under: requirements, preferred, about, or None
    text = _plain_text(text)
    lines = [_table_row(raw.strip()) for raw in text.split("\n") if raw.strip()]
    invited = bool(_INVITE.search("\n".join(lines)))  # "apply anyway" anywhere: no DROP in this posting
    bar_lines: set[int] = set()
    read_lines: set[int] = set()
    about_lines: set[int] = set()  # the company's own section speaks about the company, not the applicant
    for i, line in enumerate(lines):
        kind = _section_of(line)
        if kind is None and section == "requirements":
            kind = _bullet_label(line)  # "- Good to have:" ends Requirements; "- Must have:" keeps it
        if kind == "keep":  # "Experience:" inside Requirements stays Requirements; it still ends an About
            section = None if section == "about" else section
        elif kind:
            section = None if kind == "other" else kind
        elif (section == "requirements" and not _LIST_ITEM.match(line)
              and not _PLAIN_SHAPE.fullmatch(_normalized(line).replace("*", ""))):
            # Requirement context is positive only: any line that is neither a list item nor itself one plain
            # requirement ends it, so an unrecognised heading ("Good to have", "Ways to stand out") and every
            # line after it can never DROP.
            section = None
        if section == "about":
            about_lines.add(i)
        sentences = _sentences(line)
        nearby = lines[max(i - 2, 0):i] + lines[i + 1:i + 3]  # two lines either side carry a waiver
        for sentence in sentences:
            others = [s for s in sentences if s is not sentence]
            # the rest of the same line is read one sentence at a time and also as one line, so "Less experience?
            # Apply anyway." after the bar on its own line waives it exactly as it does on the next line
            around = "\n".join(nearby + others + [" ".join(others)])
            row = _read_sentence(sentence, section == "requirements", section == "preferred", invited or bool(_WAIVER.search(around)))
            if row:
                evidence.append(row[:4] + (re.sub(r"\s+", " ", sentence)[:180], row[4]))
                read_lines.add(i)
                if not row[3]:
                    bar_lines.add(i)
    # THE LAST NET (round 22): a line that nothing above read, whose own clause names experience (or a work label)
    # and a count of years, is a REVIEW, never a silent PASS, whatever the layout ("Job Type: Full-time | Experience:
    # 8 years", "Experience (Nursing): 8 years", "| Experience | Nursing | 8 years |"). Only the closed list keeps
    # such a clause silent: an age, a record or lookback, a pay or benefit tenure, or the company's own years.
    for i, line in enumerate(lines):
        if i in read_lines or i in about_lines:
            continue
        clauses = [line] if line.lstrip().startswith("|") else re.split(r"\s+\|\s+|;\s+|\s+[·•]\s+|(?<=[.!?])\s+", line)
        for clause in clauses:
            c = _normalized(clause)
            m = _LAST_NET_COUNT.search(c)
            if m and _LAST_NET_WORK.search(c) and not _LAST_NET_CLOSED.search(c):
                n = _number(m.group(1))
                evidence.append((n, None, False, True, re.sub(r"\s+", " ", clause)[:180], n))
                break
    firm_floor = max((e[0] for e in evidence if not e[3]), default=None)
    # THE ONE-VOICE RULE (round 20): a DROP stands only when no other line of the posting talks about experience,
    # level, qualifications, requirements, potential or applying ("Level will be determined based on experience",
    # "If you are close, apply", "We hire for potential"). Headings and refusals do not count. Every other posting
    # is a REVIEW: the bar is shown to a person, never silently dropped.
    if firm_floor is not None and any(
            i not in bar_lines and i not in about_lines and (_section_of(line) is None or len(line.split()) > 6)
            and _OTHER_VOICE.search(line)
            and not _REFUSAL.search(line)
            for i, line in enumerate(lines)):
        evidence = [e[:3] + (True,) + e[4:] for e in evidence]
        firm_floor = None
    offers = [int(m.group(1)) for m in _LOWER_BAR.finditer("\n".join(lines))]
    offers += [e[0] for e in evidence]  # any other count of work years read in the posting ("## Electrician II / 3+ years")
    offers += [_number(m.group(1)) for m in re.finditer(  # ... and any count of experience, whoever it is about
        r"(?<![\d.,$/])(\d{1,2}|" + _W + r")\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[\w-]+\s+){0,3}?experience\b",
        _normalized("\n".join(lines)))]
    if firm_floor is not None and any(o < firm_floor for o in offers):
        evidence = [e[:3] + (True,) + e[4:] for e in evidence]  # a lower level is offered: a person reads the bar
    firm = [(e[0], e[1]) for e in evidence if not e[3]]
    weak = [(e[0], e[1]) for e in evidence if e[3]]
    floor = max((f for f, _ in firm), default=None)
    ceilings = [c for f, c in firm if f == floor and c is not None]
    return {"floor": floor, "ceiling": max(ceilings) if ceilings else None,
            "weak": weak, "weak_floor": max((f for f, _ in weak), default=None), "evidence": evidence}


def title_of(dossier: Path) -> str:
    readme = dossier / "README.md"
    if readme.exists():
        first = readme.read_text(errors="ignore").splitlines()
        for ln in first[:3]:
            if ln.startswith("# "):
                return ln[2:].strip()
    return dossier.name.replace("-", " ")


def is_senior_title(title: str) -> bool:
    # A dossier heading is "Company: Role Title". Only the role counts, or a company called Principal
    # Foods would make every one of its jobs senior.
    t = title.split(":", 1)[-1].lower()
    ladder = _TRADE_ROLE.sub(" ", t)  # Lead Maintenance Engineer is a trade, not a technical ladder
    return (bool(_SENIOR_WORD.search(_ORDINARY_TITLE.sub(" ", t)))
            or bool(_STAFF_LADDER.search(ladder)) or bool(_LEAD_LADDER.search(ladder)))


def _only_placeholders(text: str) -> bool:
    """True when a jd-*.md still holds only the template: headings, comments, the fenced facts block, and
    "[...]" slots. Nothing of a posting is in it, so comparing it would check nothing."""
    body = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            continue                                               # a heading names a section, not the posting
        line = re.sub(r"\[[^\]]*\]", " ", line)                  # a template slot
        if re.sub(r"^\s*(?:[-*>•]|\d+[.)])\s*", "", line).strip(" \t*_:|-"):
            return False
    return True


def verdict_for(dossier: Path):
    """Return (verdict, bar, reason, evidence_lines). verdict is one of DROP/REVIEW/PASS/NO-JD, or
    UNCONFIGURED when YOUR_YEARS_OF_EXPERIENCE has never been set in scripts/config.py."""
    jds = sorted(dossier.glob("jd-*.md"))
    if not jds:
        return ("NO-JD", None, "no jd-*.md file in dossier", [])
    text = "\n".join(p.read_text(errors="ignore") for p in jds)
    if _only_placeholders(text):
        return ("NO-JD", None, "jd-*.md still holds only the template's placeholders", [])
    if DROP_FLOOR is None:
        return ("UNCONFIGURED", None, "YOUR_YEARS_OF_EXPERIENCE is not set in scripts/config.py", [])
    your_years = DROP_FLOOR - 1
    a = analyze_jd(text)
    floor, ceiling = a["floor"], a["ceiling"]
    title = title_of(dossier)
    ev = a["evidence"][:2]

    if floor is not None and floor >= DROP_FLOOR:
        return ("DROP", floor, f"JD requires {floor}+ years (you have {your_years})",
                [e for e in a["evidence"] if not e[3] and e[0] >= DROP_FLOOR])
    if floor == your_years and ceiling and ceiling >= your_years + CEILING_SPREAD_FOR_REVIEW:
        return ("REVIEW", your_years, f"JD says {your_years}-{ceiling} years -- floor matches you but ceiling reaches senior", ev)
    # Anything else above your years, on a line a person has to read. A preferred range counts too.
    unclear = [e for e in a["evidence"] if e[3] and (e[5] >= DROP_FLOOR or (
        e[0] == your_years and (e[1] or 0) >= your_years + CEILING_SPREAD_FOR_REVIEW))]
    if unclear:
        main = max(unclear, key=lambda e: (e[5], e[0]))
        lowest, top = main[0], main[5]
        said = f"mentions {top} years, lowest number offered {lowest}" if lowest < top else f"mentions {top} years"
        how = "stated as preferred" if main[2] else "not as one plain requirement"
        return ("REVIEW", max(e[0] for e in unclear), f"{said}, {how}; read the line", unclear)
    if is_senior_title(title) and (floor is None or floor <= your_years):
        title_tail = title.split(":")[-1].strip()[:40]
        return ("REVIEW", floor, f"'{title_tail}' is a senior-plus title, years bar {floor if floor is not None else 'unstated'}", ev)
    return ("PASS", floor, f"floor {floor if floor is not None else 'unstated'} <= {your_years}", ev)


# tracker parse (brace-balanced, quote-aware)
def folder_status_map() -> dict[str, str]:
    if not TRACKER.exists():
        return {}
    html = TRACKER.read_text(errors="ignore")
    out: dict[str, str] = {}
    i = 0
    n = len(html)
    while i < n:
        if html[i] == "{":
            depth, j, instr, q = 0, i, False, ""
            while j < n:
                c = html[j]
                if instr:
                    if c == q and html[j - 1] != "\\":
                        instr = False
                elif c in "\"'":
                    instr, q = True, c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            obj = html[i:j + 1]
            fo = re.search(r'folder:"([^"]*)"', obj)
            st = re.search(r'status:"([^"]*)"', obj)
            if fo and st:
                out[fo.group(1).strip().rstrip("/")] = st.group(1).strip()
            i = j + 1
        else:
            i += 1
    return out


# A dossier is "handled" (no longer an OPEN drop) if it was submitted OR you already dropped it:
# tracker status "passed", or a drop banner prepended to its README. Without "passed" here the gate
# would re-flag every already-dropped role forever.
HANDLED_STATUSES = {"applied", "interview", "offer", "rejected", "ghosted", "passed"}
# Any wording of the banner: "DROPPED 2031-03-04: seniority gate", "Seniority gate: DROPPED".
_DROP_BANNER_RE = re.compile(r"DROPPED\b[^\n]{0,40}?(?i:seniority)|(?i:seniority)[^\n]{0,20}?\bDROPPED\b")
# The user's "no, keep it" after a DROP (R27): /wave writes "Seniority: KEPT <date> (you said fill it)" to the README,
# so the gate stops asking the same question again.
_KEPT_RE = re.compile(r"^[\s>#*_-]*seniority(?:\s+gate)?\s*:\s*\**\s*KEPT\b", re.I | re.M)
# A real submission record starts its own line and carries a date ("## SUBMITTED 2031-03-04").
# "NOT submitted" on the template's status line, or the word in prose, is not one.
_SUBMIT_RECORD = re.compile(
    r"^[ \t>#*_`\u2705]*(?:status\s*[:\-]\s*[*_` \t\u2705]*)?(?:submitted|applied on)\b"
    r"[*_`: \t\-\u2014]*(?:on\s+)?20\d\d-\d\d-\d\d", re.I | re.M)


def _visible(text: str) -> str:
    return re.sub(r"(?s)<!--.*?-->", "", text)


def is_handled(dossier: Path, fmap: dict[str, str]) -> bool:
    rel = f"applications/{dossier.name}"
    st = fmap.get(rel) or fmap.get(rel + "/")
    if st in HANDLED_STATUSES:
        return True
    rdme = dossier / "README.md"
    if rdme.exists():
        shown = _visible(rdme.read_text(errors="ignore"))
        if _DROP_BANNER_RE.search(shown[:800]) or _KEPT_RE.search(shown):
            return True
    app = dossier / "application.md"
    return app.exists() and bool(_SUBMIT_RECORD.search(_visible(app.read_text(errors="ignore"))))


def _any_floor(text: str):
    """Selftest helper: the strong floor, else the weak one, else None (nothing read at all)."""
    a = analyze_jd(text)
    return a["floor"] if a["floor"] is not None else a["weak_floor"]


def _graded(text: str):
    """Selftest helper: ("strong", n) for a plain requirement, ("weak", n) for a REVIEW line, or None."""
    a = analyze_jd(text)
    if a["floor"] is not None:
        return ("strong", a["floor"])
    return ("weak", a["weak_floor"]) if a["weak_floor"] is not None else None


# selftest
def _selftest_parsing(check) -> None:
    """Spelled ranges, doubled numbers, degree paths and the company's own age, in many fields."""
    global DROP_FLOOR
    saved = DROP_FLOOR
    fl = lambda t: _any_floor(t)
    span = lambda t: (_any_floor(t), analyze_jd("Requirements\n" + t)["ceiling"])
    try:
        check("'two years of retail experience' -> floor 2", fl("two years of retail experience"), 2)
        check("'3 or 4 years' binds at the lower number", fl("Must have 3 or 4 years of welding experience"), 3)
        check("'Level 2 or 8 years' stays the count, the level is no floor",
              fl("Level 2 or 8 years of welding experience"), 8)
        check("'one to three years of warehouse experience' -> 1-3",
              span("one to three years of warehouse experience"), (1, 3))
        check("'Two to four years of bookkeeping experience' -> 2-4, not 4",
              span("Two to four years of bookkeeping experience"), (2, 4))
        check("'five-eight yrs of HVAC experience' -> 5-8", span("five-eight yrs of HVAC experience"), (5, 8))
        check("'3 to five years of classroom teaching experience' -> 3-5 (mixed)",
              span("3 to five years of classroom teaching experience"), (3, 5))
        check("'six to nine years of inside sales experience' -> 6-9",
              span("six to nine years of inside sales experience"), (6, 9))
        check("'it will take five to ten years of focus' -> no floor (a horizon)",
              fl("Everyone here knows it will take five to ten years of focus to get there."), None)

        check("'Nine (9) years of warehouse experience' -> floor 9",
              fl("Nine (9) years of warehouse experience"), 9)
        check("'Six (6)+ years of nursing experience' -> floor 6", fl("Six (6)+ years of nursing experience"), 6)
        check("'three (3) to five (5) years of audit experience' -> 3-5",
              span("three (3) to five (5) years of audit experience"), (3, 5))

        check("two bars joined by 'and' are a person's to read -> the lowest, 5",
              fl("at least 5 years of nursing and at least 7 years in oncology"), 5)
        check("'preferred' on the line is never a required floor across paths",
              analyze_jd("Must have 9 years of audit experience preferred OR master's with 6 years")["floor"], None)

        check("'a family-owned contractor with 30+ years' -> no floor",
              fl("Northwind is a family-owned contractor with 30+ years of roofing work behind it."), None)
        check("'a regional hospital with 15-20 years' -> no floor",
              fl("Join a regional hospital with 15-20 years of trauma care."), None)
        check("'a retailer with twelve+ years' -> no floor", fl("Hooli is a retailer with twelve+ years on Main Street."), None)
        check("'market leader with 25+ years' -> no floor", fl("Globex is the market leader with 25+ years in plumbing supply."), None)
        check("'We have 40+ years of service' -> no floor", fl("We have 40+ years of service in this county."), None)
        check("'a people leader with 8+ years' stays a bar -> floor 8",
              fl("We are hiring a people leader with 8+ years of store management."), 8)
        check("'a nurse with 7+ years' stays a bar -> floor 7", fl("Seeking a nurse with 7+ years on a surgical floor."), 7)
        check("'for over 20 years' about the company -> no floor",
              fl("Initech has fixed furnaces in this valley for over 20+ years."), None)
        check("'for over 8+ years' asked of you stays a bar -> floor 8",
              fl("You must have worked as a machinist for over 8+ years."), 8)

        DROP_FLOOR = 6
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-audit-manager"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Audit Manager\n")
            (d / "jd-acme.md").write_text("Minimum of 9 years of accounting experience OR master's degree and 6 years OR doctorate and 4 years\n")
            check("a degree path is a person's call, the lowest number shown", verdict_for(d)[:2], ("REVIEW", 4))
    finally:
        DROP_FLOOR = saved


def _selftest_any_field(check) -> None:
    """The bar stated in any field's own words, and the lines that only look like one."""
    for line, want in (
            ("Candidates need 9 years of commercial driving with a clean record", 9),
            ("Eight years of HVAC field service", 8),
            ("RN license with 5 years acute care", 5),
            ("must have 6 years on the tools", 6),
            ("A teaching license and 6 years in the classroom", 6),
            ("Must have 7 years in a Level I trauma center", 7),
            ("10 years' classroom experience", 10),
            ("Must have ten years\u2019 warehouse supervision", 10),
            ("- 6 years as a charge nurse", 6),
            ("You have 8 yrs at a public accounting firm", 8),
            ("Experience: 7 years of store management", 7)):
        check(f"{line!r} -> floor {want}", _any_floor(line), want)
    for line in ("Over the next 5 years we will open new depots",
                 "Over the next 5 years of growth, you will help shape it",
                 "The depot opened 5 years ago",
                 "Five years in a row named a best place to work",
                 "Acme has been in logistics for 30 years of steady growth",
                 "Our 15 years of retail know-how shows",
                 "A company with 25 years in roofing",
                 "After 3 years of employment you qualify for extra leave",
                 "Health cover for you after 2 years with the company",
                 "Equity vests over 4 years of service",
                 "Must be at least 18 years old",
                 "Must be 21 years of age or older",
                 "Four years of college or equivalent",
                 "Retain 7 years of records",
                 "A 5 years warranty on every part"):
        check(f"{line!r} -> no floor", _any_floor(line), None)
    # A number that counts something other than experience, stated with a cue that would read it as a bar.
    not_bars = ("Must have a 4 year degree",
                "You will care for 3 year olds and 4 year olds",
                "Must have completed a 4 year apprenticeship",
                "Must pass a background check covering 7 years of address history",
                "Must have 3 years of high school math",
                "Must make a 2 year teaching commitment",
                "Must make 2 year teaching commitment",
                "You must hold a 4 year nursing degree",
                "Must have an 8 year welding apprenticeship behind you",
                "Must have finished a four year accounting program",
                "Must have 4 year degree in logistics",
                "Must finish 2 years of residency",
                "You need a clean record: 5 years clean driving",
                "Must provide 10+ years of address history",
                "Must show 5-7 years of credit history",
                "Must have completed 3 years of high school science",
                "You must sign a three year service commitment")
    for line in not_bars:
        check(f"{line!r} -> no floor", _any_floor(line), None)
    # The same words where they do name the work, or the number is the bar.
    for line, want in (("Must provide 10 years of employment history", 10),
                       ("Must provide 7 years of work history", 7),
                       ("Must provide at least 10 years of employment history", 10),
                       ("Must list ten years of employment history", 10),
                       ("Must have 5 years program management", 5),
                       ("Must have 6 years high school teaching", 6),
                       ("Must have 5 years high volume retail", 5),
                       ("Must have 5 years employment law practice", 5),
                       ("Must have 4 years of art history teaching", 4),
                       ("Must have 5 years of work experience", 5),
                       ("Must have 5 year experience in sales", 5),
                       ("Must have a 5 year experience in nursing", 5),
                       ("Must have 3 years driving a forklift", 3),
                       ("Must have 3 years in the classroom", 3),
                       ("Must have 3 years' classroom experience", 3),
                       ("Must have 4 years of commercial driving with a clean record", 4)):
        check(f"{line!r} -> floor {want}", _any_floor(line), want)
    # Through the verdict, at three years configured: the lines above must not drop anyone.
    global DROP_FLOOR
    saved = DROP_FLOOR
    DROP_FLOOR = 4
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-teacher"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Teacher\n")
            for line in not_bars[:7]:
                (d / "jd-acme.md").write_text(line + "\n")
                check(f"three years configured, {line!r} -> PASS", verdict_for(d)[0], "PASS")
            (d / "jd-acme.md").write_text("Must have 5 years program management\n")
            check("three years configured, a loose 5-year mention -> REVIEW", verdict_for(d)[0], "REVIEW")
            (d / "jd-acme.md").write_text("Must have 5 years of program management experience\n")
            check("three years configured, a real 5-year bar -> DROP", verdict_for(d)[0], "DROP")
    finally:
        DROP_FLOOR = saved
    # Numbers spelled past twelve.
    fl = lambda t: _any_floor(t)
    for line, want in (("Fifteen years of experience required", 15),
                       ("Thirteen years of welding experience", 13),
                       ("sixteen years of retail experience", 16),
                       ("at least nineteen years of nursing experience", 19),
                       ("twenty years of accounting experience", 20),
                       ("Twenty-five years of trucking experience", 25),
                       ("Twenty five years of classroom teaching experience", 25),
                       ("Twenty-five (25) years of audit experience", 25),
                       ("thirty years of sales experience", 30),
                       ("eighteen+ years in logistics", 18)):
        check(f"{line!r} -> floor {want}", fl(line), want)
    check("'twelve to fifteen years of welding experience' -> 12-15",
          (fl("twelve to fifteen years of welding experience"),
           analyze_jd("Requirements\ntwelve to fifteen years of welding experience")["ceiling"]), (12, 15))
    check("'sixteen to twenty yrs of trucking experience' -> 16-20",
          (fl("sixteen to twenty yrs of trucking experience"),
           analyze_jd("Requirements\nsixteen to twenty yrs of trucking experience")["ceiling"]), (16, 20))
    check("'Must be eighteen years old' -> no floor", fl("Must be eighteen years old"), None)
    check("'twenty years of service' (benefit) -> no floor", fl("A gold watch after twenty years of service"), None)
    _selftest_broken_config(check)


def _selftest_evidence(check) -> None:
    """Strong, weak or nothing, in many fields. A DROP holds the job until you say skip it, so each kind of
    sentence is checked twice: how it is graded, and what it does to a dossier."""
    global DROP_FLOOR, APPS
    strong = (("Must have 8+ years of nursing experience", 8), ("9 years of accounting experience required", 9),
              ("At least seven years of classroom teaching experience", 7),
              ("Must have 9 yrs. experience", 9), ("Thirty-five years of trucking experience required", 35),
              ("Nine (9) years' experience in audit required", 9), ("Must have 5 year experience in sales", 5))
    # An experience reading with nothing asking for it: weak alone, strong as an item under Requirements.
    listed = (("8+ years of nursing experience", 8), ("9 years of accounting experience", 9),
              ("Seven years of classroom teaching experience", 7), ("9 yrs experience", 9), ("9 yrs. experience", 9), ("9 yr experience", 9),
              ("Thirty-five years of trucking experience", 35),
              ("Nine (9) years' experience in audit", 9))
    weak = (("Minimum 6+ years of warehouse and forklift experience", 6),
            ("Required: 7 years of retail, grocery, or warehouse experience", 7),
            ("You must have 10 years of inside sales expertise", 10), ("You have 8 years background in logistics", 8),
            ("Experience required: 7 years", 7), ("Minimum Years of Experience: 9", 9),
            ("Nursing: 7 years (Required)", 7), ("Forklift: 6 years (Required)", 6),
            ("10 years of inside sales expertise", 10), ("8 years background in logistics", 8),
            ("Experience: 7 years", 7), ("Experience: 7+ years", 7), ("Years of Experience: 9", 9),
            ("Years of Experience: 6-8", 6), ("**Years of Experience:** 9", 9), ("Experience of 8 years", 8),
            ("10 years of employment history", 10), ("Up to 5 years of experience", 5),
            ("Less than 10 years of experience", 10), ("No more than 4 years of retail experience", 4),
            ("Must have 9 years of commercial driving", 9), ("9 years of commercial driving", 9),
            ("6 years in the classroom", 6), ("5 years acute care", 5), ("Must have held a license for 6 years", 6),
            ("held a license for 6 years", 6), ("A 7 year track record in sales", 7), ("Ten-plus years in banking", 10),
            ("Must have 6 years on the tools", 6), ("8+ yrs of software engineering", 8), ("Nursing: 7 years", 7),
            ("at least 8 yrs leading teams", 8), ("6 years teaching high school math", 6),
            ("Must have 5 years program management", 5), ("Must have 5 years.", 5),
            ("You have 8 years on a surgical floor", 8), ("You bring 8 years in public accounting", 8),
            ("You must have 6 years as a journeyman plumber", 6),
            ("Candidates must have 9 years of commercial driving", 9), ("Applicants should have 7 years in retail", 7),
            ("The ideal candidate has 8 years in retail", 8), ("Seeking a welder with 9 years on pipe", 9),
            ("We have openings for nurses with 8+ years of experience", 8))
    nothing = ("3-5 year olds", "We teach 3-5 year olds", "ages 6 to 12 years", "aged 6-12 years",
               "children ages 3 to 5 years", "at least 18 years old", "Must be 18+ years old",
               "a 4 year degree", "two years of college", "2 years of college required",
               "3 years of high school math", "Must have completed a 5 year apprenticeship", "4 years of apprenticeship",
               "clean 3 year MVR", "clean 5 year driving record", "Must have a clean 5 year driving record",
               "Records must be kept for at least 10 years", "Retain documents for at least 7 years",
               "Warranty of at least 10 years", "7 years of address history",
               "a 2 year teaching commitment", "Must pass a 7 year background check",
               "Teachers with 10 years of experience earn $70,000",
               "Drivers with 5 years of experience can earn up to $90,000",
               "Pay: $25 per hour with 3 years experience",
               "The partner has 20 years of experience and will mentor you",
               "Your manager has 15 years of nursing experience",
               "The manager you report to has 15 years of experience",
               "The team you join has 20 years of experience",
               "Over 40 years of experience serving our customers", "Backed by 30+ years of expertise",
               "Backed by over 30 years of expertise", "Led by a team with over 30 years of experience",
               "Our team averages 12 years of experience", "Our nurses have an average of 15 years experience",
               "Our founder brings 25 years of expertise", "10 year anniversary bonus",
               "Over 20 years of combined experience", "Term: 3 years (Required)", "Contract length: 2 years")
    for line, n in strong:
        check(f"strong: {line!r}", _graded(line), ("strong", n))
    for line, n in weak:
        check(f"weak: {line!r}", _graded(line), ("weak", n))
    for line, n in listed:
        check(f"alone, no requirement word: {line!r}", _graded(line), ("weak", n))
        check(f"under Requirements: {line!r}", _graded("Requirements\n- " + line), ("strong", n))
    for line in nothing:
        check(f"nothing: {line!r}", _graded(line), None)

    # Each sentence keeps its own cue: another sentence's "you" does not rescue a company line.
    check("company history then a 'you' sentence -> nothing",
          _graded("Over 40 years of experience serving our customers. You will join a great team."), None)
    check("a real bar after a company sentence -> strong 5",
          _graded("Join our team! 5 years of retail experience required."), ("strong", 5))
    check("a label marked preferred is a REVIEW", _graded("Nursing: 7 years (Preferred)"), ("weak", 7))
    check("an age and a real bar on one line -> a REVIEW of the bar",
          _graded("Ages 3-5 years, 2 years of experience required"), ("weak", 2))
    check("a college teaching bar is not education", _graded("Must have 6 years of college teaching experience"), ("strong", 6))
    check("a training bar is not education", _graded("Must have 5 years of corporate training experience"), ("strong", 5))
    two = analyze_jd("3+ years of retail experience required\n6 years on the tools")
    check("a weak mention above a strong floor keeps both", (two["floor"], two["weak_floor"]), (3, 6))

    import contextlib
    import io
    import tempfile
    saved = (DROP_FLOOR, APPS, globals()["folder_status_map"])
    try:
        DROP_FLOOR = 4
        with tempfile.TemporaryDirectory() as td:
            APPS = Path(td)
            globals()["folder_status_map"] = lambda: {}
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Teacher\n")
            jd = d / "jd-acme.md"
            for line, n in strong:
                if n >= 4:
                    jd.write_text(line + "\n")
                    check(f"three years configured, strong {line!r} -> DROP", verdict_for(d)[:2], ("DROP", n))
            for line, n in weak + listed:
                jd.write_text(line + "\n")
                check(f"three years configured, weak {line!r} -> REVIEW", verdict_for(d)[:2], ("REVIEW", n))
            for line in nothing:
                jd.write_text(line + "\n")
                check(f"three years configured, {line!r} -> PASS", verdict_for(d)[0], "PASS")
            jd.write_text("2 years of retail experience\n6 years in the classroom\n")
            v = verdict_for(d)
            check("a weak mention above a passing floor -> REVIEW, evidence is the weak line",
                  (v[0], v[3][0][4] if v[3] else None), ("REVIEW", "6 years in the classroom"))
            # REVIEW never sets the exit code; only an unhandled DROP does.
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_all(True, False)
            check("a REVIEW is listed, exit 0, 0 unhandled",
                  (rc, "acme-role" in buf.getvalue(), "=> 0 UNHANDLED" in buf.getvalue()), (0, True, True))
            with contextlib.redirect_stdout(io.StringIO()):
                rc_review = run_one(str(d))
                jd.write_text("6 years of retail experience required\n")
                rc_drop = run_one(str(d))
            check("one dossier: REVIEW exits 0, an unhandled DROP exits 1", (rc_review, rc_drop), (0, 1))
    finally:
        DROP_FLOOR, APPS, globals()["folder_status_map"] = saved


# Every shape the requirement reading has to get right, across fields. (sentence, expected grade), where
# a grade is ("strong", n), ("weak", n), ("preferred", n), or None for no floor at all.
_READING_CASES = (
    # the experience readings, each with a requirement word
    ("8+ years of retail experience required", ("strong", 8)),
    ("Experience: 7 years (Required)", ("weak", 7)),
    ("7.5 years of experience required", ("strong", 7.5)),
    ("60 months of experience required", ("weak", 5)),
    ("A minimum of 5 year's experience", ("strong", 5)),
    ("Minimum experience 7 years", ("weak", 7)),
    ("Experience of 8 years is required", ("weak", 8)),
    ("Retail experience of 6 years required", ("weak", 6)),
    ("10 years total experience required", ("weak", 10)),
    # each requirement word
    ("No less than 8 years of bookkeeping experience", ("weak", 8)),
    ("Not fewer than 6 years of welding experience", ("weak", 6)),
    ("At least 9 years of classroom experience", ("strong", 9)),
    ("Candidates must have 7 years of store management experience", ("weak", 7)),
    ("Applicants should have 6 years of audit experience", ("weak", 6)),
    ("You have 8+ years of software engineering experience", ("strong", 8)),
    ("You bring 7 years of logistics experience", ("strong", 7)),
    ("We need 6 years of payroll experience", ("strong", 6)),
    ("This position requires 7 years of paralegal experience", ("weak", 7)),
    # a negation or another person earlier in the sentence does not hide a later bar
    ("We don't require a degree, but you must have 8 years of experience", ("weak", 8)),
    ("You will report to the director, and you must have 8 years of experience", ("weak", 8)),
    ("Experience working with children, 5 years of experience required", ("weak", 5)),
    # licensed or held for a time: no experience word, so a person reads it
    ("Applicants must have been licensed for 7 years", ("weak", 7)),
    ("Must have held a CDL for 6 years", ("weak", 6)),
    # negation
    ("You don't need 5 years of bedside experience to start here", None),
    ("We do not require 8 years of experience", None),
    ("No 6 years of experience required", None),
    ("8 years of experience is not required", None),
    ("We are not looking for 10 years of experience", None),
    ("You don't need 5 years on the tools to start here", None),
    # ceilings, against the floors that read like them
    ("Up to 3 years of retail experience", ("weak", 3)),
    ("Less than 5 years of experience is fine", ("weak", 5)),
    ("Fewer than 4 years of accounting experience", ("weak", 4)),
    ("5 or fewer years of bookkeeping experience", None),
    ("2 years or less of bookkeeping experience", ("weak", 2)),
    # other people
    ("Surgeons with 20 years of experience run this unit", ("weak", 20)),
    ("You will assist a director with 20 years of experience", ("weak", 20)),
    ("Mentored by a lead with 18 years of experience", ("weak", 18)),
    ("Associates report to a partner with 25 years of experience", ("weak", 25)),
    ("Apprentices work alongside a foreman with 30 years of experience", ("weak", 30)),
    ("Trained under the supervision of a master electrician with 22 years of experience", ("weak", 22)),
    ("Learn from a chef with 15 years of experience", ("weak", 15)),
    ("Shadow a master teacher with 25 years of experience", ("weak", 25)),
    ("Join a crew of 12 with 80 years of combined experience", None),
    ("You will join a team of nurses with 30 years of experience", ("weak", 30)),
    ("Our previous manager had 12 years of experience", ("weak", 12)),
    ("Sam, who brings 20 years of experience, will train you", ("weak", 20)),
    ("Must be able to work alongside surgeons with 20 years of experience", ("weak", 20)),
    ("Must work under the supervision of a director with at least 20 years of experience", ("weak", 20)),
    # pay and benefits
    ("Salary schedule: BA + 10 years = $58,000", None),
    ("Step 10 teachers with 10 years of experience", None),
    ("Teachers with 20 years of experience are eligible for a sabbatical", None),
    ("Nurses with 10 years of experience receive an extra week of vacation", None),
    ("Shift differential for nurses with 8 years of experience", None),
    ("Employees with 5 years of experience get additional vacation", None),
    # any-level, company, residence, remaining time, recruiting others
    ("Whether you have 1 year or 20 years of retail experience, we want to meet you", ("weak", 1)),
    ("Acme has been in roofing for 40 years", None),
    ("Must have resided in the state for 5 years", None),
    ("Must have 5 years left on your license", ("weak", 5)),
    ("You'll have 4 years of job security", None),
    ("You will recruit candidates with 10+ years of experience", ("weak", 10)),
    ("You will interview engineers with 10+ years of experience", ("weak", 10)),
    # an alternative to a degree nobody has said you hold: a person reads it
    ("Bachelor's degree or 4 years of equivalent experience", ("weak", 4)),
    ("Must have a bachelor's degree or 8 years of equivalent experience", ("weak", 8)),
    ("8 years of experience may substitute for a bachelor's degree", ("weak", 8)),
    ("Must have 8 years of experience in lieu of a degree", ("weak", 8)),
    # nursing
    ("RN with at least 6 years of ICU experience", ("weak", 6)),
    ("Must have 7 years of med-surg nursing experience", ("strong", 7)),
    ("Our charge nurses average 15 years of experience", None),
    ("6 years of bedside experience helpful", ("weak", 6)),
    # teaching
    ("Must have 5 years of classroom experience", ("strong", 5)),
    ("Minimum of 3 years of special education teaching experience", ("strong", 3)),
    ("Teachers with 12 years of experience start at $70,000", None),
    ("Ten years of teaching is what most of our staff bring", None),
    # trades
    ("Journeyman license and 6 years of electrical experience required", ("weak", 6)),
    ("6 years on the tools", ("weak", 6)),
    ("Must have been a licensed plumber for 7 years", ("weak", 7)),
    ("Must have led a team of 10 with 5 years of management experience", ("weak", 5)),
    # logistics
    ("Drivers must have 3 years of over-the-road experience", ("weak", 3)),
    ("Drivers need 3 years of over-the-road experience", ("weak", 3)),
    ("3 years of forklift experience", ("weak", 3)),
    ("A 36 month warranty on every truck", None),
    # retail
    ("Store managers with 5+ years of experience earn a bonus", None),
    ("We are hiring a supervisor with 5 years of retail experience", ("weak", 5)),
    ("We need a director with 12 years of retail experience", ("weak", 12)),
    ("Retail experience of 6 years", ("weak", 6)),
    # law
    ("Must have 6 years of litigation experience", ("strong", 6)),
    ("At least 4 years of law firm experience", ("strong", 4)),
    ("You will source laterals with 8 years of experience", ("weak", 8)),
    ("Paralegals with 9 years of experience work with our partners", None),
    # accounting
    ("Minimum 5 years of public accounting experience", ("weak", 5)),
    ("5 years of public accounting experience", ("weak", 5)),
    ("Preferred: 8 years of tax experience", ("weak", 8)),
    ("Must pass 7 years of credit history review", None),
    # software
    ("No less than 7 years of backend experience", ("weak", 7)),
    ("We are recruiting engineers with 8+ years of experience", ("weak", 8)),
    ("Engineers with 8+ years of experience are required to submit a portfolio", ("weak", 8)),
    ("8 years of experience with required forms", ("weak", 8)),
    ("If you have 8 years of experience, we want to talk", ("weak", 8)),
    ("Do you have 8 years of experience?", ("weak", 8)),
    ("You have access to a mentor with 10 years of experience", ("weak", 10)),
    # a requirement word that is not asking for the applicant's own years
    ("We believe at least 10 years of experience is overrated", ("weak", 10)),
    ("At least 8 years of experience is common on this team", ("weak", 8)),
    ("A preceptor with at least 8 years of experience is assigned to you", ("weak", 8)),
    ("Must have a sponsor with 10 years of experience", ("weak", 10)),
    ("Applicants must provide a reference with 10 years of experience", ("weak", 10)),
    ("You will need a co-signer with 10 years of experience", ("weak", 10)),
    ("Required reading for new staff with 5 years of experience", ("weak", 5)),
    ("Must have a nursing license with 5 years of experience", ("weak", 5)),
    ("Must be a nurse with 8 years of experience", ("weak", 8)),
    ("We require applicants to list 10 years of work experience", ("weak", 10)),
    ("Must disclose 10 years of work experience on the form", ("weak", 10)),
    ("Promotion to Level 3 requires 8 years of experience", ("weak", 8)),
    ("Tenure requires 7 years of teaching experience", ("weak", 7)),
    ("7 years of experience required for senior band", ("weak", 7)),
    ("Your supervisor must have 15 years of experience", ("weak", 15)),
    ("Mentors must have 15 years of experience", ("weak", 15)),
    ("Team members must have 15 years of experience to mentor others", ("weak", 15)),
    ("3 years of experience maximum required", ("weak", 3)),
    ("8 years of nursing experience or less", ("weak", 8)),
    ("You have 20 years of experience behind you at Globex", ("weak", 20)),
    ("You will have 10 years of experience to draw on from our team", ("weak", 10)),
    ("Must have 5 years of experience or a degree", ("weak", 5)),
    ("HS diploma or GED and 8 years of experience required", ("weak", 8)),
    ("Candidates must be prepared to support clients with 15 years of experience", None),
    ("You must have the ability to teach adults with 20 years of experience", ("weak", 20)),
    ("You'll need 7 years of experience", ("weak", 7)),
    ("Sales Experience (5+ years required)", ("weak", 5)),
)

_SECTION_CASES = (
    ("Requirements\n- 8 years of nursing experience", ("strong", 8)),
    ("## Qualifications\n8 years of nursing experience", ("strong", 8)),
    ("**Minimum Qualifications:**\n- 6+ years of warehouse experience", ("strong", 6)),
    ("What you bring\n- 7 years of audit experience", ("strong", 7)),
    ("What you'll need:\n- 7 years of audit experience", ("strong", 7)),
    ("Requirements:\nExperience:\n- 8 years of nursing experience", ("strong", 8)),
    ("Preferred Qualifications\n- 8 years of nursing experience", ("weak", 8)),
    ("Preferred Qualifications\n- Minimum 8 years of nursing experience", ("weak", 8)),
    ("Nice to have\n- 8 years of nursing experience", ("weak", 8)),
    ("Requirements\n- CPR card\n\nBenefits\n- 8 years of nursing experience", ("weak", 8)),
    ("Requirements\n- CPR card\n\n## Responsibilities\n- 8 years of nursing experience", ("weak", 8)),
    ("Requirements\n- Our team has 20 years of experience", None),
    ("Requirements\n- We value 10 years of experience", ("weak", 10)),
    ("Requirements\n- Up to 2 years of retail experience", ("weak", 2)),
    ("Requirements\n- Bachelor's degree or 9 years of equivalent experience", ("weak", 9)),
    ("About Northwind\n30 years of industry experience\n\nRequirements\n- 4 years of retail experience", ("strong", 4)),
)


# WHO must meet the demand. Each was read wrong before the subject and hedge check: a DROP on a line about
# someone else, or nothing at all on a real bar.
_WHO_CASES = (
    ("Unlike other firms that require 10 years of experience, we train you.", ("weak", 10)),
    ("We no longer require 7 years of experience.", ("weak", 7)),
    ("It's not a requirement to have 7 years of experience.", ("weak", 7)),
    ("Screen candidates for at least 7 years of experience", ("weak", 7)),
    ("Subcontractors are required to have 7 years of experience.", None),
    ("This role typically requires a minimum of 7 years of experience, however we waive it for graduates of our program.", ("weak", 7)),
    ("Vendors must have 7 years of experience.", None),
    ("Clients must have 7 years of experience.", None),
    ("Agents you recruit must have 7 years of experience.", ("weak", 7)),
    ("Other roles require 7 years of experience.", ("weak", 7)),
    ("Level II requires 7 years of experience.", ("weak", 7)),
    ("You will gain a minimum of 5 years of experience.", ("weak", 5)),
    ("Nurses on our float pool must have 7 years of experience", ("weak", 7)),
    ("Contractors need at least 6 years of plumbing experience", ("weak", 6)),
    ("Most hospitals require 8 years of charge nurse experience", ("weak", 8)),
    ("Some districts require 7 years of teaching experience", ("weak", 7)),
    ("Formerly a minimum of 9 years of sales experience was required", ("weak", 9)),
    ("Customers need 6 years of trading experience", ("weak", 6)),
    ("Tier 3 requires 7 years of help desk experience", ("weak", 7)),
    ("You will acquire at least 6 years of forklift experience", ("weak", 6)),
    ("Suppliers should have 7 years of lumber experience", None),
    ("Track at least 8 years of experience for each technician", ("weak", 8)),
    ("Accountants normally need 7 years of experience", ("weak", 7)),
    ("Vendors: minimum 7 years of experience", None),
    ("For subcontractors, 7 years of experience required", None),
    ("They need 7 years of experience", ("weak", 7)),
    ("We must have 7 years of experience on every job", ("weak", 7)),
    ("Must have 7 years of nursing experience and other acute care skills", ("weak", 7)),
    ("Applicants usually have at least 7 years of retail experience", None),
    ("Our founder spent 20+ years in education", ("weak", 20)),
    ("Must have 5 years of education", None),
    # Real bars, and still real with the applicant named or left out.
    ("5yrs experience required", ("strong", 5)),
    ("Must have 5yrs experience", ("strong", 5)),
    ("6yrs nursing experience required", ("weak", 6)),
    ("Must have 7yr of plumbing experience", ("strong", 7)),
    ("Mandatory: 6 years retail", ("weak", 6)),
    ("Essential: 5 years in retail", ("weak", 5)),
    ("Essential: 7 years of warehouse experience", ("weak", 7)),
    ("Minimum exp 6 years", ("weak", 6)),
    ("Experience: 5+ years in education", ("weak", 5)),
    ("Qualifications: 5+ years in education", ("weak", 5)),
    ("Requirements: 5+ years in education", ("weak", 5)),
    ("Must have 5+ years in education", ("weak", 5)),
    ("5+ years in education required", ("weak", 5)),
    ("Must have half a decade of retail experience", ("weak", 5)),
    ("Half a decade of nursing experience required", ("weak", 5)),
    ("Must have a decade of retail experience", ("weak", 10)),
    ("A half-decade of retail experience is required", ("weak", 5)),
    ("This decade of nursing experience is required", None),
    ("Applicants must have 7 years of bookkeeping experience", ("weak", 7)),
    ("This position requires 6 years of nursing experience", ("weak", 6)),
    ("We require 8 years of classroom experience", ("strong", 8)),
    ("We need 8 years of classroom experience", ("strong", 8)),
    ("We are looking for at least 7 years of warehouse experience", ("weak", 7)),
    ("The ideal candidate will have a minimum of 6 years of sales experience", ("weak", 6)),
    ("- Minimum of 9 years of welding experience", ("strong", 9)),
    ("You need 7 years of payroll experience", ("weak", 7)),
    ("Your background must include 7 years of underwriting experience", ("weak", 7)),
    ("Bachelor's degree and 7 years of audit experience required", ("weak", 7)),
    ("Experience required: 6 years in logistics", ("weak", 6)),
)


# Lines that must never DROP a job, and the alternatives and shapes that used to be misread.
_NEGATION_CASES = (
    ("Requirements\n- No need for 12+ years of warehouse experience; we train.", None),
    ("Requirements\nThere's no need for 10 years of nursing experience", None),
    ("Requirements\nWithout 8+ years of bookkeeping experience, you can still apply", ("weak", 8)),
    ("Requirements\nEven without 9 years of classroom experience, you are welcome here", ("weak", 9)),
    ("Requirements\nNot requiring 8 years of retail experience", None),
    ("Requirements\nNot asking for 7 years of welding experience", None),
    ("Requirements\nNot necessary: 8+ years of sales experience", ("weak", 8)),
    ("Requirements\nIt's not necessary for you to have 6 years of audit experience", None),
    ("Requirements\nThere is no requirement of 9 years of driving experience", None),
)
# The turn back to the applicant still reads as a bar.
_NEGATION_GUARDS = (
    ("Requirements\nWithout a degree, you must have 8 years of plumbing experience", ("weak", 8)),
    ("Requirements\nNo license required, but 8 years of driving experience required", ("weak", 8)),
    ("Requirements\nYou not only need 8 years of nursing experience", ("weak", 8)),
)
_OR_CASES = (
    ("Requires 5 years of nursing experience or 8 years of home care experience.", ("weak", 5)),
    ("Minimum qualifications: 4 years of experience as a bookkeeper or 8 years of payroll experience", ("weak", 4)),
    ("Four years of crew lead experience, or eight years of general labor experience, required", ("weak", 4)),
    ("Requirements\n8 years of teaching experience or 5 years of college", ("weak", 5)),
)
_OR_GUARDS = (
    ("Requirements\nBachelor's degree and 5 years of audit experience, or 8 years of audit experience", ("weak", 5)),
    ("Must have 5 years of nursing experience and must have 7 years of oncology experience", ("weak", 5)),
)
_OTHER_PARTY_CASES = (
    ("We require our vendors to have at least 10 years of roofing experience", None),
    ("We require all subcontractors to have 8 years of electrical experience", None),
    ("We need our suppliers to have at least 9 years of lumber experience", None),
)
_OTHER_PARTY_GUARDS = (("We require 8 years of electrical experience", ("strong", 8)),)
_SHAPE_CASES = (
    ("Experience: Welding: 7 years (Required)", ("weak", 7)),
    ("Must have worked in a body shop for over a decade.", ("weak", 10)),
    ("You bring a decade of commercial plumbing work.", ("weak", 10)),
    ("two decades of auditing experience", ("weak", 20)),
    ("nearly two decades of auditing experience", ("weak", 19)),
    ("10yrs+ welding", ("weak", 10)),
    ("A decade or more of bookkeeping", ("weak", 10)),
    ("Eight years or more of bookkeeping", ("weak", 8)),
    ("- 9+ years of relevant work history", ("weak", 9)),
    ("Track record of 7+ years in retail sales", ("weak", 7)),
    ("Must have a track record of 8 years in logistics", ("weak", 8)),
)
_SHAPE_GUARDS = (
    ("Terms: Contract: 8 years (Required)", None),
    ("Serving families for two decades.", None),
    ("Globex has served this county for over two decades.", None),
    ("A decade ago we opened a depot.", None),
    ("In a decade we will double our fleet.", None),
    ("A decade-long partnership with Hooli", None),
    ("Must provide 7 years of work history", ("weak", 7)),
    ("Background check covers 7 years of work history", None),
    ("Acme has a proud track record of 40+ years in roofing", None),
    ("Our track record of 40+ years in roofing speaks for itself", None),
)
_REREAD_CASES = (_NEGATION_CASES + _NEGATION_GUARDS + _OR_CASES + _OR_GUARDS + _OTHER_PARTY_CASES + _OTHER_PARTY_GUARDS
                 + _SHAPE_CASES + _SHAPE_GUARDS)


def _selftest_requirement_reading(check) -> None:
    """A DROP needs a positive reading. Every shape, graded, then run through a real dossier verdict."""
    global DROP_FLOOR
    saved = DROP_FLOOR
    import tempfile
    try:
        for text, want in _READING_CASES + _SECTION_CASES + _WHO_CASES + _REREAD_CASES:
            check(f"graded: {text!r}", _graded(text), want)
        DROP_FLOOR = 2  # one year configured, so every floor in the tables is above it
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"
            for text, want in _READING_CASES + _SECTION_CASES + _WHO_CASES + _REREAD_CASES:
                jd.write_text(text + "\n")
                verdict = ("PASS" if want is None else "DROP" if want[0] == "strong" else "REVIEW")
                check(f"verdict at one year: {text!r} -> {verdict}", verdict_for(d)[0], verdict)

    finally:
        DROP_FLOOR = saved


# The owner's allowlist (limit 6). Every line that is not the one plain shape must not DROP.
_ALLOWLIST_DROP = (
    ("8+ years of nursing experience required", 8), ("Requires 10 years of welding experience", 10),
    ("Minimum of eight years of bookkeeping experience", 8), ("You have 9+ years of classroom teaching experience", 9),
)
_ALLOWLIST_REVIEW = (
    ("Applicants who do not have the required 8 years of experience will not be considered", 8),
    ("Degree not required - 8+ years of warehouse experience", 8),
    ("Requires 8 years of experience, or 5 years with a BSN", 5),
    ("Requires 5 years of experience with a degree, or 8 years without", 5),
    ("Must have 8 years of experience (or 5 with a bachelor's degree)", 5),
    ("8 years of experience or an equivalent combination of education and training", 8),
    ("8+ years of contract management experience required", 8),
    ("Must have 8 years of contract law experience", 8),
    ("Experience: Contract drafting: 8 years (Required)", 8),
    ("Residential plumbing: 8 years (Required)", 8),
    ("Business analysis: 8 years (Required)", 8),
    ("Applicants with less than 8 years of experience will not be considered", 8),
    ("Do not apply if you have less than 8 years of experience", 8),
    ("Must have 8+ years of employment history in trucking", 8),
    ("Your resume must show 8+ years of relevant work history", 8),
    ("8 years under your belt as a welder", 8),
)
_ALLOWLIST_NOTHING = (
    "- Clean MVR: 8 years (Required)", "- Accident-free: 8 years (Required)",
    "With two decades of experience serving Ohio, Acme is hiring", "We require 10 years of experience from our vendors",
    "No need for 12+ years of experience; we train.", "4 year degree", "Must be 21 years of age",
    "8 year contract", "Lease term: 8 years",
)


def _selftest_allowlist(check) -> None:
    """DROP only on the one plain shape; everything else tied to work is a REVIEW, never a silent PASS."""
    global DROP_FLOOR
    import tempfile
    saved = DROP_FLOOR
    DROP_FLOOR = 7  # six years configured
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"
            for text, n in _ALLOWLIST_DROP:
                jd.write_text(text + "\n")
                check(f"allowlist, plain shape: {text!r} -> DROP", verdict_for(d)[:2], ("DROP", n))
            for text, n in _ALLOWLIST_REVIEW:
                jd.write_text(text + "\n")
                check(f"allowlist, not the shape: {text!r} -> REVIEW", verdict_for(d)[0], "REVIEW")
                check(f"allowlist, lowest offered: {text!r}", analyze_jd(text)["weak_floor"], n)
            for text in _ALLOWLIST_NOTHING:
                jd.write_text(text + "\n")
                check(f"allowlist, not experience: {text!r} -> PASS", (verdict_for(d)[0], _graded(text)), ("PASS", None))
            # An alternative beside the sentence, or a heading that only prefers it, is never a DROP.
            for text in ("Requires 8 years of welding experience. Equivalent training considered.",
                         "- 8 years of welding experience required\n- Equivalent combination of education considered",
                         "Requirements\n- 8 years of welding experience\nOR\n- 5 years with a trade certificate",
                         "Preferred Qualifications\n- Must have 8 years of welding experience"):
                jd.write_text(text + "\n")
                check(f"an alternative or a preference stops the DROP: {text!r}", verdict_for(d)[0], "REVIEW")
            # A range below the limit never drops, and a limit nobody can reach never drops.
            jd.write_text("Requires 4-8 years of welding experience\n")
            check("a range whose floor is under the limit is no DROP", verdict_for(d)[0], "PASS")
    finally:
        DROP_FLOOR = saved


# The structure of a DROP, at five years configured. Each line here was read wrong before: a DROP on a hedged
# tail, an unknown or preferred heading or a waiver beside it, or silence on a real count of years.
_HEDGED_TAILS = ("8+ years of experience in hospital nursing recommended", "8+ years of experience in hospital nursing encouraged",
                 "8+ years of experience in retail is beneficial", "8+ years of experience in retail would be ideal",
                 "8+ years of experience in accounting is valued", "8+ years of experience in sales a strong advantage")
_UNKNOWN_HEADINGS = ("Good to have", "Assets", "An asset", "Optional", "Helpful", "Ways to stand out", "What we'd love to see",
                     "The ideal candidate", "Preferred Education and Experience", "Experience Preferred",
                     "Preferred Skills and Experience", "Preferred Knowledge, Skills and Abilities", "Bonus:", "Nice to have")
_WAIVED = ("Requirements:\n- 8 years of welding experience\nAlternatively, 5 years with a BS.",
           "Requirements:\n- 8 years of welding experience\nWe will also consider new graduates",
           "Requirements:\n- 8 years of welding experience\nExceptions may be made for strong portfolios",
           "Without a degree:\n- 8 years of welding experience",
           "Requirements:\nWithout a degree:\n- 8 years of welding experience")
_MUST_REVIEW = ("- 8+ years of experience in business development", "8 years of experience in business banking",
                "10 years experience in business analysis", "6+ years of experience running a retail floor during holiday rushes",
                "8+ years data engineering", "8+ years business development", "8+ years operations management",
                "8+ years records management", "8+ years school counseling", "Must have 8+ years market research",
                "Worked for 8 years in retail management", "Has worked for 8 years as a nurse", "Must be an RN with 8 years",
                "Nurse (8 years)", "8 year minimum in nursing", "Store manager with 8 years in retail.",
                "Seeking a store manager with 8 years in grocery.", "We need a store manager with 8 years running teams.",
                "Must have taught high school for 8 years.", "Must have supervised a crew for 8 years.",
                "Must have managed a store for 8 years.", "Must have been a cashier for 8 years.",
                "Must hold a license for 8 years.", "Experience Required: 8+", "Minimum Experience: 8+", "Years required: 8",
                "Yrs exp: 8+", "Requirements\n- 8 years data engineering", "Requirements\n- Forklift, 8 years",
                # years of service asked of the applicant, with no benefit cue
                "Must have 8 years of service as a firefighter.", "Minimum of 8 years of service with a fire department.",
                "Must have completed 8 years of service as a teacher.", "Requirements:\n- 8 years of service as a police officer",
                # a two-cell table row read like its label form
                "| Years of Experience | 8+ |", "| Years of experience | 8 |",
                # applicant lines the other-party rule must leave alone
                "Candidates with 8+ years of experience", "Seeking a team lead who has 8 years of experience.",
                "Mentored by a lead with 18 years of experience.")
_MUST_STAY_NOTHING = ("- Clean MVR: 8 years (Required)", "- Accident-free: 8 years (Required)",
                      "With two decades of experience serving Ohio, Acme is hiring",
                      "We require 10 years of experience from our vendors", "No need for 12+ years of experience; we train.",
                      "4 year degree", "Must be 21 years of age", "Must have resided in the state for 8 years",
                      "Acme has been in business for 40 years", "Founded in 1985, Globex has 40 years of roofing know-how",
                      "Nurses with 10 years of experience earn $48 an hour", "A 10 year warranty on every roof",
                      "Tuition covered for up to 8 years", "Shares vest over 8 years", "Must be at least 21 years old",
                      "Globex has been named a top workplace for 8+ years and ranked by Hooli Weekly",
                      "Sam Lee started out as an apprentice and has been wiring homes for 9+ years.",
                      "Named best employer in the county 8 years running", "Records must be stored for 10 years",
                      # a benefit after N years of service or employment is tenure, not a bar
                      "Pension after 10 years of service.",
                      "Employees receive an extra week of leave after 5 years of service.",
                      "Eligible for Public Service Loan Forgiveness after 10 years of qualifying employment.",
                      "Retirement plan with employer match after 5 years of employment.",
                      # someone the applicant reports to or works with
                      "Report to a manager with 15 years of experience.",
                      "You'll work with mentors who have 10+ years of experience.",
                      # a table row about something else
                      "| Founded | 1998 |", "| Company age | 25 years |")
_STILL_DROP = (("Requirements\n- 8 years of experience in hospital nursing", 8),
               ("Requires 8 years of experience as a staff nurse", 8),
               ("Requirements\n- 8 years of experience in a related field", 8),
               ("## Qualifications\n9 years of welding experience", 9),
               ("Requirements:\n- CPR card\n- 8 years of nursing experience", 8),
               ("You have 8 years of experience", 8),
               # a range drops on its floor, with either separator
               ("Requires 6-8 years of experience.", 6), ("Requires 8 to 10 years of experience.", 8))


def _selftest_structure(check) -> None:
    """DROP stays exact; requirement context is positive; silence needs a reason from the short list."""
    global DROP_FLOOR
    import tempfile
    saved = DROP_FLOOR
    DROP_FLOOR = 6  # five years configured
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"

            def verdict(text):
                jd.write_text(text + "\n")
                return verdict_for(d)[0]
            for line in _HEDGED_TAILS:
                for text in ("Requirements\n- " + line.lstrip("- "), "Requires " + line.lstrip("- ")):
                    check(f"a hedge after 'experience' is no DROP: {text!r}", verdict(text), "REVIEW")
            for heading in _UNKNOWN_HEADINGS:
                text = f"Requirements:\n- 3 years of experience\n{heading}\n- 8 years of experience"
                check(f"an unknown or preferred heading ends requirements: {heading!r}", verdict(text), "REVIEW")
            for text in _WAIVED:
                check(f"a waiver near the line stops the DROP: {text!r}", verdict(text), "REVIEW")
            for text in _MUST_REVIEW:
                check(f"a real count of years is at least REVIEW: {text!r}", verdict(text), "REVIEW")
            for text in _MUST_STAY_NOTHING:
                check(f"a short-list count stays no floor: {text!r}", (verdict(text), _graded(text)), ("PASS", None))
            for text, n in _STILL_DROP:
                jd.write_text(text + "\n")
                check(f"the plain shape still drops: {text!r}", verdict_for(d)[:2], ("DROP", n))
    finally:
        DROP_FLOOR = saved


# Each was read wrong before: a bullet sub-heading that did not end Requirements, an age, company history, and an
# invitation to apply with less experience. Five years configured.
_BULLET_LABELS = ("- Good to have:", "- Plus if you have:", "- What sets you apart:", "- Would love to see:",
                  "* Ways to stand out", "- **Good to have**", "  - Good to have:", "- Proficient with the following:")
_BULLET_KEEPS = ("- Must have:", "- Required:", "- 8+ years in one of:", "- Education:")
_AGE_LINES = ("Must be 18 years or older.", "18 years or older", "Must be over 18 years.",
              "Must be 21 years or older to drive company vehicles", "Applicants must be at least 18 years or over.")
_COMPANY_HISTORY = ("Serving the community for 25 years.", "Proudly serving Ohio for 30 years.",
                    "Acme has been a trusted name in HVAC for 20+ years.", "Our company has been around for 30 years.",
                    "We have been in business for 30 years.")
# Round 11: three round 10 silence shapes hid work bars. An age needs an age cue and no work word; "Serving"
# is company history only for a place or a community.
_ROUND11_WORK = ("Requirements\n- Experience: 8 years or above", "Minimum 8 years or above in accounts payable.",
                 "Requirements\n- Nursing experience must be at least 8 years.",
                 "Total experience should be at least 8 years.",
                 "Requirements\n- Serving customers for 8+ years in a high-volume restaurant",
                 "Requirements\n- Serving in a supervisory role for 8+ years",
                 "Requirements\n- Serving Medicare patients for 8 years",
                 "Minimum 18 years or above in retail sales")
_ROUND11_SILENT = ("Requirements\n- Serving the greater Dayton area for 20 years.", "Must be 18 years or older in Ohio")
_LESS_EXPERIENCE = ("Candidates with less experience are encouraged to apply",
                    "If you have less experience, we still want to hear from you",
                    "Don't meet every requirement? Apply anyway.",
                    "We encourage you to apply even if you don't meet every qualification.")


def _selftest_round10(check) -> None:
    global DROP_FLOOR
    import tempfile
    saved = DROP_FLOOR
    DROP_FLOOR = 6
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"

            def verdict(text):
                jd.write_text(text + "\n")
                return verdict_for(d)[0]
            ap = "- 8+ years of experience in accounts payable"
            check("a real 'Nice to have' heading -> REVIEW",
                  verdict("Requirements\n- 3 years of experience in accounts payable\nNice to have\n" + ap), "REVIEW")
            for label in _BULLET_LABELS:
                check(f"a bullet sub-heading ends Requirements: {label!r}",
                      verdict(f"Requirements\n- 3 years of experience in accounts payable\n{label}\n{ap}"), "REVIEW")
            for label in _BULLET_KEEPS:
                check(f"a requirement bullet keeps Requirements: {label!r}", verdict(f"Requirements\n{label}\n{ap}"), "DROP")
            for line in _AGE_LINES:
                check(f"an age is no floor: {line!r}", (verdict(line), _graded(line)), ("PASS", None))
            check("18 years of experience stays work", verdict("Must have 18 years or more of experience"), "REVIEW")
            check("'Must be 8 years into a career' is still read", verdict("Must be 8 years into a nursing career"), "REVIEW")
            for line in _COMPANY_HISTORY:
                for text in (line, "Requirements\n- " + line):
                    check(f"company history is no floor: {text!r}", (verdict(text), _graded(text)), ("PASS", None))
            for text in ("You have been serving customers for 8 years", "Requirements\n- You have been serving customers for 8 years",
                         "Requirements\n- Serving as a charge nurse for 8 years",
                         "Requirements\n- A nurse who has been a leader on the floor for 8 years"):
                check(f"the applicant's own run stays REVIEW: {text!r}", verdict(text), "REVIEW")
            for text in _ROUND11_WORK:
                check(f"a silence shape never hides a work bar: {text!r}", verdict(text), "REVIEW")
            for text in _ROUND11_SILENT:
                check(f"a place or an age stays no floor: {text!r}", (verdict(text), _graded(text)), ("PASS", None))
            bar = "- 7+ years of experience in acute care nursing"
            check("the bar alone still drops", verdict("Requirements\n" + bar), "DROP")
            for line in ("Requires 7+ years of experience as a registered nurse.",
                         "Requires 7+ years of experience as a chartered surveyor."):
                check(f"a field -ed word is not a hedge: {line!r}", verdict(line), "DROP")
            check("a licence word stays REVIEW (a possible other path)",
                  verdict("Requires 7+ years of experience as a licensed electrician."), "REVIEW")
            check("a hedge -ed word still keeps it REVIEW",
                  verdict("Requires 7+ years of experience, preferred."), "REVIEW")
            for cue in _LESS_EXPERIENCE:
                check(f"an invitation with less experience is a waiver: {cue!r}",
                      verdict(f"Requirements\n{bar}\n{cue}"), "REVIEW")
            for cue in ("Applicants who do not meet all requirements need not apply.",
                        "Applicants with less experience should not apply."):
                check(f"no shortfall invited, the bar still drops: {cue!r}", verdict(f"Requirements\n{bar}\n{cue}"), "DROP")
    finally:
        DROP_FLOOR = saved


# Round 11. Under a requirements heading, a line that names years and a work word is silent only in a closed-list
# shape. Each WORK line must be REVIEW or DROP; each CLOSED line is on the list and stays no floor. Five years.
_REQ_WORK_TABLE = (
    "8+ years of experience with the tools we use", "8+ years of experience in the markets we serve",
    "8+ years of experience in industries we support", "8+ years of experience in our industry",
    "8+ years of experience with the EHR we use (Epic)", "Locally based with 8+ years of experience",
    "Electrician has 8+ years of experience", "8+ years of experience (we're strict about this)",
    "Driven professional with 8+ years of sales experience", "Backed by 8+ years of experience in payroll",
    "8+ years of work in a busy kitchen like ours", "8 years working on the platforms we build",
    "8+ years of teaching experience in a district like ours", "Based in Ohio with 8+ years as a welder",
    "8+ years in a role like the one we offer", "8+ years of employment in logistics",
    "8+ years of career progression in accounting", "8+ years of service as a firefighter",
    "8+ years in a supervisory position", "8+ years as a charge nurse on our units",
    "Proven 8+ years of success in retail management", "8+ years of experience serving the clients we support",
    "Has 8+ years of experience as a paralegal", "Brings 8+ years of experience in software testing",
    "The ideal teammate has 8+ years of experience", "Our next store manager has 8+ years of retail experience",
    "Successful candidates typically have 8+ years of experience", "You'll have 8 years of experience as a paralegal",
    "8+ years of hands-on experience; we train on our own systems", "8+ years of experience in the field, which we value",
    "Experienced in the 8+ years of month-end close", "8+ years of experience leading crews like ours",
    "Seasoned with 8+ years of experience in HVAC", "Powered by 8+ years of experience in claims",
    "8+ years of experience with us or a similar firm", "8+ years of experience in each of our core areas",
    "8+ years of experience in the sectors we cover", "8+ years of nursing experience, as our patients need",
    "Store Manager has 8 years of experience", "8 (eight) years of paralegal experience",
    # a pay, benefit or label phrase in another clause of the line never silences the count
    "8+ years of experience; pay starts at $20", "8+ years of experience; $18 to $22 an hour",
    "8+ years of experience; benefits after 90 days", "8+ years of experience. Shift: nights",
    "Experience: 8+ years; Pay: $20/hr", "8+ years of nursing experience; earn $40 an hour",
    "8+ years of bookkeeping experience, eligible for a bonus", "8+ years of retail experience; we pay $20 per hour",
    "8+ years of welding experience, pay rate $30/hr", "Clean record, retail experience: 8 years",
    "8+ years of teaching experience; a $2 raise after 5 years of service",
    "$20/hr, open to candidates with 8+ years of experience in logistics")
_REQ_CLOSED_TABLE = (
    "Must be 18 years or older", "Report to a manager with 15 years of experience",
    "Your mentor has 20 years of experience", "The manager you report to has 15 years of experience",
    "Serving the community for 25 years", "Acme has been a trusted name in HVAC for 20+ years",
    "Clean driving record for the last 7 years", "No years of experience required",
    "Experience is not required; we train you", "Sam Lee has 20 years of experience",
    "Records are kept for 7 years", "401(k) match after 5 years of service",
    # the count is itself the pay, benefit, tenure or label quantity
    "A $2 raise after 5 years of service", "Contract: 2 years", "Pay: $20/hr, rising after 3 years",
    "Eligible for a pension after 10 years of employment", "Age: 18 years",
    "Teachers with 10 years of experience earn $70,000", "Nurses with 8 years of experience receive a $3 differential")


def _selftest_round11(check) -> None:
    global DROP_FLOOR, APPS
    import contextlib
    import io
    import tempfile
    saved = (DROP_FLOOR, APPS)
    DROP_FLOOR = 6
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"

            def verdict(text):
                jd.write_text(text + "\n")
                return verdict_for(d)[0]
            for line in _REQ_WORK_TABLE:
                check(f"under Requirements, years + a work word is never silent: {line!r}",
                      verdict("Requirements\n- " + line) in ("REVIEW", "DROP"), True)
            for line in _REQ_CLOSED_TABLE:
                check(f"under Requirements, a closed-list line stays no floor: {line!r}",
                      verdict("Requirements\n- " + line), "PASS")
            # the applicant under another name, outside a heading too
            for text in ("You'll bring 8 years of experience as a paralegal.", "You'd have 8+ years of experience in retail.",
                         "The ideal teammate has 8+ years of experience.",
                         "Our next store manager has 8+ years of retail experience."):
                check(f"the applicant under another name is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            check("'4 years of job security' is a promise, not a bar", verdict("You'll have 4 years of job security"), "PASS")
            # a count with a bracketed twin reads like "Eight (8) years"
            for text in ("Requirements\n- Requires 8 (eight) years of paralegal experience.",
                         "Requirements\n- 10 (ten) years of experience as an electrician",
                         "Requirements\n- (8) years of experience", "Requirements\n- Eight (8) years of experience"):
                check(f"a bracketed count is read: {text!r}", verdict(text), "DROP")
            bar = "Requirements\n- 8+ years of experience"
            check("a waiver later on the same line keeps it REVIEW",
                  verdict("Requirements\n- 6+ years of experience in retail. Less experience? Apply anyway."), "REVIEW")
            for cue in ("Less experienced candidates are welcome.", "Not quite 8 years? We'd still love to talk.",
                        "We're happy to consider candidates with less experience."):
                check(f"a nearby shortfall, no refusal, is a waiver: {cue!r}", verdict(f"{bar}\n{cue}"), "REVIEW")
            for cue in ("- Mentor less experienced nurses on the unit",
                        "Candidates with less experience will not be considered."):
                check(f"no shortfall waiver, the bar still drops: {cue!r}", verdict(f"{bar}\n{cue}"), "DROP")
            # an invitation to apply opens the door (the open-door rule), so a person reads the bar
            # the open-door rule: school, trade and level wording anywhere in the posting
            for cue in ("Recent graduates are encouraged to apply.", "New grads welcome!",
                        "First-year teachers are welcome to apply.", "Student teaching counts toward experience.",
                        "Trade school counts toward experience.", "Military experience counts.",
                        "## Electrician II requirements\n- 3+ years of electrical experience",
                        "We hire at several levels; Electrician I needs 2 years."):
                check(f"an open door anywhere leaves the bar for a person: {cue!r}",
                      verdict(f"{bar}\n- Valid license\n- CPR\n\nBenefits\n- Health insurance\n\n{cue}"), "REVIEW")
            for cue in ("You don't need to meet every requirement to apply.",
                        "If this sounds like you but you're missing a few years, please apply.",
                        "We hire at Nurse 1 through Nurse 3.", "We hire RN II and RN III.",
                        "Nurses with 2 years of experience may qualify for our Nurse Fellowship track."):
                check(f"an open door anywhere leaves the bar for a person: {cue!r}",
                      verdict(f"{bar}\n- Valid license\n- CPR\n\nBenefits\n- Health insurance\n\n{cue}"), "REVIEW")
            check("an invitation to apply leaves the bar for a person",
                  verdict(f"{bar}\nWe encourage you to apply even if you have never worked in a hospital."), "REVIEW")
            # an invitation below the bar waives it anywhere in the posting, not only two lines away
            far = "\n- Valid driver's license\n- CPR certification\n- Able to lift 50 lbs\n\nBenefits\n- Health insurance\n\n"
            for cue in ("We encourage you to apply even if you don't meet every qualification.",
                        "Don't meet 100% of the qualifications? Apply anyway.",
                        "Not sure you meet all the qualifications? Apply!",
                        "We'd love to hear from you even if you have less.",
                        "Candidates need any one of the above."):
                check(f"a far invitation below the bar is a waiver: {cue!r}", verdict(f"{bar}{far}{cue}"), "REVIEW")
                check(f"the same invitation on the next line is a waiver: {cue!r}", verdict(f"{bar}\n{cue}"), "REVIEW")
            for cue in ("Candidates who don't meet 100% of the qualifications should not apply.",):
                check(f"a far line that is no invitation leaves the DROP: {cue!r}", verdict(f"{bar}{far}{cue}"), "DROP")
            # a party that is hiring the applicant does not own the count
            for text in ("Our client, a regional hospital, requires 6+ years of experience.",
                         "Our client, a CPA firm, requires 6 years of audit experience.",
                         "Our client, a regional hospital, is seeking an RN with 6+ years of experience.",
                         "Students will benefit from a teacher with 6+ years of experience.",
                         "Requirements\n- Our client, a logistics firm, needs a planner with 9 years of experience"):
                check(f"a hiring party's applicant count is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Our clients have 20 years in business.", "Clients: 10 years with us on average"):
                check(f"the party's own count stays silent: {text!r}", verdict(text), "PASS")
            # a label wording no listed shape reads is a REVIEW, never a silent PASS
            for text in ("Experience (years): 9", "| Experience (years) | 9 |", "Years of experience - 9",
                         "Years of experience (minimum): 9", "Experience, years: 9", "Experience (yrs): 9+",
                         "Years of relevant experience - 9", "Requirements\n- Experience (years): 9"):
                check(f"an unlisted label line is read: {text!r}", verdict(text), "REVIEW")
            for text in ("Must be 18 years of age; experience: none", "Shift: 7 am, years of experience helpful"):
                check(f"no bare count beside the label: {text!r}", verdict(text), "PASS")
            for text in ("Requirements\n- Requires 9 years of experience as a guideline.",
                         "Requirements\n- 9 years of experience (flexible)",
                         "Requirements\n- 9 years of experience, negotiable"):
                check(f"a guideline is not a plain bar: {text!r}", verdict(text), "REVIEW")
            # a jd file that still holds only the template's placeholders checked nothing
            jd.write_text("# JD: Company · Role Title\n\n```\nsource: [apply URL]\nfetched: [YYYY-MM-DD]\n```\n\n"
                          "<!--\nEverything below is copied EXACTLY from the real posting.\n-->\n\n"
                          "## Intro (verbatim)\n\n[copy exactly]\n\n## About the Role (verbatim)\n\n"
                          "- [bullet-for-bullet copy of the posting's own responsibilities list]\n")
            check("a placeholder-only jd is NOT CHECKED, never a pass", verdict_for(d)[0], "NO-JD")
            jd.write_text("# JD: Acme · Nurse\n\n## Intro (verbatim)\n\nWe run three clinics.\n")
            check("a jd with posting text is read", verdict_for(d)[0], "PASS")
            # round 14: a list word that names a field after the count, an -ing word with an object, a substitution
            # clause far from the bar
            for text in ("Requirements\n- Must have 9+ years running a store", "Requirements\n- 9+ years running an electrical crew",
                         "Requirements\n- 9+ years hiring and training retail staff",
                         "Requirements\n- 9+ years in operations at a distribution center",
                         "Nine years in criminal investigations", "- 9+ years in credit underwriting",
                         "- 9 years in background screening", "- 9 years in felony prosecution",
                         "Managing vendors: 9 years (Required)", "Supervising subcontractors: 9 years (Required)",
                         "Background investigation: 9 years (Required)"):
                check(f"a field or task after the count is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Named best employer in the county 9 years running", "We have been in operation for 30 years.",
                         "- 10 years clean driving record", "- 7 years with no moving violations",
                         "Requirements\n- No felony convictions in the last 7 years", "Must have completed 2 years in college",
                         "Must have lived in the area for 5 years", "Pension after 10 years in the plan",
                         "Our team has 50 years in the trade", "Background check: 7 years"):
                check(f"a closed-list line stays silent: {text!r}", verdict(text), "PASS")
            for clause in ("Equivalent combinations of education and experience will be considered.",
                           "Substitution: A master's degree may substitute for one year.",
                           "This requirement may be waived for exceptional candidates."):
                check(f"a far substitution clause waives the bar: {clause!r}", verdict(f"{bar}{far}{clause}"), "REVIEW")
            # round 15: a lower level offered elsewhere, or the years called a guideline, leaves the bar for a person
            for cue in ("Junior: 1+ years. Mid: 4+ years. Senior: 8+ years.",
                        "This role can be filled at the Associate level (2+ years) or the Senior level.",
                        "- Internal candidates: 4+ years", "- We're flexible on years for the right person",
                        "The years requirement is a guideline, not a hard rule.",
                        "*Years may be reduced for candidates with relevant certifications."):
                check(f"a lower bar elsewhere waives the DROP: {cue!r}", verdict(f"{bar}{far}{cue}"), "REVIEW")
            for cue in ("- Senior: 10+ years", "Benefits\n- 401k after 1 year"):
                check(f"no lower bar offered, the DROP stands: {cue!r}", verdict(f"{bar}\n{cue}"), "DROP")
            # a word that only stresses the count ("Six full years", "9 total years") is read like the bare count
            for text in ("Requirements\n- Nine full years of paralegal work.", "Requirements\n- 9 full years of experience.",
                         "Requirements\n- Nine total years of paralegal work.", "Requirements\n- Nine consecutive years of paralegal work.",
                         "Requirements\n- Nine additional years of pharmacy practice.",
                         "Requirements\n- Nine continuous years of electrical work.", "Requirements\n- 9 total years of experience required."):
                check(f"a stressed count is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Must be 18 full years of age", "Vesting after 3 full years of service"):
                check(f"a stressed closed-list count stays silent: {text!r}", verdict(text), "PASS")
            # invisible characters and look-alike plus signs from a scraped posting never hide a plain bar
            for text in ("Requirements\n- 9\u200b+ years of experience in payroll.",
                         "Requirements\n- 9+\u200byears of experience in payroll.",
                         "Requirements\n- 9+ ye\u00adars of experience in payroll.",
                         "Requirements\n- 9+ years\u2060 of experience in payroll.",
                         "Requirements\n- 9\uff0b years of experience in payroll.",
                         "Requirements\n- 9\u207a years of experience in payroll.",
                         "Requirements\n- 9\ufe62 years of experience in payroll.",
                         "Requirements\n- 9+\u00a0years of experience in payroll."):
                check(f"hidden characters never hide a bar: {text!r}", verdict(text), "DROP")
            # round 17: the posting says its requirements are not hard, anywhere in it
            for cue in ("These are not hard requirements.", "None of the above are strict requirements.",
                        "The above are guidelines, not hard requirements.", "Requirements are flexible for the right candidate.",
                        "Years of experience are a guide, not a rule.", "no experience minimum",
                        "We value potential over years of experience.", "- No experience required.",
                        "- Experience preferred but not required", "No experience necessary."):
                check(f"a not-hard line waives the DROP: {cue!r}", verdict(f"{bar}{far}{cue}"), "REVIEW")
            for cue in ("No travel required.", "No weekends required."):
                check(f"a line naming no experience requirement waives nothing: {cue!r}", verdict(f"{bar}{far}{cue}"), "DROP")
            for text in ("Requirements\n- A 9-year history of progressive responsibility in accounting",
                         "Requirements\n- Demonstrated 9-year history of successful classroom teaching",
                         "Requirements\n- 9 years of sales history"):
                check(f"a history of the applicant's own work is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Requirements\n- 6+ years of claims history work as an adjuster.",
                         "Requirements\n- 6+ years of credit history analysis in consumer lending.",
                         "Requirements\n- 6+ years of medical history documentation as a scribe."):
                check(f"a record word naming a field is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("With a 50-year history of serving Ohio families, Acme Plumbing is hiring.",
                         "A 75-year history of service to the community.",
                         "Building on a 30-year history of excellence in patient care, Acme Clinic is growing.",
                         "Requirements\n- 6 years of credit history.", "Requirements\n- 7 years of address history required"):
                check(f"company history and a plain record stay silent: {text!r}", verdict(text), "PASS")
            # round 18: under Requirements a past-tense verb with no subject is the applicant's own work
            for text in ("Requirements\n- Driven professionally for 9 years", "Requirements\n- Led crews for 9 years",
                         "Requirements\n- Led classrooms for 9+ years", "Requirements\n- Supported patients for 9+ years",
                         "Requirements\n- Guided tours for 9 years", "Requirements\n- Has driven for 9+ years"):
                check(f"a subjectless past-tense bullet under Requirements is read: {text!r}",
                      verdict(text) in ("REVIEW", "DROP"), True)
            check("a span with no record in it is the applicant's work",
                  verdict("Requirements\n- Employed continuously for the last 9 years") in ("REVIEW", "DROP"), True)
            check("a span over a record stays silent",
                  verdict("Requirements\n- No moving violations in the last 7 years"), "PASS")
            for text in ("Requirements\n- 7 years of rental history", "Requirements\n- 7 years of payment history",
                         "Requirements\n- 7 years of residential address history", "Requirements\n- 7 years of medical history on file",
                         "Requirements\n- 7 years of credit history."):
                check(f"a record's history stays silent: {text!r}", verdict(text), "PASS")
            for text in ("Requirements\n- 7 years of address history", "Acme has a 50-year history of service."):
                check(f"a record or the company's history stays silent: {text!r}", verdict(text), "PASS")
            for text in ("Requirements\n- 9+ years of experience as a dispatcher helps",
                         "Requirements\n- 9+ years of experience in dispatch maybe",
                         "Requirements\n- 9+ years of experience in dispatch matters"):
                check(f"a comment word at the end is not the plain shape: {text!r}", verdict(text), "REVIEW")
            check("a field name at the end is the plain shape",
                  verdict("Requirements\n- 9+ years of experience in family medicine"), "DROP")
            # round 20: the one-voice rule, and a schooling length in brackets
            far20 = "\n- CPA license\n\n## Benefits\n- Health insurance\n- No travel required\n\n"
            for cue in ("Level will be determined based on experience.", "If you are close, apply.",
                        "Lesser experience will be reviewed case by case.", "We hire for potential.",
                        "We are hiring at multiple levels.", "Title and level will depend on experience.",
                        "Not every candidate will have every qualification; tell us what you bring."):
                check(f"another voice on the bar leaves it for a person: {cue!r}", verdict(f"{bar}{far20}{cue}"), "REVIEW")
            check("no other voice on the bar: the DROP stands", verdict(f"{bar}{far20}## About us\nWe have 30 years of "
                                                                     "industry experience serving Ohio."), "DROP")
            check("a schooling length in brackets stays silent", verdict("Requirements\n- Bachelor's degree (4 years)"), "PASS")
            check("a trade bar in hours is read", verdict("Requirements\n- 18,000 hours of documented electrical work"), "REVIEW")
            # round 21: a work label with the count after it, with and without a heading or bullet, across fields
            for line in ("Experience: Nursing (9 years)", "Experience: Bookkeeping, 9 years", "**Experience:** Accounting (9 years)",
                         "Work history: accounting (9 years)", "Skills: QuickBooks (9 years)", "Background: Welding (9 years)",
                         "Experience Level: Mid (9 years)", "Experience: classroom teaching (9 years)"):
                for text in (line, "Requirements\n" + line, "Requirements\n- " + line):
                    check(f"a work label with a count is read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Requirements\n- No DUI in the past 10 years.", "Requirements\n- No at-fault accidents in the last 3 years.",
                         "Requirements\n- No DUI or reckless driving in the last 5 years.",
                         "Requirements\n- No suspensions in the past 5 years."):
                check(f"a driver record stays silent: {text!r}", verdict(text), "PASS")
            check("accident investigation work is read",
                  verdict("Requirements\n- 9 years of accident investigation experience") in ("REVIEW", "DROP"), True)
            # round 22: the last net, any layout, with no requirements heading
            for text in ("Job Details\nJob Type: Full-time | Experience: 9 years", "Job Details\nShift: Nights | Experience: 9 years",
                         "Job Details\nShift: Nights; Experience: 9 years", "Job Details\nShift: Nights · Experience: 9 years",
                         "Job Details\nSalary: $60,000 | Experience: 9 years of accounting",
                         "Job Details\nGrade: 3-5 | Experience: 9 years classroom teaching",
                         "Job Details\nLicensure: RN; Experience: 9 years", "Job Details\nExperience (Nursing): 9 years",
                         "Job Details\nExperience - Nursing (9 years)", "Job Details\n| Experience | Nursing | 9 years |",
                         "Job Details\nExperience: Retail management (9 years); age 18+"):
                check(f"the last net reads any layout: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for tail in ("of school counseling", "of credit underwriting", "of medical record coding", "in our industry",
                         "of college teaching", "of after-hours dispatch", "in age-care nursing"):
                text = f"Job Details\nJob Type: Full-time | Experience: 9 years {tail}"
                check(f"the last net reads a field that shares a closed word: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Job Details\nPay: $20/hr | Raise after 2 years of experience", "We have 30 years of experience.",
                         "Job Details\nMust be 18 years of age | Experience: none", "Background check covering the last 7 years"):
                check(f"the last net leaves the closed list silent: {text!r}", verdict(text), "PASS")
            for text in ("Experience: none needed", "Skills: forklift, Excel", "Requirements: Must be 18 years of age",
                         "Background: no felonies in the last 7 years"):
                check(f"a work label with no count is no floor: {text!r}", verdict(text), "PASS")
            check("hours that are no bar stay silent", verdict("Requirements\n- Able to work 40 hours a week"), "PASS")
            check("the company's proud run stays silent", verdict("We have proudly served the Tulsa community for 40 years."), "PASS")
            # round 23
            for text in ("Requires 9 years of college teaching.", "Requirements\n- 9 years of college teaching",
                         "Must have 9 years of college-level teaching.", "Candidates need 9 years of college coaching.",
                         "Requires 9 years of school bus driving.", "Requires 9 years of university admissions.",
                         "We want someone who has been nursing for 9 years.", "We want someone who has been in accounting for 9 years.",
                         "We want a bookkeeper who has been in the trade for 9 years.", "Nursing: 9 yrs min.",
                         "Welding: 9 years min.", "Retail pharmacy: 9 yrs min"):
                check(f"round 23 shapes are read: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Requirements\n- 9 years of age-appropriate classroom instruction", "Requirements\n- 9 years of age-group coaching",
                         "Requirements\n- Minimum 9 years of age appropriate lesson planning in a preschool",
                         "You have 9 years of age-appropriate teaching.", "Requirements\n- Teaching children ages 3-5: 9 years",
                         "Requirements\n- 9 years of residency program coordination"):
                check(f"an age word beside a work count is no age: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for text in ("Must be 18 years of age", "Camp serves children ages 6 to 12 years", "Must be at least 21 years old"):
                check(f"a real age stays silent: {text!r}", verdict(text), "PASS")
            for text in ("Requirements\n- 9y+ auditing experience", "Requirements\n- 9y+ experience in nursing",
                         "Requirements\n- 9+ y experience", "Requirements\n- experience: 9y", "Requirements\n- Min. 9y experience"):
                check(f"a 'y' count is read as years: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            for cue in ("Nine years is preferred but not required.", "Please note: 9 years is ideal, not required.",
                        "The 9 years are not mandatory.", "Note: the years are ideal, not required."):
                check(f"years called optional leave the bar for a person: {cue!r}",
                      verdict(f"Requirements\n- 9+ years of experience\n{cue}"), "REVIEW")
            for text in ("Requirements\n- 4 years of college", "Requirements\n- 2 years of college coursework",
                         "Must have completed 3 years of high school math", "Maple Grove Elementary, serving our community for 50 years."):
                check(f"schooling and company history stay silent: {text!r}", verdict(text), "PASS")
            for text in ("Requirements\n- 18,000 documented hours of electrical work", "Requirements\n- Completed 18,000 hours of apprenticeship",
                         "Requirements\n- 18000+ hours in the field"):
                check(f"a trade bar in hours, any wording, is read: {text!r}", verdict(text), "REVIEW")
            for text in ("Requirements\n- 9+ YOE", "Requirements\n- 9 YOE in accounting"):
                check(f"YOE is years of experience: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            check("a substitute teacher is a job, not a substitution",
                  verdict("Requirements\n- 9 years of experience as a substitute teacher"), "DROP")
        # no dossier at all: the run checked nothing, so exit 3, never "0 UNHANDLED"
        with tempfile.TemporaryDirectory() as td:
            APPS = Path(td)
            for name in ("TEMPLATE-company-role", "EXAMPLE-fixture"):
                (APPS / name).mkdir()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_all(True, False)
            check("no dossier yet: --all --unsubmitted exits 3 and says so, never '0 UNHANDLED'",
                  (rc, "not checked: no dossier yet" in buf.getvalue(), "UNHANDLED" in buf.getvalue()),
                  (EXIT_NOT_CHECKED, True, False))
    finally:
        DROP_FLOOR, APPS = saved


# Round 12: no line naming applicant years is dropped before _is_work reads it, whatever heading it sits under.
_R12_HEADINGS = (None, "Requirements", "Qualifications", "About the Candidate", "About the Role", "About You",
                 "Your Role", "The Position", "What we're looking for", "About the ideal candidate", "About the Applicant",
                 "About This Position", "About this job", "About the Work", "About the Opportunity", "About the hire",
                 "About the team", "About Acme")
_R12_WORK_LINES = (
    "8+ years of experience as a registered nurse", "7 years total in skilled trades", "Seven years total in nursing",
    "10 years total, 5 in a supervisory role", "8 years of classroom teaching experience",
    "9+ years of public accounting experience", "Minimum 8 years in retail store management",
    "At least 7 years of warehouse operations experience", "8+ years of B2B sales experience",
    "10+ years of software engineering experience", "7+ years as a licensed electrician",
    "8 years of experience driving a forklift", "At least 9 years of payroll experience",
    "12 years total in hospital pharmacy", "Eight years of dispensing experience as a pharmacist",
    "You have 8+ years of experience as a paralegal", "8+ years leading a kitchen brigade",
    "Must have 7 years of welding experience", "7-10 years of HVAC service experience",
    "Requires 8 years of experience in medical billing", "8+ years of experience in supply chain planning",
    "Ten years total as a dental hygienist", "9 years of commercial plumbing experience",
    "7+ years in inside sales", "8+ years of experience as a CPA", "Seven or more years of nursing experience",
    "8 years of experience teaching high school math", "10 years total, three of them as a shift lead",
    "8+ years of front-end development experience", "7+ years of experience in loss prevention")
_R12_HISTORY_LINES = ("Acme has been a trusted name for 20+ years", "We have been in business for 30 years",
                      "Serving the community for 25 years")


def _selftest_round12(check) -> None:
    global DROP_FLOOR
    import tempfile
    saved = DROP_FLOOR
    DROP_FLOOR = 6
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"

            def verdict(text):
                jd.write_text(text + "\n")
                return verdict_for(d)[0]
            missed = []
            for heading in _R12_HEADINGS:
                for line in _R12_WORK_LINES:
                    for form in ("- " + line, line):
                        text = form if heading is None else f"{heading}\n{form}"
                        if verdict(text) == "PASS":
                            missed.append(text.replace("\n", " / "))
            check(f"an applicant work bar is never PASS under any of {len(_R12_HEADINGS)} headings "
                  f"({len(_R12_WORK_LINES)} lines, bullet and plain)", missed, [])
            for heading in ("About Acme", "About us", "Who we are", "Our story"):
                for line in _R12_HISTORY_LINES:
                    check(f"company history under {heading!r} stays no floor: {line!r}",
                          verdict(f"{heading}\n{line}"), "PASS")
            # the old note-skips were for your own notes; a posting's line is always read
            for text in ("Qualifications\n- 7 years total in skilled trades", "Seven years total in nursing",
                         "Requirements\n- 10 years total, 5 in a supervisory role"):
                check(f"'years total' is a bar, never a note: {text!r}", verdict(text) in ("REVIEW", "DROP"), True)
            check("a third party's tenure stays no floor", verdict("Sam Lee has 12 years of experience at two hospitals"), "PASS")
            # "All levels encouraged to apply" invites a shortfall: the bar beside it is for a person to read
            bar = "Requirements\n- 8+ years of experience"
            for cue in ("All levels encouraged to apply.", "All experience levels are welcome to apply."):
                check(f"an all-levels invitation is a waiver: {cue!r}", verdict(f"{bar}\n{cue}"), "REVIEW")
            check("a level named for the team, not the applicant, is no waiver",
                  verdict(f"{bar}\nYou will coach staff at all levels of the store."), "DROP")
    finally:
        DROP_FLOOR = saved


# The backstop (round 12 follow-up): each line pairs one silence-shaped phrase with a separate applicant work count.
# The work count is above the test candidate's 5 years, so the line is never PASS.
_BACKSTOP_LINES = (
    # age
    "Must be 18 years of age with 8 years of experience as an electrician",
    "Applicants must be 21 years of age with 10 years of verifiable truck driving experience",
    "Must be at least 18 years old and have 7 years of retail management experience",
    "Must be 18 years of age, 9 years cooking on a busy line",
    "Must be 21 years or older and have 8 years selling insurance",
    "Must be 18 years old with 7 years as a line cook",
    "Must be 18 years of age with 8 years in the electrical field",
    "Must be 21 years of age and have 9 years in supervisory roles",
    "Students ages 5 to 12 years; 8 years teaching elementary school",
    "Patients 65 years and older; 8 years of geriatric nursing experience",
    # pay
    "Pay rises after 2 years; 8 years of accounting experience",
    "Salary step 3 after 4 years of service; requires 9 years of payroll experience",
    "Retention bonus after 2 years; 8 years serving customers in a restaurant",
    "After 2 years we pay a bonus, and we want 9 years caring for seniors",
    # records and lookbacks
    "No felony convictions in the last 7 years and 8 years of security guard experience",
    "Clean driving record for 5 years, 10 years driving tractor-trailers",
    "A 10-year driving record lookback; 7 years of route delivery experience",
    "Background check covering 7 years with 9 years of background investigation experience",
    "Credit history for 7 years, plus 8 years of loan underwriting experience",
    "Clean record for 3 years and 10 years driving school buses",
    "Credit check covering 7 years with 8 years working as a bank teller",
    "Residency history for 7 years and 9 years of property tax assessment experience",
    # contract, lease, warranty, schooling
    "This is a 2 year contract; 8 years of contract nursing experience required",
    "A 12 month lease term with 6 years of property management experience",
    "3 year commitment, 9 years of software engineering experience",
    "Contract term 2 years, 8 years nursing in an ICU",
    "Warranty work covers 5 years; 9 years of auto repair experience",
    "4 years of college and 7 years of civil engineering experience",
    "A 2 year degree plus 8 years of IT support experience",
    # the company and its history
    "Acme has served the city for 40 years and needs 8 years of plumbing experience",
    "Serving the community for 25 years, we need 7 years of HVAC service experience",
    "Globex has been a trusted name for 30 years; you bring 8 years of sales experience",
    "With 50 years in business, Initech requires 9 years of tax accounting experience",
    "Acme has been around for 60 years; 7 years managing a retail floor",
    # benefits and tenure
    "Pension after 10 years of service and 8 years of firefighting experience",
    "Tuition help after 1 year; 7 years of pharmacy technician experience",
    "Sabbatical after 7 years of employment, 10 years of teaching experience required",
    # another party
    "Our vendors must have 5 years in business; you need 8 years of procurement experience",
    "Report to a manager with 15 years of experience; 7 years of warehouse experience",
    "Sam Lee has 20 years of experience and you bring 8 years of bookkeeping experience",
    "Clients with 10 years of history at Hooli, and 8 years of account management experience",
    # the serving class on its own (no silence phrase needed: the word alone used to silence it)
    "10 years serving customers",
    "12 years serving guests in a full-service restaurant",
    "8 years serving tables in fine dining",
)
# The only count on each line is a closed-list one: these stay PASS.
_BACKSTOP_CONTROLS = (
    "Must be 18 years of age",
    "Applicants must be 21 years or older",
    "No felony convictions in the last 7 years",
    "A 10-year driving record lookback",
    "Clean driving record for the past 5 years",
    "Pension after 10 years of service",
    "Sabbatical after 7 years of employment",
    "This is a 2 year contract",
    "A 3 year teaching commitment",
    "Serving the community for 25 years",
    "Acme has been a trusted name for 30 years",
    "Sam Lee has 20 years of experience at two clinics",
    "Report to a manager with 15 years of experience",
    "A $2 raise after 5 years of service",
    "Requires a 4 year degree in accounting",
    "Our vendors must have 5 years in business",
    "Patients ages 65 years and up",
    "Residency history for 7 years",
    "Globex spent the last ten years stocking shelves across the county",
)


def _selftest_backstop(check) -> None:
    global DROP_FLOOR
    import tempfile
    saved = DROP_FLOOR
    try:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-role"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Associate\n")
            jd = d / "jd-acme.md"

            def verdict(text, limit=5):
                global DROP_FLOOR
                DROP_FLOOR = limit + 1
                jd.write_text(text + "\n")
                return verdict_for(d)[0]
            passed = [f"{h} / {f}" for h in (None, "Requirements") for line in _BACKSTOP_LINES
                      for f in ("- " + line, line) if verdict(f if h is None else f"{h}\n{f}") == "PASS"]
            check(f"backstop: a work count beside a silence phrase is never PASS ({len(_BACKSTOP_LINES)} lines, "
                  "bullet and plain, no heading and under Requirements)", passed, [])
            loud = [f"{h} / {f}" for h in (None, "Requirements") for line in _BACKSTOP_CONTROLS
                    for f in ("- " + line, line) if verdict(f if h is None else f"{h}\n{f}") != "PASS"]
            check(f"backstop: a closed-list count alone stays PASS ({len(_BACKSTOP_CONTROLS)} lines)", loud, [])
            # the defects that opened this round, at the limit each was found at
            for limit, line, want in (
                    (5, "- Must be 18 years of age with 8 years of experience as an electrician", "REVIEW"),
                    (5, "- Applicants must be 21 years of age with 10 years of verifiable truck driving experience", "REVIEW"),
                    (3, "- Must be 21 years of age and have 5 years of experience", "REVIEW"),
                    (5, "- 10 years serving customers", "REVIEW"),
                    (3, "Requires 5 years serving customers in a restaurant.", "REVIEW"),
                    (5, "- 12 years serving guests in a full-service restaurant", "REVIEW"),
                    (3, "- 5 years of background investigation experience", "REVIEW"),
                    (3, "- No felony convictions in the last 7 years", "PASS"),
                    (3, "- a 10-year driving record lookback", "PASS"),
                    (3, "- Must be 18 years of age", "PASS")):
                check(f"backstop defect at limit {limit}: {line!r}", verdict(line, limit), want)
            # the age count itself stays silent: only the work count is shown
            check("backstop: the age count is not a bar, the work count is",
                  [e[0] for e in analyze_jd("- Must be 18 years of age with 8 years of experience as an electrician")["evidence"]],
                  [8])
            # the backstop never makes a DROP of a hedged line, and a plain bar still DROPs
            check("backstop: a hedged work count beside an age is not a DROP",
                  verdict("Requirements\n- Must be 18 years of age, ideally with 8 years of experience"), "REVIEW")
            check("backstop: a plain bar under Requirements still DROPs", verdict("Requirements\n- 8 years of experience"), "DROP")
    finally:
        DROP_FLOOR = saved


def _selftest_no_jd(check) -> None:
    """A dossier with no jd-*.md was never checked: exit 3 and a NOT CHECKED line, never a pass."""
    global DROP_FLOOR, APPS
    import contextlib
    import io
    import tempfile
    saved = (DROP_FLOOR, APPS, globals()["folder_status_map"])
    try:
        DROP_FLOOR = 6
        with tempfile.TemporaryDirectory() as td:
            APPS = Path(td)
            globals()["folder_status_map"] = lambda: {}
            d = Path(td) / "acme-clerk"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Clerk\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc_one = run_one(str(d))
                rc_all = run_all(True, False)
            out = buf.getvalue()
            check("no jd-*.md, one dossier: exit 3, says not checked", (rc_one, "not checked: no jd-*.md" in out), (3, True))
            check("no jd-*.md, --all --unsubmitted: exit 3, listed under NOT CHECKED",
                  (rc_all, "NOT CHECKED" in out and "applications/acme-clerk" in out), (3, True))
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc_drops = run_all(True, True)
            check("no jd-*.md, --drops-only: exit 3, warns on stderr", (rc_drops, "not checked" in err.getvalue()), (3, True))
            (d / "application.md").write_text("## SUBMITTED 2031-03-04\n")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = run_all(True, False)
            check("a submitted dossier with no jd-*.md is not counted by --unsubmitted", rc, 0)
            (d / "application.md").unlink()
            e = Path(td) / "globex-nurse"
            e.mkdir()
            (e / "README.md").write_text("# Globex: Nurse\n")
            (e / "jd-g.md").write_text("Requires 9 years of nursing experience.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = run_all(True, False)
            check("an unhandled DROP outranks NOT CHECKED: exit 1", rc, 1)
            (e / "jd-g.md").write_text("Requires 2 years of nursing experience.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = run_all(True, False)
            check("a PASS beside a no-JD dossier still exits 3", rc, 3)
    finally:
        DROP_FLOOR, APPS, globals()["folder_status_map"] = saved


def _selftest_broken_config(check) -> None:
    """A config.py with a mistake: one plain line naming the file and line, exit 3, no traceback."""
    import shutil
    import subprocess
    import tempfile
    for label, body, line in (("a syntax error", "X = 1\nYOUR_YEARS_OF_EXPERIENCE = = 5\n", "line 2"),
                              ("an error while it runs", "X = 1\n\nY = undefined_name\n", "line 3")):
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td) / "scripts"
            scripts.mkdir()
            (Path(td) / "applications").mkdir()
            shutil.copy(Path(__file__), scripts / "seniority_gate.py")
            (scripts / "config.py").write_text(body, encoding="utf-8")
            r = subprocess.run([sys.executable, str(scripts / "seniority_gate.py"), "--all"],
                               capture_output=True, text=True)
            out = r.stdout + r.stderr
            check(f"broken config.py ({label}): exit 3, names the file and {line}, no traceback",
                  (r.returncode, f"scripts/config.py {line}" in out, "Traceback" in out), (3, True, False))


def _selftest_titles(check) -> None:
    """Senior-plus titles across fields, and the same words on ordinary jobs."""
    for title in ("Lead Engineer", "Lead Software Engineer", "Lead Product Designer", "Tech Lead",
                  "Engineering Team Lead", "Team Lead, Software Engineering", "Design Lead",
                  "Lead Data Analyst", "Software Engineer, Lead", "Principal Engineer",
                  "Principal Consultant", "School Principal", "Director of Nursing",
                  "Director of Operations", "Creative Director", "Head of Finance", "Head of Nursing",
                  "Solutions Architect", "Enterprise Architect", "Acme: Lead Engineer",
                  "Staff Software Engineer", "Staff Engineer", "Lead Data Engineer", "Staff ML Engineer",
                  "Lead Research Scientist", "Lead Graphic Designer", "Lead Site Reliability Engineer",
                  "Staff Backend Developer"):
        check(f"is_senior_title({title!r})", is_senior_title(title), True)
    for title in ("Lead Teacher", "Lead Cashier", "Lead Line Cook", "Lead Carpenter", "Lead Mechanic",
                  "Lead Nurse", "Lead Warehouse Associate", "Lead Generation Specialist",
                  "Lead Paint Inspector", "Shift Lead", "Team Lead", "Team Lead, Retail",
                  "Team Lead, Technician Services", "Data Entry Lead", "Head Cashier", "Head Chef",
                  "Head Teller", "Head of Year", "Head of Housekeeping", "Assistant Principal",
                  "Principal Clerk", "Principal Dancer", "Funeral Director", "Activities Director",
                  "Art Director", "Choir Director", "Landscape Architect", "Project Architect",
                  "Architectural Drafter", "Staff Architect", "Staff Nurse", "Crew Chief", "Chief Cook",
                  "Principal Foods: Claims Examiner", "Director Supply Co: Shelf Stocker",
                  "Lead Maintenance Engineer", "Stationary Engineer Lead", "Lead Sanitation Engineer",
                  "Staff Interior Designer", "Lead Building Engineer", "Lead HVAC Engineer",
                  "Lead Fashion Designer"):
        check(f"is_senior_title({title!r})", is_senior_title(title), False)


def _selftest_handled(check) -> None:
    """Only a real submission or a real drop banner takes a dossier off the list."""
    global DROP_FLOOR, APPS
    import contextlib
    import io
    import tempfile
    # The starter dossier as shipped. If a copy has removed it, the same status line still tests the rule.
    shipped = REPO / "applications" / "TEMPLATE-company-role" / "application.md"
    template = (shipped.read_text(encoding="utf-8", errors="ignore") if shipped.exists()
                else "# Application\n\n**Status: dossier built; form NOT filled, NOT submitted.**\n")
    saved_floor, saved_apps, saved_map = DROP_FLOOR, APPS, globals()["folder_status_map"]
    try:
        with tempfile.TemporaryDirectory() as td:
            APPS, DROP_FLOOR = Path(td), 10
            globals()["folder_status_map"] = lambda: {}
            d = Path(td) / "acme-charge-nurse"
            d.mkdir()
            (d / "README.md").write_text("# Acme: Charge Nurse\n")
            (d / "jd-acme.md").write_text("12+ years of nursing experience required.\n")
            (d / "application.md").write_text(template, encoding="utf-8")
            check("the shipped application.md template is not 'handled'", is_handled(d, {}), False)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_all(True, False)
            check("a 12-year JD on the shipped template is an UNHANDLED drop, exit 1",
                  (rc, "=> 1 UNHANDLED" in buf.getvalue()), (1, True))
            for head, want in (("## SUBMITTED 2031-03-04", True),
                               ("## \u2705 SUBMITTED 2031-03-04 by hand", True),
                               ("**Status: SUBMITTED 2031-03-04**", True),
                               ("**Applied on:** 2031-03-04", True),
                               ("Status: NOT SUBMITTED", False),
                               ("A sibling role was submitted 2031-03-04.", False),
                               ("<!-- ## SUBMITTED 2031-03-04 -->", False),
                               ("\u2705 verify_claims is clean", False)):
                (d / "application.md").write_text(template + "\n" + head + "\n", encoding="utf-8")
                check(f"application.md with {head!r} handled={want}", is_handled(d, {}), want)
            (d / "application.md").write_text(template, encoding="utf-8")
            for banner, want in (("# DROPPED 2031-03-04: seniority gate", True),
                                 ("# DROPPED for seniority", True),
                                 ("> Seniority gate: DROPPED", True),
                                 ("<!-- DROPPED: seniority gate -->", False),
                                 ("# Dropped the ball on seniority", False),
                                 ("Seniority: KEPT 2031-03-04 (you said fill it)", True),
                                 ("- **Seniority:** KEPT 2031-03-04", True),
                                 ("<!-- Seniority: KEPT 2031-03-04 -->", False),
                                 ("We kept the seniority notes here.", False)):
                (d / "README.md").write_text(banner + "\n\nnotes\n")
                check(f"README banner {banner!r} handled={want}", is_handled(d, {}), want)
    finally:
        DROP_FLOOR, APPS = saved_floor, saved_apps
        globals()["folder_status_map"] = saved_map


def selftest() -> int:
    print("seniority_gate.py selftest\n")
    ok = True

    def check(desc, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        mark = "✓" if good else "✗"
        print(f"  {mark} {desc}: got {got!r} want {want!r}")

    # A JD stating an explicit high floor -- this is why the gate exists.
    senior_jd = "- 6+ years of clinical laboratory experience"
    a = analyze_jd("Requirements\n" + senior_jd)
    check("'6+ years of clinical laboratory experience' -> floor 6", a["floor"], 6)

    # A role the fictional candidate genuinely fits -- must PASS.
    check("'2+ years of relevant experience' -> floor 2", _any_floor("2+ years of relevant experience"), 2)

    # Cadence line must NOT register as a requirement.
    check("'about four times a year' -> no floor",
          _any_floor("Staff rotate onto the weekend shift about four times a year"), None)

    # A named third person's tenure is someone else's, never the applicant's bar.
    check("'Alex Kim has 12 years of teaching experience at two schools' -> no floor",
          _any_floor("Alex Kim has 12 years of teaching experience at two schools"), None)

    # Requirement variants.
    check("'at least 7 years' -> floor 7", _any_floor("We want at least 7 years of experience"), 7)
    check("'6-9 years' -> floor 6", _any_floor("6-9 years of experience building production systems"), 6)
    check("'10+ years' -> floor 10", _any_floor("10+ years of experience"), 10)
    check("'3+ years' -> floor 3", _any_floor("3+ years of experience in operations"), 3)

    # The abbreviation / 'or more' / spelled forms that a naive `years?`-only regex would miss.
    # A JD writing its bar as "8+ yrs" must still register a floor, never silently pass.
    check("'8+ yrs of relevant experience' -> floor 8 (abbreviation form)",
          _any_floor("8+ yrs of relevant experience"), 8)
    check("'6+ yrs software engineering' -> floor 6", _any_floor("6+ yrs software engineering"), 6)
    check("'six or more years of experience' -> floor 6",
          _any_floor("We want six or more years of experience"), 6)
    check("'Minimum 7 yrs of experience' -> floor 7", _any_floor("Minimum 7 yrs of experience"), 7)
    check("'at least 8 yrs leading teams' -> floor 8", _any_floor("at least 8 yrs leading teams"), 8)
    # and the abbreviation still PASSES a role the candidate fits.
    check("'5+ yrs of industry experience' -> floor 5 (candidate fits)", _any_floor("5+ yrs of industry experience"), 5)

    # Real JD shapes the parser once misread, as fictional lines.
    check("benefits line 'a sabbatical after seven years of service' -> no floor",
          _any_floor("Long-serving warehouse staff can take a paid month away after seven years of service."), None)
    check("'eight years of professional experience' -> floor 8",
          _any_floor("eight years of professional experience"), 8)
    check("'at least seven years in hospital pharmacy' -> floor 7",
          _any_floor("You have at least seven years in hospital pharmacy"), 7)
    check("'seven+ years' -> floor 7", _any_floor("seven+ years running a print shop"), 7)
    check("'six years building custom cabinets' -> floor 6", _any_floor("six years building custom cabinets"), 6)
    check("'Globex spent the last ten years stocking shelves' -> no floor (company history)",
          _any_floor("Globex spent the last ten years stocking shelves across the county"), None)
    check("'the past 10 years expanding our clinics' -> no floor",
          _any_floor("We have spent the past 10 years expanding our clinic network"), None)
    check("'4-6+ years of front-of-store ownership' -> floor 4, not 6",
          _any_floor("4-6+ years of front-of-store ownership"), 4)
    check("'minimum of 5 years ... OR a minimum of 9 years equivalent' -> floor 5",
          _any_floor("Teaching certificate AND a minimum of 5 years classroom experience "
                     "OR a minimum of 9 years of classroom experience with any mix of schooling"), 5)
    check("'6+ years of experience, 2-3 as a shift supervisor' -> REVIEW, lowest shown",
          _any_floor("6+ years of experience, 2-3 years as a shift supervisor"), 2)
    check("'3 - 7 years of experience' -> floor 3, not 7",
          _any_floor("- **Field time:** 3 - 7 years of relevant experience"), 3)
    check("'~3 to ~7 years of experience' -> floor 3, not 7",
          _any_floor("> Northwind has several openings at ~3 to ~7 years of experience."), 3)
    check("'expects 5-10 years of focus before the line pays off' -> no floor (company horizon)",
          _any_floor("Everyone at the plant expects 5-10 years of focus before the new line pays off."), None)
    check("'roughly a decade of industry experience' -> floor 10",
          _any_floor("You bring roughly a decade of industry experience"), 10)
    check("'nearly a decade managing consumer programs' -> floor 9",
          _any_floor("nearly a decade managing consumer programs"), 9)
    check("'more than a decade of inventory' -> no floor (the company's, not a bar)",
          _any_floor("Initech keeps a well-stocked parts room with more than a decade of inventory behind it"), None)
    check("'the next decade of expansion' -> no floor", _any_floor("Northwind will open depots over the next decade of expansion"), None)
    check("'at least 5 years and at least 7 years in payroll' -> REVIEW, lowest shown",
          _any_floor("at least 5 years of bookkeeping and at least 7 years in payroll"), 5)
    check("'8 years of software engineering' -> floor 8",
          _any_floor("8 years of software engineering in production systems"), 8)

    # Any field, not only software and design: the experience words can be anyone's.
    check("'7 years of nursing experience required.' -> floor 7",
          _any_floor("7 years of nursing experience required."), 7)
    check("'Seven years of accounting experience.' -> floor 7",
          _any_floor("Seven years of accounting experience."), 7)
    check("'a decade of clinical experience' -> floor 10",
          _any_floor("You bring a decade of clinical experience"), 10)
    check("'4+ years of classroom teaching experience' -> floor 4",
          _any_floor("4+ years of classroom teaching experience (grades 6-8)"), 4)
    check("'6 years teaching high school math' -> floor 6",
          _any_floor("6 years teaching high school math"), 6)
    check("'5 years journeyman electrician experience' -> floor 5",
          _any_floor("5 years journeyman electrician experience, licensed in-state"), 5)
    check("'three years of hands-on HVAC experience' -> floor 3",
          _any_floor("three years of hands-on HVAC experience"), 3)
    check("'8 years in retail store management experience' -> floor 8",
          _any_floor("Minimum 8 years retail store management experience"), 8)
    check("a named accountant's tenure -> no floor",
          _any_floor("Sam Lee spent 11 years auditing for Globex before founding the firm"), None)
    check("'the clinic opened 12 years ago' -> no floor",
          _any_floor("The clinic opened 12 years ago and serves the whole county"), None)
    check("'after seven years of service' (benefit, no 'experience') -> no floor",
          _any_floor("Paid sabbatical after seven years of service with the district"), None)

    # The company's own years are not a bar for the candidate.
    check("'Globex has 40 years of manufacturing experience.' -> no floor",
          _any_floor("Globex has 40 years of manufacturing experience."), None)
    check("'Celebrating 25 years of customer experience excellence' -> no floor",
          _any_floor("Celebrating 25 years of customer experience excellence"), None)
    check("'With 30 years of industry experience, Initech is ...' -> no floor",
          _any_floor("With 30 years of industry experience, Initech is the region's most trusted supplier."), None)
    check("'30 years of industry experience' under an About heading -> only the real bar (4)",
          _any_floor("About Northwind\n30 years of industry experience\n\nRequirements\n"
                     "- 4 years of retail experience"), 4)
    check("'Umbrella has served the county for over 20 years of trusted experience' -> no floor",
          _any_floor("Umbrella has served the county for over 20 years of trusted experience"), None)
    # ...but a company voice that still names a bar for the candidate stays a requirement.
    check("'We need 5 years of bookkeeping experience' -> floor 5",
          _any_floor("We need 5 years of bookkeeping experience"), 5)
    check("'Our ideal hire has 6 years of logistics experience' -> floor 6",
          _any_floor("Our ideal hire has 6 years of logistics experience"), 6)
    check("'Join our team: 7 years of warehouse experience required' -> floor 7",
          _any_floor("Join our team: 7 years of warehouse experience required"), 7)
    check("'Join our team! 5 years of retail experience.' -> floor 5 (a bare 'our' is not company voice)",
          _any_floor("Join our team! 5 years of retail experience."), 5)
    check("'We have 35 years of trucking experience behind every load' -> no floor",
          _any_floor("We have 35 years of trucking experience behind every load"), None)
    check("a bare bullet '5 years of nursing experience' with no heading -> floor 5",
          _any_floor("- 5 years of nursing experience"), 5)

    # End-to-end verdicts on synthetic dossiers, with a fixed fictional configuration: the test
    # candidate has 2 years, so DROP_FLOOR is 3 -- independent of whatever a real user's own
    # scripts/config.py says (or doesn't say).
    global DROP_FLOOR
    saved_drop_floor = DROP_FLOOR
    DROP_FLOOR = 3
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-lab-supervisor"
            d.mkdir()
            (d / "README.md").write_text("# Acme Labs: Lab Supervisor\n")
            (d / "jd-acme.md").write_text("Requirements\n" + senior_jd)
            v = verdict_for(d)
            check("senior-shaped dossier -> DROP", v[0], "DROP")

            d2 = Path(td) / "globex-senior-analyst"
            d2.mkdir()
            (d2 / "README.md").write_text("# Globex: Senior Analyst\n")
            (d2 / "jd-globex.md").write_text("2+ years of relevant experience in medical billing")
            check("2+ dossier for a 2-year candidate -> PASS", verdict_for(d2)[0], "PASS")

            d3 = Path(td) / "initech-staff-scientist"
            d3.mkdir()
            (d3 / "README.md").write_text("# Initech: Staff Scientist\n")
            (d3 / "jd-initech.md").write_text("Bring good judgment. Strong track record required.")
            check("Staff Scientist, no years stated -> REVIEW", verdict_for(d3)[0], "REVIEW")
            for title, field in (("Staff Accountant", "accountant"), ("Staff Nurse", "nurse")):
                ds = Path(td) / f"northwind-{field}"
                ds.mkdir()
                (ds / "README.md").write_text(f"# Northwind: {title}\n")
                (ds / "jd-n.md").write_text("Strong track record required.")
                check(f"{title}, no years stated -> PASS (not a senior rung)", verdict_for(ds)[0], "PASS")
            for title, want in (("Staff Software Engineer", True), ("Staff Product Designer", True),
                                ("Staff Developer", True), ("Staff Writer", False), ("Wait Staff", False)):
                check(f"is_senior_title({title!r})", is_senior_title(title), want)

            # End-to-end: a JD that states its bar ONLY as "8+ yrs" must still DROP.
            d4 = Path(td) / "northwind-staff-engineer"
            d4.mkdir()
            (d4 / "README.md").write_text("# Northwind: Staff Engineer\n")
            (d4 / "jd-northwind.md").write_text("You have 8+ yrs of software engineering experience.")
            check("a JD stating its bar only as '8+ yrs' -> DROP (abbreviation form)", verdict_for(d4)[0], "DROP")

            # A "5-8+" range on an "ideally" line must not turn the 8-year ceiling into a silent PASS.
            d5 = Path(td) / "umbrella-charge-nurse"
            d5.mkdir()
            (d5 / "README.md").write_text("# Umbrella: Charge Nurse\n")
            (d5 / "jd-umbrella.md").write_text("- 5-8+ years of bedside nursing on a surgical floor, ideally "
                                              "in a teaching hospital")
            check("'5-8+ years ..., ideally ...' -> REVIEW (senior ceiling)", verdict_for(d5)[0], "REVIEW")
    finally:
        DROP_FLOOR = saved_drop_floor

    # The same nursing JD against several configured years: the bar is the USER's own number.
    saved_drop_floor = DROP_FLOOR
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            dn = Path(td) / "acme-health-charge-nurse"
            dn.mkdir()
            (dn / "README.md").write_text("# Acme Health: Charge Nurse\n")
            (dn / "jd-acme-health.md").write_text("7 years of nursing experience required.\n")
            for yrs, want in ((1, "DROP"), (5, "DROP"), (7, "PASS"), (12, "PASS")):
                DROP_FLOOR = yrs + 1
                check(f"'7 years of nursing experience' with YOUR_YEARS_OF_EXPERIENCE={yrs} -> {want}",
                      verdict_for(dn)[0], want)
    finally:
        DROP_FLOOR = saved_drop_floor

    # Unconfigured mode: with YOUR_YEARS_OF_EXPERIENCE never set, the gate must degrade to a
    # documented no-op rather than crash or guess a number.
    saved_drop_floor = DROP_FLOOR
    DROP_FLOOR = None
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "acme-unconfigured"
            d.mkdir()
            (d / "jd-acme.md").write_text(senior_jd)
            check("unconfigured gate -> UNCONFIGURED, never a crash or a guess", verdict_for(d)[0], "UNCONFIGURED")
            # S12: unset must say plainly it did not check, and must never exit 0 or print a
            # "0 UNHANDLED" line a reader (or a hook) could take as proof.
            import io, contextlib
            buf, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc_all = run_all(True, False)
                rc_one = run_one(str(d))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc_drops = run_all(True, True)
            text = buf.getvalue()
            check("unset: --all --unsubmitted exits 3 (not checked), never 0", rc_all, EXIT_NOT_CHECKED)
            check("unset: a single dossier exits 3 too", rc_one, EXIT_NOT_CHECKED)
            check("unset: --drops-only exits 3 and warns on stderr", (rc_drops, NOT_CHECKED_LINE in err.getvalue()),
                  (EXIT_NOT_CHECKED, True))
            check("unset: output says 'not checked: set YOUR_YEARS_OF_EXPERIENCE'",
                  "not checked: set YOUR_YEARS_OF_EXPERIENCE" in text, True)
            check("unset: output never carries a '=> N UNHANDLED' line",
                  bool(re.search(r"=>\s*\d+\s+UNHANDLED", text)), False)
    finally:
        DROP_FLOOR = saved_drop_floor

    _selftest_parsing(check)
    _selftest_any_field(check)
    _selftest_evidence(check)
    _selftest_requirement_reading(check)
    _selftest_allowlist(check)
    _selftest_structure(check)
    _selftest_round10(check)
    _selftest_round11(check)
    _selftest_round12(check)
    _selftest_backstop(check)
    _selftest_no_jd(check)
    _selftest_titles(check)
    _selftest_handled(check)

    print("\nSELFTEST OK" if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


# runners
EXIT_NOT_CHECKED = 3
NOT_CHECKED_LINE = "seniority_gate: not checked: set YOUR_YEARS_OF_EXPERIENCE in scripts/config.py"


def _warn_unconfigured(stream=None) -> None:
    out = stream or sys.stdout
    print(NOT_CHECKED_LINE, file=out)
    print("  No dossier was compared against a years requirement, so this run proves nothing.", file=out)
    print("  It is NOT a pass and NOT \"0 unhandled\". Add your real number, e.g.", file=out)
    print("  `YOUR_YEARS_OF_EXPERIENCE = 3`, to scripts/config.py and run it again.", file=out)
    print("=> NOT CHECKED (exit 3)", file=out)


def run_all(only_unsubmitted: bool, drops_only: bool) -> int:
    if DROP_FLOOR is None:
        # --drops-only prints folder paths for a script to consume, so the warning goes to stderr.
        _warn_unconfigured(sys.stderr if drops_only else None)
        return EXIT_NOT_CHECKED
    dossiers = [d for d in (sorted(APPS.iterdir()) if APPS.is_dir() else [])
                if d.is_dir() and not is_scaffold_dossier(d.name)]
    if not dossiers:
        # Nothing was compared, so "0 UNHANDLED" would be a claim the run cannot back. TEMPLATE-/EXAMPLE-
        # folders are scaffolding and do not count.
        print("seniority_gate: not checked: no dossier yet", file=sys.stderr if drops_only else sys.stdout)
        if not drops_only:
            print("=> NOT CHECKED (exit 3)")
        return EXIT_NOT_CHECKED
    fmap = folder_status_map()
    rows = []
    for d in dossiers:
        verdict, bar, reason, ev = verdict_for(d)
        if verdict in ("PASS", "UNCONFIGURED"):
            continue
        handled = is_handled(d, fmap)
        if only_unsubmitted and handled:
            continue
        rows.append((d.name, verdict, bar, handled, reason, ev))

    drops = [r for r in rows if r[1] == "DROP"]
    reviews = [r for r in rows if r[1] == "REVIEW"]
    # A dossier with no jd-*.md was never compared, so it is never a pass. An unsubmitted one makes the run exit 3;
    # an unhandled DROP still outranks it with exit 1.
    unchecked = [r for r in rows if r[1] == "NO-JD"]
    open_unchecked = [r for r in unchecked if not r[3]]
    open_drops = [r for r in drops if not r[3]]
    rc = 1 if open_drops else EXIT_NOT_CHECKED if open_unchecked else 0

    if drops_only:
        for name, verdict, bar, handled, reason, ev in drops:
            print(f"applications/{name}")
        if open_unchecked:
            print(f"seniority_gate: not checked: {len(open_unchecked)} unsubmitted dossier(s) have no jd-*.md with the posting's text", file=sys.stderr)
        return rc

    print(f"seniority_gate -- {'actionable (unhandled) only' if only_unsubmitted else 'all dossiers'}\n")
    print(f"\U0001F534 DROP (JD requires {DROP_FLOOR}+ years, you have {DROP_FLOOR - 1}): {len(drops)}")
    for name, verdict, bar, handled, reason, ev in sorted(drops, key=lambda r: (-(r[2] or 0), r[0])):
        tag = "  [already handled]" if handled else ""
        print(f"  {bar}+ yr  applications/{name}{tag}")
        if ev:
            print(f"           └─ {ev[0][4]}")
    print(f"\n\U0001F7E1 REVIEW (surface to you, not auto-dropped): {len(reviews)}")
    for name, verdict, bar, handled, reason, ev in sorted(reviews, key=lambda r: r[0]):
        tag = "  [handled]" if handled else ""
        print(f"  applications/{name}{tag} -- {reason}")

    if unchecked:
        print(f"\n\u26aa NOT CHECKED (no posting text in a jd-*.md, never compared, NOT a pass): {len(unchecked)}")
        for name, verdict, bar, handled, reason, ev in sorted(unchecked, key=lambda r: r[0]):
            tag = "  [handled]" if handled else ""
            print(f"  applications/{name}{tag} -- not checked: {reason}")
    print(f"\n=> {len(open_drops)} UNHANDLED dossier(s) to show you (senior-reach, not yet passed or submitted); "
          f"on your yes mark it passed, on your no add 'Seniority: KEPT <date>' to its README.")
    if open_unchecked:
        print(f"=> NOT CHECKED: {len(open_unchecked)} unsubmitted dossier(s) have no jd-*.md with the posting's text (exit {rc})")
    return rc


def run_one(path: str) -> int:
    d = Path(path)
    if not d.is_absolute():
        d = REPO / path
    if not d.is_dir():
        print(f"not a dossier dir: {path}")
        return 2
    verdict, bar, reason, ev = verdict_for(d)
    if verdict == "UNCONFIGURED":
        _warn_unconfigured()
        return EXIT_NOT_CHECKED
    if verdict == "NO-JD":
        print(f"\u26aa NOT CHECKED  --  {d.name}")
        why = "no jd-*.md in this dossier" if reason.startswith("no jd") else reason
        print(f"   seniority_gate: not checked: {why}. NOT a pass: nothing was compared.")
        print("   Save the posting's full text as jd-<slug>.md, then run the gate again.")
        return EXIT_NOT_CHECKED
    fmap = folder_status_map()
    handled = is_handled(d, fmap)
    icon = {"DROP": "\U0001F534", "REVIEW": "\U0001F7E1", "PASS": "\U0001F7E2", "NO-JD": "⚪"}.get(verdict, "?")
    print(f"{icon} {verdict}  --  {d.name}")
    print(f"   title   : {title_of(d)}")
    print(f"   reason  : {reason}")
    print(f"   handled : {handled} (submitted or already dropped/passed)")
    if ev:
        print("   evidence :")
        for floor, ceil, is_pref, is_weak, line, *_ in ev[:4]:
            print(f"     - [{floor}{'+' if ceil is None else f'-{ceil}'}{' pref' if is_pref else ''}{' weak' if is_weak else ''}] {line}")
    return 1 if verdict == "DROP" and not handled else 0  # a REVIEW is for a person, not a failure


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    if CONFIG_ERROR:
        print(f"seniority_gate: not checked: {CONFIG_ERROR}")
        print("  Fix that line and run this again. NOT a pass: no dossier was compared.")
        sys.exit(EXIT_NOT_CHECKED)
    if "--all" in args:
        sys.exit(run_all("--unsubmitted" in args, "--drops-only" in args))
    positional = [a for a in args if not a.startswith("--")]
    if positional:
        sys.exit(run_one(positional[0]))
    print(__doc__)
    sys.exit(2)
