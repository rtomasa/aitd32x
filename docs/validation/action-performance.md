# Action performance measurements — 2026-10-12

Measured revision `7d87383`, Edward, NTSC, using the current release ROM in
local PicoDrive. These are diagnostic scene placements followed by actual
controller input and production LIFE scripts, not a complete playthrough or
physical 32X/MiSTer timing validation. Production engine sources and ROM were
not changed during the baseline measurements below. No frontend battery saves were read or written.

## Release results

FPS counts completed draws over emulated VBlanks, rather than host execution
time. Idle and settling windows last three seconds; interaction windows last
five seconds. Room settling uses five seconds. The door rotation subset spans
about two seconds and excludes the closed/open endpoints.

| Scene | Before | During / after action | Largest observed frame interval |
| --- | ---: | ---: | ---: |
| Starting attic chest, camera 3, pushing | 20.0 FPS | 14.8 FPS during five-second push | 100 ms |
| First downstairs door, camera 1, opening | 22.7 FPS | 17.6 FPS while rotating; 19.6 FPS across the entire interaction; 25.0 FPS after settling away from it | 83 ms |
| Sofa room 2, camera 9 → hallway room 1, camera 2 | 25.0 FPS | 11.0 FPS in the hallway | 233 ms on entry, followed by 83–100 ms frames |

The chest moves from Z=300 to Z=-1176. The first downstairs door is object 22;
its verified rotation runs from the original closed angle 256 to open angle
580. Walking towards it triggers its original opening script; input is
released when it reaches the open angle. The transition walks through an
already-open door 33. These setups preserve the original scripts and collision
behavior, but positions/camera angles are not guaranteed to match a user's run.

A second opening fixture, door 33 in the sofa room, changes angle 0 → 513 and
averages 19.4 FPS across its interaction. Its settled rate returns to 25 FPS
after the character withdraws. A separate stationary fixture near the open
first downstairs door produces approximately 12 FPS. Door proximity can
therefore be expensive without a moving door or repeated scenery rebuilds.

## Stage timings

An isolated PROFILE build adds scopes around scene metadata, cache work,
ordinary drawing, contact geometry/raster work, collision, LIFE and actor-pool
refresh. The existing timer-enabled PicoDrive core supplies the missing FRC
counter support. Its published timer progress agrees with the emulated VBlank
clock within 0.21% over continuous measurement windows. No measured draw exceeds
the 16-bit timer's approximately 356 ms wrap interval.

Numbers below are mean master wall time per completed draw in that diagnostic
build. Worker execution and synchronization are included in the enclosing
render phase. They are not separate CPU utilization percentages. Nested scopes
must not be added to their parents: collision/LIFE are inside Update;
DrawList is inside metadata; geometry and raster are inside contact.

| Stage | Chest pushing | First door rotating | Settled hallway |
| --- | ---: | ---: | ---: |
| Game update, including accumulated simulation ticks | 3.82 ms | 2.38 ms | 5.36 ms |
| Ordinary actor drawing and cached foreground replay | 26.49 ms | 33.45 ms | 26.02 ms |
| Contact geometry and primitive preparation | 12.21 ms | 3.47 ms | 12.52 ms |
| Contact rasterization, masks and worker completion | 10.13 ms | 3.12 ms | 32.37 ms |

Chest pushing adds dynamic prop drawing and increases the depth footprint.
Collision costs only about 0.71 ms per draw in that fixture. There is one full
cache build and one order repair over the five-second push, not a full build
every frame. The door's rotating interval is dominated by ordinary model
drawing; its full interaction produces two full cache builds, totaling only
about 36 ms across five seconds in the instrumented run.

The settled hallway makes no full or order-only cache rebuilds during its
five-second window. Contact work still costs about **44.89 ms per draw**,
approximately **53% of its 85.24 ms draw scope**. Actor ordering costs another
6.27 ms, inside the 6.83 ms metadata scope. Collision is approximately 1.21 ms;
LIFE interpretation is 2.19 ms, both inside Update. This sustained slowdown is
primarily rendering work rather than room loading or script execution.

## The room-entry hitch

A second focused diagnostic separates static actor drawing, coverage-list
construction and framebuffer baking. Its entry interval is 250 ms; the stock
core/release interval is 233 ms. Within the diagnostic entry draw:

| Work | Time |
| --- | ---: |
| Camera/background binding and loading | 3.14 ms |
| Full scenery cache build | 142.88 ms |
| ↳ Eleven cached actor draws, including coverage extraction | 137.86 ms |
| ↳ Coverage extraction alone, included in the actor draws above | 33.04 ms |
| ↳ Framebuffer-to-RAM bake | 3.20 ms |
| Ordinary dynamic drawing | 29.80 ms |
| Contact correction | 49.73 ms |

