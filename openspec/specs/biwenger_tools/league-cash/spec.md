# Capability: league-cash

Every manager's cash and maximum bid, which the league hides
(`settings.balance = "hidden"`): no endpoint returns a rival's balance. It is
rebuilt from the league board, where Biwenger logs every movement of money,
and sent as one image to the owner's chat on `/saldos`. The same figures warn
the owner, in the daily digest, when one of their players is about to lose
its clause protection.

Rebuilt from scratch on every request, from the live board plus the scraper's
append-only copy of it (`board_archive/{season}/entries`), which fills in what
Biwenger no longer returns. No balance is stored, so a rebuild cannot drift
the way an incremental ledger could; the whole read is ~15 sequential requests
and one Firestore list in under 5 seconds.

- **Source:** `packages/biwenger_tools/api/logic/league_cash.py` (pure),
  `packages/biwenger_tools/api/logic/board_archive_store.py`,
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

`/saldos` SHALL rebuild from the live board merged with
`board_archive/{season}/entries`, deduplicated by `board_entry_key`. Entries
older than the latest `seasonStarted` SHALL be ignored. When neither the read
nor the archive contains a `seasonStarted` entry, it SHALL raise rather than
return figures, since the rebuild would be missing the season's first movements.

The board is paged newest first and SHALL stop at the page that contains
`seasonStarted` — a full-history read is ten times the requests for entries
that are then discarded.

When the archive holds entries of the current season the live board no longer
returns, the image SHALL say how many, next to the self-check: the figures are
still right, and the note is the early warning that Biwenger has started to
forget. When the
archive cannot be read, the rebuild SHALL use the live board alone and the
image SHALL say the archive was not read — the answer is no worse than
without an archive, and it does not pretend to be protected.

#### Scenario: last season's movements, a short read, and a forgetful board
- **WHEN** the read holds entries from before the latest season start
- **THEN** they do not move anyone's cash
- **WHEN** neither the read nor the archive contains a `seasonStarted` **THEN**
  it raises
- **WHEN** the live board lost September's transfers the archive holds **THEN**
  the cash is the same as from the full board, and the image says entries were
  filled from the archive
- **WHEN** the live board no longer reaches `seasonStarted` but the archive
  holds it **THEN** the rebuild still answers
- **WHEN** the archive cannot be read **THEN** the live board alone answers and
  the image says so
- *Verifies:* `test_entries_before_the_season_start_are_ignored`,
  `test_a_read_that_never_reaches_the_season_start_raises`,
  `test_get_all_board_messages_stops_at_the_page_holding_until_type`
  (`core/tests/test_biwenger_client.py`),
  `test_the_archive_fills_what_the_live_board_lost`,
  `test_archived_entries_the_board_lost_are_reported`,
  `test_the_union_still_needs_a_season_start`,
  `test_the_archive_fills_a_lost_season_start`,
  `test_an_archived_older_season_is_not_counted_as_lost`,
  `test_nothing_lost_says_nothing_about_the_archive`,
  `test_an_unreadable_archive_is_said_not_hidden`,
  `test_league_money_adds_what_only_the_archive_holds`,
  `test_an_unreadable_archive_leaves_the_live_board_and_says_so`
  (`api/tests/test_actions.py`)

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
  plain one, a `clause` or an `immediateSale` (a sale straight to the market,
  no buyer, booked like any sale) SHALL be named on the image as a reason the
  figures may be wrong. The league allows loans and exchanges and neither has been
  seen yet; an exchange would most likely arrive as a new `transfer` kind.
  The scraper archives such an entry too, so fixing the rule later can still
  count it.

#### Scenario: the self-check and an unknown movement
- **WHEN** the rebuilt owner balance equals `/account` **THEN** the image says
  it matches
- **WHEN** it differs **THEN** the image gives both figures
- **WHEN** an unknown entry type carries an amount **THEN** it is named
- **WHEN** an entry with no type at all carries an amount **THEN** it is named
  too (as `None`), and the note still renders
- **WHEN** an unknown entry type carries no amount **THEN** it is ignored
- **WHEN** a type that never carried money starts carrying an amount, or a
  `transfer` arrives with an unseen kind **THEN** it is named
