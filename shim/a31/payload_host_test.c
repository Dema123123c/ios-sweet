#include "payload.h"
#include "support.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *size)
{
    FILE *file = fopen(path, "rb");
    assert(file && !fseek(file, 0, SEEK_END));
    long length = ftell(file);
    assert(length > 0 && length < 32 * 1024 * 1024);
    rewind(file);
    uint8_t *data = malloc((size_t)length);
    assert(data && fread(data, 1, (size_t)length, file) == (size_t)length);
    fclose(file); *size = (size_t)length; return data;
}
static void put64(uint8_t *data, uint64_t value)
{
    for (unsigned i = 0; i < 8; i++) data[i] = (uint8_t)(value >> (8 * i));
}
struct writer { uint8_t *data; uint64_t base, size; unsigned fail; };
static int write_memory(void *context, uint64_t address, const void *data, size_t size)
{
    struct writer *writer = context;
    if (writer->fail) return 0;
    assert(address >= writer->base && size <= writer->size &&
           address - writer->base <= writer->size - size);
    if (data) memcpy(writer->data + address - writer->base, data, size);
    else memset(writer->data + address - writer->base, 0, size);
    return 1;
}
int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    uint64_t base = strtoull(argv[2], NULL, 0), memory_size = strtoull(argv[3], NULL, 0);
    size_t size;
    uint8_t *data = read_file(argv[1], &size), *bad = malloc(size);
    assert(bad);
    if (argc == 5) {
        size_t fdt_size;
        uint8_t *fdt_data = read_file(argv[4], &fdt_size);
        struct dt_view dt;
        assert(dt_open(&dt, fdt_data, fdt_size));
        assert(dt_ram_available(&dt, base, memory_size));
        free(fdt_data);
    }
    struct a31_payload_plan plan;
    const char *error = a31_payload_validate(data, size, 0x47c80000, base, memory_size, &plan);
    if (error) { fprintf(stderr, "Payload rejected: %s\n", error); return 1; }
    for (size_t n = 0; n < 0x2a8; n++)
        assert(a31_payload_validate(data, n, 0x47c80000, base, memory_size, &plan));
    const unsigned offsets[] = {0, 8, 12, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40,
                                0x2a8, 0x2b0, 0x2b8, 0x2c0};
    for (unsigned i = 0; i < sizeof(offsets) / sizeof(offsets[0]); i++) {
        memcpy(bad, data, size);
        put64(bad + offsets[i], UINT64_MAX);
        assert(a31_payload_validate(bad, size, 0x47c80000, base, memory_size, &plan));
    }
    memcpy(bad, data, size); memset(bad + 0x48, 'x', A31_BOOT_LINE_LENGTH);
    assert(a31_payload_validate(bad, size, 0x47c80000, base, memory_size, &plan));
    assert(a31_payload_validate(data, size, base, base, memory_size, &plan));
    assert(a31_payload_validate(data, size, UINT64_MAX - 7, base, memory_size, &plan));
    assert(!a31_payload_validate(data, size, 0x47c80000, base, memory_size, &plan));
    uint64_t adt_offset = plan.adt_offset;
    memcpy(bad, data, size); put64(bad + adt_offset, UINT64_MAX);
    assert(a31_payload_validate(bad, size, 0x47c80000, base, memory_size, &plan));
    memcpy(bad, data, size);
    for (size_t i = (size_t)adt_offset; i + 44 <= size; i++) {
        if (!memcmp(bad + i, "dram-base\0", 10)) {
            put64(bad + i + 36, base + 0x4000);
            break;
        }
    }
    assert(a31_payload_validate(bad, size, 0x47c80000, base, memory_size, &plan));
    assert(!a31_payload_validate(data, size, 0x47c80000, base, memory_size, &plan));
    assert(plan.top - base <= 64 * 1024 * 1024);
    struct writer writer = {malloc((size_t)(plan.top - base)), base, plan.top - base, 0};
    assert(writer.data); memset(writer.data, 0xa5, (size_t)writer.size);
    assert(!a31_payload_prepare(&plan, write_memory, &writer));
    for (uint32_t i = 0; i < plan.count; i++) {
        const struct a31_payload_segment *s = &plan.segments[i];
        uint8_t *target = writer.data + s->destination - base;
        assert(!memcmp(target, data + s->offset, (size_t)s->file_size));
        for (uint64_t j = s->file_size; j < s->memory_size; j++) assert(!target[j]);
    }
    const struct a31_boot_args *args = (const void *)(writer.data + plan.args_address - base);
    assert(args->revision == 2 && args->version == 2 && !args->video.base && !args->video.display);
    assert(args->physical_base == base && args->memory_size == memory_size);
    assert(args->device_tree == plan.virtual_base + plan.adt_address - base);
    assert(args->top == plan.top && !memcmp(args->command_line, data + 0x48, A31_BOOT_LINE_LENGTH));
    assert(!memcmp(writer.data + plan.adt_address - base, data + plan.adt_offset, (size_t)plan.adt_size));
    writer.fail = 1;
    assert(a31_payload_prepare(&plan, write_memory, &writer));
    printf("PAYLOAD validation, malformed bounds, copy/BSS, ADT and boot args PASS; segments=%u; entry=0x%llx\n",
           plan.count, (unsigned long long)plan.entry);
    free(writer.data); free(data); free(bad);
    return 0;
}
