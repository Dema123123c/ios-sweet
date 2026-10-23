#include "support.h"
#include "payload.h"

#define READ(reg) ({ uint64_t v; __asm__ volatile("mrs %0, " #reg : "=r"(v)); v; })
#define WRITE(reg, value) __asm__ volatile("msr " #reg ", %0" :: "r"((uint64_t)(value)) : "memory")
#define BARRIER() __asm__ volatile("dsb sy; isb" ::: "memory")
static uint32_t read32(uintptr_t p) { return *(volatile uint32_t *)p; }
static uint64_t read64(uintptr_t p) { return *(volatile uint64_t *)p; }
static void write32(uintptr_t p, uint32_t v) { *(volatile uint32_t *)p = v; }
#if !DIAG_QEMU
static struct sec_log log_ring;
static struct ramoops_log pstore_ring;
static int log_ready;
static int pstore_ready;
static struct samsung_recovery recovery_context;
static int recovery_ready;
static uint64_t psci(uint64_t function)
{
    register uint64_t x0 __asm__("x0") = function;
    register uint64_t x1 __asm__("x1") = 0;
    register uint64_t x2 __asm__("x2") = 0;
    register uint64_t x3 __asm__("x3") = 0;
    __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3) ::
                     "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11",
                     "x12", "x13", "x14", "x15", "x16", "x17", "memory");
    return x0;
}
#endif
static uint64_t frequency;
static volatile uint32_t timer_irqs, other_irqs;
extern char _head[], _end[];

static void putc(char c)
{
#if DIAG_QEMU
    for (unsigned i = 0; i < 1000000 && (read32(0x09000018) & 0x20); i++) {}
    write32(0x09000000, (uint32_t)(unsigned char)c);
#else
    if (log_ready) sec_log_putc(&log_ring, c);
    if (pstore_ready) ramoops_log_putc(&pstore_ring, c);
#endif
}
static void text(const char *s) { while (*s) putc(*s++); BARRIER(); }
static void hex(uint64_t v)
{
    static const char digits[] = "0123456789abcdef";
    text("0x");
    for (int i = 60; i >= 0; i -= 4) putc(digits[(v >> i) & 15]);
    BARRIER();
}
static void field(const char *name, uint64_t value) { text(name); hex(value); text("\n"); }
static __attribute__((noreturn)) void finish(int success)
{
    __asm__ volatile("msr daifset, #15" ::: "memory");
#if DIAG_QEMU
    uint64_t result[] = { 0x20026, success ? 0 : 1 };
    register uint64_t x0 __asm__("x0") = 0x20;
    register uint64_t x1 __asm__("x1") = (uintptr_t)result;
    __asm__ volatile("hlt #0xf000" : "+r"(x0), "+r"(x1) :: "memory");
#else
    (void)success;
    if (recovery_ready) {
        text("RECOVERY RETURN REQUESTED\n");
        samsung_recovery_request(&recovery_context);
        BARRIER();
        field("PSCI_RESET_RETURN=", psci(0x84000009));
        text("RECOVERY RETURN FAILED\n");
    }
#endif
    for (;;) __asm__ volatile("wfe");
}
static __attribute__((noreturn)) void fail(const char *why)
{
    text("[A31-DIAG] FAIL "); text(why); text("\n"); finish(0);
}
static uint64_t now(void) { __asm__ volatile("isb"); return READ(cntpct_el0); }
static int wait_clear(uintptr_t address, uint32_t mask)
{
    uint64_t start = now();
    while (read32(address) & mask) if (now() - start > frequency) return 0;
    return 1;
}

#if !DIAG_QEMU
static void stop_platform_watchdog(const struct dt_view *dt)
{
    uint32_t node;
    uint64_t base, size;
    if (!dt_compatible(dt, "mediatek,toprgu", &node) ||
        !dt_reg(dt, node, 0, &base, &size) || base != 0x10007000 || size != 0x1000)
        fail("watchdog reservation mismatch");
    uint32_t mode = read32(base);
    field("WDT_MODE_BEFORE=", mode);
    field("WDT_STATUS_BEFORE=", read32(base + 0x0c));
    /* Same keyed EN-bit clear as this A31 kernel's mtk_wdt_stop(). */
    if (mode & 1) write32(base, (mode & ~1U) | 0x22000000U);
    BARRIER();
    uint32_t after = read32(base);
    field("WDT_MODE_AFTER=", after);
    if (after & 1) fail("watchdog disable did not stick");
    text("WDT OFF\n");
}

