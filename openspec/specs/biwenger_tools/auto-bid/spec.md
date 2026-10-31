# Capability: auto-bid

Daily aggressive auto-bidding on the Biwenger daily market. Cloud Scheduler
posts `POST /market/auto-bid` at 09:00 Madrid. The system reads the rotating
computer-owned free agents Biwenger exposes each morning, attaches SofaScore
(SF) ratings from JP blended with Oráculo, and bids on each — best first —
until cash runs out, then reports the run to Telegram.

- **Source:** `packages/biwenger_tools/api/logic/auto_bid.py`,
  `packages/biwenger_tools/api/logic/auction_calibration.py`,
  `packages/biwenger_tools/scripts/auto_bid/calibrate.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_auto_bid.py`,
  `packages/biwenger_tools/api/tests/test_auction_calibration.py`

---

### Requirement: Tier-based bid sizing

The system SHALL size each bid from the player's SF rating using four tiers,
each bidding a flat share over Biwenger's cf-base `price` (not `owner.price`),
plus jitter.

| Tier | SF band | Bid |
|---|---|---|
| T1 | SF ≥ 700 | `price × 1.15` |
| T2 | 550 ≤ SF < 700 | `price × 1.08` |
| T3 | 400 ≤ SF < 550 | `price × 1.06` |
| T4 | 300 ≤ SF < 400 | `price × 1.05` |
| skip | SF < 300 | — |

**The shares are set from the market, not by feel.** The first calibration
(27/09, 137 auctions) set +40 / +20 / +10 / +5 % to win most auctions — it
optimised the win rate. Re-measured on 12/10 against 95 auctions with a known
price, the question became value: the managers who gain value pay a median
+0–1 % over the price, a bid of +15 % wins 77 % of the league's auctions, +8 %
65 %, +3 % 47 %; and +15 % at the top would still have won every one of our 14
wins. Under the +40 / +20 / +10 / +5 % ladder we won six, all T3/T4, paying
0.96M over the next best bid (or the price, where nobody else bid — four of the
six). The third reading (22/10, 196 priced auctions) moved only the bottom:
a bid of +0 % wins 4–12 % of the auctions under 5M and +5 % wins 68–72 %, so
most rival bids land in that gap and T4's +3 % sat inside it — two of our
losses went by 2,000–2,500 €. T3 and T4 moved to +6 % and +5 %, just above it;
T1 and T2 did not move, since the contested stars go for +19–35 % and the 19
wins still paid 7.6M over the runner-up. The earlier ladder — the whole wallet for T1, and
`min(price × 1.7 / 1.5 / 1.2, price + 5M / 2M / 500K)` below — had paid 6.36M
over the runner-up across eight wins (Valverde alone 3.24M). The trader
(`market-trader`) buys risers at +3 %, which is where squad trading now lives.

The cut-offs are set against the league as it scores, not a round number: at
800/600 only two players in LaLiga reached T1 and five reached T2, and 24
logged bids over 16 days held one T2 and no T1. At 700/550 T1 holds the
handful of genuine stars and T2 the next nine.

#### Scenario: each tier's share
- **WHEN** a T1 / T2 / T3 / T4 player is priced 26M / 14.3M / 10M / 1M with
  cash to spare
- **THEN** the bid is 29.9M / 15.444M / 10.6M / 1.05M (+ jitter)
- *Verifies:* `test_each_tier_bids_its_share_over_the_price`

### Requirement: Inclusive lower boundaries

Tier thresholds SHALL be inclusive on the lower end: a player at exactly a
tier's minimum SF lands in that tier, not the one below.

#### Scenario: SF exactly on a boundary
- **WHEN** a player has SF = 700 / 550 / 400 / 300
- **THEN** they land in T1 / T2 / T3 / T4 respectively
- **AND** SF = 299 is skipped (below the T4 floor of 300)
- *Verifies:* `test_tier_boundaries`

### Requirement: No tier bids the whole wallet

