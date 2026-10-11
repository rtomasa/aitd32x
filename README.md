# AITD32X

A native Sega 32X port of **Alone in the Dark 1**, built from the original game's resources. The port is in active development: gameplay currently supports floors 0 and 1; full-house progression is unfinished.

## Download and play

Downloadable ROM builds are distributed through [GitHub Releases](https://github.com/rtomasa/aitd32x/releases). Source archives contain the engine and importer; building requires your own original game installation.

Load `AITD32X.32x` in a 32X-capable emulator with **SSF2 cartridge mapper support** and cartridge SRAM saving enabled. The current ROM is 5.125 MiB. Native checks use PicoDrive libretro in NTSC and PAL; physical 32X hardware validation is still pending. CD narration is not implemented.

## Features

- Original animated Infogrames logo, title, credits, start menu, character selection, biographies and scripted arrival at Derceto.
- Both Emily Hartwood and Edward Carnby, with their original introductions.
- Original three-section inventory with rotating 3D items, quantities, health, actions and scrolling; original Leave/Take pickup screen with a 3D object preview.
- Original proportional typography, mixed case and symbols throughout menus and gameplay. Information messages appear once, directly over the scene.
- Original paper, book and notebook artwork, illustrations, document layout and page sounds.
- Original scripted death cinematic, final picture and return to the title menu.
- 101 original sound effects through 32X PWM and eight original AdLib music tracks adapted to YM2612/PSG. Instrument timbre differs from the PC version.
- Persistent saving with one visible slot and two alternating SRAM records for recovery if the newest record is damaged.

## Controls

| Button | Gameplay |
|---|---|
| Up / Down | Walk forward / backward |
| Left / Right | Turn |
| B + Up | Run |
| Hold A + direction | Selected action / attack |
| C | Inventory |
| Start | Pause menu |

**Startup:** A/B/C/Start skips the logo, title or credits. Up/Down selects Begin a New Game, Resume a Saved Game or Replay Intro; A/Start confirms. B loads the latest valid save directly.

**Character selection:** Left chooses Emily, Right chooses Edward, C toggles, and A/Start opens the biography. B returns to the start menu. In biographies, Up/Left and Down/Right change pages; A/Start/C advances and begins the arrival after the last page. B returns to character selection. A/B/C/Start skips the arrival or death cinematic.

**Inventory and actions:** Up/Down selects an object, A opens its actions, Up/Down selects an action, and A confirms. C/B returns. The Actions entry selects Fight, Search, Close or Push through the original scripts. Hold A while facing furniture and use a direction to search or push. In Fight, A + Up/Down/Left/Right selects attacks. Furniture closing automatically is original game behaviour.

**Pickups:** Left/Right selects Leave or Take; A confirms. Take is selected initially. B/C leaves the object.

**Reading:** Up/Down, Left/Right or B changes pages; A/C closes. Original arrows show available previous/next pages.

**Pause menu:** Up/Down selects Resume, Save Game, Load Game or Return to Title; A confirms. Start/B/C resumes. Loading leaves gameplay paused. Inventory, pickups and reading also pause the world.

## Saves

Enable cartridge SRAM in your emulator. The frontend usually stores it in a `.srm` battery file associated with the ROM's filename. When changing ROM filenames, back up your existing battery file and copy it to the new ROM's basename without overwriting another save.

A new game does not erase your save. Saving can take a few seconds; wait for the saved confirmation. Loading restores world, characters, inventory, scripts and animation state. Music restarts at the beginning of the restored track; the exact audio playhead and active sample voices are not saved. Saves use this port's own format, and existing port battery saves remain compatible.

## Performance

Gameplay simulation runs at 25 Hz, with an independent 60 Hz animation clock. Native video is 320×224 with a 320×200 scene. Rendering uses both SH2 processors, cached scenery, partial background repairs and contact-depth rendering where applicable.

Static presentation screens redraw when their content changes; palette fades do not require full redraws. Inventory and pickup screens cache their panels and labels and update the rotating preview at up to 30 FPS. Menu input follows controller snapshots independently of the world clock. Compressed presentation images share the same optimized decoder across the game.

The FPS counter measures completed draws and is hidden during startup. Zero FPS on an idle, static screen is normal. Room transitions and complex scenes can still take longer to render; emulator results do not establish hardware performance.

## Build

GNU Make, Python 3, host C/C++ compilers and Marsdev GCC 13.1.0 `m68k-elf`/`sh-elf` toolchains are required. Configure local dependency paths in `local.mk`, then import your original CD resources and build:

```sh
cp local.mk.example local.mk
# Edit local.mk to configure your dependency paths.
make assets GAME_DATA="/path/to/ALONE1/INDARK"
make -j2
```

The result is `build/AITD32X.32x`. Without `GAME_DATA`, the importer uses `msdos-game/AITD_CD/INDARK`. Original DOS data, converted assets, builds, local dependencies and emulator saves are excluded from Git.

## Development and validation

Read [development instructions](docs/DEVELOPMENT.md) for local setup and focused checks, and [architecture](docs/ARCHITECTURE.md) for processor responsibilities, ROM banking, memory budgets and save transport.

Current UI and menu evidence is documented in [menu feedback validation](docs/validation/menu-feedback.md) and [gameplay UI/death validation](docs/validation/gameplay-ui-death.md). [Validation history](docs/VALIDATION.md) records earlier builds; those reports describe their respective revisions, rather than verification of every later checkout. Run only the checks relevant to a change.

## License

Engine source is GPL; see [LICENSE](LICENSE) and [third-party notices](third_party/NOTICES.md). Original game resources retain their original ownership.
