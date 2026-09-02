# Sent-ledger — every outreach message and application email that actually left (append-only)

**The rule (CLAUDE.md §13.6):** one row per message actually sent to a real person. Sessions
APPEND rows; never rewrite, never delete — a wrong row gets a correcting row, not an edit. Every
outreach handoff ends with ready-to-append rows for this file; the next session reconciles
handed-over vs ledger and any gap becomes one direct question to you. `copy-state-at-send` names
any known defect in the copy as it went out — this column is why the file exists.

Schema: `date · recipient · company · channel · message-ref · copy-state-at-send · sent-by`

| date | recipient | company | channel | message-ref | copy-state-at-send | sent-by |
|---|---|---|---|---|---|---|
