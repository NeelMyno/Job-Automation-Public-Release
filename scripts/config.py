#!/usr/bin/env python3
"""config.py: optional local configuration for the gate scripts (throughput.py, outreach_queue.py,
and any other script in this folder that chooses to read it).

EVERY VALUE BELOW IS OPTIONAL. The whole pipeline works correctly with all of them left at their
defaults: no gate crashes, no gate falsely fires, and no --selftest depends on any of them being
set. Set a value only if you want a check to sharpen for your own setup; leave the rest alone.

This file is the one place your own name, paths, and pacing preferences live, kept out of the gate
scripts themselves so those scripts stay generic and shareable. If you fork this repo, edit the
values below; never hardcode a name or path back into throughput.py / outreach_queue.py.
"""

from __future__ import annotations

# Your name, exactly as it might appear in your own dossier notes when YOU (not an agent) did
# something, e.g. "SUBMITTED 2026-07-21 by Jordan", "Jordan filled this form by hand". Used by
# throughput.py to recognize a self-attested submission or a self-attested form fill.
# Leave as None to fall back to name-independent phrasing ("by hand", "filled it myself"); the
# checks work correctly with zero configuration; setting this only sharpens them for your own notes.
OPERATOR_NAME: str | None = None

# Absolute path to a sibling checkout of your PUBLISHED site/portfolio repo (the one a recruiter
# actually downloads your résumé from, if you keep one separate from this repo). throughput.py's
# live-site-drift check compares every résumé PDF in this repo's resume/ folder against a
# same-named file in that checkout's resume/ folder.
# Leave as None to skip that check entirely: it is silently skipped (not a failure) rather than
# crashing or guessing at a path.
SITE_CHECKOUT_PATH: str | None = None

# Recruiter/agency platform keywords throughput.py treats as an auth-walled surface it cannot see
# for itself, so a claim that you're "available" on one of these lists needs YOUR confirmation,
# never the agent's assumption. The generic word "recruiter" is always checked too, regardless of
# this list, so it already covers most cases. Add your own platform's name here (e.g. "hired",
# "vettery", "torc") only if you use one and want the check to recognize it by name.
RECRUITER_PLATFORM_KEYWORDS: list[str] = []

# Your own years of professional experience, used by seniority_gate.py to flag a JD asking for
# materially more years than you actually have (a role you'd be dropped from at the resume screen,
# not one worth spending a tailored application on). Leave as None to skip that check entirely: it
# is silently skipped (not a failure) rather than guessing a number.
YOUR_YEARS_OF_EXPERIENCE: int | None = None

# Absolute URL to your own LIVE, published résumé (the one a recruiter actually downloads), if you
# publish one outside this repo. throughput.py's live-site-drift check fetches it and compares it
# against this repo's own resume/ folder, so a stale or fabricated live file can never sit
# undetected behind a clean-looking repo.
# Leave as None to skip that check entirely: it is silently skipped (not a failure).
LIVE_RESUME_URL: str | None = None

# outreach_queue.py pacing preferences.
# FOLLOWUP_DAYS: days of silence before the single permitted follow-up nudge.
FOLLOWUP_DAYS: int = 4
# SMALL_BASKET_CAP: max outreach sends per day to the same small/unknown-size company (the
# "big company: no cap, small company: pace it" split; see outreach_queue.py's own docstring).
SMALL_BASKET_CAP: int = 3
# BIG_COMPANIES: companies large enough that sends to different people there need no daily cap
# (outreach_bundle.py). Empty means every company is paced as small, the safe default.
BIG_COMPANIES: list[str] = []

# Your time zone, as an IANA name such as "America/Chicago". Every date and time the agent writes
# into a record is in this zone, with its label (CLAUDE.md §7). Leave as None to use this machine's
# local zone. Scripts read it through local_now() at the bottom of this file; an unknown name also
# falls back to the local zone rather than crashing.
TIMEZONE: str | None = None

# codex_hook_adapter.py: when True, Codex is handed the current time (in TIMEZONE) each turn and a
# reply must open with that exact "Response at:" line. Off by default; nothing else depends on it.
RESPONSE_TIMESTAMP: bool = False

# cold.py thresholds, in days: how long something can sit before it is listed as gone cold.
# COLD_APP_DAYS: an application with no reply. COLD_ACCEPT_DAYS: a connection note never accepted.
# COLD_REST_DAYS: a thread whose one follow-up is spent. COLD_LEAD_DAYS: a lead never acted on.
COLD_APP_DAYS: int = 21
COLD_ACCEPT_DAYS: int = 14
COLD_REST_DAYS: int = 30
COLD_LEAD_DAYS: int = 21

# Day of the month your paid messaging credits refill, if you use any (the optional InMail ledger).
# Leave as None if you don't; nothing depends on it.
INMAIL_REFILL_DAY: int | None = None

# voice_check.py flags outbound copy that mentions your work authorization when nothing asked for
# it (knowledge-base/12-application-answers.md §3 owns when to mention it). Set False to turn the
# check off.
WORK_AUTH_MENTION_CHECK: bool = True

# hooks.py: the record reflex at the end of a turn (CLAUDE.md §7). Set False to turn it off.
RECORD_REFLEX: bool = True

# account_guard.py (CLAUDE.md §0.2). NEVER_TOUCH_DOMAINS: extra sites no agent may contact in any
# way, treated like LinkedIn. BLOCKED_ACCOUNT_DOMAINS: extra sites where you are logged in that no
# agent may drive in a browser or open for you (a logged-out public fetch stays allowed).
NEVER_TOUCH_DOMAINS: list[str] = []
BLOCKED_ACCOUNT_DOMAINS: list[str] = []

# throughput.py: application-site hosts where the agent's browser cannot finish a submit (for
# example a site that rejects an automated browser), so a filled form there must also carry a paste
# kit with the direct link and the named reason. Empty means the check stays off.
PASTE_KIT_ATS_HOSTS: tuple[str, ...] = ()

# throughput.py: the git remote you push YOUR OWN copy of this repo to (e.g. "mine"), if you push
# at all. The unpushed-commits check compares your branch against that remote only. Unset (the
# default) means the check stays off: a fresh clone's "origin" is the public template, which you
# never push to, so counting commits ahead of it would warn forever about nothing.
PUSH_REMOTE: str | None = None

# throughput.py: names of work-sample sources you have retired (an old portfolio, a project you no
# longer show). Any image under a dossier's snippets/ or attachments/ that cites one is flagged.
# Empty means only the basic "every image names its source" check runs.
STALE_WORK_SOURCES: tuple[str, ...] = ()


def local_now():
    """The current time in TIMEZONE, or in this machine's local zone when TIMEZONE is unset or not a
    zone this Python knows. Every script that writes a date or time into a record should use this."""
    from datetime import datetime
    if TIMEZONE:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(TIMEZONE))
        except Exception:
            pass
    return datetime.now().astimezone()


def local_stamp() -> str:
    """local_now() as "2026-01-05 3:04 PM CST": the form a record or a reply header uses."""
    t = local_now()
    return f"{t:%Y-%m-%d} {t.strftime('%I:%M %p').lstrip('0')} {t.tzname() or ''}".rstrip()
