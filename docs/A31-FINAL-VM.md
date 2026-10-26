# A31 final diagnostic mappings

Patch 0091 prepares the transition from bootstrap to final kernel tables.
It deliberately stops after TTBR0 invalidation, before pmap bootstrap,
drivers, scheduling or userland. Compilation is not native validation.

The unused diagnostic L2 slot at `0xfffffe0002000000` receives one fresh
16 KiB L3. It maps 17 Normal-NC/NX pages at physical `0x4d05c000` and
one Device/NX page at `0x10c000`. Every other L3 entry remains invalid.
Console and recovery aliases are `0xfffffe0002003000` and
`0xfffffe0002045c00`. An occupied slot or unexpected page attributes stop
the transition. Checked AT/PAR translations precede changing the C pointers.

Fatal high virtual vectors restore the preserved bootstrap TTBR0, flush
the TLB, and branch to the existing physical fatal handler. That handler
can then disable translation and log/reset without dereferencing a stack.
The relay never disables translation while its PC is a high virtual address.
Its fixed RAM policy is checked before installation.

The normal checkpoint requires all previous native-stage markers, final
alias validation, and AT faults for both old low diagnostic addresses after
TTBR0 invalidation. A separate QEMU control deliberately executes BRK at the
linked `a31_vm_control_trap` symbol after this boundary; the physical logger
must recover the exact ESR/ELR with MMU enabled on exception entry. Both
actual-kernel controls must pass before the normal BOOT is tested on A31.
QEMU has no Samsung recovery SRAM, so it cannot establish firmware reset.

The bounded table builder and assembly are mirrored into XNU and checked
against their tested sources. No phone results for this transition are
claimed until a matching native pstore checkpoint is captured.
