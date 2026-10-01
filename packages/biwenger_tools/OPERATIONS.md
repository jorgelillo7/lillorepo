# 🛠️ Operations — biwenger_tools

Per-module commands (run, test, Docker, deploy) for the Biwenger platform, plus
the season rollover and Firestore maintenance runbooks.

Repo-wide procedures (prerequisites, Python dependency workflow, secrets,
linter, GCP cost/cleanup) live in [`docs/operations.md`](../../docs/operations.md).
Setting the whole thing up from zero in another GCP project:
[`DEPLOY_YOUR_OWN.md`](DEPLOY_YOUR_OWN.md).

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
- [📰 League front pages (portadas)](#-league-front-pages-portadas)
- [🗓️ Season rollover](#️-season-rollover)
- [🏁 Annual draft](#-annual-draft)
- [🛠️ Firestore maintenance scripts](#️-firestore-maintenance-scripts)

---

## 1. Biwenger Web App

  * **🏠 Run locally (development server):**

    ```bash
      bazel run //packages/biwenger_tools/web:web_local
    ```

    Firestore and the competitions tab (Google Sheets) read through your ADC —
    there is no key file. Once per machine, log in with the Sheets scope, or
    the competitions page comes up empty:

    ```bash
      gcloud auth application-default login \
        --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets.readonly
    ```
  * **🧪 Tests:**
    ```
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
      bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v --cache_test_results=no

      pytest packages/biwenger_tools/web/tests/
    ```

  * **🐳 Run with Docker locally:**

    Useful for validating the production container (gunicorn + entrypoint.sh) before deploying.
    The image is linux/amd64 (what Cloud Run runs), so on an Apple-silicon Mac it
    runs emulated: fine to check it boots and serves, too slow for heavy work —
    matplotlib's `savefig` stalls under emulation and completes natively.

    ```bash
      # Build and load the image into the local Docker daemon
      bazel run //packages/biwenger_tools/web:load_image_to_docker_local

      # Start the container, lending it your ADC (Firestore + Sheets). Setting
      # GOOGLE_APPLICATION_CREDENTIALS here, on a local run, is fine — never
      # in BUILD.bazel or a deploy (docs/gcp.md).
      docker run --rm -p 8080:8080 \
        -v "$HOME/.config/gcloud/application_default_credentials.json:/adc.json:ro" \
        -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
        bazel/web:local
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

    URL: https://biwenger-summary-pjpqofuevq-no.a.run.app/26-27/

    `deploy.sh` changes only the image and the version stamp (`GIT_COMMIT` is
    your local `HEAD`, so commit first or the footer names the wrong code).
    Secrets, env vars and resources stay as the last CI deploy left them, and
    the next merge overwrites the stamp. Creating the service from zero is
    [`DEPLOY_YOUR_OWN.md`](DEPLOY_YOUR_OWN.md), not this script.

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

    **⚠️ Always clean up with `--to-latest`.** `--no-traffic` switches the
    service from "serve the latest revision" to traffic *pinned* to whatever
    revision was serving at that moment. It stays pinned: the next deploy from
    `master` builds and deploys fine, reports success, and still serves the old
    revision — a green CI run that shipped nothing. `--remove-tags` does **not**
    undo this.

    ```bash
      # Drop the preview tag AND restore latest-revision routing
      gcloud run services update-traffic biwenger-summary \
        --region europe-southwest1 --remove-tags preview
      gcloud run services update-traffic biwenger-summary \
        --region europe-southwest1 --to-latest

      # Delete the preview revision first if it is newer than the one you want
      # served — `--to-latest` routes to the newest ready revision.
      gcloud run revisions delete <preview-revision> --region europe-southwest1
    ```

    Confirm the service is back to latest-revision mode — `spec.traffic` must
    read `latestRevision: true`, not a pinned `revisionName`:

    ```bash
      gcloud run services describe biwenger-summary --region europe-southwest1 \
        --format='value(spec.traffic)'
    ```

    > **Cost:** none in practice. The service has no `minScale`, so a
    > preview revision with 0 % traffic scales to zero and bills nothing while
    > idle; you only pay the CPU/memory seconds of the requests you make to it
    > yourself (cents at most, inside the free tier). The image layers are
    > already in Artifact Registry from the push step.

    > **Not a substitute for CI.** A preview proves the page renders; it does
    > not run Ruff or the tests. The change still goes through
    > branch → PR → green checks → merge.

  * **🏆 Special-tournament winner images (Palmarés "Copas especiales"):**

    Public bucket `gs://biwenger` (project `biwenger-tools`, us-central1,
    `allUsers:objectViewer`), under the `special-tournaments/` prefix. The
    `/palmares` page builds an `<img>` per known cup from
    `special-tournaments/{slug}/{temporada}` and drops the ones that 404, so
    **adding a winner needs no redeploy** — just upload the file:

    ```bash
      # <slug> ∈ config.SPECIAL_TOURNAMENTS (santa-cup, castolo-cup, …)
      # <temporada> = the palmarés Firestore doc id (short "25-26" for
      #   rollover-skill seasons, long "2024-2025" for legacy docs).
      # The template tries .png then .jpg — either extension works.
      gcloud storage cp copa-santa-25-26.jpg \
          gs://biwenger/special-tournaments/santa-cup/25-26.jpg
    ```

    A brand-new cup *type* is one line in `config.SPECIAL_TOURNAMENTS` (that
    one does need a redeploy). A teammate also holds `storage.objectCreator` on the
    bucket; the grant names them, and this file does not need to.

    **Name the winner too.** The graphic alone forces a click to find out who
    won, so `palmares/{temporada}` carries a `copas` map keyed by the same
    slug; the caption renders it under the image. No redeploy — it is data:

    ```python
      db.document("palmares/25-26").set({"copas": {
          "santa-cup":   {"ganador": "Fabio", "equipo": "Rayo Entrebirras"},
          "castolo-cup": {"ganador": "Jorge", "equipo": "Farolillo Oracle United"},
      }}, merge=True)
    ```

    A season with no `copas` still renders the graphics, just without names.

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
        # Build and load the image into the local Docker daemon (bakes in the
        # local .env; the pushed image never carries it)
        bazel run //packages/biwenger_tools/scraper_job:load_image_to_docker_local

        # Start the container, lending it your ADC for Firestore
        docker run --rm \
          -v "$HOME/.config/gcloud/application_default_credentials.json:/adc.json:ro" \
          -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
          bazel/scraper_job:local
    ```

  * **Deploy to production (Cloud Run Job):**

      * **Build and push the image to GCP:**
        ```bash
            bazel run //packages/biwenger_tools/scraper_job:push_image_to_gcp --platforms=//platforms:linux_amd64
        ```
      * **Create the Job (first time only)** — matches the live job:
        ```bash
          gcloud run jobs create biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 --project biwenger-tools \
              --service-account=run-biwenger-scraper@biwenger-tools.iam.gserviceaccount.com \
              --memory=512Mi --cpu=1 --max-retries=3 --task-timeout=600s \
              --labels=app=biwenger \
              --set-env-vars TEMPORADA_ACTUAL=26-27 \
              --set-secrets="BIWENGER_CREDENTIALS_JSON=biwenger-secrets:latest,TELEGRAM_BOT_CONFIG_JSON=biwenger-secrets:latest"
        ```
      * **Update the Job** — what CI runs on every scraper change:
        ```bash
          gcloud run jobs update biwenger-scraper-data \
              --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/scraper_job \
              --region europe-southwest1 --project biwenger-tools \
              --service-account=run-biwenger-scraper@biwenger-tools.iam.gserviceaccount.com \
              --update-env-vars TEMPORADA_ACTUAL=26-27 \
              --update-secrets="BIWENGER_CREDENTIALS_JSON=biwenger-secrets:latest,TELEGRAM_BOT_CONFIG_JSON=biwenger-secrets:latest"
        ```
      * **Execute the Job manually:**
        ```bash
          gcloud run jobs execute biwenger-scraper-data --region europe-southwest1
        ```

  * **Board archive (`board_archive/{season}/entries`):** each run appends the
    season's new money entries; nothing is ever deleted. After the first deploy
    of the archive — and after any change to `board_entry_key` — execute the
    job by hand at once, while the board still reaches `seasonStarted`, instead
    of waiting for Sunday. Check it: the Telegram summary says how many entries
    were archived (~250 for a full season by late September), and a second run
    archives none.

## 3. Biwenger API

Cloud Run **Service** that owns the Biwenger business logic over HTTP. Called
by the bot (every Telegram command) and by Cloud Scheduler (the daily digest).
Private (no `allUsers` invoker); invokers authenticate with an OIDC
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
    | `GET`  | `/pact` · `POST` `/pact/toggle` | Read / flip the non-aggression pact — bot's `/pacto` |
    | `GET`  | `/market` | Transfer market — bot's `/mercado` |
    | `POST` | `/lineups/auto-pick` | Pick the lineup; applies it unless previewing — bot's `/alinear`, `/preview` |
    | `GET`  | `/budget/recommendations` | Top affordable clausulazo targets per position — bot's `/recomendar` |
    | `POST` | `/scraper/trigger` | Queue a scraper job execution — bot's `/scrapper` |
    | `POST` | `/emergency/clausulazo/preview` · `/execute` | Emergency clausulazo: plan, then buy on confirmation |
    | `POST` | `/emergency/rebuild/execute` | Execute a stored squad-rebuild plan |
    | `POST` | `/offers/inbox` · `/offers/decide` | Score the received offers — bot's `/ofertas` — and accept or reject one |
    | `GET`/`POST` | `/draft/managers` · `/register` · `/state` · `/pick` · `/pick/confirm` · `/undo` · `/export` | The annual draft, driven from the group (see "Annual draft") |
    | `POST` | `/periodico/portada` | Publish a front page sent to the bot (see "League front pages") |
    | `POST` | `/digests/daily` | Cron (Scheduler only) — squad + market images, lineup, auto-bid, clause-protection alert, offers scored ACEPTAR |
    | `POST` | `/league/compare` | Every squad ranked by value and projection — bot's `/comparar`, owner's chat only |
    | `POST` | `/league/cash` | Every manager's cash and max bid rebuilt from the board, plus the three players each rival can clause from us — bot's `/saldos`, owner's chat only |
    | `POST` | `/market/auto-bid` | Tiered auto-bid on the daily market — chained into `/digests/daily`; also the bot's `/pujar` |

  * **Substitutes strong enough to start:** JP predicts the XI rather than
    reporting it, so a player it leaves out still starts when his projection
    clears `LINEUP_SUB_STARTS_ABOVE` — **300** today, set by the repository
    variable (`deploy.yml` falls back to 350 when the variable is unset). Raise
    it to trust JP more, lower it to trust the projection more — no deploy
    needed:

    ```bash
      # takes effect now, and lasts until the next deploy
      gcloud run services update biwenger-api --region europe-southwest1 \
        --update-env-vars LINEUP_SUB_STARTS_ABOVE=400

      # to keep it, set the repository variable the deploy reads
      gh variable set LINEUP_SUB_STARTS_ABOVE --body 400
    ```

    Both, in that order: `gcloud` for this matchday, `gh variable` so the next
    deploy does not put it back. The same rule as
    `DRAFT_APPLY_TO_BIWENGER` — `deploy.yml` rewrites the whole env block, so an
    env var set only on Cloud Run survives exactly until someone merges.

    Set too high, a benched star costs a matchday; too low, a genuine reserve
    displaces someone who is actually playing. The default is a judgement —
    nothing measures how often JP's predicted eleven is right.

  * **Offer notifications when the squad is on the market:** listing players
    returns one offer each, so `/ofertas` used to arrive as one message per
    listed player. Rejected offers collapse into a single no-button digest
    that still names every one and its price; accept them in the Biwenger app
    if you disagree. To get a message per offer back:

    ```bash
      gcloud run services update biwenger-api --region europe-southwest1 \
        --update-env-vars OFFERS_MUTE_REJECTED=0
      gh variable set OFFERS_MUTE_REJECTED --body 0
    ```

    Same two-step rule as above.

  * **Provider watch — reading it, and what silence means:**

    Every lineup pick (the 09:00 digest, `/alinear`, `/preview`) runs
    `logic/provider_watch.py` over the squad first. It **decides nothing**: it
    writes a log line when Biwenger or Jornada Perfecta send something this
    code does not model, and swallows its own errors so it can never break a
    lineup.

    ```bash
      gcloud logging read \
        'resource.labels.service_name="biwenger-api" AND
         jsonPayload.name="packages.biwenger_tools.api.logic.provider_watch"' \
        --project=biwenger-tools --limit=20 --freshness=7d
    ```

    It watches **Biwenger and Jornada Perfecta only** — Oráculo is not
    watched, because nothing reads a *state* from it; the blend reads a
    number and treats a missing one as no opinion.

    **Silence is the normal state.** Four things break it, and each means
    something different:

    | Log line | What it means | What to do |
    |---|---|---|
    | *JP status never seen before* | JP invented a status outside the six measured on 2026-08-08 (`ok`, `ok-available`, `injured`, `doubt`, `sanctioned`, `other`). It is being treated as playable | Decide whether it belongs in `CANNOT_PLAY`, then add it to `OBSERVED_JP_STATUS` |
    | *No Jornada Perfecta entry for this player* | Biwenger has him, JP does not, so he scores 0 and is invisible to the optimizer. A couple of dozen missing names league-wide is normal; one of them *in the squad* is not | Check whether he is really unavailable, or whether the name match failed |
    | *Fixture status never seen before* | A `nextMatch.status` other than `pending`. `finished` arrived with the season and is **deliberately not acted on**: Biwenger freezes the eleven at the matchday's first kick-off, so from Saturday the daily run is building next week's lineup and a played fixture is stale input | Confirm what the value means before modelling it. `break` is handled but still unseen, so its first sighting is the one worth waiting for |
    | *Providers disagree on availability* | One says the player can be fielded and the other does not. Two cases in 533 on 2026-08-08: JP `ok` vs Biwenger `injured` (indefinite return), and JP `other` vs Biwenger `discarded` ("Sanción FIFA") | Nothing automatic. JP remains the only source a decision reads. Collect these until there are enough to justify a rule |

    The constants are named `OBSERVED_*` rather than `HANDLED_*` on purpose:
    they record what has been **seen in the wild**, so a value the code handles
    but has never encountered still reports its first sighting.

    The digest also writes the **projection ledger** — one document per round
    in `proyecciones`, holding the eleven the blend picked and the eleven
    Jornada Perfecta alone would have picked. It is written on every run
    while the round has not kicked off, overwriting, so what survives is the
    last projection before Biwenger freezes the eleven.

    Grade it by hand with
    `packages/biwenger_tools/scripts/projections/report.py`. **Read
    [`projection-ledger.md`](../../docs/technical/backend/projection-ledger.md)
    before acting on what it prints** — only rounds where the two elevens
    differed are evidence, and the script deliberately refuses a verdict until
    there are enough of them.

    Re-measure the auto-bid shares (`TIER_T*_OVERBID` in `auto_bid.py`)
    against the season's settled auctions, roughly once a month:

    ```bash
    PYTHONPATH=. python3 packages/biwenger_tools/scripts/auto_bid/calibrate.py
    ```

    Read-only. It prints, per price band, the share of auctions each overbid
    would have won and the smallest share that wins 70/80/90 % of them, next
    to what each tier bids today — plus the auctions we lost and what we paid
    over the runner-up in the ones we won. Price histories are cached per day
    under `scripts/auto_bid/.cache/`. Choosing new shares is a judgement: the
    market is split by price, the tiers by projection (see the auto-bid spec).

    The digest-chained auto-bid honours `AUTO_BID_PAUSED_UNTIL` (ISO date,
    default in `api/config.py`) — pause semantics are specified in
    [`daily-digest`](../../openspec/specs/biwenger_tools/daily-digest/spec.md)
    ("Config-driven auto-bid pause"). Override without a deploy:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars AUTO_BID_PAUSED_UNTIL=<YYYY-MM-DD>
    ```

    **That override, and the lineup switch below, last only until the next api
    deploy**: neither has a repository variable, and `deploy.yml` rewrites the
    env block. To make one stick, change its default in `api/config.py`.

    The digest also **sets the lineup** every morning, so a player who arrived
    overnight is fielded without anyone opening the app. It PUTs to Biwenger,
    so it has its own kill switch — a step that writes needs one that does not
    require a release:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars DAILY_LINEUP_ENABLED=false
    ```

    Squad values and the full offers inbox are not in the digest — both are
    on demand (`/comparar`, `/ofertas`). The digest only sends an offer
    scored ACEPTAR, plus a warning when a player's clause protection is about
    to end.

    09:00 is deliberately early and deliberately not optimal: Biwenger locks
    each player at *his* kickoff and a matchday can span twelve days, so this
    is a floor. `/alinear` stays the way to re-align closer to a match that
    matters.

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

  * **Run locally:**

    ```bash
      bazel run //packages/biwenger_tools/bot:bot_local
    ```

  * **Tests:**
    ```bash
      bazel test //packages/biwenger_tools/bot:bot_tests --test_output=streamed --test_arg=-v
    ```

  * **Commands, menu and webhook:** CI runs `bot/setup_commands.py` after every
    bot deploy. It calls `setMyCommands` + `setChatMenuButton`, and with
    `BIWENGER_BOT_URL` set it also re-registers the webhook with
    `allowed_updates=["message", "callback_query"]` — without `callback_query`
    Telegram silently drops menu taps, so never register the webhook by hand
    with a bare `setWebhook`. To run it locally (with `TELEGRAM_BOT_TOKEN` and
    `TELEGRAM_WEBHOOK_SECRET` in `bot/.env`):

    ```bash
      URL=$(gcloud run services describe biwenger-bot --region europe-southwest1 \
        --project biwenger-tools --format='value(status.url)')
      PYTHONPATH=. BIWENGER_BOT_URL="$URL/telegram/webhook" \
        python3 packages/biwenger_tools/bot/setup_commands.py
    ```

    Leave `BIWENGER_BOT_URL` out to refresh only the commands; Telegram keeps
    the last webhook.

  * **Deploy to production (Cloud Run Service):**

    CI deploys automatically on push to `master` when `packages/biwenger_tools/bot/**`
    changes. To redeploy a locally built image — only the image changes;
    secrets, env and resources stay as CI left them:

    ```bash
      bazel run //packages/biwenger_tools/bot:push_image_to_gcp \
          --platforms=//platforms:linux_amd64
      gcloud run deploy biwenger-bot \
          --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/bot \
          --region europe-southwest1 \
          --project biwenger-tools
    ```

---

## 📰 League front pages (portadas)

The league newspaper's covers shown on `/{season}/salseo`. They live in a public
bucket, not in Firestore: `gs://biwenger/periodico/{season}/{YYYY-MM-DD}.jpg`
plus a manifest `index.json` holding the headline of each date. The web reads
the manifest at request time, so publishing needs no deploy.

**Normal path — send it to the bot** (owner private chat only):

Send the image with a caption and the bot publishes it:

| Caption | Result |
|---|---|
| `Mañana empieza la guerra` | published under today's date (Madrid) |
| `2026-08-14 Mañana empieza la guerra` | published under that date |

Send it **as a file**, not as a photo: Telegram recompresses photos to ~1280 px
on the long side, which loses the body copy of a newspaper page. It must be a
JPEG (the web builds every URL as `.jpg`) and under 20 MB (the Bot API cannot
download more). Sending the same date again replaces that cover.

It shows up on `/{season}/salseo` within a minute — image and manifest are both
written with `max-age=60`, on top of the web's own 600 s per-instance cache.

**Manual fallback** — if the bot or the bucket write is broken:

```bash
  gcloud storage cp portada.jpg gs://biwenger/periodico/26-27/2026-08-14.jpg \
      --cache-control="public, max-age=60"
  gcloud storage cp gs://biwenger/periodico/26-27/index.json .
  # add {"fecha": "2026-08-14", "titulo": "…"} to the list, newest first
  gcloud storage cp index.json gs://biwenger/periodico/26-27/index.json \
      --cache-control="public, max-age=60"
```

Without `--cache-control` an object keeps serving from the edge for an hour
(the bucket default), so a new or corrected cover appears late for everyone.

---

## 🗓️ Season rollover

The rollover is **manual and deliberate** — it happens once a year, when the
league is reset in Biwenger. The `season-rollover` skill walks the whole flow
and opens the PR; the manual pieces are here.

### Steps

1. **`deploy.yml`** — bump `TEMPORADA_ACTUAL` in the global `env:` block:
   ```yaml
   TEMPORADA_ACTUAL: "26-27"
   ```

2. **`packages/biwenger_tools/web/config.py`** — add the new season to
   `TEMPORADAS_DISPONIBLES`, and its `COMPETICIONES_SHEET_IDS_<season>` entry
   (plus the GitHub secret and the `deploy.yml` line; the skill has them):
   ```python
   TEMPORADAS_DISPONIBLES = ["24-25", "25-26", "26-27"]
   ```

3. **Local `.env` files** — update `TEMPORADA_ACTUAL` in `web/.env` and
   `scraper_job/.env`.

4. **PR → green checks → merge** — CI redeploys the web, the api and the
   scraper job with the new season.

> To switch the season in production **without a redeploy** (the api reads the
> same variable as `CURRENT_SEASON`):
> ```bash
> gcloud run services update biwenger-summary --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> gcloud run services update biwenger-api --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> gcloud run jobs update biwenger-scraper-data --update-env-vars TEMPORADA_ACTUAL=26-27 --region europe-southwest1
> ```

---

## 🏁 Annual draft

Once a year, in pre-season. The bot referees from the Telegram supergroup: it
keeps the turn, the budget and the squad shape, and — when the flag is on —
applies each transfer in Biwenger. Full behaviour in
`openspec/specs/biwenger_tools/draft/spec.md`.

### 1. Open the draft (upload the CSV and start the clock)

The market is exported by hand from Biwenger **on the agreed market-close
day** — deliberately not downloaded automatically: a late export carries the
wrong prices.

One command uploads the CSV, marks the draft open, stamps the starting instant
and sends the welcome message to the group. Without `--write` it only shows
what it would do:

```bash
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/open.py \
    --csv ~/Downloads/primera-division.csv --write
```

Stamping the starting instant is not cosmetic: in the 26-27 draft nobody
recorded it, so per-turn waits only existed from pick 49 on and the earlier
ones had to be recovered from Cloud Logging.

Keep an immutable copy too, as the record of the prices the draft was played
with:

```bash
gcloud storage cp primera-division.csv \
    gs://biwenger/draft/26-27/market-$(date +%F).csv
```

The api caches the market per instance, so **re-uploading the CSV is not
enough to make it re-read**: force new revisions (`gcloud run services update
biwenger-api --update-env-vars DEPLOY_TIME=...`) or wait for the next cold
start.

**Closing is automatic** *if the deployed revision carries it*. When the last
pick lands the draft is marked closed and `/pick` and `/deshacer` stop
accepting orders. That is deliberate: `/deshacer` runs a real
`release_player` + `apply_bonus`, and in October that does not undo a pick, it
sells a player mid-season. See "Close the draft" below for when it does not
fire.

### 2. Roll call

Each manager types `/soy` in the group and taps their name. It is stored in
`draft/{season}/managers` and **survives the reset**, so it happens once even
with a rehearsal first.

### 3. Turn on writing to Biwenger

**Off between drafts** (`DRAFT_APPLY_TO_BIWENGER=false`): with the flag off the
whole draft can be rehearsed — validation, turns, Firestore, messages —
without moving a player. When the draft opens, decide whether this one writes
to Biwenger; if it does, turn it on **after** the rehearsal and its reset, and
before the first real pick.

Set it in both places: the **repository variable**, because the deploy uses
`--set-env-vars` and replaces the whole block (a Cloud Run–only change is lost
on the next deploy), and the running service, so it applies without waiting
for a deploy:

```bash
gh variable set DRAFT_APPLY_TO_BIWENGER --body true   # or false
gcloud run services update biwenger-api --region europe-southwest1 \
  --update-env-vars DRAFT_APPLY_TO_BIWENGER=true      # or false
```

Check the current value before opening:

```bash
gh variable list | grep DRAFT_APPLY
```

### 4. Reset between the rehearsal and the real draft

```bash
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/reset.py --season 26-27
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/reset.py --season 26-27 --apply
```

Before resetting, **check in Biwenger that the squads are empty**. The reset
deletes the picks from Firestore but does not touch Biwenger: a player still
assigned there loses every trace of existing. If you undid them with
`/deshacer` they are already back; otherwise remove them from the admin panel
first.

### 5. Undo a pick

`/deshacer` in the group, admin only (`draft_admin_telegram_id` in the
`biwenger-secrets` secret, a **user** id, always positive). It returns the
player to the market, refunds the price and rewinds the turn. Chainable: each
call undoes the latest pick.

### 6. Close the draft (and save the history)

```bash
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/close.py --write
```

It closes the draft, writes `{season}/disponibilidad.md` + `.csv` into the
skill and says goodbye to the group. Without `--write` it only shows what it
would do. It refuses to close with picks pending unless given
`--force --reason "..."`.

Two reasons it exists even though closing is automatic:

- **`close_draft()` is reachable from nowhere else in the api**: it is a side
  effect of the last pick. If the final pick lands on an old revision, the
  draft stays open forever and `/deshacer` keeps selling real players.
- **The api cannot write the history.** It runs on Cloud Run and never touches
  this repo. `{season}/disponibilidad.csv` is what `archetypes.py --history`
  reads the following year, so if nobody generates it there is no reference
  next year.

Both files **are committed**. The skill's other outputs are gitignored on
purpose.

### 7. After the draft

Turn `DRAFT_APPLY_TO_BIWENGER` back off (step 3, both commands with `false`),
so next year's rehearsal cannot move a real player.

`PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/postdraft.py --write`
compares everyone's draft and posts the verdict to the group, one message per
manager. Nothing prompts you to run it; without `--write` it is a rehearsal.

---

## 🛠️ Firestore maintenance scripts

One-off surgical edits live under `packages/biwenger_tools/scripts/`. Run them
from the repo root as `PYTHONPATH=. python3 packages/biwenger_tools/scripts/<script>.py`
— without `PYTHONPATH=.` they fail on `import core`. All default to a dry run:
the scraper and reset scripts write with `--apply`, the draft scripts and
`league_compare.py` (which post to Telegram) with `--write`. They use ADC
(`gcloud auth application-default login` once) and respect
`FIRESTORE_PROJECT` / `GOOGLE_CLOUD_PROJECT`.

- **`scraper/surgery.py`** — recovery toolkit for scraper mishaps (e.g. a `/scrapper` run against the wrong season). Three subcommands:
  - `list-messages <SEASON> [--author X] [--limit N]` — inspect `comunicados/{SEASON}/messages` and find a `doc-id`.
  - `move-message <FROM> <TO> --doc-id <ID> [--rename-author <NAME>]` — copy one message across seasons (same id_hash), optionally rewriting `autor`, and rebuild `participacion/{TO}/authors/{autor}` accordingly.
  - `wipe-season <SEASON>` — delete every doc under `comunicados`, `participacion`, `clausulazos`, `tabla_justicia` for that season.
- **`scraper/rename_team.py`** — rename a team across `clausulazos/{season}/transfers` and rebuild `tabla_justicia/{season}/teams` from the corrected data.
- **`scraper/recategorise.py`** — recompute `categoria` for every message and rebuild `participacion/{season}/authors`; supports `--autor-alias OLD=NEW`.
- **`scraper/check_categorias.py`** — read-only audit of `categoria` mismatches.
- **`draft/open.py`** — open the draft: upload the frozen market CSV,
  stamp the starting instant, greet the group. Dry-run without `--write`. See
  "Abrir el draft" above.
- **`draft/close.py`** — close the draft, write `{temporada}/disponibilidad.md` +
  `.csv` and say goodbye. Dry-run without `--write`. The api closes itself on
  the last pick but cannot write files, and `close_draft()` is reachable no
  other way. See "Cerrar el draft" above.
- **`draft/backfill_timings.py`** — recover `applied_at` /
  `waited_seconds` from Cloud Logging for picks made before timings shipped,
  and hand the clock over to live tracking.
- **`draft/postdraft.py`** — after closing, compare everyone's draft and post
  the verdict to the group, one message per manager. See "After the draft".
- **`league_compare.py`** — post the `/comparar` squad ranking to your own
  chat — never the draft group, which would hand every rival the projections.
- **`draft/reset.py`** — wipe `draft/{season}/picks` + `state` between a
  rehearsal and the real draft, and again at the rollover. Keeps
  `draft/{season}/managers` unless `--managers` is passed: those bindings are
  the `/soy` roll-call, and repeating it with seven people waiting is the
  friction the bot exists to remove.

Usage pattern is the same everywhere: run without the write flag first, review, then re-run with it.

For the Firestore data model these scripts operate on, see [`docs/firestore.md`](../../docs/firestore.md).
