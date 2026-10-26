    .text
    .balign 4
    .globl EXT(a31_armvm_control_trap)
LEXT(a31_armvm_control_trap)
    brk #0xa33
    b EXT(a31_armvm_control_trap)
