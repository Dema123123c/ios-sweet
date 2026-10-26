# A31 pmap bootstrap checkpoint

## Measured native result, 2026-10-26

V24 source `0b7dee09e0314cedc28ed00126a8bc04a9b2fc2d` reached these ordered
checkpoints on the actual SM-A315F, after every V23 VM-table checkpoint:

```text
[A31-XNU] C STAGE 11: physmap table pointers rebound
[A31-XNU] TABLE-POINTERS-CHECK PASS
[A31-XNU] C STAGE 12: calling pmap_bootstrap
[A31-XNU] PMAP-ENTER-CHECK PASS
XNU_PMAP_MEM_BYTES=0x000000003fd00000
XNU_PMAP_ALLOC_BEGIN=0x00000001024fc000
XNU_PMAP_ALLOC_END=0x00000001025a4000
XNU_PMAP_ALLOC_LIMIT=0x000000013fd00000
XNU_PMAP_ROOT=0x00000001024d4000
XNU_PMAP_MAX_ASIDS=0x0000000000000800
[A31-XNU] C STAGE 24: pmap structures initialized
[A31-XNU] PMAP-STRUCTURES-CHECK PASS
[A31-XNU] C STAGE 13: pmap_bootstrap done
[A31-XNU] PMAP-BOOTSTRAP-CHECK PASS
[A31-XNU] RECOVERY REQUEST
```

The metadata allocation consumes 688128 bytes, within the observed managed
RAM bank. There are 2048 initial ASIDs. Always-on checks validate the kernel
pmap root against hardware TTBR1, table pointers through `kvtophys`, kernel
type, NX/64-bit flags, reference count, first/last ASID bitmap bits and
physical bounds. Guards run BEFORE metadata/ASID memory clears. Apple
UAT/SART bootstrap hooks are no-ops; no GPU/IOMMU driver is being tested.

Native EL1, SCTLR=0x3454593d, 13 MHz timer and exact linked VBAR
0xfffffe0007490800 are recorded. The user confirmed automatic TWRP return.
Only matching pstore proves XNU; last_kmsg contains loader records. Full
32 MiB BOOT readback and post-test BOOT/recovery/both-vbmeta checks passed.
Private raw evidence: `research/a31-v24-pmap-logs/report.json`.

This verifies early pmap bootstrap, not complete VM initialization or ASID
allocation for user tasks. Execution stops BEFORE `disable_preemption` and
the remaining page-table expansion in `arm_vm_init`; that function has not
returned. GPU, display/input/storage drivers, scheduler and iOS userland
remain unverified. V24 deliberately remains in BOOT, with TWRP available.

## Build and controls

- Kernel: [40365585903](https://github.com/Dema123123c/ios-sweet/actions/runs/40365585903).
- Shim: [40365585959](https://github.com/Dema123123c/ios-sweet/actions/runs/40365585959).
- Actual linked-kernel QEMU: [40368222414](https://github.com/Dema123123c/ios-sweet/actions/runs/40368222414).
- Kernel SHA256: `edc3b4171f78ff9573fe40a218a8ab4a6e062ecb41a6f4bb09e0a383d3380e8e`.
- BOOT SHA256: `4c58f083dff4fbd525488f966838951ab2bc6d84d3bfc17d10bd49e2a4c473af`.

All 76 host Python tests and ASan/UBSan allocation-bound checks passed on CI.
Twenty shim fault controls and twelve EL1/EL2 handoff controls passed. The
exact linked kernel passed three QEMU scenarios: normal pmap completion,
BRK #0xa31 after TTBR0 invalidation and BRK #0xa32 after pmap returned.
The latter recorded ESR=0xf2000a32 and ELR=0xfffffe0007491080, with MMU on
and no pmap PASS. Both fault controls reached the existing fatal handler
through the high-vector relay. Native fault injection was not performed.

## Private backups

At the user's request, important files were saved on both the PC and their
private Google Drive mount. There are 53 raw firmware/service/eMMC-boot
partitions (8687452160 bytes), primary/secondary GPT regions, original
Samsung BOOT/RECOVERY and Odin restore tars, plus source/evidence archives.
Every raw partition matches phone SHA256 before/after copying and the PC
and cloud-mount copies. Google Drive desktop confirmed all files synced.
No device identity dumps or key partitions are committed to Git.

This is NOT a userdata or authenticated RPMB backup. The primary GPT header
and array pass CRC. The secondary header passes, but its array CRC already
mismatched on the phone; two independent reads matched. Both raw regions
were preserved without repair. An unaliased second metadata partition,
p34, was explicitly included alongside the by-name partitions.

Private locations and live restore state are in `NOTES.md`. Do not restore
EFS/NVRAM/key partitions to another phone or automatically write GPT.

## Next boundary

Audit and group the remaining `arm_vm_init` page-table allocations, page
protection and pmap initialization through its return. Preserve high
diagnostic aliases, the bootstrap-table fatal relay and exact linked-kernel
normal/fault controls before advancing on hardware. Full VM startup and
GPU/display work are later milestones.
