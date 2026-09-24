# Capability: photos

Photo handling for water entries: the studio-image pipeline (process, watermark,
upload) and the audit engine that diagnoses and repairs the catalog's shots.

- **Source:** `packages/be_water/web/photos.py`, `photo_audit.py`
- **Verified by:** `packages/be_water/web/tests/test_photo_audit.py`, `packages/be_water/web/tests/test_photos.py`

---

### Requirement: Studio-canvas detection

`looks_like_studio` SHALL recognise a processed studio image by its square
`_STUDIO_SIDE` dimensions and light canvas, rejecting wrong sizes and
dark-cornered images.

#### Scenario: shape and canvas checks
- **WHEN** the image is a square white canvas of the studio side
- **THEN** it is detected as studio
- **WHEN** the size is wrong, or the corners are dark
- **THEN** it is not
- *Verifies:* `test_looks_like_studio_true_for_square_white_canvas`,
  `test_looks_like_studio_false_for_wrong_size`

### Requirement: Catalog scan and verdict

`scan_catalog` SHALL classify each water with a photo (skipping photo-less
ones), marking `studio_ok` true/false, and `None` (undetermined) when the image
can't be read — never crashing. `suggest_verdict` SHALL map a status to `OK` or
`MAIN_NOT_STUDIO`.

#### Scenario: classification and resilience
- **WHEN** a studio and a raw photo (and a photo-less water) are scanned
- **THEN** the photo-less one is excluded; the studio is `OK`, the raw is
  `MAIN_NOT_STUDIO`
- **WHEN** a photo is unreadable
- **THEN** its `studio_ok` is `None`, no crash
- *Verifies:* `test_scan_catalog_flags_non_studio_main`,
  `test_scan_catalog_survives_unreadable_photo`

### Requirement: Repair operations

`rerun_studio` SHALL re-process and overwrite the main photo at its object path.
`replace_label` SHALL store the processed raw at the `originals/` path.
`delete_water` SHALL remove both objects (main then `originals/`) before the doc.

#### Scenario: rerun, replace, delete
- **WHEN** re-running studio on a water
- **THEN** the processed studio image overwrites the main object and the doc is saved
- **WHEN** replacing the label **THEN** it lands under `originals/`
- **WHEN** deleting **THEN** every object the water owns goes before the doc
  — the current pair and one pair per analysis, since a dated submission
  promotes its photos to `{water_id}__{date}.jpg`
- *Verifies:* `test_rerun_studio_overwrites_main`,
  `test_replace_label_targets_originals_path`,
  `test_delete_water_removes_every_object_it_owns_then_the_doc`

### Requirement: Image-processing pipeline

`process_image`, `studio_photo` and `_stamp_watermark` (`photos.py`) SHALL
normalise an uploaded shot, compose it onto the studio canvas and stamp the
watermark, producing the bytes uploaded to storage.

#### Scenario: real bytes through the pipeline
- **WHEN** a large photo is processed **THEN** it is downscaled within
  `MAX_SIDE` keeping its aspect ratio, re-encoded as RGB JPEG, and its EXIF is
  dropped; a small one keeps its size
- **WHEN** the studio step runs on Gemini's cutout **THEN** the result is the
  square white canvas with the watermark stamped bottom-right only
- **WHEN** Gemini fails **THEN** the failure propagates to the caller
- **WHEN** the upload is not an image, or is a JPEG cut off mid-upload
  **THEN** processing raises `NotAnImage` instead of producing bytes to store
- *Verifies:* `test_process_image_downscales_within_max_side_keeping_aspect`,
  `test_process_image_leaves_small_images_untouched_in_size`,
  `test_process_image_strips_exif`,
  `test_studio_photo_builds_square_watermarked_canvas`,
  `test_stamp_watermark_marks_bottom_right_only`,
  `test_studio_photo_propagates_gemini_failure`,
  `test_process_image_refuses_bytes_that_are_not_an_image`,
  `test_a_truncated_jpeg_is_not_an_image_either`

### Requirement: A file that is not a photo gets a sentence, not a 500

Each of the three upload points on the add form (the label shot, the optional
front shot and the origin face) SHALL answer an undecodable file by
re-rendering the form with "Ese archivo no parece una foto". Nothing SHALL be
uploaded to the bucket and nothing SHALL be sent to the label reader. The
origin face SHALL keep everything already on the form. Both photo-flow shots
SHALL be decoded before either is uploaded.

The picker asks for `image/*`, but nothing stops a PDF or a truncated file
reaching the route, and the app has no error page: an unhandled decode error
was a bare 500. The origin face is the third photo of a half-filled form, so
losing the form there would cost the contributor everything they typed.
Decoding both shots first means a bad front shot does not leave the label
shot orphaned under `uploads/`.

#### Scenario: label shot, front shot, origin face
- **WHEN** the label shot is not an image **THEN** the form comes back with
  the sentence, and nothing is uploaded or read
- **WHEN** the label shot is fine but the front shot is not **THEN** the same,
  and the reader is not called
- **WHEN** the origin face is not an image **THEN** the sentence appears and
  the typed name and the temporary photos survive
- *Verifies:* `test_a_non_image_photo_gets_a_message_not_a_500`,
  `test_a_non_image_front_shot_gets_a_message_not_a_500`,
  `test_a_non_image_origin_photo_keeps_the_form`

### Requirement: The studio shot lands on white, whatever the model returns

`studio_photo` SHALL force a **near-white** backdrop in the generated image to
pure white before squaring it onto the canvas, and SHALL leave a genuinely dark
or coloured background untouched.

Motive: the prompt asks for pure white and the model does not always deliver —
it returns the bottle on its own light-grey studio sweep, which the white
square canvas then frames as a visible grey rectangle. One ficha then looks
unlike every other in the grid, which is the whole point of the studio
treatment. Whitening a dark background instead would rewrite the photograph
rather than repair it, so the repair is limited to a white that drifted.

#### Scenario: drifted white, and a deliberate dark backdrop
- **WHEN** the model returns the bottle on a light-grey sweep **THEN** the
  backdrop is white and the bottle is untouched
- **WHEN** the background is dark or coloured **THEN** it is left as it is
- *Verifies:* `test_a_near_white_studio_backdrop_is_flattened_to_white`,
  `test_a_deliberately_dark_backdrop_is_left_alone`

### Requirement: A replaced photo replaces what visitors see

Every object the photo pipeline writes SHALL carry a `Cache-Control` of at most
five minutes, set as object metadata rather than as an upload request header.
A photo whose bytes are replaced at a path a ficha already points at SHALL be
given a URL the caches cannot already hold — a new object name, or the stored
URL suffixed with the new generation — when the ficha must show it immediately.

Motive: a public object defaults to an hour at the edge, and every path here is
overwritten in place — a re-run studio shot, a replaced composition label. The
ficha points at new bytes while the edge keeps serving the old ones, which
reads as the site having ignored the upload; it cannot be purged, and it
outlives a private window. A `Cache-Control` header on an `uploadType=media`
request is accepted and silently dropped, so it has to travel as metadata.

#### Scenario: uploading a photo
- **WHEN** any photo is uploaded **THEN** it carries `public, max-age=300` as
  object metadata
- **WHEN** a temporary upload is promoted **THEN** the copy inherits it
- *Verifies:* `test_upload_photo_asks_for_a_short_cache_on_every_object`,
  `test_upload_object_sends_cache_control_as_object_metadata`
