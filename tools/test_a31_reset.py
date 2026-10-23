import struct
import unittest

from a31_reset_check import check_kernel_reset


def kernel():
    data = bytearray(0x400)
    va = 0xfffffe0007000000
    struct.pack_into('<8I', data, 0, 0xfeedfacf, 0x100000c, 0, 2, 2, 96, 0, 0)
    struct.pack_into('<II16s4Q4I', data, 32, 0x19, 72, b'__TEXT_EXEC', va, len(data), 0, len(data), 7, 5, 0, 0)
    strings = b'\0_a31_return\0_next\0'
    struct.pack_into('<6I', data, 104, 2, 24, 0x300, 2, 0x340, len(strings))
    struct.pack_into('<IBBHQ', data, 0x300, 1, 0xe, 1, 0, va + 0x200)
    struct.pack_into('<IBBHQ', data, 0x310, 13, 0xe, 1, 0, va + 0x240)
    data[0x340:0x340 + len(strings)] = strings
    struct.pack_into('<III', data, 0x208, 0xd5033f9f, 0xd5033fdf, 0xd4000003)
    return data


class ResetMachineCodeTests(unittest.TestCase):
    def test_accepts_complete_sequence_in_reset_function(self):
        self.assertEqual(check_kernel_reset(kernel())['smc_va'], '0xfffffe0007000210')

    def test_rejects_comment_truncated_inline_assembly(self):
        data = kernel()
        struct.pack_into('<II', data, 0x20c, 0xd65f03c0, 0xd503201f)
        with self.assertRaisesRegex(ValueError, 'DSB / ISB / SMC'):
            check_kernel_reset(data)

    def test_unrelated_smc_in_other_function_is_insufficient(self):
        data = kernel()
        data[0x248:0x254] = data[0x208:0x214]
        data[0x208:0x214] = bytes(12)
        with self.assertRaisesRegex(ValueError, 'DSB / ISB / SMC'):
            check_kernel_reset(data)

    def test_rejects_symbol_table_outside_file(self):
        data = kernel()
        struct.pack_into('<I', data, 112, 0xfffffff0)
        with self.assertRaisesRegex(ValueError, 'bounds'):
            check_kernel_reset(data)
