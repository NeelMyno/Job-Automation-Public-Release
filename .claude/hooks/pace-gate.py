#!/usr/bin/env python3
# pace-gate.py, stamped by the infinite-loop commands. PreToolUse gate on Bash:
# the turn-chain wake (any command containing NEXT_TURN) must be the pure 5-second
# chain-link. Blocks longer sleeps (the banned time-based hold) and bundled work.
# Fails OPEN on any internal error. Inert outside loops (keys on NEXT_TURN only).
#
# "NEXT_TURN" is a marker-string convention, not a builtin of this repo: nothing here
# ships a self-rescheduling loop command by default, so this gate simply never fires
# unless you build your own loop-style command whose wake-chain command contains that
# same marker. If your convention uses a different marker, update the check below to match.
import json, re, sys
try:
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "")
    if "NEXT_TURN" not in cmd:
        sys.exit(0)
    for n in re.findall(r"sleep\s+(\d+)", cmd):
        if n != "5":
            print("PACE GATE: the chain-link must be exactly 'sleep 5'; you armed sleep %s. A longer wake is a banned time-based hold: it lets both unsupervised long sleeps and disguised real work ride along in an autonomous loop's wake-chain. Re-arm with the canonical 3-line chain: stop-check + one progress line + sleep 5." % n, file=sys.stderr)
            sys.exit(2)
    for tok in ("git commit", "git add", "npm ", "yarn ", "pnpm ", "make ", "pytest", "tsc ", "cargo ", "go build", "go test"):
        if tok in cmd:
            print("PACE GATE: the chain task does NO work ('%s' found in it). Work belongs IN the turn; the chain task is only stop-check + one progress line + sleep 5. Run the work first, then arm the pure chain as the final action." % tok.strip(), file=sys.stderr)
            sys.exit(2)
    sys.exit(0)
except SystemExit:
    raise
except Exception:
    sys.exit(0)
