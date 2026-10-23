/* QEMU-only receiver; validates the actual branch ABI, not XNU. */
.text
.global _entry
_entry:
    mov x2, #0x50010000
    cmp x0, x2
    b.ne failed
    ldr w1, [x0]
    mov w2, #0x20002
    cmp w1, w2
    b.ne failed
    ldr x1, [x0, #16]
    mov x2, #0x50000000
    cmp x1, x2
    b.ne failed
    mrs x1, CurrentEL
    cmp x1, #4
    b.ne failed
    mrs x1, SCTLR_EL1
    mov x2, #0x1005
    tst x1, x2
    b.ne failed
    mrs x1, DAIF
    and x1, x1, #0x3c0
    cmp x1, #0x3c0
    b.ne failed
    mrs x1, CNTV_CTL_EL0
    tbnz x1, #0, failed
    mrs x1, CNTP_CTL_EL0
    tbnz x1, #0, failed
    adr x1, _entry
    mov x2, #0x50000000
    add x2, x2, #0x4000
    cmp x1, x2
    b.ne failed
    adr x1, success
    mov x0, #4
    hlt #0xf000
    adr x1, exit_ok
    b exit
failed:
    adr x1, failure
    mov x0, #4
    hlt #0xf000
    adr x1, exit_bad
exit:
    mov x0, #0x20
    hlt #0xf000
    b .
success: .asciz "A31 HANDOFF FIXTURE PASS\n"
failure: .asciz "A31 HANDOFF FIXTURE FAIL\n"
.balign 8
exit_ok: .quad 0x20026, 0
exit_bad: .quad 0x20026, 1
