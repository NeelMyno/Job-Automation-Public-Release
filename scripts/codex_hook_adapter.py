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
from zoneinfo import ZoneInfo

try:
    from config import RESPONSE_TIMESTAMP_TZ
except ImportError:
    RESPONSE_TIMESTAMP_TZ = None


REPO = Path(__file__).resolve().parents[1]
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.M)
FORCE_PUSH = re.compile(
    r"(?:^|[;&|]\s*)git\s+push\b[^\n;&|]*(?:--force(?:-with-lease)?\b|-f\b)", re.I
)
SENSITIVE = re.compile(
    r"(?:^|[\s/\"'=])(?:\.mcp\.json|\.env(?:\.[^\s/\"']+)?)"
)
SAFE_SECRET_METADATA = re.compile(
    r"^\s*(?:git\s+(?:status|check-ignore)|grep\s+-l|wc\s+-c|shasum\b)", re.I
)


def read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def now_stamp() -> str:
    tz = ZoneInfo(RESPONSE_TIMESTAMP_TZ) if RESPONSE_TIMESTAMP_TZ else None
    return datetime.now(tz).strftime("%Y-%m-%d %I:%M %p %Z").lstrip("0")


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
    if not RESPONSE_TIMESTAMP_TZ:
        return None  # off by default; set config.RESPONSE_TIMESTAMP_TZ to enable
    stamp = now_stamp()
    save_expected_stamp(data, stamp)
    context = (
        f"CURRENT TIME, computed by the system clock just now: {stamp}\n\n"
        "MANDATORY: the FIRST line of every user-facing reply in this turn must be exactly:\n\n"
        f"📅 Response at: {stamp}\n\n"
        "Every earlier timestamp in this conversation is STALE. Do not copy one forward, infer "
        "the time, or substitute another timezone."
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
    if not RESPONSE_TIMESTAMP_TZ:
        return None  # off by default; set config.RESPONSE_TIMESTAMP_TZ to enable
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
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str):
        return None
    if tool_name == "Bash" and FORCE_PUSH.search(command):
        return deny("Force-push is forbidden in this repo. Pull with rebase and push normally.")
    if tool_name in {"Bash", "apply_patch"} and SENSITIVE.search(command):
        if tool_name == "apply_patch" or not SAFE_SECRET_METADATA.search(command):
            return deny(
                "Do not read or modify .mcp.json or .env files. Check only presence or metadata "
                "with git status, git check-ignore, grep -l, wc -c, or shasum."
            )
    return None


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
    if RESPONSE_TIMESTAMP_TZ:
        injected = timestamp_inject(base) or {}
        expected = load_expected_stamp(base)
        checks.append(("timestamp injection has Codex envelope", injected.get("hookSpecificOutput", {}).get("hookEventName") == "UserPromptSubmit"))
        checks.append(("timestamp injection leaves a per-turn receipt", bool(expected)))
        compliant = dict(base, last_assistant_message=f"📅 Response at: {expected}\n\nHello")
        checks.append(("timestamp Stop allows the exact supplied line", timestamp_stop(compliant) is None))
        missing = dict(base, last_assistant_message="Hello")
        checks.append(("timestamp Stop blocks a missing line", (timestamp_stop(missing) or {}).get("decision") == "block"))
    else:
        checks.append(("timestamp injection no-ops when RESPONSE_TIMESTAMP_TZ is unset", timestamp_inject(base) is None))
        idle = dict(base, last_assistant_message="Hello")
        checks.append(("timestamp Stop no-ops when RESPONSE_TIMESTAMP_TZ is unset", timestamp_stop(idle) is None))
    patch = "*** Begin Patch\n*** Update File: README.md\n*** Add File: .codex/x.json\n*** End Patch"
    paths = patch_paths({"cwd": str(REPO), "tool_input": {"command": patch}})
    checks.append(("multi-file apply_patch paths are extracted", {p.name for p in paths} == {"README.md", "x.json"}))
    checks.append(("force-push is denied wherever the flag appears", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "git push origin main --force"}}))))
    checks.append(("secret-file reads are denied", bool(pre_tool({"tool_name": "Bash", "tool_input": {"command": "sed -n 1,20p .env.local"}}))))
    checks.append(("safe commands remain allowed", pre_tool({"tool_name": "Bash", "tool_input": {"command": "git status --short"}}) is None))
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
    elif mode == "--post-edit":
        result = post_edit(data)
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
