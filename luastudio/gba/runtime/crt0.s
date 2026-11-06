@ LuaStudio GBA crt0 - cabecalho da ROM, pilhas, copia de .iwram/.ewram, zera .bss, divisao via BIOS.
@ O cabecalho (logo/titulo/checksum) e preenchido depois por gbafix.py.
    .section .text.start, "ax"
    .arm
    .global _start
_start:
    b       rom_start
    .fill   156, 1, 0          @ logo Nintendo (gbafix)
    .fill   12, 1, 0           @ titulo
    .fill   4, 1, 0            @ codigo do jogo
    .fill   2, 1, 0            @ maker
    .byte   0x96               @ fixo
    .byte   0, 0               @ unit code, device type
    .fill   7, 1, 0
    .byte   0                  @ versao
    .byte   0                  @ checksum (gbafix)
    .fill   2, 1, 0

rom_start:
    mov     r0, #0x12          @ modo IRQ
    msr     cpsr_c, r0
    ldr     sp, =__sp_irq
    mov     r0, #0x1F          @ modo System
    msr     cpsr_c, r0
    ldr     sp, =__sp_usr

    ldr     r0, =__iwram_lma   @ copia .iwram (codigo quente + .data) ROM -> IWRAM
    ldr     r1, =__iwram_start
    ldr     r2, =__iwram_end
1:  cmp     r1, r2
    ldrcc   r3, [r0], #4
    strcc   r3, [r1], #4
    bcc     1b

    ldr     r0, =__ewram_lma   @ copia .ewram ROM -> EWRAM
    ldr     r1, =__ewram_start
    ldr     r2, =__ewram_end
2:  cmp     r1, r2
    ldrcc   r3, [r0], #4
    strcc   r3, [r1], #4
    bcc     2b

    ldr     r1, =__bss_start   @ zera .bss
    ldr     r2, =__bss_end
    mov     r3, #0
3:  cmp     r1, r2
    strcc   r3, [r1], #4
    bcc     3b

    ldr     r0, =main
    mov     lr, pc
    bx      r0
4:  b       4b                 @ main nao deve retornar

@ ---- divisao: libgcc armv4t nem sempre existe em arm-none-eabi; usamos o BIOS (SWI 6) ----
    .align 2
    .global __aeabi_idiv
    .global __aeabi_idivmod
    .type __aeabi_idiv, %function
__aeabi_idiv:
__aeabi_idivmod:
    cmp     r1, #0
    moveq   r0, #0
    moveq   r1, #0
    bxeq    lr
    swi     0x060000           @ r0=quociente, r1=resto (assinado)
    bx      lr

    .global __aeabi_uidiv
    .global __aeabi_uidivmod
    .type __aeabi_uidiv, %function
__aeabi_uidiv:
__aeabi_uidivmod:
    cmp     r1, #0
    moveq   r0, #0
    moveq   r1, #0
    bxeq    lr
    orrs    r2, r0, r1         @ algum operando com bit 31? -> caminho lento
    bmi     9f
    swi     0x060000
    bx      lr
9:  cmp     r0, r1             @ divisao restauradora de 32 bits
    movcc   r1, r0
    movcc   r0, #0
    bxcc    lr
    tst     r1, #0x80000000
    movne   r1, r1             @ divisor >= 2^31 => quociente 1
    subne   r1, r0, r1
    movne   r0, #1
    bxne    lr
    mov     r2, #0
    mov     r3, #0
    mov     ip, #32
5:  adds    r0, r0, r0
    adc     r3, r3, r3
    cmp     r3, r1
    subcs   r3, r3, r1
    adc     r2, r2, r2
    subs    ip, ip, #1
    bne     5b
    mov     r0, r2
    mov     r1, r3
    bx      lr
    .pool
