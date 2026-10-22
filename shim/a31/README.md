# A31 diagnostic shim

This is a standalone first-stage diagnostic, not an XNU loader or iOS image.
It does not read or write storage, initialise the display, or start secondary
CPUs. It enters EL1 (including an EL2 handoff), checks 16 KiB translation
through a distinct virtual alias, and checks three virtual-timer interrupts
through GICv3. The native build then halts; manual recovery is required.

The native build accepts the captured MT6768 platform and the Samsung
sec-log reserved region at 0x46c00000 / 2 MiB. It appends to the LOGM ring
described in Samsung's `drivers/samsung/misc/sec_log.c`; Linux normally
copies the old ring to `/proc/last_kmsg`. Persistence across this phone's
bootloader/recovery sequence has not yielded a diagnostic session. On the
latest recovery boot, `last_kmsg` instead exports LK logs, so it cannot be
assumed to contain the previous Linux/kernel log.

The updated native build additionally appends Linux persistent-RAM console
records in the observed pstore reservation: 0x4d010000 / 0xe0000. The measured
recovery layout has 4 KiB records, 256 KiB console, a second 256 KiB bconsole,
4 KiB ftrace, 64 KiB pmsg and ECC disabled; the console starts at 0x4d05f000.
It uses the DBGC header (signature/start/size), validates the reserved region
and rejects overlap with the shim or FDT. The packager requires the matching
fresh recovery sysfs profile. Collection includes
`/sys/fs/pstore/console-ramoops-0`; actual native persistence is untested.

After logging entry, the native build checks the `mediatek,toprgu` FDT range
at 0x10007000 / 4 KiB, records watchdog MODE/STATUS, and clears only MODE.EN
using key 0x22000000, as the A31 kernel's `mtk_wdt_stop()` does. It verifies
EN stayed clear. Watchdog reset is a hypothesis, not a measured explanation
of the earlier bootloop. The QEMU build does not access these registers.

No framebuffer writes or
Qualcomm restart/USB/UFS register accesses are included.

```sh
python3 shim/a31/build.py --out research/a31-diag/native
python3 shim/a31/build.py --qemu --out research/a31-diag/qemu
python3 shim/a31/run_qemu.py --image research/a31-diag/qemu/Image --out research/a31-diag/results
```

`--cc` accepts an NDK clang executable on Windows. Output includes a padded
Linux arm64 `Image`, `Image.gz`, ELF/map files, and a SHA-256 manifest. The
builder rejects absolute C-data relocations. The QEMU variant only accepts
QEMU virt and uses PL011/semihosting; **do not boot it on the phone**.

The `a31-shim` workflow tests both EL1 and EL2 entries and the parser/log
ring with AddressSanitizer and UndefinedBehaviorSanitizer. Those are emulator
and host checks; only a later phone test can establish MediaTek compatibility.

References:
- [AArch64 boot protocol](https://www.kernel.org/doc/html/latest/arch/arm64/booting.html)
- [Samsung log layout](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/lineage-19.1/drivers/samsung/misc/sec_log.c)
- [Samsung log addresses and magic](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/lineage-19.1/include/linux/sec_debug.h)
- [A31 watchdog driver](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/48d7bfb222e1e722b9c77f78beef056d0011f4cc/drivers/watchdog/mtk_wdt.c)
- [Samsung ramoops layout](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/lineage-19.1/fs/pstore/ram.c)
- [Persistent-RAM header](https://github.com/Galaxy-MT6768/android_kernel_samsung_mt6768/blob/lineage-19.1/fs/pstore/ram_core.c)

No device dump, stock DTB, original boot image, or per-device identifier is
included here. A phone boot package and a verified restore package must be
prepared privately before requesting authorization to write any partition.
