#!/usr/bin/env python3
"""Prepare private A31 diagnostic/restore BOOT packages. Never flashes a phone."""
import argparse
import gzip
import hashlib
import io
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

from a31_fdt import parse, strings
from a31_payload import inspect_payload

STOCK_SHA256 = 'af9ef4265e3d15bb0cc3ff8c0b968eeb6da0253db305e37908aa649cfba176f1'
TOOL_HASHES = {
    'mkbootimg': '2a8d05d34110f66c463668f43fc812ce2e46e66459c347eaadb080271df69aa8',
    'avbtool': 'a9ec360fc5395db9b72d36c03af59ff984f4eefcc349dc32a556de7f8ed892ab',
}
PSTORE_PROFILE = {'mem_address': 0x4d010000, 'mem_size': 0xe0000,
                  'console_size': 0x40000, 'record_size': 0x1000,
                  'ftrace_size': 0x1000, 'pmsg_size': 0x10000,
                  'mem_type': 0, 'ecc': 0}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ParentBootMismatch(ValueError):
    pass


def validate_pstore_profile(profile):
    try:
        values = {k: int(profile[k], 0) if isinstance(profile[k], str) else profile[k]
                  for k in PSTORE_PROFILE}
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError('incomplete recovery pstore profile') from error
    if values != PSTORE_PROFILE or any(type(v) is not int for v in values.values()):
        raise ValueError('recovery pstore layout differs from the compiled diagnostic; refusing package')
    return values


def validate_return_recovery(metadata, recovery_image):
    requirement = metadata.get('recovery_return')
    if not requirement:
        return None
    if recovery_image is None:
        raise ValueError('automatic recovery return requires --recovery-image from current TWRP')
    data = recovery_image.read_bytes()
    expected = 'd8a89533d039c79618b4dffcdc5cdec5949534020b2011088a02b1899bbcd890'
    if (requirement.get('recovery_sha256') != expected or len(data) != 33554432 or
            sha(data) != expected):
        raise ValueError('recovery does not match the independently checked SRAM reset ABI')
    return {'sha256': expected, 'reset_abi_verified_in_recovery_binary': True,
            'native_return_hardware_tested': False}


def validate_payload_input(metadata, payload):
    mode = metadata.get('payload_mode')
    if not mode and payload is None and metadata.get('kernel_jump_enabled') is not True:
        return None
    entry_mode = mode == 'XNU entry checkpoint; stop before CPU/VM startup'
    if not entry_mode and (mode != 'prepare-only; no XNU jump' or metadata.get('kernel_jump_enabled') is not False):
        raise ValueError('payload only allowed with the explicit prepare-only native loader')
    if payload is None:
        raise ValueError('payload checker requires --payload')
    data = payload.read_bytes()
    result = inspect_payload(data)
    if entry_mode:
        expected = metadata.get('expected_payload_sha256')
        if (metadata.get('kernel_jump_enabled') is not True or not isinstance(expected, str) or
                not re.fullmatch(r'[0-9a-f]{64}', expected) or result['sha256'] != expected):
            raise ValueError('entry checkpoint requires the exact payload SHA-256 bound into its loader')
        from a31_payload import ENTRY_MARKERS
        segments = []
        for i in range(result['segments']):
            offset, size = struct.unpack_from('<2Q', data, 0x2a8 + 32 * i + 16)
            segments.append(data[offset:offset + size])
        if any(not any(marker in segment for segment in segments) for marker in ENTRY_MARKERS):
            raise ValueError('entry checkpoint markers missing from payload')
        result['kernel_jump_enabled'] = True
    return result


def validate_unlocked_stock(properties):
    required = {'ro.product.model': 'SM-A315F', 'ro.product.device': 'a31',
                'ro.build.PDA': 'A315FXXU5DXJ1', 'sys.boot_completed': '1',
                'ro.boot.flash.locked': '0',
                'ro.boot.vbmeta.device_state': 'unlocked',
                'ro.boot.verifiedbootstate': 'orange'}
    if not isinstance(properties, dict) or any(properties.get(k) != v for k, v in required.items()):
        raise ValueError('requires fresh stock Android A31 properties confirming unlocked/orange')
    return required