A bid that exceeds `remaining_cash` SHALL come back whole, whatever the tier,
for the caller to skip for lack of cash. No single auction is worth the whole
wallet: the market loses an auction, the squad keeps its money. T1 and T2 used
to bid the wallet when short of cash, the mechanism behind the season's
largest overpayments.

#### Scenario: short of cash
- **WHEN** a T1 / T2 / T3 / T4 bid does not fit the wallet **THEN** it comes
  back whole and is never labelled `todo el saldo`
- **WHEN** the wallet does not reach the asking price **THEN** the same
- *Verifies:* `test_no_tier_empties_the_wallet_when_short_of_cash`,
  `test_a_wallet_below_the_price_is_not_bid_as_a_whole`,
  `test_a_top_tier_with_no_cash_is_left_to_the_caller`

### Requirement: Never overspend, and one skip never blocks the next

The system SHALL skip any player whose would-be bid exceeds `remaining_cash`,
without aborting the run — a later, cheaper candidate still gets its bid. Cash
is only decremented by bids that actually land.

#### Scenario: unaffordable top pick does not starve a cheaper one
- **WHEN** cash is 5M and the highest-SF candidate needs 9.6M (and 5M does
  not cover his 8M price) but the next needs 2.4M
- **THEN** the expensive one is skipped (kind `no_cash`) and the cheaper one
  is bid; the run continues
- *Verifies:* `test_run_auto_bid_first_too_expensive_does_not_block_cheaper_next`

### Requirement: Cash already promised to waiting bids is not bid again

`remaining_cash` SHALL start from the account balance minus every bid still
waiting on the market. Biwenger does not take a waiting bid off the balance,
so a second run on the same morning read the full balance again and bid it a
second time — three bids for 13.4M against 8.5M of cash. A failed read of the
waiting bids SHALL stop the run rather than bid on the gross balance.

#### Scenario: a waiting bid shrinks the wallet
- **WHEN** cash is 5M and 3M are already waiting on another player
- **THEN** a 3.15M bid does not fit and the run reports 2M remaining
- *Verifies:* `test_cash_already_promised_to_waiting_bids_is_not_bid_again`

### Requirement: Anti-pattern jitter stays negligible and in range

Every non-skipped bid SHALL carry a random 0–`BID_JITTER_MAX` (1000 €) offset
so amounts do not look botty. The offset SHALL never leave `[0, BID_JITTER_MAX]`
and SHALL never push a bid above the affordability cap.

#### Scenario: jitter bounded over many samples
- **WHEN** the same tier bid is computed 500 times
- **THEN** every offset is within `[0, 1000]` and at least a few distinct
  values appear (randomness is on)
- *Verifies:* `test_tier_jitter_is_within_advertised_range`

### Requirement: Candidate selection

The system SHALL bid only on daily-market (computer-owned) listings, dropping
user-owned listings and players absent from the Biwenger player map. Players
with no JP match are kept with SF = 0. Candidates SHALL be ordered by SF
descending.

#### Scenario: filtering and ordering
- **WHEN** the market mixes computer listings, a user listing, an unmatched
  player, and a player missing from the map
- **THEN** only the valid computer listings survive, sorted SF-desc, unmatched
  kept at SF 0
- *Verifies:* `test_build_candidates_drops_user_listings_and_unmatched_players`,
  `test_build_candidates_sorts_by_sf_descending`

### Requirement: A keeper is signed only to replace the one owned

A goalkeeper on the market SHALL get a bid only when he projects above the
keeper the squad already starts and JP has him in his club's eleven. A
manager's only keeper cannot be claused (league rule, as in
`clausulazo-emergency`); a second one exposes both, so a keeper behind the
current one is skipped — chollo or not — and the summary says who he does not
beat. One who would start is bid as usual, and the summary names the keeper he
replaces; the trader then sells that one (`market-trader`). Without the squad
nothing is skipped: a signal not read must not suppress a bid.

#### Scenario: keepers
- **WHEN** a market keeper projects below the one owned **THEN** no bid, and
  the summary shows "Segundo portero"; the same for a chollo keeper
