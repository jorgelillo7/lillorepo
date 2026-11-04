# Capability: scenes

Point-and-click presentation over the same runtime: a passage listed in a
chapter's scene file is shown as an image with clickable areas beside its text,
and the art for those images is kept consistent through a per-series art bible
whose descriptions are quoted from the story.

- **Source:** `packages/interactive_fiction/src/engine/scenes.ts`,
  `packages/interactive_fiction/scripts/art-bible.ts`,
  `packages/interactive_fiction/scripts/prompts.ts`,
  `packages/interactive_fiction/src/app/main.ts`
- **Verified by:** `packages/interactive_fiction/tests/scenes.test.ts`,
  `packages/interactive_fiction/tests/art-bible.test.ts`
- **Procedure:** `packages/interactive_fiction/.claude/skills/scene-art/SKILL.md`

---

### Requirement: Only what the passage offers can be clicked

A hotspot SHALL appear only when some of its targets are links the passage
offers in this render. When the passage offers one of them, tapping the
hotspot follows it; when it offers several at once — the three exits of one
door, the answers given to one character — tapping it SHALL open a menu of
those choices beside it, fitted inside the picture, so every choice tied to
something visible is played from the image and none is left as a button only
because two of them share an object. A hotspot MAY instead name a `view`,
another scene of the file: tapping it SHALL show that picture for the same
passage — with the door when the room changes, the text left as read — and
the passage's choices on what they lead to there, so leaving a room through
its door is played in the corridor beyond. It SHALL appear only when that view
holds a choice the passage offers. Links with no hotspot,
and `(link:)` reveals, SHALL stay available as buttons in the text. Without
this, an area drawn on the image would bypass the story's own conditions. A
link the image shows is not repeated in the text, unless the reader sets
"Opciones: También como botones" in the settings, for whoever prefers not to
search the image.

#### Scenario: a gated link
- **WHEN** a condition removes a link from the passage
- **THEN** the hotspot for it disappears too
- *Verifies:* `scenes.test.ts: only what the passage offers is clickable: a gated link hides its hotspot`,
  `scenes.test.ts: a hotspot whose passage offers one of its targets leads straight there`

#### Scenario: several ways through one object
- **WHEN** the passage offers several of one hotspot's targets
- **THEN** the hotspot carries them all, in its own order, and opens a menu of them
- *Verifies:* `scenes.test.ts: a hotspot whose passage offers several of its targets carries them all, for a menu`

#### Scenario: stepping through to a view
- **WHEN** a hotspot names a view that holds some of the passage's choices
- **THEN** it is shown carrying them, it is hidden when the view holds none, and in the view its own choices sit on its objects
- *Verifies:* `scenes.test.ts: a door to a view appears when that view holds choices the passage offers, and carries them`,
  `scenes.test.ts: a door to a view with nothing the passage offers is not shown`,
  `scenes.test.ts: in the view, its own choices and the way back are shown`

#### Scenario: links without an area
- **WHEN** a passage offers actions no hotspot covers
- **THEN** they remain as buttons
- *Verifies:* `scenes.test.ts: actions without a hotspot stay available as buttons`

### Requirement: Scene files are checked against the story at build

The build SHALL fail when a scene file names a passage that does not exist, a
hotspot targets something that is not a passage, a passage uses an undefined
scene, an image file is missing, a hotspot has no area yet, a hotspot's view
is not a scene of the file, or a hotspot has neither targets nor a view.

#### Scenario: a broken scene file
- **WHEN** any of those is wrong
- **THEN** the build reports each error and stops
- *Verifies:* `scenes.test.ts: unknown passages, unknown targets and missing images are errors`,
  `scenes.test.ts: a clean scene file passes`,
  `scenes.test.ts: a hotspot with no area yet is an error, so a drafted scene cannot ship unplaced`,
  `scenes.test.ts: a view must be a scene of the file, and a hotspot needs a target or a view`

### Requirement: Planned images are generated from the bible, and every call is paid

