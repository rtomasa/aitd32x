# Reported window/door visibility repairs — 2026-10-11

Two reported poses exposed defects that the preceding initial-state sweeps
could not establish: a pushed attic cupboard covered by the window, and a
nearby door filling the pink-chair bedroom camera with brown polygons.

## Causes and shared repairs

Attic floor 0, room 0, camera 2 reproduces the window problem when cupboard
object 4 moves to `(-600,0,4540)`. Its mesh ends at world Z=4972; window object
7 starts at Z=5000 and the camera is at Z=1160. Every shared ray therefore
reaches the cupboard first. Their camera-depth ranges overlap, and third actors
can defeat this correct pair order in the original insertion heuristic.
The shared graph pass now includes compatible X/Z separating-plane precedence
alongside its preceding Y and hard camera-depth rules. Contradictory X/Z
preferences retain stable order; cyclic plane preferences can be relaxed while
hard camera-depth constraints remain intact. This adds no global workspace.

Bedroom floor 1, room 4, camera 5 reproduces the giant panel with adjoining
library door 59/body 25 at beta 512. Its camera Z range is -207..1483.
FITD's `processPrim_*` routines reject a primitive if any referenced vertex
has Z <=100. The port instead clipped crossing faces at Z=51, producing a
nearly full-screen panel that FITD never draws. Whole-primitive rejection now
applies to ordinary world drawing, contact fallback and regenerated prepared
props. Valid faces remain visible; the actor is not discarded wholesale.
The removed clipping path also eliminates its interpolation work and scratch.

The port adapts FITD, an engine reimplementation, and uses the original game's
assets and scripts. It does not execute the DOS renderer unchanged. Two-SH2
raster work, scenery baking, prepared drawing, local depth and framebuffer
repairs are port-specific adaptations. Their visibility/composition rules must
be checked against the reference. Painter sorting also depends on original
camera masks; a single distance key cannot solve interpenetrating geometry.
Cache-versus-uncached equality alone can conceal a shared visibility mistake.

## Validation

```sh
make assets
make -j2 host all
python3 tools/check_window_furniture.py
python3 tools/check_door_projection.py
python3 tools/check_raster_parity.py --ordinary
python3 tools/check_world_order.py
python3 tools/check_draw_order_cache.py --sweep
python3 tools/check_contact_order.py
python3 tools/check_bank_layout.py
python3 tools/check_window_door_native.py .local/tools/picodrive_libretro.so --region NTSC
python3 tools/check_window_door_native.py .local/tools/picodrive_libretro.so --region PAL
```

| Check | Result and scope |
|---|---|
| Pushed cupboard | 384 frame comparisons pass: both characters, closed/open cupboard body bind poses, intact/broken windows, six pushed positions, cache/full paths and both framebuffer histories. The independently proved separating plane and nearer-cupboard repaint expose 224 incorrect frames / 33,552 pixels in the preceding build. |
| Near door | 270 comparisons pass: both characters, five views, beta 512..768 in steps of 32, ordinary paint, asserted static baking and contact depth. A private source mesh pruned by the FITD Z rule supplies the oracle. The preceding renderer fails 54 comparisons. |
| Prepared props | All 1,106 prepared poses pass 2,212 exact pixel/coverage/bounds comparisons against ordinary drawing with prepared programs disabled in a private bank; three moved/rotating fallbacks also pass. |
| World hard-depth rules | 2,780 sampled cases across all 144 cameras pass 99,856 separated-depth constraints and the preceding explicit foreground-door cases. |
| Graph cycle audit | 2,792 cases, including pushed poses, retain deterministic order and all 100,260 hard-depth edges. 202 cases contain cycles; fallback relaxes 431 X/Z and 411 Y preferences. Four distinct scene/pairs have overlapping screen bounds among relaxed X/Z edges, so this is not a proof of visibility in every playable pose. |
| Scenery/contact composition | 2,660 cached/all-dynamic comparisons across all 144 cameras pass; the preceding 64 contact-interval comparisons also pass. |
| NTSC/PAL cartridge | 24 frozen scenes pass: both characters, bedroom closed/rotating door, library/opposite view, pushed attic cupboard and ordinary hallway. Both physical framebuffer banks match reloaded host pixels. Each fixture runs in a fresh process with private SRAM; a private SDRAM RTS/NOP stub freezes `World::Update` before Resume, with a DRC flush. Renderer instructions and the ROM file remain unchanged. This pixel check makes no timing or hardware claim. |
| Linked layout | Mapper-page isolation, protected data/code/audio, module, checksum and SDRAM budgets pass. |

