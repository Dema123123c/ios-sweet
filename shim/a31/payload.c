#include "payload.h"

#define HEADER 0x2a8U
#define PAGE 0x4000ULL
static uint32_t u32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t u64(const uint8_t *p) { return u32(p) | (uint64_t)u32(p + 4) << 32; }
static int within(uint64_t start, uint64_t size, uint64_t limit)
{
    return size <= limit && start <= limit - size;
}
static int overlaps(uint64_t a, uint64_t n, uint64_t b, uint64_t m)
{
    return n && m && a < b + m && b < a + n;
}
static int name_is(const uint8_t *p, size_t n, const char *wanted)
{
    size_t i = 0;
    while (i < n && wanted[i] && p[i] == (uint8_t)wanted[i]) i++;
    return i < n && !p[i] && !wanted[i];
}

struct adt_check {
    const uint8_t *data;
    size_t size, cursor;
    unsigned nodes, chosen;
    uint64_t base, memory_size;
};
static int adt_node(struct adt_check *check, unsigned depth)
{
    if (depth > 16 || ++check->nodes > 256 || !within(check->cursor, 8, check->size)) return 0;
    uint32_t properties = u32(check->data + check->cursor);
    uint32_t children = u32(check->data + check->cursor + 4);
    check->cursor += 8;
    if (properties > 128 || children > 128) return 0;
    const uint8_t *name = NULL;
    uint32_t name_size = 0;
    unsigned dram_fields = 0;
    uint64_t base = 0, size = 0;
    for (uint32_t i = 0; i < properties; i++) {
        if (!within(check->cursor, 36, check->size)) return 0;
        const uint8_t *property = check->data + check->cursor;
        unsigned terminated = 0;
        for (unsigned j = 0; j < 32; j++) if (!property[j]) terminated = 1;
        if (!terminated) return 0;
        uint32_t length = u32(property + 32) & 0x7fffffff;
        uint64_t padded = ((uint64_t)length + 3) & ~3ULL;
        check->cursor += 36;
        if (!within(check->cursor, padded, check->size)) return 0;
        const uint8_t *value = check->data + check->cursor;
        if (name_is(property, 32, "name")) {
            if (name || !length || length > 64 || value[length - 1]) return 0;
            name = value; name_size = length;
        } else if (name_is(property, 32, "dram-base")) {
            if (length != 8 || (dram_fields & 1)) return 0;
            base = u64(value); dram_fields |= 1;
        } else if (name_is(property, 32, "dram-size")) {
            if (length != 8 || (dram_fields & 2)) return 0;
            size = u64(value); dram_fields |= 2;
        }
        check->cursor += (size_t)padded;
    }
    if (!name) return 0;
    if (depth == 1 && name_is(name, name_size, "chosen")) {
        if (++check->chosen != 1 || dram_fields != 3 ||
            base != check->base || size != check->memory_size) return 0;
    }
    for (uint32_t i = 0; i < children; i++) if (!adt_node(check, depth + 1)) return 0;
    return 1;
}