static void prepare_recovery_return(const struct dt_view *dt)
{
    uint32_t node;
    struct dt_property property;
    static const uint8_t descriptor[16] = {
        0x00, 0xdc, 0x10, 0x00, 0x00, 0x08, 0x00, 0x00,
        0x01, 0x00, 0x00, 0x00, 0xc0, 0x0a, 0x00, 0x00 };
    if (!dt_root_child(dt, "chosen", &node) ||
        !dt_property(dt, node, "ram_console", &property) || property.size != 16)
        fail("recovery SRAM descriptor missing");
    for (unsigned i = 0; i < sizeof(descriptor); i++)
        if (property.data[i] != descriptor[i]) fail("recovery SRAM descriptor mismatch");
    if (!samsung_recovery_bind(&recovery_context, (void *)0x10dc00, 0x800))
        fail("recovery SRAM header mismatch");
    if ((!dt_compatible(dt, "arm,psci-1.0", &node) &&
         !dt_compatible(dt, "arm,psci-0.2", &node)) ||
        !dt_property(dt, node, "method", &property) || property.size != 4 ||
        !dt_string(&property, "smc")) fail("recovery PSCI conduit mismatch");
    uint64_t version = psci(0x84000000);
    field("PSCI_VERSION=", version);
    if (version != 2 && (version < 0x10000 || version > 0x10002))
        fail("recovery PSCI version unsupported");
    recovery_ready = 1;
    text("RECOVERY RETURN ARMED\n");
}
#endif

static uint64_t l1[2048] __attribute__((aligned(16384)));
static uint64_t identity[2048] __attribute__((aligned(16384)));
static uint64_t alias_l2[2048] __attribute__((aligned(16384)));
static uint64_t alias_l3[2048] __attribute__((aligned(16384)));
static uint64_t probe_page[2048] __attribute__((aligned(16384)));

static int probe_mmu(uint64_t ram_base, uint64_t ram_size)
{
    uint64_t mmfr0 = READ(id_aa64mmfr0_el1);
    field("MMFR0_EL1=", mmfr0);
    unsigned granule = (unsigned)((mmfr0 >> 20) & 15);
    if (granule != 1 && granule != 2) return 0;
    uint64_t old_sctlr = READ(sctlr_el1), old_tcr = READ(tcr_el1);
    uint64_t old_ttbr0 = READ(ttbr0_el1), old_mair = READ(mair_el1);
    if (old_sctlr & 5) return 0;
    uint64_t ips = mmfr0 & 15;
    if (ips > 5) ips = 5;
    for (unsigned i = 0; i < 2048; i++) {
        uint64_t p = (uint64_t)i << 25;
        uint64_t attributes = (1ULL << 10) | 1;
        if (p >= ram_base && p + (1ULL << 25) <= ram_base + ram_size)
            attributes |= 3ULL << 8;
        else attributes |= (1ULL << 2) | (3ULL << 53);
        identity[i] = p | attributes;
    }
    l1[0] = (uintptr_t)identity | 3;
    l1[1] = (uintptr_t)alias_l2 | 3;
    alias_l2[0] = (uintptr_t)alias_l3 | 3;
    alias_l3[0] = (uintptr_t)probe_page | 3 | (1ULL << 10) | (3ULL << 8);
    WRITE(mair_el1, 0x0044);
    WRITE(tcr_el1, 24 | (2ULL << 14) | (3ULL << 12) | (1ULL << 23) | (ips << 32));
    WRITE(ttbr0_el1, (uintptr_t)l1);
    BARRIER();
    __asm__ volatile("tlbi vmalle1; dsb sy; isb" ::: "memory");
    probe_page[0] = 0xa3116a55c0decafeULL;
    BARRIER();
    WRITE(sctlr_el1, old_sctlr | 1);
    __asm__ volatile("isb" ::: "memory");
    volatile uint64_t *alias = (volatile uint64_t *)0x1000000000ULL;
    int passed = *alias == probe_page[0];
    *alias = 0xa3116a75f00dbeefULL;
    BARRIER();
    passed &= probe_page[0] == 0xa3116a75f00dbeefULL;
    __asm__ volatile("at s1e1r, %0; isb" :: "r"((uintptr_t)alias) : "memory");
    uint64_t translated = READ(par_el1);
    passed &= !(translated & 1) &&
        ((translated & 0x0000fffffffff000ULL) == (uintptr_t)probe_page);
    WRITE(sctlr_el1, old_sctlr);
    BARRIER();
    __asm__ volatile("tlbi vmalle1; dsb sy; isb" ::: "memory");
    WRITE(tcr_el1, old_tcr); WRITE(ttbr0_el1, old_ttbr0); WRITE(mair_el1, old_mair);
    BARRIER();
    field("MMU16K_PAR=", translated);
    return passed;
}

