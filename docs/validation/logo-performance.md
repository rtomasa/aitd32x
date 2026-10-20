# Logo and base-renderer review — 2026-10-20

Baseline: alpha.4, commit `3bcd342852bf281e8ec2a0ab36a15cde70703220`.
The player-front door experiment is rolled back. Accurate door ordering,
contact correction and ordinary triangle exclusions are restored. The changes
retained here preserve the sampled pixels and apply to shared renderer paths.

## Findings and retained changes

The rotating armadillo uses ordinary software geometry and rasterization.
Its model contains 192 vertices and 227 primitives: 136 triangles, 86 quads
and five lines. It has no skeletal groups. `Game::StartupDraw()` does not run
room streaming, gameplay LIFE, collision or contact correction for this model.
The slow logo therefore demonstrates a base-renderer cost independently of
bathroom doors. Its angle follows the independent 60 Hz animation clock;
rendering is not capped by the 25 Hz gameplay simulation.

Three focused changes are retained:

- Clear the static logo out of the existing RAM background once on entry to
  rotation. Subsequent frames restore only the moving model's damage, instead
  of restoring the static logo and clearing the upper 320×141 pixels every draw.
  Both physical framebuffer banks receive a full initial restore.
- Reuse polygon acceptance and bounds already calculated by `SortFaces()`.
  `DrawActor()` copies accepted polygon projections without repeating their
  near-plane and viewport checks. Lines, points and other primitive types retain
  their existing checks. This applies to ordinary models throughout the game;
  stable face order, masks and contact-depth arithmetic remain unchanged.
- Batch `Renderer::Box()` clipping, restore fencing and damage updates. Full-width
  rectangles use the existing contiguous aligned word writer; partial rectangles
  retain the shared span rasterizer. This also applies to other UI rectangles.

`Box()` executes from protected ROM to keep the static SDRAM allocation within
its existing stack reserve. No cache-mode, animation-clock, gameplay, asset,
audio-driver or save-format changes are included.

## Matched MiSTer results

An isolated diagnostic runs six identical fixtures on PicoDrive and the user's
MiSTer, using core `S32X_20260603.rbf` at 60 Hz. Each case warms up for one second,
then measures at least three seconds. The low-overhead RELEASE harness times
complete drawing and flip separately. Report screenshots carry raw counters,
a checksum and a frozen-frame pixel hash; those hashes match baseline, candidate
and PicoDrive for all five frozen cases. The live case is excluded from frozen
pixel comparison. Diagnostics use separate ROM basenames and no battery saves.

| Case | Baseline draw time | Candidate draw time | Baseline FPS | Candidate FPS |
| --- | ---: | ---: | ---: | ---: |
| Frozen large logo, rotation step 0 | 53.41 ms | 36.14 ms | 15.0 | 20.0 |
| Frozen smaller logo, step 60 | 50.44 ms | 32.57 ms | 18.90 | 30.0 |
| Live starting room, initial message | 52.19 ms | 51.23 ms | 15.0 | 15.0 |
| Frozen starting room, no message | 41.03 ms | 39.77 ms | 20.0 | 20.0 |
| Frozen bathroom corridor, door angle 96, accurate contact | 123.55 ms | 121.29 ms | 7.5 | 7.5 |
| Frozen floor 3, room 1, camera 3 | 56.84 ms | 56.44 ms | 15.0 | 15.0 |

Draw time excludes framebuffer flip wait and world updates. FPS measures
completed draws including those operations. Frozen fixtures measure rendering
capacity at specific poses; they are not complete animated-logo or gameplay
averages. VBlank presentation boundaries make FPS changes discontinuous.
Small gameplay timing differences should not be treated as a significant
whole-game improvement. **The broader gameplay slowdown remains unresolved.**

For the same baseline cases, PicoDrive draw times are respectively 27.03,
24.45, 30.59, 23.88, 78.35 and 31.89 ms. PicoDrive therefore understates these
MiSTer drawing costs; its emulator FPS alone is insufficient to judge an
optimization intended for MiSTer.

A separate PROFILE diagnostic attributes the large logo's MiSTer time:

| Scope | Mean time per draw |
| --- | ---: |
| Restore submission/master copying | 4.18 ms |
| Geometry transformation/projection | 5.07 ms |
| Face visibility/sorting | 6.33 ms |
| Primitive execution, including fill/worker coordination | 22.72 ms |
| Fill, already included in primitive execution | 15.23 ms |
| Per-frame clear, including its restore fence | 15.47 ms |
| Complete drawing, excluding flip | 54.57 ms |
| Framebuffer flip wait | 12.05 ms |

