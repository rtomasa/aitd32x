# Renderer architecture investigation — 2026-10-17

## Outcome

Three alternative contact compositors were implemented and measured. None
provides enough improvement to replace the current renderer. The production
sources, ROM, ELF and host library have been restored to the exact baseline;
the rejected implementations remain under ignored `build/scene-compositor/`.
This investigation does **not** achieve or establish stable 20 FPS throughout
the game. It also does not rule out a larger rendering redesign.

The Raspberry Pi 5 was reached using the user's local deployment settings.
Tests loaded its installed `/opt/replay/cores/picodrive_libretro.so` directly
through a private headless libretro harness. No frontend configuration, running
frontend, installed game ROM or user battery save was modified. The tests and
private fixtures live in `/opt/aitd32x/scene-compositor-20261017`.
This is Pi-hosted **emulator evidence**, not physical 32X validation or a test
of the frontend's display/audio scheduling.

## Measured results

Edward, NTSC, production gameplay scripts and controller actions following
diagnostic placement. Action and hallway windows are five seconds. Completed
draws are counted over emulated VBlanks, not host execution time.

| Workload | Baseline, local | Color tiles, local | Baseline, Pi | Color tiles, Pi |
| --- | ---: | ---: | ---: | ---: |
| Attic chest pushing | 15.0 FPS | 15.0 FPS | 15.0 FPS | 15.0 FPS |
| Downstairs door, full interaction | 19.8 FPS | 19.8 FPS | 19.8 FPS | 19.8 FPS |
| Settled hallway after room entry | 11.8 FPS | 12.0 FPS | 11.8 FPS | 12.0 FPS |

The local room-entry draw interval falls from 200 to 183.3 ms with color
tiles. Input release follows completed frames, so the crossing position and
subsequent simulation batching differ slightly. These short traces do not
establish a repeatable 16.7 ms saving in every transition. Settled chest rates
vary by one draw over three seconds between the two emulator builds; that is
not evidence of a general speed improvement.

The Pi executes each complete headless fixture in about 1.6–2.4 host seconds,
including startup and more than ten emulated seconds. These tests therefore
show an emulated rendering bottleneck, rather than the Pi simply failing to
execute this headless workload in real time. Frontend settings remain outside
that conclusion.

## Alternatives tested

**Deferred color tiles.** Keep exact reciprocal-depth comparisons, shade into
two 64×32 color tiles in dead projection storage, then publish final covered
color runs to the framebuffer. Uncovered pixels remain untouched; black is
opaque and glass/masks preserve their holes. Compact primitive bounds and
separate CPU-owned scratch preserve CONTACT/END ownership. This is the color
candidate in the table. It changes framebuffer traffic but retains ordinary
scene drawing followed by contact correction.

**Conservative span bounds.** Add minimum/maximum depth bounds for 16-pixel
row blocks. Proven front spans avoid depth reads; proven hidden spans are
rejected. Ambiguous spans retain exact per-pixel checks. The local hallway
falls to 11.2 FPS. Bounds maintenance, dispatch and code-placement costs
outweigh the saved comparisons in this fixture. This candidate was rejected
before further Pi testing.

**Visible surface runs.** Replace each depth tile with two-byte `(end, owner)`
run records naming the winning primitive. Affine depth comparisons resolve
entire spans where possible. Quantized ties and crossings use exact pixel
comparisons; points, lines, masks and glass are retained. Final runs are
written once. The local hallway falls to 6.8 FPS: run splitting, copying and
repeated winner evaluation are too expensive for this workload. It was also
rejected before Pi testing.

## Correctness and memory

- Color tiles match the preserved renderer in 2,660 sampled comparisons across
  all 144 camera views and both characters, with zero pixel differences.
- Contact ordering passes 64 comparisons, including an intervening foundable
  object and diagnostic ownership colors.
- The NTSC linked color candidate matches host pixels at forced SH2 ownership
  extremes for six character/scene combinations and both framebuffer banks.
- The run compositor passes 1,200 synthetic tile cases against the retained
  pixel renderer, including intermediate results, quantized depth crossings,
  black, glass, masks, clipped tiles and scratch guards. It also passes the
  contact-order cases and the 60 focused preserved-renderer comparisons.
- All six Pi baseline/candidate fixtures finish without LIFE/mapper faults.

The color candidate adds no persistent BSS allocation; both color tiles reuse
existing projection storage after geometry preparation. Its BIOS-loaded
module nevertheless grows from 84,756 to 85,076 bytes, reducing the static
stack margin from 328 to **8 bytes**. Fallback/setup code moves to protected
ROM to fit. The padded cartridge remains 14,155,776 bytes. The tiny remaining
margin and negligible sustained gain are additional reasons not to adopt it.
No asset identities, save schema or simulation/animation clocks were changed.

Restoration reproduces the baseline ROM, ELF and host library byte for byte.
The restored layout check passes with the original 328-byte margin. ROM hash:
`691dfce0283d2b9e48a2e20fb533b3b5650f1f96dccd5f5e3aa26f89197854d1`.

## Implications for the next design

The tested alternatives replace the final contact compositor. They do not
remove the earlier ordinary actor draw, its geometry preparation or later
foreground replays. A substantially different engine pipeline remains an
untested hypothesis. The existing [stage measurements](action-performance.md)
still point to those repeated passes and new-view scenery construction.

The next architectural prototype should evaluate a scene plan that selects
ordinary or depth-resolved drawing before shading. It must avoid adding a
third geometry pass merely to discover bounds. Outside contact regions it
must retain painter output; inside them it must preserve architectural mask
erasures, glass, intersecting surfaces and intervening objects. These are
correctness requirements, not optional work that can simply be bypassed.

A complementary asset-compiler experiment is to prepare rigid props' camera
geometry/depth commands, extending the existing prepared-color programs.
Matching camera/pose keys could avoid repeated transforms and depth-gradient
setup. Moving, skeletal and differently masked objects still need appropriate
runtime handling. Extra data must be measured against both the fixed ROM
window and the eventual 7 MiB cartridge target; pre-rendering every pose is
not an established solution.

At 20 FPS the complete frame has about 50 ms. The recorded optimized hallway
already spends about 39 ms in contact work, alongside ordinary drawing and
simulation. A replacement must demonstrate a substantial reduction in total
frame work, with RAM/ROM headroom, before house-wide integration is justified.

## Evidence and reproduction

Compact hashes, layout and measured windows are in
[render-architecture-prototypes.json](render-architecture-prototypes.json).
Local experiment trees and their binaries are preserved in:

- `build/scene-compositor-reference/`: unmodified baseline.
- `build/scene-compositor/color-tile-compositor/`: Pi-tested color candidate.
- `build/scene-compositor/run-compositor/`: rejected surface-run candidate.
- `build/scene-compositor/pixel-compositor-experiments/`: span-bound experiment.
- `build/scene-compositor/color-tile-compositor.patch`: reviewable color change.

The first two candidate trees retain a focused `check_contact_tiles` target;
the private trace harness/fixtures are preserved in
`build/scene-compositor/pi-bundle/` and
`build/action-performance-7d87383/measure.py`. These ignored artifacts contain
original game resources and must not be added to Git or published as source.

The cache checker now accepts `--reference-library` for independent exact-pixel
comparisons without changing its normal cached/uncached oracle. For example:

```sh
python3 tools/check_draw_order_cache.py --sweep \
  --library build/scene-compositor/color-tile-compositor/build/libaitd32x.so \
  --reference-library build/scene-compositor-reference/build/libaitd32x.so \
  --output build/scene-compositor/color-reference.json
```
