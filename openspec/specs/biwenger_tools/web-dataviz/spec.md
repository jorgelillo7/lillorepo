# Capability: web-dataviz

The public Flask site on Cloud Run that visualises league data: season-scoped
content pages, palmarés, the market/justice table, Lloros Awards, a
season-agnostic calendar, and a CSRF- and rate-limit-protected admin surface.

- **Source:** `packages/biwenger_tools/web/routes/` (`main.py`, `admin.py`,
  `season.py`), `app.py`
- **Verified by:** `packages/biwenger_tools/web/tests/test_web_app.py`

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

### Requirement: Lloros Awards from Sheets

The Lloros Awards page SHALL carry three tabs — Liga H2H, Ligas Especiales and
Trofeos. The ligas/trofeos endpoints SHALL be season-scoped in the path, SHALL
return data read from Google Sheets, and SHALL return an empty result (not an
error) when no sheet is configured for that season.

#### Scenario: configured vs unconfigured
- **WHEN** a sheet is configured for the season in the path **THEN** its
  ligas/trofeos data is returned
- **WHEN** none is configured **THEN** an empty result is returned
- *Verifies:* `test_api_lloros_ligas_returns_sheets_data`,
  `test_api_lloros_ligas_returns_empty_when_no_sheet_configured`,
  `test_api_lloros_trofeos_returns_sheets_data`

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

### Requirement: the H2H page degrades to its calendar

A season with no H2H sheet configured SHALL state that the competition was not
played, not render an error. A season whose sheet is configured but unreadable
SHALL still render the full calendar, with the scores absent and a banner
saying so — the Sheets credential died once and every page it fed simply went
blank for a season.

The H2H read SHALL be cached, and the admin panel SHALL be able to flush that
cache so a freshly typed score can be seen without waiting for the TTL.

#### Scenario: missing season, dead credential, cache
- **WHEN** the season predates the competition **THEN** the page says so
- **WHEN** the Sheets read raises **THEN** the calendar still renders with a
  banner
- **WHEN** two visits fall inside the TTL **THEN** the sheet is read once
- *Verifies:* `test_h2h_page_states_a_season_never_played_it`,
  `test_h2h_page_renders_calendar_when_sheet_unavailable`,
  `test_h2h_read_is_cached_between_requests`,
  `test_h2h_standings_render_from_the_sheet`, `test_refresh_h2h_requires_login`

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
