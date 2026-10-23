import struct
import hashlib
import unittest

from a31_payload import validate_kernel, fixture, inspect_payload, ENTRY_MARKERS, validate_entry_checkpoint
from mka31diag import validate_payload_input
from pathlib import Path
from tempfile import TemporaryDirectory


def kernel():
    data = bytearray(0x4000)
    struct.pack_into('<8I', data, 0, 0xfeedfacf, 0x100000c, 0, 2, 2, 360, 0, 0)
    struct.pack_into('<II16s4Q4I', data, 32, 0x19, 72, b'__TEXT',
                     0xfffffe0007004000, 0x4000, 0, 0x4000, 5, 5, 0, 0)
    struct.pack_into('<4I', data, 104, 5, 288, 6, 68)
    struct.pack_into('<Q', data, 104 + 272, 0xfffffe0007005000)
    return data


class A31PayloadTests(unittest.TestCase):
    def test_entry_gate_requires_exact_payload_and_checkpoint_code(self):
        data = fixture(0x100000000, 0x3fd00000, entry_code=b'\0'.join(ENTRY_MARKERS))
        metadata = {'payload_mode': 'XNU entry checkpoint; stop before CPU/VM startup',
                    'kernel_jump_enabled': True, 'expected_payload_sha256': hashlib.sha256(data).hexdigest()}
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'payload'; path.write_bytes(data)
            self.assertTrue(validate_payload_input(metadata, path)['kernel_jump_enabled'])
            for key, value in [('expected_payload_sha256', '0' * 64), ('expected_payload_sha256', None),
                               ('kernel_jump_enabled', False)]:
                bad = dict(metadata); bad[key] = value
                with self.assertRaises(ValueError): validate_payload_input(bad, path)
            path.write_bytes(fixture(0x100000000, 0x3fd00000))
            metadata['expected_payload_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'markers'): validate_payload_input(metadata, path)
        with self.assertRaisesRegex(ValueError, 'entry-check'): validate_entry_checkpoint(kernel())
        with self.assertRaises(ValueError): validate_payload_input({'kernel_jump_enabled': True}, None)
    def test_native_payload_entry_and_args_are_bounded(self):
        result = inspect_payload(fixture(0x100000000, 0x3fd00000))
        self.assertEqual(result['entry_pa'], '0x100004000')
        self.assertEqual(result['boot_args_pa'], '0x100010000')
        self.assertFalse(result['kernel_jump_enabled'])

    def test_rejects_payload_corruption_before_packaging(self):
        for offset in [8, 12, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40,
                       0x2a8, 0x2b0, 0x2b8, 0x2c0]:
            data = bytearray(fixture(0x100000000, 0x3fd00000))
            struct.pack_into('<Q', data, offset, (1 << 64) - 1)
            with self.subTest(offset=offset), self.assertRaises(ValueError): inspect_payload(data)

    def test_rejects_payload_destination_and_source_overlap(self):
        for src, dst in [(0x2a8, 0x2c8), (0x2b8, 0x2d8)]:
            data = bytearray(fixture(0x100000000, 0x3fd00000))
            data[dst:dst + 8] = data[src:src + 8]
            with self.assertRaisesRegex(ValueError, 'overlap'): inspect_payload(data)

    def test_rejects_adt_ram_mismatch(self):
        data = bytearray(fixture(0x100000000, 0x3fd00000))
        offset = data.index(b'dram-size\0')
        struct.pack_into('<Q', data, offset + 36, 0x100000)
        with self.assertRaisesRegex(ValueError, 'ADT RAM'): inspect_payload(data)

    def test_ramdisk_replacement_requires_prepare_only_build(self):
        metadata = {'payload_mode': 'prepare-only; no XNU jump', 'kernel_jump_enabled': False}
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'payload'
            path.write_bytes(fixture(0x100000000, 0x3fd00000))
            self.assertEqual(validate_payload_input(metadata, path)['segments'], 2)
            with self.assertRaises(ValueError): validate_payload_input({}, path)
            with self.assertRaises(ValueError): validate_payload_input(metadata, None)
            metadata['kernel_jump_enabled'] = True
            with self.assertRaises(ValueError): validate_payload_input(metadata, path)

    def test_accepts_plain_arm64_executable_entry(self):
        self.assertEqual(validate_kernel(kernel())['architecture'], 'arm64')

    def test_rejects_arm64e_or_wrong_machine(self):
        for offset, value in [(4, 0x1000007), (8, 2), (12, 6)]:
            data = kernel(); struct.pack_into('<I', data, offset, value)
            with self.assertRaises(ValueError): validate_kernel(data)

    def test_rejects_command_bounds_and_oversized_section_table(self):
        for offset, value in [(20, 0x1000000), (36, 0), (32 + 64, 100), (104 + 4, 280)]:
            data = kernel(); struct.pack_into('<I', data, offset, value)
            with self.assertRaises(ValueError): validate_kernel(data)

    def test_rejects_entry_outside_executable_file_data(self):
        data = kernel(); struct.pack_into('<Q', data, 104 + 272, 0x40000000)
        with self.assertRaisesRegex(ValueError, 'executable'): validate_kernel(data)
        data = kernel(); struct.pack_into('<I', data, 32 + 60, 1)
        with self.assertRaisesRegex(ValueError, 'executable'): validate_kernel(data)

    def test_rejects_truncated_kernel_data(self):
        with self.assertRaises(ValueError): validate_kernel(kernel()[:-1])
        with self.assertRaises(ValueError): validate_kernel(b'')

    def test_fixture_has_bss_and_separate_file_ranges(self):
        data = fixture()
        self.assertEqual(data[:8], b'SWEETXNU')
        self.assertEqual(struct.unpack_from('<I', data, 12)[0], 2)
        self.assertEqual(struct.unpack_from('<Q', data, 0x2c0)[0], 13)
