# Capability: biwenger-reads

Read league and competition state out of Biwenger: cash and maximum bid, the
member list, standings and reports, board feeds, squads, the market, the
received-offers inbox, the saved lineup, and the public player/team catalogue.

- **Source:** `core/sdk/biwenger.py` (the URL builders and every `get_*` method)
- **Verified by:** `core/tests/test_biwenger_client.py`

---

### Requirement: A null envelope reads as empty, never as a crash

Every read SHALL treat a payload whose `data` (or a nested list inside it) is
**present and null** exactly like a missing one, and return the empty
collection.

Biwenger answers a disabled market with `200` and a null body. `.get("data",
{})` returns `None` for a key that is present and null — the default only fires
when the key is absent — so chaining off it raised `AttributeError` deep inside
the SDK. The visible failure was `/analizar` answering 500 *after* every squad
photo had already been delivered: the work succeeded and the user got a bare
error. Six read methods shared the same latent shape, which is why this is a
rule for all of them rather than a fix in one.

#### Scenario: a closed market
- **WHEN** the market answers `{"data": null}`, `{"data": {"sales": null}}` or `{}`
- **THEN** the result is an empty list and no exception escapes
- **WHEN** the market is open **THEN** the sales list is returned as sent
- *Verifies:* `test_get_market_players_when_the_market_is_disabled`,
  `test_get_market_players`

#### Scenario: an empty report
- **WHEN** a report answers with no `columns` and no `rows`
- **THEN** the result is an empty list
- *Verifies:* `test_get_report_rows_empty_payload`

#### Scenario: a null envelope on every reader that defends against one
- **WHEN** `data` comes back `null` from the league users, standings, manager
  squad, received offers or current lineup endpoint
- **THEN** each reader hands back its own empty value rather than raising
- *Verifies:* `test_a_null_envelope_reads_as_empty_not_as_a_crash`

### Requirement: Reads hand back Biwenger's own objects

A read SHALL unwrap the envelope and return the collection Biwenger nested
inside it, with the entries untouched — the squad list, the market's `sales`,
the standings rows.

Renaming or trimming fields here would create a second vocabulary for the same
data: every caller that already reasons in Biwenger's terms (`price`,
`clauseValue`, `owner`) would need a translation table, and a field added
upstream would be invisible until the SDK was taught about it. Interpretation
belongs where the decision is made, not in the transport.

#### Scenario: a squad and a market page
- **WHEN** a manager's squad or the market is read
- **THEN** the entries arrive as Biwenger sent them, in order
- *Verifies:* `test_get_manager_squad`, `test_get_market_players`

#### Scenario: standings arrive in Biwenger's order
- **WHEN** the standings endpoint answers with a ranked table
- **THEN** the rows are handed back in that order, unsorted
- *Verifies:* `test_get_standings_full_returns_the_table_in_order`,
  `test_a_null_envelope_reads_as_empty_not_as_a_crash`

### Requirement: "Puja máxima" is computed on this side

`get_account_state` SHALL return the league's cash `balance`, and — when handed
a squad and a price map — the maximum bid as `cash + squad_value // 4`, where
`squad_value` sums the catalogue price of each squad member. Without both
inputs, `max_bid` SHALL be 0 rather than a guess. An unknown league SHALL yield
zeros.

Biwenger exposes no `maxBid` on any endpoint — `/account`, `/user`,
`/user/{id}`, `/league/{id}` and their `?fields=*` variants were all probed.
The mobile app computes the figure client-side, and the 25% factor was fitted
against the app's own display to the euro (12,972,212 € cash + 25% of
93,450,000 € squad = 36,334,712 €). It is therefore a reconstruction, not a
contract: if a league setting ever moves that factor, the drift shows up as a
wrong `Saldo` header in the budget recommendations, with nothing else to catch
it.

A squad member missing from the price map SHALL contribute 0 rather than fail —
the catalogue and the squad are two separate downloads and can disagree.

