# Capability: team-analysis

The `/analizar` surface: render squad tables as Telegram images — one manager or
all managers plus the market — resilient to per-image delivery failures.

- **Source:** `packages/biwenger_tools/api/logic/actions.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_actions.py`,
  `test_routes.py`, `test_image_formatter.py`

> Coverage note: `actions.py` line coverage is ~32%; the multi-image resilience
> path is unit-tested, the rest goes through route tests. A candidate for the
> test-hardening pass.

---

### Requirement: Scope by manager

`run_teams` SHALL, with no manager, render every manager's squad image plus the
market image; with a manager id, render that single squad and no market.
`manager=all` SHALL alias the no-filter (all + market) mode, and a non-integer
manager SHALL be rejected (400) upfront. `list_managers` SHALL expose the
manager list for the bot's picker.

#### Scenario: routing by manager param
- **WHEN** `/teams` has no manager (or `manager=all`) **THEN** all squads +
  market are rendered
- **WHEN** `manager=<id>` **THEN** only that squad, no market
- **WHEN** `manager` is not an integer **THEN** 400
- **WHEN** the picker asks **THEN** the manager list is returned
- *Verifies:* `test_teams_without_manager_calls_run_teams_with_none`,
  `test_teams_with_manager_id_filters`,
  `test_teams_with_manager_all_is_alias_for_no_filter`,
  `test_teams_with_invalid_manager_returns_400`, `test_managers_endpoint`,
  `test_market_calls_run_market`

### Requirement: The table encodes three independent facts, in three channels

Every squad and market image is rendered by `build_table_image` on a dark
surface. Three questions are asked of each player, and each SHALL keep its own
visual channel — collapsing any two is what has repeatedly made the table say
something untrue about a player:

- **Can he be fielded?** (`availability`) — the reserved status hues. A player
  JP leaves out of its projected eleven is **available**, and SHALL keep
  counting toward "N juegan".
- **How well is he projected?** (`band_for_score`) — a single violet hue
  stepped dark→light, brightness rising with the projection. Violet rather
  than green because green is ΔE 4.1 from the reserved red under deuteranopia
  and both appear in this table. The band SHALL be read off the number on
  screen, not the source rate behind it (see "Order and colour").
- **Can I count on him starting?** (`is_bench`) — amber, plus a marker glyph
  (`●` certain starter, `○` not certain, `✕` out) in its own leading column.
  Both ways a fit player fails to start SHALL mark the same: JP leaving him
  out of its projected eleven, and JP listing him as a `doubt`. The "Juega"
  column carries which of the two it is ("suplente" / "duda"); the marker
  answers the coarser question a reader asks first. Reserved: amber SHALL NOT
  appear in the projection ramp or the status hues.

Every image SHALL carry the instant it was generated, bottom-right below the
last row, in muted ink at a smaller size than any body cell. These arrive as
photos in a chat and outlive the morning they describe: scrolled back to a
week later, an undated squad table is indistinguishable from today's. The
corner is chosen because the table grows downward and its rightmost column
holds the shortest text, so nothing is displaced.

The canvas SHALL widen in proportion to what the extra columns weigh. Column
widths are normalised over their total, so every column added shrinks all the
others; a flat per-column allowance let the clause view come out **narrower per
column** than the plain one, and unreadable when zoomed. Rendering SHALL be at
`_DPI` ≥ 200 — these are read on a phone by zooming in on one row of fifteen.

Every body cell SHALL be given an explicit ink — matplotlib defaults to black,
which is invisible on the dark surface for any column no other rule recolours.

Availability outranks the bench in both the marker and the row tint: an injured
substitute is *out*, and two marks for one player is how a reader stops trusting
the column. Markers SHALL be BMP glyphs — `_strip_emoji` exists because
matplotlib renders anything above the BMP as a dotted-circle placeholder.

#### Scenario: substitutes are findable at a glance
- **WHEN** a squad holds starters, substitutes and an injured player
- **THEN** each carries its own marker, the substitutes are amber in the marker,
  name and reason columns, and the header line counts them separately
