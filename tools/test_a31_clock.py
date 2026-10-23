"""Execute the exact A31 clock-ratio patch with zero and high clock rates."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class A31ClockTests(unittest.TestCase):
    def test_exact_clock_policy_handles_zero_and_high_rates(self):
        patch = (ROOT / 'xnu/patches/0088-a31-platform-clock-checkpoint.patch').read_text()
        added = patch.split('+#if defined(A31)\n', 1)[1].split('+#else\n', 1)[0]
        code = ''.join(line[1:] for line in added.splitlines(keepends=True) if line.startswith('+'))
        compiler = shutil.which('clang')
        if not compiler:
            self.skipTest('native host C compiler unavailable; Android cross compiler is insufficient')
        source = '''#include <stdint.h>
#include <assert.h>
struct { uint32_t bus_clock_rate_hz, cpu_clock_rate_hz, dec_clock_rate_hz,
bus_to_cpu_rate_num, bus_to_cpu_rate_den, bus_to_dec_rate_num,
bus_to_dec_rate_den; } gPEClockFrequencyInfo;
static void policy(void) {
''' + code + '''
}
int main(void) {
    gPEClockFrequencyInfo.cpu_clock_rate_hz = 4000000000U;
    gPEClockFrequencyInfo.dec_clock_rate_hz = 13000000;
    policy();
    assert(gPEClockFrequencyInfo.bus_clock_rate_hz == 0);
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_num == 0);
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_den == 1);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_num == 0);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_den == 1);
    gPEClockFrequencyInfo.bus_clock_rate_hz = 100000000;
    policy();
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_num == 4000000000U);
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_den == 100000000);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_num == 13000000);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_den == 100000000);
    gPEClockFrequencyInfo.bus_clock_rate_hz = 1;
    gPEClockFrequencyInfo.cpu_clock_rate_hz = 0;
    gPEClockFrequencyInfo.dec_clock_rate_hz = 0;
    policy();
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_num == 0);
    assert(gPEClockFrequencyInfo.bus_to_cpu_rate_den == 1);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_num == 0);
    assert(gPEClockFrequencyInfo.bus_to_dec_rate_den == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / 'clock.c'
            src.write_text(source)
            exe = Path(folder) / ('clock.exe' if os.name == 'nt' else 'clock')
            flags = [] if os.name == 'nt' else ['-fsanitize=undefined']
            subprocess.run([compiler, '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', *flags,
                            str(src), '-o', str(exe)], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True, text=True)
