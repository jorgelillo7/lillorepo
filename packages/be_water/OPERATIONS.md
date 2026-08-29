# 🛠️ Operations — be_water

Commands for running, testing, syncing, curating and deploying **Be Water**,
the public bottled-waters catalog. It runs against its **own GCP project**
(`be-water-app`) — see [`INFRA.md`](../../INFRA.md) for the inventory and
[`.github/workflows/README.md`](../../.github/workflows/README.md) for the
cross-project deploy grants.

Repo-wide procedures (prerequisites, Python dependency workflow, secrets,
linter, GCP cost/cleanup) live in [`docs/operations.md`](../../docs/operations.md).
For the Firestore data model, see [`docs/firestore.md`](../../docs/firestore.md).

**What each capability does** — the similarity engine, per-field provenance,
AESAN coverage, the idempotent catalog sync, community badges, the curation
rules — lives in the behaviour specs at
[`openspec/specs/be_water/`](../../openspec/specs/be_water/). This file is the
operational how-to; the specs are the single source of *what must be true*.

---

## Be Water Web

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

  * **🧹 Curation & audit tooling (local, ADC — read-only until you confirm a write):**

    Interactive maintenance CLIs over the live catalog. Each shares the same
    engine the future `/admin` page will reuse (`photo_audit`, `data_audit`,
    `provenance`).

    ```bash
      # Photos — audit every uploaded shot; --fix repairs (studio regenerate /
      # re-upload / delete). Records verdicts to a local photo_audit.json.
      bazel run //packages/be_water/scripts:audit_photos
      bazel run //packages/be_water/scripts:audit_photos -- --fix

      # Data — sign off eligible fichas as verified (label photo + a
      # label-confirmed value → freezes it); review duplicates / bad values.
      bazel run //packages/be_water/scripts:audit_data
      bazel run //packages/be_water/scripts:audit_data -- --duplicates
      bazel run //packages/be_water/scripts:audit_data -- --suspicious

      # Drift — where the in-repo dataset and the live catalog disagree.
      # Read-only: the fix is a PR against seed_data.py, not a Firestore write.
      bazel run //packages/be_water/scripts:audit_data -- --drift

      # Revert — undo a contribution that overwrote a composition, from the
      # snapshot the add flow stores in water_revisions.
      bazel run //packages/be_water/scripts:revert_water               # list all
      bazel run //packages/be_water/scripts:revert_water -- penaclara  # one water

      # Provenance — one-shot backfill of Water.sources; dry-run by default.
      bazel run //packages/be_water/scripts:backfill_sources           # preview
      bazel run //packages/be_water/scripts:backfill_sources -- --apply

      # Analysis date — re-read the stored label photos to fill
      # Water.analysis_date. Only reaches fichas that have a label photo.
      bazel run //packages/be_water/scripts:backfill_analysis_date            # preview
      bazel run //packages/be_water/scripts:backfill_analysis_date -- --write
    ```

    > Provenance model: each mineral's source is `label` (in `verified_fields`,
    > shown as ✓), `manufacturer`, `manual` or (for identity) `aesan`. A ficha
    > is `verified` either by auto-promotion (every value label-backed) or by an
    > admin sign-off via `audit_data`; verified fichas are frozen against
    > overwrite.
    >
    > `analysis_date` dates the whole composition block ("CNTA, Febrero 2025"
    > → `2025-02`). Labels need not print it, so null is normal and never
    > outranks a dated analysis. Saving an older (or undated) label over a
    > dated one warns and asks the contributor to confirm; any save that moves
    > an existing composition snapshots the previous doc to `water_revisions`
    > first, which is what `revert_water` reads.

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

  * **🔐 Activar Google Sign-In + /admin (runbook — one manual step):**

    All the code shipped and is dormant until `google_client_id` exists. The
    button hides and `/admin` 404s meanwhile, so nothing breaks. To activate:

    1. Console → project **be-water-app** → *APIs & Services → OAuth consent
       screen*: External · app name "Be Water" · support email
       jorge.lillo9@gmail.com · no extra scopes · Publish (or keep Testing
       and add your email as test user).
    2. *Credentials → Create credentials → OAuth client ID → Web application*:
       - Authorized JavaScript origins:
         `https://be-water-lzqhg7kcoa-no.a.run.app` and `http://localhost:8080`
       - Authorized redirect URIs:
         `https://be-water-lzqhg7kcoa-no.a.run.app/auth/google`
       Copy the client id (`xxxx.apps.googleusercontent.com`).
    3. Add it to the consolidated secret (stays at 1 active version —
       destroy the old one after verifying):

       ```bash
       gcloud secrets versions access latest --secret=flask-web-config-regional \
           --project=be-water-app | \
           python3 -c "import json,sys; d=json.load(sys.stdin); d['google_client_id']='PASTE_CLIENT_ID'; print(json.dumps(d))" | \
           gcloud secrets versions add flask-web-config-regional \
           --project=be-water-app --data-file=-
       # after verifying login works:
       gcloud secrets versions destroy 1 --secret=flask-web-config-regional --project=be-water-app
       ```
    4. Redeploy be-water (any merge, or Actions → Deploy → Run workflow) so
       the new secret version binds.
    5. Verify: the home shows the G button · sign in with
       jorge.lillo9@gmail.com · 🛡️ Admin appears in the nav (admin emails
       live in `BEWATER_ADMIN_EMAILS` in deploy.yml).

