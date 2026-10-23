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

V22 passed the next group on the real A31: `rtclock_early_init`, startup
tunables/timeouts/locks, timer-call initialization and `cpu_init`. Patch 0090
continues stage 4/5, verifies the runtime CPU fields, then stops at stage 6
before `processor_bootstrap` and VM. Matching pstore contains the ordered
prior checkpoints, STARTUP-LOCKS-CHECK PASS, CPU-INIT-CHECK PASS and recovery
request with EL1, SCTLR `0x3454593d`, 13 MHz CNTFRQ and no exception/failure.
The user confirmed automatic TWRP return. Only pstore establishes XNU results;
last_kmsg contains loader records. Private evidence:
`research/a31-v22-runtime-logs/report.json`.

Source `70bbb0efad041da1e7edc8c6651c191df2a4790d`, kernel CI39977026628,
shim CI39977026552 and actual-kernel QEMU CI39978346567 passed. QEMU's absent
Samsung SRAM header prevents emulated firmware reset; the native software
reset is separately confirmed. The actual target disables MONOTONIC and
paravirtual ticket locks; generic KPC idle hooks are empty. No Apple PMU or
Qualcomm driver initialization is introduced by this test.

V22 remains in BOOT with the original restore retained; full readback SHA:
`5daceb2c179f0f4298dbbef9d4611922fafa1a85307faaac5ac724a4ff6c0db1`.
Recovery and both vbmetas were checked unchanged. This is CPU initialization,
not GPU initialization. Scheduling, VM, graphics and iOS userland have not run.
Before VM teardown of TTBR0, the log and recovery helpers need persistent
final kernel mappings and a checked transition from their current low VAs.

V20 passed early `PE_init_platform(FALSE)` on the real A31. Patch 0088
represents the unknown bus frequency as zero with valid 0/1 ratios, avoiding
zero division and doubled-CPU overflow without inventing a bus frequency.
The native checkpoint verifies 13 MHz timebase/decrementer, a nonzero CPU
rate and the unknown-bus policy before stage 2/PLATFORM-CHECK PASS/reset.
Only matching pstore establishes this result; last_kmsg has loader records.
Evidence: private `research/a31-v20-platform-logs/report.json`, loader build
`0cfdae130e969f4f23d58fc2e502fbcdcc0f9479`, kernel source
`473dd625283d629be06a3e554218ff42410c2fc7`. Kernel CI39972353910 and corrected
QEMU CI39973877942 passed; the first QEMU fixture was rejected before XNU
because it retained Redmi identity. The corrected fixture is regression-tested.
V20 BOOT SHA: `36cf89f539bca7a5f5d09254020b19fe721a595227b6b0129f59a28e37f9bbf5`.

V21 groups generic event-stream setup, CPU topology, bootstrap-thread
creation and `cpu_bootstrap` in one test. Patch 0089 continues stages 2/3
and checks one CPU/cluster, boot CPU 0, current-thread identity, its CPU data
pointer and zero preemption level before stage 4/CPU-BOOTSTRAP-CHECK PASS.
`cpu_bootstrap` itself is empty on this generic ARM target. This does not
start scheduling or secondary CPUs. Execution stops before early rtclock,
startup callbacks, VM and drivers. Kernel CI39974602127 and shim CI39974601865
passed at `33a398308dd27d50f1088eae64639e4cbc3bfef5`. Actual-kernel QEMU
CI39976029411 and the subsequent native A31 test also passed: matching
pstore contains all ordered prior stages, topology PASS, stage 4
CPU-BOOTSTRAP-CHECK PASS and recovery request, with EL1, MMU enabled and
13 MHz timer. No failure/exception/reset-return markers were present.
The user confirmed automatic TWRP return. Private evidence:
`research/a31-v21-cpu-bootstrap-logs/report.json`; last_kmsg remains loader-only.
V21 remains in BOOT, SHA-256
`028a6aeae42d9e72c3d89739c24226a63cb11a476a82cf9cc7b93cd9c308d8a6`.
Recovery and both vbmetas were checked unchanged; the original BOOT restore
is retained. Scheduling, secondary CPUs, VM and phone drivers are not running.

V19 adds patch 0087. Stage 21 now returns once; the original boot-argument
copy and `cpu_data_init(&BootCpuData)` execute. Before `PE_init_platform`,
the diagnostic compares every copied boot-argument byte with the original
and verifies initial CPU flags, interrupt state, pending AST, rtcPop,
register-map address and sleep token. Stage 22 emits CPU-DATA-CHECK PASS
only in the validated stage sequence, then uses the existing recovery reset.
It does not initialize CPU topology, scheduling, VM or phone drivers.
The collector requires the ordered prior stages and this new completion
within one matching session. V19 passed on the actual A31: matching
`57397c0` pstore records all three ordered C stages, CPU-DATA-CHECK PASS
and RECOVERY REQUEST with EL1, SCTLR `0x3454593d`, CNTFRQ 13 MHz and no
failure/exception/reset-return markers. The user confirmed automatic TWRP.
Only pstore establishes XNU completion; last_kmsg has loader records.
Private evidence is `research/a31-v19-cpu-data-logs/report.json`.
V19 remains in BOOT with the original restore available.

Kernel CI39969205795, shim CI39969205881 and actual-kernel QEMU
CI39971077759 passed at `57397c01982c9c2ee3396f182b5b050940567b57`.
Linked disassembly confirms the 736-byte argument copy, CPU data call,
byte/field checks and stage 22 before the platform call. V19 was written
to BOOT and fully read back; SHA-256:
`ecffffc8f9d6d33e4b9bf79b40dc955a2dda2cb3ae3f97a18e5feece30e2ecdb`.
Recovery and both vbmetas were checked unchanged.

Before V20, the platform boundary required a clock-policy fix: `mka31adt.py`
omits the unknown bus frequency, while `pe_identify_machine()` uses that
zero frequency in a division. This is undefined C behavior and produces
invalid clock ratios; no native platform crash is established by that
source audit. V19 deliberately stopped before this code; patch 0088 now
guards the unknown-bus ratios. Do not invent an
A31 bus frequency to make the calculation pass.

V18 advances the boundary using patch 0086: the first validated C hook
returns once; stage 21 runs immediately after `arm_setup_pre_sign()` and
`arm_slide_rebase_and_sign_image()`. It stops before copying boot arguments,
`cpu_data_init()`, `PE_init_platform()` or CPU/VM startup. It retains the
bootstrap log/reset mappings and rejects unexpected stages. A later native
PASS requires ordered stage 1, entry PASS, stage 21, REBASE-CHECK PASS and
recovery request in one matching session, with EL1/MMU/13 MHz registers.

Kernel CI39966833389, shim CI39966833403 and actual-kernel QEMU
CI39968197929 passed at `cf64132eaf5c67696eb5200a620f095a91085afd`.
QEMU reaches REBASE-CHECK PASS; its absent Samsung SRAM header prevents
firmware reset and logs RECOVERY FAILED, as expected for this emulator.
The subsequent native test also passed: matching `cf64132` pstore contains
both ordered C stages, REBASE-CHECK PASS, EL1, SCTLR `0x3454593d`, CNTFRQ
13 MHz and RECOVERY REQUEST, without failure/exception/reset-return markers.
The user confirmed automatic TWRP return. last_kmsg contains loader records
only; pstore establishes the XNU result. Evidence is private
`research/a31-v18-post-rebase-logs/report.json`. V18 remains in BOOT with
the stock restore available. CPU/VM initialization and drivers have not run.
BOOT SHA-256:
`efe9935846af0e1885be787a6cf1ab051a7c0215b8f25be653397345023f396d`.

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
