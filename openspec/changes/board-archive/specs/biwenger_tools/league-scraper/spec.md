## ADDED Requirements

### Requirement: The board's money entries are archived, append-only

The scraper SHALL read the board back to the season start and store every
money entry (`transfer`, `market`, `adminTransfer`, `clauseIncrement`, `bonus`,
`roundFinished`, `seasonStarted`) raw in `board_archive/{season}/entries`,
keyed by `board_entry_key`, dropping entries older than the latest
`seasonStarted` the read returned or than 1 July of the season's first year,
whichever is later. It SHALL write only keys not yet stored
and SHALL never delete or overwrite an archived entry.

Biwenger purges these entries at the season change and has lost them mid-season;
raw entries let every derivation (`/saldos`) be fixed and re-run later, where a
stored balance would freeze its bugs.

#### Scenario: archive once, keep forever
- **WHEN** the scraper runs twice over the same board **THEN** the second run
  writes nothing
- **WHEN** the board no longer returns an archived entry **THEN** the archive
  still holds it
- **WHEN** the read never reaches `seasonStarted` **THEN** every money entry
  read is archived and the run logs a WARNING
- *Verifies:* `test_money_entries_are_archived_once`,
  `test_the_archive_keeps_entries_the_board_lost`,
  `test_a_board_read_without_its_season_start_is_archived_with_a_warning`,
  `test_the_archive_skips_last_season_after_the_rollover`
