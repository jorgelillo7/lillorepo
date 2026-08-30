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

> **GAP — unverified.** No test asserts the timeout and retry values reaching
> the Gemini client. A test would patch `gemini.generate_json` and assert
> `timeout=90, retries=1`.
