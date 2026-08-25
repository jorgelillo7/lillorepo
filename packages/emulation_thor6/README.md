# Emulation Collection — AYN Thor 6

> ## No copyrighted files are stored here
>
> This directory holds **notes, a folder layout and checklists**. It contains
> **no ROMs, no disc images, no BIOS dumps, no encryption keys and no
> copyrighted game data of any kind**. It links to none, it does not say where
> to obtain any, and it never will. Requests to add them will not be met.
>
> **You can check this rather than take our word for it.** Everything tracked
> here is Markdown, a shell script, a Python script and empty `.gitkeep`
> files:
>
> ```bash
> git ls-files packages/emulation_thor6/
> ```
>
> The directories under `SD_TEMPLATE/`, `BIOS/` and `ROMs/` exist to **describe
> a shape** — where a file would go on your own SD card. They are empty and
> gitignored, and `.gitkeep` is the only thing ever committed inside them.
>
> What this is for: organising a collection you already own. Every checklist
> assumes **dumps you made yourself from media you own**, which is the only use
> supported here. Where a note mentions a translation patch or a ROM hack, it
> means a patch applied to your own dump; the patch is not distributed here
> either.
>
> The tooling follows the same rule. `scripts/sdcard.sh` copies files you
> supply onto a card. It downloads nothing, and it will not help you find
> anything.

Setup notes and per-system checklists for one handheld. It lives here rather
than in `docs/` because it is not only prose: `SD_TEMPLATE/` is a folder tree
meant to be copied onto a card, and a directory layout is an awkward thing to
keep in a documentation folder. `my_photos` set the precedent — a personal
project with no deployable code, tracked in the repo because that is where
things get found again.

Nothing here builds, deploys or runs in CI.

A `NOTES.local.md` beside this file is the private half — links, versions, a
build log — and is gitignored, because this repository is public and that one
is a notebook. It is not required; nothing here depends on it.

## What the script does, and what it does not

The script prepares **the card**. It does not touch the console, and the
console is the larger half of the job. Worth being blunt about, because
"the card is ready" reads a lot like "I can play now" and it is not.

| | Where | Who |
|---|---|---|
| Format the card, build the folder tree | Mac | `sdcard.sh` |
| Copy your BIOS and games across | Mac | `sdcard.sh` |
| Report what is on the card | Mac | `sdcard.sh` |
| **Install each emulator** | Thor 6 | you, once per emulator |
| **Point each one at its folder on the card** | Thor 6 | you, once per emulator |
| **Load the BIOS into the emulators that need one** | Thor 6 | you |
| **Assign the controller to port 1** | Thor 6 | you, once per emulator |
| **Apply the renderer settings** | Thor 6 | you, for DS / 3DS / PS2 |

So the answer to "the card is full, am I done?" is no. Each emulator is an
ordinary Android app with its own settings screen, and nothing on the card
configures them — the files being in the right place is a precondition for
that work, not a replacement for it.

`./scripts/sdcard.sh status` is the checkpoint between the two halves: run it
before you pick the console up, and again whenever something will not load,
because "the file is not where the emulator is looking" and "the emulator is
misconfigured" look identical from the couch.

Per-system settings live in [`docs/`](docs/) — each document names its
emulator, where its files go, whether it needs a BIOS, and the settings worth
changing from the defaults.

## The script

`scripts/sdcard.sh` does the card work. It moves files **you** supply — it
downloads nothing, and it will not help you find anything.

```bash
./scripts/sdcard.sh            # check the card and report what is on it
./scripts/sdcard.sh prepare    # create the folder tree on the card
./scripts/sdcard.sh sync       # copy BIOS/ and ROMs/ onto the card
./scripts/sdcard.sh format     # reformat to exFAT (erases, asks first)
```

The bare command is read-only; everything that writes is a named subcommand.
Put your dumps in `BIOS/` and `ROMs/<system>/` beside this file — both are
gitignored — and `sync` places them by the layout below.

Three things it refuses to do:

- **Touch anything that is not removable media.** The check runs against the
  *whole disk* the volume sits on, not the mounted slice, because those are
  different objects and only one of them gets erased. Pointing `SD_VOLUME` at
  your boot disk is refused too.
