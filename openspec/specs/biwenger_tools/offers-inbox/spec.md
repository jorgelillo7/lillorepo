# Capability: offers-inbox

Analyse received transfer offers and recommend accept / reject / doubtful per a
tier- and market-aware algorithm, then present each to Telegram with decide
buttons.

- **Source:** `packages/biwenger_tools/api/logic/offers.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_offers.py`

---

### Requirement: Sell recommendation algorithm

`recommend` SHALL classify an offer as **RECHAZAR / DUDOSO / ACEPTAR** from the
player's tier (shared with auto-bid), starter status, and the offer vs cf-base
market value:

- T1 (star) is never sold by default; a star with an indecent over-market offer
  becomes DUDOSO.
- T2 starters (fixed titular) are rejected — even when not explicitly marked
  starter.
- A useful T3 with a heavy loss (≥ 25% under what was paid) is rejected, unless
  the market pays a strong premium over cf-base (loss-aversion override).
- Bench/discard players with a profit, or any offer clearly above market, are
  accepted; offers clearly below market are rejected (sell publicly instead).
- Ambiguous T4/no-tier or fair-market rotation cases fall through to DUDOSO.

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
- **WHEN** labelling by SF **THEN** the auto-bid tier minimums map to T1–T4 and
  below the T4 floor is "Descarte"
- *Verifies:* `test_tier_label_boundaries`

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
