#!/usr/bin/env python3
"""doctor.py: is this clone ready to run? One health check for a new user or the agent.

Every check prints one line, and every line that is not OK carries a plain-language fix. It makes
no network calls. It reads files and asks the local `node` for its version; that is all.

    python3 scripts/doctor.py              # everything
    python3 scripts/doctor.py --fill       # only what filling an application form needs
    python3 scripts/doctor.py --json       # the same checks as JSON (combine with --fill)
    python3 scripts/doctor.py --selftest   # synthetic temp dirs only; never reads your files

Exit 0 = all OK. Exit 1 = warnings only. Exit 2 = at least one blocker. With --fill, only the
form-filling checks count toward the exit code (crawler and PDF-rendering checks are not run).
--fill always ends with the steps to turn the browser tool on, under the heading
"If your tool list has no browser tool", because a green config check cannot see a server the user
declined at the approval prompt.

Why this exists: a fresh clone that had no browser tool configured left the agent telling its user
to fill application forms by hand. `--fill` turns that silent gap into exit 2 with the exact steps
to turn the browser tool on, for Claude Code and for Codex.

What it cannot see: whether the agent session you are in actually loaded a browser tool. It
checks the configuration and Node only. Inside a session, the agent then checks its own tool list,
and any browser automation tool it actually has counts (the one configured here or another one);
with one present it fills the form even if this script reports the configuration as missing.

Unfilled-KB detection reuses the gates' own logic rather than inventing a new one:
  * KB-12 §3: `visa_gate.load_expected()` returns None until the block is truly filled.
  * KB-07: `resume_gate._parse_canonical_facts()` on the canonical-facts block, with the same
    "a value still wrapped in [brackets] is a template placeholder" rule visa_gate uses.
  * KB-01 / KB-02: the same bracket-placeholder rule, applied to the fields an employer sees.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import resume_gate  # noqa: E402  (reused parser: canonical-facts block)
import visa_gate  # noqa: E402  (reused parser: work-authorization block)

OK, WARN, BLOCK = "ok", "warn", "block"
MARK = {OK: "OK  ", WARN: "WARN", BLOCK: "STOP"}
MCP_PKG = "chrome-devtools-mcp@1.10.1"
# chrome-devtools-mcp 1.10.1 package.json engines (registry.npmjs.org, read 2026-10-22).
NODE_ENGINES = "^20.19.0 || ^22.12.0 || >=23"
# Same placeholder rule as visa_gate.load_expected(): a value still wrapped in [brackets]
# (or <angle brackets>, the canonical-facts template's own style) is unfilled template text.
PLACEHOLDER = re.compile(r"^\s*[\[<]")

ENABLE_HEADING = "If your tool list has no browser tool:"
ENABLE_STEPS = (
    "  1. Install Node.js 20.19+ or 22.12+ (https://nodejs.org) and Google Chrome\n"
    "     (https://www.google.com/chrome/), then open a new terminal.\n"
    "  2. Claude Code: the repo's .mcp.json already lists `chrome-devtools`. Start `claude` from\n"
    "     the repo folder and approve the `chrome-devtools` project server when asked. Then type\n"
    "     /mcp: if `chrome-devtools` shows as disabled, enable it there. If you said no to the\n"
    "     approval prompt earlier, quit, run `claude mcp reset-project-choices`, start `claude`\n"
    "     again and approve it.\n"
    "  3. Codex: .codex/config.toml already lists it; Codex only reads that file for a trusted\n"
    "     project, so trust this folder when Codex asks. Or add it for yourself:\n"
    f"     `codex mcp add chrome-devtools -- npx -y {MCP_PKG}`\n"
    "  4. Restart the session so the agent picks the tool up, then run this check again.\n"
    "The first start downloads the tool with npx, so it needs internet and can take a minute.\n"
    "It opens its own separate Chrome profile, never your everyday browser.")
# The one sentence for what the agent does when its session has no browser tool at all. The same
# words sit in .claude/rules/application-protocol.md section 14 and .claude/commands/wave.md 7.0.
NO_TOOL_LINE = ("With no browser tool in its session at all, the agent gives you these steps and "
                "stops at the form; once you restart, it fills the form. It never asks you to fill "
                "the form by hand.")
# The blockers a session's own browser tool makes moot: the agent can still fill with that tool.
TOOL_ONLY_BLOCKERS = {"node", "browser-tool"}


def check(name, status, msg, fix="", fill=False):
    return {"name": name, "status": status, "message": msg, "fix": fix, "fill": fill}


def _read(p: Path):
    """File text, or None if missing; ('unreadable', err) if it exists but cannot be read."""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    except OSError as e:
        return ("unreadable", str(e))


# Python, packages

def check_python(version=None):
    v = version or sys.version_info[:3]
    if tuple(v[:2]) >= (3, 9):
        return check("python", OK, f"Python {'.'.join(map(str, v))}", fill=True)
    return check("python", BLOCK, f"Python {'.'.join(map(str, v))} is too old",
                 "Install Python 3.9 or newer (https://www.python.org/downloads/).", fill=True)


def _importable(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def check_pyyaml(importable=_importable):
    if importable("yaml"):
        return check("pyyaml", OK, "PyYAML installed")
    return check("pyyaml", BLOCK, "PyYAML is missing (the job crawler needs it)",
                 "Run: python3 -m pip install -r pipeline/job-crawler/requirements.txt")


def _weasy_import_error():
    """None when `import weasyprint` works in this Python, else the exception's class name."""
    try:
        import weasyprint  # noqa: F401
        return None
    except Exception as e:  # missing, or present but its system libraries are not
        return type(e).__name__


