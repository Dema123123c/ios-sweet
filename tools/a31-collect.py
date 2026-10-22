#!/usr/bin/env python3
"""Read A31 bring-up inputs using TWRP's privileged ADB sync service."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from a31_fdt import describe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    base = [args.adb] + (['-s', args.serial] if args.serial else [])

    def run(command, timeout=30):
        p = subprocess.run(base + ['shell', command], capture_output=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError(p.stderr.decode(errors='replace').strip() or p.stdout.decode(errors='replace').strip())
        return p.stdout.decode(errors='replace').strip()

    device = run('getprop ro.product.device') or run('getprop ro.product.system.device')
    platform = run('getprop ro.board.platform')
    recovery = run('getprop ro.twrp.version')
    if device != 'a31' or platform != 'mt6768':
        raise RuntimeError('expected a31/mt6768; got %s/%s' % (device, platform))
    if not recovery:
        raise RuntimeError('TWRP not confirmed by ro.twrp.version')
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                'device': device, 'platform': platform, 'twrp': recovery,
                'files': {}, 'unavailable': {}}

    def binary(remote, name, expected=None):
        dest = args.out / name
        temp = dest.with_suffix(dest.suffix + '.partial')
        # Some TWRP builds keep sync as root but force shell/exec-out to uid 2000.
        p = subprocess.run(base + ['pull', remote, str(temp)], capture_output=True, timeout=180)
        if p.returncode:
            temp.unlink(missing_ok=True)
            raise RuntimeError(p.stderr.decode(errors='replace').strip() or p.stdout.decode(errors='replace').strip() or 'read failed')
        actual = temp.stat().st_size
        if not actual or expected is not None and actual != expected:
            temp.unlink()
            raise RuntimeError('unexpected byte count %d; expected %s' % (actual, expected))
        digest = hashlib.sha256(temp.read_bytes()).hexdigest()
        second = temp.with_suffix('.readback')
        try:
            p = subprocess.run(base + ['pull', remote, str(second)], capture_output=True, timeout=180)
            if p.returncode or not second.exists() or digest != hashlib.sha256(second.read_bytes()).hexdigest():
                temp.unlink(missing_ok=True)
                raise RuntimeError('independent second read failed or SHA256 mismatch for ' + remote)
        finally:
            second.unlink(missing_ok=True)
        temp.rename(dest)
        manifest['files'][name] = {'size': actual, 'sha256': digest, 'source': remote}
        print('Verified', name, actual, 'bytes', flush=True)
        return dest

    def save_manifest():
        (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    try:
        fdt = binary('/sys/firmware/fdt', 'live.dtb')
        (args.out / 'board.json').write_text(json.dumps(describe(fdt.read_bytes()), indent=2) + '\n', encoding='utf-8')
        for partition in ['boot', 'recovery', 'dtbo', 'vbmeta', 'vbmeta_samsung']:
            remote = '/dev/block/by-name/' + partition
            target = run('readlink -f ' + remote)
            if not re.fullmatch(r'/dev/block/mmcblk0p[0-9]+', target):
                raise RuntimeError('unexpected block device for ' + partition)
            size = int(run('cat /sys/class/block/' + target.rsplit('/', 1)[1] + '/size')) * 512
            if not 0 < size <= 256 * 1024 * 1024:
                raise RuntimeError('unexpected partition size for ' + partition)
            binary(remote, partition + '.img', size)
        for name, remote in {
            'iomem.txt': '/proc/iomem',
            'cpuinfo.txt': '/proc/cpuinfo',
            'meminfo.txt': '/proc/meminfo',
            'partitions.txt': '/proc/partitions',
            'input.txt': '/proc/bus/input/devices',
        }.items():
            p = subprocess.run(base + ['pull', remote, str(args.out / name)], capture_output=True, timeout=30)
            if p.returncode:
                manifest['unavailable'][name] = p.stderr.decode(errors='replace').strip()
        (args.out / 'partition-links.txt').write_text(run('ls -l /dev/block/by-name'), encoding='utf-8')
        (args.out / 'framebuffer.txt').write_text(run('for f in name virtual_size bits_per_pixel stride modes; do echo "$f"; cat /sys/class/graphics/fb0/$f; done'), encoding='utf-8')
        try:
            binary('/proc/config.gz', 'config.gz')
        except RuntimeError as error:
            manifest['unavailable']['config.gz'] = str(error)
    finally:
        save_manifest()
    print('Read-only collection complete:', args.out)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print('ERROR:', error, file=sys.stderr)
        raise SystemExit(1)
