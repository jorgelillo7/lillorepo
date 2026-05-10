# chucknorris_bot

A Telegram bot that delivers Chuck Norris facts on demand, powered by [chucknorris.io](https://api.chucknorris.io).

> **Disclaimer**: This should probably live in its own GCP project. It doesn't. Couldn't be bothered.

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + command list |
| `/help` | Show command list |
| `/random` | Random fact |
| `/science` | Science fact |
| `/food` | Food fact |
| `/animal` | Animal fact |
| `/dev` | Developer fact |

## Development

```bash
# Run tests
bazel test //packages/chucknorris_bot/bot:bot_tests --test_output=streamed --test_arg=-v

# Run locally
bazel run //packages/chucknorris_bot/bot:bot_local
```

## Deployment

```bash
# Build and push image
bazel run //packages/chucknorris_bot/bot:push_image_to_gcp --platforms=//platforms:linux_amd64

# Deploy to Cloud Run
cd packages/chucknorris_bot/bot/ && ./deploy.sh
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret
```

Register the webhook with Telegram after deploying:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://<CLOUD_RUN_URL>/telegram/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```

## Origin

This bot started life on **6 October 2015** as a Node.js + Express experiment — the first commit message was literally *"appbot example"*. Back then it ran on Heroku, used a Bootstrap landing page, and was wired up as a proof of concept for the Telegram Bot API, Node.js and Heroku all at once. It lived quietly at [`jorgelillo7/ChuckNorrisJokesBot`](https://github.com/jorgelillo7/ChuckNorrisJokesBot) for nearly a decade.

Fast-forward to 2026: same bot, same jokes API ([chucknorris.io](https://api.chucknorris.io)), completely different stack. Node.js → Python/Flask. Heroku → Google Cloud Run. Standalone repo → monorepo managed by Bazel. The Heroku `Procfile` is gone; so is the jQuery-flavoured landing page. What remains is the same silly idea, now sharing infrastructure with a Biwenger fantasy football analyzer because, well, why not.
