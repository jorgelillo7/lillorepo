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

A hotspot SHALL appear only when one of its targets is a link the passage
offers in this render; the first target offered wins. Links with no hotspot,
and `(link:)` reveals, SHALL stay available as buttons in the text. Without
this, an area drawn on the image would bypass the story's own conditions.

#### Scenario: a gated link
- **WHEN** a condition removes a link from the passage
- **THEN** the hotspot for it disappears too
- *Verifies:* `scenes.test.ts: only what the passage offers is clickable: a gated link hides its hotspot`,
  `scenes.test.ts: the first target that is a current action wins`

#### Scenario: links without an area
- **WHEN** a passage offers actions no hotspot covers
- **THEN** they remain as buttons
- *Verifies:* `scenes.test.ts: actions without a hotspot stay available as buttons`

### Requirement: Scene files are checked against the story at build

The build SHALL fail when a scene file names a passage that does not exist, a
hotspot targets something that is not a passage, a passage uses an undefined
scene, or an image file is missing.

#### Scenario: a broken scene file
- **WHEN** any of those is wrong
- **THEN** the build reports each error and stops
- *Verifies:* `scenes.test.ts: unknown passages, unknown targets and missing images are errors`,
  `scenes.test.ts: a clean scene file passes`

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
a generated image has no recorded prompt, or when an image names an unknown
character, place or base image.

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
  `art-bible.test.ts: unknown characters, places and edit bases are errors`
