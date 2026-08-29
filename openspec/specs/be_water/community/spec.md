# Capability: community

Contributor ranking and achievement badges for the be_water community page,
computed from the catalog's contribution metadata.

- **Source:** `packages/be_water/web/community.py`
- **Verified by:** `packages/be_water/web/tests/test_community.py`

---

### Requirement: The score counts acts, not the catalog's current state

`build_community_stats` SHALL rank contributors by score = `2 × waters_added +
2 × past_analyses + verified_fields_count`, descending. Seed waters (no real
contributor) SHALL NOT rank.

It SHALL read the analysis series as well as the fichas. A composition is a
dated series, and an older analysis deliberately never touches the ficha — so
a ranking built from `waters` alone paid **nothing** for photographing a label
from a year nobody had documented, which is the work the series exists to
invite. A past analysis is worth what a new water is worth: it is the same
act, someone with a bottle in hand, and it is the scarcer of the two once the
catalog fills up.

Nothing SHALL be paid for twice:

- A dated water's entry for the composition it *currently* shows is the act of
  adding that water, so only entries on some **other** date count as
  `past_analyses`.
- Confirmed fields SHALL be counted in the entry that earned them, and on the
  ficha only for undated waters, which have no entry. The ficha carries the
  union of every label ever photographed, so counting both would inflate the
  score of exactly the contributors who document a water most.

#### Scenario: scoring and exclusion
- **WHEN** the catalog mixes seed waters and real contributions
- **THEN** seed waters do not rank; a contributor with 2 waters + 2 verified
  fields scores 6, one with 1 water + 0 fields scores 2, ordered desc
- **WHEN** someone adds an analysis for a year a water lacked, adding no water
- **THEN** they rank, scoring 2 plus the fields that label confirmed
- **WHEN** the entry is the water's own current composition
- **THEN** it adds no `past_analyses` and its fields are counted once
- *Verifies:* `test_seed_waters_do_not_rank`, `test_scores_and_ranking_order`,
  `test_rescuing_an_analysis_a_water_lacked_is_worth_adding_one`,
  `test_a_water_is_not_paid_twice_for_its_own_composition`,
  `test_the_field_count_does_not_double_when_a_water_is_dated`,
  `test_an_undated_water_still_counts_its_fields`

### Requirement: Monthly counters

Per-contributor counters SHALL distinguish all-time `waters_added` from
`month_waters` (added in the reporting month), using each water's `added_at`.

#### Scenario: month vs all-time
- **WHEN** a contributor added one water this month and one last month
- **THEN** `waters_added` = 2 and `month_waters` = 1
- *Verifies:* `test_monthly_counters_use_added_at`

### Requirement: Achievement badges on thresholds

Badges SHALL fire on their thresholds: first water, verified-field counts,
photo counts, province spread, monthly streak, water-count tiers (20 →
"Manantial andante", 50 → "Fuente inagotable"), a sparkling-water badge ("Con
gas"), "Explorador" for a water outside the AESAN registry, and three over the
analysis series — "Segunda opinión" (a first past analysis), "Archivero" (five
waters turned into a series) and "Arqueólogo" (15 past analyses). Badges below
their threshold SHALL NOT fire.

Thresholds SHALL be set to be worked for. A badge everybody holds says nothing
about anybody, and the ceiling moved when compositions became a series: a water
is no longer one contribution but as many as it has been measured.

"Archivero" counts **waters given a history**, not analyses added — five
measurements of one water is one history, not five.

#### Scenario: thresholds fire and gate correctly
- **WHEN** a contributor has 7 waters × 9 verified fields, 7 photos, 7
  provinces, all this month
- **THEN** the first-gota / field / province / streak badges fire, but the
  photo tier, the 20- and 50-water tiers, "Con gas" and "Segunda opinión" do
  not
- **WHEN** they reach 21 waters including a sparkling one
- **THEN** "Manantial andante" and "Con gas" fire, "Fuente inagotable" does not
- **WHEN** five analyses are added to the *same* water
- **THEN** `past_analyses` is 5, `histories_deepened` is 1, and "Archivero"
  does not fire
- *Verifies:* `test_achievements_fire_on_thresholds`,
  `test_con_gas_and_higher_water_count_tiers`,
  `test_archivero_counts_waters_turned_into_a_series_not_analyses`

#### Scenario: Explorador vs the registry
- **WHEN** a contributed water is absent from / present in the AESAN registry
- **THEN** "Explorador" fires / does not fire
- *Verifies:* `test_explorador_fires_for_water_outside_aesan_registry`,
  `test_explorador_does_not_fire_for_water_matching_aesan_registry`
