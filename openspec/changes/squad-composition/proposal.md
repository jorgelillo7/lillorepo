# Proposal: what the squad is made of

One question, three candidate answers, one measurement. This change replaces
`value-squad-ceiling`, which proposed the first answer alone.

## Why

The squad the tooling builds scores below the league average almost every
round, while the projection ranks it near the top.

| Round | Our points | Rank (of 7) | League average | Best |
|---|---|---|---|---|
| 1 | 55 | 5 | 60 | 71 |
| 2 | 27 | 7 | 51 | 78 |
| 3 | 51 | 6 | 65 | 93 |
| 4 | 15 | 7 | 57 | 101 |
| 5 | 108 | 1 | 67 | 108 |
| 6 | 48 | 5 | 55 | 80 |
| 7 | 59 | 6 | 66 | 84 |
| 9 | 50 | 6 | 72 | 109 |
| 10 | 58 | 7 | 81 | 134 |
| 11 | 63 | 7 | 90 | 103 |

Below the average in 9 of 10 rounds with data, while `league_compare` put the
squad second by projection. Picking the eleven is not where it is lost: in
hindsight every manager fields 71–80 % of the best eleven his own lineup
allowed, and we field 72 %.

## Three candidate answers

1. **Ceiling.** Rivals win rounds with one or two explosive players; auto-bid
   and the trader rank by mean SF, so they buy a flat squad.
2. **Team strength.** The league's scoring pays +1 for a win, −1 for a loss,
   +1 for playing past 65 minutes and a clean-sheet bonus to keepers and
   defenders, none of which the SofaScore-scale projection carries. A squad
   from losing sides gives those points away.
3. **The rest of the eleven.** The difference is in the players behind the
   best two, whose base SofaScore points fall short of what their projection
   ranked them at.

## Evidence

`scripts/projections/squad_gap.py` splits every manager's round into the
SofaScore base and each bonus. Full run, rounds 1–11 (round 8 has no league
points), all 70 manager-rounds, per round:

| | Points | Base | Play | Win − loss | Clean sheet | Top two |
|---|---|---|---|---|---|---|
| Leader | 74.8 | 64.0 | 9.6 | +1.3 | 1.9 | 31 (41 %) |
| Us | 52.6 | 44.7 | 8.6 | −0.7 | 2.0 | 25 (47 %) |

- **Against answer 2 as the main cause:** of the 22 points a round, the base
  explains 19; win minus loss 2; the rest nothing.
- **Against answer 1 as the main cause:** the leader's best two outscore ours
  by 6 a round, the other nine by 16.
- **For answer 3, and its cause.** Per player fielded, ours score the least in
  the league at defence, midfield and up front. The squad is also the
  cheapest (team value 66 M against 72–110 M), and with cash and clause money
  the poorest manager by 14 M (75 M against 89–140 M). Per million of team
  value it scores 0.80 points a round, the league's middle (0.64–0.96). The
  tooling turns money into points as well as the others; it has less money.

So the squad is weaker because it is cheaper, not because auto-bid buys the
wrong kind of player for the money. Where the wealth went (the draft, trading,
clauses taken from us) is not measured yet.

## Gate: evidence before code

Nothing in auto-bid or the trader changes until these are read:

1. `squad_gap.py` over every finished matchday with no manager-round left out
   (done, above).
2. Where our wealth fell behind: team value plus cash over the season,
   against each rival.
3. 8 rounds of `league_projection` and `league_points` in the projection
   ledger, read with `report.py`: whether the squads projected highest are the
   ones that score highest, and where ours falls.

The answer that survives decides the delta. If it is answer 1, the delta in
`specs/` stands as written. If it is answer 2, a capped team-strength
adjustment replaces it. If it is answer 3, the projection itself is the
suspect, and the next step is grading it player by player, not changing what
auto-bid buys.

## Not in scope

- Changing JP or Oráculo weights. That is the blend's question, graded
  separately by the ledger.
- The lineup pick. Its hindsight efficiency is the league's average.
- The opponent effect (defenders against Barcelona and Real Madrid). It is a
  per-fixture lineup question, measured on its own
  (`projection-ledger.md`, "The opponent effect").
- Reading the next 2–3 fixtures in auto-bid, parked by the owner
  (`PENDING.md`).
- Any automatic tuning of a weight from the same rounds that motivated it.