The expensive one-time operation is constructing the new scenery cache.
Copying the background is a small fraction of the hitch. The next frames
remain slow because contact correction continues after the cache is ready.

## Diagnostic contact bypass

For an A/B check, only the private emulator's RAM entry point for
`Renderer::ResolveOverlap` was replaced with a return-false stub. The on-disk
release ROM was untouched. This intentionally removes occlusion corrections;
it is an attribution experiment, **not a proposed game change**.

| Fixture | Normal rendering | Contact bypass |
| --- | ---: | ---: |
| Chest pushing, five-second window | 14.8 FPS | 22.4 FPS |
| Settled hallway, five-second window | 11.0 FPS | 20.0 FPS |
| Stationary near the open downstairs door | 12.0 FPS | 25.0 FPS |
| First door opening, entire five-second interaction | 19.6 FPS | 22.0 FPS |

The first door rotation subset improves from 17.6 FPS to 20.0
FPS in the bypass run. Ordinary drawing remains its larger cost. Controller
release and simulation batching occur between completed draws, so positions
can differ slightly across runs. Bypass results establish the scale of contact
cost; they do not predict the result of a correctness-preserving optimization.

## Recommended order of work

1. Reduce unnecessary contact work using conservative camera-depth separation
   and tighter affected regions; preserve depth correction for intersecting
   geometry. Optimize the remaining depth spans/tiles and avoid repeated
   geometry work where existing scratch storage permits reuse.
2. Reduce static cache construction on camera changes, especially the 33 ms
   coverage extraction and repeated static model work. Investigate reusing
   the existing prepared prop data for coverage without allocating another
   full-screen buffer. Apply equivalent paths across all cameras and props.
3. Improve ordinary dynamic prop drawing and reuse unchanged ordering/bounds.
   This addresses the door rotation and the residual cost of chest pushing.

Further division scheduling or synchronization tuning alone will not remove
the measured 143 ms scenery-build hitch or the hallway's 45 ms contact pass.
Simulation remains on the independent 25 Hz clock; render frames can contain
multiple accumulated updates.

## Implemented follow-up — 2026-10-13

The shared rendering paths now:

- Reuse the last ordinary actor's live camera-space vertices and projection
  when it belongs to the next contact group. The hint is invalidated after
  each contact call; prepared draws and previews never supply a stale hint.
  The reused actor converts first at offset zero, followed by other members.
- Prepare each contact primitive's screen bounds once in the dead compact
  vertex workspace. Tiles skip disjoint commands before building the actor's
  architectural mask. Bounds use uncached slave reads and the existing fences.
- Build prepared-prop cache coverage from the stored color spans, merging
  adjacent colors on a row. Existing bitmap scratch subtracts current mask
  erasures. This avoids rerecording the silhouette while drawing and scanning
  empty parts of its rectangle. Black pixels, glass holes, capacity fallback
  and conditional masks retain their previous behavior.
- Collect ordinary primitive vertices and screen bounds in one traversal.
  The equivalent polygon traversal is shared by inventory/pickup previews.

These conditions apply across all game cameras and actors. They add no
persistent allocation, asset format, save migration or simulation-clock change.
Prepared lookup/cache construction and fallback depth wrappers execute from
protected ROM to leave hot loops in SDRAM. Contact selection, near-plane rules,
depth arithmetic, polygon sorting and per-pixel visibility remain intact.

The same stock-core RELEASE input fixtures produce:

| Fixture | Revision `7d87383` | Optimized build |
| --- | ---: | ---: |
| Chest pushing, five-second interaction | 14.8 FPS | 15.0 FPS |
| First downstairs door, whole five-second interaction | 19.6 FPS | 19.8 FPS |
| Settled hallway, five-second window | 11.0 FPS | 11.8 FPS |
| Largest room-entry draw interval | 233 ms | 200 ms |
| Largest chest draw interval | 100 ms | 83 ms |

Chest idle/settled rates remain 20.0/18.0 FPS; the sofa door interaction remains
19.4 FPS; both door fixtures settle at 25 FPS. The gains are modest and are
subject to VBlank quantization. They are not measured improvements on MiSTer,
Pi/RePlayOS or a physical console.

An isolated PROFILE build using the same timer-enabled core reports:

