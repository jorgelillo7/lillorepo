# Capability: water-similarity

Mineral-profile similarity and recommendation engine for be_water. Given a
water's mineral vector, find the closest waters in the catalog; given a user's
favourites, recommend waters from a place and describe their taste profile.

- **Source:** `packages/be_water/web/similarity.py`, `packages/be_water/web/domain.py`
- **Verified by:** `packages/be_water/web/tests/test_similarity.py`

---

### Requirement: Log-scale weighted distance

The system SHALL score similarity as a weighted Euclidean distance over the
mineral fields **both** waters declare, in `log10(value + 1)` space (mineral
ranges span orders of magnitude, so absolute gaps mislead). Field weights:
TDS ×2.0 (the one-number summary of a water's character), sodium ×1.5, the
rest ×1.0. The sum SHALL be normalised by the number of shared fields so
waters with different coverage stay comparable.

#### Scenario: ordered by profile, not absolute gap
- **WHEN** comparing Solán (TDS 261) to Liviana (285) vs Bezoya (27) vs Vichy (3052)
- **THEN** Liviana is closest and Vichy is far, despite raw-number arithmetic
- *Verifies:* `test_distance_orders_by_profile_not_absolute_gap`

#### Scenario: a missing field must not inflate distance
- **WHEN** one water is identical to another except it omits one mineral
- **THEN** it scores closer than a genuinely different water
- *Verifies:* `test_distance_normalizes_by_shared_coverage`

### Requirement: Incomparable below minimum shared fields

When two waters share fewer than `MIN_SHARED_FIELDS` (3) declared fields, the
distance SHALL be `inf` — sparse labels (Lanjarón prints 4 values) must never
cluster just because their missing fields coincide as zeros. Incomparable
waters SHALL be excluded from results, never ranked.

#### Scenario: sparse waters are not similar
- **WHEN** two waters share only 1–2 declared fields
- **THEN** their distance is `inf`
- **AND** an incomparable water never appears in `similar_waters` output
- *Verifies:* `test_sparse_waters_are_not_comparable`,
  `test_similar_waters_excludes_incomparable_entries`

### Requirement: Closest waters exclude self

`similar_waters` SHALL return the `top_n` closest comparable waters to the
target, excluding the target itself, sorted nearest-first.

#### Scenario: self is excluded and order is nearest-first
- **WHEN** finding waters similar to Solán within a catalog that contains it
- **THEN** Solán is absent and Liviana ranks first
- *Verifies:* `test_similar_waters_excludes_self_and_sorts`

### Requirement: EU mineralisation classification

`mineralization_label(tds)` SHALL classify by dry residue using the EU bands:
`< 50` → *muy débil*, `< 500` → *débil*, `< 1500` → *fuerte*, `≥ 1500` →
*muy fuerte*, and `None` → *desconocida*.

#### Scenario: band boundaries
- **WHEN** TDS is 27 / 261 / 900 / 3052 / None
- **THEN** the label is muy débil / débil / fuerte / muy fuerte / desconocida
- *Verifies:* `test_mineralization_labels`

### Requirement: Favourites centroid

`favorites_centroid` SHALL be the per-field linear-space mean of the
favourites' mineral vectors, over declared values only (a field absent from a
favourite does not count against its mean). Empty favourites SHALL yield
`None`.

#### Scenario: fields averaged over declared values
- **WHEN** two favourites have TDS 261 and 285
- **THEN** the centroid TDS is 273 (their mean)
- *Verifies:* `test_centroid_averages_fields`

### Requirement: Place-scoped recommendations

`recommend` SHALL return catalog waters from `place` (matched against either
`province` or `community`, case-insensitively), closest to the favourites
centroid, excluding the favourites themselves. With no favourites it SHALL
return an empty list.

#### Scenario: filter by place, rank by centroid
- **WHEN** favourites = [Solán] and place = "Girona"
- **THEN** results are Girona-only (Ribes, Vichy) and Ribes — the weaker,
  Solán-like profile — ranks first, never Vichy
- *Verifies:* `test_recommend_filters_by_place_and_ranks_by_centroid`

#### Scenario: place matches community too
- **WHEN** place = "Cataluña" (a community, not a province)
- **THEN** Catalan waters are returned, Ribes first
- *Verifies:* `test_recommend_matches_community_too`

#### Scenario: no favourites → no recommendation
- **WHEN** favourites is empty
- **THEN** the result is an empty list
- *Verifies:* `test_recommend_without_favorites_is_empty`

### Requirement: Neighbour-province fallback

`recommend_nearby` SHALL apply the same centroid scoring to waters from
provinces bordering `place` (accent-insensitive), for places with no bottled
water of their own (Madrid is the canonical case). It SHALL return an empty
list when `place` has no known neighbours or there are no favourites.

> **GAP — unverified.** The geo helper `adjacent_provinces` is tested
> (`test_geo.py`), but `recommend_nearby`'s own filtering + scoring path has no
> test. Candidate for the next test-hardening pass.

### Requirement: Taste-profile description

`profile_traits` SHALL word the strongest deviations of the favourites centroid
from the catalog **median** per mineral (log-scale, declared values only),
returning the `top_n` most distinctive as human labels. It SHALL exclude TDS
(the mineralisation class already headlines it), ignore deviations under ~±30%
(`|log-ratio| < 0.12`), and skip any field observed in fewer than 5 catalog
waters (too little data to define a median).

#### Scenario: only distinctive traits, worded by direction
- **WHEN** the centroid is calcium-heavy and sodium-light vs the catalog, with
  magnesium near the median
- **THEN** traits include "rica en calcio" and "muy baja en sodio", and never
  mention magnesium
- *Verifies:* `test_profile_traits_words_the_strong_deviations`

#### Scenario: not enough catalog coverage → no trait
- **WHEN** a field is observed in fewer than 5 catalog waters
- **THEN** no trait is emitted for it
- *Verifies:* `test_profile_traits_needs_enough_catalog_coverage`
