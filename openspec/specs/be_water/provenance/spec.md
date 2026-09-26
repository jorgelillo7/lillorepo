# Capability: provenance

Per-field sourcing for a water's mineral values, so the UI can name where each
number came from (`label` / `aesan` / `manual`) — never a source guessed after
the fact, and never a number nobody can stand behind.

- **Source:** `packages/be_water/web/provenance.py`, `domain.py`,
  `submission.py`, `routes/add.py`
- **Verified by:** `packages/be_water/web/tests/test_provenance.py`,
  `test_submission.py`, `test_routes.py`

---

### Requirement: Derive sources from the registry, never invent a mineral's

`derive_sources` SHALL keep every source a water already records, and SHALL
add `aesan` to province and community only when the AESAN registry match
agrees with the stored value. It SHALL NOT fill in a source for a mineral:
who wrote a number nobody recorded cannot be known after the fact, and
naming a source for it would be inventing one.

That is the rule, because it once was broken. A seed dataset of values
transcribed from brands' sites let the ficha label any matching number
"fabricante"; two documents were found carrying that mark on values no
photographed label printed, or on values a label did print but was not
credited for. The seed is gone and those documents were corrected.

#### Scenario: minerals are left alone, recorded sources kept
- **WHEN** a mineral has no recorded source **THEN** none is derived
- **WHEN** it already has one **THEN** it is kept
- *Verifies:* `test_a_mineral_with_no_recorded_source_stays_unknown`,
  `test_existing_source_is_kept`

#### Scenario: identity from AESAN only on agreement
- **WHEN** the AESAN registry match agrees on province **THEN** province and
  community are sourced `aesan`
- **WHEN** it disagrees **THEN** no `aesan` source is set
- *Verifies:* `test_province_and_community_from_aesan_registry`,
  `test_no_aesan_source_when_registry_disagrees`

### Requirement: A province decides its own community

`resolve_place` SHALL store the community that belongs to the submitted
province whenever the province is one this repo knows, rather than whatever
the form carried. A province's community is a fact, not the contributor's to
choose, and "Valencia · Cataluña" used to save exactly as typed.

A submitted *community* that is really a **province** SHALL be read as the
fields having been shifted one slot, and corrected. `tramuntana` reached
production with `province="Talarrubias"` — a town in Badajoz — and
`community="Badajoz"`, which dropped it out of every province and community
view in silence, because the place search matches province or community and
it had neither.

Text matching neither list SHALL be kept as typed. A village nobody has
mapped is still what the contributor read on the label; `data_audit` is where
a human decides. Only a provable mistake is repaired.

#### Scenario: what reaches the doc
- **WHEN** the province is known **THEN** its own community is stored, even if
  the form named a different one
- **WHEN** the community names a province and the province names nothing
- **THEN** the pair is read as shifted: the community becomes the province and
  the real community is derived
- **WHEN** neither is recognised **THEN** both are stored as typed
- *Verifies:* `test_build_water_derives_the_community_from_the_province`,
  `test_a_known_province_decides_its_own_community`,
  `test_a_community_that_is_really_a_province_means_the_fields_are_shifted`,
  `test_a_place_nobody_has_mapped_is_kept_as_typed`,
  `test_build_water_leaves_an_unknown_province_without_a_community`

### Requirement: Each source means one thing, and the ficha says so

`label` / `manual` / `aesan` — and the absence of any — are a vocabulary shown
to readers, not internal states, and each SHALL keep its meaning:

| Value | Renders | Means |
|---|---|---|
| `label` | ✓ etiqueta | Read off a photographed label kept as proof |
| `manual` | a mano | The contributor submitted it, and no label backs it |
| `aesan` | AESAN | Identity cross-checked against the state register — **never a composition** |

The ficha SHALL let a reader reach the explanation of any badge it shows. The
badges carried their meaning in a `title` attribute alone, which does nothing
on a touch screen, and the page they linked to explained three of the four
words — never `manual`. Every badge now links to its own entry there, and no
badge may render without one.

