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
PYTHONPATH=. python3 .claude/skills/draft/scripts/draft_ranking.py \
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

## Phase B — the adviser (interactive, not a script)

Work with the user over the ranked CSV. Not a solver — each year is its own
case. Steps:

1. **Build the 15** within budget, respecting the composition rule: a valid XI
   **plus at least one sub per line** (≥2 GK; each outfield line starters+1).
   Favour SofaScore, but weigh value-per-€ for the mid/late picks.
2. **Top-5 = the base**: give each of the first 5 picks **3 alternatives** at
   the same price/points tier. The user picks 3rd in a snake of 7, so their
   global picks land at ~3, 12, 17, 26… — several tiers vanish between picks,
   which is *why* the top-5 need plan B/C (resilience, not predicting rivals).
3. **News due-diligence (before finalising)**: web-search each shortlisted
   player for red flags the price/points can't see — points reward last season,
   the news is about *this* one starting. Check for:
   - **Injuries / suspensions** (apercibido) and **transfer/exit rumours** (a
     player who leaves LaLiga is auto-sold per reglamento Art. 6).
   - **Coach changes / locker-room conflict** — a new manager can freeze or
     bench players regardless of last season's numbers (2026/27: Mourinho's
     Real Madrid cut-list — Rodrygo, Camavinga, Fran García… — tanked their
     minutes; Valverde's dressing-room fight + sale pressure made his 688 SF a
     trap). Web-search the club's manager + "bajas/descartes".
   - **Backward-looking scores**: a high SofaScore earned at a **promoted club
     or a different league** may not translate to LaLiga (2026/27: cheap DEF
     "chollos" from Málaga/Deportivo scored their points in Segunda; Aubameyang's
     508 was from Marseille). Flag and discount these.
4. **Validate**: final 15 ≤ budget and composition-valid — warn on overspend or
   a lineless bench.

## Output

Simple + structured (not prose-heavy): the ranked CSV, then a compact squad
table (player · pos · price · pts · value/€ · no-data badge) with totals +
remaining budget, and a tight alternatives block for the top-5.

## Archetype generator

`scripts/archetypes.py --ranked <draft-ranked.csv>` builds and compares several
squad-construction archetypes (value-max, captain-anchor, spine, superstar,
2-galácticos, ultra-balanced) under the budget + composition, ranked by
**effective points** = total SF + captain SF. Pass `--exclude "name,name"` for
the news-DD blacklist (Mourinho outcasts, etc.). It writes a local
`mi-arquetipos.md` (gitignored).

**The captain rule is decisive.** Biwenger rejects any captain priced ≥ 3M
(`_CAPTAIN_MAX_PRICE`), and the captain doubles points — so the most valuable
roster slot is the **best player under 3M**. Two consequences the generator
bakes in:
- **Prices move daily**, so a captain pegged at ~2.9M crosses 3M after one good
  match. Prefer a **durable** captain: ≤ 2.5M buffer *and* not a screaming
  bargain (a high value-per-M player rockets past 3M fast). Gayà-type
  (~2.2M, fairly priced, nailed-on starter) beats a 1.5M rocket.
- A build with **no player under 3M** (the flat 3-4M "ultra-balanced" trap)
  has **no captain** and throws away ~one player's SF every week.
- When two archetypes tie on effective points, **pick the one with the durable
  captain** (the raw number can't see that a rocket captain loses eligibility
  in weeks — that's why "captain-anchor" usually beats "value-max" in practice).

## Reglamento anchors (stable rules)

15 players; valid XI + 1 sub per line; snake draft (round order reverses each
round); prices frozen to the export day; market closed during the draft;
**captain must cost < 3M** (Biwenger hard cap). Full text: the Lloros League
reglamento, Capítulo I.
