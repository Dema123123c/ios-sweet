    .section .text.head, "ax"
    .global _head
_head:
    b _start
    .long 0
    .quad 0x80000
    .quad _end
    .quad 12
    .quad 0, 0, 0
    .ascii "ARM\x64"
    .long 0

    .text
_start:
    msr daifset, #15
    mov x19, x0
    mrs x20, CurrentEL
    cmp x20, #8
    b.eq from_el2
    cmp x20, #4
    b.ne halt
    mrs x1, sctlr_el1
    tbnz x1, #0, halt
    tbnz x1, #2, halt
    b prepare_entry
from_el2:
    mrs x1, sctlr_el2
    tbnz x1, #0, halt
    tbnz x1, #2, halt
prepare_entry:
    msr spsel, #1
    adr x1, _stack_top
    mov sp, x1
    adr x1, _bss_start
    adr x2, _bss_end
1:  cmp x1, x2
    b.hs 2f
    str xzr, [x1], #8
    b 1b
2:  adr x1, vectors
    cmp x20, #8
    b.eq 3f
    msr vbar_el1, x1
    b 4f
3:  msr vbar_el2, x1
4:  isb
    mov x0, x19
    lsr x1, x20, #2
    bl diag_early
#if DIAG_ENTRY_FAULT
    .inst 0
#endif
    cmp x20, #8
    b.ne at_el1
    mov x1, #0x80000000
    msr hcr_el2, x1
    msr cptr_el2, xzr
    mov x1, #3
    msr cnthctl_el2, x1
    msr cntvoff_el2, xzr
    mrs x1, icc_sre_el2
    orr x1, x1, #1
    orr x1, x1, #8
    msr icc_sre_el2, x1
    mov x1, #0x0800
    movk x1, #0x30d0, lsl #16
    msr sctlr_el1, x1
    adr x1, at_el1
    msr elr_el2, x1
    mov x1, #0x3c5
    msr spsr_el2, x1
    isb
    eret
at_el1:
    msr spsel, #1
    adr x1, _stack_top
    mov sp, x1
    adr x1, vectors
    msr vbar_el1, x1
    isb
    mov x0, x19
    lsr x1, x20, #2
    bl diag_main
halt:
    wfe
    b halt

#if DIAG_XNU_ENTRY
    .balign 4
    .global a31_kernel_enter
    .type a31_kernel_enter, %function
a31_kernel_enter:
    msr daifset, #15
    msr cntv_ctl_el0, xzr
    msr cntp_ctl_el0, xzr
    mov x16, x0
    mov x0, x1
    mov x1, xzr
    mov x2, xzr
    mov x3, xzr
    /* All destination writes used MMU/caches off; no dirty D-cache lines.
     * Synchronize the copied instructions before the physical branch.
     */
    dsb sy
    ic iallu
    dsb sy
    isb
    br x16
#endif

.macro vector slot
    .balign 0x80
    stp x29, x30, [sp, #-16]!
    mov x29, #\slot
    b exception_common
.endm
    .balign 0x800
vectors:
    vector 0
    vector 1
    vector 2
    vector 3
    vector 4
    vector 5
    vector 6
    vector 7
    vector 8
    vector 9
    vector 10
    vector 11
    vector 12
    vector 13
    vector 14
    vector 15
exception_common:
    sub sp, sp, #240
    stp x0, x1, [sp, #0]
    stp x2, x3, [sp, #16]
    stp x4, x5, [sp, #32]
    stp x6, x7, [sp, #48]
    stp x8, x9, [sp, #64]
    stp x10, x11, [sp, #80]
    stp x12, x13, [sp, #96]
    stp x14, x15, [sp, #112]
    stp x16, x17, [sp, #128]
    stp x18, x19, [sp, #144]
    stp x20, x21, [sp, #160]
    stp x22, x23, [sp, #176]
    stp x24, x25, [sp, #192]
    stp x26, x27, [sp, #208]
    str x28, [sp, #224]
    mov x0, x29
    bl diag_exception
    ldp x0, x1, [sp, #0]
    ldp x2, x3, [sp, #16]
    ldp x4, x5, [sp, #32]
    ldp x6, x7, [sp, #48]
    ldp x8, x9, [sp, #64]
    ldp x10, x11, [sp, #80]
    ldp x12, x13, [sp, #96]
    ldp x14, x15, [sp, #112]
    ldp x16, x17, [sp, #128]
    ldp x18, x19, [sp, #144]
    ldp x20, x21, [sp, #160]
    ldp x22, x23, [sp, #176]
    ldp x24, x25, [sp, #192]
    ldp x26, x27, [sp, #208]
    ldr x28, [sp, #224]
    add sp, sp, #240
    ldp x29, x30, [sp], #16
    eret
