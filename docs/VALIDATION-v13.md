# Revision 13 validation

Release ROM SHA-256: `de9781ccbbf437a7a64c461626816b61e595b18eb3316cde0966e208440610c1`. ROM 3,801,088 bytes, header checksum 168F. Module 85,652 bytes, BSS 159,968 bytes, static end 0x0603BF78: 136 bytes below the unchanged 12 KiB master / 4 KiB slave stack reservation. Native linker assertions pass. The eight-entry dual-SH2 raster queue is unchanged. Later features need careful RAM reuse.

This revision changes static-cache dependencies and adds build-time drawing programs for fixed skeleton-free props. Movement, LIFE, original assets and the approved v12 bezel/padding layout are retained.

Focused checks completed:

- Stock PicoDrive release trace of sofa-room to hall, followed for eight seconds: NTSC Edward and PAL Emily, with v12 baselines. Original movement/room links and scripts run after diagnostic setup. No script faults or fatal codes. The late repeated bake disappears; two initial long frames remain. See PERFORMANCE.md for measured values and scope.
- 432 prepared prop entries, each with two collision-bounds modes: 864 exact comparisons against v12's ordinary renderer, including every pixel, cached coverage span and reported screen bound. Three relocated/nonorthogonal door fallback poses also match. Both character banks are covered.
- Exact 320×224 framebuffer and selected world-state parity on 345 frames for each character (690 total), including settling in the sofa room, real controller crossing and 200 hall ticks. This catches incorrect mask/order cache reuse. The prior renderer library uses only added diagnostic host exports; its engine/render implementation remains v12.
- Twelve fresh-versus-cached/unbaked window, hall and opening-door cases pass for both characters. Focused native renderer checks pass for eyes, glass CPU split, contact depth, masks, black/colored coverage and particles. Generic raw/RLE decoder parity and capacity checks pass. Compressed camera assets are now deliberately rejected because the bank supplies raw cameras.
- Native original attic → first-floor stairs → room/camera links → attic round-trip passes. Sustained native chest pushing still advances about 25 world ticks/second, reaches the same end positions as v12 and triggers one cache rebuild. No pushing speedup is claimed.
- A clean build of the delivered source archive with independently reimported assets reproduces the release ROM byte for byte.
- Fresh importer output is byte-identical to the release bank: SHA-256 `ee92c4001158d86417480f605d8332da9b487fd3d887a1298af39997d458cbf7`. All 1,847 prior payloads, asset names/IDs and source-file hashes are unchanged; one type-14 STATIC_RASTERS asset is appended. All 1,848 flags are zero.

Reproduce the focused checks with `make host build/check_render build/check_decode`, `tools/check_room_transition.py CORE --mars MARS --label v13`, and its PAL/Emily variant. The two differential tools take `--reference /path/to/v12-project`; build that reference with the current diagnostic tools/host.cpp (no runtime changes). Reports are in docs/validation. The source ZIP excludes original asset banks and build products; the importer requires the same original installation and a host C++ compiler.

Validation is limited to these focused cases. Previous UI, puzzles/combat, stairs, monster, camera, particle and sorting checks are retained as historical reports, not represented as a full rerun. Full-house conversion, audio, SRAM saving, full PC behavior parity and physical hardware validation remain unfinished.