- *Verifies:* `test_mark_distinguishes_starter_bench_and_out`,
  `test_an_injured_substitute_reads_as_out_not_as_bench`,
  `test_bench_row_gets_its_own_tint`,
  `test_bench_amber_is_not_reused_by_any_other_channel`,
  `test_markers_survive_the_emoji_stripper`,
  `test_build_table_image_renders_a_squad_with_substitutes`,
  `test_a_doubt_is_not_marked_as_a_certain_starter`,
  `test_a_doubt_still_counts_among_the_players_who_can_play`,
  `test_bench_count_covers_both_ways_of_not_starting`,
  `test_the_image_is_stamped_with_when_it_was_made`,
  `test_extra_columns_widen_the_canvas_instead_of_squeezing_the_others`,
  `test_the_render_is_dense_enough_to_zoom_into`

### Requirement: The projection is one number, and the table shows what made it

`Proyección` SHALL carry a single number per player — the one every other
reader sorts, colours and bids on — and the table SHALL place the two readings
behind it alongside, in a `JP` and an `Oráculo` column. A blend nobody can take
apart is a blend nobody trusts: the two columns make a disagreement between the
sources visible at the moment it moves the number.

Jornada Perfecta is the base and Oráculo the second opinion, in that order.
Where the blend ran, `Proyección` SHALL show it; where it did not, the raw JP
rate. A missing second opinion costs precision, never the row.

`Oráculo` SHALL distinguish *no opinion* from *an opinion of zero*: a player it
never rated renders `—`, a player it rates at zero renders the number. Collapsing
the two would read as a provider that covers everybody and thinks a third of the
league unplayable.

Shortlist membership SHALL render as stars beside that number, one per
qualifying list, capped at three so the bonus cannot outweigh the blend and so
the count stays legible without a legend. `chollos` and `capitanes` SHALL NOT
earn a star — the first ranks by price, which is not a question the projection
asks, and the second is already answered by the projection itself.

The reach is deliberate and was checked against a live read: 8 lists, 60 slots,
41 distinct players in the whole division. Stars are a Yamal/Raphinha/Fermín
phenomenon — common in the market and rival images, rare in the owner's own.
That is the intent. The bonus values the *player*, not its holder: a rival's
starred Yamal is the table saying what his clause costs.

#### Scenario: both readings, and the difference between nothing and zero
- **WHEN** a player carries a projection from both sources **THEN** each appears
  in its own column and `Proyección` shows the blend
- **WHEN** Oráculo never rated him **THEN** the cell reads `—`; **WHEN** it rates
  him zero **THEN** the cell reads the number
- **WHEN** he appears on qualifying lists **THEN** one star per list, three at most,
  and `chollos` / `capitanes` add none
- *Verifies:* `test_a_matched_player_carries_the_oraculo_numbers`,
  `test_an_unmatched_player_is_marked_not_zeroed`,
  `test_a_zero_projection_is_an_opinion_not_a_gap`,
  `test_an_unmatched_row_renders_an_em_dash_in_the_oraculo_column`,
  `test_a_matched_row_with_no_points_also_renders_an_em_dash`,
  `test_a_zero_projection_is_shown_as_a_real_number`,
  `test_jp_cell_is_an_em_dash_with_no_jp_data`,
  `test_stars_count_qualifying_lists_only`,
  `test_the_lists_a_player_appears_on_ride_along`,
  `test_lists_are_sorted_so_the_stars_are_stable`,
  `test_build_squad_rows_forwards_the_oraculo_index`,
  `test_build_market_rows_forwards_the_oraculo_index`

### Requirement: The photo says when it is running on Jornada Perfecta alone

The blend SHALL be all-or-nothing across a table. Below `ORACULO_MIN_COVERAGE`
every row SHALL fall back to its raw JP rate, and the image SHALL declare it —
the `Proyección` header is marked and the title takes a suffix.

Half a blend is worse than none. Midweek the second opinion covers a handful of
players, and blending only those pushes three names above the rest for no reason
beyond Oráculo having looked at their fixture first — invisible to a reader who
has only the photo.

#### Scenario: thin coverage, and the reader is told
- **WHEN** coverage is below the floor **THEN** every row shows its JP rate, the
  header is marked and the title takes its suffix
- **WHEN** coverage is sufficient **THEN** neither mark appears
- **WHEN** a row Oráculo rated has no JP reading at all **THEN** the fallback
  still renders instead of raising
