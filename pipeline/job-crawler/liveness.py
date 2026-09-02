#!/usr/bin/env python3
"""
Liveness / ghost-job re-checker.

Before you spend effort on a lead, RE-VERIFY the posting is still actually live. A meaningful
fraction of job postings are ghosts or already filled, so a lead that looked good last week may
be dead today. This module re-checks a single URL, or every open `lead` in the tracker, and
returns one of three verdicts: `live` | `dead` | `uncertain`.

CONSERVATIVE BY DESIGN. A false "dead" makes you skip a real job, which is the expensive mistake,
so the bar for "dead" is strong evidence only; everything short of that is `uncertain`. "live"
likewise needs positive evidence (the posting is really still on the board / the page really is a
job description). When in doubt the answer is `uncertain`, never a guess.

HONEST BY CONSTRUCTION (mirrors crawl.py / hn.py). This module only OBSERVES and REPORTS. It
never invents a verdict, never edits a posting, and writes nothing about you. The ATS check is
authoritative (it asks the same public board API the crawler reads); the HTTP check reports only
what the fetched page shows.

Clean-room: original Python, stdlib only. It REUSES crawl.py's helpers (`fetch`, `strip_html`,
`UA`) and the same three public ATS endpoints: no third-party code, no new dependencies, no
login, no scraping, and no automating any auth-walled platform (those leads return `uncertain`).

Two check strategies, picked automatically:
  * ATS postings (Greenhouse / Lever / Ashby, detected from the URL) -> the RELIABLE check:
    re-query the public board API and test whether the posting's own job id is still present.
    Present -> live; absent -> dead. This is the same JSON the company publishes for its careers
    page, so it is ground truth for "is this posting still open".
  * Everything else (company careers pages, aggregators, HN links) -> a plain HTTP GET that
    follows redirects, then a conservative text classifier (`classify`).

Usage:
  python3 liveness.py --url <URL>                 # check one posting -> verdict + reason
  python3 liveness.py --url <URL> --company Acme   # help resolve a company-hosted ATS slug
  python3 liveness.py --tracker                   # re-check every `lead` row, print a report
  python3 liveness.py --tracker --write           # + annotate each checked row (liveness/checked)
  python3 liveness.py --tracker --company acme     # only leads whose company matches
  python3 liveness.py --tracker --sleep 0.5 --timeout 15   # tune politeness / timeouts
  python3 liveness.py --tracker --today 2026-07-14         # override the check date (sandbox clock)
"""
import json, sys, argparse, re, html, time, socket, datetime
import urllib.request, urllib.error
from urllib.parse import urlparse, parse_qs
from pathlib import Path

import crawl  # sibling module (same dir, on sys.path): reuse fetch(), strip_html(), UA (clean-room)

HERE = Path(__file__).resolve().parent
TRACKER = HERE.parent / "tracker.html"          # pipeline/tracker.html
UA = crawl.UA

# The three public ATS board endpoints are IDENTICAL to crawl.py's fetchers (single source of truth
# for the API shape; kept here as named templates so the ATS check is self-documenting).
GH_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
LEVER_API = "https://api.lever.co/v0/postings/{slug}?mode=json"

# ---------------------------------------------------------------------------------------------
# Closed-signal vocabulary for the HTTP text classifier. Two tiers, deliberately.
#   STRONG: specific phrases that cannot plausibly sit on a LIVE job description. One hit -> dead.
#   WEAK:   generic words ("removed", "closed", "no longer available") that DO appear innocently
#           on live pages ("this feature is no longer available", cookie notices). One alone is
#           NOT enough -> it takes two, or a corroborating signal. This split is the mechanism
#           behind "only say dead on strong evidence": the ambiguous words can never sink a real
#           lead on their own.
# ---------------------------------------------------------------------------------------------
STRONG_CLOSED = (
    "no longer accepting", "no longer accept applications", "no longer accepts applications",
    "we are no longer accepting", "this position has been filled", "position has been filled",
    "this role has been filled", "role has been filled", "this job is no longer",
    "this posting is closed", "posting is closed", "this position is closed",
    "applications are closed", "application period has closed", "job not found",
    "position not found", "posting not found", "page not found", "404 not found",
    "job posting has expired", "this opening has been filled",
)
WEAK_CLOSED = (
    "no longer available", "no longer active", "has been closed", "been removed",
    "position filled", "role is closed", "opening is closed", "has expired", "now closed",
)

