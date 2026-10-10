# AITD32X — original startup and arrival sequence

Native Sega 32X conversion using the original Alone in the Dark 1 installation supplied by the user. Revision 15 corrects the window-collision script error, matches the CD scripts to their original AdLib music cues, balances music/effects, and restores original note/book/notebook artwork, proportional typography, illustrations and page sounds. Other game menus retain their gold bezels and four-pixel black text padding.

Startup now includes the original animated Infogrames armadillo, title, timed credits, start menu, character portraits and biographies, and the scripted journey through Derceto to the attic. The console menu offers Replay Intro in place of Return to DOS. Both characters retain their original introduction text and arrival animations.

## Play

Load `AITD32X.32x` in a 32X-capable emulator with cartridge SRAM saving enabled. The frontend retains saves in its battery/save file (usually `.srm`). Any button skips the logo/title/credits to the start menu. Up/Down selects Begin a New Game, Resume a Saved Game or Replay Intro; A/Start confirms. B loads the latest valid save directly from this menu.

Character selection: Left chooses Emily, Right chooses Edward, C toggles, and A/Start opens the selected biography. B returns to the menu. In the biography, Up/Left and Down/Right change pages; A/Start/C advances and begins the arrival after the last page. B returns to character selection. A/B/C/Start skips the arrival to fresh gameplay. Credits turn pages automatically. The frog close-up pauses the arrival simulation, and completing or skipping the introduction starts a clean game without erasing a save.

| Button | Gameplay |
|---|---|
| Up / Down | Walk forward / backward |
| Left / Right | Turn |
| B + Up | Run |
| Hold A + direction | Selected action / attack |
| C | Inventory |
| Start | Pause menu |

In the pause menu, Up/Down selects Resume, Save Game, Load Game or Return to Title; A confirms. Start/B/C resumes. Loading opens this menu with gameplay paused. There is one visible save slot, backed by two alternating records; a damaged newest record falls back to the previous valid save. A new game does not erase the save. Save transfers can take a few seconds; wait for GAME SAVED. A load restores both characters, floor/room/camera, health, inventory, variables, enemies, doors, furniture, RNG and animation state. The music track restarts from its beginning when loading; exact audio playhead/sample voices are not saved. Saves use this port's own format. Revision 14 saves remain compatible; when using a versioned ROM filename, copy its existing .srm battery file to the new ROM's filename.

Inventory: Up/Down selects an object, A opens its actions, Up/Down selects, A confirms, C/B returns. The Actions entry selects Fight, Search, Close or Push through original scripts. Hold A while facing furniture to search/push; approach with a direction. In Fight, A + Up/Down/Left/Right selects attacks. Pickups use A to take or C/B to leave. Books use Up/Down, Left/Right or B for pages and A/C to close. Original arrows indicate available previous/next pages. Gameplay time freezes in these screens.

The game remains a 25 Hz simulation with the approved 60 Hz animation clock. Native video is 320×224 with a 320×200 scene and black borders. FPS measures completed draws and is hidden during startup. A static paused game can show zero FPS.

Static pause, inventory and action menus redraw on input or a changed FPS value. Document text shares the optimized proportional-font renderer used by startup.

## Audio

101 original VOC effects are converted offline to 8 kHz mono IMA ADPCM and mixed through interrupt-driven 32X PWM, with two simultaneous voices. Original LIFE sound commands drive footsteps, actions, combat, creatures and scripted effects; repeating/chained effects and stop commands are connected. Eight original ADLM songs are converted offline using the pinned FITD music driver. Six melodic voices use YM2612 FM; extra melodic voices and approximate percussion use PSG. Low auxiliary PSG notes are moved up by octaves to stay within its pitch range. Instruments, waveforms and percussion are adapted to these chips, so timbre differs from AdLib. World/save files retain the CD edition’s cue numbers. Playback maps them to the corresponding floppy AdLib themes, audited against 101 paired original script cues (tools/audio/music_cues.json). CD cues with no AdLib counterpart stop FM playback; CD-specific PCM musical effects remain on their original sound path. Track selection, queued transitions and three-second fades follow LIFE commands. Equivalent CD cues sharing one AdLib theme preserve its playhead. Stop/track-end explicitly mutes all FM operators, including instruments with a zero release rate. Music FM carriers and PSG are about 6 dB quieter than v14, while PWM effects have 1.5× the previous gain. Music advances on the 68000 at 58.8 driver ticks/s in NTSC and PAL, independent of rendering, with region pitch compensation. Camera images remain raw; audio encoding is decoded continuously by the audio interrupt.

