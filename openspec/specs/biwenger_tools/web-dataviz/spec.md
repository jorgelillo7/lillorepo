# Capability: web-dataviz

The public Flask site on Cloud Run that visualises league data: season-scoped
content pages, palmarés, the market/justice table, the competitions page, a
season-agnostic calendar, and a CSRF- and rate-limit-protected admin surface.

- **Source:** `packages/biwenger_tools/web/routes/` (`main.py`, `admin.py`,
  `season.py`), `app.py`, plus the pure readers `h2h.py` and
  `competiciones.py`
- **Verified by:** `packages/biwenger_tools/web/tests/test_web_app.py`,
  `test_h2h.py`, `test_competiciones.py`, `core/tests/test_gcp_services.py`

---

### Requirement: Season routing

The root SHALL redirect to the current season, and a `before_request` hook
SHALL resolve the active season from the URL, ignoring malformed season
segments rather than erroring.

#### Scenario: redirect and resolution
- **WHEN** `/` is requested **THEN** it redirects to the current season
- **WHEN** the URL season segment is invalid **THEN** it is ignored, not fatal
- *Verifies:* `test_home_redirects_to_current_season`,
  `test_before_request_manages_season`, `test_before_request_ignores_invalid_url`

### Requirement: Content views degrade, never 500 blindly

Content pages (comunicados, salseo, participación, mercado) SHALL render from
Firestore/repository data, computing derived counts, and SHALL handle upstream
failures gracefully (a data-source exception renders an error state, not a raw
stack trace). The mercado page SHALL render a valid empty state when there is
no data.

#### Scenario: success and failure paths
- **WHEN** data is present **THEN** counts render (participación, comunicados,
  mercado)
- **WHEN** the data source raises **THEN** an error state renders
- **WHEN** the mercado has no data **THEN** an empty state renders
- *Verifies:* `test_comunicados_success`, `test_comunicados_general_exception`,
  `test_participacion_renders_calculated_counts`, `test_mercado_success`,
  `test_mercado_no_data`

### Requirement: Palmarés rules

The palmarés SHALL render multas with the farolillo (last place) marker and
special-tournament slots, and SHALL only show special cups from season 25-26
onward (earlier seasons had none).

#### Scenario: markers and season gating
- **WHEN** rendering the palmarés
- **THEN** the farolillo marker and special slots appear; special cups are
  hidden for seasons before 25-26
- *Verifies:* `test_palmares_renders_multas_with_farolillo_marker`,
  `test_palmares_renders_special_tournament_slots`,
  `test_palmares_skips_special_cups_before_25_26`

### Requirement: the sheet describes the competitions, not the config

The competitions page SHALL build its tab strip from the tabs of the
spreadsheets a season points at, classifying each tab by its own shape: a
`Jornada | Partido` header row is the Liga H2H fixture block, and `Nombre de
la liga` in A1 is a table competition. A tab in neither format, or one with no
data rows yet, SHALL be named on the page — never dropped in silence.

Configuration SHALL hold one entry per season, listing spreadsheet ids
separated by `;`, so a season may span several workbooks without a code
change. The separator is not a comma because `gcloud run deploy
--set-env-vars` splits its own argument on commas, and one inside a value
fails the deploy before the app starts. Adding, renaming or
retiring a competition SHALL therefore require no code, no secret and no
deploy: a sheet id per competition per season is what left these pages empty
for a year.

A season whose sheets hold nothing SHALL say so rather than render empty
panels, and the page's former `/{season}/lloros-awards` address SHALL redirect
to it permanently.

#### Scenario: tabs come from the workbook
- **WHEN** a workbook holds an H2H tab and a cup tab **THEN** both render as
  tabs, labelled from the sheet rather than the tab name
- **WHEN** a season lists two workbooks **THEN** their tabs concatenate
- **WHEN** a tab matches neither format, or has no rows **THEN** it is
  reported on the page
