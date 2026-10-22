#!/usr/bin/env python3
"""
Board discovery: finds company job boards for you and adds the checked ones to boards.yaml.

The crawler reads companies' public job boards on six ATS platforms (Greenhouse, Lever, Ashby,
SmartRecruiters, Workable, Workday). Nobody should have to hand-list those boards, so this script
finds them, for any role, any industry, any company:

  --sweep           Harvest company board names for Greenhouse, Lever, Ashby, SmartRecruiters and
                    Workable from the free Common Crawl URL index, then read each board's public API
                    and add only the companies with at least one open posting whose title matches
                    your filters.yaml include_titles AND whose location passes the same location
                    rule crawl.py applies (locations.py). Bounded: a run stops after --max-minutes
                    (3 by default) and continues where it stopped on the next run, page by page.
                    This is the default way to build a real board list.
  --urls FILE|-     Any job or careers URLs (a web search's results, a pasted list, anything): reads
                    the ATS and board name from each (all six ATSes, Workday included), checks the
                    board is live, dedupes, and adds it.
  --company NAME..  Guesses each company's board name on the five guessable ATSes, checks each
                    guess, adds the hits, and reports the misses honestly.
  --queries         Prints web-search queries for your titles; feed the result URLs to --urls.

Options: --dry-run (change nothing), --json (machine-readable result), --limit N (most boards to
check against their APIs this run; it does not bound the index harvest), --max-minutes M (the sweep's
whole time budget, index harvest included; 0 = no limit), --workers N, --ats a,b (restrict the
sweep), --refresh-index, --selftest (offline).

How long a sweep takes: the first run is the slowest, because it reads the Common Crawl index before
it can check any board; on a slow day that harvest needs several 3-minute runs to finish (each run
continues it). Later runs reuse the harvest and spend their time checking boards: about 1 to 3
minutes for 150 boards. When the index is overloaded (HTTP 5xx), a domain is skipped after a few
failures in a row, the fallback advice is printed at once, and the run ends within its budget.

Rows this script adds carry `source: discover:<mode>` and an `added:` date, so they can always be
told apart from rows you wrote. It never removes or edits an existing row.

Politeness: a clear User-Agent, timeouts on every call, a few workers at most with a pause between
calls, retries with back-off on the index, and a cache under cache/ (gitignored) so no work is
repeated: the harvested index is reused for the same crawl, and a board already checked against the
same titles is not checked again for two weeks.

HONEST BY CONSTRUCTION: a board is added only after its own public API answered with real postings.
A guess that did not answer is reported as a miss, never added.
"""
import argparse, hashlib, json, random, re, sys, time
import urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

from http_util import read_url  # sibling module: gzip + retry on a cut-off read
import locations  # sibling module: the location rule crawl.py applies, shared so both agree
import titles as title_rule  # sibling module: the title rule crawl.py applies, shared so both agree

HERE = Path(__file__).resolve().parent
BOARDS = HERE / "boards.yaml"
FILTERS = HERE / "filters.yaml"
CACHE_DIR = HERE / "cache"
UA = "Mozilla/5.0 (personal job-search crawler, board discovery; see pipeline/job-crawler/README.md)"

ATSES = ("greenhouse", "lever", "ashby", "smartrecruiters", "workable", "workday")
SWEEP_ATSES = ("greenhouse", "lever", "ashby", "smartrecruiters", "workable")
GUESS_ATSES = SWEEP_ATSES  # a Workday board needs tenant + host + site, which cannot be guessed

# Common Crawl URL index (CDX server). Newest crawl id: the first entry of collinfo.json.
# Pagination, as the live API answers it:
#   <cdx-api>?url=<domain>/*&output=json&showNumPages=true  ->  {"pages": N, "pageSize": 5, "blocks": B}
#   <cdx-api>?url=<domain>/*&output=json&fl=url&page=K      ->  one JSON object per line, K = 0..N-1
# The server answers some queries with HTTP 504; those are retried with back-off, then the next
# older crawl is tried.
COLLINFO = "https://index.commoncrawl.org/collinfo.json"
CDX_DOMAINS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "ashby": ("jobs.ashbyhq.com",),
    "smartrecruiters": ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"),
    "workable": ("apply.workable.com",),
}
INDEX_MAX_PAGES = 20          # per domain: bounds one harvest
INDEX_MAX_5XX = 4             # consecutive 5xx / timeouts from the index for one domain: skip it this run
DEFAULT_MAX_MINUTES = 3.0     # a sweep's whole time budget (index harvest + board checks)
HARVEST_SHARE = 2 / 3         # the index harvest may use at most this share of the budget
FALLBACK_ADVICE = ("The Common Crawl index is not answering right now (it is often overloaded). "
                   "Boards already harvested are still checked, and the sweep tries the index again "
                   "next run. To add boards without it: discover.py --company \"Name\" \"Other Name\", "
                   "or discover.py --queries, run those searches, and pipe the result URLs into "
                   "discover.py --urls -")
INDEX_REUSE_DAYS = 45         # a harvested index is reused this long when collinfo is unreachable
RECHECK_DAYS = 14             # a board checked against the same titles is skipped this long
DEAD_RECHECK_DAYS = 45        # a board that 404'd or had no postings is skipped this long
DEFAULT_SWEEP_LIMIT = 150
DEFAULT_WORKERS = 4
PAUSE_SECONDS = 0.3           # each worker pauses this long after each call

GH_RESERVED = {"embed", "v1", "api", "job_app", "job_board", "jobs"}
WORKABLE_RESERVED = {"api", "j", "careers", "jobs"}
NAME_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "technologies",
                 "technology", "labs", "group", "holdings", "hq", "the", "plc", "gmbh"}


# ============================================================================================
# HTTP (one small class, so the selftest can swap in a fake with no network)
# ============================================================================================
class OutOfTime(Exception):
    """The run's time budget is spent."""


class IndexDown(Exception):
    """The index failed INDEX_MAX_5XX times in a row for one domain."""


class HttpStatus(Exception):
    def __init__(self, code, url=""):
        super().__init__(f"HTTP {code}")
        self.code = code
        self.url = url


class Http:
    def __init__(self, timeout=20):
        self.timeout = timeout

    def _open(self, req, timeout):
        try:
            return read_url(req, timeout or self.timeout)
        except urllib.error.HTTPError as e:
            raise HttpStatus(e.code, req.full_url)

    def get_text(self, url, timeout=None):
        return self._open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout)

    def get_json(self, url, timeout=None):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        return json.loads(self._open(req, timeout))

    def post_json(self, url, body, timeout=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={
            "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
        return json.loads(self._open(req, timeout))


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ============================================================================================
# URL -> (ats, slug).  The same parser serves --urls and the Common Crawl harvest.
# ============================================================================================
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2})?$")


def canon_slug(seg):
    """Percent-encoded, trimmed board name, or None if it can't be one. Kept percent-encoded so it
    drops straight into an API URL (crawl.py builds URLs from it with no further quoting)."""
    s = urllib.parse.unquote(seg or "").strip()
    if not s or len(s) > 100:
        return None
    q = urllib.parse.quote(s, safe="-._~")
    return q if re.fullmatch(r"[A-Za-z0-9%._~-]+", q) and not q.startswith(".") else None


