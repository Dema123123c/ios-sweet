#ifndef A31_XNU_ENTRY_IO_H
#define A31_XNU_ENTRY_IO_H
#include <stddef.h>
#include <stdint.h>

/* Mirrored into the XNU patch; host tests require byte-identical source. */
static inline int
a31_xnu_ring_putc(void *memory, size_t bytes, char character)
{
    if (!memory || ((uintptr_t)memory & 3) || bytes != 0x40000) return 0;
    volatile uint32_t *header = memory;
    const uint32_t capacity = 0x40000 - 12;
    uint32_t start = header[1], used = header[2];
    if (header[0] != 0x43474244 || start >= capacity || used > capacity ||
        (used < capacity && start != used)) return 0;
    volatile uint8_t *data = (volatile uint8_t *)memory + 12;
    data[start++] = (uint8_t)character;
    if (start == capacity) start = 0;
    header[1] = start;
    if (used < capacity) header[2] = used + 1;
    return 1;
}

static inline int
a31_xnu_request_recovery(void *memory, size_t bytes)
{
    if (!memory || ((uintptr_t)memory & 3) || bytes != 0x800) return 0;
    volatile uint32_t *header = memory;
    uint32_t linux_offset = header[11], console_offset = header[12];
    if (header[0] != 0x43474244 || header[10] != bytes ||
        linux_offset < 64 || (linux_offset & 63) ||
        linux_offset > bytes - 0x3fc ||
        console_offset < linux_offset + 0x3fc || console_offset > bytes) return 0;
    volatile uint32_t *state = (volatile uint32_t *)((volatile uint8_t *)memory + linux_offset);
    state[0x3ec / 4] = 0;
    state[0x3f4 / 4] = 0x12345678;
    state[0x3f8 / 4] = 0x12345674;
    return 1;
}
#endif
