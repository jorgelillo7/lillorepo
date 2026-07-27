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
   - **Backward-looking scores**: a high SofaScore earned in a **different
     league** may not translate to LaLiga (2026/27: Aubameyang's 508 was from
     Marseille). Flag and discount these.
   - **Placeholder scores**: promoted-club players and new signings often carry
     JP's flat default, not a real score — see "JP placeholder scores" below.
     The generator drops them; if you re-add one by hand, treat him as unrated.
4. **Validate**: final 15 ≤ budget and composition-valid — warn on overspend or
   a lineless bench.

## Output

Simple + structured (not prose-heavy): the ranked CSV, then a compact squad
table (player · pos · price · pts · value/€ · no-data badge) with totals +
remaining budget, and a tight alternatives block for the top-5.

## Archetype generator

`scripts/archetypes.py --ranked <draft-ranked.csv>` builds and compares several
squad-construction archetypes (value-max, captain-anchor, spine, superstar,
2-galácticos, ultra-balanced) under the budget + composition. Pass
`--exclude "name,name"` for the news-DD blacklist (Mourinho outcasts, etc.). It
writes a local `mi-arquetipos.md` (gitignored).

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

## Reglamento anchors (stable rules)

15 players; valid XI + 1 sub per line; snake draft (round order reverses each
round); prices frozen to the export day; market closed during the draft;
**captain must cost < 3M** (Biwenger hard cap). Full text: the Lloros League
reglamento, Capítulo I.
