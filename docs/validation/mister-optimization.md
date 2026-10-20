# MiSTer optimization experiments — 2026-10-20

The measured improvement is in shared original-font rendering. On the user's
MiSTer `S32X_20260603` core, the automatic live starting-room sample improves
from 12.20 to 15.00 FPS, and the frozen near-camera sample from 12.00 to 15.00
FPS. These fixtures contain an initial gameplay message. They do not establish
a general gameplay gain after that message expires, close the complete
PicoDrive/MiSTer gap, or validate a physical 32X.

## Experiment decisions

The [initial profiling report](mister-performance.md) was followed by a RELEASE
renderer harness with only per-frame draw/flip timing. Removing detailed
profiling leaves the sampled baseline essentially unchanged. The difference
from earlier release traces must not be attributed solely to instrumentation:
the scene fixtures, retained message and emulator timer behavior differ.

Eleven matched variants ran in PicoDrive with the existing FRC shim and on
MiSTer, using Edward/NTSC, one second of warmup, at least three seconds of
measurement and four-second report screens. Frozen cases force rendering
without advancing the world; live gameplay retains the 25 Hz simulation and
60 Hz animation clock. Reports include frame counts, timer-calibrated draw
time and scene pixel hashes. Every frozen hash matches its PicoDrive result
and the original baseline across all variants. Live animations are not
expected to have identical hashes at different draw rates.

| Variant | MiSTer observation | Production decision |
|---|---|---|
| Adaptive baseline | Live 12.20 FPS, near 12 FPS | Reference |
| Fixed split at row 100 | No sampled FPS improvement | Retain adaptive scheduling |
| Fixed split at row 140 | No sampled FPS improvement | Retain adaptive scheduling |
| Fixed split at row 60 | Near/two-voice case drops to 10 FPS | Reject |
| Master-only rendering | No sampled FPS improvement | Retain both SH2s |
| Synchronous background restoration | No sampled FPS improvement | Retain overlap |
| Packed 16-bit queue coordinates | Frees about 2 KiB, no sampled FPS gain | Experimental only |
| Packed queue plus sorter in SDRAM | Small draw-time gains, no broad FPS improvement | Experimental only |
| Coarse scene phases | Identifies a large cost outside scene drawing in message fixtures | Investigate text |
| Register-based glyph-row scanning | Live 13 FPS, near 13.33 FPS | Include in text change |
| Glyph scanning plus batched text spans | Live 15 FPS, near 15 FPS | Selected |

The coarse phases also show expensive actor drawing on MiSTer: approximately
37 ms versus 21 ms in PicoDrive in the starting room, and 47 ms versus 28 ms
near the camera. Those costs remain. Queue stalls alone were not a sufficient
explanation or an effective first optimization target in this matrix.

## Selected change

`src/render/book.cpp` implements the proportional font shared by gameplay
messages, startup/biographies, inventory/actions, pickup/pause/save screens and
document text. It previously recomputed a bitmap-byte index and bit mask while
scanning each pixel, repeatedly reading the same row bytes. Every horizontal
glyph run also called `Renderer::Span`, which created a raster surface, fenced
background restoration and committed damage independently.

The new scanner loads only the one to three bytes touched by a glyph row and
scans their bits in a register. Glyph widths are encoded in four bits, so the
maximum is 15 pixels; row starts can have any bit offset. Conditional loads
preserve the original byte boundaries.

One raster surface and completion fence now cover a complete text range, or
one precompiled document-layout line. Damage is committed before returning or
processing the next layout item. Illustration drawing keeps its existing
behavior. Centering, widths, clipping, ellipses, colors, glyph shapes and
background repair remain identical. This uses the shared font path throughout
the game; no text or approved UI behavior was removed.

## Paired measurements

| Case | PicoDrive FPS before / after | MiSTer FPS before / after | MiSTer draw ms before / after |
|---|---:|---:|---:|
| Live starting room | 19.78 / 24.67 | 12.20 / 15.00 | 59.26 / 52.36 |
| Frozen starting room, quiet | 24.00 / 30.00 | 15.00 / 15.00 | 60.44 / 53.42 |
| Frozen starting room, two voices | 20.00 / 30.00 | 15.00 / 15.00 | 65.98 / 58.88 |
| Frozen near camera, quiet | 20.00 / 20.00 | 12.00 / 15.00 | 70.51 / 63.50 |
| Frozen near camera, two voices | 20.00 / 20.00 | 12.00 / 12.00 | 77.35 / 70.30 |
| Frozen floor 3, room 1, camera 3 | 29.83 / 29.83 | 15.00 / 15.00 | 57.14 / 57.37 |

