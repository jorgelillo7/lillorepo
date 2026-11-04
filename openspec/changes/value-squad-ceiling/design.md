# Design notes: value-squad-ceiling

## Measuring a ceiling

| Option | Source | Cost | Weakness |
|---|---|---|---|
| Share of a player's recent rounds with ≥ 10 points | `fitness` in the competition payload: the last five rounds' points, already read every morning | None | Five rounds is little; the base scoring, not the league's custom one |
| 90th percentile of his season's points | Player-detail reports | One read per candidate, on the endpoint shared with the phone app (~500 per 8 h) | Too costly for every market candidate every day |
| On an Oráculo captain or star list | Already in the rows (`oraculo_lists`) | None | A proxy, chosen by somebody else's model |
| Position | Known | None | Coarse: a forward is not explosive by being a forward |

The likely first cut is the first option, with the Oráculo lists as a
tie-breaker. It is free, and it is the same data the morning already reads.

## Where it weighs

Inside the existing tier and eleven rules, not around them. It acts as a
bounded adjustment to the SF a candidate is ranked by, capped like
`ORACULO_MAX_MOVE` is today. A cap keeps a single hot fortnight from buying a
bench player at T1 prices.

## What it must not do

- Raise the price paid for a player. Tiers price a bid. The ceiling only
  reorders candidates and breaks near-ties.
- Override the "would make the eleven" rule for T3/T4. A ceiling on the bench
  scores nothing.
- Be tuned on the rounds that motivated it. Choose the weight from early
  rounds and judge it on later ones (`projection-ledger.md`, "Tuning on this
  data invalidates it").

## Alternatives considered

- **Do nothing; it is variance.** Possible. Nine of ten rounds below average
  is unlikely to be luck alone, but the ranks are correlated week to week
  (same squad), so the gate asks for the league comparison rather than
  trusting the streak.
- **Buy stars outright.** The budget does not allow a T1 every week. The point
  is preferring ceiling among the players the budget already reaches.
