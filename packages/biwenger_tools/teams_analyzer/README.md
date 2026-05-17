# ⚽ Biwenger Teams Analyser

Pre-matchday analysis tool. Pulls squads, market and rival data from the Biwenger API,
enriches them with predicted ratings from the **Jornada Perfecta private API** (the
SofaScore-based "Automanager" rating, `predict[type=2].rate`), and posts the digest
to Telegram as PNG table images.

No browser automation, no scraping — one HTTP call per source.

## 🚀 What it does

1. **Health-check the JP API** — fails fast if the app token has rotated.
2. **Fetch all LaLiga players from JP** — 1 request, ~600 players, includes predicted
   rating, status, fitness, streak, next-match info.
3. **Log into Biwenger** — fetch the league standings, your own squad, every rival
   squad, and the current free-agent market.
4. **Match Biwenger ↔ JP** — by normalised name (with slug fallback and a manual
   override map for known mismatches like `vinicius jr` → `vini jr`).
5. **Render PNG tables with matplotlib** and push them to Telegram via `sendPhoto`.
   What is sent depends on `ANALYSIS_MODE` (see entry point below).

Each row in the table includes a traffic-light cell (🟢/🟡/🔴/⚪ via background color),
position, price, SF predict, streak and a play-status label (casa/fuera/lesionado/
sancionado/no convocado/duda/sin partido).

## ⚙️ Configuration

In production the job reads `BIWENGER_CREDENTIALS_JSON` and `TELEGRAM_BOT_CONFIG_JSON`
from Secret Manager. The JP API token lives inside `BIWENGER_CREDENTIALS_JSON` as the
`jp_auth_token` key (moved there from a hardcoded constant on 2026-05-16 so it stops
living in public git history).

For local dev, `.env` at this directory can fall back to individual vars:

```
BIWENGER_EMAIL=...
BIWENGER_PASSWORD=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
JP_AUTH_TOKEN=...
```

If JP rotates the token, `check_api_health()` raises with the extraction command —
see `docs/technical/reverse-engineering/frida-android-intercept.md`.

For run/test commands see [`docs/operations.md`](../../../docs/operations.md) section
**1.3 Teams Analyzer**.

## 🔧 Player name mappings

Biwenger and Jornada Perfecta sometimes spell the same player differently. The
`PLAYER_NAME_MAPPINGS` dict in `logic/player_matching.py` handles known exceptions
(applied after direct-match and slug-match fail):

```python
PLAYER_NAME_MAPPINGS = {
    "vinicius jr": "vini jr",
    "vinicius junior": "vini jr",
    "sancet": "oihan sancet",
    # ...
}
```

Add new entries when you spot a player tagged ⚪ ("no JP data") that you know does
exist in JP — they're just spelled differently.

## 📬 Telegram setup

If you don't have a bot yet:

1. Talk to `@BotFather` on Telegram, run `/newbot`, get a `TELEGRAM_BOT_TOKEN`.
2. Send a message to your bot, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` to get your `chat_id`.

## 🗺️ Entry point

`main.py` is the single entry point. It dispatches to one of five mode handlers
based on the `ANALYSIS_MODE` env var (`daily`, `all`, `my_team`, `market`,
`alinear`). To follow the flow, open `main.py` and look at `_MODE_HANDLERS` —
each handler is its own function.

## 🧠 How `/alinear` picks the lineup

All in `logic/lineup.py`. Read it top-to-bottom: `pick_lineup` is the public
entry, helpers come after.

### Step by step

1. **Filter to available players** (`_is_available`). Out: no JP data,
   injured, suspended, team has no match this week, or JP says
   `playerInLineup=False` (explicit "no convocado"). `None` ("don't know
   yet") is *kept* — we want the gamble. `doubt` is also kept.
2. **Iterate the 12 supported formations** (`FORMATIONS`).
3. For each formation, **find the 11-player assignment that maximises the
   sum of SF** (`_try_fill`). This honours multi-position players (a
   FWD/MID can play either slot) and chooses the placement that gives the
   best total, not the first that fits.
4. **Compare totals across formations** and keep the best.
5. **Pick reserves** (`_pick_reserves`) in Biwenger's positional order
   POR → DEF → MED → DEL: highest-SF eligible bench player per slot.
6. **Pick captain** (`_pick_captain`): highest SF among starters whose
   market value is strictly below 3 M€ (Biwenger API rejects ≥ 3 M).
   Fallback: cheapest known-price player if nobody is under the cap.

### Why exhaustive backtracking

The previous version of `_try_fill` returned the first feasible assignment
and used a "prefer primary position" heuristic for multi-position players.
That broke as soon as moving a multi-position player to their alt freed up
a stronger combination at the primary. Worked example with formation 4-3-3:

- Squad: 4 FWDs (one is FWD/MID with SF 400, others 380/360/340) and 3 MIDs
  (350/320/280).
- **Option A** — multi-position player as FWD:
  FWDs = 400 + 380 + 360 = **1140** · MIDs = 350 + 320 + 280 = **950** → 2090
- **Option B** — multi-position player as MID:
  FWDs = 380 + 360 + 340 = **1080** · MIDs = 400 + 350 + 320 = **1070** → **2150** ← picked

Now the function explores every valid assignment for a given formation and
returns the one with the highest total SF. The unit test
`test_try_fill_places_multiposition_where_it_maximises_total` reproduces
exactly this scenario.

### Performance

Squad sizes are 20-25 players. Worst case is `O((squad_size choose 11) × 11!)`
in theory, but the "most-constrained slot first" pruning + the small input
size keep it well under a second per `/alinear`. If the squad grows to 50+
players (it won't in Biwenger) we'd add memoisation by sorted-bw_id key.

### When you want to tweak something

- **Add or remove a formation** → edit `FORMATIONS`.
- **Change the "no convocado" policy** (e.g. penalise SF instead of
  excluding) → edit the last branch of `_is_available`.
- **Change the captain rule** → `_pick_captain` is the only place.
- **Reserves order** → currently `(GK, DEF, MID, FWD)` in `_pick_reserves`,
  which mirrors Biwenger's slot order on the bench.
- **Penalise `doubt` status** → not done today (user wants to gamble); if
  reopened, the place would be `_sf` returning a discounted value.
