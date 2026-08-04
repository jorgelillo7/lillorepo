---
name: draft
description: Annual pre-season helper for the Lloros League draft. Merges the closed-market CSV (frozen prices) with live Jornada Perfecta SofaScore into a ranked CSV, then advises on the 15-man squad with alternatives for the top picks. Use at the start of each Biwenger season when building the draft squad.
model-invocable: false
allowed-tools:
  - Read
  - Bash
  - WebSearch
  - AskUserQuestion
---

# Draft — Lloros League pre-season squad builder

Runs once a year, at the season draft. Two phases: a deterministic **merge**
(a script), then an interactive **adviser** (conversation).

## Inputs the user provides

- **The closed-market CSV** — the user exports it from Biwenger web on the
  chosen "market closed" day (the `primera-division` export, ~500 players:
  `Equipo;Jugador;Posición;Puntos;Precio;…`, UTF-8 BOM, `;` delimited). Prices
  are frozen to that day; the reglamento says market swings don't affect the
  draft. **Not auto-downloaded** — a late run would use wrong prices.
- **The yearly params** (ask with AskUserQuestion, don't assume):
  - **Budget** — 50M base, plus any extra (this rolls over: 2026/27 the user
    won the Copa Castolo → **52M**).
  - **Draft order + the user's pick position** — inverse to last season's
    standings, with anomalies for new entrants. 2026/27: Rubén · Javi · **Lillo
    (3rd)** · Manu · Pablo · Lucen · Fabio (snake, 15 rounds).

## Phase A — the merge (deterministic)

Run the script from the repo root (it self-loads the api `.env` for the JP
token and reuses `core.sdk.jp.fetch_all_players` + the production
`player_matching`):

```bash
PYTHONPATH=. python3 packages/biwenger_tools/.claude/skills/draft/scripts/draft_ranking.py \
    --csv /path/to/primera-division.csv --out draft-ranked.csv
```

It fetches live JP SofaScore, joins on names (accent/slug folding + the
`PLAYER_NAME_MAPPINGS` overrides — e.g. De la Fuente→Dela, De Tomás→RDT), adds
a **value-per-million** column, ranks by SofaScore, and flags players with no
JP data (`no_jp_data=True`). **Re-runnable**: JP scores update several times a
day, so a re-run days later refreshes the points with the same frozen prices —
no flags needed, `fetch_all_players` self-invalidates on JP's `updated_at`.

If a flagged player is one the user wants, check whether it's a JP short-name
(view the Automanager/SofaScore screen) and add a `PLAYER_NAME_MAPPINGS`
override in `packages/biwenger_tools/api/logic/player_matching.py` (helps
auto-bid too), or leave it as a genuine no-data (newcomer / not tracked).

## Phase B — real points for the shortlist (bounded)

**The ranked CSV is for discarding, not for deciding.** JP projects SofaScore;
this league scores `Personalizado`. The measured ratio between the two ranges
from 0.225 to 0.610, so no constant makes the projection comparable across
players — only the real total does.

Narrow the market to the **30-45 players that actually compete** for the slots
still open (line, price band, availability), then fetch only those:

```bash
PYTHONPATH=. python3 packages/biwenger_tools/.claude/skills/draft/scripts/fetch_real_points.py \
    --shortlist draft-shortlist.csv --out draft-real-points.csv
```

It computes each player's real `Personalizado` from per-match `rawStats` and
reports **games played** alongside it. Both matter: *70 points in 5 games and
70 in 38 describe opposite players*. Feed it back in:

```bash
PYTHONPATH=. python3 packages/biwenger_tools/.claude/skills/draft/scripts/archetypes.py \
    --ranked draft-ranked.csv --real-points draft-real-points.csv \
    --budget 52 --pick-position 3 --managers 7 --max-per-team 2 \
    --out mi-arquetipos.md --decision final-decision.md
```

The generator then ranks by the real total where it has one, and by a
**per-line calibrated** projection where it does not, measuring the factor from
the overlap in your own data rather than assuming one.

**Never shortlist more than the cap.** Biwenger allows ~500 requests per 8-hour
window **per account**, shared with the phone app — a sweep of the whole market
locked the entire league out mid-draft. 45 requests is 9%; the script refuses a
longer shortlist, goes sequential, caches to disk and stops at the first 429.

**Why 30-45 and not 15.** Querying only the players you already chose confirms
your own bias. Dmitrović was the *sixth* goalkeeper by projection and the
*first* by real points; Juan Iglesias was not in any draft and ended up captain.

Players with **no La Liga minutes last season** are excluded from the output
rather than published as zero — the `seasons` block counts every competition,
so someone arriving from Ligue 1 or Segunda would otherwise read as a genuine
zero, which the optimiser would believe.

## Phase C — the adviser (interactive, not a script)

Work with the user over the refined data. Not a solver — each year is its own
case. **Iterate**: when a player falls (taken, or bad news), promote the next
candidate, fetch his real points too, and re-check budget and composition.
Steps:

1. **Build the 15** within budget, respecting the composition rule: a valid XI
   **plus at least one sub per line** (≥2 GK; each outfield line starters+1).
   Favour SofaScore, but weigh value-per-€ for the mid/late picks.
2. **Top-5 = the base**: give each of the first 5 picks **3 alternatives** at
   the same price/points tier. The user picks 3rd in a snake of 7, so their
   global picks land at ~3, 12, 17, 26… — several tiers vanish between picks,
   which is *why* the top-5 need plan B/C (resilience, not predicting rivals).
3. **News due-diligence — BLOCKING, not optional.** Skipping it in 26/27 until
   the user asked mid-draft turned up three things no number could see: Marcos
   Alonso left out of the pre-season squad pending a renewal, Canales returning
   at 35 from three years in Liga MX, and Fortuño competing with the keeper who
   was meant to stay unclausable all season.

   Record the findings in an `--exclude-file`, never in `--exclude`: a bare
   name records *that* somebody was dropped and never *why*, and next season
   nobody remembers whether it was an injury, a rumour or a dressing-room
   fight. Web-search each shortlisted
   player for red flags the price/points can't see — points reward last season,
   the news is about *this* one starting. Check for:
   - **Injuries / suspensions** (apercibido) and **transfer/exit rumours** (a
     player who leaves LaLiga is auto-sold per reglamento Art. 6).
   - **Coach changes / locker-room conflict** — a new manager can freeze or
     bench players regardless of last season's numbers (2026/27: Mourinho's
     Real Madrid cut-list — Rodrygo, Camavinga, Fran García… — tanked their
     minutes; Valverde's dressing-room fight + sale pressure made his 688 SF a
     trap). Web-search the club's manager + "bajas/descartes".
   - **Backward-looking scores**: a high SofaScore earned in a **different
     league** may not translate to LaLiga (2026/27: Aubameyang's 508 was from
     Marseille). Flag and discount these.
   - **Placeholder scores**: promoted-club players and new signings often carry
     JP's flat default, not a real score — see "JP placeholder scores" below.
     The generator drops them; if you re-add one by hand, treat him as unrated.
