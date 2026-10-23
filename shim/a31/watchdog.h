#pragma once
#include <stdint.h>

typedef uint32_t (*a31_wdt_read)(void *, unsigned);
typedef void (*a31_wdt_write)(void *, unsigned, uint32_t);

/* Audited recovery v2 driver ABI. Caller supplies ordered MMIO callbacks.
 * No DDR-reserve, PMIC, non-reset or reset-source configuration changes.
 */
static inline int a31_watchdog_arm(void *context, a31_wdt_read read,
                                   a31_wdt_write write, unsigned seconds)
{
    if (seconds < 1 || seconds > 8 || read(context, 0) != 0x5c) return 0;
    uint32_t length = (seconds << 11) | 8;
    write(context, 4, length);
    if ((read(context, 4) & 0xffe0) != (length & 0xffe0)) return 0;
    write(context, 8, 0x1971);
    /* Single-stage reset: retain EXTEN/EXTRA_CNT; clear IRQ/DUAL_MODE. */
    write(context, 0, 0x22000015);
    if (read(context, 0) != 0x15) return 0;
    write(context, 8, 0x1971);
    return 1;
}
