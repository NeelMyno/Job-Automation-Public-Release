# Known defects

Known defects found mid-wave (a broken script, a gate bug, a stale record), one row per item, so the
wave keeps moving and nothing is lost. `scripts/hooks.py` lists any OPEN row older than 7 days at
session start. Close a row by changing its Status to `CLOSED <date>: <what fixed it>`; never delete it.

| Opened | Owner | Item | Status |
|---|---|---|---|
