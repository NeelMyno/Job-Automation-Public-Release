#!/usr/bin/env python3
"""
Free job APIs, read by crawl.py next to the company ATS boards and Hacker News.

Each source here is a public JSON or RSS feed that a person may read for their own job search.
`sources.yaml` turns each one on or off and holds its settings; the terms and limits of each source
are summarized in that file's comments. Every job keeps its ORIGINAL link (several sources require
that) and carries a `source` id, so the feed can name the source on every row.

Politeness, enforced here rather than left to good intentions:
  * Each source has a minimum interval between fetches: the larger of `min_interval_minutes` in
    sources.yaml and the floor in FLOOR_MINUTES below (taken from that source's own terms). A run
    inside the interval does NOT call the source again. It reuses the jobs cached from the last
    successful fetch and says so in the crawl report, so frequent runs stay polite.
  * Search sources are queried one title at a time, a few seconds apart, capped by `max_queries`.
    A title a source cannot search is adapted or skipped for that source only: Jobicy answers
    HTTP 400 to a tag outside 3 to 20 characters, so "rn" is not sent there and a longer title is
    sent as its last words that fit ("journeyman electrician" as "electrician"). crawl.py still
    matches every job against your full titles.
  * One failed query does not lose the others: the results that came back are kept, and the source
    counts as failed only when every query failed. A rate limit (HTTP 429) stops that source's
    queries for this run at once.
  * A failed or rate-limited call still counts as an attempt, so a broken source is not hammered.

HONEST BY CONSTRUCTION (same as crawl.py): this module only copies real fields from real postings.
A field a source does not give is left empty, never guessed.

Keys: no source here needs one, except USAJOBS, which reads USAJOBS_API_KEY and USAJOBS_EMAIL from
the environment. A key is never read from, or written to, any file in this repo.

Run `python3 sources.py --selftest` for an offline check (synthetic fixtures, no network).
"""
import json, os, re, sys, time, html, urllib.request, urllib.error, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from pathlib import Path

from http_util import read_url, UA  # sibling module: gzip + retry on a cut-off read
import config_files  # sibling module: reads the settings files, with plain errors

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
STATE_NAME = "sources-state.json"
CONFIG_ENTRY = "sources-config"  # report entry for a problem in sources.yaml
NOT_SOURCES = ("cache", CONFIG_ENTRY)  # report entries that are notes about this run, not job sources

# Display name and home page of each source, for attribution in the feed.
LABELS = {
    "himalayas": "Himalayas", "jobicy": "Jobicy", "remotive": "Remotive", "remoteok": "Remote OK",
    "themuse": "The Muse", "weworkremotely": "We Work Remotely", "usajobs": "USAJOBS",
}
HOMEPAGES = {
    "himalayas": "https://himalayas.app", "jobicy": "https://jobicy.com",
    "remotive": "https://remotive.com", "remoteok": "https://remoteok.com",
    "themuse": "https://www.themuse.com", "weworkremotely": "https://weworkremotely.com",
    "usajobs": "https://www.usajobs.gov",
}
# Minimum minutes between two fetches of a source. sources.yaml may raise these, never lower them.
#   jobicy: "one automated pass per hour" (its feed docs).  remotive: "about 4 times a day".
#   The rest state no number (or were not read); one fetch an hour is a polite default.
FLOOR_MINUTES = {"himalayas": 60, "jobicy": 60, "remotive": 360, "remoteok": 60,
                 "themuse": 60, "weworkremotely": 60, "usajobs": 60}
# Used when sources.yaml is missing or leaves a source out. Mirrors the shipped sources.yaml.
DEFAULTS = {
    "himalayas": {"enabled": True, "country": "US", "max_queries": 5},
    "jobicy": {"enabled": True, "geo": "usa", "count": 50, "max_queries": 5},
    "remotive": {"enabled": True},
    "remoteok": {"enabled": True},
    "themuse": {"enabled": False, "pages": 2},
    "weworkremotely": {"enabled": False},
    "usajobs": {"enabled": True, "max_queries": 5},
}
ORDER = list(LABELS)
# Sources that list remote jobs only. With remote_ok: false nearly all their jobs fail the location
# rule, and crawl.py says so in its hints when these are the only sources that returned anything.
REMOTE_ONLY = frozenset({"himalayas", "jobicy", "remotive", "remoteok", "weworkremotely"})
QUERY_GAP_SECONDS = 2.0
DESC_MAX = 4000


