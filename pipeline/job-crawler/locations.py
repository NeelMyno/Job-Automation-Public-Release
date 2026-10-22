#!/usr/bin/env python3
"""
Where you can work: the one location rule that crawl.py (which postings to keep) and discover.py
(which company boards are worth adding) both apply, so a board is never added for jobs you would
then filter out.

Two gates, both set in filters.yaml:

1. Region gate (require_us, us_markers, location_block). Drops a posting whose location names a
   clearly non-US place and names no US marker. Matching is on word boundaries, so 'india' does
   not hit 'Indianapolis, IN' and 'mexico' does not hit 'New Mexico'.

2. Work-mode gate (remote_ok, onsite_ok, home_metros):
     remote_ok: true            keep remote postings (false: drop postings that are remote only)
     onsite_ok: anywhere        keep onsite and hybrid postings anywhere (the default)
                home_metros     keep onsite and hybrid postings only in a place listed in home_metros
                none            drop onsite and hybrid postings
     home_metros: ["denver", "boulder"]   place names matched as whole words in the location text

   "Remote, or onsite in Denver, no relocation" is: remote_ok: true, onsite_ok: home_metros,
   home_metros: ["denver"]. Leaving all three keys out keeps every location (the old behaviour).

A posting whose location is empty, or whose work mode can't be read from it, is KEPT: the gate never
guesses, and the posting itself says where the job is. Stdlib only, no network.

Run:  python3 locations.py --selftest
"""
import functools, re, sys

ONSITE_CHOICES = ("anywhere", "home_metros", "none")
_REMOTE = re.compile(r"(?<![a-z0-9])(remote|anywhere|distributed|work from home|wfh)(?![a-z0-9])")
_ONSITE = re.compile(r"(?<![a-z0-9])(hybrid|on-?site|in[- ]office|in[- ]person)(?![a-z0-9])")


@functools.lru_cache(maxsize=None)
def _block_re(terms):
    """Compile a list of place names into ONE word-boundary regex, cached per term tuple. Digits
    count as word characters so a term never bleeds into an adjacent token."""
    parts = [r"(?<![a-z0-9])" + re.escape(t.strip().lower()) + r"(?![a-z0-9])"
             for t in terms if t and str(t).strip()]
    return re.compile("|".join(parts)) if parts else None


def settings(F):
    """(remote_ok, onsite_ok, home_metros) from filters.yaml, with the defaults that keep every
    location. Raises ValueError with a one-sentence fix when the settings can't be applied."""
    remote_ok = F.get("remote_ok", True)
    if not isinstance(remote_ok, bool):
        raise ValueError("filters.yaml: remote_ok must be true or false.")
    onsite = F.get("onsite_ok", "anywhere")
    # YAML reads a bare yes/no as true/false; accept those as anywhere/none.
    onsite = {True: "anywhere", False: "none", None: "anywhere"}.get(onsite, onsite)
    onsite = str(onsite).strip().lower().replace("-", "_").replace(" ", "_")
    if onsite not in ONSITE_CHOICES:
        raise ValueError("filters.yaml: onsite_ok must be one of anywhere, home_metros, none.")
    metros = tuple(str(m).strip().lower() for m in (F.get("home_metros") or []) if str(m).strip())
    if onsite == "home_metros" and not metros:
        raise ValueError("filters.yaml: onsite_ok is home_metros, so list at least one place under "
                         "home_metros (for example: home_metros: [\"denver\"]).")
    if not remote_ok and onsite == "none":
        raise ValueError("filters.yaml: remote_ok is false and onsite_ok is none, which keeps no job "
                         "at all; allow one of them.")
    return remote_ok, onsite, metros


def describe(F):
    """One line saying what the work-mode gate keeps, for the crawl report."""
    remote_ok, onsite, metros = settings(F)
    parts = ["remote" if remote_ok else None,
             {"anywhere": "onsite or hybrid anywhere",
              "home_metros": "onsite or hybrid in " + ", ".join(metros),
              "none": None}[onsite]]
    return "keeps " + " and ".join(p for p in parts if p) + "; postings with no readable location are kept"


def region_ok(job, F):
    """Region gate. Off unless require_us is true. An empty location is kept."""
    if not F.get("require_us"):
        return True
    ll = (job.get("location") or "").lower()
    if not ll.strip():
        return True
    br = _block_re(tuple(F.get("location_block") or []))
    blocked_hit = bool(br and br.search(ll))
    us_hit = any(u in ll for u in (F.get("us_markers") or []))
    return not (blocked_hit and not us_hit)


