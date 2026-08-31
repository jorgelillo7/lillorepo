# Capability: photos

Photo handling for water entries: the studio-image pipeline (process, watermark,
upload) and the audit engine that diagnoses and repairs the catalog's shots.

- **Source:** `packages/be_water/web/photos.py`, `photo_audit.py`
- **Verified by:** `packages/be_water/web/tests/test_photo_audit.py`

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

> **GAP — unverified.** Every test mocks `process_image` / `studio_photo`; the
> real byte transformation (resize, canvas composition, watermark, EXIF) has no
> direct test (coverage of `photos.py` is ~34%). Given the daily digest ships
> Telegram photos and there is history of studio-photo failures, this is the
> top candidate for the next test-hardening pass: feed a synthetic image and
> assert output dimensions, watermark presence, and error handling on a corrupt
> input.

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
