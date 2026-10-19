# AITD32X

A native Sega 32X port of **Alone in the Dark 1**, using the original game's resources and engine behavior adapted from [FITD](third_party/NOTICES.md). All eight original floors are enabled, including the underground areas, final ritual, destruction animation and escape. This is an alpha in active development; a full playthrough with both characters is still pending.

## Download and play

Find published ROM builds and their release notes in [GitHub Releases](https://github.com/rtomasa/aitd32x/releases). This README describes the current development checkout; earlier releases may contain fewer features. Source archives contain the engine and importer; building requires your own original game installation.

Load `AITD32X.32x` in a 32X-capable emulator with **SSF2 cartridge mapper support** and cartridge SRAM saving enabled. The current ROM is **14,155,776 bytes (14.16 MB / 13.5 MiB)**. Native checks use PicoDrive libretro in NTSC and PAL. A physical flash cartridge must support this mapper in 32X mode and have enough ROM storage; compatibility with the previously reported cheap flash cartridge remains unestablished.

The current development build uses the `SEGA SSF` header and extended SSF
initialization for large cartridge ROMs. Keep the **`.32x` extension**. This
addresses the reported EverDrive Pro selection of `10M+32x (3)`; the intended
mapper is **SSF (5)**. Saving now uses **32 KiB of odd-byte SRAM**,
with conventional access for PicoDrive/MiSTer and the documented upper-half
page-31 window on extended SSF hardware. Save/load and core-restart checks
pass in PicoDrive, including private models of both hardware layouts. The user
has also confirmed saving works on MiSTer. Physical cartridge SRAM access and
flashcart SD export still need confirmation. See [SRAM validation](docs/validation/sram.md) and
[mapper validation](docs/validation/ssf-mapper.md).

## Features

- Original animated Infogrames logo, title, credits, start menu, character selection, biographies and scripted arrival at Derceto.
- Both Emily Hartwood and Edward Carnby, with their original introductions.
- Original three-section inventory with rotating 3D items, quantities, health, actions and scrolling; original Leave/Take pickup screen with a 3D object preview.
- Original proportional typography, mixed case and symbols throughout menus and gameplay. Information messages appear once, directly over the scene.
- Original paper, book and notebook artwork, illustrations, document layout and page sounds.
- All eight floors, 58 original rooms and 144 camera views, with the full original script and track resources for enemies, puzzles, the final ritual and escape.
- Dark-room lighting follows the held or dropped lantern; the original 50-actor capacity is supported.
- Original scripted death cinematic, final picture, destruction animation and escape progression.
- 101 original sound effects through 32X PWM and eight original AdLib music tracks adapted to YM2612/PSG. Effects decode at 8 kHz with interpolated output through a roughly 24 kHz PWM carrier; outputs stop at idle. Instrument timbre differs from the PC version.
- Persistent saving with one visible slot and two alternating SRAM records for recovery if the newest record is damaged.

The PWM update applies to all effects, including both alternating footsteps.
The user reports improved sound quality. A follow-up removes blocking FIFO
waits that could freeze the drawing processor. The full logo and arrival,
effect durations, chaining and repeats pass native NTSC/PAL checks; device
confirmation of the revised driver remains pending. See [PWM validation](docs/validation/pwm.md).

## Latest rendering changes

- Shared ordering repairs for doors, furniture and floor hatches, including the attic window behind the pushed cupboard.
- Original near-camera face rejection restored, fixing the giant door polygon in the pink-chair bedroom.
- Cached scenery now preserves architectural masks and repairs the full area overwritten by foreground actors.
- Contact-depth rendering includes intervening overlapping objects, and prepared prop drawing follows the same visibility rules as ordinary drawing.

Focused checks cover all 144 cameras in sampled states and both reported scenes in PicoDrive NTSC/PAL, with both characters and framebuffer banks. They do not verify every animation or puzzle pose. Full playthrough, physical 32X validation and sustained hardware performance remain pending. CD narration is not implemented; music timbre and some visual effects differ from DOS.

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

**Character selection:** Left chooses Emily, Right chooses Edward, C toggles, and A/Start opens the biography. B returns to the start menu. In biographies, Up/Left and Down/Right change pages; A/Start/C advances and begins the arrival after the last page. B returns to character selection. A/B/C/Start skips the arrival or death cinematic; skipping the destruction movie resumes the escape.

**Inventory and actions:** Up/Down selects an object, A opens its actions, Up/Down selects an action, and A confirms. C/B returns. The Actions entry selects Fight, Search, Close or Push through the original scripts. Hold A while facing furniture and use a direction to search or push. In Fight, A + Up/Down/Left/Right selects attacks. Furniture closing automatically is original game behaviour.

**Pickups:** Left/Right selects Leave or Take; A confirms. Take is selected initially. B/C leaves the object.

**Reading:** Up/Down, Left/Right or B changes pages; A/C closes. Original arrows show available previous/next pages.

**Pause menu:** Up/Down selects Resume, Save Game, Load Game or Return to Title; A confirms. Start/B/C resumes. Loading leaves gameplay paused. Inventory, pickups and reading also pause the world.

## Saves

Enable cartridge SRAM in your emulator. The frontend usually stores it in a `.srm` battery file associated with the ROM's filename. When changing ROM filenames, back up your existing battery file and copy it to the new ROM's basename without overwriting another save.

A new game does not erase your save. Saving can take a few seconds; wait for the saved confirmation. Loading restores world, characters, inventory, scripts and animation state. Music restarts at the beginning of the restored track; the exact audio playhead and active sample voices are not saved. Saves use this port's own format. The compact format retains the original 50-actor capacity, animation poses and lighting state in two 16 KiB recovery records. A size check runs before writing; an oversized state fails without changing the previous save.

**This build starts a new save format and does not load earlier battery saves or emulator savestates.** Use a new ROM filename for testing so the frontend keeps previous battery files separate. No existing files are converted or modified automatically.

On flash cartridges, use the cartridge's normal SRAM-to-SD backup procedure after the game confirms saving. On MiSTer, enable cartridge backup saving and verify loading again after reloading the core. These are in-game saves; EverDrive emulator-style savestates are a separate feature.

## Performance

Gameplay simulation runs at 25 Hz, with an independent 60 Hz animation clock. Native video is 320×224 with a 320×200 scene. Rendering uses both SH2 processors, cached scenery, partial background repairs and contact-depth rendering where applicable. Camera images remain raw and use bank switching; fixed engine resources stay outside the mapped aperture, allowing camera pages to remain selected between draws. Prepared prop rendering is available across the house, with a normal rendering fallback.

Ordinary model and contact-depth drawing adapt their SH2 row split from measured
workload. Larger background repairs use both processors and can overlap vertex
transformation and face sorting, including inventory and pickup previews.
Completion fences preserve masks, scenery readback and framebuffer swaps.
See [SH2 scheduling validation](docs/validation/sh2-scheduling.md) for measured
benefits and hardware testing limits.

Shared solid spans, background copies, image decoding and panels use aligned
32-bit writes with safe word tails and partial-pixel handling. Compact SH2 wait
loops cover rendering, framebuffer swaps and mapper/audio/save handshakes.
See [framebuffer and synchronization validation](docs/validation/framebuffer-sync.md)
for pixel checks, measured menu response and pending hardware comparisons.

Paired vertex projection schedules Y-numerator work during X division and
centers/clamps X during Y division. It preserves exact signed arithmetic and
the hardware divider's latency across gameplay, contact depth, effects and
3D previews. See [projection validation](docs/validation/projection.md).

Contact correction reuses ordinary projections, skips triangle pixels that it
will redraw, and caches settled-prop depth commands in unused scenery-span
storage. Face rejection precedes sorting; architectural masks seek relevant
rows and prepare activation once per actor. In paired PicoDrive runs on a Pi 5,
the hallway improves from 11.8 to 14.8 FPS and standing near the chest from
20 to 23 FPS. Active pushing improves only from 15 to 15.4 FPS. See
[render preparation measurements](docs/validation/render-preparation.md) for
the memory budget, validation and remaining slow scenes, and
[earlier action measurements](docs/validation/action-performance.md) for the
preceding changes. MiSTer and physical 32X comparisons remain pending.

Static presentation screens redraw when their content changes; palette fades do not require full redraws. Inventory and pickup screens cache their panels and labels and update the rotating preview at up to 30 FPS. Menu input follows controller snapshots independently of the world clock. Compressed presentation images share the same optimized decoder across the game.

The ending animation applies precompiled changed spans to the retained image. Dark rooms use a bounded lamp mask, restoring each framebuffer's previous illuminated footprint. Compact original bone channels let the 50-actor pool fit in the existing RAM budget.

The FPS counter measures completed draws and is hidden during startup. Zero FPS on an idle, static screen is normal. Room transitions and complex scenes can still take longer to render; emulator results do not establish hardware performance.

The latest rendering fixes retain approximately 24.2 completed draws/s in short early-game PicoDrive traces in both regions, with no material loss in the sampled comparisons. Complex animated scenes remain slower; these measurements are not a whole-game FPS guarantee.

### ROM size

The original camera archives use about **3.0 MB compressed**. This build stores the same 144 camera images as **9.2 MB of raw pixels**, allowing direct copies and background-mask repairs without decompression during room changes. That accounts for most of the increase over the DOS installation. Prepared prop drawing adds about **0.76 MB**; converted resources, engine code, mapper alignment and padding account for the rest. This trades cartridge space for runtime performance. See the [measured size breakdown](docs/validation/window-door.md#why-the-rom-is-larger-than-the-dos-installation).

The original assets and scripts do not make the DOS renderer run unchanged on the 32X. The port's two-SH2 drawing, scenery caches and local depth correction must preserve the reference engine's visibility rules. The latest fixes address discrepancies in those adaptations; distance sorting alone cannot resolve every intersecting polygon.

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

Full-game coverage and its limits are documented in [full-game validation](docs/validation/full-game.md). Shared rendering-order repairs are in [draw-order validation](docs/validation/draw-order.md); the subsequent [window/door validation](docs/validation/window-door.md) records reported visibility fixes, current ROM figures and the size breakdown. Current UI and menu evidence is documented in [menu feedback validation](docs/validation/menu-feedback.md) and [gameplay UI/death validation](docs/validation/gameplay-ui-death.md). [Validation history](docs/VALIDATION.md) records earlier builds; those reports describe their respective revisions, rather than verification of every later checkout. Run only the checks relevant to a change.

## License

Engine source is GPL; see [LICENSE](LICENSE) and [third-party notices](third_party/NOTICES.md). Original game resources retain their original ownership.
