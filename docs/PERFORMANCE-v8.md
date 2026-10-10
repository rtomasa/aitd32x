# Revision 8 performance

Unmodified PicoDrive DRC_SH2, release ROM. Five-second samples count completed game draws; the simulation is 25 Hz.

| Scene | Region / character | Render FPS | Simulation ticks |
|---|---|---:|---:|
| Attic, near camera | NTSC / Edward | 25.0 | 125 |
| Attic, near camera | PAL / Emily | 25.0 | 125 |
| Chair contact, room 5 | NTSC / Edward | 12.0 | ≈125 |
| Chair contact, room 5 | PAL / Emily | 12.4 | ≈125 |

V7 measured 20.0 and 20.8 FPS respectively in these views. Backface culling reduces primitive fill/overdraw. The first-floor contact correction adds work only around nearby intersecting models; it uses an 8 KiB tile shared with the normal face-sort scratch, and skips ground pickup objects as contact triggers.

The contact test places the player beside the chair, selects Push through the controller UI, releases the action, settles for two seconds, then samples for five seconds. The depth correction is substantially more expensive than ordinary cached drawing. It repairs the reported limb/prop ordering, but contact views remain a performance limitation; 25 FPS in the attic does not imply 25 FPS throughout the house. Movement still keeps its original clock.

The FPS sampler can request a display-only redraw without a simulation/game frame. NTSC's sample observes 130 swaps but 125 game frames: five FPS-only redraws. The counter intentionally reports 25.0 game FPS. Validation now accounts for those display-only swaps instead of incorrectly treating their difference as a counter failure.

These are emulator measurements for the documented poses, not a whole-game minimum or physical-hardware measurement. Scene changes can cause a one-time static-cache rebuild. Details and remaining limits are in VALIDATION.md; historical measurements are in PERFORMANCE-v7.md.
