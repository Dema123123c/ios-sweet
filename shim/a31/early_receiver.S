.text
.global _entry
_entry:
    adr x1, message
    mov x0, #4
    hlt #0xf000
    b checkpoint
message: .asciz "A31 EARLY RECEIVER REACHED\n"
.org 0x1c78
checkpoint:
    nop
    adr x1, bad
    mov x0, #4
    hlt #0xf000
    adr x1, exit_bad
    mov x0, #0x20
    hlt #0xf000
    b .
bad: .asciz "A31 EARLY RECEIVER OVERSTEP\n"
.balign 8
exit_bad: .quad 0x20026, 1
