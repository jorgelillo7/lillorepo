# my_photos — plan

> **State:** plan only, no code. The [open questions](#open-questions) are
> settled by the first trial session, before anything is automated further.

## The problem

Years of photos handled by hand, and a move from a shared Google Photos
library to a shared iCloud library that never settled. In the last year not a
single album was made.

The family's format is an album per event, named `YYYY-MM-DD event`. That
format stays, in Apple Photos, where the family already looks at photos. What
has to go is the work of deciding what an event is, naming it and weeding out
the junk — the part nobody sits down to do.

## Decisions

- **Apple Photos stays the place where photos live and are looked at.** A
  separate Google account owning the organised library was considered and
  rejected: nobody wants to switch accounts to see their own albums.
- **No cloud pipeline.** Apple has no web API for Photos. Albums can only be
  created by code on a Mac (AppleScript, PhotoKit,
  [osxphotos](https://github.com/RhetTbull/osxphotos)). Reading iCloud from
  GCP would need `icloudpd`, which is looking for a maintainer, gets
  datacenter IPs blocked, and still could not create a single album.
- **The agent is Claude Code on the Mac, driving the `osxphotos` CLI.** No
  LangGraph and no third-party MCP server: `osxphotos` is maintained (v0.78.1,
  November 2026), reads the library directly and can add photos to albums.
  The procedure lives in a skill in this package.
- **No paid product does this.** Google's automatic trips, Apple's Trips,
  Mylio and Ask Photos (not in the EU) all group on their own terms and names.

## What there is

| Item | Notes |
|---|---|
| Two iPhones | One per spouse, iCloud Photos with a Shared Library |
| Mac M1 | Often off, little free disk; the agent needs it only during a session |
| Old disk (10+ years) | The history since 2014, already in `YYYY-MM-DD event` folders. Treat it as about to die: **copy, never move** |
| 5 TB disk | Not empty; it has to be emptied before use |
| iCloud+ | 200 GB today, ~27 GB used; moves to **2 TB** |
| Google One AI Pro, 5 TB family plan | Kept anyway for Gemini and YouTube; becomes the background second copy |
| Amazon Prime | Kept anyway; Amazon Photos is an optional extra copy of photos |

## The design

### Set up once

| What | Why |
|---|---|
| iCloud+ **2 TB** (9.99 €/month, [prices](https://www.applesfera.com/servicios-apple/nuevos-planes-icloud-asi-quedan-sus-precios-nuevos-almacenamientos)) | Room for decades: nothing is trimmed or moved off iCloud |
| Shared Library on both iPhones, Camera set to share automatically | Most photos become both spouses' without anyone acting — see the limit below |
| Google Photos app backup on both phones, original quality | A second copy that runs by itself; not used for browsing |
| WhatsApp auto-save only on family chats; Telegram only from private contacts | Keeps memes out of the camera roll |
| Copy the old disk onto the 5 TB one | The history stops depending on a dying disk |
| Import the old disk into Photos | `osxphotos import <dir> --walk --album "{filepath.parent.name}"` turns each `YYYY-MM-DD event` folder into an album |

### Day to day

Nothing changes: take photos, iCloud syncs them, Google backs them up in the
background, both look at them in Photos.

### Every few months: the session

On the Mac, in Claude Code: *"organise July to September"*. The agent:

1. Reads that period from the Photos library with `osxphotos query` — no
   download, thumbnails are already local.
2. Groups photos by time gaps and place.
3. Looks at a few thumbnails per group and proposes `YYYY-MM-DD event`.
4. Flags what adds nothing: screenshots, blurred shots, burst duplicates,
   messaging junk.
5. Shows the proposal; the owner confirms or corrects in the chat.
6. Creates the albums (`osxphotos query --uuid … --add-to-album …`) and puts
   the flagged photos in a **"Revisar para borrar"** album. **It never
   deletes.**

Skipping a session loses nothing: the next one says *"organise everything
since June"*.

### What stays manual

- **Sharing each album with the wife.** Shared Albums are out of reach of
  AppleScript, Automator and `osxphotos`
  ([Apple Community](https://discussions.apple.com/thread/250697301)). In
  Photos: open the album, select all, Share › Shared Album › new, same name.
  About 30 seconds per album. Since iOS 27 shared albums keep full-resolution
  originals ([MacRumors](https://macrumors.com/2026/08/20/ios-27-shared-albums-eat-into-icloud-storage)),
  so they are a real archive, not previews.
- **Deleting** what the agent flagged: review "Revisar para borrar", select
  all, delete.

### Archiving old years

iCloud does not have to hold everything forever. The same session checks
the library size (`osxphotos query` sums original sizes, a proxy for iCloud
use) against a threshold, say 80% of the plan, and when it is crossed offers
to archive the oldest years beyond a window (say, keep the last 10):

1. **Export** those years to the 5 TB disk with their albums as folders:
   `osxphotos export /Volumes/<disk> --directory "{created.year}/{album}"
   --update --report <file>`. `--update` makes it incremental, so a
   re-run only adds what is missing.
2. **Verify** the copy: `osxphotos` has no checksum option, so the skill
   compares counts against the library and hashes the exported files against
   the report.
3. **Confirm the second copy**: the same years must be in Google Photos.
4. **Stage the deletion**: put every archived photo in an album
   **"Archivado — borrar"**. Neither `osxphotos` nor AppleScript can delete
   from Photos ([photoscript](https://github.com/RhetTbull/photoscript):
   AppleScript "cannot … delete a photo"), so the last step is the owner's:
   open the album, select all, delete. One action a year at most.

What archiving costs: those years leave Photos on both iPhones. They stay in
Google Photos (searchable, without the albums) and on the disk (with the
albums as folders).

**Shared albums get in the way.** A shared album holds its own copy: deleting
from the library does not remove it from the album, and removing it from the
album leaves the library untouched
([Apple](https://support.apple.com/guide/photos/pht5f6df5f0/mac),
[Apple](https://support.apple.com/en-us/108314)). Classic albums keep only a
2048 px copy; iOS 27 albums are reported to keep the full-resolution one,
stored once for the owner ([iDrop News](https://www.idropnews.com/ios-27/ios-27-icloud-shared-albums-overhaul/266144/),
not Apple). If so, deleting an archived photo **frees no iCloud space while it
is still in an iOS 27 shared album**. Archiving a year then means choosing:
remove its shared albums too (they cannot be scripted, so that is manual and
the events leave the phones), or keep them and accept that they keep their
space. A throwaway ~1 GB video settles it: note iCloud usage, add it to a
new shared album, delete it from the library, empty Recently Deleted, and
see whether usage drops.

With 2 TB the threshold may not be reached for many years; the check costs
nothing and runs every session anyway.

### Copies

| Where | What |
|---|---|
| iCloud | Everything, native |
| Google Photos (each spouse's account) | Everything on each phone, in the background |
| Amazon Photos | Photos, optional |
| 5 TB disk | The history, plus archived years exported with their albums as folders |

## Open questions

Each one is checked in the first trial session or before it.

1. **The Shared Library cannot share everything.** "Sharing from Camera"
   offers Share Automatically (only when another participant is nearby, by
   Bluetooth), Share When At Home, or Share Manually — there is no "always"
   ([Apple](https://support.apple.com/en-us/118229)). The wife's photos taken
   alone and away stay in her personal library, which the agent on the
   owner's Mac cannot see. She adds them to the shared album, or moves them to
   the Shared Library. Check how often that happens in practice.
2. **Shared Album limits.** 5,000 items per album and 100 subscribers; Apple's
   regional pages disagree on whether an owner can share at most 200 albums
   or has no limit ([Apple](https://support.apple.com/en-gb/148868)). At
   ~10 events a year plus the history since 2014, 200 would run out. If the
   cap is real, share only the events the wife wants on her phone, or share
   the history moved into the Shared Library instead of as albums.
3. **Storage.** Shared Albums count against the owner's iCloud since iOS 27,
   including what others add. Measure whether a photo in both the Shared
   Library and a shared album counts twice, and the size of the old disk,
   before assuming 2 TB lasts decades (`scripts/inventory.sh`).
4. **Importing the history on a small Mac disk.** Photos copies imported
   files into the library before uploading them; with little free space the
   import goes in batches, letting "Optimize Mac Storage" free room between
   them. Imports land in the owner's personal library; moving them to the
   Shared Library is one bulk action in Photos.
5. **Google backup coverage.** Confirm that the Google Photos app backs up
   Shared Library items as well as personal ones.
6. **`osxphotos` writes** only to the last-opened library, and macOS asks once
   for permission to control Photos.
7. **Deleting from the Shared Library deletes for both** — "Revisar para
   borrar" and "Archivado — borrar" are reviewed with that in mind.
8. **`--directory "{created.year}/{album}"`** — confirm with `--dry-run
   --verbose` how a photo in several albums, or in none, is exported.

## Later, if wanted

The agent runs only while the Mac is on. A scheduled run on the Mac
(`launchd` starting Claude Code headless) could send its proposal to Telegram
and apply the answer on the next run. It still needs the Mac; nothing in the
cloud can create an Apple Photos album.

## What this package will not do

- Run in the cloud, or read iCloud from outside a Mac.
- Delete photos by itself: Photos cannot be told to by any script.
- Be a viewer or a cloud.
- Self-host Immich or PhotoPrism.

## The order

1. **Copy the old disk onto the 5 TB one** — urgent, no code. Copy, never
   move; verify both trees with checksums.
2. Set up iCloud 2 TB, the Camera sharing setting, Google backup and the
   messaging rules.
3. A trial session together on one month of photos, answering the open
   questions.
4. Write the skill (organise, flag junk, archive old years) and import the
   old disk.
