# Revision 9 — reported performance and rendering fixes

ROM SHA-256: `24b75db7a2baf760b99e9a8b2126d158eed070bf2b492417d62241306ffd3f78`. Size: 3,014,656 bytes. Header checksum: `0xDD12`. Original imported bank is unchanged: `a7dd45ef9a57231dd986417e9e9e94faba41a954155dbb70334f0d65304d9fa8`.

| Report | Change |
|---|---|
| Slow hallway / large door views | Eliminate idle/walk contact correction, floor-plane false contacts and unrelated models from contact depth groups. Tighten bounds to visible primitives. |
| Heavy slowdown when moving chest/furniture | Preserve dynamic cache membership until the camera changes, even when LIFE switches a prop back to a static TYPE. One transition rebuild replaces repeated full scenery rebuilds. |
| Window drawn over player / door ordering | Foreground masks copy the original camera image instead of baked model pixels. Remove mounted-prop height buckets from world sorting. Cached window, closed/open/opening door poses match a fresh painter pass from the original camera image. This fixes these cache/sort causes; it is not a general proof of every possible intersecting polygon order. |
| Mauve hit particles | SPECIAL 1 uses red palette entries 80–83. Death evaporation keeps its original effect palette. |
| Death particles too small | SPECIAL 0's projected width and height are each tripled, including distant one-pixel points becoming 3×3. Hit particle size is retained. |

## Focused checks

- Renderer pixel checks pass for player/dog eyes, FPS border isolation, glass background preservation across the SH2 row split and intersecting arm/chair depth. Added checks render original-camera mask spans over deliberately contaminated baked pixels with raw and compressed backgrounds, including RLE runs crossing rows and palette index zero. Actual SPECIAL creation plus raster output checks red hits and death footprints of 21×21, 9×9 and 3×3 at three depths. Particle RNG leaves gameplay RNG unchanged.
- Both characters pass twelve window/hallway/open/opening-door scene comparisons. Cached draws equal fresh cache rebuilds and a painter pass starting from the original camera image, byte for byte. Broken windows are checked with the player in front and behind. Contact views use their depth pass and are covered separately.
- Existing shared-engine regressions pass for both characters: chest/rifle, books, drop/retake, throw, enemy arrivals, melee/rifle, stair/room round trip and twelve existing fresh/cached framebuffer comparisons. The v8 bug regression also passes vase/key, natural dog window exit/pursuit/damage/death/deletion, particle expiry, zombie death particles and hallway camera gaps.
- The actual final release ROM on stock PicoDrive passes native NTSC Edward and PAL Emily vase throw/key pickup, natural dog window exit, controller-driven punches, health/death/deletion, particles/expiry and equal frozen images in both physical framebuffer banks (dog death and chair contact). Initial scene placement/offer and combat alignment are diagnostic setup; actual LIFE, tracks and controller actions execute native gameplay.
- Native matched performance tests cover both hallway cameras and moving chest/chair. Additional release samples cover the window and open far door; PAL Emily also runs sustained chest/chair pushing. Tick progress remains consistent with 25 Hz using completed-frame timestamps. See PERFORMANCE.md for exact results and sampling limits.

The release build has no C++ warnings. The expected freestanding RWX linker-segment warning remains. Module: 82,852 bytes; BSS: 160,464 bytes; static SDRAM end: `0x0603B678`. There are 2,440 bytes below the master/slave stack reservation. Compact contact storage is bounded to 768 vertices; two maximum-size imported models fit, and larger groups safely retain painter output. Source archive contents are verified against the packaged project; original assets and generated build files are excluded from that archive.

## Remaining scope

Moving furniture is substantially faster but still costly (9.6 FPS for the tested visible chair pushing pose, 11.4 FPS for the moving chest). Whole-model painter sorting and bounded contact correction do not resolve arbitrary multi-object intersections. Contact repair is specifically enabled for Search/Push reaching limbs; other animation/contact cases can require further work. Glass uses a 50% indexed-color screen-door pattern, not smooth blending. Effects remain a bounded native point cloud rather than verified DOS-identical effects. Full-house progression, audio, saves, exact original-engine parity and physical 32X testing remain unfinished. These checks validate the documented scenes and interactions, not a full playthrough. Earlier v8 evidence and reports are retained unchanged.
