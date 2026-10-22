#!/usr/bin/env python3
"""Build an A31 CPU/RAM-disk ADT. Requires the A31 kernel target, not SWEET."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

import adt
import mkadt
from a31_fdt import describe, parse, reg, strings


def replace(node, name, value):
    node.props = [(k, f, v) for k, f, v in node.props if k != name]
    node.props.append((name, 0, value))


def child(node, name):
    return next(n for n in node.children if dict((k, v) for k, f, v in n.props)['name'] == name.encode() + b'\0')


def validate_memory(data, iomem, base, size):
    if base % 0x2000000 or size % 0x4000 or size < 64 * 1024 * 1024:
        raise ValueError('RAM base must be 32 MiB aligned; size must be 16 KiB aligned and >= 64 MiB')
    end = base + size
    if base < 0 or end >= 1 << 40 or end <= base:
        raise ValueError('invalid 40-bit RAM extent')
    board = describe(data)
    if not any(base >= start and end <= start + length for start, length in board['memory']):
        raise ValueError('requested extent is outside the live FDT memory banks')
    ranges = [(int(a, 16), int(b, 16) + 1) for a, b in re.findall(r'^([0-9a-fA-F]+)-([0-9a-fA-F]+) : System RAM$', iomem, re.M)]
    if not any(base >= lo and end <= hi for lo, hi in ranges):
        raise ValueError('requested extent must fit one live /proc/iomem System RAM range')
    reserved = [(entry['path'], start, length) for entry in board['reserved'] for start, length in entry['reg']]
    reserved += [('FDT memreserve', start, length) for start, length in board['memreserve']]
    for name, start, length in reserved:
        if length and base < start + length and end > start:
            raise ValueError('requested extent overlaps ' + name)
    return board


def build(data, iomem, base, size):
    board = validate_memory(data, iomem, base, size)
    nodes, _ = parse(data)
    cpu_paths = [p for p, props in nodes.items() if props.get('device_type') == b'cpu\0' and reg(nodes, p)[0][0] == 0]
    if len(cpu_paths) != 1 or 'arm,cortex-a55' not in strings(nodes[cpu_paths[0]].get('compatible', b'')):
        raise ValueError('expected one boot Cortex-A55 at MPIDR affinity 0')
    frequency = board['timer']['frequency_hz']
    if len(frequency) != 1 or frequency[0] != 13000000 or board['timer']['virtual_intid'] != 27:
        raise ValueError('unexpected MT6768 timer description')
    if board.get('psci', {}).get('method') != ['smc']:
        raise ValueError('expected PSCI via SMC')
    # Reuse Apple's tree serialization and the generic CPU properties only.
    root = mkadt.build(qemu=True)
    root.children = [n for n in root.children if dict((k, v) for k, f, v in n.props)['name'] != b'sweet-fbcon\0']
    replace(root, 'compatible', b'D22AP\0iPhone10,3\0samsung,a31\0mediatek,MT6768\0AppleARM\0')
    chosen = child(root, 'chosen')
    managed = size - mkadt.PANIC_LOG_SIZE
    replace(chosen, 'dram-base', mkadt.u64(base))
    replace(chosen, 'dram-size', mkadt.u64(managed))
    for key in ['firmware-version', 'system-firmware-version']:
        replace(chosen, key, b'a31-bringup\0')
    replace(child(root, 'pram'), 'reg', mkadt.u64(base + managed, mkadt.PANIC_LOG_SIZE))
    cpu = child(child(root, 'cpus'), 'cpu0')
    replace(cpu, 'compatible', b'arm,cortex-a55\0ARM,v8\0')
    for key in ['timebase-frequency', 'peripheral-frequency', 'fixed-frequency']:
        replace(cpu, key, mkadt.u32(frequency[0]))
    replace(cpu, 'clock-frequency', mkadt.u32(struct.unpack('>I', nodes[cpu_paths[0]]['clock-frequency'])[0]))
    cpu.props = [(k, f, v) for k, f, v in cpu.props if k not in ['memory-frequency', 'bus-frequency']]
    armio = child(root, 'arm-io')
    armio.children = [n for n in armio.children if dict((k, v) for k, f, v in n.props)['name'] != b'disp0\0']
    gic = child(armio, 'gic')
    regions = board['gic']['reg']
    if len(regions) < 2 or any(address < mkadt.SOC_BASE for address, length in regions[:2]):
        raise ValueError('invalid GIC register windows')
    replace(gic, 'reg', mkadt.u64(regions[0][0] - mkadt.SOC_BASE, regions[0][1],
                                regions[1][0] - mkadt.SOC_BASE, regions[1][1]))
    replace(gic, 'virtual-timer-intid', mkadt.u32(27))
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-fdt', type=Path, required=True)
    parser.add_argument('--iomem', type=Path, required=True)
    parser.add_argument('--dram-base', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--dram-size', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = args.live_fdt.read_bytes()
    blob = adt.serialize(build(data, args.iomem.read_text(), args.dram_base, args.dram_size))
    args.out.write_bytes(blob)
    manifest = {'target': 'A31', 'status': 'initial CPU/RAM-disk ADT; no hardware boot validation',
                'live_fdt_sha256': hashlib.sha256(data).hexdigest(),
                'adt_sha256': hashlib.sha256(blob).hexdigest(), 'dram_base': hex(args.dram_base),
                'dram_size_including_panic_log': hex(args.dram_size), 'cpus': 1,
                'storage_driver': None, 'display_driver': None, 'input_driver': None}
    args.out.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(args.out, len(blob), 'bytes; A31 target only; no flash image generated')


if __name__ == '__main__':
    main()
