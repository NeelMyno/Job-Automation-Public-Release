#!/usr/bin/env python3
"""check_law.py: keeps the operating law internally consistent.

WHY THIS EXISTS
---------------
A career-automation repo accumulates instruction files fast: the main entry file, command
definitions, workflow scripts, skill files, knowledge-base notes. A rule stated once and then
restated in two or three more places looks harmless right up until the rule CHANGES. At that
point only the file someone remembered to edit gets updated, and every restatement quietly keeps
teaching the old, wrong version. That is not a hypothetical failure mode for this kind of repo: a
restated visa-answer or policy rule that goes stale for even a few days is a real, load-bearing
risk if an agent follows the copy instead of the current source of truth.

So this file enforces one rule, which is the highest-leverage discipline for any instruction
surface that more than one file reads from:

    A RULE LIVES IN EXACTLY ONE FILE. A RESTATEMENT IS A DEFECT.
    Other files LINK to the owner. They do not repeat its content.

Plus two mechanical integrity checks, because a pointer that does not resolve is worse than a
restatement; it looks correct and teaches nothing:
    * every `§N` / `§N.M` reference resolves to a real CLAUDE.md heading
    * every `ADR-NNNN` reference names an ADR that exists

USAGE
    python3 scripts/check_law.py             # exit 1 on any finding
    python3 scripts/check_law.py --selftest
"""

from __future__ import annotations

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The live instruction surface, DISCOVERED not hand-listed: a hand-typed file list drifts the
# moment a new instruction file is added and nobody remembers to add it to the list. A glob
# cannot drift.
#
# `ops/` is excluded: ADRs and notes are immutable history and legitimately restate a rule as it
# stood on the day they were written. `EXTRA_SURFACES` below is the single, surgical exception:
# for a live (non-immutable) file that should still be held to one named rule.
LAW_GLOBS = [
    "CLAUDE.md", "STRUCTURE.md", "README.md", "docs/DESIGN.md",
    "knowledge-base/*.md",
    ".claude/*.md",               # root-level .claude/ instruction files. `.claude/commands` and
    #                                `.claude/workflows` were globbed but a root-level file like
    #                                `.claude/outreach-handover-format.md` sat outside both, so its
    #                                restatement drift and §/ADR pointers were never machine-checked.
    #                                A glob cannot drift out of date; a hand-typed file list can.
    ".claude/commands/*.md",
    ".claude/rules/*.md",         # path-scoped law files: the application protocol (CLAUDE.md §13
    #                                and §14 text) lives in `.claude/rules/application-protocol.md`
    ".claude/workflows/*.js",
    ".agents/skills/*/SKILL.md",
]

# A file that is NOT part of the general law surface, opened for ONE named rule and nothing else.
# Use this for a file that legitimately needs to summarize a live rule's current value (a status
# index, a dashboard) where scanning the WHOLE file under every OWNED rule would be wrong (most of
# the file is unrelated content), but the one row that states the live value should still be held
# to the rule that owns it.
#   {"path/to/file.md": {"the-owned-rule-id", ...}}
EXTRA_SURFACES: dict[str, set[str]] = {}

# Never scanned, and said out loud rather than left to be inferred.
NOT_CHECKED = [
    ("ops/**", "immutable history legitimately restates the rule of its day"),
    ("applications/**", "a dedicated claim-verification tool, if you have one, owns outbound "
                        "dossiers; sources/ subfolders are verbatim snapshots"),
    ("pipeline/**", "employer-authored JD text, never graded against how YOU must write"),
    ("resume/**, scripts/**", "not instruction surfaces"),
    ("§ / ADR pointer integrity inside any path listed in NO_POINTER_CHECK",
     "a write-up about work done in ANOTHER codebase; those pointers resolve against "
     "that repo's own numbering, not this one's. The restatement rules DO still run there."),
    ("the CONTENT of any rule", "this gate proves a rule lives in ONE place and that its pointers "
                                "resolve. It cannot tell you the rule is right; that is a job for "
                                "whatever gate owns the rule's own subject matter."),
]


def law_files() -> list[str]:
    """Every instruction file on the live surface, resolved from LAW_GLOBS."""
    seen: set[str] = set()
    for g in LAW_GLOBS:
        for p in REPO.glob(g):
            if p.is_file():
                seen.add(str(p.relative_to(REPO)))
    return sorted(seen)

