# Capability: market-trader

The daily digest's trading step: sell the squad's price fallers and bid on the
market's risers, inside the owner's two limits — an eleven that plays is always
left, and on the eve of a round the wallet may not end below zero. It rests on
one measured fact: Biwenger prices move in runs (after three days up, the next
three were up again in ~86 % of the cases sampled on 12/10), and this league
overpays little on a market buy (median +1.7 %).

**Phase A (current): plans and reports only.** Nothing is listed, accepted or
bid; `TRADER_MODE=live` is read as `dry_run` until the list-for-sale endpoint is
known. Plan and phase B: `.claude/plans/market-trader.md`.

- **Source:** `packages/biwenger_tools/api/logic/trader.py`,
  `price_history.py` (pure), `price_history_store.py`, `trader_run.py`
  (service), `digests.py` (`_safe_run_trader`), `actions.py`
  (`read_open_rounds`)
- **Verified by:** `packages/biwenger_tools/api/tests/test_trader.py`,
  `test_price_history.py`, `test_price_history_store.py`,
  `test_trader_run.py`, `test_digests.py`

---

### Requirement: Every day's prices are kept for sixty days

The step SHALL store every priced player's cf-base price once a day in
`price_snapshots/{YYYY-MM-DD}`, from the players map the digest already reads,
with an `expires_at` sixty days out for the collection's TTL policy — whatever
`TRADER_MODE` is, `off` included, so switching the trader on finds history
waiting. A second write the same day replaces the first.

#### Scenario: one document a day
- **WHEN** the day is written twice **THEN** one document holds the later
  prices and an expiry sixty days after the date
- **WHEN** the last days are read **THEN** they come oldest first, keyed by
  integer player id
- **WHEN** the mode is `off` **THEN** the day is still stored and nothing else
  happens
- *Verifies:* `test_a_day_is_stored_once_under_its_date_with_an_expiry`,
  `test_recent_returns_the_last_days_oldest_first_with_integer_ids`,
  `test_off_still_keeps_the_price_history_but_plans_nothing`,
  `test_prices_keep_every_priced_player_by_id`

### Requirement: A streak is today's run, and nothing else

A player's streak SHALL be the number of consecutive daily moves in one
direction ending on the newest day — positive rising, negative falling. A flat
day, or a day the player is missing from, ends it; a gap is never bridged.

#### Scenario: reading the run
- **WHEN** a price rose on each of the last three days **THEN** the streak is 3
- **WHEN** it rose and then fell today **THEN** the streak is −1
- **WHEN** today was flat, or there is one day or none **THEN** it is 0
- **WHEN** a day is missing **THEN** only the moves after the gap count
- *Verifies:* `test_a_rise_on_each_of_the_last_three_days_is_a_streak_of_three`,
  `test_falls_count_negative`, `test_only_the_run_that_ends_today_counts`,
  `test_a_flat_day_ends_the_streak`,
  `test_a_day_without_the_player_ends_the_streak_rather_than_bridging_it`,
  `test_too_little_history_is_no_streak`

### Requirement: Sell a faller only if an eleven that plays is left

A squad player falling for `TRADER_SELL_AFTER_FALLS` days or more SHALL be sold
at today's price — longest fall first — unless the rest of the squad would no
longer field a full eleven of players the projection expects to play; then he
is held, and the plan says why.

#### Scenario: fallers
- **WHEN** a player has fallen two days and the rest still field an eleven
  **THEN** he is sold at today's price
- **WHEN** selling him leaves the eleven short **THEN** he is held
- **WHEN** he has fallen one day **THEN** nothing happens
- **WHEN** a player is left out by the projection **THEN** he does not count
  towards the eleven
- *Verifies:*
  `test_a_player_falling_two_days_is_sold_when_the_rest_still_fields_an_eleven`,
  `test_a_faller_is_kept_when_selling_him_would_leave_the_eleven_short`,
  `test_one_day_down_is_not_a_reason_to_sell`,
  `test_a_player_the_projection_leaves_out_does_not_count_towards_the_eleven`

### Requirement: Bid on a riser just over his price

A market player rising for `TRADER_BUY_AFTER_RISES` days or more, projected at
`TRADER_BUY_MIN_SF` or above and not already owned, SHALL be bid his price plus
`TRADER_BUY_MARGIN` — best projection first, never past `MAX_SQUAD_SIZE`.

#### Scenario: risers
- **WHEN** a riser of three days clears the floor **THEN** he is bid at
  price × 1.03
- **WHEN** he is projected below the floor, or has risen two days **THEN** he
  is not bid
- **WHEN** two risers compete for the wallet **THEN** the better projected wins
- **WHEN** the squad is full **THEN** nobody is bid, and the plan says so
- *Verifies:* `test_a_market_player_rising_three_days_is_bid_just_over_his_price`,
  `test_a_riser_below_the_projection_floor_is_not_bought`,
  `test_two_days_up_is_not_yet_a_trend`,
  `test_the_best_projected_riser_is_bought_first`, `test_a_full_squad_buys_nobody`

### Requirement: No negative wallet on a round's eve

Today's sales SHALL count towards today's bids. The wallet MAY end as low as
−`TRADER_NEGATIVE_LIMIT` on an ordinary day, since the whole squad is on sale
and something sells by the next morning, but SHALL NOT end below zero when a
round's first match falls today or tomorrow (Madrid). Only rounds still
`pending` start; the rest of one under way does not. An unreadable calendar
counts as an eve.

#### Scenario: the floor
- **WHEN** no round is near **THEN** a bid may take the wallet negative down to
  the limit, and one past it is skipped
- **WHEN** a round starts tomorrow **THEN** no bid may leave the wallet below
  zero, however high the limit
- **WHEN** a sale is planned **THEN** its price pays for the day's bids
- **WHEN** the calendar cannot be read **THEN** the day is treated as an eve
- *Verifies:*
  `test_away_from_a_round_the_wallet_may_go_negative_down_to_the_limit`,
  `test_past_the_negative_limit_the_bid_is_skipped`,
  `test_on_a_round_s_eve_nothing_may_take_the_wallet_below_zero`,
  `test_today_s_sales_pay_for_today_s_buys`,
  `test_a_round_starting_tomorrow_makes_today_its_eve`,
  `test_a_round_three_days_out_is_not_its_eve`,
  `test_the_rest_of_a_round_already_under_way_does_not_count_as_a_start`,
  `test_an_unreadable_calendar_is_treated_as_an_eve`

### Requirement: The plan reaches the owner, and touches nothing in phase A

After the offers inbox the digest SHALL plan on the very rows and rounds it
already read and send the plan to Telegram, marked as a simulation, naming
every sale, bid, hold and skip. With fewer days of prices than a buy signal
needs, the message SHALL say so rather than read as a quiet market. Without the
squad's rows the step stands down; a failure in it never costs the digest.

#### Scenario: the morning's trading message
- **WHEN** the mode is `dry_run` **THEN** the day is stored, the plan is sent,
  and no bid or offer decision reaches Biwenger
- **WHEN** only two days are stored **THEN** the message says so
- **WHEN** the step raises **THEN** the digest still completes
- *Verifies:*
  `test_a_dry_run_stores_the_day_plans_and_reports_without_touching_biwenger`,
  `test_short_history_is_said_rather_than_read_as_a_quiet_market`,
  `test_the_report_says_it_is_a_simulation_and_names_every_move`,
  `test_the_trader_plans_on_the_rows_and_rounds_the_digest_already_read`,
  `test_a_failing_trader_never_costs_the_digest`
