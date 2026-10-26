#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "xnu_final_io.h"

int main(void)
{
    uint64_t storage[2050] = {0};
    uint64_t *page = storage + 1;
    storage[0] = storage[2049] = UINT64_C(0x123456789abcdef0);
    assert(!a31_xnu_final_fill(NULL, 0x4000));
    assert(!a31_xnu_final_fill(page, 0x3ff8));
    page[1023] = 1;
    assert(!a31_xnu_final_fill(page, 0x4000));
    assert(page[0] == 0 && page[17] == 0 && page[1023] == 1);
    page[1023] = 0;
    assert(a31_xnu_final_fill(page, 0x4000));
    for (size_t i = 0; i < 17; ++i)
        assert(page[i] == ((UINT64_C(0x4d05c000) + i * 0x4000) | A31_FINAL_NORMAL_PTE));
    assert(page[17] == (UINT64_C(0x10c000) | A31_FINAL_DEVICE_PTE));
    for (size_t i = 18; i < 2048; ++i) assert(page[i] == 0);
    assert(storage[0] == UINT64_C(0x123456789abcdef0));
    assert(storage[2049] == UINT64_C(0x123456789abcdef0));
    assert(!a31_xnu_final_fill(page, 0x4000));
    assert(A31_FINAL_LOG_VA - A31_FINAL_IO_VA == 0x3000);
    assert(A31_FINAL_SRAM_VA - (A31_FINAL_IO_VA + 17 * 0x4000) == 0x1c00);
    return 0;
}
