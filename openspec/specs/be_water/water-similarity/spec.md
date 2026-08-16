# Capability: water-similarity

Mineral-profile similarity and place search for be_water. Given a water's
mineral vector, find the closest waters in the catalog; given a place, list the
waters there and nearby; given a user's favourites, order those lists to their
taste and describe it.

- **Source:** `packages/be_water/web/similarity.py`,
  `packages/be_water/web/domain.py`, `packages/be_water/web/geo.py`,
  `routes/main.py::recommend`
- **Verified by:** `packages/be_water/web/tests/test_similarity.py`,
  `test_geo.py`, `test_routes.py`

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
cluster just because their missing fields coincide as zeros. An incomparable
water SHALL never be **ranked**, which cuts two ways by surface:

- Where the answer *is* a similarity claim — `similar_waters`, the `/perfil`
  match list — it SHALL be excluded. An uncomparable water is not an answer to
  "what else is like this".
- Where the list claims to be **complete** — a region listing — it SHALL be
  appended after every comparable water, in neutral order. A region's water
  vanishing from a page that says it shows the region is the worse answer.

#### Scenario: sparse waters are not similar
- **WHEN** two waters share only 1–2 declared fields
- **THEN** their distance is `inf`
- **AND** an incomparable water never appears in `similar_waters` output
- *Verifies:* `test_sparse_waters_are_not_comparable`,
  `test_similar_waters_excludes_incomparable_entries`

#### Scenario: incomparable but present in its own region
- **WHEN** a region holds a water too sparse to score against the centroid
- **THEN** it is listed last, after the ranked waters, never dropped
- *Verifies:* `test_a_water_too_sparse_to_rank_still_appears_last`

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

### Requirement: The region listing is public and identity-independent

`waters_in_place` SHALL return **every** catalog water from `place` — matched
against `province` or `community`, accent- and case-insensitively — with no
cap, no favourites filter and no scoring. The set a place resolves to SHALL
depend only on `place`: not on whether a visitor is logged in, and not on
whether they have favourites. An empty or blank `place` SHALL return nothing.

The catalogue is already public on `/` and `/agua/<id>`. A region search that
answered "entra con tu nick" made `/recomendar` contradict the rest of the
site, and left it in the sitemap with no content for an anonymous crawler.

#### Scenario: an anonymous visitor gets waters, not a login wall
- **WHEN** a visitor with no session searches a place that has waters
- **THEN** the waters render, and the login invitation appears *below* them
  as a call to action
- *Verifies:* `test_an_anonymous_visitor_gets_the_waters_not_a_login_wall`,
  `test_a_registered_visitor_without_favorites_sees_the_same_set`

#### Scenario: place matches province, community, and unaccented spellings
- **WHEN** place = "Cataluña", or "Girona", or a hand-typed "cadiz"
- **THEN** the waters of that place are returned in each case
- *Verifies:* `test_place_matches_community_too`,
  `test_place_matching_ignores_accents_and_case`,
  `test_a_hand_typed_unaccented_place_still_finds_its_waters`

#### Scenario: an empty place is not a wildcard
- **WHEN** `place` is `""` and the catalog holds waters with a blank community
- **THEN** nothing is returned — a blank place must not match a blank field
- *Verifies:* `test_an_empty_place_matches_nothing`

### Requirement: Identity orders the listing, never redraws it

The listing SHALL be ordered by one of two rules:

- **Neutral** (`by_mineralization`) — ascending dry residue, undeclared TDS
  last, name as tie-break. The default for a visitor with no favourites.
- **Personalised** (`rank_by_centroid`) — closest to the favourites centroid
  first. The default for a visitor with favourites.

`?perfil=0` SHALL opt out of personalisation. It is written as an opt-out so a
stray parameter in a shared URL degrades to the neutral view rather than
needing a case of its own. The two orders SHALL be permutations of the same
set — the invariant that makes the toggle honest.

Nothing is truncated in either mode. A cap would break that invariant in the
neutral mode specifically: capping a weakest-first list always returns *the
same weakest few*, so the rest of a large region would be permanently
unreachable.

