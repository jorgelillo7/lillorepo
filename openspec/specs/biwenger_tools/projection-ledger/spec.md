# Capability: projection-ledger

The record of what was projected and what happened: every round, the eleven
the Oráculo blend picked beside the eleven Jornada Perfecta alone would have
picked, both captured before the round kicks off, then the real points once
Biwenger calls the round finished. It answers whether the blend beats Jornada
Perfecta alone, and holds the league-wide data for the open measurements in
`PENDING.md` (what the squad is made of, the opponent effect).

How to read its output, and the ways it is easy to misread:
`docs/technical/backend/projection-ledger.md`.

- **Source:** `packages/biwenger_tools/api/logic/projection_ledger.py` (pure),
  `projection_ledger_capture.py`, `projection_ledger_store.py`,
  `real_points.py`, `opponent_effect.py`, `squad_gap.py` (pure);
  `packages/biwenger_tools/scripts/projections/report.py`,
  `opponent_effect.py`, `repair_matchday.py`, `squad_gap.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_projection_ledger.py`,
  `test_projection_ledger_capture.py`, `test_projection_ledger_store.py`,
  `test_real_points.py`, `test_opponent_effect.py`, `test_squad_gap.py`

---

### Requirement: The projection is captured for the round the pick lands on, never after it kicks off

`target_round` SHALL return the current round while its first kick-off is
still ahead, the next round once the current one has kicked off, and `None`
when neither kick-off is confirmed in the future or the payload is malformed.
A capture with no target SHALL write nothing: a stale silence beats a snapshot
that overwrites a round already under way.

#### Scenario: which round
- **WHEN** the current round has not kicked off **THEN** it is the target
- **WHEN** it has kicked off and the next has not **THEN** the next is
- **WHEN** neither has games, both are in the past, or the payload is not a
  round **THEN** there is no target
- *Verifies:* `test_target_round_is_the_current_one_before_its_kickoff`,
  `test_target_round_is_next_once_the_current_one_has_kicked_off`,
  `test_target_round_is_none_when_neither_kickoff_is_confirmed`,
  `test_target_round_is_none_once_both_are_in_the_past`,
  `test_target_round_survives_a_malformed_payload`

### Requirement: The snapshot holds both elevens and every provider number

`build_snapshot` SHALL solve the lineup twice, on the blend and with the blend
stripped, and store both elevens, whether they differ and how. Per player it
SHALL store Jornada Perfecta's SF, Oráculo's points, chance and the lists the
player was on, and the blend. A squad with no legal eleven SHALL still produce
a snapshot.

#### Scenario: the two elevens and the numbers behind them
- **WHEN** the blend swaps a player **THEN** the snapshot says the elevens
  differ and names who is only in each
- **WHEN** nothing moves **THEN** it says they agree
- **WHEN** a player is on Oráculo lists **THEN** the lists are stored
- *Verifies:* `test_the_snapshot_reports_two_elevens_that_actually_differ`,
  `test_the_snapshot_says_so_when_the_two_elevens_agree`,
  `test_the_snapshot_carries_every_provider_number_per_player`,
  `test_the_snapshot_survives_a_squad_with_no_legal_eleven`,
  `test_the_snapshot_keeps_the_oraculo_lists_each_player_was_on`

### Requirement: The league halves are extras that never cost our own record

The capture SHALL add, each in its own guard so a failure leaves our own
projection stored:

- `league_projection`: every squad's projected eleven (total SF), from the
  same morning;
- `league_jp`: Jornada Perfecta's SF for **every player it projects** in the
  competition, keyed by the Biwenger id as a string. A player it does not
  project is left out, never stored as zero.

`league_jp` exists because whether a fixture moves the projection can only be
measured on the whole competition; our own squad meets Barcelona a few times
a season.

#### Scenario: both extras, and a failure in either
- **WHEN** the league reads work **THEN** the snapshot carries every squad's
  eleven and every projected player's SF
- **WHEN** either read raises **THEN** our own projection is still written,
  without that extra
- **WHEN** Jornada Perfecta has no projection for a player **THEN** he is
  absent from `league_jp`
- *Verifies:* `test_the_snapshot_carries_every_squads_projected_eleven`,
  `test_a_failed_league_read_still_writes_our_own_projection`,
  `test_the_snapshot_carries_jornada_perfectas_number_for_every_player`,
  `test_a_failed_league_jp_read_still_writes_our_own_projection`,
  `test_league_jp_keeps_every_projected_player_by_string_id`,
  `test_league_jp_leaves_out_a_player_jp_does_not_project`

