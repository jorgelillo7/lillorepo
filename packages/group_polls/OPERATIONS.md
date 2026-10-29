# group_polls — operations

Everything is run by hand from the repo root, with your own Google credentials (ADC).
`GROUP_POLLS_PROJECT` is the project id chosen in step 1 (e.g. `que-votais-app`).

## 1. Create the project (once)

Reviewed end to end against `infra/` before the first run. Ask the owner before every `apply`,
and before anything else that creates or changes a cloud resource. Order matters: steps 1–4 by
hand, 5 needs the app in Play Console, 6 is one PR, and 7 comes last.

**Why Spark, unlike `biwenger-tools` and `be-water-app`.** Spark is Firebase's free plan: the
project has no billing account at all, so it cannot be charged. The other two run Cloud Run,
Artifact Registry and Cloud Scheduler, which need billing (Blaze or plain GCP with a billing
account), and they are guarded by €1 budget alerts. This app has no server: Firestore, anonymous
Auth and App Check all fit Spark's free quotas. Past a quota, Firestore refuses requests instead
of billing (§5).

1. **Firebase console** → <https://console.firebase.google.com> → *Add project*:
   - name `que-votais` (Firebase suggests an id; write it down: it is `GROUP_POLLS_PROJECT`);
   - Google Analytics **off**;
   - plan **Spark** (free, no billing). Spark has no Cloud Functions; nothing here needs them.
2. **Firestore** → *Create database* → **`europe-southwest1` (Madrid)**, production mode.
   The region must be exactly this: `infra/group_polls.tf` uses `local.region`, and any other
   location makes Terraform want to replace the database (see 6).
3. **Authentication** → *Get started* → *Sign-in method* → **Anonymous** → enable.
4. **Project settings** → *Your apps* → **Android** → package `com.jorgelillo.grouppolls`.
   Skip the `google-services.json` download step: the app reads three values instead. Create
   `lillo-android-apps/apps/group-polls/firebase.properties` (public identifiers, safe to commit):
   ```properties
   projectId=<project id>
   appId=<"App ID", 1:…:android:…>
   apiKey=<"Web API key" from Project settings → General>
   ```
   Never commit a key file or a service-account JSON.
5. **App Check, registered but not enforced yet.**
   - Create the app in **Play Console** first (App · Social; the listing is ready in
     `app/src/main/play/listings`) and upload a first internal-testing build.
   - Copy the **app signing key** SHA-256 (Play Console → *App integrity* → *App signing key
     certificate*), not the upload key's. Play re-signs every build it distributes, so this is
     the certificate Play Integrity sees. A release APK installed by hand, signed with the upload
     key, never passes Play Integrity: test through the internal-testing track or with the
     debug token below.
   - Firebase → *App Check* → *Apps* → the Android app → **Play Integrity** → register with that
     SHA-256.
   - Debug builds: run the app once, copy the token from logcat (`DebugAppCheckProvider`) and add
     it under *Apps* → *Manage debug tokens*.
   - **Do not enforce yet**: enforcement comes in step 7, once real requests show as verified.
6. **Terraform**, in one PR:
   - in `infra/group_polls.tf` set `local.group_polls` to the project id. `infra/ci_plan.tf`
     picks it up by itself and gives CI's read-only plan identity viewer access to the new
     project; without that grant, the PR's own `terraform plan` check fails;
   - adopt the two things the console created. The database, and **the rules release**:
     production mode publishes default rules as `cloud.firestore`, and creating that release
     again would fail with "already exists":
     ```bash
     cd infra
     terraform import 'google_firestore_database.group_polls["<id>"]' 'projects/<id>/databases/(default)'
     terraform import 'google_firebaserules_release.group_polls["<id>"]' 'projects/<id>/releases/cloud.firestore'
     terraform plan
     ```
   - **Read the plan before applying.** Expected: the APIs, the feed index, the `votes.voterId`
     field and a new ruleset are created (`+`); the database changes in place (`~`), because the
     console creates it without delete protection and the `.tf` turns it on; the release changes
     in place to point at the new ruleset. **A replace (`-/+`) on the database means stop**: the
     region or the type differs, and `prevent_destroy` will refuse it anyway.
   - If a Firebase API answers "requires a quota project" (user credentials do that with
     `firebaserules` and `identitytoolkit`), run `gcloud auth application-default
     set-quota-project <id>` and plan again. A quota project needs no billing. If CI later hits
     the same thing, give the `group_polls` resources a provider alias with
     `user_project_override = true` and `billing_project = <id>`.
   - `terraform apply`, after the owner's yes.