4. **Cap the club concentration at 2 players per club.** Nothing in the score
   sees it, but three players from one side means one bad run drags three slots
   at once — and under the custom scoring below, all three lose the same win
   bonus on the same weekends. Prefer pairs in different lines.
5. **Validate**: final 15 ≤ budget and composition-valid — warn on overspend or
   a lineless bench.

## The league scores "Personalizado", not SofaScore

**This is the biggest correction to the whole ranking, and it is easy to miss.**
JP's projection *is* SofaScore, and the league is not:

Read off the league's own configuration screen and implemented in
`scripts/fetch_real_points.py`:

```
Personalizado = SofaScore base
              + 1  played > 65 min      · + 1 win  · − 1 loss  (both > 65 min)
              + 2  clean sheet (GK)     · + 1 clean sheet (DF)
              − 1  yellow card          · − 1 penalty goal
              − 2  penalty missed
              + 1  GK goal              · + 2 GK assist · + 1 DF assist
```

**Verified to the point against two controls of different lines:** Vinícius Jr
`296 → 330` (forward) and Joan García `190 → 274` (goalkeeper). Biwenger's
per-match `star` flag is *not* the config's MVP bonus — adding it overshoots
both (345 and 277), so it is ignored.

Beware the shortcut that fits one control and fails the other: `SofaScore +
2×wins + 2×clean sheets` reproduces Joan García's 274 exactly and misses
Vinícius by 15. One control is never enough here.

