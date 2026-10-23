import importlib.util
from pathlib import Path
import unittest


class WatchdogBuildGates(unittest.TestCase):
    def test_control_rejects_every_payload_or_qemu_mode_before_build(self):
        path = Path(__file__).resolve().parents[1] / 'shim/a31/build.py'
        spec = importlib.util.spec_from_file_location('watchdog_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for flags in [{'qemu': True}, {'entry_fault': True}, {'payload_check': True},
                      {'entry_check_sha': '0' * 64}, {'entry_trap': True}, {'trap_offset': 0x1c78}]:
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, 'must never execute'):
                module.build(Path('must-not-be-created'), watchdog_control=True, **flags)