const char *a31_payload_validate(const void *memory, size_t size, uint64_t source_address,
                               uint64_t expected_base, uint64_t expected_size,
                               struct a31_payload_plan *plan)
{
    const uint8_t *data = memory;
    static const uint8_t magic[8] = {'S','W','E','E','T','X','N','U'};
    if (!data || !plan || size < HEADER || size > 24 * 1024 * 1024 || (source_address & 7) ||
        !within(source_address, size, UINT64_MAX)) return "payload bounds";
    if ((expected_base & 0x1ffffff) || (expected_size & (PAGE - 1)) ||
        expected_size < 0x4000000 || !within(expected_base, expected_size, 1ULL << 40))
        return "RAM policy";
    for (unsigned i = 0; i < 8; i++) if (data[i] != magic[i]) return "payload magic";
    uint32_t count = u32(data + 12);
    if (u32(data + 8) != 1 || !count || count > A31_PAYLOAD_MAX_SEGMENTS ||
        !within(HEADER, 32ULL * count, size)) return "segment table";
    uint64_t virtual_base = u64(data + 0x10), entry = u64(data + 0x18);
    uint64_t adt_offset = u64(data + 0x20), adt_size = u64(data + 0x28);
    uint64_t kernel_end = u64(data + 0x30);
    if (u64(data + 0x38) != expected_base || u64(data + 0x40) != expected_size ||
        overlaps(source_address, size, expected_base, expected_size)) return "RAM policy mismatch";
    if (virtual_base < 0xffff000000000000ULL || (virtual_base & 0x1ffffff) ||
        !within(virtual_base, expected_size, UINT64_MAX)) return "virtual base";
    if ((adt_offset & 7) || adt_offset < HEADER + 32ULL * count ||
        adt_size < 8 || adt_size > 0x100000 || !within(adt_offset, adt_size, size))
        return "ADT bounds";
    unsigned command_terminated = 0;
    for (unsigned i = 0; i < A31_BOOT_LINE_LENGTH; i++)
        if (!data[0x48 + i]) command_terminated = 1;
    if (!command_terminated) return "command line";
    uint64_t highest = 0;
    unsigned entry_found = 0;
    for (uint32_t i = 0; i < count; i++) {
        const uint8_t *raw = data + HEADER + 32 * i;
        uint64_t va = u64(raw), memory_size = u64(raw + 8);
        uint64_t offset = u64(raw + 16), file_size = u64(raw + 24);
        if (va < virtual_base || (va & (PAGE - 1)) || !memory_size ||
            !within(va - virtual_base, memory_size, expected_size) || file_size > memory_size)
            return "segment destination";
        if ((offset & 7) || offset < HEADER + 32ULL * count || !within(offset, file_size, size) ||
            overlaps(offset, file_size, adt_offset, adt_size)) return "segment source";
        uint64_t destination = expected_base + va - virtual_base;
        for (uint32_t j = 0; j < i; j++) {
            const struct a31_payload_segment *other = &plan->segments[j];
            if (overlaps(destination, memory_size, other->destination, other->memory_size) ||
                overlaps(offset, file_size, other->offset, other->file_size))
                return "segment overlap";
        }
        plan->segments[i] = (struct a31_payload_segment){destination, memory_size, offset, file_size};
        uint64_t end = va - virtual_base + memory_size;
        if (end > highest) highest = end;
        if (!(entry & 3) && entry >= va && entry - va < file_size) entry_found = 1;
    }
    if (!entry_found) return "entry outside file-backed segments";
    highest = (highest + PAGE - 1) & ~(PAGE - 1);
    if (kernel_end < virtual_base || kernel_end - virtual_base != highest) return "kernel end";
    uint64_t args_offset = (highest + adt_size + PAGE - 1) & ~(PAGE - 1);
    if (!within(args_offset, PAGE, expected_size)) return "boot args outside RAM";
    struct adt_check check = {data + adt_offset, (size_t)adt_size, 0, 0, 0,
                             expected_base, expected_size};
    if (!adt_node(&check, 0) || check.cursor != adt_size || check.chosen != 1)
        return "ADT structure or RAM mismatch";
    plan->data = data; plan->size = size;
    plan->physical_base = expected_base; plan->memory_size = expected_size;
    plan->virtual_base = virtual_base; plan->entry = expected_base + entry - virtual_base;
    plan->adt_offset = adt_offset; plan->adt_size = adt_size;
    plan->adt_address = expected_base + highest; plan->args_address = expected_base + args_offset;
    plan->top = plan->args_address + PAGE; plan->count = count;
    return NULL;
}

const char *a31_payload_prepare(const struct a31_payload_plan *plan,
                              a31_payload_writer write, void *context)
{
    for (uint32_t i = 0; i < plan->count; i++) {
        const struct a31_payload_segment *segment = &plan->segments[i];
        if (!write(context, segment->destination, plan->data + segment->offset, segment->file_size) ||
            !write(context, segment->destination + segment->file_size, NULL,
                   segment->memory_size - segment->file_size)) return "segment write/readback";
    }
    if (!write(context, plan->adt_address, plan->data + plan->adt_offset, plan->adt_size) ||
        !write(context, plan->args_address, NULL, PAGE)) return "ADT or args write/readback";
    struct a31_boot_args args;
    for (size_t i = 0; i < sizeof(args); i++) ((uint8_t *)&args)[i] = 0;
    args.revision = 2; args.version = 2;
    args.virtual_base = plan->virtual_base; args.physical_base = plan->physical_base;
    args.memory_size = plan->memory_size; args.top = plan->top;
    args.device_tree = plan->virtual_base + plan->adt_address - plan->physical_base;
    args.device_tree_size = (uint32_t)plan->adt_size;
    for (unsigned i = 0; i < A31_BOOT_LINE_LENGTH; i++) args.command_line[i] = plan->data[0x48 + i];
    args.actual_memory_size = plan->memory_size;
    if (!write(context, plan->args_address, &args, sizeof(args))) return "boot args write/readback";
    return NULL;
}
