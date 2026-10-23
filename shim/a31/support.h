#pragma once
#include <stddef.h>
#include <stdint.h>

struct dt_view {
    const uint8_t *data;
    uint32_t size, structure, structure_size, strings, strings_size;
};
struct dt_property { const uint8_t *data; uint32_t size; };
int dt_open(struct dt_view *dt, const void *data, size_t available);
int dt_property(const struct dt_view *dt, uint32_t node, const char *name,
                struct dt_property *value);
int dt_compatible(const struct dt_view *dt, const char *compatible, uint32_t *node);
int dt_reserved(const struct dt_view *dt, const char *prefix, uint32_t *node);
int dt_reg(const struct dt_view *dt, uint32_t node, unsigned index,
           uint64_t *base, uint64_t *size);
int dt_string(const struct dt_property *property, const char *value);
int dt_root_child(const struct dt_view *dt, const char *name, uint32_t *node);

struct samsung_recovery {
    volatile uint32_t *upload, *power_reset, *reason;
};
int samsung_recovery_bind(struct samsung_recovery *context, void *memory, size_t size);
void samsung_recovery_request(struct samsung_recovery *context);

struct sec_log {
    volatile uint8_t *data;
    volatile uint32_t *head, *position, *magic;
    uint32_t capacity;
};
int sec_log_bind(struct sec_log *log, void *memory, size_t size);
void sec_log_putc(struct sec_log *log, char c);

struct ramoops_log {
    volatile uint32_t *signature, *start, *size;
    volatile uint8_t *data;
    uint32_t capacity;
};
int ramoops_log_bind(struct ramoops_log *log, void *memory, size_t size);
void ramoops_log_putc(struct ramoops_log *log, char c);
