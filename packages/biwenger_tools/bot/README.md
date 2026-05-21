# 📡 Biwenger Tools — Telegram Bot

Cloud Run **Service** (`biwenger-bot`) that receives Telegram webhooks and
calls the [`biwenger-api`](../api/README.md) service over HTTP. Pure
orchestrator — no business logic lives here.

Single-tenant: only the configured `chat_id` is honoured; everything else is
silently dropped (returns `200` so Telegram does not retry).

## 🗺️ Entry point

`app.py` exposes `POST /telegram/webhook`. The flow per request:

1. Validate `X-Telegram-Bot-Api-Secret-Token` against the stored secret using
   `hmac.compare_digest` (constant-time). 401 if it mismatches.
2. Extract `chat_id` + `text` from the update body. Drop if the chat is not
   the one we own.
3. Parse the command via `core.sdk.telegram.parse_command` (strips
   `@botname` suffix, lowercases).
4. Map command → `(api path, http method)` and call `api_client.call_api`
   with a Google-signed ID token.

```
/menu        →  sends an inline-keyboard menu (no api call)
/analizar    →  opens the manager picker (GET /managers, then /teams?manager=<id|all>)
/mercado     →  GET  /market
/alinear     →  POST /lineups/auto-pick
/recomendar  →  GET  /budget/recommendations
/scrapper    →  POST /scraper/trigger
/version     →  bot SHA + GET /version on biwenger-api
/help        →  static HTML message (no api call)
```

Inline-keyboard taps come back as `callback_query` updates. They share
the same webhook entry point and dispatch on a `prefix:value`
`callback_data` shape (`menu:<action>`, `analizar:<id|all>`).

The api processes each request synchronously (build JP index, talk to
Biwenger, render PNG, send to Telegram). The bot is just the HTTP edge.

## 🔐 Auth to biwenger-api

The api is deployed with `--no-allow-unauthenticated`. The bot's runtime SA
has `roles/run.invoker` on `biwenger-api`. `api_client.call_api` uses
`google.oauth2.id_token.fetch_id_token` against the metadata server (no
extra config on Cloud Run) and sends the result as `Authorization: Bearer`.

## 🔑 Secrets

In production: `TELEGRAM_BOT_CONFIG_JSON` from Secret Manager. Keys:

```json
{
  "bot_token": "...",
  "chat_id": "...",
  "webhook_secret": "..."
}
```

For local dev, fall back to the same names as plain env vars. After deploying,
register the webhook once with Telegram:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://biwenger-bot-.../telegram/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

## 📋 Bot command menu

`setup_commands.py` registers the menu shown in Telegram's `/` UI. Run it once
after creating the bot or whenever commands change:

```bash
python3 packages/biwenger_tools/bot/setup_commands.py
```

## 🚀 Runtime config

Bots run with `cpu=0.5 concurrency=1` (GCP forbids `cpu<1` with
`concurrency>1`). The values are baked into `.github/workflows/deploy.yml`, so
every CI deploy reapplies them — no drift.

`BIWENGER_API_URL` is resolved at deploy time by reading the api service URL
from gcloud and passed as an env var (see `deploy-bot` in the workflow).

See [`docs/operations.md`](../../../docs/operations.md) for build/test/deploy
commands.
