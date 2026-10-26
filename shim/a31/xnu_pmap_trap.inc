    .text
    .balign 4
    .globl EXT(a31_pmap_control_trap)
LEXT(a31_pmap_control_trap)
    brk #0xa32
    b EXT(a31_pmap_control_trap)
