# Capability: catalog-sync

Idempotent sync of the curated seed dataset into Firestore: create missing
waters, refresh unverified ones without clobbering user contributions, never
overwrite bottle-verified data, and notify newcomers on Telegram.

- **Source:** `packages/be_water/web/catalog_sync.py`
- **Verified by:** `packages/be_water/web/tests/test_catalog_sync.py`

---

### Requirement: Create missing, refresh unverified, preserve user fields

`sync_catalog` SHALL create waters absent from Firestore, and for unverified
existing docs refresh the dataset-owned fields (minerals) while preserving
user-owned fields (`photo_url`, `added_by`, …).

#### Scenario: create and non-destructive update
- **WHEN** the dataset has waters missing from Firestore, and an unverified doc
  with a stale mineral value plus a user photo
- **THEN** missing waters are created; the stale value is refreshed but the
  photo and `added_by` survive
- *Verifies:* `test_creates_missing_waters`,
  `test_updates_unverified_but_preserves_user_fields`

### Requirement: Verified waters are data-frozen

A `verified` doc SHALL never have its minerals touched by the sync. Only
enrichment is allowed: an empty `photo_url` may be filled and `mentions` may be
added from the dataset. A dataset entry flagged `verified` SHALL promote an
unverified doc, carrying the flag.

#### Scenario: freeze data, allow enrichment, promote
- **WHEN** a verified doc's dataset value differs
- **THEN** minerals stay exactly as bottle-checked
- **WHEN** the dataset supplies a photo or mentions for a verified doc
- **THEN** only those are added, minerals untouched
- **WHEN** a dataset entry is `verified` over an unverified doc
- **THEN** the doc is upgraded and the flag carried
- *Verifies:* `test_never_touches_verified_waters`,
  `test_verified_doc_gets_photo_enrichment_only`,
  `test_verified_doc_gets_mentions_enrichment`,
  `test_dataset_verified_flag_promotes_existing_entry`

### Requirement: Label-backed minerals beat the dataset, field by field

A mineral in `verified_fields` SHALL keep its stored value when the dataset
updates an otherwise-unverified doc — label beats dataset per field.

#### Scenario: label field survives merge
- **WHEN** an unverified doc has a label-backed `tds` differing from the dataset
- **THEN** the label value survives and stays in `verified_fields`
- *Verifies:* `test_label_backed_minerals_survive_dataset_merge`

### Requirement: Idempotent, with user-only reporting

A re-run over already-synced state SHALL write nothing (`unchanged` count).
Docs the dataset doesn't know (new water or typo'd name) SHALL be surfaced in
the summary `user_only` and never written.

#### Scenario: no-op re-run and user-only surfacing
- **WHEN** the sync runs twice **THEN** the second writes nothing
- **WHEN** an unknown doc exists **THEN** it is reported, not touched
- *Verifies:* `test_rerun_is_a_noop`, `test_user_only_waters_are_reported_not_touched`

### Requirement: AESAN coverage line + Telegram notification

The summary SHALL include AESAN coverage (accent-insensitive name matching).
When Telegram credentials are present, the sync SHALL send a summary (new
count, AESAN line, user-only ping — even when the only change is an unknown
doc); with no credentials it SHALL send nothing.

#### Scenario: coverage and conditional notify
- **WHEN** matching against AESAN **THEN** covered folds accents (Solán = Solan)
- **WHEN** credentials are set **THEN** a summary with "Nuevas (N)"/"AESAN"/
  user-only line is sent; **WHEN** absent **THEN** no send
- *Verifies:* `test_aesan_coverage_is_accent_insensitive`,
  `test_notify_includes_aesan_line`, `test_user_only_alone_triggers_notification`,
  `test_notify_skipped_without_creds`, `test_notify_sent_with_creds`