# --------------------------------------------------------------------------------------
# OWNED RULES: each rule, its single owner, and the shape of an illegal restatement.
#
# `restatement` must match a CONCRETE assertion of the rule's content, not a mention of it.
# "read CLAUDE.md §5 for the policy" is a pointer and is fine. "the policy is X" is a restatement
# and drifts. Getting that line right is the whole craft of this file: too loose and it flags
# every legitimate cross-reference, and a checker that cries wolf gets switched off.
#
# Entry schema:
#   {
#       "id":               "short-kebab-id",
#       "owner":            "path/to/the/one/file/that/may/state/this/rule.md",
#       "also_ok":          ["OTHER.md"],       # optional: files allowed to POINT at the rule
#                                                # (never to restate its content; see below)
#       "restatement":      re.compile(r"..."), # a soft restatement of the rule's CONTENT
#       "hard_restatement": re.compile(r"..."), # optional: a hardcoded, unambiguous printing of
#                                                # the rule's answer; NOT exempted by `also_ok`:
#                                                # only the owner may ever print a live answer
#       "hard_why":         "...",              # required if hard_restatement is set
#       "documented_by":    r"DECISION-\d+",    # optional: a reference that means "documenting
#                                                # the change", not "restating the dead rule"
#       "why":              "...",
#       "instead":          "...",
#   }
#
# TO ADD ONE: the moment a rule of yours has drifted (restated in more than one file, or a value
# hardcoded somewhere other than its source of truth), register it here in the same commit as the
# fix. This registry starts EMPTY. It has no opinion about your rules until you give it one.
#
# Worked, non-live example (uncomment and adapt once you have a real rule to register):
#
# _EXAMPLE_OWNED = {
#     "id": "start-date-answer",
#     "owner": "knowledge-base/12-application-answers.md",
#     "also_ok": ["CLAUDE.md"],
#     "restatement": re.compile(r"start\s+date\s+is\s+always\s+\*{0,2}\w", re.I),
#     "why": "The start-date answer changed once already; a copy hardcoded outside its owner "
#            "goes stale the next time it moves.",
#     "instead": "link to knowledge-base/12-application-answers.md and read the answer there",
# }

# The work-authorization question stems a form prints, and a verdict printed right after one.
# Together they catch a HARDCODED answer ("authorized to work now = YES") outside the answer bank.
_WORKAUTH_Q = (
    r"(?:legally\s+authoriz\w*"
    r"|authoriz\w*[\s-]+to[\s-]+work"
    r"|authoriz\w*[\s-]*now"
    r"|requires?[\s-]+sponsorship\w*"
    r"|needs?\s+sponsorship"
    r"|sponsorship\s+(?:to\s+begin|now|at\s+(?:the\s+time\s+of\s+)?hire|for\s+this\s+position)"
    r"|now\s+or\s+in\s+the\s+future"
    r"|at\s+the\s+time\s+of\s+hire)"
)
_VERDICT = r"(?:[=:?|]|->|\u2192|\u2014)\s*[*_`\s]{0,4}(?:YES|NO)\b"

