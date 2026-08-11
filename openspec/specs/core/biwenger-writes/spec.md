# Capability: biwenger-writes

Every call that changes something in Biwenger: market bids, release-clause
buyouts, accepting or rejecting a received offer, saving a lineup, and the
league-admin operations that move players and money by hand.

This is the money path. Nothing here is undone by a second attempt, and most of
it is undocumented — the payload shapes were reverse-engineered from live
traffic and confirmed against real transactions.

- **Source:** `core/sdk/biwenger.py` (`place_market_bid`, `place_clausulazo`,
  `decide_offer`, `set_lineup`, `_post_admin_operation`, `transfer_player`,
  `release_player`, `revert_transfer`, `apply_bonus`)
- **Verified by:** `core/tests/test_biwenger_client.py`

---

### Requirement: League-admin mutations are never retried

`transfer_player`, `release_player`, `revert_transfer` and `apply_bonus` SHALL
post exactly once and SHALL NOT be wrapped in
[`http-retry`](../http-retry/spec.md). A failure SHALL surface to the caller.

None of these endpoints carries an idempotency key, and all of them answer
`204` with an empty body. A response lost in transit is therefore
indistinguishable from a mutation that never happened — and a retry after a
lost `204` assigns the player twice and charges the manager twice, or pays a
refund twice. The generic retry helper exists for reads and for writes that can
prove they are the same write; these can prove nothing.

The consequence for callers is stated rather than hidden: an empty `204`
confirms nothing, so a caller that needs certainty SHALL re-read Biwenger state
rather than trust the status code. This is the repo-wide rule in
`docs/technical/backend/python-conventions.md` § 3, and this is the code it was
written for.

#### Scenario: a failing admin write is not repeated
- **WHEN** a transfer, a revert or a bonus answers 5xx
- **THEN** the error is raised after exactly one request
- *Verifies:* `test_transfer_player_not_retried_on_failure`,
  `test_revert_transfer_not_retried_on_failure`,
  `test_apply_bonus_not_retried_on_failure`

### Requirement: The admin payloads carry the shapes and signs Biwenger reads

Admin operations SHALL post the exact bodies the web UI sends:

- **transfer** — `{to, amount, player, operation: "transfer"}`, assigning the
  player to a manager and charging the amount atomically. `to = 0` means free
  agency, so the zero SHALL round-trip untouched rather than being treated as
  "unset".
- **revertOffer** — `{to: 0, amount, player, offer, operation: "revertOffer"}`,
  where `amount` is the **same positive value** as the original transfer, not
  its negation, and `offer` identifies the transfer being undone.
- **bonus** — `{amount: {user_id: signed_delta, …}, reason}`, mapping **every**
  league member (0 for the untouched ones) because that is what the UI sends,
  with the sign convention **opposite** to a transfer: negative deducts,
  positive credits. `reason` is free text and is published on the league board,
  so it is read by humans.

Two mutations with opposite sign conventions in the same class is a trap; it is
recorded here because the only feedback for getting it backwards is real money
moving the wrong way in a real league.

#### Scenario: transfer, revert and bonus bodies
- **WHEN** a player is transferred to free agency **THEN** the body carries
  `to: 0` and the transfer operation, posted to the league transfer URL
- **WHEN** a transfer is reverted **THEN** the body repeats the positive amount
  and references the original offer id
- **WHEN** a bonus is applied **THEN** every manager in the map is sent, zeros
  included, with the reason
- *Verifies:* `test_transfer_player_posts_expected_body_and_url`,
  `test_revert_transfer_posts_expected_body`,
  `test_apply_bonus_posts_expected_body`

#### Scenario: releasing a player charges nobody
- **WHEN** a player is sent back to free agency
- **THEN** the body carries `to: 0` and `amount: 0` — the zero is the whole
  safety property, since a non-zero value charges someone for a player being
  taken away from them
- **WHEN** the endpoint answers 5xx **THEN** it is raised after a single
  attempt, never retried
- *Verifies:* `test_release_player_moves_no_money`,
  `test_release_player_does_not_retry`

### Requirement: An admin transfer cannot be undone by reference

`revert_transfer` SHALL NOT be used to undo a transfer this SDK made. Undoing
one SHALL be a `release_player` followed by an `apply_bonus` refund.

Biwenger issues no identifier for an admin transfer: the POST answers `204`
with an empty body and no useful headers, and the `adminTransfer` board entries
carry no `id` even when one is requested explicitly. There is simply nothing to
revert *by* — `revert_transfer` remains only for offers that do have an id.