These are inclusive scopes, not independent costs to add together. The clear
scope includes waiting for asynchronous background restoration. Instrumentation
also changes timing slightly; the preceding RELEASE table is authoritative
for the comparison. The clear/restore overlap is a demonstrated avoidable
cost, while geometry, primitive execution and coordination still consume
substantial time. These counters do not isolate cartridge-bus stalls from
instruction/data cache misses or establish a cycle-accurate CPU utilization.

The frozen starting-room profile spends about 6.43 ms transforming, 6.01 ms
sorting and 19.16 ms executing primitives; queue waiting is 6.06 ms inside that
work. The floor-3 case spends about 12.05 ms transforming, 10.02 ms sorting and
17.41 ms waiting inside primitive execution. The bathroom retains expensive
contact correction in addition to ordinary drawing. Further gameplay work
should target this shared geometry/command path and contact preparation using
matched MiSTer measurements; the logo improvement is not a door-stall fix.

## Rejected experiments

Disabling data-cache allocation while retaining instruction allocation
(`CCR 0x11 → 0x15` after purge on both SH2s) makes MiSTer much slower: the
frozen starting-room draw rises from 41.03 to roughly 140 ms, while PicoDrive
barely changes. The normal cache setting is retained. This supports investigating
memory locality, not globally disabling the data cache. Register semantics are
from the [SH7604 hardware manual, section 8](https://antime.kapsi.fi/sega/files/sh7604.pdf).

Packing cached world projections into signed 16-bit coordinates preserves the
sampled pixels but gives no meaningful MiSTer FPS gain. A convex-quad raster
prototype saves about 3 ms in the bathroom fixture but also leaves its FPS
unchanged and slightly regresses another sample. Neither is adopted; the
existing preview scratch representation and raster coverage rules are retained.
The ordinary face-check reuse alone saves approximately 1 ms in several cases;
its benefit is modest compared with removing the logo's redundant framebuffer
work. Rectangle batching alone raises both sampled logo cases to 20 FPS.

## Validation, memory and playable build

Validation passed:

- `make -j2 all host`, linked bank/layout checks and `git diff --check`.
- 2,660 exact-pixel comparisons against the preserved accurate renderer across
  all 144 cameras, both characters and sampled framebuffer histories.
- 604 logo pose/bank comparisons, including forward/reverse rotation history,
  and 150 rectangle cases, including black, clipped edges and RAM composition.
- 16 native cartridge scenes in PicoDrive NTSC/PAL: both characters, bathroom
  doors from either side and attic furniture; both framebuffer banks match host
  pixels. These use private SRAM fixtures, not user battery files.
- Focused native boot in both regions: original static logo/title/menu pixels,
  phase timing and visible rotating logo. No unrelated full-game suite is run.
- The six MiSTer diagnostic cases complete without reported world faults;
  frozen framebuffer hashes match the accurate baseline.

RELEASE ROM remains 14,155,776 bytes. Assets are byte-identical to alpha.4
(SHA-256 `94c7dc55da69f2445bbafd7e1f6531cb67f2e0c878328305a30ad4645a7dfe6e`).
The loaded module falls from 84,724 to 84,708 bytes; BSS remains 160,704 bytes.
Static SDRAM ends at `0x0603BEA8`, leaving 344 bytes before the reserved 12/4 KiB
master/slave stacks, compared with 328 bytes before. No new buffer is allocated.

Playable ROM: `build/AITD32X-render-review.32x`, SHA-256
`9ad58eaed3cd9841467c5601af7e640d3131a2d9a838542a0c56566359b1bc55`.
The same hash is verified on MiSTer at
`/media/fat/games/S32X/AITD32X-render-review.32x`, and the game is left at the
original start menu. Its new battery filename receives a copy of the existing
save only because that destination did not exist. Hashes of the original save,
the earlier door-test save and `S32X.CFG` remain unchanged. Menu capture:
`build/renderer-review/mister-menu.png`.

It uses the ordinary game entry point; diagnostic ROMs are separate. Local
source, counters, screenshots and rejected variants remain under ignored
`build/renderer-review/`. MiSTer is FPGA-core validation, not a physical 32X
measurement. Full-game visual review and physical hardware testing remain open.
No commit or GitHub release is made.