# JD-shaped sections: presence of the apply affordance AND >=2 of these on a substantial page is
# positive evidence the page really is a live job description (a careers INDEX has none of these).
JD_SECTIONS = (
    "responsibilities", "qualifications", "what you'll do", "what you will do", "about the role",
    "about the job", "about this role", "who you are", "requirements", "your role", "the team",
    "benefits", "compensation", "minimum qualifications", "preferred qualifications",
    "what we're looking for", "what we are looking for", "you will", "role overview",
    "job description", "in this role", "what you'll bring", "our team",
)

# Generic careers-index / site-root path segments. A redirect that lands on one of these (with no
# job id in the final URL) means the specific posting was pulled and the board bounced us home.
CAREERS_WORDS = {
    "careers", "career", "jobs", "job", "openings", "opening", "opportunities", "positions",
    "position", "roles", "work", "join", "hiring", "search", "listing", "listings", "board",
}

# ATS id shapes. Greenhouse ids are long integers, carried as gh_jid=, token=, or /jobs/<id>.
# Ashby & Lever both use a UUID in the URL path.
GH_ID_RE = re.compile(r"(?:gh_jid=|token=|/jobs/)(\d{4,})")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Hosts we cannot honestly verify by fetching: always return `uncertain`, never a guess. Add any
# other login-walled platform you rely on to this tuple rather than trying to automate it.
AUTH_WALLED_HOSTS = ("linkedin.com",)


# ============================================================================================
# 1) THE PURE CLASSIFIER  (no network: feed it strings; this is what test_liveness.py exercises)
# ============================================================================================
def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _clean_text(body):
    """Tags -> spaces, entities unescaped, whitespace collapsed (crawl.strip_html), then lowered."""
    return crawl.strip_html(body or "").lower()


def _has_job_id(url):
    """Does this URL still point at a SPECIFIC posting (an ATS job id / uuid), vs a bare index?"""
    return bool(GH_ID_RE.search(url or "") or UUID_RE.search(url or ""))


def _norm(url):
    """host + path (lowercased, trailing slash dropped), for detecting a real redirect."""
    p = urlparse(url or "")
    return (p.hostname or "").lower(), (p.path or "/").rstrip("/").lower()


def _redirected(original_url, final_url):
    return bool(final_url) and bool(original_url) and _norm(original_url) != _norm(final_url)


def _looks_like_index(url):
    """True if the URL's path is a careers index / site root (root, or a generic careers word)."""
    _, path = _norm(url)
    if path in ("", "/"):
        return True
    segs = [s for s in path.split("/") if s]
    return bool(segs) and segs[-1] in CAREERS_WORDS


def _looks_like_jd(text):
    """Positive evidence the page IS a live job description: an apply affordance + >=2 named JD
    sections. The section requirement is the real signal (a JS shell / nav-only page has none);
    the small length floor just rejects a near-empty body. Conservative on purpose: anything
    short of this is 'uncertain', never 'live'."""
    if len(text) < 300:
        return False
    if "apply" not in text:
        return False
    return sum(1 for w in JD_SECTIONS if w in text) >= 2


def classify(status_code, final_url, body_text, *, original_url):
    """Pure decision: (verdict, reason) from an HTTP result. No network, no side effects.

    Order matters and encodes the conservative bias:
      1. 404 / 410                      -> dead   (the server says the resource is gone)
      2. redirect to a careers index    -> dead   (posting pulled; the board bounced us home)
      3. a STRONG closed-signal in body -> dead
      4. two+ WEAK closed-signals       -> dead
      5. any other non-2xx status       -> uncertain  (403/429/5xx/999 = blocked or transient,
                                                        NOT evidence the posting closed)
      6. positive JD evidence           -> live
      7. anything else                  -> uncertain  (incl. a lone weak signal / thin page)
    """
    text = _clean_text(body_text)

    # 1. hard HTTP "gone"
    if status_code in (404, 410):
        return "dead", "HTTP %s" % status_code

    # 2. redirected to a careers index / root with no job id in the final URL
    if _redirected(original_url, final_url) and not _has_job_id(final_url) and _looks_like_index(final_url):
        p = urlparse(final_url)
        return "dead", "redirected to careers index (%s%s)" % ((p.hostname or ""), (p.path or "/"))

    # 3. a single strong closed-signal
    hit = next((p for p in STRONG_CLOSED if p in text), None)
    if hit:
        return "dead", "closed-signal in page: %r" % hit

    # 4. multiple weak signals corroborate each other
    weak = [p for p in WEAK_CLOSED if p in text]
    if len(weak) >= 2:
        return "dead", "multiple closed-signals: %s" % ", ".join(repr(w) for w in weak[:3])

    # 5. blocked / transient status -> never call it dead on this alone
    if status_code is not None and status_code not in (200, 201, 202, 203, 204, 206):
        return "uncertain", "HTTP %s (blocked/transient, not evidence of closure)" % status_code

    # 6. positive evidence the page is a live JD
    if _looks_like_jd(text):
        return "live", "page reads as a live job description"

    # 7. inconclusive: the SAFE default (a lone weak word, a thin page, a JS shell, etc.)
    if weak:
        return "uncertain", "only a weak signal %r (not conclusive)" % weak[0]
    if len(text) < 400:
        return "uncertain", "thin/empty page: no job content and no closed-signal"
    return "uncertain", "no apply affordance and no closed-signal"


