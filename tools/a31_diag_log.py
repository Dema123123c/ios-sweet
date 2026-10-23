#!/usr/bin/env python3
"""Read diagnostic evidence from A31 TWRP, with no phone writes or reboots."""
import argparse
import json
import re
import struct
import subprocess
from pathlib import Path


def chronological(data):
    if len(data) == 0x200000:
        head, position, magic = struct.unpack_from('<3I', data, len(data) - 12)
        capacity = len(data) - 12
        if magic == 0x4d474f4c and head <= 1 and position < capacity:
            return data[position:capacity] + data[:position] if head else data[:position]
    return data


def inspect(data, expected_build):
    text = chronological(data).decode('utf-8', errors='replace').replace('\r', '')
    sessions = re.findall(r'\[A31-DIAG v1\] BEGIN\n(.*?)(?=\[A31-DIAG v1\] BEGIN|\Z)', text, re.S)
    found = []
    for session in sessions:
        if not re.search(r'^BUILD=' + re.escape(expected_build) + r'$', session, re.M):
            continue
        fields = dict(re.findall(r'^([A-Z0-9_]+)=(0x[0-9a-f]+)$', session, re.M))
        failure = re.search(r'^\[A31-DIAG\] FAIL (.*)$', session, re.M)
        complete = all(re.search(r'^' + re.escape(line) + r'$', session, re.M) for line in [
            'MMU16K PASS', 'VTIMER PASS', '[A31-DIAG] PASS'])
        status = 'fail' if failure else 'pass' if complete else 'incomplete'
        entry_failure = re.search(r'^\[A31-XNU\] (?:ENTRY-CHECK FAIL|REBASE-CHECK FAIL|CPU-DATA-CHECK FAIL|PLATFORM-CHECK FAIL|PANIC:|RECOVERY FAILED|BOOT EXCEPTION|BOOT RECOVERY FAILED)', session, re.M)
        entry_pass = all(re.search(r'^' + re.escape(line) + r'$', session, re.M) for line in [
            'MMU16K PASS', 'VTIMER PASS', 'PAYLOAD COPY/READBACK PASS', '[A31-DIAG] XNU HANDOFF',
            '[A31-XNU] ENTRY MMU-OFF v1', '[A31-XNU] ENTRY-CHECK PASS', '[A31-XNU] RECOVERY REQUEST'])
        entry_trap_pass = (complete and not failure and all(re.search(r'^' + re.escape(line) + r'$', session, re.M)
            for line in ['PAYLOAD COPY/READBACK PASS', 'ENTRY BRK ARMED; NO XNU INSTRUCTIONS',
                         '[A31-DIAG] XNU HANDOFF', 'PHYSICAL ENTRY BRK PASS']) and
            fields.get('ENTRY_TRAP_ESR') == '0x00000000f2000a31' and
            fields.get('ENTRY_TRAP_ELR') is not None and
            fields.get('ENTRY_TRAP_ELR') == fields.get('XNU_ENTRY_PA'))
        early_asm_pass = (complete and not failure and all(re.search(r'^' + re.escape(line) + r'$', session, re.M)
            for line in ['PAYLOAD COPY/READBACK PASS', 'EARLY XNU BRK ARMED',
                         '[A31-DIAG] XNU HANDOFF', '[A31-XNU] ENTRY MMU-OFF v1', 'PHYSICAL ENTRY BRK PASS']) and
            fields.get('ENTRY_TRAP_ESR') == '0x00000000f2000a31' and
            fields.get('ENTRY_TRAP_ELR') == '0x000000010148e100' and
            fields.get('ENTRY_TRAP_TARGET') == fields.get('ENTRY_TRAP_ELR') and
            fields.get('XNU_ENTRY_PA') == '0x000000010148c488')
        rebase_markers = ['[A31-XNU] ENTRY MMU-OFF v1',
                          '[A31-XNU] C STAGE 1: arm_init entered (MMU on)',
                          '[A31-XNU] ENTRY-CHECK PASS',
                          '[A31-XNU] C STAGE 21: image rebasing done; before boot args and CPU data',
                          '[A31-XNU] REBASE-CHECK PASS', '[A31-XNU] RECOVERY REQUEST']
        positions = [session.find(line + '\n') for line in rebase_markers]
        rebase_pass = (entry_pass and not failure and not entry_failure and
                       all(p >= 0 for p in positions) and positions == sorted(positions) and
                       fields.get('XNU_CURRENT_EL') == '0x0000000000000001' and
                       fields.get('XNU_CNTFRQ') == '0x0000000000c65d40' and
                       bool(int(fields.get('XNU_SCTLR_EL1', '0'), 16) & 1))
        cpu_markers = ['[A31-XNU] REBASE-CHECK PASS',
                       '[A31-XNU] C STAGE 22: boot args copied; CPU data initialized; before platform',
                       '[A31-XNU] CPU-DATA-CHECK PASS', '[A31-XNU] RECOVERY REQUEST']
        cpu_positions = [session.find(line + '\n') for line in cpu_markers]
        cpu_data_pass = (rebase_pass and all(p >= 0 for p in cpu_positions) and
                         cpu_positions == sorted(cpu_positions))
        platform_markers = ['[A31-XNU] CPU-DATA-CHECK PASS',
                            '[A31-XNU] C STAGE 2: PE_init_platform done',
                            '[A31-XNU] PLATFORM-CHECK PASS', '[A31-XNU] RECOVERY REQUEST']
        platform_positions = [session.find(line + '\n') for line in platform_markers]
        platform_pass = (cpu_data_pass and all(p >= 0 for p in platform_positions) and
                         platform_positions == sorted(platform_positions))
        if entry_failure:
            status = 'fail'
        elif platform_pass:
            status = 'xnu_platform_pass'
        elif cpu_data_pass:
            status = 'xnu_cpu_data_pass'
        elif rebase_pass:
            status = 'xnu_rebase_pass'
        elif entry_pass and not failure:
            status = 'xnu_entry_pass'
        elif early_asm_pass:
            status = 'xnu_early_asm_pass'
        elif entry_trap_pass:
            status = 'entry_trap_pass'
        found.append({'status': status, 'build_id': expected_build, 'fields': fields,
                      'failure': failure.group(1) if failure else None,
                      'physical_entry_trap_pass': entry_trap_pass, 'xnu_early_asm_pass': early_asm_pass,
                      'xnu_entry_pass': entry_pass and not failure and not entry_failure,
                      'xnu_rebase_pass': rebase_pass,
                      'xnu_cpu_data_pass': cpu_data_pass,
                      'xnu_platform_pass': platform_pass,
                      'xnu_entry_failure': entry_failure.group(0) if entry_failure else None,
                      'payload_prepared': bool(re.search(r'^PAYLOAD COPY/READBACK PASS$', session, re.M)),
                      'kernel_jump_disabled': bool(re.search(r'^XNU JUMP DISABLED$', session, re.M))})
    return {'status': found[-1]['status'] if found else 'not_found', 'sessions': found}


