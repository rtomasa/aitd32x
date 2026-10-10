# Startup casing and rendering performance

Menu labels and arrival messages now retain their original English casing.
The appended `AS_STARTUP_TEXT` contains the original ENGLISH:0 casing and glyph bytes;
existing `AS_TEXT`, gameplay UI, asset IDs and save fingerprint remain unchanged.
The adapted third menu item reads `Replay Intro`.

Static startup fades update CRAM without restoring or redrawing their pixels.
Biography paper and the selected portrait are composed once using the existing
background and hidden framebuffer. Shared proportional-font rendering writes
horizontal runs rather than one span per pixel, improving credits, biographies,
messages and every gameplay document that uses that font.

The arrival now shares gameplay's static scenery cache and damage restoration.
Intro doors with no animation asset are cached by complete pose/mask hashes;
scripted movement invalidates them until they settle. Raw banked camera pixels
remain mapped only during scene rendering, providing immutable architectural
masks while RAM holds baked scenery. Camera binding finishes before mapping,
SH2 jobs finish before unmapping, and all relevant geometry/metadata/audio/code
are checked outside the aperture. The original scripted painter order and masks
are preserved during the arrival; gameplay retains its contact-depth repair.
Scene rebuilds preserve presentation fade levels.

The same idle-work reduction applies throughout the game: inventory/action
menus respond to input edges, as pause/document screens already do. FPS sampling
requests an overlay redraw only when its value or readiness actually changes.
The 25 Hz simulation, 60 Hz animation clock and save schema remain unchanged.
The requested reuse rule is also recorded in AGENTS.md.

## Measured performance

PicoDrive libretro 2.04, NTSC. Frozen native entrance poses separate renderer
capacity from world updates. Both physical framebuffer histories exactly match
the preceding startup build at both measured poses.

| Entrance view | Previous capacity | Cached capacity | Scene pixels |
| --- | ---: | ---: | --- |
| Floor 3, room 1, camera 3 | 6.8 FPS | 20.0 FPS | Identical |
| Floor 3, room 1, camera 2 | 4.6 FPS | 20.0 FPS | Identical |

The final ROM's natural moving arrival averages **15.38 / 16.26 FPS** in those
views over **9.10 / 6.95 seconds**. These figures include door movement and cache
rebuilding and are separate from the frozen measurements. The frozen capacity
report predates the final palette-preservation and gameplay idle fixes; its
retained images and settled-pose rendering path are unchanged.

Startup menu/selection/biography idle flips fell from three to zero over three
seconds. On the final ROM, pause/inventory/actions each produce **zero redraws,
zero flips and zero world updates** over five idle seconds after FPS settles.
Navigation produces exactly one draw in each. Inventory test items exist only
in emulator RAM; no battery-save fixture was written.

## Build and memory

The performance measurements above use the following build. The glyph-only
follow-up below has the same ROM size, asset layout and RAM usage.

- RELEASE ROM: **5,111,808 bytes / 4.875 MiB**, SHA-256
  `639ec5fddb8283a7386c0db648dbaf379f1f719069277a7b491f15904ad9981d`.
- Asset bank: **2,034 IDs**, 4,971,520 logical bytes, SHA-256
  `6bd5259e7c89535f906a7979c2d616278fd267f3fce372b7631cbd76a803cb68`.
- Fixed bank: **3,897,428 bytes**. Extra images: **908,288 bytes** on pages 8–9;
  12 raw arrival images and four compressed presentation images.
- BIOS module: **83,812 bytes**, ending at physical **4,112,312**;
  **81,992 bytes** remain below 4 MiB.
- BSS remains **160,176 bytes**. Static SDRAM ends at **`0x0603B918`**, leaving
  **1,768 bytes** before the existing 12 KiB master / 4 KiB slave stacks.

Compared with the initial startup build, fixed assets grow by 5,304 bytes for
the separate text table/directory entry. Extra images grow by 469,395 bytes;
padded ROM grows by 458,752 bytes. Linked SDRAM code grows by 736 bytes, with
no new global RAM buffer/state. Existing audio payloads are unchanged.

## Focused validation

`make -j2 all host check`, decoder parity and the linked bank-layout check pass.
The host lifecycle covers both complete arrivals, both biographies and
Back/reselection, picture pause, fresh gameplay, skip and byte-identical legacy
save payloads. Differential rendering covers **6,493 frames / 6,471 world
ticks**, all 17 views per character, with zero geometry or palette mismatches.
Only rows 180–195 containing intentionally changed mixed-case messages are
excluded from geometry comparison. Document and static-screen glyph/pixel
comparisons also pass. The optional differential fails on any mismatch.

Final-ROM native NTSC covers the complete arrival and gameplay idle menus;
PAL covers natural boot, both biographies, short arrival/skip and private SRAM
save/core-restart/Resume. The full NTSC arrival completes without LIFE faults,
exercises mapper pages 8 and 9, and restores bank 1 at completed/idle boundaries
and gameplay. The frog is visibly shown for 19 NTSC frames (0.317 seconds), with
world time held. Nonzero PCM continues during mapped rendering; this observation
does not measure FM music cue accuracy.

Evidence is retained under ignored `build/`:

- `bank-layout.json`, `startup-fix-build-final.log`, `startup-fix-checks.log`.
- `startup-host-fix.json`, `startup-static-pixels.json`,
  `startup-arrival-pixels-final.json`.
- `startup-performance/before-NTSC.json`, `after-NTSC.json`,
  `after-NTSC-live.json` and their original private pose/image fixtures.
- `startup-native-PAL-short.json`, `startup-text-case/case-validation.json`,
  `startup-raw-camera/import-validation.json`.

All native results are emulator evidence. Physical 32X/mapper arbitration has
not been validated. Original assets, user saves and `.local/baseline` were
preserved; generated outputs remain ignored and no commit was made.

## Original glyph follow-up

Proportional-font startup text now preserves source bytes instead of replacing
copyright `A9` with `(C)` and the I-Motion separator `FA` with a hyphen. This
matches the original credits page and preserves every original glyph throughout
menus and arrival messages. All 204 entries match ENGLISH:0 byte for byte.
Only `AS_STARTUP_TEXT` changed; gameplay text and all other asset payloads and
IDs are identical to the measured build.

Current ROM SHA-256:
`c6f197ad3059ffa4483e80e79accd73d5a55c40baa7f8de1dcf1bb97e3f86592`.
Asset-bank SHA-256:
`e828c778e98de63d3a0464e2e61f4074215572f5450e0813f6b3ea66eba78db5`.
ROM size remains 5,111,808 bytes; the padded text asset remains 5,288 bytes.
No runtime code or RAM allocation changed.

`make assets`, `make -j2 all host` and the linked bank-layout check pass.
A focused NTSC PicoDrive check confirms all 524 pixels of the animated
copyright line match the original font bitmap exactly. This is emulator
evidence; the performance/lifecycle suite above was not repeated for this
text-only change. Evidence is retained in ignored `build/startup-glyph-import.json`,
`build/startup-glyph-native.json`, `build/startup-glyph-copyright.png` and
`build/startup-glyph-layout.log`. No user save was touched.