Most of the bonus is **team property, not player property**. What follows:

- A Barcelona starter banks **+84 a season** for turning up; a promoted-club
  starter, ~+30. Fifty points of gap before anyone touches the ball.
- **Minutes are the gate.** Every play/win bonus needs *more than 65 minutes*,
  so a substitute collects almost none of them. Iago Aspas scored 143 points in
  32 appearances but started 10 and cleared 65 minutes eight times — his total
  looks like a bargain and does not transfer to a starting slot. Rank by
  `starts`, not by appearances.
- **Goalkeepers at defensively strong clubs are systematically underpriced.** A
  clean sheet barely moves a SofaScore rating but pays +2 here, so JP's number
  understates exactly the keepers this league rewards. In 26/27 this is what
  made Oblak (3,88M, Atlético) the pick over Joan García (10,12M) — same clean
  sheets, 6M cheaper.
- The captain doubles the bonus too, so a cheap full-back at a clean-sheet club
  beats a cheap forward of equal projection.

### Getting the real numbers

`GET /players/la-liga/{slug}?fields=*,reports(*)` (documented in
`docs/external/biwenger-api.yaml`) returns per-match `rawStats` with `win`,
`cleanSheet`, `minutesPlayed` and the base score — everything the formula needs.
`seasons(*)` gives season totals per scoring-system id (1 Marca, 2 SofaScore,
3 Picas, 5 media, 6 AS). **The league's own `scoreID: 100` is never one of those
keys** — no endpoint serves custom totals, the app computes them client-side.

> **Fetch the shortlist, never the database.** This endpoint is per-player, so
> the cost is one request per name — and the answer only ever needs the ~20
> players actually in contention for the remaining picks. Filter first (position
> gaps, price band, still available), then fetch.
>
> Pulling all ~550 in parallel got the whole league 429'd for hours **mid-draft**,
> including the user's own phone and, potentially, the bot's transfers. Hard
> rules: shortlist only, **sequential with a delay**, checkpoint to disk, and
> stop on the first 429 instead of retrying. If the draft is live and the data
> isn't already cached, don't run it at all — estimate the team bonus from last
> season's table and say plainly which numbers are measured and which are
> modelled.

## Output

Simple + structured (not prose-heavy): the ranked CSV, then a compact squad
table (player · pos · price · pts · value/€ · no-data badge) with totals +
remaining budget, and a tight alternatives block for the top-5.

## Archetype generator

`scripts/archetypes.py --ranked <draft-ranked.csv>` builds and compares
squad-construction archetypes under the budget + composition rules, ranked by
**XI points** (only the eleven score on a matchday; the all-fifteen figure is
reported alongside as a depth reading).

