#!/usr/bin/env python3
"""
Job crawler.

Pulls REAL postings straight from companies' public ATS boards (Greenhouse / Lever / Ashby)
AND the monthly Hacker News "Ask HN: Who is hiring?" thread, filters to your own target roles
(configured in filters.yaml), DROPS hard blockers you define (e.g. citizenship/clearance/ITAR
walls, if any apply to you), FLAGS soft "won't sponsor" postings (kept, not dropped, by default
— edit filters.yaml if this doesn't apply to your situation), and returns the fresh matches. $0,
no API keys, no login, no scraping of any login-walled platform (no account-ban risk). The whole
point is to catch a posting the day it goes up, before it's buried under a week of new listings.

HONESTY: this script only SELECTS real postings and copies their real fields. It never invents,
edits, embellishes, or generates anything about a job.

Reads:   boards.yaml (company -> ats + slug), filters.yaml (what to keep/drop).
Sources: the public ATS JSON, plus HN "Who's Hiring" via the free Algolia API (see hn.py).
Prints:  JSON of fresh matches to stdout.
--write also: rewrites ../job-feed.md (the review feed) and appends new, deduped `lead`
              rows to ../tracker.html's APPLICATIONS array (safely, with validation).

Usage:
  python3 crawl.py                  # fresh matches (last lookback_hours), JSON to stdout
  python3 crawl.py --write          # also update job-feed.md + tracker.html
  python3 crawl.py --hours 168      # widen the window to a week
  python3 crawl.py --company acme   # one company (also filters HN postings by that company)
  python3 crawl.py --all            # ignore the time window (still title/US/hard-wall filtered)
  python3 crawl.py --no-hn          # ATS boards only (skip the HN "Who's Hiring" source)
  python3 crawl.py --hide-no-sponsor# drop the "won't sponsor" postings too (default: keep + flag)
"""
import json, sys, argparse, re, html, functools, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

import hn  # sibling module: the HN "Who's Hiring" collector (same dir, on sys.path)

HERE = Path(__file__).resolve().parent
FEED = HERE.parent / "job-feed.md"        # pipeline/job-feed.md
TRACKER = HERE.parent / "tracker.html"    # pipeline/tracker.html
UA = "Mozilla/5.0 (personal job-search crawler; see pipeline/job-crawler/README.md)"


def load_yaml(name):
    import yaml  # PyYAML
    return yaml.safe_load((HERE / name).read_text())


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


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
                        # an old job edited today would read as fresh — prefer first_published.
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


FETCHERS = {"greenhouse": from_greenhouse, "ashby": from_ashby, "lever": from_lever}


def title_match(job, F):
    t = job["title"].lower()
    return next((it for it in F["include_titles"] if it in t), None)


def blocked(job, F):
    dl = (job["title"] + " " + job["description"]).lower()
    co = job["company"].lower()
    if any(x in co for x in F.get("exclude_companies", [])):
        return "excluded-company"
    hit = next((x for x in F.get("exclude_patterns", []) if x in dl), None)
    return f"blocker:{hit.strip()}" if hit else None


def sponsorship_flagged(job, F):
    """SOFT sponsorship signal — does the posting SAY it will not sponsor a visa? Scans the SAME
    text blocked() does (title + description). Unlike blocked(), a hit here NEVER drops the
    posting on its own: whether that matters to you depends on your own work-authorization
    situation (see knowledge-base/02-work-authorization.md). The hard walls — anything you've put
    in exclude_patterns — live in blocked(), and a posting that trips BOTH is dropped by blocked()
    first (a wall always wins). Leave filters.yaml's flag_patterns empty to disable this feature
    entirely. Returns bool."""
    dl = (job["title"] + " " + job["description"]).lower()
    return any(p in dl for p in F.get("flag_patterns", []))


@functools.lru_cache(maxsize=None)
def _block_re(terms):
    """Compile the location_block list into ONE word-boundary regex, cached per term-tuple.
    Word-boundary matching (not bare substring) avoids the collision class where a blocked
    country/city name is a substring of a genuine US place: 'india' inside 'Indianapolis, IN' /
    'Indiana', 'mexico' inside 'New Mexico'. Digits count as word chars so a term never bleeds
    into an adjacent token."""
    parts = [r"(?<![a-z0-9])" + re.escape(t.strip()) + r"(?![a-z0-9])"
             for t in terms if t and t.strip()]
    return re.compile("|".join(parts)) if parts else None


