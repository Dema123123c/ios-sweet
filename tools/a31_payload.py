#!/usr/bin/env python3
"""Build an A31 XNU payload for preparation/readback checks. Never flashes or jumps."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import adt
import mkpayload


def validate_adt(data, base, memory_size):
    nodes, chosen = 0, 0
    def walk(cursor, depth):
        nonlocal nodes, chosen
        nodes += 1
        if depth > 16 or nodes > 256 or cursor + 8 > len(data):
            raise ValueError('ADT node bounds')
        properties, children = struct.unpack_from('<II', data, cursor)
        cursor += 8
        if properties > 128 or children > 128:
            raise ValueError('ADT node counts')
        values = {}
        for _ in range(properties):
            if cursor + 36 > len(data) or b'\0' not in data[cursor:cursor + 32]:
                raise ValueError('ADT property header')
            name = bytes(data[cursor:cursor + 32].split(b'\0')[0])
            size = struct.unpack_from('<I', data, cursor + 32)[0] & 0x7fffffff
            cursor += 36
            padded = (size + 3) & ~3
            if padded > len(data) - cursor or name in values:
                raise ValueError('ADT property bounds or duplicate')
            values[name] = data[cursor:cursor + size]
            cursor += padded
        name = values.get(b'name', b'')
        if not 1 <= len(name) <= 64 or name[-1:] != b'\0':
            raise ValueError('ADT name')
        if depth == 1 and name == b'chosen\0':
            chosen += 1
            if (values.get(b'dram-base'), values.get(b'dram-size')) != (
                    struct.pack('<Q', base), struct.pack('<Q', memory_size)):
                raise ValueError('ADT RAM mismatch')
        for _ in range(children): cursor = walk(cursor, depth + 1)
        return cursor
    if walk(0, 0) != len(data) or chosen != 1:
        raise ValueError('ADT trailing data or chosen count')


def inspect_payload(data):
    if not 0x2a8 <= len(data) <= 24 * 1024 * 1024 or data[:8] != b'SWEETXNU':
        raise ValueError('payload header bounds or magic')
    version, count = struct.unpack_from('<II', data, 8)
    if version != 1 or not 1 <= count <= 32 or 0x2a8 + 32 * count > len(data):
        raise ValueError('payload segment count')
    virtual, entry, tree_offset, tree_size, kernel_end, base, size = struct.unpack_from('<7Q', data, 16)
    if (base, size) != (0x100000000, 0x3fd00000):
        raise ValueError('payload RAM policy')
    if virtual < 0xffff000000000000 or virtual % 0x2000000 or virtual + size >= 1 << 64:
        raise ValueError('payload virtual base')
    if (tree_offset % 8 or tree_offset < 0x2a8 + 32 * count or
            not 8 <= tree_size <= 0x100000 or tree_offset + tree_size > len(data)):
        raise ValueError('payload ADT bounds')
    if b'\0' not in data[0x48:0x2a8]: raise ValueError('payload command line')
    destinations, sources, file_entry, highest = [], [], False, 0
    for i in range(count):
        va, length, offset, file_size = struct.unpack_from('<4Q', data, 0x2a8 + 32 * i)
        if va < virtual or va % 0x4000 or not length or va - virtual + length > size or file_size > length:
            raise ValueError('payload destination bounds')
        if offset % 8 or offset < 0x2a8 + 32 * count or offset + file_size > len(data):
            raise ValueError('payload source bounds')
        if file_size and offset < tree_offset + tree_size and tree_offset < offset + file_size:
            raise ValueError('payload source overlaps ADT')
        if any(va < end and start < va + length for start, end in destinations):
            raise ValueError('payload destination overlap')
        if any(file_size and offset < end and start < offset + file_size for start, end in sources):
            raise ValueError('payload source overlap')
        destinations.append((va, va + length))
        if file_size: sources.append((offset, offset + file_size))
        file_entry |= entry % 4 == 0 and va <= entry < va + file_size
        highest = max(highest, va - virtual + length)
    highest = (highest + 0x3fff) & ~0x3fff
    if not file_entry or kernel_end != virtual + highest:
        raise ValueError('payload entry or kernel end')
    args_offset = (highest + tree_size + 0x3fff) & ~0x3fff
    if args_offset + 0x4000 > size: raise ValueError('payload boot args outside RAM')
    validate_adt(data[tree_offset:tree_offset + tree_size], base, size)
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'segments': count,
            'entry_pa': hex(base + entry - virtual), 'boot_args_pa': hex(base + args_offset),
            'top': hex(base + args_offset + 0x4000), 'kernel_jump_enabled': False}


def validate_kernel(data):
    if len(data) < 32:
        raise ValueError('truncated Mach-O header')
    magic, cpu, subtype, kind, count, length, flags, reserved = struct.unpack_from('<8I', data)
    if (magic, cpu, subtype, kind) != (0xfeedfacf, 0x100000c, 0, 2):
        raise ValueError('expected a plain arm64 executable A31 kernel (no arm64e)')
    if not 1 <= count <= 128 or length > len(data) - 32:
        raise ValueError('Mach-O command bounds')
    cursor, entry, text, spans, executable = 32, None, None, [], []
    for _ in range(count):
        if cursor + 8 > 32 + length:
            raise ValueError('truncated load command')
        command, size = struct.unpack_from('<II', data, cursor)
        if size < 8 or size % 8 or size > 32 + length - cursor:
            raise ValueError('invalid load-command size')
        if command == mkpayload.LC_SEGMENT_64:
            if size < 72:
                raise ValueError('truncated segment command')
            name = data[cursor + 8:cursor + 24].split(b'\0')[0]
            va, memory, offset, file_size = struct.unpack_from('<4Q', data, cursor + 24)
            maximum, initial, sections, segflags = struct.unpack_from('<4I', data, cursor + 56)
            if 72 + sections * 80 > size or offset > len(data) or file_size > len(data) - offset:
                raise ValueError('segment source bounds')
            if memory:
                if file_size > memory or va % 0x4000 or va + memory >= 1 << 64:
                    raise ValueError('segment destination bounds')
                if any(va < end and start < va + memory for start, end in spans):
                    raise ValueError('overlapping kernel segments')
                spans.append((va, va + memory))
                if initial & 4:
                    executable.append((va, va + file_size))
            if name == b'__TEXT':
                if text is not None or offset or not memory:
                    raise ValueError('invalid kernel __TEXT')
                text = va
        elif command == mkpayload.LC_UNIXTHREAD:
            if size != 288 or struct.unpack_from('<II', data, cursor + 8) != (6, 68) or entry is not None:
                raise ValueError('unexpected arm64 entry state')
            entry = struct.unpack_from('<Q', data, cursor + 272)[0]
        elif command == mkpayload.LC_DYLD_CHAINED_FIXUPS:
            raise ValueError('this initial A31 payload requires a kernel without chained fixups')
        cursor += size
    if cursor != 32 + length or text is None or entry is None or entry % 4:
        raise ValueError('incomplete Mach-O commands or entry')
    if not any(start <= entry < end for start, end in executable):
        raise ValueError('kernel entry is not executable file-backed code')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'entry': hex(entry), 'text': hex(text), 'architecture': 'arm64', 'segments': len(spans)}


ENTRY_MARKERS = (b'[A31-XNU] ENTRY MMU-OFF v1', b'[A31-XNU] ENTRY-CHECK PASS',
                 b'[A31-XNU] RECOVERY REQUEST', b'XNU_SCTLR_EL1=')


def validate_entry_checkpoint(data):
    result = validate_kernel(data)
    if any(marker not in data for marker in ENTRY_MARKERS):
        raise ValueError('A31 entry-check code missing from linked kernel')
    return result


def build(kernel, tree, output, command_line, entry_checkpoint=False):
    report = validate_kernel(kernel.read_bytes())
    if entry_checkpoint:
        report = validate_entry_checkpoint(kernel.read_bytes())
    blob = tree.read_bytes()
    root, end = adt.parse(blob)
    if end != len(blob) or b'samsung,a31\0' not in (root.prop('compatible') or b''):
        raise ValueError('expected complete A31 ADT')
    if mkpayload.adt_dram(blob) != (0x100000000, 0x3fd00000):
        raise ValueError('unexpected A31 managed RAM extent')
    if len(command_line.encode('ascii')) >= mkpayload.BOOT_LINE_LENGTH or '\0' in command_line:
        raise ValueError('command line must be ASCII, NUL-free and shorter than 608 bytes')
    payload, packed = mkpayload.build(str(kernel), str(tree), command_line)
    checked = inspect_payload(payload)
    if b'[A31-XNU] VM-TABLES-CHECK PASS' in kernel.read_bytes():
        if struct.unpack_from('<Q', payload, 16)[0] != 0xfffffe0006000000:
            raise ValueError('VM diagnostic relay requires the fixed A31 virtual base')
    if output.exists():
        raise FileExistsError('use a new payload path')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    report.update({'payload_sha256': hashlib.sha256(payload).hexdigest(),
                   'payload_bytes': len(payload), 'adt_sha256': hashlib.sha256(blob).hexdigest(),
                   'mode': ('XNU entry-check payload; requires separately gated entry loader' if entry_checkpoint
                            else 'prepare/readback only; kernel jump disabled'), 'packed': packed,
                   'loader_validation': checked})
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def fixture(base=0x50000000, size=0x4000000, entry_code=None):
    root, chosen = adt.Node(), adt.Node()
    root.props = [('name', 0, b'device-tree\0')]
    chosen.props = [('name', 0, b'chosen\0'), ('dram-base', 0, struct.pack('<Q', base)),
                    ('dram-size', 0, struct.pack('<Q', size))]
    root.children = [chosen]
    tree = adt.serialize(root)
    out = bytearray(0x2e8)
    virtual = 0xfffffe0006000000
    first = len(out)
    code = b'KERNEL-ENTRY!' if entry_code is None else entry_code
    if not 1 <= len(code) < 0x4000:
        raise ValueError('fixture entry must fit one page')
    out += code + bytes((-len(code)) % 8)
    second = len(out)
    out += b'SECOND!!'
    tree_offset = len(out)
    out += tree
    struct.pack_into('<8sII7Q', out, 0, b'SWEETXNU', 1, 2, virtual, virtual + 0x4000,
                     tree_offset, len(tree), virtual + 0xc000, base, size)
    out[0x48:0x50] = b'cpus=1\0\0'
    struct.pack_into('<4Q', out, 0x2a8, virtual + 0x4000, 0x4000, first, len(code))
    struct.pack_into('<4Q', out, 0x2c8, virtual + 0x8000, 0x4000, second, 8)
    return bytes(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', required=True, type=Path)
    parser.add_argument('--adt', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--cmdline', default='debug=0xc serial=3 cpus=1 keepsyms=1')
    parser.add_argument('--entry-checkpoint', action='store_true', help='require compiled A31 entry/return checkpoint markers')
    args = parser.parse_args()
    print(json.dumps(build(args.kernel, args.adt, args.out, args.cmdline, args.entry_checkpoint), indent=2))
