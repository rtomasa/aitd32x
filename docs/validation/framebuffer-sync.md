# Aligned framebuffer writes and compact SH2 waits

## Changes

`pixel_words.hpp` shares aligned longword copy/fill loops across solid raster
spans, master/slave background repairs, architectural mask repairs, scenery
readback, panels, portraits, raw images, RLE fills, eligible LZ4 matches and
video clearing. It uses the normal framebuffer aperture, so black pixels are
written. Halfword alignment leads/tails stay word-sized; mismatched copy
alignments fall back to word copies. Partial pixels retain their existing
read/modify/write handling and glass/depth-tested pixels retain selective
stores. Copies never round outward or read beyond their supplied word count.
LZ4 matches at offset two remain sequential word copies; offset four or larger
can use longwords. Row padding remains untouched.

`32x/wait.hpp` replaces padded worker/mapper/audio/save polling with compact
assembly loops. The producer reads its own write index once and polls the
slave's read index using unsigned wrap-safe subtraction. Completion reads
remain cache-through and payload fences remain in place. The delay-slot
`add #0,address` keeps PicoDrive from misclassifying these loops as sleeps.
Video initialization, framebuffer swaps, palette permission and slave-ready
waits use the same pattern. Audio interrupts stay enabled. Controller snapshots,
25 Hz simulation, 60 Hz animation and 68000 service loops are unchanged.
Required DIVU latency and bootstrap delay instructions remain intact.

The implementation was informed by the polling wrappers and aligned stores in
the [Virtua Racing patch](https://github.com/AlbertoBen/sega-vr-disasm/tree/30fps-patch),
reviewed at `39a3e13`; it incorporates no game code or resources from that project.

## Focused verification

- RELEASE ROM and host library build; only the existing RWX linker warning.
- Decoder checks: independent word-copy/fill references for lengths 0–257,
  both word alignments, zero pixels, mismatched alignment and forward overlap.
  Raw/RLE/LZ4 decoding covers all four byte alignments, row padding, boundaries,
  offset-two/four/six/3200 matches and 200 camera-row indices. All pass.
- Raster band checks: 200 cases, 12 boundaries, 2,400 comparisons, 6,600
  primitive calls; pixels, damage and guards pass, including glass and black.
- Native SH2 scheduling check passes NTSC/PAL: both characters, glass/cupboard,
  bedroom door and contact group, forced ownership extremes and both banks.
  Reports: `build/sh2-scheduling-native-{NTSC,PAL}.json`.
- Native startup checks pass NTSC/PAL with `--short-arrival`: original images,
  menu/portrait navigation, biographies, banked arrivals with nonzero audio,
  skip and private-SRAM save/load/restart. Reports:
  `build/startup-native-{NTSC,PAL}-short.json`.
- Linked bank/RAM/protected-ROM limits pass. Disassembly confirms aligned
  `mov.l` stores and compact delay-slot address writes. `git diff --check` passes.

Only private emulator memory is used. User battery saves and prior release
bundles are untouched. This is PicoDrive evidence; real 32X, EverDrive and
MiSTer timing/compatibility are not established by these checks.

## Comparison with the preceding build

The prior scheduling ROM/ELF/host library is preserved in ignored
`build/framebuffer-sync-reference/`. Assets are identical. NTSC report:
`build/framebuffer-sync-performance.json`.

| Sample | Before | After |
|---|---:|---:|
| 10-second early-game trace | 24.2 draws/s, 251 world ticks | 24.2 draws/s, 251 world ticks |
| Frozen floor 3, room 1, camera 3 | 19 draws/s | 19 draws/s |
| Frozen floor 6, room 0, camera 2 | 29 draws/s | 29 draws/s |
| Frozen floor 7, room 1, camera 3 | 29 draws/s | 29 draws/s |
| Start-menu up | 3 VBlanks | 2 VBlanks |
| Character selection left | 4 VBlanks | 3 VBlanks |
| Inventory up | 6 VBlanks | 5 VBlanks |

Other sampled menu directions retain their previous latency. Frozen scene
pixel hashes match. These are short, display-quantized comparisons; they do
not demonstrate a general FPS increase or predict MiSTer gains. The live
floor-6 continuation measures 22 versus 24 draws in one second, with 23 versus
24 updates at the sampling boundary; it is too short to establish a speedup.
The reported MiSTer v260603 US/NTSC starting-room result needs a matched retest.
Longword stores reduce CPU store/branch work; the physical framebuffer bus
still transfers 16-bit words, so this is not a claim of doubled bus bandwidth.

## Memory and candidate

ROM: 14,155,776 bytes, unchanged. BIOS module: 84,916 bytes (+448).
BSS: 160,672 bytes, unchanged. Static end: `0x0603BF58`, stack margin 168 bytes
(previously 616). Video initialization and scenery readback moved to protected
ROM to fit; raster code stays in SDRAM. Reserved stacks are unchanged. No new
buffers, assets, mapper layout, save fields or migration. These figures apply
to RELEASE; PROFILE was not built.

Candidate: `build/AITD32X.32x`, checksum `EBBF`, SHA-256
`1312eecb7acf08503b8815a2e20a90ca530c8008ae043982396930e7d7bcd4b4`.
No commit was created.
