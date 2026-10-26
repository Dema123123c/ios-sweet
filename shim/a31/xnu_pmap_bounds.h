#ifndef A31_XNU_PMAP_BOUNDS_H
#define A31_XNU_PMAP_BOUNDS_H
#include <stdint.h>

/* The CPU0 fixture manages at most this observed, contiguous A31 RAM bank. */
static inline int
a31_xnu_pmap_bounds(uint64_t bytes, uint64_t start, uint64_t end, uint64_t limit)
{
    const uint64_t base = UINT64_C(0x100000000);
    return bytes >= UINT64_C(0x4000000) && bytes <= UINT64_C(0x3fd00000) &&
        !(bytes & UINT64_C(0x3fff)) && base <= start && start <= end &&
        end <= limit && limit <= base + bytes;
}
#endif
