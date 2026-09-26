# Capability: league-cash

Every manager's cash and maximum bid, which the league hides
(`settings.balance = "hidden"`): no endpoint returns a rival's balance. It is
rebuilt from the league board, where Biwenger logs every movement of money,
and sent as one image to the owner's chat on `/saldos`. The same figures warn
the owner, in the daily digest, when one of their players is about to lose
its clause protection.

Rebuilt from scratch on every request — nothing is stored. The board is the
source of truth, so a fresh read cannot drift the way an incremental ledger
could, and the whole read is ~15 sequential requests in under 5 seconds.

- **Source:** `packages/biwenger_tools/api/logic/league_cash.py` (pure),
  `packages/biwenger_tools/api/logic/actions.py` (`run_league_cash`,
  `run_protection_watch`), `packages/biwenger_tools/api/logic/digests.py`,
  `packages/biwenger_tools/api/logic/image_formatter.py` (`build_cash_image`),
  `packages/biwenger_tools/api/app.py` (`POST /league/cash`),
  `packages/biwenger_tools/bot/app.py` (`/saldos`)
- **Verified by:** `packages/biwenger_tools/api/tests/test_league_cash.py`,
  `packages/biwenger_tools/api/tests/test_actions.py`,
  `packages/biwenger_tools/api/tests/test_digests.py`,
  `packages/biwenger_tools/api/tests/test_rows.py`,
  `packages/biwenger_tools/api/tests/test_image_formatter.py`,
  `packages/biwenger_tools/api/tests/test_routes.py`,
  `packages/biwenger_tools/bot/tests/test_bot.py`

Validated before it shipped against two managers' real figures, both to the
euro: the owner's `/account` balance, and a rival's own app screen (*Saldo*
and *Puja máxima*).

**Known limits.** Two managers out of seven is not all of them; a quirk only
another manager's history holds would go unnoticed, which is why the owner's
figure is re-checked on every run. The league allows loans and exchanges and
neither has produced a board entry yet. And both copies of the one corrected
round paid the same amounts, so what Biwenger does when a correction *changes*
a payout is unobserved. The 50M start is proven on the owner's account and
corroborated league-wide: the −50,000,001 € fine that retired the chronicler
account left it at exactly −1.

---

### Requirement: Cash is the starting balance plus every board movement this season

A manager's cash SHALL be the draft's `DEFAULT_BUDGET` (50M — the draft
budget *is* the starting Biwenger balance) plus, over the board entries dated at or after the latest
`seasonStarted`:

| Entry | Effect |
|---|---|
| `transfer`, `market`, `adminTransfer` | `amount` leaves `to` and reaches `from`; either side may be absent (the market, the draft pool) |
| `clauseIncrement` | `amount` leaves `user` — a negative amount is a refund and adds |
| `bonus` | `amount` reaches `user` (admin bonuses, draft-undo refunds, cup prizes) |
| `roundFinished` | each `results[].bonus` reaches its `user` |

A manager with no entry at all SHALL be at the starting balance.

#### Scenario: movements of every kind
- **WHEN** a manager buys at the market, sells to the market, pays and
  receives clauses, drafts, raises a clause and is paid a round
- **THEN** the cash is the starting balance plus the signed sum of all of them
- *Verifies:* `test_every_movement_kind_moves_the_right_side`,
  `test_a_manager_with_no_entries_keeps_the_starting_balance`

### Requirement: A clause refund adds cash

Lowering a clause, or selling a player whose clause was raised, returns 75 %
of what was put in (`clauseDecrement = 75`), logged as a `clauseIncrement`
with a **negative** amount. It SHALL add to the manager's cash.

#### Scenario: raised, then refunded on sale
- **WHEN** a manager raises a clause by 2M and later gets −1.5M back
- **THEN** the net effect on cash is −0.5M
- *Verifies:* `test_a_negative_clause_increment_is_a_refund`

### Requirement: A score correction restates the round, it does not pay twice

