/* Fatal boot-CPU relay from final KVA back to the preserved bootstrap map.
 * Never disable translation while executing a high virtual PC. No stack/data.
 * Fixed base policy is checked in arm_init before this VBAR is installed. */
    .text
    .balign 2048
    .globl EXT(a31_final_vectors)
LEXT(a31_final_vectors)
.macro a31_final_vector index
    .balign 128
    mov x23, #\index
    b EXT(a31_final_fault)
.endmacro
    a31_final_vector 0
    a31_final_vector 1
    a31_final_vector 2
    a31_final_vector 3
    a31_final_vector 4
    a31_final_vector 5
    a31_final_vector 6
    a31_final_vector 7
    a31_final_vector 8
    a31_final_vector 9
    a31_final_vector 10
    a31_final_vector 11
    a31_final_vector 12
    a31_final_vector 13
    a31_final_vector 14
    a31_final_vector 15
    .balign 2048
LEXT(a31_final_fault)
    msr daifset, #15
    MOV64 x9, 0xfffffe0006000000
    MOV64 x10, 0x100000000
    adrp x11, EXT(bootstrap_pagetables)@page
    add x11, x11, EXT(bootstrap_pagetables)@pageoff
    sub x11, x11, x9
    add x11, x11, x10
    dsb sy
    msr ttbr0_el1, x11
    isb
    tlbi vmalle1is
    dsb ish
    isb
    adrp x12, EXT(a31_boot_fault)@page
    add x12, x12, EXT(a31_boot_fault)@pageoff
    sub x12, x12, x9
    add x12, x12, x10
    adrp x13, EXT(a31_boot_vectors)@page
    add x13, x13, EXT(a31_boot_vectors)@pageoff
    sub x13, x13, x9
    add x13, x13, x10
    msr vbar_el1, x13
    isb
    br x12

    .balign 4
    .globl EXT(a31_vm_control_trap)
LEXT(a31_vm_control_trap)
    brk #0xa31
    b EXT(a31_vm_control_trap)
