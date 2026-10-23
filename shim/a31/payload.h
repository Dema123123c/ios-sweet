#pragma once
#include <stddef.h>
#include <stdint.h>

#define A31_PAYLOAD_MAX_SEGMENTS 32
#define A31_BOOT_LINE_LENGTH 608

struct a31_payload_segment { uint64_t destination, memory_size, offset, file_size; };
struct a31_payload_plan {
    const uint8_t *data;
    uint64_t size, physical_base, memory_size, virtual_base;
    uint64_t entry, adt_offset, adt_size, adt_address, args_address, top;
    uint32_t count;
    struct a31_payload_segment segments[A31_PAYLOAD_MAX_SEGMENTS];
};
struct a31_boot_video { uint64_t base, display, row_bytes, width, height, depth; };
struct a31_boot_args {
    uint16_t revision, version;
    uint64_t virtual_base, physical_base, memory_size, top;
    struct a31_boot_video video;
    uint32_t machine_type;
    uint64_t device_tree;
    uint32_t device_tree_size;
    char command_line[A31_BOOT_LINE_LENGTH];
    uint64_t flags, actual_memory_size;
};
_Static_assert(offsetof(struct a31_boot_args, command_line) == 108, "XNU boot args command line");
_Static_assert(sizeof(struct a31_boot_args) == 736, "XNU boot args v2 layout");

const char *a31_payload_validate(const void *data, size_t size, uint64_t source_address,
                               uint64_t expected_base, uint64_t expected_size,
                               struct a31_payload_plan *plan);
typedef int (*a31_payload_writer)(void *context, uint64_t address, const void *data, size_t size);
const char *a31_payload_prepare(const struct a31_payload_plan *plan,
                              a31_payload_writer write, void *context);
