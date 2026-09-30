# Proposal — keep the league's money history even if Biwenger loses it

## Why

Biwenger deletes every money-moving board entry (`transfer`, `market`,
`adminTransfer`, `clauseIncrement`, `bonus`) at the season change: the only
older entries the board still returns are non-money types. Measured: the live
`transfer` feed holds this season's clausulazos only, and 25-26 survives solely
in our Firestore — 109 clausulazos, the first on 28/09 although the season's
first clausulazos came weeks earlier. Those first weeks were lost when the board
stopped returning them mid-season and the scraper, which rewrites
`clausulazos/{season}/transfers` in full every Sunday, deleted them from
Firestore too.

Two things depend on a board that forgets:

- the scraper's clausulazos and the justice table derived from them, which
  follow the board's deletions by design;
- `/saldos`, which rebuilds every manager's cash from the live board and stores
  nothing.

## What changes

1. **The scraper never deletes a clausulazo.** It adds and updates what the feed
   returns and keeps what the feed no longer does; the justice table counts
   both. When stored clausulazos are missing from the feed, it says so.
2. **The scraper archives the board's money entries, append-only**, in
   `board_archive/{season}/entries/{key}`, under a key derived from what does
   not change (Biwenger gives the entries no id).
3. **`/saldos` rebuilds from archive ∪ live board**, deduplicated by that key.
   It still refuses to answer when the union holds no season start, and it says
   so when the archive holds movements the live board no longer returns.

## Out of scope

- Earlier seasons: already purged upstream; 25-26 lives on as its 109
  clausulazos, which change 1 protects.
- Weekly balance checkpoints — possible later on top of the archive.
