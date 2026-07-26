# Capability: community

Contributor ranking and achievement badges for the be_water community page,
computed from the catalog's contribution metadata.

- **Source:** `packages/be_water/web/community.py`
- **Verified by:** `packages/be_water/web/tests/test_community.py`

---

### Requirement: Score and ranking

`build_community_stats` SHALL rank contributors by score = `2 × waters_added +
verified_fields_count`, descending. Seed waters (no real contributor) SHALL NOT
rank.

#### Scenario: scoring and exclusion
- **WHEN** the catalog mixes seed waters and real contributions
- **THEN** seed waters do not rank; a contributor with 2 waters + 2 verified
  fields scores 6, one with 1 water + 0 fields scores 2, ordered desc
- *Verifies:* `test_seed_waters_do_not_rank`, `test_scores_and_ranking_order`

### Requirement: Monthly counters

Per-contributor counters SHALL distinguish all-time `waters_added` from
`month_waters` (added in the reporting month), using each water's `added_at`.

#### Scenario: month vs all-time
- **WHEN** a contributor added one water this month and one last month
- **THEN** `waters_added` = 2 and `month_waters` = 1
- *Verifies:* `test_monthly_counters_use_added_at`

### Requirement: Achievement badges on thresholds

Badges SHALL fire on their thresholds: first water, verified-field counts, photo
counts, province spread, monthly streak, water-count tiers (10 → "Manantial
andante", 25 → "Fuente inagotable"), a sparkling-water badge ("Con gas"), and
"Explorador" for a water outside the AESAN registry. Badges below their
threshold SHALL NOT fire.

#### Scenario: thresholds fire and gate correctly
- **WHEN** a contributor has 5 waters × 9 verified fields, 5 photos, 5
  provinces, all this month
- **THEN** the first-gota / field / photo / province / streak badges fire, but
  the 10- and 25-water tiers and "Con gas" do not
- **WHEN** they reach 11 waters including a sparkling one
- **THEN** "Manantial andante" and "Con gas" fire, "Fuente inagotable" does not
- *Verifies:* `test_achievements_fire_on_thresholds`,
  `test_con_gas_and_higher_water_count_tiers`

#### Scenario: Explorador vs the registry
- **WHEN** a contributed water is absent from / present in the AESAN registry
- **THEN** "Explorador" fires / does not fire
- *Verifies:* `test_explorador_fires_for_water_outside_aesan_registry`,
  `test_explorador_does_not_fire_for_water_matching_aesan_registry`
