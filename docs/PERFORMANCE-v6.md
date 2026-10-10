# Renderer profiling — revision 6

Revision 6 uses both SH-2 processors for rasterization, prepares repeated Q15 rotations once, and reduces edge and span overhead. Revision 4's approved motion, the 25 Hz simulation, stable painter order and one-pixel eyes are preserved. The temporary help panel was hidden during profiling and received no dedicated optimization. Revision 5's report is preserved in `PERFORMANCE-v5.md`.

## Release cartridge results

These are actual RELEASE cartridges running in fresh processes on the **unmodified PicoDrive libretro core**, with the FPS counter enabled. Five-second samples compare camera 0, the same positions and orientation. Independent framebuffer swaps agree with completed game renders.

| Character / region | Position | Revision 5 FPS | Revision 6 FPS | Change |
|---|---|---:|---:|---:|
| Edward / NTSC | Starting position | 20.0 | 25.0 | +25% |
| Edward / NTSC | Close | 20.0 | 22.0 | +10% |
| Emily / NTSC | Close | 20.0 | 20.0 | Unchanged |
| Edward / PAL | Close | 16.6 | 25.0 | +51% |
| Emily / PAL | Close | 16.8 | 25.0 | +49% |
| Edward / NTSC | Far | 25.0 | 25.0 | Unchanged |

Starting position is `(3231,0,-1548)`, Edward close is `(3231,0,-3733)`, Emily close is `(3231,0,-3705)`, and orientation is 0. The far case uses the same backward-to-`z >= 500` benchmark procedure; it is not a fixed-pose pixel comparison. These reproducible views do not reconstruct the exact positions of the user's screenshots. Camera, orientation, projected model size and foreground masks affect cost.

The fresh v5 baseline rebuild matches the distributed v5 ROM byte-for-byte. All six v6 samples advanced 125 logical ticks in five seconds; the fresh PAL Emily baseline advanced 126, reflecting the diagnostic snapshot boundary. Native motion checks for Edward and Emily in PAL and NTSC match the imported animation phase and root displacement, and pause freezes motion. Faster rendering does not change walking or running speed.

## CPU work and presentation

Average milliseconds per completed close NTSC PROFILE draw:

| Master stage | Edward v5 | Edward v6 | Emily v5 | Emily v6 |
|---|---:|---:|---:|---:|
| Pose/camera transforms and projection | 7.56 | 5.14 | 7.69 | 5.33 |
| Stable depth sorting | 3.13 | 3.16 | 3.68 | 3.71 |
| Primitive processing, including master fill and queue waits | 31.73 | 22.92 | 31.83 | 23.66 |
| Master polygon fill | 27.50 | 11.16 | 27.19 | 11.90 |
| Background damage restoration | 2.22 | 2.21 | 2.64 | 2.64 |
| Foreground masks | 1.83 | 1.82 | 1.98 | 1.98 |
| FPS overlay | 0.61 | 0.61 | 0.61 | 0.61 |
| Framebuffer flip wait | 2.27 | 9.70 | 0.92 | 11.37 |
| Entire draw and flip, excluding simulation | 49.38 | 45.63 | 49.37 | 49.37 |
| Draw critical path, excluding flip wait | **47.11** | **35.93** | **48.45** | **38.00** |

The draw critical path falls by about 24% for Edward and 22% for Emily. The master-fill row measures only its upper 100 logical rows in v6; the slave draws the lower 100 concurrently. It therefore does not represent total raster work or a directly comparable full-model fill reduction. Primitive processing includes clipping, dispatch, copying commands, master filling and waiting for free queue entries. Slave work overlaps the master; adding the two CPUs' times would overstate frame duration. Fill is nested inside primitives, which is nested inside the whole frame.

The isolated single-CPU raster changes reduced close fill to 23.57 ms for Edward and 23.66 ms for Emily before distributing the work. Prepared rotations and the exact SH-2 Q15 helper reduced the transform stage by about 2.4 ms. The combined build obtains the larger CPU reduction by overlapping the two row bands.

VBlank synchronization converts CPU savings into discrete presentation intervals. A faster draw can spend more time waiting to flip, which explains Emily's unchanged 20 FPS in close NTSC despite less CPU work. Both close PAL benchmarks reach the 25 Hz update rate. The current NTSC close cases still miss some logical-update presentations. Faster filling and projection remain useful, but the remaining command traffic and shared memory bandwidth also matter.

## Accepted changes

