# Design

## Where things live

Worlds, their manifest (`worlds.json`) and the characters' cut-outs live with
the story, in the author's `web/3d/`, like the pictures; the reader's build
reads them through the series link and validates them as it validates scene
files. Nothing of the story enters this repository.

## The draft is the reference

`experiments/draft3d` already holds the behaviour this change makes
permanent: worlds fitted to their picture, hotspots cast onto the collider,
bounds, cut-out figures, only nearby rooms kept in memory, the build stamp
against stale caches, landscape on phones. Its tools (`generate`, `fit`,
`check`, `cutout`, `view`) and the `scene-3d` skill stay the way worlds are
made. Folding it into the reader is the plan's work; the draft is retired with
the preview Worker.

## Trade-offs the behaviour depends on

- **Fallback, not choice of platform.** 3D needs WebGL2 and memory for one
  world at a time; a device without them gets the 2D reader the site has
  today, not an error. The same switch serves the reader who prefers 2D.
- **Quality by connection.** Each world exists at 500k and 100k splats; the
  connection decides, not the device, because the cost the reader feels is
  the download.
- **No migration of 2D saves.** Few readers have progress; carrying it would
  tie the 3D reader to the 2D storage layout for good. The cost is that a
  reader halfway through starts the chapter again.
- **Publishing gate.** A chapter mixing worlds and flat pictures reads as
  unfinished; it waits until every scene has a world (the author can still
  preview it as a draft).
