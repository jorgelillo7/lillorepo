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
water's minerals (keeper wins on conflict), label photo, sources **and analysis
series** into the keeper, then delete the dropped doc.

The series has to move first: `delete_water` takes a water's entries with it,
so a merge that folded only the composition destroyed the duplicate's
measurement history — the one thing it held that the keeper cannot
reconstruct.

#### Scenario: re-source and merge semantics
- **WHEN** a field's source is set to `manufacturer` then back to `label`
- **THEN** it leaves and re-enters `verified_fields` accordingly
- **WHEN** merging a duplicate into a keeper
- **THEN** non-conflicting minerals and the label photo fold in, the keeper's
  conflicting value wins, and the dropped doc is deleted
- **WHEN** the dropped water holds analyses the keeper does not
- **THEN** they are rewritten under the keeper before the delete; a date the
  keeper already has wins, like every other field in a merge
- *Verifies:* `test_set_source_moves_field_in_and_out_of_verified`,
  `test_merge_waters_folds_and_deletes_drop`,
  `test_merging_a_duplicate_rescues_its_analysis_series`

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

### Requirement: Geography is audited, and a foreign water is not judged by Spain's

`geo_reasons` SHALL flag a ficha whose origin cannot be right: no spring, no
province (no *region*, outside Spain), a province that is not in
`geo.ALL_PROVINCES`, a missing community, or a community that does not match
the one its province derives.

It SHALL be kept apart from `suspicious_reasons`, which judges minerals: the
two answer different questions and a ficha can fail one while passing the
other. Both of the catalog's broken fichas did exactly that, and both were
`verified = True`, because nothing here looked at geography at all.

A non-`ES` water SHALL NOT be checked against Spanish provinces or communities
— its region is not a province and has no community to derive, so the check
would make every correct foreign ficha permanently suspicious. It SHALL still
be required to say where it is from.

`find_geo_gaps` SHALL return `(water, reasons)` for the whole catalog, and it
SHALL NOT write: unlike a mineral, a wrong province cannot be resolved by
re-reading the label with a machine. It backs `/admin`'s worklist and
`audit_data.py --geo`.

#### Scenario: the two shapes of a broken origin, and what must not be flagged
- **WHEN** a ficha stores `province='portugal', community='portugal'`
  **THEN** it is flagged as not a Spanish province
- **WHEN** a ficha has no spring, province or community **THEN** it is flagged
- **WHEN** a community does not match its province **THEN** it is flagged
- **WHEN** a Portuguese water has a region and no community **THEN** it is clean
- **WHEN** a foreign water has no region at all **THEN** it is flagged
- **WHEN** a correct Spanish ficha is checked **THEN** no reasons
- *Verifies:* `test_a_province_that_is_not_one_is_flagged`,
  `test_a_missing_origin_is_flagged`,
  `test_a_community_that_does_not_match_its_province_is_flagged`,
  `test_a_foreign_water_is_not_judged_by_spanish_geography`,
  `test_a_foreign_water_still_needs_a_region`,
  `test_a_correct_spanish_water_is_clean`,
  `test_find_geo_gaps_returns_only_the_broken_fichas`,
  `test_admin_page_lists_the_origins_that_need_a_human`
