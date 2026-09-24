# Capability: league-records

The document contracts for the league's history as it is stored in
Firestore: board messages, per-author participation, clausulazos, the
"tabla justicia" and the season palmarés. `scraper_job` writes them, `web`
reads them, and both go through these models so that neither needs to know
the stored shape.

- **Source:** `core/domain/models.py`
- **Verified by:** `core/tests/test_domain_models.py`

---

### Requirement: The identity lives in the document id, not in a field

Every model whose identity is natural SHALL take it from the Firestore
document id when reading and leave it out of the fields when writing: the
message's `id_hash`, the participation's `autor`, the justice entry's
`equipo` and the palmarés' `temporada`. Clausulazos SHALL use auto-ids and
ignore the id when reading.

Storing the key twice would let the two copies drift. The id is what
Firestore indexes and what a re-run overwrites.

#### Scenario: key out of the fields, back from the id
- **WHEN** a message is serialised **THEN** `id_hash` is not a field, and
  reading the document under that id restores an equal model
- **WHEN** a document with no fields is read **THEN** the id is still set and
  every text field is empty
- *Verifies:* `test_league_message_firestore_roundtrip`,
  `test_league_message_from_firestore_handles_missing_fields`

### Requirement: Dates are stored as timestamps and read back as Madrid display strings

`fecha` SHALL be written as a native, timezone-aware Firestore timestamp in
Madrid time when the display string parses, and as the raw string otherwise.
Reading SHALL render it back in the model's own display format: seconds for
messages, minutes for clausulazos. A value that is already a string SHALL
pass through untouched.

Native timestamps are what make ordering and range queries work in
Firestore. Templates and sorting code only ever deal with the display string,
so they do not need to know about timestamps. Keeping an unparseable raw
string, instead of dropping it, means no data is lost silently.

#### Scenario: known formats parse; each model keeps its precision
- **WHEN** a seconds-precision or minute-precision date is parsed **THEN** it
  becomes a Madrid-tz datetime, and unknown or empty input yields `None`
- **WHEN** a message or a clausulazo round-trips **THEN** its `fecha` string
  comes back exactly, in its own precision
- *Verifies:* `test_parse_fecha_known_formats`,
  `test_league_message_firestore_roundtrip`,
  `test_clausulazo_firestore_roundtrip`

#### Scenario: an unparseable date survives as given
- **WHEN** a message's `fecha` matches no known format **THEN** the same string
  is stored and read back
- *Verifies:* `test_an_unparseable_fecha_is_stored_as_given`

### Requirement: Collections are native arrays, with derived totals

Participation SHALL store its four id lists as native arrays plus a derived
`total`, which is the sum of their lengths. Justice entries SHALL store
`hechos`/`recibidos` as arrays of `{team, count}` maps, and read them back as
`[team, count]` pairs.

The derived `total` exists so a ranking can be a Firestore query rather than a
full scan. Maps are used because Firestore cannot store nested arrays.

#### Scenario: round-trips and empty total
- **WHEN** a participation or a justice entry round-trips **THEN** it comes
  back equal, and the stored document carries the derived shape
- **WHEN** a participation has no ids **THEN** its `total` is 0
- *Verifies:* `test_participation_firestore_roundtrip`,
  `test_participation_total_with_empty_lists`,
  `test_justice_entry_firestore_roundtrip`

### Requirement: The palmarés reads old seasons and new ones alike

A palmarés SHALL round-trip its podium, fines, neutrals, per-user
`standings_table` and cup winners. When an older document carries a separate
`farolillo` field, reading SHALL append it to the end of `multas` unless it
is already there. A season with no `standings_table` SHALL read as an empty
table.

Older seasons stored the farolillo beside the fines. Callers see one ordered
list where the last fine is the farolillo, marked at render time, and the old
documents stay as they are until someone rewrites them. The per-user table
only exists for seasons captured from 26-27 onwards, and the page falls back
to the podium when it is empty.

#### Scenario: legacy farolillo, standings table, round-trip
- **WHEN** a palmarés round-trips **THEN** it comes back equal
- **WHEN** a legacy document has `farolillo` apart from `multas` **THEN** it
  is read as the last entry of `multas`
- **WHEN** a season carries a standings table, or does not **THEN** both
  round-trip, and each standing row round-trips on its own
- *Verifies:* `test_palmares_firestore_roundtrip`,
  `test_palmares_legacy_firestore_doc_merges_farolillo_into_multas`,
  `test_palmares_with_standings_table_roundtrip`,
  `test_season_standing_firestore_roundtrip`

#### Scenario: cup winners round-trip
- **WHEN** a palmarés with a cup winner is stored and read back **THEN** `copas`
  comes back unchanged
- *Verifies:* `test_palmares_cup_winners_round_trip`
