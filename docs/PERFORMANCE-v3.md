# Renderer profiling — revision 3

This document records revision 3’s renderer investigation. In that revision the simulation continued at 25 Hz and the movement/animation code remained unchanged from revision 1. Revision 4 subsequently corrected animation time units using measurements from the original DOS executable; see `TIMING.md`. Its close NTSC benchmark still produces 12 FPS and 125 simulation ticks in five seconds.

Revision 3 corrects both protagonists' eyes and reduces measured rendering costs. Type-2 body primitives are tiny points: FITD's `renderPoint` uses screen-space size 0.3, whereas its type-7 zixel is a separate perspective-sized primitive. Revision 2 incorrectly gave the eyes an invented 32-unit billboard footprint. Each eye now draws one native pixel, including close to the camera. Display scaling enlarges that pixel along with the rest of the image.

## Release cartridge measurements

Five-second stationary intervals after moving to three positions in attic camera 0, measured on the **unmodified** Linux PicoDrive libretro core. Each case runs in a fresh process. Framebuffer swaps are counted independently and agree with completed game renders.

| Character / region | Position | Revision 2 FPS | Revision 3 FPS | Change |
|---|---|---:|---:|---:|
| Edward / NTSC | Far | 15.0 | 20.0 | +33% |
| Edward / NTSC | Starting position | 13.6 | 17.0 | +25% |
| Edward / NTSC | Close | 8.6 | 12.0 | +40% |
| Emily / NTSC | Close | 8.6 | 12.0 | +40% |
| Edward / PAL | Close | 8.4 | 12.6 | +50% |

The close positions are identical between revisions: Edward `(3231,0,-3734)` and Emily `(3231,0,-3711)`, orientation 0. The starting position is `(3231,0,-1548)`. The far position varies by 18 original world units at the input-release boundary (`z=548` versus `530`), less than one rendered pixel in this view. These are reproducible benchmark positions, not a reconstruction of the exact player coordinates in the supplied screenshots.

Every interval advanced 124–126 simulation ticks, consistent with 125 ticks in five seconds and the diagnostic snapshot's one-render boundary lag. The separate PAL/NTSC pause check advanced exactly 250 ticks in ten seconds. Render performance remains below the 25 Hz simulation rate in the close view; this revision improves it without claiming the performance problem is fully resolved. Other cameras and orientations have different costs.

## SH-2 stage timings

`BUILD=PROFILE` uses the master's SH7604 free-running counter at internal clock /128. Reads use the required high-byte/low-byte latch order. Timings accumulate in `profile_state`, published after each completed frame. A scope must finish before one 16-bit counter wrap (~356 ms on an NTSC 32X). This profiling code is absent from RELEASE builds.

The bundled PicoDrive source does not implement the FRC. `tools/picodrive-frt.patch` adds a counter-only profiling shim with the internal divider and byte latch; it does not implement compare, capture, interrupts or a full FRT. Profile measurements used this separate core. The normal core was used for the release FPS results above. The shim counts PicoDrive's modeled SH-2 cycles, including elapsed wait time. PicoDrive defaults to a quantized 2.4× 68000 clock to approximate latency; the tool uses that model for milliseconds and checks it against VBlank time. Timer calibration differed by 0.12% on NTSC and 0.59% on PAL. These are emulator estimates, not physical hardware cycle measurements.

Edward, NTSC, same close position, average milliseconds per completed frame:

| Stage | Revision 2 profile | Revision 3 profile |
|---|---:|---:|
| Simulation update batch | 1.08 | 0.77 |
| Background damage restore | 2.21 | 2.20 |
| Pose/camera transform, including shared projection in v3 | 6.49 | 7.77 |
| Stable depth sort | 6.02 | 5.97 |
| Primitive clipping/projection/dispatch, excluding polygon fill | 12.35 | 4.52 |
| Polygon fill | **67.03** | **47.79** |
| Foreground masks | **15.76** | **1.79** |
| FPS overlay | 0.61 | 0.61 |
| Framebuffer flip wait | 5.02 | 11.78 |
| Entire draw + flip, excluding simulation | 115.52 | 82.46 |

The primitive total includes polygon fill; the table subtracts fill to avoid double counting. Transform in v3 includes projection once per shared vertex. Flip waits can increase as rendering gets faster because the next VBlank boundary changes. Per-polygon timer calls and profiling bookkeeping add overhead, so the separate release measurements are the performance result to use.

Polygon fill accounts for about 58% of the original close frame's draw/flip time, followed by mask restoration at about 14%. Simulation is small and keeps up. The remaining dominant cost is polygon filling, followed by transforms/sorting and synchronization. The slave still performs its heartbeat; it does not rasterize the scene.

## Changes made from the measurements

- Polygon intersections divide only during edge setup, then advance with integer additions and remainder carries. Signed truncation matches the previous division-based scan converter, including reversed edges and off-screen clipping.
- Shared vertices are projected once. Polygons crossing the near plane retain the original clipping and projection path.
- Active foreground runs restore background pairs directly rather than calling a one-pixel span for every pixel. Palette index zero still uses word writes when needed.
- Nonzero span endpoints use the 32X's byte writes to avoid framebuffer reads. Zero endpoints preserve their neighboring pixel with a word write.
- Remaining edge-setup and perspective divisions use the SH-2's signed DIVU. A conservative explicit 39-cycle wait is included, so emulator implementations with instant division do not report an artificial speedup.

A corrected-eye reference build using the old fill/projection/mask code matched the optimized host renderer exactly in **966 pixel and palette comparisons**, covering both characters, camera transitions, orientations, close placements and near-plane cases. This verifies preservation of the previous renderer's pixels; it does not establish full FITD rendering parity. Eye close-up captures are host renderer diagnostics, while attic/window and benchmark captures come from the actual cartridge.

## Reproduce

Release FPS, without timer support:

```sh
make BUILD=RELEASE
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance far
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --character emily
```

For stages, apply `tools/picodrive-frt.patch` to the PicoDrive source used here and build a separate core:

```sh
patch -p1 < /path/to/AITD32X/tools/picodrive-frt.patch
make -f Makefile.libretro -j2 TARGET_NAME=picodrive-frt use_libchdr=0 GIT_REVISION=aitd32x
```

Then, from the game source:

```sh
make BUILD=PROFILE
python3 tools/profile_renderer.py /path/to/picodrive-frt_libretro.so --distance near --label profile-v3
make BUILD=RELEASE
```

Changing build mode automatically recompiles SH-2 objects. `--region PAL`, `--character emily` and `--project /path/to/another/source-root` select other cases/builds. The tools write JSON reports and native screenshots into `build/`. Machine-readable before/after results are preserved in `docs/validation/`.

The existing top-left FPS meter continues to count completed game frames over about one second. It excludes redraws solely for static title/pause counters and remains separate from the simulation clock.
