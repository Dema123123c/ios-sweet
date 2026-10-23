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
int dt_root_child(const struct dt_view *dt, const char *wanted, uint32_t *node)
{
    uint32_t p = dt->structure, kind, found = 0, match = 0;
    int depth = 0;
    const char *name;
    struct dt_property value;
    while (p < dt->structure + dt->structure_size) {
        uint32_t start = p;
        if (!token(dt, &p, &kind, &name, &value)) return 0;
        if (kind == 1) {
            if (++depth == 2 && equal(name, wanted)) { found++; match = start; }
        } else if (kind == 2) depth--;
        else if (kind == 9) break;
    }
    if (found != 1) return 0;
    *node = match;
    return 1;
}

static uint64_t be64(const uint8_t *p) { return (uint64_t)be32(p) << 32 | be32(p + 4); }
static int region_overlap(uint64_t a, uint64_t n, uint64_t b, uint64_t m)
{
    return n && m && a < b + m && b < a + n;
}
int dt_ram_available(const struct dt_view *dt, uint64_t base, uint64_t size)
{
    if (!size || base > UINT64_MAX - size) return 0;
    uint32_t p = dt->structure, kind;
    int depth = 0, reserved = 0, found = 0;
    const char *name;
    struct dt_property property;
    if (!dt_property(dt, p, "#address-cells", &property) || property.size != 4 ||
        be32(property.data) != 2 || !dt_property(dt, p, "#size-cells", &property) ||
        property.size != 4 || be32(property.data) != 2) return 0;
    while (p < dt->structure + dt->structure_size) {
        uint32_t start = p;
        if (!token(dt, &p, &kind, &name, &property)) return 0;
        if (kind == 1) {
            ++depth;
            if (depth == 2) reserved = equal(name, "reserved-memory");
            if (depth == 2 && reserved) {
                if (!dt_property(dt, start, "#address-cells", &property) || property.size != 4 ||
                    be32(property.data) != 2 || !dt_property(dt, start, "#size-cells", &property) ||
                    property.size != 4 || be32(property.data) != 2) return 0;
            }
            if (reserved && depth > 3) return 0;
            int memory = depth == 2 && dt_property(dt, start, "device_type", &property) &&
                         dt_string(&property, "memory");
            if (memory || (reserved && depth == 3)) {
                if (!dt_property(dt, start, "reg", &property)) {
                    /* Size-only nodes request future OS allocation; these drivers do not run here. */
                    if (memory || !dt_property(dt, start, "size", &property) ||
                        property.size != 8 || !be64(property.data)) return 0;
                    if (dt_property(dt, start, "alloc-ranges", &property)) {
                        if (!property.size || property.size % 16) return 0;
                        for (uint32_t i = 0; i < property.size; i += 16)
                            if (be64(property.data + i) > UINT64_MAX - be64(property.data + i + 8)) return 0;
                    }
                    continue;
                }
                if (!property.size || property.size % 16) return 0;
                for (uint32_t i = 0; i < property.size; i += 16) {
                    uint64_t address = be64(property.data + i), length = be64(property.data + i + 8);
                    if (address > UINT64_MAX - length) return 0;
                    if (memory && base >= address && size <= length && base - address <= length - size)
                        found = 1;
                    if (!memory && region_overlap(base, size, address, length)) return 0;
                }
            }
        } else if (kind == 2) { if (depth == 2) reserved = 0; depth--; }
        else if (kind == 9) break;
    }
    p = be32(dt->data + 16);
    if (p < 40 || (p & 7)) return 0;
    while (p <= dt->size && dt->size - p >= 16) {
        uint64_t address = be64(dt->data + p), length = be64(dt->data + p + 8);
        if (!address && !length) return found;
        if (address > UINT64_MAX - length || region_overlap(base, size, address, length)) return 0;
        p += 16;
    }
    return 0;
}

int samsung_recovery_bind(struct samsung_recovery *context, void *memory, size_t size)
{
    if (!memory || ((uintptr_t)memory & 3) || size != 0x800) return 0;
    volatile uint32_t *header = memory;
    uint32_t linux_offset = header[11], console_offset = header[12];
    if (header[0] != 0x43474244 || header[10] != size ||
        linux_offset < 64 || (linux_offset & 63) ||
        linux_offset > size - 0x3fc ||
        console_offset < linux_offset + 0x3fc || console_offset > size) return 0;
    /* Offsets independently verified in the installed recovery's sec_reboot(). */
    volatile uint8_t *reason = (volatile uint8_t *)memory + linux_offset;
    context->upload = (volatile uint32_t *)(reason + 0x3ec);
    context->power_reset = (volatile uint32_t *)(reason + 0x3f4);
    context->reason = (volatile uint32_t *)(reason + 0x3f8);
    return 1;
}

void samsung_recovery_request(struct samsung_recovery *context)
{
    *context->upload = 0;
    *context->power_reset = 0x12345678;
    *context->reason = 0x12345674;
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

int ramoops_log_bind(struct ramoops_log *log, void *memory, size_t size)
{
    if (!memory || ((uintptr_t)memory & 3) || size < 16 || size > 0x40000 ||
        (size & 3)) return 0;
    log->signature = memory;
    log->start = log->signature + 1;
    log->size = log->signature + 2;
    log->data = (volatile uint8_t *)(log->signature + 3);
    log->capacity = (uint32_t)size - 12;
    uint32_t start = *log->start, used = *log->size;
    if (*log->signature != 0x43474244 || start >= log->capacity ||
        used > log->capacity || (used < log->capacity && start != used)) {
        *log->start = 0;
        *log->size = 0;
        *log->signature = 0x43474244;
    }
    return 1;
}

void ramoops_log_putc(struct ramoops_log *log, char c)
{
    uint32_t start = *log->start;
    log->data[start++] = (uint8_t)c;
    if (start == log->capacity) start = 0;
    *log->start = start;
    if (*log->size < log->capacity) ++*log->size;
}
