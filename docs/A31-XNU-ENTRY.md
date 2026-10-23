# A31 first XNU entry checkpoint

## Native checkpoint verified, 2026-10-23

V17 reached the first `sweet_early_mark(1, ...)` in `arm_init` on the real
SM-A315F and returned automatically to TWRP. The matching pstore session
`6f23efccc9675f5073fad7202d3877927bf00e77` records, in order:

```text
[A31-XNU] ENTRY MMU-OFF v1
[A31-XNU] STACKS NEXT
[A31-XNU] TABLES READY
[A31-XNU] MMU ENABLE NEXT
[A31-XNU] C STAGE 1: arm_init entered (MMU on)
XNU_CURRENT_EL=0x0000000000000001
XNU_SCTLR_EL1=0x000000003454593d
XNU_CNTFRQ=0x0000000000c65d40
[A31-XNU] ENTRY-CHECK PASS
[A31-XNU] RECOVERY REQUEST
```

No artificial BRK or watchdog reset was used. This verifies native high-VA
C execution with MMU/cache enabled and the corrected C PSCI reset path.
Only pstore contains the XNU checkpoint; last_kmsg contains loader records.
Private evidence is `research/a31-v17-smc-fix-logs/report.json` and its raw
console. Full BOOT readback matched SHA-256
`cad0ce8607f34e693adccbb5ec61bdc84633fc548480fbcecd6fcefb2b02dc18`.
Recovery and both vbmetas remained unchanged. V17 is retained in BOOT.
Kernel CI39964266332 and shim CI39964266188 succeeded at source
`f5f5a2ce3dcc9c26eb891edf2bb9afaf5539da83`.

Execution deliberately ends before rebasing, CPU/VM initialization, drivers
and userland. A working display or iOS installation is not established.

## Checkpoint design and historical controls

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

The separate loader mode requires `--entry-check-sha` with the exact
payload SHA-256; the packager checks this hash, its presence in the compiled
loader and the checkpoint markers within file-backed payload segments.
After successful copying/readback, it requires EL1 with MMU/D-cache/I-cache
off, masks DAIF, disables both generic timers, synchronizes writes,
invalidates the I-cache and branches to the physical Mach-O entry with
`x0 = boot_args PA`. The existing diagnostic vectors remain until XNU
replaces them. It does not emit diagnostic PASS before the kernel branch.

A QEMU-only machine-code receiver tests the actual branch, physical PC,
`x0`/boot-args fields, EL1, masked DAIF, caches/MMU off and timers disabled
from incoming EL1 and EL2. This proves the handoff ABI for that fixture,
not XNU execution. Its payload and QEMU image must never be flashed.

## Physical-entry BRK control after V8

V8 remained on the splash according to the user. On resume, TWRP was
available after a USB reconnect; Windows and ADB both enumerated it.
Matching V8 sessions were absent from all three readable log sources.
This does not distinguish entry failure from loss of logs during return.
Fresh full reads confirmed the same V8 BOOT, recovery and both vbmetas,
with unlocked/orange state. No V8 success is claimed.

The separate `--entry-trap` mode requires an exact payload SHA and only
changes the copied entry word in RAM to `BRK #0xa31` (`0xd4214620`).
It reads that word back and follows the same physical branch as V8.
The loader's vectors and stack remain active. Only an EL1 SP1 synchronous
exception with ESR `0xf2000a31` and ELR equal to the armed entry address
counts as PHYSICAL ENTRY BRK PASS; it then uses the verified software
recovery return. Other exceptions follow the existing failure path.
The persisted BOOT/payload are never patched by this RAM operation.
No original XNU instruction executes in this control. It tests the real
physical branch and exception-return logging, not XNU startup.
QEMU tests both incoming EL1 and EL2 and forbids execution of the normal
receiver's success/failure messages in this mode.

V9 then passed on the actual A31: both recovered log sources contained
expected source0ffbb56, ELR10148c488 and ESRf2000a31, plus copy/core PASS
and automatic recovery return. This establishes the physical branch and
BRK control at the real high-RAM entry, not execution of original XNU.

The next control moves the RAM-only BRK to entry +0x1c78, PA10148e100.
The exact V8 kernel begins with B14000719 to start_first_cpu10148e0ec,
then MSR OSLAR, DAIF mask, MOV x20/x0, MOV x21/0 and BL entry_record.
The checkpoint replaces ADRP opcodef0ffffe0 immediately AFTER that call,
before XNU replaces VBAR or SP. The original marker routine returns with
the loader's vectors/stack intact. Native building/packaging demand this
exact offset, original opcode and V8 payload SHA; runtime checks that the
word lies inside copied file-backed bytes and still has that opcode.
Unlike the zero-offset control, original early XNU assembler does execute.
It still does not reach C or enable the kernel MMU. Evidence requires the
actual XNU physical marker and exact checkpoint ELR in one loader session.
A separate synthetic QEMU receiver exercises the same nonzero offset,
with its own fixture label; it is not presented as an XNU boot.

V10 passed on hardware. The matching console-ramoops session contains
original `[A31-XNU] ENTRY MMU-OFF v1`, exact checkpoint ELR10148e100,
ESRf2000a31 and diagnostic/core/copy PASS; the user observed automatic
TWRP return. This verifies execution of original XNU early assembler and
its physical log routine, stopping before VBAR/SP changes and MMU setup.
last_kmsg contains the matching shim/trap result but omits the XNU marker;
only pstore supplies full original-assembler evidence. C entry and the
kernel's own MMU initialization are not yet verified. The next task is a
stack-independent early exception log/return path across those transitions.