| Diagnostic work | Baseline | Optimized |
| --- | ---: | ---: |
| Chest action contact geometry, mean per draw | 12.21 ms | 8.06 ms |
| Hallway contact geometry, mean per draw | 12.52 ms | 7.95 ms |
| Hallway contact raster, mean per draw | 32.36 ms | 31.25 ms |
| Room-entry full scenery cache | 142.88 ms | 102.58 ms |
| ↳ Eleven cached draws, including coverage | 137.86 ms | 97.54 ms |
| ↳ Coverage extraction, included above | 33.04 ms | 21.85 ms |
| ↳ Framebuffer bake | 3.20 ms | 3.21 ms |

Timer calibration agrees with VBlank progress within 0.20% in these optimized
windows. The diagnostic's adaptive splits and resulting simulation/draw
sampling can differ from the stock core, as described below. These are wall
cost estimates, not additional independent FPS measurements or CPU-utilization
percentages. The sustained hallway bottleneck remains per-pixel contact work
and ordinary drawing. Its contact pass is still about 39 ms per draw.

Two depth-span experiments (coalesced framebuffer writes and byte-sized mask
chunks) matched the previous rasterizer in 4,000 randomized cases, but reduced
hallway FPS in stock PicoDrive. They were discarded; the production depth
kernel remains unchanged. Coarse distance-only contact bypass was not enabled:
intersecting geometry and intervening painter layers still need correction.

Focused validation passed:

- 2,212 pixel/coverage comparisons for all 1,106 prepared entries, plus three
  moved/rotating fallbacks, against ordinary rendering.
- 2,660 cached/uncached scene comparisons across all 144 cameras and both
  characters, plus a separate 2,660-comparison differential against the
  preserved pre-optimization host library: no pixel changes.
- 64 contact-order comparisons and partial-cache repair fixtures, including
  masks, black pixels, glass and both physical framebuffer histories.
- Native PicoDrive ordinary/contact ownership boundaries at rows 20/180/100
  in NTSC and PAL, both characters and both framebuffer banks; pixels match
  the serial host reference. Native inventory/pickup preview checks also pass.
- RELEASE/host builds, cartridge layout and whitespace checks.

Final RELEASE ROM remains 14,155,776 bytes; assets are unchanged. BSS remains
160,672 bytes, BIOS module is 84,756 bytes, and static SDRAM ends at
`0x0603BEB8`, leaving 328 bytes below the unchanged stack reserve. The BIOS
module ends at physical byte 4,180,548, below the 4 MiB fixed-window limit.
No user save files, original assets or preserved baseline releases were touched.

The final ROM SHA-256 is
`691dfce0283d2b9e48a2e20fb533b3b5650f1f96dccd5f5e3aa26f89197854d1`.
The ignored profiling directory retains `reused-*.json` for final stock-core
results, `optimized-profile-*.json` for stage timings, `optimized-instrumented/`
and `prepare-optimized.py`. The `optimized-*` and `chunked-*` stock results are
intermediate experiments, not the final build. The preserved old library/ROM
is under `build/action-optimization-reference/`; source parity and native
ownership reports remain under `build/action-*.log` and their tool JSON outputs.

## Baseline artifacts and limits

The ignored directory `build/action-performance-7d87383/` contains `prepare.py`,
`measure.py`, the separate instrumented checkout, per-frame JSON, logs and PNGs.
The principal result files are `release-push.json`,
`release-opening-stairs-door.json`, `release-transition.json`,
`profile-push.json`, `profile-opening-stairs-door.json`,
`profile-cache-transition.json`, and matching `no-contact-*` experiments.
Other files retain exploratory near-door fixture measurements.

Preparation builds with `BUILD=PROFILE` against read-only asset symlinks. The
diagnostic alone moves the combat routine to protected ROM to make room for
counters; none of these fixtures engages combat. Its final static SDRAM ends
at `0x0603B8C0`, leaving 1,856 bytes below the unchanged stack reserve; BSS is
161,128 bytes. The baseline production build retained its original 160,672-byte BSS and
8-byte static margin. The follow-up layout is recorded above.

Stock PicoDrive does not implement the FRC needed by these timers. Timer-enabled
and instrumented runs can change adaptive row splits and VBlank quantization:
for example, pushing measures 14.8 FPS in stock release, 15.2 FPS in the
timer-enabled release and 15.0 FPS in the first profile build. Therefore the
stock release supplies the reported FPS and frame gaps; stage timings are
diagnostic estimates. MiSTer, Pi/RePlayOS and physical 32X stage timings remain
unmeasured here. No generic conclusion about every door or room is implied.

Baseline ROM SHA-256 before and after the original measurement:
`c542dcea37c8c4ad1c4c35685c94305165d7f89ce1e8f3b47744629b195b33f6`.
