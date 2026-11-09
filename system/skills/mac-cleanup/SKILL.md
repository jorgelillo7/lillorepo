---
name: mac-cleanup
description: Audit this Mac's disk and recover space safely. Use when the owner asks to review the disk, free space, or find files to delete ("revisa el mac", "recuperar espacio", "limpieza").
---

# Mac disk cleanup

Measure first, report, and delete only what the owner confirms in this round. Earlier
approvals do not carry over.

## Hard rules

- **Photos are never deleted** (Pictures, Photos library, photo folders and their
  Drive zips in Downloads), unless the owner names the exact item.
- **Other Claude sessions may be using things.** Before touching a cache or temp folder,
  check `ps` for processes using it (Docker, Bazel, Gradle, Chrome, emulators). Ask the
  owning session before removing its files, and answer when a session asks what you deleted.
- Never touch `~/.android/debug.keystore`, `~/.android/adbkey`, `~/.android/avd/`,
  `~/Library/Android/sdk/`, any `.jks` or `keystore.properties`, or `~/.config/`.
- Empty the Trash only after listing what is in it and getting a yes.
- Use literal absolute paths in `rm`; no variables that may expand to empty.
- zsh notes: `$path` is PATH (do not use it as a loop variable); globs with no match abort
  the command, so use `find` instead. `ls` output goes through rtk; use `rtk proxy ls`.
- `du -h` prints decimal commas here, so `sort -h` misorders. Use `du -sk` with `sort -rn`.

## Measure

```bash
df -h /System/Volumes/Data | tail -1
cd ~ && du -sk Downloads Desktop Movies Pictures .Trash Library/Caches \
  "Library/Application Support" Library/Containers Library/Android Library/Developer \
  .android .gradle .m2 .npm .cache 2>/dev/null | sort -rn
find "$(getconf DARWIN_USER_TEMP_DIR)" -mindepth 1 -maxdepth 1 -exec du -sk {} + 2>/dev/null | sort -rn | head -20
find ~/Downloads -mindepth 1 -maxdepth 1 -exec du -sk {} + | sort -rn | head -15
```

## Usual suspects (seen before)

| What | Where | Safe? |
|---|---|---|
| Headless Chrome profiles left by test scripts (`fit-*`, `wl-*`, `d3-*`, ~170 MB each) | `$(getconf DARWIN_USER_TEMP_DIR)` | Yes, once no running Chrome uses them (check `ps` for `user-data-dir=`). Orphaned headless Chromes (parent PID 1) also stop the normal Chrome from opening; kill them first |
| Chrome `code_sign_clone` copies | same temp dir | Yes, with Chrome closed |
| Bazel cache | `~/Library/Caches/bazel` | Yes when no build runs; it is rebuilt |
| Docker disk | Docker Desktop data | Only with Docker stopped and the owner's yes |
| Installers (`.dmg`, `.pkg`, `.zip` of apps) | `~/Downloads` | Yes, after listing |
| Gradle and Android | `~/.gradle/caches`, `~/.gradle/wrapper/dists`, `~/.android/cache`, AVD snapshots | Ask the Android session first |
| Steam, emulators, old downloads | various | The owner decides |

## Report

Reply in Spanish with a table: what, size, risk. Give free space before and after.
Separate what is safe from what needs a decision. Point out what keeps growing back
and which project causes it.