def validate_live_unlocked_fdt(data):
    nodes, _ = parse(data)
    if 'mediatek,MT6768' not in strings(nodes.get('/', {}).get('compatible', b'')):
        raise ValueError('live recovery FDT must identify MT6768')
    bootargs = nodes.get('/chosen', {}).get('bootargs', b'').split(b'\0')[0].decode('ascii')
    required = {'androidboot.vbmeta.device_state': 'unlocked',
                'androidboot.verifiedbootstate': 'orange'}
    for key, expected in required.items():
        values = [v for token in bootargs.split() for k, sep, v in [token.partition('=')]
                  if sep and k == key]
        if values != [expected]:
            raise ValueError('fresh recovery FDT must confirm unlocked/orange; '
                             'older stock Android evidence is insufficient')
    return {'sha256': sha(data), 'bootargs_state': required}


def require_parent_digest(data, size, algorithm, salt, expected):
    if not 0 < size <= len(data):
        raise ValueError('parent BOOT hash range exceeds the candidate image')
    if algorithm != 'sha256' or len(expected) != 32 or len(salt) > 64:
        raise ValueError('unsupported parent BOOT hash descriptor')
    actual = hashlib.sha256(salt + data[:size]).digest()
    if actual != expected:
        raise ParentBootMismatch('candidate BOOT does not match parent vbmeta; '
                                 'its own AVB footer does not satisfy the parent hash')


def check_boot_contract(data, size, algorithm, salt, expected, unlocked_stock=None):
    evidence = validate_unlocked_stock(unlocked_stock) if unlocked_stock is not None else None
    try:
        require_parent_digest(data, size, algorithm, salt, expected)
    except ParentBootMismatch:
        if evidence is None:
            raise
        # AVB permits verification errors when unlocked; Samsung acceptance still needs a real boot.
        return {'boot_digest_matches': False,
                'boot_contract': 'parent mismatch; explicitly testing unlocked AVB policy',
                'unlocked_stock_properties': evidence}
    return {'boot_digest_matches': True,
            'boot_contract': 'candidate matches supplied parent BOOT digest'}