#### Scenario: same waters, different order
- **WHEN** the same place is searched with and without `?perfil=0`
- **THEN** both return the same set of waters, ordered differently
- *Verifies:* `test_the_region_listing_does_not_depend_on_who_asks`,
  `test_favorites_personalize_the_order_and_perfil_0_opts_out`

#### Scenario: neutral order is weakest-first
- **WHEN** ordering waters neutrally, one of which declares no TDS
- **THEN** they run from lowest to highest dry residue, the undeclared last
- *Verifies:* `test_neutral_order_is_weakest_first_with_unknown_tds_last`

### Requirement: Favourites are kept in the region, dropped from nearby

The region listing SHALL **include** the visitor's favourites: "what do I
drink here" is best answered by their own water when it is from here.
Excluding them once emptied La Rioja, whose single catalogue water is
Peñaclara, and the neighbour section then offered Zaragoza as if the province
had none.

The nearby listing SHALL **exclude** them, and SHALL exclude the place's own
waters too. It answers "what else is around", where a water already listed
above — or already a favourite — is not an answer. The asymmetry is
deliberate.

#### Scenario: a place whose only water is already a favourite still returns it
- **WHEN** favourites include the only catalogue water of the searched place
- **THEN** it is the result, not a redirection to the neighbours
- *Verifies:* `test_a_place_whose_only_water_is_already_a_favorite_still_returns_it`

#### Scenario: nearby never repeats the region
- **WHEN** the place has waters of its own
- **THEN** none of them appears in the nearby section
- *Verifies:* `test_nearby_excludes_the_places_own_waters`

### Requirement: Neighbouring places are always offered

`waters_near_place` SHALL return waters from the provinces bordering `place`,
whether `place` names a **province or a community** — `geo.adjacent_places`
derives a community's neighbours as the union of its provinces' neighbours
minus its own. It SHALL return an empty list when the place has no land
border, and the section SHALL then be absent rather than an empty heading.

Nearby is offered **alongside** the region, not only when the region is empty.
As a fallback it was invisible unless the visitor searched Madrid; and
`adjacent_provinces` answers `[]` for every community, which silently emptied
it for half the selector.

#### Scenario: a community search finds its neighbours
- **WHEN** place = "Comunidad de Madrid" and Bezoya (Segovia) is in the catalog
- **THEN** Bezoya is offered as nearby; a Girona water is not
- *Verifies:* `test_nearby_works_for_a_community_not_only_a_province`,
  `test_a_community_search_offers_its_neighbours`,
  `test_adjacent_places_covers_communities_as_well_as_provinces`

#### Scenario: nearby is offered even when the region has its own waters
- **WHEN** the searched place has waters and a neighbour has others
- **THEN** both sections render
- *Verifies:* `test_nearby_is_offered_even_when_the_place_has_its_own_waters`

#### Scenario: an island has no neighbours, and no empty heading
- **WHEN** place = "Illes Balears" or "Canarias"
- **THEN** the nearby list is empty and the section is absent; the page invites
  adding the first water instead
- *Verifies:* `test_nearby_is_empty_when_the_place_has_no_neighbours`,
  `test_islands_and_unknown_places_have_no_neighbouring_places`,
  `test_a_place_with_no_waters_and_no_neighbours_invites_the_first`

### Requirement: Every place is offered and indexable

The `/recomendar` selector SHALL offer every Spanish province and every
autonomous community, not only those the catalogue happens to cover — a place
with no water of its own answers with its neighbours', and one with neither
invites the first. The sitemap SHALL list `/recomendar?lugar=<place>`,
percent-encoded, for every place the catalogue covers, and each place page
SHALL carry its own `<title>` and meta description.

#### Scenario: the selector is the whole geography
- **WHEN** the page renders with a catalogue covering few communities
- **THEN** Comunidad de Madrid, Región de Murcia and Canarias are still offered
- *Verifies:* `test_the_selector_offers_every_community`

#### Scenario: place URLs survive as valid XML and valid URLs
- **WHEN** the sitemap lists a place with an accent and a space
- **THEN** it appears percent-encoded (`Castilla%20y%20Le%C3%B3n`)
- *Verifies:* `test_sitemap_lists_place_pages_percent_encoded`

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
