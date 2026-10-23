"""Keep the native entry checkpoint's tested I/O identical to the XNU patch."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class KernelEntrySourceTests(unittest.TestCase):
    def test_boot_exception_assembly_matches_executable_test_source(self):
        patch = (ROOT / 'xnu/patches/0084-a31-physical-boot-exceptions.patch').read_text()
        added = patch.split('+++ b/osfmk/arm64/a31_boot_asm.inc\n', 1)[1]
        source = ''.join(line[1:] for line in added.splitlines(keepends=True)
                         if line.startswith('+'))
        self.assertEqual(source, (ROOT / 'shim/a31/xnu_boot_asm.inc').read_text())

    def test_kernel_uses_exact_tested_ring_and_recovery_header(self):
        patch = (ROOT / 'xnu/patches/0083-a31-xnu-entry-check.patch').read_text()
        added = patch.split('+++ b/osfmk/arm64/a31_entry_io.h\n', 1)[1]
        header = ''.join(line[1:] for line in added.splitlines(keepends=True)
                         if line.startswith('+'))
        self.assertEqual(header, (ROOT / 'shim/a31/xnu_entry_io.h').read_text())


if __name__ == '__main__':
    unittest.main()
