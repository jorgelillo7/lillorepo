# Proposal: the 3D rooms become the reader

## Why

Chapters 1 and 2 play fully in 3D in an experiment beside the reader
(`experiments/draft3d`, its own preview Worker): every room a World Labs world
grown from its picture, characters as sharp cut-outs. The owner and the author
prefer it to the 2D reader. But the experiment is not a reader: it keeps no
progress, has no settings or achievements, shows a black screen where 3D
cannot run, and costs a phone ~7.5 MB per room. Two sites showing the same
story drift apart.

## What changes

- The reader gains a 3D mode that is its default: the scene of a passage is
  its room's world when the chapter has one, and the 2D picture only as a
  fallback.
- 2D stays as an automatic fallback (no WebGL2, a world that will not load)
  and as a visible setting, "Modo ligero".
- Progress, end codes, settings, achievements and discoveries work in 3D as
  they do in 2D. Progress saved by today's 2D site need not carry over.
- On a slow connection or with data saving on, rooms load at low quality, with
  one notice.
- A chapter ships only when every one of its scenes has a world.
- Every change reaches the preview URL first; the main URL switches to the 3D
  reader only after the author's OK, and the preview Worker is retired then.

## Not in scope

Native apps; generating worlds at build or on the reader's device (worlds are
made offline with the `scene-3d` skill and live with the story); moving
characters.
