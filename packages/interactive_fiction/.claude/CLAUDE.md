# interactive_fiction — Claude Notes

Skills specific to this package: they assume a Twine/Harlowe story read by this
reader, with its point-and-click scenes. Read `/CLAUDE.md` and
`/.claude/CLAUDE.md` first; the repo-wide rules apply here too.

The stories themselves are **never in git** (the repo is public, the text is
the author's). They live in `stories/<series>/`, gitignored, and every skill
here reads and writes there.

## Skills

| Skill | When |
|---|---|
| [`scene-art`](skills/scene-art/SKILL.md) | A chapter arrives or changes, or a scene needs new art: keep the art bible, compose the prompts, take the generated images in, place the hotspots, check, publish. |
| [`scene-3d`](skills/scene-3d/SKILL.md) | A chapter's rooms should be tried in 3D, or a 3D room looks wrong: a World Labs world per room, the camera fitted so the hotspots land, a new view painted when a picture is wrong for 3D, played through, previewed for the author. |
