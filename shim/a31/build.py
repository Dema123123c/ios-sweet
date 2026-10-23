#!/usr/bin/env python3
"""Build a standalone diagnostic Image; never accesses a phone."""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path


def build(out, cc='clang', qemu=False, entry_fault=False, payload_check=False, entry_check_sha=None, entry_trap=False, trap_offset=0, trap_instruction=0):
    if trap_offset:
        if not entry_trap or trap_offset != 0x1c78 or trap_instruction not in (0xf0ffffe0, 0xd503201f):
            raise ValueError('only the audited pre-VBAR checkpoint is supported')
        if not qemu and (trap_instruction != 0xf0ffffe0 or entry_check_sha != '8d60696d9394a073bd911ca301f32b696ffa949c12dbac573ddf5773b36c030d'):
            raise ValueError('native pre-VBAR checkpoint requires exact audited V8 payload')
    if entry_trap and entry_check_sha is None:
        raise ValueError('entry trap requires an exact payload SHA-256')
    if entry_fault and not qemu:
        raise ValueError('entry fault injection is QEMU-only')
    if entry_check_sha is not None:
        if not re.fullmatch(r'[0-9a-f]{64}', entry_check_sha) or entry_fault:
            raise ValueError('entry checkpoint requires one exact payload SHA-256 and no injected fault')
        payload_check = True
    source = Path(__file__).resolve().parent
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(cc) or str(Path(cc).resolve())
    suffix = '.exe' if Path(compiler).suffix == '.exe' else ''
    tools = Path(compiler).parent
    try:
        build_id = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                           text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.run(['git', '-C', str(source), 'diff', '--quiet', 'HEAD', '--', '.'],
                               stderr=subprocess.DEVNULL).returncode
        if dirty:
            build_id += '-dirty'
    except (FileNotFoundError, subprocess.CalledProcessError):
        build_id = 'unversioned'
    objcopy = tools / ('llvm-objcopy' + suffix)
    readelf = tools / ('llvm-readelf' + suffix)
    if not objcopy.is_file():
        objcopy = Path(shutil.which('llvm-objcopy') or '')
    if not readelf.is_file():
        readelf = Path(shutil.which('llvm-readelf') or '')
    flags = ['--target=aarch64-none-elf', '-march=armv8-a', '-O2',
             '-ffreestanding', '-nostdlib', '-fno-pic', '-fno-builtin',
             '-fno-stack-protector', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-jump-tables',
             '-mgeneral-regs-only', '-mstrict-align', '-mno-outline-atomics',
             '-Wall', '-Wextra', '-Werror', f'-DDIAG_QEMU={int(qemu)}',
             f'-DDIAG_ENTRY_FAULT={int(entry_fault)}',
             f'-DDIAG_PAYLOAD_CHECK={int(payload_check)}',
             f'-DDIAG_XNU_ENTRY={int(entry_check_sha is not None)}',
             f'-DDIAG_ENTRY_TRAP={int(entry_trap)}',
             f'-DDIAG_TRAP_OFFSET={trap_offset}', f'-DDIAG_TRAP_INSTRUCTION={trap_instruction}U',
             f'-DDIAG_ENTRY_PAYLOAD_SHA="{entry_check_sha or "disabled"}"',
             f'-DDIAG_BUILD_ID="{build_id}"']
    objects = []
    for name in ['start.S', 'support.c', 'payload.c', 'diag.c']:
        obj = out / (Path(name).stem + '.o')
        subprocess.run([compiler, *flags, '-c', str(source / name), '-o', str(obj)], check=True)
        objects.append(obj)
        if name.endswith('.c'):
            relocations = subprocess.check_output([str(readelf), '-r', str(obj)], text=True)
            if 'R_AARCH64_ABS' in relocations:
                raise ValueError(f'{name}: absolute data relocation prevents relocation-free boot')
    elf = out / 'diag.elf'
    subprocess.run([compiler, *flags, '-fuse-ld=lld', '-static',
                    '-Wl,--build-id=none', '-Wl,-z,max-page-size=16384',
                    '-Wl,-T,' + str(source / 'shim.ld'),
                    '-Wl,-Map,' + str(out / 'diag.map'),
                    *map(str, objects), '-o', str(elf)], check=True)
    image = out / 'Image'
    subprocess.run([str(objcopy), '-O', 'binary', str(elf), str(image)], check=True)
    data = image.read_bytes()
    offset, size, image_flags = struct.unpack_from('<QQQ', data, 8)
    if data[56:60] != b'ARM\x64' or offset != 0x80000 or image_flags != 12:
        raise ValueError('unexpected arm64 Linux Image header')
    if size < len(data) or size > 0x80000 or size % 16384:
        raise ValueError('unexpected diagnostic memory footprint')
    data += bytes(size - len(data))
    image.write_bytes(data)
    (out / 'Image.gz').write_bytes(gzip.compress(data, mtime=0))
    metadata = {'kind': 'A31 diagnostic shim, not XNU', 'qemu': qemu,
                'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'native_boot_tested': False, 'build_id': build_id, 'text_offset': '0x80000',
                'image_flags': image_flags, 'entry_fault_test': entry_fault,
                'early_entry_log': True}
    if payload_check:
        metadata['payload_mode'] = 'prepare-only; no XNU jump'
        metadata['kernel_jump_enabled'] = False
    if entry_check_sha is not None:
        metadata['kind'] = 'A31 XNU entry-check loader; stops at first arm_init checkpoint'
        metadata['payload_mode'] = 'XNU entry checkpoint; stop before CPU/VM startup'
        metadata['kernel_jump_enabled'] = True
        metadata['expected_payload_sha256'] = entry_check_sha
    if entry_trap:
        metadata['kind'] = 'A31 physical entry BRK control; no XNU instructions'
        metadata['payload_mode'] = 'physical entry BRK control; no XNU instructions'
        metadata['entry_trap_control'] = True
    if trap_offset:
        metadata['kind'] = metadata['payload_mode'] = 'early XNU assembler BRK checkpoint'
        metadata['trap_offset'] = trap_offset
        metadata['trap_instruction'] = trap_instruction
    if not qemu:
        metadata['recovery_return'] = {
            'method': 'Samsung SRAM recovery flags + PSCI SYSTEM_RESET via SMC',
            'recovery_sha256': 'd8a89533d039c79618b4dffcdc5cdec5949534020b2011088a02b1899bbcd890',
            'sram_base': '0x10dc00', 'sram_bytes': 0x800,
            'hardware_tested': False}
        metadata['pstore_console'] = {'base': '0x4d05f000', 'bytes': 0x40000,
                                     'recovery_layout_profile_required': True}
        metadata['watchdog'] = {'base': '0x10007000', 'action': 'keyed clear of EN bit; readback required',
                                'hardware_tested': False}
    (out / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, indent=2))
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--qemu', action='store_true')
    parser.add_argument('--entry-fault-test', action='store_true',
                        help='QEMU only: inject an undefined instruction after the early log')
    parser.add_argument('--payload-check', action='store_true',
                        help='validate/copy the initrd XNU payload, verify readback, then return; no jump')
    parser.add_argument('--entry-check-sha', help='enable entry only for a package with this exact payload SHA-256')
    parser.add_argument('--entry-trap', action='store_true', help='replace the copied entry instruction in RAM with BRK; never execute XNU')
    parser.add_argument('--trap-offset', type=lambda s: int(s, 0), default=0)
    parser.add_argument('--trap-instruction', type=lambda s: int(s, 0), default=0)
    args = parser.parse_args()
    build(args.out, args.cc, args.qemu, args.entry_fault_test, args.payload_check, args.entry_check_sha, args.entry_trap, args.trap_offset, args.trap_instruction)
