import struct
import hashlib
import unittest

from mka31diag import (dtbs, unpack, require_parent_digest, check_boot_contract,
                      validate_live_unlocked_fdt, validate_pstore_profile, PSTORE_PROFILE)
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
    def test_pstore_profile_accepts_recovery_sysfs_decimal_strings(self):
        self.assertEqual(validate_pstore_profile({k: str(v) for k, v in PSTORE_PROFILE.items()}),
                         PSTORE_PROFILE)

    def test_pstore_profile_rejects_changed_ecc_or_memory_layout(self):
        for key in ['ecc', 'mem_address', 'console_size', 'mem_size', 'ftrace_size']:
            profile = dict(PSTORE_PROFILE)
            profile[key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_pstore_profile(profile)
        with self.assertRaises(ValueError):
            validate_pstore_profile({'ecc': '0'})

    def test_live_recovery_requires_unlocked_and_orange(self):
        data = fixture(b'androidboot.vbmeta.device_state=unlocked '
                       b'androidboot.verifiedbootstate=orange\0')
        self.assertEqual(validate_live_unlocked_fdt(data)['sha256'],
                         hashlib.sha256(data).hexdigest())

    def test_live_recovery_rejects_observed_green_state(self):
        data = fixture(b'androidboot.vbmeta.device_state=unlocked '
                       b'androidboot.verifiedbootstate=green\0')
        with self.assertRaisesRegex(ValueError, 'older stock Android evidence is insufficient'):
            validate_live_unlocked_fdt(data)

    def test_live_recovery_rejects_missing_or_ambiguous_state(self):
        for args in [b'', b'androidboot.verifiedbootstate=orange',
                     b'androidboot.vbmeta.device_state=locked androidboot.verifiedbootstate=orange',
                     b'androidboot.vbmeta.device_state=unlocked androidboot.verifiedbootstate=orange '
                     b'androidboot.verifiedbootstate=green']:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_live_unlocked_fdt(fixture(args))

    def unlocked_properties(self):
        return {'ro.product.model': 'SM-A315F', 'ro.product.device': 'a31',
                'ro.build.PDA': 'A315FXXU5DXJ1', 'sys.boot_completed': '1',
                'ro.boot.flash.locked': '0', 'ro.boot.vbmeta.device_state': 'unlocked',
                'ro.boot.verifiedbootstate': 'orange'}

    def test_parent_mismatch_remains_fatal_by_default(self):
        with self.assertRaisesRegex(ValueError, 'does not match parent'):
            check_boot_contract(b'modified boot', 13, 'sha256', b'', bytes(32))

    def test_unlocked_policy_reports_mismatch_without_claiming_parent_match(self):
        result = check_boot_contract(b'modified boot', 13, 'sha256', b'', bytes(32),
                                     self.unlocked_properties())
        self.assertFalse(result['boot_digest_matches'])
        self.assertIn('explicitly testing', result['boot_contract'])

    def test_unlocked_policy_rejects_locked_or_conflicting_stock_evidence(self):
        for key, value in [('ro.boot.flash.locked', '1'),
                           ('ro.boot.vbmeta.device_state', 'locked'),
                           ('ro.boot.verifiedbootstate', 'green'),
                           ('sys.boot_completed', '0'),
                           ('ro.product.device', 'sweet'),
                           ('ro.product.model', 'SM-A315G'),
                           ('ro.build.PDA', 'different')]:
            with self.subTest(key=key):
                evidence = self.unlocked_properties()
                evidence[key] = value
                with self.assertRaisesRegex(ValueError, 'stock Android A31'):
                    check_boot_contract(b'boot', 4, 'sha256', b'', bytes(32), evidence)

    def test_oem_permission_alone_does_not_enable_unlocked_policy(self):
        with self.assertRaisesRegex(ValueError, 'stock Android A31'):
            check_boot_contract(b'boot', 4, 'sha256', b'', bytes(32),
                                {'sys.oem_unlock_allowed': '1'})

    def test_unlocked_policy_does_not_accept_bad_range_or_algorithm(self):
        for size, algorithm in [(5, 'sha256'), (4, 'sha512')]:
            with self.subTest(size=size, algorithm=algorithm), self.assertRaises(ValueError):
                check_boot_contract(b'boot', size, algorithm, b'', bytes(32),
                                    self.unlocked_properties())

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