def work_mode(job):
    """'remote', 'onsite' (hybrid counts as onsite: you have to be there) or 'unknown'."""
    ll = (job.get("location") or "").lower()
    if _ONSITE.search(ll):
        return "onsite"
    if job.get("remote") is True or _REMOTE.search(ll):
        return "remote"
    if ll.strip() or job.get("remote") is False:
        return "onsite"
    return "unknown"


def in_home_metro(job, metros):
    br = _block_re(tuple(metros))
    return bool(br and br.search((job.get("location") or "").lower()))


def work_mode_ok(job, F):
    remote_ok, onsite, metros = settings(F)
    mode = work_mode(job)
    if mode == "unknown":
        return True
    if mode == "remote" and remote_ok:
        return True
    # onsite, or a remote posting when remote is off (it may still name a place you can reach)
    if onsite == "anywhere":
        return mode == "onsite"
    if onsite == "home_metros":
        return in_home_metro(job, metros)
    return False


def location_ok(job, F):
    """Both gates. `job` needs `location` (text) and optionally `remote` (True/False/None)."""
    return region_ok(job, F) and work_mode_ok(job, F)


def settings_key(F):
    """A short text that changes whenever any location setting changes (discover.py uses it to
    re-check boards that had no match under the old settings)."""
    remote_ok, onsite, metros = settings(F)
    return "|".join([str(bool(F.get("require_us"))), ",".join(sorted(map(str, F.get("location_block") or []))),
                     ",".join(sorted(map(str, F.get("us_markers") or []))), str(remote_ok), onsite,
                     ",".join(sorted(metros))])


def _selftest():
    J = lambda loc, remote=None: {"location": loc, "remote": remote}
    us = {"require_us": True, "us_markers": ["united states", ", co", "new mexico"],
          "location_block": ["ireland", "dublin", "india", "mexico"]}
    # region gate: word boundaries, US markers rescue, empty kept, off by default
    assert not region_ok(J("Dublin, Ireland"), us)
    assert region_ok(J("Indianapolis, IN"), us) and region_ok(J("Albuquerque, New Mexico"), us)
    assert region_ok(J(""), us) and region_ok(J("Dublin, Ireland"), {})
    # work mode reading
    assert work_mode(J("Remote (United States)")) == "remote"
    assert work_mode(J("Hybrid - Denver, CO")) == "onsite"
    assert work_mode(J("San Francisco, CA")) == "onsite"
    assert work_mode(J("", True)) == "remote" and work_mode(J("")) == "unknown"
    # defaults keep everything (the behaviour before these settings existed)
    for loc in ("Remote", "Austin, TX", "Hybrid - Denver, CO", ""):
        assert work_mode_ok(J(loc), {})
    # remote, or onsite in a home metro, no relocation
    jr = dict(us, remote_ok=True, onsite_ok="home_metros", home_metros=["denver", "boulder"])
    assert location_ok(J("Remote (United States)"), jr)
    assert location_ok(J("Denver, CO"), jr) and location_ok(J("Hybrid - Boulder, CO"), jr)
    assert not location_ok(J("San Francisco, CA"), jr)
    assert not location_ok(J("Remote - Dublin, Ireland"), jr)        # region gate still applies
    assert location_ok(J(""), jr)                                     # unknown: kept, never guessed
    # remote only
    ro = {"remote_ok": True, "onsite_ok": "none"}
    assert location_ok(J("Remote"), ro) and not location_ok(J("Austin, TX"), ro)
    # onsite only, home metro: a remote posting is kept only if it names the metro
    oo = {"remote_ok": False, "onsite_ok": "home_metros", "home_metros": ["austin"]}
    assert not location_ok(J("Remote"), oo) and location_ok(J("Remote or Austin, TX"), oo)
    # YAML yes/no, and clear errors
    assert settings({"onsite_ok": False})[1] == "none" and settings({"onsite_ok": True})[1] == "anywhere"
    for bad in ({"onsite_ok": "home_metros"}, {"onsite_ok": "sometimes"}, {"remote_ok": "yes"},
                {"remote_ok": False, "onsite_ok": "none"}):
        try:
            settings(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    assert "onsite or hybrid in denver" in describe(jr)
    assert settings_key(jr) != settings_key(dict(jr, home_metros=["austin"]))
    print("locations.py selftest: OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    print(__doc__.strip())
