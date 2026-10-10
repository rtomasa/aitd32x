# Revision 8 bug fixes — 2026-10-07

ROM SHA-256: `42a1e8a0fabe9ef0dc54ce70feeaa8c294a72b58855c6b3a22a02ec501cdeaf1`. Size: 3,014,656 bytes. Header checksum: `0x3B7E`.

| Reported issue | Cause and correction |
|---|---|
| Hallway camera jumps to the bow room | Camera-2/3 coverage leaves a gap around room-1 X=1550, Z=0. V7 defaulted to the first listed camera, whose room-1 coverage is empty. Keep the current valid view when no replacement covers the actor; include polygon boundaries, collision-box center and FITD camera-angle preference. |
| Bedroom dog stuck at window | Collision-on was restored while the actor still overlapped the static window/wall. Allow motion towards the closest exit from an existing static overlap; moving actors retain their normal blocking behavior. Original arrival, pursuit, health and death LIFE remain responsible for gameplay. |
| Missing vase key | Projectile removal left the inventory flag set. Clear it on throw/drop/PUT; original LIFE 68 now breaks the vase and PUT_AT places key 53. The key can be taken. Broken vase and key share a position, so a pickup prompt can offer the vase first. |
| Oversized monster eyes | Monster eyes are small type-3 spheres, rather than player type-2 points. The forced radius of one produced a minimum three-pixel diameter. Permit radius zero: one native pixel. |
| Opaque glass | Material 2 was ignored. Render its glass with a 50% screen-door pattern, preserving alternate scenery pixels. This is an indexed-color approximation, not smooth alpha blending. |
| Door latches visible through both sides | Back-facing polygons were drawn. Cull their winding before dispatching to either SH2. |
| Hands/arms behind furniture | Whole-model painter sorting cannot resolve a limb crossing a prop. Resolve model contacts per pixel using reciprocal depth, including movable furniture while being pushed. Static baking remains the normal path. |
| Missing death effects | SPECIAL was a no-op. Add bounded evaporation/hit/smoke particles. This is a small native implementation inspired by the original effect parameters, not a verified pixel-identical recreation of DOS particles. |

## Focused validation

- Shared cartridge engine: both characters pass vase/key take, window exit/pursuit, melee damage/death/deletion, 30 death particles and expiry, attic zombie death particles, and the uncovered hallway-camera gap.
- Existing gameplay regression: both characters pass chest/rifle, books, drop/retake, throw, enemy arrivals, melee/rifle, stair/room round-trip and twelve fresh/cached framebuffer comparisons.
- Renderer: player and sphere eye footprints, FPS border, material-2 background preservation across the SH2 row split, and intersecting arm/chair triangles whose front order changes across the image. Exact coplanar ties allow either color under LEQUAL.
- Actual release cartridge on unmodified PicoDrive DRC_SH2: NTSC Edward and PAL Emily pass first-floor vase throw/key pickup, natural window exit, normal controller punches applying health/death/deletion, death particles/expiry, and equal images in both physical banks (including the chair view). Placement and the initial vase offer are diagnostic setup; arrival tracks, THROW/LIFE/key spawn, damage and death execute native gameplay. Combat placement is realigned between attempts to shorten pursuit, so this is not a full combat playthrough.
- Five seconds of native simulation produce 125 ticks. Approved movement/animation speed is retained.

The release compiler reports no C++ warnings; the expected freestanding RWX linker segment warning remains. Module: 81,508 bytes; BSS: 162,312 bytes; static SDRAM end: `0x603b870`. There are 1,936 bytes before the reserved master/slave stack area.

## Remaining limits

Full-house progression, audio, saves and exact original-engine parity remain unfinished. No physical 32X test was performed. Non-glass patterned/shaded materials retain the existing flat-color approximation. Contact resolution is bounded (1024 vertices/group); other general painter-order cases can still need work. The measured chair-contact view renders at about 12 FPS; this is a known cost of the correction, while simulation remains 25 Hz (see PERFORMANCE.md). Particles use the native palette and a bounded point cloud rather than a complete DOS-effect reconstruction. Historical revision-7 evidence is preserved in VALIDATION-v7.md; its whole-model ordering comparisons do not validate the revision-8 contact correction.