# ============================================================================================
# 2) TARGET RESOLUTION  (URL -> which ATS, which board slug, which job id)
# ============================================================================================
def detect_ats(url):
    """Greenhouse / Ashby / Lever from the URL, or None. A company-hosted page carrying `gh_jid=`
    is Greenhouse even though its host is the company's own domain (e.g. stripe.com, brex.com)."""
    h = _host(url)
    u = url or ""
    if "ashbyhq.com" in h:
        return "ashby"
    if "lever.co" in h:
        return "lever"
    if "greenhouse.io" in h:
        return "greenhouse"
    if "gh_jid=" in u or "greenhouse" in u:
        return "greenhouse"
    return None


def job_id_from_url(url, ats):
    """The posting's own id from the URL (gh_jid / token / /jobs/<n> for Greenhouse; the UUID for
    Ashby & Lever). None if it cannot be read; the caller then falls back to an HTTP check."""
    if ats == "greenhouse":
        m = GH_ID_RE.search(url or "")
        return m.group(1) if m else None
    m = UUID_RE.search(url or "")
    return m.group(0).lower() if m else None


def slug_from_url(url, ats):
    """The board slug from the URL path, when present. Company-hosted Greenhouse pages
    (stripe.com/...?gh_jid=) do NOT carry the slug; that is resolved from the company via
    boards.yaml instead (see resolve_target)."""
    p = urlparse(url or "")
    h = _host(url)
    segs = [s for s in (p.path or "").split("/") if s]
    if ats == "ashby" and "ashbyhq.com" in h and segs:
        return segs[0]
    if ats == "lever" and "lever.co" in h and segs:
        return segs[0]
    if ats == "greenhouse" and "greenhouse.io" in h:
        q = parse_qs(p.query)
        if q.get("for"):                       # boards.greenhouse.io/embed/job_app?for=<slug>
            return q["for"][0]
        if segs and segs[0] not in ("embed",):  # boards.greenhouse.io/<slug>/jobs/<id>
            return segs[0]
    return None


def _board_lookup(company, boards_map):
    """Match a tracker row's company name to a boards.yaml entry -> (ats, slug), or None.
    boards_map keys are lowercased company names AND slugs; we test the company's word-tokens
    against them, so 'Acme' -> acme, while a name in parentheses or with extra qualifiers misses."""
    if not company or not boards_map:
        return None
    cl = company.lower()
    if cl in boards_map:
        return boards_map[cl]
    tokens = set(re.findall(r"[a-z0-9]+", cl))
    for key, val in boards_map.items():
        if key in tokens:
            return val
    return None


def resolve_target(url, company=None, boards_map=None):
    """(ats, slug, job_id) if this URL can be checked via a board API, else None (-> HTTP check).
    The slug comes from the URL when it is there; otherwise, for a company-hosted Greenhouse page,
    from boards.yaml via the row's company name."""
    ats = detect_ats(url)
    if not ats:
        return None
    jid = job_id_from_url(url, ats)
    if not jid:
        return None
    slug = slug_from_url(url, ats)
    if not slug:
        found = _board_lookup(company, boards_map)
        if found and found[0] == ats:
            slug = found[1]
    if not slug:
        return None
    return (ats, slug, jid)


