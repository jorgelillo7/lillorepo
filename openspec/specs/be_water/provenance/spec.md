# Capability: provenance

Per-field sourcing for a water's mineral values, so the UI can name where each
number came from (`label` / `manufacturer` / `aesan` / `manual`) instead of a
blanket "sin verificar".

- **Source:** `packages/be_water/web/provenance.py`, `domain.py`,
  `submission.py`, `routes/add.py`
- **Verified by:** `packages/be_water/web/tests/test_provenance.py`,
  `test_submission.py`, `test_routes.py`

---

### Requirement: Derive sources from seed + registry

`derive_sources` SHALL assign, per mineral field: `label` fields (those in
`verified_fields`) are **not stored** (their source is implied); a value equal
to the seed dataset is `manufacturer`; a value changed from the seed, or absent
from it, is `manual`; an already-recorded source is preserved. Province and
community SHALL be sourced `aesan` only when the AESAN registry match agrees
with the stored value.

#### Scenario: mineral field sourcing
- **WHEN** a field is label-verified / matches seed / differs from seed /
  is new / already has a source
- **THEN** it is omitted / `manufacturer` / `manual` / `manual` / kept as-is
- *Verifies:* `test_seed_matching_values_are_manufacturer_label_fields_excluded`,
  `test_value_changed_from_seed_is_manual`, `test_value_absent_from_seed_is_manual`,
  `test_existing_source_is_kept`

#### Scenario: identity from AESAN only on agreement
- **WHEN** the AESAN registry match agrees on province **THEN** province and
  community are sourced `aesan`
- **WHEN** it disagrees **THEN** no `aesan` source is set
- *Verifies:* `test_province_and_community_from_aesan_registry`,
  `test_no_aesan_source_when_registry_disagrees`

### Requirement: Sources recomputed on save

`sources_on_save` SHALL mark new minerals `manual`, drop fields that became
label-backed or that no longer exist as minerals, and preserve prior mineral
sources and identity (province/community) sources.

#### Scenario: save recomputation
- **WHEN** saving with new minerals, label promotions, and vanished fields
- **THEN** new → `manual`, label/vanished → dropped, prior + identity → kept
- *Verifies:* `test_sources_on_save_marks_new_minerals_manual_labels_implied`,
  `test_sources_on_save_preserves_prior_and_identity_sources`,
  `test_sources_on_save_drops_vanished_and_label_fields`

### Requirement: The label's analysis date dates the whole composition

`Water.analysis_date` SHALL hold the date of the lab analysis the label
declares, normalised to `"YYYY-MM"` or `"YYYY"` when the label prints only a
year. `normalize_analysis_date` SHALL accept what the OCR and the form
produce (`2025-02`, `2025-2`, `2023`, `Febrero 2025`, `febrero de 2025`) and
SHALL return `None` for anything it cannot read, rather than guess — a
malformed date would sort wrongly against a real one. It is not a mineral: it
dates the block, so it stays out of `MINERAL_FIELDS` and the similarity vector.

Labels are not required to carry it (RD 1798/2010 art. 9.2.b mandates the
values, not their date), so `None` is a normal state and SHALL never outrank a
dated analysis. A submission that declares no date SHALL inherit the one
already on file.

#### Scenario: normalisation and inheritance
- **WHEN** a label date arrives as ISO, a bare year, or a Spanish month name
- **THEN** it normalises to `YYYY-MM` / `YYYY`
- **WHEN** the text is a lot code or an impossible month
- **THEN** the result is `None` (or the year alone), never a guess
- **WHEN** a submission carries no date and the stored ficha has one
- **THEN** the stored date survives; a dated submission keeps its own
- *Verifies:* `test_normalize_analysis_date_accepts_what_labels_and_ocr_produce`,
  `test_normalize_analysis_date_rejects_rather_than_guesses`,
  `test_a_dateless_submission_inherits_the_date_on_file`,
  `test_a_dated_submission_keeps_its_own_date`

### Requirement: An older label never overwrites a newer one silently

When a submission's analysis predates the stored one — or carries no date
while the stored one does — the add flow SHALL re-render the form with a
warning naming both dates and SHALL save nothing until the contributor
confirms. It SHALL NOT refuse the submission: the contributor may be holding
the better bottle. A newer analysis SHALL save straight through.

Any save that changes an existing ficha's minerals SHALL first snapshot the
whole previous document to `water_revisions`, tagged `older_analysis` or
`composition_changed`, so a bad edit is reversible from
`scripts/revert_water.py`. The trail is not limited to the older case: an
undated or mistyped overwrite produces the same regret and the same need.

#### Scenario: warn, confirm, snapshot
- **WHEN** the submitted analysis is older than the stored one and unconfirmed
- **THEN** the form comes back showing both dates, and nothing is written
- **WHEN** the contributor confirms
- **THEN** the water saves and the previous doc is snapshotted as `older_analysis`
- **WHEN** the analysis is newer but the composition moves
- **THEN** it saves straight through, still snapshotted as `composition_changed`
- **WHEN** the composition does not move
- **THEN** no snapshot is taken
- *Verifies:* `test_older_label_needs_confirming_and_saves_nothing_until_then`,
  `test_confirming_an_older_label_saves_and_snapshots_the_previous_state`,
  `test_a_newer_label_saves_straight_through_but_still_snapshots`,
  `test_no_snapshot_when_the_composition_did_not_move`,
  `test_older_or_undated_analysis_warns_newer_one_does_not`,
  `test_no_warning_when_there_is_nothing_to_protect`
