#ifndef A31_XNU_FINAL_IO_H
#define A31_XNU_FINAL_IO_H
#include <stdint.h>
#include <stddef.h>

#define A31_FINAL_IO_VA UINT64_C(0xfffffe0002000000)
#define A31_FINAL_LOG_VA (A31_FINAL_IO_VA + UINT64_C(0x3000))
#define A31_FINAL_SRAM_VA (A31_FINAL_IO_VA + UINT64_C(0x45c00))
#define A31_FINAL_NORMAL_PTE UINT64_C(0x0060000000000607)
#define A31_FINAL_DEVICE_PTE UINT64_C(0x006000000000060f)

/* A fresh 16 KiB L3 only: 17 NC/NX console pages, then one device/NX page.
 * Validate the entire page before the first store; never replace a mapping. */
static inline int
a31_xnu_final_fill(uint64_t *page, size_t bytes)
{
    if (!page || ((uintptr_t)page & 7) || bytes != 0x4000) return 0;
    for (size_t i = 0; i < 2048; ++i) if (page[i]) return 0;
    for (size_t i = 0; i < 17; ++i)
        page[i] = (UINT64_C(0x4d05c000) + i * 0x4000) | A31_FINAL_NORMAL_PTE;
    page[17] = UINT64_C(0x10c000) | A31_FINAL_DEVICE_PTE;
    return 1;
}
#endif
