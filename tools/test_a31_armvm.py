import unittest
from a31_armvm import check_armvm_fields, REQUIRED


def valid_fields():
    numbers = [0x3fd00000, 0x1025a4000, 0x1025a4000, 0x1025d0000, 0x13fd00000,
               11, 3, 0, 0, 0, 0x1025d0000, 0xfffffe000a000000, 0xfffffe000d000000,
               0xfffffe8fffdfc000, 0xfffffe8fffffffff]
    return {name: f'0x{number:016x}' for name, number in zip(REQUIRED, numbers)}


class ArmVMReportTests(unittest.TestCase):
    def test_complete_report(self):
        self.assertTrue(check_armvm_fields(valid_fields()))

    def test_each_field_required_including_zero_values(self):
        for name in REQUIRED:
            fields = valid_fields()
            del fields[name]
            self.assertFalse(check_armvm_fields(fields), name)

    def test_bad_bounds_counts_preemption_ast_and_windows(self):
        for name, value in [('ALLOC_BEGIN', 0x1025a8000), ('ALLOC_END', 0x140000000),
                            ('PT_PAGES', 10), ('PT_PAGES', 33), ('LEAF_PAGES', 0),
                            ('PREEMPT_AFTER', 1), ('PENDING_AST', 1),
                            ('FIRST_AVAIL', 0x1025cc000), ('COPY_START', 0xfffffe8fffdf8000),
                            ('IO_START', 0xfffffe0002000000), ('IO_END', 0xfffffe000d000001)]:
            fields = valid_fields()
            fields['XNU_ARMVM_' + name] = hex(value)
            self.assertFalse(check_armvm_fields(fields), name)

    def test_malformed_integer_rejected(self):
        fields = valid_fields()
        fields['XNU_ARMVM_PENDING_AST'] = 'not hexadecimal'
        self.assertFalse(check_armvm_fields(fields))
