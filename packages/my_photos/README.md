# my_photos — plan

> **State:** plan only, no code. The order below replaces the earlier plan
> (iCloud → `icloudpd` → disk → Amazon Photos, videos to Google Photos through
> `rclone`).

## The problem

Years of photos handled by hand, and a move from a shared Google Photos
library to a shared iCloud library that was never finished. The result is a
backlog nobody wants to sort.

The design rule is laziness: every piece is judged by how many manual steps
and decisions it removes, not by how complete it is. And the order is the one
that **protects first, organises last** — a photo that exists in two places
is safe; a photo in a well-named folder on a single disk is not.

## What there is

| Item | Notes |
|---|---|
| Two iPhones | Shared iCloud Photos library, the day-to-day camera roll |
| Mac M1 | Not on all the time, little free disk: nothing always-on, no local staging of the library |
| Old disk (10+ years) | The history since 2014, already in `YYYY-MM-DD event` folders. Treat it as about to die: **copy, never move** |
| 5 TB disk | Not empty; it has to be emptied and formatted (exFAT + GPT) before use |
| Google One, 5 TB family plan | Paid for anyway (YouTube Premium Lite and Gemini come with it); about 10 GB used |
| iCloud+, 200 GB | About 27 GB used: no upgrade needed |

## The order

### 1. Google Photos backup on both iPhones — no code

Turn on backup in the Google Photos app on each iPhone, at **original
quality**. With 5 TB paid for and 10 GB used, Google Photos becomes a second
cloud for photos **and** videos, with nothing to install on the Mac and
nothing to run.

This one step replaces three pieces of the old plan:

- **Amazon Photos** as the second copy: it never covered videos and only
  uploads from a desktop app watching a folder.
- **`rclone` for videos**: its shared Google Photos client ID is being
  retired during 2026, and since 2025 the API only sees what the app itself
  uploaded.
- **Emptying Google Photos to zero**: the old shared albums can stay; there
  is no space pressure to clear them.

iCloud stays as it is — the camera roll and the viewer on the phones. It is
not purged.

### 2. Copy the old disk onto the 5 TB one — no code

1. Empty the 5 TB disk somewhere else and format it exFAT with a GPT table
   (readable from Windows and the Mac; exFAT has no journal, so always eject
   it cleanly).
2. **Copy, never move**, the old disk onto it.
3. Verify the copy (checksums of both trees, plus a spot-check of a few
   folders) before anything on the old disk is touched.
4. Upload that history to Google Photos too, so the archive also lives in two
   places.

After step 2 nothing is lost if either disk dies: the history is on the 5 TB
disk and in Google Photos, and everything since is in iCloud and Google
Photos.

### 3. The event folders, once or twice a year — a script and a session

Organising is the only part that needs code, and it is the part that matters
least for safety, so it comes last and runs rarely.

- A **script** pulls what is new since the last run onto the 5 TB disk
  (staging on the disk, never on the Mac), removes exact duplicates by hash,
  and groups the photos by gaps in their EXIF date and by place. All of that
  is deterministic and costs no tokens.
- A **Claude Code session** looks at three or four thumbnails per group,
  proposes a `YYYY-MM-DD event` name, and the owner confirms or corrects it.
  The script then moves each group into its folder.

How the script gets the new photos from iCloud is open. `icloudpd` was the
plan, but it is looking for maintainers and its Homebrew formula is
deprecated; the alternative is exporting from Photos on the Mac
(`osxphotos`), which needs the originals downloaded and the Mac has little
room for them. Decide when step 3 starts, against whatever state both tools
are in then.

## What this package will not do

- Run all the time, on a schedule, or on GCP: the work needs the disk plugged
  in, so it is started by hand.
- Be a viewer (Apple Photos and Google Photos are) or a cloud.
- Self-host Immich or PhotoPrism.
- Edit photos.

## Capacity

| Limit | When | What then |
|---|---|---|
| iCloud 200 GB | Years away at ~18 GB a year | Delete the oldest years from iCloud once they are on the disk and in Google Photos, or move to 2 TB |
| 5 TB disk | Dies of age before it fills | Replace every 6–8 years by copying everything onto a new disk; keep the old one as a cold copy |
| Google One 5 TB | Not in sight | If the plan is ever lowered, the disk holds the full archive |

If something must be deleted somewhere: iCloud first, Google next, the disk
never — a disk is replaced, not pruned.
