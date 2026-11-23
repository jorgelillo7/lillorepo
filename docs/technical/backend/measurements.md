# Measurements — what biwenger_tools is measuring, and why

One page for every open question the platform is answering with data rather
than opinion: what each one asks, what has been learnt so far, where its data
comes from, and what result would change the code. `PENDING.md` keeps one line
per item; this is the map behind those lines. The detail of each measurement
lives where linked.

The rule they all share: **nothing changes a dial until the data says so,
and the data that motivated a change is never the data that judges it.**

## What is already known

Rounds 1–11 of 2026/27, seven managers.

| Finding | Number | Source |
|---|---|---|
| The gap to the leader is the players' base points, not the bonuses | 19 of 22 points a round are SofaScore base; the league's bonuses (play, win − loss, clean sheet) about 2 | `scripts/projections/squad_gap.py` |
| Picking the eleven is not where points are lost | 72 % of the best eleven the lineup allowed, in hindsight; the league ranges 71–80 % | the same |
| The squad is the cheapest, and the manager the poorest | Team value 66 M against 72–110 M; with cash and clause money 75 M against 89–140 M. Per million of team value it scores 0.80 points a round, the league's middle (0.64–0.96) | the same, and `/saldos` |
| Our best two are not the problem; the other nine are | The leader's best two outscore ours by 6 a round, the other nine by 16 | the same |
| Contested auctions were overpaid, by hand | 9.1 M paid over the second bid in 12 contested wins (0.76 M each; the league pays 0.2–0.4 M). The largest (Valverde +3.2 M, Germán Valera +2.5 M, Giuliano +1.3 M) are not in `auto_bid_log`, so they were manual bids | `board_archive` |
| The auto-bid bought on the way down | 8 of our 18 bids with known price trend were on players falling two days running, against 2 of 40 league purchases; two of the three won (Joan García −21.9 %, Koski −18.6 %) lost ~2.4 M | `auto_bid_log`, `price_snapshots` |
| We trade less than the top of the table | 23 market buys and 27 sales, against 51/47 (leader) and 71/65 (second) | `board_archive` |
| Our wealth gap is the market, not the prizes | Take each manager's wealth now (squad value plus cash), remove the 50 M start, round prizes and bonuses, and add back clause raises: the market made +45.0 M for the second, +36.6 M for the leader, −38.5 M for us. We collected the most in round prizes (62.4 M). The rebuilt cash matches `/saldos` to the euro | `board_archive` and today's prices |
| The loss is buying dear and selling cheap | Market buys we later sold: −17.5 M, of which −15.7 M is six August–September signings (Valverde −4.1, Parrott −3.2, Chupe −2.6, Calatrava −2.3, Giuliano −2.2, Galilea −1.3). The leaders made +38 to +40 M the same way. Clause signings cost everyone about the same (−24 M held, ours included) | the same |
| The most profitable trader buys cheap, many, and holds ~10 days | Second place: 71 buys at 3.0 M on average, sells 86 % at a profit, +0.68 M each, 10 days median. Us: 23 buys at 4.5 M, 29 % at a profit, −1.03 M each, 17 days. The trader's own sales since 22/10 are all up (+1.4 M) | the same |
| Defenders sink against Barcelona and Real Madrid | −3.3 and −2.4 points under their own mean; 9 and 10 of 11 games negative | `scripts/projections/opponent_effect.py` |
| A long injury is a sale only in rounds missed | Lemar (9/11, back ~25/11) was 16 days out but missed one round: the international break leaves round 13 (20/11) before round 14 (27/11) | the trader's rounds; JP `estimatedReturn` |
| The round prize is the mirror position's points × 75 k | Round 11: last on 63, paid 7.725 M = the winner's 103 × 75 k; other managers within a few points (bonuses on top) | `board_archive` |
| The eleven freezes at the round's first kick-off | `settings.lineupRoundChanges = 0`; the lineup is now also set half an hour before it (`/lineups/kickoff`) | `biwenger-official-rules.md` |
| Auto-bid loses auctions by a wide margin, not by a crumb | Since 22/10 (61 priced auctions) our five losses went to bids of +12 to +26 % against our +3 to +6 %; the three wins at +6 % beat a runner-up at +0 to +1.3 %. A point or two on any share would have changed none. The shares stay +15/+8/+6/+5 % (fourth reading, 23/11, 251 priced) | `scripts/auto_bid/calibrate.py`, `auto_bid_log` |
| Seven days is the better sale hold | Replaying the trader's two-day-fall sale on 44 league purchases in `price_snapshots`: a 7-day hold beat 14 in 20 of the 22 where they differ, +4.4 M over 21 days (≈7 % of the price), and 12 of 13 over 28 days. Shorter holds score higher still, but the hold is there so projection noise does not undo a signing, so it stays at 7 | `price_snapshots`, `board_archive` |

## What is collected every day, without anyone running anything

