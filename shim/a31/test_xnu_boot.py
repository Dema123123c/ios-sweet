#!/usr/bin/env python3
"""Run the mirrored XNU fault assembly with SP=0; never connects to a phone."""
import argparse
import json
import shutil
import struct
import subprocess
from pathlib import Path


def run(out, cc='clang', qemu='qemu-system-aarch64', compile_only=False):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    compiler = Path(shutil.which(cc) or cc).resolve()
    objcopy = compiler.with_name('llvm-objcopy' + compiler.suffix)
    if not objcopy.is_file(): objcopy = Path(shutil.which('llvm-objcopy') or 'llvm-objcopy')
    reports = []
    cases = [(0, 0, 1), (1, 0, 1), (0, 0, 0), (1, 0, 0)] + [(0, bad, 1) for bad in range(1, 7)]
    for mmu, bad, source_sp in cases:
        case = out / (f'mmu{mmu}-bad{bad}' + ('-sp0' if not source_sp else ''))
        case.mkdir(exist_ok=True)
        flags = ['--target=aarch64-none-elf', '-march=armv8-a', '-O2', '-ffreestanding',
                 '-nostdlib', '-fno-builtin', '-fno-stack-protector', '-mgeneral-regs-only',
                 '-mno-outline-atomics', '-fno-pic', '-Wall', '-Wextra', '-Werror',
                 f'-DBOOT_MMU={mmu}', f'-DBOOT_BAD={bad}', f'-DBOOT_SOURCE_SP={source_sp}']
        objects = []
        for name in ['xnu_boot_test.S', 'xnu_boot_test.c']:
            obj = case / (name + '.o')
            subprocess.run([str(compiler), *flags, '-c', str(source / name), '-o', str(obj)], check=True)
            objects.append(str(obj))
        elf, image = case / 'test.elf', case / 'Image'
        subprocess.run([str(compiler), *flags, '-fuse-ld=lld', '-static',
                        '-Wl,--build-id=none', '-Wl,-z,max-page-size=16384',
                        '-Wl,-T,' + str(source / 'xnu_boot_test.ld'), *objects, '-o', str(elf)], check=True)
        subprocess.run([str(objcopy), '-O', 'binary', str(elf), str(image)], check=True)
        data = image.read_bytes()
        offset, size, image_flags = struct.unpack_from('<QQQ', data, 8)
        if data[56:60] != b'ARM\x64' or offset != 0x80000 or image_flags != 12 or not len(data) <= size < 0x80000:
            raise ValueError('test Image header mismatch')
        image.write_bytes(data + bytes(size - len(data)))
        if compile_only: continue
        for virtualization, entry_el in [('off', 1), ('on', 2)]:
            command = [qemu, '-machine', f'virt,gic-version=3,virtualization={virtualization}',
                       '-cpu', 'max', '-m', '512M', '-smp', '1', '-display', 'none',
                       '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot',
                       '-semihosting-config', 'enable=on,target=native', '-kernel', str(image)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired as error:
                (case / f'el{entry_el}.log').write_bytes((error.stdout or b'') + (error.stderr or b''))
                raise
            text = result.stdout + result.stderr
            (case / f'el{entry_el}.log').write_text(text, encoding='utf-8')
            print(f'MMU={mmu} bad={bad} source_SP={source_sp} incoming_EL={entry_el}: {text.strip()}')
            if result.returncode or 'A31 BOOT FAULT TEST PASS' not in text or 'FAIL ' in text:
                raise RuntimeError('boot fault assembly test failed')
            reports.append({'mmu_at_fault': mmu, 'bad_header_case': bad, 'incoming_el': entry_el,
                            'result': 'pass', 'stack_pointer_at_fault': 0, 'source_sp': source_sp})
    (out / 'results.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--qemu', default='qemu-system-aarch64')
    parser.add_argument('--compile-only', action='store_true')
    args = parser.parse_args()
    run(args.out, args.cc, args.qemu, args.compile_only)
