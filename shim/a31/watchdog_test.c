#include "watchdog.h"
#include <assert.h>
#include <stdio.h>

struct state { uint32_t mode, length; unsigned count, bad; };
static uint32_t read_reg(void *context, unsigned offset)
{
    struct state *s = context;
    assert(offset == 0 || offset == 4);
    return offset ? s->length : s->mode;
}
static void write_reg(void *context, unsigned offset, uint32_t value)
{
    struct state *s = context;
    const unsigned offsets[] = {4, 8, 0, 8};
    assert(s->count < 4 && offset == offsets[s->count++]);
    if (!offset) {
        assert(value == 0x22000015);
        if (s->bad != 2) s->mode = value & 0xff;
    } else if (offset == 4) {
        assert((value & 31) == 8);
        if (s->bad != 1) s->length = value & 0xffe0;
    } else assert(value == 0x1971);
}
int main(void)
{
    for (unsigned seconds = 0; seconds <= 9; seconds++) {
        struct state s = {.mode = 0x5c};
        int result = a31_watchdog_arm(&s, read_reg, write_reg, seconds);
        assert(result == (seconds >= 1 && seconds <= 8));
        assert(s.count == (result ? 4U : 0U));
        if (result) assert(s.length == seconds << 11 && s.mode == 0x15);
    }
    for (unsigned mode = 0; mode < 256; mode++) {
        struct state s = {.mode = mode};
        assert(a31_watchdog_arm(&s, read_reg, write_reg, 4) == (mode == 0x5c));
        if (mode != 0x5c) assert(!s.count);
    }
    for (unsigned bad = 1; bad <= 2; bad++) {
        struct state s = {.mode = 0x5c, .bad = bad};
        assert(!a31_watchdog_arm(&s, read_reg, write_reg, 4));
        assert(s.count == (bad == 1 ? 1U : 3U));
    }
    puts("Watchdog timeout bounds, ordered register writes and failed readback PASS");
}