# The files this template itself ships as rule OWNERS. Your own rules go below them. Each owner
# must exist on disk: `run()` reports an owner path that resolves to nothing (`owner-missing`),
# because a rule whose owner moved or was renamed points every reader at nowhere.
OWNED: list[dict] = [
    {
        "id": "work-auth-answers",
        "owner": "knowledge-base/12-application-answers.md",
        # CLAUDE.md and the application protocol POINT at the answer bank and carry the hard-stop
        # framing. They may never PRINT an answer (see hard_restatement).
        "also_ok": ["CLAUDE.md", ".claude/rules/application-protocol.md"],
        "restatement": re.compile(
            r"(?:the\s+)?(?:form\s+)?answers?\s+are\s+\*{0,2}(?:yes|no)\b"
            r"|require\s+sponsorship\s*[,)]?\s*\*{0,2}yes\*{0,2}\s*(?:\)|,|\.|$)",
            re.I),
        # NOT exempted by `also_ok`: only the owner may print an answer. An exemption for the
        # most-read file in the repo is the worst place for a frozen answer to hide, because it
        # gets copied into commands and dossiers before anyone notices the answer bank changed.
        "hard_restatement": re.compile(_WORKAUTH_Q + r"[^\n]{0,120}?" + _VERDICT, re.I),
        "hard_why": "This line does not point at the work-authorization answers, it PRINTS one. "
                    "The honest answer depends on the exact question a form prints (authorized now, "
                    "sponsorship to begin, sponsorship now or in the future), and the answer bank "
                    "maps each wording. A frozen Yes/No elsewhere goes wrong the day the bank changes, "
                    "and a wrong work-authorization answer is a hard-stop category.",
        "why": "Work-authorization answers live in exactly one file, mapped per question wording. "
               "A copy anywhere else drifts the next time the mapping changes.",
        "instead": "link to `knowledge-base/12-application-answers.md` §3 and let the agent read it there",
    },
    {
        "id": "voice-rules",
        "owner": "knowledge-base/17-writing.md",
        "also_ok": [],
        # A restated voice RULEBOOK (a banned-word list, a list of forbidden openers), not a
        # mention of the voice owner. "Write per knowledge-base/17-writing.md" is a pointer.
        "restatement": re.compile(
            r"\b(?:banned|forbidden|never[- ]use)\s+(?:ai[- ]?tell\s+)?(?:words?|phrases?|openers?|closers?)"
            r"\s*(?:list\s*)?[:=]", re.I),
        "why": "How outbound copy and chat replies sound is owned by the writing file. A second "
               "copy of its banned list rots the first time the list changes, and then two files "
               "teach two voices.",
        "instead": "point at `knowledge-base/17-writing.md`",
    },
    {
        "id": "application-protocol",
        "owner": ".claude/rules/application-protocol.md",
        # CLAUDE.md keeps the §13/§14 HEADINGS as an index so every §13.x pointer still lands.
        "also_ok": ["CLAUDE.md"],
        "restatement": re.compile(
            r"never\s+ship\s+a\s+r(?:e|\u00e9)sum(?:e|\u00e9)\s+or\s+cover\s+letter\s+without\s+\w+\s+"
            r"independent\s+review\s+passes"
            r"|the\s+deliverable\s+is\s+the\s+filled\s+form\s*[:.]\s*\w", re.I),
        "why": "The application protocol (the review passes, the dossier, the form-fill law) has "
               "one text. A command that restates it keeps the old version the day the protocol "
               "changes.",
        "instead": "point at `.claude/rules/application-protocol.md` (CLAUDE.md §13/§14 index it)",
    },
    # Your own rules go here. See the schema and worked example above.
]

# `§` is not exclusively ours, and neither is `ADR-NNNN`. Both integrity checks resolve against
# THIS repo: `§N` against a CLAUDE.md heading, `ADR-NNNN` against a file in `ops/decisions/`. Three
# populations of `§` were never pointers into CLAUDE.md at all and must not be reported as dangling:
#
#   * a statute             e.g. citing a real regulation as "22 CFR §120.62"
#   * an external agreement e.g. a platform's own "User Agreement §8.2"
#   * another named document "`SOME-OTHER-DOC.md` §6", "`INTEGRATION.md §4`"
#
# Each resolves (or fails) against its OWN document. Flagging them is the checker being wrong
# about correct content, and this file's own comments already say why that is fatal: "a checker
# that cries wolf gets switched off".
SECTION_REF = re.compile(r"(?<!\d)§\s?(\d{1,2})(?:\.(\d+))?\b")
FOREIGN_DOC_NEAR = re.compile(
    r"(?:\b(?:CFR|U\.?S\.?C|USC|Fed\.?\s*Reg)\b"                       # a statute
    r"|\b(?:User\s+Agreement|UA|ToS|EULA|Terms|Privacy\s+Policy)\b"    # an external agreement
    r"|[\w./-]+\.md`?)"                                                # another named document
    r"[\s`*_,;:)\]'\"]{0,4}$", re.I)
# …but CLAUDE.md naming ITSELF is the normal, correct form ("`CLAUDE.md` §13.2") and must stay checked.
OWN_DOC_NEAR = re.compile(r"CLAUDE\.md`?[\s`*_,;:)\]'\"]{0,4}$", re.I)
ADR_REF = re.compile(r"\bADR-(\d{4})\b")

# A subtree of instruction-adjacent files whose §/ADR references point at ANOTHER codebase's
# numbering, not this repo's, e.g. a project write-up describing work done in a different repo,
# quoting THAT repo's own section numbers or decision-record ids. Running pointer-integrity there
# produces false positives: the number either fails to resolve (correctly, but noisily) against
# the wrong document, or (worse) happens to collide with an unrelated real heading in THIS
# CLAUDE.md and passes for the wrong reason. A check that is right by accident is not a check. The OWNED
# restatement rules still run on every file listed here; only the §/ADR integrity checks skip it.
NO_POINTER_CHECK: tuple[str, ...] = ()


