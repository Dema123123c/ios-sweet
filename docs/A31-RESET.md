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
The existing native watchdog stop is unchanged.

## First native result, 2026-10-23

Source `a678d2ce7cb4dd427afab315993e7c45bc042185` completed its diagnostic
on the A31. Both `/proc/last_kmsg` and `/sys/fs/pstore/console-ramoops`
contained the same expected-build PASS session: EL1 entry, 16 KiB MMU
alias PASS, three virtual-timer IRQs and no other IRQs, WDT MODE 0x5d to
0x5c, PSCI version 1.1, and RECOVERY RETURN REQUESTED. The phone reset itself
and opened TWRP after the user acknowledged the second boot warning with
a short Power press. No forced recovery-key combination was used.

This verifies native diagnostic execution and this software-return/log
retention path. It does not establish an XNU or iOS boot. Post-test full
partition reads confirmed the diagnostic BOOT remained installed, with
TWRP and both vbmetas unchanged and the loader still unlocked/orange.

Host tests check the SRAM bounds and that every other word remains intact;
QEMU checks exercise diagnostic entry/exception paths, not Samsung reset
hardware. Original BOOT and TWRP backups remain the fallback.

Runtime kallsyms collection temporarily changed kptr_restrict from 2 to 0
and restored it to 2 immediately, including the error path. Private raw
images, symbols and control records stay outside Git.

## Bounded watchdog return control

A separate native-only control is available as --watchdog-control. It
rejects QEMU and every payload/entry mode. After normal EL1/MMU/timer
checks, it prearms the same validated three Samsung SRAM recovery words,
logs WATCHDOG CONTROL WAIT and arms a four-second single-stage watchdog.
If eight seconds pass, it disables the watchdog and uses the existing
PSCI recovery fallback. The control never branches into XNU.

The actual installed recovery Image was independently disassembled using
its captured live symbol addresses and Image virtual base. At offset
0xbfb5e0, mtk_wdt_set_time_out_value shifts seconds by6, clamps to0x7ff,
shifts by5, inserts key8, writes LENGTH at+4 and issues DSB. Mode config
at0xbfb640 confirms keyed MODE writes, enable bit0, external reset bit2,
IRQ bit3 and dual mode bit6. The restart routine begins at0xbfb9e0.
The header and reference v2 source agree with the binary.

The guarded control accepts only observed stopped MODE0x5c, writes
LENGTH=(4<<11)|8, checks timeout bits, kicks RESTART+8 with0x1971, writes
MODE0x22000015, verifies0x15, and kicks again. IRQ/dual are cleared so the
first expiry requests reset; EXTEN/EXTRA_CNT remain enabled. It does not
change DDR reserve, PMIC, non-reset registers, storage or reset routing.
Host tests enforce timeout bounds, exact register order/write allowlist,
all other mode rejection and failed readback paths. Timed reset and log
retention are NOT established by compilation, mocks or disassembly.
They require the separate native control before XNU handoff use.
