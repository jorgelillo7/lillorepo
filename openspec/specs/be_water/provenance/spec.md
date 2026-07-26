# Capability: provenance

Per-field sourcing for a water's mineral values, so the UI can name where each
number came from (`label` / `manufacturer` / `aesan` / `manual`) instead of a
blanket "sin verificar".

- **Source:** `packages/be_water/web/provenance.py`, `domain.py`
- **Verified by:** `packages/be_water/web/tests/test_provenance.py`

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
