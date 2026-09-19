# Capability: auto-bid

Daily aggressive auto-bidding on the Biwenger daily market. Cloud Scheduler
posts `POST /market/auto-bid` at 09:00 Madrid. The system reads the rotating
computer-owned free agents Biwenger exposes each morning, attaches SofaScore
(SF) ratings from JP blended with Oráculo, and bids on each — best first —
until cash runs out, then reports the run to Telegram.

- **Source:** `packages/biwenger_tools/api/logic/auto_bid.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_auto_bid.py`

---

### Requirement: Tier-based bid sizing

The system SHALL size each bid from the player's SF rating using four tiers,
computed over Biwenger's cf-base `price` (not `owner.price`). Each non-all-in
tier bids `min(price × multiplier, price + cap)`, so the multiplier bounds
cheap players and the absolute cap bounds expensive ones.

| Tier | SF band | Bid formula |
|---|---|---|
| T1 (all-in) | SF ≥ 800 | `remaining_cash − jitter` |
| T2 | 600 ≤ SF < 800 | `min(price × 1.7, price + 5M) + jitter` |
| T3 | 400 ≤ SF < 600 | `min(price × 1.5, price + 2M) + jitter` |
| T4 | 300 ≤ SF < 400 | `min(price × 1.2, price + 500K) + jitter` |
| skip | SF < 300 | — |

Crossover prices (multiplier == cap): T2 ≈ 7.14M, T3 = 4M, T4 = 2.5M. Below
the crossover the multiplier wins; above it the cap wins.

#### Scenario: multiplier wins on a cheap player
- **WHEN** a T3 player (SF 400) is priced at 750K
- **THEN** the bid is `min(750K × 1.5, 750K + 2M) = 1.125M` — never the +2M cap
- *Verifies:* `test_tier_t3_multiplier_wins_on_cheap_player_regression_calvo`

#### Scenario: cap wins on an expensive player
- **WHEN** a T3 player (SF 500) is priced at 10M
- **THEN** the bid is `min(10M × 1.5, 10M + 2M) = 12M` — the cap, not +50%
- *Verifies:* `test_tier_t3_cap_wins_on_expensive_player`

### Requirement: Inclusive lower boundaries

Tier thresholds SHALL be inclusive on the lower end: a player at exactly a
tier's minimum SF lands in that tier, not the one below.

#### Scenario: SF exactly on a boundary
- **WHEN** a player has SF = 800 / 600 / 400 / 300
- **THEN** they land in T1 / T2 / T3 / T4 respectively
- **AND** SF = 299 is skipped (below the T4 floor of 300)
- *Verifies:* `test_tier_boundaries`

### Requirement: All-in tier spends the full wallet

For T1 (SF ≥ 800) the system SHALL bid the entire `remaining_cash` regardless
of the player's price, so it never leaves cash on the table on a top target.
The bid SHALL never exceed `remaining_cash` (jitter is *subtracted* here, and
a zero wallet yields a zero bid rather than a negative one).

#### Scenario: top target against a smaller wallet
- **WHEN** an SF 910 player priced at 26M faces 30M cash
- **THEN** the bid is ~30M (`30M − jitter`), never `price + anything`
- *Verifies:* `test_tier_all_in_uses_remaining_cash_regardless_of_price`,
  `test_tier_jitter_subtracted_for_all_in`

#### Scenario: empty wallet
- **WHEN** `remaining_cash = 0` on an all-in target
- **THEN** the bid is 0 (never negative), which the caller turns into a skip
- *Verifies:* `test_tier_all_in_when_cash_is_zero_returns_zero_so_caller_skips`

### Requirement: Never overspend, and one skip never blocks the next

The system SHALL skip any player whose would-be bid exceeds `remaining_cash`,
without aborting the run — a later, cheaper candidate still gets its bid. Cash
is only decremented by bids that actually land.

#### Scenario: unaffordable top pick does not starve a cheaper one
- **WHEN** cash is 5M and the highest-SF candidate needs 13M but the next
  needs 3.4M
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
injured. Read alone, that number sent the all-in tier after both. Before the
ladder sees a candidate:

- **WHEN** he cannot be fielded at all (injured, suspended, no fixture)
  **THEN** he SHALL be skipped, and reported as skipped for that reason.
- **WHEN** JP leaves him out of its projected eleven, **or** the squad already
  owns better cover at every position he plays (`SQUAD_DEPTH_SLOTS`)
  **THEN** his SF SHALL be clamped to `BENCH_PRICED_SF` so he cannot reach the
  all-in or T2 tiers, and the summary SHALL say the bid was reduced and why.
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

The speculative path SHALL sit outside `tier_bid` rather than inside it with a
loosened clamp. `bid_sf` holds a would-be substitute down to
`BENCH_PRICED_SF` because the ladder once went all-in on a benched star; a
chollo is that same shape with a different intent — a little, knowingly,
rather than everything, mistakenly. A flat price bypasses the clamp for this
path alone, where weakening the clamp would reopen the original bug for every
candidate. Nothing about the player's projection is consulted: the trade does
not care whether he plays.

Cash SHALL be reserved before the ladder starts, sized from the chollos
actually on offer that morning. "Whatever is left over" is usually nothing,
because the ladder spends best-first, so leftovers would fire the trade only
on days it was not needed.

The reserve SHALL yield to the ladder, down to T3 and no further. The all-in
tier releases it outright — one genuine monster beats three lottery tickets —
and where a signing at `TIER_T3_MIN` or above fits the wallet but not beside
the reserve, the reserve gives way exactly as far as that bid needs. Skipping
a 3.4M signing to keep a 950K lottery ticket alive is the trade backwards.

Below T3 it SHALL hold. There the ladder is buying squad filler — SF 300 to
399, bid at 1.2× the asking price — and a ticket with an explicit exit is
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
- **WHEN** a candidate reaches the all-in tier **THEN** the reserve is released
  and the speculation stands down
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
  `test_the_all_in_tier_takes_the_reserve_with_it`,
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
