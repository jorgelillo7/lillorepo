# 📡 Biwenger Tools — Telegram Bot

Cloud Run **Service** that receives webhooks from Telegram and fans out to the
`teams_analyzer` Cloud Run **Job**. Pure orchestrator — no heavy logic lives
here.

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
4. Map command → `ANALYSIS_MODE` and call `job_trigger.trigger_analyzer_job`
   to execute the Cloud Run Job.

```
/analizar  →  ANALYSIS_MODE=all
/myteam    →  ANALYSIS_MODE=my_team
/mercado   →  ANALYSIS_MODE=market
/alinear   →  ANALYSIS_MODE=alinear
/help      →  static HTML message (no job)
```

`job_trigger.trigger_analyzer_job` lives in this package because the env-var
override (`ANALYSIS_MODE=<mode>`) is what makes the same job behave like five
different commands. The actual rendering and posting back to the chat is done
by `teams_analyzer`, not here.

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
  -d "url=https://biwenger-telegram-bot-.../telegram/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

## 📋 Bot command menu

`setup_commands.py` registers the menu shown in Telegram's `/` UI. Run it once
after creating the bot or whenever commands change:

```bash
python3 packages/biwenger_tools/telegram_bot/setup_commands.py
```

## 🚀 Runtime config

Bots run with `cpu=0.5 concurrency=1` (GCP forbids `cpu<1` with
`concurrency>1`). The values are baked into `.github/workflows/deploy.yml`, so
every CI deploy reapplies them — no drift.

See [`docs/operations.md`](../../../docs/operations.md) for build/test/deploy
commands.
