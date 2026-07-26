# Capability: league-scraper

Cloud Run Job that scrapes the league's board messages into Firestore,
categorises them, aggregates per-author participation, and builds the
"tabla justicia" of clause aggressions.

- **Source:** `packages/biwenger_tools/scraper_job/logic/processing.py`
- **Verified by:** `packages/biwenger_tools/scraper_job/tests/test_processing.py`

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
