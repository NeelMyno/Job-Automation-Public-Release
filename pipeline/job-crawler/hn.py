#!/usr/bin/env python3
"""
HN "Who's Hiring" collector.

The monthly "Ask HN: Who is hiring?" thread is a high-signal, FREE source for roles that never
reach an ATS board — especially early-stage/founding roles. This module finds the LATEST official
thread and turns each top-level comment into one candidate posting, in the SAME record shape the
ATS fetchers in crawl.py return, so crawl.py can run them through the identical filters.yaml gates
(title, reject patterns, US-location, freshness).

Source: the free Algolia Hacker News Search API (https://hn.algolia.com/api). $0, no key,
no login, no scraping — the same public JSON the HN site itself reads.

HONEST BY CONSTRUCTION (mirrors crawl.py): this module only SELECTS real comments and copies
their real fields. It never invents a company, role, or location. HN comments are freeform, so
a field that isn't cleanly present is returned empty (crawl.py renders that as an em-dash) —
never guessed. It filters CONSERVATIVELY: a comment is kept only if a title from your own
`include_titles` list appears in its header (the role line), not merely because a related word
shows up somewhere in the body.

Standalone module: no import of crawl.py (avoids a cycle). It reuses crawl.py's *vocabulary*
by taking the loaded filters `F` as an argument (include_titles, us_markers, location_block) —
so all title/geography knowledge stays in the one place, filters.yaml.
"""
import json, re, html, urllib.request, urllib.error
from datetime import datetime, timezone

ALGOLIA = "https://hn.algolia.com/api/v1"
HN_ITEM = "https://news.ycombinator.com/item?id={}"
UA = "Mozilla/5.0 (personal job-search crawler; see pipeline/job-crawler/README.md)"

# Header delimiters seen in real Who's-Hiring posts: pipes, bullets, and SPACED dashes
# (em/en/hyphen). Spaced-only for the hyphen so intra-word hyphens survive ("Full-Stack",
# "on-site", "Top-of-Funnel", "150-250k").
_DELIM = re.compile(r"\s*[|•·]\s*|\s+[—–]\s+|\s+-\s+")
_HREF = re.compile(r'href="([^"]+)"')
_REMOTE = re.compile(r"\bremote\b", re.I)
_ONSITE = re.compile(r"\b(on-?site|in-?person)\b", re.I)
_LOC_HINT = re.compile(r"\b(remote|on-?site|hybrid|anywhere|distributed|wfh|in-?person)\b", re.I)
_CITY_ST = re.compile(r",\s*[a-z]{2,}\.?\s*$", re.I)          # "..., WA" / "..., UK"
_CO_SUFFIX = {"inc", "inc.", "llc", "ltd", "co", "co.", "corp", "corp.",
              "gmbh", "srl", "bv", "plc", "ag", "sa", "oy", "ab"}