def parse_board_url(url):
    """Returns (ats, slug, None) on success or (None, None, reason). Workday slugs are
    'tenant/host/site', exactly as boards.yaml and crawl.py expect."""
    u = (url or "").strip().strip("<>()[]\"'.,;")
    if not u:
        return None, None, "empty"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u
    p = urllib.parse.urlparse(u)
    host = (p.hostname or "").lower()
    segs = [s for s in (p.path or "").split("/") if s]
    q = urllib.parse.parse_qs(p.query)

    def first(xs, reserved=()):
        return canon_slug(xs[0]) if xs and xs[0].lower() not in reserved else None

    if host.endswith("greenhouse.io"):
        if q.get("for"):
            s = canon_slug(q["for"][0])
        elif host.startswith("boards-api."):
            s = canon_slug(segs[2]) if len(segs) >= 3 and segs[:2] == ["v1", "boards"] else None
        else:
            s = first(segs, GH_RESERVED)
        return ("greenhouse", s, None) if s else (None, None, "Greenhouse URL without a board name")
    if host == "jobs.lever.co" or host == "api.lever.co":
        s = first(segs[2:] if host == "api.lever.co" and segs[:2] == ["v0", "postings"] else segs)
        return ("lever", s, None) if s else (None, None, "Lever URL without a board name")
    if host.endswith(".lever.co"):
        return None, None, "a regional Lever board (e.g. jobs.eu.lever.co): crawl.py reads only jobs.lever.co"
    if host == "jobs.ashbyhq.com":
        s = first(segs, {"api"})
        return ("ashby", s, None) if s else (None, None, "Ashby URL without a board name")
    if host == "api.ashbyhq.com":
        s = canon_slug(segs[2]) if len(segs) >= 3 and segs[:2] == ["posting-api", "job-board"] else None
        return ("ashby", s, None) if s else (None, None, "Ashby API URL without a board name")
    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        s = first(segs)
        return ("smartrecruiters", s, None) if s else (None, None, "SmartRecruiters URL without a company")
    if host == "api.smartrecruiters.com":
        s = canon_slug(segs[2]) if len(segs) >= 3 and segs[:2] == ["v1", "companies"] else None
        return ("smartrecruiters", s, None) if s else (None, None, "SmartRecruiters API URL without a company")
    if host == "apply.workable.com":
        if segs[:1] == ["api"]:
            i = segs.index("accounts") + 1 if "accounts" in segs else len(segs)
            s = canon_slug(segs[i]) if i < len(segs) else None
        else:
            s = first(segs, WORKABLE_RESERVED)
        return ("workable", s, None) if s else (None, None, "Workable URL without an account")
    if host.endswith(".workable.com") and host.count(".") == 2 and host.split(".")[0] not in ("www", "apply", "jobs"):
        return "workable", canon_slug(host.split(".")[0]), None
    if host.endswith(".myworkdayjobs.com"):
        parts = host.split(".")
        if len(parts) != 4:
            return None, None, "Workday host not in the tenant.wdN.myworkdayjobs.com shape"
        tenant, wd = parts[0], parts[1]
        if segs[:2] == ["wday", "cxs"] and len(segs) >= 4:
            site = segs[3]
        else:
            rest = segs[1:] if segs and _LOCALE.match(segs[0]) else segs
            site = rest[0] if rest else None
        site = canon_slug(site) if site else None
        return ("workday", f"{tenant}/{wd}/{site}", None) if site else (None, None, "Workday URL without a site name")
    if host.endswith(".myworkdaysite.com"):
        wd = host.split(".")[0]
        if len(segs) >= 3 and segs[0] == "recruiting":
            return "workday", f"{segs[1].lower()}/{wd}/{canon_slug(segs[2])}", None
        return None, None, "Workday site URL not in the /recruiting/<tenant>/<site> shape"
    if "gh_jid=" in (p.query or ""):
        return None, None, ("a company-hosted Greenhouse page: the board name is not in the URL, "
                            "so try --company with the company's name")
    return None, None, "not a URL on one of the six supported ATSes"


def extract_urls(text):
    """Every URL-ish token in free text (a search-result dump, a pasted list, JSON...)."""
    found = re.findall(r"https?://[^\s<>\"'()\[\]{}|,]+", text or "")
    hosts = r"(?:[\w.-]+\.)?(?:greenhouse\.io|lever\.co|ashbyhq\.com|smartrecruiters\.com|workable\.com|myworkdayjobs\.com|myworkdaysite\.com)"
    for m in re.finditer(r"(?<![\w/.:-])(" + hosts + r"/[^\s<>\"'()\[\]{}|,]*)", text or "", re.I):
        found.append(m.group(1))
    out, seen = [], set()
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ============================================================================================
# Board probes: read one board's public API, return what is really there
# ============================================================================================
def _pretty(slug):
    s = urllib.parse.unquote(slug.split("/")[0])
    s = re.sub(r"[-_]+", " ", s).strip()
    return s.title() if s == s.lower() else s


def probe(ats, slug, http, sleep=time.sleep, tries=3):
    """{status: live|empty|dead|error, count, titles, jobs, name, error}. `jobs` holds each posting's
    title, location and remote flag, so the location rule can be applied. `name` is the company name when
    the API gives one, else None. A transient failure (a cut-off read, a timeout, HTTP 429 or 5xx)
    is retried after a pause, so a flaky connection is not reported as a missing board."""
    for k in range(tries):
        res = _probe_once(ats, slug, http)
        transient = res["status"] == "error" and not re.match(r"HTTP 4(?!29)", res["error"] or "")
        if not transient or k == tries - 1:
            return res
        sleep(2.0 * (k + 1))
    return res


