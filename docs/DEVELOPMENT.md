# Development handoff — v15 baseline

## Current baseline

This repository starts from the validated revision 15 source. Tag: `v15-baseline`.
The initial commit adds migration/build documentation and local dependency configuration; gameplay source is unchanged.

Known working ROM: 4,128,768 bytes, SHA-256
`556275aae35a59cf1863d9c47f39912578912be772a749c40d17a9506857eb60`.
Asset bank: 3,976,924 bytes, 1,969 entries, SHA-256
`b1a17763e20dd481337d4495c0ee32147b08a9e474c3a4e2c122164079f97dfa`.
The preserved release is `.local/baseline/AITD32X-v15.32x`; it is not tracked.

## Local layout and build

- `msdos-game/AITD_CD/INDARK`: original CD resources; current importer input.
- `msdos-game/AITD_FLOPPY`: Spanish floppy resources; reference for original music cues.
- `.local/toolchain/mars`: preserved Marsdev v1.0.0-rc1, GCC 13.1.0 m68k-elf/sh-elf toolchains.
- `.local/tools/picodrive_libretro.so`: preserved stock PicoDrive core for native checks.
- `.local/saves`: battery-save backups; never write automated test fixtures here.
- `local.mk`: local Make settings, ignored. `local.mk.example` is tracked.

This machine's dependencies are copied from the original development workspace so deleting that workspace will not remove the compiler or emulator core. Fresh clones need their own original game installation and dependencies; Git does not include them.
GNU Make, Python 3, host `cc`/`c++` and the Marsdev tools are required.

```sh
# Run from the repository root. On a fresh checkout first configure local.mk:
# cp local.mk.example local.mk
make assets
make -j2
# Result: build/AITD32X.32x
```

Compiler executable paths are quoted to support this project's path containing spaces.
Do not replace the CD source with floppy data without auditing asset IDs and script conventions.
The importer vendors its decompressor and music-capture driver; a separate FITD checkout is needed only for the optional gameplay oracle (tools/reference/README.md).

## Relevant verification

Do not run the entire historical test collection for every change.
For host script, document or save changes, select the relevant check:

```sh
make host
python3 tools/check_v15.py
# Save changes only:
# python3 tools/check_save.py
# make build/check_save_capacity && ./build/check_save_capacity
```

For native document/audio checks, explicitly pass local dependency paths:

```sh
python3 tools/check_v15.py --core "$PWD/.local/tools/picodrive_libretro.so" --mars "$PWD/.local/toolchain/mars" --region NTSC
# Repeat with --region PAL only when region behaviour is relevant.
```

Some older test scripts still fall back to old workspace paths; use their explicit --mars/--core arguments. Music-level comparisons additionally require a preserved v14 reference project. Historical validation files describe earlier releases, not a fresh verification of this checkout. See docs/validation/v15-validation.md and rebuild-v15.json for the original release evidence; migration-v15.json records the relocation check.

## Implemented behaviour and limits

Gameplay runs at 25 Hz with the approved 60 Hz animation clock. Floors 0 and 1 are imported; full-house progression is unfinished. Camera backgrounds are raw ROM data; static rendering, transparency dithering, door/window/furniture ordering and transition caches have received fixes.

UI retains simplified controls, original gold bezels and black text margins. Reading uses original paper/book/notebook art, proportional font, illustrations and page sound. Audio includes 101 effects through two-voice 8 kHz ADPCM/PWM and eight AdLib songs adapted to YM2612/PSG. CD LIFE cue IDs map to audited floppy themes. Window script error LIFE 20 word 59 is fixed.

One visible save slot uses two 64 KiB SRAM journals; v14 saves remain compatible. A frontend usually associates `.srm` with the ROM basename. Copy an existing battery file when changing ROM names; do not overwrite it with an empty file. The user tests on a separate device and confirmed no local save backup is needed. Preserve battery saves on that device when changing ROM filenames.

The v15 ROM is near the 4 MiB direct SH2 ROM window. SH2 RAM is 256 KiB; static end 0x0603BDF0 leaves only 528 bytes below the reserved 12 KiB master/4 KiB slave stacks. Avoid adding global buffers casually. See docs/ARCHITECTURE.md for layout details. Physical 32X hardware and CD narration remain unvalidated/unimplemented respectively.

## Next priorities

The current uncommitted opening/occlusion/saber fixes and the reproduced
key/chest audio fix are documented in
[reported-bugs validation](validation/reported-bugs.md). Furniture automatic
closing is original behaviour and is retained. Use its focused check instead
of running the historical suite for these changes. The user confirmed the
door audio guard on RePlayOS/PicoDrive; the expanded key unlock guard awaits
confirmation on that device.

1. Keep the playable v15 tag available while fixing any user-reported audio, reading or save regressions.
2. Extend original game progression beyond floors 0 and 1; plan ROM capacity/bank switching before importing the full house.
3. Validate real hardware audio, SRAM, region timing and sustained performance when hardware is available.

Use small feature/fix branches and reviewable commits. Record build commands and decisions in repository documentation so a new Codex chat can continue from files. Desktop and VS Code may use this same checkout; coordinate active edits.