- **WHEN** he projects above **THEN** he is bid, and the summary names the
  keeper he replaces
- **WHEN** the squad could not be read **THEN** he is bid as before
- *Verifies:* `test_a_keeper_who_would_not_start_gets_no_bid`,
  `test_a_keeper_who_would_start_is_bid_on_and_the_other_is_named`,
  `test_a_chollo_keeper_who_would_not_start_gets_no_bid_either`,
  `test_without_the_squad_a_keeper_is_still_bid_on`

### Requirement: A T3 or T4 player is bid on only if he would make the eleven

A candidate rated T3 or T4 (SF from `TIER_T4_MIN` to under `TIER_T2_MIN`) SHALL
get a bid only when the lineup search would field him in the best eleven if he
joined the squad; otherwise he is skipped and the summary says so
(`🪑 Banquillo … no entraría en tu once`). Below the bid floor no such line is
written — he was never going to get a bid. T1/T2 keep the bench clamp of
`bid_sf`; a chollo is still bid on, since it is bought to sell; without the
squad nothing is skipped.

On 23/10 auto-bid spent 9.65M of 12.44M on three players behind every owned
one at their lines (Cucurella at 5.99M with SF 307). The next morning his
projection rose to 377, enough to be the sixth defender, and the depth rule
bid 5.93M on him again: the depth chart counts a spare, the eleven does not.

#### Scenario: the eleven decides
- **WHEN** a T3/T4 would not make the best eleven **THEN** no bid, and the
  summary shows "Banquillo"
- **WHEN** he would start over someone owned **THEN** he is bid on as before
- **WHEN** he is below the bid floor anyway **THEN** no "Banquillo" line
- *Verifies:* `test_a_bottom_tier_player_behind_every_owned_one_gets_no_bid`,
  `test_a_bottom_tier_player_who_would_start_is_still_bid_on`,
  `test_a_player_below_the_bid_floor_is_not_reported_as_bench`,
  `test_bench_players_from_a_club_do_not_fill_its_cap`

### Requirement: A bid is priced on whether the player will be on a pitch

The tier ladder reads a single SF number, and JP hands a high one to players who
are not going to play — one it leaves out of its projected eleven, and one who is
injured. Read alone, that number sent the top tier after both. Before the
ladder sees a candidate:

- **WHEN** he cannot be fielded at all (injured, suspended, no fixture)
  **THEN** he SHALL be skipped, and reported as skipped for that reason.
- **WHEN** JP leaves him out of its projected eleven, **or** the squad already
  owns better cover at every position he plays (`SQUAD_DEPTH_SLOTS`)
  **THEN** his SF SHALL be clamped to `BENCH_PRICED_SF` so he cannot reach the
  T1 or T2 tiers, and the summary SHALL say the bid was reduced and why.
- **WHEN** he is versatile **THEN** one uncovered position is enough to price
  him at full value — a signing needs one door open, not all of them.
- **WHEN** the squad cannot be read **THEN** bidding SHALL continue on the
  player's own SF, as it did before the signal existed.

The clamp changes what is *paid*, never what is *reported*: the summary shows the
SF JP actually gave him.

#### Scenario: high-SF non-players do not drain the wallet
- **WHEN** the daily market offers an injured SF 900 and a benched SF 900
- **THEN** the injured one is skipped and the benched one is bid for on the T3
  ladder, leaving the rest of the wallet intact
- *Verifies:* `test_build_candidates_flags_bench_and_unavailable_players`,
  `test_bid_sf_caps_a_benched_star_out_of_the_all_in_tier`,
  `test_bid_sf_caps_a_signing_who_would_sit_on_our_bench`,
  `test_bid_sf_leaves_a_real_signing_alone`,
  `test_bid_sf_does_not_annotate_a_player_already_below_the_cap`,
  `test_would_be_bench_needs_every_position_covered`,
  `test_would_be_bench_is_false_when_the_position_is_thin`,
  `test_would_be_bench_is_false_without_a_position`,
  `test_run_auto_bid_skips_the_injured_and_does_not_all_in_the_benched`