static int probe_timer(const struct dt_view *dt)
{
    uint32_t node;
    uint64_t gicd, gicd_size, gicr, gicr_size;
    if (!dt_compatible(dt, "arm,gic-v3", &node) ||
        !dt_reg(dt, node, 0, &gicd, &gicd_size) ||
        !dt_reg(dt, node, 1, &gicr, &gicr_size) ||
        gicd_size < 0x10000 || gicr_size < 0x20000 || gicr_size > 0x1000000) return 0;
#if DIAG_QEMU
    if (gicd != 0x08000000 || gicr != 0x080a0000) return 0;
#else
    if (gicd != 0x0c000000 || gicr != 0x0c040000) return 0;
#endif
    field("GICD=", gicd); field("GICR=", gicr);
    uint64_t mpidr = READ(mpidr_el1);
    uint32_t affinity = (uint32_t)(mpidr & 0xffffff) | (uint32_t)((mpidr >> 8) & 0xff000000);
    uintptr_t redistributor = 0;
    for (uint64_t p = gicr; p - gicr <= gicr_size - 0x20000;) {
        uint64_t type = read64(p + 8);
        if ((uint32_t)(type >> 32) == affinity) { redistributor = p; break; }
        if (type & 0x10) break;
        p += type & 2 ? 0x40000 : 0x20000;
    }
    if (!redistributor) return 0;
    WRITE(icc_sre_el1, READ(icc_sre_el1) | 1); BARRIER();
    if (!(READ(icc_sre_el1) & 1)) return 0;
    write32(redistributor + 0x14, read32(redistributor + 0x14) & ~2U);
    if (!wait_clear(redistributor + 0x14, 4)) return 0;
    uintptr_t sgi = redistributor + 0x10000;
    write32(sgi + 0x180, 1U << 27);
    write32(sgi + 0x80, read32(sgi + 0x80) | (1U << 27));
    write32(sgi + 0xd00, read32(sgi + 0xd00) & ~(1U << 27));
    *(volatile uint8_t *)(sgi + 0x400 + 27) = 0x80;
    write32(sgi + 0xc04, read32(sgi + 0xc04) & ~(3U << 22));
    write32(sgi + 0x100, 1U << 27);
    uint32_t control = read32(gicd);
    field("GICD_CTLR_BEFORE=", control);
    /* DS=1 has a single-security-state view: Group 1 enable moves to bit 1. */
    uint32_t group_enable = (control & 0x40) ? 2 : 1;
    if (!(control & 0x10)) {
        write32(gicd, control & ~3U);
        if (!wait_clear(gicd, 1U << 31)) return 0;
        control = (control & ~3U) | 0x10;
        write32(gicd, control);
        if (!wait_clear(gicd, 1U << 31)) return 0;
    }
    write32(gicd, control | group_enable);
    if (!wait_clear(gicd, 1U << 31)) return 0;
    WRITE(icc_ctlr_el1, READ(icc_ctlr_el1) & ~2ULL);
    WRITE(icc_pmr_el1, 0xff); WRITE(icc_bpr1_el1, 0); WRITE(icc_igrpen1_el1, 1);
    WRITE(cntv_tval_el0, frequency / 100); WRITE(cntv_ctl_el0, 1); BARRIER();
    uint64_t start = now();
    __asm__ volatile("msr daifclr, #2" ::: "memory");
    while (timer_irqs < 3 && now() - start < frequency) {}
    __asm__ volatile("msr daifset, #2" ::: "memory");
    field("CNTV_CTL=", READ(cntv_ctl_el0));
    field("GICD_CTLR_AFTER=", read32(gicd));
    field("GICR_PENDING=", read32(sgi + 0x200));
    WRITE(cntv_ctl_el0, 0); write32(sgi + 0x180, 1U << 27); BARRIER();
    field("VTIMER_IRQS=", timer_irqs); field("OTHER_IRQS=", other_irqs);
    return timer_irqs >= 3 && !other_irqs;
}
#if DIAG_PAYLOAD_CHECK
extern __attribute__((noreturn)) void a31_kernel_enter(uint64_t entry, uint64_t boot_args);
static uint64_t fdt_integer(const struct dt_property *property)
{
    uint64_t value = 0;
    for (uint32_t i = 0; i < property->size; i++) value = value << 8 | property->data[i];
    return value;
}
static int payload_write(void *context, uint64_t address, const void *source, size_t size)
{
    (void)context;
    volatile uint8_t *destination = (volatile uint8_t *)(uintptr_t)address;
    const uint8_t *data = source;
    size_t position = 0;
    if (!(address & 7) && (!data || !((uintptr_t)data & 7))) {
        for (; size - position >= 8; position += 8)
            *(volatile uint64_t *)(destination + position) = data ? *(const uint64_t *)(data + position) : 0;
    }
    for (; position < size; position++) destination[position] = data ? data[position] : 0;
    BARRIER();
    for (position = 0; position < size; position++)
        if (destination[position] != (data ? data[position] : 0)) return 0;
    return 1;
}
static void probe_payload(const struct dt_view *dt)
{
    uint32_t node;
    struct dt_property start, end;
    if (!dt_root_child(dt, "chosen", &node) ||
        !dt_property(dt, node, "linux,initrd-start", &start) ||
        !dt_property(dt, node, "linux,initrd-end", &end) ||
        (start.size != 4 && start.size != 8) || end.size != start.size)
        fail("payload initrd properties");
    uint64_t first = fdt_integer(&start), last = fdt_integer(&end);
    if (last <= first || last - first > 24 * 1024 * 1024) fail("payload initrd bounds");
#if DIAG_QEMU
    uint64_t base = 0x50000000, size = 0x4000000;
    if (first < 0x40000000 || last > 0x60000000) fail("QEMU payload source");
#else
    uint64_t base = 0x100000000ULL, size = 0x3fd00000;
    if (first != 0x47c80000) fail("A31 payload source");
#endif
    if (!dt_ram_available(dt, base, size)) fail("payload RAM reserved or absent");
    struct a31_payload_plan plan;
    const char *error = a31_payload_validate((const void *)(uintptr_t)first, last - first,
                                            first, base, size, &plan);
    if (error) fail(error);
    field("PAYLOAD_SOURCE=", first); field("PAYLOAD_BYTES=", last - first);
    field("XNU_ENTRY_PA=", plan.entry); field("ADT_PA=", plan.adt_address);
    field("BOOT_ARGS_PA=", plan.args_address); field("XNU_TOP=", plan.top);
    error = a31_payload_prepare(&plan, payload_write, NULL);
    if (error) fail(error);
    text("PAYLOAD COPY/READBACK PASS\n");
#if DIAG_XNU_ENTRY
    if ((READ(CurrentEL) >> 2) != 1 || (READ(sctlr_el1) & ((1ULL << 12) | 5)))
        fail("kernel entry requires EL1 and MMU/caches off");
    text("ENTRY_PAYLOAD_SHA256=" DIAG_ENTRY_PAYLOAD_SHA "\n");
    text("[A31-DIAG] XNU HANDOFF\n");
    a31_kernel_enter(plan.entry, plan.args_address);
#else
    text("XNU JUMP DISABLED\n");
#endif
}
#endif
void diag_exception(uint64_t slot)
{
    if ((READ(CurrentEL) >> 2) == 2) {
        field("EXCEPTION_EL=", 2); field("EXCEPTION_SLOT=", slot);
        field("ESR_EL2=", READ(esr_el2)); field("ELR_EL2=", READ(elr_el2));
        field("FAR_EL2=", READ(far_el2));
        fail("EL2 entry exception");
    }
    if (slot == 5) {
        uint64_t interrupt = READ(icc_iar1_el1);
        unsigned id = interrupt & 0xffffff;
        if (id >= 1020 && id <= 1023) return;
        if (id == 27) { timer_irqs++; WRITE(cntv_tval_el0, frequency / 100); }
        else other_irqs++;
        WRITE(icc_eoir1_el1, interrupt);
        __asm__ volatile("isb");
        return;
    }
    field("EXCEPTION_EL=", 1); field("EXCEPTION_SLOT=", slot);
    field("ESR_EL1=", READ(esr_el1));
    field("ELR_EL1=", READ(elr_el1)); field("FAR_EL1=", READ(far_el1));
    fail("exception");
}

