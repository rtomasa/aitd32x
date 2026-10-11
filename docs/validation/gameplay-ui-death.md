# Original gameplay typography, inventory and death

Gameplay text now retains all 204 original ENGLISH:0 records, including the
copyright/I-Motion symbols and ë in the arrival's composer credit. TEXT and
STARTUP_TEXT retain their existing IDs and share one original-glyph payload.
Gameplay messages, pickups, pause/options and inventory use the same original
16-pixel proportional font as startup and documents. Wrapping uses pixel widths;
bounded labels ellipsize safely. Shared glyph spans return their advance to
avoid repeated table lookups throughout these screens and reading.

Inventory restores the original list/preview/actions layout, gold rails,
scrolling arrows, highlight colors, shadows, found-body models and quantities.
The five-row list scrolls; console action/back controls remain. Health stays
visible. Panels/labels are composed on input changes and cached using the
existing scenery background. Animated previews restore their damage without
redrawing labels or decoding panels. Gameplay and previews share the stable
four-face-run merge sort. Preview faces wholly inside their viewport bypass
clipping; disjoint faces are rejected. The original 60 Hz orbit clock remains
independent of the paused world, with presentation capped at 30 FPS.

Death continues original player LIFE 39→555→556→558→554 and zombie LIFE 557,
track movement, three cemetery views and ITD_RESS:12. The final picture holds
for 240 original timer ticks (four seconds); GAME_OVER holds for 120 ticks
before returning to the title. A/B/C/Start skips to the title. The existing
scenery cache, image buffer and presentation clock are reused. Picture/end
holds retain idle pixels and stop the simulation. DEAD_PERSO permits floor 6
only during death; ordinary gameplay remains limited to floors 0 and 1.

## Build and memory

- ROM: **5,373,952 bytes / 5.125 MiB**, SHA-256
  `b0fc4b51bea4d007b40596370e56d46a166cba07ee373cfd96cd3ab92056fa28`.
- Bank: **2,052 IDs**, 5,224,474 logical bytes, SHA-256
  `b1f374b905f1e205f75923039b922d05d398c2d29aa4815f24a6a27012fd360d`.
- Fixed assets: **3,910,248 bytes**; extra images: **1,161,242 bytes**.
- BIOS module: **83,380 bytes**, physical end **4,124,700**; **69,604 bytes**
  remain below 4 MiB.
- BSS: **160,176 bytes**, unchanged. Static SDRAM ends at **`0x0603B768`**,
  leaving **2,200 bytes** before the unchanged 12 KiB/4 KiB stack reserves.

Compared with the preceding startup/glyph release, ROM grows by 256 KiB,
fixed assets by 12,820 bytes and extra images by 252,954 bytes. Linked module
shrinks by 432 bytes; no global image/geometry buffer or save field is added.
All 2,034 existing asset IDs are preserved. Existing payload changes are
limited to TEXT and the taller message bezel required for two proportional
rows. Save schema and fingerprint `0x0eebc721` remain unchanged.

## Focused validation

`make assets`, `make -j2 all host`, the linked bank-layout check and
`git diff --check` pass. Relevant checks:

```sh
python3 tools/check_gameplay_ui.py --core .local/tools/picodrive_libretro.so
python3 tools/check_death.py
python3 tools/check_death_native.py .local/tools/picodrive_libretro.so
```

The typography proof checks all 67 used original glyph bitmaps, all 204 source
records and bounded/clipped wrapping. Host inventory checks both characters,
rotating previews, static-section pixel stability, world pause, scrolling,
original action-script dispatch and both framebuffer restorations. Previous
release saves load and re-save with byte-identical payloads for both characters.

PicoDrive libretro NTSC/PAL inventory measurements over three seconds per item:

| Preview | NTSC FPS | PAL FPS |
| --- | ---: | ---: |
| Actions | 30.00 | 30.00 |
| Oil lamp | 30.00 | 30.00 |
| Gramophone | 30.00 | 25.33 |

The sampled static sections remain pixel-identical throughout animation,
both framebuffer banks are used, simulation ticks stay frozen, and controller
back navigation restores gameplay without LIFE faults. The complex Actions
and gramophone meshes exercise the larger original preview models. These
figures measure completed presentation draws; the rotation clock does not
slow when rendering falls below 30 FPS.

Host death checks complete both original movies in 843/825 world ticks with
all three cemetery views, correct player/zombie scripts and exact original
picture pixels. Holds freeze the simulation, title/skip preserve the private
save, and the live saved game reloads successfully. Native NTSC follows the
complete death route, exercises banked rendering, restores bank 1, displays
the original picture for four seconds, and returns to the title after the end
hold. Only health is modified in private emulator RAM to shorten combat;
original scripts choose and run the cinematic.

Evidence remains ignored under `build/`: `gameplay-font-validation.json`,
`gameplay-ui-import.json`, `gameplay-ui-layout.json`, `gameplay-ui-check/report.json`,
`death-check/report.json`, `death-native-NTSC.json`, corresponding captures and
build logs. No battery saves, original resources or `.local/baseline` were
changed. These are emulator/host results; physical hardware is unvalidated.
No commit was made.
