# Capability: add-water

The public add-a-water flow: a contributor photographs a bottle, reviews what
was read off the label, and saves. This capability owns **who may save, what
lands in the doc, and what happens when the water is already in the
catalogue** — the reading of the label is `label-ocr`, the per-field sourcing
and the dated series are `provenance`, and the monthly reconciliation is
`catalog-sync`.

- **Source:** `packages/be_water/web/submission.py`,
  `packages/be_water/web/routes/add.py`
- **Verified by:** `packages/be_water/web/tests/test_submission.py`,
  `packages/be_water/web/tests/test_routes.py`

---

### Requirement: Only a signed-in, unblocked contributor may save

`/anadir` SHALL redirect a visitor with no nickname, and SHALL refuse to write
anything for a blocked one.

#### Scenario: the gate
- **WHEN** a visitor with no session opens the form **THEN** they are redirected
- **WHEN** a blocked nickname posts a water **THEN** nothing is saved
- *Verifies:* `test_add_water_requires_login`,
  `test_blocked_nickname_cannot_login_or_add`

### Requirement: The id comes from the name, folded to ASCII

`slugify` SHALL fold accents before slugging, so `Lanjarón` becomes `lanjaron`.

The fold has to happen first or the duplicate guard misses: slugging the
accented text directly yields `lanjar-n`, which matches no existing doc and
creates a second ficha for a water already in the catalogue.

#### Scenario: accented names
- **WHEN** the name carries accents **THEN** the id is their ASCII fold
- *Verifies:* `test_slugify_folds_accents`

### Requirement: A near-duplicate is asked about, never merged silently

Before creating a new water, the flow SHALL look for a similar name by token
subset (`similar_water`) and re-render the form with the candidate for the
contributor to confirm. An **exact** name whose declared spring shares no token
with the stored one (`springs_differ`) SHALL also be asked about rather than
merged.

Two waters can share a commercial name and be different products — the Font
Vella case, Sacalm versus Sigüenza. Merging them silently destroys one
composition; refusing outright blocks a legitimate second source. Only the
contributor holding the bottle can tell, so they are asked.

When they answer "it is a new water", the id SHALL be disambiguated with the
spring tokens the name does not already carry (`disambiguated_id`).

#### Scenario: fuzzy match, differing spring, and the split
- **WHEN** a submitted name is a token subset of a catalogue name **THEN** the
  candidate comes back for confirmation
- **WHEN** the springs share no token **THEN** the same, even on an exact name
- **WHEN** the contributor forces a new water **THEN** the id gains the spring
  tokens
- *Verifies:* `test_similar_water_matches_on_token_subset`,
  `test_springs_differ_only_for_genuinely_different_sources`,
  `test_disambiguated_id_appends_new_spring_tokens_only`

### Requirement: Free text is capped, minerals are parsed and range-guarded

Text fields SHALL be trimmed and capped at `MAX_FIELD_LEN` (80). Mineral inputs
SHALL accept a decimal comma, ignore unparseable values, and keep only
`0 ≤ value ≤ MAX_MINERAL_VALUE` (100 000 mg/L). `brand` SHALL default to the
name when not given.

The cap is a public-form guard, not a domain rule — nobody's manantial needs 80
characters. The mineral ceiling is the point past which the reading is not
water, so it is a typo rather than a measurement.

#### Scenario: caps, commas and nonsense
- **WHEN** a value is `"1,5"` **THEN** it is stored as `1.5`
- **WHEN** a value is not a number, or out of range **THEN** it is dropped
- **WHEN** no brand is given **THEN** the brand is the name
- *Verifies:* `test_parse_minerals_normalises_comma_and_guards_range`,
  `test_build_water_defaults_brand_to_name`

### Requirement: Merging into an existing doc lets the form win, and loses nothing

When a submission targets an existing unverified water, the reviewed form
SHALL take precedence field by field, while everything the form cannot carry
survives from the stored doc: minerals merge, photos, spring, place, brand,
mentions and `verified_fields` are kept when the form leaves them empty. A
confirmed fuzzy match SHALL keep the stored canonical display name.

Attribution SHALL follow the contributor who did the work: a **seeded** water
is adopted by whoever first backs it with a label, while a water contributed by
a real user keeps its original author and date.

The form is a partial view of a water — it has no field for mentions and may
legitimately leave the spring blank. Treating it as the whole truth would
delete data on every edit.

