# Source provenance

## FITD

Reference: [yaz0r/FITD, 543e22bc78b64405537ae545ecd382dcdf2c12b2](https://github.com/yaz0r/FITD/tree/543e22bc78b64405537ae545ecd382dcdf2c12b2).

The resource formats, group animation/transform interpretation, trigonometric table, camera and occlusion interpretation, protagonist collision-box construction, LIFE/track interpretation and object/inventory/combat state derive from this revision. The host-only `tools/aitdpack/fitd_unpack.c` is adapted from FITD's unpacker, retaining its attribution to Cyril Voila and Mark Adler. Its platform includes and unused zlib wrapper were removed. The root `LICENSE` preserves FITD's GPL license text.

The reference is pinned for reproducibility. Revision 7 verifies selected original gameplay paths with a headless core oracle. Complete graphical desktop/gameplay parity remains unestablished; source differences are documented in docs/VALIDATION.md.

## Marsdev

Reference: [andwn/marsdev, 3318d3f](https://github.com/andwn/marsdev/tree/3318d3f). Toolchain release used: `v1.0.0-rc1`, GCC 13.1.0 for m68k-elf and sh-elf.

The 32X skeleton supplies 68000 startup/controller assembly, SH-2 boot/vectors/interrupt startup and the initial linker organization. Local changes specialize the header, build paths, SDRAM executable layout, startup status handling and fatal exception path. The supervisor, mailbox, video implementation and engine are local additions. Marsdev's MIT text is included in `LICENSE.marsdev`.

## Debug font

`src/render/font.cpp` preserves the MSX font table from Marsdev's older 32X skeleton and its BSD notice: copyright 2005 Marcus R. Brown, James Forshaw and John Kelley. The corresponding [PSPSDK BSD license](https://github.com/pspdev/pspsdk/blob/master/LICENSE) is preserved in `LICENSE.font`.

## Other references

[32XDK](https://github.com/viciious/32XDK) and [Doom 32X Resurrection](https://github.com/viciious/d32xr) were consulted for hardware documentation and platform organization. [Dream in the Dark](https://github.com/Corbachu/DITD) was consulted for console-port organization. No Doom gameplay or Dreamcast renderer code is included.

Validation uses an external [PicoDrive](https://github.com/notaz/picodrive) libretro core. The core and cross-compilers are not bundled in the source ZIP. `tools/picodrive-frt.patch` is a counter-only addition to its SH-2 peripheral implementation for profiling, with context from the MAME-licensed source (notaz 2013; irixxxx 2019–2024). The external patch is governed by `LICENSE.picodrive`; it is separate from, and not linked into, the cartridge engine.

Revision 12 extracts the gold UI corner/rail/plaque sprites from ITD_RESS.PAK resource 4; the frame assembly follows FITD’s `aitdBox.cpp`. They are precomposed into indexed panel images by the host importer.

Original Alone in the Dark graphics, models, animations and other resources were imported from the installation supplied by the user. Their ownership is unchanged; the engine source license does not cover these resources.

## DOSBox timing reference

`tools/dosbox-reference.patch` instruments external DOSBox 0.74-3 source (copyright 2002–2014 The DOSBox Team, GPL-2.0-or-later). It logs PIT programming, samples DOS memory and injects timed keyboard events for the original-game timing investigation. The external emulator is not bundled or linked into the cartridge. Its GPL text is preserved as `LICENSE.dosbox`. The original executable and PAKs are not modified by this patch.

## Original AdLib music conversion

`tools/audio/fitd_music_capture.cpp` adapts the same pinned FITD `FitdLib/music.cpp` driver. The host adapter replaces OPL output calls with a register-event capture and removes the desktop `playMusic` wrapper. It remains GPL under the root LICENSE. The complete original ADLM sequences are evaluated offline; YM2612/PSG adaptation and PWM/IMA playback are local additions. No OPL emulator is linked into the cartridge. Original LISTMUS/LISTSAMP resources remain owned by their original rights holders and are excluded from the source ZIP.
