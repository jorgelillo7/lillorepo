# Emergency rebuild mode

## Why

`/emergencia` models "a player was taken from me". After a raid the real
problem is "my squad can no longer field an eleven", and the two stop being
the same thing the moment more than one player goes.

Today, with seven losses, the flow asks which line to reinforce, buys **one**
player, and stops. The other six holes are never revisited — nothing persists
between the selector and the execution. Worse, the single pick is ranked by
predicted points with price used only as an affordability cut-off, so a manager
sitting on the cash of seven clause payments is steered at the most expensive
rival on the board. The money that had to cover seven holes goes into one.

Nothing in the flow ever checks that the squad can still field a legal eleven.
The repo owns that primitive twice over — `lineup.xi_snapshot`, which
`/ofertas` already calls to refuse a deal that breaks the eleven, and the
draft's composition feasibility check — and the emergency path imports neither.

## What changes

When the squad **cannot field any legal eleven**, `/emergencia` stops proposing
a signing and proposes a **plan**: the set of players that restores an eleven
plus two substitutes, ordered so the holes that block every formation are
filled first, with the budget for the remaining holes reserved before each
purchase, ranked by points per euro rather than raw points, and shown with the
eleven it would produce before a single euro moves.

Below that threshold — a loss the squad can still absorb — nothing changes.
The one-player flow is right when there is one hole and money to spare.

Three defects in the code this replaces are fixed with it:

- Two goalkeeper losses currently answer *"sin clausulazos recientes contra ti"*
  — a denial that the raid happened, at the worst possible moment.
- The goalkeeper line can be targeted, against the rule the code's own comment
  states.
- `force_position` outside 1-4 raises `KeyError` instead of answering 400.

## What does not change

- The one-loss flow, its selector, and its confirmation.
- `/recomendar`, which is advisory and never spends.
- Execution remains manual: nothing is bought without an explicit confirmation.