def _probe_once(ats, slug, http):
    res = {"ats": ats, "slug": slug, "status": "error", "count": 0, "titles": [], "jobs": [], "name": None,
           "error": None}

    def J(title, location="", remote=None):
        return {"title": title or "", "location": location or "", "remote": remote}
    try:
        if ats == "greenhouse":
            d = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            jobs = [J(j.get("title"), (j.get("location") or {}).get("name") if isinstance(j.get("location"), dict)
                      else j.get("location")) for j in d.get("jobs", [])]
        elif ats == "lever":
            d = http.get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            jobs = []
            for j in (d if isinstance(d, list) else []):
                loc = (j.get("categories") or {}).get("location") or ""
                jobs.append(J(j.get("text"), loc, "remote" in loc.lower() or None))
        elif ats == "ashby":
            d = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
            jobs = [J(j.get("title"), j.get("location"), j.get("isRemote"))
                    for j in d.get("jobs", []) if j.get("isListed") is not False]
        elif ats == "smartrecruiters":
            jobs, offset = [], 0
            while offset < 300:
                d = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
                content = d.get("content", []) if isinstance(d, dict) else []
                for j in content:
                    loc = j.get("location") or {}
                    place = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
                    jobs.append(J(j.get("name"), place, True if loc.get("remote") else None))
                    res["name"] = res["name"] or ((j.get("company") or {}).get("name"))
                offset += 100
                if not content or offset >= (d.get("totalFound") or 0):
                    break
        elif ats == "workable":
            d = http.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
            jobs = [J(j.get("title"), ", ".join(x for x in (j.get("city"), j.get("country")) if x),
                      True if j.get("telecommuting") else None)
                    for j in (d.get("jobs", []) if isinstance(d, dict) else [])]
            res["name"] = d.get("name") if isinstance(d, dict) else None
        elif ats == "workday":
            tenant, host, site = slug.split("/")
            d = http.post_json(f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
                               {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
            jobs = [J(j.get("title"), j.get("locationsText")) for j in (d.get("jobPostings") or [])]
            res["count_total"] = d.get("total") or len(jobs)
        else:
            res["error"] = f"unknown ats '{ats}'"
            return res
    except HttpStatus as e:
        res["status"] = "dead" if e.code in (404, 410) else "error"
        res["error"] = f"HTTP {e.code}"
        return res
    except Exception as e:
        res["error"] = f"{type(e).__name__} {str(e)[:70]}"
        return res
    jobs = [dict(j, title=j["title"].strip()) for j in jobs if j["title"].strip()]
    titles = [j["title"] for j in jobs]
    res.update(titles=titles, jobs=jobs, count=res.pop("count_total", None) or len(titles))
    res["status"] = "live" if res["count"] else "empty"
    return res


def board_name(ats, slug, http):
    """Greenhouse gives the company's display name on a separate endpoint; one call, hits only."""
    if ats != "greenhouse":
        return None
    try:
        return (http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}") or {}).get("name")
    except Exception:
        return None


def matching_titles(job_titles, F):
    want = F["include_titles"]
    return [t for t in job_titles if any(title_rule.term_hits(w, t) for w in want)]


def matching_jobs(jobs, F):
    """(titles of postings that match your titles AND pass the location rule, count of title
    matches the location rule turned away)."""
    hit = [j for j in jobs if matching_titles([j["title"]], F)]
    ok = [j["title"] for j in hit if locations.location_ok(j, F)]
    return ok, len(hit) - len(ok)


def excluded_company(name, F):
    n = (name or "").lower()
    return any(x and str(x).lower() in n for x in (F.get("exclude_companies") or []))


# ============================================================================================
# boards.yaml: read, and append only (never rewrite a row the user wrote)
# ============================================================================================
def read_boards(path):
    import yaml
    text = path.read_text() if path.exists() else "boards:\n"
    data = yaml.safe_load(text) or {}
    rows = data.get("boards") if isinstance(data, dict) else data
    return text, [r for r in (rows or []) if isinstance(r, dict)]


def board_key(ats, slug):
    return f"{ats}:{urllib.parse.unquote(str(slug)).lower()}"


def existing_keys(rows):
    return {board_key(r.get("ats"), r.get("slug")) for r in rows if r.get("ats") and r.get("slug")}


def _row_line(r):
    return ("  - {company: %s, ats: %s, slug: %s, source: %s, added: %s}"
            % (json.dumps(r["company"]), r["ats"], json.dumps(r["slug"]),
               json.dumps(r["source"]), json.dumps(r["added"])))


def append_rows(path, new_rows):
    """Append rows under `boards:`. Safe: the file is re-parsed after the edit and written only if
    every old row is unchanged and exactly len(new_rows) rows were added. Returns (ok, message)."""
    import yaml
    if not new_rows:
        return True, "nothing to add"
    text, old = read_boards(path)
    lines = text.splitlines()
    keys = [i for i, ln in enumerate(lines) if re.match(r"^[A-Za-z_][\w-]*\s*:", ln)]
    if not keys or not lines[keys[-1]].startswith("boards"):
        return False, ("boards.yaml: `boards:` is not the last top-level key, so rows can't be appended "
                       "safely. Move `boards:` to the end of the file and run again.")
    i = keys[-1]
    if re.match(r"^boards\s*:\s*\[\s*\]\s*(#.*)?$", lines[i]):
        lines[i] = "boards:"
    elif not re.match(r"^boards\s*:\s*(#.*)?$", lines[i]):
        return False, "boards.yaml: `boards:` must be a block list (one `- {...}` line per company)."
    patched = "\n".join(lines).rstrip("\n") + "\n" + "\n".join(_row_line(r) for r in new_rows) + "\n"
    data = yaml.safe_load(patched) or {}
    rows = [r for r in (data.get("boards") or []) if isinstance(r, dict)]
    if rows[:len(old)] != old or len(rows) != len(old) + len(new_rows):
        return False, "post-edit check failed; boards.yaml NOT written"
    path.write_text(patched)
    return True, f"added {len(new_rows)} row(s) to {path.name}"


# ============================================================================================
# Config + cache
# ============================================================================================
def load_filters(path=FILTERS):
    import yaml
    F = yaml.safe_load(path.read_text()) or {}
    F["include_titles"] = [str(t).strip().lower() for t in (F.get("include_titles") or []) if str(t).strip()]
    return F


def titles_key(F):
    """Changes whenever your titles or location settings change, so 'no match' verdicts are redone."""
    text = "\n".join(sorted(F["include_titles"]))
    try:
        loc = locations.settings_key(F)
    except ValueError:
        loc = ""
    if loc != locations.settings_key({}):
        text += "\nloc:" + loc
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _jload(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def _jsave(p, obj):
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps(obj, indent=1))
    except Exception as e:
        log(f"[discover] could not write cache {p}: {e}")


class Ctx:
    def __init__(self, boards=BOARDS, filters=FILTERS, cache=CACHE_DIR, http=None, sleep=time.sleep,
                 now=None, F=None, clock=time.monotonic):
        self.boards, self.filters, self.cache = Path(boards), Path(filters), Path(cache)
        self.http = http or Http()
        self.sleep = sleep
        self.clock = clock
        self.deadline = None          # clock() value at which the whole run stops (None: no limit)
        self.advised = False          # FALLBACK_ADVICE already printed this run
        self.now = now or datetime.now(timezone.utc)
        self.F = F
        self.today = datetime.now().astimezone().date().isoformat()  # the user's own local date

    def left(self, until=None):
        """Seconds left before `until` (default: the run's deadline), or None when unbounded."""
        d = self.deadline if until is None else until
        return None if d is None else d - self.clock()

    def cap(self, timeout, until=None):
        """A network timeout that never runs past the deadline."""
        left = self.left(until)
        return timeout if left is None else max(1.0, min(timeout, left))

    def advise(self):
        if not self.advised:
            self.advised = True
            log("[sweep] " + FALLBACK_ADVICE)

    def filters_loaded(self):
        if self.F is None:
            self.F = load_filters(self.filters)
        return self.F


def _retry(ctx, fn, tries=3, waits=(5, 20), until=None, strikes=None):
    """Call fn, retrying a 429/5xx or a network error with back-off. Raises OutOfTime when `until`
    (or the run's deadline) has passed, and IndexDown when `strikes` (a one-item list shared by
    every call for one index domain) reaches INDEX_MAX_5XX failures in a row."""
    last = None
    for k in range(tries):
        left = ctx.left(until)
        if left is not None and left <= 0:
            raise OutOfTime()
        try:
            r = fn()
            if strikes is not None:
                strikes[0] = 0
            return r
        except HttpStatus as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        if strikes is not None:
            strikes[0] += 1
            if strikes[0] >= INDEX_MAX_5XX:
                raise IndexDown(f"{last} ({strikes[0]} failures in a row)")
        if k < tries - 1:
            wait = waits[min(k, len(waits) - 1)]
            left = ctx.left(until)
            ctx.sleep(wait if left is None else max(0.0, min(wait, left)))
    raise last


# ============================================================================================
# --sweep: Common Crawl harvest -> probe -> add matches
# ============================================================================================
def _best_case(found):
    """One board, several spellings of case: keep the most common one (ties: the lowercase one)."""
    best = {}
    for s, n in found.items():
        k = urllib.parse.unquote(s).lower()
        if k not in best or (n, s == s.lower()) > (found[best[k]], best[k] == best[k].lower()):
            best[k] = s
    return best


def _slugs_from(state, atses):
    """{ats: [slug, ...]}: every board name harvested so far for that ATS, including the names a
    previous crawl's harvest found (kept while a new crawl is being read)."""
    out = {}
    for ats in atses:
        found = {}
        for d in CDX_DOMAINS[ats]:
            for s, n in ((state.get("domains") or {}).get(d, {}).get("found") or {}).items():
                found[s] = found.get(s, 0) + n
        best = _best_case(found)
        for s in (state.get("carried") or {}).get(ats, []):
            best.setdefault(urllib.parse.unquote(s).lower(), s)
        out[ats] = sorted(best.values(), key=str.lower)
    return out


def _domain_done(st):
    return bool(st) and "pages" in st and st.get("next", 0) >= st["pages"]


def harvest(ctx, atses, refresh=False, crawl_id=None, until=None):
    """Board names from the Common Crawl index, cached in cache/cc-index.json PAGE BY PAGE, so a run
    that stops (its time budget, an index failure) continues from the same page next time. Returns
    (slugs_by_ats, notes, progress). Stops reading the index at `until`."""
    path = ctx.cache / "cc-index.json"
    cached = _jload(path, {})
    if "domains" not in cached:  # first run, or a cache from before page-level resume
        cached = {"domains": {}, "carried": cached.get("slugs") or {}}
    state = cached
    notes = []
    progress = {"pages_read": 0, "pages_total": 0, "complete": False, "stopped_for_time": False,
                "domains_down": []}

    def save():
        _jsave(path, state)
    try:
        ids = [crawl_id] if crawl_id else [c["id"] for c in _retry(
            ctx, lambda: ctx.http.get_json(COLLINFO, timeout=ctx.cap(60, until)), tries=2, waits=(3,),
            until=until)[:3]]
    except OutOfTime:
        progress["stopped_for_time"] = True
        notes.append("the time budget ran out before the index answered; used the boards already harvested")
        return _slugs_from(state, atses), notes, progress
    except Exception as e:
        ctx.advise()
        progress["domains_down"].append("index.commoncrawl.org")
        notes.append(f"Common Crawl index list unreachable ({e}); used the boards already harvested")
        return _slugs_from(state, atses), notes, progress
    newest = ids[0]
    if state.get("crawl_id") != newest or refresh:
        # a new crawl (or --refresh-index): read it from the start, keep the names found so far
        state = {"crawl_id": newest, "fetched": ctx.now.isoformat(), "domains": {},
                 "carried": _slugs_from(state, SWEEP_ATSES)}
        save()
    for ats in atses:
        for domain in CDX_DOMAINS[ats]:
            st = state["domains"].setdefault(domain, {})
            if _domain_done(st) or progress["stopped_for_time"]:
                continue
            strikes = [0]
            order = ([st["cid"]] if st.get("cid") in ids else []) + [c for c in ids if c != st.get("cid")]
            for cid in order:
                try:
                    _harvest_domain(ctx, cid, domain, ats, st, until, strikes, save)
                    if cid != newest:
                        notes.append(f"{domain}: newest crawl failed, used {cid}")
                    break
                except OutOfTime:
                    progress["stopped_for_time"] = True
                    break
                except IndexDown as e:
                    log(f"[sweep] index {domain}: {e}; skipping it this run")
                    break
                except Exception as e:
                    log(f"[sweep] index {cid} {domain}: {e}")
            if not _domain_done(st) and not progress["stopped_for_time"]:
                progress["domains_down"].append(domain)
                notes.append(f"{domain}: the Common Crawl index did not answer (it is often overloaded); "
                             f"skipped this run, tried again next run")
                ctx.advise()
    for st in state["domains"].values():
        progress["pages_read"] += st.get("next", 0)
        progress["pages_total"] += st.get("pages", 0)
    wanted = [d for a in atses for d in CDX_DOMAINS[a]]
    progress["complete"] = all(_domain_done(state["domains"].get(d)) for d in wanted)
    if progress["stopped_for_time"]:
        notes.append(f"the index harvest stopped at its share of the time budget ({progress['pages_read']} "
                     f"index pages read so far); the next run continues from there")
    elif progress["complete"]:
        notes.append(f"index harvest of {newest} is complete")
    save()
    out = _slugs_from(state, atses)
    for a in atses:
        log(f"[sweep] index: {len(out[a])} {a} boards so far")
    return out, notes, progress


def _harvest_domain(ctx, cid, domain, want_ats, st, until, strikes, save):
    """Read one domain's index pages from st['next'] on, updating st and saving after every page."""
    base = f"https://index.commoncrawl.org/{cid}-index?url={domain}/*&output=json"
    if st.get("cid") != cid or "pages" not in st:
        info = json.loads(_retry(ctx, lambda: ctx.http.get_text(base + "&showNumPages=true",
                                                                timeout=ctx.cap(120, until)),
                                 tries=2, waits=(3, 10), until=until, strikes=strikes))
        st.clear()
        st.update(cid=cid, pages=min(int(info.get("pages") or 0), INDEX_MAX_PAGES), next=0, found={})
        save()
    while st["next"] < st["pages"]:
        page = st["next"]
        log(f"[sweep] index {cid} {domain} page {page + 1}/{st['pages']}")
        text = _retry(ctx, lambda: ctx.http.get_text(f"{base}&fl=url&page={page}", timeout=ctx.cap(180, until)),
                      tries=2, waits=(3, 10), until=until, strikes=strikes)
        for line in text.splitlines():
            try:
                u = json.loads(line).get("url", "")
            except ValueError:
                continue
            ats, slug, _ = parse_board_url(u)
            if ats == want_ats and slug:
                st["found"][slug] = st["found"].get(slug, 0) + 1
        st["next"] = page + 1
        save()
        ctx.sleep(1.0)


def run_pool(ctx, jobs, workers, label):
    """Probe (ats, slug) pairs with bounded concurrency; yields results as they finish. Once the
    run's deadline passes, the boards not yet started come back as status 'skipped' (unchecked)."""
    def task(ats, slug):
        left = ctx.left()
        if left is not None and left <= 0:
            return {"ats": ats, "slug": slug, "status": "skipped", "count": 0, "titles": [], "jobs": [],
                    "name": None, "error": "time budget spent"}
        r = probe(ats, slug, ctx.http, sleep=ctx.sleep)
        ctx.sleep(PAUSE_SECONDS)
        return r
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as ex:
        futs = [ex.submit(task, a, s) for a, s in jobs]
        for f in as_completed(futs):
            done += 1
            if done % 10 == 0 or done == len(futs):
                log(f"[{label}] checked {done}/{len(futs)}")
            yield f.result()


def sweep(ctx, args):
    F = ctx.filters_loaded()
    t0 = ctx.clock()
    minutes = getattr(args, "max_minutes", None)
    if minutes and minutes > 0:
        ctx.deadline = t0 + minutes * 60
        harvest_until = t0 + minutes * 60 * HARVEST_SHARE
    else:
        harvest_until = None
    atses = [a for a in (args.ats.split(",") if args.ats else SWEEP_ATSES) if a in SWEEP_ATSES]
    slugs, notes, progress = harvest(ctx, atses, refresh=args.refresh_index, crawl_id=args.crawl_id,
                                     until=harvest_until)
    _, rows = read_boards(ctx.boards)
    have = existing_keys(rows)
    pfile = ctx.cache / "sweep-checked.json"
    checked = _jload(pfile, {})
    tk = titles_key(F)
    if checked.get("titles_key") != tk:  # titles or location changed: "no match" verdicts are stale
        checked = {"titles_key": tk, "boards": {k: v for k, v in checked.get("boards", {}).items()
                                                if v.get("result") in ("dead", "empty")}}
    checked.setdefault("boards", {})

    def due(key):
        v = checked["boards"].get(key)
        if not v:
            return True
        age = ctx.now - datetime.fromisoformat(v["at"])
        if v["result"] in ("dead", "empty"):
            return age > timedelta(days=DEAD_RECHECK_DAYS)
        if v["result"] == "nomatch":
            return age > timedelta(days=RECHECK_DAYS)
        return v["result"] == "error"

    queues = {}
    for ats in atses:
        q = [s for s in slugs.get(ats, []) if board_key(ats, s) not in have and due(board_key(ats, s))]
        random.Random(f"{ats}:{len(slugs.get(ats, []))}").shuffle(q)  # stable order between runs
        queues[ats] = q
    pending = sum(len(q) for q in queues.values())
    order = []
    while len(order) < args.limit and any(queues.values()):
        for ats in atses:
            if queues[ats] and len(order) < args.limit:
                order.append((ats, queues[ats].pop(0)))
    log(f"[sweep] {pending} boards not yet checked; checking up to {len(order)} this run")

    hits = []
    counts = {"match": 0, "nomatch": 0, "location": 0, "dead": 0, "empty": 0, "error": 0, "skipped": 0}
    n = 0
    for r in run_pool(ctx, order, args.workers, "sweep"):
        key = board_key(r["ats"], r["slug"])
        if r["status"] == "skipped":  # the time budget ran out first: stays due for the next run
            counts["skipped"] += 1
            continue
        n += 1
        if r["status"] == "live":
            m, turned_away = matching_jobs(r["jobs"], F)
            verdict = "match" if m else "nomatch"
            if m:
                hits.append(dict(r, matching=m))
            elif turned_away:
                counts["location"] += 1
        else:
            verdict = r["status"]
        counts[verdict] += 1
        checked["boards"][key] = {"at": ctx.now.isoformat(), "result": verdict}
        if n % 25 == 0 and not args.dry_run:
            _jsave(pfile, checked)

    new_rows, skipped = [], []
    for h in sorted(hits, key=lambda x: (x["ats"], x["slug"].lower())):
        name = h["name"] or board_name(h["ats"], h["slug"], ctx.http) or _pretty(h["slug"])
        if excluded_company(name, F):
            skipped.append(f"{name}: in your exclude_companies")
            continue
        new_rows.append({"company": " ".join(str(name).split())[:80], "ats": h["ats"], "slug": h["slug"],
                         "source": "discover:sweep", "added": ctx.today,
                         "_matching": h["matching"][:3], "_open": h["count"]})
    write = (True, "dry run: boards.yaml not changed") if args.dry_run else \
        append_rows(ctx.boards, [{k: v for k, v in r.items() if not k.startswith("_")} for r in new_rows])
    if not args.dry_run:
        _jsave(pfile, checked)
    checked_n = len(order) - counts["skipped"]
    remaining = pending - checked_n
    elapsed = round(ctx.clock() - t0)
    if not any(slugs.get(a) for a in atses):
        if progress["domains_down"]:
            summary = ("The Common Crawl index did not answer this run, so no boards were checked. "
                       + FALLBACK_ADVICE + ".")
        else:
            summary = ("The index harvest used this run's time budget before any board names came in. "
                       "Run --sweep again to continue it (the first run is the slowest), or raise "
                       "--max-minutes.")
    else:
        summary = (f"Checked {checked_n} boards: {len(new_rows)} had postings matching your titles in a "
                   f"place you can work and {'would be' if args.dry_run else 'were'} added to boards.yaml, "
                   f"{counts['nomatch']} had none ({counts['location']} of those only in places your "
                   f"location settings rule out), {counts['dead'] + counts['empty']} were closed or empty, "
                   f"{counts['error']} failed. {remaining} boards are left to check; run --sweep again "
                   f"to continue.")
        if counts["skipped"]:
            summary += (f" {counts['skipped']} boards were not reached before the time budget ran out "
                        f"(--max-minutes).")
        if progress["domains_down"]:
            summary += " Part of the index did not answer: " + FALLBACK_ADVICE + "."
    summary += f" ({elapsed}s.)"
    return {
        "mode": "sweep", "index_notes": notes,
        "index_boards": {a: len(slugs.get(a, [])) for a in atses},
        "index_progress": progress, "elapsed_seconds": elapsed,
        "checked": checked_n, "results": counts, "added": [
            {"company": r["company"], "ats": r["ats"], "slug": r["slug"], "open_postings": r["_open"],
             "matching_titles": r["_matching"]} for r in new_rows],
        "skipped": skipped, "remaining_unchecked": remaining, "boards_yaml": write[1], "ok": write[0],
        "summary": summary,
    }


# ============================================================================================
# --urls and --company: check specific boards and add the live ones
# ============================================================================================
def _add_checked(ctx, args, candidates, mode, F):
    """candidates: [(ats, slug, origin, expected_name_or_None)]. Probes each unique board once."""
    _, rows = read_boards(ctx.boards)
    have = existing_keys(rows)
    uniq, already = {}, []
    for ats, slug, origin, expect in candidates:
        k = board_key(ats, slug)
        if k in have:
            already.append({"origin": origin, "ats": ats, "slug": slug})
        elif k not in uniq:
            uniq[k] = (ats, slug, origin, expect)
    order = [(a, s) for a, s, _, _ in uniq.values()][:args.limit]
    results = {board_key(r["ats"], r["slug"]): r for r in run_pool(ctx, order, args.workers, mode)}
    added, misses = [], []
    for k, (ats, slug, origin, expect) in uniq.items():
        r = results.get(k)
        if not r:
            misses.append({"origin": origin, "ats": ats, "slug": slug, "why": "not checked: over --limit"})
            continue
        if r["status"] != "live":
            why = {"dead": "no board there", "empty": "board exists but has no open postings"}.get(r["status"], r["error"] or "error")
            misses.append({"origin": origin, "ats": ats, "slug": slug, "why": why})
            continue
        name = r["name"] or board_name(ats, slug, ctx.http)
        if expect and name and not _same_company(expect, name):
            misses.append({"origin": origin, "ats": ats, "slug": slug,
                           "why": f"that board belongs to '{name}', not '{expect}'; not added"})
            continue
        company = expect or name or _pretty(slug)
        if excluded_company(company, F):
            misses.append({"origin": origin, "ats": ats, "slug": slug, "why": "in your exclude_companies"})
            continue
        added.append({"company": " ".join(str(company).split())[:80], "ats": ats, "slug": slug,
                      "source": f"discover:{mode}", "added": ctx.today, "_open": r["count"],
                      "_matching": matching_jobs(r["jobs"], F)[0][:3] if F["include_titles"] else [],
                      "_name_confirmed": bool(name)})
    write = (True, "dry run: boards.yaml not changed") if args.dry_run else \
        append_rows(ctx.boards, [{k: v for k, v in r.items() if not k.startswith("_")} for r in added])
    return {"mode": mode, "ok": write[0], "boards_yaml": write[1], "already_listed": already,
            "added": [{"company": r["company"], "ats": r["ats"], "slug": r["slug"], "open_postings": r["_open"],
                       "matching_titles": r["_matching"],
                       "name_confirmed_by_api": r["_name_confirmed"]} for r in added],
            "misses": misses,
            "summary": (f"{len(added)} board(s) {'would be' if args.dry_run else ''} added, "
                        f"{len(already)} already listed, {len(misses)} not added (see misses).").replace("  ", " ")}


def _norm_words(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in NAME_SUFFIXES]


def _same_company(a, b):
    wa, wb = _norm_words(a), _norm_words(b)
    if not wa or not wb:
        return True
    n = min(len(wa), len(wb))
    return "".join(wa) == "".join(wb) or wa[:n] == wb[:n]  # equal, or one name starts the other


def slug_candidates(name):
    words = re.findall(r"[a-z0-9]+", name.lower().replace("&", " and "))
    core = list(words)
    while core and core[-1] in NAME_SUFFIXES:
        core.pop()
    if core and core[0] == "the" and len(core) > 1:
        core = core[1:]
    out = []
    for ws in (words, core):
        for c in ("".join(ws), "-".join(ws)):
            if c and c not in out:
                out.append(c)
    return out[:4]


def company_mode(ctx, args):
    F = ctx.filters_loaded()
    cands = []
    for name in args.company:
        for s in slug_candidates(name):
            for ats in GUESS_ATSES:
                slug = s
                if ats == "smartrecruiters":  # its company ids are usually CamelCase
                    slug = "".join(w.capitalize() for w in re.split(r"-", s)) if "-" in s else s.capitalize()
                cands.append((ats, slug, name, name))
    # keep only the first hit per (company, ats): probe all, then filter
    res = _add_checked(ctx, argparse.Namespace(**dict(vars(args), dry_run=True)), cands, "company", F)
    firsts, seen = [], set()
    for r in res["added"]:
        key = (r["company"].lower(), r["ats"])
        if key not in seen:
            seen.add(key)
            firsts.append(r)
    found = {r["company"].lower() for r in firsts}
    failed = [m for m in res["misses"] if m["why"] not in ("no board there", "board exists but has no open postings")
              and "belongs to" not in m["why"]]
    not_found = [n for n in args.company if " ".join(n.split())[:80].lower() not in found]
    unsure = sorted({m["origin"] for m in failed if m["origin"] in not_found})
    rows = [{"company": r["company"], "ats": r["ats"], "slug": r["slug"], "source": "discover:company",
             "added": ctx.today} for r in firsts]
    write = (True, "dry run: boards.yaml not changed") if args.dry_run else append_rows(ctx.boards, rows)
    wrong = [m for m in res["misses"] if "belongs to" in m["why"]]
    return {"mode": "company", "ok": write[0], "boards_yaml": write[1], "added": firsts,
            "already_listed": res["already_listed"], "wrong_company_boards": wrong,
            "not_found": not_found, "check_failed": failed,
            "summary": (f"{len(firsts)} board(s) found for {len(args.company) - len(not_found)} of "
                        f"{len(args.company)} companies. Not found on any guessable ATS: "
                        f"{', '.join(not_found) or 'none'}"
                        + (f" (some checks for {', '.join(unsure)} failed on the network, so run again "
                           f"before concluding)" if unsure else "")
                        + ("." if not not_found else ". A company may use Workday, another ATS, or a "
                           "board name that can't be guessed: search for its careers page and pass that "
                           "URL to --urls."))}


def urls_mode(ctx, args):
    F = ctx.filters_loaded()
    text = sys.stdin.read() if args.urls == "-" else Path(args.urls).read_text()
    cands, unresolved = [], []
    for u in extract_urls(text):
        ats, slug, why = parse_board_url(u)
        if ats:
            cands.append((ats, slug, u, None))
        else:
            unresolved.append({"url": u, "why": why})
    res = _add_checked(ctx, args, cands, "urls", F)
    res["unresolved"] = unresolved
    res["summary"] += f" {len(unresolved)} URL(s) were not on a supported ATS."
    return res


# ============================================================================================
# --queries
# ============================================================================================
QUERY_SITES = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
               "jobs.smartrecruiters.com", "apply.workable.com", "myworkdayjobs.com")


def queries_mode(ctx, args):
    F = ctx.filters_loaded()
    qs = []
    for t in F["include_titles"]:
        qs += [f'site:{s} "{t}"' for s in QUERY_SITES]
        qs.append(f'"{t}" jobs careers greenhouse OR lever OR ashbyhq OR workable OR myworkdayjobs')
        qs += [f'"{t}" jobs {c} careers' for c in (args.company or [])]
    note = ("Run these with your web search tool, collect every result URL, and pipe them in: "
            "python3 pipeline/job-crawler/discover.py --urls - . Some search tools ignore `site:`; if "
            "results come back off-site, run the plain '<title> jobs <company> careers' form instead "
            "(pass company names with --company to --queries to get those lines).")
    return {"mode": "queries", "note": note, "queries": qs}


# ============================================================================================
# Output + CLI
# ============================================================================================
def print_human(res):
    if res["mode"] == "queries":
        print("# " + res["note"])
        print("\n".join(res["queries"]))
        return
    print(res["summary"])
    for r in res.get("added", []):
        extra = f", e.g. {r['matching_titles'][0]}" if r.get("matching_titles") else ""
        print(f"  + {r['company']} ({r['ats']}: {r['slug']}): {r['open_postings']} open{extra}")
    shown = res.get("wrong_company_boards", []) + res.get("check_failed", []) if res["mode"] == "company" \
        else res.get("misses", [])
    for m in shown:
        print(f"  - {m['ats']}: {m['slug']}: {m['why']}")
    for u in res.get("unresolved", []):
        print(f"  ? {u['url']}: {u['why']}")
    for s in res.get("skipped", []):
        print(f"  - {s}")
    for n in res.get("index_notes", []):
        print(f"  note: {n}")
    print(res.get("boards_yaml", ""))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Find company job boards and add the checked ones to boards.yaml.",
        epilog="A --sweep run stops after --max-minutes (3 by default) and continues where it stopped "
               "on the next run. The first run is the slowest: it reads the Common Crawl index before "
               "checking boards, which can take a few runs when the index is slow. Later runs take 1 to "
               "3 minutes. If the index is down, use --company or --queries plus --urls instead.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sweep", action="store_true", help="harvest boards from Common Crawl and add those hiring for your titles")
    g.add_argument("--urls", metavar="FILE|-", help="job/careers URLs to resolve, check and add")
    g.add_argument("--queries", action="store_true", help="print web-search queries for your titles")
    g.add_argument("--selftest", action="store_true", help="offline selftest (no network)")
    ap.add_argument("--company", nargs="+", metavar="NAME", help="guess, check and add these companies' boards")
    ap.add_argument("--limit", type=int, default=None,
                    help=f"most boards to check against their APIs this run (sweep default "
                         f"{DEFAULT_SWEEP_LIMIT}); it does not bound the index harvest, --max-minutes does")
    ap.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES,
                    help=f"--sweep's whole time budget in minutes, index harvest included (default "
                         f"{DEFAULT_MAX_MINUTES:g}; 0 = no limit). The run stops there and the next run "
                         f"continues where it stopped. The first run is the slowest")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--ats", default=None, help="sweep only these ATSes, comma-separated")
    ap.add_argument("--dry-run", action="store_true", help="report what would be added; change nothing")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--refresh-index", action="store_true", help="re-harvest the Common Crawl index")
    ap.add_argument("--crawl-id", default=None, help="use this Common Crawl id instead of the newest")
    args = ap.parse_args(argv)
    # --company is a mode on its own, or adds company-specific lines to --queries
    mode = ("selftest" if args.selftest else "sweep" if args.sweep else "urls" if args.urls
            else "queries" if args.queries else "company" if args.company else None)
    if mode is None:
        ap.error("choose one of --sweep, --urls, --company, --queries, --selftest")
    if mode in ("sweep", "urls") and args.company:
        ap.error("--company is its own mode (or a modifier of --queries)")
    if mode == "selftest":
        return _selftest()
    if args.limit is None:
        args.limit = DEFAULT_SWEEP_LIMIT if mode == "sweep" else 200
    ctx = Ctx()
    F = ctx.filters_loaded()
    try:
        locations.settings(F)
    except ValueError as e:
        print(f"discover: {e}", file=sys.stderr)
        return 2
    if not F["include_titles"] and mode in ("sweep", "queries"):
        print("No job titles set: add your role titles under include_titles in "
              "pipeline/job-crawler/filters.yaml first (discovery matches boards against them).", file=sys.stderr)
        return 2
    try:
        res = {"sweep": sweep, "urls": urls_mode, "company": company_mode, "queries": queries_mode}[mode](ctx, args)
    except RuntimeError as e:
        print(f"discover: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print_human(res)
    return 0 if res.get("ok", True) else 1


# ============================================================================================
# Offline selftest: synthetic fixtures, a fake HTTP layer, a temp boards.yaml. No network.
# ============================================================================================
class FakeHttp:
    """url-substring -> response (dict/list/str) or an int HTTP status. Any URL not listed is a 404.
    Real network is never touched."""
    def __init__(self, routes, clock=None, step=0.0):
        self.routes = routes
        self.calls = []
        self.clock, self.step = clock, step   # a FakeClock advanced by `step` seconds per call

    def _find(self, url):
        self.calls.append(url)
        if self.clock:
            self.clock.t += self.step
        for key, val in self.routes.items():
            if key in url:
                if isinstance(val, int):
                    raise HttpStatus(val, url)
                return val
        raise HttpStatus(404, url)

    def get_json(self, url, timeout=None):
        v = self._find(url)
        return json.loads(v) if isinstance(v, str) else v

    def get_text(self, url, timeout=None):
        v = self._find(url)
        return v if isinstance(v, str) else json.dumps(v)

    def post_json(self, url, body, timeout=None):
        return self.get_json(url)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


FIXTURE_BOARDS = """# header comment the user wrote
boards:
  # Add your own companies below.
  - {company: "Acme", ats: greenhouse, slug: "acme"}
"""


def _fixture_routes():
    cdx_page = "\n".join(json.dumps({"url": u}) for u in [
        "https://boards.greenhouse.io/globex/jobs/123", "https://boards.greenhouse.io/acme/jobs/9",
        "https://boards.greenhouse.io/embed/job_app?for=initech", "https://boards.greenhouse.io/deadco",
        "https://jobs.lever.co/northwind/abc-def", "https://jobs.lever.co/Northwind/zzz"])
    return {
        "collinfo.json": [{"id": "CC-MAIN-2099-01"}, {"id": "CC-MAIN-2098-52"}],
        "showNumPages=true": {"pages": 1, "pageSize": 5, "blocks": 1},
        "&fl=url&page=0": cdx_page,
        "boards-api.greenhouse.io/v1/boards/globex/jobs": {"jobs": [{"title": "Senior Data Analyst"}, {"title": "Chef"}]},
        "boards-api.greenhouse.io/v1/boards/globex": {"name": "Globex Corporation"},
        "boards-api.greenhouse.io/v1/boards/initech/jobs": {"jobs": [{"title": "Welder"}]},
        "boards-api.greenhouse.io/v1/boards/deadco/jobs": 404,
        "api.lever.co/v0/postings/northwind": [{"text": "Data Analyst II"}],
        "apply.workable.com/api/v1/widget/accounts/mirror": {"name": "Mirror", "jobs": [{"title": "Nurse"}]},
        "fathom.wd5.myworkdayjobs.com/wday/cxs/fathom/External/jobs": {"total": 3, "jobPostings": [{"title": "Data Analyst"}]},
        "api.ashbyhq.com/posting-api/job-board/mirror": {"jobs": []},
    }


def _selftest():
    import tempfile
    # never touch the network, even by mistake
    def _no_net(*a, **k):
        raise AssertionError("selftest tried to use the network")
    real_urlopen, urllib.request.urlopen = urllib.request.urlopen, _no_net
    try:
        # 1) URL parsing, all six ATSes
        P = lambda u: parse_board_url(u)[:2]
        assert P("https://boards.greenhouse.io/acme/jobs/123") == ("greenhouse", "acme")
        assert P("https://job-boards.greenhouse.io/acme/jobs/1?gh_jid=1") == ("greenhouse", "acme")
        assert P("boards.greenhouse.io/embed/job_app?for=initech&token=5") == ("greenhouse", "initech")
        assert P("https://boards-api.greenhouse.io/v1/boards/globex/jobs") == ("greenhouse", "globex")
        assert P("https://jobs.lever.co/northwind/0b15-uuid/apply") == ("lever", "northwind")
        assert P("https://jobs.ashbyhq.com/Anthos%20Capital/uuid") == ("ashby", "Anthos%20Capital")
        assert P("https://jobs.smartrecruiters.com/AcmeCorp/7443") == ("smartrecruiters", "AcmeCorp")
        assert P("https://apply.workable.com/mirror/j/ABC123/") == ("workable", "mirror")
        assert P("https://apply.workable.com/api/v1/widget/accounts/mirror") == ("workable", "mirror")
        assert P("https://fathom.wd5.myworkdayjobs.com/en-US/External/job/Denver/Analyst_R1") == ("workday", "fathom/wd5/External")
        assert P("https://fathom.wd5.myworkdayjobs.com/External") == ("workday", "fathom/wd5/External")
        assert P("https://wd1.myworkdaysite.com/recruiting/fathom/Careers/job/x") == ("workday", "fathom/wd1/Careers")
        assert parse_board_url("https://www.example.com/careers?gh_jid=55")[0] is None
        assert parse_board_url("https://jobs.eu.lever.co/acme")[0] is None
        assert parse_board_url("https://example.com/jobs")[0] is None
        assert extract_urls("see jobs.lever.co/northwind and https://apply.workable.com/mirror/ ok") == [
            "https://apply.workable.com/mirror/", "jobs.lever.co/northwind"]
        assert slug_candidates("The Globex Corporation") == ["theglobexcorporation", "the-globex-corporation", "globex"]
        assert _same_company("Globex", "Globex Corporation") and not _same_company("Globex", "Initech")

        tmp = Path(tempfile.mkdtemp())
        F = {"include_titles": ["data analyst"], "exclude_companies": []}

        def ctx_for(routes):
            b = tmp / "boards.yaml"
            b.write_text(FIXTURE_BOARDS)
            return Ctx(boards=b, cache=tmp / "cache", http=FakeHttp(routes), sleep=lambda s: None,
                       now=datetime(2099, 1, 2, tzinfo=timezone.utc), F=dict(F))

        def ns(**kw):
            base = dict(limit=50, workers=2, ats=None, dry_run=False, refresh_index=False, crawl_id=None, company=None)
            base.update(kw)
            return argparse.Namespace(**base)

        # 2) sweep: harvest -> probe -> add only title matches; never touch the user's row
        ctx = ctx_for(_fixture_routes())
        res = sweep(ctx, ns(ats="greenhouse,lever"))
        added = {(r["ats"], r["slug"]) for r in res["added"]}
        assert added == {("greenhouse", "globex"), ("lever", "northwind")}, res
        assert res["results"]["nomatch"] == 1 and res["results"]["dead"] == 1, res["results"]
        text = ctx.boards.read_text()
        assert text.startswith(FIXTURE_BOARDS), "the user's file must be kept byte for byte"
        assert 'company: "Globex Corporation", ats: greenhouse, slug: "globex", source: "discover:sweep"' in text
        _, rows = read_boards(ctx.boards)
        assert rows[0] == {"company": "Acme", "ats": "greenhouse", "slug": "acme"} and len(rows) == 3
        # 3) resumable: a second sweep re-checks nothing and adds nothing
        calls_before = len(ctx.http.calls)
        res2 = sweep(ctx, ns(ats="greenhouse,lever"))
        assert res2["checked"] == 0 and not res2["added"], res2
        assert not any("boards-api" in c or "api.lever" in c for c in ctx.http.calls[calls_before:])
        assert len(read_boards(ctx.boards)[1]) == 3
        # 3b) an index that keeps failing is reported, and not cached as "no boards"
        routes = _fixture_routes()
        routes["showNumPages=true"] = 504
        ctx = ctx_for(routes)
        res = sweep(ctx, ns(ats="ashby"))
        assert res["checked"] == 0 and "did not answer" in res["summary"], res
        assert not _jload(ctx.cache / "cc-index.json", {})["domains"]["jobs.ashbyhq.com"].get("pages")
        # 3c) fail fast: a domain is given up after INDEX_MAX_5XX failures in a row, across crawl
        #     ids, and the fallback advice is printed the moment the index fails, not at the end
        index_calls = [c for c in ctx.http.calls if "jobs.ashbyhq.com" in c and "showNumPages" in c]
        assert len(index_calls) == INDEX_MAX_5XX, index_calls
        assert ctx.advised and "--company" in res["summary"] and "--urls" in res["summary"]
        assert res["index_progress"]["domains_down"] == ["jobs.ashbyhq.com"]
        # 3d) the time budget: a slow index stops the harvest at its share of --max-minutes, the
        #     run ends inside the budget, and the next run continues from the same index page
        routes = _fixture_routes()
        routes["showNumPages=true"] = {"pages": 6, "pageSize": 5, "blocks": 6}
        for k in range(6):
            routes[f"&fl=url&page={k}"] = json.dumps({"url": f"https://jobs.lever.co/board{k}/x"})
        clock = FakeClock()
        b = tmp / "boards.yaml"
        b.write_text(FIXTURE_BOARDS)
        ctx = Ctx(boards=b, cache=tmp / "cache-slow", http=FakeHttp(routes, clock, 40.0), sleep=lambda s: None,
                  now=datetime(2099, 1, 2, tzinfo=timezone.utc), F=dict(F), clock=clock)
        res = sweep(ctx, ns(ats="lever", max_minutes=3))
        prog = res["index_progress"]
        assert prog["stopped_for_time"] and 0 < prog["pages_read"] < 6, prog
        assert clock.t <= 3 * 60 + 40, clock.t   # at most one call past the budget
        read_first = prog["pages_read"]
        ctx2 = Ctx(boards=b, cache=tmp / "cache-slow", http=FakeHttp(routes), sleep=lambda s: None,
                   now=datetime(2099, 1, 2, tzinfo=timezone.utc), F=dict(F))
        res = sweep(ctx2, ns(ats="lever", max_minutes=0))
        assert res["index_progress"]["complete"], res["index_progress"]
        again = [c for c in ctx2.http.calls if "&fl=url&page=" in c]
        assert len(again) == 6 - read_first, again        # resumed, no page read twice
        assert res["index_boards"]["lever"] == 6
        # 3e) the location rule: a board whose only matching postings are somewhere you can't work
        #     is not added (and is counted as such); the same rule crawl.py applies
        routes = _fixture_routes()
        routes["boards-api.greenhouse.io/v1/boards/globex/jobs"] = {"jobs": [
            {"title": "Data Analyst", "location": {"name": "Dublin, Ireland"}}]}
        ctx = ctx_for(routes)
        ctx.F.update(require_us=True, us_markers=["united states"], location_block=["ireland", "dublin"])
        res = sweep(ctx, ns(ats="greenhouse,lever"))
        assert {(r["ats"], r["slug"]) for r in res["added"]} == {("lever", "northwind")}, res
        assert res["results"]["location"] == 1, res["results"]
        ctx = ctx_for(_fixture_routes())
        ctx.F.update(remote_ok=True, onsite_ok="home_metros", home_metros=["denver"])
        routes = ctx.http.routes
        routes["boards-api.greenhouse.io/v1/boards/globex/jobs"] = {"jobs": [
            {"title": "Data Analyst", "location": {"name": "Denver, CO"}}]}
        routes["api.lever.co/v0/postings/northwind"] = [{"text": "Data Analyst", "categories": {"location": "Austin, TX"}}]
        res = sweep(ctx, ns(ats="greenhouse,lever"))
        assert {(r["ats"], r["slug"]) for r in res["added"]} == {("greenhouse", "globex")}, res
        # 4) dry run changes nothing
        ctx = ctx_for(_fixture_routes())
        sweep(ctx, ns(ats="greenhouse", dry_run=True))
        assert ctx.boards.read_text() == FIXTURE_BOARDS
        # 5) --urls: resolve, verify, dedupe, add; report the rest honestly
        ctx = ctx_for(_fixture_routes())
        src = tmp / "urls.txt"
        src.write_text("https://boards.greenhouse.io/acme/jobs/1\nhttps://jobs.lever.co/northwind/x\n"
                       "https://jobs.lever.co/northwind/y\nhttps://fathom.wd5.myworkdayjobs.com/en-US/External/job/1\n"
                       "https://jobs.ashbyhq.com/mirror\nhttps://www.example.com/careers?gh_jid=5\n")
        res = urls_mode(ctx, ns(urls=str(src)))
        assert {(r["ats"], r["slug"]) for r in res["added"]} == {("lever", "northwind"), ("workday", "fathom/wd5/External")}, res
        assert len(res["already_listed"]) == 1 and len(res["unresolved"]) == 1
        assert any(m["slug"] == "mirror" and "no open postings" in m["why"] for m in res["misses"])
        assert 'slug: "fathom/wd5/External", source: "discover:urls"' in ctx.boards.read_text()
        # 6) --company: guesses, first hit per ATS, honest misses, wrong-company guard
        routes = _fixture_routes()
        routes["apply.workable.com/api/v1/widget/accounts/globex"] = {"name": "Northwind Traders", "jobs": [{"title": "Data Analyst"}]}
        ctx = ctx_for(routes)
        res = company_mode(ctx, ns(company=["Globex", "Nonexistent Widgets"]))
        assert [(r["ats"], r["slug"]) for r in res["added"]] == [("greenhouse", "globex")], res
        assert res["not_found"] == ["Nonexistent Widgets"]
        assert any("belongs to" in m["why"] for m in res["wrong_company_boards"])
        # 7) a file whose boards: is not last is refused, untouched
        bad = tmp / "bad.yaml"
        bad.write_text("boards:\n  - {company: A, ats: lever, slug: a}\nother: 1\n")
        ok, _ = append_rows(bad, [{"company": "B", "ats": "lever", "slug": "b", "source": "x", "added": "d"}])
        assert not ok and bad.read_text().endswith("other: 1\n")
        empty = tmp / "empty.yaml"
        empty.write_text("# only comments\nboards: []\n")
        ok, _ = append_rows(empty, [{"company": "B", "ats": "lever", "slug": "b", "source": "x", "added": "d"}])
        assert ok and len(read_boards(empty)[1]) == 1
        # 8) queries carry the plain-search fallback note
        q = queries_mode(ctx_for({}), ns(company=["Globex"]))
        assert any(x.startswith("site:jobs.lever.co") for x in q["queries"]) and "ignore" in q["note"]
        assert '"data analyst" jobs Globex careers' in q["queries"]
    finally:
        urllib.request.urlopen = real_urlopen
    print("discover.py selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
