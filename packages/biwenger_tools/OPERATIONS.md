# 🛠️ Operations — biwenger_tools

Per-module commands (run, test, Docker, deploy) for the Biwenger platform, plus
the season rollover and Firestore maintenance runbooks.

Repo-wide procedures (prerequisites, Python dependency workflow, secrets,
linter, GCP cost/cleanup) live in [`docs/operations.md`](../../docs/operations.md).

**What each capability does** — the tier rules, the clausulazo house rules, the
digest SLO, the offer-decision algorithm — lives in the behaviour specs at
[`openspec/specs/biwenger_tools/`](../../openspec/specs/biwenger_tools/). This
file is the operational how-to (run, test, deploy, env vars); the specs are the
single source of *what must be true*.

📜 Index

- [1. Biwenger Web App](#1-biwenger-web-app)
- [2. Scraper Job](#2-scraper-job)
- [3. Biwenger API](#3-biwenger-api)
- [4. Biwenger Bot](#4-biwenger-bot)
- [🗓️ Cambio de temporada](#️-cambio-de-temporada)
- [🛠️ Firestore maintenance scripts](#️-firestore-maintenance-scripts)

---

## 1. Biwenger Web App

  * **🏠 Run locally (development server):**

    ```bash
      bazel run //packages/biwenger_tools/web:web_local
    ```
  * **🧪 Tests:**
    ```
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest packages/biwenger_tools/web/tests/
    ```

  * **🐳 Run with Docker locally:**

    Useful for validating the production container (gunicorn + entrypoint.sh) before deploying.

    ```bash
      # Build and load the image into the local Docker daemon
      bazel run //packages/biwenger_tools/web:load_image_to_docker_local

      # Start the container
      docker run --rm -p 8080:8080 bazel/web:local
    ```

    > **Tip:** If `Ctrl+C` does not stop the container, use `docker ps` to find the container ID and then `docker kill <container_id>`.

  * **☁️ Deploy to production:**

    ```bash
      # Package and push the image to GCP
      bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64

      # Run the deploy script
      cd packages/biwenger_tools/web/
      ./deploy.sh
    ```

    URL: https://biwenger-summary-pjpqofuevq-no.a.run.app/25-26/

    > **Note:** The footer shows "local" when deploying from a local machine because the `GIT_COMMIT` env var is not set (defaults to `"local"`). CI injects the real value automatically via `${GITHUB_SHA::7}`. This is expected behaviour — it does not indicate a failed deploy.

  * **👀 Preview deploy (validate a change without touching production):**

    Publishes the current working tree as a Cloud Run revision that receives
    **0 % of traffic** and is reachable only through its own tagged URL. Use it
    to check a UI change from a phone, or from any machine that can't run the
    app locally. Everyone else keeps seeing the live revision.

    ```bash
      # 1. Push the image (same step as a production deploy)
      bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64

      # 2. Deploy it as a tagged revision with no traffic
      cd packages/biwenger_tools/web/
      ./deploy.sh --no-traffic --tag preview
    ```

    URL: `https://preview---biwenger-summary-pjpqofuevq-no.a.run.app`
    (pattern: `https://<tag>---<service-host>`). Use a distinct `--tag` to keep
    two previews alive at once.

    Verify which revision serves real traffic before and after:

    ```bash
      gcloud run services describe biwenger-summary --region europe-southwest1 \
        --format='table(status.traffic.revisionName, status.traffic.percent, status.traffic.tag)'
    ```

    Clean up once validated — an untagged, trafficless revision is harmless but
    the tag clutters the service:

    ```bash
      gcloud run services update-traffic biwenger-summary \
        --region europe-southwest1 --remove-tags preview
    ```

    > **Cost:** none in practice. The service has no `minScale`, so a
    > preview revision with 0 % traffic scales to zero and bills nothing while
    > idle; you only pay the CPU/memory seconds of the requests you make to it
    > yourself (cents at most, inside the free tier). The image layers are
    > already in Artifact Registry from the push step.

    > **Not a substitute for CI.** A preview proves the page renders; it does
    > not run flake8, Black or the tests. The change still goes through
    > branch → PR → green checks → merge.

  * **🏆 Special-tournament winner images (Palmarés "Copas especiales"):**

    Public bucket `gs://biwenger-special-tournaments` (project `biwenger-tools`,
    us-central1, `allUsers:objectViewer`). The `/palmares` page builds an
    `<img>` per known cup from `{slug}/{temporada}` and drops the ones that
    404, so **adding a winner needs no redeploy** — just upload the file:

    ```bash
      # <slug> ∈ config.SPECIAL_TOURNAMENTS (santa-cup, castolo-cup, …)
      # <temporada> = the palmarés Firestore doc id (short "25-26" for
      #   rollover-skill seasons, long "2024-2025" for legacy docs).
      # The template tries .png then .jpg — either extension works.
      gcloud storage cp copa-santa-25-26.jpg \
          gs://biwenger-special-tournaments/santa-cup/25-26.jpg
    ```

    A brand-new cup *type* is one line in `config.SPECIAL_TOURNAMENTS` (that
    one does need a redeploy). Teammate `d.lucena9@gmail.com` has
    `storage.objectCreator` on the bucket.

## 2. Scraper Job

  * **Run locally:**

    ```bash
        bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
    ```

  * **Tests:**

    ```bash
      # Run tests with Bazel (verbose output)
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v

      # Force test run ignoring cache
      bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      # Run tests directly with pytest (requires venv activated)
      pytest packages/biwenger_tools/scraper_job/tests/
    ```

  * **Run with Docker locally:**

    Useful for validating the exact Cloud Run Job container before deploying.

    ```bash
        # Build and load the image into the local Docker daemon (secrets included)
        bazel run //packages/biwenger_tools/scraper_job:load_image_to_docker_local

        # Start the container
        docker run --rm bazel/scraper_job:local
    ```

  * **Deploy to production (Cloud Run Job):**

      * **Build and push the image to GCP:**
        ```bash
            bazel run //packages/biwenger_tools/scraper_job:push_image_to_gcp --platforms=//platforms:linux_amd64
        ```
      * **Create the Job (first time only):**
        ```bash
          gcloud run jobs create biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 \
              --set-secrets="/gdrive_sa/biwenger-tools-sa.json=biwenger-tools-sa-regional:latest" \
              --update-secrets="BIWENGER_CREDENTIALS_JSON=biwenger-credentials-regional:latest"
        ```
      * **Update the Job (when changing the image or secrets):**
        ```bash
          gcloud run jobs update biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 \
              --update-env-vars TEMPORADA_ACTUAL=26-27
        ```
      * **Execute the Job manually:**
        ```bash
          gcloud run jobs execute biwenger-scraper-data --region europe-southwest1
        ```

## 3. Biwenger API

Cloud Run **Service** that owns the Biwenger business logic over HTTP. Called
by the bot (every Telegram command) and by Cloud Scheduler (the daily digest).
Deployed with `--no-allow-unauthenticated`; invokers authenticate with an OIDC
ID token whose service account has `roles/run.invoker` on `biwenger-api`.

  * **Setup:** `.env` with Biwenger + Telegram credentials. The JP token lives
    inside `BIWENGER_CREDENTIALS_JSON.jp_auth_token`.

  * **Run locally:**

    ```bash
      bazel run //packages/biwenger_tools/api:api_local
    ```

  * **Tests:**

    ```bash
      bazel test //packages/biwenger_tools/api:api_tests --test_output=streamed --test_arg=-v
      bazel test //packages/biwenger_tools/api:api_tests --test_output=streamed --test_arg=-v --cache_test_results=no
      pytest packages/biwenger_tools/api/tests/
    ```

  * **Endpoints:**

    | Method | Path | What |
    |---|---|---|
    | `GET`  | `/health` | Liveness (do NOT use `/healthz` — GFE reserves it) |
    | `GET`  | `/version` | SHA + deploy time |
    | `GET`  | `/teams[?manager=<id>]` | One squad if `manager` is set; all managers + market otherwise |
    | `GET`  | `/managers` | League managers list (powers the bot's `/analizar` picker) |
    | `GET`  | `/market` | Transfer market (was `/mercado`) |
    | `POST` | `/lineups/auto-pick` | Pick + apply lineup (was `/alinear`) |
    | `GET`  | `/budget/recommendations` | Top affordable clausulazo targets per position |
    | `POST` | `/scraper/trigger` | Queue a scraper job execution (bot's `/scrapper`) |
    | `POST` | `/digests/daily` | Cron — my team + market images, then auto-bid summary (chained, Scheduler only) |
    | `POST` | `/market/auto-bid` | Tiered auto-bid on the daily market — chained into `/digests/daily` at 09:00 Madrid; also exposed standalone for the bot's `/pujar` manual trigger |

    The digest-chained auto-bid honours `AUTO_BID_PAUSED_UNTIL` (ISO date,
    default in `api/config.py`) — pause semantics are specified in
    [`daily-digest`](../../openspec/specs/biwenger_tools/daily-digest/spec.md)
    ("Config-driven auto-bid pause"). Override without a deploy:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars AUTO_BID_PAUSED_UNTIL=2026-09-01
    ```

  * **Smoke test:**

    ```bash
      URL=$(gcloud run services describe biwenger-api --region europe-southwest1 --format='value(status.url)')
      TOKEN=$(gcloud auth print-identity-token)
      curl -H "Authorization: Bearer $TOKEN" $URL/health
      curl -H "Authorization: Bearer $TOKEN" $URL/version
    ```

  * **Deploy:** CI on push to `master` when `packages/biwenger_tools/api/**`,
    `core/**`, `tools/**`, `docker/**` or `MODULE.bazel` changes.

## 4. Biwenger Bot

Cloud Run Service that receives Telegram webhooks and calls `biwenger-api`
over HTTP with an ID token. Stateless orchestrator — no business logic.

  * **Tests:**
    ```bash
      bazel test //packages/biwenger_tools/bot:bot_tests --test_output=streamed --test_arg=-v
    ```

  * **Register bot commands (one-shot, run after deploy or when commands change):**

    Must be run manually — CI does not call this automatically.

    ```bash
      PYTHONPATH=. python3 packages/biwenger_tools/bot/setup_commands.py
    ```

    This calls `setMyCommands` + `setChatMenuButton` so the slash-command menu in
    Telegram shows the current command list. Requires `TELEGRAM_BOT_TOKEN` in the
    local `.env` (or environment).

  * **Update the Telegram webhook URL** (after a destructive bot rename, etc.):

    ```bash
      curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
        -H "Content-Type: application/json" \
        -d "{\"url\":\"https://biwenger-bot-<hash>.run.app/telegram/webhook\",\"secret_token\":\"<WEBHOOK_SECRET>\"}"
    ```

  * **Deploy to production (Cloud Run Service):**

    CI deploys automatically on push to `master` when `packages/biwenger_tools/bot/**`
    changes. To deploy manually:

    ```bash
      bazel run //packages/biwenger_tools/bot:push_image_to_gcp \
          --platforms=//platforms:linux_amd64
      gcloud run deploy biwenger-bot \
          --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/bot \
          --region europe-southwest1 \
          --project biwenger-tools
    ```

---

## 🗓️ Cambio de temporada

El cambio de temporada es **manual e intencional** — ocurre cuando se resetea la liga en Biwenger (una vez al año). El flujo completo está automatizado por la skill `season-rollover`; los comandos manuales viven aquí.

### Pasos

1. **`deploy.yml`** — actualizar `TEMPORADA_ACTUAL` en el bloque `env:` global:
   ```yaml
   TEMPORADA_ACTUAL: "26-27"
   ```

2. **`packages/biwenger_tools/web/config.py`** — añadir la nueva temporada a `TEMPORADAS_DISPONIBLES`:
   ```python
   TEMPORADAS_DISPONIBLES = ["24-25", "25-26", "26-27"]
   ```

3. **`.env` locales** — actualizar `TEMPORADA_ACTUAL` en `web/.env` y `scraper_job/.env`.

4. **Commit + push a `master`** → el CI despliega ambos servicios automáticamente con la nueva temporada.

> Si necesitas cambiar la temporada en producción **sin redeploy**:
> ```bash
> gcloud run services update biwenger-summary --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> gcloud run jobs update biwenger-scraper-data --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> ```

---

## 🛠️ Firestore maintenance scripts

One-off surgical edits live under `packages/biwenger_tools/scripts/`
(run as `python3 packages/biwenger_tools/scripts/<script>.py` from the repo
root). All default to dry-run; pass `--apply` to write. They use ADC (`gcloud auth application-default login` once) and respect `FIRESTORE_PROJECT` / `GOOGLE_CLOUD_PROJECT`.

- **`biwenger_firestore_surgery.py`** — recovery toolkit for scraper mishaps (e.g. a `/scrapper` run against the wrong season). Three subcommands:
  - `list-messages <SEASON> [--author X] [--limit N]` — inspect `comunicados/{SEASON}/messages` and find a `doc-id`.
  - `move-message <FROM> <TO> --doc-id <ID> [--rename-author <NAME>]` — copy one message across seasons (same id_hash), optionally rewriting `autor`, and rebuild `participacion/{TO}/authors/{autor}` accordingly.
  - `wipe-season <SEASON>` — delete every doc under `comunicados`, `participacion`, `clausulazos`, `tabla_justicia` for that season.
- **`biwenger_rename_team.py`** — rename a team across `clausulazos/{season}/transfers` and rebuild `tabla_justicia/{season}/teams` from the corrected data.
- **`biwenger_recategorise.py`** — recompute `categoria` for every message and rebuild `participacion/{season}/authors`; supports `--autor-alias OLD=NEW`.
- **`biwenger_check_categorias.py`** — read-only audit of `categoria` mismatches.

Usage pattern is the same everywhere: run without `--apply` first, review, then re-run with `--apply`.

For the Firestore data model these scripts operate on, see [`docs/firestore.md`](../../docs/firestore.md).
