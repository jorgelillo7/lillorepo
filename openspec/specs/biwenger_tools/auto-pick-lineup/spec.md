# Capability: auto-pick-lineup

Pick the captain for the starting XI and render the lineup message, using
cf-base player values.

- **Source:** `packages/biwenger_tools/api/logic/lineup.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_lineup.py`

---

### Requirement: Captain by highest SF under the 3M price cap

`_pick_captain` SHALL choose the starter with the highest SF whose price is
**strictly below 3M** (`_CAPTAIN_MAX_PRICE = 3_000_000`) — Biwenger returns
HTTP 403 *"Captain over max MV: X > 3000000"* for any captain priced ≥ 3M. The
cap applies to the **cf.biwenger.com base price** (`row["price"]`), NOT the
per-league `owner.price`, which can be much lower — a player who looks cheap in
your league can still be rejected on his cf-base value. Starters with an
unknown (0) price are excluded — never gamble the captaincy on a market value
we can't see. When no starter qualifies it SHALL return `None` (caller PUTs
`captain=0`).

#### Scenario: cap, strictness, unknown price
- **WHEN** several starters qualify **THEN** the highest-SF under 3M wins
- **WHEN** a starter sits exactly at 3M **THEN** it is excluded (strict `<`)
- **WHEN** every starter is over the cap, or all prices are unknown
- **THEN** the result is `None`
- **WHEN** a price-0 starter has the highest SF but known options exist
- **THEN** it does not win
- *Verifies:* `test_pick_captain_picks_highest_sf_under_cap`,
  `test_pick_captain_cap_is_strict`,
  `test_pick_captain_returns_none_when_every_starter_over_cap`,
  `test_pick_captain_returns_none_when_all_prices_unknown`,
  `test_pick_captain_ignores_unknown_price_when_known_options_exist`

### Requirement: Message rendering

`format_lineup_message` SHALL render the lineup, omitting the © captain marker
and showing a no-captain warning when no captain was picked.

#### Scenario: no captain
- **WHEN** captain is `None`
- **THEN** the message omits © and shows the warning
- *Verifies:* `test_format_lineup_message_renders_no_captain_warning`

### Requirement: cf-base pricing

`build_squad_rows` SHALL keep `row["price"]` as the cf.biwenger.com base price,
ignoring any `owner` price block (present or absent) — the same value auto-bid
and offers reason over.

#### Scenario: price source
- **WHEN** a squad entry has, or lacks, an `owner` block
- **THEN** `row["price"]` stays the cf-base price
- *Verifies:* `test_build_squad_rows_keeps_cf_base_price_ignoring_owner`,
  `test_build_squad_rows_keeps_cf_base_price_without_owner`
