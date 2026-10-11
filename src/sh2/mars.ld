OUTPUT_ARCH(sh)
MEMORY {
    rom (rx) : ORIGIN = 0x02000000, LENGTH = 0x02000000
    ram (rwx) : ORIGIN = 0x06000000, LENGTH = 0x0003C000
}
PROVIDE(__stack = 0x0603F000);
SECTIONS {
    /* Header/bootstrap and immutable asset bank stay in cartridge ROM. */
    .text 0x02000000 : AT(0) {
        build/start.o(.text)
        . = ALIGN(16);
        *(.romcode .romcode.*)
        build/src/render/book.o(.text .text.* .rodata .rodata.*)
        build/src/engine/save.o(.text .text.* .rodata .rodata.*)
        build/src/platform/save_bridge.o(.text .text.* .rodata .rodata.*)
        build/src/engine/startup.o(.rodata .rodata.*)
        build/src/engine/death.o(.rodata .rodata.*)
        build/src/engine/lighting.o(.rodata .rodata.*)
        build/src/engine/inventory.o(.rodata .rodata.*)
        /* Expanded intro floor/asset lookup tables need no SDRAM copy. */
        build/src/engine/world.o(.rodata .rodata.*)
        . = ALIGN(4);
    } > rom
    /* Fixed asset origin also defines the importer's mapper page offsets. */
    .assets 0x02020000 : AT(0x00020000) { build/assets.o(.assets) } > rom
    _stext = 0x00020000 + SIZEOF(.assets);
    /* BIOS loads this whole module. Vectors must remain first and fixed. */
    .data 0x06000000 : AT(_stext) {
        build/start.o(.data)
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.* .shdata)
        *(.got.plt .got)
        . = ALIGN(16);
        __INIT_SECTION__ = .;
        SHORT(0x000B) SHORT(0x0009)
        . = ALIGN(16);
        __FINI_SECTION__ = .;
        SHORT(0x000B) SHORT(0x0009)
        . = ALIGN(4);
        _edata = .;
    } > ram
    _sdata = SIZEOF(.data);
    .bss : {
        __bss_start = .;
        *(.shbss .bss .bss.* COMMON)
        . = ALIGN(8);
        _end = .; __end = .; end = .;
    } > ram
    /* Only cold presentation images extend beyond the direct ROM window. */
    .romextra 0x02400000 : AT(0x00400000) {
        build/assets.o(.romextra)
        _asset_bank_end = .;
    } > rom
    /DISCARD/ : { *(.eh_frame .comment .note*) }
}
ASSERT(__end <= 0x0603C000, "SDRAM overlaps master stack reserve")
ASSERT(_sdata < 0x0003C000, "SH-2 startup module exceeds SDRAM")
ASSERT(SIZEOF(.text) <= 0x00020000, "ROM code overlaps fixed asset origin")
ASSERT(_stext + _sdata <= 0x00400000, "BIOS module exceeds fixed cartridge window")
ASSERT((_stext & 3) == 0, "BIOS module source must be longword aligned")
ASSERT(SIZEOF(.romextra) <= 0x01C00000, "Cartridge exceeds 32 MiB mapper limit")
