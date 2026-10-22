#!/usr/bin/env python3
"""account_guard.py: the account-safety rule, enforced as a PreToolUse + PostToolUse hook.

WHY. Sites like LinkedIn watch for automated access. An agent that opens profiles, reads pages or
clicks around inside YOUR logged-in browser looks exactly like a scraping tool, and the platform can
restrict or ban the account. A restricted LinkedIn account mid-search costs you your network, your
referrals and your inbox. Other major accounts (email, social, job boards that ban automation) carry
the same risk. Each single agent call looks harmless ("just one page, read only"); the volume adds up
quietly over weeks. So the rule is a hook, not a habit: a PreToolUse exit 2 means the call never runs,
in every permission mode, bypass included, on anyone's instruction.

WHAT IT BLOCKS.
  TIER 0, never touch (LinkedIn: linkedin.com, lnkd.in, licdn.com): blocked for every agent tool
          that can reach a network: any browser tool, WebFetch, scraper MCP tools (any tool named for
          LinkedIn, or carrying a LinkedIn URL), computer-use, and Bash fetches (curl, wget, python
          requests/urllib/httpx, node fetch, `open <url>` ...). No read, no "just one page".
  TIER 1, your other major accounts (mail, Google account pages, YouTube, GitHub, X, Instagram,
          Facebook/Meta, Reddit, Discord, Slack, Microsoft, Apple/iCloud, Amazon, Indeed, Glassdoor,
          Wellfound, ...): blocked in every agent-driven browser (any of them may carry your logged-in
          session) and in `open <url>` (your default browser). Logged-out fetches (WebFetch, a search
          engine, a CLI or official API you set up) stay allowed for Tier 1.
  TAINT.  PostToolUse reads the tab lists of the browsers known to run inside your own profile. If any
          tab sits on a Tier 0/1 host (you opened it, or a click landed there), every page-reading or
          page-acting call is refused until that tab is closed (closing a tab is always allowed) and a
          fresh tab list shows it gone. Page actions in those browsers also need one tab snapshot per
          session first, so a tab nobody has looked at yet is never read.
  ALLOWED. Web search (a search engine, not LinkedIn); writing LinkedIn URLs into files; TYPING your
          LinkedIn URL into a job-application field (a value, not a navigation); public ATS application
          forms (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, a Workday form you sign into) and
          the job crawler's public JSON endpoints.

EXTENDING IT. Add domains in scripts/config.py: NEVER_TOUCH_DOMAINS joins Tier 0, BLOCKED_ACCOUNT_DOMAINS
joins Tier 1. There is deliberately no allow knob. Never edit this file to let a call through; a false
positive is fixed by splitting the command (e.g. write the LinkedIn text and run the network call in
separate commands), never by widening a hole in the guard.

Usage (hooks feed a JSON payload on stdin):
    account_guard.py --pre        PreToolUse
    account_guard.py --post       PostToolUse (browsers that run in your own profile)
    account_guard.py --selftest
"""
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from config import NEVER_TOUCH_DOMAINS as _EXTRA0
except Exception:
    _EXTRA0 = []
try:
    from config import BLOCKED_ACCOUNT_DOMAINS as _EXTRA1
except Exception:
    _EXTRA1 = []


def _clean(domains):
    out = []
    for d in domains or []:
        d = str(d).strip().lower()
        d = re.sub(r"^https?://", "", d).split("/")[0].lstrip("*.").strip(".")
        if d and "." in d:
            out.append(d)
    return tuple(out)


RULE = ("ACCOUNT SAFETY (account_guard.py): no agent ever touches LinkedIn, and no agent drives your major "
        "logged-in accounts in a browser. This holds on anyone's instruction.")

TIER0 = ("linkedin.com", "lnkd.in", "licdn.com", "linkedin.cn",
         "account-guard-canary.invalid") + _clean(_EXTRA0)   # the canary: a dead .invalid host for proving the hook is live