Biwenger republishes a whole round as a new `roundFinished` entry when it
corrects scores (`reason: ["Corrección de puntuaciones"]`). Only the **latest**
entry per `round.id` SHALL count. Counting both overstated a balance by exactly
one round's payout.

#### Scenario: the same round published twice
- **WHEN** two `roundFinished` entries share a round id
- **THEN** only the later one's payouts are counted
- *Verifies:* `test_a_republished_round_counts_once_and_the_latest_wins`

### Requirement: Only the current season counts, and the read must reach its start

Entries older than the latest `seasonStarted` SHALL be ignored. A read that
does not contain a `seasonStarted` entry SHALL raise rather than return
figures, since the rebuild would be missing the season's first movements.

The board is paged newest first and SHALL stop at the page that contains
`seasonStarted` — a full-history read is ten times the requests for entries
that are then discarded.

#### Scenario: last season's movements, and a short read
- **WHEN** the read holds entries from before the latest season start
- **THEN** they do not move anyone's cash
- **WHEN** the read contains no `seasonStarted` **THEN** it raises
- *Verifies:* `test_entries_before_the_season_start_are_ignored`,
  `test_a_read_that_never_reaches_the_season_start_raises`,
  `test_get_all_board_messages_stops_at_the_page_holding_until_type`
  (`core/tests/test_biwenger_client.py`)

### Requirement: The maximum bid is cash plus a quarter of the squad, before pending bids

The league runs `maximumBid = "quarterTeam"`. A manager's maximum bid SHALL be
their cash plus a quarter of their squad's value at today's catalogue prices,
the same formula `get_account_state` uses for the owner.

The app subtracts a manager's own **pending bids** from this, and those are
blind to everyone else. The figure is therefore an upper bound, exact whenever
that manager has no bid open, and the image SHALL say so.

#### Scenario: a manager with no cash can still bid
- **WHEN** a manager has 89,890 € and a 67.2M squad
- **THEN** the maximum bid is 16,892,390 €
- *Verifies:* `test_max_bid_is_cash_plus_a_quarter_of_the_squad`,
  `test_squad_value_sums_catalogue_prices`

### Requirement: The figures check themselves, and doubt is shown, not hidden

Two things can make the rebuild wrong without an error, and each SHALL be
stated on the image rather than left to look like data:

- **The owner's own balance** is the one figure that can be checked. The
  rebuilt value SHALL be compared with `/account`, and the image SHALL say
  whether they match — and by how much they differ when they do not.
- **A movement the rebuild does not know.** Any board entry of a type the
  rebuild does not book money for that nonetheless carries an `amount` — none
  ever has, `bettingPool` included — and any `transfer` of a kind other than a
  plain one or a `clause` SHALL be named on the image as a reason the figures
  may be wrong. The league allows loans and exchanges and neither has been
  seen yet; an exchange would most likely arrive as a new `transfer` kind.

#### Scenario: the self-check and an unknown movement
- **WHEN** the rebuilt owner balance equals `/account` **THEN** the image says
  it matches
- **WHEN** it differs **THEN** the image gives both figures
- **WHEN** an unknown entry type carries an amount **THEN** it is named
- **WHEN** an unknown entry type carries no amount **THEN** it is ignored
- **WHEN** a type that never carried money starts carrying an amount, or a
  `transfer` arrives with an unseen kind **THEN** it is named
- *Verifies:* `test_notes_confirm_a_matching_self_check`,
  `test_notes_give_both_figures_when_the_self_check_fails`,
  `test_an_unknown_type_with_an_amount_is_reported`,
  `test_an_unknown_type_without_an_amount_is_ignored`,
  `test_a_moneyless_type_that_starts_carrying_an_amount_is_reported`,
  `test_a_transfer_of_an_unseen_kind_is_reported`

### Requirement: `/saldos` sends one image to the owner, richest first

