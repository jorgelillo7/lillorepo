# group_polls — operations

Everything is run by hand from the repo root, with your own Google credentials (ADC).
`GROUP_POLLS_PROJECT` is the project id chosen in step 1 (e.g. `que-votais-app`).

## 1. Create the project (once)

1. **Firebase console** → <https://console.firebase.google.com> → *Add project*:
   - name `que-votais` (Firebase suggests an id; write it down: it is `GROUP_POLLS_PROJECT`);
   - Google Analytics **off**;
   - plan **Spark** (free, no billing). Spark has no Cloud Functions; nothing here needs them.
2. **Firestore** → *Create database* → **`europe-southwest1` (Madrid)**, production mode.
3. **Authentication** → *Get started* → *Sign-in method* → **Anonymous** → enable.
4. **Project settings** → *Your apps* → **Android** → package `com.jorgelillo.grouppolls`.
   Skip the `google-services.json` download step: the app reads three values instead. Create
   `lillo-android-apps/apps/group-polls/firebase.properties` (public identifiers, safe to commit):
   ```properties
   projectId=<project id>
   appId=<"App ID", 1:…:android:…>
   apiKey=<"Web API key" from Project settings → General>
   ```
5. **App Check** → *Apps* → the Android app → **Play Integrity** → register (needs the app's
   SHA-256 from Play Console → *App integrity*). Then *APIs* → **Cloud Firestore** → **Enforce**.
   For debug builds: run the app once, copy the debug token from logcat
   (`DebugAppCheckProvider`) and add it under *Apps* → *Manage debug tokens*.
6. **Terraform** (`infra/group_polls.tf`): set `local.group_polls` to the project id, then
   adopt what the console created and create the rest:
   ```bash
   cd infra
   terraform import 'google_firestore_database.group_polls["<id>"]' 'projects/<id>/databases/(default)'
   terraform plan    # APIs, feed index, votes.voterId field, rules ruleset + release
   terraform apply
   ```
   Also give CI's read-only plan identity viewer access to the new project (`ci_plan.tf`, same as
   the other two), or `terraform plan` in CI fails.
7. Firebase projects on Spark have no billing account, so no budget alert applies. If the project
   is ever moved to Blaze, add it to `infra/budgets.tf` with a €1 alert like the others.

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

## 4. Delete a user's data on request

Users do it in the app (*Settings → Delete my data*): name blanked on their polls and votes,
votes still counted, the phone forgets everything. If someone asks by email instead, they need to
send their poll links (there is no account to look them up by); blank `creatorName` on those
polls in the Firebase console, or remove them with `moderate.py remove`.

## 5. Costs

Spark (free) limits per day: 50k reads, 20k writes, 20k deletes, 1 GiB stored. One vote is two
writes (vote + counter); opening the feed reads up to 200 polls. When usage gets near the limits
Firestore starts refusing requests (no bill on Spark): the app shows "Something went wrong".
