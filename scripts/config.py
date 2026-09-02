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

# outreach_queue.py pacing preferences.
# FOLLOWUP_DAYS: days of silence before the single permitted follow-up nudge.
FOLLOWUP_DAYS: int = 4
# SMALL_BASKET_CAP: max outreach sends per day to the same small/unknown-size company (the
# "big company: no cap, small company: pace it" split; see outreach_queue.py's own docstring).
SMALL_BASKET_CAP: int = 3
