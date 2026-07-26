# 🛠️ Operations — chucknorris_bot

Commands for running, testing and deploying the Chuck Norris Telegram bot.
It shares the `biwenger-tools` GCP project and Artifact Registry (see the
disclaimer in [`README.md`](README.md)).

Repo-wide procedures (prerequisites, Python dependency workflow, secrets,
linter, GCP cost/cleanup) live in [`docs/operations.md`](../../docs/operations.md).

**What the bot does** — webhook gating, command/keyboard dispatch, joke-fetch
fallback — lives in the behaviour spec at
[`openspec/specs/chucknorris_bot/chuck-jokes/spec.md`](../../openspec/specs/chucknorris_bot/chuck-jokes/spec.md).
This file is the operational how-to.

---

## Bot

  * **🧪 Tests:**

    ```bash
      bazel test //packages/chucknorris_bot/bot:bot_tests --test_output=streamed --test_arg=-v
    ```

  * **🏠 Run locally:**

    ```bash
      bazel run //packages/chucknorris_bot/bot:bot_local
    ```

  * **☁️ Deploy to production (Cloud Run Service):**

    ```bash
      # Build and push image
      bazel run //packages/chucknorris_bot/bot:push_image_to_gcp --platforms=//platforms:linux_amd64

      # Deploy to Cloud Run
      cd packages/chucknorris_bot/bot/ && ./deploy.sh
    ```

  * **🔗 Register the Telegram webhook (after deploy):**

    ```bash
      curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
        -d "url=https://<CLOUD_RUN_URL>/telegram/webhook" \
        -d "secret_token=<WEBHOOK_SECRET>"
    ```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret
```