- *Verifies:* `test_notes_confirm_a_matching_self_check`,
  `test_notes_give_both_figures_when_the_self_check_fails`,
  `test_an_unknown_type_with_an_amount_is_reported`,
  `test_an_untyped_entry_with_an_amount_is_reported_not_a_crash`,
  `test_an_unknown_type_without_an_amount_is_ignored`,
  `test_an_immediate_sale_pays_the_seller_and_is_not_reported`,
  `test_a_moneyless_type_that_starts_carrying_an_amount_is_reported`,
  `test_a_transfer_of_an_unseen_kind_is_reported`

### Requirement: `/saldos` sends one image to the owner, richest first

`/saldos` SHALL call `POST /league/cash`, which sends one image to the owner's
chat: one row per playing manager (non-playing accounts excluded), with full
euro figures for cash, money in clauses and maximum bid, ordered by maximum
bid, highest first. Money in clauses is what each manager has put into raising
the clauses of the squad he holds today (`owner.invested`, from the squad reads
the image already makes); it is already out of his cash, and lowering a clause
gives back 75 % of it on the spot.

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
clause ≤ max bid). Cash here SHALL include the 75 % a rival gets back by
lowering his own raised clauses, since he can do it the same minute. The second is a lesser threat: a rival still negative when
the matchday starts scores nothing for it. A missing clause is reached by
nobody. A rival under the non-aggression pact SHALL be marked, not dropped —
the pact binds the owner, and nothing says it binds the rival.

#### Scenario: the two tiers
- **WHEN** a clause sits above one rival's cash and below two others' max bid
- **THEN** one is listed by cash, two by max bid
- **WHEN** it sits above every max bid **THEN** nobody reaches it
- **WHEN** a rival's cash falls short but his cash plus 75 % of his money in
  clauses does not **THEN** he is listed by cash
- *Verifies:* `test_reach_splits_rivals_by_cash_and_by_max_bid`,
  `test_reach_counts_what_a_rival_can_take_back_out_of_his_clauses`,
  `test_money_in_clauses_is_summed_and_three_quarters_come_back`,
  `test_build_cash_image_shows_money_in_clauses`,
  `test_reach_is_nobody_above_every_max_bid`,
  `test_exposure_rows_count_who_reaches_each_top_player`

### Requirement: `/saldos` shows who reaches my best players' clauses

The `/saldos` image SHALL add a second table: the owner's three players with
the best shown projection, each with that projection, its market value, its
clause, how many
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

`run_protection_watch`, chained into the daily digest, SHALL send one short
message when a **starter of the best eleven** has a clause lock
(`clauseLockedUntil`) ending within the next 24 hours **and** some rival has
the **cash** to pay that clause — one line per player under one heading with
the moment the clauses open. Otherwise it SHALL send nothing.

Two things stay out on purpose, because the message used to list all twelve
players and went unread. A bench player taken by a clause pays his clause,
usually far above his value: that is money, not a threat. And a rival who
could pay only by going negative is not named: every rival always can.

A quiet morning SHALL cost one squad read: the board and the rival squads are
read only once a lock is actually ending. A failure SHALL NOT stop the digest.

#### Scenario: quiet, ending, unreachable
- **WHEN** no lock ends within a day **THEN** nothing is sent and the board is
  not read
- **WHEN** a starter's lock ends and a rival has the cash **THEN** one line
  names the player, the clause and the rivals, pacts marked
- **WHEN** rivals could pay only by going negative **THEN** they are not named,
  and with nobody else nothing is sent
- **WHEN** the player is on the bench **THEN** he is not named
- **WHEN** the watch raises **THEN** the digest records it and runs the offers
  step anyway
- *Verifies:* `test_protection_ending_keeps_only_locks_ending_inside_the_window`,
  `test_protection_watch_reads_nothing_more_on_a_quiet_morning`,
  `test_protection_watch_warns_when_a_lock_ends_and_a_rival_can_pay`,
  `test_protection_alert_names_who_can_pay_with_their_cash_and_marks_the_pact`,
  `test_protection_alert_leaves_out_who_could_only_pay_by_going_negative`,
  `test_protection_alert_is_silent_when_no_rival_has_the_cash`,
  `test_protection_alert_names_only_the_starters`,
  `test_protection_alert_is_one_line_per_player_under_one_heading`,
  `test_run_daily_runs_the_protection_watch_and_survives_its_failure`,
  `test_a_squad_row_carries_the_raw_clause_lock`

---

### Requirement: The public `/saldos` is the league's figures, never the owner's edge

