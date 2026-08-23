# Emulation Collection — AYN Thor 6

Setup notes and per-system checklists for one handheld. It lives here rather
than in `docs/` because it is not only prose: `SD_TEMPLATE/` is a folder tree
meant to be copied onto a card, and a directory layout is an awkward thing to
keep in a documentation folder. `my_photos` set the precedent — a personal
project with no deployable code, tracked in the repo because that is where
things get found again.

Nothing here builds, deploys or runs in CI.

## Legal

> **This directory is documentation only.**
>
> It contains **no ROMs, no disc images, no BIOS dumps and no encryption
> keys**. It links to none of those, and it does not explain where to obtain
> them. Requests to add any of them will not be met.
>
> Every checklist below assumes **you are supplying a dump you made yourself
> from media you own**. That is the only use this guide supports. Where a note
> mentions a translation patch or a ROM hack, it means a patch applied to your
> own dump — the patch is not distributed here either.
>
> `SD_TEMPLATE/` is deliberately empty. It exists to describe a shape, and
> `.gitkeep` is the only file that will ever be committed inside it.

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
