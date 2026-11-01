# Capability: game

The game layer a series adds over its chapters without touching the story:
sound, documents, the condition and inventory read from the story's own
variables, text pacing, settings, the title screen, and what a reader has
discovered. Its configuration lives in the series folder (`game.json`, out of
git) and is validated at build like the scenes.

- **Source:** `packages/interactive_fiction/src/engine/game.ts`,
  `packages/interactive_fiction/src/app/` (`audio`, `settings`, `reader`)
- **Verified by:** `packages/interactive_fiction/tests/game.test.ts`

---

### Requirement: The game config is checked against the story at build

The build SHALL fail when the config names a passage that does not exist, a
condition or inventory variable no chapter sets, an ambience the reader cannot
play, a title image that is missing, or an item description whose quote is no
longer in the text. Descriptions shown to the reader SHALL be sentences quoted
from the story, never invented prose.

#### Scenario: a broken config
- **WHEN** any of those is wrong
- **THEN** the build reports each one
- *Verifies:* `game.test.ts: missing passages, unset variables, unknown sounds, changed quotes and missing art are errors`,
  `game.test.ts: a consistent config passes`

### Requirement: Sound is synthesized, follows the room, and waits for the reader

Ambience SHALL come from the scene's room, else the passage's tags, else the
series default, and SHALL crossfade when it changes. Doors, steps, scare
stings and a heartbeat are synthesized with the Web Audio API — no audio files.
Nothing SHALL sound before the reader's first tap or key (browsers forbid it);
a sting SHALL play only on arriving at a passage the config names, never on
undo or resume; the toolbar mutes, and the choice is remembered; audio is
suspended while the page is hidden.

#### Scenario: picking the ambience and the stings
- **WHEN** a passage is shown
- **THEN** its ambience is the room's, the tags', or the default, and a sting fires only where configured
- *Verifies:* `game.test.ts: ambience comes from the room, then the passage's tags, then the default`,
  `game.test.ts: stings and documents fire only on the passages configured for them`

### Requirement: Condition and inventory are the author's own

The condition SHALL be read from the story variable the config names and
shown with the author's own word for each value; an unknown value shows none.
The inventory SHALL be the story's own array of item names, absent in chapters
that do not track one.

#### Scenario: reading them from the story
- **WHEN** the variables hold a value
- **THEN** the condition label and the item list come from them unchanged
- *Verifies:* `game.test.ts: the condition is the author's own state for the variable's value`,
  `game.test.ts: the inventory is read from the story's array, and absent when the chapter has none`

### Requirement: Text is read paragraph by paragraph, and nothing is ever hidden for good

On arrival at a passage its text SHALL appear one paragraph at a time: split
at line breaks among the passage's top-level nodes, short lines joined to the
next (about 300 characters at least), and never inside an element, so the
author's own HTML appears whole. A tap on the text, Space or Enter shows the
next paragraph; "Mostrar todo" shows the rest. Hotspots and the end panel
SHALL wait until the text is read. A passage reached by undo or resume, or any
passage when the reader chose "all at once", SHALL appear whole. Every node is
moved, in order, never dropped: the revealed text was checked word for word
against the engine's output, which matches Harlowe's.

#### Scenario: splitting without losing anything
- **WHEN** a passage is split into paragraphs
- **THEN** its text and markup are unchanged once revealed, and an element is never cut
- *Verifies:* `pacing.test.ts: paragraphs split at line breaks, short lines are joined, and nothing is lost, in order`,
  `pacing.test.ts: an element is never split, even with blank lines inside it`

#### Scenario: reading
- **WHEN** the reader advances
- **THEN** one paragraph appears at a time, and the passage is done exactly once at the end; an instant reveal is done at once
- *Verifies:* `pacing.test.ts: reading reveals one paragraph at a time and calls back once at the end`,
  `pacing.test.ts: an instant reveal, or a single paragraph, is done straight away`
