# Renderer profiling — revision 5

Revision 5 specializes triangle filling and replaces the full insertion depth sort with stable merged runs. The accepted revision-4 movement/animation clock, collision, controls and one-pixel eyes are retained. The temporary help panel was hidden during these measurements and received no dedicated optimization.

## Release cartridge results

Actual SH-2 cartridges measured on the **unmodified PicoDrive libretro core**, with the FPS meter enabled. Each five-second stationary case runs in a fresh process. Independent physical framebuffer swap counts agree with completed game renders.

| Character / region | Camera-0 position | Revision 4 FPS | Revision 5 FPS | Gain |
|---|---|---:|---:|---:|
| Edward / NTSC | Starting position | 17.2 | 20.0 | 16% |
| Edward / NTSC | Close | 12.0 | 20.0 | 67% |
| Emily / NTSC | Close | 12.0 | 20.0 | 67% |
| Edward / PAL | Close | 12.4 | 16.6 | 34% |

Positions match exactly between builds: start `(3231,0,-1548)`, Edward close `(3231,0,-3733)`, Emily close `(3231,0,-3705)`, orientation 0. These are reproducible camera-0 benchmark views; they do not reconstruct the exact positions in the user's screenshots. FPS varies with camera, orientation, protagonist size and foreground masks. The original v4 source was rebuilt and reproduced the supplied v4 ROM byte-for-byte before comparison.

All intervals advanced 124–125 logical ticks, consistent with 25 Hz and the diagnostic snapshot's one-render boundary lag. Separate native movement checks passed for Edward and Emily in both PAL and NTSC: displacement and animation phase agree with imported root motion, and pause freezes both. Renderer improvements have not changed their walking/running speed.

## What the profile found

Average milliseconds per completed close NTSC draw, measured with `BUILD=PROFILE`:

| Stage | Edward v4 | Edward v5 | Emily v4 | Emily v5 |
|---|---:|---:|---:|---:|
| Polygon fill | **47.81** | **27.50** | **43.66** | **27.19** |
| Stable depth sort | 6.00 | 3.13 | 8.94 | 3.68 |
| Pose/camera transform and shared projection | 7.55 | 7.56 | 7.69 | 7.69 |
| Primitive clipping/projection/dispatch, excluding fill | 4.50 | 4.23 | 4.94 | 4.64 |
| Background damage restoration | 2.22 | 2.22 | 2.63 | 2.64 |
| Foreground masks | 1.83 | 1.83 | 1.98 | 1.98 |
| FPS overlay | 0.61 | 0.61 | 0.61 | 0.61 |
| Framebuffer flip wait | 11.90 | 2.27 | 11.95 | 0.92 |
| Entire draw + flip, excluding simulation | 82.44 | 49.38 | 82.43 | 49.37 |

Fill remains the largest stage. Its reduction is 42% for Edward and 38% for Emily; sorting falls by 48% and 59%. The FPS overlay remains about 0.61 ms per render, around 1.2% of the new complete close frame. VBlank synchronization quantizes presentation rates; a smaller CPU cost does not always produce a proportional FPS change, particularly between PAL and NTSC.

The profiler reads the SH7604 free-running counter at internal clock /128. The separate `picodrive-frt` core implements a counter-only shim; it counts PicoDrive's modeled SH-2 cycles, including elapsed waits. The conversion uses PicoDrive's quantized 2.4× 68000 clock model and checks against VBlank elapsed time. Calibration remains within 2%. Per-polygon instrumentation adds overhead and is removed from RELEASE. These are emulator measurements; physical 32X performance has not been measured. Use the unmodified-core release table for the resulting FPS.

## Accepted renderer changes

- Triangles advance their two active edges directly between vertex rows. The former generic path checked every edge and sorted intersections on every scanline. Active Edward bodies contain 208 triangles/3 quads; Emily contains 230 triangles/23 quads. Quads and larger near-clipped polygons retain the general scan converter.
- Triangles accumulate the bounds of actually written, clipped spans and commit damage once per primitive. Background restoration therefore covers exactly the same rectangle as before.
- An edge starting at an on-screen vertex uses that endpoint directly, avoiding an unnecessary initial division. Top-clipped edges retain the division. The original directed edge's signed truncation correction, half-open Y coverage and inclusive span endpoints are preserved.
- Depth sorting first uses insertion sort in four-face runs, then stable merges. Equal-depth primitives keep their original order. Fixed 2 KiB SDRAM scratch replaces repeated shifting of the whole face list; no heap or z-buffer is added.
- Span stores retain nonzero endpoint byte writes and zero-color word writes that preserve neighboring pixels on the 32X.

A portable Q15 transform experiment was rejected because the SH-2 compiler retained its expensive shift helper and timings regressed. The accepted build leaves transform math unchanged. No hardware autofill or slave rasterization has been introduced.

## Correctness and artifact identity

The combined renderer matches v4 in **966 exact framebuffer/palette comparisons**, using both original protagonists, camera travel, orientations and near-plane placements. An additional **1,147 differential cases** compare pixels, both damage rectangles and the restored background: flat/reversed/degenerate triangles, extreme clipping, general quads, overlapping primitives, and zero/nonzero endpoint colors. AddressSanitizer, UndefinedBehaviorSanitizer and framebuffer guards passed this raster coverage. The differential checks establish preservation of the existing renderer; full FITD material/sphere parity remains unverified.

Runtime timing/movement files are byte-identical to v4. The final packaged source rebuild regenerates its original-game assets and reproduces the v5 ROM byte-for-byte.

Release ROM: 720,896 bytes (704 KiB), checksum `0xC91C`, SHA-256 `51166d0f1b708ffe92477ec06b0a326acc6d3da035f8f48f199243bede1e8707`.

The immutable asset bank is unchanged. The loaded SH-2 module is 21,300 bytes; BSS is 80,452 bytes. The static SDRAM working set ends at `0x06018D78` (101,752 bytes), below the linker-enforced stack reservation. The added sort workspace accounts for 2,048 BSS bytes.

## Reproduce

Release measurements, in fresh processes per case:

```sh
make BUILD=RELEASE MARSDEV=/path/to/mars
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --label release-v5
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --character emily --label release-v5
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance middle --label release-v5
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --region PAL --label release-v5
```

For stage timings, apply `tools/picodrive-frt.patch` to the PicoDrive source and build the separate core as described in `PERFORMANCE-v3.md`. Then use `BUILD=PROFILE` and pass that core to the same commands. Changing build mode automatically rebuilds SH-2 objects.

For differential rendering, build the v4 and v5 host libraries, then run:

```sh
make host build/check_raster
python3 tools/compare_renderer.py /path/to/v4/build/libaitd32x.so build/libaitd32x.so
./build/check_raster build/raster.txt
```

Build and run v4's raster report with the same `tools/check_raster.cpp` and v4's renderer:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -I/path/to/v4 tools/check_raster.cpp /path/to/v4/src/render/render.cpp /path/to/v4/src/render/font.cpp -o build/check_raster_v4
./build/check_raster_v4 build/raster-v4.txt
cmp build/raster-v4.txt build/raster.txt
```

JSON profiles, release samples, native movement checks and differential raster reports are preserved in `docs/validation/`. Previous rendering measurements are in `PERFORMANCE-v3.md`; original DOS animation timing is in `TIMING.md`.

The next renderer target remains triangle filling, followed by transforms. Any future hardware-fill or slave work should be measured against this baseline and verified on physical hardware before claiming cycle accuracy.
