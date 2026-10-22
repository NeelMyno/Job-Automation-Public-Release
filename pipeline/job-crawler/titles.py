#!/usr/bin/env python3
"""
How a job title matches one of your filters.yaml include_titles terms: the one title rule that
crawl.py (which postings to keep) and discover.py (which company boards are worth adding) share.

A term matches as a lowercase substring of the title, so "analyst" finds "Senior Data Analyst"
and "engineer" finds "Engineering Manager". A SHORT term (SHORT_TITLE_MAX characters or fewer,
such as "rn", "qa", "pm", "cna") must match as a whole word instead, with an optional plural "s":
as a substring it would hit inside ordinary words ("rn" inside "International" or "Internal",
"pm" inside "Development"). Stdlib only, no network.

Run:  python3 titles.py --selftest
"""
import re, sys

SHORT_TITLE_MAX = 3


def is_short(term):
    return len((term or "").strip()) <= SHORT_TITLE_MAX


def term_hits(term, title):
    """Does this one include_titles term match this job title? Case-insensitive."""
    term = (term or "").strip().lower()
    if not term:
        return False
    t = (title or "").lower()
    if is_short(term):
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"s?(?![a-z0-9])", t) is not None
    return term in t


def first_match(terms, title):
    """The first term in `terms` that matches `title`, or None."""
    return next((it for it in terms if term_hits(it, title)), None)


def _selftest():
    # a short term never matches inside a word
    for t in ("International Marketing Manager", "Internal Audit Lead", "Learning Coordinator", "Governance Analyst"):
        assert not term_hits("rn", t), t
    assert not term_hits("pm", "Software Development Engineer")
    # ...but matches as a word, plural, or beside punctuation
    for t in ("RN, Med-Surg", "Registered Nurse (RN)", "ICU RN - Nights", "Travel RNs", "RN/LPN"):
        assert term_hits("rn", t), t
    assert term_hits("qa", "Senior QA Engineer") and term_hits("c++", "C++ Developer")
    # a longer term keeps substring matching
    assert term_hits("analyst", "Senior Data Analyst") and term_hits("engineer", "Engineering Manager")
    assert term_hits("data analyst", "Lead Data Analysts")
    assert not term_hits("", "Anything") and not term_hits("rn", "")
    assert first_match(["rn", "data analyst"], "International Data Analyst") == "data analyst"
    assert first_match(["rn"], "International Relations Lead") is None
    print("titles.py selftest: OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    print(__doc__.strip())