## 🧹 Reclaiming abandoned upload photos

Every `/anadir/foto` attempt writes **two** objects to
`gs://be-water-photos/uploads/` — the label shot and the display photo —
*before* the label is read. A read that fails leaves both behind, so three
failed attempts on the same bottle leave six.

`routes/add.py` claimed a lifecycle rule reclaimed them. **It does not exist**:
the bucket reports `lifecycle: null`, and `uploads/` has only grown — 6 objects
and 491 KB when this was first written, 14 objects and ~1 MB a week later.
Nothing has ever deleted them, and the README's architecture diagram claimed a
3-day TTL that was never created either.

The bucket rides Cloud Storage's 5 GB always-free tier and sat at 3.5 MB, so
this has never cost anything — but the invariant the code asserts is false and
the pile only grows.

Create the rule (deletes anything under `uploads/` after 7 days; a form nobody
finished in a week is abandoned):

```bash
cat > /tmp/lifecycle.json <<'JSON'
{"rule": [{
  "action": {"type": "Delete"},
  "condition": {"age": 7, "matchesPrefix": ["uploads/"]}
}]}
JSON
gcloud storage buckets update gs://be-water-photos \
  --lifecycle-file=/tmp/lifecycle.json --project=be-water-app
```

Verify, and confirm it is scoped to `uploads/` before trusting it — the same
bucket holds `originals/`, which is the permanent verification proof and must
never be swept:

```bash
gcloud storage buckets describe gs://be-water-photos \
  --format="json(lifecycle)" --project=be-water-app
```

## 🤖 Changing the Gemini model

Models are retired **per API key**, and the local `.env` key is not the one
production uses. Testing with the wrong one is how `gemini-2.5-flash` briefly
got pinned while production could not call it at all — it answered locally and
404'd in Cloud Run.

Always measure with the production key:

```bash
KEY=$(gcloud secrets versions access latest --secret=flask-web-config-regional \
  --project=be-water-app | python3 -c "import json,sys; print(json.load(sys.stdin)['gemini_api_key'])")
```

When a model is retired the 404 body names its replacement, which is where
`gemini-3.6-flash` came from:

```
This model models/gemini-2.5-flash is no longer available to new users.
Please update your code to use models/gemini-3.6-flash
```

Swap it without a deploy, then bump the default in `core/sdk/gemini.py`:

```bash
gcloud run services update be-water --update-env-vars GEMINI_MODEL=<model> \
  --region europe-southwest1 --project be-water-app
```

**Do not go back to a `-latest` alias.** It read-timed out at 60 s for a whole
morning, and there is no way to know which model is behind it — for a reader
that fills a catalog people trust for being verified, the extraction changing
without notice is worse than a loud 404.
