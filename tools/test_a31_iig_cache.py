import json
from pathlib import Path
import tempfile
import unittest
from a31_iig_cache import digest, prepare, replay


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.definition = self.root / 'xnu/iokit/DriverKit/Example.iig'
        self.definition.parent.mkdir(parents=True)
        self.definition.write_text('class Example {};')
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.manifest = dict(inputs={'iokit/DriverKit/Example.iig': digest(self.definition.read_bytes())}, outputs={})
        for leaf in ('Example.h', 'Example.iig.cpp'):
            data = ('cached ' + leaf).encode()
            (self.cache / leaf).write_bytes(data)
            self.manifest['outputs'][leaf] = digest(data)
        (self.cache / 'manifest.json').write_text(json.dumps(self.manifest))
        self.arguments = ['--def', str(self.definition), '--header', str(self.root / 'Example.h'),
                          '--impl', str(self.root / 'Example.iig.cpp'), '--framework-name', 'DriverKit', '--']

    def test_exact_replay(self):
        replay(self.arguments, self.cache)
        self.assertEqual((self.root / 'Example.h').read_bytes(), (self.cache / 'Example.h').read_bytes())

    def test_changed_input_rejected_without_output(self):
        self.definition.write_text('class Different {};')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            replay(self.arguments, self.cache)
        self.assertFalse((self.root / 'Example.h').exists())

    def test_added_definition_rejected(self):
        (self.definition.parent / 'Other.iig').write_text('class Other {};')
        with self.assertRaisesRegex(ValueError, 'definition set changed'):
            replay(self.arguments, self.cache)

    def test_corrupt_cached_output_rejected(self):
        (self.cache / 'Example.h').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'corrupted IIG output'):
            replay(self.arguments, self.cache)

    def test_unrecognized_archive_rejected(self):
        archive = self.root / 'bad.tgz'
        archive.write_bytes(b'untrusted')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            prepare(archive, self.root / 'new-cache')
        self.assertFalse((self.root / 'new-cache').exists())
