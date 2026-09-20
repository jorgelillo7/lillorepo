# Biwenger's official rules, as the app states them

**Captured from the app's `REGLAS` screen on 2026-09-20.** Transcribed from
nine screenshots, nothing inferred and nothing filled in from memory.

## Why this file exists

Three things in this project depend on how Biwenger scores and when it locks
a lineup, and all three were once reasoned about from memory. One of them
shipped: `finished` fixtures were treated as unplayable on the argument that
"points already banked were settled at kick-off", which was asserted rather
than checked, and it was reverted the same day.

The repo's first ground rule says never to claim how something external
behaves without checking. This is the thing to check against.

## What Biwenger fixes, and what a league configures

The rules text names its own escape hatches. These are **per-league settings**,
so nothing below them is a fact about *our* league until it is read from our
league's own screen:

- the starting squad and balance — *"dependiendo de la configuración de su liga"*
- how long a free agent stays in the market — *"ajustable en las opciones de tu liga"*
- the payout after each matchday — *"en base a la puntuación conseguida y las opciones de tu liga"*
- how a split matchday is handled — *"cada liga Biwenger puede elegir"*
- **the scoring system itself**

> **Our league does not use the plain SofaScore system.** It is based on it
> with additional bonuses — see "The Lloros League's own scoring" below, which
> carries them from the reglamento.

## Generales

1. Each member receives a full squad and/or balance at the start of the game or
   of a new season, depending on the league's configuration.
2. Player states, possible lineups and fantasy advice come from **external
   providers**; they are *"meramente orientativo"* and must never be
   determinative when buying or fielding a player.
3. During each competition's transfer window a player's **position on the pitch
   and his club can both change**, as the data provider stipulates.

## Puntuación

1. Whoever has the most points at the end of the season wins. A tie is broken
   by squad value + balance.
2. **Before each matchday begins, the system registers the lineup and team
   strategy each user has set.** Start and end dates are in the Calendar on the
   Inicio tab, and can move for postponements or other circumstances outside
   Biwenger.
3. **Only players who are in your lineup score.**
4. If your **balance is negative at the exact moment the matchday starts**, you
   receive **no points and no payout** for that matchday, even if you return to
   positive during it. Active challenges for that matchday are marked lost.
5. **−4 points for each unoccupied position** in a matchday's lineup — except a
   completely empty lineup, which scores 0.
6. Points are computed per the formulas of the league's scoring system.
7. A tie on matchday points goes to the higher **fielded** squad value, measured
   at the matchday's start. In fantasy-type leagues the *lower* value wins.
8. After each matchday you receive balance based on points scored and the
   league's options.
9. Ties in the ideal/best-value elevens use the highest-valued player for ideal
   elevens and the lowest-valued for value elevens, priced at the matchday's
   start.

## Fichajes

1. You cannot bid above your **Puja Máxima**.
2. Bids for free agents are processed **when their time in the market expires**
   (league-adjustable).
3. Bids for free agents are **secret, and the highest wins. A tie goes to the
   bid placed first.**
4. The market makes you a purchase offer for players you put up for sale, at
   **±5% of the player's market value** at the time of the offer. It is
   withdrawn if unanswered **within 2 days**.
5. Offers between users of a league expire **within 7 days** if the recipient
   does not answer.

## The SofaScore system — the baseline our league is built on

A rating from the provider, rounded to one decimal, converted by this table:

| Rating | Points | Band |
|---|---:|---|
| 9,5 – 10 | 14 | Excelente |
| 9 – 9,4 | 13 | Excelente |
| 8,6 – 8,9 | 12 | Muy bueno |
| 8,2 – 8,5 | 11 | Muy bueno |
| 8 – 8,1 | 10 | Muy bueno |
| 7,8 – 7,9 | 9 | Bueno |
| 7,6 – 7,7 | 8 | Bueno |
| 7,4 – 7,5 | 7 | Bueno |
| 7,2 – 7,3 | 6 | Bueno |
| 7 – 7,1 | 5 | Medio |
| 6,8 – 6,9 | 4 | Medio |
| 6,6 – 6,7 | 3 | Medio |
| 6,4 – 6,5 | 2 | Medio |
| 6,2 – 6,3 | 1 | Medio |
| 6 – 6,1 | 0 | Malo |
| 5,8 – 5,9 | −1 | Malo |
| 5,6 – 5,7 | −2 | Malo |
| 5,4 – 5,5 | −3 | Malo |
| 5,2 – 5,3 | −4 | Malo |
| 5 – 5,1 | −5 | Muy malo |
| 0 – 4,9 | −6 | Muy malo |

