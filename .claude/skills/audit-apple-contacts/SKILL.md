---
name: audit-apple-contacts
description: Audit the Apple Contacts address book and merge a Google Contacts export into it — cross-account duplicates, phone numbers in a dozen formats, company tags stuck inside names, cards with no way to reach anyone. Proposes every change as a queue the owner approves one contact at a time, and writes nothing until they do.
model-invocable: false
allowed-tools:
  - Bash
  - Read
  - Write
---

# Goal

Leave one address book — the Apple one — holding every contact, with each piece
of information in the field it belongs to.

The work is not the editing. It is **deciding**, and only the owner can decide:
whether two cards are one person, what a surname is, whether a card with no
phone and no email is worth keeping. This skill's job is to prepare those
decisions well enough that answering them is fast, and then to apply exactly
what was answered.

This is the address-book counterpart to `audit-mac-tools`: same shape, same
public-repo constraint. **The output contains real contact data and never goes
in the repository** — `reports/` is git-ignored, and `--out` should point
outside the working tree entirely.

# Phases

Run them in this order. The order is the safety property, not a preference.

| phase | what | reversible |
|---|---|---|
| 0 | the owner exports a **Contacts Archive** (`.abbu`) | — |
| 1 | read both books, build the action queue | nothing written |
| 2 | the owner approves each action | nothing written |
| 3 | apply everything that edits existing cards | yes, from the vCard dump |
| 4 | apply the imports | yes, from the journal in `applied.json` |
| 5 | verify, then the owner deletes the source book by hand | — |

**Everything before phase 4 touches cards that already exist. Phase 4 creates
new ones that propagate to every synced device within seconds — reversible,
but only because every created id is journalled as it goes.**

## Phase 0 — being able to go back

Three things can undo a mistake here, and they are good at different mistakes.
Reaching for the wrong one is how a small error becomes a large one.

**The journal is the undo for imports.** `apply.py` records the id of every
card it creates in `applied.json`. Reversing a batch is then deleting exactly
those ids — surgical, and it leaves everything else alone. Restoring an
archive to undo one batch reverts every change made since, which is almost
never what was wanted.

**The vCard export is a complete snapshot**, and worth keeping for that: every
field of every card, diffable, and the evidence for what a card held before.
It is a poor *restore*, because importing **adds** rather than replaces — going
back through it means deleting the book and re-importing, which regenerates
every id and breaks whatever referred to them.

**The Contacts Archive (`.abbu`) is the only in-place restore.** Contacts →
File → Export → Contacts Archive. It earns its two clicks against the failure
the other two cannot cover: something going wrong with the cards that already
existed. Recommended before a large edit; not a gate on imports, which the
journal already covers.

## Phase 1 — read

```bash
python3 scripts/audit.py \
  --primary   icloud=/path/icloud.vcf \
  --secondary gmail=/path/contacts.vcf \
  --config    /path/config.json \
  --out       ~/contacts-audit
```

Get the primary book out of Contacts with one bulk call, not one per person:

```bash
osascript -e 'with timeout of 900 seconds
tell application "Contacts" to return vcard of every person
end timeout' > icloud.vcf
```

Then **repair it** — see the AppleScript traps below — and confirm the card
count matches what the app reports before trusting anything derived from it.

**The Mac's copy can be behind iCloud.** Contacts on a Mac shows both the
iCloud account and a local *On My Mac* account in one list, and a card in the
local one exists on that machine and nowhere else. Worse, the Mac may simply
not have pulled everything: here it held 113 of the 115 cards the phone
listed. Compare the count against a device before trusting the export, and if
they differ, export from `icloud.com` instead — that is the authority.

A card with no `UID` and no `CATEGORIES:card` came from the local account;
`audit.py` flags those as `local_only`, which is what explains a contact the
phone cannot find.

Get the secondary book from `contacts.google.com` → Export → **vCard**. Prefer
exporting over configuring the Google account inside Contacts: it keeps the
source book strictly read-only, so every write this skill makes lands in one
place.

## Phase 2 — approve

```bash
python3 scripts/review.py --dir ~/contacts-audit --interactive   # alone
python3 scripts/review.py --dir ~/contacts-audit --list EMPTY    # relayed by an agent
python3 scripts/review.py --dir ~/contacts-audit --decide EMPTY-1a2b3c4d=yes
```

Both modes share one decisions file and can be mixed freely.

Do not decide anything on the owner's behalf. Facts they mention in passing — a
surname, who someone is — belong in the queue as a **proposal** carrying that
fact, not as a decision already taken.

# The traps

Every one of these cost a real failure. None is theoretical.

## Permissions

- macOS asks for **two separate grants**: Automation (drive the app) and
  Privacy → Contacts (read the data). The first does not imply the second.
- While a grant dialog waits for a click the script **hangs**, then fails with
  `-1712`. That is not a bug in the script. Detect it with
  `pgrep -x UserNotificationCenter`.
- The grant belongs to **the terminal app hosting the session**. Through tmux,
  attaching from a different app asks again.
- The app must already be running: `launch` inside the `tell` is not enough and
  returns `-600`. Use `open -a Contacts` first.

## AppleScript

- There is **no `account` class** (`-2741`). Accounts cannot be enumerated that
  way; identify them from the exports instead.
- **`id of person` is not the vCard `UID`.** Different namespaces. Applying
  changes keyed on the UID finds nothing. Build the mapping and *verify* it —
  bulk-fetch ids and names, then check every name against the parsed card.
- `vcard of every person` returns the list joined with `", "`, so every
  `BEGIN:VCARD` after the first sits mid-line and the file is not valid vCard.
  Repair with `s/\r\n, BEGIN:VCARD/\r\nBEGIN:VCARD/`.
- Wrap every call in `with timeout of N seconds`, and prefer one bulk fetch to
  N round trips.
- Nothing persists without `save`. A batch that fails halfway and then saves
  commits half the change, so make each chunk save-or-nothing.
- Address individual `phone` elements when rewriting a number. Rebuilding the
  list drops labels and reorders.

## Data

- **A shared landline is not a duplicate.** Four people in one house share one
  number; matching on it declares them one person. Require the name or the
  email to agree as well, and never drop someone from an import because a phone
  matched.
- Numbers carry **invisible bidi controls** (`U+202A`, `U+202C`) from iOS and
  Google. They look identical and are not.
- Verify a blanket country prefix before applying it. `blanket_prefix_safe`
  does this; it is cheap and it is the difference between fixing 78 numbers and
  breaking the foreign ones. **It is only valid for the files it was run on** —
  re-run after any new export.
- Flip `Surname, Given` **before** composing anything on top, or a kinship
  prefix produces «Prima Mancheño, Ire».
- Splitting a full name on the last space is wrong wherever two surnames are
  normal. Offer the buckets and let the owner choose; do not auto-propose a
  split that is wrong in the common case.

## The queue

- **Action ids must be stable** — hash the content, never a counter. A counter
  renumbers on regeneration and silently points existing decisions at other
  contacts.
- **Save after every decision**, bulk approval included.

## Environment

- Python's text mode **normalises `\r\n` to `\n`**: a parser splitting on
  `\r\n` reads nothing and raises nothing.
- zsh does **not** word-split an unquoted variable, so `for f in $files` runs
  once with everything glued. Wrong results, no error.

# Rules

- Never write to the address book before phase 3, and never import before the
  `.abbu` exists.
- Never write contact data into the repository. `--out` goes outside it.
- Never merge two cards on a phone match alone.
- Never present a proposal the owner has to correct in the common case — a
  review that is mostly wrong is a review that gets rubber-stamped.
- Report what was applied against what was approved, and name any difference.
