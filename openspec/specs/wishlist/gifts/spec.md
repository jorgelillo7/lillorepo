# Capability: gifts

The list itself lives in D1, and the owner adds, edits, hides and deletes gifts, with a
photo from the phone, on `/admin`. A photo never keeps where it was taken.

- **Source:** `packages/wishlist/src/gifts.ts`, `packages/wishlist/src/jpeg.ts`,
  `packages/wishlist/src/app.ts`, `packages/wishlist/web/admin.js`,
  `packages/wishlist/migrations/`
- **Verified by:** `packages/wishlist/tests/*.test.ts` (Vitest; the Worker runs against
  Node's SQLite with every real migration). The page script, and the canvas resize in
  it, run in a browser and are not covered by the tests.

---

### Requirement: The public list is read from D1

`/api/list` SHALL return the current event's title, recipients and visible gifts in
order, each with the path of its photo. The first list SHALL be imported once with the
ids and static photo paths it had, so existing claims keep pointing at the same gifts.
Each gift SHALL belong to an event, and only the event marked current is shown.

#### Scenario: the imported list
- **WHEN** the migrations have run
- **THEN** the list has the title, recipients, gift ids and photo paths of `gifts.json`, in order, and no hidden flag
- *Verifies:* `gifts.test.ts: the first list is imported with its ids, recipients and static photos`

#### Scenario: claims survive
- **WHEN** a claim exists on an imported gift
- **THEN** `/admin` shows it with its name
- *Verifies:* `gifts.test.ts: existing claims survive the move to D1 and still show for the same ids`

### Requirement: The owner adds a gift from the phone

A photo SHALL be uploaded first, as the raw `image/jpeg` body of `/admin/api/photo`,
and then named by the add request. A gift SHALL need a title, a photo uploaded and not
yet used, and a recipient of the event or none. Its id SHALL be made from the title
and kept unique. Text SHALL be collapsed and cut to its limit. An upload no gift took
SHALL be discarded after a day.

#### Scenario: adding
- **WHEN** a gift is added with a title, recipient, detail, note and uploaded photo
- **THEN** it takes the last place on the public list with those fields, and a second gift with the same title gets a different id
- *Verifies:* `gifts.test.ts: a new gift gets an id from its title, the last place, and shows on the public list`

#### Scenario: refusing
- **WHEN** the title is empty, the recipient unknown, or the photo missing, static or already in use
- **THEN** the request gets 400 and no gift is added
- *Verifies:* `gifts.test.ts: a gift needs a title, a known recipient and an uploaded photo nobody else uses`

#### Scenario: forgotten uploads
- **WHEN** an upload is more than a day old and no gift uses it, and another photo is uploaded
- **THEN** the old one is gone and photos in use are kept
- *Verifies:* `gifts.test.ts: an upload no gift took is discarded on the next upload after a day`

### Requirement: Photos carry nothing but the image

The admin page SHALL redraw a chosen photo through a canvas, at most 1280 px on its long
edge, before uploading it. The Worker SHALL independently rebuild every upload as a
single-scan baseline JPEG: keep only the tables, the frame, a colour profile and the
scan, cut everything after the end-of-image marker, and refuse a file that is not a
baseline JPEG, is wider or taller than 1600 px, would display turned by an EXIF
orientation that stripping drops, is truncated, or is larger than 600 KB. A photo
SHALL be served from `/photos/u/<id>.jpg` with an immutable cache, under an id that
changes whenever the photo does.

#### Scenario: no metadata is stored
- **WHEN** a JPEG with EXIF and GPS, a multi-picture block, IPTC, a comment and a second EXIF-carrying picture appended after its end is uploaded
- **THEN** the stored bytes contain none of them, hold the image segments only and end at the first end-of-image marker
- *Verifies:* `gifts.test.ts: the stored bytes carry no EXIF, GPS, IPTC, comment or appended second picture`

#### Scenario: refused files
- **WHEN** the upload is not a JPEG, is progressive, too wide, turned by EXIF, over the cap, labelled as another type or truncated
- **THEN** it gets 400, 413 or 415 and nothing is stored
- *Verifies:* `gifts.test.ts: what is not a clean baseline JPEG, or is too big, is refused and nothing is stored`

#### Scenario: serving
- **WHEN** an uploaded photo is requested
- **THEN** it is served as `image/jpeg` with `Cache-Control: public, max-age=31536000, immutable`
- *Verifies:* `gifts.test.ts: an uploaded photo is served from D1 with an immutable cache and nothing but the image`

### Requirement: Gifts can be edited, hidden and deleted

Editing SHALL change a gift's text, recipient and photo, and drop its old uploaded
photo. A hidden gift SHALL leave the public list and the public state, SHALL NOT be
reservable, and SHALL keep its claim for `/admin`. Deleting SHALL remove the gift, its
claim and its uploaded photo together, and a gift with a claim SHALL be deleted only
when the request says `force`, so a page that has not asked cannot delete it.

#### Scenario: editing
- **WHEN** a gift's text and photo are edited
- **THEN** the public list shows the change and the previous uploaded photo is gone
- *Verifies:* `gifts.test.ts: a gift's text and photo can change; the old uploaded photo goes`

#### Scenario: hiding
- **WHEN** a reserved gift is hidden
- **THEN** it leaves the public list and state, cannot be reserved, still shows in `/admin`, and comes back when shown again
- *Verifies:* `gifts.test.ts: a hidden gift leaves the public list and cannot be reserved, but keeps its claim`

#### Scenario: deleting
- **WHEN** a free gift is deleted, and when a claimed one is deleted without and then with `force`
- **THEN** the free one goes with its photo, the claimed one gets 409 and stays until forced, and then claim and photo go too
- *Verifies:* `gifts.test.ts: deleting removes the gift and its uploaded photo; a claimed gift needs force`
