#!/usr/bin/env python3
"""Codex-to-repo hook adapter.

The incident-earned repository checks remain in scripts/hooks.py. This file
only translates Codex hook payloads, optionally supplies and verifies a
configurable response timestamp (off by default; see config.py), and blocks
command shapes that Claude's local settings already prohibited.

Modes:
    --timestamp-inject
    --timestamp-stop
    --pre-tool
    --post-tool
    --post-edit
    --selftest
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from config import RESPONSE_TIMESTAMP
except ImportError:
    RESPONSE_TIMESTAMP = False
try:
    from config import local_stamp
except ImportError:  # an older config.py without the helper: this machine's local zone
    def local_stamp() -> str:
        t = datetime.now().astimezone()
        return f"{t:%Y-%m-%d} {t.strftime('%I:%M %p').lstrip('0')} {t.tzname() or ''}".rstrip()


REPO = Path(__file__).resolve().parents[1]
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.M)
FORCE_PUSH = re.compile(
    # A force-push is a history rewrite (forbidden; the point of the auto-commit convention is a
    # rewindable history that never gets rewritten). The flag forms are `--force` /
    # `--force-with-lease` / `-f`, but a `+`-prefixed REFSPEC (`git push origin +main`,
    # `+HEAD:main`) forces a non-fast-forward update with no flag at all. The command is
    # NORMALIZED before this runs (quotes stripped, whitespace collapsed; see the caller), so a
    # quoted refspec (`"+main"`), leading whitespace, and an env-var prefix
    # (`GIT_SSH_COMMAND=... git push`) all reduce to the plain form. The anchor accepts `git push`
    # at line start, after a shell separator, or after any whitespace (the env prefix).
    # ` \+(?=[\w/])` catches the refspec: a space, then `+`, then a ref character.
    r"(?:^|[;&|]|\s)git\s+push\b[^\n;&|]*(?:--force(?:-with-lease)?\b|-f\b|\s\+(?=[\w/]))", re.I
)
SENSITIVE = re.compile(
    # re.I: a case-insensitive filesystem serves `cat .MCP.JSON` as the real `.mcp.json`. A
    # case-sensitive guard let every upper/mixed-case spelling through.
    r"(?:^|[\s/\"'=:])(?:\.mcp\.json|\.env(?:\.[^\s/\"']+)?)", re.I
)
SAFE_SECRET_METADATA = re.compile(
    r"^\s*(?:git\s+(?:status|check-ignore)|grep\s+-l|wc\s+-c|shasum\b)", re.I
)
# The repo ships its own `.mcp.json` (the browser tool config, no keys in it), and doctor.py tells a
# user to restore it with `git checkout -- .mcp.json`. So a segment that names ONLY `.mcp.json` (never
# an .env file) may read it or restore it from git. Any write (a redirect, sed -i, rm, an editor) is
# still denied, and so is every .env command that is not metadata-only.
ENV_FILE = re.compile(r"(?:^|[\s/\"'=:])\.env(?:\.[^\s/\"']+)?", re.I)
SAFE_SHIPPED_MCP = re.compile(
    r"^\s*(?:git\s+(?:checkout\s+(?:HEAD\s+)?--|restore\b|show\b|diff\b|log\b)|cat\b|head\b|tail\b|less\b)",
    re.I,
)


def _segment_allowed(seg: str) -> bool:
    """A shell segment that touches a secret-looking file is allowed only when it is metadata-only,
    or when it reads or restores the shipped .mcp.json and names no .env file."""
    if SAFE_SECRET_METADATA.search(seg):
        return True
    return (not ENV_FILE.search(seg) and ">" not in seg and bool(SAFE_SHIPPED_MCP.search(seg)))


def read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def now_stamp() -> str:
    # config.TIMEZONE, or this machine's local zone when it is unset (config.local_stamp).
    return local_stamp()


def state_path(data: dict) -> Path:
    key = f"{data.get('session_id', '')}\0{data.get('turn_id', '')}"
    digest = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "repo-codex-hooks"
    return base / f"{digest}.json"


def save_expected_stamp(data: dict, stamp: str) -> None:
    try:
        p = state_path(data)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"stamp": stamp}) + "\n", encoding="utf-8")
    except Exception:
        pass


def load_expected_stamp(data: dict) -> str | None:
    try:
        value = json.loads(state_path(data).read_text(encoding="utf-8")).get("stamp")
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


def timestamp_inject(data: dict) -> dict | None:
    if not RESPONSE_TIMESTAMP:
        return None  # off by default; set config.RESPONSE_TIMESTAMP = True to enable
    stamp = now_stamp()
    save_expected_stamp(data, stamp)
    context = (
        f"CURRENT TIME, computed by the system clock just now: {stamp}\n\n"
        "MANDATORY: the FIRST line of every user-facing reply in this turn must be exactly:\n\n"
        f"📅 Response at: {stamp}\n\n"
        "Every earlier timestamp in this conversation is STALE. Do not copy one forward, infer "
        "the time, or substitute another time zone."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }


def normalized_first_line(message: str) -> str:
    lines = message.lstrip().splitlines()
    if not lines:
        return ""
    return re.sub(r"[*_]", "", lines[0]).strip()


def timestamp_stop(data: dict) -> dict | None:
    if not RESPONSE_TIMESTAMP:
        return None  # off by default; set config.RESPONSE_TIMESTAMP = True to enable
    if data.get("stop_hook_active"):
        return None
    message = data.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return None
    expected = load_expected_stamp(data)
    if not expected:
        return None  # fail open when the supplying hook did not leave a receipt
    wanted = f"📅 Response at: {expected}"
    got = normalized_first_line(message)
    if got == wanted:
        return None
    return {
        "decision": "block",
        "reason": (
            "MISSING OR STALE RESPONSE TIMESTAMP. Re-send the response with this exact first "
            f"line, copied verbatim from the turn's clock hook:\n\n{wanted}\n\n"
            f"The response began with: {got[:160] or '(no text)'}"
        ),
    }


def deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def pre_tool(data: dict) -> dict | None:
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    # Account safety: no agent touches LinkedIn, and no agent drives the user's major logged-in
    # accounts. scripts/account_guard.py owns the decision; this only routes Codex calls to it.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import account_guard
        why = account_guard.pre_decision(str(tool_name or ""), tool_input, str(data.get("session_id", "?")))
    except Exception as exc:  # a guard failure must not open the door on a LinkedIn-shaped call
        why = (f"account guard error ({exc.__class__.__name__})"
               if re.search(r"linkedin|lnkd\.in|licdn", json.dumps(data, default=str), re.I) else None)
    if why:
        return deny(f"ACCOUNT GUARD: {why} No agent touches LinkedIn or drives the user's major logged-in "
                    f"accounts (scripts/account_guard.py), on anyone's instruction.")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return None
    # Normalize before the force-push check: strip quotes and collapse whitespace so a quoted
    # refspec (`git push origin "+main"`), leading whitespace, and an env-var prefix all reduce to
    # the plain form the regex matches.
    if tool_name == "Bash":
        fp_cmd = re.sub(r"\s+", " ", command.replace('"', " ").replace("'", " "))
        if FORCE_PUSH.search(fp_cmd):
            return deny("Force-push is forbidden in this repo. Pull with rebase and push normally.")
    if tool_name in {"Bash", "apply_patch"} and SENSITIVE.search(command):
        _secret_deny = deny(
            "Do not read or modify .env files, and do not modify .mcp.json. Check .env only for "
            "presence or metadata with git status, git check-ignore, grep -l, wc -c, or shasum. "
            "The shipped .mcp.json may be read or restored (git checkout -- .mcp.json)."
        )
        if tool_name == "apply_patch":
            return _secret_deny
        # Per-SEGMENT, not per-command. SAFE_SECRET_METADATA is `^`-anchored, so the old check let
        # a safe LEADING verb whitelist the WHOLE compound command: `git status && cat .env` would
        # dump the secret. Split on the shell separators AND treat the inside of a
        # $(...)/backtick command substitution as its own segment: `wc -c $(cat .env)` has a
        # safe leading verb but RUNS `cat .env` inside the substitution, leaking the secret.
        # Deny if ANY segment that touches a secret file is not itself metadata-only.
        segs = re.split(r"&&|\|\||[;&|\n]", command)
        segs += [g for mm in re.finditer(r"\$\(([^)]*)\)|`([^`]*)`", command) for g in mm.groups() if g]
        for seg in segs:
            if SENSITIVE.search(seg) and not _segment_allowed(seg):
                return _secret_deny
    return None


def post_tool(data: dict) -> dict | None:
    """Codex PostToolUse for browser tools: the same tab-taint check `.claude/settings.json` runs
    (account_guard.py --post). A logged-in browser tab left on LinkedIn or a major account blocks
    further page actions until a fresh tab list shows it closed."""
    tool = str(data.get("tool_name") or "")
    try:
        import account_guard
        if not tool.startswith(account_guard.LOGGED_IN):
            return None
        session = str(data.get("session_id", "?"))
        state = account_guard.load_state()
        msg = account_guard.post_update(tool, data.get("tool_response", data.get("tool_result", "")), session, state)
        account_guard.save_state(state)
    except Exception:
        return None  # PostToolUse fails open; the PreToolUse guard still refuses Tier 0/1 targets
    if not msg:
        return None
    try:
        account_guard.log_block(session, tool, "tainted tab: " + msg[:160])
    except Exception:
        pass
    return {
        "decision": "block",
        "reason": msg,
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg},
    }


def patch_paths(data: dict) -> list[Path]:
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return []
    cwd = Path(data.get("cwd") or REPO)
    paths: list[Path] = []
    for raw in PATCH_FILE.findall(command):
        p = Path(raw.strip())
        paths.append((p if p.is_absolute() else cwd / p).resolve())
    return list(dict.fromkeys(paths))


def post_edit(data: dict) -> dict | None:
    messages: list[str] = []
    contexts: list[str] = []
    for path in patch_paths(data):
        payload = json.dumps({"tool_input": {"file_path": str(path)}})
        try:
            proc = subprocess.run(
                [sys.executable, str(REPO / "scripts" / "hooks.py"), "--post-edit"],
                cwd=REPO,
                input=payload,
                capture_output=True,
                text=True,
                timeout=40,
            )
            raw = proc.stdout.strip()
            if not raw:
                continue
            result = json.loads(raw)
            if result.get("systemMessage"):
                messages.append(str(result["systemMessage"]))
            ctx = (result.get("hookSpecificOutput") or {}).get("additionalContext")
            if ctx:
                contexts.append(str(ctx))
        except Exception:
            continue  # hook adapters fail open; Stop remains the backstop
    if not messages and not contexts:
        return None
    return {
        "systemMessage": " | ".join(messages),
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(contexts),
        },
    }


def selftest() -> int:
    checks: list[tuple[str, bool]] = []
    base = {"session_id": "selftest", "turn_id": "turn-1"}
    if RESPONSE_TIMESTAMP:
        injected = timestamp_inject(base) or {}
        expected = load_expected_stamp(base)
        checks.append(("timestamp injection has Codex envelope", injected.get("hookSpecificOutput", {}).get("hookEventName") == "UserPromptSubmit"))
        checks.append(("timestamp injection leaves a per-turn receipt", bool(expected)))
        compliant = dict(base, last_assistant_message=f"📅 Response at: {expected}\n\nHello")
        checks.append(("timestamp Stop allows the exact supplied line", timestamp_stop(compliant) is None))
        missing = dict(base, last_assistant_message="Hello")
        checks.append(("timestamp Stop blocks a missing line", (timestamp_stop(missing) or {}).get("decision") == "block"))
    else:
        checks.append(("timestamp injection no-ops when RESPONSE_TIMESTAMP is off", timestamp_inject(base) is None))
        idle = dict(base, last_assistant_message="Hello")
        checks.append(("timestamp Stop no-ops when RESPONSE_TIMESTAMP is off", timestamp_stop(idle) is None))
    checks.append(("the stamp carries a zone label (config.TIMEZONE or local)", bool(re.match(r"^\d{4}-\d\d-\d\d \d{1,2}:\d\d [AP]M \S+$", now_stamp()))))
    # PostToolUse tab taint (account_guard --post), on a throwaway state file.
    import account_guard
    saved_state_dir = account_guard.STATE_DIR
    with tempfile.TemporaryDirectory() as td:
        account_guard.STATE_DIR = Path(td)
        try:
            tabs_bad = {"tool_name": "mcp__claude-in-chrome__tabs_context_mcp", "session_id": "selftest-post",
                        "tool_response": 'tabId 1: Feed ("https://www.' + "linked" + 'in.com/feed")'}
            tabs_ok = {"tool_name": "mcp__claude-in-chrome__tabs_context_mcp", "session_id": "selftest-post",
                       "tool_response": 'tabId 1: Apply ("https://boards.greenhouse.io/acme/jobs/1")'}
            blocked = post_tool(tabs_bad) or {}
            checks.append(("🔴 post-tool: a logged-in tab left on LinkedIn blocks with a Codex envelope",
                           blocked.get("decision") == "block" and blocked.get("hookSpecificOutput", {}).get("hookEventName") == "PostToolUse"))
            checks.append(("post-tool: a fresh tab list with only an ATS form clears it", post_tool(tabs_ok) is None))
            checks.append(("post-tool: a non-browser tool is ignored", post_tool({"tool_name": "Bash", "tool_response": "linkedin.com"}) is None))
        finally:
            account_guard.STATE_DIR = saved_state_dir
    patch = "*** Begin Patch\n*** Update File: README.md\n*** Add File: .codex/x.json\n*** End Patch"
    paths = patch_paths({"cwd": str(REPO), "tool_input": {"command": patch}})
    checks.append(("multi-file apply_patch paths are extracted", {p.name for p in paths} == {"README.md", "x.json"}))
    checks.append(("force-push is denied wherever the flag appears", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "git push origin main --force"}}))))
    # A `+`-prefixed refspec forces a non-fast-forward push with no flag at all, and slipped both
    # this guard and the settings.json deny globs before it was named explicitly.
    checks.append(("🔴 force-push via +refspec is denied (git push origin +main)", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "git push origin +main"}}))))
    checks.append(("🔴 account safety: a LinkedIn fetch is denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "curl -s https://www." + "linked" + "in.com/in/x"}}))))
    checks.append(("🔴 account safety: a LinkedIn WebFetch is denied", bool(pre_tool({"tool_name": "web_fetch", "tool_input": {"url": "https://www." + "linked" + "in.com/jobs"}}))))
    checks.append(("account safety: an ATS fetch is allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "curl -s https://api.ashbyhq.com/posting-api/job-board/acme"}}) is None))
    checks.append(("a normal push is still allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}) is None))
    checks.append(("secret-file reads are denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "sed -n 1,20p .env.local"}}))))
    # SAFE_SECRET_METADATA is ^-anchored, so a safe leading verb used to whitelist the WHOLE
    # compound command and leak the secret in a later segment.
    checks.append(("🔴 a secret read behind a safe prefix is denied (git status && cat .env)", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "git status && cat .env"}}))))
    checks.append(("🔴 metadata-then-read compound is denied (wc -c .env && cat .env)", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "wc -c .env && cat .env"}}))))
    # Three more bypasses of the two guards above, all closed the same pass.
    checks.append(("🔴 secret read via command substitution is denied (wc -c $(cat .env))", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "wc -c $(cat .env)"}}))))
    checks.append(("🔴 secret read via backtick substitution is denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "wc -c `cat .env`"}}))))
    checks.append(("🔴 UPPER-case secret spelling is denied (cat .ENV on a case-insensitive filesystem)", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "cat .ENV"}}))))
    checks.append(("🔴 UPPER-case .mcp.json write is denied (echo x > .MCP.JSON)", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "echo x > .MCP.JSON"}}))))
    checks.append(("🔴 quoted +refspec force-push is denied (git push origin \"+main\")", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": 'git push origin "+main"'}}))))
    checks.append(("🔴 leading-whitespace +refspec force-push is denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "   git push origin +main"}}))))
    checks.append(("🔴 env-prefixed +refspec force-push is denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "GIT_SSH_COMMAND='ssh -i k' git push origin +main"}}))))
    checks.append(("safe commands remain allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "git status --short"}}) is None))
    checks.append(("a real metadata-only secret check is still allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "wc -c .env"}}) is None))
    checks.append(("a metadata check with an unrelated substitution is still allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "wc -c $(ls) .env"}}) is None))
    # The shipped .mcp.json: doctor.py's own fix command used to be denied.
    def _allowed(cmd):
        return pre_tool({"tool_name": "Bash", "tool_input": {"command": cmd}}) is None
    checks.append(("doctor.py's fix `git checkout -- .mcp.json` is allowed", _allowed("git checkout -- .mcp.json")))
    checks.append(("restoring the shipped .mcp.json with git restore is allowed", _allowed("git restore .mcp.json")))
    checks.append(("reading the shipped .mcp.json (cat, git show, git diff) is allowed",
                   _allowed("cat .mcp.json") and _allowed("git show HEAD:.mcp.json") and _allowed("git diff -- .mcp.json")))
    checks.append(("🔴 writing .mcp.json is still denied (redirect, sed -i, rm)",
                   not any(_allowed(c) for c in ("echo x > .mcp.json", "sed -i '' s/a/b/ .mcp.json", "rm .mcp.json"))))
    checks.append(("🔴 .env stays denied even beside .mcp.json (cat .mcp.json .env, git show HEAD:.env)",
                   not _allowed("cat .mcp.json .env") and not _allowed("git show HEAD:.env")
                   and not _allowed("git checkout -- .env")))
    checks.append(("🔴 a patch to .mcp.json is still denied",
                   bool(pre_tool({"tool_name": "apply_patch", "tool_input": {"command": "*** Update File: .mcp.json"}}))))
    for label, ok in checks:
        print(f"  {'✓' if ok else '✗'} {label}")
    passed = all(ok for _, ok in checks)
    print(f"SELFTEST {'OK' if passed else 'FAILED'}: {sum(ok for _, ok in checks)}/{len(checks)}")
    return 0 if passed else 1


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "--selftest":
        return selftest()
    data = read_payload()
    result = None
    if mode == "--timestamp-inject":
        result = timestamp_inject(data)
    elif mode == "--timestamp-stop":
        result = timestamp_stop(data)
    elif mode == "--pre-tool":
        result = pre_tool(data)
    elif mode == "--post-tool":
        result = post_tool(data)
    elif mode == "--post-edit":
        result = post_edit(data)
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
