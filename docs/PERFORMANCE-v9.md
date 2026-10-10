# Revision 9 performance — 2026-10-07

Matched release cartridges on unmodified PicoDrive DRC_SH2, using the same default clock settings and imported bank. Each FPS result counts completed game draws during five seconds of emulator VBlanks. Diagnostic placement makes the scenes repeatable; controller input selects Push and then holds A+Up for moving-object samples.

| Scene | V8 FPS | V9 FPS | V8 → V9 cache rebuilds |
|---|---:|---:|---:|
| Hallway camera 2, beside foreground door | 6.0 | 15.2 | 0 → 0 |
| Hallway camera 3, close to camera | 7.8 | 15.0 | 0 → 0 |
| Moving closed attic chest, camera 3 | 3.4 | 11.4 | 17 → 1 |
| Moving chair, camera 5, room door open | 3.4 | 9.6 | 15 → 1 |

These matched comparisons use NTSC Edward. PAL Emily measures 11.0 FPS pushing the chest and 9.8 FPS pushing the chair with the door open. Additional NTSC views measure 21.6 FPS in front of the bedroom window and 15.0 FPS with the far hallway/bow-room door open. These are samples, not whole-game minimums. The native vase/dog regression's stationary chair view measures 16.8 FPS for NTSC Edward and 16.6 for PAL Emily; it releases the action before sampling, unlike the sustained pushing rows above.

An additional stress pose with the room door closed and filling the camera measures 2.6 → 7.0 FPS while pushing the chair (NTSC Edward), and 7.0 FPS for PAL Emily in v9. The open-door case is the visible furniture test. Both are retained with descriptive evidence filenames.

## Causes and changes

The v8 instrumented camera-3 pose spends about 84.4 ms/frame in the contact correction (FRC calibration ratio 1.001). Its broad screen-overlap group included unrelated scenery, and ordinary idle/walking actors paid for correction simply by standing near a door. Flat floor patches also triggered false contacts. V9 restricts correction to Search/Push, collects physically nearby props, excludes floor planes, and reapplies unrelated foreground props through their ordinary painter position. Reciprocal depth is calculated once per vertex when near clipping is unnecessary. Contact damage bounds are updated by row rather than by every pixel. The contact renderer still adds a substantial cost during sustained pushing.

Original LIFE scripts change a chest between TYPE 16 while pushing and TYPE 0 while stationary. V8 repeatedly put it back into the background cache and rebuilt the scenery. V9 keeps a slot dynamic after movement/animation or a changed static pose until the view changes. The one rebuild during each pushing sample removes the newly moving prop from the bake; subsequent motion needs no rebuild. Visible primitive bounds now omit culled/offscreen geometry, reducing needless restoration and overlap work.

Foreground masks now read the original camera image from ROM. They previously read the composite static cache, which could repaint baked door/window pixels over another actor. Compressed cameras have a 600-byte row index; no second 64 KiB image is allocated. World ordering uses planar camera distance without mounted-prop height buckets. Glass retains the existing screen-door approximation.

The native worker wait loops space shared-RAM reads to avoid a PicoDrive polling-detector missed wakeup after completion has already been published. Both SH2s remain enabled; emulator settings and source are unmodified for release comparisons.

## Movement clock and scope

Movement values and the 60 Hz animation / 25 Hz simulation clock are unchanged. Both native gameplay regressions observe 125 ticks across five seconds. Slow render samples can end while another frame is in progress: e.g. the chest report publishes 122 ticks over 4.85 seconds between its completed-frame timestamps, about 25.15 Hz. The report records both timestamps and checks tick progress against the same elapsed interval, within one tick of phase rounding. A raw endpoint difference below 125 does not by itself indicate a slower simulation.

Evidence is in `validation/release-v9-*.json`, matched `baseline-v8-*.json`, `profile-v8-hall3-contact.json`, and `memory-performance-v9.json`. The instrumented profile has nested scopes and uses the FRC-only timer shim; its stage totals must not be summed as independent costs. The headline table uses release ROMs on the stock core. No physical 32X measurement was performed. Historical v8 results remain in PERFORMANCE-v8.md.
