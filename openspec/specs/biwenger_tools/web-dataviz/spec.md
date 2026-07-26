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

The Lloros Awards endpoints SHALL return data read from Google Sheets, and
SHALL return an empty result (not an error) when no sheet is configured.

#### Scenario: configured vs unconfigured
- **WHEN** a sheet is configured **THEN** its ligas/trofeos data is returned
- **WHEN** none is configured **THEN** an empty result is returned
- *Verifies:* `test_api_lloros_ligas_returns_sheets_data`,
  `test_api_lloros_ligas_returns_empty_when_no_sheet_configured`,
  `test_api_lloros_trofeos_returns_sheets_data`

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
