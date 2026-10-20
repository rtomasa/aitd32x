# Batched model rotations — 2026-10-20

This focused pass follows the [logo/base-renderer review](logo-performance.md).
The preceding playable build is `9ad58eaed3cd9841467c5601af7e640d3131a2d9a838542a0c56566359b1bc55`.

## Change

`Actor_Vertices()` now rotates each contiguous model/group vertex range with
`RotateVertices()`, instead of calling the scalar rotation function for every
vertex. Each enabled axis processes the whole range, avoiding repeated function
calls and axis selection. It retains the exact Y/X/Z order and signed Q15
truncation after each axis. Parent/descendant rotation and anchor translation
order are unchanged. Identity rotations do no vertex work.

The shared actor path covers characters, props, contact-geometry preparation and
inventory/pickup models. Camera projection, SH2 commands, adaptive row ownership,
accurate door clipping, assets, audio, saves and the 25/60 Hz clocks are unchanged.
No persistent geometry cache or additional buffer is introduced.

## Results

One candidate uses the existing six-case MiSTer diagnostic, with one second of
warmup and at least three seconds of measurement per case. The baseline is the
preceding pass's matched diagnostic. Frozen hashes match that baseline and
PicoDrive in all five frozen cases; the live case is excluded from pose parity.

| MiSTer case | Before draw time | After draw time | Before / after FPS |
| --- | ---: | ---: | ---: |
| Frozen large logo, step 0 | 36.14 ms | 35.63 ms | 20.0 / 23.74 |
| Frozen smaller logo, step 60 | 32.57 ms | 32.09 ms | 30.0 / 30.0 |
| Live starting room, message | 51.23 ms | 50.34 ms | 15.0 / 15.0 |
| Frozen starting room, no message | 39.77 ms | 39.35 ms | 20.0 / 20.0 |
| Frozen bathroom, accurate door contact | 121.29 ms | 120.12 ms | 7.5 / 7.5 |
| Frozen floor 3, room 1, camera 3 | 56.44 ms | 56.51 ms | 15.0 / 15.0 |

Drawing excludes simulation and flip wait; completed FPS includes them. These
short windows do not establish a sustained gameplay improvement or the complete
rotating animation's FPS. VBlank boundaries and adaptive balance can change FPS
more than the small mean draw-time difference suggests. The floor-3 result is
essentially unchanged. **The broad gameplay slowdown and door stalls remain.**
PicoDrive shows approximately 0.4–1.2 ms less drawing work in the same cases.

## Focused verification and limits

To limit testing cost, only this candidate and the relevant checks were run:

- RELEASE/host build and linked bank/layout check.
- 190,472 exact vertex comparisons against scalar rotation, all eight enabled
  axis combinations, empty/single/maximum ranges and untouched boundary guards.
- 60 scene pixel comparisons against the preceding host renderer; no full-house
  sweep or historical suite was rerun.
- Eight native PicoDrive NTSC scenes covering both characters, bathroom doors
  from either side and attic furniture; both framebuffer banks match host.
  Fixtures use private SRAM. No queue/timing protocol changed, so the preceding
  PAL/ownership matrix was not repeated.
- One MiSTer six-case comparison; frozen hashes and reported world faults pass.

This is MiSTer FPGA-core and emulator evidence, not physical 32X validation.
No complete playthrough or renewed preview/UI matrix was performed. The
arithmetic check covers all axis combinations used by the shared geometry path.
Raw evidence and source/reference builds are ignored under `build/geometry-pass/`
and `build/renderer-review/rotation-batch/`.

The loaded module grows by 288 bytes, from 84,708 to 84,996. BSS remains 160,704
bytes. Static SDRAM ends at `0x0603BFC8`, leaving 56 bytes below the reserved
12/4 KiB stacks. That static margin is very tight; future additions must pass
the linker/layout checks. The stack reserves themselves are unchanged.
ROM remains 14,155,776 bytes, and the asset bank is unchanged.

Playable build: `build/AITD32X-geometry-batch.32x`, SHA-256
`dab1c65d75369833454987acb8c6a53647d8fc4f5d672d382d7e3335b74430c4`.
The ROM is uploaded under that basename to MiSTer. The new save filename
receives a copy of the preceding `AITD32X-render-review.sav` without overwriting
any existing battery file. Original save/config hashes are unchanged before and
after deployment. The ready capture is `build/geometry-pass/mister-ready.png`.
No commit or release is made.
