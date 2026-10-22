import struct
import unittest

from a31_diag_log import inspect

BUILD = 'a' * 40
BEGIN = b'\n[A31-DIAG v1] BEGIN\nBUILD=' + BUILD.encode() + b'\n'
PASS = b'MMU16K PASS\nVTIMER PASS\n[A31-DIAG] PASS\n'


class A31LogTests(unittest.TestCase):
    def test_pass_requires_one_matching_build_session(self):
        result = inspect(BEGIN + b'CURRENT_EL=0x0000000000000001\n' + PASS, BUILD)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['sessions'][0]['fields']['CURRENT_EL'], '0x0000000000000001')

    def test_different_build_is_not_evidence(self):
        self.assertEqual(inspect(BEGIN + PASS, 'b' * 40)['status'], 'not_found')

    def test_partial_passes_do_not_prove_completion(self):
        self.assertEqual(inspect(BEGIN + b'MMU16K PASS\n', BUILD)['status'], 'incomplete')

    def test_failure_is_not_overridden_by_pass_text(self):
        self.assertEqual(inspect(BEGIN + b'[A31-DIAG] FAIL exception\n' + PASS, BUILD)['status'], 'fail')

    def test_does_not_borrow_pass_from_next_session(self):
        other = BEGIN.replace(BUILD.encode(), b'b' * 40)
        self.assertEqual(inspect(BEGIN + b'MMU16K PASS\n' + other + PASS, BUILD)['status'], 'incomplete')

    def test_rotated_samsung_ring_is_decoded(self):
        capacity = 0x200000 - 12
        content = BEGIN + PASS
        original = bytes(capacity - len(content)) + content
        position = capacity - 20
        rotated = original[-position:] + original[:-position]
        raw = rotated + struct.pack('<3I', 1, position, 0x4d474f4c)
        self.assertEqual(inspect(raw, BUILD)['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