| Data | Where | Written by | Since |
|---|---|---|---|
| Our projection (blend and Jornada Perfecta alone), then the real points of the whole squad | `proyecciones` | the lineup pick (digest, `/alinear`, kick-off tick) | round 8 (earlier rounds backfilled) |
| Every squad's projected eleven, and what every manager scored | `proyecciones.league_projection`, `actual.league_points` | the same | round 12 |
| Jornada Perfecta's projection for every player | `proyecciones.league_jp` | the same | round 13 |
| Each team's win, draw, loss and clean-sheet chances | `proyecciones.team_outlook` | the same | round 13 |
| Oráculo's points as its page and its API give them | `proyecciones.oraculo_scales` | the same | round 13 |
| Every player's price | `price_snapshots` (60 days) | the trader | 26/10 |
| Every auto-bid placed | `auto_bid_log/{day}/bids` | auto-bid | 25/08 |
| Every money movement in the league | `board_archive/{season}/entries` | the weekly scraper | the start of the season |

## Open measurements

| Question | What would change | Data, and when there is enough | Read with |
|---|---|---|---|
| Does the Oráculo blend beat Jornada Perfecta alone? | `ORACULO_W` stays, or goes to 0 | 10 rounds where the two elevens differ; 2 so far | `report.py`; [projection-ledger.md](projection-ledger.md) |
| What is the squad made of — ceiling, team strength, or the rest of the eleven? | What auto-bid and the trader buy | Where the wealth fell behind is answered (above). Next: 8 rounds of `league_projection` | `squad_gap.py`; [squad-composition](../../../openspec/changes/squad-composition/proposal.md) |
| Should the captain, or a close defender call, follow the chance his team wins or keeps a clean sheet? | A tie-break in `lineup._pick_captain` and the eleven | 6–8 rounds of `team_outlook`, from round 13. Expect a small answer: bonuses are worth ~2 points a round | the ledger; [projection-ledger.md](projection-ledger.md) |
| Should a defender facing Barcelona or Real Madrid be benched whatever JP projects? | A lineup rule | Whether JP already discounts the fixture: `league_jp`, from round 13 | `opponent_effect.py`; [the opponent effect](projection-ledger.md#the-opponent-effect) |
| Is two rounds missed the right line to sell an absence, and 6.4 M the right star line? | `TRADER_ABSENCE_ROUNDS`, `TRADER_STAR_PRICE` | Since 9/11. Check each "baja larga" sale against the player's price when he came back | the trader's Telegram plan, `price_snapshots` |
| Does bidding the tier above for a better captain under 3 M pay? | The captain upgrade in auto-bid | Since 9/11. Late November: the upgraded signings, whether they captained, and their points as captain against the 383 they replaced | `auto_bid_log` labels, the ledger's captain |
| Does bidding a falling player only his price and a crumb lose the right auctions? | `FALLING_DAYS` / `FALLING_OVERBID` | Since 9/11 a player falling two days running is bid +1 % instead of his tier's share, on 40 league purchases (2 of fallers) and our own 8 falling bids (two of three wins lost ~20 %). 23/11: no falling bid since 9/11 (every logged bid carries its tier's share), so nothing to judge yet | `auto_bid_log`, `price_snapshots` |
| Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar to start a projected substitute? | The threshold | Promotions against real points; one in twelve months, so seasons | the ledger |
| Should the draft penalise players who rarely start? | `--starts-penalty` on by default | Next pre-season | the draft skill |
| Does the blend, now SofaScore-only, beat Jornada Perfecta alone? | `ORACULO_W` kept or 0 | Until 9/11 it read Oráculo in Diario AS (the predictions page's only scale). Since then it reads SofaScore points for the ~40 players on Oráculo's lists and JP alone for the rest. Graded with the blend question above, from round 13 | `report.py`; [the routes](../../external/analitica-fantasy-api.yaml) |

Two sightings wait on events rather than rounds: Jornada Perfecta and Biwenger
disagreeing on whether a player is available (one case so far), and a
`nextMatch.status == "break"` on a player we own (none so far). One case is
not a rule.

## Monthly review

The open questions `PENDING.md` folds into one monthly line. Read them together, late each month, and move a row out when it leads to a change or to "leave it".

| | Question | Data so far and how to read it |
|---|---|---|
| ⏳ | Is 16 the right squad floor (`TRADER_MIN_SQUAD`, raised from 14 on 11/11)? | **23/11: not enough data.** The squad sat at 15 on all but three days since 11/11 (no cash to buy), so the floor blocked every trader sale: none since 13/11. What it cost so far is one bench faller held, Tenaglia (−0.24 M from his first two-day fall); the other bench players rose. The other half, how often a reserve came on, needs `squad_gap.py` over rounds 12+ (its player cache is empty, ~200 reads, so a run of its own). Late December: both halves over rounds 12–16 |
| ⏳ | Are two rounds missed (`TRADER_ABSENCE_ROUNDS`) and 6.4 M (`TRADER_STAR_PRICE`) the right lines for selling an absence? | Since 9/11 · each "baja larga" sale against the player's price when he came back · **23/11: one sale**, Lemar (9/11, 4.17 M; 4.51 M today, +8 %, back ~25/11). One case is not a line; late December with the trader's other checks · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Does auto-bid's captain upgrade (the tier above for a player under 3 M who would captain better than the squad's best) pay? | Since 9/11 · the upgraded signings, how often they captained, their points as captain · **23/11: none.** No bid in `auto_bid_log` carries the upgraded share, and auto-bid has placed no bid since 12/11 (cash 0.56 M or negative every morning). It cannot be measured until there is cash to bid with · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Does the Oráculo blend beat Jornada Perfecta alone? (`ORACULO_W` stays, or goes to 0) — **until 9/11 it blended Oráculo's Diario AS points**; since then SofaScore for the ~40 listed players, JP alone for the rest, so grade rounds 13+ apart from the earlier ones | 10 rounds where the two elevens differ, graded by the projection ledger — 3 so far (J10 −9, J11 +3, J12 −5), none yet from round 13; 7 to go, so not before late January at one differing round in two · read with `report.py`, [how](docs/technical/backend/projection-ledger.md) |
| ⏳ | What the squad is made of: why it scores below average while projected near the top | **Measured, rounds 1–11, all managers** (`scripts/projections/squad_gap.py`): the base SofaScore explains 19 of the 22 points a round to the leader, bonuses ~2; picking the eleven is at the league's average (72 % of hindsight, range 71–80 %); per million of team value the squad scores at the league's middle, but it is the cheapest (66 M against 72–110 M) and, with cash, the poorest manager (75 M against 89–140 M). **Where the wealth went**: market flips — −17.5 M for us (six August–September signings bought dear, −15.7 M) against +38–40 M for the two leaders; the trader's own flips since 22/10 are all up. **Round 12, the first with `league_projection`: our eleven projected last (SF 4,752 against 5,034–5,993) and finished last (50)**, so "projected near the top" no longer holds; the gap is now in the projection too. Next: 7 more rounds of `league_projection` · [`openspec/changes/squad-composition/`](openspec/changes/squad-composition/proposal.md) |
| ⏳ | Captain (and close defender calls) by the chance his team wins or keeps a clean sheet | 6–8 rounds of `team_outlook` in the projection ledger, captured from round 13 — **none graded on 23/11** (round 13 still playing) · free: Analítica Fantasy's calendar predictor, already the Oráculo source · expected gain is small (bonuses ~2 pts a round; captain tie-breaks ~0.5–1.5 by a review's estimate), so it ships only if the graded rounds show it · [what is stored](docs/technical/backend/projection-ledger.md) |
| ⏳ | Should a defender facing Barcelona or Real Madrid be benched whatever JP projects? | **Measured, the effect is real**: re-read 23/11 through round 12: defenders score −3.7 (Barcelona) and −2.5 (Madrid) SofaScore points under their own mean, defenders and keepers together negative in 10 of 12 games against each; keepers only against Barcelona (−5.1). What decides a rule is whether JP already discounts it — 5 own-squad cases say no; `league_jp`, captured from round 13, gives the sample — none yet on 23/11 · `scripts/projections/opponent_effect.py`, [how to read it](docs/technical/backend/projection-ledger.md#the-opponent-effect) |

## Two auto-bid changes dropped

Both were parked, and both were dropped after the 23/11 review. These are the reasons, and when either one would be worth reopening.

- **Bid above the cash when the signing would start.** The constraint the review found is not one skipped starter but the wallet: auto-bid has placed nothing since 12/11 and the squad has sat at 15, under the 16 floor, so the trader cannot sell either. A bid above the cash then needs a sale to cover it, which the floor forbids until the squad reaches 17, and the balance would still be negative at kick-off. It adds nothing while the squad is the league's poorest; reopen it only if cash and the floor stop binding.
- **Read the next 2–3 fixtures.** The fixture effect that has been measured is the defenders' against Barcelona and Madrid (−3.7 and −2.5 a game); midfielders and forwards move by 1–1.6 against any side. Whether Jornada Perfecta already prices it has no sample yet. If it does, a longer horizon adds little; if it does not, the cheaper first step is the lineup rule of the defenders question, not a change to bids that are not being placed. Fold it into that question rather than keep it as a separate change.

## What was looked at and left out

| Source | Why not |
|---|---|
| Analítica Fantasy's power ranking | No starter information: it ranked Espanyol's benched keeper first |
| Analítica Fantasy's saves and rating leaderboards | Season averages the projections already contain; saves track a keeper who is shot at, not one who keeps a clean sheet |
| Analítica Fantasy's per-match probable lineups | A second opinion on starters, which Oráculo's `chance` and Jornada Perfecta already give; a per-match page scrape for little more |
| Oráculo's own captain list | Every player on it costs more than the league's 3 M captain cap |
| A betting-odds provider | The calendar predictor gives win and clean-sheet chances for free, and the bonuses they price are worth about 2 points a round |

## Before running a script

The player-detail endpoint shares a small window with the phone app: a run of
about 200 reads was answered 429, and the public host then refused that
machine for at least an hour, competition data included. Every script reads
sequentially, caches on disk and stops at the first 429. The authenticated
host (`biwenger.as.com`) serves the same player detail and kept answering.
Scripts run on the lock, never the Mac's Python (`CLAUDE.md`).
