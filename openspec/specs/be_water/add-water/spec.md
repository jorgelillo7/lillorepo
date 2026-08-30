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
