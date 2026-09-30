# Tasks

## Core — the key
- [x] `board_entry_key` + `MONEY_ENTRY_TYPES` in `core/sdk/biwenger.py`
- [x] `test_board_entry_key_ignores_names_icons_and_comment_counts`
- [x] `test_board_entry_key_separates_entries_in_the_same_second`
- [x] `test_a_republished_round_keeps_its_own_key`

## Scraper — clausulazos never deleted
- [x] insert only unseen (date + price) instead of wipe; justice table from
      stored ∪ new
- [x] `test_clausulazos_missing_from_the_feed_are_kept`
- [x] `test_the_justice_table_counts_stored_and_fetched_clausulazos`
- [x] `test_clausulazos_missing_from_the_feed_are_reported`
- [x] `test_a_renamed_team_does_not_duplicate_its_clausulazos`
- [x] season floor (1 July): `test_last_seasons_clausulazos_are_neither_stored_nor_missed`

## Scraper — the archive
- [x] archive the money entries of the season, new keys only
- [x] `test_money_entries_are_archived_once`
- [x] `test_the_archive_keeps_entries_the_board_lost`
- [x] `test_a_board_read_without_its_season_start_is_archived_with_a_warning`
- [x] `test_the_archive_skips_last_season_after_the_rollover`

## `/saldos` — archive ∪ live
- [x] `_league_money` merges the archive before `season_entries` (so `/saldos`
      and the protection watch both get it); an unreadable archive degrades
      to the live board, with a note
- [x] `test_the_archive_fills_what_the_live_board_lost`
- [x] `test_the_archive_fills_a_lost_season_start`
- [x] `test_an_archived_older_season_is_not_counted_as_lost`
- [x] `test_archived_entries_the_board_lost_are_reported`
- [x] `test_nothing_lost_says_nothing_about_the_archive`
- [x] `test_an_unreadable_archive_is_said_not_hidden`
- [x] `test_the_union_still_needs_a_season_start`
- [x] `test_league_money_adds_what_only_the_archive_holds`
- [x] `test_an_unreadable_archive_leaves_the_live_board_and_says_so`

## Landing
- [x] PR A: "Clausulazos are never deleted" folded into `league-scraper`
- [ ] PR B: the archive requirement and the core key folded
- [ ] PR C: the `league-cash` delta folded; delete this folder
- [ ] `docs/firestore.md`: `board_archive`; OPERATIONS: seed run after deploy
- [ ] after deploy: run the scraper job by hand; archived counts = the season's
      money entries; `/saldos` identical to the euro
