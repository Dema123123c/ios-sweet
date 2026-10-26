#!/usr/bin/env python3
"""Replay verified Xcode 15 DriverKit outputs; reject changed source inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile

ARCHIVE_SHA = '38f9bc2dd58d7f27895e38dedcdd34a7e49415b33694e422bd98c06a684aa273'
PREFIX = 'build/xnu.obj/DEVELOPMENT_ARM64_A31/iokit/DEVELOPMENT/DriverKit/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(archive, target):
    if digest(archive.read_bytes()) != ARCHIVE_SHA:
        raise ValueError('Unrecognized V22 build-tree archive')
    target.mkdir(parents=True, exist_ok=False)
    inputs, outputs = {}, {}
    with tarfile.open(archive) as tree:
        for member in tree.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if name.startswith('xnu/') and name.endswith(('.h', '.iig')):
                # This SDK copy belongs to libpthread, outside DriverKit inputs.
                if name == 'xnu/bsd/pthread/sweet_libpthread/TargetConditionals.h':
                    continue
                inputs[name[4:]] = digest(tree.extractfile(member).read())
            elif name.startswith(PREFIX) and name.endswith(('.h', '.iig.cpp')):
                leaf = name[len(PREFIX):]
                if PurePosixPath(leaf).name != leaf:
                    raise ValueError('Nested generated output')
                data = tree.extractfile(member).read()
                (target / leaf).write_bytes(data)
                outputs[leaf] = digest(data)
    if len(outputs) != 34 or len(inputs) < 1900:
        raise ValueError('Incomplete V22 DriverKit cache')
    (target / 'manifest.json').write_text(json.dumps(dict(inputs=inputs, outputs=outputs), indent=2))


def replay(arguments, cache):
    parser = argparse.ArgumentParser()
    parser.add_argument('--def', dest='definition', type=Path, required=True)
    parser.add_argument('--header', type=Path, required=True)
    parser.add_argument('--impl', type=Path, required=True)
    parser.add_argument('--framework-name', required=True, choices=['DriverKit'])
    options, extra = parser.parse_known_args(arguments)
    if not extra or extra[0] != '--':
        raise ValueError('Missing compiler argument boundary')
    definition = options.definition.resolve()
    root = definition.parent.parent.parent
    if definition.parent != root / 'iokit' / 'DriverKit':
        raise ValueError('Unexpected IIG source directory')
    manifest = json.loads((cache / 'manifest.json').read_text())
    for relative, expected in manifest['inputs'].items():
        file = root / relative
        if not file.is_file() or digest(file.read_bytes()) != expected:
            raise ValueError('IIG cache input changed: ' + relative)
    expected_defs = {name for name in manifest['inputs'] if name.endswith('.iig')}
    actual_defs = {str(file.relative_to(root)).replace('\\', '/') for file in root.rglob('*.iig')}
    if actual_defs != expected_defs:
        raise ValueError('IIG definition set changed')
    stem = definition.stem
    for output, suffix in ((options.header, '.h'), (options.impl, '.iig.cpp')):
        leaf = stem + suffix
        data = (cache / leaf).read_bytes()
        if output.name != leaf or digest(data) != manifest['outputs'][leaf]:
            raise ValueError('Unexpected/corrupted IIG output: ' + leaf)
        output.write_bytes(data)
    print('Verified Xcode 15 IIG cache: ' + definition.name)


if __name__ == '__main__':
    if sys.argv[1:2] == ['prepare']:
        prepare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        replay(sys.argv[1:], Path(os.environ['A31_IIG_CACHE']))