The ordering and the money rules of the pair belong to the caller and are
stated in [`draft`](../../biwenger_tools/draft/spec.md).

#### Scenario: undo without an identifier
- **WHEN** an applied pick is undone
- **THEN** the player is released and the price refunded, with no call to
  `revert_transfer`
- *Verifies:* `test_undo_works_without_an_offer_id`,
  `test_undo_releases_the_player_and_refunds_the_price`

### Requirement: An offer is routed by who it is addressed to

Bids and clause buyouts SHALL both POST to `/offers`, and the body SHALL carry
the routing Biwenger reads:

- **daily-market bid** — `{to: null, type: "purchase", amount,
  requestedPlayers: [id]}`. The null `to` is what marks a computer-owned player;
  a user listing takes the seller's id instead, and sending the wrong one turns
  a market bid into a user-to-user offer against someone who never listed
  the player.
- **clausulazo** — `{to: <seller_user_id>, type: "clause", amount,
  requestedPlayers: [id]}`. `to` is the current owner; the authenticated user is
  the buyer Biwenger echoes back as `fromID`.

Both SHALL return Biwenger's `data` block — which carries the offer `id` and
`status` — and SHALL return an empty dict rather than `None` when a `200`
arrives without one, so a caller can read `.get("id")` unconditionally.

#### Scenario: the two bodies and the returned offer
- **WHEN** a daily-market bid is placed **THEN** `to` is null and the type is
  `purchase`
- **WHEN** a clausulazo is placed **THEN** `to` is the seller and the type is
  `clause`
- **WHEN** a `200` carries no `data` **THEN** the caller gets `{}`
- *Verifies:* `test_place_market_bid_posts_offer_with_expected_body`,
  `test_place_clausulazo_posts_offer_with_expected_body`,
  `test_place_market_bid_returns_empty_dict_when_data_missing`

### Requirement: Every numeric field is sent as a plain integer

Player ids, manager ids and euro amounts SHALL be coerced to `int` before
serialising, whatever the caller passed.

Amounts reach these methods through budget arithmetic and through numeric types
that serialise as `8480000.0`, and Biwenger answers a float amount with a `400`.
The coercion sits in the SDK because it is the last point that knows what the
wire needs.

#### Scenario: floats and numeric strings
- **WHEN** an amount arrives as a float, or an id as a string
- **THEN** the JSON body carries plain integers
- *Verifies:* `test_place_market_bid_coerces_numeric_args_to_int`,
  `test_place_clausulazo_coerces_numeric_args_to_int`,
  `test_transfer_player_coerces_numeric_args_to_int`

### Requirement: A refused offer fails immediately; a flaky one is retried

Offer POSTs SHALL go through [`http-retry`](../http-retry/spec.md): a 5xx or a
network blip is retried, and a 4xx is raised at once.

The two halves have different reasons. A transient failure must not lose a bid
the auto-bid loop already decided to place — the market window is once a day.
A 4xx is Biwenger's verdict on this specific offer, and retrying it only spends
quota: the player is gone, a higher bid is in, or the clause is refused.

Biwenger's refusals on a clause buyout, observed live, are the caller's
decision table — the amount is validated server-side and the response body
carries the human message:

| HTTP | Meaning | When |
|---|---|---|
| 400 | Invalid amount | amount outside `[price, clauseValue]` |
| 403 | Invalid clause: X < Y | amount is at or above the price but below the clause value — that is a regular offer, not a buyout |
| 403 | Clause locked | amount clears the clause value, but the player is inside the lock window Biwenger applies after a fresh purchase |
| 200 | `data.status = processed` | the player changes owner immediately |

#### Scenario: a rejected bid reaches the caller
- **WHEN** Biwenger answers 4xx to a bid
- **THEN** the error is raised so the caller can log it and move to the next
  candidate
- *Verifies:* `test_place_market_bid_raises_on_4xx`

#### Scenario: a transient failure does not lose a bid
- **WHEN** Biwenger answers 5xx and then succeeds
- **THEN** the bid is placed and the caller sees the accepted offer — the
  wrapper is pinned at the call site, not merely in the helper
- *Verifies:* `test_place_market_bid_retries_a_transient_failure`,
  `test_place_clausulazo_retries_a_transient_failure`

> **GAP — partially verified.** The clausulazo's own 4xx path is still
> uncovered — the refusals carrying the table above (`Invalid amount`,
> `Invalid clause`, `Clause locked`) are only exercised for the market bid.

### Requirement: A lineup is saved with or without a captain

