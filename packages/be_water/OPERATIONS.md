# 🛠️ Operations — be_water

Commands for running, testing, syncing, curating and deploying **Be Water**,
the public bottled-waters catalog. It runs against its **own GCP project**
(`be-water-app`) — see [`INFRA.md`](../../INFRA.md) for the inventory and
[`.github/workflows/README.md`](../../.github/workflows/README.md) for the
cross-project deploy grants.

Repo-wide procedures (prerequisites, Python dependency workflow, secrets,
linter, GCP cost/cleanup) live in [`docs/operations.md`](../../docs/operations.md).
For the Firestore data model, see [`docs/firestore.md`](../../docs/firestore.md).

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

      # Provenance — one-shot backfill of Water.sources; dry-run by default.
      bazel run //packages/be_water/scripts:backfill_sources           # preview
      bazel run //packages/be_water/scripts:backfill_sources -- --apply
    ```

    > Provenance model: each mineral's source is `label` (in `verified_fields`,
    > shown as ✓), `manufacturer`, `manual` or (for identity) `aesan`. A ficha
    > is `verified` either by auto-promotion (every value label-backed) or by an
    > admin sign-off via `audit_data`; verified fichas are frozen against
    > overwrite.

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
