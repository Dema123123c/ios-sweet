#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static sigjmp_buf trapped;
static volatile sig_atomic_t probing;

static void trap_handler(int sig)
{
    if (probing)
        siglongjmp(trapped, sig);
    _exit(128 + sig);
}

static int read_register(unsigned reg, uint64_t *value)
{
    if (sigsetjmp(trapped, 1)) {
        probing = 0;
        return 0;
    }
    probing = 1;
    switch (reg) {
    case 0: __asm__ volatile("mrs %0, midr_el1" : "=r"(*value)); break;
    case 1: __asm__ volatile("mrs %0, id_aa64mmfr0_el1" : "=r"(*value)); break;
    case 2: __asm__ volatile("mrs %0, id_aa64pfr0_el1" : "=r"(*value)); break;
    case 3: __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(*value)); break;
    default: probing = 0; return 0;
    }
    probing = 0;
    return 1;
}

int main(void)
{
    static const char *names[] = {"MIDR_EL1", "ID_AA64MMFR0_EL1", "ID_AA64PFR0_EL1", "CNTFRQ_EL0"};
    struct sigaction action = {0};
    action.sa_handler = trap_handler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGILL, &action, NULL) || sigaction(SIGSEGV, &action, NULL)) {
        perror("sigaction");
        return 1;
    }
    cpu_set_t allowed, original;
    if (sched_getaffinity(0, sizeof(allowed), &allowed)) {
        perror("sched_getaffinity");
        return 1;
    }
    original = allowed;
    puts("A31 CPU probe: Linux EL0 view; ID registers may be emulated or masked.");
    puts("This does not test a 16K MMU or the bare-metal boot handoff.");
    printf("Linux page size: %ld\n", sysconf(_SC_PAGESIZE));
    int examined = 0;
    for (int cpu = 0; cpu < CPU_SETSIZE; cpu++) {
        if (!CPU_ISSET(cpu, &allowed))
            continue;
        cpu_set_t one;
        CPU_ZERO(&one);
        CPU_SET(cpu, &one);
        if (sched_setaffinity(0, sizeof(one), &one)) {
            printf("CPU %d: affinity unavailable: %s\n", cpu, strerror(errno));
            continue;
        }
        examined++;
        printf("CPU %d\n", cpu);
        for (unsigned reg = 0; reg < sizeof(names) / sizeof(names[0]); reg++) {
            uint64_t value = 0;
            if (!read_register(reg, &value)) {
                printf("  %s: unavailable at EL0\n", names[reg]);
                continue;
            }
            printf("  %s: 0x%016" PRIx64 "\n", names[reg], value);
            if (reg == 1)
                printf("  TGran16 field: 0x%" PRIx64 " (Linux-visible value)\n", value >> 20 & 15);
        }
    }
    if (sched_setaffinity(0, sizeof(original), &original)) {
        perror("restore affinity");
        return 1;
    }
    return examined ? 0 : 1;
}
