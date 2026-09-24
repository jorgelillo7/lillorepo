# Capability: oraculo-reader

Reads Analítica Fantasy's Oráculo, the second opinion next to Jornada
Perfecta: its recommendation lists and its per-player projections. It reports
what Oráculo says and decides nothing itself.

- **Source:** `core/sdk/oraculo.py`
- **Verified by:** `core/tests/test_oraculo.py` (fixtures in `core/tests/data/`)

---

### Requirement: The scoring system is verified, never assumed

`fetch_picks` SHALL request the recommendation lists for an explicit scoring
system (Biwenger's by default). It SHALL raise `OraculoError` when the
`sistema` the API echoes back differs from the one requested.

The same player projects 7.38 under LaLiga Fantasy and 3.60 under Biwenger. A
read against the wrong scoring system looks healthy while halving every
projection, and nothing downstream could tell. The API route is used precisely
because it is the only one that can be asked for a scoring system and that
reports which one it served. An unverified answer is worth less than no answer.

#### Scenario: lists read, scoring system checked
- **WHEN** the API serves the requested `sistema` **THEN** the result carries
  the matchday, `generated_at`, the model tag, the eight recommendation lists
  and the fixtures
- **WHEN** the API serves a different `sistema` **THEN** `OraculoError` is
  raised, naming it
- *Verifies:* `test_picks_returns_the_lists_and_the_matchday`,
  `test_the_scoring_system_is_verified_not_assumed`

### Requirement: A failed read raises, it never returns empty

An HTTP error, a timeout or a page with no parseable data SHALL raise
`OraculoError`. It SHALL NOT come back as an empty list.

"Oráculo has no opinion on anybody" and "the read broke" call for opposite
responses. An empty list would make them look the same.

#### Scenario: HTTP failure, timeout, unparseable page
- **WHEN** the picks API answers 500 or times out **THEN** `OraculoError` is
  raised
- **WHEN** the predictions page carries no RSC flight payload **THEN**
  `OraculoError` is raised
- *Verifies:* `test_an_http_failure_raises_rather_than_returning_nothing`,
  `test_a_timeout_raises_too`, `test_an_unparseable_page_raises`

### Requirement: Whole-squad projections come from the predictions page

`fetch_predictions` SHALL return every player row embedded in the
`/biwenger/predicciones` page's Next.js flight payload, de-duplicated by
`playerId`. A row with `predictedPoints == 0` SHALL be kept.

The API's recommendation lists only cover highlights. The page is the only
source for the rest of the squad, and it carries its data inside the HTML
rather than behind an endpoint. Parsing that payload is the fragile part of
the reader, so a change in the site's framework has to break a test and not
the service. A zero is a real answer: the site shows `Esperado 0.00` for a
player it expects not to play. Dropping the row would make that player
indistinguishable from one Oráculo does not carry.

#### Scenario: rows read out of the page, zero kept
- **WHEN** the page is served **THEN** every `playerId` in its flight payload
  is returned once
- **WHEN** a player projects 0 **THEN** the row is present with
  `predictedPoints == 0`
- *Verifies:* `test_predictions_are_read_out_of_the_flight_payload`,
  `test_a_row_without_a_projection_is_kept_and_marked`

### Requirement: One matchday at a time

`matchday_dates` SHALL return the `YYYY-MM-DD` dates of the picks' fixtures,
and `rows_for_dates` SHALL keep only the prediction rows whose fixture falls on
one of them. `lists_for` SHALL name, in sorted order, the recommendation lists
a player appears in.

The predictions page carries two matchdays at once: the one in play and the
next one. Mixing them would score a squad against games that have already been
played. The fixture dates from the API are what tells the two apart.

#### Scenario: filter to one matchday, resolve a player's lists
- **WHEN** the picks name fixtures on two dates **THEN** `matchday_dates`
  returns exactly those dates, and `rows_for_dates` drops rows played on any
  other day
- **WHEN** a player appears in several lists **THEN** `lists_for` returns them
  sorted, and returns `[]` for a player in none
- *Verifies:* `test_matchday_dates_come_from_the_api_fixtures`,
  `test_rows_are_filtered_to_one_matchday`,
  `test_lists_a_player_belongs_to_are_resolvable`

### Requirement: Polite by construction

Every request SHALL identify itself with a `lillorepo` user agent and never
imitate a browser. Results SHALL be cached per process for an hour.

The site keeps the ability to see this reader, rate-limit it or block it,
which is what separates reading from hiding. The model retrains hourly, so a
shorter cache would spend someone else's bandwidth and gain nothing.

#### Scenario: identified, cached
- **WHEN** a request is sent **THEN** its `User-Agent` contains `lillorepo`
  and not `Mozilla`
- **WHEN** `fetch_picks` is called twice within the TTL **THEN** the network
  is hit once
- *Verifies:* `test_the_reader_identifies_itself`,
  `test_the_second_call_is_served_from_cache`

#### Scenario: the cache expires
- **WHEN** a second read comes one second inside the TTL **THEN** it is served
  from the cache
- **WHEN** a read comes past the TTL **THEN** it reaches the network again
- *Verifies:* `test_the_cache_expires_after_its_ttl`
