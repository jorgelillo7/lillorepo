# Capability: data-curation

Admin curation engine: verification sign-off, duplicate detection, suspicious-
value flagging, and repair operations (re-source a field, merge duplicates).

- **Source:** `packages/be_water/web/data_audit.py`
- **Verified by:** `packages/be_water/web/tests/test_data_audit.py`

---

### Requirement: Verification sign-off requires proof

A water SHALL be `verifiable` only with both a label photo and at least one
label field, and not already verified. `mark_verified` SHALL freeze and save on
proof, and SHALL refuse (raise) without it.

#### Scenario: eligibility and refusal
- **WHEN** a water has a label photo + a label field and is not yet verified
- **THEN** it is verifiable; marking it freezes and saves
- **WHEN** either the photo or the label field is missing
- **THEN** it is not verifiable and marking raises without saving
- *Verifies:* `test_verifiable_needs_label_photo_and_a_label_field`,
  `test_mark_verified_freezes_and_saves`, `test_mark_verified_refuses_without_proof`

### Requirement: Duplicate detection respects multi-spring brands

`find_duplicates` SHALL group same-name waters with compatible springs (one
side unknown counts as compatible), but SHALL leave genuinely different springs
of the same brand as distinct entries.

#### Scenario: group compatible, keep distinct springs
- **WHEN** two "Font Vella" share a spring (or one is unknown)
- **THEN** they group as duplicates
- **WHEN** two "Font Vella" have different real springs
- **THEN** they are not grouped
- *Verifies:* `test_find_duplicates_groups_same_name_compatible_spring`,
  `test_find_duplicates_leaves_multi_spring_brands_alone`

### Requirement: Suspicious-value flags

`suspicious_reasons` SHALL flag out-of-range pH and ion/residue incoherence
(e.g. high TDS with near-zero ions), and return no reasons for a coherent water.

#### Scenario: flags and clean pass
- **WHEN** pH is 12, or TDS 2000 with ~zero ions **THEN** a reason is flagged
- **WHEN** the water is coherent **THEN** there are no reasons
- *Verifies:* `test_suspicious_flags_ph_and_ion_incoherence`,
  `test_suspicious_clean_water_has_no_reasons`

### Requirement: Repairs — re-source and merge

`set_source` SHALL move a field in/out of `verified_fields` consistently with
its source (`label` ↔ in verified_fields). `merge_waters` SHALL fold the dropped
water's minerals (keeper wins on conflict), label photo and sources into the
keeper, then delete the dropped doc.

#### Scenario: re-source and merge semantics
- **WHEN** a field's source is set to `manufacturer` then back to `label`
- **THEN** it leaves and re-enters `verified_fields` accordingly
- **WHEN** merging a duplicate into a keeper
- **THEN** non-conflicting minerals and the label photo fold in, the keeper's
  conflicting value wins, and the dropped doc is deleted
- *Verifies:* `test_set_source_moves_field_in_and_out_of_verified`,
  `test_merge_waters_folds_and_deletes_drop`

### Requirement: Dataset drift is detectable

`dataset_drift` SHALL report, per ficha, every mineral where the in-repo
dataset and the live catalog disagree, tagging `[etiqueta]` when the live
value is label-backed. Waters the dataset never seeded, and fields the ficha
does not carry, SHALL be ignored.

Seven waters once drifted this way: a label photo corrected Firestore and
nobody backported the numbers, so the dataset kept seeding values no bottle
supports. `suspicious_reasons` could not catch it — the wrong values were
internally coherent — so the comparison is its own check, and read-only: the
fix belongs in `seed_data.py`, not in Firestore.

#### Scenario: drift reporting
- **WHEN** a seeded ficha's stored value differs from the dataset's
- **THEN** the difference is reported, tagged `[etiqueta]` when label-backed
- **WHEN** the dataset agrees, or the water was never seeded
- **THEN** nothing is reported
- *Verifies:* `test_dataset_drift_reports_where_the_repo_disagrees_with_the_catalog`,
  `test_dataset_drift_is_silent_when_the_dataset_agrees`,
  `test_dataset_drift_ignores_waters_the_dataset_never_seeded`