# ============================================================================================
# 3) THE CHECKS  (ATS board API, authoritative; and the HTTP fallback)
# ============================================================================================
def _fetch_ats_ids(ats, slug, timeout=25):
    """Return (all_ids, listed_ids, error). ids are strings, lowercased for uuids. On any fetch
    error return ([], [], reason) so the caller reports `uncertain`, never `dead`, off a failure."""
    api = {"greenhouse": GH_API, "ashby": ASHBY_API, "lever": LEVER_API}[ats].format(slug=slug)
    try:
        d = crawl.fetch(api, timeout=timeout)
    except urllib.error.HTTPError as e:
        note = "board '%s' not found (HTTP 404)" % slug if e.code == 404 else "board HTTP %s" % e.code
        return [], [], "%s %s: can't verify" % (ats, note)
    except Exception as e:
        return [], [], "%s board fetch failed: %s" % (ats, type(e).__name__)

    all_ids, listed_ids = set(), set()
    if ats == "greenhouse":
        for j in d.get("jobs", []):
            jid = str(j.get("id"))
            all_ids.add(jid)
            # belt-and-suspenders: also take the id embedded in the posting URL
            m = GH_ID_RE.search(j.get("absolute_url", "") or "")
            if m:
                all_ids.add(m.group(1))
        listed_ids = set(all_ids)                     # Greenhouse has no unlisted-but-present state
    elif ats == "ashby":
        for j in d.get("jobs", []):
            jid = (j.get("id") or "").lower()
            if not jid:
                continue
            all_ids.add(jid)
            if j.get("isListed") is not False:        # isListed True or missing == publicly listed
                listed_ids.add(jid)
    else:  # lever -> a bare list of postings
        for j in (d if isinstance(d, list) else []):
            jid = (j.get("id") or "").lower()
            if jid:
                all_ids.add(jid)
        listed_ids = set(all_ids)
    return all_ids, listed_ids, None


def check_ats(ats, slug, job_id, cache=None, timeout=25):
    """Authoritative liveness via the public board API. (verdict, reason).
    A successful fetch with the id present -> live; absent -> dead. A failed fetch -> uncertain."""
    key = (ats, slug)
    if cache is not None and key in cache:
        all_ids, listed_ids, err = cache[key]
    else:
        all_ids, listed_ids, err = _fetch_ats_ids(ats, slug, timeout)
        if cache is not None:
            cache[key] = (all_ids, listed_ids, err)
    if err:
        return "uncertain", err

    jid = job_id.lower()
    label = ats.capitalize()
    if ats == "ashby":
        if jid in listed_ids:
            return "live", "listed on the %s board" % label
        if jid in all_ids:
            return "dead", "present but UNLISTED on the %s board (not publicly open)" % label
        return "dead", "absent from the %s board (posting pulled or filled)" % label
    if jid in all_ids:
        return "live", "present on the %s board" % label
    return "dead", "absent from the %s board (posting pulled or filled)" % label