### Requirement: One finished round is collected per run, oldest first, and never early

`next_round_to_collect` SHALL pick the oldest stored round Biwenger reports as
finished that has no `actual` key; the key's presence decides, not its
contents. A round Biwenger has not finished SHALL NOT be collected: under
*jornada única* it is not final until every match is played.

#### Scenario: the queue
- **WHEN** several rounds are pending **THEN** the oldest is next
- **WHEN** a pending round is not finished **THEN** nothing is collected
- **WHEN** nothing is pending **THEN** the answer is `None`, not an error
- *Verifies:* `test_the_oldest_round_without_an_outcome_is_next`,
  `test_a_round_biwenger_has_not_finished_is_not_collected`,
  `test_nothing_to_collect_is_not_an_error`

### Requirement: An outcome is the whole squad's real points, and a missing report refuses it

The outcome SHALL hold the league's own points (`personalizado`, rebuilt from
raw stats) for **the whole squad**, the eleven fielded with its captain, the
eleven's total with the captain doubled, and what every manager scored
(`league_points`; one who fielded nothing is left out, not zeroed). If any
fielded player has no report for the round, the round SHALL be refused rather
than stored short: no report scores zero, the same number as a dreadful
afternoon.

#### Scenario: what is stored, and what refuses it
- **WHEN** a round is collected **THEN** bench players are scored too and
  the eleven's total doubles the captain
- **WHEN** a fielded player has no report **THEN** he is reported missing,
  while a real zero is not
- **WHEN** a keeper scores or assists **THEN** it is paid once, at its value
- *Verifies:* `test_a_finished_round_scores_the_whole_squad_not_only_the_eleven`,
  `test_xi_real_points_sums_and_doubles_the_captain`,
  `test_xi_real_points_treats_a_player_with_no_data_as_zero`,
  `test_extract_applied_lineup_finds_the_manager_by_id`,
  `test_extract_applied_lineup_drops_null_bench_slots`,
  `test_extract_applied_lineup_is_none_for_an_unknown_manager`,
  `test_the_league_round_is_read_for_every_manager_who_played`,
  `test_reports_for_round_keeps_only_the_matching_matchday`,
  `test_reports_for_round_is_empty_when_the_player_did_not_feature`,
  `test_reports_for_round_tolerates_a_report_with_no_round_at_all`,
  `test_personalizado_still_lives_here_and_still_scores_a_clean_sheet`,
  `test_a_fielded_player_with_no_report_is_not_a_zero`,
  `test_a_real_zero_is_not_reported_missing`,
  `test_a_player_whose_round_has_no_reports_is_missing_not_zero`,
  `test_counted_reports_make_a_real_zero_legible`,
  `test_a_keeper_s_goal_is_not_paid_twice`,
  `test_a_keeper_s_assist_is_still_worth_three`,
  `test_the_bonuses_are_counted_apart_from_the_base`

### Requirement: A matchday split across round ids is collected as one

Every round id whose name, before " (", matches another's SHALL be one
matchday (`matchday_ids`; a round the season does not list, or lists with no
name, is its own). A round SHALL be collected only once every id of its
matchday is finished. Each player SHALL be scored from his reports under any
id of the matchday. When another round of the same matchday already holds a
real outcome, the round SHALL be stored as `covered_by` it — no read, no
points — so the matchday is never graded or ranked twice, and a projection
captured for an id Biwenger never applied a lineup to is never graded.

#### Scenario: J6, split three ways
- **WHEN** a postponed round is named after J6 **THEN** it belongs to J6's
  matchday, with every other id named alike
- **WHEN** any part of a matchday is unfinished **THEN** none of it is
  collected
- **WHEN** a fielded player's game was filed under the sibling id **THEN**
  he is scored from that report, not missing and not zero
- **WHEN** the matchday already has an outcome under another id **THEN** the
  round is stored as covered by it, with no player read
- *Verifies:* `test_a_postponed_round_belongs_to_its_matchday`,
  `test_a_round_the_season_does_not_list_is_its_own_matchday`,
  `test_a_matchday_is_finished_only_when_every_part_is`,
  `test_a_matchday_split_across_round_ids_reads_every_one`,
  `test_a_player_whose_game_was_postponed_is_scored_from_the_sibling_round`,
  `test_a_sibling_of_a_collected_matchday_is_covered_without_a_read`,
  `test_a_matchday_with_a_game_still_to_play_is_not_collected`,
  `test_a_collected_matchday_reads_every_part_of_it`

