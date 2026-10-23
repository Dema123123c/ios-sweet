# A31 XNU payload preparation

This stage loads kernel data into RAM and checks it, without executing XNU.
The successful V6 native diagnostic is the baseline, not an XNU boot.

`tools/a31_payload.py` checks plain-arm64 Mach-O headers, load-command bounds,
segment source and destination ranges, overlap and executable entry. The
initial path rejects chained-fixup kernels and arm64e. It packs the existing
SWEETXNU v1 format only after checking the A31 ADT and managed RAM policy.
The resulting payload is checked again as a standalone object.

`shim/a31/payload.c` independently validates that object in the native loader:

- At most 32 segments; bounded source, destination, entry and command line.
- No overlapping file data, destination segments or ADT region.
- Bounded recursive ADT structure, exactly one chosen node and matching RAM.
- ADT and boot arguments fit after the kernel within the managed extent.
- Boot args Revision/Version 2, 736-byte layout, disabled video output.
- Every segment byte, BSS zero, ADT and boot-argument write is read back.

The native `--payload-check` image reads its payload from the FDT initrd
range. On A31 the expected source starts at `0x47c80000`, with a 24 MiB
maximum. The only destination extent allowed is
`0x100000000 + 0x3fd00000`; the ADT reserves its separate panic-log area.
The FDT memory bank, memreserve table and fixed reserved-memory ranges are
checked again before copying. Size-only reserved-memory nodes request
future OS/driver allocations, rather than naming existing address ranges;
none of those Linux device drivers runs in this standalone shim. The fresh
packaging preflight also checks the live Linux System RAM map.

Reference: [reserved-memory schema](https://github.com/devicetree-org/dt-schema/blob/main/dtschema/schemas/reserved-memory/reserved-memory.yaml).

The tested original A31 Mach-O is 17,171,976 bytes, SHA-256
`78dad2f54e7a861d47fab8deef719368318ecc856f9873070d482eca52ffc629`.
The current prepared payload contains ten segments and a 3,728-byte ADT.
Its computed entry PA is `0x10148b488`, boot args PA `0x1024c8000`, top
`0x1024cc000`. These addresses have not yet been used for native preparation
at this source checkpoint. Local Linux EL0 tests on the A31 validated the
actual payload, live FDT, simulated copying/BSS and exact boot args; they
did not write those physical destinations or enter XNU.

`mka31diag.py --payload` replaces the original BOOT ramdisk only when the
native manifest explicitly says prepare-only and kernel-jump-disabled.
It validates the payload independently, preserves the original DTB/header,
and verifies the packaged ramdisk matches the checked bytes. BOOT restore,
fresh unlocked/orange FDT, pstore profile and exact recovery ABI gates remain.
The tool does not flash a device.

QEMU checks both EL1 and EL2 preparation using a separate fixture in its
own RAM window; C tests with sanitizers cover malformed data and write
failure. Native hardware copying still requires a separate measured result.
Success must include `PAYLOAD COPY/READBACK PASS` and `XNU JUMP DISABLED`.
Neither that result nor simulator tests demonstrate XNU execution.

Next: A31-specific early XNU log mappings and panic recovery, then actual
Mach-O/ADT/boot-args handoff. No kernel-entry mode is exposed by this stage.