`/saldos` SHALL call `POST /league/cash`, which sends one image to the owner's
chat: one row per playing manager (non-playing accounts excluded), with full
euro figures for cash and maximum bid, ordered by maximum bid, highest first.

It goes to `TELEGRAM_CHAT_ID` only, like `/comparar`: the league hides these
numbers from everyone, and the tooling is the owner's edge.

#### Scenario: the command and the order
- **WHEN** `/saldos` is sent **THEN** the bot dispatches `POST /league/cash`
- **WHEN** rows are ranked **THEN** the highest maximum bid comes first
- *Verifies:* `test_saldos_command_dispatches`,
  `test_league_cash_calls_the_action`, `test_league_cash_rejects_get`,
  `test_rows_are_ranked_by_max_bid`, `test_build_cash_image_returns_a_png`

### Requirement: Who can pay a clause of mine, in two tiers

For a clause of the owner's, rivals SHALL be split into those who can pay it
**from cash** and those who can only reach it **by going negative** (cash <
clause ≤ max bid). The second is a lesser threat: a rival still negative when
the matchday starts scores nothing for it. A missing clause is reached by
nobody. A rival under the non-aggression pact SHALL be marked, not dropped —
the pact binds the owner, and nothing says it binds the rival.

#### Scenario: the two tiers
- **WHEN** a clause sits above one rival's cash and below two others' max bid
- **THEN** one is listed by cash, two by max bid
- **WHEN** it sits above every max bid **THEN** nobody reaches it
- *Verifies:* `test_reach_splits_rivals_by_cash_and_by_max_bid`,
  `test_reach_is_nobody_above_every_max_bid`,
  `test_exposure_rows_count_who_reaches_each_top_player`

### Requirement: `/saldos` shows who reaches my best players' clauses

The `/saldos` image SHALL add a second table: the owner's three players with
the best shown projection, each with that projection, its clause, how many
rivals reach it from
cash, how many only by going negative, and whether it is clausable now.

Measured on the day it shipped, every one of the owner's fourteen players was
reachable by three rivals from cash — a warning of "who is at risk" would be
the same fourteen names every morning. So the standing picture lives here, on
demand, next to the figures it is computed from; the digest only speaks when
something changes.

#### Scenario: the block
- **WHEN** the squad has projections **THEN** the three best are shown, best
  first, unprojected players left out
- **WHEN** the block is drawn **THEN** the image grows to hold it
- *Verifies:* `test_exposed_takes_the_best_projections_first`,
  `test_build_cash_image_draws_the_exposure_block`

### Requirement: The digest warns when a protection is about to end

`run_protection_watch`, chained into the daily digest, SHALL send one message
when a player of the owner's has a clause lock (`clauseLockedUntil`) ending
within the next 24 hours **and** some rival could pay that clause, naming the
rivals by tier. Otherwise it SHALL send nothing.

A quiet morning SHALL cost one squad read: the board and the rival squads are
read only once a lock is actually ending. A failure SHALL NOT stop the digest.

#### Scenario: quiet, ending, unreachable
- **WHEN** no lock ends within a day **THEN** nothing is sent and the board is
  not read
- **WHEN** a lock ends and a rival can pay **THEN** the player, clause, the
  moment it opens and the rivals by tier are sent
- **WHEN** a lock ends but nobody can pay **THEN** nothing is sent
- **WHEN** the watch raises **THEN** the digest records it and runs the offers
  step anyway
- *Verifies:* `test_protection_ending_keeps_only_locks_ending_inside_the_window`,
  `test_protection_watch_reads_nothing_more_on_a_quiet_morning`,
  `test_protection_watch_warns_when_a_lock_ends_and_a_rival_can_pay`,
  `test_protection_alert_names_who_can_pay_and_marks_the_pact`,
  `test_protection_alert_is_silent_when_nobody_reaches`,
  `test_run_daily_runs_the_protection_watch_and_survives_its_failure`,
  `test_a_squad_row_carries_the_raw_clause_lock`
