# Proposal: value a squad's ceiling, not only its average

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
squad second by projection.

Round 11 shows the likely mechanism:

- **Our players score what they are projected.** About 1.1 real points per
  100 SF across the rounds the projection ledger holds. The eleven projected
  ~56 and scored 63.
- **The rivals win with one or two explosive players** each round: Raphinha
  16, Fermín 17, Mbappé 12, Gordon 13, Satriano 13, Arda Güler 12. Our best
  was 12, the rest of the eleven 1–7.
- **The squad is flat.** Auto-bid and the trader rank candidates by mean SF,
  so they buy many SF 400–500 players. That sums to a high projection and
  finishes last.

This is a hypothesis from eleven rounds, ten of them before any rival
projection was recorded, so it stays a proposal until the ledger shows it.

## What changes

When the evidence below holds, candidate evaluation in auto-bid (and in the
market trader, which shares its ruler) also weighs a player's **ceiling**: how
often he has a big round, not only his mean. Between two candidates of similar
projection, prefer the one who can win a round. A flat SF 450 that will not
make a difference loses its bid to a slightly lower SF with a real chance of
15.

The lineup pick is not changed: for one round, the best expected eleven is
still the right eleven. The change is about which players the squad is made of.

## Gate: evidence before code

The projection ledger now records every squad's projected eleven and every
squad's real points per round (`league_projection`, `league_points`). This
change starts only if, over at least **8 rounds** with both halves recorded:

1. our squad's projected rank is in the top 3 in most of them, while its real
   rank is in the bottom 3 in most of them; **and**
2. the rounds' winners get a clearly larger share of their points from their
   top two players than our squad does.

If (1) holds and (2) does not, the problem is not the squad's shape, and this
proposal is withdrawn rather than implemented.

## Not in scope

- Changing JP or Oráculo weights. That is the blend's question, graded
  separately by the ledger.
- The captain. The league's under-3M captain rule leaves too little room.
- Any automatic tuning of the new weight from the same rounds that motivated
  it.
