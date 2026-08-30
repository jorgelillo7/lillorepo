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
    > not run flake8, Black or the tests. The change still goes through
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
    | `POST` | `/digests/daily` | Cron — my team + market images, lineup, auto-bid summary and offers (chained, Scheduler only) |
    | `POST` | `/league/compare` | Every squad ranked by value and projection — bot's `/comparar`, owner's chat only |
    | `POST` | `/market/auto-bid` | Tiered auto-bid on the daily market — chained into `/digests/daily` at 09:00 Madrid; also exposed standalone for the bot's `/pujar` manual trigger |

  * **Substitutes strong enough to start:** JP predicts the XI rather than
    reporting it, so a player it leaves out still starts when his projection
    clears `LINEUP_SUB_STARTS_ABOVE` (350). Raise it to trust JP more, lower it
    to trust the projection more — no deploy needed:

    ```bash
      # takes effect now, and lasts until the next deploy
      gcloud run services update biwenger-api --region europe-southwest1 \
        --update-env-vars LINEUP_SUB_STARTS_ABOVE=400

      # to keep it, set the repository variable the deploy reads
      gh variable set LINEUP_SUB_STARTS_ABOVE --body 400
    ```

    Both, in that order: `gcloud` for this matchday, `gh variable` so the next
    deploy does not put it back to 350. The same rule as
    `DRAFT_APPLY_TO_BIWENGER` — `deploy.yml` rewrites the whole env block, so an
    env var set only on Cloud Run survives exactly until someone merges.

  * **Offer notifications when the squad is on the market:** listing players
    returns one offer each, so `/ofertas` used to arrive as one message per
    listed player. Rejected offers now collapse into a single no-button digest
    that still names every one and its price; accept them in the Biwenger app
    if you disagree. To get a message per offer back:

    ```bash
      gcloud run services update biwenger-api --region europe-southwest1 \
        --update-env-vars OFFERS_MUTE_REJECTED=0
      gh variable set OFFERS_MUTE_REJECTED --body 0
    ```

    Same two-step rule as above.

    Set too high, a benched star costs a matchday; too low, a genuine reserve
    displaces someone who is actually playing. The 350 default is a judgement —
    nothing measures how often JP's predicted eleven is right.

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

    **Silence is the normal state.** Three things break it, and each means
    something different:

    | Log line | What it means | What to do |
    |---|---|---|
    | *JP status never seen before* | JP invented a status outside the six measured on 2026-08-08 (`ok`, `ok-available`, `injured`, `doubt`, `sanctioned`, `other`). It is being treated as playable | Decide whether it belongs in `CANNOT_PLAY`, then add it to `OBSERVED_JP_STATUS` |
    | *Fixture status never seen before* | A `nextMatch.status` other than `pending`. **This is the one worth waiting for**: `_sf` has scored `break` as 0 for months and the value has never been observed in 533 players | Confirm the player really had no fixture. If `break` never appears, delete the branch — as happened with `suspended` |
    | *Providers disagree on availability* | One says the player can be fielded and the other does not. Two cases in 533 on 2026-08-08: JP `ok` vs Biwenger `injured` (indefinite return), and JP `other` vs Biwenger `discarded` ("Sanción FIFA") | Nothing automatic. JP remains the only source a decision reads. Collect these until there are enough to justify a rule |

    The constants are named `OBSERVED_*` rather than `HANDLED_*` on purpose:
    they record what has been **seen in the wild**, so a value the code handles
    but has never encountered still reports its first sighting.

    The digest-chained auto-bid honours `AUTO_BID_PAUSED_UNTIL` (ISO date,
    default in `api/config.py`) — pause semantics are specified in
    [`daily-digest`](../../openspec/specs/biwenger_tools/daily-digest/spec.md)
    ("Config-driven auto-bid pause"). Override without a deploy:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars AUTO_BID_PAUSED_UNTIL=2026-09-01
    ```

    The digest also **sets the lineup** every morning, so a player who arrived
    overnight is fielded without anyone opening the app. It PUTs to Biwenger,
    so it has its own kill switch — a step that writes needs one that does not
    require a release:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars DAILY_LINEUP_ENABLED=false
    ```

    The league value snapshot chained after it has its own switch, and is the
    first thing to drop if the 09:00 budget gets tight — it pays one squad
    read per manager:

    ```bash
    gcloud run services update biwenger-api --region europe-southwest1 \
      --update-env-vars DAILY_LEAGUE_VALUES_ENABLED=false
    ```

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

It shows up on `/{season}/salseo` within a minute — the manifest is written with
`max-age=60` and the web caches it for 600 s per instance.

**Manual fallback** — if the bot or the bucket write is broken:

```bash
  gcloud storage cp portada.jpg gs://biwenger/periodico/26-27/2026-08-14.jpg
  gcloud storage cp gs://biwenger/periodico/26-27/index.json .
  # add {"fecha": "2026-08-14", "titulo": "…"} to the list, newest first
  gcloud storage cp index.json gs://biwenger/periodico/26-27/index.json \
      --cache-control="public, max-age=60"
```

Without that `--cache-control` the manifest keeps serving from the edge for an
hour (the bucket default), so the new cover appears late for everyone.

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

## 🏁 Draft anual

Una vez al año, en pretemporada. El bot arbitra desde el supergrupo de Telegram:
lleva el turno, el presupuesto y la composición, y —si el flag está encendido—
aplica el traspaso en Biwenger. Comportamiento completo en
`openspec/specs/biwenger_tools/draft/spec.md`.