| Flag | Qué hace |
|---|---|
| `--budget 52` | En **millones**. Pasar euros es un error y falla en seco |
| `--exclude-file f.txt` | **El veto de noticias, con su motivo.** Un nombre por línea, tras `#` el porqué. Se versiona: el año que viene querrás saber *por qué* descartaste a alguien |
| `--history h.csv` | Modelo de disponibilidad de `availability_report.py`. Añade la columna **¿Llega?** |
| `--exclude "n,n"` | Veto de la due-diligence de noticias (lesionados, sancionados, puntos de otra liga) |
| `--force "n,n"` | Arquetipo **a medida** alrededor de quien tú digas. Genera versión normal y banco mínimo |
| `--bets "n,n"` | Titulares baratos que una fuente de scouting anticipa. Su SofaScore es bajo porque no jugaron: se revalúan a `--bet-sf` (400) y salen marcados 🎲 |
| `--pick-position 3 --managers 7` | Añade el **plan de picks**: en qué turno global coger a cada uno |
| `--decision fichero.md` | Escribe además el **pliego de decisión**: los 15 en orden, alternativas para los 5 primeros y reglas de ejecución. Con `--force` sigue tu elección, no el ranking |
| `--keep-placeholder` | No descartar a los que JP puntúa por defecto |
| `--max-per-team 2` | Tope de jugadores por club. Los bonus de victoria y portería a cero son de equipo: tres compañeros los ganan y los pierden el mismo fin de semana |

Escribe `mi-arquetipos.md` (gitignored) y, con `--decision`, el pliego aparte.

### La llamada completa, tal cual se usó en el draft 26/27

```bash
python3 packages/biwenger_tools/.claude/skills/draft/scripts/archetypes.py \
    --ranked draft-ranked.csv --budget 52 --pick-position 3 --managers 7 \
    --exclude "Aubameyang,Soler,Kike Salas" \
    --bets "Fer Niño,Carlos Maciá,Riedel,Pablo Campos,Odysseas,Marc Bernal,Unai López,Adrián Niño,Julio Díaz" \
    --force "Dani Olmo" \
    --out arquetipos.md --decision final-decision.md
```

De dónde sale cada cosa, porque los nombres cambian cada año y lo que hay que
repetir es el **criterio**:

- **`--budget 52`** — 50M base + 2M de la Copa Castolo. Sale de
  `BUDGET_OVERRIDES` en `api/logic/draft.py`.
- **`--pick-position 3 --managers 7`** — tu puesto en el orden snake de la
  temporada (`core.constants.DRAFT_ORDER_NAMES`).
- **`--exclude`** — el veto de la due-diligence de noticias. Aquel año:
  Aubameyang (sus puntos eran de la Ligue 1 y fichaba por un recién ascendido),
  Carlos Soler (lesión de rodilla desde diciembre anterior, jugando en el
  filial) y Kike Salas (investigado por amañar tarjetas). Los tres tenían buena
  puntuación y los tres eran trampas.
- **`--bets`** — los tapados que Jornada Perfecta daba titulares en sus
  previas de pretemporada. Su SofaScore es bajo porque no jugaron, no porque
  sean malos.
- **`--force`** — la estrella elegida a mano. El generador proponía a
  Valverde, pero arrastraba la pelea con Mourinho y la presión de salida;
  Dani Olmo rendía casi igual (−6 puntos) por 0,34M menos y sin ese riesgo.

**The captain rule is decisive**, and it is now enforced in the ranking rather
than left to the reader. Biwenger rejects any captain priced ≥ 3M
(`_CAPTAIN_MAX_PRICE`), and the captain doubles points — so the most valuable
roster slot is the **best startable player under 3M**. What the generator bakes
in:

- Archetypes are ranked by **durable effective points** = squad SF + the SF of
  a captain who *starts* and *survives price drift* (< 3M, ≤ 2.5M buffer, and
  value-per-M ≤ 200). Raw effective points — any captain eligible today — are
  printed alongside as the optimistic bound. A build whose only sub-3M options
  are rockets or players pegged at the cap scores **zero** captain bonus,
  because within weeks that is exactly what it has.
- **The captain must be in the XI.** The generator picks the best formation
  among the shapes Biwenger accepts and looks for the captain only among those
  eleven, the same constraint production applies (`lineup.py`, `starters`). A
  5th-choice midfielder cannot be captain no matter how cheap he is.
- Every archetype gets a **captain-repair pass**: if it cannot field a durable
  captain, the generator swaps in the cheapest one that fits. The premium is
  ~10 SF out of ~7300, so there is no reason to run a build without an anchor —
  which is also why value-max and captain-anchor usually converge on the same 15.
