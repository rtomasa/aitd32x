# Performance — revision 7

Revision 7 adds active world objects, original script execution and multiple models to the v6 renderer. Measurements below use the final RELEASE ROM on an unmodified PicoDrive DRC_SH2 libretro core, in fresh processes, with FPS enabled. They are emulator measurements, not physical-console results.

| Case | FPS | Simulation ticks in 5 seconds |
|---|---:|---:|
| Edward, close NTSC, camera 0 `(3231,0,-3733)` | 20.0 | 125 |
| Emily, close NTSC, camera 0 `(3231,0,-3705)` | 20.0 | 125 |
| Emily, close PAL, same close position | 20.8 | 125 |
| Edward, standing after attic return, NTSC | 25.0 | 125 |
| Emily, standing after attic return, NTSC | 25.0 | 125 |
| Edward, standing after attic return, PAL | 24.8 | 125 |
| Emily, standing after attic return, PAL | 25.0 | 125 |

The near profiles compare actual completed renders with physical bank swaps; the two counts agree. The standing samples follow the same item/stair/room route and keep both items. Snapshot boundaries can shift a five-second count by a frame. V6 had 22 FPS for close NTSC Edward, 20 for Emily and 25 for the close PAL cases. The extra gameplay/world work has a measurable cost; this milestone preserves the approved movement rate, not every v6 render benchmark.

## Static object cost and correction

A first naive multi-model build redrew nine unchanged room models on every frame. Its starting NTSC Edward PROFILE sample measured 6.4 FPS. Caching static models in the background raised that sample to 23.6 FPS. These diagnostic samples precede the final combat/foreground cache and are retained as development evidence, not final release measurements.

Correct ordering requires furniture in front of a moving actor to remain visible. Redrawing those overlapping models reduced the pre-span close RELEASE samples to 16.8 FPS for Edward and 15.0 for Emily. The final coverage-span cache copies only each prop's visible pixels, preserving ordered rendering while restoring both close NTSC cases to 20.0 FPS. The host checker compares the cache against full sorted model rendering in twelve representative positions across both characters; native checks also compare both completed banks.

Cache rebuilding is occasional work: camera changes, animated/changing props and push completion can cost a slower frame. Multiple enemies, large near-camera models, menus and camera transitions can produce lower FPS than the standing sample. The 25 Hz world still catches up before drawing; pause/menu time is excluded. Gameplay checks verify clock progress, item state and native combat rather than treating a high FPS display as proof of logic correctness.

The FPS counter remains the same small border overlay from v6. Earlier profiling measured about 0.6 ms per frame for it. No temporary help-panel optimization was added; that panel has been replaced by the gameplay controls.

## Reproduce

```sh
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --region NTSC --character edward --distance near --label release-v7
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --region NTSC --character emily --distance near --label release-v7
python3 tools/profile_renderer.py /path/to/picodrive_libretro.so --region PAL --character emily --distance near --label release-v7
```

`validation/release-v7-*.json` identifies the final ROM hash. `validation/gameplay-native-*.json` holds the route/standing samples and clock results. The inherited PROFILE counter shim, nested-stage interpretation and dual-CPU caveats remain documented in `PERFORMANCE-v6.md`. The final delivery uses RELEASE without profiling instrumentation.