def preflight_parent(avbtool, parent_path, data, unlocked_stock=None):
    if unlocked_stock is not None:
        validate_unlocked_stock(unlocked_stock)
    if sha(avbtool.read_bytes()) != TOOL_HASHES['avbtool']:
        raise ValueError('parent verification requires the pinned AOSP avbtool')
    spec = importlib.util.spec_from_file_location('a31_parent_avb', avbtool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    image = module.ImageHandler(str(parent_path), read_only=True)
    try:
        footer, header, descriptors, _ = module.Avb()._parse_image(image)
        if footer:
            raise ValueError('expected the top-level phone vbmeta partition')
        image.seek(0)
        blob = image.read(header.SIZE + header.authentication_data_block_size +
                          header.auxiliary_data_block_size)
        if not module.verify_vbmeta_signature(header, blob):
            raise ValueError('parent vbmeta signature is invalid')
        report = {'sha256': sha(parent_path.read_bytes()), 'flags': header.flags,
                  'bootloader_acceptance_verified': False}
        if header.flags & 2:
            report['boot_contract'] = 'verification disabled in supplied parent'
            return report
        hashes = [d for d in descriptors if isinstance(d, module.AvbHashDescriptor)
                  and d.partition_name == 'boot']
        chains = [d for d in descriptors if isinstance(d, module.AvbChainPartitionDescriptor)
                  and d.partition_name == 'boot']
        if len(hashes) != 1 or chains:
            raise ValueError('unsupported parent BOOT contract; refusing a flash package')
        descriptor = hashes[0]
        report.update(check_boot_contract(data, descriptor.image_size, descriptor.hash_algorithm,
                                          descriptor.salt, descriptor.digest, unlocked_stock))
        return report
    finally:
        image._image.close()


def dtbs(data):
    if data[:4] == bytes.fromhex('d00dfeed'):
        return [data]
    if len(data) < 32:
        raise ValueError('truncated Android DT table')
    magic, total, header, entry, count, offset, page, version = struct.unpack_from('>8I', data)
    if magic != 0xd7b7ab1e or total > len(data) or header != 32 or entry != 32 or \
            not 1 <= count <= 16 or offset < header or offset + count * entry > total or version:
        raise ValueError('unexpected Android DT table header')
    result = []
    for index in range(count):
        size, start = struct.unpack_from('>2I', data, offset + index * entry)
        if start < offset + count * entry or start > total or size > total - start:
            raise ValueError('Android DT entry outside table')
        result.append(data[start:start + size])
    return result


def unpack(data):
    if len(data) < 1660 or data[:8] != b'ANDROID!':
        raise ValueError('not an Android boot image v2')
    ks, ka, rs, ra, ss, sa, ta, page, version, osv = struct.unpack_from('<10I', data, 8)
    if version != 2 or page != 2048 or ss or struct.unpack_from('<I', data, 1632)[0]:
        raise ValueError('expected A31 v2/2048 boot layout without second/recovery_dtbo')
    ds, da = struct.unpack_from('<IQ', data, 1648)
    if struct.unpack_from('<I', data, 1644)[0] != 1660 or not ds:
        raise ValueError('invalid v2 header size or missing DTB')
    parts = {}
    offset = page
    for name, size in [('kernel', ks), ('ramdisk', rs), ('dtb', ds)]:
        if size > len(data) - offset:
            raise ValueError(f'truncated {name}')
        parts[name] = data[offset:offset + size]
        offset += (size + page - 1) // page * page
    cmdline = data[64:576].split(b'\0')[0] + data[608:1632].split(b'\0')[0]
    return {'kernel_addr': ka, 'ramdisk_addr': ra, 'tags_addr': ta,
            'dtb_addr': da, 'os_version': osv, 'page_size': page,
            'board': data[48:64].split(b'\0')[0].decode('ascii'),
            'cmdline': cmdline.decode('ascii'), 'parts': parts}


def package_tar(path, data):
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        entry = tarfile.TarInfo('boot.img')
        entry.size = len(data)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(data))
    with tarfile.open(path, 'r') as archive:
        if archive.getnames() != ['boot.img'] or archive.extractfile('boot.img').read() != data:
            raise ValueError('Odin package round-trip failed')


