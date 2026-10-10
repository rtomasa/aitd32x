# Revision 12 UI validation

ROM SHA-256: `636164edbcf90de49065d97b025c23b1a0c4cacfbd3c1b06af178601aa74201c`.

Revision 12 adds the original textured gold bezel and title plaque around the existing title, pickup, inventory/actions, message, book, pause, death and script-error panels. The simple layout and controller mappings are retained. Text has a minimum four-pixel black margin inside the original eight-pixel gold border. The title, message and pickup rectangles have small height adjustments; headers and control hints are inset, and message/book wrapping uses 35 characters to retain the side margins. No game movement, actor rendering, static cache, transition logic or script semantics changed.

## Focused checks performed

- Original frame sprites were decoded from ITD_RESS.PAK resource 4 using the pinned FITD sprite-directory format. Corners, rails and the small plaque are source graphics, not approximations.
- Host captures cover all seven panel assets and every overlay mode; border pixels are checked against the imported panel data, and a four-pixel inner ring must remain black in every capture. Title-palette matching preserves the title image’s palette. All captures were visually reviewed.
- Closing each host overlay restores the exact preceding scene through normal damage restoration, including black pixels.
- Original text entry 2 is exactly `(C)1992 I-MOTION/INFOGRAMES`. Source bytes A9 and FA previously became unsupported ASCII replacement glyphs.
- Actual RELEASE ROM loaded in stock PicoDrive in NTSC and PAL. Title C selection, Start play, C inventory, A item actions, C return, and Start pause/resume passed. Title, inventory, actions and pause bezels match their assets in both physical framebuffer banks. Inventory/actions/pause hold the world tick clock fixed.
- All 1,839 preceding asset payloads other than TEXT are byte-identical to v11, and their IDs and original input hashes are unchanged. Seven frame assets are appended. Source assets are read without modifying the original installation.
- Native build passed linker memory assertions: module 84,228 bytes, BSS 160,568 bytes, static end 0x0603BC40, 960 bytes below the unchanged stack reservation. ROM is 3,473,408 bytes, checksum 6E0F.

Commands: `make host`; `python3 tools/check_ui.py --core /path/to/picodrive_libretro.so --region NTSC` (and PAL). Reports and captures are in `validation/ui-v12-*`. These are UI checks, not another complete gameplay/performance run. Native pickup/death/book paths inherit their unchanged controls; their new panel graphics were checked through the same host engine.

## Inherited validation and remaining work

`VALIDATION-v11.md` preserves the latest broader gameplay, sorting, cache-history and transition checks. `PERFORMANCE-v11.md` preserves those actual-ROM measurements. They remain historical evidence, not new v12 results. Full-house conversion, audio, SRAM saving, complete PC behavior parity and real-hardware testing remain unfinished.