#### Scenario: cash alone, and cash plus a quarter of the squad
- **WHEN** no squad or no price map is passed **THEN** only cash is returned
- **WHEN** both are passed **THEN** `max_bid` is cash plus a quarter of the
  summed squad price
- **WHEN** a squad member has no price entry **THEN** he adds nothing and the
  rest still counts
- **WHEN** the client's league is not in the response **THEN** both fields are 0
- *Verifies:* `test_get_account_state_cash_only`,
  `test_get_account_state_computes_max_bid_with_squad_and_prices`,
  `test_get_account_state_handles_missing_prices`,
  `test_get_account_state_unknown_league_returns_zeros`

### Requirement: The caller names the accounts the member list must hide

`get_league_users` SHALL map user id → name from the standings, dropping every
id in the **required** `excluded_ids` argument.

Some leagues contain an account that posts board messages and plays no football
(here, the cronista). Left in, it becomes an empty squad in every iteration, a
pickable manager in every menu, a clausulazo candidate with nothing to buy, and
a line in the palmarés. Filtering at the single point where the member list is
built is what keeps every downstream feature from having to remember.

Which accounts those are is a property of a **league**, not of Biwenger, so the
SDK does not know them — the caller passes them. The argument is required and
has no default on purpose: a default would let a new call site silently
re-include them, and the failure is invisible until a menu shows a manager with
no squad. The league's own list lives in
`packages/biwenger_tools/constants.py`.

Passing an empty set asks for everyone, which is what the scraper needs:
board-message author resolution and the participación count must still see
non-competing accounts — see
[`league-scraper`](../../biwenger_tools/league-scraper/spec.md).

#### Scenario: excluded ids are dropped, an empty set keeps everyone
- **WHEN** the standings include an account named in `excluded_ids`
- **THEN** the map omits it
- **WHEN** `excluded_ids` is empty **THEN** the same member appears with its name
- *Verifies:* `test_get_league_users`,
  `test_get_league_users_excluding_nobody_returns_everyone`

### Requirement: Reports are keyed by the label the app shows

`get_report_rows` SHALL zip a `report/*` response's `columns` and `rows` into
one dict per row, keyed by the raw column name, positionally and tolerant of a
row shorter than the header.

Biwenger's report endpoints return a spreadsheet, not objects: the meaning of
each cell lives only in its column. Keeping Biwenger's own labels ("Jornadas
ganadas", "Posición media") means a caller reads a value by the same name the
user sees in the app, and a new column added upstream appears rather than
shifting every field by one.

The first column is a user object; the rest are scalars whose type varies by
report, so no coercion is applied.

#### Scenario: a rounds report
- **WHEN** a report with three columns and two rows is read
- **THEN** each row is a dict keyed by column name, the user cell keeping its
  `id`/`name` object
- *Verifies:* `test_get_report_rows_parses_columns_and_rows`

### Requirement: Paged feeds are read to exhaustion

`get_all_board_messages` and `get_all_clausulazos` SHALL walk `limit`/`offset`
pages from a caller-supplied base URL until a page comes back empty or shorter
than `limit`, and return everything gathered — a flat list for messages, a
`{"data": [...]}` envelope for clausulazos, matching the single-page shape each
one's caller already parses.

Stopping on a short page is what keeps a full history read to a bounded number
of requests against a per-account quota, instead of one extra request per feed
every time.

#### Scenario: one page, several pages, no pages
- **WHEN** the first page is shorter than `limit` **THEN** exactly one request
  is made
- **WHEN** a full page is followed by a short one **THEN** both are returned and
  the walk stops
- **WHEN** the first page is empty **THEN** the result is empty and no second
  request is made
- *Verifies:* `test_get_all_board_messages_single_page`,
  `test_get_all_board_messages_paginates`,
  `test_get_all_clausulazos_paginates`,
  `test_get_all_clausulazos_stops_on_empty`

#### Scenario: a dict-shaped page is read by its values
- **WHEN** a clausulazos page returns `data` as a dict rather than a list
- **THEN** its values are taken, in order, and pagination continues
- *Verifies:* `test_get_all_clausulazos_accepts_a_dict_shaped_page`