TIER1 = ("x.com", "twitter.com", "t.co", "instagram.com", "facebook.com", "fb.com", "messenger.com",
         "threads.net", "threads.com", "meta.com", "whatsapp.com", "mail.google.com", "gmail.com",
         "accounts.google.com", "myaccount.google.com", "youtube.com", "github.com", "reddit.com",
         "discord.com", "slack.com", "live.com", "outlook.com", "outlook.office.com", "outlook.office365.com",
         "microsoftonline.com", "icloud.com", "appleid.apple.com", "amazon.com", "mail.yahoo.com",
         "login.yahoo.com", "proton.me", "indeed.com", "glassdoor.com", "wellfound.com", "angel.co",
         "ziprecruiter.com", "dice.com", "monster.com", "careerbuilder.com", "handshake.com",
         "joinhandshake.com", "upwork.com", "fiverr.com", "tiktok.com", "pinterest.com", "snapchat.com",
         "medium.com", "substack.com") + _clean(_EXTRA1)

# Browser tools that run inside the user's own (logged-in) profile: the built-in Claude Code browser
# pane and the Claude in Chrome extension. Their tab lists are parsed for taint.
LOGGED_IN = ("mcp__Claude_Browser__", "mcp__claude-in-chrome__")
# Any other browser-automation MCP (chrome-devtools, playwright, puppeteer, browserbase ...). It MAY be
# attached to your real profile, so Tier 0 and Tier 1 navigations are refused there too.
OTHER_BROWSER = re.compile(r"(?i)^mcp__.*(chrome-devtools|playwright|puppeteer|browser|selenium|browserbase)")
SCRAPER = re.compile(r"(?i)scrap|crawl|fetch|extract|dataset|browse|search_engine|web_data")

# Page actions that never read or act on page content (always allowed; URL-bearing ones are URL-checked).
SAFE_PAGELESS = {"tabs_context", "tabs_close", "tabs_create", "tabs_select", "preview_list", "preview_stop",
                 "preview_logs", "preview_start", "navigate", "resize_window",
                 "tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "list_connected_browsers",
                 "select_browser", "switch_browser", "shortcuts_list"}

NAV_KEYS = {"url", "urls", "starturl", "start_url", "href", "link", "uri", "target_url", "page_url"}
JS_TOOLS = {"javascript_tool", "evaluate_script", "navigate_page", "browser_evaluate"}   # navigate_page carries initScript
JS_KEYS = {"text", "function", "code", "script", "expression", "initscript"}
JS_NET = re.compile(r"(?i)fetch\s*\(|XMLHttpRequest|\blocation\b|window\.open|\.href\s*=|navigate|sendBeacon|"
                    r"import\s*\(|WebSocket|EventSource|<iframe|\.src\s*=")
BASH_NET = re.compile(r"(?i)\b(?:curl|wget|httpie|xh|aria2c|lynx|w3m|links2?|playwright|puppeteer|selenium|"
                      r"webbrowser|urlopen|urllib|httpx|aiohttp|pycurl|scrapy|mechanize|axios|osascript|"
                      r"xdg-open|Invoke-WebRequest|iwr)\b|\brequests\.|http\.client|fetch\s*\(")
BASH_OPEN_SEG = re.compile(r"(?:^|[\s;&|(`$'\"])(?:xdg-)?open\s+([^\n;&|]*)", re.I)   # opens your own browser
DOMAIN = re.compile(r"(?i)(?<![a-z0-9@._-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![a-z0-9-])")
URL = re.compile(r"https?://[^\s\"'<>()\]\\]+", re.I)

STATE_DIR = Path(os.environ.get("ACCOUNT_GUARD_STATE_DIR") or Path.home() / ".claude-account-guard")


# host matching
def _match(host, tier):
    host = host.lower().strip(".")
    return next((d for d in tier if host == d or host.endswith("." + d)), None)


def hosts_in(text):
    return {m.group(1).lower() for m in DOMAIN.finditer(text or "")}


def first_hit(text, tier):
    for h in hosts_in(text):
        if _match(h, tier):
            return h
    return None


