#!/usr/bin/env python3
"""commit_guard.py: the record gates run at commit time, and git commands that bypass them are refused.

WHY THIS EXISTS
The Stop gate (scripts/hooks.py --stop) only sees files still uncommitted when a turn ends, so a chat
that writes a record and commits it in the same turn never meets it. A git pre-commit hook is the one
door every commit passes, whoever makes it: a chat, Codex or you in a terminal. The agent-side check
refuses the few git commands that skip that door or can strand uncommitted work.

MODES
    commit_guard.py --pre-commit   git pre-commit hook: runs the record gates on the staged record files
    commit_guard.py --pre-tool     Claude Code PreToolUse hook (JSON on stdin): exit 2 refuses a dangerous git command
    commit_guard.py --install      sets the repo-local git hook config (safe to repeat; SessionStart runs it)
    commit_guard.py --selftest     proves both guards work, on synthetic data in a temp folder

FAILS OPEN. A missing script, a gate that crashes, no git, or a git too old for config-based hooks
never stops a commit or a session. Only a real finding in a file you staged refuses a commit, and the
refusal says what to fix. Fix the record, never this file.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __name__ == "__main__" and "--selftest" in sys.argv:
    import voice_check
    voice_check.selftest_in_sandbox(__file__)

REPO = Path(__file__).resolve().parents[1]
HOOK_NAME = "job-commit-guard"
GIT = "git"

# git runs a hook from the top of the working tree. Written so a checkout without this script, or a
# machine without python3, skips the hook instead of failing every commit.
HOOK_CMD = ('if [ -f scripts/commit_guard.py ] && command -v python3 >/dev/null 2>&1; '
            'then python3 scripts/commit_guard.py --pre-commit; fi')

TRACKER = "pipeline/tracker.html"
TRUTHY = {"", "true", "1", "yes", "on"}
AUTOSTASH_KEYS = {"rebase.autostash", "pull.autostash", "merge.autostash"}
HOOK_KEY_PREFIX = f"hook.{HOOK_NAME}"

WHY_AUTOSTASH = ("--autostash is refused here. It stashes every uncommitted change in this folder, including work "
                 "from another open chat, and a failed re-apply can leave the repo stuck mid-rebase. Commit your own "
                 "files, then run `git pull --rebase`. If someone else's uncommitted files block that, run "
                 "`git pull --no-rebase`.")
WHY_AUTOSTASH_ON = ("Turning autostash on is refused here, for the same reason as --autostash: it can sweep up work "
                    "from another open chat. Commit your own files first, then pull.")
WHY_NO_VERIFY = ("Skipping the commit hook (--no-verify or -n) is refused here, because that hook checks your records. "
                 "Run the commit without that flag. If it is refused, the message says which row to fix.")
WHY_HOOK_OFF = ("Removing or redirecting the commit check is refused here (scripts/commit_guard.py). If a commit is "
                "refused, fix the row the message names and commit again.")

# Wrappers that may sit in front of the real command word.
_PREFIX_WORDS = {"sudo", "env", "command", "exec", "time", "nohup", "nice"}
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
_CONFIG_READ_FLAGS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l"}
_CONFIG_UNSET_FLAGS = {"--unset", "--unset-all", "--remove-section", "--rename-section"}
_CONFIG_WITH_VALUE = {"--file", "-f", "--blob", "--type", "--default", "--comment", "--value"}
_CONFIG_VERBS = {"get", "list", "set", "unset", "rename-section", "remove-section", "edit"}
_COMMIT_VALUE_FLAGS = set("mFCct")      # a short flag that takes the next token, or the rest of its own
_COMMIT_ATTACHED_ONLY = set("uS")       # a short flag whose optional value can only be attached


def _strip_text(command: str) -> str:
    """Text is not a command: drop here-doc bodies and quoted strings holding a space (commit messages,
    echoed notes), so writing ABOUT these flags is allowed. A quoted single token ("--flag") stays."""
    cmd = re.sub(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", " ", command, flags=re.S | re.M)
    cmd = re.sub(r"'[^'\n]*\s[^'\n]*'|\"[^\"\n]*\s[^\"\n]*\"", " ", cmd)
    cmd = cmd.replace("\\\n", " ")
    return cmd.replace('"', " ").replace("'", " ")


def _git_calls(command: str) -> list[tuple[list[str], list[str]]]:
    """Each git call in a shell command, as (the -c config values, the subcommand and its arguments)."""
    calls = []
    for seg in re.split(r"[;&|\n()`]", _strip_text(command)):
        toks = seg.split()
        i = 0
        while i < len(toks) and (toks[i] in _PREFIX_WORDS or _ENV_ASSIGN.match(toks[i])):
            i += 1
        if i >= len(toks) or not (toks[i] == "git" or toks[i].endswith("/git")):
            continue
        i += 1
        configs: list[str] = []
        while i < len(toks) and toks[i].startswith("-"):
            tok = toks[i]
            if tok in _GLOBAL_WITH_VALUE:
                if tok == "-c" and i + 1 < len(toks):
                    configs.append(toks[i + 1])
                i += 2
            else:
                i += 1
        calls.append((configs, toks[i:]))
    return calls


def _commit_skips_hook(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        tok = args[i]
        i += 1
        if tok == "--":
            return False
        if tok.startswith("--"):
            if len(tok) >= 6 and "--no-verify".startswith(tok):
                return True
            continue
        if not tok.startswith("-") or tok == "-":
            continue
        letters = tok[1:]
        for pos, ch in enumerate(letters):
            if ch == "n":
                return True
            if ch in _COMMIT_ATTACHED_ONLY:
                break
            if ch in _COMMIT_VALUE_FLAGS:
                if pos == len(letters) - 1:
                    i += 1              # its value is the next token, whatever that looks like
                break
    return False


def _config_danger(args: list[str]) -> str | None:
    flags = {a for a in args if a.startswith("-")}
    positional: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        i += 1
        if tok in _CONFIG_WITH_VALUE:
            i += 1
        elif not tok.startswith("-"):
            positional.append(tok)
    verb = positional.pop(0) if positional and positional[0] in _CONFIG_VERBS else ""
    if flags & _CONFIG_READ_FLAGS or verb in {"get", "list"} or not positional:
        return None
    key = positional[0].lower()
    value = positional[1].lower() if len(positional) > 1 else None
    unsetting = bool(flags & _CONFIG_UNSET_FLAGS) or verb in {"unset", "remove-section", "rename-section"}
    if key.startswith(HOOK_KEY_PREFIX) and (unsetting or value is not None):
        return WHY_HOOK_OFF
    if unsetting:
        return None
    if key == "core.hookspath" and value is not None:
        return WHY_HOOK_OFF
    if key in AUTOSTASH_KEYS and value is not None and value in TRUTHY:
        return WHY_AUTOSTASH_ON
    return None


def danger(command: str) -> str | None:
    """The reason a shell command is refused, or None."""
    for configs, argv in _git_calls(command):
        for item in configs:
            key, _, value = item.partition("=")
            key = key.lower()
            if key == "core.hookspath" or key.startswith(HOOK_KEY_PREFIX):
                return WHY_HOOK_OFF
            if key in AUTOSTASH_KEYS and value.lower() in TRUTHY:
                return WHY_AUTOSTASH_ON
        if not argv:
            continue
        sub, args = argv[0], argv[1:]
        if sub in {"pull", "rebase", "merge"}:
            if any(len(a) >= 7 and "--autostash".startswith(a) for a in args):
                return WHY_AUTOSTASH
        elif sub == "commit":
            if _commit_skips_hook(args):
                return WHY_NO_VERIFY
        elif sub == "config":
            why = _config_danger(args)
            if why:
                return why
    return None


def run(args: list[str], repo: Path) -> tuple[int, str]:
    """Run a gate script from the repo root. -1 means it could not run at all."""
    try:
        p = subprocess.run([sys.executable, *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return -1, f"{type(e).__name__}: {e}"
    return p.returncode, (p.stdout + p.stderr).strip()


def staged(repo: Path) -> list[str]:
    try:
        p = subprocess.run([GIT, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=repo,
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [x for x in p.stdout.split("\0") if x] if p.returncode == 0 else []


def _record_patterns():
    """hooks.py owns which files are records and which dossiers are scaffolding."""
    try:
        import hooks
        return hooks.RECORD_FILE, hooks._SCAFFOLD
    except Exception:
        return None, None


def gates_for(paths: list[str]) -> list[list[str]]:
    """The gates a set of staged paths needs. Scoped to those paths, so an old row in a file you did
    not stage never stops today's commit."""
    records, scaffold = _record_patterns()
    if records is None:
        return []
    real = [p for p in paths if not scaffold.match(p)]
    gates = []
    if TRACKER in real:
        gates.append(["scripts/tracker_check.py"])
    recs = [p for p in real if records.search(p)]
    if recs:
        gates.append(["scripts/records_check.py", "--files", *recs])
    return gates


