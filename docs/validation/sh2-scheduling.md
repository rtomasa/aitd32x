# Adaptive SH2 ownership and background overlap

## Scope

Implemented ordinary-model and contact-depth load balancing plus overlap of
background repair with geometry preparation. The design was informed by the
[Virtua Racing 30 FPS patch](https://github.com/AlbertoBen/sega-vr-disasm/blob/30fps-patch/VR30FPS.md),
reviewed at `39a3e13`. This port uses its own queue, rasterizer and timer-driven
balancing; no Virtua Racing game code or assets are incorporated.

Ordinary drawing measures master submission/raster time excluding queue stalls
and slave raster time. Three agreeing samples with more than 25% imbalance move
the boundary by four rows, bounded to 20–180. Contact depth independently adapts
the fraction of its repair rectangle assigned to each CPU (10%–90%). Jobs keep
the published boundary until END; actors retain their mask and scratch fences.
Both paths retain painter order, zero-color writes and glass dithering.

For background repairs of at least eight rows and 512 words, the slave restores
the lower half while the master restores the upper half. Vertex generation,
projection and sorting can continue while that copy remains pending. The
same repair path covers gameplay, startup, menus, inventory/pickup previews,
death and the ending. Preview rasterization remains serial. Small repairs and
RAM compositions stay synchronous.

A restore token joins before framebuffer writes/readback, image replacement,
RAM composition or a flip. The slave reads background data through an uncached
alias; the master cannot modify it until completion. Commands are copied before
ring entries are released. Audio interrupts remain enabled throughout.

## Build and focused checks

- `make -j2 host build/check_bands all`: passes RELEASE and host builds. The
  existing RWX linker warning remains; no new C/C++ warnings.
- `./build/check_bands`: 200 cases, 12 boundaries, 2,400 comparisons and 6,600
  primitive calls; pixels, damage, row ownership and guards match. Cases include
  glass, zero-color primitives, ordered overlaps and offscreen edges.
- `check_sh2_scheduling_native.py`: NTSC and PAL, both characters, attic glass,
  bedroom door and a contact-depth group containing an intervening item. Forced
  splits at 20/100/180 and contact shares at 10%/50%/90% match serial host pixels
  in both displayed framebuffer banks. Reports:
  `build/sh2-scheduling-native-{NTSC,PAL}.json`.
- `check_window_door_native.py`: sampled closed/rotating doors, cupboard/window,
  hallway and opposite-camera scenes match host pixels in both banks, NTSC.
- `check_full_game_native.py`: sampled scenes across all eight floors, original
  background pixels, both framebuffers, mapper and live updates pass, NTSC.
- `check_startup_native.py --short-arrival`: logo/title/menu pixels, both
  biographies, short arrivals, skip, banked images with nonzero audio and
  private-SRAM save/restart pass, NTSC.
- `check_bank_layout.py`: protected-ROM helpers, assets, mapper and stack limits
  pass. `git diff --check` passes.

All native checks use PicoDrive libretro and private SRAM/SDRAM. They neither
read nor write user battery files and do not establish real 32X/MiSTer behavior.
The forced-boundary check changes ownership between emulator slices, including
when a draw may be in flight; already published jobs keep their row bands.

## Performance observations

Comparison uses the immediately preceding SSF ROM preserved under
`build/sh2-overlap-reference/`, with identical assets and private scene fixtures.
Evidence: `build/sh2-scheduling-performance.json` (NTSC).

| Measurement | Before | After |
|---|---:|---:|
| 10-second natural early-game trace | 24.3 draws/s | 24.2 draws/s |
| Frozen floor 3, room 1, camera 3 | 19 draws/s | 19 draws/s |
| Frozen floor 6, room 0, camera 2, lantern | 19 draws/s | 29 draws/s |
| Frozen arrival floor 7, room 1, camera 3 | 29 draws/s | 29 draws/s |
| Character selection, right | 4 VBlanks | 3 VBlanks |
| Inventory selection, down | 7 VBlanks | 6 VBlanks |

Other sampled menu changes retain their previous 3–7 VBlank latency. Frozen
scene pixel hashes match between builds. These short measurements are display
quantized and are not whole-game speed guarantees. The natural trace remains
near the unchanged 25 Hz simulation cadence; its update counts differ by one
at the measurement boundary (252 versus 251). No simulation/animation clock
code changes. The floor-6 result measures frozen renderer capacity, not gameplay
at 29 simulation ticks/s. MiSTer v260603 US/NTSC previously reported 17.4 FPS
in the starting room versus 25 in PicoDrive; this new ROM needs a matched
MiSTer retest before claiming an improvement there.

A later [matched instrumented MiSTer/PicoDrive comparison](mister-performance.md)
reproduces the slowdown and measures draw work, queue waits and audio contention
using an isolated automatic diagnostic. Its added profiling overhead means
those figures do not replace the production measurements above.

The subsequent [MiSTer optimization experiments](mister-optimization.md) retain
the production scheduling policy: fixed splits, serial drawing and synchronous
restoration do not improve the sampled FPS. The selected change instead reduces
shared text-rendering cost, with scoped gains while messages are visible.

## Memory and artifacts

RELEASE ROM remains 14,155,776 bytes. BIOS module is 84,468 bytes (+48), BSS
160,672 bytes (+32), static end `0x0603BD98`, stack margin 616 bytes (previously
696). Camera setup and worker control/copy helpers moved to protected ROM to
fit without reducing stacks. There is no extra image/depth buffer, actor state,
asset change, mapper change or save migration. PROFILE was not built in this
focused validation; these linked memory figures apply to RELEASE.

ROM SHA-256:
`c471f52cd536360b3df7c50266f98d25ebd66912be369f6a5c84513556a813e0`.
The rebuilt candidate is `build/AITD32X.32x`. Existing release/test bundles and
the ignored `.local/baseline` remain intact. No commit was created.
