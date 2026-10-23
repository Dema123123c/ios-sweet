# A31 diagnostic log retention and recovery return

On 2026-10-23 V5 returned to TWRP manually. The user observed no repeated
splash. No expected-build session was recovered from either Samsung log
source, and neither pstore console file existed. This does not establish
whether native entry, the MMU test or the timer test executed.

Two Linux controls used different unique PMSG markers on the same phone:

| Return method | Recovery pstore | Control marker |
| --- | --- | --- |
| Power+Down, then Power+Up back to TWRP | Empty directory | Not recovered |
| `adb reboot recovery` | Console and PMSG files | Recovered in PMSG |

These measurements show that the manual return route loses access to the
control record. They do not identify whether DRAM was erased, a boot stage
cleared the buffers, or recovery discarded them. Native log persistence
cannot be assessed using that route without another observation channel.

## Candidate software return

The installed recovery identifies itself as Linux 4.14.186-physwizz+ and
has CONFIG_SEC_REBOOT and CONFIG_ARM_PSCI_FW. Its source-level Samsung
reboot mechanism sets SRAM request fields before restarting. Reference:
[Samsung sec_reboot.c](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/48d7bfb222e1e722b9c77f78beef056d0011f4cc/drivers/samsung/sec_reboot.c).

Offsets were independently checked in the actual recovery kernel, rather
than assuming that the reference source has the same structure layout.
The compressed kernel SHA-256 is
`8fed8f3fd04590778eedc5ad65a54f6cba8d9ba2a5adb3fd683ee71484feaa4f`.
The recovery partition SHA-256 is
`d8a89533d039c79618b4dffcdc5cdec5949534020b2011088a02b1899bbcd890`.

The kernel Image's initial branch identifies `stext`; matching that symbol
to live kallsyms locates `sec_reboot` at Image offset `0xd1e7fc`. Its
instructions load the console header's Linux offset at `+0x2c` and use:

| Field relative to Linux structure | Offset | Recovery request value |
| --- | --- | --- |
| is_upload | 0x3ec | 0 |
| is_power_reset | 0x3f4 | 0x12345678 |
| power_reset_reason | 0x3f8 | 0x12345674 |

The last value was checked against the actual `recovery` string branch in
the binary. The SRAM base comes from the captured little-endian chosen
descriptor: `0x10dc00, 0x800, type 1, memory-info offset 0xac0`.
The native code demands that exact descriptor, a valid DBGC header, matching
buffer size, aligned and bounded Linux offset, and bounded console offset.
The packager requires the exact independently checked recovery dump.

After validating the FDT PSCI SMC method and supported PSCI_VERSION, finish
writes those three words, issues a system barrier, and invokes standard
PSCI SYSTEM_RESET (`0x84000009`). It does not use MediaTek reset registers,
write PMIC state or modify any storage partition to select recovery.
The existing native watchdog stop is unchanged. Native reset, recovery
selection and log retention through this candidate remain unverified.

Host tests check the SRAM bounds and that every other word remains intact;
QEMU checks exercise diagnostic entry/exception paths, not Samsung reset
hardware. Original BOOT and TWRP backups remain the fallback.

Runtime kallsyms collection temporarily changed kptr_restrict from 2 to 0
and restored it to 2 immediately, including the error path. Private raw
images, symbols and control records stay outside Git.