### Requirement: The market and the squad are measured with one ruler

Both projections this module compares SHALL come from the same blend, built
from the same scale in the same request: the market candidates and the squad
rows they are weighed against.

`_would_be_bench` asks whether a signing would sit behind players already
owned, and that answer sets the bid. Blending one side and leaving the other
on raw Jornada Perfecta tilts every bid the same way, and nothing in the
output would say so — the module spends real money each morning with nobody
watching, so a silent bias is the worst failure mode available to it.

Market candidates are not built by `build_squad_rows`, so they SHALL go
through `rows.build_row` and `rows.enrich_with_custom_prediction` rather than
reading a projection of their own. A second blending path is the same defect
wearing a different shape.

The tier thresholds need no recalibration. The conversion is a percentile map
**into JP units**, so a threshold expressed in those units keeps its meaning
and is simply applied to a better estimate; the ±25% clamp bounds how far any
one player can move.

#### Scenario: the blend decides a signing the raw rate would have refused
- **WHEN** Oráculo rates a market keeper far above the two already owned, while
  JP ranks him below both
- **THEN** on the raw rates he is bench and draws no bid, and once both sides
  carry the blend he breaks into the depth chart
- **WHEN** the Oráculo read failed and there is no scale
- **THEN** every projection is the raw JP rate, identical to an unthreaded call
- *Verifies:* `test_the_market_and_the_squad_are_ranked_on_one_scale`,
  `test_without_a_scale_every_projection_stays_raw_jp`

### Requirement: No more than three players from one club

A candidate from a club that already has `MAX_PLAYERS_PER_CLUB` (3) starters
in the squad's best eleven SHALL draw no bid, chollos included, and the summary
SHALL say so (🏟️). The bench does not count — three weak reserves from a club
must not cost the bid on a good one. Bids placed earlier in the same run — and,
on a retry, the ones already logged — count when the signing would start. A
bad day for one club costs every starter owned from it. When the squad could not be read the cap SHALL NOT apply: a signal that is
missing never suppresses a bid.

#### Scenario: the club cap
- **WHEN** the best eleven already starts three of a candidate's club **THEN**
  he is skipped and the summary names the cap; a candidate from another club
  is bid
- **WHEN** the club's players in the squad are reserves **THEN** they do not
  count and the bid goes out
- **WHEN** two candidates from a club two-deep are on the market **THEN** only
  the first is bid
- **WHEN** the squad read fails **THEN** the cap is off and bids go out
- *Verifies:* `test_a_club_already_three_deep_in_the_squad_gets_no_bid`,
  `test_bids_placed_in_the_same_run_count_towards_the_club`,
  `test_without_the_squad_the_club_cap_does_not_hold_bids_back`,
  `test_bench_players_from_a_club_do_not_fill_its_cap`

### Requirement: The chollos trade buys to sell, with pocket money