- *Verifies:* `test_blended_rows_falls_back_to_jp_when_coverage_is_thin`,
  `test_projection_header_marks_only_when_the_blend_did_not_run`,
  `test_title_takes_a_suffix_only_when_the_blend_did_not_run`,
  `test_blended_rows_never_crashes_on_a_matched_row_with_no_jp_player`,
  `test_coverage_counts_rows_with_an_opinion`,
  `test_coverage_of_nothing_is_zero_not_a_crash`

### Requirement: Order and colour follow the number on screen

The sort order and the projection's colour band SHALL both be read off the
number the row displays, never the source rate behind it.

They read the raw rate once, and the rendered column came out visibly unsorted —
`525, 536, 494, 460, 437, 472, …` — with rows shaded for a projection no longer
on screen. A table whose own column contradicts its ordering is the fastest way
to lose a reader's trust in every other column.

#### Scenario: the column the reader sees is the column the table sorted
- **WHEN** rows carry blends that reorder them against their JP rates
- **THEN** the table is sorted on the blends and each row is shaded for its own
  displayed number
- **WHEN** a row has no blend **THEN** it sorts on its JP rate
- **WHEN** it has neither **THEN** it sorts last rather than raising
- *Verifies:* `test_the_table_sorts_by_the_projection_it_displays`,
  `test_a_row_without_a_blend_sorts_on_its_jp_rate`,
  `test_the_colour_band_follows_the_blended_number`,
  `test_shown_score_is_none_when_there_is_no_projection_at_all`

### Requirement: One image failure never aborts the batch

In all-managers mode, a single Telegram photo refusal SHALL NOT skip the
remaining manager squads nor the market image. Each failure is reported per
-image via the text fallback, and the `sent` count reflects only photos that
actually landed.

#### Scenario: mid-batch photo failure
- **WHEN** the first squad photo fails but the rest succeed
- **THEN** every remaining squad and the market photo are still attempted, and
  `sent` counts only the successes
- *Verifies:* `test_run_teams_all_mode_continues_after_first_photo_fails`

---

### Requirement: A missing market never fails the run

The market SHALL be read after the squad images are already delivered, and a
failure reading or rendering it SHALL be reported in the chat without failing
the request.

Returning 5xx at that point is the worst outcome available: every squad photo
has landed, so the work succeeded and the bot still shows a bare error.

Biwenger answers a disabled market with `200` and a **null** payload, which is
not the same as an empty one — `.get("data", {})` yields `None` for a key that
is present and null, so any chained lookup raises. Payload unwrapping in the
SDK SHALL treat null and missing alike.

#### Scenario: the market is closed
- **WHEN** the market payload is null, or its sales are null **THEN** the SDK returns
  an empty list rather than raising
- **WHEN** reading the market fails during an all-managers run **THEN** the squads
  still count, a notice is posted, and the request succeeds
- *Verifies:* `test_get_market_players_when_the_market_is_disabled`,
  `test_run_teams_all_mode_survives_a_broken_market`

---

### Requirement: The league compared, on demand and to the owner alone

`POST /league/compare` SHALL rank every squad in the league by market value and
by projected points, and send the result to the owner's chat — never to the
draft group. Handing every rival the projection of their own squad gives away
the only edge the tooling provides.

The two rankings SHALL stay separate and uncombined: they answer different
questions, and merging them needs a weighting that would be invented rather
than measured. The value heading SHALL follow the data — with a cost to compare
against it reads "quién compró mejor", without one "equipo más caro", because a
month into the season half a squad arrived by clause and nobody remembers what
it cost.

It SHALL be on demand rather than chained into the daily digest: the value is in
reading it *while deciding whether to buy*, and a fifth message every morning is
noise. Because it costs one squad read per manager against a budget the whole
league shares, and because it hangs off a menu button, the result SHALL be
cached for a few minutes.

#### Scenario: ranking and delivery
- **WHEN** `/comparar` is invoked **THEN** both rankings are sent to the owner's chat
- **WHEN** a cost is present **THEN** the value ranking is titled "quién compró mejor"
- **WHEN** it is absent **THEN** it is titled "equipo más caro"
- **WHEN** it is invoked twice inside the cache window **THEN** Biwenger is read once
- *Verifies:* `test_league_compare_calls_the_action`,
  `test_league_compare_rejects_get`,
  `test_render_says_who_bought_best_only_when_there_is_a_cost`,
  `test_the_two_rankings_are_independent`,
  `test_the_comparison_is_cached_so_a_second_tap_costs_nothing`
