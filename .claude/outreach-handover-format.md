# Outreach handover format (LOCKED)

**This is the format every outreach handover follows, without exception.** If you want it changed,
update THIS file and follow the updated version from there on. Don't let the shape drift session
to session.

> **Two files, not one.** The send file carries connection notes ONLY, and only for people nobody has
> contacted yet. The DMs live in `pipeline/outreach-bundle-dms-on-accept.md` and are handed over when
> you report who accepted. A DM in the send file sends you to a profile whose request is still
> pending, with nothing to do there. Rule owner: `.claude/rules/application-protocol.md` §13.6.

## Why this format

Most chat/DM tools collapse indented or blockquoted paragraphs on paste. Putting each message in
its own fenced code block preserves the blank-line paragraph breaks, so you copy one block and
paste a clean, well-paragraphed message. At any real volume that saves you from reformatting every
message by hand.

## Delivery

- **Generate it: `python3 scripts/outreach_bundle.py`.** It derives the scope from the queue,
  re-gates every dossier that minute, leaves out anything that has not passed (and lists why), and
  writes TWO gitignored files: `pipeline/outreach-bundle-<date>.md` (connection notes only, nobody
  already contacted; a 1st-degree contact gets the DM as the one message to send) and
  `pipeline/outreach-bundle-dms-on-accept.md` (Part 1 = note already sent, waiting on accept; Part 2
  = note not sent yet). Its `render()` and `render_dms()` ARE this layout; change them together with
  this file.
- **When the operator reports acceptances**, hand over those people's DMs in chat, read verbatim off
  the DM file (or `referrals.md`), then log the sends. Never put a DM back into the send file. For a
  one-off of a few people, a scratchpad `.md` in the same structure is fine. Either way, give the
  operator the file's full path so it opens formatted with copyable code blocks.
- It is a **disposable copy-paste sheet**, regenerated per batch, NOT a maintained record. The
  source of truth is each dossier's `referrals.md`; copy is read **verbatim** off it (CLAUDE.md
  §13.6). Never maintain a queue / send-sheet file (the SSOT law in `.claude/commands/outreach.md`).

## Structure (mirror this exactly)

**At the top of the file, a short "how to use" block:**
- Note = free connection request. The DMs are NOT in this file: they are in the on-accept file,
  handed over when the operator reports who accepted (the operator reports the channel, the agent
  logs it).
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

    (the DM is NOT here: it goes to the on-accept file, under the same name, as:)
    **DM:**
    ```
    Hi <Name>,

    <paragraph 1: an observation about THEIR own work, first>

    <paragraph 2: your matching real work; the give = the page that shows your work, if you keep one>

    <the ask, always present, reshaped (never dropped) for a decision-node>

    <Your name>
    ```

Separate each person with a `---`, and each company block with `---` then `---`.

**Bottom of the file:** a one-line "as you send, tell me and I log each" note.

## The rules that still bind (this file governs LAYOUT only)

Copy is verbatim from `referrals.md`; the message doctrine (CLAUDE.md §13.6), the mandatory
structure (recipient's-own-work observation first, the give, the explicit ask), the
paragraphing, the req-ID rule, the card rule (§13.2), and the gates (`outreach_format.py` +
`verify_claims.py`) all still apply.