- A build with **no player under 3M** (the flat 3-4M "ultra-balanced" trap) has
  no captain at all and throws away ~one player's SF every week.

**JP placeholder scores.** JP hands out one flat score (400 in 2026/27) to
players it has no data for — promoted clubs and fresh signings. It is a
top-decile number attached to 1.5M players, so it poisons every cheap-heavy
archetype. The generator auto-detects the spike and **drops those players**,
listing them in the report; `--keep-placeholder` overrides, `--placeholder-sf N`
pins the value by hand.

Known limitation: squad shape is fixed at 2-5-5-3. It is a valid composition and
covers every formation the XI picker uses, but the generator does not explore
other legal shapes (2-6-5-2, 2-5-6-2…).

## ¿Llegará a tu pick? Pregúntaselo al draft anterior

The optimiser builds the ideal fifteen as if every player were purchasable.
They are not — at position 3 of 7, nine leave the board between your first pick
and your second — so a plan without this correction is fantasy.

Close the previous draft with the machine-readable model and feed it back:

```bash
PYTHONPATH=. python3 .../scripts/availability_report.py \
    --season 26-27 --out draft-disponibilidad.md --history-csv draft-history.csv

# al año siguiente
... archetypes.py --history draft-history.csv ...
```

The **¿Llega?** column then reports, for each planned pick, how much of that
line and price band was still on the board at that height last time:

| | Significado |
|:-:|---|
| ✅ | más de la mitad seguía libre — el plan aguanta |
| ⚠️ | entre un cuarto y la mitad — ten el recambio elegido |
| 🔥 | casi ninguno — adelántalo o dalo por perdido |

Es medido, no intuido. En el 26/27 marcó 🔥 a Gerard Moreno en el pick 17, que
fue exactamente el jugador que desapareció antes de lo previsto.

## Tu posición en el snake cambia el plan

Con 7 presidentes y 15 rondas los huecos entre tus turnos dependen de dónde
piques, y eso cambia qué decisión tomas, no sólo cuándo:

| Posición | Huecos | Qué implica |
|---|---|---|
| 1-2 (arriba) | 11-3 alternos | Eliges primero pero esperas casi una ronda entera. Sales con el mejor del mercado y vuelves cuando ya han caído once |
| 3-5 (medio) | 9-5 / 7-7 | El caso peor: nunca eliges primero y nunca eliges dos seguidos. Hay que acertar el tier, porque entre turno y turno desaparece uno entero |
| 6-7 (abajo) | 1-13 alternos | Eliges **de dos en dos** (final de ronda + principio de la siguiente) y luego esperas trece. Puedes cerrar parejas complementarias — un portero y su suplente, dos centrales — pero pierdes tiers completos |

No es "más agresivo arriba y más conservador abajo". Es que **arriba compras
certeza y abajo compras combinaciones**: el último elige dos a la vez, así que
puede permitirse un plan que dependa de dos jugadores concretos; el de en medio
no, y necesita alternativas reales en cada tier.

Regla práctica en el medio: prioriza al que **no tenga sustituto equivalente**.
Si en tu tier hay tres jugadores parecidos, espera; si hay uno solo, cógelo ya.

## El histórico es la mejor fuente de "cuándo"

`draft-2025-26.md` guarda el draft anterior pick a pick. Cotejar el 15 objetivo
contra él es lo único que dice si el plan es realista: el año pasado Gerard
Moreno se fue en el pick 7 y Marcos Alonso — que hoy costaría 3,32M — en el
pick 10. Un plan que los espere en el pick 40 es papel mojado.

Al terminar cada draft, **añade el nuevo a ese fichero**.

## Reglamento anchors (stable rules)

15 players; valid XI + 1 sub per line; snake draft (round order reverses each
round); prices frozen to the export day; market closed during the draft;
**captain must cost < 3M** (Biwenger hard cap). Full text: the Lloros League
reglamento, Capítulo I.
