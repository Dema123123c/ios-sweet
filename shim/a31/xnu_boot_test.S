#define EXT(x) x
#define LEXT(x) x:
#define A31_BOOT_LOG_PA 0x49000000
#define A31_BOOT_SRAM_PA 0x49100000
#define A31_BOOT_TEST 1
.macro MOV64 reg, value
    movz \reg, #((\value) & 0xffff)
    movk \reg, #(((\value) >> 16) & 0xffff), lsl #16
    movk \reg, #(((\value) >> 32) & 0xffff), lsl #32
    movk \reg, #(((\value) >> 48) & 0xffff), lsl #48
.endm
.section .text.head,"ax"
.global _head
_head:
    b start
    .long 0
    .quad 0x80000, _end - _head, 12, 0, 0, 0
    .ascii "ARM\x64"
    .long 0
.text
start:
    msr daifset, #15
    mrs x0, CurrentEL
    cmp x0, #8
    b.ne el1
    mov x0, #0x80000000
    msr hcr_el2, x0
    msr cptr_el2, xzr
    MOV64 x0, 0x30d00800
    msr sctlr_el1, x0
    adr x0, el1
    msr elr_el2, x0
    mov x0, #0x3c5
    msr spsr_el2, x0
    eret
el1:
    msr spsel, #1
    ldr x0, =_stack_top
    mov sp, x0
    ldr x0, =_bss_start
    ldr x1, =_bss_end
1:  cmp x0, x1
    b.hs 2f
    str xzr, [x0], #8
    b 1b
2:  adr x0, a31_boot_vectors
    msr vbar_el1, x0
    isb
    bl a31_boot_test_prepare
#if BOOT_MMU
    msr ttbr0_el1, x0
    MOV64 x0, 0x20080b018
    msr tcr_el1, x0
    mov x0, #0x44
    msr mair_el1, x0
    dsb sy
    isb
    tlbi vmalle1
    dsb sy
    isb
    mrs x0, sctlr_el1
    mov x1, #0x1005
    orr x0, x0, x1
    msr sctlr_el1, x0
    isb
#endif
    mov x0, #0
    mov sp, x0
#if !BOOT_SOURCE_SP
    msr sp_el0, x0
    msr spsel, #0
#endif
.global a31_boot_test_fault
a31_boot_test_fault:
    .inst 0
    b .
.global a31_boot_test_finish
a31_boot_test_finish:
    ldr x1, =_stack_top
    mov sp, x1
    bl a31_boot_test_verify
    b .
#include "xnu_boot_asm.inc"
