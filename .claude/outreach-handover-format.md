# Outreach handover format (LOCKED)

**This is the format every outreach handover follows, without exception.** If you want it changed,
update THIS file and follow the updated version from there on. Don't let the shape drift session
to session.

## Why this format

Most chat/DM tools collapse indented or blockquoted paragraphs on paste. Putting each message in
its own fenced code block preserves the blank-line paragraph breaks, so you copy one block and
paste a clean, well-paragraphed message. At any real volume that saves you from reformatting every
message by hand.

## Delivery

- Write the handover to the **session scratchpad** as an `.md` file (e.g.
  `batchN-linkedin-outreach.md`), then send it as a file the operator can open directly, formatted
  with copyable code blocks.
- It is a **disposable copy-paste sheet**, regenerated per batch, NOT a maintained record. The
  source of truth is each dossier's `referrals.md`; copy is read **verbatim** off it (CLAUDE.md
  §13.6). Never maintain a queue / send-sheet file (the SSOT law in `.claude/commands/outreach.md`).

## Structure (mirror this exactly)

**At the top of the file, a short "how to use" block:**
- Note = free connection request, send it first. DM = after they accept (or as a normal message if
  already connected; the operator reports the channel, the agent logs it).
- InMail default (NO unless a block says YES) + the current InMail balance, if you track one.
- Any link caveat (e.g. a domain redirect) if relevant.

**Then, grouped by company, one section per company:**

    # <Company>: <Role>
    **<Req / Job ID>** · <basket + pacing: big = all same-day; small = 3/company/day> · InMail: <default>

**Then, per person under that company:**

    ## N. <Full Name>  *(optional tag: send today / send tomorrow, for paced baskets)*
    **Profile:** <linkedin url>
    **Why:** <one true, grounded line: the specific reason this person>
    (InMail-YES people only: · 🔴 **InMail: YES**, <one-line reason>)

    **Connection note:**
    ```
    <the connection note, under 300 chars, one paragraph>
    ```

    **DM (after accept):**
    ```
    Hi <Name>,

    <paragraph 1: an observation about THEIR own work, first>

    <paragraph 2: your matching real work; the give = your portfolio>

    <the ask, always present, reshaped (never dropped) for a decision-node>

    <Your name>
    ```

Separate each person with a `---`, and each company block with `---` then `---`.

**Bottom of the file:** a one-line "as you send, tell me and I log each" note.

## The rules that still bind (this file governs LAYOUT only)

Copy is verbatim from `referrals.md`; the message doctrine (CLAUDE.md §13.6), the mandatory
structure (recipient's-own-work observation first, the give = portfolio, the explicit ask), the
paragraphing, the req-ID rule, the card rule (§13.2), and the gates (`outreach_format.py` +
`verify_claims.py`) all still apply.
