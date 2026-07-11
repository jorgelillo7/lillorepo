# Pending work

Long-running follow-ups that don't yet warrant a plan or PR.

**Rules of the file:**
- Never deleted; lives at the repo root.
- Lines are pruned as items ship or stop being relevant — keep it short.
- Group items by package; use `infra` for cross-cutting GCP/CI/policy tasks.
- "What has shipped" lives in `packages/biwenger_tools/release-notes.md` — do not duplicate here.

---

## infra

- **Drive folder cleanup** (USER-OWNED, week of 2026-05-26) — when the league ends:
  delete the Drive folder contents (the old CSVs the scraper used to upload), then
  drop the `biwenger-tools-sa-regional` secret or repoint it to a Sheets-only SA
  (Sheets API still authenticates through that mount for `ligas_especiales` /
  `trofeos`).
- **Resume the weekly scraper scheduler on 2026-07-14** (Biwenger league restart) —
  paused on 2026-05-26 with
  `gcloud scheduler jobs pause biwenger-scraper-data-scheduler-trigger`
  (Cloud Scheduler, europe-west1, project `biwenger-tools`). Resume with:
  `gcloud scheduler jobs resume biwenger-scraper-data-scheduler-trigger --location=europe-west1 --project=biwenger-tools`
  so the Sunday 22:00 Madrid scrape fires again. Note: Cloud Scheduler is not
  offered in europe-southwest1, so europe-west1 is deliberate — do not try to
  "fix" the region.

## my_photos

- **Photo-recognition project** — tracked in `packages/my_photos/README.md`, not here.
