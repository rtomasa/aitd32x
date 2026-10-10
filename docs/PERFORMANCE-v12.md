# Revision 12 UI change

The following gameplay measurements are retained from revision 11; they were not rerun for this UI-only change. Gameplay movement, scene rendering, caching and transition loading are unchanged. UI panels are precomposed in cartridge ROM and copied with word writes only when an overlay is drawn. The release module grows by 240 bytes, with unchanged BSS and no extra RAM bitmap. Native NTSC/PAL UI checks passed, including both framebuffer banks. No new gameplay FPS claim is made for revision 12.

# Revision 11 performance — 2026-10-07

This revision addresses the route-dependent FPS in floor 1, room 7, camera 14, and the remaining camera-change hitches. Release measurements use unmodified PicoDrive DRC_SH2 at its default clocks. The approved 25 Hz world and 60 Hz animation clocks and walk/run speeds are unchanged.

## Stair-room cache history

Original LIFE 91/92 stop the two ghosts' idle animations. V10 retained their dynamic render classification until a camera change, even after their animation/movement flags cleared. Arriving from another view could therefore cache the same stationary models and run faster. The same issue also affected a door that opened while the camera was active.

| Identical stationary scene, NTSC Edward | V10 FPS | V11 FPS |
|---|---:|---:|
| Models settled before entry | 25.0 | 25.0 |
| Ghosts settled while in view | 12.0 | 25.0 |
| Ghosts and door settled while in view | 10.0 | 25.0 |
| Cache reset | 25.0 | 25.0 |

These diagnostic samples freeze LIFE/animation pose changes and replay the render-cache history, isolating rendering rather than enemy behavior or player position. Every history has the same final framebuffer hash within its ROM and advances exactly 125 world ticks in five seconds. PAL Emily also measures 25.0 FPS and 125 ticks for all four histories. Warm-up timing changes the frozen animation phase between ROMs; these hashes prove equivalence within each history comparison, not a cross-ROM original-pixel oracle.

V11 keeps an object dynamic during movement or animation, then caches it after 25 unchanged world ticks with stationary flags. The delay avoids the old repeated rebuilds when LIFE toggles pushed furniture between moving and stationary flags. Cache history also resets when an active slot changes its owning object. A sustained NTSC moving-chest sample measures 12.0 FPS, one cache rebuild and 124 ticks over 4.95 seconds of completed-frame timestamps. V10's corresponding sample was 11.8 FPS; this revision primarily removes unnecessary work after models stop.

## Release transition measurements

Diagnostic placement enters the original attic stair trigger. Original tracks and controller movement execute the floor/room round-trip. The first completed frame after each view change includes simulation update, drawing and presentation.

| Transition, NTSC Edward | V10 VBlanks | V11 VBlanks | V10 → V11 first-frame time |
|---|---:|---:|---:|
| Attic stairs → floor 1, room 6 | 10 | 4 | 166.7 → 66.7 ms |
| Room 6 → room 0, same camera | 0 | 1 | Within current refresh interval → 16.7 ms |
| Room 0, camera 0 → camera 1 | 13 | 6 | 216.7 → 100.0 ms |
| Room 0, camera 1 → camera 0 | 10 | 3 | 166.7 → 50.0 ms |
| Room 0 → room 6, same camera | 1 | 2 | 16.7 → 33.3 ms |
| Return stairs → attic camera 4 | 10 | 6 | 166.7 → 100.0 ms |

Timing uses the 68000 VBlank sequence captured at the iteration's start and read when its frame is displayed. Resolution is one refresh interval; zero means completion during the same interval, not zero processing time. Initial warm-up is excluded. The new-camera/floor samples improve by about 40–70%. Same-camera links were already inexpensive in v10 and vary by frame alignment/cache work; this sample does not claim every transition became faster. Camera-boundary and stair landing positions match v10 on this route despite different warm-up tick origins.

PAL Emily completes the same route. V11 measures 60, 20, 100, 60, 60 and 120 ms respectively; its new-camera/floor frames improve from v10's 160, 220, 160 and 160 ms to 60, 100, 60 and 120 ms. These scene samples are not whole-game worst cases or measurements of every door in the house.

## Background and cache work

A separately instrumented v10 copy identifies RLE background decoding at about 61 ms and a second row-index pass at 22 ms for first-floor cameras 0/1. Full restoration costs 21 ms, full bake readback 10 ms, and camera 1's per-pixel coverage scanning about 34 ms. Timer calibration against VBlank is 1.00114.

The cartridge has enough room to store all 20 camera images raw. The importer now does that, and aligned word copying reduces measured camera binding from about 84 ms to 7.3 ms in a separately instrumented raw-background build (calibration 1.00141). Raw assets remove runtime image expansion and RLE row indexing during ordinary room/camera changes. All 1840 decoded payloads and all original input-file hashes are unchanged. The converted bank grows by 264,592 bytes to 3,164,508; the release ROM is 3,276,800 bytes (3.125 MiB), below the direct 4 MiB window. No additional background RAM is allocated. Legacy RLE banks remain supported; their mask row indexes are generated during decode.

Coverage extraction reads each uncached bitmap byte once and skips solid/empty runs. Full restoration copies aligned words directly, with four-word loop unrolling. Static baking copies only the damaged rectangle back into the already-decoded background, including masks and black pixels. The single-pass silhouette capture, original-camera foreground masks and bounded fallback remain intact.

A camera change still performs new-scene setup and rendering. The remaining 50–100 ms NTSC and 60–120 ms PAL new-camera/floor frames can be noticeable; this revision reduces the hitch rather than making transitions instant. Physical 32X timing remains unverified. See VALIDATION.md for the evidence scope.
