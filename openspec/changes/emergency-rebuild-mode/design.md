# Design notes

## Why the trigger is "no legal eleven", not a count of losses

A count is a proxy. Three losses out of a deep squad leave a team that plays on
Saturday; two losses that empty the defence do not. `lineup` already answers the
real question — whether any of its formations can be filled from the players
that remain — so the trigger is that answer, not an arithmetic threshold on
losses.

It also makes the mode reachable when it should be and unreachable when it
should not: a squad broken by sales, or by losses older than the detection
window, still gets the rebuild, because the trigger reads the squad rather than
the board.

## Why the budget is reserved, not spent greedily

This is the whole point of the change. Ranking by predicted points and cutting
at affordability is correct with one hole: buy the best thing you can pay for.
With seven holes it is the failure — the first purchase is the best player the
whole budget can buy, and the remaining six holes are then unaffordable.

Reserving turns a sequence of local choices into one feasible plan: before
committing to a hole, the cheapest credible candidate for **each** remaining
hole is held back, and only what is left is spendable now. A star signing that
would leave a hole unfillable is not affordable, however much cash is on screen.

Ranking inside that band is by points per euro rather than raw points, for the
same reason: when money is the binding constraint, the metric that spends it
well is value, not quality.

## Why the goalkeeper is never bought

A league rule, enforced by the admin rather than by Biwenger: a manager's
**only** goalkeeper cannot be claused — an attempt is cancelled and penalised.
No raid can therefore leave a squad with zero goalkeepers, and one goalkeeper is
all an eleven needs. A second is a comfort the rebuild's money is always better
spent elsewhere.

This is also why the goalkeeper line is never a blocking hole, and why the
existing intent resolution targeting position 1 after a goalkeeper loss is a
defect and not a feature.

## Why the plan is proved before it is offered

A plan that spends the budget and still cannot field an eleven is worse than no
plan, because it looks like progress. Running the same eleven-picking logic over
the squad the plan would produce is the only honest way to make the claim, and
it costs nothing — the code already exists for `/ofertas`.

When the budget cannot reach a legal eleven at all, the plan is still shown,
labelled as incomplete. Refusing to help a manager who cannot afford a full
recovery would leave them with nothing; claiming an eleven that is not there
would be a lie. Saying "this is as far as your money goes" is neither.

## Why execution re-plans between purchases

Clause values move and rivals sell. A plan approved thirty seconds ago can have
a hole in it by the third purchase, and a flow that discovered this by failing
would leave the squad half-rebuilt with the money already spent. Re-planning
between purchases keeps the remaining reserve honest; substituting only within
the same position and the amount already reserved for it keeps the approved
plan's shape, so what executes is still what was agreed.

## Deliberately not handled

- **The clause freeze.** Clauses freeze 24 h before a matchday's first kick-off,
  so a rebuild has a deadline the code does not know about. It is stated in
  `STATUS.md` as an assumption drawn from the platform's behaviour rather than
  read from the API, and inventing a deadline from an unverified rule is worse
  than leaving the manager to judge the clock.
- **Selling to raise money.** The plan spends what is in the account; it never
  proposes selling to afford a signing.
- **The cash floor's value.** That the plan prefers to keep one is behaviour;
  how much it keeps is a tuning constant, and a percentage of a raid windfall
  would reserve absurd amounts. A flat figure in config, in the region of a
  cheap clause, is the recommendation.

## Why the floor yields to the eleven

The floor buys the ability to retaliate; the eleven buys points every matchday.
Ranked against each other they are not close, so the cushion is what survives
out of the money the plan did not need — never a wall the plan stops in front
of. It is still worth keeping when it is free to keep, and worth reporting when
it is spent, because a manager left without cover should know it.