The starting-room fixtures retain a message during measurement; freezing the
world also freezes its expiry. Coarse phase measurements place about 14 ms
outside scene drawing in those MiSTer cases, whereas the floor-3 fixture has
almost no such cost. The text optimization saves approximately 7 ms per draw
in the message fixtures. The floor-3 result is effectively unchanged.

Display-refresh boundaries hide some time savings: a draw can become faster
while waiting longer for its next flip, leaving completed draws/s unchanged.
Two simultaneous repeating voices remain a deliberate stress case rather
than the duty cycle of ordinary alternating footsteps. The audio driver and
its sound-quality fix are unchanged.

These are short diagnostic windows, with screenshots requested roughly every
two seconds. There is no whole-game FPS guarantee or claim that every message
has the same rendering cost. The complete matrix and ROM hashes are in
[mister-optimization.json](mister-optimization.json); raw reports, captures,
build logs and isolated source trees remain under ignored
`build/mister-experiment/`.

## Focused validation

- Release ROM and host library build successfully, with only the existing
  RWX linker warning; linked bank/RAM/ROM limits pass.
- `check_font_spans.py` compares the actual public text/layout functions
  against the preserved pre-change host library: 5,898 complete-frame pixel
  comparisons, codepoints 32–255, all eight bit offsets and widths 1–15,
  black/nonzero ink, clipping, centering, ellipses, both buffers and all 181
  imported document/biography-layout pages. Synthetic font modifications exist
  only in private host memory.
- `check_menu_messages.py` passes message position/color and both-buffer
  cleanup for messages, pause and reading screens, with the world paused.
- `check_gameplay_ui.py --native-only` passes NTSC and PAL in stock PicoDrive:
  startup/biography navigation, inventory text/actions, rotating previews,
  static UI retention, both framebuffers and paused world state.
- All six selected diagnostic cases complete without world faults on MiSTer
  and PicoDrive. Frozen scene hashes match across platforms and the baseline.

No renderer/worker algorithm changed in production, so the rejected scheduling
variants did not become release changes. No original assets, save fields,
simulation clocks or audio code changed. The checks use private emulator/host
RAM and never write fixtures to a user's battery save.

## Memory and delivery

Release ROM remains 14,155,776 bytes. The loaded module remains 84,724 bytes,
BSS 160,704 bytes and static SDRAM end `0x0603BEB8`, leaving the same 328 bytes
below the reserved stacks. Fixed ROM code grows by 224 bytes, from 69,176 to
69,400, within its 128 KiB region. No tables, image buffers or heap were added.

Compiler stack reports show `DrawRange` changing from 60 to 112 bytes,
`Glyph` from 76 to 60 bytes, and `Book_DrawLayout` from 108 to 148 bytes.
The per-run `Renderer::Span` call is removed from those glyph paths. These are
individual compiler frame sizes, not a hardware stack-watermark measurement;
the reserved master/slave stacks remain 12/4 KiB.

Candidate release SHA-256:
`242ee06415658f53388319389a844d0c412d6841d40b115d27adfa217238c282`.
It is deployed separately as `games/S32X/AITD32X-text-perf-242ee064.32x`.
The original alpha3 ROM, sound-fix ROM, existing `AITD32X.sav` and core settings
retain their original hashes. The candidate has its own filename/save namespace.
No commit or publication was made. Physical-console performance remains untested.

The deployed candidate hash matches the local release, and a remote screenshot
confirms it reaches the start menu. The eleven temporary experiment ROMs were
removed only after matching each against its local SHA-256; their local sources,
ROMs and measurements remain available. The earlier profiling ROM is retained.

The preserved original source tree is
`build/mister-optimization-reference/source/`. For example, an isolated
before/after reproduction can use:

```sh
python3 tools/build_mister_profile.py --source build/mister-optimization-reference/source --variant baseline
python3 tools/build_mister_profile.py --source build/mister-optimization-reference/source --variant font-batch
python3 tools/check_mister_profile.py --core .local/tools/picodrive-frt_libretro.so --project build/mister-experiment/font-batch
python3 tools/check_font_spans.py --reference build/mister-optimization-reference/libaitd32x.so
```
