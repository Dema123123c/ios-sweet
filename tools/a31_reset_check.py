"""Require the actual PSCI instruction in the linked A31 C reset function."""
import struct


def check_kernel_reset(data):
    if len(data) < 32:
        raise ValueError('reset check: truncated Mach-O')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    if (magic, cpu, subtype, kind) != (0xfeedfacf, 0x100000c, 0, 2):
        raise ValueError('reset check: expected plain arm64 executable')
    if not 1 <= count <= 128 or size > len(data) - 32:
        raise ValueError('reset check: command bounds')
    cursor, segments, symtab = 32, [], None
    for _ in range(count):
        if cursor + 8 > 32 + size:
            raise ValueError('reset check: command header bounds')
        command, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or length % 8 or length > 32 + size - cursor:
            raise ValueError('reset check: command bounds')
        if command == 0x19:
            if length < 72:
                raise ValueError('reset check: segment bounds')
            va, memory, offset, file_size = struct.unpack_from('<4Q', data, cursor + 24)
            protection = struct.unpack_from('<I', data, cursor + 60)[0]
            if offset > len(data) or file_size > len(data) - offset:
                raise ValueError('reset check: segment data bounds')
            if protection & 4:
                if file_size > memory:
                    raise ValueError('reset check: executable segment memory bounds')
                segments.append((va, offset, file_size))
        elif command == 2:
            if length != 24 or symtab is not None:
                raise ValueError('reset check: symbol-table command')
            symtab = struct.unpack_from('<4I', data, cursor + 8)
        cursor += length
    if cursor != 32 + size or symtab is None:
        raise ValueError('reset check: symbol table missing')
    offset, count, strings, string_size = symtab
    if count > 1000000 or offset > len(data) or count * 16 > len(data) - offset or strings > len(data) or string_size > len(data) - strings:
        raise ValueError('reset check: symbol/string bounds')
    symbols = []
    for i in range(count):
        index, type_, section, desc, address = struct.unpack_from('<IBBHQ', data, offset + 16 * i)
        if type_ & 0xe0 or type_ & 0x0e != 0x0e:
            continue
        if index >= string_size:
            raise ValueError('reset check: symbol name bounds')
        end = data.find(b'\0', strings + index, strings + string_size)
        if end < 0:
            raise ValueError('reset check: unterminated symbol name')
        symbols.append((data[strings + index:end], address, section))
    matches = [(address, section) for name, address, section in symbols if name == b'_a31_return']
    if len(matches) != 1:
        raise ValueError('reset check: unique a31_return function missing')
    start, section = matches[0]
    segments = [s for s in segments if s[0] <= start < s[0] + s[2]]
    if len(segments) != 1:
        raise ValueError('reset check: function not in executable file data')
    va, offset, length = segments[0]
    end = min([address for _, address, sect in symbols if sect == section and address > start] + [va + length, start + 4096])
    function = data[offset + start - va:offset + end - va]
    sequence = struct.pack('<III', 0xd5033f9f, 0xd5033fdf, 0xd4000003)
    positions = [i for i in range(0, len(function) - 11, 4) if function[i:i + 12] == sequence]
    if len(positions) != 1:
        raise ValueError('reset check: a31_return must contain DSB / ISB / SMC, not a comment-truncated asm string')
    return {'function_va': hex(start), 'smc_va': hex(start + positions[0] + 8),
            'sequence': ['DSB SY', 'ISB', 'SMC #0'], 'machine_code_verified': True}
