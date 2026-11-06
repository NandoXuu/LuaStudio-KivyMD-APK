/* LuaStudio GBA linker script */
OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(_start)

MEMORY {
    rom   (rx)  : ORIGIN = 0x08000000, LENGTH = 32M
    iwram (rwx) : ORIGIN = 0x03000000, LENGTH = 32K - 0x100
    ewram (rwx) : ORIGIN = 0x02000000, LENGTH = 256K
}
__sp_usr = 0x03007F00;
__sp_irq = 0x03007FA0;

SECTIONS {
    .text : {
        KEEP(*(.text.start))
        *(.text .text.*)
        *(.glue_7t) *(.glue_7) *(.vfp11_veneer) *(.v4_bx)
        *(.rodata .rodata.* )
        . = ALIGN(4);
    } > rom

    .iwram : {
        __iwram_start = .;
        *(.iwram .iwram.*)
        *(.data .data.*)
        . = ALIGN(4);
        __iwram_end = .;
    } > iwram AT > rom
    __iwram_lma = LOADADDR(.iwram);

    .ewram : {
        __ewram_start = .;
        *(.ewram .ewram.*)
        . = ALIGN(4);
        __ewram_end = .;
    } > ewram AT > rom
    __ewram_lma = LOADADDR(.ewram);

    .sbss (NOLOAD) : { *(.sbss .sbss.*) . = ALIGN(4); } > ewram

    .bss (NOLOAD) : {
        __bss_start = .;
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > iwram

    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.exidx*) *(.ARM.extab*) }
}