@dataclass
class Finding:
    severity: str
    path: str
    line_no: int
    kind: str
    text: str
    why: str
    instead: str

    def render(self) -> str:
        t = self.text.strip()
        if len(t) > 150:
            t = t[:147] + "..."
        return (f"  [{self.severity}] {self.path}:{self.line_no}  ({self.kind})\n"
                f"      says:    {t}\n"
                f"      why:     {self.why}\n"
                f"      instead: {self.instead}")


def claude_sections() -> set[str]:
    """Every §-addressable heading in CLAUDE.md, as {'0', '0.1', '13', '13.2', ...}."""
    out: set[str] = set()
    p = REPO / "CLAUDE.md"
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^#{2,4}\s+(\d+)(?:\.(\d+))?[.\s]", line)
        if m:
            out.add(m.group(1))
            if m.group(2):
                out.add(f"{m.group(1)}.{m.group(2)}")
    return out


def known_adrs() -> set[str]:
    d = REPO / "ops" / "decisions"
    return {f.name[:4] for f in d.glob("[0-9][0-9][0-9][0-9]-*.md")} if d.is_dir() else set()


def check_file(rel: str, text: str, sections: set[str], adrs: set[str],
               only_rules: set[str] | None = None) -> list[Finding]:
    """`only_rules` restricts a file to a named subset of OWNED and skips the integrity checks.

    It exists for EXTRA_SURFACES: a file opened for one named rule row and nothing else. Its § and
    ADR references are history/context and are not this gate's business.
    """
    out: list[Finding] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        # 1. Restatement of an owned rule, outside its owner.
        for rule in OWNED:
            if only_rules is not None and rule["id"] not in only_rules:
                continue
            if rel == rule["owner"]:
                continue

            # 1a. A HARDCODED answer. No `also_ok` exemption reaches this: only the owner may
            #     print one. See the OWNED schema comment for why that exemption is dangerous.
            hard = rule.get("hard_restatement")
            if hard and hard.search(line):
                # 🔴 NO CITATION ESCAPE, and re-adding one voids the whole rule. A summary that
                # cites its source is still a copy, and a copy is exactly what drifts the moment
                # the owner moves. A citation is not a lookup. ADR discipline says a rule lives
                # in exactly one file; the honest application is that only the owner PRINTS the
                # value and every other file POINTS at it, including files that also name the
                # owner correctly.
                out.append(Finding("HIGH", rel, i + 1, f"hardcodes:{rule['id']}", line,
                                   rule["hard_why"] + f" Owner: {rule['owner']}.",
                                   rule["instead"]))
                continue  # one finding per rule per line; the hard one is the sharper report

            if rel in rule.get("also_ok", []):
                continue
            if rule["restatement"].search(line):
                # A line that names the decision which CHANGED the rule is documenting the
                # change, not asserting the dead version. That distinction is the same
                # assertion-vs-prohibition problem canon.py solves, and getting it wrong here
                # would flag every honest explanation of why a rule moved.
                if rule.get("documented_by") and re.search(rule["documented_by"], line, re.I):
                    continue
                out.append(Finding("HIGH", rel, i + 1, f"restates:{rule['id']}", line,
                                   rule["why"] + f" Owner: {rule['owner']}.", rule["instead"]))

        if only_rules is not None:
            continue  # EXTRA_SURFACES get the named rule and nothing else
        if any(rel.startswith(p) for p in NO_POINTER_CHECK):
            continue  # its §/ADR pointers belong to another repo: see NO_POINTER_CHECK

        # 2. A §-reference that resolves to nothing.
        for m in SECTION_REF.finditer(line):
            ref = m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
            near = line[max(0, m.start() - 20):m.start()]
            if not OWN_DOC_NEAR.search(near) and FOREIGN_DOC_NEAR.search(near):
                continue  # "22 CFR §120.62", "User Agreement §8.2", "`OTHER-DOC.md §4`"
            if sections and ref not in sections:
                out.append(Finding("MEDIUM", rel, i + 1, "dangling-section", line,
                                   f"§{ref} does not resolve to any CLAUDE.md heading. A pointer "
                                   f"that goes nowhere teaches nothing and reads as authoritative.",
                                   "fix the number, or link the file directly"))

        # 3. An ADR reference to a file that does not exist.
        for m in ADR_REF.finditer(line):
            if adrs and m.group(1) not in adrs:
                out.append(Finding("MEDIUM", rel, i + 1, "dangling-adr", line,
                                   f"ADR-{m.group(1)} has no file in ops/decisions/.",
                                   "cite an ADR that exists"))
    return out


