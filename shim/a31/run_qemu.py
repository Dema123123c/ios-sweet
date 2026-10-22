#!/usr/bin/env python3
"""Exercise real EL1/EL2 entry, 16K translation and timer IRQs in QEMU."""
import argparse
import json
import subprocess
from pathlib import Path


def run(image, out, qemu='qemu-system-aarch64'):
    image, out = Path(image).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for virtualization, entry in [('off', 1), ('on', 2)]:
        command = [qemu, '-machine', f'virt,gic-version=3,virtualization={virtualization}',
                   '-cpu', 'max', '-m', '512M', '-smp', '1',
                   '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
                   '-no-reboot', '-semihosting-config', 'enable=on,target=native',
                   '-kernel', str(image)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired as error:
            partial = (error.stdout or b'') + (error.stderr or b'')
            (out / f'el{entry}.log').write_bytes(partial)
            print(partial.decode(errors='replace'))
            raise
        text = result.stdout + result.stderr
        (out / f'el{entry}.log').write_text(text, encoding='utf-8')
        print(text, end='')
        expected = [f'ENTRY_EL=0x{entry:016x}', 'CURRENT_EL=0x0000000000000001',
                    'MMU16K PASS', 'VTIMER PASS', '[A31-DIAG] PASS']
        if result.returncode != 0 or any(item not in text for item in expected):
            raise RuntimeError(f'EL{entry} QEMU diagnostic failed, return code {result.returncode}')
        reports.append({'entry_el': entry, 'result': 'pass', 'virtualization': virtualization})
    (out / 'qemu-results.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--qemu', default='qemu-system-aarch64')
    args = parser.parse_args()
    run(args.image, args.out, args.qemu)
