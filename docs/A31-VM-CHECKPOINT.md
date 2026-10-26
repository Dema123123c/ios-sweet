# A31 final VM-table checkpoint

## Measured native result, 2026-10-26

V23 reached the following ordered checkpoints on the actual SM-A315F:

```text
[A31-XNU] CPU-INIT-CHECK PASS
[A31-XNU] C STAGE 7: entering arm_vm_init
[A31-XNU] VM-ENTER-CHECK PASS
[A31-XNU] C STAGE 23: final diagnostic mappings prepared
[A31-XNU] VM-MAPS-CHECK PASS
XNU_FINAL_LOG_VA=0xfffffe0002003000
XNU_FINAL_SRAM_VA=0xfffffe0002045c00
[A31-XNU] FINAL-IO-ALIASES PASS
[A31-XNU] C STAGE 10: TTBR0 off; TLB flushed
XNU_TTBR0_EL1=0x00000001024d0000
XNU_VBAR_EL1=0xfffffe0007490800
[A31-XNU] VM-LOW-ALIASES INVALID
[A31-XNU] VM-TABLES-CHECK PASS
[A31-XNU] RECOVERY REQUEST
```

EL1, SCTLR_EL1=0x3454593d and CNTFRQ=13000000 are recorded. VBAR matches
the exact linked final-vector symbol. The user confirmed automatic TWRP
return. Only pstore contains XNU evidence; last_kmsg contains loader records.
Private raw captures/report: `research/a31-v23-vm-logs/`. Full BOOT readback
and post-test recovery/both-vbmeta checks passed. No Data/TEE/bootloader write.

This verifies early `arm_vm_init` through final TTBR1 activation and TTBR0
invalidation. Execution deliberately ends BEFORE `kva_active` becomes true,
table-pointer rebinding and `pmap_bootstrap`. It does not establish complete
VM initialization, a scheduler, GPU/display support or an iOS boot.

## Provenance and controls

- Source: `2dd5a3519740da42b2103ab97454259775abcae9`.
- Kernel build: [40357691472](https://github.com/Dema123123c/ios-sweet/actions/runs/40357691472).
- Shim controls: [40357697386](https://github.com/Dema123123c/ios-sweet/actions/runs/40357697386),
  including 20 fault and 12 EL1/EL2 handoff controls.
- Actual linked-kernel QEMU: [40360455620](https://github.com/Dema123123c/ios-sweet/actions/runs/40360455620),
  both normal VM transition and post-TTBR0 fault control passed.
- Kernel SHA256: `95a7ef88fb3bd4369a1a837d0d5d4773a309c6734e9f1bea9a7c6204e78f704f`.
- Diagnostic BOOT SHA256: `5426b2ced6736821dfdfd1d13dab69573d865e6ca315894962f21f9b34dd4c7b`.
- Original BOOT SHA256: `af9ef4265e3d15bb0cc3ff8c0b968eeb6da0253db305e37908aa649cfba176f1`.

The QEMU fault control executes BRK #0xa31 at the exact symbol
0xfffffe0007491078 with MMU enabled, after both low aliases become invalid.
The high-vector relay restores bootstrap TTBR0 and reaches the canonical
physical fatal handler BEFORE disabling MMU. ESR=0xf2000a31 and ELR match.
This fault relay was tested in QEMU; the native success path did not raise
an exception. QEMU lacks Samsung SRAM, so recovery-failed markers there
are expected; native recovery succeeded without those markers.

## Build migration

The macOS14 runner was unavailable during GitHub's scheduled brownout.
macOS15 Intel/Xcode16 now compiles the kernel. Hash-gated generated Xcode15
DriverKit output preserves XNU8796's IORPC ABI. Its archive, original source
header/definition and generated-output hashes are checked. Exactly two
private SDK TargetConditionals.h copies belonging to HFS/pthread are excluded;
all other original inputs match V22. Apple generated files remain outside Git.

## Next boundary

Audit and test the group covering `kva_active`, `phystokv` table-pointer
rebinding and `pmap_bootstrap`, with normal and exact-symbol fault controls
before a native write. Keep the diagnostic aliases and verify that bootstrap
tables needed by the fatal relay remain available throughout that group.
Inspect pmap locks/ASID allocation, `pmap_data_bootstrap`, UAT/SART callbacks
and available-RAM bounds. Do not advance straight to GPU initialization.
