# Deploy your own copy

Step by step, commands first, to run `biwenger_tools` for **your** Biwenger
league in **your** Google Cloud project: the API, the Telegram bot (your
private chat and the draft group), the weekly scraper and, optionally, the
web — all inside the **free tier**. Why each piece is the way it is lives in
[`docs/gcp.md`](../../docs/gcp.md) and [`OPERATIONS.md`](OPERATIONS.md).

> The commands mirror this project's production configuration (read off the
> live services), but have not been run end to end on a brand-new project.
> If one fails, the error usually names what is missing.

---

## 0. What you need

- A Google account with billing enabled. A card is required even though
  everything below stays within the free tier.
- `gcloud`, `bazelisk`, `docker` with `buildx`, `jq`, `openssl`, Python 3.13.
- A clone of this repo.
- The **Biwenger account** the tools will act as — email and password. For
  the draft it must be an **admin of the league** (Biwenger → your league →
  settings → administrators): drafting assigns players and refunds undos
  through the admin-only transfer and bonus endpoints, and a plain member
  gets refused.
- A **Jornada Perfecta** token (the projections the lineup, bids and offers
  run on). It is not public: **request it from the project owner**
  ([@jorgelillo7](https://github.com/jorgelillo7)).
- A Telegram account.

## 1. Pick your names

```bash
export PROJECT_ID=my-biwenger            # new, globally unique
export REGION=europe-southwest1          # Madrid; everything lives here…
export SCHED_REGION=europe-west1         # …except Cloud Scheduler, not offered in Madrid
export REPO=biwenger-docker
export REGISTRY=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO
export BUCKET=$PROJECT_ID-media          # globally unique
```

## 2. Project, APIs, storage

```bash
gcloud projects create $PROJECT_ID
gcloud billing projects link $PROJECT_ID --billing-account=<BILLING_ACCOUNT_ID>
gcloud config set project $PROJECT_ID

# compute: creates the default service account every service runs as.
gcloud services enable compute.googleapis.com run.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  firestore.googleapis.com cloudscheduler.googleapis.com iamcredentials.googleapis.com

gcloud firestore databases create --location=$REGION --type=firestore-native
gcloud firestore indexes composite create --collection-group=messages \
  --query-scope=COLLECTION \
  --field-config=field-path=categoria,order=ascending \
  --field-config=field-path=fecha,order=descending

gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev

# Newspaper front pages and cup images, read publicly by the web. In the US
# on purpose: Cloud Storage's free 5 GB only exists in US regions.
gcloud storage buckets create gs://$BUCKET --location=us-central1
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member=allUsers --role=roles/storage.objectViewer
```

## 3. Point the code at your project and your league

```bash
# Every image path names our project; swap it for yours (tracked files only).
git grep -l "biwenger-tools/biwenger-docker" -- MODULE.bazel packages/biwenger_tools \
  | xargs sed -i '' "s#europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker#$REGISTRY#g"
```

(`sed -i ''` is macOS; on Linux drop the `''`.)

Then edit — **all of these, even if you never draft**: the API resolves the
draft names when it starts, and an unknown one stops it from booting.

| File | Constant | Set it to |
|---|---|---|
| [`constants.py`](constants.py) | `LEAGUE_ID` | The number in your league's Biwenger URL |
| | `LEAGUE_MEMBERS` | `{biwenger_user_id: "Name"}` for every manager |
| | `NON_PLAYING_MEMBER_IDS` | Accounts that post but do not compete, or empty |
| | `DRAFT_ORDER_NAMES` | Your managers, by those names |
| | `H2H_ROUNDS` | Your managers, or the H2H tests fail |
| [`api/logic/draft.py`](api/logic/draft.py) | `DEFAULT_BUDGET` | Your league's **starting balance** — `/saldos` rebuilds everyone's cash from it |
| | `BUDGET_OVERRIDES` | `{}` (ours gives one manager a cup prize) |

`/saldos` also assumes the league's max bid is *a quarter of the team value*
(Biwenger → league settings). With another rule, the cash column is still
right and the max-bid column is not.

## 4. The base image

Every service extends one pre-built image with all the Python dependencies
already installed — that is what keeps cold starts to a few seconds (step 12).

```bash
docker buildx create --name builder --driver docker-container --use
docker buildx build --platform linux/amd64,linux/arm64 \
  -f docker/Dockerfile.base -t $REGISTRY/python-base:latest --push .

gcloud artifacts docker images list $REGISTRY/python-base \
  --include-tags --filter='tags:latest' --format='value(version)' | head -1
```

Put that `sha256:…` in `MODULE.bazel` as the `digest` of `oci.pull(name = "python_with_deps")`.

## 5. The Telegram bot — one bot, two chats

The private chat and the draft group are **the same bot**. In your private
chat it answers every command; in the draft group only the draft ones.

1. Talk to [@BotFather](https://t.me/BotFather): `/newbot` → keep the **token**.
2. **Your chat id**: send your bot any message, then
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq '.result[].message.chat.id'
   ```
3. **Draft group** (skip if you do not draft): create a group, add the bot,
   make the bot an **admin** of the group so it sees every message, post
   anything in it, and run the same `getUpdates` — the group id is the
   negative one, starting `-100`.

Do this before step 8: once the webhook is registered, `getUpdates` stops
answering. Adding the group later means `curl .../deleteWebhook`, reading the
id, and running step 8's `setup_commands.py` again.

## 6. Secrets

Two JSON secrets. **Regional** replication, never the automatic
(multi-region) default: every replica counts as a billed version, and the free
tier is 6 active versions per *billing account*, not per project.

```bash
new_secret() {  # name, then the value on stdin
  gcloud secrets create "$1" --data-file=- \
    --replication-policy=user-managed --locations=$REGION
}

jq -n --arg email "<BIWENGER_EMAIL>" --arg password "<BIWENGER_PASSWORD>" \
  --arg jp "<JORNADA_PERFECTA_TOKEN — requested from the project owner>" \
  '{email: $email, password: $password, jp_auth_token: $jp}' \
  | new_secret biwenger-credentials-regional

jq -n --arg token "<BOT_TOKEN>" --arg chat "<YOUR_CHAT_ID>" \
  --arg draft "<DRAFT_GROUP_ID or empty>" --arg hook "$(openssl rand -hex 32)" \
  '{bot_token: $token, chat_id: $chat, draft_chat_id: $draft, webhook_secret: $hook}' \
  | new_secret telegram-bot-config-regional
```

Changing one later: add the new version, redeploy, then **destroy** the old
one — a disabled version still bills.

```bash
gcloud secrets versions add <secret> --data-file=-
gcloud secrets versions destroy <old_version> --secret=<secret>
```

## 7. Permissions

Every service runs as the project's default compute service account. Ours
holds `roles/editor` plus `roles/secretmanager.secretAccessor`, and that is
the combination known to work.

```bash
SA=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com
gcloud iam service-accounts describe $SA   # must exist — see step 2
for role in roles/editor roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$role
done
```

## 8. Deploy — passive first

The API goes out with **bidding, speculative bids and the lineup switched
off**, so nothing spends money or touches your team until step 10 checks out.

```bash
# API — private: only the bot and the scheduler may call it.
bazel run //packages/biwenger_tools/api:push_image_to_gcp --platforms=//platforms:linux_amd64
gcloud run deploy biwenger-api --image $REGISTRY/api --region $REGION \
  --no-allow-unauthenticated --memory=512Mi --cpu=1 --concurrency=10 --timeout=300 \
  --update-secrets="BIWENGER_CREDENTIALS_JSON=biwenger-credentials-regional:latest,TELEGRAM_BOT_CONFIG_JSON=telegram-bot-config-regional:latest" \
  --set-env-vars="TEMPORADA_ACTUAL=26-27,GCP_PROJECT_ID=$PROJECT_ID,PERIODICO_BUCKET=$BUCKET,DRAFT_APPLY_TO_BIWENGER=false,AUTO_BID_PAUSED_UNTIL=2099-01-01,CHOLLO_MAX_BIDS=0,DAILY_LINEUP_ENABLED=false"
API_URL=$(gcloud run services describe biwenger-api --region $REGION --format='value(status.url)')
gcloud run services add-iam-policy-binding biwenger-api --region $REGION \
  --member=serviceAccount:$SA --role=roles/run.invoker

# Bot — public: Telegram calls it, and the webhook secret keeps everyone else out.
bazel run //packages/biwenger_tools/bot:push_image_to_gcp --platforms=//platforms:linux_amd64
gcloud run deploy biwenger-bot --image $REGISTRY/bot --region $REGION \
  --allow-unauthenticated --memory=256Mi --cpu=0.5 --concurrency=1 --timeout=300 \
  --update-secrets="TELEGRAM_BOT_CONFIG_JSON=telegram-bot-config-regional:latest" \
  --set-env-vars="BIWENGER_API_URL=$API_URL"

# Register the webhook and the command menu with Telegram.
pip3 install requests python-dotenv python-json-logger
CFG=$(gcloud secrets versions access latest --secret=telegram-bot-config-regional)
BOT_URL=$(gcloud run services describe biwenger-bot --region $REGION --format='value(status.url)')
PYTHONPATH=. TELEGRAM_BOT_TOKEN=$(echo "$CFG" | jq -r .bot_token) \
  TELEGRAM_WEBHOOK_SECRET=$(echo "$CFG" | jq -r .webhook_secret) \
  BIWENGER_BOT_URL="$BOT_URL/telegram/webhook" \
  python3 packages/biwenger_tools/bot/setup_commands.py

# Scraper — a job, not a service: it runs weekly and exits.
bazel run //packages/biwenger_tools/scraper_job:push_image_to_gcp --platforms=//platforms:linux_amd64
gcloud run jobs create biwenger-scraper-data --image $REGISTRY/scraper_job --region $REGION \
  --memory=512Mi --cpu=1 --task-timeout=600s --max-retries=3 \
  --update-secrets="BIWENGER_CREDENTIALS_JSON=biwenger-credentials-regional:latest,TELEGRAM_BOT_CONFIG_JSON=telegram-bot-config-regional:latest" \
  --set-env-vars="TEMPORADA_ACTUAL=26-27"
```

## 9. The two clocks

Two of the three scheduler jobs free per billing account. No retries on
purpose: a retried digest sends every message twice.

```bash
# 09:00 Madrid digest: squad, market, lineup, bids, clause warnings, offers.
gcloud scheduler jobs create http biwenger-daily-digest-trigger --location=$SCHED_REGION \
  --schedule="0 9 * * *" --time-zone=Europe/Madrid --http-method=POST \
  --uri="$API_URL/digests/daily" --attempt-deadline=180s \
  --oidc-service-account-email=$SA --oidc-token-audience="$API_URL"

# Sunday 22:00 scraper run.
gcloud scheduler jobs create http biwenger-scraper-data-scheduler-trigger --location=$SCHED_REGION \
  --schedule="0 22 * * 0" --time-zone=Europe/Madrid --http-method=POST \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/biwenger-scraper-data:run" \
  --attempt-deadline=180s --oauth-service-account-email=$SA
```

## 10. Check it works, then switch it on

In your private chat: `/menu`, then `/version` and `💰 Saldos`. The
`/saldos` image should say *"Tu saldo reconstruido cuadra con Biwenger"* — if
it does, the league id, the credentials, the starting balance and the whole
API path are right. Logs:
`gcloud run services logs read biwenger-api --region $REGION --limit 50`.

Then let it bid and set the lineup:

```bash
gcloud run services update biwenger-api --region $REGION \
  --remove-env-vars=AUTO_BID_PAUSED_UNTIL,CHOLLO_MAX_BIDS,DAILY_LINEUP_ENABLED
```

## 11. The draft (once a year)

The bot arbitrates it in the draft group; `DRAFT_APPLY_TO_BIWENGER` decides
whether picks are also written to Biwenger.

1. The Biwenger account in the secret is a **league admin** (step 0).
2. `draft_chat_id` is set in `telegram-bot-config-regional` (step 5).
3. Turn the writes on:
   ```bash
   gcloud run services update biwenger-api --region $REGION \
     --update-env-vars DRAFT_APPLY_TO_BIWENGER=true
   ```
4. Open, run and close it with the scripts and the order in
   [OPERATIONS.md → Draft anual](OPERATIONS.md#-draft-anual).

## 12. Staying free, and cold starts

| Piece | Free limit | What keeps you inside it |
|---|---|---|
| Cloud Run | 2M requests, 360k vCPU-s, 180k GiB-s / month | `min-instances` at its default **0**: nothing bills while idle |
| Secret Manager | 6 active versions per billing account | Regional secrets (step 6); destroy replaced versions |
| Cloud Scheduler | 3 jobs per billing account | Two used |
| Artifact Registry | 0.5 GB | The shared base image; delete old image digests now and then |
| Cloud Storage | 5 GB, **US regions only** | The bucket in `us-central1` (step 2) |
| Firestore | 1 GiB, 50k reads / 20k writes a day | One league is far below it |
| Cloud Logging | 50 GiB ingestion / month | Keep 7 days, below |

```bash
gcloud logging buckets update _Default --location=global --retention-days=7

# An email if anything ever costs money.
gcloud billing budgets create --billing-account=<BILLING_ACCOUNT_ID> \
  --display-name="biwenger 1 EUR" --budget-amount=1EUR \
  --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

**Cold starts without paying for them.** With `min-instances=0` the first
request after an idle spell starts a container. The pre-built base image
(step 4) keeps that to roughly 5–10 s, the bot answers "procesando…" at once
and does the work in the background, and the 09:00 digest has five minutes of
budget. `--min-instances=1` would remove the wait, but it keeps an instance
running all month and leaves the free tier — not worth it for a league.

## 13. Optional: the web

The public dashboard (comunicados, salseo, market, competitions). One more
secret and, for the competitions tabs, a Google Sheet read through a service
account key — skip it if the bot is all you want.

```bash
jq -n --arg key "$(openssl rand -hex 32)" --arg pw "<ADMIN_PASSWORD>" \
  '{secret_key: $key, admin_password: $pw}' | new_secret flask-web-config-regional

bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64
gcloud run deploy biwenger-summary --image $REGISTRY/web --region $REGION \
  --allow-unauthenticated --timeout=300 \
  --update-secrets="FLASK_WEB_CONFIG_JSON=flask-web-config-regional:latest" \
  --set-env-vars="TEMPORADA_ACTUAL=26-27,GCP_PROJECT_ID=$PROJECT_ID,CLOUD_RUN_REGION=$REGION,CLOUD_RUN_JOB_NAME=biwenger-scraper-data,PERIODICO_BUCKET=$BUCKET,SPECIAL_TOURNAMENTS_BUCKET=$BUCKET"
```

The competitions tabs (Sheets) are wired in [`web/README.md`](web/README.md).

## 14. Optional: deploy from GitHub on every merge

What this repo does: `.github/workflows/deploy.yml` deploys on each push to
`master`, keyless through Workload Identity Federation. In a fork:

- change `PROJECT_ID`, `REGISTRY` and the `workload_identity_provider` /
  `service_account` lines;
- remove the `chucknorris-bot` and `be-water` jobs — they deploy other
  projects;
- create a WIF pool and provider **restricted to your fork's repository**, and
  a deploy service account with, at least, `roles/artifactregistry.writer`,
  `roles/run.developer`, `roles/iam.serviceAccountUser` on the compute service
  account, and `roles/secretmanager.secretAccessor` on
  `telegram-bot-config-regional` (the bot deploy step reads it).
