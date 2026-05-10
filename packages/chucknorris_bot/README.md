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

Originally a Node.js app deployed on Heroku ([jorgelillo7/ChuckNorrisJokesBot](https://github.com/jorgelillo7/ChuckNorrisJokesBot)).
Rewritten in Python and moved into this monorepo to share infrastructure and avoid managing a second GCP project.
