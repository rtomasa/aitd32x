OUTPUT_ARCH(sh)
MEMORY {
    rom (rx) : ORIGIN = 0x02000000, LENGTH = 0x00400000
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
        build/assets.o(.rodata)
        . = ALIGN(4);
    } > rom
    _stext = SIZEOF(.text);
    /* BIOS loads this whole module. Vectors must remain first and fixed. */
    .data 0x06000000 : AT(SIZEOF(.text)) {
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
    /DISCARD/ : { *(.eh_frame .comment .note*) }
}
ASSERT(__end <= 0x0603C000, "SDRAM overlaps master stack reserve")
ASSERT(_sdata < 0x0003C000, "SH-2 startup module exceeds SDRAM")