def collect(adb, serial, output, expected_build):
    if output.exists():
        raise FileExistsError('use a new private output folder')
    prefix = [str(adb), '-s', serial]
    def prop(name):
        return subprocess.check_output(prefix + ['shell', 'getprop', name],
                                       text=True, timeout=15).strip()
    if prop('ro.product.device') != 'a31' or not prop('ro.twrp.version'):
        raise ValueError('expected the connected A31 in TWRP')
    output.mkdir(parents=True)
    report = {'expected_build': expected_build, 'phone_writes': False, 'sources': {}}
    sources = {'last_kmsg': '/proc/last_kmsg', 'sec_log': '/proc/sec_log',
               'pstore_console': '/sys/fs/pstore/console-ramoops',
               'pstore_console_indexed': '/sys/fs/pstore/console-ramoops-0'}
    for name, remote in sources.items():
        partial = output / (name + '.partial')
        result = subprocess.run(prefix + ['pull', remote, str(partial)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            report['sources'][name] = {'status': 'read_failed', 'error': result.stderr.strip()}
            continue
        target = output / (name + '.bin')
        partial.rename(target)
        report['sources'][name] = inspect(target.read_bytes(), expected_build)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-build', required=True)
    args = parser.parse_args()
    collect(args.adb, args.serial, args.out, args.expected_build)