`set_lineup` SHALL PUT `{lineup: {type, playersID, reservesID, captain}}` and
SHALL send `0` for the captain when the caller has none, which is Biwenger's
"no captain selected" value.

Applying the eleven matters more than the armband: when no starter clears
Biwenger's captain price cap the lineup is still saved, missing only the ©,
rather than being abandoned. Who may wear it is decided upstream, in
[`auto-pick-lineup`](../../biwenger_tools/auto-pick-lineup/spec.md).

The PUT SHALL go through [`http-retry`](../http-retry/spec.md): saving a lineup
is idempotent — the same eleven written twice is the same eleven — so a 5xx is
worth retrying, while a 4xx (rejected captain, malformed payload) is a verdict
and surfaces at once.

#### Scenario: the payload, with and without a captain
- **WHEN** a lineup is saved **THEN** formation, `playersID` and `reservesID`
  go out in the order given — Biwenger reads them positionally
- **WHEN** no starter clears the 3M cap (`None`, or `0`)
- **THEN** the wire carries `0`; sending null would reject the whole payload
  and leave yesterday's XI standing
- *Verifies:* `test_set_lineup_sends_the_formation_starters_reserves_and_captain`,
  `test_set_lineup_sends_zero_when_no_starter_can_wear_the_armband`

#### Scenario: a 5xx is retried, a refusal is not
- **WHEN** Biwenger answers 5xx and then succeeds **THEN** the lineup is applied
- **WHEN** Biwenger answers 4xx **THEN** it surfaces after one attempt
- *Verifies:* `test_set_lineup_retries_a_transient_failure`,
  `test_set_lineup_does_not_retry_a_payload_biwenger_refused`

### Requirement: An offer decision is checked before it is sent

`decide_offer` SHALL accept only `"accepted"` or `"rejected"`, raising
`ValueError` on anything else before touching the network, and SHALL PUT
`{"status": decision}` to `/offers/{id}`, returning Biwenger's echoed offer.

The decision arrives from a Telegram button callback, so a typo or a stale
button would otherwise be handed to Biwenger to interpret. The echoed status is
the confirmation the caller reports back: an accepted offer comes back
`processed` — Biwenger has already executed the transaction — while a rejected
one stays `rejected`.

#### Scenario: the guard, the route and the settled status
- **WHEN** the decision is anything but `accepted` or `rejected`
- **THEN** `ValueError` is raised and no request is made
- **WHEN** a valid decision is sent **THEN** it goes to `/offers/{id}` as
  `{"status": decision}` and Biwenger's echoed offer is returned
- **WHEN** an accept settles **THEN** the returned status is what Biwenger
  concluded (`processed`), not what was asked for
- **WHEN** Biwenger answers 4xx **THEN** it is raised rather than reported to
  the user as done
- *Verifies:* `test_decide_offer_refuses_a_decision_biwenger_does_not_understand`,
  `test_decide_offer_puts_the_decision_to_the_offer_and_returns_its_data`,
  `test_decide_offer_returns_the_status_biwenger_settled_on`,
  `test_decide_offer_raises_when_biwenger_refuses`

> **GAP — decision, not coverage.** `decide_offer` still has no stated position
> on retrying: neither wrapped nor commented as deliberately unwrapped. The
> tests pin what it does today, which is a bare PUT.
>
> What the flow is, so the decision is not taken blind: a human taps an inline
> button, the keyboard is cleared before the call fires, and the webhook answers
> 200 at once because the api call runs in a background thread — so Telegram
> does not redeliver either. Nothing retries anywhere. The cost of a transient
> 5xx today is a lost decision and a second `/ofertas`.
>
> The argument from shape: this is `PUT /offers/{id}` with `{"status": …}` — it
> sets a **state** on an identified resource, the same shape as `set_lineup`,
> which is wrapped precisely because writing the same eleven twice is the same
> eleven. What must never retry is the opposite shape: an admin operation POSTs
> a **delta** with no idempotency key and an empty 204, so a repeat charges
> twice.
>
> The awkward part, and why this deserves a decision rather than a default:
> `place_market_bid` POSTs to **create** a new offer and *is* wrapped, so a lost
> response there could leave two bids standing. By first principles the policy
> is backwards — the most idempotent of the three writes is the only one
> unprotected. That reads like nobody decided, not like somebody decided
> against.
>
> The one missing fact is what Biwenger answers to a second `accepted` on an
> offer already `processed`. Cheap to settle: on the next real offer, repeat the
> same PUT by hand and read the response.
