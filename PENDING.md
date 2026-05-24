# Pending work

Long-running follow-ups that don't yet warrant a plan or PR.

**Rules of the file:**
- Never deleted; lives at the repo root.
- Lines are pruned as items ship or stop being relevant — keep it short.
- "What has shipped" lives in `packages/biwenger_tools/release-notes.md` — do not duplicate here.

---

- **Drive folder cleanup** (USER-OWNED, week of 2026-05-26) — when the league ends:
  delete the Drive folder contents (the old CSVs the scraper used to upload), then
  drop the `biwenger-tools-sa-regional` secret or repoint it to a Sheets-only SA
  (Sheets API still authenticates through that mount for `ligas_especiales` /
  `trofeos`).
- **Move Drive/Sheets IDs out of BUILD.bazel** — Sheets IDs (`LIGAS_ESPECIALES_*`,
  `TROFEOS_*`) are still hardcoded in `packages/biwenger_tools/web/BUILD.bazel`.
  Env-var them when convenient. Low priority.
- **Photo-recognition project** — tracked in `packages/my_photos/README.md`, not here.
