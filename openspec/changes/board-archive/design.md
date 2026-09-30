# Design

## The archive key

Board entries carry no `id` (top-level fields: `type`, `title`, `content`,
`date`, `fixed`, `author`). The key is

    sha1(json([type, date, identity(entry)]))

where `identity` keeps only what cannot change after the fact:

| Type | Identity |
|---|---|
| `transfer`, `market`, `adminTransfer`, `clauseIncrement`, `bonus` | per content item: `type`, `player` (id), `amount`, `releaseClause`, `reason`, and the **ids** of `from` / `to` / `user` / `admin` — sorted |
| `roundFinished` | `round.id`, `scoreID` |
| `seasonStarted` | `season.id` |

Names and icons are excluded (a team renames itself; icons carry `?v=…`), and so
is `roundFinished.article`, whose comment count moves daily. A score correction
republishes a round with a new `scoreID` and date, so it keeps its own key; the
rebuild already counts a round once.

Measured on two reads three days apart: 244 money entries, the same 244 keys in
both, 0 collisions within either read.

## Where it lives

`core/sdk/biwenger.py` gains `board_entry_key(entry)` and `MONEY_ENTRY_TYPES`:
both the scraper (writes) and the api (reads) need them, and shared code is a
Bazel edge, never a path (LP-9).

Firestore `board_archive/{season}/entries/{key}`, one document per entry holding
the raw entry. A few hundred documents per season — inside the free tier.
Private: the public bucket is not an option for the league's money.

## Append-only, everywhere

- The archive is written with the new keys only; nothing is deleted or
  overwritten by a job.
- `clausulazos/{season}/transfers` is neither wiped nor rewritten: the scraper
  only inserts clausulazos it has not stored yet. A genuine upstream deletion
  is handled by hand (`scripts/scraper/surgery.py`).
- **Identity of a clausulazo is its date and price.** The doc id hashes the
  team and player *names*, which change: a team renaming itself would give
  every one of its clausulazos a new id, a duplicate, a double count in the
  justice table and a false "missing" warning. `rename_team.py` also fixes
  names in place under the old id. So a fetched clausulazo whose date and
  price are already stored counts as stored and is not written — which also
  keeps a manual fix from being reverted by the feed. Measured: date + price
  is unique across the 115 stored (25-26 and 26-27); the live feed's 6 ids
  match the 6 stored.
- The trade-off: a clausulazo Biwenger itself retracts stays until someone
  removes it. That has never happened; losing a month of history has.

## The rollover gap

The code rolls over to the new season in May (26-27: bumped 26/05/2026);
Biwenger opens it in July (26-27: `seasonStarted` on 14/07/2026) and until then
its feeds still return last season. The old wipe hid this — last season's
clausulazos landed in the new collection and vanished at the purge. With
nothing ever deleted they would stay, so both writers take a floor from
`TEMPORADA_ACTUAL`: 1 July of its first year, Madrid time. It separates the
last 25-26 clausulazo (22/05/2026) from the 26-27 season start with seven weeks
to spare. `/saldos` counts as lost only archived entries dated from the
union's season start, the ones the rebuild uses.

## Saying so

- Scraper: stored clausulazos missing from the feed → a WARNING log and a line
  in the Sunday Telegram summary.
- `/saldos`: archived entries the live board no longer returns → a note on the
  image, next to the existing self-check. The figures stay correct; the note is
  the early warning that Biwenger has started to forget.

## Seeding

The first scraper run after deploy archives the whole season from 1 September,
while the board is still complete; run the job by hand right after the deploy
rather than wait for Sunday.
