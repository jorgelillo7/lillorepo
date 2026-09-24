# Capability: label-ocr

Reading a bottle's composition label from a photograph: the photo the
contributor takes becomes a prefilled form, and stays as the proof behind the
numbers.

- **Source:** `packages/be_water/web/label_ocr.py`,
  `packages/be_water/web/routes/add.py` (`add_water_photo`)
- **Verified by:** `packages/be_water/web/tests/test_routes.py`

---

### Requirement: The label is read into a fixed schema, and never invented

`extract_label` SHALL ask for a structured response covering the water's name,
spring, province, community, sparkling flag, analysis date and every field in
`MINERAL_FIELDS`, with every field nullable, and SHALL instruct the model to
return `null` for anything the label does not print.

A guessed mineral value is indistinguishable from a read one once it is in the
form, and the contributor is reviewing values they cannot check against a label
that never carried them. Absent has to stay absent.

The analysis date SHALL come back as `YYYY-MM`, or `YYYY` when the label prints
only a year, and SHALL NOT be confused with the batch or the best-before date.

#### Scenario: prefilled form
- **WHEN** a label photo is uploaded **THEN** the form comes back filled with
  what the label declared, and those mineral fields marked as label-read
- *Verifies:* `test_photo_flow_prefills_form_and_runs_studio`,
  `test_ocr_prefill_completes_provenance_from_aesan`

### Requirement: The composition shot is kept as proof, the pretty shot is optional

The uploaded composition photo SHALL be processed and stored as the label
photo, and an optional second "front of bottle" upload SHALL become the display
photo instead of the label shot.

A composition label is usually the ugly side of the bottle. Showing it as the
catalogue thumbnail is the wrong trade — but it is the only thing that proves
the numbers, so it is kept either way.

#### Scenario: one photo or two
- **WHEN** only the composition photo is uploaded **THEN** it is both proof and
  display
- **WHEN** a front shot is uploaded too **THEN** it becomes the display photo
- *Verifies:* `test_beauty_photo_becomes_the_display_shot`

### Requirement: The OCR and the studio photo run at the same time

The label read and the studio-photo generation SHALL be dispatched
concurrently, not in sequence. The studio call SHALL fire only for an admin
nickname; every other contributor SHALL still get the OCR prefill and keep
their raw photo.

Sequentially the wait was their sum, and the studio call alone can take ninety
seconds — the user was waiting on the one thing they did not ask for before the
one they did. Image generation is also the only paid call in the project, which
is why it is restricted while the OCR is not.

#### Scenario: concurrency and the admin gate
- **WHEN** an admin uploads a photo **THEN** both calls are in flight together
- **WHEN** a non-admin uploads **THEN** no studio call is made and the OCR
  prefill still arrives
- *Verifies:* `test_the_studio_photo_and_the_ocr_run_at_the_same_time`,
  `test_non_admin_upload_skips_studio_but_keeps_ocr`

### Requirement: Either call failing must not cost the other, or the photo

A failed studio call SHALL fall back to the raw photo and say so. A failed OCR
SHALL still store the photos and open the form for manual entry.

The photo is the expensive thing to reproduce — the contributor is standing in
front of a bottle they may not own. Losing it because a model was busy is the
one outcome worth engineering against.

#### Scenario: each failure in turn
- **WHEN** the studio call fails **THEN** the raw photo is kept, with a note
- **WHEN** the OCR fails **THEN** the form opens empty with both photos attached
- **WHEN** the OCR fails after a successful studio photo **THEN** the studio
  photo is still saved
- *Verifies:* `test_photo_flow_studio_failure_falls_back_to_raw`,
  `test_photo_flow_survives_gemini_failure`,
  `test_a_failed_ocr_still_saves_the_studio_photo`

### Requirement: An overloaded reader says so, instead of blaming the photo

When the OCR fails with a 429 or 503, **or times out**, the message SHALL say
the reader is busy and suggest trying later; any other failure SHALL name both
possibilities — the photo or the reader — rather than the photo alone.

Only a reply carries a status code, and when the model is busy enough the
request often gets no reply at all. That case fell through to the generic
wording, which reads as "your photo is unreadable" and had the owner
re-shooting the same bottle three times while the API was telling everyone else
it was experiencing high demand.

#### Scenario: overloaded, timed out, and merely unreadable
- **WHEN** the failure is a 429/503 or a read timeout **THEN** the message says
  the reader is saturated