### Requirement: A refusal still standing a week after the capture is final

A round refused for missing reports SHALL be retried on later mornings, since
Biwenger can file a report a day or two late. Once the snapshot's
`captured_at` is at least `REFUSAL_FINAL_AFTER` (7 days) old, the refusal
SHALL be stored as the round's outcome: the reason, the ids with no report and
when — and **no points of any kind**, so no zero is ever stored for a fielded
player. Its presence keeps the round from being chosen again; grading and the
league ranking ignore it. A snapshot with no readable capture date SHALL be
retried, never given up on.

Retried for ever, such a round re-read about twenty players a day from the
window shared with the phone app.

Every run SHALL log what the capture and the collection did ("Projection
ledger ran.", results in `extra`), so a round that never collects is visible.

#### Scenario: given up after a week, retried before
- **WHEN** a refusal's capture is a week old **THEN** the refusal is stored
  with who was missing and no points, and the round is never read again
- **WHEN** the capture is recent, or its date unreadable **THEN** nothing is
  written and the round is retried the next morning
- **WHEN** a round holds a refused outcome **THEN** it is neither collected,
  graded nor ranked, and it survives the store's round trip unchanged
- *Verifies:* `test_a_refusal_is_final_once_the_capture_is_a_week_old`,
  `test_a_recent_refusal_is_retried`,
  `test_a_round_with_no_capture_date_is_retried`,
  `test_a_refused_outcome_names_who_was_missing_and_scores_nobody`,
  `test_a_refused_round_is_not_collected_again`,
  `test_a_refused_round_is_neither_graded_nor_ranked`,
  `test_a_round_refused_for_a_week_is_marked_and_never_read_again`,
  `test_a_fresh_refusal_writes_nothing_and_is_retried_tomorrow`,
  `test_a_refused_outcome_round_trips_unchanged`

### Requirement: Only rounds where the elevens differed are evidence, and a verdict needs enough of them

`grade` SHALL count only rounds with a projection, an outcome and two elevens
that differed. Rounds stored by the daily capture SHALL be scored from their
per-player points, and only when every player of both elevens has them. Below
`MIN_ROUNDS_FOR_VERDICT` differing rounds there SHALL be no verdict.

#### Scenario: what counts
- **WHEN** the elevens agreed, the outcome is missing or the round was
  backfilled **THEN** it is not compared
- **WHEN** a captured round has every player's points **THEN** both elevens
  are scored from them; when one is missing **THEN** it is not graded
- **WHEN** fewer than the threshold differ **THEN** there is no verdict and
  the shortfall is reported; at the threshold **THEN** a verdict appears
- *Verifies:* `test_rounds_where_the_elevens_agreed_are_not_evidence`,
  `test_a_round_with_no_outcome_yet_is_not_counted`,
  `test_a_backfilled_round_never_counts`,
  `test_a_round_stored_by_the_daily_capture_is_graded_from_its_player_points`,
  `test_a_round_missing_the_points_of_an_eleven_player_is_not_graded`,
  `test_too_few_disagreements_refuses_a_verdict`,
  `test_a_verdict_appears_once_there_is_enough_to_read`

### Requirement: The league ranking sets each squad's projected rank against its real one

`league_ranking` SHALL rank every squad by projected eleven and by real
points, side by side, and SHALL be empty unless a round holds both halves.

#### Scenario: projected second, finished last
- **WHEN** a round holds both halves **THEN** each squad carries both ranks
- **WHEN** either half is missing **THEN** the ranking is empty
- *Verifies:* `test_each_squads_projected_rank_is_set_against_its_real_rank`,
  `test_a_round_without_both_halves_has_no_league_ranking`

### Requirement: One document per season and round, outcomes merged in

The store SHALL key documents by season and round, overwrite a projection for
the same key, set an outcome on an existing projection **replacing any earlier
outcome whole** (Firestore's `merge=True` merges nested maps, which once kept
old points beside a new `covered_by`), mark a backfilled outcome as having no
projection, and round-trip per-player points as integer keys.

#### Scenario: the store
- *Verifies:* `test_doc_id_keys_by_season_and_round`,
  `test_write_overwrites_last_seasons_snapshot_for_the_same_round`,
  `test_read_returns_none_for_a_round_never_written`,
  `test_write_actual_merges_into_an_existing_projection`,
  `test_write_backfill_marks_the_record_as_having_no_projection`,
  `test_list_all_reads_every_round_in_the_collection`,
  `test_player_points_survive_the_round_trip_as_integers`,
  `test_a_document_without_player_points_is_left_alone`,
  `test_a_rewritten_outcome_keeps_nothing_of_the_old_one`

### Requirement: The opponent effect compares each player with himself

`opponent_effect` SHALL measure each appearance against a given opponent as
the player's points minus **his own mean in his other games**, those games
excluding every watched opponent (`WATCHED`: Barcelona, Real Madrid), and
SHALL leave out a player with fewer than `MIN_OTHER_GAMES` other games. Games
SHALL be counted once however many round ids list them. It SHALL also
aggregate per team and game, since one heavy defeat sinks a whole back line,
and, on rounds whose snapshot holds `league_jp`, set Jornada Perfecta's
projection delta beside the real one over the same baseline rounds.

No threshold or verdict: it is read, not acted on, until a rule is proposed in
`openspec/changes/`.

#### Scenario: the measurement
- **WHEN** a game appears under three round ids **THEN** it counts once
- **WHEN** a defender scored −7 against Barcelona and 5 on average elsewhere
  **THEN** the delta is −12, whatever he scored against Madrid
- **WHEN** a player has too few other games, or another position **THEN** he
  is left out
- **WHEN** deltas are summarised **THEN** the count below their own mean is
  given; per game, one team's appearances are averaged together
- **WHEN** a round has no `league_jp` **THEN** it is not used for the
  projection comparison
- *Verifies:* `test_each_side_of_a_game_faces_the_other`,
  `test_a_game_listed_under_two_round_ids_counts_once`,
  `test_an_unfinished_game_and_a_report_without_points_are_left_out`,
  `test_a_delta_is_against_the_players_own_mean_elsewhere`,
  `test_the_baseline_leaves_out_every_watched_opponent`,
  `test_a_player_with_too_few_other_games_has_no_baseline`,
  `test_only_the_asked_positions_are_measured`,
  `test_summary_counts_how_many_fell_below_their_own_mean`,
  `test_an_empty_sample_has_no_summary`,
  `test_by_match_groups_one_teams_defence_in_one_game`,
  `test_jp_and_real_deltas_are_measured_on_the_same_rounds`,
  `test_a_round_without_a_league_jp_capture_is_not_used`

### Requirement: The squad gap splits a round into base and bonuses

`squad_gap` SHALL rebuild a manager's round from his applied lineup, each
starter who did not play replaced by the reserve of his line (`RESERVE_LINES`:
keeper, defender, midfielder, forward) when that reserve played, and the
captain counted twice, bonuses included. It SHALL split the round's points
into the SofaScore base, the play bonus, win minus loss, the clean-sheet bonus
by position, and the rest, which sum back to the points. It SHALL count wins
and losses per player, never the captain twice, and give the points of the
round's two best contributions. Summaries SHALL rank managers per round, since
a manager-round with an unread player is left out rather than scored.

No threshold or verdict: it is the evidence `openspec/changes/squad-composition/`
reads.

#### Scenario: the rebuild
- **WHEN** a starter did not play **THEN** the reserve of his line counts, if
  he played; an empty slot counts nobody
- **WHEN** the captain did not play **THEN** nothing is doubled
- **WHEN** a round is split **THEN** base, play, result, clean sheet and the
  rest add up to its points, and wins and losses count each player once
- **WHEN** managers are summarised **THEN** they rank by points per round
- *Verifies:* `test_a_starter_who_did_not_play_is_replaced_by_the_reserve_of_his_line`,
  `test_a_reserve_who_did_not_play_replaces_nobody`,
  `test_an_empty_slot_in_the_eleven_counts_nobody`,
  `test_the_total_splits_into_base_play_result_clean_sheet_and_the_rest`,
  `test_wins_and_losses_count_players_not_the_captain_twice`,
  `test_a_captain_who_did_not_play_doubles_nothing`,
  `test_top_two_is_the_share_of_the_round_from_its_two_best_players`,
  `test_summary_adds_each_managers_rounds_and_ranks_by_points_per_round`