def check_ops_numbering() -> list[Finding]:
    """`ops/<sub>/NNNN-slug.md`, one running sequence per subfolder, no number reused.

    Not cosmetic: a duplicate number is a wrong cross-reference waiting to be followed. If two
    files are ever both `0018-*.md` in the same subfolder, a bare pointer like `ops/notes/0018`
    stops naming one thing.
    """
    out: list[Finding] = []
    for sub in ("notes", "decisions", "briefs", "reports"):
        d = REPO / "ops" / sub
        if not d.is_dir():
            continue
        seen: dict[str, str] = {}
        for f in sorted(d.glob("*.md")):
            if f.name in ("INDEX.md", "README.md"):
                continue
            m = re.match(r"^(\d{4})-", f.name)
            if not m:
                out.append(Finding("MEDIUM", f"ops/{sub}/{f.name}", 0, "ops-naming", f.name,
                                   "Files here must be NNNN-slug.md (the global ops/ convention).",
                                   "give it the next free number, or move it if it is not a note"))
                continue
            n = m.group(1)
            if n in seen:
                out.append(Finding("HIGH", f"ops/{sub}/{f.name}", 0, "ops-duplicate-number", f.name,
                                   f"Number {n} is already used by `{seen[n]}`. A bare "
                                   f"`ops/{sub}/{n}` reference becomes ambiguous the moment a "
                                   f"second file claims it.",
                                   "renumber this one to the next free number and update live refs"))
            else:
                seen[n] = f.name
    return out


def run() -> list[Finding]:
    sections, adrs = claude_sections(), known_adrs()
    found: list[Finding] = []
    for rel in law_files():
        p = REPO / rel
        found.extend(check_file(rel, p.read_text(encoding="utf-8", errors="replace"), sections, adrs))
    for rel, rules in EXTRA_SURFACES.items():
        p = REPO / rel
        if not p.is_file():
            continue
        found.extend(check_file(rel, p.read_text(encoding="utf-8", errors="replace"),
                                sections, adrs, only_rules=rules))
    found.extend(check_ops_numbering())
    found.extend(check_owners())
    return found


def check_owners() -> list[Finding]:
    """Every OWNED rule's owner (and every `also_ok` file) must exist on disk.

    A rule whose owner was renamed or never created points every reader at nowhere, and the
    restatement check then has no file it treats as the source of truth.
    """
    out: list[Finding] = []
    for rule in OWNED:
        if not (REPO / rule["owner"]).is_file():
            out.append(Finding("HIGH", rule["owner"], 0, "owner-missing", rule["owner"],
                               f"Rule '{rule['id']}' names this file as its owner, and it does "
                               f"not exist.",
                               "create the owner file, or point the rule at the file that now "
                               "owns it"))
        for ok in rule.get("also_ok", []):
            if not (REPO / ok).is_file():
                out.append(Finding("MEDIUM", ok, 0, "also-ok-missing", ok,
                                   f"Rule '{rule['id']}' lists this file in also_ok, and it does "
                                   f"not exist.", "drop it from also_ok or fix the path"))
    return out


# --------------------------------------------------------------------------------------
# Self-test: the mechanical checks (§ cross-reference integrity, ADR-file-existence integrity,
# ops-numbering collision detection, owner existence) and the template's three OWNED rules.
# Add cases here the day you register a rule of your own.
# --------------------------------------------------------------------------------------

