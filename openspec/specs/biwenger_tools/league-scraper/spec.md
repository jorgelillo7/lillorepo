# Capability: league-scraper

Cloud Run Job that scrapes the league's board messages into Firestore,
categorises them, aggregates per-author participation, keeps every clausulazo
of the season and builds the "tabla justicia" from them, and archives the
board's money entries for `/saldos`. Clausulazos and the archive only ever
grow: Biwenger forgets, Firestore does not.

- **Source:** `packages/biwenger_tools/scraper_job/logic/processing.py`,
  `packages/biwenger_tools/scraper_job/main.py`
- **Verified by:** `packages/biwenger_tools/scraper_job/tests/test_processing.py`,
  `packages/biwenger_tools/scraper_job/tests/test_main.py`

---

### Requirement: Title categorisation

`categorize_title` SHALL map a message title to one of `cronica`, `dato`,
`cesion`, `comunicado`. Matching is accent- and case-insensitive; `cronica`
matching is lenient (bare "CRÓNICA", "CRÓNICA <x>", "CRÓNICAS" all count) but
SHALL NOT match words that merely start with the substring
("Cronicado" → comunicado). Anything unmatched (including empty) SHALL default
to `comunicado`.

#### Scenario: keyword mapping and the substring guard
- **WHEN** the title is "Crónica jornada 10" / "DATOS - …" / "Cesión - …" /
  "" / "Cronicado el partido"
- **THEN** cronica / dato / cesion / comunicado / comunicado
- *Verifies:* `test_categorize_title`

### Requirement: Participation aggregation

`process_participation` SHALL aggregate message ids per author and category,
deduplicating by `id_hash`, exposing a `total` = sum of the four category
lists. Authors with no messages in a category SHALL carry an empty list, and a
non-competing cronista present in the user map SHALL be a first-class author.

#### Scenario: dedup and totals
- **WHEN** an author has a duplicate message id and messages across categories
- **THEN** the id appears once, per-category lists are correct, `total` sums
  them, and the cronista is included
- *Verifies:* `test_process_participation`

### Requirement: Chronological ordering, invalid dates last

`sort_messages` SHALL order messages newest-first by parsing the
`DD-MM-YYYY HH:MM:SS` date, placing entries with an unparseable date last.

#### Scenario: mixed valid and invalid dates
- **WHEN** messages carry three valid dates and one invalid
- **THEN** valid ones sort newest-first and the invalid one lands last
- *Verifies:* `test_sort_messages`

### Requirement: Clausulazo parsing

`parse_clausulazos` SHALL extract clause events, resolving the player name
whether the payload carries a full player dict or a bare id (via the players
map), capturing seller, buyer and amount. Non-clause board entries SHALL be
skipped.

#### Scenario: dict player, int player, non-clause
- **WHEN** the payload has a dict player / an int id / a non-clause type
- **THEN** the name resolves from the dict / from the map / the entry is skipped
- *Verifies:* `test_parse_clausulazos_with_dict_player`,
  `test_parse_clausulazos_with_int_player`,
  `test_parse_clausulazos_skips_non_clause_entries`

### Requirement: Tabla justicia

`build_tabla_justicia` SHALL aggregate, per team, clauses made and received,
their most-frequent victim (`punto_de_mira`) and most-frequent aggressor
(`mayor_agresor`), and the per-victim breakdown. An empty input SHALL yield an
empty table.

#### Scenario: aggression counts and extremes
- **WHEN** team A clauses B twice and C clauses A once
- **THEN** A has 2 made / 1 received, `punto_de_mira` = B, `mayor_agresor` = C
- *Verifies:* `test_build_tabla_justicia`, `test_build_tabla_justicia_empty`

### Requirement: Clausulazos are never deleted by the scraper

The scraper SHALL add the clausulazos the feed returns that are not stored yet,
and SHALL never delete or rewrite a stored one. A clausulazo is already stored
when a stored one has the same date and price, whatever the team and player
names say. Clausulazos dated before 1 July of the season's first year SHALL be
ignored: the code rolls over in May, weeks before Biwenger opens the season in
July, and the feed still returns last season's in between. The justice table
SHALL be built from stored and fetched clausulazos together. When stored clausulazos are
missing from the feed, the run SHALL log a WARNING naming how many, and the
Sunday Telegram summary SHALL say so.

Biwenger stopped returning a season's first weeks of clausulazos once, and at
every season change it deletes them all; a scraper that mirrors the feed deleted
them from Firestore too. The stored copy is the only history left.

#### Scenario: the feed forgets
- **WHEN** a stored clausulazo is missing from the feed **THEN** it stays in
  Firestore and in the justice table, and the run reports it
- **WHEN** the feed returns a new clausulazo **THEN** it is added and nothing
  stored is removed
- **WHEN** a team renames itself **THEN** its clausulazos are neither
  duplicated nor counted twice
- *Verifies:* `test_clausulazos_missing_from_the_feed_are_kept`,
  `test_the_justice_table_counts_stored_and_fetched_clausulazos`,
  `test_clausulazos_missing_from_the_feed_are_reported`,
  `test_a_renamed_team_does_not_duplicate_its_clausulazos`

#### Scenario: between the rollover and the new season
- **WHEN** the feed still returns last season's clausulazos **THEN** none is
  stored, counted in the justice table or reported missing
- *Verifies:* `test_last_seasons_clausulazos_are_neither_stored_nor_missed`

### Requirement: The board's money entries are archived, append-only

The scraper SHALL read the board back to the season start and store every
money entry (`transfer`, `market`, `adminTransfer`, `clauseIncrement`, `bonus`,
`roundFinished`, `seasonStarted`, and any other type whose content carries an
`amount`) raw in `board_archive/{season}/entries`, keyed by `board_entry_key`,
dropping entries older than the latest `seasonStarted` the read returned or
than 1 July of the season's first year, whichever is later. It SHALL write only
keys not yet stored and SHALL never delete or overwrite an archived entry.

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
- **WHEN** Biwenger adds a type that carries an `amount` **THEN** it is
  archived too — the type `/saldos` would flag as unknown is never lost
- *Verifies:* `test_money_entries_are_archived_once`,
  `test_an_unknown_type_carrying_an_amount_is_archived_too`,
  `test_the_archive_keeps_entries_the_board_lost`,
  `test_a_board_read_without_its_season_start_is_archived_with_a_warning`,
  `test_the_archive_skips_last_season_after_the_rollover`
