# Validation — revision 7, 2026-10-07

Release SHA-256: `999a08dee49185194b86e15d7eb86cb15fc0e8dba465602be54150499be97d84`.
ROM size: 3,014,656 bytes. Header checksum: `0x90B4`.

## Implemented milestone

1. Freeze and exercise the original FITD core through selected attic paths.
2. Execute required LIFE/track programs and preserve actor/object/variable state.
3. Render multiple active actors with painter order, masks and correct restoration.
4. Connect actions, inventory, books and basic combat to the original item scripts.
5. Execute the first floor transition, walk into the adjoining room and return with items retained.

| Check | Result |
|---|---|
| Native 68000/SH2 RELEASE build, Marsdev GCC 13.1.0 | Passed; no C++ compiler warnings. The freestanding SDRAM load segment retains its expected RWX linker warning. |
| Compact model bank versus pre-change renderer | 876 exact comparisons before gameplay changes; geometry/material data retained. |
| Original animation timing/root totals | Original walk/run durations, fractional key crossing and irregular PAL/NTSC catch-up passed on the v7 bank. |
| Eye points/FPS border | Real renderer keeps type-2 points one pixel and FPS outside the game image. |
| Shared host engine, both characters | Chest/rifle offer and take, book/read/close, drop/retake, projectile flight/stop/retake, timed enemy arrivals, melee/rifle damage and ammunition passed. |
| Stair/room round trip, shared host engine | Floor 0 → floor 1 room 6 → room 0 → attic; manual control restored and inventory retained, both characters. |
| Cached foreground props versus full ordered model redraw | Twelve exact framebuffer comparisons, both characters, representative positions/cameras. |
| Actual RELEASE cartridge, Edward/Emily × PAL/NTSC | Title selection, controller-driven Search/chest/rifle pickup, original down/up stair tracks, adjoining room and retained inventory passed. |
| Both native physical framebuffer banks | Identical frozen images in attic, stair landing and attic return for all four cases; combat images also checked in both NTSC cases. |
| Actual RELEASE combat, both NTSC characters | Original timed arrivals, controller-selected Fight, melee kill, rifle equip/fire, second enemy damage and ammo use passed. Dog HP 0, zombie HP -2, ammo 2, player HP 19 at the combat checkpoints. |
| Actual RELEASE clock | All final five-second route samples advanced 125 world ticks; gameplay remains 25 Hz independently of render FPS. |
| Memory guard | 233,160 bytes static SDRAM; end `0x06038EC8`, 12,600 bytes below stack reserve; bounded actor/span pools and linker guard. |

The native checker derives layout offsets using the actual SH2 compiler. Inputs operate the menus/actions; debugger placement shortens travel and positions combatants. It waits for the original arrival track to finish before measuring combat. Captures wait for completed swaps and compare scene pixels from both banks. These diagnostics are not an uninterrupted human playthrough of every puzzle.

## Original core reference and observed differences

The canonical source is yaz0r/FITD commit `543e22bc78b64405537ae545ecd382dcdf2c12b2`. The actual original game core was compiled with deterministic input/time and presentation/audio stubs. Its selected paths cover idle, chest, pushing, book reading, timed dog arrival and the first down stair sequence. All 207 variable values agree at the twelve recorded scenario endpoints (six paths × both characters). The reference chest emits item offer 3 and the book script requests original book index 1/type 0. Native pickup UI is verified separately.

Both cores reach floor 1 room 6, finish track 31, restore manual movement and return to LIFE 549. The reference landing Z values are -1873/-1867; native values are -1895/-1898. That small displacement difference reflects this conversion's approved fractional animation clock and discrete transition/collision boundaries. It is not an assertion of frame-exact desktop parity.

Known behavior differences remain: collision/pushing uses bounded substeps and axis sliding rather than FITD's accumulated animation collision offsets (a fixed push scenario moves the chest about 882 units natively versus 596 in the reference). Combat pacing/contact checkpoints also differ; native combat is functional but has not reached exact reference parity. Native B+Up replaces the original manual run gesture. An exactly opposite track goal gets a defined turn to avoid a stall. Projectile sweeps and backwards stopping searches are bounded. The pinned core's rifle ray wall-test branch appears inverted; native rays stop on obstructions and have direct damage tests instead of claiming exact agreement with that branch.

The full graphical PC reference was not built because its external graphics/audio dependencies are absent. The headless oracle establishes selected core behavior, not original-PC pixels, menu behavior or full-house correctness. `tools/reference/` contains the harness, patch, pinned source hashes and rebuild helper. `reference-observations-v7.json` preserves reference/native endpoints and differences.

## Remaining limits

Only floors 0 and 1 are loaded. Floor 1's full puzzle/room sequence is imported but unverified. Other resources/LIFE records are present to support those objects, not a claim that the entire house is playable. Later-floor requests end the build instead of reading missing assets.

The actor pool is capped at 24 (peak 14 in the validated route). Unknown opcodes and script/asset bounds errors stop with a diagnostic. Audio/PWM playback, particle presentation, original graphical inventory models, complete text typography, SRAM saving, full game progression and physical 32X testing remain later work. Static cache rebuilding can produce a slower frame. Multiple enemies and near-camera models can lower render FPS; see PERFORMANCE.md. Original game installations were read only.

Reports in `validation/` identify the final ROM and asset hashes. Earlier v6 validation/math/raster results remain historical evidence; their full exhaustive suites were not repeated for this gameplay milestone. The source archive clean rebuild receipt records the generated bank, resource IDs and release ROM identity.
