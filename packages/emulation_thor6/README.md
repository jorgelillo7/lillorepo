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
| [Nintendo DS](docs/nds.md) | DraStic | 19 |
| [Nintendo 3DS](docs/3ds.md) | Azahar | 5 |
| [PlayStation Portable](docs/psp.md) | PPSSPP | 3 |
| [Dreamcast](docs/dreamcast.md) | Redream / Flycast | 1 |
| [GameCube and Wii](docs/gamecube-wii.md) | Dolphin | 4 |
| [PlayStation 2](docs/ps2.md) | NetherSX2 | 16 |
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

## A launcher, once it gets big

Fifteen systems and 142 titles is past the point where launching each emulator
by hand stays pleasant. A front-end that scans one ROMs folder, sorts by
platform and shows box art is the usual answer, and the write-up uses one
(Console Launcher) pointed at the ROMs directory with automatic platform
detection turned on. Any of the common front-ends does the same job.

This is worth doing **after** the systems work individually, not before: a
launcher that fails to start a game tells you nothing about whether the
emulator or the launcher is at fault.

---

## Source

The device-specific settings, driver notes and performance figures above come
from [Cómo instalar emuladores en la AYN
Thor](https://www.profesionalreview.com/2026/08/16/como-instalar-emuladores-ayn-thor/)
(Profesional Review, August 2026). Read it for the walkthrough with
screenshots; this guide keeps only what stays true as app versions move, plus
the parts specific to this collection.
