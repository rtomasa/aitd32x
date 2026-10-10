# Original startup and banked graphics

This records the initial startup build. The subsequent casing and performance
fixes, current ROM/RAM figures and differential evidence are in
[startup performance validation](startup-performance.md).

Implemented the Infogrames logo/model animation and thunder flash, title,
automatically paged credits, New Game/Resume/Replay Intro menu, original
character portraits and biographies, and the complete scripted arrival.
Replay Intro replaces the DOS exit command. Controller navigation and skip
controls are documented in README.md. The introduction visits floors 7, 3, 2
and 1 and completes its final LIFE 539 track before initializing gameplay.
It does not extend the playable floor boundary.

Presentation uses a VBlank-derived 60 Hz clock with 1/1500-second units;
arrival simulation retains 25 Hz updates and the approved animation clock.
The original frog picture suspends world updates for 20 presentation ticks.
Both skipping and completion rebuild the original floor-0 gameplay world.
The FPS border is hidden during startup. The original CD narration remains
unimplemented; existing converted effects and AdLib music are retained.

## Build and memory

The RELEASE build was made with `make assets`, `make -j2 all host`, Marsdev
GCC 13.1.0 and the supplied CD installation. ROM:

- Size: **4,653,056 bytes / 4.4375 MiB**.
- SHA-256: `e67096bcdeed9f1aabad58f20ec1307901ab9b620b573ae5c2cddd2f9c98731e`.
- Asset bank: **2,033 IDs**, logical size 4,502,125 bytes, SHA-256
  `4c1446caa9b6cae6bfe4d77b7af579a5866208f39d74f207ca2bae19c0881cf3`.
- Fixed assets: 3,892,124 bytes at physical `0x20000`.
- Extra images: 438,893 bytes at physical `0x400000`; all 16 fit mapper page 8.
- BIOS module: 83,076 bytes, ending at physical 4,106,272; **88,032 bytes**
  remain below the direct-window limit.
- BSS: 160,176 bytes. Static SDRAM ends at **`0x0603B638`**, leaving
  **2,504 bytes** before the existing 12 KiB master / 4 KiB slave stacks.

Startup adds 32 bytes of state and reuses the existing background and render
scratch. Expanded world lookup tables move into fixed ROM. Gameplay camera
images, existing panels and reading sprites retain their raw formats. Title,
reading backgrounds and startup images use lossless LZ4; new startup panels
use header-plus-LZ4 pixels. No audio format or payload changed.

The SH2 direct window is 4 MiB. A 32 MiB cartridge needs a mapper; this build
uses SSF2 512 KiB pages with a 32 MiB physical-ROM limit. The 68000 briefly
sets RV to write `A130F3`, the SH2 decodes via uncached slot 1, and bank 1 is
restored before normal world/render access. Executable ROM code, all 101
sound effects and eight music streams avoid the aperture. Details and primary
source references are in [ARCHITECTURE.md](../ARCHITECTURE.md).

## Focused verification

Checks passed against the build above:

- `tools/check_bank_layout.py`: main/extra bytes match the linked ROM;
  directory bounds, page isolation, protected code/audio, BIOS module,
  checksum and stack reservation pass.
- `tools/check_startup.py`: natural boot, animated logo, seven timed credit
  pages, replay, both portraits/biographies, full arrival, picture pause in
  both framebuffer histories, skipping and clean gameplay initialization.
  Edward/Emily complete in **3,252 / 3,219 world ticks**, without LIFE faults
  or death state. All 17 required floor/camera pairs are visited.
- Legacy saves produced by the preserved pre-startup host library load
  through Resume. Both 21,812-byte serialized payloads remain byte-identical
  after load/save. Schema, all 1,969 old asset IDs and fingerprint
  **`0x0eebc721`** are unchanged. Private host SRAM arrays were used.
- Native PicoDrive libretro 2.04 checks on **NTSC and PAL**: original
  logo/title/menu pixels, animated model, seven/eight-page biographies,
  complete Edward/Emily arrivals respectively, frog pixels and paused world,
  skip, and save/core-restart/resume with pose/character/variable intact.
  Mapper slot 1 returns to bank 1, and audio remains active during image loads.
  Independent video inspection observed the frog for 21 NTSC frames
  (0.35 seconds) and 19 PAL frames (0.38 seconds), accounting for VBlank
  rounding and presentation. These visible durations are recorded separately
  from the world/phase pause measurements.
- Decoder fixtures: raw/RLE/LZ4, extended lengths, overlapping matches,
  malformed offsets, odd widths/strides and zero-safe framebuffer writes.
  Render regression and the 25 Hz scheduler / 60 Hz animation checks pass.
- Import comparison: 1,968 old decoded payloads match the baseline exactly;
  the static raster asset changes only its offset-dependent pose keys.
  Independent liblz4 checks pass for all 22 LZ4 assets.

Ignored evidence is retained in `build/bank-layout.json`,
`build/startup-host-final.json`, `build/startup-native-NTSC.json`,
`build/startup-native-PAL.json`, and
`build/startup-analysis/import-validation-final.json`. PNG captures are under
`build/startup-host-captures/` and `build/startup-NTSC-*.png` /
`build/startup-PAL-*.png`. No emulator battery-save files were written.
Independent visible picture measurements are in `build/startup-picture-video.json`.

These are host/emulator results. Physical cartridge mapper compatibility,
RV arbitration, audio and SRAM on actual 32X hardware remain unvalidated.
PicoDrive does not emulate the RV arbitration timing. Hardware or a flash cart
must support the SSF2 mapper; ROM size alone does not provide that capability.
