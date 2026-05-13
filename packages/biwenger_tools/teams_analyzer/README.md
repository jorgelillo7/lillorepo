# ⚽ Biwenger Teams Analyser

Pre-matchday analysis tool. Pulls squads, market and rival data from the Biwenger API,
enriches them with predicted ratings from the **Jornada Perfecta private API** (the
SofaScore-based "Automanager" rating, `predict[type=2].rate`), and posts the digest
to Telegram as formatted text messages.

No browser automation, no scraping — one HTTP call per source.

## 🚀 What it does

1. **Health-check the JP API** — fails fast if the hardcoded app token has rotated.
2. **Fetch all LaLiga players from JP** — 1 request, ~600 players, includes predicted
   rating, status, fitness, streak, next-match info.
3. **Log into Biwenger** — fetch the league standings, your own squad, every rival
   squad, and the current free-agent market.
4. **Match Biwenger ↔ JP** — by normalised name (with slug fallback and a manual
   override map for known mismatches like `vinicius jr` → `vini jr`).
5. **Send Telegram messages** in three sections:
   - 🛡️ **MI EQUIPO** — your starters sorted by predict-SF descending
   - 🛒 **MERCADO** — free agents, top 10 by predict-SF
   - 👤 **One message per rival manager** — same sort order, split if the message
     would exceed 4096 chars

Each player line includes a traffic-light emoji (🟢/🟡/🔴/⚪), position, price, today's
price increment, four prediction columns (SF / AS / Avg / Streak) and whether they
will play in their next match.

## ⚙️ Configuration

`.env` at this directory must define:

```
BIWENGER_EMAIL=...
BIWENGER_PASSWORD=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The JP token is hardcoded in `core/sdk/jp.py` (it lives in the JP Android app bundle,
not a per-user session). If JP rotates it, `check_api_health()` raises with the
extraction command — see `docs/technical/reverse-engineering/frida-android-intercept.md`.

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
