"""Keep final-mapping and fatal-relay test sources identical to linked XNU."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class FinalVMSourceTests(unittest.TestCase):
    def test_shared_final_sources_are_exact_patch_copies(self):
        patch = (ROOT / 'xnu/patches/0091-a31-final-vm-diagnostics.patch').read_text()
        for local, kernel in [('xnu_final_io.h', 'a31_final_io.h'),
                              ('xnu_final_vectors.inc', 'a31_final_vectors.inc')]:
            block = patch.split('+++ b/osfmk/arm64/' + kernel + '\n', 1)[1]
            lines = []
            for line in block.splitlines(keepends=True):
                if line.startswith('--- '):
                    break
                if line.startswith('+'):
                    lines.append(line[1:])
            added = ''.join(lines)
            self.assertEqual(added, (ROOT / 'shim/a31' / local).read_text())

    def test_shared_pmap_sources_are_exact_patch_copies(self):
        patch = (ROOT / 'xnu/patches/0092-a31-pmap-bootstrap-checkpoint.patch').read_text()
        for local, kernel in [('xnu_pmap_bounds.h', 'a31_pmap_bounds.h'),
                              ('xnu_pmap_trap.inc', 'a31_pmap_trap.inc')]:
            block = patch.split('+++ b/osfmk/arm64/' + kernel + '\n', 1)[1]
            lines = []
            for line in block.splitlines(keepends=True):
                if line.startswith('--- '):
                    break
                if line.startswith('+'):
                    lines.append(line[1:])
            self.assertEqual(''.join(lines), (ROOT / 'shim/a31' / local).read_text())

    def test_relay_keeps_mmu_on_until_branching_to_existing_physical_handler(self):
        text = (ROOT / 'shim/a31/xnu_final_vectors.inc').read_text()
        self.assertNotIn('msr sctlr_el1', text)
        self.assertLess(text.index('msr ttbr0_el1'), text.index('tlbi vmalle1is'))
        self.assertLess(text.index('tlbi vmalle1is'), text.index('br x12'))
        self.assertIn('EXT(bootstrap_pagetables)@page', text)
        self.assertIn('EXT(a31_boot_fault)@page', text)
