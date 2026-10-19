# Cartridge SRAM fix — 2026-10-20

Built from `8392965` plus the working SRAM changes. ROM SHA-256:
`239f0d4a57e8ac1a3cc3eaf304e474fc64d77360cd26121b254a63a36f84ceb8`.

## Fix and limits

The previous save transport assumed 128 KiB of word-wide SRAM. The inspected
[MiSTer cartridge decoder](https://github.com/MiSTer-devel/S32X_MiSTer/blob/3d4209c659512a8c0f43913b1fa54d3d550b2794/rtl/CART/cart.sv)
has a 15-bit SRAM address and only the low data byte. The previous extended
path also accessed the beginning of page 31, whereas
[Krikzz's extended SSF specification](https://krikzz.com/pub/support/mega-everdrive/x3x5x7/dev/extended_ssf-v2.txt)
places battery SRAM in its upper 256 KiB. The published
[Pro implementation](https://github.com/krikzz/mega-ed-pub/blob/23dbd5ef527999eb85590ece7ad0ba6e202c8a4c/fpga/mapper/map_ssf/map_ssf.sv)
maps the entire page; source inspection alone does not prove which problem
caused the reported firmware's failure. See the preceding
[issue investigation](hardware-issue-1.md).

Both save paths now use odd-byte accesses and 32 KiB of logical storage.
The header declares `RA F820`, start `0x200001`, end `0x20FFFF`. Conventional
access uses that window. Extended SSF temporarily selects page 31 in bank 4
and accesses `0x240001 + 2 * logical offset`. Two bytes still share each COMM
exchange, but the 68000 performs two byte bus cycles. Each exchange restores
ROM mapping and write protection before clearing RV and acknowledging. This
also prevents conventional SRAM from hiding fixed assets while SH2 code
serializes or reconstructs actor poses. No destructive mapper probes were added.

The shared serializer retains all previous gameplay fields, with streaming
LZSS compression and two 16 KiB records. It measures the encoded payload
before writing SRAM. Overflow leaves both existing records intact. Magic
commits last; FNV-1a, bounds and compressed-stream validity are checked before
applying a load. Corrupt newest records retain the previous checksum-valid
recovery path. This applies across the game, independently of floor/character.

Only format `0x53313602` is supported. **Backward compatibility and conversion
are intentionally omitted at the user's request.** Earlier battery files and
emulator savestates are not accepted. No user's battery file was opened,
modified or replaced during implementation or validation.

## Focused results

| Check | Result |
| --- | --- |
| Host round trip, both characters | Pass; corruption recovery, title load and malformed-stream rejection |
| Moving, combat, reading, inventory | Pass; all serialized fields round-trip through an independent decoder |
| Held/dropped lantern, both characters | Pass; darkness, source and every saved field preserved |
| 50 active actors, largest 28-bone skeleton | Pass; 5,235 compressed bytes, 16,360-byte payload capacity |
| Incompressible synthetic poses | Save refused before any existing SRAM byte changed |
| Stock PicoDrive NTSC and PAL | Pass; two journals, fresh-core reload and resumed gameplay |
| Documented extended upper-half SRAM model, NTSC | Pass; odd lanes, RV, write protection, bank restoration and fresh-core reload |
| MiSTer 8-bit/32 KiB SRAM model, NTSC | Pass; both records and fresh-core reload |
| Linked header, banks and RAM limits | Pass |

The eight natural host fixtures use 5,096–5,178 compressed bytes. The
50-actor fixture's preceding uncompressed representation was 53,930 bytes.
These are sampled states, not a whole-playthrough capacity guarantee. Truly
incompressible states can exceed the record limit and will safely report
**Save failed**.

The native bus models run the actual compiled 68000 and SH2 save paths in
PicoDrive. They are installed after boot; the extended path is selected in
private 68000 RAM because stock PicoDrive lacks that mapper extension.
**These checks do not validate extended-mapper autodetection on a cartridge,
physical bus timing, a MiSTer bitstream, or SRAM-to-SD export.** The existing
read-only bank-0 probe is unchanged. A successful private model cannot
establish that a physical EverDrive selected the same backend.

PicoDrive exposes a 65,536-byte battery image containing unused even addresses;
the 32,768 data bytes occupy odd addresses. Packed host SRAM and the private
MiSTer model contain only the data bytes. Do not assume frontend battery-file
layouts are interchangeable.

## Memory and performance scope

ROM remains 14,155,776 bytes. SH2 static BSS remains 160,696 bytes; the linked
module remains 84,612 bytes, static SDRAM ends at `0x0603BE40`, and the margin
below the reserved stacks remains 448 bytes. No heap or global SH2 save buffer
was added. The streaming codec holds a 1 KiB ring and a 16-byte token packet
on the master stack; save-only heavy routines run from protected ROM. Compiler
stack reports put `Game_Save` at 1,176 bytes, `ReadPayload` at 1,120, and the
nested payload serializer at 896. These are per-function figures, not a full
call-chain/interrupt stack proof.

Compression and its preflight run only while saving/loading, with gameplay
paused and the existing clock resynchronization retained. There is no new
per-frame rendering or simulation work. No audio changes were included.

## Reproduction and hardware test

Commands are listed in [development instructions](../DEVELOPMENT.md). Relevant
ignored evidence is `build/sram-host.json`, `build/full-game-save.json`,
`build/bank-layout.json`, and `build/sram-{stock,extended,mister}-*.json`.
`build/sram-transport-*.log` records the current native runs. Earlier migration
and PAL extended experiments under `build/` describe intermediate revisions,
not this final ROM.

Use `build/AITD32X-sram-test.32x` with a new basename to keep older battery
files separate. Expected configuration is **SSF+32X (5)** and **SRAM 32K**
where the cartridge exposes those settings. Retained per-ROM overrides may
need updating to match the new header.

1. Start a new game, use Pause → Save Game, and wait for **Game saved**.
2. Move, then load; confirm position, inventory and room restore correctly.
3. Save again to exercise the other recovery record.
4. Follow the device's normal SRAM backup procedure, reload the ROM/core,
   and select Resume a Saved Game. Confirm persistence after a cold restart.

Physical EverDrive Pro and MiSTer confirmation remain pending. Existing
release bundles and the preserved baseline were not replaced; no commit or
GitHub publication was made.