Nothing had ever stated this vocabulary: the four values existed only as
constants and template branches, which is why `manual` could be quietly
repurposed as "not confirmed by a label" without a single test or spec
objecting.

#### Scenario: a reader can find out where a number came from
- **WHEN** a ficha shows fields sourced from a label and from a contributor
- **THEN** each badge links to the entry in `/acerca` that explains that
  source, and every anchor it links to exists on that page
- *Verifies:* `test_every_provenance_badge_links_to_an_explanation_that_exists`

### Requirement: Only a backed number is shown; an unphotographed ficha says so

Every stored mineral SHALL be backed: read off a photographed label, or
carrying a recorded source. A water nobody has photographed SHALL have no
composition, and its ficha SHALL say so and point to the add flow, rather than
show numbers nobody can stand behind. Every page SHALL serve such a water.

The catalogue started from a seed of values transcribed from brand sites.
Checked against the photographed labels, none of the unbacked values that
survived on photographed fichas appeared on the bottle, so the seed's numbers
were removed wherever no label backed them: 28 fichas were emptied and seven
lost the values their label does not print. The empty ones fill themselves as
bottles are photographed. `scripts/purge_unbacked_minerals.py` enforces the
invariant on existing data, dry-run by default.

#### Scenario: an empty ficha, and pages that cope with it
- **WHEN** a water has no composition **THEN** its ficha says "Composición
  pendiente" and links to the add flow
- **WHEN** such a water is in the catalogue, the favourites or a search
  **THEN** the home, ficha, search, community, about and sitemap pages serve it
- *Verifies:* `test_an_empty_ficha_asks_for_the_label_photo`,
  `test_every_page_serves_a_water_with_no_composition`

#### Scenario: what the purge keeps
- **WHEN** a mineral has no label and no real source **THEN** it is unbacked
  and removed; an unphotographed ficha is emptied
- **WHEN** an analysis entry's value is verified on its ficha from the same
  photo **THEN** it is re-marked as label-verified instead
- *Verifies:* `test_a_value_with_no_source_and_no_label_is_unbacked`,
  `test_an_unphotographed_ficha_is_emptied`,
  `test_a_value_no_label_backs_is_removed_with_its_source`,
  `test_an_entry_value_its_ficha_read_off_the_same_label_becomes_verified`

### Requirement: Sources recomputed on save

`sources_on_save` SHALL mark `manual` every mineral the contributor submitted
in the form that was not read off the label. A mineral merged through from the
ficha, which the contributor never submitted, SHALL keep the source it had, or
none. Fields that became label-backed or no longer exist as minerals SHALL be
dropped; identity (province/community) sources SHALL be preserved.

`manual` means a contributor submitted it, and SHALL NOT be used as the
catch-all for "not confirmed by a label". Lunares' label declares eight
minerals; the ficha held ten, and the two merged-through values were credited
to whoever photographed the bottle.

#### Scenario: save recomputation
- **WHEN** the contributor submits minerals, some read off the label **THEN**
  the rest are `manual` and the label ones are not stored
- **WHEN** a value was merged from the ficha, not submitted **THEN** it keeps
  its source, or has none
- **WHEN** a value is resubmitted **THEN** it becomes `manual`
- **WHEN** a field became label-backed or vanished **THEN** it is dropped
- *Verifies:* `test_what_the_contributor_submitted_is_manual_labels_implied`,
  `test_a_value_merged_from_the_ficha_is_not_credited_to_the_contributor`,
  `test_a_merged_value_keeps_the_source_it_had`,
  `test_resubmitting_a_value_makes_it_the_contributor_s`,
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

### Requirement: a composition is a dated series, not a single value

The same water from the same spring measures differently in different lab
analyses. A **dated** composition SHALL join `water_analyses`, keyed by its
analysis date, whatever its age. `waters/{water_id}` SHALL keep the most recent
one, and the catalog, the search and the similarity engine SHALL read only
that, so a water with a series appears exactly once everywhere but its ficha.

An analysis that predates the stored one SHALL join the series and **leave the
ficha untouched**. It used to overwrite the present after a warning the
contributor confirmed, which is a measurement lost by clicking through a
dialog. There is nothing to warn about when nothing is replaced.

