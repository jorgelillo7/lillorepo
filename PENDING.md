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
- **Drop the in-code CSV layer** — once the Drive CSVs are gone (item above),
  remove the legacy CSV serialization paths now that Firestore is the only source
  of truth: `from_csv_rows` / `to_csv_row` / `CSV_FIELDS` across `core/domain/models.py`
  (`Palmares`, `Participation`, `Clausulazo`, `JusticeEntry`, `LeagueMessage`), the
  one-shot `scripts/backfill_firestore.py` recovery tool, and the related tests in
  `core/tests/test_domain_models.py`. Update `docs/firestore.md` to drop the
  "Backfill (one-shot)" row.

## my_photos

- **Photo-recognition project** — tracked in `packages/my_photos/README.md`, not here.