- **WHEN** the season has no workbook **THEN** the page states there are no
  competitions registered
- *Verifies:* `test_competiciones_renders_every_tab_from_one_read`,
  `test_a_season_can_span_several_workbooks`,
  `test_a_season_only_shows_the_competitions_its_sheet_holds`,
  `test_the_h2h_tab_is_found_by_its_header_not_its_name`,
  `test_a_tab_in_neither_format_is_reported_not_dropped`,
  `test_a_table_tab_with_no_data_rows_yet_is_reported`,
  `test_the_tab_takes_its_label_from_the_sheet_not_the_tab_name`,
  `test_workbooks_concatenate_in_order`, `test_a_second_h2h_tab_is_refused`,
  `test_the_old_awards_url_still_resolves`,
  `test_sheet_ids_split_on_semicolons_and_commas`

### Requirement: a group stage is several tables in one tab

A tab SHALL be split into sections wherever a row repeats the header's labels;
that row's column A is the section title. A tab with a single section SHALL
keep column A's label as a normal column header.

Reading only the first header rendered the second group's header row as if it
were a competitor — the 25-26 Copa Santa Claus stacks `GRUPO A` and `GRUPO B`
in one tab.

#### Scenario: groups and plain tables
- **WHEN** a tab repeats its header row **THEN** each repeat opens a titled
  section and no group name lands in a data row
- **WHEN** a tab has one table **THEN** it has no section title and keeps its
  first column header
- **WHEN** a data row is shorter than the header **THEN** it survives as sent
- *Verifies:* `test_a_group_stage_splits_into_one_section_per_group`,
  `test_a_group_stage_renders_one_table_per_group`,
  `test_a_single_table_keeps_its_first_column_header`,
  `test_ragged_rows_survive`

### Requirement: one read serves the whole page

A season's workbooks SHALL be read once per cache window and every tab
rendered server-side, so switching tabs costs no request. The read SHALL take
two API calls per workbook regardless of tab count. The admin panel SHALL be
able to flush the cache so a freshly typed score can be seen without waiting
for the TTL.

#### Scenario: one fetch, cached
- **WHEN** the page is requested **THEN** each workbook is read once and every
  tab is present in the response
- **WHEN** two visits fall inside the TTL **THEN** the workbook is read once,
  and the admin flush makes the next visit read again
- *Verifies:* `test_competiciones_renders_every_tab_from_one_read`,
  `test_competiciones_read_is_cached_between_requests`,
  `test_get_workbook_reads_every_tab_in_two_calls`,
  `test_get_workbook_returns_empty_tabs_as_empty`,
  `test_get_workbook_with_no_tabs_makes_no_values_call`,
  `test_refresh_competiciones_requires_login`

### Requirement: Liga H2H is derived, not transcribed

The Liga H2H tab SHALL render the competition from the reglamento's own rules
rather than from the organiser's spreadsheet totals. The 35-matchday calendar
SHALL come from `constants.H2H_ROUNDS` (art. 3.1); the spreadsheet SHALL
contribute only the two scores per duel. The site SHALL award 3 points for a
win and 1 for a draw, SHALL treat a gap of **five points or fewer as a draw**
(art. 3.3), and SHALL count a duel as played only when **both** scores are
present. The classification SHALL be ordered by points, then goal difference,
then wins (art. 3.4); a tie surviving those three SHALL be marked as
unresolved rather than given an invented rank, because the next criterion —
the season's total Liga Regular score — is not in the spreadsheet.

A spreadsheet row naming a pairing the calendar does not have SHALL have its
scores discarded and the mismatch reported, never silently applied to a
different duel.

#### Scenario: scoring and tiebreaks
- **WHEN** two presidents finish five points apart **THEN** it is a draw; six
  apart is a win
- **WHEN** only one score of a duel is filled in **THEN** the duel has not
  been played and neither president's record moves
- **WHEN** two presidents are level on points, difference and wins **THEN**
  both are flagged as an unresolved tie
