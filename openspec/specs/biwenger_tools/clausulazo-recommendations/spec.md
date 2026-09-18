# Capability: clausulazo-recommendations

The `/recomendaciones` surface: find the best rival players to clause, filtered
by an affordability budget that scales with cash and by league house rules, and
present the top per position. Shares candidate helpers with clausulazo-emergency.

- **Source:** `packages/biwenger_tools/api/logic/recommendations.py`,
  `clausulazo_candidates.py`, `pact_store.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_recommendations.py`,
  `test_pact.py`

---

### Requirement: Dynamic affordability margin

`compute_dynamic_margin` SHALL be 40% of cash, rounded to the nearest 500k and
clamped to `[2M, 10M]`; a non-positive cash yields the 2M minimum. This margin
widens the affordability target as the wallet grows.

#### Scenario: scaling and clamps
- **WHEN** cash is 0 / 5M / ~13M / 20M / 30M+ 
- **THEN** margin is 2M / 2M / 5M / 8M / 10M (capped)
- *Verifies:* `test_compute_dynamic_margin_scales_with_cash`

### Requirement: Ranking reads the number the card displays

`sf_of` SHALL read the blended prediction (`custom_prediction`) when one was
computed for the row, falling back to the raw JP rate only when it was not.
`filter_affordable`, `top_per_position` and `rebuild`'s value-per-clause both
rank and cut candidates by this reader — reading the raw rate underneath would
let the Oráculo blend move a card's displayed number without moving where it
sorts or whether it clears the SF-0 cut.

#### Scenario: the blend, when present, decides
- **WHEN** a candidate row carries both a JP rate and a blended prediction
- **THEN** `sf_of` returns the blend
- **WHEN** no blend ran **THEN** it returns the JP rate
- **WHEN** neither is available **THEN** it returns 0
- *Verifies:* `test_sf_of_prefers_the_blended_prediction_over_the_raw_jp_rate`,
  `test_sf_of_falls_back_to_the_raw_jp_rate_when_no_blend_ran`,
  `test_sf_of_is_zero_for_a_player_with_no_projection_at_all`

### Requirement: Affordability filter + house rules

`filter_affordable` SHALL exclude my own players, non-clausulable (locked)
players, players above the target budget, and SF-0 players. It SHALL enforce the
league house rule: **never clause a rival's only goalkeeper** — a rival with a
backup GK is fair game, and the rule SHALL NOT extend to outfield positions
(a rival's only striker stays recommendable).

#### Scenario: exclusions and the sole-GK rule
- **WHEN** filtering a mix of mine / locked / too-expensive / SF-0 / affordable
- **THEN** only the affordable, clausulable, non-mine, SF>0 survive
- **WHEN** a rival's sole GK, a rival's backup GK, and a rival's sole striker
  are candidates **THEN** only the backup GK and the striker survive
- *Verifies:* `test_filter_affordable_excludes_my_players_and_locked_and_too_expensive`,
  `test_filter_affordable_excludes_rival_only_gk_house_rule`

### Requirement: Rival annotation and top-per-position

`gather_rivals` SHALL tag each rival row with the owner's GK count and user id
(feeding the house rule). `top_per_position` SHALL group candidates by primary
position, mark multi-position players, and cap at `top_n`.

#### Scenario: annotation, grouping, cap
- **WHEN** gathering rivals **THEN** each row carries owner GK count + user id
- **WHEN** presenting **THEN** candidates group by primary position, multi-pos
  players are badged, and each group is capped at `top_n`
- *Verifies:* `test_gather_rivals_annotates_owner_gk_count_and_user_id`,
  `test_top_per_position_groups_by_primary_and_marks_multi`,
  `test_top_per_position_caps_at_top_n`

### Requirement: Telegram formatting

The recommendations message SHALL show exact euros, a multi-position badge, mark
a manually-set margin, and dash the bid when max_bid is missing.

#### Scenario: formatting details
- **WHEN** rendering **THEN** exact euros + multi badge appear; a manual margin
  is marked; a missing max_bid renders a dash
- *Verifies:* `test_format_telegram_text_includes_multi_badge_and_exact_euros`,
  `test_format_telegram_text_marks_manual_margin`,
  `test_format_telegram_text_dashes_when_max_bid_missing`

### Requirement: The non-aggression pact is shown here, never enforced

A manager under the pact (see clausulazo-emergency) SHALL still have their
players ranked and listed by `/recomendar`, each row carrying `pacted: true`
and rendered with a 🤝 badge plus a footnote naming `/emergencia` as where the
pact binds.

The veto SHALL NOT live in `filter_affordable`, which both flows share:
applying it there would hide pacted players from this surface too. `/recomendar`
is advice about the whole market, and the owner is the one who decides whether
a pact still holds.

#### Scenario: a pacted player is ranked on merit and flagged
- **WHEN** the highest-SF candidate belongs to a pacted manager
- **THEN** they head the position's list, flagged, above an unpacted rival
- *Verifies:* `test_recommendations_keep_pacted_players_and_carry_the_flag`,
  `test_recommendations_render_a_badge_for_a_pacted_player`
