"""Reject accidental Redmi identity or wrong RAM/timer in platform fixtures."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import adt
from a31_bootstrap_qemu import run
from a31_payload import validate_adt


class PlatformFixtureTests(unittest.TestCase):
    def test_actual_platform_and_bootstrap_fixture_match_a31_payload_contract(self):
        class FixtureChecked(Exception):
            pass

        def check(kernel, tree, output, command, entry_checkpoint):
            blob = tree.read_bytes()
            root, end = adt.parse(blob)
            self.assertEqual(end, len(blob))
            self.assertIn(b'samsung,a31\0', root.prop('compatible'))
            validate_adt(blob, 0x100000000, 0x3fd00000)
            cpu = next(n for n in root.children if n.prop('name') == b'cpus\0').children[0]
            self.assertEqual(cpu.prop('timebase-frequency'), struct.pack('<I', 13000000))
            self.assertIsNone(cpu.prop('bus-frequency'))
            self.assertTrue(entry_checkpoint)
            raise FixtureChecked

        for mode in ['platform', 'bootstrap', 'runtime', 'vm']:
            with tempfile.TemporaryDirectory() as directory:
                with patch('a31_bootstrap_qemu.build', side_effect=check):
                    with self.assertRaises(FixtureChecked):
                        run(Path('unused.kernel'), Path(directory) / 'fixture', **{mode: True})
