# Known defects

Known defects found mid-wave (a broken script, a gate bug, a stale record), one row per item, so the
wave keeps moving and nothing is lost. `scripts/hooks.py` lists any OPEN row older than 7 days at
session start. Owner is `agent` or `you`. Close a row by changing its Status to
`CLOSED YYYY-MM-DD: <what fixed it>`; never delete it. Row shape: `.claude/rules/records-format.md` §9.

| Opened | Owner | Item | Status |
|---|---|---|---|
