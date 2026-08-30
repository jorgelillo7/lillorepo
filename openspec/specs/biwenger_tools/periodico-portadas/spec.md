# Capability: periodico-portadas

The league newspaper's front pages: published by sending the image to the bot's
owner chat, and rendered on `/{season}/salseo`.

Both halves ride on a public bucket rather than Firestore — the web reads
`periodico/{season}/index.json` at request time and resolves each image as
`{fecha}.jpg`, so publishing a front page needs no deploy and no credentials on
the web side.

- **Source:** `packages/biwenger_tools/api/logic/periodico.py`,
  `packages/biwenger_tools/api/app.py` (`/periodico/portada`),
  `packages/biwenger_tools/bot/app.py` (webhook media branch),
  `packages/biwenger_tools/web/routes/season.py` (`_fetch_portadas`)
- **Verified by:** `packages/biwenger_tools/api/tests/test_periodico.py`,
  `packages/biwenger_tools/bot/tests/test_bot.py`,
  `packages/biwenger_tools/web/tests/test_web_app.py`

---

### Requirement: The date names the front page

A front page SHALL be stored as `periodico/{season}/{fecha}.jpg` with its
headline in `periodico/{season}/index.json`, where `fecha` is `YYYY-MM-DD`. The
caption MAY open with an explicit `YYYY-MM-DD`; without one the front page SHALL
be published under today's date in Europe/Madrid. A headline that merely starts
with a number SHALL keep its first word.

#### Scenario: caption with and without a date prefix
- **WHEN** the caption is `2026-08-14 Titular` (optionally `-`/`—` separated)
- **THEN** it is published as `2026-08-14` with headline `Titular`
- **WHEN** the caption carries no date **THEN** today in Madrid is used
- **WHEN** the caption is `3 fichajes en un día` **THEN** the headline is intact
- *Verifies:* `test_caption_with_a_date_prefix_wins`,
  `test_caption_without_a_date_publishes_under_today`,
  `test_caption_keeps_a_headline_that_starts_with_a_number`,
  `test_first_portada_of_a_season_creates_the_manifest`

### Requirement: One date holds one front page

Publishing a date that already exists SHALL overwrite the image and **replace**
its manifest entry, never append a second one, and the manifest SHALL stay
ordered newest-first.

#### Scenario: correcting a published front page
- **WHEN** a front page is sent for a date already in the manifest
- **THEN** the entry's headline is replaced, the list holds one entry for that
  date, and the confirmation says "actualizada"
- **WHEN** a new date is published **THEN** it sorts above the older ones
- *Verifies:* `test_same_date_replaces_the_entry_instead_of_appending`,
  `test_new_portada_is_prepended_newest_first`

### Requirement: The manifest is never published stale or clobbered

The manifest SHALL be written with `Cache-Control: public, max-age=60`, read
back over the authenticated JSON API rather than its public URL, and left
untouched when it does not parse as a JSON list.

Motive: a public object defaults to `max-age=3600`, which stacks with the web's
own 600 s TTL — a front page could take over an hour to appear. Reading the
public URL for a read-modify-write can merge onto an edge-cached copy and drop
whatever was published in the last hour; overwriting an unparseable manifest
would drop the whole season.

#### Scenario: cache headers and a corrupt manifest
- **WHEN** the manifest is written **THEN** it carries `max-age=60`, while the
  image keeps the bucket default
- **WHEN** the stored manifest is not valid JSON **THEN** nothing is written
- *Verifies:* `test_manifest_is_written_with_a_short_cache_so_the_web_sees_it`,
  `test_unparseable_manifest_is_not_overwritten`,
  `test_upload_object_posts_bytes_and_returns_public_url`,
  `test_download_object_returns_bytes`

### Requirement: JPEG only, documents preferred

The image SHALL be rejected unless its bytes start with the JPEG magic number,
and a front page sent as a Telegram `photo` SHALL be published with a warning
that Telegram recompressed it.

Motive: the web hardcodes the `.jpg` extension, so any other format would leave
bytes, content type and file name disagreeing. Telegram caps a `photo` at
~1280 px on the long side, which loses the body copy of a newspaper page —
sending it as a document keeps the original bytes.

#### Scenario: PNG, and a recompressed photo
- **WHEN** the bytes are not a JPEG **THEN** nothing is written and the operator
  is told to export it as JPEG
- **WHEN** the attachment arrived as a `photo` **THEN** it publishes with a note
  to resend it as a file
- **WHEN** it arrived as a `document` **THEN** the confirmation carries no note
- *Verifies:* `test_non_jpeg_is_rejected_before_anything_is_written`,
  `test_a_photo_confirmation_warns_about_recompression`,
  `test_a_document_confirmation_carries_no_warning`

### Requirement: The operator's mistakes are instructions, not errors

A missing headline, an impossible date, a non-JPEG image and a file `getFile`
refuses (over 20 MB) SHALL come back `200` with a message the bot relays
verbatim, and SHALL write nothing. Genuine failures — no write access to the
bucket, Telegram unreachable — SHALL surface as an error to the owner chat.

#### Scenario: rejection versus failure
- **WHEN** the caption has no headline, or the date is impossible, or the file
  is too big **THEN** 200 with instructions and no upload
- **WHEN** the bucket refuses the write **THEN** the owner gets an error message
  rather than a confirmation or silence
- *Verifies:* `test_missing_headline_is_reported_without_downloading_anything`,
  `test_impossible_date_is_rejected`,
  `test_file_too_big_is_reported_as_instructions_not_a_failure`,
  `test_write_failure_raises_so_the_bot_reports_an_error`,
  `test_portada_route_answers_200_when_the_front_page_is_rejected`,
  `test_portada_failure_is_reported_instead_of_leaving_the_ack_hanging`

### Requirement: Only the owner chat can publish

An image attachment SHALL be handled only when it arrives in the owner private
chat; one from the draft supergroup SHALL be ignored with no reply. A non-image
document SHALL fall through to the text path.

Motive: every league member can post a photo in the supergroup, and the front
page is the league newspaper's, not theirs.

#### Scenario: chat gating
- **WHEN** a photo arrives from the draft supergroup **THEN** nothing is called
  and nothing is sent
- **WHEN** a document arrives from the owner chat **THEN** it is published, the
  largest size is used for a `photo`
- **WHEN** the document is a CSV **THEN** it is not treated as a front page
- *Verifies:* `test_draft_group_photo_is_ignored`,
  `test_owner_document_publishes_the_portada`,
  `test_owner_photo_sends_the_largest_size`,
  `test_non_image_document_falls_through_to_the_text_path`,
  `test_extract_webhook_media_prefers_the_document`,
  `test_extract_webhook_media_takes_the_largest_photo`,
  `test_extract_webhook_media_ignores_non_image_documents`

### Requirement: The salseo page renders what the manifest holds

`/{season}/salseo` SHALL render a "Portadas" section from the season manifest,
newest first, each card linking the full image. A season with no manifest — or
one briefly unreachable — SHALL render no section rather than an error.

#### Scenario: manifest present and absent
- **WHEN** the manifest lists front pages **THEN** the section renders with the
  image URLs
- **WHEN** it is missing or malformed **THEN** the page renders without it
- *Verifies:* `test_salseo_shows_the_league_front_pages`,
  `test_salseo_survives_a_season_with_no_front_pages`

---

## Parked

- **Non-JPEG front pages.** The web builds every URL as `{fecha}.jpg`. Supporting
  PNG would mean an optional `file` key in the manifest entry, with `{fecha}.jpg`
  as the fallback for the entries already published. Not built: every front page
  so far is a JPEG.
