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
- **WHEN** deleting **THEN** both objects go before the doc
- *Verifies:* `test_rerun_studio_overwrites_main`,
  `test_replace_label_targets_originals_path`,
  `test_delete_water_removes_both_objects_then_doc`

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
