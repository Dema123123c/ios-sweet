#!/usr/bin/env python3
"""Inspect the A31's Linux FDT without inventing an XNU memory layout."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def cells(data):
    if len(data) % 4:
        raise ValueError('property is not a sequence of 32-bit cells')
    return list(struct.unpack('>%dI' % (len(data) // 4), data))


def strings(data):
    return data.rstrip(b'\0').decode('ascii', errors='replace').split('\0')


def parse(data):
    if len(data) < 40:
        raise ValueError('truncated FDT header')
    magic, total, start, names, reserve, version, last, boot, name_size, size = struct.unpack_from('>10I', data)
    if magic != 0xd00dfeed or version < 17 or last > 17:
        raise ValueError('expected an FDT version 17 compatible header')
    if total > len(data) or start < 40 or names < 40 or reserve < 40 or reserve > total - 16:
        raise ValueError('invalid FDT offsets')
    if start + size > total or names + name_size > total:
        raise ValueError('FDT block outside totalsize')
    names_blob = data[names:names + name_size]
    pos, end, stack, nodes, finished = start, start + size, [], {}, False
    reservations = []
    while reserve + 16 <= total:
        address, length = struct.unpack_from('>QQ', data, reserve)
        reserve += 16
        if not address and not length:
            break
        reservations.append([address, length])
    else:
        raise ValueError('unterminated FDT reservation table')

    def take(length):
        nonlocal pos
        if length < 0 or pos + length > end:
            raise ValueError('truncated FDT structure')
        result = data[pos:pos + length]
        pos += length
        return result

    while pos < end:
        token, = struct.unpack('>I', take(4))
        if token == 1:
            stop = data.find(b'\0', pos, end)
            if stop < 0:
                raise ValueError('unterminated FDT node name')
            name = take(stop - pos + 1)[:-1].decode('ascii')
            pos = (pos + 3) & ~3
            if '/' in name or not stack and (nodes or name):
                raise ValueError('invalid FDT root or node name')
            stack.append(name)
            path = '/' + '/'.join(stack[1:])
            if path in nodes:
                raise ValueError('duplicate FDT node')
            nodes[path] = {}
        elif token == 2:
            if not stack:
                raise ValueError('unbalanced FDT END_NODE')
            stack.pop()
        elif token == 3:
            length, offset = struct.unpack('>II', take(8))
            if not stack or offset >= len(names_blob):
                raise ValueError('invalid FDT property')
            stop = names_blob.find(b'\0', offset)
            if stop < 0:
                raise ValueError('unterminated FDT property name')
            name = names_blob[offset:stop].decode('ascii')
            props = nodes['/' + '/'.join(stack[1:])]
            if name in props:
                raise ValueError('duplicate FDT property')
            props[name] = take(length)
            pos = (pos + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            if stack or '/' not in nodes:
                raise ValueError('unbalanced FDT tree')
            finished = True
            break
        else:
            raise ValueError('unknown FDT token %d' % token)
    if not finished:
        raise ValueError('missing FDT_END')
    return nodes, reservations


def reg(nodes, path):
    parent = path.rsplit('/', 1)[0] or '/'
    props = nodes[parent]
    ac = cells(props.get('#address-cells', struct.pack('>I', 2)))[0]
    sc = cells(props.get('#size-cells', struct.pack('>I', 1)))[0]
    values = cells(nodes[path].get('reg', b''))
    if ac not in (1, 2) or sc not in (0, 1, 2) or len(values) % (ac + sc):
        raise ValueError('unsupported or invalid reg at ' + path)
    def number(v):
        value = 0
        for cell in v:
            value = value << 32 | cell
        return value
    return [[number(values[i:i + ac]), number(values[i + ac:i + ac + sc])]
            for i in range(0, len(values), ac + sc)]


def describe(data):
    nodes, reservations = parse(data)
    compatible = strings(nodes['/'].get('compatible', b''))
    if not any('mt6768' in value.lower() for value in compatible):
        raise ValueError('FDT is not for MediaTek MT6768')
    report = {'source_sha256': hashlib.sha256(data).hexdigest(),
              'status': 'hardware description only; not a bootable iOS port',
              'compatible': compatible, 'memory': [], 'reserved': [], 'cpus': []}
    for path, props in nodes.items():
        comp = strings(props.get('compatible', b''))
        if props.get('device_type') == b'memory\0':
            report['memory'].extend(reg(nodes, path))
        if path.startswith('/reserved-memory/'):
            item = {'path': path, 'reg': reg(nodes, path)}
            for key in ['size', 'alignment', 'alloc-ranges']:
                if key in props:
                    item[key] = cells(props[key])
            report['reserved'].append(item)
        if props.get('device_type') == b'cpu\0':
            report['cpus'].append({'path': path, 'compatible': comp, 'reg': reg(nodes, path),
                                   'enable-method': strings(props.get('enable-method', b''))})
        if 'arm,gic-v3' in comp:
            report['gic'] = {'path': path, 'reg': reg(nodes, path)}
        if 'arm,armv8-timer' in comp:
            interrupts = cells(props.get('interrupts', b''))
            if len(interrupts) < 9 or interrupts[6] != 1 or interrupts[7] >= 16:
                raise ValueError('virtual timer is not a GIC PPI')
            report['timer'] = {'virtual_intid': 16 + interrupts[7],
                               'frequency_hz': cells(props.get('clock-frequency', b'')),
                               'interrupts': interrupts}
        if path == '/psci':
            report['psci'] = {'compatible': comp, 'method': strings(props.get('method', b''))}
        if any('msdc' in value for value in comp):
            report.setdefault('storage_controllers', []).append({'path': path, 'reg': reg(nodes, path)})
    report['memreserve'] = reservations
    report['live_display_handoff_present'] = any(
        key in nodes.get('/chosen', {}) for key in ['atag,videolfb', 'linux,framebuffer'])
    report['memory_selection'] = 'not selected: static and dynamic reservations require review'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fdt', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = json.dumps(describe(args.fdt.read_bytes()), indent=2)
    if args.out:
        args.out.write_text(result + '\n', encoding='utf-8')
    else:
        print(result)