def _is_finding(gate: str, rc: int, out: str) -> bool:
    """Only a real finding refuses a commit. tracker_check says BROKEN (exit 2); records_check exits 1.
    A 'not checked' exit, a crash or a timeout is reported and lets the commit through."""
    if gate.endswith("tracker_check.py"):
        return rc != 0 and "BROKEN" in out
    return rc == 1


def _what_to_fix(gate: list[str], out: str) -> str:
    if gate[0].endswith("tracker_check.py"):
        return ("pipeline/tracker.html has a script error, so the tracker page would open blank. Usually it is a "
                "stray double quote inside a row; write it as \\\" instead.\n"
                f"{out[-800:]}\n"
                "Check it again with: python3 scripts/tracker_check.py")
    files = " ".join(gate[2:])
    return ("A record row is not in the shape the job-search scripts read, so they would miss it. Each row below "
            "names the problem. The shapes are in .claude/rules/records-format.md.\n"
            f"{out[-1500:]}\n"
            f"Check it again with: python3 scripts/records_check.py --files {files}")


def pre_commit(repo: Path | None = None) -> int:
    repo = repo or REPO
    problems, notes = [], []
    for gate in gates_for(staged(repo)):
        if not (repo / gate[0]).is_file():
            continue
        rc, out = run(gate, repo)
        if _is_finding(gate[0], rc, out):
            problems.append(_what_to_fix(gate, out))
        elif rc not in (0, 3):
            notes.append(f"commit_guard: {gate[0]} could not run (exit {rc}), so it was skipped for this commit.")
    for note in notes:
        print(note, file=sys.stderr)
    if problems:
        print("Commit stopped. Nothing was committed and your files are unchanged.\n\nWhat to fix:\n\n"
              + "\n\n".join(problems)
              + "\n\nFix that, run `git add` on the file again, then commit again.", file=sys.stderr)
        return 1
    return 0