def _walk(obj, key=None):
    """Yield (key, string) for every string leaf, keeping the nearest dict key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, str(k).lower())
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v, key)
    elif isinstance(obj, str):
        yield key, obj


def short(tool):
    return tool.split("__")[-1] if tool.startswith("mcp__") else tool


# state (taint)
def _state_file():
    return STATE_DIR / "state.json"


def load_state():
    try:
        return json.loads(_state_file().read_text())
    except Exception:
        return {}


def save_state(st):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - 3 * 86400
        st = {k: v for k, v in st.items() if v.get("t", 0) >= cutoff}
        fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), prefix=".state-")
        with os.fdopen(fd, "w") as f:
            json.dump(st, f)
        os.replace(tmp, _state_file())
    except Exception:
        pass


def log_block(session, tool, why):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_DIR / "blocks.log", "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{session}\t{tool}\t{why}\n")
    except Exception:
        pass


# PreToolUse decision
def pre_decision(tool, tool_input, session="?", state=None):
    """Return a refusal reason, or None to allow. Pure given (tool, input, state)."""
    tool = tool or ""
    inp = tool_input if isinstance(tool_input, (dict, list)) else {"_": str(tool_input or "")}
    name = short(tool).lower()
    logged_in = tool.startswith(LOGGED_IN)
    browser = logged_in or bool(OTHER_BROWSER.match(tool))

    if tool in ("WebFetch", "web_fetch"):
        h = first_hit(json.dumps(inp), TIER0)
        return f"{tool} of {h}. No LinkedIn page, logged in or not." if h else None

    if tool == "Bash":
        cmd = inp.get("command", "") if isinstance(inp, dict) else str(inp)
        h0 = first_hit(cmd, TIER0)
        if h0 and BASH_NET.search(cmd):
            return (f"this Bash command fetches or opens {h0}. If you are NOT fetching it (the host is only "
                    f"text you are writing to a file), split the network call and that text into separate "
                    f"commands.")
        for seg in BASH_OPEN_SEG.findall(cmd):
            for u in URL.findall(seg):
                h = first_hit(u, TIER0) or first_hit(u, TIER1)
                if h:
                    return f"`open {u}` loads {h} in your own logged-in browser."
        return None

    if tool.startswith("mcp__computer-use__"):
        h = first_hit(json.dumps(inp), TIER0)
        return f"computer-use input names {h}." if h else None

    if tool.startswith("mcp__") and not browser:
        # Any other MCP tool: one named for LinkedIn is a LinkedIn scraper; a scraper-shaped tool may
        # not carry a LinkedIn host anywhere in its input; any tool may not take one as a URL.
        if "linkedin" in tool.lower():
            return f"{tool} is a LinkedIn tool. No LinkedIn data, by any route."
        scraper = bool(SCRAPER.search(name))
        for key, s in _walk(inp):
            if scraper or key in NAV_KEYS:
                h = first_hit(s, TIER0)
                if h:
                    return f"{tool} input names {h}. No LinkedIn data, by any route."
        return None

    if not browser:
        return None

    # Browsers: URL-bearing keys are navigations; JS that fetches/navigates is a navigation; typed form
    # VALUES are not (a job form's "LinkedIn profile" field legitimately takes your URL).
    for key, s in _walk(inp):
        if key in NAV_KEYS or (key in JS_KEYS and name in JS_TOOLS and JS_NET.search(s)):
            for tier in (TIER0, TIER1):
                h = first_hit(s, tier)
                if h:
                    return f"{short(tool)} would load {h} in a browser that may carry your logged-in session."
    # browser_batch: check each inner action as its own tool call
    if name == "browser_batch" and isinstance(inp, dict):
        prefix = tool[: -len("browser_batch")]
        for a in inp.get("actions") or []:
            if isinstance(a, dict):
                r = pre_decision(prefix + str(a.get("name", "")), a.get("input") or {}, session, state)
                if r:
                    return r

    # Taint: page reads/acts in a logged-in browser need a clean, known tab list.
    if logged_in and name not in SAFE_PAGELESS:
        st = (state if state is not None else load_state()).get(session, {})
        if st.get("tainted"):
            return (f"a tab in your logged-in browser is on {', '.join(st['tainted'])}. Do not read, click, type, "
                    f"screenshot or run scripts. Close that tab (closing is always allowed), or ask the user to "
                    f"close it, then list the tabs again to confirm it is gone.")
        if not st.get("seen"):
            return ("no tab snapshot yet this session. List the tabs first (always allowed), so a LinkedIn or "
                    "major-account tab is never read by accident.")
    return None


# PostToolUse: read tab lists from logged-in browser results
TAB_LINE = re.compile(r"tabId\s+[^\s:]+:[^\n]*?\(\s*\"?(https?://[^\s\")]+)")
ORIGIN_JSON = re.compile(r"\"origin\"\s*:\s*\"(https?://[^\"]*)\"")
CAPTURED = re.compile(r"captured at origin\s+(https?://[^\s)]+)", re.I)
NAVIGATED = re.compile(r"navigated to\s+(https?://\S+)", re.I)


def _flat(resp):
    if isinstance(resp, str):
        return resp
    try:
        return json.dumps(resp, ensure_ascii=False).replace("\\n", "\n").replace('\\"', '"')
    except Exception:
        return str(resp)


def post_update(tool, response, session, state):
    """Update the session's tab picture. Return a message if a Tier 0/1 tab is (still) open."""
    if not tool.startswith(LOGGED_IN):
        return None
    text = _flat(response)
    st = state.setdefault(session, {})
    st["t"] = time.time()
    if tool.startswith("mcp__Claude_Browser__"):
        full = TAB_LINE.findall(text) + ORIGIN_JSON.findall(text)
        partial = CAPTURED.findall(text) + NAVIGATED.findall(text)
    else:   # Claude in Chrome: its format varies, so any URL counts; a tab-list call is a full snapshot
        urls = URL.findall(text)
        is_list = short(tool) in ("tabs_context_mcp",) or "tabId" in text or "tab_id" in text
        full, partial = (urls, []) if is_list else ([], urls)
    bad_full = sorted({u for u in full if first_hit(u, TIER0) or first_hit(u, TIER1)})
    bad_partial = sorted({u for u in partial if first_hit(u, TIER0) or first_hit(u, TIER1)})
    if full:
        st["seen"] = True
        st["tainted"] = bad_full
    elif partial:
        st["seen"] = True
    if bad_partial:
        st["tainted"] = sorted(set(st.get("tainted") or []) | set(bad_partial))
    if st.get("tainted"):
        return (f"ACCOUNT GUARD: a tab in your logged-in browser is on {', '.join(st['tainted'])}. STOP. "
                f"Do not read, click, type, screenshot or script it. Close it, or tell the user, then list "
                f"the tabs again to confirm. {RULE}")
    return None


