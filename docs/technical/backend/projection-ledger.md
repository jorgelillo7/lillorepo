# The projection ledger — how to read it

`packages/biwenger_tools/scripts/projections/report.py` compares the eleven
the Oráculo blend picked against the eleven Jornada Perfecta alone would have
picked, using what the players really scored.

**Read this before acting on its output.** The numbers are easy to produce and
easy to misread, and every way of misreading them ends the same way: changing
a dial for a reason that was not there.

## The question it answers, and the one it does not

It answers **"does our blend beat Jornada Perfecta alone?"** That is a question
about our own code, and it has an action attached — if the answer is no,
`ORACULO_W=0` and the system gets simpler at no cost.

It does **not** answer "is Jornada Perfecta accurate" or "is Oráculo accurate".
Grading a provider is auditing somebody else's work and nothing here can act on
the result. A player sent off after ten minutes is noise, not a finding.

## What counts as evidence

Only a round where **the two elevens actually differed**.

Most rounds they agree, and an agreeing round contributes a zero. Averaging
those zeros in moves the answer towards "no effect" by arithmetic rather than
by observation — the more rounds you store, the more confidently wrong that
average becomes. `rounds_compared` is the number that matters; `rounds_stored`
is not.

Backfilled rounds never count. They carry `has_projection: false` because the
projection was gone before the ledger existed, and that is recorded explicitly
so it can never be mistaken for a projection of zero.

## Three ways to misread it

**One round is not a result.** A blend that won a matchday by 12 points won it
because one player had a good afternoon. The script refuses to print a verdict
below `MIN_ROUNDS_FOR_VERDICT` differing rounds for exactly this reason. That
threshold is in `logic/projection_ledger.py` under test, not in the script,
so it cannot be quietly lowered by whoever is impatient.

**A direction is not a proof.** Past the threshold the script prints how often
the blend came out ahead. That is a direction. Football's week-to-week spread
is wide enough that a real edge and a lucky streak look alike for a long time.

**Tuning on this data invalidates it.** Both projections are stored per player,
so any weight can be replayed retrospectively — sweep `ORACULO_W` from 0 to 1
and one value will come out best. With four dials and a dozen observations,
one always does, and it will not repeat next season.

If a weight is going to be chosen from this data, choose it on the early rounds
and judge it on later ones that had no part in choosing it. Anything else
measures how well a number was fitted to the past.

## What a null result means

The most likely outcome is **"no distinguishable difference"**, and that is a
result rather than a failure. `ORACULO_MAX_MOVE` caps how far Oráculo can move
anyone at 25%, so the effect being looked for is small by construction.

If it is indistinguishable, the honest reading is that the blend is not paying
for its complexity, and `ORACULO_W=0` is the conclusion. Knowing that is worth
more than a number that flatters the work.

## Running it

Dry run by default: the grading mode reads, prints, and writes nothing until
`--apply`, which caches each finished round's outcome so a second run never
re-fetches it. A finished round's points do not change.

Per-player points come from Biwenger's public player-detail endpoint, read
**sequentially with a delay** and cached on disk. Parallel reads return 429,
and the budget is shared with the phone app. This is why it is a script run by
hand rather than anything scheduled.

Needs ADC for Firestore (`gcloud auth application-default login`) and Biwenger
credentials in `.env`.

## What is stored

One document per round in `proyecciones`, written by the daily digest **while
the round has not yet kicked off**, overwriting on each run. What survives is
therefore the last projection before Biwenger freezes the eleven — which it
does at the round's first kick-off (`settings.lineupRoundChanges = 0`, see
`biwenger-official-rules.md`). Forcing a digest before kick-off just refreshes
it; running one afterwards writes nothing.

Each document holds both elevens, the per-player projections behind them, and
once graded, the real outcome. 38 documents a season.
