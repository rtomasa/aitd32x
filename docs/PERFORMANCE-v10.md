# Revision 10 transition performance — 2026-10-07

The v9/v10 comparison uses the release cartridges on unmodified PicoDrive DRC_SH2 at its default clocks, with the same imported data bank. Diagnostic placement enters the original stair trigger; original tracks and controller movement execute the stair/room round-trip. This measures the first completed frame after a view change, including simulation update, scene work, rendering and presentation.

| Transition, NTSC Edward | V9 first-frame VBlanks | V10 first-frame VBlanks | V9 → V10 time |
|---|---:|---:|---:|
| Attic stairs → floor 1, room 6 | 17 | 10 | 283.3 → 166.7 ms |
| Room 6 → room 0, same camera | 16 | 0 | 266.7 ms → within the current refresh interval |
| Room 0, camera 0 → camera 1 | 19 | 13 | 316.7 → 216.7 ms |
| Room 0, camera 1 → camera 0 | 16 | 10 | 266.7 → 166.7 ms |
| Room 0 → room 6, same camera | 16 | 1 | 266.7 → 16.7 ms |
| Return stairs → attic camera 4 | 13 | 10 | 216.7 → 166.7 ms |

Timing comes from the 68000's VBlank sequence captured at the start of an update/render iteration and read when the resulting frame is displayed. It is quantized by the refresh interval, not a CPU timer or an FPS estimate. A zero-VBlank difference means the frame completed within the same refresh interval; it does not mean zero processing time. The initial warm/paused trace entry is excluded from the table. V9/v10 first-floor track landing positions and camera-boundary positions match on this route; the tick origins differ because warm-up/render timing differs. These are scene samples, not whole-game worst cases.

PAL Emily completes the same original round-trip. V10's measured new-camera/floor frames are 8, 11, 8 and 8 VBlanks (160, 220, 160 and 160 ms). Its same-camera room links take 1 and 2 VBlanks (20 and 40 ms). No matched v9 PAL transition run was needed for this focused revision.

## Changes and remaining cost

V9 drew each static model once in color and again in monochrome to collect its foreground coverage. V10 records the visible silhouette during the colored draw, then creates the same bounded coverage-span cache. Black model pixels remain represented; glass records only its screen-door pixels, and original-camera masks remove hidden pixels. Both SH2s write disjoint whole-row portions of an uncached 8000-byte bitmap. It reuses the existing contact/face-sort scratch, after copying at most 384 face indices to a 768-byte local array. No second background image is allocated. BakeBackground now uses that completed colored pass directly, without the old second draw and final full-frame restore.

Camera binding/decompression happens once when rebuilding, rather than in both Update and Draw. A room link that retains the same camera asset preserves the scene cache and updates the room binding. Actor/body/pose changes still invalidate or leave the bake through the existing per-slot rules. A changed camera resets that history. The renderer reloads CRAM only if the palette actually changes; the first game frame still loads the correct game palette before presentation.

The independent world/animation clocks and approved walk/run speeds are unchanged. A five-second NTSC moving-chest sample measures 11.8 FPS with one cache rebuild; its 124 world ticks over 4.95 seconds of completed-frame timestamps remain consistent with 25 Hz. V9's corresponding sample was 11.4 FPS. This revision targets transition work, not a large steady-state FPS increase.

Camera changes still rebuild and render the new scenery, so the documented 160–220 ms first frames remain noticeable. This revision reduces the hitch rather than eliminating it. Physical hardware timing is unverified. See PERFORMANCE-v9.md for the prior hallway/moving-furniture improvements and VALIDATION.md for the targeted checks.
