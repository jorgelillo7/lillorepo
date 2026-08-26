# PlayStation 2

> **Documentation only.** This directory holds notes, folder layouts and
> checklists. It contains no ROMs, disc images, BIOS dumps or encryption keys,
> it links to none, and it explains where to obtain none. Every entry below
> assumes you are supplying a dump you made yourself from media you own, which
> is the only use this guide supports.


- **Emulator:** NetherSX2 Turnip, with two alternates — see notes
- **Games go in:** `SD_TEMPLATE/ROMs/ps2/`
- **BIOS:** Required. NetherSX2 will not boot without a PS2 BIOS image dumped from your own console.
- **BIOS goes in:** `SD_TEMPLATE/BIOS/`

## Notes

**The one system where the emulator is a per-game decision.** Three builds,
all descended from the abandoned AetherSX2, and community reports on this
handheld use all three:

| Build | When |
|---|---|
| **NetherSX2 Turnip** | the default — best compatibility and performance overall |
| **NetherSX2 Classic** (not the Turnip build) | the odd game the default handles worse; Sly Cooper 1 was reported |
| **ARMSX2 Refresh** (recent Turnip or T26 "Toasted" drivers) | the heaviest titles — Jak 3, Shadow of the Colossus |

ARMSX2 is actively developed and improving, but still shows visual bugs in
lighter titles (MGS2 was reported), so it earns its place on the demanding
games rather than as a default.

**Memory cards are not shared between emulators.** Switching build mid-game
leaves your saves in the old one. This is the trap on this system.

**Do not rely on save states here.** Use in-game saves.

Settings: Vulkan renderer, shader disk cache on, asynchronous shaders on. Turn
on the colour/saturation boost — PS2 output looks washed out on an OLED
without it. Widescreen hacks are built in.

When something runs badly, in order: switch Vulkan ↔ OpenGL, try another
build, **disable hardware readbacks** (a large gain, at the cost of minor
graphical bugs), lower the internal resolution. The software renderer always
works if original PS2 visuals are acceptable. Gran Turismo 3 and 4 run well,
though night stages may want readbacks off.

Both Kingdom Hearts FINAL MIX editions are Japanese releases; playing them in
English or Spanish means a fan translation over your own dump. San Andreas has
two well-known audio versions — the original licensed soundtrack and the later
reduced one — and which you get depends on which disc you dumped.

## Checklist (16 titles)

- [ ] Grand Theft Auto: San Andreas
- [ ] Bully (Canis Canem Edit)
- [ ] The Simpsons: Hit & Run
- [ ] Need for Speed Underground 2
- [ ] Burnout 3: Takedown
- [ ] Tony Hawk's Underground
- [ ] Tony Hawk's Underground 2
- [ ] Dragon Ball Z: Budokai Tenkaichi 3
- [ ] Kingdom Hearts FINAL MIX
- [ ] Kingdom Hearts II FINAL MIX
- [ ] Jak and Daxter: The Precursor Legacy
- [ ] Ratchet & Clank
- [ ] Dragon Quest VIII: Journey of the Cursed King
- [ ] The Lord of the Rings: The Return of the King
- [ ] Silent Hill 2
- [ ] One Piece: Grand Adventure