A submission for a date already in the series SHALL replace that entry, so a
mis-read past year is correctable from the form rather than a CLI.

`verified_fields`, `sources` and the label photo SHALL travel **inside** the
entry, and a dated label SHALL be promoted to
`originals/{water_id}__{analysis_date}.jpg`. Both for the same reason: one path
and one tick-list per water would print one year's "confirmado por etiqueta"
over another year's numbers, and the second label would overwrite the first
one's proof — destroying the evidence of the very entry the history exists to
keep.

An **undated** composition SHALL NOT enter the series: it has no place on a
timeline, and 34 of 46 waters are in that state because the label is not
required to print the date. It may still be the ficha's composition, and
replacing a dated one with it is still an overwrite — so that case alone keeps
the warning, the confirmation and the snapshot.

Any save that changes an existing ficha's minerals SHALL first snapshot the
whole previous document to `water_revisions`, tagged `older_analysis` or
`composition_changed`, so a bad edit is reversible from
`scripts/revert_water.py`. That trail stays a trail: it is deletable, and the
series is not.

#### Scenario: where a submitted composition goes
- **WHEN** the analysis is older than the ficha's
- **THEN** it joins the series, the ficha does not change, and nothing is
  snapshotted — no confirmation is asked for
- **WHEN** the analysis is newer **THEN** it becomes the ficha's and joins the
  series, snapshotting the previous doc if the composition moved
- **WHEN** the date is already in the series **THEN** that entry is replaced
- **WHEN** the composition carries no date **THEN** it never joins the series,
  and replacing a dated one still warns and snapshots
- **WHEN** two analyses exist **THEN** each keeps its own label photo, its own
  bottle photo and its own verified fields — a submission's photos are promoted
  to `{water_id}__{date}.jpg`, never to the bare path an older submission would
  overwrite invisibly
- **WHEN** an entry brought no bottle photo **THEN** the ficha's is shown for
  it; the label never falls back, because it is the evidence for that year
- **WHEN** a past analysis is on screen **THEN** the page's own metadata
  describes it — title, description, `og:image` and the JSON-LD all follow the
  entry shown, while the canonical URL drops `analisis` so the variants
  consolidate on the ficha instead of competing with it
- **WHEN** the ficha already holds minerals the submission does not declare
  **THEN** the entry records only the declared ones, with only the ✓ that
  submission earned, while the ficha keeps the merge — an entry is the record
  of one measurement, the ficha is the best-known current state and is what the
  catalog, the search and the mineralisation badge read
- **WHEN** the composition does not move **THEN** no snapshot is taken
- *Verifies:* `test_an_older_analysis_does_not_touch_the_current_composition`,
  `test_an_older_analysis_needs_no_confirmation_any_more`,
  `test_an_undated_label_over_a_dated_one_still_needs_confirming`,
  `test_a_resubmission_for_the_same_date_replaces_that_entry`,
  `test_an_undated_composition_never_enters_the_series`,
  `test_each_dated_analysis_keeps_its_own_label_photo`,
  `test_an_older_submission_never_overwrites_the_current_bottle_photo`,
  `test_an_analysis_entry_keeps_the_photos_that_submission_brought`,
  `test_a_past_analysis_shows_the_bottle_of_its_own_year`,
  `test_an_analysis_with_no_bottle_of_its_own_keeps_the_ficha_s`,
  `test_a_past_analysis_swaps_the_numbers_and_its_verification`,
  `test_a_dated_entry_carries_only_what_that_label_declared`,
  `test_the_ficha_keeps_the_merge_the_entry_does_not`,
  `test_a_past_analysis_does_not_advertise_the_present_numbers`,
  `test_only_the_ficha_reads_the_analysis_series`,
  `test_an_unknown_analysis_is_a_404_not_the_current_one`,
  `test_a_newer_label_saves_straight_through_but_still_snapshots`,
  `test_no_snapshot_when_the_composition_did_not_move`,
  `test_older_or_undated_analysis_warns_newer_one_does_not`,
  `test_no_warning_when_there_is_nothing_to_protect`