def check_weasyprint(import_error=None, cli=None):
    """Résumé and cover-letter PDFs are rendered with the `weasyprint` command, so the command on
    PATH is enough. The Python import matters only to code that imports it; a working command
    (for example one installed by Homebrew or pipx, outside this Python) is reported as ready."""
    err = _weasy_import_error() if import_error is None else (import_error or None)
    path = shutil.which("weasyprint") if cli is None else (cli or None)
    if err is None:
        return check("weasyprint", OK, "weasyprint imports (PDF rendering ready)")
    if path:
        return check("weasyprint", OK, f"weasyprint command found at {path}; PDF rendering ready "
                     f"(this Python cannot import it: {err}, which the render commands do not need)")
    return check("weasyprint", WARN, f"weasyprint is not installed (no `weasyprint` command; import: {err})",
                 "Needed only to render résumé and cover-letter PDFs. Install it one way: "
                 "`python3 -m pip install weasyprint` (on macOS also `brew install pango`), or on macOS "
                 "`brew install weasyprint`, which puts the `weasyprint` command on your PATH. "
                 "See SETUP.md Troubleshooting.")


# Node + the browser tool

def _parse_ver(s: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def node_satisfies(ver) -> bool:
    """^20.19.0 || ^22.12.0 || >=23 (chrome-devtools-mcp's engines field)."""
    if not ver:
        return False
    major = ver[0]
    if major == 20:
        return ver >= (20, 19, 0)
    if major == 22:
        return ver >= (22, 12, 0)
    return major >= 23


def _node_version():
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or out.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def check_node(version_str=None, have_npx=None):
    vs = _node_version() if version_str is None else version_str
    npx = (shutil.which("npx") is not None) if have_npx is None else have_npx
    if vs is None or vs == "missing":
        return check("node", BLOCK, "Node.js is not installed (the browser tool runs on it)",
                     "Install Node.js 20.19+ or 22.12+ from https://nodejs.org, then open a new terminal.",
                     fill=True)
    ver = _parse_ver(vs)
    if not node_satisfies(ver):
        return check("node", BLOCK, f"Node.js {vs or '(version unreadable)'} is too old for the "
                     f"browser tool (needs {NODE_ENGINES})",
                     "Install Node.js 20.19+ or 22.12+ from https://nodejs.org, then open a new terminal.",
                     fill=True)
    if not npx:
        return check("node", BLOCK, f"Node.js {vs} found but `npx` is missing",
                     "Reinstall Node.js from https://nodejs.org (npx ships with it).", fill=True)
    return check("node", OK, f"Node.js {vs} and npx present", fill=True)


def find_chrome(platform=None, exists=None, which=None, env=None):
    """Path of an installed Google Chrome, or None. chrome-devtools-mcp drives Google Chrome
    (its README: "Chrome current stable version or newer"); it does not install one."""
    import os
    platform = platform or sys.platform
    exists = exists or os.path.exists
    which = which or shutil.which
    env = os.environ if env is None else env
    if platform == "darwin":
        app = "Google Chrome.app/Contents/MacOS/Google Chrome"
        cands = ["/Applications/" + app, str(Path.home() / "Applications" / app)]
    elif platform.startswith("win"):
        cands = [str(Path(env[k]) / "Google" / "Chrome" / "Application" / "chrome.exe")
                 for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if env.get(k)]
    else:
        found = next((w for w in (which(n) for n in ("google-chrome", "google-chrome-stable"))
                      if w), None)
        if found:
            return found
        cands = ["/opt/google/chrome/chrome"]
    return next((c for c in cands if exists(c)), None)


def check_chrome(path=None):
    """A warning, never a crash: Chrome may sit somewhere this check does not look."""
    where = find_chrome() if path is None else (path or None)
    if where:
        return check("chrome", OK, f"Google Chrome found at {where}", fill=True)
    return check("chrome", WARN, "Google Chrome was not found (the browser tool drives Chrome; it "
                 "does not install it)",
                 "Install Google Chrome from https://www.google.com/chrome/. If Chrome is already "
                 "installed somewhere unusual, this warning is safe to ignore.", fill=True)


def check_pymupdf(importable=_importable):
    """resume_gate.py and verify_claims.py (R9) read the rendered PDFs with PyMuPDF (`import
    fitz`). Without it the résumé gate fails and verify_claims refuses any dossier holding a PDF,
    which blocks the gate that runs right before a form is filled."""
    if importable("fitz"):
        return check("pymupdf", OK, "PyMuPDF installed (the résumé and grounding gates read PDFs)",
                     fill=True)
    return check("pymupdf", BLOCK, "PyMuPDF is missing (resume_gate.py and verify_claims.py read "
                 "the rendered PDFs with it)", "Run: python3 -m pip install pymupdf", fill=True)


def check_pdftotext(path=None):
    """Optional: the five-pass review (.claude/workflows/application-review.js) tells reviewers to
    read the PDF with `pdftotext -layout`. Without it they read the PDF another way."""
    where = shutil.which("pdftotext") if path is None else (path or None)
    if where:
        return check("pdftotext", OK, f"pdftotext found at {where}")
    return check("pdftotext", WARN, "pdftotext is not installed (optional: the five-pass review "
                 "reads the PDF with it)",
                 "Install poppler: macOS `brew install poppler`, Ubuntu/Debian "
                 "`apt install poppler-utils`, Windows: see https://poppler.freedesktop.org.")


def _mcp_has_server(text) -> bool | None:
    if text is None or isinstance(text, tuple):
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return False
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    entry = servers.get("chrome-devtools") if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        return False
    return "chrome-devtools-mcp" in " ".join([str(entry.get("command", ""))] +
                                             [str(a) for a in entry.get("args", [])])


def _codex_has_server(text) -> bool:
    if not isinstance(text, str):
        return False
    m = re.search(r"(?ms)^\[mcp_servers\.chrome-devtools\]\s*$(.*?)(?=^\[|\Z)", text)
    return bool(m and "chrome-devtools-mcp" in m.group(1))


def check_browser_config(root: Path):
    mcp_text = _read(root / ".mcp.json")
    codex = _codex_has_server(_read(root / ".codex" / "config.toml"))
    claude = _mcp_has_server(mcp_text)
    where = [n for n, v in (("Claude Code .mcp.json", claude), ("Codex .codex/config.toml", codex))
             if v]
    if claude and codex:
        return check("browser-tool", OK, "chrome-devtools is configured for Claude Code and Codex",
                     fill=True)
    if isinstance(mcp_text, tuple):
        note = "could not read .mcp.json (" + mcp_text[1] + ")"
    elif mcp_text is None:
        note = ".mcp.json is missing"
    elif claude is False:
        note = ".mcp.json has no chrome-devtools server"
    else:
        note = ""
    missing = []
    if not claude:
        missing.append(note or "Claude Code config missing")
    if not codex:
        missing.append(".codex/config.toml has no [mcp_servers.chrome-devtools]")
    status = WARN if where else BLOCK
    fix = ("Restore the repo's .mcp.json and .codex/config.toml (git checkout -- .mcp.json "
           ".codex/config.toml), then follow the steps under \"" + ENABLE_HEADING + "\" below.")
    return check("browser-tool", status,
                 ("configured for " + ", ".join(where) + "; " if where else "") + "; ".join(missing),
                 fix, fill=True)


# The four required knowledge-base files

KB = {
    "01": "knowledge-base/01-profile-and-identity.md",
    "02": "knowledge-base/02-work-authorization.md",
    "07": "knowledge-base/07-master-resume.md",
    "12": "knowledge-base/12-application-answers.md",
}


def _field(text: str, label: str):
    """Value after a `**Label:**` (or `**Question?**`) bullet, or None if the label is absent."""
    m = re.search(r"\*\*" + re.escape(label) + r":?\*\*:?[ \t]*(.*)", text)
    return m.group(1).strip() if m else None


def _unfilled_fields(text: str, labels) -> list:
    out = []
    for lab in labels:
        v = _field(text, lab)
        if v is None or not v or PLACEHOLDER.match(v):
            out.append(lab)
    return out


def kb01_problems(text: str) -> list:
    probs = [f"`{x}` not filled" for x in _unfilled_fields(text, ["Name", "Email", "Location"])]
    if "[Write your own here.]" in text:
        probs.append("`Who you are` still has the template line")
    return probs


def kb02_problems(text: str) -> list:
    labs = ["My status", "Do I need an employer to sponsor a visa, ever, for this to work?"]
    return [f"`{x}` not filled" for x in _unfilled_fields(text, labs)]


def kb07_problems(text: str) -> list:
    # The template's own header comment mentions ```canonical-facts, so anchor on a fence that
    # starts its own line and take the last one, then hand it to resume_gate's own parser.
    blocks = re.findall(r"(?ms)^```canonical-facts\n(.*?)^```", text)
    if not blocks:
        return ["no ```canonical-facts``` block"]
    facts = resume_gate._parse_canonical_facts("```canonical-facts\n" + blocks[-1] + "```")
    exact = dict(facts["exact"])
    probs = [f"canonical-facts `exact: {k}` not filled" for k in ("email", "title")
             if not exact.get(k) or PLACEHOLDER.match(exact[k])]
    if "[Your Full Name]" in text or "[Employer Name]" in text:
        probs.append("the résumé body still has template lines ([Your Full Name] / [Employer Name])")
    if "### WORK EXPERIENCE" not in text:
        probs.append("missing the exact heading `### WORK EXPERIENCE` (resume_gate.py reads it)")
    return probs


def kb12_problems(root: Path) -> list:
    saved = visa_gate.KB_ANSWERS
    visa_gate.KB_ANSWERS = root / KB["12"]
    try:
        expected = visa_gate.load_expected()
    finally:
        visa_gate.KB_ANSWERS = saved
    probs = [] if expected else ["§3 work-authorization block not filled (visa_gate.py reads it)"]
    text = _read(root / KB["12"])
    if isinstance(text, str):
        for lab in ("First name", "Last name", "Email"):
            m = re.search(r"^\|\s*" + re.escape(lab) + r"\s*\|\s*(.*?)\s*\|", text, re.M)
            if not m or not m.group(1) or PLACEHOLDER.match(m.group(1)):
                probs.append(f"§1 `{lab}` not filled")
    return probs


def check_kb(root: Path):
    out = []
    for num, rel in KB.items():
        text = _read(root / rel)
        if text is None:
            out.append(check(f"kb-{num}", BLOCK, f"{rel} is missing",
                             "Restore it with git checkout, then run /setup.", fill=True))
            continue
        if isinstance(text, tuple):
            out.append(check(f"kb-{num}", WARN, f"could not read {rel} ({text[1]})", fill=True))
            continue
        probs = {"01": lambda: kb01_problems(text), "02": lambda: kb02_problems(text),
                 "07": lambda: kb07_problems(text), "12": lambda: kb12_problems(root)}[num]()
        if probs:
            out.append(check(f"kb-{num}", BLOCK, f"{rel}: " + "; ".join(probs),
                             "Run /setup and the agent fills it from your answers and your résumé "
                             "(or edit the file by hand; its comments say what goes where).",
                             fill=True))
        else:
            out.append(check(f"kb-{num}", OK, f"{rel} filled", fill=True))
    return out


# Crawler config

def _yaml_load(text: str):
    try:
        import yaml
    except ImportError:
        return None
    try:
        return yaml.safe_load(text)
    except Exception:
        return "invalid"


def check_filters(root: Path):
    rel = "pipeline/job-crawler/filters.yaml"
    text = _read(root / rel)
    if not isinstance(text, str):
        return check("filters", BLOCK, f"{rel} is missing or unreadable",
                     "Restore it with git checkout, then run /setup.")
    data = _yaml_load(text)
    if data == "invalid":
        return check("filters", BLOCK, f"{rel} is not valid YAML", "Fix the YAML syntax it reports.")
    if isinstance(data, dict):
        titles = [str(t) for t in (data.get("include_titles") or [])]
    else:  # PyYAML missing: read the list by hand
        m = re.search(r"(?ms)^include_titles:\s*\n((?:\s+-.*\n?)+)", text)
        titles = [re.sub(r"\s+#.*$", "", ln.strip()[1:]).strip().strip("\"'")
                  for ln in (m.group(1).splitlines() if m else []) if ln.strip().startswith("-")]
    real = [t for t in titles if t.strip() and not t.strip().lower().startswith("example")]
    if real:
        return check("filters", OK, f"{len(real)} target title(s) in include_titles")
    return check("filters", BLOCK, f"{rel} has no job titles yet (include_titles ships empty, and "
                 "the crawler needs at least one)",
                 "Run /setup, or list your own role titles under include_titles.")


def _board_names_by_hand(text: str) -> list:
    """check_boards' fallback when PyYAML is missing: company names on non-comment lines only,
    so the commented `e.g.` example in boards.yaml never counts as a board."""
    live = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    return re.findall(r"company:\s*\"?([^\",}]+)", live)


def check_boards(root: Path):
    rel = "pipeline/job-crawler/boards.yaml"
    text = _read(root / rel)
    if not isinstance(text, str):
        return check("boards", WARN, f"{rel} is missing or unreadable",
                     "Restore it with git checkout.")
    data = _yaml_load(text)
    if isinstance(data, dict):
        boards = data.get("boards") or []
        names = [str(b.get("company", "")) for b in boards if isinstance(b, dict)]
    else:
        names = _board_names_by_hand(text)
    real = [n for n in names if n.strip() and not n.strip().lower().startswith("example")]
    if real:
        return check("boards", OK, f"{len(real)} company board(s) in boards.yaml")
    return check("boards", WARN, "boards.yaml has no company boards yet (it ships empty; the crawler "
                 "still reads the free job feeds in sources.yaml)",
                 "The agent can find boards for you: python3 pipeline/job-crawler/discover.py "
                 "--sweep (finds company boards with postings matching your titles), plus "
                 "--company \"Name\" for companies you name. /setup runs this.")


def check_config(root: Path):
    p = root / "scripts" / "config.py"
    if not p.is_file():
        return check("config", BLOCK, "scripts/config.py is missing", "Restore it with git checkout.")
    try:
        spec = importlib.util.spec_from_file_location("_doctor_config", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        return check("config", BLOCK, f"scripts/config.py does not import ({type(e).__name__}: {e})",
                     "Fix the line it names; every value there is optional, so the original file "
                     "(git checkout -- scripts/config.py) always works.")
    return check("config", OK, "scripts/config.py imports")


# Run

def run(root: Path, fill_only: bool = False, node=None, npx=None, importable=_importable,
        chrome=None, pdftotext=None):
    checks = [check_python(), check_node(node, npx), check_chrome(chrome),
              check_browser_config(root), check_pymupdf(importable)] + check_kb(root)
    if not fill_only:
        checks += [check_pyyaml(importable), check_weasyprint(), check_pdftotext(pdftotext),
                   check_filters(root), check_boards(root), check_config(root)]
    # --fill answers one question, "can the agent fill a form?", so only form-filling checks
    # count toward its exit code, whatever else a future edit adds to the list.
    counted = [c for c in checks if c["fill"]] if fill_only else checks
    statuses = {c["status"] for c in counted}
    code = 2 if BLOCK in statuses else 1 if WARN in statuses else 0
    return checks, code


def render(checks, code, fill_only) -> str:
    lines = [f"doctor.py: {'form-filling readiness' if fill_only else 'repo health'}"]
    for c in checks:
        lines.append(f"  [{MARK[c['status']]}] {c['name']}: {c['message']}")
        if c["status"] != OK and c["fix"]:
            lines += ["         fix: " + ln if i == 0 else "         " + ln
                      for i, ln in enumerate(c["fix"].splitlines())]
    blocked = [c["name"] for c in checks if c["status"] == BLOCK]
    if fill_only and code == 2:
        lines.append("")
        lines.append("FORM FILLING IS NOT READY (" + ", ".join(blocked) + ").")
        if set(blocked) <= TOOL_ONLY_BLOCKERS:
            lines.append("This reads the repo's configuration only, not the session. If the session the "
                         "agent is in already has ANY browser automation tool in its own tool list, the "
                         "agent uses that tool and fills the form anyway.")
        else:
            lines.append("Fix the STOP lines above first (/setup fixes the knowledge-base ones). The agent "
                         "fills no form until they pass: an empty or wrong knowledge base has nothing true "
                         "to type.")
    tool_lines = {"node", "chrome", "browser-tool"}
    if fill_only or any(c["name"] in tool_lines and c["status"] != OK for c in checks):
        lines.append("")
        lines.append(ENABLE_HEADING)
        lines.append(ENABLE_STEPS)
        lines.append(NO_TOOL_LINE)
    lines.append({0: "All OK.", 1: "OK with warnings.", 2: "Blockers found (exit 2)."}[code])
    return "\n".join(lines)


# Selftest (synthetic temp dirs only)

T01 = ("# Profile\n\n[Write your own here.]\n\n- **Name:** [Full legal name]\n"
       "- **Email:** [address]\n- **Location:** [City, State]\n")
F01 = ("# Profile\n\nI build billing systems at Acme.\n\n- **Name:** Jordan Rivera\n"
       "- **Email:** jordan.rivera@example.com\n- **Location:** Springfield, IL\n")
T02 = ("## Current status\n\n- **My status:** [Pick the one that's actually true, and be\n  specific]\n"
       "- **Do I need an employer to sponsor a visa, ever, for this to work?** [Yes / No]\n")
F02 = ("## Current status\n\n- **My status:** Authorized to work in the US without restriction.\n"
       "- **Do I need an employer to sponsor a visa, ever, for this to work?** No.\n")
T07 = ("<!-- opens with the literal line ```canonical-facts -->\n[Your Full Name]\n"
       "```canonical-facts\nexact: email | [your real email]\nexact: title | [your real title]\n```\n\n"
       "### WORK EXPERIENCE\n\n**[Employer Name], [Your Title]**\n")
F07 = ("<!-- opens with the literal line ```canonical-facts -->\nJordan Rivera\n"
       "```canonical-facts\nexact: email | jordan.rivera@example.com\nexact: title | Analyst\n```\n\n"
       "### WORK EXPERIENCE\n\n**Globex, Analyst** (Jan 2022 - Present)\n")
T12 = ("## 1. Identity\n\n| Field | Value |\n|---|---|\n| First name | [ ] |\n| Last name | [ ] |\n"
       "| Email | [ ] |\n\n## 3.\n\n```work-authorization\nauthorized-now: [YES/NO] | [why]\n"
       "sponsorship-to-begin: [YES/NO] | [why]\nsponsorship-now-or-future: [YES/NO] | [why]\n"
       "restricted-authorization: [YES/NO] | [why]\n```\n")
F12 = ("## 1. Identity\n\n| Field | Value |\n|---|---|\n| First name | Jordan |\n| Last name | Rivera |\n"
       "| Email | jordan.rivera@example.com |\n\n## 3.\n\n```work-authorization\n"
       "authorized-now: YES | citizen\nsponsorship-to-begin: NO | citizen\n"
       "sponsorship-now-or-future: NO | citizen\nrestricted-authorization: NO | citizen\n```\n")
MCP_OK = json.dumps({"mcpServers": {"chrome-devtools": {"command": "npx",
                                                         "args": ["-y", MCP_PKG]}}})
CODEX_OK = ('project_doc_max_bytes = 1\n\n[features]\nhooks = true\n\n'
            '[mcp_servers.chrome-devtools]\ncommand = "npx"\nargs = ["-y", "' + MCP_PKG + '"]\n')
FILTERS_T = "# include_titles:\n#   - data analyst\ninclude_titles: []\n"
FILTERS_F = "include_titles:\n  - data analyst\n  - example title two\n"
BOARDS_T = '#   e.g.  - {company: "Acme", ats: greenhouse, slug: "acme"}\n\nboards:\n'
BOARDS_F = BOARDS_T + '  - {company: "Initech", ats: lever, slug: "initech"}\n'


def _make(d: Path, filled: bool, mcp=True, codex=True):
    files = {KB["01"]: F01 if filled else T01, KB["02"]: F02 if filled else T02,
             KB["07"]: F07 if filled else T07, KB["12"]: F12 if filled else T12,
             "pipeline/job-crawler/filters.yaml": FILTERS_F if filled else FILTERS_T,
             "pipeline/job-crawler/boards.yaml": BOARDS_F if filled else BOARDS_T,
             "scripts/config.py": "OPERATOR_NAME = None\n",
             ".codex/config.toml": CODEX_OK if codex else "[features]\nhooks = true\n"}
    if mcp:
        files[".mcp.json"] = MCP_OK
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def selftest() -> int:
    ok = True

    def t(label, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {'✓' if good else '✗'} {label}" + ("" if good else f"  (got {got!r}, want {want!r})"))

    def status(checks, name):
        return next(c["status"] for c in checks if c["name"] == name)

    print("doctor.py --selftest")
    for v, want in (("v18.20.0", False), ("v20.18.9", False), ("v20.19.0", True), ("v21.7.0", False),
                    ("v22.11.0", False), ("v22.12.0", True), ("v23.0.0", True), ("v25.8.1", True),
                    ("garbage", False)):
        t(f"node {v} satisfies {NODE_ENGINES}: {want}", node_satisfies(_parse_ver(v)), want)
    t("python 3.8 blocks", check_python((3, 8, 10))["status"], BLOCK)
    t("python 3.9 passes", check_python((3, 9, 6))["status"], OK)
    t("missing node blocks", check_node("missing", True)["status"], BLOCK)
    t("node present without npx blocks", check_node("v22.12.0", False)["status"], BLOCK)
    t("pyyaml missing blocks", check_pyyaml(lambda m: False)["status"], BLOCK)
    t("weasyprint importable is OK", check_weasyprint("", "")["status"], OK)
    cli_only = check_weasyprint("ModuleNotFoundError", "/usr/local/bin/weasyprint")
    t("weasyprint command on PATH without the import is OK, naming the command",
      (cli_only["status"], "/usr/local/bin/weasyprint" in cli_only["message"]), (OK, True))
    neither = check_weasyprint("ModuleNotFoundError", "")
    t("no weasyprint at all is a warning offering pip or brew",
      (neither["status"], "brew install weasyprint" in neither["fix"]), (WARN, True))
    t("weasyprint is not a form-filling check", neither["fill"], False)

    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "fresh"
        _make(fresh, filled=False)
        checks, code = run(fresh, node="v22.12.0", npx=True, chrome="/c", importable=lambda m: True)
        for n in ("kb-01", "kb-02", "kb-07", "kb-12", "filters"):
            t(f"fresh clone: {n} is a blocker", status(checks, n), BLOCK)
        t("fresh clone: boards is a warning, naming discover.py --sweep",
          (status(checks, "boards"), "discover.py --sweep" in
           next(c for c in checks if c["name"] == "boards")["fix"]), (WARN, True))
        t("fresh clone: browser tool configured", status(checks, "browser-tool"), OK)
        t("fresh clone exits 2", code, 2)
        t("KB-07 template's header-comment fence is not mistaken for the real block",
          any("exact: email" in p for p in kb07_problems(T07)), True)

        ready = Path(td) / "ready"
        _make(ready, filled=True)
        checks, code = run(ready, node="v22.12.0", npx=True, importable=lambda m: True, chrome="/c", pdftotext="/p")
        for n in ("kb-01", "kb-02", "kb-07", "kb-12", "filters", "boards", "config", "browser-tool"):
            t(f"filled clone: {n} OK", status(checks, n), OK)
        t("filled clone exits 0 or 1 (weasyprint is warn-only)", code in (0, 1), True)
        _, code = run(ready, fill_only=True, node="v22.12.0", npx=True, chrome="/c", importable=lambda m: True)
        t("--fill on a ready clone exits 0", code, 0)
        (ready / "pipeline/job-crawler/boards.yaml").write_text(BOARDS_T, encoding="utf-8")
        checks, code = run(ready, node="v22.12.0", npx=True, importable=lambda m: True, chrome="/c", pdftotext="/p")
        t("empty boards.yaml says it ships empty, not 'example boards'",
          ("ships empty" in next(c for c in checks if c["name"] == "boards")["message"],
           status(checks, "boards")), (True, WARN))
        _, code = run(ready, fill_only=True, node="v22.12.0", npx=True, chrome="/c", importable=lambda m: True)
        t("--fill exit ignores a crawler warning (empty boards)", code, 0)
        t("without PyYAML, a commented example board is not counted",
          (len(_board_names_by_hand(BOARDS_T)), len(_board_names_by_hand(BOARDS_F))), (0, 1))
        (ready / "pipeline/job-crawler/boards.yaml").write_text(BOARDS_F, encoding="utf-8")

        nobrowser = Path(td) / "nobrowser"
        _make(nobrowser, filled=True, mcp=False, codex=False)
        checks, code = run(nobrowser, fill_only=True, node="v22.12.0", npx=True, chrome="/c", importable=lambda m: True)
        t("--fill with no browser tool exits 2", code, 2)
        out = render(checks, code, True)
        t("--fill blocker prints Claude Code and Codex enable steps",
          all(s in out for s in ("reset-project-choices", "codex mcp add chrome-devtools", MCP_PKG)),
          True)
        t("--fill skips crawler checks", any(c["name"] == "filters" for c in checks), False)
        t("--fill with only browser blockers says the session's own tool still fills",
          "fills the form anyway" in out, True)

        # D1: a user who declined the approval prompt has a green config. --fill must still
        # print the enable steps (/mcp, reset-project-choices, restart), not only "All OK."
        checks, code = run(ready, fill_only=True, node="v22.12.0", npx=True, chrome="/c",
                           importable=lambda m: True)
        out = render(checks, code, True)
        t("--fill on a ready clone still prints the enable steps under their heading",
          (code, all(x in out for x in (ENABLE_HEADING, "/mcp", "reset-project-choices",
                                        "Restart the session", NO_TOOL_LINE))), (0, True))
        full_checks, full_code = run(ready, node="v22.12.0", npx=True, chrome="/c", pdftotext="/p",
                                     importable=lambda m: True)
        t("full run with the browser tool ready does not repeat the enable steps",
          ENABLE_HEADING in render(full_checks, full_code, False), False)

        # D2: an empty KB must not get "fills the form anyway" (wave.md 0a stops on it).
        checks, code = run(fresh, fill_only=True, node="v22.12.0", npx=True, chrome="/c",
                           importable=lambda m: True)
        out = render(checks, code, True)
        t("--fill on an empty KB says fix first, never 'fills the form anyway'",
          (code, "fills the form anyway" in out, "fills no form until they pass" in out),
          (2, False, True))

        # D5 / D6: Chrome, PyMuPDF and pdftotext.
        t("no Chrome is a warning, not a crash or a blocker", check_chrome("")["status"], WARN)
        t("Chrome found is OK", check_chrome("/Applications/x")["status"], OK)
        t("find_chrome on macOS finds the app bundle",
          find_chrome("darwin", exists=lambda p: p.startswith("/Applications/"),
                      which=lambda n: None, env={}) is not None, True)
        t("find_chrome on Linux uses google-chrome on PATH",
          find_chrome("linux", exists=lambda p: False,
                      which=lambda n: "/usr/bin/google-chrome" if n == "google-chrome" else None,
                      env={}), "/usr/bin/google-chrome")
        t("find_chrome on Windows reads Program Files",
          find_chrome("win32", exists=lambda p: p.endswith("chrome.exe"), which=lambda n: None,
                      env={"PROGRAMFILES": "C:/PF"}) is not None, True)
        t("find_chrome returns None when nothing is installed",
          find_chrome("linux", exists=lambda p: False, which=lambda n: None, env={}), None)
        t("PyMuPDF missing blocks form filling",
          (check_pymupdf(lambda m: m != "fitz")["status"], check_pymupdf(lambda m: True)["fill"]),
          (BLOCK, True))
        t("pdftotext missing is a warning, not a form-filling check",
          (check_pdftotext("")["status"], check_pdftotext("")["fill"]), (WARN, False))
        checks, code = run(ready, fill_only=True, node="v22.12.0", npx=True, chrome="",
                           importable=lambda m: True)
        t("--fill with no Chrome exits 1 (warning), not 2", code, 1)

        half = Path(td) / "half"
        _make(half, filled=True, mcp=True, codex=False)
        t("Claude config only is a warning, not a blocker",
          check_browser_config(half)["status"], WARN)
        _, code = run(ready, fill_only=True, node="v18.0.0", npx=True, chrome="/c", importable=lambda m: True)
        t("--fill with Node 18 exits 2", code, 2)

        broken = Path(td) / "broken"
        _make(broken, filled=True)
        (broken / "scripts" / "config.py").write_text("OPERATOR_NAME = (\n", encoding="utf-8")
        t("config.py syntax error blocks", check_config(broken)["status"], BLOCK)
        (broken / ".mcp.json").write_text("{not json", encoding="utf-8")
        t("malformed .mcp.json is not counted as configured",
          _mcp_has_server(_read(broken / ".mcp.json")), False)

        js = json.loads(json.dumps({"exit": code, "checks": checks}))
        t("--json payload round-trips", isinstance(js["checks"], list), True)

    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    fill_only = "--fill" in argv
    checks, code = run(REPO, fill_only=fill_only)
    if "--json" in argv:
        print(json.dumps({"exit": code, "mode": "fill" if fill_only else "all", "checks": checks},
                         indent=2, ensure_ascii=False))
    else:
        print(render(checks, code, fill_only))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