- Exact DDA setup skips division for known integer quotients and one-row edges. Original-direction rounding is encoded in the initial fractional phase, removing its per-scanline correction. Next edge coordinates and remainders are stored once. Span loops share a branch between two word stores, and triangle rows advance a framebuffer pointer. Coverage, damage bounds and zero-color writes remain exact.
- Camera and bone-group rotations prepare sine/cosine coefficients once for repeated vertices. Rotation order, Q15 products and signed truncation stay unchanged. The SH-2 helper implements division by 32768 with sign bias and fixed shifts/rotate-through-carry, retaining the seventeenth quotient bit across the full signed 32-bit input range.
- The master owns logical rows `[0,100)` and the slave owns `[100,200)`. Both process overlapping primitives in the same stable painter order. Conservative vertical bounds avoid sending or drawing primitives that cannot touch an owner's rows. Whole-row ownership separates the word read/modify/write needed for palette-index-zero endpoints.
- A fixed eight-entry command ring carries copied projected points and parameters through cache-through SDRAM. The slave copies each payload to private scratch before acknowledging its slot. An end-of-frame token publishes completed damage before the master merges it, applies foreground masks and flips. No shared cached payload alias, heap, z-buffer or hardware autofill is used.

Fixed row 100 performed better than tested fixed splits at 90, 110 and 120, and an adaptive projected-model midpoint. The accepted code keeps the measured fixed split.

## Profiling limits

PROFILE reads each SH-2's local SH7604 free-running counter at internal clock /128. A separate `picodrive-frt` core implements a counter-only shim that counts PicoDrive's modeled cycles, including waits. Conversion uses PicoDrive's quantized 2.4× 68000 clock model and checks calibration against VBlank elapsed time, within 2%. Per-polygon instrumentation and worker counters add overhead and are removed from RELEASE. Use the unmodified-core table for delivered FPS. These are emulator measurements; no physical 32X performance result is claimed.

Cache-through sharing follows the SH7604 hardware manual's section 8.5.3 because the CPUs' caches do not snoop one another. The 32X hardware manual confirms that zero-byte framebuffer writes are ignored; word stores retain their required behavior. Physical bus contention and final hardware compatibility still require a console test.

## Correctness and artifact identity

Host rendering matches v5 in **966 exact pixel/palette comparisons** across both protagonists, camera travel, orientations and near clipping. **1,147 differential raster cases** preserve pixels, both damage rectangles, restored backgrounds and framebuffer guards. **1,200 band comparisons** across six splits and 3,432 primitive calls preserve pixels, damage unions and row ownership, including zero-color endpoints and sphere fallbacks. The compiled native Q15 helper matches signed C division in **458,752 boundary, adjacent and deterministic-random comparisons** across the signed 32-bit range.

The combined PROFILE cartridge matches the actual v5 native NTSC reference cartridge in 40 frozen poses per protagonist. The final RELEASE cartridge also matches in **160 native comparisons**: 40 poses × both protagonists × PAL/NTSC, with all five cameras and both completed framebuffer banks. All release reports identify the final distributed ROM hash. These comparisons are separate from the host-only serial worker path; details are in `VALIDATION.md`. These checks preserve the implemented renderer and do not establish full FITD material or sphere parity.

Release ROM: 720,896 bytes (704 KiB), checksum `0x5B3C`, SHA-256 `29c8fcdd7f39a396b2657280f1220511a464823fe5897f9bd667dee637f169a5`.

The immutable asset bank is unchanged. The loaded SH-2 module is 23,460 bytes and BSS is 85,324 bytes. Static SDRAM usage is 108,784 bytes, ending at `0x0601A8F0`; 136,976 bytes remain before the reserved stacks at `0x0603C000`. The worker ring and private scratch occupy 4,876 BSS bytes. The slave's largest raster stack frame is 2,172 bytes; its nonrecursive call path fits the 4 KiB reserve.

A fresh source-archive extraction regenerated assets from the original installation and reproduced the distributed release ROM, asset bank and resource IDs byte-for-byte. `validation/source-archive-rebuild-v6.json` records the result and hashes of the verified build inputs.

## Reproduce

Run each native case in a fresh process:

```sh
make BUILD=RELEASE MARSDEV=/path/to/mars
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --label release-v6
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --character emily --label release-v6
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance middle --label release-v6
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance far --label release-v6
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --region PAL --label release-v6
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --distance near --region PAL --character emily --label release-v6
```

For stage timings, use `BUILD=PROFILE` and the timer-capable core described in `PERFORMANCE-v3.md`. Changing build mode recompiles SH-2 objects.

For host and raster comparisons:

```sh
make host check build/check_raster build/check_bands
python3 tools/compare_renderer.py /path/to/v5/build/libaitd32x.so build/libaitd32x.so
./build/check_raster build/raster-v6.txt
./build/check_bands
```

Compare the raster report with v5's report using `cmp`. `tools/check_q15_native.py` builds its own isolated diagnostic cartridge and verifies native arithmetic. Native motion and frozen rendering checks use `tools/check_movement.py` and `tools/native_render_check.py`; consult their `--help` for project, toolchain, character and region arguments. JSON profiles, release samples and correctness reports are preserved in `docs/validation/` as `profile-v6-*`, `single-v6-*`, `release-v6-*`, `release-v5-final-*` and the comparison reports listed in `VALIDATION.md`. Original DOS animation timing is in `TIMING.md`.
