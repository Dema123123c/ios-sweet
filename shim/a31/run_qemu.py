#!/usr/bin/env python3
"""Exercise real EL1/EL2 entry, 16K translation and timer IRQs in QEMU."""
import argparse
import json
import subprocess
from pathlib import Path


def run(image, out, qemu='qemu-system-aarch64', expect_entry_fault=False, payload=None, expect_handoff=False, expect_trap=False, expect_early=False):
    if expect_early:
        expect_trap = True
    if expect_trap and (payload is None or expect_entry_fault or expect_handoff):
        raise ValueError("entry trap requires a payload and no other fault mode")
    if expect_handoff and (payload is None or expect_entry_fault):
        raise ValueError('handoff test requires an executable payload and no entry fault')
    image, out = Path(image).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for virtualization, entry in [('off', 1), ('on', 2)]:
        command = [qemu, '-machine', f'virt,gic-version=3,virtualization={virtualization}',
                   '-cpu', 'max', '-m', '512M', '-smp', '1',
                   '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
                   '-no-reboot', '-semihosting-config', 'enable=on,target=native',
                   '-kernel', str(image)]
        if payload is not None:
            command += ['-initrd', str(Path(payload).resolve())]
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
        expected = [f'ENTRY_EL=0x{entry:016x}', f'EARLY_CURRENT_EL=0x{entry:016x}',
                    'EARLY ENTRY RECORDED']
        if expect_entry_fault:
            expected += [f'EXCEPTION_EL=0x{entry:016x}', f'ESR_EL{entry}=0x0000000002000000',
                         '[A31-DIAG] FAIL ']
            expected_return = 1
            forbidden = ['EL1 HANDOFF RECORDED', '[A31-DIAG] PASS']
        else:
            expected += ['EL1 HANDOFF RECORDED', 'CURRENT_EL=0x0000000000000001',
                         'MMU16K PASS', 'VTIMER PASS']
            expected_return = 0
            forbidden = ['[A31-DIAG] FAIL ']
            if payload is not None:
                expected += ['PAYLOAD COPY/READBACK PASS',
                             'XNU_ENTRY_PA=0x0000000050004000']
            if expect_trap:
                expected += ['EARLY XNU BRK ARMED' if expect_early else 'ENTRY BRK ARMED; NO XNU INSTRUCTIONS', 'PHYSICAL ENTRY BRK PASS',
                             'ENTRY_TRAP_ELR=0x0000000050005c78' if expect_early else 'ENTRY_TRAP_ELR=0x0000000050004000',
                             'ENTRY_TRAP_ESR=0x00000000f2000a31', '[A31-DIAG] PASS']
                if expect_early:
                    expected += ['A31 EARLY RECEIVER REACHED']
                    forbidden += ['A31 EARLY RECEIVER OVERSTEP']
                forbidden += ['XNU JUMP DISABLED', 'A31 HANDOFF FIXTURE PASS', 'A31 HANDOFF FIXTURE FAIL']
            elif expect_handoff:
                expected += ['[A31-DIAG] XNU HANDOFF', 'A31 HANDOFF FIXTURE PASS']
                forbidden += ['XNU JUMP DISABLED', '[A31-DIAG] PASS', 'A31 HANDOFF FIXTURE FAIL']
            else:
                expected += ['[A31-DIAG] PASS']
                if payload is not None: expected += ['XNU JUMP DISABLED']
        if (result.returncode != expected_return or any(item not in text for item in expected)
                or any(item in text for item in forbidden)):
            raise RuntimeError(f'EL{entry} QEMU diagnostic failed, return code {result.returncode}')
        reports.append({'entry_el': entry, 'result': 'pass', 'virtualization': virtualization,
                        'entry_fault_caught': expect_entry_fault, 'handoff_fixture_pass': expect_handoff, 'entry_brk_pass': expect_trap})
    (out / 'qemu-results.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--qemu', default='qemu-system-aarch64')
    parser.add_argument('--expect-entry-fault', action='store_true')
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--expect-handoff', action='store_true')
    parser.add_argument("--expect-trap", action="store_true")
    parser.add_argument("--expect-early", action="store_true")
    args = parser.parse_args()
    run(args.image, args.out, args.qemu, args.expect_entry_fault, args.payload, args.expect_handoff, args.expect_trap, args.expect_early)
