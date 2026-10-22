#!/usr/bin/env python3
"""
Job crawler.

Pulls REAL postings from three kinds of free source, for any role in any industry:
  1. companies' public ATS boards (Greenhouse / Lever / Ashby / Workday / SmartRecruiters /
     Workable), listed in boards.yaml. You don't hand-list these: discover.py finds them
     (`discover.py --sweep` harvests thousands of boards and keeps the ones hiring for your titles);
  2. free job APIs (Himalayas, Jobicy, Remotive, Remote OK, and USAJOBS with a free key), set up in
     sources.yaml, each fetched politely within its own terms (see sources.py);
  3. the monthly Hacker News "Ask HN: Who is hiring?" thread.
It filters all of them the same way, to your own target roles
(configured in filters.yaml), DROPS hard blockers you define (e.g. citizenship/clearance/ITAR
walls, if any apply to you), FLAGS soft "won't sponsor" postings (kept, not dropped, by default;
edit filters.yaml if this doesn't apply to your situation), and returns the fresh matches. $0,
no API keys, no login, no scraping of any login-walled platform (no account-ban risk). The whole
point is to catch a posting the day it goes up, before it's buried under a week of new listings.

HONESTY: this script only SELECTS real postings and copies their real fields. It never invents,
edits, embellishes, or generates anything about a job.

Reads:   boards.yaml (company -> ats + slug), sources.yaml (job APIs), filters.yaml (what to keep/drop).
Sources: the public ATS JSON, the job APIs in sources.py, and HN "Who's Hiring" via the free
         Algolia API (see hn.py).
Prints:  JSON of fresh matches to stdout, plus a `sources` report: every source, whether it ran,
         how many jobs it returned, and why any was skipped.
--write also: rewrites ../job-feed.md (the review feed) and appends new, deduped `lead`
              rows to ../tracker.html's APPLICATIONS array (safely, with validation).

Usage:
  python3 crawl.py                  # fresh matches (last lookback_hours), JSON to stdout
  python3 crawl.py --write          # also update job-feed.md + tracker.html
  python3 crawl.py --hours 168      # widen the window to a week
  python3 crawl.py --company acme   # one company (also filters HN postings by that company)
  python3 crawl.py --all            # ignore the time window (still title/US/hard-wall filtered)
  python3 crawl.py --no-hn          # skip the HN "Who's Hiring" source
  python3 crawl.py --no-api         # skip the job APIs in sources.yaml
  python3 crawl.py --hide-no-sponsor# drop the "won't sponsor" postings too (default: keep + flag)
"""
import json, sys, argparse, re, html, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

from http_util import read_url  # sibling module: gzip + retry on a cut-off read
import hn  # sibling module: the HN "Who's Hiring" collector (same dir, on sys.path)
import sources as api_sources  # sibling module: the free job APIs configured in sources.yaml
import locations  # sibling module: the location rule crawl.py and discover.py share
import titles  # sibling module: the title rule crawl.py and discover.py share
from locations import _block_re, location_ok  # noqa: F401  (kept importable from crawl.py)

HERE = Path(__file__).resolve().parent
FEED = HERE.parent / "job-feed.md"        # pipeline/job-feed.md
TRACKER = HERE.parent / "tracker.html"    # pipeline/tracker.html
UA = "Mozilla/5.0 (personal job-search crawler; see pipeline/job-crawler/README.md)"
CACHE_DIR = HERE / "cache"                # gitignored: source fetch times + discovery state
NO_TITLES = ("No job titles set: run /setup, or add your role titles under include_titles in "
             "pipeline/job-crawler/filters.yaml, then run the crawler again.")
NO_BOARDS_HINT = ("boards.yaml has no company boards yet (it ships empty), so only the job APIs and "
                  "Hacker News were searched. Run `python3 pipeline/job-crawler/discover.py --sweep` "
                  "to find company boards hiring for your titles (it stops after a few minutes and "
                  "continues on the next run), or add named companies with `discover.py --company "
                  "\"Name\"`, or job URLs with `discover.py --urls -`.")


def load_yaml(name):
    import yaml  # PyYAML
    return yaml.safe_load((HERE / name).read_text())


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.loads(read_url(req, timeout))


