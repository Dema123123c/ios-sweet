#include "support.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void write_be32(uint8_t *p, uint32_t n)
{
    p[0] = n >> 24; p[1] = n >> 16; p[2] = n >> 8; p[3] = n;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb");
    assert(file);
    assert(fseek(file, 0, SEEK_END) == 0);
    long length = ftell(file);
    assert(length > 40);
    rewind(file);
    uint8_t *data = malloc((size_t)length), *bad = malloc((size_t)length);
    assert(data && bad);
    assert(fread(data, 1, (size_t)length, file) == (size_t)length);
    fclose(file);
    struct dt_view dt;
    uint32_t node;
    uint64_t base, size;
    assert(dt_open(&dt, data, (size_t)length));
    assert(dt_compatible(&dt, "mediatek,MT6768", &node) && node == dt.structure);
    assert(dt_compatible(&dt, "arm,gic-v3", &node));
    assert(dt_reg(&dt, node, 0, &base, &size) && base == 0x0c000000 && size == 0x40000);
    assert(dt_reg(&dt, node, 1, &base, &size) && base == 0x0c040000 && size == 0x200000);
    assert(!dt_reg(&dt, node, 2, &base, &size));
    assert(!dt_compatible(&dt, "arm,not-a-device", &node));
    assert(dt_root_child(&dt, "reserved-memory", &node));
    assert(!dt_root_child(&dt, "firmware", &node));
    assert(!dt_root_child(&dt, "absent", &node));
    assert(dt_reserved(&dt, "firmware", &node));
    assert(!dt_reserved(&dt, "sec-log", &node));
    assert(!dt_open(&dt, data, (size_t)length - 1));
    for (unsigned field = 0; field < 10; field++) {
        memcpy(bad, data, (size_t)length);
        write_be32(bad + field * 4, UINT32_MAX);
        if (field == 4 || field == 7) continue;
        assert(!dt_open(&dt, bad, (size_t)length));
    }
    memcpy(bad, data, (size_t)length);
    assert(dt_open(&dt, data, (size_t)length));
    write_be32(bad + dt.structure, 2);
    assert(!dt_open(&dt, bad, (size_t)length));
    memcpy(bad, data, (size_t)length);
    write_be32(bad + dt.structure_size + dt.structure - 4, 0xff);
    assert(!dt_open(&dt, bad, (size_t)length));
    free(data); free(bad);

    uint32_t guarded[20];
    for (unsigned i = 0; i < 20; i++) guarded[i] = 0xa5a5a5a5;
    struct sec_log ring;
    assert(sec_log_bind(&ring, guarded + 2, 64));
    assert(ring.capacity == 52 && *ring.position == 0 && *ring.head == 0);
    for (unsigned i = 0; i < 52; i++) sec_log_putc(&ring, (char)i);
    assert(*ring.position == 0 && *ring.head == 1);
    sec_log_putc(&ring, 'X');
    assert(*ring.position == 1 && ring.data[0] == 'X');
    struct sec_log same;
    assert(sec_log_bind(&same, guarded + 2, 64) && *same.position == 1);
    *same.position = UINT32_MAX;
    assert(sec_log_bind(&same, guarded + 2, 64) && *same.position == 0);
    assert(guarded[0] == 0xa5a5a5a5 && guarded[1] == 0xa5a5a5a5 &&
           guarded[18] == 0xa5a5a5a5 && guarded[19] == 0xa5a5a5a5);
    assert(!sec_log_bind(&same, (uint8_t *)guarded + 1, 64));
    assert(!sec_log_bind(&same, guarded, 12));
    for (unsigned i = 0; i < 20; i++) guarded[i] = 0xa5a5a5a5;
    struct ramoops_log prz;
    assert(ramoops_log_bind(&prz, guarded + 2, 64));
    assert(*prz.signature == 0x43474244 && *prz.start == 0 && *prz.size == 0);
    for (unsigned i = 0; i < 52; i++) ramoops_log_putc(&prz, (char)i);
    assert(*prz.start == 0 && *prz.size == 52);
    ramoops_log_putc(&prz, 'X');
    assert(*prz.start == 1 && *prz.size == 52 && prz.data[0] == 'X');
    struct ramoops_log persisted;
    assert(ramoops_log_bind(&persisted, guarded + 2, 64));
    assert(*persisted.start == 1 && *persisted.size == 52);
    *persisted.size = 3;
    assert(ramoops_log_bind(&persisted, guarded + 2, 64));
    assert(*persisted.start == 0 && *persisted.size == 0);
    assert(guarded[0] == 0xa5a5a5a5 && guarded[1] == 0xa5a5a5a5 &&
           guarded[18] == 0xa5a5a5a5 && guarded[19] == 0xa5a5a5a5);
    assert(!ramoops_log_bind(&persisted, (uint8_t *)guarded + 1, 64));
    assert(!ramoops_log_bind(&persisted, guarded, 12));
    assert(!ramoops_log_bind(&persisted, guarded, 0x40004));
    uint32_t reset_guarded[514], original[514];
    for (unsigned i = 0; i < 514; i++) reset_guarded[i] = 0x5a5a5a5a;
    uint32_t *header = reset_guarded + 1;
    header[0] = 0x43474244;
    header[10] = 0x800;
    header[11] = 0x200;
    header[12] = 0x740;
    memcpy(original, reset_guarded, sizeof(original));
    struct samsung_recovery recovery;
    assert(samsung_recovery_bind(&recovery, header, 0x800));
    samsung_recovery_request(&recovery);
    assert(header[(0x200 + 0x3ec) / 4] == 0);
    assert(header[(0x200 + 0x3f4) / 4] == 0x12345678);
    assert(header[(0x200 + 0x3f8) / 4] == 0x12345674);
    for (unsigned i = 0; i < 514; i++) {
        if (i != 1 + (0x200 + 0x3ec) / 4 && i != 1 + (0x200 + 0x3f4) / 4 &&
            i != 1 + (0x200 + 0x3f8) / 4) assert(reset_guarded[i] == original[i]);
    }
    for (unsigned i = 0; i < 4; i++) {
        memcpy(reset_guarded, original, sizeof(original));
        header[(unsigned[]){0, 10, 11, 12}[i]] = 0xffffffff;
        assert(!samsung_recovery_bind(&recovery, header, 0x800));
    }
    memcpy(reset_guarded, original, sizeof(original));
    header[11] = 0x201;
    assert(!samsung_recovery_bind(&recovery, header, 0x800));
    header[11] = 0x200;
    header[12] = 0x5f8;
    assert(!samsung_recovery_bind(&recovery, header, 0x800));
    assert(!samsung_recovery_bind(&recovery, header, 0x7ff));
    assert(!samsung_recovery_bind(&recovery, header, 0x804));
    assert(!samsung_recovery_bind(&recovery, (uint8_t *)header + 1, 0x800));
    puts("FDT bounds/reg, Samsung LOGM, ramoops and recovery SRAM bounds tests PASS");
    return 0;
}
