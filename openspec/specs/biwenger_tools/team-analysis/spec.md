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