# hook entry points
def _payload(raw):
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return None


_SMELLS_TIER0 = re.compile(r"linkedin|lnkd\.in|licdn", re.I)


def run_pre(raw):
    data = _payload(raw)
    if data is None:   # unreadable payload: fail CLOSED only if it smells of LinkedIn
        if _SMELLS_TIER0.search(raw):
            print(f"ACCOUNT GUARD: unreadable tool payload mentioning LinkedIn. Refused. {RULE}", file=sys.stderr)
            return 2
        return 0
    tool, inp, sess = data.get("tool_name", ""), data.get("tool_input", {}), str(data.get("session_id", "?"))
    try:
        why = pre_decision(tool, inp, sess)
    except Exception as e:   # a guard bug must not open the door
        why = (f"guard error ({e.__class__.__name__}) on an input that mentions LinkedIn"
               if _SMELLS_TIER0.search(raw) else None)
    if why:
        log_block(sess, tool, why)
        print(f"ACCOUNT GUARD blocked {tool}: {why}\n{RULE} Tell the user what you needed; they do LinkedIn and "
              f"their own accounts by hand (give them the text to send, or ask for a screenshot or pasted text).",
              file=sys.stderr)
        return 2
    return 0


def run_post(raw):
    data = _payload(raw) or {}
    tool, sess = data.get("tool_name", ""), str(data.get("session_id", "?"))
    if not tool.startswith(LOGGED_IN):
        return 0
    state = load_state()
    try:
        msg = post_update(tool, data.get("tool_response", data.get("tool_result", "")), sess, state)
    except Exception:
        msg = None
    save_state(state)
    if msg:
        log_block(sess, tool, "tainted tab: " + msg[:160])
        print(msg, file=sys.stderr)
        return 2
    return 0


