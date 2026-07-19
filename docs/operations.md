# 🛠️ OPERATIONS - Biwenger Tools

This guide centralises commands and workflows for **development, testing, deployment, and maintenance** of the Biwenger tools.

📜 Index

- [🛠️ OPERATIONS - Biwenger Tools](#️-operations---biwenger-tools)
  - [📋 Prerequisites](#-prerequisites)
  - [🚀 Project Modules](#-project-modules)
    - [1. Biwenger Web App](#1-biwenger-web-app)
    - [2. Scraper Job](#2-scraper-job)
    - [3. Biwenger API](#3-biwenger-api-api)
    - [4. Biwenger Bot](#4-biwenger-bot-bot)
    - [Extra. Core](#extra-core)
  - [📦 How to Add or Update Python Dependencies](#-how-to-add-or-update-python-dependencies)
    - [Step 1: Add the library to the module's `requirements.txt`](#step-1-add-the-library-to-the-modules-requirementstxt)
    - [Step 2: Regenerate the central `requirements.in`](#step-2-regenerate-the-central-requirementsin)
    - [Step 3: Regenerate the Lock File](#step-3-regenerate-the-lock-file)
    - [Step 4: Use the new library in `BUILD.bazel`](#step-4-use-the-new-library-in-buildbazel)
    - [Step 5: Verify with Bazel](#step-5-verify-with-bazel)
  - [🔐 Secrets Management](#-secrets-management)
    - [Examples: creating secrets in GCP](#examples-creating-secrets-in-gcp)
    - [Updating a secret (e.g. token.json)](#updating-a-secret-eg-tokenjson)
  - [💅 Linter and Auto-formatter (VS Code)](#-linter-and-auto-formatter-vs-code)
  - [🧹 GCP Cleanup and Cost Control](#-gcp-cleanup-and-cost-control)
    - [Artifact Registry](#artifact-registry)
  - [⚠️ Important Notes](#️-important-notes)


## 📋 Prerequisites

Before you start, make sure you have the following installed:

  * **Python 3.x**
  * **Visual Studio Code** with the [Bazel (The Bazel Team)](https://marketplace.visualstudio.com/items?itemName=BazelBuild.vscode-bazel) extension.
  * **Command-line tools:**
    ```bash
      brew install bazelisk
      brew install buildifier
    ```
  * **Google Cloud deployment:**
  ```bash
    gcloud auth login
    gcloud config set project biwenger-tools
    gcloud auth configure-docker europe-southwest1-docker.pkg.dev
  ```

**Important note:** Bazel manages all Python dependencies hermetically — no venv is needed to run, test, or build. A venv is only required for `pip-tools` (used to regenerate the lock file) and for IDE integration (linting, autocomplete).

  ```bash
    # Only needed for dependency management and IDE support
    python3 -m venv venv
    source venv/bin/activate
    pip install pip-tools
  ```

## 🚀 Project Modules

Commands for running each component.

### 1\. Biwenger Web App

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

### 2\. Scraper Job

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

### 3\. Biwenger API (`api`)

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
    default in `api/config.py`): while today (Madrid) is before that date the
    digest posts a pause note instead of bidding. `/market/auto-bid` (bot's
    `/pujar`) ignores the pause. Override without a deploy:

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

### 4\. Biwenger Bot (`bot`)

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

### 5\. Be Water Web (`be_water`)

Runs against its **own GCP project** (`be-water-app`) — see `INFRA.md` for the
inventory and `.github/workflows/README.md` for the cross-project deploy grants.

  * **🏠 Run locally (development server):**

    ```bash
      bazel run //packages/be_water/web:web_local
    ```
  * **🧪 Tests:**
    ```
      bazel test //packages/be_water/web:web_tests --test_output=streamed --test_arg=-v
    ```

  * **🔄 Catalog sync (idempotent, merges the in-repo dataset into Firestore):**

    Runs monthly in production (Scheduler `be-water-catalog-sync-monthly`,
    day 1 09:00 Madrid → Cloud Run Job `be-water-catalog-sync`). Manual runs:

    ```bash
      # local, against prod Firestore via ADC
      bazel run //packages/be_water/web:sync_local

      # or execute the production job
      gcloud run jobs execute be-water-catalog-sync \
          --region europe-southwest1 --project be-water-app
    ```

    > Safe to re-run: verified waters are never clobbered, label-backed
    > minerals and user photos survive. It notifies Telegram (creds from the
    > consolidated secret, or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env
    > locally) about changes and about waters the dataset doesn't know
    > (typos or novelties).

  * **☁️ Deploy to production:**

    Normally via CI (`deploy-be-water` job on merge to master). Manual fallback:

    ```bash
      bazel run //packages/be_water/web:push_image_to_gcp --platforms=//platforms:linux_amd64
      gcloud run deploy be-water \
          --image europe-southwest1-docker.pkg.dev/be-water-app/be-water-docker/web \
          --region europe-southwest1 \
          --project be-water-app
    ```

    URL: https://be-water-lzqhg7kcoa-no.a.run.app

### Extra\. Core

  * **Tests:**
    ```
      bazel test //core:core_tests --test_output=streamed --test_arg=-v
      bazel test //core:core_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest core/tests/
    ```

-----

## 📦 How to Add or Update Python Dependencies

The project uses a three-level system to manage dependencies, keeping modules isolated and guaranteeing 100% reproducible builds.

1.  **`[module]/requirements.txt`** (e.g. `core/requirements.txt`): The **starting point and source of truth**. This is where you, as a developer, add or remove the libraries a specific module needs.
2.  **`requirements.in`**: An **intermediate, auto-generated file**. It consolidates the lists from all modules into a single place for the next tool. **Never edit this file by hand.**
3.  **`requirements_lock.txt`**: The **final, locked file** generated by the computer. It contains the exact list of all libraries (direct and indirect) with their versions and hashes — what Bazel uses. **Never edit this file by hand.**

The workflow for adding a new library (using `numpy` in the `core` module as an example):

### Step 1: Add the library to the module's `requirements.txt`

Decide that the `core` module needs `numpy`. Open `core/requirements.txt` and add it.

**File: `core/requirements.txt`**

```diff
requests
google-api-python-client
google-auth-oauthlib
google-auth
python-dateutil
python-json-logger
black
flake8
pytest
requests-mock
+ numpy
```

-----

### Step 2: Regenerate the central `requirements.in`

Run this command from the project root. It will pick up the changes you made in `core/requirements.txt` and update the central file.

```bash
{
  for req_file in core/requirements.txt \
    packages/biwenger_tools/scraper_job/requirements.txt \
    packages/biwenger_tools/api/requirements.txt \
    packages/biwenger_tools/bot/requirements.txt \
    packages/biwenger_tools/web/requirements.txt \
    packages/chucknorris_bot/bot/requirements.txt; do
    echo; echo "# From: $req_file"; cat "$req_file"
  done
} > requirements.in
```

-----

### Step 3: Regenerate the Lock File

This command reads the `requirements.in` you just generated and resolves all dependencies, creating the final `requirements_lock.txt`.

*(Remember to have `pip-tools` installed: `pip install pip-tools`)*

```bash
pip-compile requirements.in -o requirements_lock.txt
```

-----

### Step 4: Use the new library in `BUILD.bazel`

Now that the library is available to Bazel, go to `core/BUILD.bazel` and add it to the `deps` list of the **most specific sub-target** that needs it.

`core/BUILD.bazel` exposes granular targets — use the right one to avoid bloating other packages:

| Target | When to add here |
|---|---|
| `//core:gcp` | Library used by `sdk/gcp.py` or `utils.py` |
| `//core:telegram` | Library used by `sdk/telegram.py` |
| `//core:biwenger` | Library used by `sdk/biwenger.py` |
| `//core` (umbrella) | Shared by all of the above |

Remember that Bazel converts hyphens (-) to underscores (_). For numpy, the name is the same.

**File: `core/BUILD.bazel`** (example: adding `numpy` to the `gcp` target)

```python
py_library(
    name = "gcp",
    srcs = ["sdk/gcp.py", "utils.py"],
    deps = [
        ":_init",
        "@pypi//google_api_python_client",
        # ... (other dependencies)
        # Add the new dependency
        "@pypi//numpy",
    ],
    visibility = ["//visibility:public"],
)
```

-----

### Step 5: Verify with Bazel

Finally, run a Bazel command to confirm everything works.

  ```bash
  bazel build //...

  ```

If the command completes successfully, you have added the dependency in a clean, isolated, and reproducible way.



## 🔐 Secrets Management

  * **Local development:** Use `.env` files at the root of each module.
  * **Production:** Use **Google Secret Manager**.

### Examples: creating secrets in GCP
```bash
# Create a secret from a file (e.g. service account)
gcloud secrets create biwenger-tools-sa-regional \
  --data-file="biwenger-tools-sa.json" \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create secrets from the command line
echo -n "YOUR_EMAIL@gmail.com" | gcloud secrets create biwenger-email-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "YOUR_PASSWORD" | gcloud secrets create biwenger-password-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "DRIVE_FOLDER_ID" | gcloud secrets create gdrive-folder-id-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"
```

### Updating a secret (e.g. token.json):
```bash
gcloud secrets versions add token_json --data-file="token.json"
```

---
## 💅 Linter and Auto-formatter

Flake8 (linter) and Black (formatter) run **on every push to `master`** as
the `lint` job in `.github/workflows/deploy.yml`. A lint failure blocks
`test` and the deploy.

Editor and CLI usage, pinned versions, and how to upgrade live in
[`setup/linter.md`](setup/linter.md).

Quick local invocation (same hermetic Python 3.13 toolchain as CI — no
version drift, no pip install needed):

```bash
bash scripts/lint.sh         # check
bash scripts/lint.sh --fix   # apply black in place
```

Under the hood: `bazel run //tools/lint:black -- ...` and `//tools/lint:flake8`.
The first invocation is slow (Bazel resolves the lint targets); subsequent
calls are cached.


## 🧹 GCP Cleanup and Cost Control

### Artifact Registry

  * **Create the Docker repository (first time only):**

    ```bash
    gcloud artifacts repositories create biwenger-docker \
        --repository-format=docker \
        --location=europe-southwest1 \
        --description="Docker images for Biwenger Tools"
    ```

  * **List images in the repository:**

    ```bash
    gcloud artifacts docker images list europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker
    ```

  * **Clean up old images (script):**

    ```bash
    cd scripts/
    ./clean-images-artifact.sh
    ```

    > This script deletes all old images, keeping only the one tagged `latest`.
    > Covers both registries: `biwenger-docker` (biwenger-tools) and
    > `be-water-docker` (be-water-app).

  * **Review costs (script):**

    ```bash
    cd scripts/
    ./check-gcp-costs.sh
    ```

    > Audits **both projects** (`biwenger-tools` + `be-water-app`) against the
    > GCP *Free Tier*, plus the billing-account-wide Secret Manager version
    > count. Pass `--project=X` to audit a single project.

    * **Clean local Docker containers:**
    ```
     docker image prune -f
     ```

-----

## 🗓️ Cambio de temporada

El cambio de temporada es **manual e intencional** — ocurre cuando se resetea la liga en Biwenger (una vez al año).

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

One-off surgical edits live under `scripts/`. All default to dry-run; pass `--apply` to write. They use ADC (`gcloud auth application-default login` once) and respect `FIRESTORE_PROJECT` / `GOOGLE_CLOUD_PROJECT`.

- **`biwenger_firestore_surgery.py`** — recovery toolkit for scraper mishaps (e.g. a `/scrapper` run against the wrong season). Three subcommands:
  - `list-messages <SEASON> [--author X] [--limit N]` — inspect `comunicados/{SEASON}/messages` and find a `doc-id`.
  - `move-message <FROM> <TO> --doc-id <ID> [--rename-author <NAME>]` — copy one message across seasons (same id_hash), optionally rewriting `autor`, and rebuild `participacion/{TO}/authors/{autor}` accordingly.
  - `wipe-season <SEASON>` — delete every doc under `comunicados`, `participacion`, `clausulazos`, `tabla_justicia` for that season.
- **`biwenger_rename_team.py`** — rename a team across `clausulazos/{season}/transfers` and rebuild `tabla_justicia/{season}/teams` from the corrected data.
- **`biwenger_recategorise.py`** — recompute `categoria` for every message and rebuild `participacion/{season}/authors`; supports `--autor-alias OLD=NEW`.
- **`biwenger_check_categorias.py`** — read-only audit of `categoria` mismatches.

Usage pattern is the same everywhere: run without `--apply` first, review, then re-run with `--apply`.

---

## ⚠️ Important Notes

  * **Do not commit** the credentials file `biwenger-tools-sa.json`.
  * If a deployment fails, check the **logs in the GCP console** (Cloud Run, Cloud Build, etc.).
  * Make sure you have a `.env` file configured in each module for local development.