- **WHEN** it is any other failure **THEN** the message names the photo *and*
  the reader
- *Verifies:* `test_photo_flow_gemini_overload_gets_honest_copy`,
  `test_an_unreadable_label_does_not_blame_the_photo_alone`

### Requirement: A slow read is waited for, not discarded

The label read SHALL allow 90 s, above the client default, and SHALL retry once.

The observed failure was a read timeout rather than an API error: reads that
were merely slow were being thrown away. The worker allows 240 s, and the call
now runs beside the studio photo rather than after it, so the wait is
affordable.

#### Scenario: 90 seconds, one retry
- **WHEN** a label is read **THEN** the Gemini call carries `timeout=90` and
  `retries=1`
- *Verifies:* `test_the_label_read_waits_90_seconds_and_retries_once`

### Requirement: Both photographed faces are read, and only one carries the ✓

When an optional front photo is uploaded it SHALL be read by the same
extractor, in parallel with the composition shot. It is already uploaded and
already paid for, and it is a second face of the same bottle: the composition
shot frames the mineral table, while spring, municipality and province usually
live elsewhere. Reading one face is how a ficha reached `verified` with no
origin at all.

`merge_label_reads` SHALL let the **composition** shot win every field it
declares, the second face filling only gaps. A gap is `None` or `""` — the
reader returns both for a field it could not find. `False` SHALL NOT be a gap:
`sparkling: False` is an answer, and treating it as missing would let the other
face turn a still water sparkling.

`ocr_fields` — which become `verified_fields` — SHALL be taken from the
composition read **before** the merge. That photo is what is stored as
`label_photo_url`, so a ✓ earned by a value only the other face declared would
point at a photograph that does not show it. Such a value still prefills the
form; it simply arrives unverified.

A failure of the second read SHALL be logged and ignored. It is a bonus, and
losing it must never cost the submission the composition shot already paid for.

#### Scenario: two faces, one prefill
- **WHEN** the composition read has no spring or province and the front read
  has both **THEN** the merged prefill carries them
- **WHEN** both declare `tds` **THEN** the composition value wins
- **WHEN** the composition read says `sparkling: False` **THEN** it stands
- **WHEN** only the front read declares a mineral **THEN** it prefills the form
  but is absent from `ocr_fields`
- **WHEN** no front photo was uploaded **THEN** nothing changes
- *Verifies:* `test_the_second_face_fills_gaps_the_first_left`,
  `test_the_composition_shot_wins_every_field_it_declares`,
  `test_a_false_is_a_value_and_not_a_gap`,
  `test_an_empty_string_is_a_gap`,
  `test_no_second_face_changes_nothing`,
  `test_the_front_shot_is_read_too_and_only_fills_gaps`,
  `test_the_tick_belongs_to_the_photo_that_is_stored_as_proof`,
  `test_beauty_photo_becomes_the_display_shot`

### Requirement: A third face is offered only when the origin is still missing

When the read leaves `spring` or `province` empty, the review form SHALL offer
one more upload for the face that carries the origin — typically the small
print beside the bottler's address. It SHALL NOT appear otherwise: 2 fichas in
51 need it, and the form must not get heavier for the other 49.

`POST /anadir/origen` SHALL read that photo and **discard it**. It never
becomes `label_photo_url` and never reaches storage: the composition shot stays
the verification proof, and `ocr_fields` is carried through untouched, so
nothing this face declares can earn a ✓.

The posted form state SHALL win over the new read — the contributor may have
corrected the reader before reaching for another photo — and SHALL survive the
round trip whole, including the temporary photo keys and typed minerals.

A failed read SHALL return the form with its state intact and say the origin
can be typed by hand.

#### Scenario: the face that answers the question the first two did not
- **WHEN** the read has no spring or province **THEN** the upload is offered
- **WHEN** it found both **THEN** it is not
- **WHEN** the origin face is read **THEN** the gaps fill, typed values stand,
  and `ocr_fields` is unchanged
- **WHEN** it is read **THEN** no photo is uploaded to storage
- *Verifies:* `test_the_origin_upload_appears_only_when_the_origin_is_missing`,
  `test_the_origin_photo_fills_the_gaps_and_keeps_what_was_typed`,
  `test_the_origin_photo_never_becomes_the_stored_proof`