# selftest (synthetic cases only)
def selftest():
    B, C, D = "mcp__Claude_Browser__", "mcp__claude-in-chrome__", "mcp__chrome-devtools__"
    P = "mcp__plugin_chrome-devtools-mcp_chrome-devtools__"
    seen = {"s": {"seen": True, "t": time.time()}}
    taint = {"s": {"seen": True, "tainted": ["https://linkedin.com"], "t": time.time()}}
    cases = [
        ("built-in browser to linkedin.com", B + "navigate", {"url": "https://www.linkedin.com/in/x/"}, seen, True),
        ("built-in browser to bare www.linkedin.com", B + "navigate", {"url": "www.linkedin.com/feed"}, seen, True),
        ("batch hides a lnkd.in navigate", B + "browser_batch",
         {"actions": [{"name": "navigate", "input": {"url": "https://lnkd.in/abc"}}]}, seen, True),
        ("built-in browser to a Greenhouse form", B + "navigate",
         {"url": "https://job-boards.greenhouse.io/acme/jobs/123"}, seen, False),
        ("built-in browser to a Lever form", B + "navigate", {"url": "https://jobs.lever.co/globex/abc/apply"}, seen, False),
        ("built-in browser to a Workday form", B + "navigate",
         {"url": "https://initech.wd5.myworkdayjobs.com/en-US/careers/job/x"}, seen, False),
        ("built-in browser to x.com (Tier 1)", B + "navigate", {"url": "https://x.com/someone"}, seen, True),
        ("Claude in Chrome to github.com (Tier 1)", C + "navigate", {"url": "https://github.com/jordan-rivera"}, seen, True),
        ("Claude in Chrome to mail.google.com (Tier 1)", C + "navigate", {"url": "https://mail.google.com/mail/u/0"}, seen, True),
        ("automation Chrome to x.com (Tier 1, may be your profile)", D + "navigate_page",
         {"pageId": 1, "url": "https://x.com/a"}, seen, True),
        ("plugin chrome-devtools to indeed.com (Tier 1)", P + "new_page", {"url": "https://www.indeed.com/viewjob"}, seen, True),
        ("automation Chrome to linkedin.com", D + "new_page", {"url": "https://linkedin.com/company/x"}, seen, True),
        ("automation Chrome to an Ashby form", D + "new_page", {"url": "https://jobs.ashbyhq.com/northwind/1"}, seen, False),
        ("playwright MCP to linkedin.com", "mcp__playwright__browser_navigate", {"url": "https://www.linkedin.com/jobs"}, seen, True),
        ("automation Chrome fills a LinkedIn URL VALUE into a form", D + "fill_form",
         {"elements": [{"uid": "1_35", "value": "https://linkedin.com/in/jordan-rivera"}]}, seen, False),
        ("built-in browser types a LinkedIn URL into a form field", B + "form_input",
         {"ref": "ref_9", "value": "https://linkedin.com/in/jordan-rivera"}, seen, False),
        ("JS that fetches linkedin.com", B + "javascript_tool",
         {"action": "javascript_exec", "text": "await fetch('https://www.linkedin.com/voyager/api/me')"}, seen, True),
        ("JS that only reads a field holding a LinkedIn URL", D + "evaluate_script",
         {"function": "() => document.querySelector('#li').value === 'https://linkedin.com/in/jordan-rivera'"}, seen, False),
        ("navigate_page initScript that fetches linkedin", D + "navigate_page",
         {"pageId": 1, "url": "https://example.com", "initScript": "fetch('https://www.linkedin.com/x')"}, seen, True),
        ("WebFetch linkedin.com", "WebFetch", {"url": "https://www.linkedin.com/company/x", "prompt": "p"}, seen, True),
        ("WebFetch an Ashby board", "WebFetch", {"url": "https://jobs.ashbyhq.com/acme", "prompt": "p"}, seen, False),
        ("WebFetch x.com logged out (Tier 1 allowed)", "WebFetch", {"url": "https://x.com/acme", "prompt": "p"}, seen, False),
        ("scraper MCP named for LinkedIn", "mcp__somescraper__web_data_linkedin_person_profile", {"url": "x"}, seen, True),
        ("scraper MCP scraping a LinkedIn URL", "mcp__somescraper__scrape_as_markdown",
         {"url": "https://linkedin.com/in/a"}, seen, True),
        ("scraper MCP scraping elsewhere", "mcp__somescraper__scrape_as_markdown", {"url": "https://example.com"}, seen, False),
        ("notes MCP storing text that names linkedin.com", "mcp__notes__create_note",
         {"body": "follow up via linkedin.com/in/x"}, seen, False),
        ("curl linkedin.com", "Bash", {"command": "curl -sL https://www.linkedin.com/company/x -o a.html"}, seen, True),
        ("python requests to linkedin.com", "Bash",
         {"command": "python3 - <<'EOF'\nimport requests\nrequests.get('https://www.linkedin.com/in/x')\nEOF"}, seen, True),
        ("open a LinkedIn URL in your browser", "Bash", {"command": "open 'https://www.linkedin.com/in/x'"}, seen, True),
        ("xdg-open a LinkedIn URL", "Bash", {"command": "xdg-open https://www.linkedin.com/feed"}, seen, True),
        ("open instagram.com in your browser (Tier 1)", "Bash", {"command": "open https://instagram.com/x"}, seen, True),
        ('open -a "Google Chrome" linkedin.com', "Bash", {"command": 'open -a "Google Chrome" https://www.linkedin.com/feed'}, seen, True),
        ("osascript open location linkedin", "Bash", {"command": "osascript -e 'open location \"https://www.linkedin.com\"'"}, seen, True),
        ("python -m webbrowser linkedin", "Bash", {"command": "python3 -m webbrowser https://www.linkedin.com/in/x"}, seen, True),
        ("crawler hits Greenhouse JSON", "Bash",
         {"command": "curl -s https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"}, seen, False),
        ("crawler hits Lever JSON", "Bash", {"command": "curl -s 'https://api.lever.co/v0/postings/globex?mode=json'"}, seen, False),
        ("crawler hits Ashby JSON", "Bash",
         {"command": "curl -s https://api.ashbyhq.com/posting-api/job-board/northwind"}, seen, False),
        ("crawler run (python script, no host in command)", "Bash", {"command": "python3 pipeline/job-crawler/crawl.py"}, seen, False),
        ("gh CLI on github (official CLI allowed)", "Bash", {"command": "gh api repos/acme/x/issues"}, seen, False),
        ("typed text mentioning Location plus a LinkedIn URL", B + "computer",
         {"action": "type", "text": "Location: Springfield. LinkedIn: https://linkedin.com/in/jordan-rivera"}, seen, False),
        ("computer-use typing a linkedin URL", "mcp__computer-use__app_type", {"text": "https://linkedin.com/in/x"}, seen, True),
        ("grep for LinkedIn URLs in a file", "Bash", {"command": "grep -n 'linkedin.com/in/' applications/x/referrals.md"}, seen, False),
        ("python writes LinkedIn URLs into a file", "Bash",
         {"command": "python3 - <<'EOF'\nopen('r.md','a').write('https://www.linkedin.com/in/x/')\nEOF"}, seen, False),
        ("git commit mentioning linkedin.com", "Bash", {"command": "git commit -m 'note: linkedin.com/in/x'"}, seen, False),
        ("the canary host", B + "navigate", {"url": "https://account-guard-canary.invalid/"}, seen, True),
        ("look-alike host notlinkedin.com", B + "navigate", {"url": "https://notlinkedin.com/"}, seen, False),
        ("email address at gmail.com in a form value", B + "form_input", {"ref": "r", "value": "jordan@gmail.com"}, seen, False),
        ("page read with no tab snapshot yet", B + "get_page_text", {}, {}, True),
        ("page read after a clean snapshot", B + "get_page_text", {}, seen, False),
        ("page read while a LinkedIn tab is open", B + "get_page_text", {}, taint, True),
        ("tabs_close while tainted", B + "tabs_close", {"tabId": "tab-4"}, taint, False),
        ("Write a file full of LinkedIn URLs", "Write", {"file_path": "r.md", "content": "https://linkedin.com/in/x"}, seen, False),
        ("WebSearch site:linkedin.com", "WebSearch", {"query": "site:linkedin.com Jordan Rivera"}, seen, False),
    ]
    ok = True
    for label, tool, inp, state, want_block in cases:
        got = pre_decision(tool, inp, "s", state) is not None
        if got != want_block:
            ok = False
            print(f"  FAIL {label}: blocked={got}, expected {want_block}")
    # PostToolUse taint + clear
    st = {}
    tab_ctx = ('left_click\n\nTab Context:\n- Executed on tabId: tab-4\n- Available tabs:\n'
               '  - tabId tab-4: "LinkedIn" ("https://www.linkedin.com/feed/")')
    t1 = bool(post_update(B + "computer", tab_ctx, "p", st)) and bool(st["p"].get("tainted"))
    m2 = post_update(B + "tabs_context", {"tabs": [{"tabId": "seed", "origin": "https://jobs.lever.co", "isActive": True}]}, "p", st)
    t2 = (m2 is None) and not st["p"].get("tainted") and st["p"].get("seen")
    t3 = bool(post_update(B + "get_page_text", "Title\n(captured at origin https://linkedin.com)", "p", st))
    for label, good in [("post: a LinkedIn tab in the tab list taints the session", t1),
                        ("post: a clean tab list clears it", t2),
                        ("post: 'captured at origin linkedin.com' taints again", t3)]:
        if not good:
            ok = False
            print(f"  FAIL {label}")
    # Config extension: a user-added domain joins its tier.
    t4 = _match("www.acme-social.example", ("acme-social.example",)) == "acme-social.example"
    t5 = _clean(["https://*.Globex-Mail.example/x", "", "nodot"]) == ("globex-mail.example",)
    for label, good in [("config: an added domain matches its subdomains", t4),
                        ("config: added domains are normalized (scheme, wildcard, case)", t5)]:
        if not good:
            ok = False
            print(f"  FAIL {label}")
    # Hook entry points: exit codes, and an unreadable payload that smells of LinkedIn fails closed.
    import io
    import contextlib
    with contextlib.redirect_stderr(io.StringIO()):
        global STATE_DIR
        saved_dir = STATE_DIR
        STATE_DIR = Path(tempfile.mkdtemp(prefix="acct-guard-selftest-"))
        try:
            e1 = run_pre(json.dumps({"tool_name": "WebFetch", "tool_input": {"url": "https://linkedin.com/in/x"}})) == 2
            e2 = run_pre(json.dumps({"tool_name": "WebFetch", "tool_input": {"url": "https://jobs.lever.co/x"}})) == 0
            e3 = run_pre("{not json linkedin.com") == 2
            e4 = run_pre("{not json") == 0
        finally:
            STATE_DIR = saved_dir
    for label, good in [("run_pre exits 2 on a LinkedIn fetch", e1), ("run_pre exits 0 on an ATS fetch", e2),
                        ("run_pre fails closed on an unreadable LinkedIn payload", e3),
                        ("run_pre passes an unreadable unrelated payload", e4)]:
        if not good:
            ok = False
            print(f"  FAIL {label}")
    n = len(cases) + 9
    print(("account_guard selftest OK" if ok else "account_guard selftest FAILED") + f" ({n} cases)")
    return 0 if ok else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--selftest":
        return selftest()
    raw = sys.stdin.read()
    if mode == "--pre":
        return run_pre(raw)
    if mode == "--post":
        return run_post(raw)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
