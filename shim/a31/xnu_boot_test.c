#include <stddef.h>
#include <stdint.h>

static uint64_t root[2048] __attribute__((aligned(16384)));
static uint64_t l2[2048] __attribute__((aligned(16384)));
static uint32_t before[0x800 / 4];
extern void a31_boot_test_fault(void);
uint64_t a31_boot_test_prepare(void);
void a31_boot_test_verify(uint64_t result);

uint64_t a31_boot_test_prepare(void)
{
    volatile uint32_t *log = (void *)0x49000000;
    log[0] = BOOT_BAD == 6 ? 0 : 0x43474244;
    log[1] = log[2] = 0;
    volatile uint32_t *sram = (void *)0x49100000;
    for (unsigned i = 0; i < 0x800 / 4; i++) sram[i] = 0xa5a5a5a5;
    sram[0] = BOOT_BAD == 1 ? 0 : 0x43474244;
    sram[10] = BOOT_BAD == 2 ? 0x400 : 0x800;
    sram[11] = BOOT_BAD == 3 ? 65 : BOOT_BAD == 4 ? 0x7c0 : 64;
    sram[12] = BOOT_BAD == 5 ? 0x400 : 0x440;
    for (unsigned i = 0; i < 0x800 / 4; i++) before[i] = sram[i];
    for (unsigned i = 0; i < 2048; i++) {
        uint64_t physical = (uint64_t)i << 25;
        uint64_t flags = (1ULL << 10) | 1;
        if (physical >= 0x40000000 && physical < 0x60000000) flags |= 3ULL << 8;
        else flags |= (1ULL << 2) | (3ULL << 53);
        l2[i] = physical | flags;
    }
    root[0] = (uintptr_t)l2 | 3;
    return (uintptr_t)root;
}
static void uart(char character)
{
    *(volatile uint32_t *)0x09000000 = (uint8_t)character;
}
static void text(const char *message)
{
    while (*message) uart(*message++);
}
static __attribute__((noreturn)) void exit_test(int success)
{
    uint64_t result[] = {0x20026, success ? 0 : 1};
    register uint64_t x0 __asm__("x0") = 0x20;
    register uint64_t x1 __asm__("x1") = (uintptr_t)result;
    __asm__ volatile("hlt #0xf000" : "+r"(x0), "+r"(x1) :: "memory");
    for (;;) __asm__ volatile("wfe");
}
static uint64_t value(const char *name, size_t size)
{
    const char *data = (const void *)(0x49000000 + 12);
    for (size_t i = 0; i < size; i++) {
        size_t n = 0;
        while (name[n] && i + n < size && data[i + n] == name[n]) n++;
        if (name[n] || i + n + 18 > size || data[i + n] != '0' || data[i + n + 1] != 'x') continue;
        uint64_t result = 0;
        for (size_t j = 0; j < 16; j++) {
            char c = data[i + n + 2 + j];
            unsigned digit = c >= '0' && c <= '9' ? (unsigned)(c - '0') :
                             c >= 'a' && c <= 'f' ? (unsigned)(c - 'a' + 10) : 16;
            if (digit == 16) return UINT64_MAX;
            result = result << 4 | digit;
        }
        return result;
    }
    return UINT64_MAX;
}
void a31_boot_test_verify(uint64_t result)
{
    int reject = BOOT_BAD >= 1 && BOOT_BAD <= 5;
    if (result != (uint64_t)reject) { text("FAIL recovery acceptance\n"); exit_test(0); }
    if (!reject) {
        before[(64 + 0x3ec) / 4] = 0;
        before[(64 + 0x3f4) / 4] = 0x12345678;
        before[(64 + 0x3f8) / 4] = 0x12345674;
    }
    volatile uint32_t *sram = (void *)0x49100000;
    for (unsigned i = 0; i < 0x800 / 4; i++)
        if (sram[i] != before[i]) { text("FAIL unrelated SRAM word\n"); exit_test(0); }
    uint64_t sctlr;
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    if (sctlr & 0x1005) { text("FAIL MMU/cache shutdown\n"); exit_test(0); }
    volatile uint32_t *header = (void *)0x49000000;
    uint32_t size = header[2];
    if (BOOT_BAD == 6) {
        if (header[0] || header[1] || header[2]) { text("FAIL invalid log changed\n"); exit_test(0); }
    } else {
        if (size > 0x3fff4 || value("XNU_FAULT_ESR=", size) != 0x2000000 ||
            value("XNU_FAULT_ELR=", size) != (uintptr_t)a31_boot_test_fault ||
            value("XNU_FAULT_SLOT=", size) != 4 || value("XNU_FAULT_SP=", size) != 0 ||
            ((value("XNU_FAULT_SCTLR=", size) & 1) != BOOT_MMU)) {
            text("FAIL fault fields\n"); exit_test(0);
        }
        const char *data = (const void *)(0x49000000 + 12);
        for (uint32_t i = 0; i < size; i++) uart(data[i]);
    }
    text("A31 BOOT FAULT TEST PASS\n");
    exit_test(1);
}
