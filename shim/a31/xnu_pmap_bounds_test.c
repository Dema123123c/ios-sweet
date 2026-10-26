#include "xnu_pmap_bounds.h"
#include <assert.h>

int main(void)
{
    const uint64_t size = 0x3fd00000, limit = 0x13fd00000;
    assert(a31_xnu_pmap_bounds(size, 0x102500000, 0x102600000, limit));
    assert(a31_xnu_pmap_bounds(size, limit, limit, limit));
    assert(!a31_xnu_pmap_bounds(size, 0xffffffff, 0x102600000, limit));
    assert(!a31_xnu_pmap_bounds(size, 0x102600000, 0x102500000, limit));
    assert(!a31_xnu_pmap_bounds(size, 0x102500000, limit + 1, limit));
    assert(!a31_xnu_pmap_bounds(size, 0x102500000, limit, limit + 1));
    assert(!a31_xnu_pmap_bounds(UINT64_MAX, 0x102500000, limit, limit));
    assert(!a31_xnu_pmap_bounds(size + 1, 0x102500000, limit, limit));
    assert(!a31_xnu_pmap_bounds(0, 0x100000000, 0x100000000, 0x100000000));
    assert(!a31_xnu_pmap_bounds(size, 0x102500000, UINT64_MAX, UINT64_MAX));
    return 0;
}