- *Verifies:* `test_draw_at_exactly_five_points_difference`,
  `test_match_unplayed_when_one_score_missing`,
  `test_win_scores_three_and_draw_one`,
  `test_tiebreak_falls_back_to_victories`,
  `test_unbreakable_tie_is_flagged_not_invented`

#### Scenario: the sheet disagrees with the calendar
- **WHEN** a row names a pairing the calendar does not have, or repeats one
- **THEN** those scores are dropped and the page names the offending row
- *Verifies:* `test_unknown_fixture_in_sheet_is_reported_not_rendered`,
  `test_duplicate_row_is_reported`, `test_scores_follow_the_pairing_not_the_column_order`

### Requirement: a failed read serves the last good one

When a season's workbooks cannot be read, the page SHALL serve the last
successful read past its TTL, with a banner saying the figures may be behind.
It SHALL NOT synthesise content: building a calendar from `H2H_ROUNDS` on
failure gives an H2H tab to a season that never played the competition, and on
a past season it would be the current roster's fixtures. With nothing cached
the page SHALL say it cannot read the data rather than render an empty one —
the Sheets credential was dead for a whole season and every page it fed went
quietly blank.

#### Scenario: outage
- **WHEN** a read fails and a previous one succeeded **THEN** that data is
  served with a staleness banner
- **WHEN** a read fails for a season that never played the H2H **THEN** no H2H
  tab appears
- *Verifies:* `test_a_failed_refresh_serves_the_last_good_read`,
  `test_a_failed_read_never_invents_an_h2h_tab`

### Requirement: Admin surface is authenticated, rate-limited, CSRF-safe

Admin login SHALL accept correct credentials, reject wrong ones, rate-limit
after a burst of attempts, and reject POSTs without a valid CSRF token. The
admin panel SHALL require a session; logout SHALL clear it. The run-scraper
action SHALL trigger the Cloud Run Job, redirect on success, flash on failure,
require login, and require CSRF.

#### Scenario: login protections
- **WHEN** credentials are wrong / a burst is sent / CSRF is missing
- **THEN** login fails / is rate-limited / is rejected
- *Verifies:* `test_admin_login_post_success`, `test_admin_login_post_fail`,
  `test_admin_login_rate_limited_after_burst`,
  `test_admin_login_post_rejected_without_csrf`, `test_logout_clears_session`

#### Scenario: run-scraper guarded
- **WHEN** triggering the scraper job
- **THEN** it runs and redirects; failure flashes; login and CSRF are required
- *Verifies:* `test_run_scraper_triggers_job_and_redirects`,
  `test_run_scraper_shows_error_flash_on_failure`,
  `test_run_scraper_requires_login`, `test_run_scraper_rejected_without_csrf`

### Requirement: Season-agnostic calendar

The calendar SHALL render events from a cached `.ics` feed, expanding recurring
events, support month navigation (404 on an invalid month), embed event detail
for a click modal, colour events by category, and hide the filter bar when only
one category is present. A network failure fetching the feed SHALL render an
empty grid, never crash.

#### Scenario: rendering, recurrence, resilience, filtering
- **WHEN** the feed loads **THEN** the current month's events (incl. expanded
  recurring) render, coloured by category, with detail embedded for the modal
- **WHEN** navigating months **THEN** the requested month renders; an invalid
  month is a 404
- **WHEN** the feed fetch fails **THEN** an empty grid renders
- **WHEN** only one category is present **THEN** the filter bar is hidden
- *Verifies:* `test_calendario_shows_current_month_event`,
  `test_calendario_expands_recurring_event`,
  `test_calendario_network_failure_renders_empty_grid`,
  `test_calendario_navigates_to_requested_month`,
  `test_calendario_invalid_month_returns_404`,
  `test_calendario_event_detail_data_is_embedded_for_the_click_modal`,
  `test_calendario_colours_events_by_category`,
  `test_calendario_hides_filter_bar_for_a_single_category`