#### Scenario: precedence, survival and attribution
- **WHEN** the form fills some fields and leaves others empty **THEN** the
  filled ones win and the rest survive from the doc
- **WHEN** the existing water was seeded **THEN** the contributor becomes its
  author
- **WHEN** it was contributed by a user **THEN** the original author stays
- **WHEN** the merge was a confirmed fuzzy match **THEN** the canonical name
  stays
- *Verifies:* `test_apply_existing_form_wins_but_preserves_uncarried_fields`,
  `test_apply_existing_adopts_seed_water_for_the_new_contributor`,
  `test_apply_existing_merge_into_keeps_canonical_name`,
  `test_merge_keeps_original_author_for_user_waters`

### Requirement: A verified water cannot be overwritten — but accepts its own past

A submission targeting a **verified** water SHALL be refused with an
explanation, except when the submitted analysis predates the one on file, which
SHALL be accepted into the history.

A verified water is bottle-checked and data-frozen against the monthly sync, so
nothing may quietly replace its numbers. But the guard once ran before the
submitted date was parsed and refused everything — blocking the one case the
history exists for, photographing an older label of a water already verified,
with a message that said "cannot be overwritten" while the submission was not
going to overwrite anything.

#### Scenario: refusal, and the accepted past
- **WHEN** a current-or-newer submission targets a verified water **THEN** it is
  refused with the explanation
- **WHEN** the submission is an older analysis **THEN** it is saved to the
  history
- *Verifies:* `test_add_water_refuses_verified_duplicates`,
  `test_a_verified_water_still_accepts_an_older_analysis`

### Requirement: A label photo backing every declared mineral promotes to verified

On save, mineral fields the OCR read off the label and a human reviewed SHALL
become `verified_fields`. When a label photo is stored **and** every declared
mineral is verified, the water SHALL become `verified`. A single hand-typed
mineral the label does not declare SHALL keep it unverified.

Verification means "these numbers are on a photograph anyone can check". One
typed value with no proof breaks that claim for the whole ficha, so the
promotion is all-or-nothing.

#### Scenario: full coverage, and one extra value
- **WHEN** the label declares every mineral and the photo is stored **THEN** the
  water is verified
- **WHEN** an extra mineral is typed by hand **THEN** it is not
- **WHEN** OCR fields are submitted **THEN** they land in `verified_fields`
- *Verifies:* `test_full_label_coverage_auto_promotes_to_verified`,
  `test_hand_typed_extra_mineral_blocks_auto_promotion`,
  `test_verified_fields_only_keeps_declared_minerals`,
  `test_add_marks_ocr_fields_as_verified`

### Requirement: An older label is confirmed, never silently applied

When the submitted analysis is older than the stored one — or undated against a
dated one — the flow SHALL warn and require an explicit confirmation before
saving, and SHALL snapshot the current values so the change is reversible.

The submission is never blocked: the contributor is holding the bottle and may
well be right. What must not happen is losing a newer measurement to a click.

#### Scenario: older, undated, and newer
- **WHEN** the submitted analysis is older, or undated against a dated ficha
- **THEN** a confirmation is required
- **WHEN** it is newer **THEN** it saves straight through, still snapshotted
- *Verifies:* `test_older_or_undated_analysis_warns_newer_one_does_not`,
  `test_no_warning_when_there_is_nothing_to_protect`,
  `test_an_undated_label_over_a_dated_one_still_needs_confirming`,
  `test_a_newer_label_saves_straight_through_but_still_snapshots`

### Requirement: Saving promotes both photos out of the upload prefix

On save, the display photo and the label photo SHALL be moved from `uploads/`
to their permanent paths and stored on the doc. A promotion that fails SHALL
flag the water rather than leave the photo where it is.

`uploads/` is swept by a lifecycle rule, so a ficha whose photo was never
promoted works for weeks and then shows nothing. The flag is what the admin
page reads.

#### Scenario: promotion on save
- **WHEN** a submission carries both temporary photos **THEN** both are promoted
  and their permanent URLs stored
- *Verifies:* `test_add_with_photo_tmp_promotes_both_and_stores_urls`,
  `test_add_water_saves_and_redirects`

### Requirement: The country decides whether Spanish geography applies

`Water.country` SHALL be written on save from a closed vocabulary
(`geo.COUNTRIES`), defaulting to `ES` — for a form that says nothing, and for
an unrecognised code. The form is public, and `country` now switches the
geography rules, so a junk value must not switch them off silently.

