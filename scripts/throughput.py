#!/usr/bin/env python3
"""throughput.py: the gates that guard the GOAL, not the truth.

WHY THIS EXISTS
---------------
The other gates in this repo (canon, visa_gate, check_law, verify_claims) all guard **honesty**,
whether a claim is true. None of them guard the actual **goal**: getting interview calls. A repo
can be perfectly honest and still be losing you applications, in ways a truth-only gate would never
catch:

  * A finished résumé PDF that never actually reached an employer, dossier-building feels like
    progress because it's tractable and ends in a visible artifact; applying is higher-friction and
    easy to defer. A session can produce five dossiers and zero applications and feel productive.
  * The résumé on your live public site silently drifting from the one in this repo, so a
    correction you made here never reaches the copy a recruiter actually downloads.
  * A dossier whose header says NOT APPLIED while its body says SUBMITTED, `/wave` reads the
    header to decide what to work on, so a stale header means real work gets silently re-done or,
    worse, a real application gets silently duplicated.
  * Commits piling up unpushed, work a parallel or future session can't see.

USAGE
    python3 scripts/throughput.py            # exit 1 if anything is losing you applications
    python3 scripts/throughput.py --selftest
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# scripts/config.py is optional (see that file's own docstring); every gate below stays safe by
# default if it has never been created. sys.path is seeded explicitly (not just relying on argv[0]
# placement) so `import config` also resolves if this module is ever imported rather than run
# directly, matching the pattern outreach_queue.py already uses for its own sibling import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import config
except ImportError:
    class config:  # type: ignore[no-redef]
        """Fallback when scripts/config.py has not been created yet: safe defaults only."""
        OPERATOR_NAME = None
        SITE_CHECKOUT_PATH = None
        RECRUITER_PLATFORM_KEYWORDS = []

REPO = Path(__file__).resolve().parents[1]
# The checkout of your published site/portfolio repo, the one a recruiter actually downloads your
# résumé from, if you keep one separate from this repo. Optional: set SITE_CHECKOUT_PATH in
# scripts/config.py to enable the live-site-drift check; left unset (the default), that check is
# silently skipped rather than crashing or guessing at a path (see site_matches_repo() below).
SITE = Path(config.SITE_CHECKOUT_PATH).expanduser().resolve() if config.SITE_CHECKOUT_PATH else None

# "by <you>" if OPERATOR_NAME is set in config.py, else name-independent fallback phrasing, used
# as ONE alternative among several inside _Submitted.search's positive-evidence window (a date or
# a ✅ still count on their own). Sharpens with zero configuration required.
_OPERATOR_BY = (r"\bby " + re.escape(config.OPERATOR_NAME) + r"\b") if config.OPERATOR_NAME \
    else r"\bby (?:hand|me)\b"

_SUBMITTED_TOKEN = re.compile(
    r"\bSUBMITTED\b|\bApplied on:\s*20\d\d-|\bapplied[_ ]on\s*:\s*20\d\d-", re.I)
# Negation within the preceding ~20 characters. A fixed-width lookbehind cannot do this in Python
# ("not yet submitted" puts "yet " between the negation and the word), so it is a window.
_NOT_NEAR = re.compile(r"\b(?:not|never|yet to be|isn'?t|hasn'?t|pending)\b[^.]{0,12}$", re.I)


class _Submitted:
    """Truthy only where the text really claims a submission.

    A dossier that reads "**NOT SUBMITTED.** Blocked on a pending go/no-go" contains the bare word
    SUBMITTED inside its own negation, and a naive \\bSUBMITTED\\b match would misread it as sent.
    That's the same polarity risk any status-detection regex runs: reading a negation as its own
    confirmation fails OPEN, silently, on exactly the case it exists to catch.
    """

    @staticmethod
    def search(text: str):
        for m in _SUBMITTED_TOKEN.finditer(text):
            before = text[max(0, m.start() - 20):m.start()]
            if _NOT_NEAR.search(before):
                continue
            # POSITIVE evidence, not merely the absence of a negation. Chasing negations is a
            # losing game: the first version missed "nothing was submitted", "no field was
            # filled… submitted", and "before this is submitted", and flagged four correct
            # dossiers as self-contradicting. Every REAL submission record in this repo carries a
            # date or an explicit confirmation ("SUBMITTED 2026-07-21 by <you>", "✅ SUBMITTED",
            # "Applied on: 2026-07-22"). Prose *about* submitting does not. Anchor on that.
            window = text[max(0, m.start() - 30):m.end() + 40]
            if re.search(r"20\d\d-\d\d-\d\d|✅|" + _OPERATOR_BY, window, re.I):
                return m
        return None


SUBMITTED = _Submitted
NOT_APPLIED = re.compile(r"\bNOT[ _]APPLIED\b|\bnot yet applied\b|\bawaiting (?:the )?form\b", re.I)
DEAD = re.compile(r"\brejected\b|\bwithdrawn\b|\bclosed\b|\bpassed\b|\bdead\b", re.I)

# EXAMPLE-*/TEMPLATE-* dossiers are scaffolding (verify_claims.py's own fixture, and the blank
# starter copy-from), never a real application. Every check below that sweeps applications/* for
# things that were "supposed to be sent" must skip these, or it fails forever on a fresh clone for
# work nobody ever intended to submit.
SCAFFOLD_DOSSIER_PREFIXES = ("EXAMPLE-", "TEMPLATE-")


def is_scaffold_dossier(folder_name: str) -> bool:
    return folder_name.startswith(SCAFFOLD_DOSSIER_PREFIXES)


@dataclass
class Finding:
    severity: str
    kind: str
    what: str
    why: str

    def render(self) -> str:
        return f"  [{self.severity}] {self.kind}\n      {self.what}\n      → {self.why}"


def sh(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=20)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------------------

def ready_but_never_sent() -> list[Finding]:
    """A finished résumé PDF that never reached an employer.

    This is often the most expensive habit in a job search: dossier-building feels like progress
    because it's tractable and ends in a visible artifact; applying is ambiguous and higher-friction.
    A session can produce five dossiers and zero applications and honestly feel productive.
    """
    # The tracker is the repo's designated source of truth for status (CLAUDE.md §9, kept live as a
    # reflex), so ask IT whether an application went out, don't infer it from prose. A dossier's own
    # notes can describe which résumé VERSION went out without being a dated submission record, and
    # the tracker may already correctly say applied/rejected, and a gate that argues with the source of
    # truth instead of deferring to it is the gate that's wrong.
    sent_folders = set()
    tracker = REPO / "pipeline" / "tracker.html"
    if tracker.is_file():
        src = tracker.read_text(encoding="utf-8", errors="replace")
        for rec in re.split(r"\n\s*\{", src):
            fm = re.search(r'folder:\s*"(applications/[^"]+)"', rec)
            sm = re.search(r'status:\s*"([^"]+)"', rec)
            if fm and sm and sm.group(1) in {"applied", "rejected", "interview", "offer", "passed"}:
                sent_folders.add(fm.group(1).rstrip("/"))

    out: list[Finding] = []
    for pdf in sorted(REPO.glob("applications/*/resume/*.pdf")):
        d = pdf.parent.parent
        if is_scaffold_dossier(d.name):
            continue
        if f"applications/{d.name}" in sent_folders:
            continue
        app = d / "application.md"
        readme = d / "README.md"
        blob = ""
        for f in (app, readme):
            if f.is_file():
                blob += f.read_text(encoding="utf-8", errors="replace")
        if not blob:
            # A rendered résumé with NO application.md and NO README is MORE suspicious, not less:
            # it means no record of this application exists anywhere. The first version of this
            # check did `continue` here and so skipped two of the eight idle dossiers, failing
            # open on the strongest signal it had. Absence of a record is a finding.
            out.append(Finding(
                "HIGH", "ready-but-never-sent",
                f"{d.name}: has a rendered résumé PDF and NO application.md or README.md at all",
                "no record exists that this was ever sent, or ever will be. §13.3 requires both."))
            continue
        if SUBMITTED.search(blob) or DEAD.search(blob):
            continue
        out.append(Finding(
            "HIGH", "ready-but-never-sent", f"{d.name}: has a rendered résumé PDF, no submit recorded",
            "finished work sitting idle. §0: progress is interviews booked, not artifacts produced."))
    return out


def cover_missing() -> list[Finding]:
    """A dossier with a rendered résumé PDF but NO cover-letter PDF.

    A cover letter PDF is treated as MANDATORY in every application bundle, exactly like the
    résumé, and travels with it. A cover letter left optional is one that quietly never gets
    attached. If a dossier is real enough to have a tailored résumé PDF, it's real enough to have a
    cover PDF. Dead dossiers (rejected/withdrawn/closed/passed, never applying) are exempt.
    """
    out: list[Finding] = []
    for pdf in sorted(REPO.glob("applications/*/resume/*.pdf")):
        d = pdf.parent.parent
        if is_scaffold_dossier(d.name):
            continue
        blob = ""
        for f in (d / "application.md", d / "README.md"):
            if f.is_file():
                blob += f.read_text(encoding="utf-8", errors="replace")
        if DEAD.search(blob):
            continue  # a dossier we will never apply to needs no cover
        cover_dir = d / "cover-letter"
        covers = list(cover_dir.glob("*.pdf")) if cover_dir.is_dir() else []
        if not covers:
            out.append(Finding(
                "HIGH", "cover-missing",
                f"{d.name}: has a résumé PDF but NO cover-letter PDF",
                "a cover letter PDF is mandatory in every application bundle, like the résumé. "
                "Render + gate the cover BEFORE the form is filled."))
    return out


def _norm_ats_url(u: str) -> str:
    """Normalize an ATS apply/JD URL to a comparison key: host+path, no scheme/query/fragment.

    The tracker holds real malformed URLs a prior session wrote (`job-job-boards.greenhouse.io`),
    and the same Greenhouse req is reachable at both `boards.greenhouse.io` and
    `job-boards.greenhouse.io`. Collapse those so two records of the SAME posting compare equal.
    """
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"[?#].*$", "", u)
    u = u.rstrip("/")
    # Collapse every Greenhouse board-host variant to one token in a SINGLE pass. Two sequential
    # str.replace()s cannot: "job-boards.greenhouse.io" contains "boards.greenhouse.io", so replacing
    # the latter re-introduces the "job-job-" typo it was meant to remove (the selftest caught this).
    u = re.sub(r"(?:job-)*boards\.greenhouse\.io", "greenhouse.io", u)
    return u


def duplicate_application() -> list[Finding]:
    """A fill-ready dossier that points at a req you have ALREADY applied to.

    Applying twice to the same posting wastes an application slot and reads to a recruiter as
    spray-and-pray. A board sweep that dedupes only on company+title can miss this if the same
    posting gets re-surfaced as a "fresh lead" under a slightly different URL. So the authoritative
    key here is the req URL (its ATS job id); company+title is a weaker secondary signal (one
    company posts many distinct roles), reported only at MEDIUM.
    """
    tracker = REPO / "pipeline" / "tracker.html"
    if not tracker.is_file():
        return []
    src = tracker.read_text(encoding="utf-8", errors="replace")

    APPLIED = {"applied", "rejected", "passed", "interview", "offer"}
    applied_url: dict[str, tuple[str, str, str]] = {}
    applied_cr: dict[tuple[str, str], tuple[str, str, str]] = {}
    rows: list[dict] = []
    for rec in re.split(r"\n\s*\{", src):
        co = re.search(r'co:\s*"([^"]*)"', rec)
        role = re.search(r'role:\s*"([^"]*)"', rec)
        st = re.search(r'status:\s*"([^"]*)"', rec)
        if not (co and role and st):
            continue
        ap = re.search(r'apply:\s*"([^"]*)"', rec)
        jd = re.search(r'jd:\s*"([^"]*)"', rec)
        fl = re.search(r'folder:\s*"(applications/[^"]+)"', rec)
        row = {"co": co.group(1), "role": role.group(1), "status": st.group(1),
               "apply": ap.group(1) if ap else "", "jd": jd.group(1) if jd else "",
               "folder": fl.group(1).rstrip("/") if fl else ""}
        rows.append(row)
        if row["status"] in APPLIED:
            for u in (row["apply"], row["jd"]):
                k = _norm_ats_url(u)
                if k:
                    applied_url[k] = (row["co"], row["role"], row["status"])
            applied_cr[(row["co"].lower().strip(), row["role"].lower().strip())] = (
                row["co"], row["role"], row["status"])

    out: list[Finding] = []
    for row in rows:
        # Only rows we might still act on: fill-ready (active) or an un-worked lead with a dossier.
        if row["status"] not in {"active", "lead"} or not row["folder"]:
            continue
        key = _norm_ats_url(row["apply"]) or _norm_ats_url(row["jd"])
        hit = applied_url.get(key) if key else None
        if hit:
            out.append(Finding(
                "HIGH", "duplicate-application",
                f'{row["folder"]} → a req ALREADY {hit[2]}: {hit[0]} / {hit[1]} (same apply URL)',
                "same posting twice wastes a slot and reads as spray-and-pray; do NOT re-apply "
                "If it is genuinely a different req, the apply URL is wrong; fix it."))
            continue
        crhit = applied_cr.get((row["co"].lower().strip(), row["role"].lower().strip()))
        if crhit:
            out.append(Finding(
                "MEDIUM", "duplicate-application",
                f'{row["folder"]}: {row["co"]} / {row["role"]} matches an already-{crhit[2]} row by '
                "company+title (apply URLs differ)",
                "likely the same posting re-listed, or a real second role; confirm the two apply "
                "URLs are different reqs before applying."))
    return out


def status_contradicts_itself() -> list[Finding]:
    """A dossier whose header says one thing and whose body says another.

    `/wave` step 2 reads these to rank what to work on, so a dossier that says NOT APPLIED at the
    top and SUBMITTED lower down gets re-worked, or worse, re-applied. Two companies came back as
    "fresh leads" on 2026-07-23 having already been applied to at the same URLs.

    DEAD dossiers (tracker status rejected/passed/withdrawn/closed) are EXEMPT: a wave never
    re-works them and CLAUDE.md §13.8 rule 3 makes them read-only forever, so an internal header/body
    disagreement there is harmless to the one decision this check protects, while flagging a defect
    that is by-rule unfixable just trains agents to scroll past a red gate. A rejected dossier whose
    header still says "active" and a passed one whose body still reads "in progress" are the standing
    examples of the shape this exemption covers.
    """
    dead_folders: set[str] = set()
    tracker = REPO / "pipeline" / "tracker.html"
    if tracker.is_file():
        src = tracker.read_text(encoding="utf-8", errors="replace")
        for rec in re.split(r"\n\s*\{", src):
            fm = re.search(r'folder:\s*"applications/([^"/]+)', rec)
            sm = re.search(r'status:\s*"([^"]+)"', rec)
            if fm and sm and sm.group(1) in {"rejected", "passed", "withdrawn", "closed"}:
                dead_folders.add(fm.group(1))

    out: list[Finding] = []
    for f in sorted(REPO.glob("applications/*/README.md")) + sorted(REPO.glob("applications/*/application.md")):
        if f.parent.name in dead_folders or is_scaffold_dossier(f.parent.name):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        head = "\n".join(lines[:12])
        body = "\n".join(lines[12:])
        if NOT_APPLIED.search(head) and SUBMITTED.search(body):
            out.append(Finding(
                "HIGH", "status-contradiction",
                f"{f.parent.name}/{f.name}: header says NOT APPLIED, body says SUBMITTED",
                "the header is what a wave reads first; fix the header or the body so they agree."))
    return out


# A REAL, dated submission record, deliberately TIGHTER than the module-level SUBMITTED that
# ready_but_never_sent uses. That one anchors on "a date OR a by-hand marker OR ✅ somewhere near
# the word", which can misread "To be submitted by hand once it's ready" (a genuinely UNSENT
# dossier) as a submission, because that marker sits in its window. For a check that will FLIP
# a tracker row that governs the §0 count, that false positive is unacceptable, so this requires
# SUBMITTED (or "Applied on") to be immediately followed by an ISO date, and refuses a future lead-in.
_SUB_DATED = re.compile(
    r"\bSUBMITTED\b\s*(?:on\b\s*)?[:\-—]?\s*20\d\d-\d\d-\d\d"
    r"|\bApplied on:?\**\s*20\d\d-\d\d-\d\d"
    r"|\bapplied_on\s*:\s*20\d\d-\d\d-\d\d", re.I)
_FUTURE_LEADIN = re.compile(
    r"\b(?:to be|will be|once|after|before this is|not yet|going to|plan(?:ned)? to)\b", re.I)


def _dated_submission(blob: str):
    """The first REAL dated-submission marker in a dossier, or None.

    A submission record here is a heading or status line carrying a date: '✅ SUBMITTED 2026-08-27
    by hand', '**Applied on:** 2026-07-22', 'applied_on: 2026-07-23'. Future-tense prose ('To be
    submitted by hand once it's ready') is not one, so a ~24-char future lead-in vetoes the match.
    """
    for m in _SUB_DATED.finditer(blob):
        if _FUTURE_LEADIN.search(blob[max(0, m.start() - 24):m.start()]):
            continue
        return m
    return None


def tracker_behind_dossier() -> list[Finding]:
    """A dossier that records a REAL submission while its tracker row still says lead/active.

    This guards against a real failure mode: a tracker regeneration that reverts `applied → lead`
    without reading the dossiers first, so real submissions sit mislabeled as leads: an undercount of
    the ONE metric §0 cares about, and it makes throughput's own `ready-but-never-sent` flag fire on
    applications that had ALREADY gone out. There is no script that reverts a status (crawl.py only
    APPENDS deduped `lead` rows), so the defence is not a source patch but a reconciliation that fails
    LOUD the moment the tracker disagrees with a dossier's own submission record. A hand-regenerated
    tracker can flip many rows back correctly and still miss one whose object carries a `folder:null`
    decoy BEFORE the real folder key, which is exactly why this must be mechanical, not manual.

    Only FOLDER-LINKED rows are checked. A large number of legitimately-applied rows carry an empty
    `folder:` and are still counted correctly, so keying an "undercount" on a missing folder would
    fire on every correctly-counted application with no folder yet. The narrow, zero-false-positive
    signal is: the row is linked to a dossier, its status is pre-submit, and that dossier records a
    DATED submission (the tight detector above, which excludes the not-yet-submitted shape below).
    """
    tracker = REPO / "pipeline" / "tracker.html"
    if not tracker.is_file():
        return []
    src = tracker.read_text(encoding="utf-8", errors="replace")
    PRESUBMIT = {"lead", "sponsor", "active"}
    out: list[Finding] = []
    for rec in re.split(r"\n\s*\{", src):
        fm = re.search(r'folder:\s*"(applications/[^"]+)"', rec)
        sm = re.search(r'status:\s*"([^"]+)"', rec)
        if not (fm and sm) or sm.group(1) not in PRESUBMIT:
            continue
        folder = fm.group(1).rstrip("/")
        d = REPO / folder
        blob = ""
        for f in (d / "application.md", d / "README.md"):
            if f.is_file():
                blob += f.read_text(encoding="utf-8", errors="replace")
        m = _dated_submission(blob)
        if not m:
            continue
        marker = blob[max(0, blob.rfind("\n", 0, m.start()) + 1):blob.find("\n", m.end())].strip()
        out.append(Finding(
            "HIGH", "tracker-behind-dossier",
            f'{folder}: dossier records a real submission, tracker row says "{sm.group(1)}"',
            f"the tracker UNDERCOUNTS a sent application (dossier says sent, tracker still says "
            f"{sm.group(1)!r}). Flip the row to applied (or its true later status). Marker: {marker[:80]}"))
    return out


def tracker_renders() -> list[Finding]:
    """The tracker's embedded <script> must PARSE, or the page is blank in a browser.

    2026-08-05: an unescaped double-quote in one NETWORK row (`name:"Janelle "Nell" Lawless"`,
    introduced 2026-07-25) terminated the JS string, threw inside the <script>, and rendered the whole
    tracker BLANK for ELEVEN days. hooks.py reads the arrays by regex and never executes the JS, so
    every session's counts stayed correct and the break was invisible to all of them. The fix was one
    character; the lesson is that a data file the browser RUNS needs a syntax gate, or it can lie
    silently for as long as no human happens to open it. Best-effort: where node is absent (cron/CI)
    the guard simply does not run, rather than blocking.
    """
    import os
    import shutil
    import tempfile
    tracker = REPO / "pipeline" / "tracker.html"
    if not tracker.is_file() or not shutil.which("node"):
        return []
    src = tracker.read_text(encoding="utf-8", errors="replace")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.S | re.I)
    if not scripts:
        return []
    tf = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    try:
        tf.write("\n;\n".join(scripts))
        tf.close()
        rc, out = sh(["node", "--check", tf.name])
    finally:
        os.unlink(tf.name)
    if rc == 0:
        return []
    first = next((l.strip() for l in out.splitlines() if "Error" in l or ".js:" in l),
                 out.strip()[:160])
    return [Finding(
        "HIGH", "tracker-unparseable",
        f"pipeline/tracker.html <script> has a SYNTAX ERROR, the page renders BLANK: {first[:110]}",
        "hooks.py parses the arrays by regex and never runs the JS, so a broken string is invisible "
        "to every session (the 2026-08-05 '\"Nell\"' quote blanked the tracker for 11 days). Fix the "
        "string; a data file the browser executes needs a syntax gate.")]


def site_matches_repo() -> list[Finding]:
    """The artifact a recruiter downloads vs the artifact this repo believes it ships.

    STRUCTURE.md-equivalent docs assert the built PDF IS the live-site file. This repo caught that
    assertion being false for four days straight; nothing had ever checked it, because every OTHER
    check here reads files inside this repo.

    Optional: set SITE_CHECKOUT_PATH in scripts/config.py to a sibling checkout of your published
    site/portfolio repo. Left unset (the default), this check is a silent no-op: "not configured"
    is deliberately not a Finding, so a fresh clone with no config.py customization stays clean.
    """
    out: list[Finding] = []
    if SITE is None:
        return out  # not configured: optional feature, degrades gracefully (see config.py)
    if not SITE.is_dir():
        return [Finding("MEDIUM", "site-unchecked",
                        f"public site checkout not found at {SITE}",
                        "cannot compare; clone it beside this repo or check the live URL by hand.")]
    for pdf in sorted(REPO.glob("resume/*.pdf")):
        site_pdf = SITE / "resume" / pdf.name
        if not site_pdf.is_file():
            continue
        ha = hashlib.sha256(pdf.read_bytes()).hexdigest()[:12]
        hb = hashlib.sha256(site_pdf.read_bytes()).hexdigest()[:12]
        if ha != hb:
            out.append(Finding(
                "HIGH", "live-site-drift",
                f"resume/{pdf.name}: repo {ha} ≠ live site {hb} "
                f"({pdf.stat().st_size}B vs {site_pdf.stat().st_size}B)",
                "your published site still serves the SITE copy, not the repo copy. Copy the repo "
                "file over and push the site, or the correction you made here never happened."))
    return out


def unpushed() -> list[Finding]:
    """Commits sitting locally that a parallel or future session can't see.

    Whether you push automatically or hold for review is your own call (CLAUDE.md §10); this
    check doesn't take a position on that. It just surfaces the count, since a pile of unpushed
    work is easy to lose track of either way.
    """
    rc, out_s = sh(["git", "rev-list", "--count", "origin/main..HEAD"])
    if rc != 0:
        return []
    try:
        n = int(out_s.strip())
    except ValueError:
        return []
    if n == 0:
        return []
    return [Finding("MEDIUM", "unpushed-commits", f"{n} commit(s) not on origin/main",
                    "not necessarily a problem (see your own §10 preference), but worth knowing "
                    "about before it grows into a real gap.")]


# "<you> filled/typed" if OPERATOR_NAME is set in config.py, else name-independent first-person
# phrasing ("filled it myself"), sharpens with zero configuration required, same pattern as
# _OPERATOR_BY above.
_OPERATOR_FILLED = (re.escape(config.OPERATOR_NAME) + r" (?:filled|typed)") if config.OPERATOR_NAME \
    else r"(?:filled|typed) it myself"

AGENT_FILL = re.compile(r"agent (?:filled|drove)|chrome-devtools|automation (?:chrome|browser)", re.I)
NOT_AGENT_FILL = re.compile(
    r"paste kit|no agent fill|not an agent fill|" + _OPERATOR_FILLED, re.I)
DOM_EVIDENCE = re.compile(
    r"_valueTracker|DOM[- ]verified|required[- ]empty|value[- ]tracker|react[- ]registered", re.I)


def agent_fill_without_dom_evidence() -> list[Finding]:
    """A dossier claiming the AGENT filled a form, with no evidence the DOM was ever checked.

    §14 documents the class in blunt terms: **the tool lies.** `fill_form` and `click` return
    "Successfully filled" / "Successfully clicked" for operations that did not happen. Both failure
    modes were caught in one session: a required checkbox that reported success and never
    registered, and a free-text field that reported success and stayed empty while a second field
    silently had its line breaks stripped.

    A script cannot see a browser, so it cannot verify a fill. What it CAN do is refuse to let the
    record *claim* an agent-verified fill with no evidence behind the claim, which is the same
    discipline CLAUDE.md §0.1 applies to a quotation. If you filled it in yourself or it went out
    via a paste kit, no agent-side DOM check applies and this stays quiet.
    """
    out: list[Finding] = []
    for app in sorted(REPO.glob("applications/*/application.md")):
        if is_scaffold_dossier(app.parent.name):
            continue
        text = app.read_text(encoding="utf-8", errors="replace")
        if not AGENT_FILL.search(text) or NOT_AGENT_FILL.search(text):
            continue
        if DOM_EVIDENCE.search(text):
            continue
        out.append(Finding(
            "MEDIUM", "fill-claimed-not-evidenced",
            f"{app.parent.name}: records an agent-driven fill with no DOM-verification evidence",
            "§14: the tool reports success for fills that did not happen. Record the check "
            "(required-empty count, _valueTracker parity, file bytes) or say you filled it "
            "yourself."))
    return out


# --------------------------------------------------------------------------------------
# Recruiter-list availability is an AUTH-WALLED-surface claim.
#
# A recruiter's own curated shortlist platform, of the kind several exist in the market, is something only the
# operator can actually see; the agent has no login and cannot check it. A stale name carried
# forward from an earlier note and silently assumed still-current, never re-checked, can turn into
# a real recommendation built on a phantom. This is the CLAUDE.md §0.1 grounding law applied to the
# tracker: a positive availability claim about a surface the agent cannot see must cite the operator
# (a screenshot / "per me" / a live check) or be marked UNCONFIRMED / OPERATOR-VERIFY / NOT FOUND.
# It must NOT rest on the agent's own assumption. A remembered preference for a role is not the same
# as a check on whether it's still open, and deliberately does not count as a source.
_AVAIL_POS = re.compile(
    r"\bAVAILABLE\b"
    r"|\bon (?:the )?(?:current )?(?:recruiter|curated) list\b"
    r"|\bstill (?:open|available)\b", re.I)
# "per <you>" / "<you> confirmed" only matches your own configured name; with no config.py, this
# degrades to name-agnostic phrasing, so a fresh clone's selftest exercises exactly what a default
# install actually recognizes.
_OPERATOR_VERIFY_WORDS = (
    r"|\bper " + re.escape(config.OPERATOR_NAME) + r"\b"
    r"|\b" + re.escape(config.OPERATOR_NAME) + r" (?:confirmed|could not|cannot|couldn'?t)\b"
    r"|" + re.escape(config.OPERATOR_NAME) + r"'?s (?:live )?(?:check|screenshot)\b"
    r"|\bconfirmed (?:by|via) " + re.escape(config.OPERATOR_NAME) + r"\b"
) if config.OPERATOR_NAME else (
    r"|\bper (?:me|the operator)\b"
    r"|\b(?:I|the operator) (?:confirmed|could not|cannot|couldn'?t)\b"
    r"|\bmy (?:live )?(?:check|screenshot)\b"
    r"|\bconfirmed (?:by|via) (?:me|hand)\b"
)
_AVAIL_VERIFIED = re.compile(
    r"\bscreenshot\b"
    + _OPERATOR_VERIFY_WORDS +
    r"|\bOPERATOR-VERIFY\b"
    r"|\bNOT FOUND\b"
    r"|\bNOT (?:on|confirmed)\b"
    r"|\bUNCONFIRMED\b"
    r"|\bunverified\b"
    r"|\bcould not find\b", re.I)


# Recruiter/agency platform keywords this repo cannot see for itself (config-driven, see
# scripts/config.py), empty by default. "recruiter" is checked unconditionally below as the
# generic fallback that already covers most cases; add your own platform's name in config.py
# only if you use one by name and want the check to recognize it too.
_RECRUITER_KEYWORDS = [kw.lower() for kw in config.RECRUITER_PLATFORM_KEYWORDS]


def _availability_claim_unsourced(source: str, freetext: str) -> bool:
    """True when a recruiter-channel row asserts list availability with no operator-confirmed source.

    Kept a pure text function so the selftest can drive it directly with realistic fixture strings,
    the same way the SUBMITTED detector is tested.
    """
    src = source.lower()
    if "recruiter" not in src and not any(kw in src for kw in _RECRUITER_KEYWORDS):
        return False
    return bool(_AVAIL_POS.search(freetext) and not _AVAIL_VERIFIED.search(freetext))


def recruiter_availability_unsourced() -> list[Finding]:
    """An agent claim about an auth-walled recruiter surface asserted as fact (CLAUDE.md §0.1)."""
    out: list[Finding] = []
    tracker = REPO / "pipeline" / "tracker.html"
    if not tracker.is_file():
        return out
    src = tracker.read_text(encoding="utf-8", errors="replace")
    for rec in re.split(r"\n\s*\{", src):
        sm = re.search(r'source:\s*"([^"]*)"', rec)
        if not sm:
            continue
        freetext = ""
        for fld in ("next", "notes", "fit"):
            m = re.search(fld + r':\s*"([^"]*)"', rec)
            if m:
                freetext += " " + m.group(1)
        if _availability_claim_unsourced(sm.group(1), freetext):
            co = re.search(r'co:\s*"([^"]*)"', rec)
            out.append(Finding(
                "HIGH", "recruiter-availability-unsourced",
                f'{co.group(1) if co else "?"}: recruiter-list availability asserted with no operator-confirmed source',
                "auth-walled surface: only you can see it. Cite a screenshot / your own live check "
                "/ 'confirmed by me', or mark UNCONFIRMED. Never let a remembered preference stand "
                "in for a live check (CLAUDE.md §0.1)."))
    return out


CHECKS = [
    ("ready-but-never-sent", ready_but_never_sent),
    ("duplicate-application", duplicate_application),
    ("cover-missing", cover_missing),
    ("fill-claimed-not-evidenced", agent_fill_without_dom_evidence),
    ("status-contradiction", status_contradicts_itself),
    ("tracker-behind-dossier", tracker_behind_dossier),
    ("tracker-unparseable", tracker_renders),
    ("recruiter-availability-unsourced", recruiter_availability_unsourced),
    ("live-site-drift", site_matches_repo),
    ("unpushed-commits", unpushed),
]


# --------------------------------------------------------------------------------------

def selftest() -> int:
    """Every case is a real shape from this repo. Includes a coverage assertion so a rule cannot
    be silently neutered while this still prints OK, the failure a red team proved on the other
    gates by deleting a fixture and watching the denominator shrink to match."""
    import tempfile, os, shutil
    passed = failed = 0
    results: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool):
        nonlocal passed, failed
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        results.append((label, ok, ""))

    # SUBMITTED / NOT-APPLIED detection against the REAL strings found in this repo.
    real_submitted = [
        "SUBMITTED 2026-07-21 by hand", "**Applied on:** 2026-07-22 (early AM PT) — SUBMITTED",
        "SUBMITTED 2026-07-22 (Ashby — success c", "applied_on: 2026-07-23",
    ]
    for s in real_submitted:
        check(f"reads as submitted: {s[:38]!r}", bool(SUBMITTED.search(s)))
    check("reads as NOT applied: 'NOT APPLIED'", bool(NOT_APPLIED.search("Status: NOT APPLIED")))
    check("'not yet applied' also reads as not applied",
          bool(NOT_APPLIED.search("Status: not yet applied")))
    check("a rejected dossier is not 'never sent'", bool(DEAD.search("Status: rejected 2026-07-14")))
    check("plain prose does not read as submitted",
          not SUBMITTED.search("We will submit once the operator confirms the salary field."))
    # 🔴 the two fail-open bugs this gate shipped on its first live run, pinned permanently.
    check("'NOT SUBMITTED' does NOT read as submitted",
          not SUBMITTED.search("**NOT SUBMITTED.** Blocked on a pending go/no-go (sponsorship)."))
    check("'not yet submitted' does NOT read as submitted",
          not SUBMITTED.search("Status: not yet submitted"))
    # 🔴 the four real dossier lines this check WRONGLY flagged on its first live run.
    check("'Nothing was submitted' is not a submission",
          not SUBMITTED.search("Read-only in the browser. No field was filled. Nothing was submitted."))
    check("'before this is submitted' is future tense, not a record (stripe)",
          not SUBMITTED.search("Re-point into Web Presence & Platform before this is submitted"))
    check("an em dash right before 'NOT SUBMITTED' after a date does not read as submitted (grafana)",
          not SUBMITTED.search("form answers (as filled, 2026-07-21, REBUILD #2) — NOT SUBMITTED"))
    check("a real dated record still reads as submitted",
          bool(SUBMITTED.search("✅ SUBMITTED 2026-07-22 by hand — success confirmation seen")))

    # The self-contradiction shape, exactly as it appears in real dossiers.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "applications" / "probe"
        d.mkdir(parents=True)
        (d / "README.md").write_text(
            "# Probe — Product Designer\nStatus: **NOT APPLIED**\n" + "\n" * 12 +
            "✅ SUBMITTED 2026-07-22 by hand\n", encoding="utf-8")
        global REPO
        saved = REPO
        REPO = Path(td)
        try:
            hits = status_contradicts_itself()
            check("catches header NOT APPLIED over body SUBMITTED", len(hits) == 1)
            (d / "README.md").write_text(
                "# Probe\nStatus: **SUBMITTED 2026-07-22**\n" + "\n" * 12 + "All good.\n",
                encoding="utf-8")
            check("a consistent dossier is not flagged", len(status_contradicts_itself()) == 0)
            # a DEAD dossier (tracker rejected/passed) is exempt: read-only per CLAUDE.md §13.8 rule 3,
            # and a wave never re-works it, so its internal contradiction is harmless once dead.
            (d / "README.md").write_text(
                "# Probe\nStatus: **NOT APPLIED**\n" + "\n" * 12 + "✅ SUBMITTED 2026-07-22 by hand\n",
                encoding="utf-8")
            pl = Path(td) / "pipeline"
            pl.mkdir(parents=True, exist_ok=True)
            (pl / "tracker.html").write_text(
                'APPLICATIONS=[\n  {co:"P", role:"D", status:"rejected", folder:"applications/probe"}\n]\n',
                encoding="utf-8")
            check("a DEAD (rejected) dossier's header/body contradiction is exempt (wall #3)",
                  len(status_contradicts_itself()) == 0)
        finally:
            REPO = saved

    # The agent-fill evidence rule, against the real vocabulary these dossiers use.
    check("an agent-driven fill WITHOUT evidence is flagged",
          bool(AGENT_FILL.search("The agent filled this form in the automation Chrome."))
          and not DOM_EVIDENCE.search("The agent filled this form in the automation Chrome."))
    check("an agent-driven fill WITH evidence is not flagged",
          bool(DOM_EVIDENCE.search("agent filled and DOM-verified, 0 required-empty")))
    check("a paste-kit fill is exempt (the operator's own browser, no agent DOM to check)",
          bool(NOT_AGENT_FILL.search("PASTE KIT — the operator applies via their own browser")))
    check("'no agent filled this form' is exempt, not a claim",
          bool(NOT_AGENT_FILL.search("No agent filled this form, so there is no agent-side fill to verify")))

    # The cover-missing rule (CLAUDE.md §13.3): a résumé PDF must travel with a cover PDF.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "applications" / "probe"
        (d / "resume").mkdir(parents=True)
        (d / "resume" / "Resume.pdf").write_text("pdf", encoding="utf-8")
        (d / "README.md").write_text("# Probe\nStatus: NOT APPLIED\n", encoding="utf-8")
        saved = REPO
        REPO = Path(td)
        try:
            check("a résumé PDF with NO cover PDF is flagged", len(cover_missing()) == 1)
            (d / "cover-letter").mkdir()
            (d / "cover-letter" / "Cover.pdf").write_text("pdf", encoding="utf-8")
            check("a bundle WITH a cover PDF is not flagged", len(cover_missing()) == 0)
            (d / "cover-letter" / "Cover.pdf").unlink()
            (d / "README.md").write_text("# Probe\nStatus: rejected 2026-07-14\n", encoding="utf-8")
            check("a DEAD dossier needs no cover (exempt)", len(cover_missing()) == 0)
        finally:
            REPO = saved

    # duplicate-application: an active dossier pointing at an already-applied req.
    # The dup row reaches the applied req by a DIFFERENT-looking URL (the job-job-boards typo, the
    # boards↔job-boards host, a stripped ?gh_jid query), so this also exercises _norm_ats_url.
    with tempfile.TemporaryDirectory() as td:
        pl = Path(td) / "pipeline"
        pl.mkdir(parents=True)
        applied = "https://boards.greenhouse.io/acme/jobs/123?gh_jid=123"
        dup = "https://job-job-boards.greenhouse.io/acme/jobs/123"
        newurl = "https://jobs.ashbyhq.com/beta/7c1c-2f44"
        rows = [
            '{co:"Acme", role:"Product Designer", status:"applied", apply:"' + applied + '", jd:"", folder:"applications/acme-old"}',
            '{co:"Acme", role:"Product Designer, Growth", status:"active", apply:"' + dup + '", jd:"", folder:"applications/acme-dup"}',
            '{co:"Beta", role:"Designer", status:"active", apply:"' + newurl + '", jd:"", folder:"applications/beta-new"}',
        ]
        (pl / "tracker.html").write_text("APPLICATIONS=[\n  " + ",\n  ".join(rows) + "\n]\n", encoding="utf-8")
        saved = REPO
        REPO = Path(td)
        try:
            hits = duplicate_application()
            check("a re-application to an already-applied req is caught by URL (HIGH), across host/typo/query normalization",
                  any(h.severity == "HIGH" and "acme-dup" in h.what for h in hits))
            check("a genuinely new req is NOT flagged as a duplicate",
                  not any("beta-new" in h.what for h in hits))
        finally:
            REPO = saved

    # Recruiter-list availability must cite the operator, never the agent's own assumption.
    src_para = "recruiter (Jordan Rivera / Acme Staffing, curated list)"
    check("an unsourced 'AVAILABLE on a recruiter list' claim is caught",
          _availability_claim_unsourced(src_para,
              "AVAILABLE 2026-08-20 on the curated list; in the recruiter's next-round set. Optional second submission alongside Beta Co."))
    check("a corrected row (the operator's own live check, NOT FOUND) is clean",
          not _availability_claim_unsourced(src_para,
              "NOT FOUND on the list per the operator's live check (2026-08-26) — could not find this role on the list."))
    check("a 'NOT ON THE LIST (operator screenshot)' row is clean",
          not _availability_claim_unsourced(src_para,
              "NOT ON THE CURRENT LIST (operator's 2026-08-20 screenshot shows three other companies). Replaced by Beta Co."))
    check("a descriptive 'skill-match on the recruiter's list' (no availability claim) is clean",
          not _availability_claim_unsourced(src_para, "TRUEST skill-match on the recruiter's list. Pursuing their next set."))
    check("an availability claim WITH an operator screenshot source is clean",
          not _availability_claim_unsourced("recruiter (Jordan, Acme Staffing)", "AVAILABLE on the list (operator screenshot 2026-08-20)."))
    check("a non-recruiter source is out of scope (no false positive on crawl finds)",
          not _availability_claim_unsourced("crawl-jobs", "role AVAILABLE now, still open"))

    # tracker-behind-dossier. The tight detector must accept a dated record and REJECT the
    # not-yet-submitted shape ("To be submitted by hand once ready", a genuinely-unsent dossier) that
    # the looser SUBMITTED reads as sent because "by hand" is in its matched range.
    check("a dated 'SUBMITTED 2026-08-27 by hand' reads as a real submission",
          bool(_dated_submission("## ✅ SUBMITTED 2026-08-27 by hand (DOM-confirmed).")))
    check("'**Applied on:** 2026-07-22' reads as a real submission",
          bool(_dated_submission("**Applied on:** 2026-07-22 (early AM PT)")))
    check("the not-yet-submitted shape 'To be submitted by hand once ready' does NOT read as submitted",
          not _dated_submission("- Not yet applied. To be submitted by hand once ready"))
    check("'will be submitted 2026-09-01' (future tense + a date) does NOT read as submitted",
          not _dated_submission("The form will be submitted 2026-09-01 once the operator reviews it."))
    check("'NOT SUBMITTED: dossier building' does NOT read as submitted",
          not _dated_submission("**Status: NOT SUBMITTED — dossier building.**"))
    with tempfile.TemporaryDirectory() as td:
        pl = Path(td) / "pipeline"
        pl.mkdir(parents=True)
        for name, body in (
            # the folder:null-decoy shape: a lead row whose object carries a folder:null key BEFORE
            # the real folder key: the exact structure a naive "has a folder key" check would miss.
            ("acme-designer", "**Status: SUBMITTED 2026-08-27 by hand (DOM-confirmed).**\n"),
            ("beta-designer", "**Status: NOT SUBMITTED.**\n- To be submitted by hand once ready.\n"),
            ("gamma-designer", "✅ SUBMITTED 2026-08-01 by hand — success page seen\n"),
        ):
            dd = Path(td) / "applications" / name
            dd.mkdir(parents=True)
            (dd / "application.md").write_text(body, encoding="utf-8")
        rows = [
            '{co:"Acme", role:"Designer", status:"lead", folder:null, folder:"applications/acme-designer"}',
            '{co:"Beta", role:"Designer", status:"active", folder:"applications/beta-designer"}',
            '{co:"Gamma", role:"Designer", status:"applied", folder:"applications/gamma-designer"}',
        ]
        (pl / "tracker.html").write_text("APPLICATIONS=[\n  " + ",\n  ".join(rows) + "\n]\n", encoding="utf-8")
        saved = REPO
        REPO = Path(td)
        try:
            hits = tracker_behind_dossier()
            check("a submitted dossier whose row still says lead (folder:null decoy) IS caught",
                  any("acme-designer" in h.what for h in hits))
            check("the not-yet-submitted shape (active row + 'to be submitted') is NOT flagged",
                  not any("beta-designer" in h.what for h in hits))
            check("a correctly-applied row is NOT flagged", not any("gamma-designer" in h.what for h in hits))
        finally:
            REPO = saved

    # tracker-unparseable (2026-08-05, the "Nell" quote that blanked the page for 11 days).
    if shutil.which("node"):
        with tempfile.TemporaryDirectory() as td:
            pl = Path(td) / "pipeline"
            pl.mkdir(parents=True)
            saved = REPO
            REPO = Path(td)
            try:
                (pl / "tracker.html").write_text(
                    '<script>const NETWORK=[{name:"Janelle "Nell" Lawless"}];</script>', encoding="utf-8")
                check("a broken tracker <script> (the 'Nell' unescaped quote) is caught",
                      len(tracker_renders()) == 1)
                (pl / "tracker.html").write_text(
                    '<script>const NETWORK=[{name:"Janelle Lawless"}];</script>', encoding="utf-8")
                check("a clean tracker <script> is not flagged", len(tracker_renders()) == 0)
            finally:
                REPO = saved
    else:
        check("tracker-unparseable selftest skipped (node absent); the guard is best-effort", True)

    # Coverage: every registered check must be exercised above.
    exercised = {"ready-but-never-sent", "status-contradiction", "live-site-drift",
                 "unpushed-commits", "fill-claimed-not-evidenced", "cover-missing",
                 "duplicate-application", "recruiter-availability-unsourced",
                 "tracker-behind-dossier", "tracker-unparseable"}
    registered = {name for name, _ in CHECKS}
    missing = registered - exercised
    check(f"every registered check is exercised (missing: {sorted(missing) or 'none'})", not missing)

    print("throughput.py selftest: real shapes from this repo\n")
    for label, ok, _ in results:
        print(f"  {'✓' if ok else '✗'} {label}")
    print()
    if failed:
        print(f"SELFTEST FAILED: {failed} of {passed + failed} wrong")
        return 1
    print(f"SELFTEST OK: {passed}/{passed + failed}")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    findings: list[Finding] = []
    for _, fn in CHECKS:
        findings.extend(fn())

    print("throughput.py: the gates that guard the GOAL (interview calls), not the truth")
    print("  checks: a finished résumé that never went out · a dossier that contradicts itself ·")
    print("          the live site drifting from the repo · commits held back")
    print("  NOT checked: whether a submitted application was any good, and whether a form's fields")
    print("               were really filled; only a browser sees that (§14 DOM verification).")
    if not findings:
        print("\nCLEAN: nothing finished is sitting idle, and the live site matches the repo.")
        return 0
    order = {"HIGH": 0, "MEDIUM": 1}
    print(f"\n{len(findings)} ITEM(S) COSTING YOU APPLICATIONS:\n")
    for f in sorted(findings, key=lambda x: order.get(x.severity, 9)):
        print(f.render())
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
