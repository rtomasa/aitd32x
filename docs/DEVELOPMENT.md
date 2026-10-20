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

For contact/scenery optimizations, see the before/after fixtures in
[action performance measurements](validation/action-performance.md).
`check_raster_parity.py --ordinary` checks every prepared prop's pixels and
coverage; `check_draw_order_cache.py --sweep`, `check_contact_order.py` and
`check_partial_cache.py` cover composition and repair. The native
`check_sh2_scheduling_native.py` verifies scratch ownership/fences in both
framebuffer banks; use NTSC/PAL for shared-worker changes. Preserve the
last-projection hint's lifetime and overwrite compact vertices with bounds
only after all contact fallback decisions have passed. Run
`check_bank_layout.py` after code-placement changes: the current RELEASE
static stack margin is only 328 bytes.

The shared [render preparation paths](validation/render-preparation.md) also
borrow unused scenery-span storage for stationary contact programs. Preserve
the complete span capacity, invalidate programs on storage/scene/pose changes,
and rebuild skipped vertices before any depth fallback. With a preserved host
library, `tools/check_prepared_contact_cache.py --reference /path/to/libaitd32x.so`
checks warm hits, invalidation, near-plane fallback and insufficient storage.
`check_draw_order_cache.py --sweep --reference-library /path/to/libaitd32x.so`
compares complete composition against that earlier renderer.

For scheduled vertex projection, build `make -j2 host all`, then run
`tools/check_projection_native.py .local/tools/picodrive_libretro.so --mars .local/toolchain/mars`
for independent native arithmetic and a VBlank-timed old/new helper comparison.
The isolated diagnostic links assets read-only and never accesses battery saves.
`check_sh2_scheduling_native.py` covers ordinary/contact projection and
`check_gameplay_ui.py --core .local/tools/picodrive_libretro.so --native-only`
covers rotating previews in both regions. Run `check_bank_layout.py` for the
very tight static SDRAM limit. See [projection validation](validation/projection.md).

For aligned framebuffer writes or SH2 waits, run the focused decoder and band
checks (`make build/check_decode build/check_bands`, then both executables),
`check_bank_layout.py`, `check_sh2_scheduling_native.py` and
`check_startup_native.py --short-arrival` with the local PicoDrive core.
Use NTSC/PAL for VDP/command-wait changes. These use private SRAM and exercise
black pixels, alignment/tails, overlapping LZ4 matches, both framebuffer banks,
SH2 queue ownership and mapper/audio/save exchanges. See
[framebuffer and synchronization validation](validation/framebuffer-sync.md).

Do not run the entire historical test collection for every change.
For shared original-font decoding/batching changes, preserve the preceding host
library, then run `tools/check_font_spans.py --reference /path/to/libaitd32x.so`,
`tools/check_menu_messages.py` and
`tools/check_gameplay_ui.py --core .local/tools/picodrive_libretro.so --native-only`.
The latter covers both NTSC and PAL; the font comparison covers all layout
pages, bit alignments, clipping and both framebuffer banks. Run the linked
layout check for ROM/stack constraints. See
[MiSTer text measurements](validation/mister-optimization.md) for scope and limits.

For PWM changes, run `make -j2 all`, `tools/check_bank_layout.py`,
`tools/check_pwm_irq.py` (FULL/EMPTY fault injection), and
`tools/check_pwm_native.py .local/tools/picodrive_libretro.so` in NTSC and with
`--region PAL`. The PWM check covers duration, both footsteps, repeats, chaining,
two voices, explicit stop, idle output disable and a frozen rendering comparison.
Also run `tools/check_startup_native.py .local/tools/picodrive_libretro.so`
without `--short-arrival` in both NTSC and PAL: skipping the intro misses the
reported logo/car freezes. Never wait for PWM FIFO status inside the ISR.
`--baseline` records the preceding driver without enforcing the new carrier/
idle policy; preserve the reference ROM/ELF before changing code. Keep all
reports/audio captures in ignored `build/`. Inspect the audio object's undefined
symbols/disassembly to ensure the IRQ and its callees never use DIVU; preserve
MACH/MACL in the assembly wrapper. See [PWM validation](validation/pwm.md).

For SRAM/serialization changes, use the current compact-save checks:

```sh
make -j2 host all build/check_save_capacity
python3 tools/check_save.py
./build/check_save_capacity
python3 tools/check_full_game_save.py
python3 tools/check_bank_layout.py
python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so --mode stock
python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so --mode stock --region PAL
python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so --mode extended
python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so --mode mister
```

