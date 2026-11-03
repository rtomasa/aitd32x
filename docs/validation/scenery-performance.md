# Scenery construction and Amiga-port review — 2026-11-03

Two shared changes are retained: compose scenery directly in the existing RAM
background, and replace per-pixel line divisions with exact incremental steps.
They reduce forced scenery-rebuild costs, but do not resolve sustained door
contact slowdowns. The sampled bathroom crossing intervals remain unchanged.

## What the other project contributes

Reviewed [Vesuri/aloneinthedark](https://github.com/Vesuri/aloneinthedark/tree/12330586b6a927e2a8439a10bc894a0a1a25afb6)
at commit `12330586b6a927e2a8439a10bc894a0a1a25afb6`. Its
[design](https://github.com/Vesuri/aloneinthedark/blob/12330586b6a927e2a8439a10bc894a0a1a25afb6/docs/design.md)
runs original Macintosh 68k instructions through native Amiga services. It is
not a replacement C++ gameplay renderer that can be transplanted into this port.

Useful findings from its
[performance review](https://github.com/Vesuri/aloneinthedark/blob/12330586b6a927e2a8439a10bc894a0a1a25afb6/docs/performance.md)
and [implementation notes](https://github.com/Vesuri/aloneinthedark/blob/12330586b6a927e2a8439a10bc894a0a1a25afb6/docs/development.md):

- Dirty rectangles are combined into disjoint horizontal bands before aligned
  conversion. Our single enclosing damage rectangle can restore untouched gaps
  between distant actors. A bounded band planner is a useful future candidate,
  provided both framebuffer histories and mask erasures remain covered.
- Actor-mask copies reject disjoint bounds early. Exact geometry-result caches
  avoid rebuilding mutable Mac regions. Our importer already converts immutable
  masks to sorted spans, and contact rendering already prepares activation and
  seeks relevant rows. A second 32 KiB region cache would duplicate work that
  is absent here and exceed our available RAM.
- Its original engine draws offscreen before publishing bounded copies. That
  supports reconsidering our framebuffer-to-RAM scenery round trip. The retained
  implementation below is independently written; no upstream code is copied.
- Trap dispatch, chunky-to-planar conversion, disk read-ahead and Paula sample
  preparation have no direct equivalent in our native indexed-framebuffer and
  cartridge-resident world pipeline. They do not explain our door stalls.

## Retained implementation

Full scenery rebuilds and partial static-order repairs now render into the
existing 64,000-byte RAM image, then restore the framebuffer from it. They no
longer upload the original background, draw static props into framebuffer RAM,
and read those pixels back. Coverage, masks, black pixels, glass and the normal
fallback renderer remain active. This applies throughout the house.

Both SH2s use the cache-through image alias during shared composition. Drawing
finishes before cached image reads resume; the master disables/purges/restores
its cache while preserving the previous configuration. Ordinary UI composition
keeps its cached path. This follows the
[SH7604 manual, sections 8.4.6 and 8.5](https://antime.kapsi.fi/sega/files/sh7604.pdf).
PicoDrive pixel checks do not establish real cache-coherence behavior on hardware.

Ordinary, prepared-depth and fallback-depth lines share an incremental signed
quotient/remainder calculation. It reproduces `start + delta*t/steps`, including
negative slopes and reversed/zero-length lines. Coordinate slopes need no
division; depth slopes can require one setup division instead of one per pixel.
Line helpers execute from protected ROM to retain static SDRAM headroom.

No original asset, save format, collision rule, door visibility policy, 25 Hz
simulation or independent 60 Hz animation clock changes.

## Measurements

Paired local PicoDrive NTSC diagnostics use the FRC-enabled core, a one-second
warmup and at least three seconds per case. Times include complete drawing,
excluding flip and simulation. Frozen hashes match in all five frozen cases.
The forced-rebuild diagnostic clears only the scenery signature before each
draw; these are repeated construction costs, not natural gameplay FPS.

| Frozen workload | Rebuild every draw: before → after | Warm cache: before → after |
| --- | ---: | ---: |
| Starting room, quiet | 76.55 → 73.68 ms | 29.90 → 29.80 ms |
| Starting room, two effects | 78.67 → 76.03 ms | 30.95 → 30.84 ms |
| Near attic scenery, quiet | 83.85 → 80.80 ms | 35.93 → 35.69 ms |
| Near attic scenery, two effects | 87.96 → 84.78 ms | 37.56 → 37.57 ms |
| Floor 3, room 1, camera 3 | 171.58 → 154.55 ms | 30.19 → 30.12 ms |

An isolated RAM-composition-only prototype saves approximately 2.5–3 ms in these
rebuilds. The combined change saves approximately 17 ms in the floor-3 rebuild;
line work can matter much more during construction than in steady rendering.
Warm-cache savings are small. One near-scene sample crosses a VBlank threshold
from 20 to 24 FPS; its 0.24 ms draw saving does not establish that sustained gain.

Stock PicoDrive, original scripts and real Up input after private placement:

| Bathroom route measurement | Before | After |
| --- | ---: | ---: |
| Eight-second approach/open/enter | 19.375 FPS | 19.5 FPS |
| Eight-second open/exit | 20.125 FPS | 20.125 FPS |
| Sampled exit/corridor-entry interval | 183.3 ms | 183.3 ms |
| Sampled entry/bathroom-camera interval | 66.7 ms | 66.7 ms |

These results do not demonstrate a material bathroom improvement. Natural
route poses can differ when rendering speed changes. No new MiSTer or physical
32X measurement, deployment or whole-game performance claim is made.
The separate sofa-room/hallway route also retains its 183.3 ms entry interval
and 14.8 FPS settled sample. This reinforces the distinction between the forced
construction diagnostic and achieved gameplay improvement.

## Validation and memory

- RELEASE/host builds and linked layout pass, retaining the existing RWX warning.
- 2,660 exact preserved-renderer comparisons cover 144 cameras, both characters
  and sampled framebuffer histories. No pixel differences.
- 17,392,057 interpolation samples match independent signed division;
  2,400 band comparisons and 192 deferred-triangle cases pass.
- Six native scenes per region pass in NTSC/PAL, both characters and both
  framebuffer banks, with forced SH2 ownership at rows 20, 180 and 100.
- Partial-order repair checks cover both characters, both banks, masks/glass,
  geometry invalidation and a bedroom/hall route on the RAM-composition candidate.
  The final line arithmetic is additionally covered by the comparisons above.
- Fixtures use private host/core SRAM. The SH2 checker now converts packed
  32 KiB saves to PicoDrive's 64 KiB odd-lane layout; its historical 128 KiB
  assumption previously prevented the check from reaching rendering.

ROM remains 14,155,776 bytes; asset-bank hash remains
`94c7dc55da69f2445bbafd7e1f6531cb67f2e0c878328305a30ad4645a7dfe6e`.
BSS remains 160,704 bytes. The loaded module falls from 84,852 to 84,580 bytes;
static SDRAM ends at `0x0603BE28`, leaving 472 bytes before the unchanged 12/4 KiB
stacks, versus 200 before. Step records use temporary stack storage; no persistent
image, geometry or depth allocation is added.

Evidence: [compact measurements](scenery-performance.json), with detailed outputs
and the preserved reference under ignored `build/scenery-ram/`. Playable ROM:
`build/AITD32X-performance-review.32x`, SHA-256
`c94626606e7b39fedfee7421bd185031c1cf1d984cb4ef2def711fbd89a95c64`.
No commit or release is made.

For a preserved source tree, reproduce cold measurements with
`tools/build_mister_profile.py --source /path/to/source --variant baseline --rebuild-scenery`,
then run `tools/check_mister_profile.py --core .local/tools/picodrive-frt_libretro.so --project build/mister-experiment/baseline-scenery`.
Archive each result before rebuilding that diagnostic path. Omit
`--rebuild-scenery` for ordinary warm-cache measurements. The diagnostic is
separate from the playable cartridge and never opens battery saves.

## Larger changes worth pursuing

The strongest remaining architectural candidate is to select painter versus
contact-depth work before shading, so an interaction does not draw ordinary
pixels, redraw them with depth, then replay foreground props. Geometry prepared
for that decision must survive into the chosen pass; adding another bounds-only
transform would repeat a previously unsuccessful experiment. Keep exact masks,
glass, near-face rejection, intervening actors and bounded fallback behavior.

For room transitions, extend partial scenery repair to static membership/pose
changes, not only painter-order changes. Removing a moving door from the bake
currently reconstructs the complete scenery. This needs old/new footprints,
mask erasures and coverage-storage compaction, rather than just deferring work
to the next frame. A bounded dirty-band planner is complementary.

Prepared rigid-prop depth programs in ROM could reduce cold contact preparation,
but the fixed window has only about 14 KiB left; bulk expansion needs a banking
design or reclaimed space. Existing RAM-tail command caching already handles
warm settled props. None of these larger designs is implemented or claimed as
an achieved improvement by this change.
