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
| We trade less than the top of the table | 23 market buys and 27 sales, against 51/47 (leader) and 71/65 (second) | `board_archive` |
| Defenders sink against Barcelona and Real Madrid | −3.3 and −2.4 points under their own mean; 9 and 10 of 11 games negative | `scripts/projections/opponent_effect.py` |
| The eleven freezes at the round's first kick-off | `settings.lineupRoundChanges = 0`; the lineup is now also set half an hour before it (`/lineups/kickoff`) | `biwenger-official-rules.md` |

## What is collected every day, without anyone running anything

| Data | Where | Written by | Since |
|---|---|---|---|
| Our projection (blend and Jornada Perfecta alone), then the real points of the whole squad | `proyecciones` | the lineup pick (digest, `/alinear`, kick-off tick) | round 8 (earlier rounds backfilled) |
| Every squad's projected eleven, and what every manager scored | `proyecciones.league_projection`, `actual.league_points` | the same | round 12 |
| Jornada Perfecta's projection for every player | `proyecciones.league_jp` | the same | round 13 |
| Each team's win, draw, loss and clean-sheet chances | `proyecciones.team_outlook` | the same | round 13 |
| Every player's price | `price_snapshots` (60 days) | the trader | 26/10 |
| Every auto-bid placed | `auto_bid_log/{day}/bids` | auto-bid | 25/08 |
| Every money movement in the league | `board_archive/{season}/entries` | the weekly scraper | the start of the season |

## Open measurements

| Question | What would change | Data, and when there is enough | Read with |
|---|---|---|---|
| Does the Oráculo blend beat Jornada Perfecta alone? | `ORACULO_W` stays, or goes to 0 | 10 rounds where the two elevens differ; 2 so far | `report.py`; [projection-ledger.md](projection-ledger.md) |
| What is the squad made of — ceiling, team strength, or the rest of the eleven? | What auto-bid and the trader buy | Next: where our wealth fell behind over the season (`board_archive`), then 8 rounds of `league_projection` | `squad_gap.py`; [squad-composition](../../../openspec/changes/squad-composition/proposal.md) |
| Should the captain, or a close defender call, follow the chance his team wins or keeps a clean sheet? | A tie-break in `lineup._pick_captain` and the eleven | 6–8 rounds of `team_outlook`, from round 13. Expect a small answer: bonuses are worth ~2 points a round | the ledger; [projection-ledger.md](projection-ledger.md) |
| Should a defender facing Barcelona or Real Madrid be benched whatever JP projects? | A lineup rule | Whether JP already discounts the fixture: `league_jp`, from round 13 | `opponent_effect.py`; [the opponent effect](projection-ledger.md#the-opponent-effect) |
| Are the auto-bid shares (T1–T4) right? | The four shares | Settled auctions, monthly; next late November | `scripts/auto_bid/calibrate.py`; [OPERATIONS.md](../../../packages/biwenger_tools/OPERATIONS.md) |
| Is holding a signing 14 days before the trader may sell him too long? | `TRADER_HOLD_DAYS` | Signings with 14 days of prices, late November | `price_snapshots` |
| Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar to start a projected substitute? | The threshold | Promotions against real points; one in twelve months, so seasons | the ledger |
| Should the draft penalise players who rarely start? | `--starts-penalty` on by default | Next pre-season | the draft skill |
| Which of Oráculo's two point scales follows Biwenger's? | Which one the blend reads | Ready now: the page and the API disagree, not by a constant | `core/sdk/oraculo.py` |

Two sightings wait on events rather than rounds: Jornada Perfecta and Biwenger
disagreeing on whether a player is available (one case so far), and a
`nextMatch.status == "break"` on a player we own (none so far). One case is
not a rule.

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
