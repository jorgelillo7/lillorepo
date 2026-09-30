## MODIFIED Requirements

### Requirement: Only the current season counts, and the read must reach its start

`/saldos` SHALL rebuild from the live board merged with
`board_archive/{season}/entries`, deduplicated by `board_entry_key`. Entries
older than the latest `seasonStarted` SHALL be ignored. When neither the read
nor the archive contains a `seasonStarted` entry, it SHALL raise rather than
return figures, since the rebuild would be missing the season's first movements.

The board is paged newest first and SHALL stop at the page that contains
`seasonStarted` — a full-history read is ten times the requests for entries
that are then discarded.

When the archive holds entries of the current season the live board no longer
returns, the image SHALL say how many, next to the self-check: the figures are still right, and
the note is the early warning that Biwenger has started to forget. When the
archive cannot be read, the rebuild SHALL use the live board alone and the
image SHALL say the archive was not read — the answer is no worse than
without an archive, and it does not pretend to be protected.

#### Scenario: last season's movements, a short read, and a forgetful board
- **WHEN** the read holds entries from before the latest season start
- **THEN** they do not move anyone's cash
- **WHEN** neither the read nor the archive contains a `seasonStarted` **THEN**
  it raises
- **WHEN** the live board lost September's transfers the archive holds **THEN**
  the cash is the same as from the full board, and the image says entries were
  filled from the archive
- **WHEN** the live board no longer reaches `seasonStarted` but the archive
  holds it **THEN** the rebuild still answers
- **WHEN** the archive cannot be read **THEN** the live board alone answers and
  the image says so
- *Verifies:* `test_entries_before_the_season_start_are_ignored`,
  `test_a_read_that_never_reaches_the_season_start_raises`,
  `test_get_all_board_messages_stops_at_the_page_holding_until_type`
  (`core/tests/test_biwenger_client.py`),
  `test_the_archive_fills_what_the_live_board_lost`,
  `test_archived_entries_the_board_lost_are_reported`,
  `test_the_union_still_needs_a_season_start`,
  `test_the_archive_fills_a_lost_season_start`,
  `test_an_archived_older_season_is_not_counted_as_lost`,
  `test_nothing_lost_says_nothing_about_the_archive`,
  `test_an_unreadable_archive_is_said_not_hidden`,
  `test_league_money_adds_what_only_the_archive_holds`,
  `test_an_unreadable_archive_leaves_the_live_board_and_says_so`
  (`api/tests/test_actions.py`)