class SourceSkip(Exception):
    """Raised by a fetcher that cannot run for a reason the user should see (e.g. a missing key)."""


class Partial(list):
    """A fetcher's jobs when some of its queries failed: the list of jobs, plus `errors`, one short
    line per failed query, for the crawl report."""
    def __init__(self, jobs=(), errors=()):
        super().__init__(jobs)
        self.errors = list(errors)


# Shortest and longest search term each source accepts. Jobicy answers HTTP 400 outside 3 to 20.
MIN_QUERY_CHARS = {"jobicy": 3}
MAX_QUERY_CHARS = {"jobicy": 20}


# small helpers
def http_get(url, headers=None, timeout=25, raw=False):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = read_url(urllib.request.Request(url, headers=h), timeout)
    return body if raw else json.loads(body)


def _clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    return html.unescape(re.sub(r"\s+", " ", s)).strip()[:DESC_MAX]


def to_dt(v):
    """Epoch seconds or ms (int or digit string), ISO-8601, or RFC 822 -> tz-aware UTC, or None."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            n = float(v)
            return datetime.fromtimestamp(n / 1000 if n > 1e12 else n, tz=timezone.utc)
        s = str(v).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            s = s.replace("Z", "+00:00")
            for cand in (s, re.sub(r"\.\d+", "", s)):
                try:
                    d = datetime.fromisoformat(cand)
                    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
                except ValueError:
                    continue
            return None
        d = parsedate_to_datetime(s)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None


def _job(source, company, title, location, url, posted_at, remote, description):
    # feeds send "Aisles &amp; Abroad": decode it once here, so the feed never shows "&amp;amp;"
    def text(v):
        return html.unescape(str(v or "")).strip()
    return dict(company=text(company), title=text(title), location=text(location), url=(url or "").strip(),
                posted_at=posted_at, remote=remote, description=_clean(description), source=source)


def _fit(title, longest):
    """The title's last words that fit in `longest` characters ("" when none do). The end of a job
    title names the job, and the wider search is safe: crawl.py filters on your full titles."""
    words = title.split()
    while words and len(" ".join(words)) > longest:
        words.pop(0)
    return " ".join(words)


def _queries(titles, cfg, source=None):
    n = int(cfg.get("max_queries") or 5)
    shortest, longest = MIN_QUERY_CHARS.get(source, 1), MAX_QUERY_CHARS.get(source)
    real = [t for t in titles if t]
    fitted = [_fit(t, longest) for t in real] if longest else real
    usable = list(dict.fromkeys(t for t in fitted if len(t.strip()) >= shortest))
    if real and not usable:
        if all(len(t.strip()) < shortest for t in real):
            raise SourceSkip(f"every title is shorter than {shortest} characters, and this source's "
                             f"search does not accept a term that short")
        raise SourceSkip(f"no title can be searched here: this source accepts {shortest} to {longest} "
                         f"characters")
    return usable[:max(1, n)]


def _per_query(queries, sleep, run):
    """Run `run(query) -> [job]` for each query, a few seconds apart. One failed query keeps the
    others' jobs; only when no query succeeded is the last error raised. HTTP 429 stops at once."""
    out, errors, last, ok = [], [], None, 0
    for i, t in enumerate(queries):
        if i:
            sleep(QUERY_GAP_SECONDS)
        try:
            out.extend(run(t))
            ok += 1
        except urllib.error.HTTPError as e:
            last = e
            errors.append(f"'{t}': HTTP {e.code}")
            if e.code == 429:
                break
        except Exception as e:
            last = e
            errors.append(f"'{t}': {type(e).__name__} {str(e)[:60]}")
    if last is not None and not ok:
        raise last
    return Partial(out, errors) if errors else out


