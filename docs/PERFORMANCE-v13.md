# Revision 13 transition performance — 2026-10-07

The sofa-room to hallway report is reproducible: floor 1, room 2/camera 9 to room 1/camera 2. Release timings come from stock PicoDrive DRC_SH2 at its default clocks, using consecutive completed presentations and the 68000 VBlank sequence. They do not use the FPS overlay as a frame timer. The fixture opens door 33 and places the character near the doorway; real controller walking executes the original room link. LIFE, collision and animation continue normally. This is a focused reproduction, not a complete puzzle playthrough or hardware benchmark.

| Actual presentation gaps / settled hall | V12 NTSC Edward | V13 NTSC Edward | V12 PAL Emily | V13 PAL Emily |
|---|---:|---:|---:|---:|
| First transition gap | 300 ms | 216.7 ms | 300 ms | 220 ms |
| Next rebuild gap | 300 ms | 233.3 ms | 300 ms | 240 ms |
| Delayed rebuild around 1.3 seconds later | 300 ms | Removed | 300 ms | Removed |
| Settled hall, after 2 seconds | 15.0 FPS | 20.0 FPS | 16.7 FPS | 19.2 FPS |

V13 delivers 16 draws in the first NTSC second after arrival and 20 each second thereafter, versus v12's 10, 11, then 15. PAL delivers 15, then about 19 per second, versus 10, 12, then about 17. The actual traces and exact sample intervals are in `validation/transition-summary-v13.json` and `validation/room-transition-*.json`. There are still two initial long frames: this is an improvement, not an instant transition. The FPS HUD measures a roughly one-second window, so a low number can outlast the expensive frame that caused it.

## Finding

V12 already stores all 1,847 cartridge assets raw, including all 20 camera images. Original PAK compression is expanded by the host importer and is never executed by the console. Enlarging the cartridge to remove compression would therefore not fix this build's transition stalls.

A separately instrumented v12 copy measured about 237 ms in static-cache construction during an approximately 293 ms transition draw; copying/binding the raw camera image took about 7 ms. Those FRC scopes are inclusive and overlap; they must not be added together. Profiling instrumentation is separate from the shipped release image.

Room activation updates collision bounds on a neighboring-room prop (object 51/body 55). V12 hashes the raw bounds, declares the prop dynamic on a hash change, removes it from the baked image, then rebuilds again when its 25-tick quiet timer expires. This is expensive even when its rendered geometry and active camera masks have not changed. Collision bounds can also change painter order, so simply ignoring them is insufficient.

V13 hashes the actual camera-mask activation results, using the same test function as drawing, and folds static objects into the scene signature in their painter order. It also excludes animation group zero because Actor_Vertices replaces that state with the actor angles already present in the signature. Real geometry, active masks and order changes still invalidate the bake. The initial order change still needs a rebuild; the redundant remove/reinsert cycle and delayed rebuild are eliminated.

## Extra ROM instead of repeated projection/rasterization

The importer prepares 432 fixed, skeleton-free prop/camera poses, sharing 169 drawing programs. These add 314,742 bytes of literal palette-color drawing spans. The importer runs the same integer projection, clipping, sorting, backface/glass rules and rasterizer as the cartridge. The runtime replays the spans and applies the current camera masks and coverage tracking. A moved, rotating or skeletal pose without a matching program uses the ordinary renderer. Physical-contact depth repair remains the normal renderer.

All preceding asset IDs and 1,847 raw payloads are unchanged. The asset bank is 3,664,046 bytes; the ROM is 3,801,088 bytes (3.625 MiB), still below the existing 4 MiB cartridge window. No banking is needed for this revision. Unused legacy compressed-camera row indexing is removed to free 600 bytes of BSS; camera loading requires raw images. The generic decoder retains host/raw-RLE parity checks. Removing unused indexing is a memory change, not the source of the measured speedup.

The approved movement, 25 Hz simulation and 60 Hz animation clocks are unchanged. The native stair round-trip passes, including both imported floors. Sustained chest pushing remains about 12 FPS (v12 12.0, v13 11.8 in five-second diagnostic samples, one rebuild each); this revision does not claim a pushing-performance gain. The resulting chest/player positions match and measured simulation is about 25 Hz.

ROM SHA-256: `de9781ccbbf437a7a64c461626816b61e595b18eb3316cde0966e208440610c1`. Physical 32X timing has not been measured. Earlier UI and broader gameplay evidence is retained in the versioned reports.
