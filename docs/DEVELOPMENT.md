# Development handoff — v15 baseline

## Preserved baseline

This repository starts from the validated revision 15 source. Tag: `v15-baseline`.
The initial commit adds migration/build documentation and local dependency configuration; gameplay source is unchanged.

Preserved v15 ROM: 4,128,768 bytes, SHA-256
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
The following historical host checks cover scripts, documents and saves:

```sh
make host
python3 tools/check_v15.py
# Save changes only:
# python3 tools/check_save.py
# make build/check_save_capacity && ./build/check_save_capacity
```

Historical native document/audio checks accept explicit dependency paths:

```sh
python3 tools/check_v15.py --core "$PWD/.local/tools/picodrive_libretro.so" --mars "$PWD/.local/toolchain/mars" --region NTSC
# Repeat with --region PAL only when region behaviour is relevant.
```

Older gameplay checks assume immediate Start-to-gameplay and must use the new controller flow or `host_startgame(character)` before reuse. Some also fall back to old workspace paths; use their explicit --mars/--core arguments. Music-level comparisons require a preserved v14 reference project. Historical validation files describe earlier releases, not a fresh verification of this checkout. See docs/validation/v15-validation.md and rebuild-v15.json for the original release evidence; migration-v15.json records the relocation check.

For startup changes, build the host library and run `python3 tools/check_startup.py`.
It checks real controller navigation, timed credits and animated logo, both
biographies, the full original arrival, the paused frog picture, skipping,
clean gameplay initialization and old-save compatibility. Evidence and captures
are written under `build/`. The old-save comparison uses the preserved
`build/startup-reference/libaitd32x.so` and its `assets/bank.bin`; it copies only
private host SRAM arrays and never reads or writes emulator battery saves.
`--world-only` checks the original World/LIFE/animation/camera sequence without
requiring that reference library. Host diagnostics `host_startgame(character)`
start gameplay directly for unrelated focused tests so those tests need not
replay the startup sequence.
For arrival-rendering changes, add
`--render-reference build/startup-fix-reference` with a preserved startup host
library and its asset bank. The same lifecycle check compares both full
arrivals at matching world ticks, including palette fades and both framebuffer
histories. Only rows 180–195 are excluded because script-message casing changes
there; all geometry differences fail the check and are recorded in its report.
`python3 tools/check_bank_layout.py` verifies linked main/extra bytes, mapper
page isolation, protected audio/code, BIOS module placement and the RAM limit.
`tools/check_startup_native.py /path/to/picodrive_libretro.so --mars /path/to/mars`
exercises the linked ROM startup and both arrivals using private in-memory SRAM.
Use `--region PAL` for its PAL timing check. Emulator evidence does not establish
physical 32X hardware validation.
Current build figures and retained check evidence are in
[startup performance validation](validation/startup-performance.md); the
[initial startup validation](validation/startup.md) records the preceding build.
For a focused entrance comparison, preserve the preceding ROM, ELF, host
library and generated assets under ignored `build/startup-fix-reference/`.
`tools/check_startup_performance.py /path/to/picodrive_libretro.so --label before`
records native entrance poses and idle UI work; `--label after` reuses the
same poses with asset pointers relocated by identity. `--live-only` measures
the complete natural route separately from frozen renderer capacity. Reports
stay under `build/startup-performance/` and use no battery-save files.
The host startup check accepts `--render-reference build/startup-fix-reference`
to compare both complete arrival sequences, excluding only the rows containing
intentionally changed mixed-case messages, and requires geometry/palette parity.

## Implemented behaviour and limits

Gameplay runs at 25 Hz with the approved 60 Hz animation clock. Gameplay is limited to floors 0 and 1; full-house progression is unfinished. Their camera backgrounds remain raw ROM data; static rendering, transparency dithering, door/window/furniture ordering and transition caches have received fixes.

The original startup now runs through the animated Infogrames logo, title,
automatically paged credits, New Game/Resume/Replay Intro menu, original Emily
and Edward portraits, their biographies, and the original scripted arrival.
Menu and portrait controls are documented in README.md. Biographies support
directional paging and A/Start/C to advance; B returns. The arrival is skippable
with A/B/C/Start. Presentation timing does not advance the world during the
frog close-up. Arrival completion or skipping calls fresh gameplay initialization;
intro state and death flags do not carry into the playable world.

Arrival-only geometry includes floors 2, 3 and 7, with a selected set of camera
images retaining their original global IDs. Missing views use invalid asset IDs;
camera selection skips these holes. `World::intro` enables these resources only
for the cinematic, and normal gameplay retains its previous floor boundary.
New asset IDs are appended; save schema, existing model/animation IDs and the
original game fingerprint are preserved. The picture request fields are
presentation state and are excluded from saves.

UI retains simplified controls, original gold bezels and black text margins. Reading uses original paper/book/notebook art, proportional font, illustrations and page sound. Audio includes 101 effects through two-voice 8 kHz ADPCM/PWM and eight AdLib songs adapted to YM2612/PSG. CD LIFE cue IDs map to audited floppy themes. Window script error LIFE 20 word 59 is fixed.

One visible save slot uses two 64 KiB SRAM journals; v14 saves remain compatible. A frontend usually associates `.srm` with the ROM basename. Copy an existing battery file when changing ROM names; do not overwrite it with an empty file. The user tests on a separate device and confirmed no local save backup is needed. Preserve battery saves on that device when changing ROM filenames.

The historical v15 ROM was near the 4 MiB direct SH2 ROM window. Startup now uses an extension bank for raw arrival cameras and compressed presentation images, reusing existing framebuffer/background scratch. SH2 RAM remains 256 KiB with 12 KiB master and 4 KiB slave stack reservations. Avoid adding global buffers casually. See docs/ARCHITECTURE.md for current layout details and limits. Physical 32X hardware and CD narration remain unvalidated/unimplemented respectively.

## Next priorities

The opening/occlusion/saber fixes and the reproduced key/chest audio fix were
committed as `a0fd040` and are documented in
[reported-bugs validation](validation/reported-bugs.md). Furniture automatic
closing is original behaviour and is retained. Use its focused check instead
of running the historical suite for these changes. The user confirmed the
door and key/chest audio guards on RePlayOS/PicoDrive.

The [initial performance review](validation/performance-review.md) and its
[implemented follow-up](validation/performance-followup.md) record partial
scenery repairs, prepared/parallel contact depth, engine-update and music-bank
optimizations. That performance build's static SDRAM ended at `0x0603BBC8`,
leaving 1,080 bytes below the reserved stacks; its assets and save format were
unchanged. Startup adds presentation state and bank transport; current figures
are in ARCHITECTURE.md. Use the
partial-cache and native contact differential checks when editing these paths.
Full new-camera bakes and contact work still limit FPS; preserve the documented
mask/order dependencies, scratch ownership and worker completion fences.

1. Keep the playable v15 tag available while fixing any user-reported audio, reading or save regressions.
2. Extend original game progression beyond floors 0 and 1; expand banked graphics while respecting the fixed code/model/audio window and RAM budget.
3. Validate real hardware audio, SRAM, region timing and sustained performance when hardware is available.

Use small feature/fix branches and reviewable commits. Record build commands and decisions in repository documentation so a new Codex chat can continue from files. Desktop and VS Code may use this same checkout; coordinate active edits.
