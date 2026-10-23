#!/usr/bin/env python3
"""Observe the linked A31 kernel's real bootstrap in QEMU, never a phone test."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

import adt
import mkpayload
from a31_payload import build, inspect_payload


def bootstrap_checkpoint(kernel, target, post=False, c_entry=False):
    if post and c_entry:
        raise ValueError('select one audited checkpoint')
    data = bytearray(kernel.read_bytes())
    if hashlib.sha256(data).hexdigest() != '3486ac517fce205e62c5d5b3e95de10152850543fb96c6c6a1db9b63618c0c50':
        raise ValueError('bootstrap checkpoint requires exact verified V11 kernel')
    address = 0xfffffe0007ad4fe8 if c_entry else 0xfffffe000748e500 if post else 0xfffffe000748e4f8
    original = 0xd10343ff if c_entry else 0xd2a00600 if post else 0xd5181000
    segments = [s for s in mkpayload.parse_macho(data)['segs']
                if s['vmaddr'] <= address < s['vmaddr'] + s['filesize']]
    if len(segments) != 1:
        raise ValueError('checkpoint not in one file-backed segment')
    segment = segments[0]
    offset = segment['fileoff'] + address - segment['vmaddr']
    if struct.unpack_from('<I', data, offset)[0] != original:
        raise ValueError('checkpoint instruction differs from audited V11 bootstrap')
    struct.pack_into('<I', data, offset, 0xd4214620)
    if target.exists():
        raise FileExistsError(target)
    target.write_bytes(data)
    return {'source_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
            'patched_sha256': hashlib.sha256(data).hexdigest(), 'file_offset': offset,
            'virtual_address': hex(address), 'physical_address': '0x101ad4fe8' if c_entry else '0x10148e500' if post else '0x10148e4f8',
            'phase': 'high-KVA arm_init entry before prologue' if c_entry else 'after MMU enable and ISB' if post else 'before MMU enable',
            'original_instruction': hex(original), 'replacement_instruction': '0xd4214620'}


def run(kernel, out, trap=False, post=False, c_entry=False):
    out.mkdir(parents=True, exist_ok=False)
    checkpoint = None
    if trap or post or c_entry:
        patched = out / 'checkpoint.kernel'
        checkpoint = bootstrap_checkpoint(kernel, patched, post, c_entry)
        kernel = patched
    root, chosen = adt.Node(), adt.Node()
    root.props = [('name', 0, b'device-tree\0'), ('compatible', 0, b'samsung,a31\0')]
    chosen.props = [('name', 0, b'chosen\0'),
                    ('dram-base', 0, struct.pack('<Q', 0x100000000)),
                    ('dram-size', 0, struct.pack('<Q', 0x3fd00000))]
    root.children = [chosen]
    tree = out / 'synthetic.adt'
    tree.write_bytes(adt.serialize(root))
    payload = out / 'xnu.payload'
    build(kernel, tree, payload, 'debug=0xc serial=3 cpus=1 keepsyms=1', entry_checkpoint=True)
    data = payload.read_bytes()
    checked = inspect_payload(data)
    virtual, entry, tree_off, tree_size, end, base, size = struct.unpack_from('<7Q', data, 16)
    files = []

    def load(name, address, blob):
        path = out / name
        path.write_bytes(blob)
        files.extend(['-device', f'loader,file={path},addr={address:#x},force-raw=on'])

    for i in range(struct.unpack_from('<I', data, 12)[0]):
        va, memory, offset, length = struct.unpack_from('<4Q', data, 0x2a8 + i * 32)
        load(f'segment{i}.bin', base + va - virtual, data[offset:offset + length] + bytes(memory - length))
    tree_pa = base + end - virtual
    args_pa, top = int(checked['boot_args_pa'], 16), int(checked['top'], 16)
    load('tree.bin', tree_pa, data[tree_off:tree_off + tree_size])
    args = bytearray(736)
    struct.pack_into('<HH', args, 0, 2, 2)
    struct.pack_into('<4Q', args, 8, virtual, base, size, top)
    struct.pack_into('<QI', args, 96, virtual + tree_pa - base, tree_size)
    args[108:716] = data[0x48:0x2a8]
    struct.pack_into('<Q', args, 728, size)
    load('args.bin', args_pa, args)
    load('ring.bin', 0x4d05f000, struct.pack('<III', 0x43474244, 0, 0))
    entry_pa = int(checked['entry_pa'], 16)
    wrapper = out / 'entry.S'
    wrapper.write_text(f'''.global _start
_start:
    msr daifset, #15
    msr spsel, #1
    ldr x0, =0x40100000
    mov sp, x0
    ldr x0, =13000000
    msr cntfrq_el0, x0
    ldr x0, ={args_pa:#x}
    ldr x1, ={entry_pa:#x}
    br x1
''')
    image = out / 'entry.elf'
    subprocess.run(['clang', '--target=aarch64-none-elf', '-nostdlib', '-fuse-ld=lld',
                    '-Wl,-Ttext=0x40080000', '-Wl,-e,_start', str(wrapper), '-o', str(image)], check=True)
    command = ['qemu-system-aarch64', '-machine', 'virt,gic-version=3,virtualization=off',
               '-cpu', 'max', '-m', '5G', '-smp', '1', '-display', 'none', '-nic', 'none',
               '-serial', f'file:{out / "serial.log"}', '-monitor', 'stdio',
               '-no-reboot', '-kernel', str(image)] + files
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(8)
        log_path = out / 'pstore.bin'
        commands = f'stop\ninfo registers\npmemsave 0x4d05f000 0x40000 "{log_path}"\nquit\n'
        stdout, _ = process.communicate(commands.encode(), timeout=15)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    (out / 'monitor.log').write_bytes(stdout)
    if not log_path.exists():
        raise RuntimeError('QEMU memory capture missing; inspect monitor.log')
    log = log_path.read_bytes()
    magic, start, length = struct.unpack_from('<III', log)
    if magic != 0x43474244 or start > 0x3fff4 or length > 0x3fff4:
        raise RuntimeError('invalid emulated log ring')
    text = (log[12:12 + length] if length < 0x3fff4 else log[12 + start:] + log[12:12 + start]).decode('utf-8', 'replace')
    (out / 'pstore.txt').write_text(text)
    report = {'environment': 'QEMU virt, synthetic ADT; NOT Galaxy A31 hardware',
              'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
              'payload': checked, 'qemu_returncode': process.returncode,
              'wrapper_branches_to_actual_kernel': True,
              'pre_mmu_checkpoint': checkpoint,
              'markers': {marker: marker in text for marker in [
                  'ENTRY MMU-OFF', 'STACKS NEXT', 'TABLES READY', 'MMU ENABLE NEXT',
                  'BOOT EXCEPTION', 'ENTRY-CHECK PASS', 'RECOVERY REQUEST']}}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(text)
    print(json.dumps(report, indent=2))
    required = ['ENTRY MMU-OFF', 'STACKS NEXT', 'TABLES READY', 'MMU ENABLE NEXT',
                'C STAGE 1: arm_init entered (MMU on)', 'ENTRY-CHECK PASS',
                'XNU_CURRENT_EL=0x0000000000000001', 'XNU_CNTFRQ=0x0000000000c65d40']
    sctlr = re.search(r'XNU_SCTLR_EL1=0x([0-9a-f]+)', text)
    if trap or post or c_entry:
        required = ['ENTRY MMU-OFF', 'STACKS NEXT', 'TABLES READY', 'MMU ENABLE NEXT',
                    'BOOT EXCEPTION', 'XNU_FAULT_ESR=0x00000000f2000a31',
                    'XNU_FAULT_ELR=' + ('0xfffffe0007ad4fe8' if c_entry else '0x000000010148e500' if post else '0x000000010148e4f8')]
        sctlr = re.search(r'XNU_FAULT_SCTLR=0x([0-9a-f]+)', text)
        if (any(marker not in text for marker in required) or 'ENTRY-CHECK PASS' in text or
                not sctlr or bool(int(sctlr.group(1), 16) & 1) != (post or c_entry)):
            raise RuntimeError('audited bootstrap checkpoint did not trap with expected MMU state')
        return
    if (any(marker not in text for marker in required) or 'BOOT EXCEPTION' in text or
            not sctlr or not int(sctlr.group(1), 16) & 1):
        raise RuntimeError('actual linked kernel did not pass the emulated first-C checkpoint')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--pre-mmu-trap', action='store_true')
    parser.add_argument('--post-mmu-trap', action='store_true')
    parser.add_argument('--c-entry-trap', action='store_true')
    options = parser.parse_args()
    if sum([options.pre_mmu_trap, options.post_mmu_trap, options.c_entry_trap]) > 1:
        parser.error('select only one checkpoint')
    run(options.kernel.resolve(), options.out.resolve(), options.pre_mmu_trap, options.post_mmu_trap, options.c_entry_trap)
