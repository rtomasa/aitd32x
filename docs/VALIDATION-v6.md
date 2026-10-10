# Validation — revision 6, 2026-10-07

Revision 6 distributes rasterization across the two SH-2 processors and reduces transform, edge and span overhead. Revision 4's approved motion remains unchanged; original-DOS timing evidence is in `TIMING.md`. Previous renderer results are preserved in `VALIDATION-v5.md` and `PERFORMANCE-v5.md`.

| Check | Result |
|---|---|
| Freestanding 68000 + SH-2 RELEASE build | Passed with Marsdev GCC 13.1.0 |
| v5 baseline identity | Clean rebuild reproduces the supplied v5 ROM exactly |
| Host rendering against v5 | 966 exact framebuffer/palette matches, both protagonists, camera travel and near clipping |
| Raster/damage/restoration | 1,147 exact differential cases; framebuffer guards passed |
| Whole-row band ownership | 1,200 comparisons, six splits and 3,432 primitive calls; exact pixels/damage, disjoint writes, guards and ASan/UBSan passed |
| Compiled SH-2 Q15 truncation | 458,752 exact comparisons against signed C division, full-range boundaries/adjacent values and 65,536 random inputs |
| Combined PROFILE native rendering | 40 frozen poses each for Edward/Emily in NTSC; all five cameras and both banks match actual v5 native NTSC reference pixels |
| Final RELEASE native rendering | 160 exact comparisons: 40 poses × Edward/Emily × PAL/NTSC; all five cameras and both completed banks match actual v5 native reference images |
| Cartridge boot/camera/pause | PAL and NTSC passed; source title/background pixels, native line mapping and borders verified |
| Actual cartridge movement | Edward/Emily in PAL/NTSC match imported animation phase and unobstructed root displacement |
| Pause and simulation | Position/orientation/animation freeze; 250 logical ticks in each ten-second region check |
| FPS accounting | Completed game draws agree with physical framebuffer swaps; all six v6 five-second samples advance 125 ticks |
| Close RELEASE performance | NTSC Edward 20 → 22 FPS, Emily 20 → 20; PAL Edward 16.6 → 25, Emily 16.8 → 25 |
| Starting / far NTSC Edward | Starting 20 → 25 FPS; far 25 → 25 FPS |
| Source archive rebuild | Fresh extraction regenerates assets and reproduces the release ROM, bank and resource IDs byte-for-byte |

The automated camera route visits cameras 0, 2, 3 and 4. Frozen native comparisons cover all five cameras, including camera 1, at fixed idle poses, orientations and near-plane placements. They inspect both physical framebuffer banks against actual v5 native NTSC reference images at the same canonical poses and include the pause overlay. Host worker functions execute serially, so native comparisons separately exercise the actual command ring and second CPU.

The final native comparison uses the distributed release hash in all four protagonist/region reports. Captures wait for complete framebuffer swaps and pause-overlay redraws before sampling; the compared sample arrays are identical to the canonical v5 native references.

`source-archive-rebuild-v6.json` records the clean rebuild and hashes of the verified build inputs. Final archive code and tools match those inputs; only documentation was updated after that rebuild.

`PERFORMANCE.md` contains exact benchmark positions, nested stage accounting and reproduction commands. Evidence files in `validation/` include `profile-v6-*`, `single-v6-*`, `release-v6-*`, fresh `release-v5-final-*`, `renderer-comparison-v6.json`, `raster-comparison-v6.json`, `raster-v5.txt`, `raster-v6.txt`, `band-comparison-v6.json`, `native-q15-v6.json`, `native-profile-v6-ntsc-*`, `native-release-v6-*`, `native-v5-ntsc-*`, `native-render-comparison-v6.json`, `movement-v6-*` and `emulator-v6-*`. `unchanged-runtime-v6.json`, `memory-v6.json` and `split-review-v6.md` record source identity, memory and split selection. The movement tool names its build outputs `movement-v4-*`; archived reports are renamed v6 and contain the actual release ROM hash.

Gameplay, collision and clock semantics are preserved. Actor advancement and animation/root interpolation remain byte-identical to v5; prepared rotation changes affect repeated geometry transforms while retaining exact arithmetic. The original game installations and imported asset bank were not modified. The help panel remains temporary and has not received dedicated optimization.

## Artifact identity and memory

Release ROM: 720,896 bytes; checksum `0x5B3C`.

SHA-256: `29c8fcdd7f39a396b2657280f1220511a464823fe5897f9bd667dee637f169a5`

Asset bank SHA-256: `c257542990a41792910f6d542eee040a8aefe985e9ab1801e31dfda67db12213` (unchanged).

SH-2 loaded module: 23,460 bytes; BSS: 85,324 bytes; total static SDRAM: 108,784 bytes; end `0x0601A8F0`. The linker-enforced stack reservations remain 12 KiB for the master and 4 KiB for the slave. Worker ring/private scratch accounts for 4,876 bytes; its largest raster frame is 2,172 bytes, with no recursive slave raster calls.

## Limits

Performance and native arithmetic/rendering checks run in PicoDrive. The stage profiler uses a separate timer-capable core; no physical 32X test has been performed. The fixed row split preserves cache coherence and row ownership by construction and measurement, but real bus contention and compatibility remain unmeasured.

The comparisons verify parity with the implemented v5 renderer rather than complete original-game rendering parity. Exact historical material/sphere behavior and the complete original controller acceleration/collision state machine remain unverified. LIFE/track execution, multiple actors, inventory, puzzles, combat, room/floor transitions, cutscenes, audio, saving and game completion remain absent.
