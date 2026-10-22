import struct
import hashlib
import unittest

from mka31diag import dtbs, unpack, require_parent_digest
from test_a31 import fixture


def table(dtb):
    return struct.pack('>8I', 0xd7b7ab1e, 64 + len(dtb), 32, 32, 1, 32, 2048, 0) + \
        struct.pack('>8I', len(dtb), 64, 0, 0, 0, 0, 0, 0) + dtb


def boot():
    data = bytearray(2048)
    data[:8] = b'ANDROID!'
    struct.pack_into('<10I', data, 8, 8, 0x40080000, 8, 0x47c80000,
                     0, 0, 0x4bc80000, 2048, 2, 0x18000182)
    struct.pack_into('<I', data, 1644, 1660)
    dtb = table(fixture())
    struct.pack_into('<IQ', data, 1648, len(dtb), 0x4bc80000)
    data[48:52] = b'TEST'
    data[64:68] = b'test'
    data.extend(b'kernel!!' + bytes(2040))
    data.extend(b'ramdisk!' + bytes(2040))
    data.extend(dtb)
    return data


class A31BootTests(unittest.TestCase):
    def test_parent_hash_accepts_exact_signed_range(self):
        salt = b'salt'
        data = b'original boot' + b'unsigned footer outside signed range'
        expected = hashlib.sha256(salt + b'original boot').digest()
        require_parent_digest(data, 13, 'sha256', salt, expected)

    def test_parent_hash_rejects_changed_kernel_despite_own_footer(self):
        expected = hashlib.sha256(b'salt' + b'original boot').digest()
        with self.assertRaisesRegex(ValueError, 'does not match parent vbmeta'):
            require_parent_digest(b'modified boot' + b'valid own AVB footer',
                                  13, 'sha256', b'salt', expected)

    def test_parent_hash_rejects_truncated_candidate(self):
        with self.assertRaises(ValueError):
            require_parent_digest(b'short', 13, 'sha256', b'', bytes(32))

    def test_parent_hash_rejects_unsupported_descriptor(self):
        with self.assertRaises(ValueError):
            require_parent_digest(b'boot', 4, 'sha512', b'', bytes(64))

    def test_android_dt_table_preserves_payload(self):
        dtb = fixture()
        self.assertEqual(dtbs(table(dtb)), [dtb])
        self.assertEqual(dtbs(dtb), [dtb])

    def test_rejects_dt_table_truncation(self):
        with self.assertRaises(ValueError):
            dtbs(table(fixture())[:-1])

    def test_rejects_dt_entry_pointing_into_header(self):
        data = bytearray(table(fixture()))
        struct.pack_into('>I', data, 36, 32)
        with self.assertRaises(ValueError):
            dtbs(data)

    def test_rejects_dt_count_overflow(self):
        data = bytearray(table(fixture()))
        struct.pack_into('>I', data, 16, 0xffffffff)
        with self.assertRaises(ValueError):
            dtbs(data)

    def test_boot_v2_offsets_and_components(self):
        result = unpack(boot())
        self.assertEqual(result['kernel_addr'], 0x40080000)
        self.assertEqual(result['dtb_addr'], 0x4bc80000)
        self.assertEqual(result['parts']['kernel'], b'kernel!!')
        self.assertEqual(result['parts']['ramdisk'], b'ramdisk!')
        self.assertEqual(dtbs(result['parts']['dtb']), [fixture()])

    def test_rejects_truncated_boot_component(self):
        with self.assertRaises(ValueError):
            unpack(boot()[:-1])

    def test_rejects_changed_boot_header_version(self):
        data = boot()
        struct.pack_into('<I', data, 40, 3)
        with self.assertRaises(ValueError):
            unpack(data)


if __name__ == '__main__':
    unittest.main()