7. **Enforce App Check**, after an internal-testing build has run on a real phone and App
   Check → *Metrics* shows Firestore requests as **verified**: *APIs* → **Cloud Firestore** →
   **Enforce**. Enforcing earlier makes the first test fail with no clear cause.
8. Firebase projects on Spark have no billing account, so no budget alert applies. If the project
   is ever moved to Blaze, add it to `infra/budgets.tf` with a €1 alert like the others.

**Afterwards** (other repos): put the same app-signing SHA-256 in
`jorgelillo7.github.io/.well-known/assetlinks.json` and publish the `/q/` share page (the privacy
page is already live). Release the first version by hand (draft → send for review), and update
`PENDING.md` in both repos.

## 2. Security rules

The app writes to Firestore directly: **every change to `firestore.rules` is tested before it is
deployed.**

```bash
# Emulator (official gcloud component, once: gcloud components install cloud-firestore-emulator).
# Needs Java 21+: the JBR from Android Studio works.
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
gcloud emulators firestore start --host-port=127.0.0.1:8085 &

bazel test //packages/group_polls:rules_tests \
  --test_env=FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 --test_output=errors
```

Without the emulator (CI) the 22 cases are skipped, not failed. The tests load the rules into
the emulator themselves (`PUT /emulator/v1/projects/…:securityRules`), so there is no
`firebase.json` and no Firebase CLI.

**Deploy:** `terraform apply` in `infra/` (it reads `packages/group_polls/firestore.rules` into a
new ruleset and releases it). The Firebase console → Firestore → *Rules* shows the live version.

## 3. Moderation

Public polls hide themselves after 3 reports. Review them every few days:

```bash
export GROUP_POLLS_PROJECT=<id>
bazel run //packages/group_polls/scripts:moderate                  # review queue
bazel run //packages/group_polls/scripts:moderate -- show CODE
bazel run //packages/group_polls/scripts:moderate -- restore CODE  # wrongly hidden
bazel run //packages/group_polls/scripts:moderate -- remove CODE   # abusive: poll + votes + reports
bazel run //packages/group_polls/scripts:moderate -- stats         # last 7 days
```

Every write asks for confirmation. To stop a repeat offender, remove their polls; their
`creatorId` is shown in the queue.

## 3b. Seed the public feed

`seed/questions.json` holds 50 questions written for the app (es + en), in the Everybody Votes
style. Publish a few per week so the feed is never empty:

```bash
bazel run //packages/group_polls/scripts:seed                          # dry run: next 3
GROUP_POLLS_PROJECT=<id> bazel run //packages/group_polls/scripts:seed -- --publish 3
```

Each question becomes two public polls (es and en sections), open 7 days, signed
"¿Qué votáis?". What was published is kept in `seed/state`, so runs never repeat.

## 4. Delete a user's data on request

Users do it in the app (*Settings → Delete my data*): name blanked on their polls and votes,
votes still counted, the phone forgets everything. If someone asks by email instead, they need to
send their poll links (there is no account to look them up by); blank `creatorName` on those
polls in the Firebase console, or remove them with `moderate.py remove`.

## 5. Costs

Spark (free) limits per day: 50k reads, 20k writes, 20k deletes, 1 GiB stored. One vote is two
writes (vote + counter); opening the feed reads up to 200 polls. When usage gets near the limits
Firestore starts refusing requests (no bill on Spark): the app shows "Something went wrong".
