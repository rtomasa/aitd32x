# Revision 11 validation — 2026-10-07

Release ROM SHA256: `917e6c1b174e69693237ae5d84954b36ae795811e1a8afa3f8f1fab37f5ee737`; 3,276,800 bytes; header checksum `CD84`. RELEASE has no timer instrumentation.

## Focused checks

- Native identical-scene cache-history tests reproduce v10's 25/12/10/25 FPS variation in stair room 7, camera 14. V11 NTSC Edward and PAL Emily run all four histories at 25.0 FPS, with identical framebuffer hashes across histories within each ROM and 125 world ticks per five-second sample. These deliberately freeze LIFE/animation state to isolate cache work. Original LIFE 91/92 explain why the ghosts naturally stop their idle animations; the tests do not represent a complete enemy playthrough.
- Native original stair/room round-trips pass for NTSC Edward and PAL Emily on the final release SHA. Each trace records completed frame timestamps and view-change frame costs. The updated checker excludes initial warm-up and gives regional capture filenames. See PERFORMANCE.md for exact v10/v11 timing and quantization limits.
- Sustained native chest pushing measures 12.0 FPS with one cache rebuild and a simulation rate consistent with 25 Hz. Stationary recaching does not restore the prior per-frame rebuild problem during pushing.
- Native hatch repros pass camera 2 and camera 3 for NTSC Edward and PAL Emily. Frozen scene pixels agree across both physical framebuffer banks; the FPS borders and engine/script state are valid.
- Host render checks pass eye scaling, FPS border, glass, contact depth, black/raw/RLE original-camera masks, colored silhouette capture, hit color and death-particle footprint checks. Twelve existing door/window cases and four hatch cases retain exact fresh/cached/original-painter agreement after the cache, decoder and damage-only bake changes.
- Host gameplay checks pass both characters' chest/book, drop/retake/throw, enemy arrival, melee/rifle, original stair/room round-trip and cache comparisons.
- Decoder checks compare aligned/unaligned source/destination buffers, raw odd tails, all RLE run lengths 1–255, guards/capacity failures, malformed runs and independent resumption of all 200 camera rows from their recorded token/skip. Legacy compressed masks remain correct.
- The importer regenerated the bank from the original installation. All 1840 unpacked payload SHA256 values and all input-file SHA256 values match v10. Only background storage representation and resulting bank offsets changed. Original source game files were read without modification.

The final build has no C++ warnings; the expected freestanding RWX linker warning remains. Module: 83,988 bytes; BSS: 160,568 bytes; static SDRAM end `0x0603BB50`, leaving 1,200 bytes below the stack reserve. The 96-byte cache-owner/quiet-time metadata is the additional persistent RAM; raw background storage adds ROM space while retaining the existing 64,000-byte RAM background. Linker limits pass. Header size/checksum and source archive contents are verified. Original assets, generated build files and Python caches are excluded from the source ZIP. Historical v10/v9/v8/v7 cartridges and archives remain unchanged.

## Limits

The cache-history result validates an identical stationary scene, not 25 FPS while enemies are moving or attacking. A settled prop's one-time rebake still has a cost. Original room/camera transitions remain visibly finite, and not every house route was measured. Full-house progression, audio, saves, exact PC behavior/graphics parity and physical hardware validation remain unfinished. Existing graphical fixes are retained; this revision does not attempt new rendering effects or movement changes.