The public variant SHALL send the same table the owner gets: every playing
manager's cash, money in clauses and maximum bid, with the trust notes. It
SHALL send it to the chat that asked, never to the owner's. The block about
the owner's best players and who reaches their clauses SHALL NOT be drawn,
because it is the owner's information about his own team. No projection
SHALL appear.

A failure SHALL reach the member only as "no disponible ahora". The detail
goes to the logs.

#### Scenario: the public image
- **WHEN** a public member asks for `/saldos` **THEN** the image reaches his
  chat, with the table and notes and without the exposure block
- **WHEN** the owner asks **THEN** his image still carries the exposure block
- **WHEN** the read fails **THEN** the member gets a short unavailable note
  and no exception text
- *Verifies:* `test_public_league_cash_goes_to_the_asking_chat`,
  `test_public_league_cash_draws_no_exposure_block`,
  `test_owner_league_cash_keeps_the_exposure_block`,
  `test_public_league_cash_failure_says_unavailable`

### Requirement: `/movimientos` lists the last 24 hours of the board

A league mate asked to hear of every movement. Polling the board for it would
spend about a hundred requests a day of an account window shared with the
phone app. `/movimientos` SHALL answer on demand instead, with the board
entries of the last 24 hours, newest first:

- market buys and sales, immediate sales and admin transfers included;
- clausulazos;
- clause raises.

Each line SHALL name the managers, the player and the amount. Round payouts,
bonuses and text posts SHALL NOT be listed. An empty window SHALL say so
rather than send nothing.

The read SHALL stop at the first page that reaches past the window, not walk
the season.

#### Scenario: what is listed
- **WHEN** the last 24 hours hold a sale, an immediate sale, a clausulazo, a
  clause raise and a round payout **THEN** the first four are listed, newest
  first, and the payout is not
- **WHEN** an entry is older than 24 hours **THEN** it is not listed
- **WHEN** nothing moved **THEN** the reply says there were no movements
- **WHEN** the newest page already reaches past the window **THEN** no second
  page is read
- *Verifies:* `test_movements_list_trades_clauses_and_raises_newest_first`,
  `test_movements_leave_out_payouts_and_posts`,
  `test_movements_older_than_a_day_are_not_listed`,
  `test_movements_say_so_when_nothing_moved`,
  `test_movements_stop_reading_at_the_window`

### Requirement: Public reads are cached, the owner's stay fresh

Every fresh read is paid from the owner's Biwenger account. A public
`/saldos` or `/movimientos` SHALL reuse a read made in the last few minutes,
so repeated taps inside the window cost no Biwenger request.

The owner's own `/saldos` SHALL keep reading fresh. He reads it right after a
clausulazo to decide the next one, and a figure five minutes old is the wrong
one then. His read refreshes the cache the public variant draws on.

The cache SHALL hold however the taps arrive:

- **Across instances.** The bot and api run on Cloud Run, where two taps can
  land on two containers. A cache held in one process would let each of them
  read Biwenger, so the cached read SHALL be shared through Firestore.
- **At the same moment.** Taps that arrive while a read is under way SHALL
  wait for it and use it, never start a second one.
- **When Biwenger fails.** A failed read SHALL also be remembered for a
  short while, and a public caller inside that while gets "no disponible
  ahora" without a new request. Tapping through a `429` would dig the
  account deeper into a window it shares with the phone app.

#### Scenario: a second tap is free, the owner is never served stale
- **WHEN** a member asks for `/saldos` twice inside the window **THEN** the
  board and the squads are read once
- **WHEN** the owner asks inside the window **THEN** Biwenger is read again,
  and a member asking next is served that newer read
- **WHEN** `/movimientos` is asked twice inside the window **THEN** the board
  is read once
- **WHEN** two public taps arrive while one read is under way **THEN** one
  Biwenger read serves both
- **WHEN** the cached read was written by another instance **THEN** it is
  reused, not read again
- **WHEN** the last read failed a moment ago **THEN** a public tap gets the
  unavailable note and makes no request
- *Verifies:* `test_public_league_cash_reuses_a_recent_read`,
  `test_owner_league_cash_always_reads_fresh_and_refreshes_the_cache`,
  `test_movements_read_is_cached`,
  `test_concurrent_public_taps_share_one_read`,
  `test_a_read_cached_by_another_instance_is_reused`,
  `test_a_recent_failure_is_not_retried_by_public_taps`