# one fetcher per source: (cfg, titles, get, sleep) -> [normalized job]
def fetch_himalayas(cfg, titles, get, sleep):
    """Himalayas search API (https://himalayas.app/api): `q` + `country`, 20 results a page."""
    def one(t):
        q = {"q": t}
        if cfg.get("country"):
            q["country"] = cfg["country"]
        d = get("https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(q))
        out = []
        for j in (d.get("jobs") or []) if isinstance(d, dict) else []:
            where = ", ".join(j.get("locationRestrictions") or [])
            out.append(_job("himalayas", j.get("companyName"), j.get("title"),
                            f"Remote ({where})" if where else "Remote",
                            # Terms: use applicationLink unchanged.
                            j.get("applicationLink") or j.get("guid"),
                            to_dt(j.get("pubDate")), True, j.get("description") or j.get("excerpt")))
        return out
    return _per_query(_queries(titles, cfg, "himalayas"), sleep, one)


def fetch_jobicy(cfg, titles, get, sleep):
    """Jobicy remote-jobs API v2 (https://jobicy.com/jobs-rss-feed): `geo`, `tag`, `count`. A tag
    outside 3 to 20 characters gets HTTP 400, so _queries() shortens or leaves out such a title."""
    def one(t):
        q = {"count": int(cfg.get("count") or 50), "tag": t}
        if cfg.get("geo"):
            q["geo"] = cfg["geo"]
        d = get("https://jobicy.com/api/v2/remote-jobs?" + urllib.parse.urlencode(q))
        out = []
        for j in (d.get("jobs") or []) if isinstance(d, dict) else []:
            geo = j.get("jobGeo") or ""
            out.append(_job("jobicy", j.get("companyName"), html.unescape(j.get("jobTitle") or ""),
                            f"Remote ({geo})" if geo else "Remote",
                            j.get("url"),  # Terms: keep the canonical Jobicy URL.
                            to_dt(j.get("pubDate")), True, j.get("jobDescription") or j.get("jobExcerpt")))
        return out
    return _per_query(_queries(titles, cfg, "jobicy"), sleep, one)


def fetch_remotive(cfg, titles, get, sleep):
    """Remotive (https://github.com/remotive-io/remote-jobs-api). Its terms block more than 2 calls a
    minute, so this makes ONE call a run: a `search` for your title when you have exactly one, else
    Remotive's default list, filtered locally by crawl.py like every other source. That default
    list is short (about 10 recent jobs when last checked), so treat Remotive as a small extra."""
    q = {}
    real = [t for t in titles if t]
    if len(real) == 1:
        q["search"] = real[0]
    if cfg.get("category"):
        q["category"] = cfg["category"]
    url = "https://remotive.com/api/remote-jobs" + ("?" + urllib.parse.urlencode(q) if q else "")
    d = get(url)
    out = []
    for j in (d.get("jobs") or []) if isinstance(d, dict) else []:
        where = j.get("candidate_required_location") or ""
        out.append(_job("remotive", j.get("company_name"), j.get("title"),
                        f"Remote ({where})" if where else "Remote", j.get("url"),
                        to_dt(j.get("publication_date")), True, j.get("description")))
    return out


def fetch_remoteok(cfg, titles, get, sleep):
    """Remote OK (https://remoteok.com/api): one feed of recent jobs, no search. The first array
    element is its legal notice, not a job; anything without a `position` is skipped."""
    d = get("https://remoteok.com/api")
    out = []
    for j in d if isinstance(d, list) else []:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        where = j.get("location") or ""
        out.append(_job("remoteok", j.get("company"), j.get("position"),
                        f"Remote ({where})" if where else "Remote",
                        j.get("url") or j.get("apply_url"),  # Terms: link back to Remote OK.
                        to_dt(j.get("epoch") or j.get("date")), True, j.get("description")))
    return out


def fetch_themuse(cfg, titles, get, sleep):
    """The Muse public API v2 (https://www.themuse.com/developers/api/v2). No title search: pages of
    jobs filtered by category / location / level, then filtered locally on your titles."""
    out = []
    for page in range(1, int(cfg.get("pages") or 2) + 1):
        if page > 1:
            sleep(QUERY_GAP_SECONDS)
        q = [("page", page)]
        for key in ("category", "location", "level"):
            vals = cfg.get(key) or []
            for v in ([vals] if isinstance(vals, str) else vals):
                q.append((key, v))
        if os.environ.get("THEMUSE_API_KEY"):
            q.append(("api_key", os.environ["THEMUSE_API_KEY"]))
        d = get("https://www.themuse.com/api/public/jobs?" + urllib.parse.urlencode(q))
        res = (d.get("results") or []) if isinstance(d, dict) else []
        for j in res:
            locs = "; ".join(x.get("name", "") for x in (j.get("locations") or []) if isinstance(x, dict))
            out.append(_job("themuse", (j.get("company") or {}).get("name"), j.get("name"), locs,
                            (j.get("refs") or {}).get("landing_page"),
                            to_dt(j.get("publication_date")), "remote" in locs.lower() or None,
                            j.get("contents")))
        if not res:
            break
    return out


def fetch_weworkremotely(cfg, titles, get, sleep):
    """We Work Remotely RSS (https://weworkremotely.com/remote-jobs.rss). Item titles read
    'Company: Role'."""
    text = get(cfg.get("feed_url") or "https://weworkremotely.com/remote-jobs.rss", raw=True)
    out = []
    root = ET.fromstring(text)
    for it in root.iter("item"):
        raw_title = (it.findtext("title") or "").strip()
        company, _, role = raw_title.partition(":")
        if not role:
            company, role = "", raw_title
        region = (it.findtext("region") or "").strip()
        out.append(_job("weworkremotely", company, role, f"Remote ({region})" if region else "Remote",
                        it.findtext("link"), to_dt(it.findtext("pubDate")), True,
                        it.findtext("description")))
    return out


def fetch_usajobs(cfg, titles, get, sleep):
    """USAJOBS Search API (https://developer.usajobs.gov/api-reference/get-api-search). Needs a free
    key: set USAJOBS_API_KEY and USAJOBS_EMAIL (the email you registered) in your environment."""
    key, email = os.environ.get("USAJOBS_API_KEY"), os.environ.get("USAJOBS_EMAIL")
    if not key or not email:
        raise SourceSkip("needs a free key: set USAJOBS_API_KEY and USAJOBS_EMAIL in your environment "
                         "(request one at https://developer.usajobs.gov)")
    headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}

    def one(t):
        q = {"Keyword": t, "ResultsPerPage": 100}
        if cfg.get("location"):
            q["LocationName"] = cfg["location"]
        d = get("https://data.usajobs.gov/api/Search?" + urllib.parse.urlencode(q), headers=headers)
        items = (((d or {}).get("SearchResult") or {}).get("SearchResultItems") or []) if isinstance(d, dict) else []
        out = []
        for it in items:
            m = it.get("MatchedObjectDescriptor") or {}
            summary = ((m.get("UserArea") or {}).get("Details") or {}).get("JobSummary") or ""
            out.append(_job("usajobs", m.get("OrganizationName"), m.get("PositionTitle"),
                            m.get("PositionLocationDisplay"), m.get("PositionURI"),
                            to_dt(m.get("PublicationStartDate")), None, summary))
        return out
    return _per_query(_queries(titles, cfg, "usajobs"), sleep, one)


