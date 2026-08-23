# Capability: team-analysis

The `/analizar` surface: render squad tables as Telegram images — one manager or
all managers plus the market — resilient to per-image delivery failures.

- **Source:** `packages/biwenger_tools/api/logic/actions.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_actions.py`,
  `test_routes.py`

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
- **How well is he projected?** (`sf_band`) — a single violet hue stepped
  dark→light, brightness rising with the projection. Violet rather than green
  because green is ΔE 4.1 from the reserved red under deuteranopia and both
  appear in this table.
- **Can I count on him starting?** (`is_bench`) — amber, plus a marker glyph
  (`●` certain starter, `○` not certain, `✕` out) in its own leading column.
  Both ways a fit player fails to start SHALL mark the same: JP leaving him
  out of its projected eleven, and JP listing him as a `doubt`. The "Juega"
  column carries which of the two it is ("suplente" / "duda"); the marker
  answers the coarser question a reader asks first. Reserved: amber SHALL NOT
  appear in the projection ramp or the status hues.

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
  `test_bench_count_covers_both_ways_of_not_starting`

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