def http_probe(url, timeout=20, max_bytes=800_000):
    """Plain GET that follows redirects. Returns (status, final_url, body, error).
    A 404/410 arrives as an HTTPError, which IS a readable response (code + url + body), so we use
    it rather than treating it as a failure. A real network failure returns error set (-> uncertain)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = getattr(r, "status", None) or r.getcode()
            return status, r.geturl(), r.read(max_bytes).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(max_bytes).decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, (getattr(e, "url", None) or url), body, None
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        return None, url, "", "%s: %s" % (type(e).__name__, str(getattr(e, "reason", e))[:80])
    except Exception as e:  # never let one bad URL crash a --tracker sweep (crawl.py's resilience)
        return None, url, "", "%s: %s" % (type(e).__name__, str(e)[:80])


def check_url(url, company=None, boards_map=None, cache=None, timeout=20):
    """Top-level single-URL check -> (verdict, reason). Picks the ATS or HTTP strategy itself."""
    if not url:
        return "uncertain", "no URL on this lead: nothing to check"
    host = _host(url)
    if any(host == h or host.endswith("." + h) for h in AUTH_WALLED_HOSTS):
        return "uncertain", "an auth-walled platform: verify by hand"
    tgt = resolve_target(url, company, boards_map)
    if tgt:
        return check_ats(*tgt, cache=cache, timeout=max(timeout, 25))
    status, final, body, err = http_probe(url, timeout=timeout)
    if err:
        return "uncertain", "could not fetch: %s" % err
    return classify(status, final, body, original_url=url)


# ============================================================================================
# 4) TRACKER READ / REPORT / (SAFE) WRITE
# ============================================================================================
def load_boards_map():
    """{company_lower|slug_lower: (ats, slug)} from boards.yaml, so company-hosted Greenhouse rows
    (stripe.com/...?gh_jid=) resolve to a board slug. PyYAML is the crawler's one existing dep;
    if it is unavailable we simply skip the map (those rows fall back to an HTTP check)."""
    out = {}
    try:
        import yaml
        data = yaml.safe_load((HERE / "boards.yaml").read_text())
    except Exception:
        return out
    for b in (data.get("boards", data) if isinstance(data, dict) else (data or [])):
        try:
            co, ats, slug = b["company"], b["ats"], b["slug"]
        except Exception:
            continue
        out[co.lower()] = (ats, slug)
        out[slug.lower()] = (ats, slug)
    return out


_APP_START = "const APPLICATIONS = ["
_ROW_RE = re.compile(r'^\s*\{co:"')


def _field(line, key):
    """Read a double-quoted field off a single row line. Returns None for `key:null` / absent.
    Safe because tracker string values never contain a literal `"` (they use single quotes)."""
    m = re.search(key + r':"((?:[^"])*)"', line)
    return m.group(1) if m else None


def find_app_block(lines):
    """(start_index, end_index) of the APPLICATIONS array: the marker line and its closing `];`."""
    start = next((i for i, l in enumerate(lines) if _APP_START in l), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if lines[j].strip() == "];"), None)
    return (start, end) if end is not None else None


def parse_applications(text):
    """List of {idx, line, co, role, status, url} for every APPLICATIONS row. `idx` is the line
    index into text.split('\\n'), so a safe writer can target exactly that line."""
    lines = text.split("\n")
    block = find_app_block(lines)
    if not block:
        return []
    start, end = block
    rows = []
    for i in range(start + 1, end):
        line = lines[i]
        if not _ROW_RE.match(line):
            continue
        rows.append(dict(
            idx=i, line=line,
            co=_field(line, "co") or "", role=_field(line, "role") or "",
            status=_field(line, "status") or "",
            url=_field(line, "apply") or _field(line, "jd") or _field(line, "link"),
        ))
    return rows


def set_liveness_on_line(line, verdict, checked):
    """Return `line` with liveness/checked fields set just before its closing brace. Idempotent:
    any prior liveness/checked is stripped first, so re-running never duplicates. Returns None if
    the line is not a well-formed single-row object (caller then leaves it untouched).

    Safe because every tracker row is ONE physical line whose only `}`/`"` are structural (verified:
    zero interior braces, zero escaped quotes in the array), so the last `}` is the row's closer."""
    line = re.sub(r',\s*liveness:"[^"]*"', "", line)
    line = re.sub(r',\s*checked:"[^"]*"', "", line)
    m = re.match(r'^(?P<body>.*\})(?P<tail>,?\s*)$', line, re.S)
    if not m:
        return None
    inner = m.group("body")[:-1].rstrip()          # everything up to (not incl.) the closing brace
    if inner.endswith(","):
        inner = inner[:-1]
    add = ', liveness:"%s", checked:"%s"' % (verdict, checked)
    return inner + add + "}" + m.group("tail")


def rewrite_tracker(text, updates, checked):
    """Return (new_text, note). `updates` = {line_idx: verdict}. Line-targeted and validated:
    only the named row lines change; structure (markers, row count, NETWORK array) must survive or
    NOTHING is written and the original text is returned with an error note.

    This is a pure text function; main() decides whether to write the result to disk."""
    lines = text.split("\n")
    block = find_app_block(lines)
    if not block:
        return text, "APPLICATIONS block not found: NOT written"

    before_co = text.count('co:"')
    new_text = text
    changed = 0
    for idx, verdict in updates.items():
        old = lines[idx]
        if not _ROW_RE.match(old):
            return text, "line %d is not a row: NOT written" % idx
        new = set_liveness_on_line(old, verdict, checked)
        if new is None:
            return text, "could not safely rewrite line %d: NOT written" % idx
        # per-row safety: the rewritten row must carry EXACTLY one of each field (no duplication)
        if new.count('liveness:"') != 1 or new.count('checked:"') != 1:
            return text, "line %d field-count off: NOT written" % idx
        if new == old:
            continue                                    # already current (idempotent re-run)
        if new_text.count(old) != 1:
            return text, "row line not unique (line %d): NOT written" % idx
        new_text = new_text.replace(old, new, 1)
        changed += 1

    # ---- structural validation: refuse to write anything that broke the file ----
    checks = {
        "one APPLICATIONS marker": new_text.count(_APP_START) == 1,
        "NETWORK array intact": new_text.count("const NETWORK = [") == text.count("const NETWORK = ["),
        "row count unchanged": new_text.count('co:"') == before_co,
        "line count unchanged": len(new_text.split("\n")) == len(lines),
        "array closer present": "\n];" in new_text,
    }
    bad = [name for name, ok in checks.items() if not ok]
    if bad:
        return text, "post-rewrite validation FAILED (%s): NOT written" % "; ".join(bad)
    if changed == 0:
        return text, "already current: no rows needed changing"
    return new_text, "ok: %d row(s) annotated" % changed


