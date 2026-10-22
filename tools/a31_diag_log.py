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
        found.append({'status': status, 'build_id': expected_build, 'fields': fields,
                      'failure': failure.group(1) if failure else None})
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
    for name in ['last_kmsg', 'sec_log']:
        partial = output / (name + '.partial')
        result = subprocess.run(prefix + ['pull', '/proc/' + name, str(partial)],
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