On top of the rating, **in the baseline system**:

| Event | Points |
|---|---:|
| Goal by a PT | 6 |
| Goal by a DF | 5 |
| Goal by a MC | 4 |
| Goal by a DL | 3 |
| Goal from a penalty, any position | 3 |
| Own goal | no goal points |
| Assist, any position | 1 |

Scoring is computed **live** during the match and can change afterwards through
the provider's precision adjustments or changes to the match report. SofaScore
ratings changed *after* a matchday's points and payouts have been delivered are
**not** reflected in the game. Where a goal's assignment is in doubt, the
referee's report prevails.

## Jornadas divididas

A matchday can be split by postponements or calendar changes, and each league
chooses how to handle it. The mode visible in the capture was *"Jornada única,
entregar puntos y abonos tras disputarse todos los partidos"*: like single-matchday
with recalculation, except **no payout and no points until every match of the
matchday has been played** — which can be weeks or months later. It avoids
paying a bottom-of-the-table bonus that a postponed result then invalidates.

## The Lloros League's own scoring

From the league reglamento, **art. 2.2 and Anexo I**, published at
`/reglamento` on the `biwenger-summary` service:

> Puntuación oficial = conversión de la nota SofaScore + bonificaciones −
> penalizaciones. Si Biwenger o SofaScore rectifican una valoración una vez
> cerrada la jornada, la corrección se aplica automáticamente a todas las
> competiciones de la Lloros League.

The conversion table is the baseline one above. Anexo I's bonuses and
penalties:

| Action | Points |
|---|---:|
| Team win (playing more than 65 min) | +1 |
| Team defeat (playing more than 65 min) | −1 |
| Clean sheet — keeper, more than 65 min | +2 |
| Clean sheet — defender, more than 65 min | +1 |
| Yellow card | −1 |
| Playing more than 65 minutes | +1 |
| Match MVP | +3 |
| Penalty saved | +2 |
| Penalty missed | −2 |
| Goal from a penalty (deducted from the normal goal) | −1 |
| Own goal | −1 |
| Goal by a DL | +3 |
| Goal by a MC | +4 |
| Goal by a DF | +5 |
| Goal by a POR | +5, **plus a further +1** |
| Assist | +1 |
| Assist by a DF (additional) | +1 |
| Assist by a POR (additional) | +2 |

So for outfielders the **goal ladder is identical to the baseline** — DEF 5,
MED 4, DEL 3. What this league customises is everything around it: the win and
defeat points, clean sheets, cards, minutes, MVP, penalties and the keeper's
and defender's assists.

**The keeper's goal is 6**, confirmed by the league owner — who also confirms
that the annex's own screenshot carries that row wrong. SofaScore's base table
already pays a keeper 6, so the annex's "+1 adicional" restates the base rather
than adding to it.

That distinction was live in the code: `personalizado` added the +1 on top of
`score2` and would have paid a keeper 7 for a goal. Nothing had caught it,
because the reconstruction's keeper control never scored one. His **assist** is
a genuine addition and keeps its +2 — 1 in the base, 3 in this league.

`lineup.py::GOAL_BONUS` holds these figures and is pinned to them by a test.
It had carried `{10, 7, 5, 4}` for a year, from no published table, and every
lineup tie was broken with it.

Note that goals are not the only thing paid by position: a clean sheet is
worth 2 to a keeper and 1 to a defender, and an assist 3 and 2 against a
midfielder's 1. `GOAL_BONUS` is a proxy for that whole shape and understates
it for the back line — see the known simplification in
`openspec/specs/biwenger_tools/auto-pick-lineup/spec.md`.

## What this file does not establish
- **Our league's starting balance and market expiry.** The rest came back from
  `/rounds/league`: `splitRound = "end"` (points and payouts only once every
  match of the round is played), `bonusPoint = 75000`, `bonusIdealLineup =
  500000`, and **`lineupRoundChanges = 0`** — which is the API confirming, in
  its own words, that the eleven cannot be changed once the round is under way.
- The app version or rules revision — the screen shows neither.
