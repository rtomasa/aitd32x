# Large SSF-banked 32X cartridge candidate

## Change and scope

The reported Mega EverDrive Pro launch was classified as `10M+32x (3)` and
blocked with a request to disconnect the 32X. Our previous `SEGA 32X` header
did not request the SSF mapper used by the runtime. Krikzz's mapper definitions
identify 3 as linear 10M and 5 as SSF. This build changes the system header to
`SEGA SSF`, retaining the `.32x` extension, original MARS bootstrap and module.
It is a cartridge test candidate; no 32X CD conversion is involved.

The RAM-resident 68000 initializer runs before releasing the SH2s. It restores
identity pages 1–7, probes protected bank-0 remapping using 256 immutable bytes,
restores bank 0 and selects 32X mode with ROM writes disabled (`A130F0=C000`).
An ordinary SSF2 mapper ignores bank-0 remapping, selecting conventional SRAM
instead. A layout check ensures the probe's two physical ROM samples differ.

Mega EverDrive Pro's extended mapper routes physical page 31 to word-wide
SRAM. Each save read/write sets RV, selects MD mode and the appropriate write
protection, maps page 31 in bank 4, accesses the word, restores fixed bank 4
and 32X mode, and restores RV before acknowledgement. Bank 1's retained image
page is untouched. Both 64 KiB journals remain within 128 KiB of SRAM, and
music pumping remains suspended during save transactions. The ordinary SRAM
path remains for stock PicoDrive. Previous save compatibility was not a
requirement for this change; no serialization migration was needed.

ROM pages 30/31 are reserved, limiting cartridge payloads to 15 MiB. The
linker, ROM finalizer, layout check and runtime page checks enforce this
consistently. Actual cartridge capacity and supported mapper registers still
depend on the device. Older EverDrive SRAM layouts are not validated.

Primary references:

- [Krikzz extended SSF specification](https://krikzz.com/pub/support/mega-everdrive/x3x5x7/dev/extended_ssf-v2.txt): header, 32X control bit, protected writes and reserved pages.
- [Krikzz Pro SSF FPGA implementation](https://github.com/krikzz/mega-ed-pub/blob/master/fpga/mapper/map_ssf/map_ssf.sv): five-bit page selection, page-31 SRAM routing and write-enable control.
- [Krikzz mapper IDs](https://github.com/krikzz/mega-ed-pub/blob/master/fpga/mapper/lib_base/defs.sv): SSF is mapper 5; 10M is mapper 3.
- [Doom 32X Resurrection's cartridge detection](https://github.com/viciious/d32xr/blob/master/src-md/everdrive.c): bank-0 comparison from 68000 RAM while RV is set.

## Build and emulator evidence

Commands used:

```sh
make -j2
python3 tools/check_bank_layout.py
python3 tools/check_startup_native.py .local/tools/picodrive_libretro.so --short-arrival
python3 tools/check_startup_native.py .local/tools/picodrive_libretro.so --region PAL --short-arrival
python3 tools/check_ssf_sram_native.py .local/tools/picodrive_libretro.so
make host
python3 tools/check_full_game_native.py .local/tools/picodrive_libretro.so
```

The native startup checks pass in NTSC and PAL: original logo/title/menu pixels,
both characters' biographies, shortened arrivals, banked frame samples with
audio, and save/load across an emulator restart. The full-game native check
passes one sampled scene per floor, background checks in both framebuffers,
live script updates, menu controls and the short gameplay trace. These are
not a complete playthrough. Its NTSC gameplay trace completes 243 draws in
10 seconds (24.3 draws/s); this is not a hardware performance measurement.

Stock PicoDrive does not emulate extended EverDrive SRAM. The focused
`check_ssf_sram_native.py` selects the compiled hardware save branch and adds
a temporary page-31 bus model to PicoDrive's 68000 memory tables. Actual
68000 code performs 106,270 word reads and 21,258 word writes; the model checks
RV, control-word protection, SRAM selection, fixed-ROM restoration, 32X mode
and avoidance of the conventional SRAM switch. Both journals and two core
restarts pass. This model does **not** test hardware mapper autodetection,
physical arbitration, FPGA timing or the OS's SD save export. All SRAM stays
in private memory; no emulator battery files are opened or overwritten.

Build figures:

- ROM: 14,155,776 bytes (13.5 MiB), unchanged size; checksum `4A9A`.
- SHA-256: `f885b8d4bcbdfac0344e4025554d2600e79f1478682638e34920f50e179fe40a`.
- SH2 module: 84,420 bytes; BSS: 160,640 bytes; static end `0603BD48`.
- SH2 stack margin: 696 bytes, unchanged; no new SH2 buffers.
- 68000 initialized RAM code/data: 3,616 bytes, up 332 bytes; BSS remains 84 bytes.
- Existing assembler `.data` attributes and linker RWX warnings remain; no new C warning.

Reports and captures stay under ignored `build/`. The previous ROM/ELFs are
preserved in `build/ssf-mapper-reference/`; existing release bundles and the
ignored baseline are unchanged.

## Physical test still required

The test bundle is `build/hardware-tests/ssf32x/`, with a separately named
`AITD32X-SSF.32x`, SHA-256 file and test instructions. Keep the `.32x` extension
and use a fresh save for the test. Record firmware version and full ROM Info;
the intended mapper is SSF (5), rather than 10M (3). Confirm boot, menus,
character selection, arrival and room transitions, then save and verify loading
after a power cycle and return to the cartridge menu. Hardware boot, mapper
selection and SD save persistence remain unvalidated until that report arrives.
