import contextlib
import io
import struct
import unittest

import adt
from a31_fdt import describe, parse
from mka31adt import build, child, validate_memory


def u32(*n):
    return struct.pack('>%dI' % len(n), *n)


def u64(*n):
    return struct.pack('>%dQ' % len(n), *n)


def fixture(bootargs=None):
    names = bytearray()
    offsets = {}
    tree = bytearray()
    def padded(value):
        return value + b'\0' * (-len(value) % 4)
    def node(name, props, children=()):
        tree.extend(u32(1) + padded(name.encode() + b'\0'))
        for key, value in props.items():
            if key not in offsets:
                offsets[key] = len(names)
                names.extend(key.encode() + b'\0')
            tree.extend(u32(3, len(value), offsets[key]) + padded(value))
        for item in children:
            node(*item)
        tree.extend(u32(2))
    node('', {'compatible': b'mediatek,MT6768\0', '#address-cells': u32(2), '#size-cells': u32(2)}, [
        ('memory', {'device_type': b'memory\0', 'reg': u64(0x40000000, 0x100000000)}),
        ('reserved-memory', {'#address-cells': u32(2), '#size-cells': u32(2)}, [
            ('firmware', {'reg': u64(0x50000000, 0x100000)})]),
        ('cpus', {'#address-cells': u32(1), '#size-cells': u32(0)}, [
            ('cpu@0', {'device_type': b'cpu\0', 'compatible': b'arm,cortex-a55\0',
                       'reg': u32(0), 'clock-frequency': u32(1701000000)})]),
        ('interrupt-controller', {'compatible': b'arm,gic-v3\0',
                                  'reg': u64(0x0c000000, 0x40000, 0x0c040000, 0x200000)}),
        ('timer', {'compatible': b'arm,armv8-timer\0', 'clock-frequency': u32(13000000),
                   'interrupts': u32(1, 13, 8, 1, 14, 8, 1, 11, 8, 1, 10, 8)}),
        ('psci', {'compatible': b'arm,psci-1.0\0', 'method': b'smc\0'}),
    ] + ([('chosen', {'bootargs': bootargs})] if bootargs is not None else []))
    tree.extend(u32(9))
    header = u32(0xd00dfeed, 56 + len(tree) + len(names), 56, 56 + len(tree), 40, 17, 16, 0, len(names), len(tree))
    return header + bytes(16) + tree + names


class A31Tests(unittest.TestCase):
    def test_real_address_and_timer_cell_encoding(self):
        board = describe(fixture())
        self.assertEqual(board['gic']['reg'][1], [0x0c040000, 0x200000])
        self.assertEqual(board['timer']['virtual_intid'], 27)
        self.assertEqual(board['memory'], [[0x40000000, 0x100000000]])

    def test_rejects_truncated_blob(self):
        with self.assertRaises(ValueError):
            parse(fixture()[:-1])

    def test_rejects_out_of_bounds_structure(self):
        data = bytearray(fixture())
        struct.pack_into('>I', data, 8, len(data) - 1)
        with self.assertRaises(ValueError):
            parse(data)

    def test_rejects_wrong_soc(self):
        with self.assertRaises(ValueError):
            describe(fixture().replace(b'MT6768', b'MT9999'))

    def test_rejects_firmware_overlap_even_if_linux_says_ram(self):
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            validate_memory(fixture(), '40000000-13fffffff : System RAM', 0x50000000, 0x4000000)

    def test_rejects_iomem_gap(self):
        with self.assertRaisesRegex(ValueError, 'System RAM'):
            validate_memory(fixture(), '100000000-101ffffff : System RAM', 0x100000000, 0x4000000)

    def test_rejects_unaligned_memory(self):
        with self.assertRaisesRegex(ValueError, 'aligned'):
            validate_memory(fixture(), '40000000-13fffffff : System RAM', 0x100004000, 0x4000000)

    def test_a31_tree_omits_qualcomm_devices(self):
        with contextlib.redirect_stderr(io.StringIO()):
            tree = build(fixture(), '100000000-13fffffff : System RAM', 0x100000000, 0x3fe00000)
        parsed, _ = adt.parse(adt.serialize(tree))
        self.assertNotIn('sweet-ufs', [n.name for n in parsed.children])
        self.assertNotIn('sweet-fbcon', [n.name for n in parsed.children])
        self.assertNotIn('disp0', [n.name for n in child(parsed, 'arm-io').children])
        props = dict((k, v) for k, f, v in parsed.props)
        self.assertIn(b'samsung,a31\0', props['compatible'])
        self.assertNotIn(b'xiaomi', props['compatible'])
        timer = dict((k, v) for k, f, v in child(child(parsed, 'arm-io'), 'gic').props)
        self.assertEqual(timer['virtual-timer-intid'], struct.pack('<I', 27))
        dram = dict((k, v) for k, f, v in child(parsed, 'chosen').props)
        panic = dict((k, v) for k, f, v in child(parsed, 'pram').props)
        self.assertEqual(struct.unpack('<Q', dram['dram-size'])[0], 0x3fd00000)
        self.assertEqual(struct.unpack('<2Q', panic['reg']), (0x13fd00000, 0x100000))


if __name__ == '__main__':
    unittest.main()
