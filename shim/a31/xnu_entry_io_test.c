#include "xnu_entry_io.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint32_t ring[0x40000 / 4], before[0x40000 / 4];
static uint32_t sram[0x800 / 4], snapshot[0x800 / 4];

int main(void)
{
    const uint32_t capacity = sizeof(ring) - 12;
    ring[0] = 0x43474244;
    assert(a31_xnu_ring_putc(ring, sizeof(ring), 'A'));
    assert(ring[1] == 1 && ring[2] == 1 && ((char *)ring)[12] == 'A');
    ring[1] = capacity - 1; ring[2] = capacity - 1;
    assert(a31_xnu_ring_putc(ring, sizeof(ring), 'Z'));
    assert(ring[1] == 0 && ring[2] == capacity && ((char *)ring)[sizeof(ring) - 1] == 'Z');
    assert(a31_xnu_ring_putc(ring, sizeof(ring), 'W'));
    assert(ring[1] == 1 && ring[2] == capacity && ((char *)ring)[12] == 'W');
    for (unsigned which = 0; which < 5; which++) {
        memset(ring, 0, sizeof(ring)); ring[0] = 0x43474244;
        if (which == 0) ring[0] = 0;
        if (which == 1) ring[1] = capacity;
        if (which == 2) ring[2] = capacity + 1;
        if (which == 3) ring[1] = 1;
        memcpy(before, ring, sizeof(ring));
        assert(!a31_xnu_ring_putc(ring, which == 4 ? 16 : sizeof(ring), 'X'));
        assert(!memcmp(before, ring, sizeof(ring)));
    }
    assert(!a31_xnu_ring_putc(NULL, sizeof(ring), 'X'));
    assert(!a31_xnu_ring_putc((char *)ring + 1, sizeof(ring), 'X'));
    for (unsigned offset = 0; offset <= 0x440; offset += 64) {
        memset(sram, 0xa5, sizeof(sram));
        sram[0] = 0x43474244; sram[10] = sizeof(sram); sram[11] = offset;
        sram[12] = offset + 0x3fc;
        memcpy(snapshot, sram, sizeof(sram));
        int expected = offset >= 64 && offset <= sizeof(sram) - 0x3fc;
        assert(a31_xnu_request_recovery(sram, sizeof(sram)) == expected);
        if (expected) {
            snapshot[(offset + 0x3ec) / 4] = 0;
            snapshot[(offset + 0x3f4) / 4] = 0x12345678;
            snapshot[(offset + 0x3f8) / 4] = 0x12345674;
        }
        assert(!memcmp(snapshot, sram, sizeof(sram)));
    }
    for (unsigned which = 0; which < 6; which++) {
        memset(sram, 0, sizeof(sram));
        sram[0] = 0x43474244; sram[10] = sizeof(sram); sram[11] = 64; sram[12] = 0x43c;
        if (which == 0) sram[0] = 0;
        if (which == 1) sram[10]--;
        if (which == 2) sram[11]++;
        if (which == 3) sram[12]--;
        if (which == 4) sram[12] = sizeof(sram) + 1;
        memcpy(snapshot, sram, sizeof(sram));
        assert(!a31_xnu_request_recovery(sram, which == 5 ? 0x400 : sizeof(sram)));
        assert(!memcmp(snapshot, sram, sizeof(sram)));
    }
    assert(!a31_xnu_request_recovery(NULL, sizeof(sram)));
    assert(!a31_xnu_request_recovery((char *)sram + 1, sizeof(sram)));
    puts("A31 XNU entry ring/recovery bounds PASS");
    return 0;
}