## Fatal boot-vector instrumentation after V10

Patch0084 installs a dedicated physical VBAR for the boot CPU, retaining
it through the MMU transition. It logs STACKS NEXT, TABLES READY and MMU
ENABLE NEXT. This entry-only kernel still stops at first C; it never
removes TTBR0 or starts secondary CPUs. These are not general runtime
exception handlers and must not be reused after the identity map is gone.

The shared assembly include records ESR/ELR/FAR/SCTLR/source-SP/SPSR/vector slot without
using SP, calling C or dereferencing global pointers. At physical VBAR it
can clear M/C/I before logging, avoiding dependence on a broken low I/O PTE.
This fatal boot path discards kernel-private dirty state; its pstore mapping
is NC and its SRAM mapping Device. It preserves no running OS and never
resumes the failed kernel. It validates the same DBGC header/bounded Linux
structure as the verified recovery ABI, writes only the three request
words and issues PSCI SYSTEM_RESET. Bad SRAM headers receive no writes.

The include is mirrored byte-for-byte into XNU, enforced by Python tests.
A separate bare-metal QEMU harness executes that exact assembly from both
incoming EL1 and EL2, with both SP selectors and SP=0, MMU off/on, five malformed SRAM-header
variants and an invalid ring header. It checks exact saved fault fields,
cache/MMU shutdown and every SRAM word. Test-only completion replaces the
final SMC after the guarded writes; it does not test Samsung firmware.
The native include uses fixed physical addresses and the real SMC.
An exception before the physical vector is installed or with an unfetchable
identity-mapped code page still has no guaranteed recovery path.

Source6326258 passed twenty shared-assembly QEMU runs: both incoming ELs,
both SP selectors with zero stacks, MMU off/on, invalid SRAM and ring
headers. Fatal logs include original source SP selected from SPSR.SP and
SPSR itself. Full kernel run39952374717 remains queued; no native boot
of this new handler or V11 BOOT package is claimed at this checkpoint.

## Actual linked bootstrap in QEMU

Workflow a31-bootstrap downloads the verified V11 kernel from run39952374717,
checks source/hash, and boots its actual segments at the native >4GiB
addresses with a synthetic two-node ADT. A small EL1 wrapper supplies
boot_args and a 13MHz CNTFRQ. This tests original linked XNU bootstrap
instructions, rather than a separate receiver or the fault handler alone.

Run39956681635 reached first arm_init C checkpoint: physical entry, stack,
tables and MMU-stage markers, EL1, SCTLR3454593d with M=1, CNTFRQ13MHz and
ENTRY-CHECK PASS. It stopped at RECOVERY FAILED because the Samsung SRAM
header and reset firmware are absent from QEMU virt. This is not native
Galaxy A31 C entry or an iOS boot. Native V11 remained on Samsung splash;
its logs were unavailable after the manual recovery return.

## Native pre-MMU checkpoint

V13 on Galaxy A31 reached the audited instruction immediately before
MSR SCTLR_EL1: original stack/table/TCR/TTBR/MAIR setup markers preceded
intentional BRK#a31. Console-ramoops reports ESRf2000a31, ELR10148e4f8,
SCTLR30d00800 with M=0 and BOOT RECOVERY REQUEST. The phone returned to
TWRP automatically. This also verifies the physical stack-independent
exception handler and software recovery path on hardware. It does not
prove MMU enable, first C or iOS boot. Only pstore contains XNU markers;
last_kmsg contains the matching shim/copy session.

V14 on the actual A31 also passed the next checkpoint at PA10148e500,
immediately after original MSR SCTLR_EL1 and ISB. The recorded
SCTLR3454593d has MMU, data cache and instruction cache enabled; exact
ESRf2000a31/ELR10148e500 and automatic software return confirm the
controlled trap. This proves that transition and physical instruction
fetch, but not the high-KVA arm_init entry or C stack operations.

V15 reached the actual high-KVA arm_init entry on A31: exact intentional
BRK at ELRfffffe0007ad4fe8 with SCTLR3454593d. This verifies the high-KVA
branch after CPACR/TPIDR/MIDR setup, before the original function prologue
or stack stores. First diagnostic C-call success remains unverified.

V16 on the A31 passed arm_init's original stack prologue, GOT guard load
and initial stores: intentional BRK at fffffe0007ad5030, SPfffffe00080b3f30,
SCTLR3454593d, before BL sweet_early_mark.

## Missing C reset instruction found

Disassembly of the actual V11 _a31_return showed DSB followed directly
by the return-value logger, with no ISB or SMC. Darwin arm64 uses semicolon
as an assembler comment, so the inline string "dsb sy; isb; smc #0"
only emitted its first instruction. A minimal target-macOS compile
reproduced this; real newline separators emitted all three instructions.
Patch0085 corrects the string. The kernel workflow now requires the exact
DSB/ISB/SMC sequence inside the linked _a31_return symbol, rather than
accepting strings or an unrelated SMC elsewhere. Host regression cases
reject a truncated string and a valid sequence in a different function.
This explains a definite missing reset call, but a corrected native
first-C run is still needed to establish complete checkpoint behavior.
