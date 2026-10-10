# Revision 10 validation — 2026-10-07

ROM: `c05cedc2dae81490677e3b04e237de632fb2718b51969d099239eff770b1e164`; 3,014,656 bytes; header checksum `668E`. The supplied original bank is unchanged. RELEASE has no FRC profiling instrumentation.

## Reported hatch sorting

The attic hatch/floor cover is object 8, body 7. Its collision Y range is 5–67, below the standing actors/chest whose lower extent is Y=0 (Y increases downwards). V9 used horizontal distance to decide its order, sometimes drawing this floor model over the raised chest or player. V10 resolves non-overlapping vertical ranges relative to the camera before applying the existing horizontal distance comparison. It does not restore the old broad height buckets that caused window ordering errors.

The reported camera 3 and camera 2 poses are reproduced with a relocated chest and standing player. Both character banks pass four host cases: the hatch sorts behind both models, cached output equals a fresh rebuild, and both equal the original-camera painter pass. Native release tests repeat both cameras for NTSC Edward and PAL Emily; both physical framebuffer banks have identical frozen scene pixels, valid borders and no script/engine fault. Captures and JSON evidence are in validation/.

## Cache and transitions

- Colored coverage is checked against an independent monochrome pixel footprint, including palette-index-zero geometry and screen-door glass. Whole-surface and two-CPU-row-split outputs agree for both color and coverage. Raw/RLE camera masks remove occluded silhouette pixels, and unmasked black spheres retain coverage.
- The existing render checks pass for eye scaling, FPS border, glass, contact depth, original-camera mask pixels, red hit effects and enlarged death effects. Raster-band checks pass 200 randomized cases at six splits each (1200 comparisons), including pixels, damage, row ownership and guards.
- Twelve existing window/door cases, using both characters, preserve exact fresh/cached/original-painter agreement.
- Both-character host gameplay checks pass the chest/book, item drop/retake/throw, enemy arrivals, melee/rifle, original stair and room round-trip, with their cache comparisons.
- Original native stair/room round-trips pass on NTSC Edward and PAL Emily. The release trace records the first displayed view-change frame and its following five frames. Comparison with v9 NTSC quantifies the reduced hitch; the opening warm/paused trace entry is not a transition result.
- The release moving-chest sample remains consistent with the approved 25 Hz simulation. Timing/animation source was not changed. Full original DOS comparison and complete combat playthroughs were not rerun for this scoped render/cache revision.

The build has no C++ warnings. The assembler expands three out-of-range branches to longer instruction sequences; the bootstrap section-attribute and freestanding RWX linker warnings also remain. All are retained in build-v10.txt. Module: 82,996 bytes; BSS: 160,472 bytes; static SDRAM end: `0x0603B710`. There are 2,288 bytes below the master/slave stack reservation. The bitmap reuses existing scratch, and the bounded span pool retains its normal-draw fallback. The source archive is verified byte-for-byte against the published project and excludes original resources, generated build files and Python caches. Historical v9/v8/v7 cartridges and archives remain unchanged.

## Limits

The floor fix resolves the reported vertically separated models; whole-model painter sorting and bounded Search/Push contact correction still cannot guarantee arbitrary intersecting geometry. Camera changes still have a measured first-frame hitch (160–220 ms in these tests). Glass remains a 50% screen-door approximation. Full-house progression, audio, saves, exact PC graphics/behavior parity and physical 32X testing remain unfinished. This validates the documented poses and transitions, not a full playthrough.
