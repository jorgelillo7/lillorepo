# my_photos — plan

> **State:** plan only, no code. Several load-bearing assumptions are still
> unproven; [the tests](#tests-before-any-code) decide whether the design
> holds before anything is written.

## The problem

Years of photos handled by hand, and a move from a shared Google Photos
library to a shared iCloud library that never settled. Some photos end up
shared, others stay in one person's library and get lost, and in the last
year not a single album was made.

The family's own format is an album — and a folder on disk — per event,
named `YYYY-MM-DD event`. That format stays. What has to go is the manual
work behind it: every process that needed someone to sit down regularly has
been abandoned.

**The design rule is "it happens by itself".** A step that needs a person
regularly is presumed to fail. The only recurring human action the design
accepts is answering a proposal in Telegram, which takes seconds and comes to
the person instead of waiting for them.

## What there is

| Item | Notes |
|---|---|
| Two iPhones | One per spouse, iCloud Photos with a Shared Library |
| Mac M1 | Often off, little free disk: the design must not depend on it |
| Old disk (10+ years) | The history since 2014, already in `YYYY-MM-DD event` folders. Treat it as about to die: **copy, never move** |
| 5 TB disk | Not empty; it has to be emptied before use |
| Google One AI Pro, 5 TB family plan | Kept anyway for Gemini and YouTube Premium Lite; about 10 GB used |
| Amazon Prime | Kept anyway for shopping; Amazon Photos stores photos without limit, video up to 5 GB |
| iCloud+, 200 GB | About 27 GB used, growing ~18 GB a year |
| GCP and this monorepo | Cloud Run, Cloud Run Jobs, Secret Manager and Telegram bots already exist here |

No paid product was found that produces `YYYY-MM-DD event` albums by itself:
Google's automatic trips, Apple's Trips collection, Mylio and Ask Photos
(not available in the EU) all group on their own terms and names. Paying
more does not buy this; the plan adds no subscription.

## The design

```
 iPhone (owner) ─┐
                 ├─► iCloud: both personal libraries + Shared Library   layer 1, native
 iPhone (wife) ──┘                 │
                                   ▼
            Cloud Run Job, daily
             · icloudpd pulls what is new from all three libraries
             · dedupes, groups by EXIF time gaps and place
             · Gemini names each group "YYYY-MM-DD event"
             · proposals stored in Firestore
                                   │
                                   ▼
            Telegram bot, monthly digest
             "4 events: 2026-11-08 Lucía's birthday ✅ ✏️ …"
             no answer within a week = accepted
                                   │
                                   ▼
            Google Photos, a dedicated "familia" account      layer 2, organised
             albums "YYYY-MM-DD event" and "YYYY-MM Varios"
             both spouses add the account in the app and browse there
                                   │
                                   ▼
            GCS Archive, folders "YYYY-MM-DD event/"           layer 3, cold copy

 Amazon Photos app on the owner's iPhone                         extra, free
```

### Who does what

| Who | What | How often |
|---|---|---|
| The phones | Take photos | Always |
| The job | Download, group, name, upload, create albums, write the cold copy | Daily, unattended |
| Owner (and wife, if she wants) | ✅ or rename each proposal in Telegram | Monthly, about a minute |
| Each spouse | Hand the iCloud 2FA code to the job | Every ~2 months |

If the job breaks, nothing is lost: iCloud still holds everything, and only
the organising pauses until it is fixed.

### Pieces and decisions

**Sources.** iCloud's Shared Library cannot share everything: "Share
Automatically" only adds photos taken near another participant or at home,
and whatever arrives from outside the camera — screenshots, WhatsApp and
Telegram saves — lands in the personal library
([Apple](https://support.apple.com/HT213248)). So the job reads **both
personal libraries and the Shared Library**, and dedupes by asset id and
hash. That means two Apple IDs and two 2FA renewals; the wife does not use
Telegram, so her renewal channel is still open (one idea: the owner's number
as a trusted number on her account).

**Downloader.** [`icloudpd`](https://github.com/icloud-photos-downloader/icloud_photos_downloader)
is the only route without a Mac; Apple has no continuous export API. Known
weaknesses: it is looking for a maintainer, sessions last about two months,
it decides what is new by looking at its local files and cookies (so both
must persist across Cloud Run executions, e.g. on a GCS-backed volume), its
docs contradict each other on Advanced Data Protection (keep ADP off), and
Apple is reported to block some datacenter ranges. **Fallback** if Cloud Run
is blocked: a small always-on box at home with a residential IP — not the
Mac.

**Naming.** One Gemini Flash call per group with three or four small
thumbnails. Cost is cents a month. Paid-tier data is not used for training,
and in the EEA those terms also cover the free tier
([terms](https://aistudio.google.com/docs/terms)).

**Approval.** A Telegram bot on Cloud Run (webhook, since Telegram drops
undelivered updates after 24 hours). ✅ accepts, ✏️ asks for the right name,
silence for a week accepts. Photos that belong to no event go to a monthly
`YYYY-MM Varios` album. Media is uploaded **only after approval**, so what is
deleted before then never reaches Google.

**Google side.** The Library API, since 31 March 2025, only lets an app
manage media and albums it created, and can no longer share albums
([updates](https://developers.google.com/photos/support/updates)). So the job
is the uploader and a dedicated **"familia" Google account** owns
everything: nothing needs sharing, both spouses simply add that account. The
phones' own Google Photos backup is turned off — it is unreliable in the
background on iOS and would duplicate everything.

- OAuth client created **by the familia account** in
  [Personal mode](https://support.google.com/cloud/answer/15549945): no
  verification and no 7-day token expiry, but it authorises only the account
  that created it, and the choice is irreversible. The Photos docs say every
  app "must pass the OAuth verification review"
  ([auth](https://developers.google.com/photos/overview/authorization)) — the
  two pages contradict each other, so this is test 5.
- Scopes from day one: `photoslibrary.appendonly`,
  `photoslibrary.readonly.appcreateddata` and
  `photoslibrary.edit.appcreateddata` (renaming an album needs the last one).
- The API has no delete. What is deleted in iCloud after upload goes to a
  "Revisar" album for a human to remove.
- Live Photos arrive as two files (HEIC + MOV) and are not documented to
  pair through the API; decide between uploading both and uploading only the
  still. Limits: 200 MB per photo, 20 GB per video, 10,000 requests a day,
  20,000 items per album ([limits](https://developers.google.com/photos/overview/api-limits-quotas)).
- The familia account must join the Google One family group (same country,
  at most one group change per 12 months) and use its 5 TB. Google deletes
  accounts after two years of inactivity and does not list Photos or API use
  as activity ([policy](https://support.google.com/accounts/answer/12418290)):
  set up the Inactive Account Manager, a recovery address and passkeys on
  both phones.

**Cold copy.** The job writes the approved originals to GCS Archive in
`YYYY-MM-DD event/` folders — the historic format — at about 2.5 $/TB a
month. Takeout is no longer needed: it scatters album membership into JSON
sidecars and duplicates files across folders.

**Old disk and backlog.** The old disk's folders are already named, so they
are loaded once, without approval, with `rclone copy <folder>
gphotos:album/<name>` on an OAuth client of the familia account (rclone's
shared client stops working during 2026, [rclone](https://rclone.org/googlephotos/)).
The year without albums is proposed one backlog month a week, or on a page
with every proposal accepted by default and only its link in Telegram, so
the chat is not flooded. Expect duplicates between the old disk and iCloud
re-exports; Google only dedupes identical bytes.

**Messaging apps.** WhatsApp: auto-save off by default, "Always" only on
family chats. Telegram: auto-save only from private contacts (it filters by
category, not by chat).

**Watching it.** A heartbeat alerts in Telegram when there has been no
successful run in 48 hours, when an iCloud session expires in under 7 days,
or when counts do not add up. Gemini model names and prices change (Flash
doubles in 2027, still cents); the model is configuration, not code.

**iCloud capacity.** The Shared Library counts against its creator's
storage, and 200 GB will not hold both libraries for long. Either move to
2 TB, or trim iCloud once photos are archived (`icloudpd
--keep-icloud-recent-days`) — which also removes them from the phones, so it
is an explicit decision, not a default.

## The order

1. **Copy the old disk onto the 5 TB one now** — no code, and the only
   urgent step. Copy, never move; verify both trees with checksums before
   anything on the old disk is touched.
2. **Run the tests below.** They can kill or reshape the design.
3. **Build** the job, the bot and the cold copy, with their spec in
   `openspec/` first.
4. **Load the old disk and the backlog** into the familia account.

## Tests before any code

1. The wife takes a photo alone and away from home: which library does it
   land in?
2. A Cloud Run Job runs `icloudpd --auth-only`, then downloads the Shared
   Library and both personal libraries for seven days in a row, reusing
   cookies, without a lockout.
3. The wife's contributions appear in the Shared Library from the owner's
   account.
4. The 2FA flow for both accounts: the code arrives and reaches icloudpd.
5. OAuth in Personal mode, created by the familia account, with the three
   scopes: the refresh token still works on day 8 and no verification screen
   appears.
6. Upload HEIC, a Live Photo, HEVC, ProRAW and an edited photo; check date,
   time zone, GPS and dedupe in Google Photos.
7. Create an album, rename it and add photos to it later through the API.
8. The familia account draws from the 5 TB family pool.
9. Upload 1 GB from GCP and read the egress on the bill (Photos is not on
   Google's zero-egress list).
10. Load three old-disk folders with rclone.
11. Write to GCS Archive and restore one file.
12. Disable the job and check that the heartbeat fires.

## What this package will not do

- Be a viewer (Google Photos and Apple Photos are) or a cloud.
- Self-host Immich or PhotoPrism.
- Edit photos.
- Depend on the Mac being on.

## Capacity

| Limit | When | What then |
|---|---|---|
| iCloud 200 GB | Sooner than the old ~18 GB/year estimate, since the owner's account holds the Shared Library | Move to 2 TB, or trim archived years explicitly |
| Google One 5 TB | Not in sight | If the plan is ever lowered, GCS Archive holds the full archive |
| GCS Archive | No limit | ~2.5 $/TB a month |
| Old and 5 TB disks | Die of age | The disk is a one-off rescue copy; the cold copy lives in GCS |

If something must be deleted somewhere: iCloud first, Google next, the cold
copy never.