The extended and MiSTer checks install private bus models after boot; stock
PicoDrive cannot validate extended-mapper autodetection, physical arbitration
or SD export. New SRAM is 32 KiB packed / 64 KiB in PicoDrive's lane-preserving
file layout. Historical fixture tools that assume 128 KiB raw records must be
adapted before use with this ROM. The host allocation retains its old diagnostic
size to keep old clear/hash helpers safe, but only 32 KiB is addressable through
the save API. See [SRAM validation](validation/sram.md). Never replace a user's real save as part of a test. Earlier save formats are
intentionally unsupported in this build.

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
clean gameplay initialization. Its historical old-save comparison does not
apply to the current SRAM format; use `--world-only` for that startup check. Evidence and captures
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

Gameplay runs at 25 Hz with the approved 60 Hz animation clock. All eight original floors, 58 rooms and 144 camera views are imported and enabled. Full playthrough validation remains pending. Their camera backgrounds remain raw banked ROM data; static rendering, transparency dithering, door/window/furniture ordering and transition caches have received fixes.

The original startup now runs through the animated Infogrames logo, title,
automatically paged credits, New Game/Resume/Replay Intro menu, original Emily
and Edward portraits, their biographies, and the original scripted arrival.
Menu and portrait controls are documented in README.md. Biographies support
directional paging and A/Start/C to advance; B returns. The arrival is skippable
with A/B/C/Start. Presentation timing does not advance the world during the
frog close-up. Arrival completion or skipping calls fresh gameplay initialization;
intro state and death flags do not carry into the playable world.

All room and camera tables now contain the complete original resources.
`World::intro` selects cinematic behaviour, rather than limiting resource access.
Two auxiliary collision/NPC rooms have no camera in the original data.
New asset IDs are appended; existing model/animation IDs and the original
game fingerprint are preserved. The expanded save format reads old saves.
The picture request fields are
presentation state and are excluded from saves.

UI retains the console controls with original proportional text and the three-section inventory, animated 3D found-body previews, quantities and scrolling arrows. Reading uses original paper/book/notebook art, proportional font, illustrations and page sound. Death plays the original scripted cemetery movie and final picture, with skip/title return and existing saves preserved. Audio includes 101 effects through two-voice 8 kHz ADPCM/PWM and eight AdLib songs adapted to YM2612/PSG. CD LIFE cue IDs map to audited floppy themes. Window script error LIFE 20 word 59 is fixed.

For gameplay text/inventory/death changes, use the focused checks in
`tools/check_gameplay_ui.py`, `tools/check_death.py` and
`tools/check_death_native.py` as documented in
[gameplay UI/death validation](validation/gameplay-ui-death.md).
The historical inventory save comparison uses legacy payloads from the preserved
`build/gameplay-ui-reference/libaitd32x.so` and its asset bank. Preserve those
preceding-release files before rebuilding if that comparison is needed.
That legacy comparison requires adaptation for the new SRAM format.
Host SRAM is private memory; native checks alter only private emulator RAM
to acquire test items or shorten combat and never access battery-save files.

For information-overlay, pickup or menu-response changes, use
`tools/check_menu_messages.py`, `tools/check_pickup.py` and
`tools/check_menu_latency.py .local/tools/picodrive_libretro.so`.
The decoder's constant-match fast path is covered by `make build/check_decode`
and `./build/check_decode`; linked memory/bank constraints use
`tools/check_bank_layout.py`. Menu compositions must write into the existing
RAM background through `BackgroundComposition`, preserving both framebuffer
damage histories. Pause snapshots invalidate the scenery cache on exit.
Presentation input consumes an edge once without advancing world time;
arrival/death scripts retain their 25 Hz update path. Current evidence and
limits are in [menu feedback validation](validation/menu-feedback.md).

One visible save slot uses two compressed 16 KiB SRAM journals. Format
`0x53313602` stores 50 actors, signed-word bone channels and lighting. Earlier
battery saves and emulator savestates are intentionally unsupported. Use a
separate ROM basename for test builds to preserve existing battery files on
the user's device. See [SRAM validation](validation/sram.md).

The historical v15 ROM was near the 4 MiB direct SH2 ROM window. Startup now uses an extension bank for raw arrival cameras and compressed presentation images, reusing existing framebuffer/background scratch. SH2 RAM remains 256 KiB with 12 KiB master and 4 KiB slave stack reservations. Avoid adding global buffers casually. See docs/ARCHITECTURE.md for current layout details and limits. Physical 32X hardware and CD narration remain unvalidated/unimplemented respectively.