`npm run art` SHALL send each planned image to the Gemini API with the prompt
composed from the bible: an edit with the image it changes (its full-size
original when there is one), any other image with the bible's style reference,
and each character with its reference image (the author's concept art), so new
rooms match the old ones and characters look as the author drew them. The
result SHALL be saved full size and as a web copy, and registered in the bible
with the exact prompt that made it. Image models have no free tier, so the key
SHALL come only from the environment, never a file; a run SHALL say its
estimated cost first, stop at `--max` calls, and `--dry-run` SHALL show every
request without calling.

#### Scenario: what is sent for an image
- **WHEN** a new image, or an edit, is requested
- **THEN** the new one carries the style reference and its characters' references before the prompt, and the edit carries only the image it changes
- *Verifies:* `art.test.ts: a new image carries the style reference, the references of its characters, then the composed prompt`,
  `art.test.ts: an edit carries only the image it edits, at full size when there is an original`

#### Scenario: a missing reference
- **WHEN** the style reference or a character's reference image is not there
- **THEN** the build reports it
- *Verifies:* `art-bible.test.ts: a style or concept-art reference that is not there is an error`

### Requirement: A chapter's scene file is drafted from the art bible

An image in the art bible MAY list, per chapter, the passages it is the scene
of. `npm run scenes:draft` SHALL then write that chapter's scene file: one
scene per image, on it one hotspot per passage its passages link to in any
state, labelled as the story labels the link, with no area yet — so the art
can arrive and only the rectangles remain. An edit is the same room as the
image it edits unless it names another place, and a room another chapter's
scene file already names keeps that name, so its sound and the door follow.

#### Scenario: drafting a chapter
- **WHEN** a chapter's images list their passages
- **THEN** the draft has their scenes, rooms and unplaced hotspots
- *Verifies:* `scene-draft.test.ts: one scene per image of the chapter, one unplaced hotspot per linked passage, labelled by the story`,
  `scene-draft.test.ts: an edit is the same room as the image it edits, and a planned image gets its future file name`,
  `scene-draft.test.ts: a room already named by another chapter's scene file keeps that name`

### Requirement: Moving between rooms plays the door; views of one room do not

Each scene MAY name its `room`. Moving between scenes of two different rooms
SHALL play a short door transition (skippable, and off when the reader prefers
reduced motion); two views of the same room, or a scene with no room, SHALL
change without it.

### Requirement: Image prompts come from an art bible quoted from the story

A series MAY keep an art bible with one description per character and place,
each backed by sentences quoted verbatim from the story, and a register of
every image with the prompt that made it. Prompts SHALL be composed from it —
style, place, characters, shot; an edit names the image it changes and adds the
new place's description when it becomes another place. The build SHALL fail
when a quote is no longer in its passage (the author changed the text, so the
description needs review), when an image a scene uses is not registered, when
a generated image has no recorded prompt, when an image names an unknown
character, place or base image, or when an image's passage does not exist or is
already the scene of another image.

#### Scenario: composing prompts
- **WHEN** a prompt is composed for a new image or for an edit
- **THEN** it carries the right style, place, characters and shot
- *Verifies:* `art-bible.test.ts: a new image gets the style, its place, its characters and its shot`,
  `art-bible.test.ts: an edit names the image it changes and keeps the room, without restating the place`,
  `art-bible.test.ts: an edit that turns the room into another place carries that place's description`

#### Scenario: the text changed under a description
- **WHEN** a quoted sentence is no longer in its passage
- **THEN** the build asks for the description to be reviewed
- *Verifies:* `art-bible.test.ts: a quote the author has since changed asks for the description to be reviewed`,
  `art-bible.test.ts: a consistent bible passes; quotes match across markup and spacing`

#### Scenario: unregistered or unexplained images
- **WHEN** a scene uses an image the bible does not list, or a generated image has no prompt, or an image names something unknown
- **THEN** the build reports it
- *Verifies:* `art-bible.test.ts: an image used by a scene but missing from the bible, or generated without its prompt, is an error`,
  `art-bible.test.ts: unknown characters, places and edit bases are errors`,
  `art-bible.test.ts: an image's passages must exist, and a passage is the scene of one image only`
