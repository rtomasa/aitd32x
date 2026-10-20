# Bathroom door investigation — 2026-10-20

Baseline: `v0.1.0-alpha.4`, commit
`3bcd342852bf281e8ec2a0ab36a15cde70703220`. **The player-front experiment
has been rolled back.** Production source again uses alpha.4's accurate door
ordering, contact-depth correction and triangle deferral. The faster prototype
is preserved separately for comparison. The earlier Mega Drive background
prototype also remains discarded; original assets are unchanged.

The current work prioritizes the shared renderer. See the completed
[logo and base-renderer review](logo-performance.md) for MiSTer measurements,
the pixel-preserving changes retained and the remaining gameplay bottleneck.
The results below describe the historical door experiment, not current behavior.

## Player-front gameplay test

The user explicitly accepts arm/hand clipping during door interactions and
requests a playable performance test before a full door-by-door visual audit.
In that prototype, gameplay room-door leaves precede the player in painter order. Player/door
pairs skip contact-depth correction and the corresponding deferred triangles;
complete ordinary player geometry is drawn instead. This applies to opening,
closing and stationary leaves, avoiding a second change of visibility policy
as a door settles. No geometry-separation test or per-camera exceptions are
installed yet.

The six original door bodies are 25, 34, 143, 144, 177 and 178, covering 43
original object records on floors 1–3. These include ordinary left/right
leaves, the entrance leaves and kitchen leaves. This is a model-based policy,
not a bathroom-only optimization. It excludes cabinet doors, chests, windows,
floor hatches and the non-swinging underground obstacle. Other actors retain
their relative painter order and furniture contact correction remains active.
Doors are also excluded from intervening members of the player's furniture
contact groups, so those groups cannot silently restore door/player correction.
Scripted arrival/death/ending drawing retains the preceding policy.

The accepted tradeoff can make the player appear over a nearer door, including
more than a hand in an unfavorable camera/pose. Full visual review and any
exceptions are deferred until after gameplay testing. Collision, scripts,
25 Hz simulation, 60 Hz animation, save format and audio drivers are unchanged.

User feedback after the MiSTer gameplay test confirms better performance with
fewer stalls, but reports image glitches. Their extent/cause has not yet been
classified as accepted limb clipping versus another composition issue. Further
door changes were superseded by the [shared renderer review](logo-performance.md). The
relaxed policy is no longer active in the production checkout.

Paired stock PicoDrive NTSC live-route results:

| Measurement | Alpha.4 | Player-front doors |
| --- | ---: | ---: |
| Corridor-side swing, mean draw interval | 116.7 ms | 68.4 ms |
| Bathroom-side swing, mean draw interval | 55.6 ms | 39.8 ms |
| Full eight-second approach/open/enter route | 19.625 FPS | 22.0 FPS |
| Full eight-second open/exit route | 19.875 FPS | 23.25 FPS |
| Settled corridor after exit, three seconds | 15.67 FPS | 20.0 FPS |
| Sampled bathroom-exit/corridor-entry interval | 183.3 ms | 133.3 ms |

Swing means select completed draws whose observed door angle is strictly
between 0 and 256: 17/29 samples entering and 36/49 exiting, before/after.
These are live comparisons; presentation poses and simulation batches differ.
They do not establish a minimum FPS or predict exact MiSTer timing. The remaining
first-frame scenery-bake cost is not removed by this change.

Validation passed:

- `make -j2 host all` and the linked bank/layout check.
- `tools/check_door_render_policy.py`: 284 ordering checks covering all 43
  original leaves; 900 bathroom route comparisons against the same-policy
  uncached renderer for both characters and alternating framebuffer histories;
  no contact group for the isolated door/player scene through sampled opening
  and closing angles. This is not the deferred complete visual clipping audit.
- 60 focused cache/composition checks and 64 independent furniture contact-order
  comparisons, with zero differences in the latter.
- 16 native cartridge scenes across NTSC/PAL: both characters, closed/swinging
  bathroom views from either side and attic furniture. Both physical framebuffer
  banks match reloaded host pixels. Private SRAM fixtures use the current
  32 KiB packed / 64 KiB odd-lane transport; no battery file is used.

The RELEASE module grows from 84,724 to 84,932 bytes (+208); BSS remains 160,704
bytes. The free gap before the reserved 12/4 KiB master/slave stacks falls from
328 to 120 bytes. Door ordering executes from protected ROM. No image, pose or
depth buffer is added. The padded ROM remains 14,155,776 bytes and assets are
byte-identical to alpha.4.

Test ROM: `build/AITD32X-door-player-front.32x`, SHA-256
`f40f63450c73a85230411f39e70f95686452e04074a8bfa41bb496335f53e0f8`.
Detailed traces, native checks and layout evidence remain under ignored
`build/door-performance/player-front-*`. No commit or GitHub release is made.

## Reproduction and costs

