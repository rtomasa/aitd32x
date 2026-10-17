# Render preparation and duplicate drawing — 2026-10-17

This change reduces repeated work in the existing renderer. It improves the
sampled sustained slow scenes, but does not establish a whole-game minimum FPS
or eliminate the remaining interaction and room-entry costs. The preceding
[architecture investigation](render-architecture-prototypes.md) rejected three
alternative contact compositors; these measurements use that restored renderer
as the baseline.

## Paired Pi 5 results

Edward, NTSC, RELEASE, original LIFE scripts and actual controller actions after
diagnostic placement. FPS counts completed draws over emulated VBlanks. Idle
and chest-settling windows last three seconds; action and hallway-settling
windows last five seconds. Both ROMs ran against the same installed PicoDrive
core through a private headless libretro harness on the user's Pi 5.

| Workload | Before | After |
| --- | ---: | ---: |
| Settled hallway after sofa-room entry | 11.8 FPS | 14.8 FPS |
| Standing near attic chest | 20.0 FPS | 23.0 FPS |
| Actively pushing chest | 15.0 FPS | 15.4 FPS |
| Settled after pushing chest | 18.3 FPS | 22.0 FPS |
| First downstairs door, full interaction | 19.8 FPS | 20.0 FPS |
| Settled away from that door | 25.0 FPS | 25.0 FPS |

The hallway improves by approximately 25%. Its first three draw intervals
change from 200/100/83.3 ms to 183.3/83.3/66.7 ms. Input release follows completed
frames, so crossing positions and simulation batching differ slightly. These
short samples do not promise the same saving in every room transition.

Local PicoDrive reproduces the hallway, action and post-push figures. Chest
idle measures 24 FPS locally, versus 23 on the Pi, and its baseline post-push
rate is 18 rather than 18.3 FPS. The same ten-second early-game input trace
averages 24.3 FPS before and after, with identical simulation/animation segment
states. Native eight-floor smoke checks still include a live scene at 10 FPS:
this is a focused improvement, not a solution for every slow area.

Each Pi fixture executes in approximately 1.6–2.4 host seconds including startup
and more than ten emulated seconds. The measured rates describe emulated 32X
work, not host wall-clock FPS. The frontend, installed game and battery saves
were left untouched; SRAM fixtures existed only in the headless process.
Tests are staged at `/opt/aitd32x/contact-plan-20261017`. These are **emulator
results**, with no physical 32X, MiSTer or frontend audio/display validation.

## Shared implementation

- Reject invisible gameplay polygon faces before sorting. Preserve stable order
  among surviving faces and the original preview path.
- For an animated contact source with exactly one nearby settled prop and a
  guaranteed bounded correction group, omit ordinary triangle pixels inside
  that prop's bounds. Contact depth supplies those pixels later. Preserve the
  original actor bounds, other primitive types, and complete ordinary drawing
  for ambiguous or moving contacts.
- Seek sorted architectural mask rows instead of scanning whole masks per
  tile. Prepare activation once per contact actor. Apply the same row seeking
  to ordinary masks and fallback depth masks.
- Cache settled-prop depth commands in unused scenery-span storage when one
  source owns the group. Reuse static transforms, reciprocal depths and
  gradients, while preserving exact primitive order. Scene/camera/order/pose
  changes invalidate programs. Insufficient storage or multiple sources use
  normal preparation; failed builds are remembered until invalidation.
- Reconstruct omitted static vertices before near-plane or capacity fallback.
  Slave jobs consume only the normal prepared scratch under existing fences.

The paths apply throughout the game wherever these conditions hold. No scene
IDs, reduced geometry, altered assets or simulation-rate changes are used.
Pushing still requires dynamic prop work; larger reductions there need another
measured optimization.

## Memory and cartridge

| RELEASE allocation | Before | After |
| --- | ---: | ---: |
| ROM bytes | 14,155,776 | 14,155,776 |
| BIOS-loaded module bytes | 84,756 | 84,612 |
| BSS bytes | 160,672 | 160,696 |
| Static SDRAM end | `0x0603BEB8` | `0x0603BE40` |
| Margin below reserved stacks | 328 bytes | 448 bytes |

BSS grows by 24 bytes for the slave surface exclusion rectangle and cache
epoch/padding. Face sorting, panel drawing and effects dispatch move to protected
ROM, reducing the loaded module by 144 bytes. Mask plans temporarily use 400
master stack bytes; the master/slave reservations remain 12/4 KiB. No image or
depth buffer is added. The full 3,072-entry color-span capacity is retained;
contact programs opportunistically borrow only its unused tail.

The cartridge still requires the existing banked extension. Compression below
7 MB was not part of this rendering change. Saves remain compatible; neither
the 25 Hz simulation nor independent 60 Hz animation clock changes.

## Validation and reproduction

Both host and RELEASE builds pass. The native linker retains its existing RWX
segment warning. Relevant checks passed:

- 2,660 exact framebuffer comparisons over 144 cameras/both characters against
  the preserved renderer, and another 2,660 against an uncached scene oracle.
  The reference sweep exercises 309 program builds and 59 warm cache hits.
- 30 preserved-renderer comparisons covering both buffers, moving characters,
  changed static poses/keys, warm-hit near-plane fallback, zero storage and
  undersized storage. Failed programs are not rebuilt on each frame.
- 64 three-model contact-depth ordering comparisons; partial scenery repair
  parity; all 1,106 ordinary prepared-prop programs (2,212 pixel/coverage
  comparisons plus three moved/rotating fallbacks).
- 2,400 primitive split comparisons plus 192 independent deferred-triangle
  cases, including black/glass, and render/mask/effects checks.
- NTSC/PAL native SH2 ownership extremes and both-bank comparisons, gameplay
  menus/previews, eight-floor native smoke coverage and the unchanged ten-second
  input trace. Bank/protected-ROM layout passes.

The row-seeking prerequisite was verified for all 632 imported masks and their
78,304 spans. Existing assets and import formats are unchanged.

To compare a future candidate, preserve the earlier host library and ROM/ELF
outside release/baseline directories, then run the focused checks:

```sh
make -j2 host all build/check_render build/check_bands
./build/check_render
./build/check_bands
python3 tools/check_bank_layout.py
python3 tools/check_draw_order_cache.py --sweep --reference-library /path/to/reference/libaitd32x.so
python3 tools/check_prepared_contact_cache.py --reference /path/to/reference/libaitd32x.so
python3 tools/check_sh2_scheduling_native.py .local/tools/picodrive_libretro.so
python3 tools/check_sh2_scheduling_native.py .local/tools/picodrive_libretro.so --region PAL
```

[Machine-readable evidence](render-preparation.json) records hashes and compact
results. Detailed local outputs are retained under ignored `build/contact-plan/`;
the original private action harness remains under
`build/action-performance-7d87383/`. No generated ROM, asset bank or save is added
to Git, and no commit is made by this change.
