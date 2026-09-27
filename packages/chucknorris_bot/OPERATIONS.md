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

    CI deploys on every push to `master` that touches
    `packages/chucknorris_bot/**`, mounts `chucknorris-secrets` as
    `CHUCKNORRIS_BOT_CONFIG_JSON`, and then runs `setup_commands.py` to refresh
    the slash-command list. Manual redeploy of a locally built image:

    ```bash
      bazel run //packages/chucknorris_bot/bot:push_image_to_gcp --platforms=//platforms:linux_amd64
      cd packages/chucknorris_bot/bot/ && ./deploy.sh
    ```

    `deploy.sh` changes only the image and the version stamp; the secret mount,
    resources and env stay as CI left them.

  * **🔗 Register the Telegram webhook (once, or after the URL changes):**

    `setup_commands.py` only refreshes the commands, so the webhook is a manual
    call. Read the token and secret from Secret Manager into a file — never
    through a filtered shell, which truncates the value
    ([`docs/operations.md`](../../docs/operations.md#one-secret-per-package)):

    ```bash
    gcloud secrets versions access latest --secret=chucknorris-secrets \
      --project=biwenger-tools --out-file=/tmp/cn.json
    URL=$(gcloud run services describe chucknorris-bot --region europe-southwest1 \
      --project biwenger-tools --format='value(status.url)')
    python3 - "$URL" <<'PY'
    import json, sys, urllib.parse, urllib.request
    cfg = json.load(open("/tmp/cn.json"))
    data = urllib.parse.urlencode({
        "url": sys.argv[1] + "/telegram/webhook",
        "secret_token": cfg["webhook_secret"],
    }).encode()
    api = f"https://api.telegram.org/bot{cfg['bot_token']}/setWebhook"
    print(urllib.request.urlopen(api, data).read().decode())
    PY
    rm /tmp/cn.json
    ```

## Configuration

Production reads one JSON secret, `chucknorris-secrets`
(`{"bot_token", "webhook_secret"}`), mounted as `CHUCKNORRIS_BOT_CONFIG_JSON`.
Locally, `config.py` falls back to plain variables — create
`packages/chucknorris_bot/bot/.env` (gitignored; the local Docker image bakes
it in, the pushed one never does):

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret
```