# ============================================================================================
# 5) CLI
# ============================================================================================
def _today(args):
    if getattr(args, "today", None):
        return args.today
    try:
        return datetime.date.today().isoformat()
    except Exception:
        return ""


_ICON = {"live": "LIVE ", "dead": "DEAD ", "uncertain": "  ?  "}


def run_tracker(args):
    if not TRACKER.exists():
        print("tracker not found: %s" % TRACKER, file=sys.stderr)
        return 2
    text = TRACKER.read_text()
    rows = parse_applications(text)
    boards_map = load_boards_map()
    cache = {}
    checked_date = _today(args)

    targets = [r for r in rows if r["status"] == "lead"]
    if args.company:
        c = args.company.lower()
        targets = [r for r in targets if c in r["co"].lower()]

    results, updates = [], {}
    print("Re-checking %d lead(s) from %s\n" % (len(targets), TRACKER.name))
    print("  %-5s  %-26s  %-42s  %s" % ("", "COMPANY", "ROLE", "REASON"))
    print("  " + "-" * 96)
    tally = {"live": 0, "dead": 0, "uncertain": 0}
    for i, r in enumerate(targets):
        verdict, reason = check_url(r["url"], company=r["co"], boards_map=boards_map,
                                    cache=cache, timeout=args.timeout)
        tally[verdict] += 1
        results.append((r, verdict, reason))
        updates[r["idx"]] = verdict
        print("  %s  %-26.26s  %-42.42s  %s" % (_ICON[verdict], r["co"], r["role"], reason))
        if i < len(targets) - 1 and args.sleep > 0:
            time.sleep(args.sleep)

    print("\n  Summary: %d live · %d dead · %d uncertain" % (tally["live"], tally["dead"], tally["uncertain"]))
    if tally["dead"]:
        print("  Dead leads to drop/verify: " +
              ", ".join("%s (%s)" % (r["co"], r["role"]) for r, v, _ in results if v == "dead"))

    if args.write:
        new_text, note = rewrite_tracker(text, updates, checked_date)
        if note.startswith("ok") and new_text != text:
            TRACKER.write_text(new_text)
            print("\n  tracker.html: %s (checked=%s)" % (note, checked_date))
        elif note.startswith("already current"):
            print("\n  tracker.html: %s (nothing to write)" % note)
        else:
            print("\n  tracker.html NOT modified: %s" % note, file=sys.stderr)
            return 1
    else:
        print("\n  (re-run with --write to stamp liveness/checked onto these rows)")
    return 0


def run_url(args):
    boards_map = load_boards_map()
    verdict, reason = check_url(args.url, company=args.company, boards_map=boards_map,
                               timeout=args.timeout)
    print("%s  %s\n%s" % (verdict.upper(), args.url, reason))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Re-verify that job leads are still live (ghost-job check).")
    ap.add_argument("--url", help="check a single posting URL")
    ap.add_argument("--tracker", action="store_true", help="re-check every `lead` row in tracker.html")
    ap.add_argument("--write", action="store_true",
                    help="with --tracker: stamp liveness/checked onto each checked row (validated)")
    ap.add_argument("--company", help="filter tracker leads by company; or resolve an ATS slug for --url")
    ap.add_argument("--today", help="check date YYYY-MM-DD (override if the clock is unavailable)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between requests (politeness)")
    ap.add_argument("--timeout", type=int, default=20, help="per-request timeout in seconds")
    args = ap.parse_args()

    if args.url:
        return run_url(args)
    if args.tracker:
        return run_tracker(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