def location_ok(job, F):
    """US-only gate: drop a posting only if its location names a clearly non-US place AND names
    no US marker. Remote/unknown locations are kept. The block list matches on WORD BOUNDARIES
    (see _block_re), so a genuine US location whose name merely CONTAINS a blocked substring —
    'Indianapolis, IN' / 'Indiana' (india), 'Albuquerque, New Mexico' (mexico) — is not silently
    dropped; its us_markers entry ('new mexico' / ', nm') asserts its US-ness instead."""
    if not F.get("require_us"):
        return True
    loc = (job["location"] or "")
    if not loc.strip():
        return True
    ll = loc.lower()
    br = _block_re(tuple(F.get("location_block", [])))
    blocked_hit = bool(br and br.search(ll))
    us_hit = any(u in ll for u in F.get("us_markers", []))
    return not (blocked_hit and not us_hit)


def score(job, F):
    """Score = count of include_keywords hits. Add your own bonus terms straight into
    filters.yaml's include_keywords rather than hardcoding a title bonus here — that keeps every
    scoring rule in one user-editable place instead of split between config and code."""
    dl = (job["title"] + " " + job["description"]).lower()
    return sum(1 for k in F.get("include_keywords", []) if k in dl)


def consider(j, F, args, cutoff, stats):
    """Run one normalized posting (from ANY source) through the shared gates — title match,
    reject patterns, US-location, freshness — and return a match dict (carrying provenance
    `source`) or None. Used identically for ATS boards and HN so both obey the same filters.yaml.
    Increments stats['title_hits'] on a title-match hit (across all sources)."""
    m = title_match(j, F)
    if not m:
        return None
    stats["title_hits"] += 1
    if blocked(j, F):
        return None
    if not location_ok(j, F):
        return None
    if not args.all and j["posted_at"] and j["posted_at"] < cutoff:
        return None
    # SOFT no-sponsor flag: keep the posting, tag it. --hide-no-sponsor drops the flagged ones.
    no_sponsor = sponsorship_flagged(j, F)
    if no_sponsor and getattr(args, "hide_no_sponsor", False):
        return None
    return dict(company=j["company"], title=j["title"], location=j["location"], url=j["url"],
                posted_at=j["posted_at"].isoformat() if j["posted_at"] else None,
                remote=j["remote"], score=score(j, F), matched=m, source=j.get("source", "ats"),
                no_sponsor_flag=no_sponsor)