def _get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _clean(s):
    """Strip HTML tags, unescape entities, collapse whitespace."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


def _parse_ts(v):
    """ISO-8601 (with or without fractional seconds / Z) -> tz-aware UTC datetime, or None."""
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    for cand in (s, re.sub(r"\.\d+", "", s)):   # 2nd try drops fractional secs for py<3.11
        try:
            d = datetime.fromisoformat(cand)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def find_latest_thread():
    """Newest official 'Ask HN: Who is hiring?' story. Returns {id,title,created_at} or None.
    Requires author 'whoishiring' (the account that posts the monthly thread) so we never pick
    a sibling 'Who wants to be hired?' / 'freelancer' thread by another user."""
    d = _get(f"{ALGOLIA}/search_by_date?query=%22Ask%20HN%3A%20Who%20is%20hiring%3F%22"
             f"&tags=story&hitsPerPage=20")
    hits = d.get("hits", [])  # search_by_date returns newest-first

    def _ok(title):
        tl = (title or "").lower()
        return ("who is hiring" in tl and "wants to be hired" not in tl and "freelanc" not in tl)

    for h in hits:
        if h.get("author") == "whoishiring" and _ok(h.get("title")):
            return dict(id=str(h.get("objectID")), title=h.get("title"), created_at=h.get("created_at"))
    for h in hits:   # fallback: title matches even if the author account was renamed
        if _ok(h.get("title")):
            return dict(id=str(h.get("objectID")), title=h.get("title"), created_at=h.get("created_at"))
    return None


def fetch_top_level(story_id):
    """Top-level comments of the thread, normalized to {id,author,text,created_at}.
    Primary: the items endpoint (its `children` ARE the top-level comments).
    Fallback: the comment search endpoint, filtered to comments whose parent is the story."""
    try:
        d = _get(f"{ALGOLIA}/items/{story_id}", timeout=60)
        out = [dict(id=k.get("id"), author=k.get("author"), text=k.get("text"),
                    created_at=k.get("created_at"))
               for k in (d.get("children") or []) if k.get("text")]
        if out:
            return out
    except Exception:
        pass
    out, page = [], 0
    while True:
        d = _get(f"{ALGOLIA}/search?tags=comment,story_{story_id}&hitsPerPage=1000&page={page}")
        hits = d.get("hits", [])
        for h in hits:
            if str(h.get("parent_id")) == str(story_id) and h.get("comment_text"):
                out.append(dict(id=h.get("objectID"), author=h.get("author"),
                                text=h.get("comment_text"), created_at=h.get("created_at")))
        if not hits or page >= d.get("nbPages", 1) - 1:
            break
        page += 1
    return out


def _split_tokens(header):
    return [t.strip() for t in _DELIM.split(header) if t.strip()]


def _title_re(term):
    # word-boundary match, tolerating a trailing plural 's' ("designers", "engineers"), so
    # "design engineer" matches "design engineers" but NOT "design engineering".
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"s?(?![a-z0-9])", re.I)


def _match_title(header, tokens, F):
    """Does the header announce a role you want? Returns (matched_term, role_token) or (None,None).
    Matches against the header (where the role lives), word-boundary, so a company whose name
    happens to contain one of your title terms, or a body that merely mentions the word once,
    does NOT trigger a match."""
    for it in F.get("include_titles", []):
        rx = _title_re(it)
        if rx.search(header):
            role_token = next((t for t in tokens if rx.search(t)), None)
            return it, role_token
    return None, None


def _looks_location(token, F):
    tl = token.lower()
    if _LOC_HINT.search(tl) or _CITY_ST.search(tl):
        return True
    for g in list(F.get("us_markers", [])) + list(F.get("location_block", [])):
        g = (g or "").strip()
        if g and g in tl:
            return True
    return False


def _is_city_state(token):
    """'Blaine, WA' / 'Austin, TX' style — used to detect a location sitting in slot 0 (so the
    company is the next token), while NOT mistaking 'Foo, Inc.' for a location."""
    t = token.strip()
    if "," not in t:
        return False
    tail = t.rsplit(",", 1)[1].strip().lower()
    if tail in _CO_SUFFIX:
        return False
    return bool(re.fullmatch(r"[a-z]{2,}\.?", tail)) and len(tail) <= 24


def _company_and_location(tokens, role_token, F):
    """Best-effort, honest company + location from the header tokens. Returns ("" , "") shapes
    that crawl.py renders as em-dashes when a field can't be determined — never a guess."""
    if not tokens:
        return "", ""
    company = ""
    role_is_first = bool(role_token) and tokens and role_token == tokens[0]
    if role_is_first:
        # "Founding Designer at Acme | Remote" — pull the company after 'at'/'@' if present,
        # else the next non-location token; otherwise leave unknown (don't call the role a company).
        m = re.search(r"\b(?:at|@)\s+(.+)$", tokens[0], re.I)
        if m:
            company = m.group(1).strip()
        elif len(tokens) > 1 and not _looks_location(tokens[1], F):
            company = tokens[1]
    else:
        first = tokens[0]
        if _is_city_state(first) and len(tokens) > 1:
            company = tokens[1]        # location was in slot 0 (the "Blaine, WA | CaseLight" case)
        else:
            company = first
    # location: header tokens that read as a place, minus whatever we used as company/role
    used = {company, role_token}
    locs, seen = [], set()
    for t in tokens:
        if t in used or t in seen:
            continue
        if _looks_location(t, F):
            locs.append(t)
            seen.add(t)
    return company, "; ".join(locs)


def _first_apply_url(raw_text):
    for m in _HREF.finditer(raw_text):
        u = html.unescape(m.group(1))
        if "news.ycombinator.com" not in u:
            return u
    return None


def parse_comment(c, F):
    """One top-level comment -> a normalized posting dict (same shape crawl.py's ATS fetchers
    emit, plus `source`/`id`), or None if it does not clearly announce a role from your list."""
    raw = c.get("text") or ""
    if not raw.strip():
        return None
    header = _clean(re.split(r"<p>", raw, maxsplit=1)[0])   # first paragraph = the posting header
    if not header:
        return None
    tokens = _split_tokens(header)
    matched, role_token = _match_title(header, tokens, F)
    if not matched:                                        # conservative: no title match -> drop
        return None
    company, location = _company_and_location(tokens, role_token, F)
    cid = c.get("id")
    url = _first_apply_url(raw) or HN_ITEM.format(cid)
    remote = True if _REMOTE.search(header) else (False if _ONSITE.search(header) else None)
    return dict(
        company=company,                                   # "" -> crawl.py shows "—"
        title=role_token or matched,                       # the role line, for display + the gate
        location=location,                                 # "" -> unknown -> location gate keeps it
        url=url,
        posted_at=_parse_ts(c.get("created_at")),          # when THIS posting went up in the thread
        remote=remote,
        description=_clean(raw),                            # full comment -> reject-pattern scan
        source="hn",
        id=f"hn-{cid}",
    )


def collect(F, thread=None):
    """Find the latest thread, parse its top-level comments into matching postings.
    Returns (postings, meta). `meta` carries the thread provenance for the crawl JSON output.
    Never raises for an empty/absent thread — returns ([], meta) so the ATS crawl is unaffected."""
    th = thread or find_latest_thread()
    meta = dict(thread_id=None, thread_title=None, thread_url=None,
                raw_comments=0, matched_postings=0)
    if not th:
        return [], meta
    comments = fetch_top_level(th["id"])
    postings = []
    for c in comments:
        try:
            j = parse_comment(c, F)
        except Exception:
            j = None
        if j:
            postings.append(j)
    meta.update(thread_id=th["id"], thread_title=th.get("title"),
                thread_url=HN_ITEM.format(th["id"]), raw_comments=len(comments),
                matched_postings=len(postings))
    return postings, meta


if __name__ == "__main__":   # quick manual probe: python3 hn.py  (uses this dir's filters.yaml)
    import yaml
    from pathlib import Path
    F = yaml.safe_load((Path(__file__).resolve().parent / "filters.yaml").read_text())
    postings, meta = collect(F)
    print(json.dumps(dict(meta=meta,
                          sample=[{k: v for k, v in p.items() if k != "description"}
                                  for p in postings[:12]]), indent=2, default=str))