void diag_early(uintptr_t fdt_address, uint64_t entry_el)
{
    struct dt_view dt;
    uint32_t node;
    uint64_t base, size;
    if ((fdt_address & 7) || fdt_address < 0x40000000 ||
        fdt_address > 0x140000000ULL - 0x200000 ||
        !dt_open(&dt, (const void *)fdt_address, 0x200000)) fail("FDT bounds");
#if DIAG_QEMU
    if (!dt_compatible(&dt, "linux,dummy-virt", &node) || node != dt.structure)
        fail("QEMU platform mismatch");
#else
    if (!dt_compatible(&dt, "mediatek,MT6768", &node) || node != dt.structure ||
        !dt_reserved(&dt, "sec-log-reserve-memory@", &node) ||
        !dt_reg(&dt, node, 0, &base, &size) || base != 0x46c00000 || size != 0x200000 ||
        ((uintptr_t)_head < base + size && (uintptr_t)_end > base) ||
        (fdt_address < base + size && fdt_address + dt.size > base) ||
        !sec_log_bind(&log_ring, (void *)(uintptr_t)base, size)) finish(0);
    log_ready = 1;
    if (!dt_compatible(&dt, "mediatek,pstore", &node) ||
        !dt_reg(&dt, node, 0, &base, &size) ||
        base != 0x4d010000 || size != 0xe0000 ||
        ((uintptr_t)_head < base + size && (uintptr_t)_end > base) ||
        (fdt_address < base + size && fdt_address + dt.size > base))
        fail("PSTORE reservation mismatch");
    /* Measured recovery layout: dump, console, bconsole, ftrace, pmsg; ECC=0. */
    if (!ramoops_log_bind(&pstore_ring, (void *)(uintptr_t)(base + 0x4f000), 0x40000))
        fail("PSTORE console bounds");
    pstore_ready = 1;
#endif
    text("\n[A31-DIAG v1] BEGIN\n");
    text("BUILD=" DIAG_BUILD_ID "\n");
    field("ENTRY_EL=", entry_el); field("EARLY_CURRENT_EL=", READ(CurrentEL) >> 2);
    field("FDT=", fdt_address);
    if (entry_el == 2) field("ENTRY_SCTLR=", READ(sctlr_el2));
    else field("ENTRY_SCTLR=", READ(sctlr_el1));
    text("EARLY ENTRY RECORDED\n");
#if !DIAG_QEMU
    prepare_recovery_return(&dt);
#endif
    (void)base; (void)size;
}