# ---- outputs: the review feed + the tracker leads ----
def _md_esc(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


_SRC_LABEL = {"hn": "HN Who's Hiring", "ats": "ATS board"}


def write_feed(matches, hours):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nflag = sum(1 for m in matches if m.get("no_sponsor_flag"))
    meta = (f"_Generated {now} · last {hours}h · {len(matches)} match(es)"
            + (f" · {nflag} ⚠ no-sponsor" if nflag else "") + " · via `pipeline/job-crawler/crawl.py`._")
    L = ["# Job feed — fresh roles, from company ATS boards + HN Who's Hiring", "",
         meta, "",
         "Real postings only, pulled straight from the source. Sources: your target companies' "
         "public ATS boards, plus the monthly Hacker News \"Who is hiring?\" thread (shown in the "
         "Source column). Filtered per `filters.yaml`'s title/keyword/location rules. HN posts are "
         "freeform, so verify company, role, and any sponsorship claim on the source before "
         "applying.", ""]
    if nflag:
        L += ["**⚠ no-sponsor flag (Flag column):** the posting says it will not sponsor a visa. "
              "It is KEPT here, not dropped, by default — whether that matters depends on your own "
              "work-authorization situation (`knowledge-base/02-work-authorization.md`). Edit "
              "`filters.yaml`'s `flag_patterns` if you'd rather these were dropped outright, or run "
              "with `--hide-no-sponsor`.", ""]
    L += ["| Score | Company | Role | Location | Posted | Source | Flag | Apply |",
          "|:-:|---|---|---|---|---|:-:|---|"]
    for m in matches:
        src = _SRC_LABEL.get(m.get("source", "ats"), m.get("source", "ats"))
        flag = "⚠ no-sponsor" if m.get("no_sponsor_flag") else "—"
        L.append(f"| {m['score']} | **{_md_esc(m['company']) or '—'}** | {_md_esc(m['title'])} | "
                 f"{_md_esc(m['location']) or '—'} | {(m['posted_at'] or '')[:10]} | {src} | {flag} | "
                 f"[open]({m['url']}) |")
    if not matches:
        L.append("| — | — | _No fresh matches this run — widen with `--hours` or add boards._ "
                 "| — | — | — | — | — |")
    FEED.write_text("\n".join(L) + "\n")
    return str(FEED)


def _js_row(m):
    def q(s):
        return (s or "").replace("\\", "").replace('"', "'")
    posted = (m["posted_at"] or "")[:10]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flagged = bool(m.get("no_sponsor_flag"))
    spon = "no" if flagged else "ask"
    src_label = "HN Who's Hiring" if m.get("source") == "hn" else "the crawler"

    # A table cell holds a FACT, never a paragraph (docs/DESIGN.md's table law) — `next` is a
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
             + " Read the full JD before tailoring, never a summary."
             " A referral is generally the strongest lever on a callback; being early is a real"
             " but modest edge (CLAUDE.md §5).")
    if flagged:
        notes = ("This posting states it will not sponsor. Whether that rules it out depends on"
                 " your own work-authorization situation — see knowledge-base/02-work-authorization.md"
                 " and answer any form question exactly per knowledge-base/12-application-answers.md §3,"
                 " never by assumption. " + notes)
    if m.get("source") == "hn":
        notes = ("Freeform HN post, so the company, role, and location are unverified. Check them on"
                 " the source before applying. " + notes)

    url = m["url"]
    posted_js = f'"{posted}"' if posted else "null"
    # Full per-job record: fresh crawler rows carry the same schema as every other row. source is
    # always "crawl-jobs" here; jd/apply = the real posting URL; folder/refs/everify start empty
    # (no dossier, no referral, work-auth-enrollment unverified, never guessed). Missing values
    # render as the no-data glyph in the tracker, never a fake value.
    return (f'  {{co:"{q(m["company"]) or ""}", role:"{q(m["title"])}", loc:"{q(m["location"]) or ""}", '
            f'comp:null, compK:null, status:"lead", fit:"watch", spon:"{spon}",\n'
            f'   posted:{posted_js}, source:"crawl-jobs", jd:"{url}", apply:"{url}", folder:null, refs:0, everify:"unknown",\n'
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
        return {"error": "APPLICATIONS array marker not found — NOT patched", "added": 0}
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
    return {"error": "post-patch validation failed — tracker NOT written", "added": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument("--all", action="store_true", help="ignore the lookback window")
    ap.add_argument("--write", action="store_true", help="write job-feed.md + patch tracker.html")
    ap.add_argument("--no-hn", action="store_true",
                    help="skip the HN 'Who's Hiring' source (ATS boards only)")
    ap.add_argument("--hide-no-sponsor", action="store_true",
                    help="exclude postings flagged 'no sponsorship' (default: include + flag them)")
    args = ap.parse_args()

    boards = load_yaml("boards.yaml")
    F = load_yaml("filters.yaml")
    board_list = boards.get("boards", boards) if isinstance(boards, dict) else boards
    hours = args.hours if args.hours is not None else F.get("lookback_hours", 72)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    matches, errors = [], []
    stats = {"boards": 0, "raw_jobs": 0, "title_hits": 0}
    for b in board_list:
        company, ats, slug = b["company"], b["ats"], b["slug"]
        if args.company and args.company.lower() not in company.lower():
            continue
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            errors.append(f"{company}: unknown ats '{ats}'")
            continue
        try:
            jobs = fetcher(company, slug)
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

    # ---- HN "Who's Hiring" source (on by default; --no-hn to skip). Failures are non-fatal:
    #      a hiccup here is reported under `errors` and never breaks the ATS crawl. ----
    hn_meta = None
    if not args.no_hn:
        try:
            hn_jobs, hn_meta = hn.collect(F)
            for j in hn_jobs:
                if args.company and args.company.lower() not in (j.get("company") or "").lower():
                    continue
                mm = consider(j, F, args, cutoff, stats)
                if mm:
                    matches.append(mm)
        except Exception as e:
            errors.append(f"hn (who's hiring): {type(e).__name__} {str(e)[:80]}")

    matches.sort(key=lambda r: (r["score"], r["posted_at"] or ""), reverse=True)

    out = dict(generated=datetime.now(timezone.utc).isoformat(), lookback_hours=hours,
               boards=stats["boards"], raw_jobs=stats["raw_jobs"], title_hits=stats["title_hits"],
               count=len(matches),
               count_by_source={s: sum(1 for m in matches if m["source"] == s)
                                for s in sorted({m["source"] for m in matches})},
               no_sponsor=sum(1 for m in matches if m.get("no_sponsor_flag")),
               hn=hn_meta, matches=matches, errors=errors)
    if args.write:
        out["feed_written"] = write_feed(matches, hours)
        out["tracker"] = patch_tracker(matches)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
