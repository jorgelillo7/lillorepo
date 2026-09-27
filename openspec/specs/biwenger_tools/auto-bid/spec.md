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
| T1 | SF ≥ 700 | `price × 1.40` |
| T2 | 550 ≤ SF < 700 | `price × 1.20` |
| T3 | 400 ≤ SF < 550 | `price × 1.10` |
| T4 | 300 ≤ SF < 400 | `price × 1.05` |
| skip | SF < 300 | — |

**The shares are set from the market, not by feel.** Across the season's 137
resolved market auctions, a bid of price +5 % would have won ~75 % of those
under 5M, and the contested stars went for +20–35 % (Güler +19 %, Camello
+35 %, Rodri +34 %). The previous ladder — the whole wallet for T1, and
`min(price × 1.7 / 1.5 / 1.2, price + 5M / 2M / 500K)` below — paid 6.36M
above the runner-up across the eight auctions it won (Valverde alone 3.24M),
while losing Güler at 16.38M to a 16.97M bid. The shares are a first
calibration, to be revisited as the board accumulates auctions.

The cut-offs are set against the league as it scores, not a round number: at
800/600 only two players in LaLiga reached T1 and five reached T2, and 24
logged bids over 16 days held one T2 and no T1. At 700/550 T1 holds the
handful of genuine stars and T2 the next nine.

#### Scenario: each tier's share
- **WHEN** a T1 / T2 / T3 / T4 player is priced 26M / 14.3M / 10M / 1M with
  cash to spare
- **THEN** the bid is 36.4M / 17.16M / 11M / 1.05M (+ jitter)
- *Verifies:* `test_each_tier_bids_its_share_over_the_price`

### Requirement: Inclusive lower boundaries

Tier thresholds SHALL be inclusive on the lower end: a player at exactly a
tier's minimum SF lands in that tier, not the one below.

#### Scenario: SF exactly on a boundary
- **WHEN** a player has SF = 700 / 550 / 400 / 300
- **THEN** they land in T1 / T2 / T3 / T4 respectively
- **AND** SF = 299 is skipped (below the T4 floor of 300)
- *Verifies:* `test_tier_boundaries`

### Requirement: A top tier short of cash bids the whole wallet

When a T1 or T2 bid would exceed `remaining_cash` but the wallet still covers
the asking price, the system SHALL bid the whole wallet instead of skipping
the player (jitter *subtracted*, so never above the cash). Skipping a player
worth those tiers leaves the auction uncontested — Güler would have been
skipped at 17.16M against 16.38M of cash. Below the asking price the market
takes no bid, so the player is skipped. T3 and T4 are not worth emptying the
wallet for: a bid that does not fit is skipped.

#### Scenario: short of cash, below the price, lower tiers
- **WHEN** a T1 or T2 player priced 14.3M faces 16.38M of cash
- **THEN** the bid is the wallet (`16.38M − jitter`), labelled `todo el saldo`
- **WHEN** the wallet does not reach the asking price **THEN** no whole-wallet bid
- **WHEN** a T3 or T4 bid does not fit **THEN** it is left for the caller to skip
- *Verifies:* `test_a_top_tier_short_of_cash_bids_the_whole_wallet`,
  `test_a_wallet_below_the_price_is_not_bid_as_a_whole`,
  `test_a_lower_tier_short_of_cash_is_left_to_the_caller`,
  `test_a_top_tier_with_no_cash_is_left_to_the_caller`,
  `test_a_whole_wallet_bid_subtracts_the_jitter`

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
signing at `TIER_T3_MIN` or above fits the wallet but not beside the reserve —
a T1/T2 whole-wallet bid included — the reserve gives way exactly as far as
that bid needs. One genuine star beats three lottery tickets; skipping a 2.4M
signing to keep a 950K lottery ticket alive is the trade backwards.

Below T3 it SHALL hold. There the ladder is buying squad filler — SF 300 to
399, bid at 1.05× the asking price — and a ticket with an explicit exit is
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
- **WHEN** a T1 short of cash bids the whole wallet **THEN** the reserve goes
  with it and the speculation stands down
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
  `test_a_top_tier_short_of_cash_takes_the_reserve_with_it`,
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