## Reading

Original ITD_RESS entries 6/7/8 provide paper, book and notebook backgrounds, entry 5 supplies the original proportional font, and entry 9 supplies the five document illustrations. Original mixed case, centered headings, paragraph indentation and explicit page breaks are retained. Layout is compiled offline; reading backgrounds use lossless ROM compression and are decoded for these screens. SAMPLE_PAGE uses original effect 49 on opening, paging and closing. The world pauses while reading and resumes with its scenery cache intact. No additional gameplay image buffer is needed.

## Build

GNU Make, Python 3, host C/C++, and Marsdev GCC 13.1.0 m68k-elf/sh-elf toolchains are required. Original resources are excluded from the source ZIP.

```sh
cp local.mk.example local.mk  # On a fresh checkout; configure dependency paths.
make assets                 # Uses msdos-game/AITD_CD/INDARK by default.
make -j2
# Overrides are also supported:
# make assets GAME_DATA="/path/to/ALONE1/INDARK"
# make -j2 MARSDEV="/path/to/mars"
```

See [development handoff](docs/DEVELOPMENT.md) for the Git baseline, local dependencies, focused checks and next work. Original DOS data, converted assets, builds and saves are ignored by Git.

Identical converted payloads share aligned ROM storage, retaining existing asset IDs. Gameplay camera images, panels and reading sprites remain raw for fast rendering. Logo, portrait, paper and picture images use lossless compression. Arrival camera images use raw banked pixels so the scenery cache can retain original occlusion masks. Static startup screens redraw when content changes; palette fades update without redrawing. Menu and arrival text preserve the original casing. This 4.875 MiB ROM requires 32X SSF2 mapper support, verified in PicoDrive. SRAM supplies two 64 KiB journal records. Rare initialization/save/UI routines execute from ROM to preserve the 12 KiB master and 4 KiB slave stack reservations. See [architecture](docs/ARCHITECTURE.md) for the current ROM layout and memory limits.

## Focused checks

```sh
make host
# Startup changes only; use the preserved pre-startup host library for old-save checks:
python3 tools/check_startup.py
python3 tools/check_bank_layout.py
python3 tools/check_startup_native.py /path/to/picodrive_libretro.so --mars /path/to/mars
# Region-sensitive startup/banking changes:
python3 tools/check_startup_native.py /path/to/picodrive_libretro.so --mars /path/to/mars --region PAL
```

The native startup check uses controller input and private in-memory SRAM for save/core-restart/resume. Older gameplay checks assume immediate Start-to-gameplay and need startup navigation or the host fixture `host_startgame(character)` before reuse. `docs/VALIDATION.md` records historical checks, [startup performance validation](docs/validation/startup-performance.md) records this build, and `docs/ARCHITECTURE.md` describes memory/transport. Gameplay supports floors 0 and 1. Additional room/camera resources are imported only for the original arrival; full-house progression and physical hardware validation remain unfinished.

Engine source is GPL; see LICENSE and third_party/NOTICES.md. Original resources retain their original ownership.

## Revision 15 validation

Historical checks and limitations are recorded in docs/validation/v15-validation.md. tools/check_v15.py covers window collision and document paging in that baseline; tools/check_mix.py compares native sound levels to a preserved v14 project. Their startup setup predates the new menus. Original resources are not redistributed in the source archive.
