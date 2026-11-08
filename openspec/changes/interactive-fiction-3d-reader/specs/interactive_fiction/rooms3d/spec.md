## ADDED Requirements

### Requirement: A passage's scene is its room in 3D, and the picture only where 3D cannot run

Readers and the author found the 3D rooms the better way to read the story,
and two sites showing the same story drift apart. The reader SHALL show a
passage's scene as its room's world — fitted to the scene's picture, its
hotspots cast onto the world, turning only within the world's bounds, its
characters laid in as cut-outs — and SHALL fall back to the scene's 2D
picture, with the same hotspots, when the device has no WebGL2 or the world
fails to load. The fallback SHALL NOT show an error or a black screen.

#### Scenario: a device that can run 3D
- **WHEN** a chapter opens on a device with WebGL2
- **THEN** each scene shows its world, and its hotspots sit on their objects
- *Verifies:* `rooms3d.test.ts: a device with WebGL2 reads in 3D unless the reader chose the light mode`

#### Scenario: a device that cannot
- **WHEN** WebGL2 is missing, or a world fails to download
- **THEN** that scene shows its picture with its hotspots, and the chapter plays on
- *Verifies:* `rooms3d.test.ts: a device without WebGL2 reads in 2D`,
  `rooms3d.test.ts: a world that fails to load falls back to the scene's picture`

### Requirement: The light mode is a setting

Some readers will want the 2D reader on purpose — battery, data, motion. Ajustes
SHALL offer "Modo ligero", which shows every scene as its 2D picture; it SHALL
apply at once and be kept with the other settings.

#### Scenario: the reader turns it on
- **WHEN** Modo ligero is on
- **THEN** no world downloads, and every scene is its picture
- *Verifies:* `rooms3d.test.ts: the light mode never downloads a world`

### Requirement: Rooms cost a phone what its connection can carry

A room is ~7.5 MB at full quality, a chapter 50–90 MB. With a slow connection
or the browser's data saving on, the reader SHALL load each world at its low
quality and say so once per session; it SHALL keep in memory only the room on
screen and the rooms one choice away.

#### Scenario: a slow connection
- **WHEN** the connection reports as slow, or data saving is on
- **THEN** worlds load at low quality, with one notice
- *Verifies:* `rooms3d.test.ts: a slow connection or data saving gets the light worlds`

#### Scenario: a long chapter
- **WHEN** the reader moves through a chapter's rooms
- **THEN** at most the current room and its neighbours are held
- *Verifies:* `rooms3d.test.ts: only the room on screen and the rooms one choice away are kept`

### Requirement: A chapter ships in 3D or not at all

A chapter that mixes worlds and flat pictures reads as unfinished. The build
SHALL leave out of the site a chapter with a scene that has no world, naming
the scenes missing, unless the chapter is a draft.

#### Scenario: a chapter with a room still flat
- **WHEN** a published chapter has a scene without a world
- **THEN** the build leaves the chapter out and names the scenes
- *Verifies:* `rooms3d.test.ts: a chapter with a scene that has no world is left out of the build`

### Requirement: Worlds are checked against the story at build

A world is useless if its scene, picture or cut-out is gone. The build SHALL
fail when `worlds.json` names a scene the series does not have, a file that is
missing, a file over the host's 25 MiB limit, or a cut-out without a rectangle.

#### Scenario: a broken manifest
- **WHEN** any of those is wrong
- **THEN** the build reports each one by scene
- *Verifies:* `rooms3d.test.ts: a world naming a missing scene, a missing file or a file over 25 MiB is an error`

### Requirement: The main site switches only after the author's review

The author reviews the story's look before readers see it. Changes to the 3D
reader SHALL reach the preview URL first; the main URL SHALL serve the 3D
reader only once the author has approved it there, and the preview Worker
SHALL be retired then.

#### Scenario: the switch
- **WHEN** the author approves the preview
- **THEN** the main URL serves the 3D reader and the preview URL is gone
- *Verifies:* checked by hand at the switch, recorded in the PR

## MODIFIED Requirements

### Requirement: The reader keeps progress, and carries the end code

Progress SHALL be saved per chapter in the browser as the state *before* the
current passage rendered, so resuming never re-applies its assignments, in 3D
as in 2D, and switching between them SHALL keep the place. A game saved before
the chapter changed SHALL resume with the variables added since at their
starting value, in every undo step too, rather than failing on the first
passage that reads one. An end code, once earned, SHALL be kept apart from
progress so undo never loses it, and SHALL be written into the next chapter's
code field while that field is empty. A link-less passage before the end code
is set SHALL read as a path not yet written, not as the end of the chapter.
Restart SHALL ask for confirmation inside the page, since embedded viewers
block browser dialogs. A chapter that cannot be loaded SHALL say so instead of
leaving the page blank. Progress saved by the 2D-only site is not carried
over. These rules are pure functions on the progress
(`src/app/progression.ts`), tested without a browser.