- **Erase without the disk identifier typed in.** Not the volume label: cards
  ship labelled `UNTITLED`, so a label is neither unique nor deliberate.
- **Copy while git is tracking your dumps.** It asks the index directly rather
  than trusting `.gitignore` — a rule written on one branch is not in effect
  on another, which is how a private file reached this public repository once.

`scripts/inventory.py` is the reporting half, and is what `status` calls. It
tells you what is on the card, and is careful about how it says it: **BIOS
files are reported as present or absent**, because their names are fixed and
the two PlayStation images are told apart by size. **Games are not.** A dump
can be named anything, so a title it does not recognise is listed as *not
obviously present* — never as missing. Sending you hunting for a game you
already own, filed under a name the script failed to parse, would be worse
than saying nothing.

## How to use `SD_TEMPLATE/`

The tree mirrors what the card should look like. Copy the structure — not the
`.gitkeep` files — to the root of the SD card, then fill it in from your own
dumps:

```
SD_TEMPLATE/
├── BIOS/                 # PS1, PS2, Dreamcast, Neo Geo
├── JoiPlay_Games/        # one folder per fangame
└── ROMs/
    ├── 3ds/
    ├── arcade/           # keep sets zipped and named as they are
    ├── dreamcast/
    ├── gamecube/
    ├── gba/
    ├── nds/
    ├── ps2/
    ├── psp/
    ├── psx/
    ├── sega_megadrive/   # Master System and Mega Drive together
    └── wii/
```

On the device:

```bash
# from the repo, with the card mounted
rsync -av --exclude='.gitkeep' SD_TEMPLATE/ /Volumes/<CARD>/
```

Two things that are easy to get wrong:

- **One BIOS folder, not one per system.** Most emulators here take a path to
  a shared directory, so `BIOS/` is flat and each emulator is pointed at it.
- **Arcade sets stay zipped.** FBNeo reads the archive; unpacking or renaming
  one is the most common reason a game that should work does not.

## The device

Per the setup write-up this guide draws on (linked at the bottom):

| | |
|---|---|
| SoC | Snapdragon 8 Gen 5 |
| OS | Android 13, clean install |
| Storage | microSD expansion supported |
| Screen | dual AMOLED touchscreen |

Two things follow from it being an Android handheld rather than a dedicated
retro box:

- **Emulators are ordinary apps.** Each is installed and configured on its own;
  there is no single settings screen covering all of them, which is why every
  document below repeats where its files go.
- **Controller mapping is per emulator.** Each one needs its pad assigned to
  port 1 explicitly — RetroArch through "assign all controls", the standalone
  emulators through their own equivalent. Worth binding a menu key and an exit
  key while you are in there; without them you are reaching for the touchscreen
  mid-game.

**GPU drivers** are only worth touching for the heaviest systems. The write-up
installs an Adreno driver through a GPU driver browser app and lets it pick the
recommended build, falling back to choosing manually if the download fails.
Nothing on the checklists below needs this — it matters for Switch emulation,
which is outside this collection.

## Systems

| System | Emulator | Titles |
|---|---|---|
| [Sega Master System / Mega Drive](docs/sega.md) | RetroArch — Genesis Plus GX | 17 |
| [Game Boy Advance](docs/gba.md) | Pizza Boy GBA Pro / RetroArch | 17 |
| [PlayStation 1](docs/psx.md) | DuckStation | 37 |
| [Nintendo DS](docs/nds.md) | melonDS Nightly | 19 |
| [Nintendo 3DS](docs/3ds.md) | Azahar | 5 |
| [PlayStation Portable](docs/psp.md) | PPSSPP Gold | 3 |
| [Dreamcast](docs/dreamcast.md) | Flycast | 1 |
| [GameCube and Wii](docs/gamecube-wii.md) | Dolphin | 4 |
| [PlayStation 2](docs/ps2.md) | NetherSX2 Turnip (+2 alternates) | 16 |
| [Arcade](docs/arcade.md) | RetroArch — FBNeo | 12 |
| [JoiPlay — PC fangames](docs/joiplay.md) | JoiPlay + RPG Maker plugin | 11 |

142 titles. Each document lists its emulator, where its files go, whether it
needs a BIOS, and a checklist to tick off as you go.

## Order worth doing it in

The systems are not equally fussy, and starting with the hardest is how people
give up. Roughly easiest to hardest:

