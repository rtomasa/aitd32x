# AITD32X — revision 15 audio cues and original reading screens

Native Sega 32X conversion using the original Alone in the Dark 1 installation supplied by the user. Revision 15 corrects the window-collision script error, matches the CD scripts to their original AdLib music cues, balances music/effects, and restores original note/book/notebook artwork, proportional typography, illustrations and page sounds. Other game menus retain their gold bezels and four-pixel black text padding.

## Play

Load `AITD32X.32x` in a 32X-capable emulator with cartridge SRAM saving enabled. The frontend retains saves in its battery/save file (usually `.srm`). On the title, C selects Edward/Emily, Start or A begins a new game, and B loads the latest valid save.

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

The game remains a 25 Hz simulation with the approved 60 Hz animation clock. Native video is 320×224 with a 320×200 scene and black borders. FPS measures completed draws. A static pause/title can show zero FPS.

## Audio

101 original VOC effects are converted offline to 8 kHz mono IMA ADPCM and mixed through interrupt-driven 32X PWM, with two simultaneous voices. Original LIFE sound commands drive footsteps, actions, combat, creatures and scripted effects; repeating/chained effects and stop commands are connected. Eight original ADLM songs are converted offline using the pinned FITD music driver. Six melodic voices use YM2612 FM; extra melodic voices and approximate percussion use PSG. Low auxiliary PSG notes are moved up by octaves to stay within its pitch range. Instruments, waveforms and percussion are adapted to these chips, so timbre differs from AdLib. World/save files retain the CD edition’s cue numbers. Playback maps them to the corresponding floppy AdLib themes, audited against 101 paired original script cues (tools/audio/music_cues.json). CD cues with no AdLib counterpart stop FM playback; CD-specific PCM musical effects remain on their original sound path. Track selection, queued transitions and three-second fades follow LIFE commands. Equivalent CD cues sharing one AdLib theme preserve its playhead. Stop/track-end explicitly mutes all FM operators, including instruments with a zero release rate. Music FM carriers and PSG are about 6 dB quieter than v14, while PWM effects have 1.5× the previous gain. Music advances on the 68000 at 58.8 driver ticks/s in NTSC and PAL, independent of rendering, with region pitch compensation. Camera images remain raw; audio encoding is decoded continuously by the audio interrupt.

## Reading

Original ITD_RESS entries 6/7/8 provide paper, book and notebook backgrounds, entry 5 supplies the original proportional font, and entry 9 supplies the five document illustrations. Original mixed case, centered headings, paragraph indentation and explicit page breaks are retained. Layout is compiled offline; backgrounds are raw ROM copies. SAMPLE_PAGE uses original effect 49 on opening, paging and closing. The world pauses while reading and resumes with its scenery cache intact. No additional gameplay RAM or cartridge bank-switching is needed.

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

Identical converted payloads share aligned ROM storage, retaining asset IDs and avoiding image decompression. The ROM is 4,128,768 bytes (3.9375 MiB), within the 4 MiB SH2 window. The 68000 uses the standard 32X ROM bank window for music reads. SRAM supplies two 64 KiB journal records. Rare initialization/save/UI routines execute from ROM to preserve the 12 KiB master and 4 KiB slave stack reservations.

## Focused checks

```sh
make host build/check_save_capacity
python3 tools/check_save.py
./build/check_save_capacity
python3 tools/check_audio_save_native.py /path/to/picodrive_libretro.so --mars /path/to/mars
python3 tools/check_audio_save_native.py /path/to/picodrive_libretro.so --mars /path/to/mars --region PAL
python3 tools/check_audio_streams.py /path/to/picodrive_libretro.so --mars /path/to/mars
python3 tools/check_audio_streams.py /path/to/picodrive_libretro.so --mars /path/to/mars --region PAL
python3 tools/check_ui.py --core /path/to/picodrive_libretro.so
```

The native save check generates compiler-derived layout data used by the stream check. Debugger setup selects music/poses; controller input exercises the save/load/menu and movement paths. `docs/VALIDATION.md` records checks and limits, `docs/PERFORMANCE.md` records release timing, and `docs/ARCHITECTURE.md` describes memory/transport. Versioned reports preserve prior evidence. Floors 0 and 1 are imported; full-house progression and physical hardware validation remain unfinished.

Engine source is GPL; see LICENSE and third_party/NOTICES.md. Original resources retain their original ownership.

## Revision 15 validation

Focused checks and limitations are recorded in docs/validation/v15-validation.md. Run tools/check_v15.py for both-character window collision and document paging; add --core /path/to/picodrive.so --mars /path/to/mars --region NTSC or PAL for actual-cartridge reading/audio checks. tools/check_mix.py compares native sound levels to a preserved v14 project. Original resources are not redistributed in the source archive.
