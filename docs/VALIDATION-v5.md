# Validation — revision 5, 2026-10-07

Revision 5 improves triangle scan conversion and stable primitive sorting. Revision 4's accepted motion remains unchanged; its original-DOS timing evidence is in `TIMING.md` and historical results in `VALIDATION-v4.md`.

| Check | Result |
|---|---|
| Freestanding 68000 + SH-2 release build | Passed with Marsdev GCC 13.1.0 |
| v4 baseline identity | Clean rebuild reproduces the supplied v4 ROM exactly |
| Existing render behavior | 966 exact pixel/palette matches against v4, both characters, camera route and near clipping |
| Raster/damage/restore coverage | 1,147 exact differential cases; framebuffer guards and ASan/UBSan passed |
| Actual cartridge movement | Edward/Emily in PAL/NTSC match original animation phase and unobstructed root displacement |
| Native pause | Position, orientation and animation remain unchanged for both characters/regions |
| Simulation and FPS | 124–125 ticks per five seconds; completed game draws agree with physical framebuffer swaps |
| Close NTSC release performance | 12 → 20 FPS for Edward and Emily, same camera/position/orientation |
| Close PAL release performance | Edward 12.4 → 16.6 FPS, same camera/position/orientation |
| Starting NTSC view | Edward 17.2 → 20 FPS |
| Packaged source rebuild | Regenerated asset bank and ROM match the distributed release byte-for-byte |

`PERFORMANCE.md` contains stage measurements, reproduction steps and the precise benchmark positions. JSON results in `validation/` are named `profile-v4-*`, `profile-v5-*`, `release-v4-*`, `release-v5-*`, `movement-v5-*`, `renderer-comparison-v5.json` and `raster-comparison-v5.json`. Native movement results contain the v5 ROM hash even though the reused movement tool names its build outputs v4. `unchanged-runtime-v5.json` records byte-identical engine, CPU and platform source files.

Only the renderer, its private fixed workspace, an optional raster coverage tool, build target and documentation changed. Original game installations and imported assets were not modified. Existing camera/mask/point behavior is preserved by differential rendering; the full historical boot/camera suite was not rerun unnecessarily for this renderer change.

## Artifact identity

Release ROM: 720,896 bytes; checksum `0xC91C`.

SHA-256: `51166d0f1b708ffe92477ec06b0a326acc6d3da035f8f48f199243bede1e8707`

Asset bank SHA-256: `c257542990a41792910f6d542eee040a8aefe985e9ab1801e31dfda67db12213` (unchanged).

SH-2 loaded module: 21,300 bytes; BSS: 80,452 bytes; static working set: 101,752 bytes; end `0x06018D78`. Linker stack checks pass. Sorting adds 2 KiB of fixed scratch memory.

## Limits

These performance figures come from PicoDrive, with a separate timer-capable core for stage profiling. No physical 32X test has been performed. Camera/pose size affects FPS, and performance is not yet sufficient to present every 25 Hz logical update in all measured views.

The new comparisons verify parity with v4's renderer, not complete original-game rendering parity. Original controller acceleration and the complete movement/collision state machine still need validation. LIFE/track execution, multiple actors, inventory, puzzles, combat, room/floor transitions, cutscenes, audio, saving and game completion remain absent.
