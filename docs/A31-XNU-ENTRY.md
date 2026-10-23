# A31 first XNU entry checkpoint

V7 proved native copying of the actual kernel, BSS, ADT and boot arguments.
The next kernel build deliberately stops at the existing first
`sweet_early_mark(1, ...)` in `arm_init`, before rebasing, CPU/VM startup,
drivers or userland. It is an XNU entry test, not a complete phone OS.

Patch 0083 enables the A31 implementations of the existing early hooks.
It appends `[A31-XNU] ENTRY MMU-OFF v1` without a stack at physical entry.
The loader must already have validated and initialized the pstore ring.
The C checkpoint appends CurrentEL, SCTLR_EL1 and CNTFRQ, requires EL1,
MMU enabled and the measured 13 MHz clock, then requests Samsung recovery
using the checked SRAM header and PSCI SYSTEM_RESET. Invalid SRAM headers
never receive writes; a failed reset is logged and the CPU waits.

The bootstrap translation code preserves the existing RAM L1/L2 tables.
It adds two L3 tables: 17 Normal-NC/NX 16 KiB pages covering
`0x4d05c000..0x4d0a0000` and one Device-nGnRnE/NX page at `0x10c000`.
Actual accesses remain within the measured pstore console
`0x4d05f000 + 0x40000` and SRAM descriptor `0x10dc00 + 0x800`.
It does not map entire 32 MiB MMIO/reserved blocks. The fixed A31 RAM
policy puts both low mappings in the existing TTBR0 L1 slot, while their
L2 slots are empty. A conflict traps before MMU enable.

The ring and recovery helper header is tested directly with invalid
headers, wraparound, boundary offsets and unchanged-byte checks. A Python
check requires its XNU patch copy to match the tested header exactly.
The new C and assembly compile locally using the real A31 generated
headers. macOS CI builds and links XNU and checks the linked checkpoint
markers, recording kernel SHA-256 and source revision.

The checkpoint's automatic return is only reachable after the first C
marker. Earlier exceptions can still halt in the original low vectors;
manual recovery remains a fallback, with the known risk of losing logs.
The existing panic hook captures a panic and requests recovery if reached
while these bootstrap mappings remain valid. This build never proceeds
to final TTBR1 setup or removal of TTBR0; persistent final mappings and a
longer kernel run are a subsequent stage. No storage driver runs here.

Compilation, host tests, and copied payloads do not demonstrate entry.
The phone result must contain the actual XNU entry marker, matching
loader build session, C checkpoint PASS and recovery request. A loader
handoff message or a return to TWRP alone is insufficient evidence.
