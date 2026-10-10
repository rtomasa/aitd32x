# Bounded row-split review

| Variant | Edward near FPS / CPU | Emily near FPS / CPU |
|---|---:|---:|
| fixed100 | 21.6 / 35.927 ms | 20.0 / 37.999 ms |
| fixed90 | 21.2 / 36.218 ms | 20.0 / 39.005 ms |
| fixed110 | 21.4 / 36.290 ms | 20.0 / 38.403 ms |
| fixed120 | 20.0 / 37.151 ms | 20.0 / 39.235 ms |
| midpoint | 20.6 / 36.700 ms | 20.0 / 38.835 ms |
| hybrid | 21.4 / 36.107 ms | 20.0 / 38.185 ms |

CPU is completed PROFILE frame time minus flip/VBlank wait; these timers use the PicoDrive emulator timing model.

Recommendation: retain the tested fixed row100 for this release. No constant variant improves both characters; midpoint selects rows114–115 and regresses the close view. The optional hybrid preserves100 whenever it crosses the actor, centers only wholly one-band large actors, and uses full-master raster below64 visible rows. It adds ~0.18ms close-view overhead and provides no observed FPS gain in the requested camera0 cases.

Hybrid far Edward: height55, worker disabled, 25FPS / 29.463ms CPU. Hybrid middle Edward: height76, split100, 25FPS / 31.816ms CPU.

Hybrid is an isolated optional source at work/performance-v6/hybrid-candidate. It changes only renderer projection bounds and worker.hpp/cpp relative to the root combined candidate. Root production/candidate sources were not edited. No extra RELEASE sweep was performed because there was no improvement to validate.