def pre_tool() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if data.get("tool_name") != "Bash":
            return 0
        cmd = (data.get("tool_input") or {}).get("command") or ""
        why = danger(cmd) if isinstance(cmd, str) else None
    except Exception:
        return 0
    if why:
        print(f"COMMIT GUARD: {why}", file=sys.stderr)
        return 2
    return 0


def _git_out(repo: Path, *args) -> tuple[int, str]:
    p = subprocess.run([GIT, *args], cwd=repo, capture_output=True, text=True, timeout=20)
    return p.returncode, p.stdout.strip()


def install(repo: Path | None = None) -> int:
    """Set the repo-local hook config. Always exits 0: a copy with no git, a downloaded ZIP or an old git
    simply goes without the commit-time check, and the same checks still run when a chat ends."""
    repo = repo or REPO
    try:
        rc, _ = _git_out(repo, "rev-parse", "--is-inside-work-tree")
        if rc != 0:
            print("commit_guard: this folder is not a git checkout, so there is no commit check to set up.")
            return 0
        changed = False
        for key, val in ((f"{HOOK_KEY_PREFIX}.event", "pre-commit"), (f"{HOOK_KEY_PREFIX}.command", HOOK_CMD),
                         ("rebase.autoStash", "false"), ("pull.autostash", "false")):
            if _git_out(repo, "config", "--local", "--get", key)[1] != val:
                if _git_out(repo, "config", "--local", key, val)[0] != 0:
                    print(f"commit_guard: could not write the git setting {key}; skipping the commit check.")
                    return 0
                changed = True
        rc, listed = _git_out(repo, "hook", "list", "pre-commit")
        if rc != 0 or HOOK_NAME not in listed:
            print("commit_guard: this version of git cannot run config-based hooks, so records are not checked at "
                  "commit time. Nothing is broken: the same checks still run when a chat ends. Updating git turns "
                  "this on.")
            return 0
    except (OSError, subprocess.SubprocessError) as e:
        print(f"commit_guard: git is not usable here ({type(e).__name__}); skipping the commit check.")
        return 0
    print(f"commit_guard: {'installed' if changed else 'already installed'} (pre-commit hook '{HOOK_NAME}', autostash off)")
    return 0


