#include "support.h"

static uint32_t be32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | p[3];
}
static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
static int prefix_equal(const char *a, const char *prefix)
{
    while (*prefix) if (*a++ != *prefix++) return 0;
    return 1;
}
static int terminated(const uint8_t *p, uint32_t length, uint32_t *size)
{
    for (uint32_t i = 0; i < length; i++) if (!p[i]) {
        *size = i + 1;
        return 1;
    }
    return 0;
}

/* Every traversal uses the same bounded token decoder. */
static int token(const struct dt_view *dt, uint32_t *cursor, uint32_t *kind,
                 const char **name, struct dt_property *value)
{
    uint32_t p = *cursor, end = dt->structure + dt->structure_size, length;
    if (p < dt->structure || p > end || end - p < 4) return 0;
    *kind = be32(dt->data + p);
    p += 4;
    *name = NULL;
    value->data = NULL;
    value->size = 0;
    if (*kind == 1) {
        if (!terminated(dt->data + p, end - p, &length)) return 0;
        *name = (const char *)(dt->data + p);
        if (length > end - p || end - p - length < ((-length) & 3)) return 0;
        p += (length + 3) & ~3U;
    } else if (*kind == 3) {
        if (end - p < 8) return 0;
        length = be32(dt->data + p);
        uint32_t offset = be32(dt->data + p + 4), name_size;
        p += 8;
        if (offset >= dt->strings_size ||
            !terminated(dt->data + dt->strings + offset,
                        dt->strings_size - offset, &name_size) ||
            length > end - p || end - p - length < ((-length) & 3)) return 0;
        *name = (const char *)(dt->data + dt->strings + offset);
        value->data = dt->data + p;
        value->size = length;
        p += (length + 3) & ~3U;
    } else if (*kind != 2 && *kind != 4 && *kind != 9) return 0;
    *cursor = p;
    return 1;
}

int dt_open(struct dt_view *dt, const void *memory, size_t available)
{
    const uint8_t *data = memory;
    if (!data || available < 40 || be32(data) != 0xd00dfeed) return 0;
    dt->data = data;
    dt->size = be32(data + 4);
    dt->structure = be32(data + 8);
    dt->strings = be32(data + 12);
    dt->strings_size = be32(data + 32);
    dt->structure_size = be32(data + 36);
    if (dt->size > available || dt->size > 0x200000 || dt->size < 40 ||
        be32(data + 20) != 17 || be32(data + 24) > 17 ||
        dt->structure < 40 || (dt->structure & 3) || dt->strings < 40 ||
        dt->structure > dt->size || dt->strings > dt->size ||
        dt->structure_size > dt->size - dt->structure ||
        dt->strings_size > dt->size - dt->strings) return 0;
    uint32_t p = dt->structure, kind, roots = 0;
    int depth = 0, seen_child = 0;
    const char *name;
    struct dt_property value;
    while (token(dt, &p, &kind, &name, &value)) {
        if (kind == 1) {
            if (!depth && (roots++ || *name)) return 0;
            if (++depth > 64) return 0;
            seen_child = 0;
        } else if (kind == 2) {
            if (!depth--) return 0;
            seen_child = 1;
        } else if (kind == 3) {
            if (!depth || seen_child) return 0;
        } else if (kind == 9) return depth == 0 && roots == 1;
    }
    return 0;
}

int dt_property(const struct dt_view *dt, uint32_t node, const char *wanted,
                struct dt_property *value)
{
    uint32_t p = node, kind;
    const char *name;
    struct dt_property item;
    if (!token(dt, &p, &kind, &name, &item) || kind != 1) return 0;
    while (token(dt, &p, &kind, &name, &item)) {
        if (kind == 3 && equal(name, wanted)) { *value = item; return 1; }
        if (kind != 3 && kind != 4) break;
    }
    return 0;
}
int dt_string(const struct dt_property *property, const char *wanted)
{
    uint32_t i = 0, length;
    while (i < property->size &&
           terminated(property->data + i, property->size - i, &length)) {
        if (equal((const char *)property->data + i, wanted)) return 1;
        i += length;
    }
    return 0;
}
int dt_compatible(const struct dt_view *dt, const char *wanted, uint32_t *node)
{
    uint32_t p = dt->structure, kind;
    const char *name;
    struct dt_property value;
    while (p < dt->structure + dt->structure_size) {
        uint32_t start = p;
        if (!token(dt, &p, &kind, &name, &value)) break;
        if (kind == 1 && dt_property(dt, start, "compatible", &value) &&
            dt_string(&value, wanted)) { *node = start; return 1; }
        if (kind == 9) break;
    }
    return 0;
}
int dt_reserved(const struct dt_view *dt, const char *prefix, uint32_t *node)
{
    uint32_t p = dt->structure, kind;
    int depth = 0, reserved = 0;
    const char *name;
    struct dt_property value;
    while (p < dt->structure + dt->structure_size) {
        uint32_t start = p;
        if (!token(dt, &p, &kind, &name, &value)) break;
        if (kind == 1) {
            ++depth;
            if (depth == 2) reserved = equal(name, "reserved-memory");
            if (depth == 3 && reserved && prefix_equal(name, prefix)) {
                *node = start;
                return 1;
            }
        } else if (kind == 2) { if (depth == 2) reserved = 0; depth--; }
        else if (kind == 9) break;
    }
    return 0;
}
int dt_reg(const struct dt_view *dt, uint32_t node, unsigned index,
           uint64_t *base, uint64_t *size)
{
    struct dt_property reg;
    /* A31 and QEMU virt both use two address and two size cells. */
    if (index > 63 || !dt_property(dt, node, "reg", &reg) ||
        reg.size % 16 || reg.size / 16 <= index) return 0;
    const uint8_t *p = reg.data + index * 16;
    *base = (uint64_t)be32(p) << 32 | be32(p + 4);
    *size = (uint64_t)be32(p + 8) << 32 | be32(p + 12);
    return *size && *base <= UINT64_MAX - *size;
}

int sec_log_bind(struct sec_log *log, void *memory, size_t size)
{
    if (!memory || ((uintptr_t)memory & 3) || size < 16 || size > 0x200000 ||
        (size & 3)) return 0;
    log->data = memory;
    log->capacity = (uint32_t)size - 12;
    log->head = (volatile uint32_t *)(log->data + log->capacity);
    log->position = log->head + 1;
    log->magic = log->head + 2;
    if (*log->magic != 0x4d474f4c || *log->position >= log->capacity || *log->head > 1) {
        *log->head = 0;
        *log->position = 0;
        *log->magic = 0x4d474f4c;
    }
    return 1;
}
void sec_log_putc(struct sec_log *log, char c)
{
    uint32_t p = *log->position;
    log->data[p++] = (uint8_t)c;
    if (p == log->capacity) { p = 0; *log->head = 1; }
    *log->position = p;
}
