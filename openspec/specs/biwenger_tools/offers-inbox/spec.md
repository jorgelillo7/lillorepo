# Capability: offers-inbox

Analyse received transfer offers and recommend accept / reject / doubtful per a
tier- and market-aware algorithm, then present each to Telegram with decide
buttons.

- **Source:** `packages/biwenger_tools/api/logic/offers.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_offers.py`

---

### Requirement: Sell recommendation algorithm

`recommend` SHALL classify an offer as **RECHAZAR / DUDOSO / ACEPTAR** from two
independent axes — what the offer is worth in money, and what the squad loses in
football — never letting one stand in for the other:

- T1 (star) is never sold by default; a star with an indecent over-market offer
  becomes DUDOSO.
- T2 starters (fixed titular) are rejected — even when not explicitly marked
  starter.
- A useful T3 with a heavy loss (≥ 25% under what was paid) is rejected, unless
  the market pays a strong premium over cf-base (loss-aversion override).
- Bench/discard players with a profit, or any offer clearly above market, are
  accepted; offers clearly below market are rejected (sell publicly instead).
- Ambiguous T4/no-tier or fair-market projection cases fall through to DUDOSO.

#### Scenario: representative decisions
- **WHEN** a star / T2 starter / heavy-loss T3 / below-market offer is seen
- **THEN** RECHAZAR (with the noted overrides)
- **WHEN** a bench profit or clearly-above-market offer is seen **THEN** ACEPTAR
- **WHEN** the market data is ambiguous **THEN** DUDOSO
- *Verifies:* `test_recommend_rejects_star_player`, `test_recommend_rejects_t2_starter`,
  `test_recommend_rejects_t2_even_when_not_marked_as_starter`,
  `test_recommend_rejects_useful_player_with_heavy_loss`,
  `test_recommend_loss_aversion_overridden_by_strong_market_premium`,
  `test_recommend_star_with_indecent_offer_becomes_doubtful`,
  `test_recommend_accepts_bench_warmer_with_profit`,
  `test_recommend_accepts_offer_clearly_above_market`,
  `test_recommend_rejects_offer_clearly_below_market`,
  `test_recommend_doubtful_for_rotation_with_fair_offer`,
  `test_recommend_catchall_returns_doubtful`

#### Scenario: tier labels
- **WHEN** labelling by SF **THEN** each band names a *projection* ("Proyección
  top / alta / media / baja", "Sin proyección") and never a squad role
- *Verifies:* `test_tier_label_boundaries`

### Requirement: Squad depth outranks the projection band

A player's JP projection says how well he is expected to *score*; it does not say
what the squad loses if he *leaves*. The recommendation SHALL price the second
question separately, by re-running the auto-pick optimizer over the squad without
the player under offer:

- **WHEN** no legal eleven can be formed without him **THEN** RECHAZAR
  regardless of the money — an unfilled slot is a flat -4 on the round.
- **WHEN** he is in the current eleven and the best eleven loses at least
  `XI_LOSS_REJECT` (150) projected SF without him **THEN** RECHAZAR, unless the
  offer clears `STAR_OVERRIDE_OVER_MARKET_PCT`, which steps it back to DUDOSO.
- **WHEN** the loss is smaller **THEN** the money rules decide, and the verdict
  names the size of the hole and the replacement rather than offering
  "decide según tu necesidad de cash" alone.
- **WHEN** the signal cannot be computed **THEN** the money rules SHALL behave
  exactly as they did without it.

The optimizer SHALL be invoked through `lineup.xi_snapshot`, which runs the same
search as `pick_lineup` with none of its observation side effects: `provider_watch`
records the promotions actually bet on each morning, and counterfactual runs must
not write to that audit trail. The replacement named to the user SHALL be taken
from the diff of the two elevens, so it is by construction the player the SF
difference measures — not the best squad member at that position, who is usually
already on the pitch.

The search is exhaustive backtracking (~0.65 s per solve on a 15-man squad, ~3 s
at 25 with many multi-position players) and `/ofertas` is chained onto
`/digests/daily`, which holds a 5-minute end-to-end SLO. Two bounds SHALL apply:

- The baseline eleven is solved **once per inbox**, not once per offer.
- An offer for a player **not** in the current eleven SHALL NOT be solved at all
  — every depth rule requires `is_starter`, so the work cannot change its verdict.
- Past `_DEPTH_BUDGET_S` of wall-clock across the inbox, the signal SHALL degrade
  to unavailable and the money rules SHALL decide alone.

#### Scenario: an irreplaceable starter is not sold on good numbers
- **WHEN** a first-choice goalkeeper projecting 404 is offered +20% over what was
  paid and +2% over cf-base, and the only other keeper projects 12
- **THEN** RECHAZAR, stating the SF the eleven would lose
- *Verifies:* `test_recommend_rejects_starter_whose_replacement_cannot_cover`,
  `test_recommend_rejects_when_selling_breaks_the_eleven`,
  `test_recommend_downgrades_irreplaceable_starter_on_an_indecent_offer`,
  `test_recommend_lets_replaceable_starter_be_sold`,
  `test_recommend_without_depth_signal_keeps_old_behaviour`,
  `test_xi_impact_prices_a_scarce_position_higher_than_a_covered_one`,
  `test_xi_impact_flags_the_squad_that_cannot_field_an_eleven_without_him`,
  `test_xi_impact_survives_an_optimizer_failure`,
  `test_xi_impact_names_the_player_who_actually_comes_in`,
  `test_xi_impact_respects_the_deadline`,
  `test_a_non_starter_offer_never_pays_for_the_search`,
  `test_a_starter_offer_does_pay_for_the_search`

#### Scenario: the message names the replacement
- **WHEN** an offer is rendered **THEN** it carries the player's role in the
  squad, the SF the eleven would lose, and the name of the player who would take
  his place
- *Verifies:* `test_xi_impact_names_the_player_who_actually_comes_in`

### Requirement: Starter detection is resilient

`_starter_ids` SHALL read the actual Biwenger lineup
(`get_current_lineup_player_ids`), not the auto-pick lineup, and SHALL swallow
an SDK failure (recommendation still works, treating no one as a confirmed
starter).

#### Scenario: source and failure
- **WHEN** starters are needed **THEN** the Biwenger current lineup is used
- **WHEN** that fetch fails **THEN** it degrades without breaking the run
- *Verifies:* `test_starter_ids_pulls_from_biwenger_lineup_not_pick_lineup`,
  `test_starter_ids_swallows_sdk_failure`

### Requirement: Inbox delivery

`run_offers_inbox` SHALL send one Telegram message per offer (with decide
buttons), skip malformed offers (empty `requestedPlayers`) without crashing, and
on an empty inbox stay silent in digest mode but send "📭 Sin ofertas…" when
`notify_empty=True` (on-demand). An invalid decision SHALL raise;
`run_offer_decision` SHALL forward a valid one to the SDK and notify.

#### Scenario: per-offer send, empty modes, decision
- **WHEN** offers exist **THEN** one message each; a malformed one is skipped
- **WHEN** the inbox is empty **THEN** silent (digest) or a note (on-demand)
- **WHEN** a decision is made **THEN** valid → SDK + notify, invalid → raises
- *Verifies:* `test_run_offers_inbox_sends_one_message_per_offer`,
  `test_run_offers_inbox_skips_malformed_offer`,
  `test_run_offers_inbox_silent_when_empty_default`,
  `test_run_offers_inbox_notifies_when_empty_and_requested`,
  `test_run_offer_decision_invalid_raises`,
  `test_run_offer_decision_forwards_to_sdk_and_notifies`
