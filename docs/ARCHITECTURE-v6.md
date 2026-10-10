# Current native architecture

This document describes the implemented prototype. The full target architecture and later phases remain in `TECHNICAL_PLAN.md`.

## CPU responsibilities

The 68000 performs bootstrap, region detection and controller polling once per VBlank. It publishes a small coherent input snapshot. The master SH-2 performs gameplay, animation, collision, camera selection, transforms, projection, stable depth sorting, background restoration, foreground masks and presentation. Rasterization is shared: the master owns logical rows `[0,100)` and the slave owns `[100,200)`. The slave also maintains its uncached mailbox heartbeat.

The cartridge runtime is freestanding C++17, compiled big-endian for SH-2. It uses no filesystem, SDL, operating system, heap, STL containers, RTTI or exceptions. Fixed-size actor and render workspaces occupy static SDRAM. Desktop host tools may allocate normally.

## Video and rendering

The packed-pixel VDP runs at 320×224 in PAL and NTSC. Both framebuffer line tables map physical row `y` to word offset `256 + y*160`. There is no vertical scaling or line reuse. The platform supplies a destination pointer offset by the 512-byte line table and twelve physical pixel rows. Engine coordinates remain 320×200.

Revision 2 draws FPS text at physical columns 4–67, rows 2–9. This presentation overlay uses word writes directly in the border and never alters the logical game target or its damage tracking. Both buffers erase old digits when drawing the next counter value.

One 64,000-byte SDRAM background cache stores the current title/camera. Each physical framebuffer has its own damaged rectangle. Before reuse, its previous damage is restored from the cached background. Camera changes invalidate both buffers for a full restore. Word writes correctly restore palette index zero, whose byte writes would be transparent on the 32X.

The renderer uses the original FITD Q15 trigonometric table, integer transforms, original camera translation/projection values, near clipping, stable primitive depth ordering and flat scanline spans. Foreground polygons are converted offline into scanline runs; their original actor-ZV test rectangles decide when background pixels occlude the protagonist. Projection, masks and overlay clipping use logical rows 0–199.

The protagonist uses FITD's `getZvCube` footprint, matching the original object with `typeZV=2`. Its square collision box remains fixed while turning. Movement follows the imported animation root deltas and keyframe durations. Small movement substeps and axis sliding test the original room hard-collision boxes. General actor collision, scripted hard-col responses and the complete original movement state machine are deferred.

The 32X palette uses 5-bit color channels converted from the source palette; palette indices and source image geometry remain unchanged. General backface/material behavior and exact sphere rasterization are not yet validated against FITD.

Type-2 points, including both protagonists' eyes, draw one native pixel, matching FITD's tiny screen-space point class. They have no embedded radius; the larger perspective-sized zixel is a separate primitive. Normal point coordinates participate in mask bounds and damage tracking. Revision 2's invented 32-unit eye billboard footprint has been removed.

Revision 3 advances polygon edges with exact integer remainder carries rather than repeated scanline division. Projected vertices are cached once per draw; near-clipped polygons keep their clipping path. Mask runs restore background words directly. Nonzero endpoint bytes avoid framebuffer reads; palette-index-zero restoration uses word writes. Renderer divisions use the executing SH-2's signed DIVU with an explicit 39-cycle wait. Each CPU uses its own local divider.

Revision 5 gives triangles a two-active-edge scan converter, preserving directed-edge rounding and half-open Y coverage. It accumulates their actual clipped damage bounds once per primitive; general polygons keep the original scan converter. On-screen edge endpoints avoid redundant initial division. Stable depth ordering uses four-face insertion runs followed by merges in a fixed 2 KiB scratch array; equal-depth faces preserve their source order. Game timing remains unchanged. Revision 6 prepares camera and bone-group Q15 rotation coefficients once per repeated transform. Its SH-2 truncation helper applies the original signed division rule with fixed shifts and rotate-through-carry; it retains the full quotient range. Host builds keep signed C division. Rotation order and intermediate arithmetic are preserved.

Revision 6 encodes each directed edge's rounding rule in its initial DDA remainder instead of correcting every scanline. Known quotients and one-row edges avoid DIVU waits; next edge values are committed once. Span loops pair word stores without changing zero-index behavior, and triangle row pointers advance directly. `src/render/raster.cpp` implements the same coverage for a full surface or any half-open row band.

## Ordered raster worker

`src/render/worker.cpp` owns a fixed eight-entry SDRAM ring. The master sends begin, projected primitive and end commands in painter order. Each command contains copied points and immutable parameters. Conservative vertical bounds route only work that can touch the slave's band and indicate whether the master must draw its portion; fallback spheres include their full radius. The master and slave never write the same logical row, protecting both ordinary stores and zero-color endpoint word read/modify/write.

All shared ring flags, payloads and final damage are read/written through the cache-through SDRAM alias at `0x26000000`; cached aliases are not used after cache-off BSS initialization. This follows SH7604 hardware manual section 8.5.3: the caches do not snoop other bus masters. Compiler memory barriers preserve publication order. The slave copies each command into private static scratch before advancing its read counter, allowing safe ring reuse while rasterizing. Unsigned sequence differences handle ring wrapping within the eight-entry capacity.

