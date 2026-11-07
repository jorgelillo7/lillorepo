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

## What happens without anybody running anything

Both halves are automatic, and both hang off the lineup pick — the daily
digest chains it, and forcing `/alinear` triggers it too:

- **The projection** is captured while the round has not kicked off,
  overwriting on each run.
- **The outcome** of **one** finished round that has none yet is collected
  per run, oldest first. One at a time so a backlog drains a round a day
  rather than spending a morning's request budget at once — the player
  endpoint's rate limit is shared with the phone app.

A round is only collected once Biwenger reports it **finished**. Under
*jornada única* it is not final until every match in it is played, so reading
it early would store a partial total as though it were the result.

If any fielded player's report is missing, the whole round is **refused**
rather than stored short. An absent report scores zero, which is the same
number as a dreadful afternoon, so a partial read would become a result
nobody ever questioned. Leaving it pending costs a day and cannot lie.

A refusal is retried each morning for a week after the round's capture, long
enough for a late report. After that it is stored as final — the reason and
who had no report, no points — and the round is not read again. A split round
needs this: Biwenger filed a postponed match under round 5176 while ten of the
eleven fielded had played their matchday under 5125, so their reports never
reach 5176 and every retry re-read twenty players for nothing. Each run logs
what the capture and the collection did (`Projection ledger ran.`).

## Running the script

The script remains for reading the comparison, and for backfilling rounds
that finished before the ledger existed. Dry run by default: it prints and
writes nothing until `--apply`.

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

Per player: JP's number, Oráculo's points, chance and **the Oráculo lists he
was on** (`oraculo_lists` — the ⭐ in the lineup message), and the blend. The
outcome's `player_points` covers **the whole squad**, not only the eleven
fielded: until 25/10 only the eleven were scored, so Yuri's 21 from the bench
— on two Oráculo lists, projected 321 — left no trace, and the ledger could
never learn from who was left out. Bench reads cost one request per extra
player, once per finished round. `applied_total` is still the eleven's score.
How much a list should move the projection is decided from this record, once
it holds a few rounds.

**Where the two totals come from.** `report.py --apply` stores
`blended_total` and `jp_only_total`; the daily collection stores
`player_points` and no totals, so `projection_ledger.outcome_totals` scores
both elevens from those points, and only when every player of both has them.
Until it did, grading skipped every automatically collected round without a
word, and the script crashed on them.

**The league, both halves.** Each projection also stores
`league_projection`: every squad's projected eleven (`total_sf`) from the same
morning, read through `league_compare` (eight squad reads, cached five
minutes; a failed read leaves our own projection stored without it). Each
outcome stores `league_points`: what every squad scored, from the round read
the collection already makes, at no extra cost. `projection_ledger.league_ranking`
sets the two side by side and the script prints it per round. It answers a
different question from the blend's: whether the projection ranks our squad
near the top in rounds it finishes at the bottom. It is a question about the
projection and the shape of a squad, so it is not graded against a threshold
here. Read it over several rounds, not one.


**Jornada Perfecta for everyone.** Each projection also stores `league_jp`:
Jornada Perfecta's SF for every player it projects in the competition, keyed
by the Biwenger id as a string, from round 13 on. It costs no request — the
morning already holds both the player list and the JP read — and about 8 KB a
document, exempt from Firestore indexing (`infra/firestore.tf`). It is what
the opponent effect below compares against.

## The opponent effect

`scripts/projections/opponent_effect.py` asks whether facing Barcelona or Real
Madrid sinks a player's points, and whether Jornada Perfecta already prices it
in. Read-only; one request per finished round to the public round endpoint,
none from the account's player-detail budget.

Each appearance is measured against **the same player's mean in his other
games**, Barcelona and Madrid left out of that mean. A weak defender is
therefore never mistaken for a bad fixture.

Measured after round 11, in SofaScore points (the base Jornada Perfecta
projects; a defender or keeper averages about 4 a game):

| Against | Defenders | Keepers |
|---|---|---|
| Barcelona | −3.3, 45 of 56 below their own mean; 9 of 11 games negative | −3.6 (n = 9) |
| Real Madrid | −2.4, 40 of 54 below; 10 of 11 games negative | −0.6 (n = 11) |
| Next worst (Real Sociedad, Elche) | about −1 | — |

How to read it:

- **The per-game count comes first.** One heavy defeat sinks a whole back
  line, so five defenders in one game are one observation, not five.
- **Appearances include substitutes.** The round payload has no minutes.
- **The league's own scoring would widen the gap.** It adds play, win and
  clean-sheet bonuses, which rarely come against these two.
- **Jornada Perfecta did not move for the fixture** in the five cases our
  own squad holds (Tenaglia 442 against Barcelona, his highest; Juan
  Iglesias, Rioja and Joan García flat against Madrid). Five cases are an
  anecdote; `league_jp` turns them into a sample, printed in the script's
  last block once graded rounds carry it.

There is no threshold and no verdict here, as with the blend: a rule that
benches a defender against these sides goes to `openspec/changes/` first,
with this output as its evidence.

## When the numbers look wrong

The script caches player reads on disk. A cached player that has no report
for the round being asked about is fetched again, because a copy read before
the round was played would otherwise pass for "no data" — that once made a
finished round look empty. If numbers still look wrong, clear
`packages/biwenger_tools/scripts/projections/.cache/`: it once kept serving
broken responses long after the cause had been fixed, eight rounds of
`0 pts reales` that looked like a terrible squad rather than an empty read.

The daily collection does not use this cache: it reads each player live.