def _selftest_env() -> dict:
    """A temp repo must ignore the caller's git state and global settings (this can run inside a hook)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def _selftest_end_to_end(check) -> None:
    if not shutil.which(GIT):
        print("  (git not on PATH: end-to-end commit checks not exercised)")
        return
    env = _selftest_env()
    fake_gate = ("import sys\nprint('  [tracker] row 3: status cell later is not a status')\nsys.exit(%d)\n")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "pipeline").mkdir()
        shutil.copy(Path(__file__).resolve(), repo / "scripts" / "commit_guard.py")
        shutil.copy(Path(__file__).resolve().parent / "hooks.py", repo / "scripts" / "hooks.py")
        gate = repo / "scripts" / "records_check.py"
        (repo / "scripts" / "tracker_check.py").write_text("print('tracker JS valid')\n", encoding="utf-8")
        ledger = repo / "pipeline" / "sent-ledger.md"

        def git(*a):
            return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, env=env, timeout=30)

        def guard(flag):
            return subprocess.run([sys.executable, "scripts/commit_guard.py", flag], cwd=repo, capture_output=True,
                                  text=True, env=env, timeout=60)

        git("init", "-q", ".")
        git("config", "--local", "user.name", "Sam Lee")
        git("config", "--local", "user.email", "sam@example.com")
        first, second = guard("--install"), guard("--install")
        check("--install exits 0", first.returncode == 0 and second.returncode == 0)
        if git("hook", "list", "pre-commit").stdout.find(HOOK_NAME) < 0:
            print("  (this git cannot run config-based hooks: end-to-end commit checks not exercised)")
            check("--install says plainly that this git cannot run the hook", "cannot run config-based hooks" in first.stdout)
            return
        check("--install is idempotent", "already installed" in second.stdout)
        check("--install turns autostash off, in this repo only",
              git("config", "--local", "--get", "rebase.autoStash").stdout.strip() == "false")

        def commit(text):
            ledger.write_text(text, encoding="utf-8")
            git("add", "pipeline/sent-ledger.md")
            return git("commit", "-q", "-m", "update ledger")

        gate.write_text(fake_gate % 1, encoding="utf-8")
        refused = commit("one\n")
        check("a staged record with a finding refuses the commit", refused.returncode != 0)
        check("the refusal says what to fix and names the row",
              "What to fix" in refused.stderr and "row 3" in refused.stderr and "Nothing was committed" in refused.stderr)
        check("the refusal never suggests a bypass", "no-verify" not in refused.stderr)
        check("a refused commit makes no commit", git("rev-parse", "-q", "--verify", "HEAD").returncode != 0)
        gate.write_text(fake_gate % 0, encoding="utf-8")
        check("a clean record commits", commit("two\n").returncode == 0)
        gate.write_text(fake_gate % 1, encoding="utf-8")
        (repo / "notes.txt").write_text("code\n", encoding="utf-8")
        git("add", "notes.txt")
        check("a commit with no record file runs no gate", git("commit", "-q", "-m", "add notes").returncode == 0)
        sub = repo / "pipeline"
        p = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "from a subfolder"], cwd=sub,
                           capture_output=True, text=True, env=env, timeout=30)
        check("a commit from a subfolder still works", p.returncode == 0)
        gate.write_text(fake_gate % 3, encoding="utf-8")
        check("a gate that says not checked (exit 3) never refuses", commit("three\n").returncode == 0)
        gate.write_text(fake_gate % 7, encoding="utf-8")
        crashed = commit("four\n")
        check("a gate that crashes never refuses, and says it was skipped",
              crashed.returncode == 0 and "could not run" in crashed.stderr)
        gate.unlink()
        check("a missing gate script never refuses", commit("five\n").returncode == 0)
        (repo / "scripts" / "commit_guard.py").unlink()
        check("a checkout without this script skips the hook", commit("six\n").returncode == 0)


def selftest() -> int:
    global GIT
    import contextlib
    import io
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok' if cond else 'FAIL'}  {name}")

    print("commit_guard.py selftest")
    flag_a, flag_n = "--auto" + "stash", "--no-" + "verify"
    for label, cmd in (
        ("pull with autostash", "git pull --rebase --autostash origin main"),
        ("quoted and chained", 'cd x && git  pull  "--autostash" --rebase origin main'),
        ("an abbreviated flag", "git pull --autost origin main"),
        ("rebase with autostash", "git rebase --autostash origin/main"),
        ("-c rebase.autoStash=true", "git -c rebase.autoStash=true rebase origin/main"),
        ("git config rebase.autostash true", "git config rebase.autostash true"),
        ("git config --global pull.autostash yes", "git config --global pull.autostash yes"),
        ("the newer git config set form", "git config set rebase.autoStash true"),
        ("commit --no-verify", "git commit --no-verify -m x"),
        ("commit --no-verify after -C", "git -C some/path commit --no-verify -m x"),
        ("commit -n in a cluster", "git commit -qn -m x"),
        ("commit -an", "git commit -an"),
        ("unsetting the guard", "git config --unset-all hook.job-commit-guard.command"),
        ("removing the guard section", "git config --remove-section hook.job-commit-guard"),
        ("redirecting hooks", "git config core.hooksPath /tmp/none"),
        ("redirecting hooks for one commit", "git -c core.hooksPath=/tmp/none commit -m x"),
        ("after an env assignment", "FOO=1 git pull --autostash origin main"),
        ("the flag after a here-doc", f"cat > a <<EOF\nx\nEOF\ngit pull {flag_a} origin main"),
        ("inside a command substitution", "echo $(git commit --no-verify -m x)"),
    ):
        check(f"refuses: {label}", danger(cmd))
    for label, cmd in (
        ("git commit -m", 'git commit -m "Add shift notes"'),
        ("commit -am", 'git commit -am "update"'),
        ("commit -q -F file", "git commit -q -F msg.txt"),
        ("an attached message holding the letter n", "git commit -mInitial"),
        ("a message that is the text -n", "git commit -m -n"),
        ("commit --amend --no-edit", "git commit --amend --no-edit"),
        ("commit --dry-run", "git commit --dry-run"),
        ("commit -S with an attached key", "git commit -Sabcn -m x"),
        ("commit with a path after --", "git commit -m x -- -n.txt"),
        ("the usual here-doc commit", f"git commit -m \"$(cat <<'EOF'\nban {flag_n} and {flag_a} -n\nEOF\n)\""),
        ("a message that mentions the flag", f'git commit -q -m "ban git commit {flag_n}"'),
        ("a here-doc that mentions both flags", f"cat > notes.md <<'EOF'\nnever git pull {flag_a}; never git commit {flag_n}\nEOF\ngit status"),
        ("git log naming commit with -n", "git log --grep commit -n 5"),
        ("git show -n", "git show -n 1 HEAD"),
        ("a folder with commit in its name", "git -C commit-notes status -n"),
        ("pull --rebase", "git pull --rebase origin main"),
        ("pull --no-rebase", "git pull --no-rebase origin main"),
        ("pull --no-autostash", "git pull --no-autostash origin main"),
        ("stash list", "git stash list"),
        ("reading the setting", "git config --get core.hooksPath"),
        ("reading it the short way", "git config core.hooksPath"),
        ("turning autostash off", "git config rebase.autostash false"),
        ("git config --list", "git config --list"),
        ("echoing about git", "echo git pull --autostash"),
        ("an ordinary program", "python3 scripts/records_check.py -n"),
    ):
        check(f"allows: {label}", not danger(cmd))

    def tool(payload):
        saved, sys.stdin = sys.stdin, io.StringIO(payload)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                return pre_tool(), err.getvalue()
        finally:
            sys.stdin = saved

    rc, err = tool(json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}}))
    check("--pre-tool exits 2 on a dangerous command and says why", rc == 2 and "COMMIT GUARD" in err)
    check("--pre-tool exits 0 on a normal commit",
          tool(json.dumps({"tool_name": "Bash", "tool_input": {"command": 'git commit -m "Add notes"'}}))[0] == 0)
    check("--pre-tool ignores other tools",
          tool(json.dumps({"tool_name": "Write", "tool_input": {"command": "git commit -n"}}))[0] == 0)
    check("--pre-tool fails open on bad JSON", tool("not json")[0] == 0)

    g = gates_for([TRACKER])
    check("the tracker staged runs tracker_check and records_check",
          ["scripts/tracker_check.py"] in g and ["scripts/records_check.py", "--files", TRACKER] in g)
    check("the records gate reads only the staged file",
          gates_for(["pipeline/sent-ledger.md"]) == [["scripts/records_check.py", "--files", "pipeline/sent-ledger.md"]])
    check("a dossier's application.md is a record",
          gates_for(["applications/northwind-nurse/application.md"])
          == [["scripts/records_check.py", "--files", "applications/northwind-nurse/application.md"]])
    check("a code-only commit runs no gate", gates_for(["scripts/config.py", "README.md"]) == [])
    check("scaffolding dossiers run no gate", gates_for(["applications/TEMPLATE-company-role/application.md"]) == [])
    check("tracker_check's BROKEN result is a finding", _is_finding("scripts/tracker_check.py", 2, "tracker JS BROKEN"))
    check("no tracker file is not a finding", not _is_finding("scripts/tracker_check.py", 2, "no pipeline/tracker.html"))

    with tempfile.TemporaryDirectory() as td:
        plain = Path(td)
        buf = io.StringIO()
        saved_cfg = {k: os.environ.pop(k, None) for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
        try:
            with contextlib.redirect_stdout(buf):
                rc = install(plain)
        finally:
            for k, v in saved_cfg.items():
                if v is not None:
                    os.environ[k] = v
        if shutil.which(GIT):
            check("--install in a folder that is not a git checkout exits 0 and says so",
                  rc == 0 and "not a git checkout" in buf.getvalue())
        buf = io.StringIO()
        saved_git, GIT = GIT, "no-such-git-binary"
        try:
            with contextlib.redirect_stdout(buf):
                rc = install(plain)
            check("--install with no git on the machine exits 0", rc == 0 and "not usable" in buf.getvalue())
            check("staged() with no git finds nothing, so a commit is never refused", staged(plain) == [])
        finally:
            GIT = saved_git

    check("the hook command skips when python3 is missing", "command -v python3" in HOOK_CMD and "|| " not in HOOK_CMD)
    _selftest_end_to_end(check)
    print("commit_guard selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--selftest"
    return {"--pre-commit": pre_commit, "--pre-tool": pre_tool, "--install": install,
            "--selftest": selftest}.get(mode, selftest)()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