The bathroom is floor 1, room 3, cameras 11/12. Its door is object 29 in the
adjacent corridor, room 1, camera 3. Private fixtures place Edward at
`(-710, 0, -700), beta 0` in the corridor or `(1100, 0, 1700), beta 512` in the
bathroom. Real Up input then runs for eight seconds, using original movement,
collision and LIFE scripts. Fixtures use private host/core SRAM; battery files
are never opened. The world and animation clocks are unchanged.

Stock PicoDrive NTSC, completed draws measured over emulated VBlanks:

| Measurement | Alpha.4 | Diagnostic with contact correction bypassed |
| --- | ---: | ---: |
| Corridor-side swing, mean draw interval while door angle is between 0 and 256 | 116.7 ms | 68.4 ms |
| Corridor-side swing, largest sampled interval | 166.7 ms | 133.3 ms |
| Full eight-second approach/open/enter route | 19.625 FPS | 22.0 FPS |
| Idle before corridor approach | 20.0 FPS | 20.0 FPS |

The swing samples contain 17 and 29 completed draws respectively. Faster
rendering changes which simulation states are presented; these are live route
comparisons, not timing comparisons of identical frozen poses. The full route
average conceals the much slower door-swing episode.

Leaving the bathroom on alpha.4 produces a 183.3 ms corridor-entry draw
interval. An isolated PROFILE build with a timer-enabled PicoDrive core
attributes approximately 87.8 ms to scenery-cache construction, 61.98 ms to
contact correction and 18.87 ms to ordinary drawing on that entry frame.
Camera binding/image preparation accounts for about 3.14 ms. Inclusive scopes
overlap and must not be added together. Timer calibration is approximately
1.002 against elapsed VBlanks.

During the corridor-side swing, representative profiled draws spend about
47–52 ms in ordinary rendering and 35–62 ms in contact correction. The first
moving pose additionally rebuilds the scenery cache to remove the formerly
baked door. Routine simulation/script/activation costs are much smaller.

The engine does not load and unload rooms from storage at these boundaries.
Room metadata, scripts and models are already in cartridge ROM. Camera changes
bind a new raw image and rebuild visible scenery. A loading transition could
cover that one-time operation, but would not remove the sustained swing cost.

## Can the player always be drawn in front?

Collision bounds and visible animated geometry are different inputs. A
proximity test alone is insufficient reason to perform depth correction, but
collision alone does not establish that every player surface is nearer than
every door surface from both camera directions.

The diagnostic bypass disables both contact correction and its ordinary-pass
triangle exclusions, leaving complete painter rendering. A separate host
comparison runs 225 simulation/draw steps in each direction for both characters
and both framebuffer histories. Flat diagnostic colors distinguish door and
player surface ownership; prepared color programs are disabled only in this
private copied asset bank. No original asset is changed.

Of 900 sampled states, 238 differ from alpha.4 with those uniform colors. In
189 states the existing depth renderer places door pixels over player pixels
that the painter-only diagnostic leaves visible. Maximum such ownership
differences are 80/32 pixels for Edward entering/exiting and 126/35 for Emily.
These are comparisons with the current depth renderer, not an independent DOS
visual oracle or proof that every current contact group is necessary. They do
show that bypassing the pass changes door-edge occlusion, rather than merely
changing shading within one model.

The initial proposal was a cheap geometric ordering test with an accurate
fallback. The user subsequently chose the simpler policy above, explicitly
accepting clipping to prioritize performance before reviewing exceptions.

## Other isolated prototypes

Three candidates intended to preserve rendering were built and sampled:

- Build static coverage lists on first foreground use instead of during every
  new scenery bake. The sampled bathroom-exit interval falls from 183.3 to
  166.7 ms, but the mean swing interval remains 116.7 ms. One later camera
  change becomes slower. This moves some work rather than eliminating it.
- Publish winning depth pixels in spans using the existing aligned writer.
  Mean swing interval is 115.7 ms: insufficient improvement. The larger code
  also requires moving cold combat code to ROM to retain the stack reserve.
- Measure moving-prop bounds before ordinary drawing to extend existing
  triangle deferral. Mean swing interval remains 116.7 ms; the additional
  preparation consumes the saving.

Each candidate passes 2,660 sampled exact-pixel comparisons across 144 camera
views and both characters against the preserved host renderer. Those checks do
not exhaust moving-door poses. None of these three candidates was adopted.
Their source, ROMs, detailed traces and captures remain under ignored
`build/door-performance/`, separate from the player-front gameplay test.

## Device scope

These performance measurements are emulator evidence only. The separately
named gameplay ROM is uploaded to MiSTer as
`/media/fat/games/S32X/AITD32X-door-player-front.32x`. Its battery file is a copy
of the existing user save under the new basename; the original save, ROMs and
S32X configuration are preserved. The user subsequently confirmed fewer stalls and reported image glitches. The uploaded ROM's hash was verified and it reached
the original start menu on MiSTer; the capture is retained as
`build/door-performance/player-front-mister-ready.png`. It was left running for that earlier test; the current playable build is
`AITD32X-render-review.32x`, with accurate clipping restored. This confirms startup, not device gameplay timing or audio
quality. No physical 32X performance claim is made.