Reports remain ignored under `build/`: `window-furniture*.json`,
`door-projection*.json`, `raster-parity-ordinary.json`,
`window-axis-cycle-audit.json`, `world-order.json`, `draw-order-cache.json`,
`contact-order.json`, `window-door-native-{NTSC,PAL}.json` and
`bank-layout.json`. The preceding ROM/ELF/library/bank
remain in `build/window-door-reference/`. Tests use private host/emulator state
and never read or write user battery files or original resources.

## Performance and memory

Fresh-process PicoDrive comparisons use byte-identical private SRAM fixtures.
Ten-second live traces measure NTSC 24.3 →24.2 draws/s and PAL 24.2 →24.2.
The single NTSC draw/update difference lands at a controller boundary;
intermediate segment traces are not exactly equal. NTSC final pose matches;
PAL differs by one position unit and four angle units. No clock code changes
are part of these repairs.

Two-second frozen entrance samples at floor 3, room 1, camera 3, player
`(3510,0,35)` measure NTSC 19.0 →19.5 counted draws/s, with 20 displayed
swaps/s in both builds; PAL retains 24 counted draws/s and 25 swaps/s.
World ticks remain frozen, both physical banks match, and before/after scene
pixels are identical. These short samples show no material performance loss;
they do not establish sustained whole-game or hardware performance.
Evidence is `build/window-door-performance.json`.

The current RELEASE ROM is 14,155,776 bytes / 13.5 MiB, checksum `FA73`, SHA-256
`80a0ea656c04a8a5dcd1f44dfb655310ba4605858189cbb6c306abe5fd6279c3`.
Bank SHA-256 is
`94c7dc55da69f2445bbafd7e1f6531cb67f2e0c878328305a30ad4645a7dfe6e`.
Fixed bank data is 3,964,720 bytes; extension data is 9,932,868 bytes.
The module shrinks by 544 bytes to 84,420; BSS remains 160,640.
Static SDRAM ends at `0x0603BD48`, leaving 696 bytes below reserved stacks.
The module ends at physical byte 4,180,212, with 14,092 bytes below 4 MiB.
No image/depth buffer, heap, timing or save-format change is introduced.
The existing linker RWX warning remains; physical hardware is unvalidated.

## Why the ROM is larger than the DOS installation

The imported original camera PAKs occupy 2,989,756 bytes, including directories;
their compressed payloads total 2,981,660 bytes. The same 144 camera images
occupy 9,216,000 bytes as raw 320×200 indexed pixels in this cartridge.
That approximately 6.23 MB expansion is the main difference. Raw images allow
aligned copies and direct foreground-mask repairs without decompression on
room changes. This is an intentional ROM-space tradeoff for the 32X's limited
RAM and rendering/transition performance.

Distinct native payload sizes, counted once for shared asset offsets:

| Resources | Bytes |
|---|---:|
| Raw camera backgrounds | 9,216,000 |
| Prepared prop drawing | 759,590 |
| Converted sound/music | 1,002,070 |
| Models/animations | 487,502 |
| Ending movie | 303,652 |
| Other assets, including presentation, UI and scripts | 1,281,620 |

The remaining 1,105,342 ROM bytes cover asset directories, alignment,
mapper-page isolation, code/headers and padding. Payloads cannot cross the
selected 512 KiB mapper aperture; gaps keep that constraint. The ROM is
14.16 decimal MB, or 13.5 MiB. Original installation sizes also vary by edition
and included languages/audio; these figures refer to this build's actual input
and generated assets. Evidence is `build/window-door-rom-size.json`.

Full manual playthrough, all animated poses and physical 32X validation remain
pending. The near-face oracle checks visibility policy, not independent raster
arithmetic; native pixel equality checks the linked rendering implementation,
not the original DOS game in every scene.