A player on Oráculo's `chollos` shortlist SHALL be bid `price +
CHOLLO_MARGIN` — a thin margin over the asking price, on **every** chollo in
the day's market rather than a selection among them.

The bid is weak on purpose. Biwenger sells to the highest offer, so anyone who
actually wants the player outbids it; the ones that land are the ones nobody
else bid on, which is the premise of the trade rather than a flaw in it. The
daily ceiling and the owner's manual cancel in the app are the second and
third guards, not the first.

That shortlist is excluded from the projection bonus for the opposite reason
it is used here: it ranks by price rather than quality, and its players will
not be fielded. Buying them is a different question from fielding them.

Membership SHALL NOT depend on the player carrying a projection. Oráculo's
projections fill up as the matchday approaches — 67 players three days out,
260 six hours later, 497 on the eve — while the shortlists are published from
the start. Resolving a market player only through the projections left the
shortlists invisible from Monday to Wednesday, which is most of the trading
week: the chollo was on the list and in the market, and we could not see him.
The shortlist entries carry their own names, so they are indexed separately
and consulted when no projection matches.

Being on a list is still not a number. A player found this way has
`oraculo_matched` False and no points, and contributes nothing to any
projection — the market path asks a different question and only it is
answered.

The speculative path SHALL sit outside `tier_bid` rather than inside it with a
loosened clamp. `bid_sf` holds a would-be substitute down to
`BENCH_PRICED_SF` because the ladder once spent the wallet on a benched star; a
chollo is that same shape with a different intent — a little, knowingly,
rather than everything, mistakenly. A flat price bypasses the clamp for this
path alone, where weakening the clamp would reopen the original bug for every
candidate. Nothing about the player's projection is consulted: the trade does
not care whether he plays.

Cash SHALL be reserved before the ladder starts, sized from the chollos
actually on offer that morning. "Whatever is left over" is usually nothing,
because the ladder spends best-first, so leftovers would fire the trade only
on days it was not needed.

The reserve SHALL yield to the ladder, down to T3 and no further: where a
signing at `TIER_T3_MIN` or above fits the wallet but not beside the reserve,
the reserve gives way exactly as far as that bid needs. One genuine star beats
three lottery tickets; skipping a 2.2M signing to keep a 950K lottery ticket
alive is the trade backwards.

Below T3 it SHALL hold. There the ladder is buying squad filler — SF 300 to
399, bid at 1.03× the asking price — and a ticket with an explicit exit is
worth more than a marginal body. The line falls at T3 because that is where
the ladder stops buying players for the eleven and starts buying depth.

No exit code is needed. `/ofertas` rule 5 — `sf < TIER_T3_MIN and roi_pct > 0
→ ACEPTAR` — is already the shape of a chollo bought to trade, and `roi_pct`
means the purchase price is known. A chollo whose projection climbs past
`TIER_T3_MIN` reaches rule 3 instead, which is correct: he stopped being a
trade and became a squad decision.

#### Scenario: the day's speculation, and what outranks it
- **WHEN** a chollo is in the market and the ladder has taken its man
  **THEN** he is bid his asking price plus the margin
- **WHEN** he is on the shortlist but Oráculo has projected nobody yet
  **THEN** he is still recognised and still bid on
- **WHEN** a T1 does not fit the wallet **THEN** he is skipped and the
  speculation still goes ahead
- **WHEN** a T3-or-better bid fits the wallet but not beside the reserve
  **THEN** the reserve yields and the signing goes through
- **WHEN** the same is true of a bottom-tier bid **THEN** the reserve holds and
  the chollo is bought instead
- **WHEN** more chollos are on offer than the daily allowance **THEN** only
  `CHOLLO_MAX_BIDS` are placed
- *Verifies:* `test_a_chollo_is_carried_off_the_shortlist_onto_the_candidate`,
  `test_a_chollo_bid_is_the_asking_price_plus_a_thin_margin`,
  `test_a_chollo_never_reaches_the_expensive_tiers`,
  `test_the_reserve_is_sized_on_the_day_s_own_chollos`,
  `test_the_reserve_never_exceeds_the_wallet`,
  `test_a_chollo_is_bought_with_cash_the_ladder_left_reserved`,
  `test_a_top_tier_short_of_cash_is_skipped_not_paid_with_the_wallet`,
  `test_the_reserve_yields_rather_than_block_a_real_signing`,
  `test_the_reserve_still_yields_to_a_third_tier_signing`,
  `test_the_reserve_holds_against_a_bottom_tier_signing`,
  `test_the_trade_can_be_switched_off_without_a_deploy`,
  `test_a_good_chollos_day_cannot_turn_the_wallet_into_bench_filler`

### Requirement: Idempotent retries

Cloud Scheduler retries 5xx responses. The system SHALL log each placed bid to
`auto_bid_log/{YYYY-MM-DD}/bids` (one doc per player id, with an `expires_at`
TTL of 90 days) and SHALL skip any player already in today's log before
bidding, so a retried half-run does not double-bid.

#### Scenario: retry does not re-bid
- **WHEN** a player is already in today's log and still matches a tier
- **THEN** no bid is placed for them
- *Verifies:* `test_run_auto_bid_skips_already_bid_today`, `test_log_bid_writes_expected_document`

#### Scenario: Firestore outage degrades safely
- **WHEN** the dedup log read raises
- **THEN** the system proceeds with an empty dedup set (worst case: a rare
  double-bid on retry) rather than skipping every candidate
- *Verifies:* `test_already_bid_ids_returns_empty_set_on_firestore_error`

### Requirement: A Biwenger rejection does not abort the run

If Biwenger rejects one bid (4xx), the system SHALL log it and continue to the
next candidate; only successful bids count and decrement cash.

#### Scenario: mid-run rejection
- **WHEN** the first bid is rejected and the second accepted
- **THEN** both are attempted, bid count is 1, cash drops only by the
  successful bid
- *Verifies:* `test_run_auto_bid_continues_when_biwenger_rejects_a_bid`

### Requirement: Telegram summary is delivered and HTML-safe

The system SHALL send one Telegram summary per run listing placed bids and
skips (with a distinct icon per skip kind: 💸 no-cash, 🔁 already-bid,
⚠️ biwenger-reject, ⏭️ tier-low), plus totals. Every dynamic value SHALL be
HTML-escaped so Telegram's HTML parser cannot misread a `<`, `>` or `&` and
drop the whole message. When bot credentials are absent, the summary SHALL be
skipped but the run SHALL still return its full result. When Telegram refuses
the summary, the error SHALL propagate (route → 500) rather than fail silently.

#### Scenario: user content is escaped
- **WHEN** a skip line contains `puja 14.000.000 € > cash 3.000.000 €` or a
  player name like `<Player & Co>`
- **THEN** the payload renders `&gt;`, `&lt;`, `&amp;` with no unescaped `>`
  left, and `<b>` tags stay balanced
- *Verifies:* `test_format_telegram_text_html_escapes_user_content`,
  `test_format_telegram_text_no_cash_skip_shows_sf_and_tier`

#### Scenario: missing credentials vs delivery failure
- **WHEN** the bot token is empty **THEN** no send happens, result still returned
- **WHEN** the send raises `TelegramDeliveryError` **THEN** it propagates
- *Verifies:* `test_run_auto_bid_skips_send_when_telegram_creds_missing`,
  `test_run_auto_bid_raises_when_telegram_send_fails`

### Requirement: The shares can be re-measured against the market

`scripts/auto_bid/calibrate.py` SHALL rebuild the season's settled market
auctions from the league board — winner, winning bid, the losing bids shown
(at most three) — price each at the asking price of the day before it closed,
and report, per price band, the share of auctions each overbid would have won
and the smallest whole-percent share winning 70 / 80 / 90 % of them, beside
the shares `auto_bid.py` bids today. It is read-only.

The report measures and does not decide: auctions are split by price and the
tiers by projection, so which band a tier's players fall in is a judgement.
A share wins an auction when `price × (100 + p) > winning bid × 100` — integer
maths, so a boundary never moves on float rounding.

#### Scenario: the auctions, the price, the rates
- **WHEN** the board holds a settled auction **THEN** its winner, winning bid,
  runner-up and our bid are read, and last season's are left out
- **WHEN** an auction closed on the 22nd **THEN** it is priced on the 21st
- **WHEN** overbids of 0–9 % are on record **THEN** +8 % is the least that
  wins eight in ten
- **WHEN** we won an auction **THEN** what we paid over the next best bid (or
  the price, if nobody else bid) counts as left on the table
- *Verifies:* `test_auctions_come_off_the_board_with_winner_and_losing_bids`,
  `test_last_seasons_auctions_are_left_out`,
  `test_price_on_reads_the_day_before_the_auction_closed`,
  `test_win_rate_counts_the_bids_a_share_would_have_beaten`,
  `test_share_to_win_finds_the_smallest_share_reaching_the_target`,
  `test_left_on_the_table_is_what_we_paid_over_the_next_best`,
  `test_overbid_by_winner_takes_the_median_per_manager`