FETCHERS = {"himalayas": fetch_himalayas, "jobicy": fetch_jobicy, "remotive": fetch_remotive,
            "remoteok": fetch_remoteok, "themuse": fetch_themuse,
            "weworkremotely": fetch_weworkremotely, "usajobs": fetch_usajobs}


# config, state, and the one entry point crawl.py calls
def read_config(path=None):
    """(cfg, problems): sources.yaml merged over DEFAULTS, plus one plain sentence for anything in
    it that could not be used. A missing file means the defaults, with nothing to report. A broken
    file also means the defaults, and says so: the crawl carries on with what is known."""
    path = Path(path) if path else HERE / "sources.yaml"
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    if not path.exists():
        return cfg, []
    try:
        data = config_files.read_yaml(path)
    except config_files.ConfigError as e:
        return cfg, [f"Using the built-in source settings for this run. {e}"]
    blocks = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(blocks, dict):
        return cfg, ["Using the built-in source settings for this run. pipeline/job-crawler/sources.yaml "
                     "has no `sources:` block of settings: restore the shipped copy with "
                     "`git checkout -- pipeline/job-crawler/sources.yaml` (or, in a Download-ZIP copy, download that file again from the repo's GitHub page), then run this again."]
    problems = []
    for name, block in blocks.items():
        if isinstance(block, dict):
            cfg.setdefault(name, {}).update(block)
        else:
            problems.append(f"sources.yaml: the `{name}` entry is not a block of settings, so it was "
                            f"ignored" + (" and its built-in settings were used." if name in DEFAULTS else "."))
    return cfg, problems


