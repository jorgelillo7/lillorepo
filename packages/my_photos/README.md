# my_photos — plan

> **State:** plan only, no code. Several assumptions are still unproven;
> [the tests](#tests-before-any-code) decide whether the design holds before
> anything is written.

## The problem

Years of photos handled by hand, and a move from a shared Google Photos
library to a shared iCloud library that never settled. Some photos end up
shared, others stay in one person's library and get lost, and in the last
year not a single album was made.

The family's own format is an album — and a folder — per event, named
`YYYY-MM-DD event`. That format stays. What has to go is the manual work
behind it: every process that needed someone to sit down regularly has been
abandoned.

**The design rule is "it happens by itself".** A step that needs a person
regularly is presumed to fail. The only recurring human action the design
accepts is answering a proposal in Telegram, which takes seconds and comes to
the person instead of waiting for them.

## What there is

| Item | Notes |
|---|---|
| Two iPhones | One per spouse, iCloud Photos on both |
| Mac M1 | Often off, little free disk: the design must not depend on it |
| Old disk (10+ years) | The history since 2014, already in `YYYY-MM-DD event` folders. Treat it as about to die: **copy, never move** |
| 5 TB disk | Not empty; it has to be emptied before use |
| Google One AI Pro, 5 TB family plan | Kept anyway for Gemini and YouTube Premium Lite; about 10 GB used |
| Amazon Prime | Kept anyway for shopping; Amazon Photos stores photos without limit, video up to 5 GB |
| iCloud+, 200 GB | About 27 GB used |
| GCP and this monorepo | Cloud Run, Cloud Run Jobs, Secret Manager and Telegram bots already exist here |

No paid product was found that produces `YYYY-MM-DD event` albums by itself:
Google's automatic trips, Apple's Trips collection, Mylio and Ask Photos
(not available in the EU) all group on their own terms and names. Paying
more does not buy this; the plan adds no subscription.

## The design

```
 iPhone (owner) ──► iCloud Photos                         layer 1, native backup
 iPhone (wife)  ──►      (untouched; nothing reads it)

 iPhone (owner) ──► Google Photos, owner's account  ─┐   app backup, opened
 iPhone (wife)  ──► Google Photos, wife's account   ─┤   nightly by a Shortcut
                                                     │
                        scheduled Takeout, every 2 months, to each Drive
                        folder shared with the "familia" account
                                                     │
                                                     ▼
            Cloud Run Job
             · reads the new Takeout archives
             · dedupes, groups by time gaps and place
             · Gemini names each group "YYYY-MM-DD event"
                                                     │
                                                     ▼
            Telegram bot: "4 events: 2026-11-08 Lucía's birthday ✅ ✏️ …"
             no answer within a week = accepted
                                                     │
                                                     ▼
            Google Photos, "familia" account                layer 2, organised
             albums "YYYY-MM-DD event" and "YYYY-MM Varios"
             both spouses add the account in the app and browse there
                                                     │
                                                     ▼
            GCS Archive, folders "YYYY-MM-DD event/"         layer 3, cold copy

 Amazon Photos app on the owner's iPhone                     extra, free
```

### How it is used

| Who | What | How often |
|---|---|---|
| Both | Take photos with the iPhone | Always |
| Each iPhone | A Shortcut opens Google Photos while charging; the app backs up the camera roll | Nightly, unattended |
| Both | Browse photos and albums in Google Photos, familia account | Any time |
| The job | Read the Takeout, group, name, ask | Every 2 months, unattended |
| Owner | ✅ or rename each proposal in Telegram | Every 2 months, about a minute |
| The job | Upload to the familia account, create the albums, write the cold copy | After approval |
| Each spouse | Re-enable the scheduled Takeout (it lasts a year); the bot reminds them | Once a year |

Albums lag up to two months behind the photos; for a family archive that does
not matter.

**Nothing is lost if a piece fails.** iCloud keeps every photo natively. If
Google's backup lags or the job breaks, only the organising waits.

### Pieces and decisions

**iCloud stays, untouched.** It is the only backup that runs reliably in the
background on iOS, which is what lets the Google side be imperfect; the
device backup and WhatsApp's chat backup live there too. Amazon Photos is not
a replacement: it is a third-party app with the same background limits as
Google, and stores 5 GB of video. Nothing in the pipeline reads iCloud, so
there is no `icloudpd`, no 2FA renewals and no Shared-Library gaps. The
Shared Library may stay or go; any duplicates it causes are removed by the
job.

**Google backup on the phones.** Each spouse backs up to their own Google
account at original quality. The app backs up everything in the camera roll,
whatever library it belongs to. Google's own help says to keep the app open
and the phone plugged in for best results
([Google](https://support.google.com/photos/answer/6193313?hl=en&co=GENIE.Platform%3DiOS)),
so a personal automation in Shortcuts opens the app nightly while charging,
set to run without asking.

**Getting the files.** The Library API, since 31 March 2025, only lets an app
read media it uploaded itself
([updates](https://developers.google.com/photos/support/updates)), so the
job cannot read what the phones backed up. The bridge is
[Takeout](https://support.google.com/accounts/answer/3024190): a scheduled
export every two months for a year, incremental for Photos since June 2026
when Photos is the only product
([9to5Google](https://9to5google.com/2026/06/01/google-photos-schedule-export/)),
delivered to each spouse's Drive and shared with the familia account. Takeout
puts dates, places and album membership in JSON sidecars; the job reads them
instead of trusting EXIF. Processed archives are deleted to keep the quota
clean.

**Naming.** One Gemini Flash call per group with three or four small
thumbnails. Cost is cents a month. Paid-tier data is not used for training,
and in the EEA those terms also cover the free tier
([terms](https://aistudio.google.com/docs/terms)).

**Approval.** A Telegram bot on Cloud Run (webhook, since Telegram drops
undelivered updates after 24 hours). ✅ accepts, ✏️ asks for the right name,
silence for a week accepts. Photos that belong to no event go to a monthly
`YYYY-MM Varios` album.

**The familia account.** The API can no longer share albums, so a dedicated
Google account owns the organised library and both spouses add it in the
app: nothing needs sharing.

- OAuth client created **by the familia account** in
  [Personal mode](https://support.google.com/cloud/answer/15549945): no
  verification and no 7-day token expiry, but it authorises only the account
  that created it, and the choice is irreversible. The Photos docs say every
  app "must pass the OAuth verification review"
  ([auth](https://developers.google.com/photos/overview/authorization)) — the
  two pages contradict each other, so this is a test.
- Scopes: `photoslibrary.appendonly`,
  `photoslibrary.readonly.appcreateddata`,
  `photoslibrary.edit.appcreateddata` (renaming an album needs it), and
  Drive access to the shared Takeout folders.
- The API has no delete: a photo removed from a phone after it was uploaded
  stays in the familia account until someone removes it there.
- Live Photos arrive as two files (HEIC + MOV) and are not documented to pair
  through the API; decide between uploading both and only the still. Limits:
  200 MB per photo, 20 GB per video, 10,000 requests a day, 20,000 items per
  album ([limits](https://developers.google.com/photos/overview/api-limits-quotas)).
- It must join the Google One family group (same country, at most one group
  change per 12 months) and draw from the 5 TB. Google deletes accounts after
  two years of inactivity and does not list Photos or API use as activity
  ([policy](https://support.google.com/accounts/answer/12418290)): set up the
  Inactive Account Manager, a recovery address and passkeys on both phones.

**Cold copy.** The job writes the approved originals to GCS Archive in
`YYYY-MM-DD event/` folders — the historic format — at about 2.5 $/TB a
month.

**Old disk and backlog.** The old disk's folders are already named, so they
are loaded once, without approval, with `rclone copy <folder>
gphotos:album/<name>` on an OAuth client of the familia account (rclone's
shared client stops working during 2026, [rclone](https://rclone.org/googlephotos/)).
The first Takeout carries everything already in Google; its proposals go out
one month a week, or on a page with every proposal accepted by default and
only its link in Telegram, so the chat is not flooded. Expect duplicates
between the old disk and later exports; Google only dedupes identical bytes,
so the job dedupes by hash first.

**Messaging apps.** WhatsApp: auto-save off by default, "Always" only on
family chats. Telegram: auto-save only from private contacts (it filters by
category, not by chat). Whatever is saved reaches the camera roll and is
backed up like any photo.

**Watching it.** The bot alerts when a Takeout is overdue, when a scheduled
export is about to expire, when a run fails, or when counts do not add up.
The Gemini model is configuration, not code.

## The order

1. **Copy the old disk onto the 5 TB one now** — no code, and the only
   urgent step. Copy, never move; verify both trees with checksums before
   anything on the old disk is touched.
2. **Turn on Google Photos backup and the nightly Shortcut** on both phones,
   and the messaging-app rules. No code, and it already gives a second copy.
3. **Run the tests below.** They can kill or reshape the design.
4. **Build** the job, the bot and the cold copy, with their spec in
   `openspec/` first.
5. **Load the old disk and the backlog** into the familia account.

## Tests before any code

1. The Shortcut opens Google Photos nightly on both phones and the backup
   completes without anyone opening the app.
2. A scheduled Takeout (Photos only) is delivered to Drive without
   intervention, and the next one is incremental.
3. The familia account reads a Takeout folder shared from another account,
   through its Personal-mode client, and the token still works on day 8 with
   no verification screen.
4. Takeout keeps originals, dates, time zones and GPS (in the files or the
   sidecars) for HEIC, a Live Photo, HEVC and an edited photo.
5. Upload those files to the familia account; create an album, rename it and
   add photos to it later through the API.
6. The familia account draws from the 5 TB family pool.
7. Upload 1 GB from GCP and read the egress on the bill (Photos is not on
   Google's zero-egress list).
8. Load three old-disk folders with rclone.
9. Write to GCS Archive and restore one file.
10. Disable the job and check that the alert fires.

## What this package will not do

- Be a viewer (Google Photos is) or a cloud.
- Read iCloud.
- Self-host Immich or PhotoPrism.
- Edit photos.
- Depend on the Mac being on.

## Capacity

| Limit | When | What then |
|---|---|---|
| iCloud 200 GB | Years away | Move to 2 TB, or trim archived years explicitly — trimming also removes them from the phones |
| Google One 5 TB | Not in sight; personal backups and the familia account both draw from it | If the plan is ever lowered, GCS Archive holds the organised archive |
| GCS Archive | No limit | ~2.5 $/TB a month |
| Old and 5 TB disks | Die of age | The disk is a one-off rescue copy; the cold copy lives in GCS |

If something must be deleted somewhere: iCloud first, Google next, the cold
copy never.