CASES: list[tuple[str, str, str, bool]] = [
    # (label, fake-path, text, should_flag)

    # --- § cross-reference integrity. Deliberately checked against THIS repo's own real, current
    # CLAUDE.md and ops/decisions/ (via `claude_sections()`/`known_adrs()` below) rather than a
    # mocked set: §1 and ADR-0001 are permanent, blessed fixtures this template ships with
    # specifically so its own gate scripts have something stable to test against. Don't delete
    # either (see `ops/decisions/0001-example-starter-decision.md`'s own text). ---
    ("a dangling section reference",
     "CLAUDE.md", "See §99.4 for the details.", True),
    ("a real section reference must not fire",
     "CLAUDE.md", "See §1 for what this repo is.", False),
    ("a dangling ADR reference",
     "CLAUDE.md", "Locked as ADR-9999.", True),
    ("a real ADR reference must not fire (the worked-example ADR this template ships with)",
     "CLAUDE.md", "See ADR-0001 for the shape every decision record follows.", False),

    # --- the populations of § that are NOT pointers into CLAUDE.md at all, and must never fire ---
    ("a statute citation must not fire",
     "knowledge-base/02-work-authorization.md",
     "Even a SOC-2-certified vendor can still violate 22 CFR §120.62.", False),
    ("an external agreement's own § must not fire",
     "knowledge-base/10-tooling-stack.md",
     "Their User Agreement §8.2 forbids automated login.", False),
    ("another named document's own § must not fire",
     "knowledge-base/11-preferences-and-conventions.md",
     "See `STRUCTURE.md` §4 for the naming rule.", False),
    ("but CLAUDE.md naming ITSELF must stay checked: '.md' is not a blanket escape",
     "knowledge-base/11-preferences-and-conventions.md",
     "Amends `CLAUDE.md` §99.4.", True),

    # --- work-auth-answers: only the answer bank may PRINT an answer ---
    ("a command that hardcodes an answer pair fires",
     ".claude/commands/apply.md",
     "The form answers are **YES** (authorized now) / **NO** (will require sponsorship).", True),
    ("a pointer to the answer bank must not fire",
     ".claude/commands/apply.md",
     "The answers belong in the form; `knowledge-base/12-application-answers.md` §3 owns them.", False),
    ("CLAUDE.md printing an answer fires even though it is in also_ok",
     "CLAUDE.md",
     "- Authorized to work in the US? **Yes** \u00b7 Require sponsorship now or in the future? **No**", True),
    ("the application protocol printing an answer fires even though it is in also_ok",
     ".claude/rules/application-protocol.md",
     "`authorized to work now = YES` and `sponsorship to begin = NO`.", True),
    ("pointer AND printed answers on one line still fires (a citation is not a lookup)",
     ".claude/commands/apply.md",
     "`knowledge-base/12-application-answers.md` §3 owns these: authorized-now -> **Yes**.", True),
    ("the answer bank itself may print the answers",
     "knowledge-base/12-application-answers.md",
     '| "Are you legally authorized to work in the United States?" | **YES** |', False),
    ("prose with a bare 'no' near a stem is not an answer pair",
     ".claude/commands/apply.md",
     "> Read the exact question; no sponsorship answer is ever inferred from another one.", False),

    # --- voice-rules: the writing file owns the voice rulebook ---
    ("a command restating a banned-word list fires",
     ".claude/commands/outreach.md",
     "Banned words: leverage, synergy, passionate.", True),
    ("a pointer to the writing file must not fire",
     ".claude/commands/outreach.md",
     "Write the note per `knowledge-base/17-writing.md`, then read it out loud.", False),
    ("the writing file itself may hold the list",
     "knowledge-base/17-writing.md",
     "Banned words: leverage, synergy, passionate.", False),

    # --- application-protocol: the rules file owns §13/§14 text ---
    ("a command restating the review-pass rule fires",
     ".claude/commands/wave.md",
     "Never ship a resume or cover letter without 5 independent review passes.", True),
    ("CLAUDE.md keeping the §13 heading must not fire",
     "CLAUDE.md",
     "### 13.1 Never ship a r\u00e9sum\u00e9 or cover letter without 5 independent review passes", False),
    ("a pointer to the protocol must not fire",
     ".claude/commands/wave.md",
     "Follow `.claude/rules/application-protocol.md` for the review passes.", False),
]


