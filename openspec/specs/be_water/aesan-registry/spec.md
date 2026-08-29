# Capability: aesan-registry

Coverage tracking against the registry of officially recognised Spanish
mineral waters (a generated snapshot). Drives the "quedan N por cubrir" and the
pending-waters list on the community page.

- **Source:** `packages/be_water/web/aesan.py`, `aesan_snapshot.py`,
  `packages/be_water/scripts/refresh_aesan_snapshot.py`,
  `.github/workflows/aesan-refresh.yml`
- **Verified by:** `packages/be_water/web/tests/test_aesan.py`,
  `packages/be_water/scripts/tests/test_refresh_aesan_snapshot.py`

---

### Requirement: Coverage counts unique names

`coverage` SHALL count the registry by **unique name**, so a brand recognised
under several springs counts once toward the total, and SHALL also report
`entries`, the raw row count.

Both numbers are published, and they are not interchangeable: the pages say
"España reconoce oficialmente N aguas minerales naturales **distintas**",
which is a factual claim about the state's register. Stating the deduplicated
figure as the register's own size overstates neither number but describes the
wrong one.

#### Scenario: multi-spring brand counts once
- **WHEN** the registry lists "Font Vella" under two springs plus two other
  brands, with one covered
- **THEN** total = 3 (unique names), covered = 1, entries = 4
- *Verifies:* `test_coverage_separates_distinct_names_from_registry_rows`

### Requirement: Pending list dedupes multi-spring brands

`pending_waters` SHALL return uncovered registry entries collapsed to one row
per name (a brand with two springs is a single pending row).

#### Scenario: two springs, one pending row
- **WHEN** an uncovered brand spans two springs
- **THEN** it appears once in the pending list
- *Verifies:* `test_pending_dedupes_multi_spring_brand`

### Requirement: Pending length matches the coverage gap

The invariant the UI relies on: `len(pending_waters) == coverage.total −
coverage.covered`. "Quedan N" and "ver las N pendientes" SHALL always agree.

#### Scenario: count invariant holds
- **WHEN** computing coverage and the pending list over the same catalog
- **THEN** the pending length equals total − covered
- *Verifies:* `test_pending_length_matches_coverage_gap`

### Requirement: The snapshot comes from the published recognitions

`aesan_snapshot.py` SHALL be generated, never hand-edited, from the official
list of natural mineral waters recognised by Spain. AESAN published that list
as its own PDF until it retired the whole `/AECOSAN/` tree; the source of
record is now the consolidated list the Commission publishes under Article 1 of
Directive 2009/54/EC, whose "recognised by Spain" section is the same registry.
Waters that Spain recognises but which are sourced abroad live in a separate
third-country table and SHALL be excluded.

The generator SHALL refuse to overwrite the snapshot when the parse looks
wrong — fewer than 100 entries, or any entry whose province did not parse — and
SHALL reject a download whose bytes are not a PDF, because a retired URL
answers with an HTML error page that a PDF reader reports as a corrupt stream.

#### Scenario: the parse survives the document's shape
- **WHEN** a row fits one line
- **THEN** trade description, source and place split on the page's own columns,
  with the province taken from the trailing parenthesis
- **WHEN** a place wraps to two lines, rendering its overflow *above* the row
- **THEN** the overflow joins the row below it
- **WHEN** a place wraps to three lines, overflowing *below* instead
- **THEN** the row keeps consuming lines until the province closes
- *Verifies:* `test_reads_a_plain_row`,
  `test_a_two_line_place_wraps_above_its_row`,
  `test_a_three_line_place_wraps_below_its_row`

#### Scenario: only Spain's own table is read
- **WHEN** page headers repeat across a page break
- **THEN** no entry is lost or invented
- **WHEN** another country's table, or Spain's third-country table, is present
- **THEN** neither contributes entries
- *Verifies:* `test_repeated_page_furniture_is_not_read_as_a_water`,
  `test_other_countries_and_third_country_tables_are_excluded`

### Requirement: The refresh runs on a schedule and reports both outcomes

The snapshot SHALL be regenerated monthly by `.github/workflows/aesan-refresh.yml`,
which SHALL open a pull request when the list changed and SHALL fail loudly,
with a Telegram message, when the generator refuses to write. It SHALL NOT
merge anything on its own: the diff is the news, and a human reads it.

No scenario: the verification is the scheduled run itself, and claiming a test
that does not exist would be worse than claiming nothing. What the generator
does with a bad parse is covered above; what CI does with a red run is CI's.

This exists because neither failure announces itself. A registry that quietly
stops changing looks identical to one nobody is refreshing — the snapshot sat
eight years stale, on a URL that had begun answering 404, until an unrelated
question about a bottle happened to expose it.
