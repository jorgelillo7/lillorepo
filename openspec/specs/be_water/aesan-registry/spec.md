# Capability: aesan-registry

Coverage tracking against the AESAN registry of officially recognised Spanish
mineral waters (a generated snapshot). Drives the "quedan N por cubrir" and the
pending-waters list on the community page.

- **Source:** `packages/be_water/web/aesan.py`, `aesan_snapshot.py`
- **Verified by:** `packages/be_water/web/tests/test_aesan.py`

---

### Requirement: Coverage counts unique names

`coverage` SHALL count the registry by **unique name**, so a brand recognised
under several springs counts once toward the total.

#### Scenario: multi-spring brand counts once
- **WHEN** the registry lists "Font Vella" under two springs plus two other
  brands, with one covered
- **THEN** total = 3 (unique names), covered = 1
- *Verifies:* `test_coverage_counts_unique_names`

### Requirement: Pending list dedupes multi-spring brands

`pending_waters` SHALL return uncovered registry entries collapsed to one row
per name (a brand with two springs is a single pending row).

#### Scenario: two springs, one pending row
- **WHEN** an uncovered brand spans two springs
- **THEN** it appears once in the pending list
- *Verifies:* `test_pending_dedupes_multi_spring_brand`

### Requirement: Pending length matches the coverage gap

The invariant the UI relies on: `len(pending_waters) == coverage.total −
coverage.covered`. "Quedan N" and "ver las N pendientes" SHALL always agree.

#### Scenario: count invariant holds
- **WHEN** computing coverage and the pending list over the same catalog
- **THEN** the pending length equals total − covered
- *Verifies:* `test_pending_length_matches_coverage_gap`
