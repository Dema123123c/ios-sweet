#ifndef A31_XNU_ARMVM_CHECK_H
#define A31_XNU_ARMVM_CHECK_H
#include <stdint.h>
#include <stddef.h>

struct a31_armvm_report {
    uint64_t memory_bytes, begin, end, limit, pt_pages, leaf_pages;
    uint64_t preempt_before, preempt_after, io_start, io_end, copy_start, copy_end;
    uint64_t first_avail, pending_ast;
};
#define A31_ARMVM_MAX_VA UINT64_C(0xfffffe8fffffffff)
#define A31_ARMVM_COPY_START UINT64_C(0xfffffe8fffdfc000)
extern void a31_armvm_checkpoint(const struct a31_armvm_report *report);

static inline int
a31_xnu_empty_l3(const uint64_t *page, size_t bytes)
{
    if (!page || ((uintptr_t)page & 0x3fff) || bytes != 0x4000) return 0;
    for (size_t i = 0; i < 2048; ++i) if (page[i]) return 0;
    return 1;
}
#endif