def build(stock_path, native_dir, output, mkbootimg, avbtool, parent_vbmeta,
          unlocked_stock_properties=None, live_recovery_fdt=None, pstore_profile=None,
          recovery_image=None, payload=None):
    live_report = None
    if unlocked_stock_properties is not None:
        if live_recovery_fdt is None:
            raise ValueError('unlocked test also requires fresh --live-recovery-fdt')
        live_report = validate_live_unlocked_fdt(live_recovery_fdt.read_bytes())
    stock = stock_path.read_bytes()
    if sha(stock) != STOCK_SHA256 or len(stock) != 33554432:
        raise ValueError('stock BOOT is not the twice-read A315FXXU5DXJ1 backup; refusing template')
    header = unpack(stock)
    if [header[k] for k in ['kernel_addr', 'ramdisk_addr', 'tags_addr', 'dtb_addr']] != [
            0x40080000, 0x47c80000, 0x4bc80000, 0x4bc80000]:
        raise ValueError('A31 load addresses changed')
    for dtb in dtbs(header['parts']['dtb']):
        nodes, _ = parse(dtb)
        if 'mediatek,MT6768' not in strings(nodes['/']['compatible']):
            raise ValueError('stock DTB does not identify MT6768')
    metadata = json.loads((native_dir / 'build.json').read_text())
    checked_recovery = validate_return_recovery(metadata, recovery_image)
    checked_payload = validate_payload_input(metadata, payload)
    payload_data = payload.read_bytes() if checked_payload is not None else None
    if payload_data is not None and sha(payload_data) != checked_payload['sha256']:
        raise ValueError('payload changed after validation')
    checked_pstore = None
    if metadata.get('pstore_console'):
        if pstore_profile is None:
            raise ValueError('this diagnostic requires a fresh --pstore-profile from recovery sysfs')
        checked_pstore = validate_pstore_profile(json.loads(pstore_profile.read_text(encoding='utf-8')))
    raw = (native_dir / 'Image').read_bytes()
    compressed = (native_dir / 'Image.gz').read_bytes()
    if metadata['qemu'] is not False or metadata['sha256'] != sha(raw) or gzip.decompress(compressed) != raw:
        raise ValueError('native diagnostic Image/manifest mismatch (QEMU image is forbidden)')
    if checked_payload and checked_payload['kernel_jump_enabled']:
        if metadata['expected_payload_sha256'].encode() not in raw:
            raise ValueError('entry payload SHA-256 is not bound into the compiled loader')
    if raw[56:60] != b'ARM\x64' or struct.unpack_from('<QQQ', raw, 8) != (0x80000, len(raw), 12):
        raise ValueError('diagnostic Linux Image header mismatch')
    for name, tool in [('mkbootimg', mkbootimg), ('avbtool', avbtool)]:
        if sha(tool.read_bytes()) != TOOL_HASHES[name]:
            raise ValueError(f'{name} must match the pinned AOSP android-12.0.0_r34 source')
    if output.exists():
        raise FileExistsError('use a new output folder; do not overwrite a reviewed flash package')
    output.mkdir(parents=True)
    staging = output / 'components'
    staging.mkdir()
    for name in ['ramdisk', 'dtb']:
        (staging / name).write_bytes(payload_data if name == 'ramdisk' and checked_payload
                                    else header['parts'][name])
    shutil.copyfile(native_dir / 'Image.gz', staging / 'Image.gz')
    osv = header['os_version']
    os_version = f'{(osv >> 25) & 127}.{(osv >> 18) & 127}.{(osv >> 11) & 127}'
    patch = f'{2000 + ((osv >> 4) & 127):04}-{osv & 15:02}'
    (output / 'diagnostic').mkdir()
    image = output / 'diagnostic' / 'boot.img'
    command = [sys.executable, str(mkbootimg), '--header_version', '2', '--base', '0',
               '--kernel', str(staging / 'Image.gz'), '--ramdisk', str(staging / 'ramdisk'),
               '--dtb', str(staging / 'dtb'), '--pagesize', '2048',
               '--kernel_offset', hex(header['kernel_addr']),
               '--ramdisk_offset', hex(header['ramdisk_addr']),
               '--tags_offset', hex(header['tags_addr']), '--dtb_offset', hex(header['dtb_addr']),
               '--board', header['board'], '--cmdline', header['cmdline'],
               '--os_version', os_version, '--os_patch_level', patch, '-o', str(image)]
    subprocess.run(command, check=True)
    with image.open('ab') as file:
        file.write(b'SEANDROIDENFORCE')
    salt = sha(image.read_bytes())
    subprocess.run([sys.executable, str(avbtool), 'add_hash_footer', '--image', str(image),
                    '--partition_name', 'boot', '--partition_size', str(len(stock)),
                    '--algorithm', 'NONE', '--salt', salt], check=True)
    subprocess.run([sys.executable, str(avbtool), 'verify_image', '--image', str(image)], check=True)
    diagnostic = image.read_bytes()
    try:
        properties = (json.loads(unlocked_stock_properties.read_text(encoding='utf-8'))
                      if unlocked_stock_properties is not None else None)
        parent_report = preflight_parent(avbtool, parent_vbmeta, diagnostic, properties)
        if live_report is not None:
            parent_report['live_recovery_fdt'] = live_report
    except Exception:
        image.unlink()
        (output / 'REJECTED.txt').write_text(
            'Parent vbmeta preflight failed. Candidate BOOT removed; no Odin '
            'flash package produced. Do not change phone partitions to bypass '
            'this check without a separately reviewed and approved plan.\n')
        raise
    after = unpack(diagnostic)
    for key, value in header.items():
        if key != 'parts' and after[key] != value:
            raise ValueError(f'boot header changed: {key}')
    if (gzip.decompress(after['parts']['kernel']) != raw or
            after['parts']['dtb'] != header['parts']['dtb'] or
            after['parts']['ramdisk'] != (staging / 'ramdisk').read_bytes()):
        raise ValueError('boot component round-trip failed')
    if len(diagnostic) != len(stock) or diagnostic[-64:-60] != b'AVBf':
        raise ValueError('partition size or AVB footer mismatch')
    (output / 'restore').mkdir()
    original = output / 'restore' / 'boot.img'
    original.write_bytes(stock)
    package_tar(output / 'a31-diagnostic-boot.tar', diagnostic)
    package_tar(output / 'a31-original-boot-restore.tar', stock)
    report = {'device': 'SM-A315F', 'firmware_template': 'A315FXXU5DXJ1',
               'kind': ('XNU entry checkpoint; stop before CPU/VM startup' if checked_payload and checked_payload['kernel_jump_enabled']
                        else 'XNU payload preparation/readback only; no kernel jump' if checked_payload
                        else 'diagnostic only; no XNU handoff'), 'native_boot_tested': False,
              'writes_performed_on_phone': False, 'target_partition': 'BOOT only',
              'stock_sha256': sha(stock), 'diagnostic_sha256': sha(diagnostic),
              'image_sha256': sha(raw), 'avb_algorithm': 'NONE (unsigned)',
              'requires_unlocked_bootloader': True,
              'parent_vbmeta_preflight': parent_report,
              'header_and_original_ramdisk_dtb_preserved': checked_payload is None,
              'header_and_original_dtb_preserved': True,
              'manual_return_to_recovery_required': True,
              'source_image_manifest': metadata}
    if checked_pstore is not None:
        report['recovery_pstore_profile'] = checked_pstore
    if checked_recovery is not None:
        report['automatic_recovery_return'] = checked_recovery
    if checked_payload is not None:
        report['prepared_payload'] = checked_payload
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-boot', type=Path, required=True)
    parser.add_argument('--native-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mkbootimg', type=Path, required=True)
    parser.add_argument('--avbtool', type=Path, required=True)
    parser.add_argument('--parent-vbmeta', type=Path, required=True,
                        help='fresh unchanged top-level vbmeta read from this phone; '
                             'requires openssl on PATH for signed metadata')
    parser.add_argument('--unlocked-stock-properties', type=Path,
                        help='explicit opt-in to testing unlocked AVB policy: fresh stock Android '
                             'getprop JSON from this A31 (unlocked/orange). This file is operator '
                             'evidence, not attestation or proof of Samsung boot acceptance')
    parser.add_argument('--live-recovery-fdt', type=Path,
                        help='fresh /sys/firmware/fdt read from current TWRP, also required '
                             'for unlocked tests; rejects green or contradictory bootargs')
    parser.add_argument('--pstore-profile', type=Path,
                        help='fresh recovery ramoops sysfs parameter JSON; mandatory for pstore diagnostics')
    parser.add_argument('--recovery-image', type=Path,
                        help='current matching TWRP partition dump; required by automatic-return diagnostics')
    parser.add_argument('--payload', type=Path,
                        help='checked XNU payload for prepare-only or an exact-SHA entry-check loader')
    args = parser.parse_args()
    build(args.stock_boot.resolve(), args.native_dir.resolve(), args.out.resolve(),
          args.mkbootimg.resolve(), args.avbtool.resolve(), args.parent_vbmeta.resolve(),
          args.unlocked_stock_properties.resolve() if args.unlocked_stock_properties else None,
          args.live_recovery_fdt.resolve() if args.live_recovery_fdt else None,
          args.pstore_profile.resolve() if args.pstore_profile else None,
          args.recovery_image.resolve() if args.recovery_image else None,
          args.payload.resolve() if args.payload else None)