For a non-`ES` water, `resolve_place` SHALL keep the region as typed and leave
`community` **empty**. It SHALL NOT derive a community and SHALL NOT apply the
province/community shift repair: both are Spanish-geography rules, and running
them on a Portuguese bottle is what stored `province='portugal',
community='portugal'` — the country asserted twice, as two things it is not.

The shift repair SHALL continue to work unchanged for `ES`.

#### Scenario: a foreign water keeps its region and gains no community
- **WHEN** `Fafe` / `PT` is submitted **THEN** province is `Fafe`, community `''`
- **WHEN** `Braga` / `Portugal` / `PT` is submitted **THEN** the fields are not
  shifted
- **WHEN** `Talarrubias` / `Badajoz` / `ES` is submitted **THEN** the shift is
  still repaired to `Badajoz` / `Extremadura`
- **WHEN** the form carries no country, or `ZZ` **THEN** `ES`
- *Verifies:* `test_a_foreign_water_keeps_its_region_and_gets_no_community`,
  `test_a_foreign_water_never_shifts_its_fields`,
  `test_the_field_shift_repair_still_works_for_spain`,
  `test_country_defaults_to_spain_when_the_form_says_nothing`,
  `test_an_unknown_country_code_falls_back_to_spain`

### Requirement: A foreign water is absent from Spanish-geography surfaces

Surfaces built on provinces and communities SHALL skip non-`ES` waters rather
than let them fall out silently:

- The **sitemap** SHALL list `?lugar=` pages only for Spanish waters' places.
- The 🗺️ **Cartógrafo** badge SHALL count Spanish provinces only; a foreign
  region is not a province and must not earn it.
- A 🌍 **Trotamundos** badge SHALL be earned by adding a water bottled outside
  Spain.

The **ficha** SHALL still render an origin for a foreign water — region and
country name — and `country_name` SHALL fall back to the raw code, never blank.

#### Scenario: foreign waters in and out of the Spanish surfaces
- **WHEN** the catalog holds a Spanish and a Portuguese water
- **THEN** the sitemap carries the Spanish place and not the Portuguese region,
  while both fichas stay indexed
- **WHEN** a contributor has five Spanish provinces and one foreign region
- **THEN** the province count is 5 and 🗺️ is not awarded, but 🌍 is
- *Verifies:* `test_the_sitemap_lists_only_places_the_spanish_geography_covers`,
  `test_cartographer_does_not_count_a_foreign_locality_as_a_province`,
  `test_a_foreign_water_earns_the_globetrotter_badge`,
  `test_an_unknown_country_code_still_renders_something`

### Requirement: The label's own identity keys are kept

`Water` SHALL carry `registry_id` (Spain's sanitary registry number, as the
label prints it) and `bottler` (the company that fills the bottle), both
defaulting to `""` so every existing ficha reads unchanged. The reader SHALL
be asked for both, and the admin form SHALL edit them.

They are the two things on the label that identify a water unambiguously, and
neither had a field. Identity is otherwise matched by `aesan.registry_matches`
— fuzzy token overlap on a commercial name — which cannot separate two springs
of one brand and misses every white label, since those register under the
producer. The bottler is the only thing that reveals two supermarket
own-brands are the same water from the same spring.

`normalize_registry_id` SHALL accept the number with or without its `RGSEAA`
prefix, uppercase and strip it, and return `""` for anything that is not one.
A malformed value is worse than none: it looks like an official key and would
be trusted as one, and the reader will sometimes answer this field with prose.

The suffix SHALL NOT be used to derive the province. It appears to encode it on
the one bottle where it is legible, and one bottle is not evidence.

#### Scenario: read, normalised, shown
- **WHEN** the label reads `RGSEAA 27.02231/BA` **THEN** `27.02231/BA` is stored
- **WHEN** the field holds `"no consta"`, `"RGSEAA"` or `"12345"` **THEN** `""`
- **WHEN** a ficha carries either **THEN** the ficha renders them
- **WHEN** an older document has neither **THEN** both read `""`
- *Verifies:* `test_a_registry_number_is_kept_uppercase_and_trimmed`,
  `test_text_that_is_not_a_registry_number_is_dropped`,
  `test_the_registry_prefix_is_accepted_and_stripped`,
  `test_a_water_carries_its_registry_number_and_bottler`,
  `test_both_default_to_empty_for_every_existing_ficha`,
  `test_the_ficha_shows_the_registry_number_and_bottler`