### 1. Abrir el draft (sube el CSV y arranca el reloj)

Se exporta a mano desde Biwenger **el día pactado de cierre de mercado** — no se
descarga solo a propósito: una exportación tardía trae precios equivocados.

Un solo comando sube el CSV, marca el draft abierto, sella el instante inicial y
manda el mensaje de bienvenida al grupo. Sin `--write` solo enseña lo que haría:

```bash
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/open.py \
    --csv ~/Downloads/primera-division.csv --write
```

Sellar el instante inicial no es cosmético: en el draft 26-27 nadie lo registró,
así que las esperas por turno solo existían a partir del pick 49 y las anteriores
hubo que rescatarlas de Cloud Logging.

Deja también una copia inmutable, para que conste con qué precios se jugó:

```bash
gcloud storage cp primera-division.csv \
    gs://biwenger/draft/26-27/market-$(date +%F).csv
```

La api cachea el mercado por instancia, así que **re-subir el CSV no basta para
que lo relea**: hay que forzar revisiones nuevas (`gcloud run services update
biwenger-api --update-env-vars DEPLOY_TIME=...`) o esperar al siguiente arranque
en frío.

**El cierre es automático** *si la revisión desplegada lo trae*. Cuando cae el
último pick el draft se marca cerrado y `/pick` y `/deshacer` dejan de aceptar
órdenes. Es deliberado: `/deshacer` ejecuta un `release_player` + `apply_bonus`
reales, y en octubre eso no deshace un pick, vende un jugador a mitad de
temporada. Ver "Cerrar el draft" abajo para el caso en que no salte.

### 2. Pase de lista

Cada presidente escribe `/soy` en el grupo y pulsa su nombre. Queda guardado en
`draft/{temporada}/managers` y **sobrevive al reset**, así que se hace una sola
vez aunque se ensaye antes.

### 3. Encender la escritura en Biwenger

Sale apagada (`DRAFT_APPLY_TO_BIWENGER=false`): con el flag off el draft se
ensaya entero —validación, turnos, Firestore, mensajes— sin mover un jugador.

El valor lo fija la **variable de repositorio** del mismo nombre, porque el
deploy usa `--set-env-vars`, que reemplaza el bloque entero: cambiarlo sólo en
Cloud Run lo perdería en el siguiente despliegue.

```bash
gh variable set DRAFT_APPLY_TO_BIWENGER --body true   # o false
```

### 4. Reset entre el ensayo y el draft real

```bash
python3 packages/biwenger_tools/scripts/draft/reset.py --season 26-27
python3 packages/biwenger_tools/scripts/draft/reset.py --season 26-27 --apply
```

Antes de resetear, **comprueba en Biwenger que las plantillas están vacías**. El
reset borra los fichajes de Firestore pero no toca Biwenger: si quedara alguno
asignado allí, se pierde el rastro de que existe. Si los deshiciste con
`/deshacer` ya están devueltos; si no, quítalos desde el panel de admin primero.

### 5. Deshacer un fichaje

`/deshacer` en el grupo, sólo el admin (`draft_admin_telegram_id` en el secreto
`telegram-bot-config-regional`, un id de **usuario**, siempre positivo). Devuelve
el jugador al mercado, reintegra el precio y rebobina el turno. Encadenable: cada
llamada deshace el último fichaje.

### 6. Cerrar el draft (y guardar el histórico)

```bash
PYTHONPATH=. python3 packages/biwenger_tools/scripts/draft/close.py --write
```

Cierra, escribe `{temporada}/disponibilidad.md` + `.csv` en la skill y despide al grupo.
Sin `--write` sólo enseña lo que haría. Se niega a cerrar con picks pendientes
salvo `--force --reason "..."`.

Dos motivos para que exista, aunque el cierre sea automático:

- **`close_draft()` no se alcanza por ningún otro sitio dentro de la api**: es un
  efecto del último pick. Si el pick final cae con una revisión antigua
  desplegada, el draft se queda abierto para siempre y `/deshacer` sigue
  vendiendo jugadores de verdad.
- **El histórico no lo puede escribir la api.** Corre en Cloud Run y no toca este
  repo. `{temporada}/disponibilidad.csv` es lo que lee `archetypes.py --history` al año
  siguiente, así que si nadie lo genera, el año que viene no hay referencia.

Los dos ficheros **se commitean**. El resto de salidas de la skill están
gitignoradas a propósito.

---

## 🛠️ Firestore maintenance scripts

One-off surgical edits live under `packages/biwenger_tools/scripts/`
(run as `python3 packages/biwenger_tools/scripts/<script>.py` from the repo
root). All default to dry-run; pass `--apply` to write. They use ADC (`gcloud auth application-default login` once) and respect `FIRESTORE_PROJECT` / `GOOGLE_CLOUD_PROJECT`.

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
- **`draft/reset.py`** — wipe `draft/{season}/picks` + `state` between a
  rehearsal and the real draft, and again at the rollover. Keeps
  `draft/{season}/managers` unless `--managers` is passed: those bindings are
  the `/soy` roll-call, and repeating it with seven people waiting is the
  friction the bot exists to remove.

Usage pattern is the same everywhere: run without `--apply` first, review, then re-run with `--apply`.

For the Firestore data model these scripts operate on, see [`docs/firestore.md`](../../docs/firestore.md).
