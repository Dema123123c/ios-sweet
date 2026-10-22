#!/usr/bin/env python3
"""Build a standalone diagnostic Image; never accesses a phone."""
import argparse
import gzip
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path


def build(out, cc='clang', qemu=False):
    source = Path(__file__).resolve().parent
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(cc) or str(Path(cc).resolve())
    suffix = '.exe' if Path(compiler).suffix == '.exe' else ''
    tools = Path(compiler).parent
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
             '-Wall', '-Wextra', '-Werror', f'-DDIAG_QEMU={int(qemu)}']
    objects = []
    for name in ['start.S', 'support.c', 'diag.c']:
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
                'native_boot_tested': False, 'text_offset': '0x80000',
                'image_flags': image_flags}
    (out / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, indent=2))
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--qemu', action='store_true')
    args = parser.parse_args()
    build(args.out, args.cc, args.qemu)