1. **Sega, GBA, arcade** — no BIOS to source (bar Neo Geo), and RetroArch
   handles all three, so one emulator gets you three systems working.
2. **PSX, PSP, DS** — DuckStation and PPSSPP are close to configure-free once
   the PS1 BIOS is in place.
3. **Dreamcast, PS2** — BIOS required, and the PS2 titles are where per-game
   settings start to matter.
4. **GameCube/Wii, 3DS** — the most demanding on the hardware and the most
   likely to need tuning per title rather than once globally.

## What this hardware handles

Everything on these checklists is within it. The write-up puts DS and 3DS at
60-120 FPS and PS2 at a comfortable 30, and reports the device handling
PS2-and-below without trouble. Switch emulation is where it starts to strain —
30 FPS on lighter titles, and only with upscaling help — which is one reason
no Switch list appears here.

So the tuning advice in these documents is about the top of the range, not the
whole of it: the Sega, GBA and arcade sections need no performance settings at
all, and saying so is more useful than inventing some.

## Save states are not saves

Its own heading because it is repeated, independently, for **PS2,
GameCube/Wii, PSP and 3DS**: do not rely on save states there. Use the in-game
save. They have held up on DS and on the RetroArch systems, which makes those
the exception rather than the rule.

The related trap, on PS2: **memory cards are not shared between emulators.**
Switching build mid-game leaves your saves behind in the old one.

## A launcher, once it gets big

Eleven systems and 142 titles is past the point where launching each emulator
by hand stays pleasant. A front-end that scans one ROMs folder, sorts by
platform and shows box art is the usual answer.

**ES-DE** is what this guide's second source settles on, for a specific
reason: it can assign a **different emulator per game**, which is exactly what
PS2 needs. It also gives favourites, collections, and hiding duplicate entries
like a Disc 2 image. Two real costs: scraping art and metadata for a large
library takes a while — set the device up a few games at a time — and pointing
it at a card, or at newer emulators, means hand-editing its custom XML files.

It is also optional. Every emulator here except RetroArch has a decent menu of
its own, and preferring a device that feels like a small computer rather than
a small console is a legitimate taste.

Either way, do it **after** the systems work individually: a launcher that
fails to start a game tells you nothing about whether the emulator or the
launcher is at fault.

## When something will not run

In order, cheapest first:

1. **Lower the internal resolution.** The single most effective change.
2. **Switch renderer** — Vulkan ↔ OpenGL.
3. **Try another emulator or core.** On PS2 that is routine rather than a last
   resort; on the RetroArch systems it is a few taps.
4. **Check the emulator's wiki**, then search the game by name. Most per-game
   quirks are known and have a one-setting fix.
5. **Check the file layout.** Depending on the front-end, files may need a
   specific structure — in ES-DE a PS1 or Dreamcast game wants its files in a
   folder named after the disc 1 `.cue`. `./scripts/sdcard.sh status` tells you
   what is where, which separates a path problem from a settings problem before
   you spend an evening on the wrong one.

Per-system troubleshooting lives in each document under [`docs/`](docs/).

## RetroAchievements

Every emulator recommended here supports it. It is opt-in and free, and it is
the main reason RetroArch is preferred for the 2D systems over standalone
emulators that are better in isolation but lack the support — N64 being the
clearest example.

---

## Sources

Two, and they disagree in places — where they do, the per-system documents
follow the second, which is hands-on across more of these systems.

1. [Cómo instalar emuladores en la AYN
   Thor](https://www.profesionalreview.com/2026/08/16/como-instalar-emuladores-ayn-thor/)
   (Profesional Review, August 2026) — the walkthrough with screenshots.
2. A community write-up on r/AynThor recommending emulators per system, with
   the settings, the per-game caveats and the troubleshooting order above.

**A caveat on the second, worth keeping in mind:** its author is running a
**Thor Max**, not a Thor 6. Which emulator handles a system best should carry
over — that is about software maturity — but performance figures and how far
you can push an internal resolution depend on the hardware, and those two
devices are not stated to be identical. Treat the settings as a starting point
to tune from, not as measurements taken on this device.

Both are dated. Emulator recommendations move fast; the second's author says
as much about their own earlier post. What is kept here is what survives a
version bump.