def load_config(path=None):
    """sources.yaml merged over DEFAULTS (read_config, without its list of problems)."""
    return read_config(path)[0]


def _interval_minutes(name, c):
    """The larger of the source's floor and its min_interval_minutes (which, if unreadable, is ignored)."""
    try:
        wanted = float(c.get("min_interval_minutes") or 0)
    except (TypeError, ValueError):
        wanted = 0
    return max(wanted, FLOOR_MINUTES.get(name, 60))


def _ser(j):
    d = dict(j)
    d["posted_at"] = j["posted_at"].isoformat() if j.get("posted_at") else None
    return d


def _deser(d):
    j = dict(d)
    j["posted_at"] = to_dt(d.get("posted_at"))
    return j


def _load_state(cache_dir):
    try:
        return json.loads((Path(cache_dir) / STATE_NAME).read_text())
    except Exception:
        return {}


def _save_state(cache_dir, state):
    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        (Path(cache_dir) / STATE_NAME).write_text(json.dumps(state, indent=1))
        return True
    except Exception:
        return False


def collect(titles, cfg=None, cache_dir=CACHE_DIR, now=None, get=http_get, sleep=time.sleep):
    """Run every enabled source once, politely. Returns (jobs, report). `report` has one entry per
    known source: {name, label, status: ran|cached|skipped|error, jobs, reason}, then one
    CONFIG_ENTRY entry per problem found in sources.yaml. Nothing raises."""
    problems = []
    if cfg is None:
        cfg, problems = read_config()
        cfg, unusable = config_files.clean_source_settings(cfg, DEFAULTS)
        problems += unusable
    now = now or datetime.now(timezone.utc)
    state = _load_state(cache_dir)
    titles_key = "|".join(sorted({str(t).strip().lower() for t in titles or []}))
    jobs, report = [], []
    for name in ORDER + [n for n in cfg if n not in ORDER]:
        c = cfg.get(name) or {}
        entry = {"name": name, "label": LABELS.get(name, name), "status": "skipped", "jobs": 0}
        report.append(entry)
        fetcher = FETCHERS.get(name)
        if not fetcher:
            entry["reason"] = "unknown source name in sources.yaml (no fetcher for it in sources.py)"
            continue
        if not c.get("enabled"):
            entry["reason"] = "disabled in sources.yaml"
            continue
        st = state.get(name) or {}
        interval = _interval_minutes(name, c)
        last = to_dt(st.get("last_attempt"))
        if last and now - last < timedelta(minutes=interval):
            ago = int((now - last).total_seconds() // 60)
            cached = [_deser(x) for x in st.get("jobs") or []]
            jobs.extend(cached)
            why = (f"the last attempt {ago} min ago failed ({st['last_error']})" if st.get("last_error")
                   else f"last fetched {ago} min ago")
            retry = max(int(interval) - ago, 1)
            entry.update(status="cached", jobs=len(cached), retry_in=retry,
                         reason=f"{why}; this source allows one call every {int(interval)} min, so it "
                                f"was not called again and {len(cached)} jobs from its last good fetch "
                                f"were reused (next call in about {retry} min)")
            if st.get("last_error"):
                entry["last_attempt_failed"] = True
            if st.get("titles") is not None and st.get("titles") != titles_key:
                # the cached jobs were searched for other titles: say so, never a silent 0 for the new ones
                entry["stale_titles"] = True
                entry["reason"] += ("; those jobs were searched for your earlier titles, so jobs for your "
                                    f"current titles may be missing until then")
            continue
        try:
            got = fetcher(c, titles, get, sleep)
        except SourceSkip as e:
            entry["reason"] = str(e)
            continue
        except urllib.error.HTTPError as e:
            entry.update(status="error", reason=f"HTTP {e.code}" + (" (rate limited)" if e.code == 429 else ""))
            state[name] = dict(st, last_attempt=now.isoformat(), last_error=entry["reason"])
            continue
        except Exception as e:
            entry.update(status="error", reason=f"{type(e).__name__} {str(e)[:80]}")
            state[name] = dict(st, last_attempt=now.isoformat(), last_error=entry["reason"])
            continue
        failed = list(getattr(got, "errors", []))
        got = [j for j in got if j["title"] and j["url"]]
        jobs.extend(got)
        state[name] = {"last_attempt": now.isoformat(), "last_success": now.isoformat(),
                       "titles": titles_key, "jobs": [_ser(j) for j in got]}
        entry.update(status="ran", jobs=len(got))
        if failed:
            entry["reason"] = (f"{len(failed)} quer{'y' if len(failed) == 1 else 'ies'} failed and the "
                               f"rest were kept: " + "; ".join(failed))
    if not _save_state(cache_dir, state):
        report.append({"name": "cache", "label": "cache", "status": "error", "jobs": 0,
                       "reason": f"could not write {Path(cache_dir) / STATE_NAME}; minimum intervals "
                                 f"cannot be enforced across runs until it is writable"})
    report += [{"name": CONFIG_ENTRY, "label": "sources.yaml", "status": "error", "jobs": 0, "reason": p}
               for p in problems]
    return jobs, report


# offline selftest
def _selftest():
    import tempfile
    fixtures = {
        "himalayas.app": {"jobs": [{"title": "Data Analyst", "companyName": "Acme",
                                    "locationRestrictions": ["United States"], "pubDate": 1792000000,
                                    "applicationLink": "https://himalayas.app/companies/acme/jobs/data-analyst?utm_source=api",
                                    "description": "<p>Real work</p>"}]},
        "jobicy.com": {"jobs": [{"jobTitle": "Data Analyst &amp; Reporting", "companyName": "Globex",
                                 "url": "https://jobicy.com/jobs/1-data-analyst", "jobGeo": "USA",
                                 "pubDate": "2026-10-20T19:20:11+00:00"}]},
        "remotive.com": {"jobs": [{"title": "Nurse Educator", "company_name": "Initech",
                                   "url": "https://remotive.com/remote-jobs/x/1",
                                   "candidate_required_location": "USA",
                                   "publication_date": "2026-10-17T16:04:29"}]},
        "remoteok.com": [{"legal": "notice"}, {"position": "Data Analyst", "company": "Northwind",
                                                "url": "https://remoteOK.com/remote-jobs/1", "epoch": "1792592961"}],
    }
    calls = []

    def fake_get(url, headers=None, raw=False):
        calls.append(url)
        if "usajobs" in url:
            return {"SearchResult": {"SearchResultItems": [{"MatchedObjectDescriptor": {
                "PositionTitle": "Data Analyst", "OrganizationName": "Fathom Agency",
                "PositionLocationDisplay": "Denver, Colorado", "PositionURI": "https://www.usajobs.gov/job/1",
                "PublicationStartDate": "2026-10-20T00:00:00.0000"}}]}}
        for host, body in fixtures.items():
            if host in url:
                return body
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)

    tmp = Path(tempfile.mkdtemp())
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    old = dict(os.environ)
    os.environ.pop("USAJOBS_API_KEY", None)
    try:
        jobs, rep = collect(["data analyst"], cfg, tmp, now, fake_get, lambda s: None)
        st = {r["name"]: r for r in rep}
        assert st["himalayas"]["status"] == "ran" and st["remoteok"]["jobs"] == 1, rep
        assert st["themuse"]["status"] == "skipped" and "disabled" in st["themuse"]["reason"]
        assert st["usajobs"]["status"] == "skipped" and "USAJOBS_API_KEY" in st["usajobs"]["reason"]
        assert all(j["source"] in LABELS for j in jobs)
        assert REMOTE_ONLY <= set(LABELS) and "usajobs" not in REMOTE_ONLY
        h = [j for j in jobs if j["source"] == "himalayas"][0]
        assert h["url"].endswith("utm_source=api") and h["posted_at"].year == 2026, h
        assert [j for j in jobs if j["source"] == "jobicy"][0]["title"] == "Data Analyst & Reporting"
        n_calls = len(calls)
        jobs2, rep2 = collect(["data analyst"], cfg, tmp, now + timedelta(minutes=5), fake_get, lambda s: None)
        assert len(calls) == n_calls, "a run inside the minimum interval must not call any source"
        assert {r["status"] for r in rep2 if r["name"] in ("himalayas", "remoteok")} == {"cached"}
        assert len(jobs2) == len(jobs)
        later = now + timedelta(minutes=61)
        jobs3, rep3 = collect(["data analyst"], cfg, tmp, later, fake_get, lambda s: None)
        s3 = {r["name"]: r["status"] for r in rep3}
        assert s3["himalayas"] == "ran" and s3["remotive"] == "cached", s3   # remotive floor is 6h
        os.environ["USAJOBS_API_KEY"], os.environ["USAJOBS_EMAIL"] = "k", "me@example.com"
        tmp2 = Path(tempfile.mkdtemp())
        jobs4, rep4 = collect(["data analyst"], cfg, tmp2, now, fake_get, lambda s: None)
        assert {r["name"]: r["status"] for r in rep4}["usajobs"] == "ran"
        assert any(j["company"] == "Fathom Agency" for j in jobs4)
        assert to_dt("Tue, 20 Oct 2026 10:00:00 +0000").day == 20 and to_dt(1792000000000).year == 2026
        # a too-short title is never sent to Jobicy, and the other titles still are
        jc = []
        def jget(url, headers=None, raw=False):
            jc.append(url)
            if "tag=rn" in url:
                raise urllib.error.HTTPError(url, 400, "bad tag", {}, None)
            return fixtures["jobicy.com"]
        got = fetch_jobicy({}, ["rn", "registered nurse"], jget, lambda s: None)
        assert len(got) == 1 and not [u for u in jc if "tag=rn&" in u or u.endswith("tag=rn")], jc
        try:
            fetch_jobicy({}, ["rn", "pa"], jget, lambda s: None)
            raise AssertionError("only too-short titles must skip Jobicy")
        except SourceSkip as e:
            assert "shorter than 3" in str(e)
        # a tag over 20 characters is shortened to its last words that fit, never sent whole
        lc = []
        fetch_jobicy({}, ["journeyman electrician", "electrician", "electrical technician"],
                     lambda url, headers=None, raw=False: lc.append(url) or fixtures["jobicy.com"], lambda s: None)
        tags = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["tag"][0] for u in lc]
        assert tags == ["electrician", "technician"], tags
        try:
            fetch_jobicy({}, ["x" * 25], jget, lambda s: None)
            raise AssertionError("a title with no words that fit must skip Jobicy")
        except SourceSkip as e:
            assert "3 to 20" in str(e)
        # one failed query keeps the rest; the source fails only when every query failed
        def hget(url, headers=None, raw=False):
            if "q=accountant" in url:
                raise urllib.error.HTTPError(url, 500, "boom", {}, None)
            return fixtures["himalayas.app"]
        part = fetch_himalayas({}, ["accountant", "bookkeeper"], hget, lambda s: None)
        assert len(part) == 1 and part.errors and "HTTP 500" in part.errors[0], part
        try:
            fetch_himalayas({}, ["accountant"], hget, lambda s: None)
            raise AssertionError("every query failed: the error must reach collect()")
        except urllib.error.HTTPError:
            pass
        rep5 = collect(["accountant", "bookkeeper"], {"himalayas": {"enabled": True}},
                       Path(tempfile.mkdtemp()), now, hget, lambda s: None)[1]
        h5 = {r["name"]: r for r in rep5}["himalayas"]
        assert h5["status"] == "ran" and h5["jobs"] == 1 and "1 query failed" in h5["reason"], h5
    finally:
        os.environ.clear()
        os.environ.update(old)
    print("sources.py selftest: OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