void diag_main(uintptr_t fdt_address, uint64_t entry_el)
{
    struct dt_view dt;
    uint32_t node;
    uint64_t ram_base, ram_size;
    (void)entry_el;
    field("CURRENT_EL=", READ(CurrentEL) >> 2);
    text("EL1 HANDOFF RECORDED\n");
    if (!dt_open(&dt, (const void *)fdt_address, 0x200000)) fail("EL1 FDT bounds");
    field("MIDR=", READ(midr_el1)); field("MPIDR=", READ(mpidr_el1));
    field("SCTLR_EL1=", READ(sctlr_el1)); field("FDT=", fdt_address);
#if !DIAG_QEMU
    stop_platform_watchdog(&dt);
#endif
    frequency = READ(cntfrq_el0); field("CNTFRQ=", frequency);
    if (frequency < 1000000 || frequency > 1000000000) fail("timer frequency");
    /* Device-type lookup includes unit-addressed memory nodes on QEMU. */
    if (!dt_compatible(&dt, "arm,gic-v3", &node)) fail("no GICv3");
#if DIAG_QEMU
    ram_base = 0x40000000; ram_size = 0x20000000;
#else
    ram_base = 0x40000000; ram_size = 0x100000000;
    unsigned part = (unsigned)((READ(midr_el1) >> 4) & 0xfff);
    if ((READ(midr_el1) >> 24) != 0x41 || (part != 0xd05 && part != 0xd0a))
        fail("unexpected CPU");
#endif
    if ((uintptr_t)_head < ram_base || (uintptr_t)_end > ram_base + ram_size)
        fail("shim outside RAM");
    if (!probe_mmu(ram_base, ram_size)) fail("16K translation");
    text("MMU16K PASS\n");
    if (!probe_timer(&dt)) fail("GICv3/virtual timer");
    text("VTIMER PASS\n");
#if DIAG_PAYLOAD_CHECK
    probe_payload(&dt);
#endif
    text("[A31-DIAG] PASS\n");
    finish(1);
}