> **Provenance unknown.** The branch is pinned, not endorsed: no feed has been
> observed returning this shape. It stays because a defence that only fires
> during a format change is the one you cannot delete on a hunch. If a feed is
> ever seen sending it, name the feed in the test.

### Requirement: A board feed is chosen by type, and an admin transfer is not a transfer

The board URL builders SHALL each pin the `type` their caller means: `text` for
league chat, `transfer` for release-clause moves, and `adminTransfer` for
movements an admin made by hand.

`adminTransfer` entries do not appear in the `transfer` feed at all. The draft
polled `transfer` for its own movements and always found an empty feed —
nothing errored, the feature was simply blind.

#### Scenario: each builder pins its own feed
- **WHEN** the league board, clausulazos and admin-transfer URLs are built
- **THEN** they carry `type=text`, `type=transfer` and `type=adminTransfer`
  respectively, and the admin builder is not the transfer one
- *Verifies:* `test_each_board_builder_pins_its_own_type`

### Requirement: The competition catalogue is public, unwrapped, and downloaded once

`get_competition_maps` SHALL return both the player map and the team map from a
**single** download of the public competition payload, and SHALL be callable
without a session.

The payload is ~550 players and the endpoint needs no authentication. Callers
that wanted both maps used to download it twice per market load, against an
account quota shared with everything else; and requiring a session to resolve a
player's name meant a login for a lookup that Biwenger serves to anonymous
callers.

The endpoint sometimes answers with a JSONP wrapper instead of plain JSON, so
the response SHALL be unwrapped when it does not parse as JSON.

The team map exists to tell namesakes apart: the player database carries only a
numeric team id while the market names the team in full.

#### Scenario: JSON, JSONP, and one download for both maps
- **WHEN** the payload is plain JSON **THEN** the player map is keyed by player id
- **WHEN** the payload arrives wrapped in a `jsonp_…(…)` call **THEN** it is
  unwrapped and parsed the same way
- **WHEN** both maps are requested **THEN** exactly one HTTP request is made,
  with no authenticated session
- *Verifies:* `test_get_all_players_data_map_json`,
  `test_get_all_players_data_map_jsonp`,
  `test_get_competition_maps_downloads_once`

### Requirement: The received-offers inbox lives on the user endpoint

`get_received_offers` SHALL read `user?fields=offers(*,from(*),to(*))` and
return only offers addressed to the authenticated user with status `waiting`.

The plain `/offers` collection returns historical entries — expired and
processed — and never the pending ones, so the inbox the app shows is only
reachable through the user endpoint with that field expansion.

The `from` block is left as sent, because its absence carries meaning the SDK
must not erase: a null `from` is Biwenger's own public-market offer, raised
automatically when a player is listed, while a populated one is a rival manager
bidding.

> **GAP — unverified.** Nothing exercises the filter. A test would assert that
> an offer addressed to another user, and one already processed, are both
> dropped, and that a null `from` survives to the caller — the recommendation
> message renders differently for the two.

### Requirement: "In my XI" means the lineup Biwenger has saved

`get_current_lineup_player_ids` SHALL return the ids in the non-null slots of
the user's **saved** lineup, read from `?fields=lineup(date,formation,players)`.

This is the only honest answer to "is this player in my eleven", and it is
deliberately not the auto-pick optimizer's answer. The optimizer computes the
*best* eleven and returns nothing when it cannot form a legal one — with a
squad of one valid player and ten holes, that flipped every player's starter
flag to false, and the offers message told the user his only starter was not in
his lineup. An empty formation slot arrives as `null`, so slots are filtered,
not counted.

The consumer contract is in
[`offers-inbox`](../../biwenger_tools/offers-inbox/spec.md).

> **GAP — unverified.** No test reads a lineup payload through the SDK. One
> would assert that null slots are skipped and that the ids of a partially
> filled formation come back intact.
