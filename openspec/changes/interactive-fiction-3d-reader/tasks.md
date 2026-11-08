# Tasks

Outcomes, not a plan (the plan comes from `rpi-plan` against this proposal).

- [ ] Worlds, `worlds.json` and cut-outs read from the author's `web/3d/` (his PR #9) and validated at build
- [ ] The reader shows scenes as worlds by default, 2D as fallback
- [ ] Modo ligero in Ajustes
- [ ] Low-quality worlds on a slow connection or data saving, one notice; only nearby rooms in memory
- [ ] Progress, codes, settings, achievements, discoveries in 3D; switching modes keeps the place
- [ ] A chapter with a scene that has no world is left out of the build
- [ ] Preview first; main URL switches after the author's OK; preview Worker retired; `experiments/draft3d` folded in and removed; `scene-3d` skill and docs updated

Tests, by exact name (`tests/rooms3d.test.ts`):

- [ ] `a device with WebGL2 reads in 3D unless the reader chose the light mode`
- [ ] `a device without WebGL2 reads in 2D`
- [ ] `a world that fails to load falls back to the scene's picture`
- [ ] `the light mode never downloads a world`
- [ ] `a slow connection or data saving gets the light worlds`
- [ ] `only the room on screen and the rooms one choice away are kept`
- [ ] `a chapter with a scene that has no world is left out of the build`
- [ ] `a world naming a missing scene, a missing file or a file over 25 MiB is an error`
