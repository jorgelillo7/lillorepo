# Capability: market-trader

The daily digest's trading step: sell the squad's price fallers and bid on the
market's risers, inside the owner's limits — the best eleven's starters are
never sold, an eleven that plays is always left, and on the eve of a round the
wallet may not end below zero. It rests on
one measured fact: Biwenger prices move in runs (after three days up, the next
three were up again in ~86 % of the cases sampled on 12/10), and this league
overpays little on a market buy (median +1.7 %).

**Two modes, `dry_run` by default.** `dry_run` plans and reports; `live` acts —
it lists the squad every morning (`POST /market {type: "team", price: 100}`,
in `docs/external/biwenger-api.yaml`), accepts the planned sells' offers and
places the planned bids. Listing sells nothing by itself: a player leaves only
when an offer for him is accepted. The dialog's "Venta inmediata" — 50 % of the
value in this league — is never used, and `{type: "remove"}` takes the whole
squad off the market at once. Plan: `.claude/plans/market-trader.md`.

- **Source:** `packages/biwenger_tools/api/logic/trader.py`,
  `price_history.py` (pure), `price_history_store.py`, `trader_run.py`
  (service, `_act` for `live`), `digests.py` (`_safe_run_trader`), `actions.py`
  (`read_open_rounds`); `core/sdk/biwenger.py` (`list_squad_for_sale`,
  `get_my_pending_bids`)
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

### Requirement: Sell a faller only off the bench, and only if an eleven is left

A squad player falling for `TRADER_SELL_AFTER_FALLS` days or more SHALL be sold
at today's price — longest fall first — unless he starts in the best eleven the
lineup search picks today, or the rest of the squad would no longer field a
full eleven of players the projection expects to play. Either way he is held,
and the plan says why. Good players are kept for their points; price rotation
is for the bench.

#### Scenario: fallers
- **WHEN** a player has fallen two days and the rest still field an eleven
  **THEN** he is sold at today's price
- **WHEN** he starts in the best eleven **THEN** he is held, however he falls
- **WHEN** the squad already lacks an eleven that plays **THEN** even the bench
  is held
- **WHEN** he has fallen one day **THEN** nothing happens
- **WHEN** a player is left out by the projection **THEN** he does not count
  towards the eleven
- *Verifies:*
  `test_a_player_falling_two_days_is_sold_when_the_rest_still_fields_an_eleven`,
  `test_a_starter_of_the_best_eleven_is_never_sold_however_he_falls`,
  `test_with_no_eleven_that_plays_even_the_bench_is_kept`,
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
round's first match still to be played falls today or tomorrow (Madrid). Only
rounds still `pending` start; the rest of one under way does not, and a
postponed round — `pending` with most of its games played — starts only with
the games it has left. An unreadable calendar counts as an eve.

#### Scenario: the floor
- **WHEN** no round is near **THEN** a bid may take the wallet negative down to
  the limit, and one past it is skipped
- **WHEN** a round starts tomorrow **THEN** no bid may leave the wallet below
  zero, however high the limit
- **WHEN** a sale is planned **THEN** its price pays for the day's bids
- **WHEN** a postponed round has played games and one left **THEN** only the
  one left can make a day its eve
- **WHEN** the calendar cannot be read **THEN** the day is treated as an eve
- *Verifies:*
  `test_away_from_a_round_the_wallet_may_go_negative_down_to_the_limit`,
  `test_past_the_negative_limit_the_bid_is_skipped`,
  `test_on_a_round_s_eve_nothing_may_take_the_wallet_below_zero`,
  `test_today_s_sales_pay_for_today_s_buys`,
  `test_a_round_starting_tomorrow_makes_today_its_eve`,
  `test_a_round_three_days_out_is_not_its_eve`,
  `test_the_rest_of_a_round_already_under_way_does_not_count_as_a_start`,
  `test_a_postponed_round_s_played_games_do_not_make_every_day_its_eve`,
  `test_an_unreadable_calendar_is_treated_as_an_eve`

### Requirement: Bids already waiting are spent, and never repeated

The step SHALL read the owner's waiting bids — auto-bid's of the same morning,
or a retried run's — count their amounts as spent and never bid again on a
player who has one, in both modes.

#### Scenario: a retried morning
- **WHEN** a bid is already waiting on a riser **THEN** he is not bid again,
  and the waiting amount comes off the wallet
- *Verifies:* `test_pending_bids_are_spent_already_and_never_bid_twice`,
  `test_a_retried_run_does_not_bid_again_on_a_player_it_already_bid_on`

### Requirement: Live sells first, and bids only with money received

In `live` the step SHALL, in this order: accept, for each planned sell, the best
received offer for him alone worth at least `TRADER_MIN_SALE_SHARE` of his
price; list the whole squad at `TRADER_LIST_PERCENT`; then bid on the risers
with the cash plus only the sales Biwenger settled (`status: processed`), minus
the waiting bids, down to the day's floor. An offer for anyone else, or for him
together with others, is never accepted. A planned sell with no acceptable
offer stays listed and is reported as waiting. Each mutation is attempted once;
a failed accept counts no money, a refused bid is reported and the run goes on.

#### Scenario: the live morning
- **WHEN** a faller has an offer at his price and a riser is in the market
  **THEN** the offer is accepted, the squad listed, the riser bid, in that order
- **WHEN** offers come below the floor, for a kept player, or for several
  players **THEN** none is accepted
- **WHEN** the accept fails **THEN** it was sent once and its money buys nothing
- **WHEN** a bid is refused **THEN** it was sent once and the report still goes out
- **WHEN** a planned sell has no offer **THEN** he waits, listed, and the report
  says so
- *Verifies:*
  `test_live_sells_the_faller_lists_the_squad_and_bids_on_the_riser`,
  `test_the_best_offer_at_or_near_the_price_is_taken_for_each_planned_sell`,
  `test_an_offer_below_the_floor_is_not_taken`,
  `test_an_offer_for_a_player_not_being_sold_is_never_taken`,
  `test_an_offer_for_several_players_is_never_taken`,
  `test_a_sale_biwenger_did_not_settle_buys_nothing_with_its_money`,
  `test_a_refused_bid_is_sent_once_and_the_run_carries_on`,
  `test_a_planned_sell_without_an_offer_waits_listed`

### Requirement: The plan reaches the owner, and touches nothing in dry run

After the offers inbox the digest SHALL plan on the very rows and rounds it
already read and send the plan to Telegram, marked as a simulation, naming
every sale, bid, hold and skip. With fewer days of prices than a buy signal
needs, the message SHALL say so rather than read as a quiet market. Without the
squad's rows the step stands down; a failure in it never costs the digest.

#### Scenario: the morning's trading message
- **WHEN** the mode is `dry_run` **THEN** the day is stored, the plan is sent,
  and no bid, listing or offer decision reaches Biwenger
- **WHEN** only two days are stored **THEN** the message says so
- **WHEN** the step raises **THEN** the digest still completes
- *Verifies:*
  `test_a_dry_run_stores_the_day_plans_and_reports_without_touching_biwenger`,
  `test_short_history_is_said_rather_than_read_as_a_quiet_market`,
  `test_the_report_says_it_is_a_simulation_and_names_every_move`,
  `test_the_trader_plans_on_the_rows_and_rounds_the_digest_already_read`,
  `test_a_failing_trader_never_costs_the_digest`