The slave processes its lower-band primitives sequentially, then publishes its damage rectangle before the end token. The master waits for that token, merges both damage rectangles, applies foreground masks and draws overlays before flipping. Target framebuffer lifetime therefore extends until all slave drawing completes. No dynamic allocation, shared z-buffer or hardware autofill is introduced. The fixed split at row 100 performed better in the measured views than other tested fixed splits and an adaptive model midpoint.

## ROM and SDRAM budget

| Item | Release build |
|---|---:|
| Padded cartridge | 720,896 bytes / 704 KiB |
| Native asset bank | 641,980 bytes; 93 entries |
| SH-2 loaded module, including vectors and executable code | 23,460 bytes |
| SH-2 BSS | 85,324 bytes |
| SDRAM code and static working set | 108,784 bytes |
| Reserved master / slave stack areas | 12 KiB / 4 KiB |

The 32X BIOS loads the executable module at `0x06000000`. Vector placement remains fixed. Executable code, fonts and trigonometric tables reside in SDRAM; immutable assets remain in cartridge ROM. BSS ends at `0x0601A8F0`. The worker ring and private slave scratch occupy 4,876 BSS bytes; 136,976 SDRAM bytes remain before the stack reservation. The largest slave raster stack frame is 2,172 bytes and its nonrecursive call path remains below 4 KiB. The linker rejects static allocations beyond `0x0603C000`, below the stack reservations. Framebuffer memory is separate from SDRAM.

## Mailbox and timing

SH-2 COMM registers start at `0x20004020`, with two bytes per entry.

| Entry | Meaning |
|---|---|
| 0 | Mode/camera; bit 7 paused; `0xE001` fatal error |
| 1 | Logical tick counter, low 16 bits |
| 2 | Slave C entry marker `0x534C` |
| 3 | Slave VBlank heartbeat |
| 4 / 5 | Pad 1 / 2: low byte held buttons; high byte press-event toggles |
| 6 | Snapshot sequence: odd while being written, even when committed |
| 7 | Region refresh rate: 50 or 60 |

The master reads only stable even snapshots. The sequence advances by two each hardware frame and wraps as a 16-bit value. A phase accumulator converts elapsed frames into 25 Hz logical updates independently of rendering. Multiple pending ticks are processed before drawing. Input press toggles preserve a short press that was released during a slower render; two presses of the same button between reads can cancel their parity.

Revision 4 uses `ANIMATION_HZ=60` alongside `GAME_HZ=25`. Each simulation update consumes 60 phase units; an imported key lasts `duration * 25` phase units. One phase unit is 1/1500 second. The actor interpolates root displacement and bone state at that phase, consumes any remaining time across keyframe boundaries and sums the root movement before collision. Neither fractional time nor a completed key’s displacement is discarded. Animation changes reset the phase and take the current pose as their blend origin. Pause stops actor advancement. Original DOS timing measurements are in `TIMING.md`.

The exported `debug_state[16]` begins with tick, camera, player X/Y/Z, orientation, mode, pause, character and consumed sequence. Revision 2 appends cumulative game renders, FPS in tenths (`-1` before a valid sample), and the latest update batch size. Its address is discovered from the ELF by the emulator checker. Revision 4 appends the current animation frame, fractional phase and asset ID. Diagnostic state is published after rendering, so it can lag an input by one render.

The FPS meter counts completed game draws against elapsed hardware VBlanks. It excludes redraws performed solely to refresh the counter on a static title or pause screen. Changing from title to gameplay starts a fresh measurement window. It does not change the simulation accumulator or motion data.

## Asset bank version 1

The host importer reads original PAKs, `OBJETS.ITD` and `DEFINES.ITD`; runtime never parses DOS containers. The bank uses big-endian fields, four-byte alignment, ordinal resource IDs and internal offsets rather than pointers.

Header: `A32X`, `u32 version`, `u32 entry_count`, `u32 bank_size`. Each 16-byte directory entry contains `u32 offset`, `u32 packed_size`, `u32 unpacked_size`, `u16 type`, `u16 flags`. Flag 0 means raw bytes; flag 1 means `(u8 count,u8 palette_index)` RLE pairs. Background compression is used only when smaller.

Converted assets include the original title and palettes, five attic cameras/backgrounds, room hard-col/scenario boxes, both protagonist body/animation banks, original objects, selected LIFE scripts and the player spawn. Objects and scripts are present as converted data but are not executed. `assets/manifest.json` records source hashes, asset ranges, the pinned FITD revision and bank SHA-256. `resource_ids.h` supplies generated compile-time indices.

Models retain original vertices, group hierarchy/order and primitive indices. Animation words become native big-endian words. Camera mask polygons become clipped foreground scanline spans. The converter is specialized for this data set and attic milestone; extending it to every floor and resource family requires further work.

## Profiling build

`BUILD=PROFILE` adds SH7604 FRC scopes for update, restore, transform, sorting, primitive processing, fill, masks, FPS, palette loading, flip and entire draw. `profile_state` publishes cumulative ticks/calls and a timer/VBlank calibration sample after each completed frame. RELEASE removes the scopes and timer code. Stage totals nest (fill inside primitives inside frame). With two CPUs, master fill covers only the upper band; the primitive remainder also includes command copies and queue backpressure, and slave work overlaps those scopes. `worker_profile_state` separately records ring/final waits and slave raster time/calls. The diagnostic tool's subtraction must not be interpreted as pure clipping cost or summed with concurrent slave work. Details and timing limitations are in `PERFORMANCE.md`.
