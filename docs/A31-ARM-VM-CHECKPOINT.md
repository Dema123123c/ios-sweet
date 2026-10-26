# A31 arm_vm_init-return checkpoint

## Measured native result, 2026-10-26

V25 source `50b7ca6e272557ab23ce4bd9732b1482fe926c00` executed the remainder
of `arm_vm_init` on the actual SM-A315F and reached its caller's checkpoint:

```text
[A31-XNU] PMAP-BOOTSTRAP-CHECK PASS
[A31-XNU] C STAGE 14: early I/O page tables ready
[A31-XNU] EARLY-IO-TABLES-CHECK PASS
XNU_ARMVM_ALLOC_BEGIN=0x00000001025a4000
XNU_ARMVM_ALLOC_END=0x00000001025d0000
XNU_ARMVM_ALLOC_LIMIT=0x000000013fd00000
XNU_ARMVM_PT_PAGES=0x000000000000000b
XNU_ARMVM_LEAF_PAGES=0x0000000000000003
XNU_ARMVM_PREEMPT_BEFORE=0x0000000000000000
XNU_ARMVM_PREEMPT_AFTER=0x0000000000000000
XNU_ARMVM_PENDING_AST=0x0000000000000000
XNU_ARMVM_FIRST_AVAIL=0x00000001025d0000
XNU_ARMVM_IO_START=0xfffffe000a000000
XNU_ARMVM_IO_END=0xfffffe000d000000
XNU_ARMVM_COPY_START=0xfffffe8fffdfc000
XNU_ARMVM_COPY_END=0xfffffe8fffffffff
[A31-XNU] C STAGE 25: late VM tables and globals verified
[A31-XNU] ARM-VM-TABLES-CHECK PASS
[A31-XNU] C STAGE 15: arm_vm_init returned
[A31-XNU] ARM-VM-INIT-CHECK PASS
[A31-XNU] RECOVERY REQUEST
```

The late allocation consumes 180224 bytes (11 x 16 KiB), contiguous with
the prior pmap metadata. The three L3 pages have valid NX table parents and
all 2048 PTEs invalid; their physical addresses belong to the new allocation.
The remaining pages are heap table directories. Always-on bounds checks run
before every `alloc_ptpage` allocation, with a 32-page late budget. Occupied
L2 slots cannot be replaced. LowGlo static/physmap bounds and first_avail are
validated, pending AST is zero, and preemption depth remains zero.

Native EL1, SCTLR=0x3454593d, 13 MHz timer and linked final VBAR
0xfffffe0007491800 are recorded. No failure, exception or reset-return marker
appears in the matching pstore session. TWRP was observed by ADB after the
recorded recovery request; the user subsequently confirmed automatic TWRP
return with only short Power presses on the boot warning. Only pstore contains XNU
evidence; last_kmsg contains loader records. Private captures/report:
`research/a31-v25-armvm-logs/`. Full BOOT readback and post-test BOOT,
recovery and both-vbmeta hashes were checked. Only BOOT was written.

This proves return from early `arm_vm_init`, not completion of the VM
subsystem, a scheduler, a GPU/display driver or an iOS boot. Execution stops
before the caller's debug/serial/console setup and later VM startup. V25
is deliberately retained in BOOT with TWRP available.

## Provenance and controls

- Kernel: [40373179878](https://github.com/Dema123123c/ios-sweet/actions/runs/40373179878).
- Shim: [40373179514](https://github.com/Dema123123c/ios-sweet/actions/runs/40373179514).
- Actual linked-kernel QEMU: [40375510661](https://github.com/Dema123123c/ios-sweet/actions/runs/40375510661).
- Kernel SHA256: `d64f01862aa6811766010c6d6fcb6c9eb10b50b43a6804266ab99971e37d29bd`.
- BOOT SHA256: `5f121379ea227579bc3ce1676701f184c72721ac38ebb3cf3368d90b4069c67b`.

All 81 host Python tests and ASan/UBSan empty-leaf checks passed on CI,
alongside the previous 20 shim fault and 12 EL1/EL2 handoff controls.
The linked kernel passed normal completion and three exact-symbol fault
controls: #0xa31 after TTBR0 invalidation, #0xa32 after pmap bootstrap, and
#0xa33 after actual arm_vm_init return. The last records ESR=0xf2000a33,
ELR=0xfffffe0007492088 and MMU on, without ARM-VM-INIT-CHECK PASS. Native
fault injection was not performed; native evidence is the normal path.

## Next boundary and preservation

Audit/group `patch_low_glo`, `PE_consistent_debug_inherit`, serial discovery
and kprintf startup. The sanitized A31 arm-io tree contains only gic/wdt;
no Apple/RPi/Qualcomm UART or framebuffer node may be introduced by copying
the Redmi configuration. Keep pstore and the fatal relay usable until an
A31 console is verified. Later platform, CPU timer/interrupt and VM startup
remain separate, unverified work.

Keep the sealed V24 archive and original Samsung BOOT/RECOVERY restore
images. Important firmware/service backups exist on both the PC and the
user's private Google Drive, with no userdata or RPMB backup. No GPT repair
was performed; see the prior pmap checkpoint for the preserved secondary
GPT CRC limitation. Device dumps and keys remain outside Git.