def selftest() -> int:
    # The §/ADR cases above deliberately read THIS repo's own real state (the same call `run()`
    # itself makes) rather than a mocked set. That is safe specifically because §1 and ADR-0001
    # are permanent fixtures this template ships with for exactly this purpose (see the CASES
    # comment above). Don't delete either.
    sections, adrs = claude_sections(), known_adrs()
    passed = failed = 0
    print("check_law.py selftest: the mechanical integrity checks, against fictional file/section names\n")
    for label, rel, text, should in CASES:
        got = bool(check_file(rel, text, sections, adrs))
        ok = got == should
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        mark = ("✓ CAUGHT " if should else "✓ allowed") if ok else \
               ("✗ MISSED " if should else "✗ FALSE-POSITIVE")
        print(f"  {mark}  {label}")
    print()

    # ops-numbering collision detection, exercised against a throwaway fixture tree. This repo's
    # own ops/notes|briefs|reports/ start empty and ops/decisions/ holds exactly one file, so there
    # is nothing to collide with on disk. Proving the check WORKS means handing it a fixture that
    # actually collides. `check_ops_numbering()` reads the module-level REPO, so REPO is swapped to
    # a temp directory for the duration of this one call and restored immediately after; nothing
    # this script ships with is read, written, or at risk.
    global REPO
    saved_repo = REPO
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        notes = tmp_path / "ops" / "notes"
        notes.mkdir(parents=True)
        (notes / "0001-first-fixture.md").write_text("fixture", encoding="utf-8")
        (notes / "0001-duplicate-fixture.md").write_text("fixture", encoding="utf-8")
        (notes / "0002-fine.md").write_text("fixture", encoding="utf-8")
        REPO = tmp_path
        try:
            collisions = check_ops_numbering()
        finally:
            REPO = saved_repo
    ops_ok = len(collisions) == 1 and collisions[0].kind == "ops-duplicate-number"
    passed, failed = (passed + 1, failed) if ops_ok else (passed, failed + 1)
    print(f"  {'✓ CAUGHT ' if ops_ok else '✗ WRONG   '}  ops-numbering: a duplicate NNNN- prefix "
          f"in a fixture ops/notes/ tree is detected exactly once")

    # The `.claude/` ROOT instruction surface must be ON the law surface, not un-gated. A
    # root-level file like `.claude/outreach-handover-format.md` used to sit outside both
    # `.claude/commands/*.md` and `.claude/workflows/*.js`, so its single-owner compliance and
    # §/ADR pointers were never machine-checked. This asserts the glob resolves it into law_files().
    handover = ".claude/outreach-handover-format.md"
    covered = (handover in set(law_files())) if (REPO / handover).is_file() else (".claude/*.md" in LAW_GLOBS)
    passed, failed = (passed + 1, failed) if covered else (passed, failed + 1)
    print(f"  {'✓ covered' if covered else '✗ UN-GATED'}   .claude/ root instruction files are on "
          f"the check_law law surface")
    rules_on = ".claude/rules/*.md" in LAW_GLOBS
    passed, failed = (passed + 1, failed) if rules_on else (passed, failed + 1)
    print(f"  {'✓ covered' if rules_on else '✗ UN-GATED'}   .claude/rules/ law files are on the "
          f"check_law law surface")

    # owner-missing: a fixture tree with one owner present and one absent.
    global OWNED
    saved_owned = OWNED
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "present.md").write_text("owner", encoding="utf-8")
        OWNED = [{"id": "fixture-ok", "owner": "present.md", "restatement": re.compile("x")},
                 {"id": "fixture-gone", "owner": "renamed-away.md", "restatement": re.compile("x")}]
        REPO = tmp_path
        try:
            owners = check_owners()
        finally:
            REPO, OWNED = saved_repo, saved_owned
    own_ok = [f.path for f in owners] == ["renamed-away.md"] and owners[0].kind == "owner-missing"
    passed, failed = (passed + 1, failed) if own_ok else (passed, failed + 1)
    print(f"  {'✓ CAUGHT ' if own_ok else '✗ WRONG   '}  owner-missing: a rule whose owner file is "
          f"gone is reported, and only that one")

    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    found = run()
    files = law_files()
    print(f"check_law.py: {len(files)} law files · {len(claude_sections())} CLAUDE.md sections "
          f"· {len(known_adrs())} ADRs")
    print("  rule: a rule lives in exactly ONE file; other files link to the owner, never restate it")
    print("  checked:     " + " · ".join(LAW_GLOBS))
    for rel, rules in EXTRA_SURFACES.items():
        print(f"               + {rel}  (rule '{', '.join(sorted(rules))}' ONLY)")
    print("  NOT checked. A verdict below does NOT cover any of these:")
    for what, why in NOT_CHECKED:
        print(f"       {what}\n           {why}")
    if not found:
        print("\nCLEAN: no restatement drift, no dangling § or ADR reference.")
        return 0
    print(f"\n{len(found)} FINDING(S):\n")
    for f in sorted(found, key=lambda x: {"HIGH": 0, "MEDIUM": 1}.get(x.severity, 2)):
        print(f.render())
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