## Next priorities

The [renderer architecture investigation](validation/render-architecture-prototypes.md)
records three rejected compositor prototypes and isolated comparisons on the
user's Pi 5. That investigation restored the production renderer byte for byte;
the subsequent accepted [preparation optimization](validation/render-preparation.md)
reduces duplicate work within its existing composition rules. Review that
evidence before repeating color-tile, block-bound or surface-run experiments;
none establishes a path to stable 20 FPS or a smaller cartridge yet.

Adaptive SH2 ownership and asynchronous background repair are documented in
[SH2 scheduling validation](validation/sh2-scheduling.md). Relevant checks:
`make -j2 host build/check_bands all`, `./build/check_bands`,
`python3 tools/check_bank_layout.py`, and
`python3 tools/check_sh2_scheduling_native.py .local/tools/picodrive_libretro.so`
(`--region PAL` selects PAL). The scheduling check changes split limits in
private emulator SDRAM and compares both displayed banks to serial host pixels;
it freezes only the private World::Update function. User battery saves are
untouched. Before changing queue payloads, preserve the preceding ROM/ELF and
host library under ignored `build/` for native comparisons. Restore must finish
before drawing/masking, scenery readback, RAM composition or presentation;
geometry preparation can overlap the outstanding copy. Keep the published
split immutable until END and leave PWM interrupts available.

For the large-ROM EverDrive Pro header/mapper fix, see
[SSF mapper validation](validation/ssf-mapper.md). Use `make -j2`,
`python3 tools/check_bank_layout.py` and
`python3 tools/check_startup_native.py .local/tools/picodrive_libretro.so --short-arrival`
(`--region PAL` selects PAL). The focused
`python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so`
executes the compiled extended-SRAM branch with a page-31 bus shim. The shim
does not model hardware timing, boot autodetection or the cartridge OS's SD
save export. All SRAM is private memory. The ROM must keep its `.32x`
extension; hardware should select SSF rather than 10M. Existing release bundles
remain unchanged; the test bundle lives under ignored `build/hardware-tests/`.

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
2. Play through both characters across the whole game and fix progression, combat, rendering or performance regressions using focused evidence.
3. Validate real hardware audio, SRAM, region timing and sustained performance when hardware is available.

Use small feature/fix branches and reviewable commits. Record build commands and decisions in repository documentation so a new Codex chat can continue from files. Desktop and VS Code may use this same checkout; coordinate active edits.

## Full-game development

See [full-game validation](validation/full-game.md) for current build figures,
coverage and unverified behaviour. Focused checks are
`tools/check_full_game_world.py --reference build/full-game-reference`,
`tools/check_full_game_scripts.py`, `tools/check_full_game_save.py`,
`tools/check_ending.py`, `tools/check_lighting.py`, and
`tools/check_full_game_native.py .local/tools/picodrive_libretro.so`.
For native ending mapping/playback, use
`tools/check_ending_native.py .local/tools/picodrive_libretro.so`;
`--region PAL` selects its PAL run.
Keep `build/full-game-reference/` intact for comparisons. It preserves the
pre-full-game ROM, ELF, host library and bank; user battery saves are never
used as fixtures. Original startup/death and inventory behaviour remains
part of regression coverage.

For shared rendering order or scenery-cache changes, use the focused suite in
[draw-order validation](validation/draw-order.md): `check_world_order.py`,
`check_draw_order_cache.py --sweep`, `check_contact_order.py`,
`check_partial_cache.py`, and `check_draw_order_native.py` with the local core.
The latter compares frozen host/ROM scenes in both physical framebuffer banks;
`--region PAL` selects PAL. These checks use private memory and preserve saves.
The historical `check_reported_bugs.py` still assumes the old startup/interaction
fixtures and does not pass unchanged in this complete-game checkout; its old
report is historical evidence. Current hallway/hatch checks are recorded in the
draw-order report.

For the reported pushed attic cupboard and nearby bedroom door, see
[window/door validation](validation/window-door.md). Use
`check_window_furniture.py` and `check_door_projection.py` for independent
visibility expectations, `check_raster_parity.py --ordinary` after regenerating
prepared props, and `check_window_door_native.py` for frozen cartridge pixels.
Regenerate assets when changing shared world projection/visibility: existing
static programs contain the preceding renderer's output. Cache parity alone
cannot establish correct visibility when both paths share the same mistake.
