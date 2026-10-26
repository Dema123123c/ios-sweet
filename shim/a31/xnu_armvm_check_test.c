#include "xnu_armvm_check.h"
#include <assert.h>

static _Alignas(16384) uint64_t page[2048];
int main(void)
{
    assert(a31_xnu_empty_l3(page, sizeof(page)));
    assert(!a31_xnu_empty_l3(0, sizeof(page)));
    assert(!a31_xnu_empty_l3(page, sizeof(page) - 1));
    assert(!a31_xnu_empty_l3(page + 1, sizeof(page)));
    page[0] = 1;
    assert(!a31_xnu_empty_l3(page, sizeof(page)));
    page[0] = 0;
    page[2047] = UINT64_MAX;
    assert(!a31_xnu_empty_l3(page, sizeof(page)));
    page[2047] = 0;
    assert(a31_xnu_empty_l3(page, sizeof(page)));
    return 0;
}