def fetch_post(url, body, timeout=25):
    """POST a JSON body, parse a JSON response. Workday's public jobs API is POST-only."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
    return json.loads(read_url(req, timeout))


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


def parse_ts(v):
    """ISO-8601 string, or ms-epoch int/str (Lever). Returns tz-aware UTC datetime or None."""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ---- per-provider fetch + normalize -> {company,title,location,url,posted_at,remote,description} ----
def from_greenhouse(company, slug):
    d = fetch(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    out = []
    for j in d.get("jobs", []):
        loc = j.get("location") or {}
        out.append(dict(company=company, title=(j.get("title") or "").strip(),
                        location=(loc.get("name") if isinstance(loc, dict) else str(loc)) or "",
                        url=j.get("absolute_url", ""),
                        # first_published is the TRUE publish time. updated_at bumps on ANY edit, so
                        # an old job edited today would read as fresh. Prefer first_published.
                        posted_at=parse_ts(j.get("first_published") or j.get("updated_at")),
                        remote=None, description=strip_html(j.get("content", ""))))
    return out


def from_ashby(company, slug):
    d = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    out = []
    for j in d.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append(dict(company=company, title=(j.get("title") or "").strip(),
                        location=j.get("location", "") or "",
                        url=j.get("jobUrl") or j.get("applyUrl", ""),
                        posted_at=parse_ts(j.get("publishedAt")), remote=j.get("isRemote"),
                        description=strip_html(j.get("descriptionHtml") or j.get("descriptionPlain", ""))))
    return out


def from_lever(company, slug):
    d = fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for j in (d if isinstance(d, list) else []):
        cat = j.get("categories") or {}
        loc = cat.get("location", "") or ""
        out.append(dict(company=company, title=(j.get("text") or "").strip(), location=loc,
                        url=j.get("hostedUrl") or j.get("applyUrl", ""),
                        posted_at=parse_ts(j.get("createdAt")), remote=("remote" in loc.lower()),
                        description=strip_html(j.get("descriptionPlain") or j.get("description", ""))))
    return out


# ---- Workday / SmartRecruiters / Workable: three more public ATS platforms beyond the GH/Lever/
#      Ashby core, useful because they host a different mix of employers (Workday in particular
#      skews toward large enterprises the other three rarely reach). Discovery only: none of these
#      list endpoints return the full JD body (fetch it from the posting URL yourself when you
#      tailor), and Workday's list API gives only a RELATIVE post date ("Posted 3 Days Ago"), so its
#      posted_at below is an APPROXIMATION, never exact. A wrong slug 404s and is reported like any
#      other bad slug, same as the three ATSes above. ----
WORKDAY_MAX_PER_TERM = 60  # 3 pages of 20; Workday relevance-sorts, so title matches surface first


def _workday_posted(text):
    """Workday's list API gives only RELATIVE text ('Posted Today', 'Posted 3 Days Ago', 'Posted 30+
    Days Ago') -- never a real date. Convert to an APPROXIMATE tz-aware UTC datetime (best available
    for recency ranking; the exact date lives on the job-detail page, not the list). None if
    unparseable."""
    if not text:
        return None
    t = text.lower()
    now = datetime.now(timezone.utc)
    if "today" in t or "just posted" in t or "hour" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\s*\+?\s*day", t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*\+?\s*month", t)
    if m:
        return now - timedelta(days=30 * int(m.group(1)))
    return None


def from_workday(company, slug, terms):
    """Workday. slug is COMPOUND: 'tenant/host/site' (e.g. 'acme/wd5/external_careers'). Read a
    company's careers URL for all three: https://<tenant>.<host>.myworkdayjobs.com/<site>. The jobs
    API is POST-only and, unlike Greenhouse/Lever/Ashby, has no "list the whole board" mode -- it
    requires a search string per call, so `terms` (your own filters.yaml `include_titles`) is POSTed
    one term at a time and the results de-duped. Returns relative post dates (approximated) and no
    JD body (fetch that later). A wrong tenant/host/site 404s and is reported like any bad slug."""
    parts = [p for p in slug.split("/") if p]
    if len(parts) != 3:
        raise ValueError(f"workday slug must be 'tenant/host/site', got '{slug}'")
    tenant, host, site = parts
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    out, seen = [], set()
    for term in terms:
        offset = 0
        while offset < WORKDAY_MAX_PER_TERM:
            d = fetch_post(api, {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term})
            jp = d.get("jobPostings", []) if isinstance(d, dict) else []
            if not jp:
                break
            for j in jp:
                path = (j.get("externalPath") or "").strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                out.append(dict(company=company, title=(j.get("title") or "").strip(),
                                location=(j.get("locationsText") or "").strip(),
                                url=f"{base}/{site}{path}",
                                posted_at=_workday_posted(j.get("postedOn")), posted_approx=True,
                                remote=None, description=""))
            offset += 20
    return out


def from_smartrecruiters(company, slug):
    """SmartRecruiters public postings API (no auth). slug = the SR company identifier
    (jobs.smartrecruiters.com/<slug>, case-sensitive). Paginated; JD body fetched later."""
    out = []
    offset = 0
    while offset < 300:
        d = fetch(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
        content = d.get("content", []) if isinstance(d, dict) else []
        if not content:
            break
        for j in content:
            loc = j.get("location") or {}
            locs = ", ".join(x for x in (loc.get("city") or "", loc.get("region") or "") if x) \
                or ("Remote" if loc.get("remote") else "")
            jid = j.get("id") or j.get("uuid") or ""
            out.append(dict(company=company, title=(j.get("name") or "").strip(), location=locs,
                            url=f"https://jobs.smartrecruiters.com/{slug}/{jid}",
                            posted_at=parse_ts(j.get("releasedDate") or j.get("createdOn")),
                            remote=bool(loc.get("remote")), description=""))
        offset += 100
        if offset >= (d.get("totalFound") or 0):
            break
    return out


def from_workable(company, slug):
    """Workable public widget API (no auth). slug = the Workable account (apply.workable.com/<slug>).
    JD body included when present."""
    d = fetch(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    out = []
    for j in (d.get("jobs", []) if isinstance(d, dict) else []):
        locs = ", ".join(x for x in (j.get("city") or "", j.get("country") or "") if x) \
            or ("Remote" if j.get("telecommuting") else "")
        code = j.get("shortcode") or ""
        url = j.get("url") or j.get("application_url") or f"https://apply.workable.com/{slug}/j/{code}/"
        out.append(dict(company=company, title=(j.get("title") or "").strip(), location=locs, url=url,
                        posted_at=parse_ts(j.get("published_on") or j.get("created_at")),
                        remote=bool(j.get("telecommuting")), description=strip_html(j.get("description", ""))))
    return out


FETCHERS = {"greenhouse": from_greenhouse, "ashby": from_ashby, "lever": from_lever,
            "workday": from_workday, "smartrecruiters": from_smartrecruiters, "workable": from_workable}


def title_match(job, F):
    """The include_titles term this job's title matches, or None (titles.py: a substring, except a
    term of 3 characters or fewer, which must be a whole word)."""
    return titles.first_match(F["include_titles"], job["title"])


def blocked(job, F):
    dl = (job["title"] + " " + job["description"]).lower()
    co = job["company"].lower()
    if any(x in co for x in F.get("exclude_companies", [])):
        return "excluded-company"
    hit = next((x for x in F.get("exclude_patterns", []) if x in dl), None)
    return f"blocker:{hit.strip()}" if hit else None


def sponsorship_flagged(job, F):
    """SOFT sponsorship signal: does the posting SAY it will not sponsor a visa? Scans the SAME
    text blocked() does (title + description). Unlike blocked(), a hit here NEVER drops the
    posting on its own: whether that matters to you depends on your own work-authorization
    situation (see knowledge-base/02-work-authorization.md). The hard walls (anything you've put
    in exclude_patterns) live in blocked(), and a posting that trips BOTH is dropped by blocked()
    first (a wall always wins). Leave filters.yaml's flag_patterns empty to disable this feature
    entirely. Returns bool."""
    dl = (job["title"] + " " + job["description"]).lower()
    return any(p in dl for p in F.get("flag_patterns", []))


def score(job, F):
    """Score = count of include_keywords hits in the title + description. Add your own bonus terms
    straight into filters.yaml's include_keywords rather than hardcoding a title bonus here: that
    keeps every scoring rule in one user-editable place. With no include_keywords set, every score
    is 0 and ranking falls back to title fit, then freshness (see RANKING)."""
    dl = (job["title"] + " " + job["description"]).lower()
    return sum(1 for k in F.get("include_keywords", []) if str(k).lower() in dl)


def _norm_title(t):
    return " ".join(re.findall(r"[a-z0-9+#]+", (t or "").lower()))


def title_fit(job, F):
    """How closely the job title matches your include_titles, best over all of them:
    3 = the title IS one of yours (ignoring case and punctuation), 2 = it contains one as whole
    words, 1 = only as part of a longer word. 0 only when nothing matches (never kept)."""
    t = _norm_title(job["title"])
    best = 0
    for it in F.get("include_titles", []):
        n = _norm_title(it)
        if not n:
            continue
        if t == n:
            return 3
        if re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", t):
            best = max(best, 2)
        elif titles.term_hits(it, job["title"]):
            best = max(best, 1)
    return best


def ranking_note(F):
    """The ranking rule, said plainly in the JSON output, so a 0 score is never mistaken for a signal."""
    kw = "keyword hits from your include_keywords (score)" if F.get("include_keywords") else \
        ("keyword hits (score), which is 0 for every match because include_keywords is empty, so it "
         "plays no part")
    return ("Matches are sorted by " + kw + ", then title fit (3 = the title is exactly one of your "
            "include_titles, 2 = it contains one as whole words, 1 = only as part of a word), then "
            "newest posting first (unknown dates last). Add include_keywords in filters.yaml to rank "
            "on the skills or terms you care about.")


def rank_key(m):
    return (m["score"], m.get("title_fit", 0), m["posted_at"] or "")


# Why consider() turned a posting away, in the order the gates run. Each count lands in the JSON
# `dropped`, so a run with few matches says which rule removed the rest.
DROP_REASONS = {
    "title": "the title matched none of your include_titles",
    "wall": "a hard wall: exclude_patterns or exclude_companies",
    "location": "the location rule (require_us, remote_ok, onsite_ok, home_metros)",
    "age": "posted before the lookback window",
    "no_sponsor_hidden": "flagged no-sponsorship and --hide-no-sponsor was set",
}


def _drop(stats, reason):
    d = stats.setdefault("dropped", {k: 0 for k in DROP_REASONS})
    d[reason] = d.get(reason, 0) + 1
    return None


def remote_only_hint(F, report, dropped):
    """A sentence for `hints` when remote_ok is false but the run's jobs came mostly from sources that
    list remote jobs only and no company board supplied any, so the location rule was bound to drop
    nearly everything; else None. (HN is one title-filtered thread a month, so a handful of HN jobs
    does not change the picture.)"""
    remote_ok, _, _ = locations.settings(F)
    if remote_ok:
        return None
    got = [r for r in report if r.get("status") in ("ran", "cached") and r.get("jobs")]
    remote = [r for r in got if r.get("name") in api_sources.REMOTE_ONLY]
    n_remote = sum(r["jobs"] for r in remote)
    n_other = sum(r["jobs"] for r in got if r not in remote)
    boards = sum(r["jobs"] for r in got if r.get("name") == "ats-boards")
    if not remote or boards or n_remote <= n_other:
        return None
    names = ", ".join(r.get("label") or r.get("name") for r in remote)
    return ("remote_ok is false in filters.yaml, but " + str(n_remote) + " of the " + str(n_remote + n_other)
            + " jobs fetched this run came from sources that list remote jobs only (" + names + ") and no "
            "company board was read, so the location rule dropped " + str(dropped.get("location", 0))
            + " postings. Onsite and hybrid postings come mostly from company boards: run "
            "`python3 pipeline/job-crawler/discover.py --sweep` to fill boards.yaml. Or set "
            "remote_ok: true if remote work suits you.")


def consider(j, F, args, cutoff, stats):
    """Run one normalized posting (from ANY source) through the shared gates (title match,
    reject patterns, US-location, freshness) and return a match dict (carrying provenance
    `source`) or None. Used identically for ATS boards and HN so both obey the same filters.yaml.
    Increments stats['title_hits'] on a title-match hit (across all sources), and counts every
    posting it turns away under stats['dropped'][<reason>] (see DROP_REASONS)."""
    m = title_match(j, F)
    if not m:
        return _drop(stats, "title")
    stats["title_hits"] += 1
    if blocked(j, F):
        return _drop(stats, "wall")
    if not locations.location_ok(j, F):
        return _drop(stats, "location")
    if not args.all and j["posted_at"] and j["posted_at"] < cutoff:
        return _drop(stats, "age")
    # SOFT no-sponsor flag: keep the posting, tag it. --hide-no-sponsor drops the flagged ones.
    no_sponsor = sponsorship_flagged(j, F)
    if no_sponsor and getattr(args, "hide_no_sponsor", False):
        return _drop(stats, "no_sponsor_hidden")
    return dict(company=j["company"], title=j["title"], location=j["location"], url=j["url"],
                posted_at=j["posted_at"].isoformat() if j["posted_at"] else None,
                remote=j["remote"], score=score(j, F), title_fit=title_fit(j, F), matched=m,
                source=j.get("source", "ats"), no_sponsor_flag=no_sponsor,
                posted_approx=bool(j.get("posted_approx")))


# ---- outputs: the review feed + the tracker leads ----
def _md_esc(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


_SRC_LABEL = dict({"hn": "HN Who's Hiring", "ats": "ATS board"}, **api_sources.LABELS)


def _src_label(m):
    return _SRC_LABEL.get(m.get("source", "ats"), m.get("source", "ats"))


def write_feed(matches, hours, keywords_on=True):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nflag = sum(1 for m in matches if m.get("no_sponsor_flag"))
    meta = (f"_Generated {now} · last {hours}h · {len(matches)} match(es)"
            + (f" · {nflag} ⚠ no-sponsor" if nflag else "") + " · via `pipeline/job-crawler/crawl.py`._")
    L = ["# Job feed: fresh roles from company job boards, free job APIs and HN Who's Hiring", "",
         meta, "",
         "Real postings only, pulled straight from the source. Sources: company ATS boards "
         "(boards.yaml), free job APIs (sources.yaml), and the monthly Hacker News \"Who is "
         "hiring?\" thread; the Source column names where each row came from. Filtered per "
         "`filters.yaml`'s title/keyword/location rules. HN posts are freeform, so verify company, "
         "role, and any sponsorship claim on the source before applying.", ""]
    used = [s for s in api_sources.ORDER if any(m.get("source") == s for m in matches)]
    if used:
        L += ["Job listings credited to their sources, each row linking to the original posting: "
              + ", ".join(f"[{api_sources.LABELS[s]}]({api_sources.HOMEPAGES[s]})" for s in used)
              + ". For your own use only; these terms forbid re-posting the jobs elsewhere.", ""]
    if nflag:
        L += ["**⚠ no-sponsor flag (Flag column):** the posting says it will not sponsor a visa. "
              "It is KEPT here, not dropped, by default; whether that matters depends on your own "
              "work-authorization situation (`knowledge-base/02-work-authorization.md`). Edit "
              "`filters.yaml`'s `flag_patterns` if you'd rather these were dropped outright, or run "
              "with `--hide-no-sponsor`.", ""]
    L += ["Rows are ranked by keyword hits (Keywords, from include_keywords), then title fit (Fit: 3 = "
          "exactly one of your titles, 2 = contains it as whole words, 1 = part of a word), then newest."
          + ("" if keywords_on else " include_keywords is empty, so Keywords shows n/a and plays no part."), ""]
    L += ["| Fit | Keywords | Company | Role | Location | Posted | Source | Flag | Apply |",
          "|:-:|:-:|---|---|---|---|---|:-:|---|"]
    for m in matches:
        src = _src_label(m)
        flag = "⚠ no-sponsor" if m.get("no_sponsor_flag") else "n/a"
        kw = m["score"] if keywords_on else "n/a"
        L.append(f"| {m.get('title_fit', 'n/a')} | {kw} | **{_md_esc(m['company']) or 'n/a'}** | {_md_esc(m['title'])} | "
                 f"{_md_esc(m['location']) or 'n/a'} | {(m['posted_at'] or '')[:10]} | {src} | {flag} | "
                 f"[open]({m['url']}) |")
    if not matches:
        L.append("| n/a | n/a | n/a | _No fresh matches this run. Widen with `--hours` or add boards._ "
                 "| n/a | n/a | n/a | n/a | n/a |")
    FEED.write_text("\n".join(L) + "\n")
    return str(FEED)


def _js_row(m):
    """One APPLICATIONS row in the exact shape of .claude/rules/records-format.md section 1 (when
    this crawler sits in the full release), so scripts/records_check.py accepts it: `posted` is
    YYYY-MM-DD or "unknown" (an approximate date goes into notes as "posted (as recorded): ..."),
    `folder` is "" (no dossier yet), comp is "" and compK null (unknown, never a fake zero), and a
    `lead` row carries no `applied` field (that is set the turn the row flips to applied)."""
    def q(s):
        return (s or "").replace("\\", "").replace('"', "'").replace("\n", " ")

    def qurl(u):
        return (u or "").replace("\\", "%5C").replace('"', "%22").replace("\n", "")
    posted_raw = (m["posted_at"] or "")[:10]
    approx = bool(m.get("posted_approx")) and bool(posted_raw)
    posted = "" if approx else posted_raw
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flagged = bool(m.get("no_sponsor_flag"))
    spon = "no" if flagged else "ask"
    src_label = "the crawler" if m.get("source", "ats") == "ats" else _src_label(m)

    # A table cell holds a FACT, never a paragraph (docs/DESIGN.md's table law); `next` is a
    # short, verb-first imperative. Everything else goes in `notes`, revealed only when a row
    # expands.
    if flagged:
        nxt = "Apply anyway if your own work-authorization answer supports it. Check the form."
    elif m.get("source") == "hn":
        nxt = "Verify the post on the source, then apply. Then chase a referral."
    else:
        nxt = "Read the full JD, tailor, apply, then chase a referral."

    notes = (f"Found by {src_label} on {today}"
             + (f" (posted {posted})." if posted else ".")
             + (f" posted (as recorded): about {posted_raw}, from the board's relative date." if approx else "")
             + " Read the full JD before tailoring, never a summary."
             " A referral is generally the strongest lever on a callback; being early is a real"
             " but modest edge (CLAUDE.md §5).")
    if flagged:
        notes = ("This posting states it will not sponsor. Whether that rules it out depends on"
                 " your own work-authorization situation: see knowledge-base/02-work-authorization.md"
                 " and answer any form question exactly per knowledge-base/12-application-answers.md §3,"
                 " never by assumption. " + notes)
    if m.get("source") == "hn":
        notes = ("Freeform HN post, so the company, role, and location are unverified. Check them on"
                 " the source before applying. " + notes)

    url = qurl(m["url"])
    posted_js = f'"{posted}"' if posted else '"unknown"'
    # Full per-job record: fresh crawler rows carry the same schema as every other row. source is
    # always "crawl-jobs" here; jd/apply = the real posting URL; folder/refs/everify start empty
    # (no dossier, no referral, work-auth-enrollment unverified, never guessed). Missing values
    # render as the no-data glyph in the tracker, never a fake value.
    return (f'  {{co:"{q(m["company"])}", role:"{q(m["title"])}", loc:"{q(m["location"])}", '
            f'comp:"", compK:null, status:"lead", fit:"watch", spon:"{spon}", posted:{posted_js},\n'
            f'   source:"crawl-jobs", jd:"{url}", apply:"{url}", folder:"", refs:0, everify:"unknown",\n'
            f'   next:"{q(nxt)}", notes:"{q(notes)}", link:"{url}"}},')


def patch_tracker(matches):
    """Append new, deduped `lead` rows to tracker.html's APPLICATIONS array. Safe: validates
    the array structure survived before writing; aborts (writes nothing) if anything is off."""
    if not TRACKER.exists():
        return {"error": "tracker.html not found", "added": 0}
    src = TRACKER.read_text()
    marker = "const APPLICATIONS = ["
    i = src.find(marker)
    if i < 0:
        return {"error": "APPLICATIONS array marker not found; NOT patched", "added": 0}
    existing = set(re.findall(r'link:"([^"]+)"', src))
    new = [m for m in matches if m["url"] and m["url"] not in existing]
    if not new:
        return {"added": 0}
    rows = "\n".join(_js_row(m) for m in new)
    at = i + len(marker)
    patched = src[:at] + "\n" + rows + src[at:]
    patched = re.sub(r'const UPDATED = "[^"]*";',
                     f'const UPDATED = "{datetime.now(timezone.utc).strftime("%Y-%m-%d")}";',
                     patched, count=1)
    # safety: exactly one array, closer present, and row count grew by exactly len(new)
    if (patched.count(marker) == 1 and "];" in patched
            and patched.count('co:"') == src.count('co:"') + len(new)):
        TRACKER.write_text(patched)
        return {"added": len(new), "companies": sorted({m["company"] for m in new})}
    return {"error": "post-patch validation failed; tracker NOT written", "added": 0}


def main():
    ap = argparse.ArgumentParser(
        description="Fetch fresh postings matching filters.yaml from company boards, free job APIs "
                    "and HN Who's Hiring.",
        epilog="Ranking: keyword hits (include_keywords), then title fit, then newest; the JSON "
               "`ranking` field says which applies. Location: filters.yaml's require_us gate plus "
               "remote_ok / onsite_ok / home_metros (see locations.py).")
    ap.add_argument("--hours", type=int, default=None, help="lookback window in hours (default: "
                    "filters.yaml lookback_hours, 72)")
    ap.add_argument("--company", default=None, help="only companies whose name contains this")
    ap.add_argument("--all", action="store_true", help="ignore the lookback window")
    ap.add_argument("--write", action="store_true",
                    help="write job-feed.md" + (" + patch tracker.html" if TRACKER.exists() else ""))
    ap.add_argument("--no-hn", action="store_true",
                    help="skip the HN 'Who's Hiring' source")
    ap.add_argument("--no-api", action="store_true",
                    help="skip the free job APIs configured in sources.yaml")
    ap.add_argument("--hide-no-sponsor", action="store_true",
                    help="exclude postings flagged 'no sponsorship' (default: include + flag them)")
    args = ap.parse_args()

    F = load_yaml("filters.yaml") or {}
    # Titles are matched as lowercase substrings of a lowercased job title.
    F["include_titles"] = [str(t).strip().lower() for t in (F.get("include_titles") or [])
                           if str(t).strip()]
    if not F["include_titles"]:
        print(NO_TITLES, file=sys.stderr)
        sys.exit(2)
    try:
        location_rule = locations.describe(F)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    boards = load_yaml("boards.yaml") if (HERE / "boards.yaml").exists() else {}
    board_list = (boards.get("boards") if isinstance(boards, dict) else boards) or []
    hours = args.hours if args.hours is not None else F.get("lookback_hours", 72)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    matches, errors, hints = [], [], []
    report = []  # one entry per source: what ran, what it returned, what was skipped and why
    stats = {"boards": 0, "raw_jobs": 0, "title_hits": 0, "dropped": {k: 0 for k in DROP_REASONS}}
    for b in board_list:
        company, ats, slug = b["company"], b["ats"], b["slug"]
        if args.company and args.company.lower() not in company.lower():
            continue
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            errors.append(f"{company}: unknown ats '{ats}'")
            continue
        try:
            # Workday has no "list the whole board" mode (see from_workday's docstring): it needs a
            # search term per call, so it's the one fetcher that takes your own include_titles too.
            jobs = fetcher(company, slug, F["include_titles"]) if ats == "workday" else fetcher(company, slug)
        except urllib.error.HTTPError as e:
            errors.append(f"{company} ({ats}:{slug}): HTTP {e.code} (bad slug?)")
            continue
        except Exception as e:
            errors.append(f"{company} ({ats}:{slug}): {type(e).__name__} {str(e)[:70]}")
            continue
        stats["boards"] += 1
        stats["raw_jobs"] += len(jobs)
        for j in jobs:
            mm = consider(j, F, args, cutoff, stats)
            if mm:
                matches.append(mm)
    n_ats = len(matches)
    if board_list:
        report.append({"name": "ats-boards", "label": "Company ATS boards (boards.yaml)", "status": "ran",
                       "boards_listed": len(board_list), "boards_read": stats["boards"],
                       "jobs": stats["raw_jobs"], "matches": n_ats})
    else:
        report.append({"name": "ats-boards", "label": "Company ATS boards (boards.yaml)",
                       "status": "skipped", "jobs": 0, "matches": 0,
                       "reason": "boards.yaml has no company boards yet (run discover.py --sweep)"})
        hints.append(NO_BOARDS_HINT)

    # ---- free job APIs (sources.yaml). Each is fetched politely within its own terms; the same
    #      job seen on an ATS board above is not listed twice. Failures are non-fatal. ----
    if args.no_api:
        report.append({"name": "job-apis", "label": "Free job APIs (sources.yaml)", "status": "skipped",
                       "jobs": 0, "matches": 0, "reason": "--no-api"})
    else:
        try:
            api_jobs, api_report = api_sources.collect(F["include_titles"], cache_dir=CACHE_DIR)
        except Exception as e:  # a broken sources.yaml must never break the crawl
            api_jobs, api_report = [], [{"name": "job-apis", "label": "Free job APIs", "status": "error",
                                         "jobs": 0, "reason": f"{type(e).__name__} {str(e)[:80]}"}]
        seen = {(m["company"].lower(), m["title"].lower()) for m in matches}
        per = {}
        for j in api_jobs:
            if args.company and args.company.lower() not in (j.get("company") or "").lower():
                continue
            key = (j["company"].lower(), j["title"].lower())
            mm = consider(j, F, args, cutoff, stats)
            if mm and key not in seen:
                seen.add(key)
                matches.append(mm)
                per[j["source"]] = per.get(j["source"], 0) + 1
        for r in api_report:
            r["matches"] = per.get(r["name"], 0)
        report += api_report

    # ---- HN "Who's Hiring" source (on by default; --no-hn to skip). Failures are non-fatal:
    #      a hiccup here is reported under `errors` and never breaks the ATS crawl. ----
    hn_meta = None
    if not args.no_hn:
        n_before = len(matches)
        try:
            hn_jobs, hn_meta = hn.collect(F)
            for j in hn_jobs:
                if args.company and args.company.lower() not in (j.get("company") or "").lower():
                    continue
                mm = consider(j, F, args, cutoff, stats)
                if mm:
                    matches.append(mm)
            report.append({"name": "hn", "label": "HN Who's Hiring", "status": "ran",
                           "jobs": len(hn_jobs), "matches": len(matches) - n_before})
        except Exception as e:
            errors.append(f"hn (who's hiring): {type(e).__name__} {str(e)[:80]}")
            report.append({"name": "hn", "label": "HN Who's Hiring", "status": "error", "jobs": 0,
                           "matches": 0, "reason": f"{type(e).__name__} {str(e)[:80]}"})
    else:
        report.append({"name": "hn", "label": "HN Who's Hiring", "status": "skipped", "jobs": 0,
                       "matches": 0, "reason": "--no-hn"})

    matches.sort(key=rank_key, reverse=True)
    ro_hint = remote_only_hint(F, report, stats["dropped"])
    if ro_hint:
        hints.append(ro_hint)

    out = dict(generated=datetime.now(timezone.utc).isoformat(), lookback_hours=hours,
               boards=stats["boards"], raw_jobs=stats["raw_jobs"], title_hits=stats["title_hits"],
               count=len(matches),
               dropped=stats["dropped"], dropped_reasons=DROP_REASONS,
               count_by_source={s: sum(1 for m in matches if m["source"] == s)
                                for s in sorted({m["source"] for m in matches})},
               no_sponsor=sum(1 for m in matches if m.get("no_sponsor_flag")),
               ranking=ranking_note(F), location_rule=location_rule,
               sources=report,
               sources_note=("Sources are not a fixed set: company boards come from boards.yaml "
                             "(grow it with discover.py), job APIs from sources.yaml, plus HN. "
                             "`sources` lists each one, what it returned, and why any was skipped."),
               hints=hints, hn=hn_meta, matches=matches, errors=errors)
    if args.write:
        out["feed_written"] = write_feed(matches, hours, keywords_on=bool(F.get("include_keywords")))
        if TRACKER.exists():  # no tracker file -> feed only, no tracker key, no error
            out["tracker"] = patch_tracker(matches)
    for h in hints:
        print(h, file=sys.stderr)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
