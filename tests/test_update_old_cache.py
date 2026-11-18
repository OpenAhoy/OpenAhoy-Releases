"""Distinguish a Codex-installed cache from release and rollback payloads."""
from hashlib import sha256
import json
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/wechat-ecosystem'))

from wce import own_update_package as package
from wce.contracts import WCEError
from wce.support_protocol import outcome

VERSION = '0.6.80'


class OldCache(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.base = Path(area.name).resolve()
        self.old = self.base / 'plugins/cache/test-market/wechat-ecosystem' / VERSION
        self.old.mkdir(parents=True)
        self.rollback = self.base / 'previous'
        source = {'plugin.json': json.dumps({'name': 'wechat-ecosystem', 'version': VERSION}),
                  'wce/example.py': 'label = "fixture"\n'}
        for name, body in source.items():
            path = self.old / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(body)
        manifest = {'schema': 1, 'files': {name: sha256(body.encode()).hexdigest() for name, body in source.items()}}
        raw = json.dumps(manifest).encode()
        (self.old / package.MANIFEST).write_bytes(raw)
        self.manifest = sha256(raw).hexdigest()
        self.pyc = Path(py_compile.compile(str(self.old / 'wce/example.py'), doraise=True, optimize=2))

    def prepare(self):
        with patch.object(package, 'trusted_previous_manifest', return_value=self.manifest):
            return package.prepare_previous(self.old, VERSION, self.rollback, lambda _: None)

    def test_release_stays_strict_runtime_accepts_attributable_cache_and_rollback_is_clean(self):
        with self.assertRaisesRegex(WCEError, '^UPDATE_PACKAGE_INVALID$'):
            package.verify_package(self.old, VERSION, self.manifest)
        caches = package.verify_runtime(self.old, VERSION, self.manifest).caches
        self.assertEqual(set(caches), {self.pyc.relative_to(self.old).as_posix()})
        original = self.pyc.read_bytes()
        self.prepare()
        self.assertEqual(self.pyc.read_bytes(), original)
        self.assertFalse(list(self.rollback.rglob('*.pyc')))
        package.verify_package(self.rollback, VERSION, self.manifest)

    def test_untrusted_cache_and_modified_payload_are_refused_before_staging(self):
        with patch.object(package, 'trusted_previous_manifest', return_value='0' * 64):
            with self.assertRaisesRegex(WCEError, '^UPDATE_OLD_CACHE_UNVERIFIED$'):
                package.prepare_previous(self.old, VERSION, self.rollback, lambda _: None)
        (self.old / 'wce/example.py').write_text('changed = True')
        with self.assertRaisesRegex(WCEError, '^UPDATE_OLD_CACHE_INVALID$'):
            self.prepare()
        self.assertFalse(self.rollback.exists())

    def test_unrelated_files_links_fifos_and_empty_directories_are_still_refused(self):
        makers = {
            'notes.txt': lambda path: path.touch(),
            'missing.cpython-313.pyc': lambda path: path.touch(),
            'badlink': lambda path: path.symlink_to(self.pyc),
            'hardlink': lambda path: os.link(self.pyc, path),
            'pipe': os.mkfifo, 'empty-folder': lambda path: path.mkdir(),
        }
        for name, create in makers.items():
            extra = self.pyc.with_name(name)
            with self.subTest(name=name):
                create(extra)
                with self.assertRaisesRegex(WCEError, '^UPDATE_OLD_CACHE_INVALID$'):
                    self.prepare()
                if extra.is_dir() and not extra.is_symlink():
                    extra.rmdir()
                else:
                    extra.unlink()
        self.assertFalse(self.rollback.exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'Codex macOS cache retention')
    def test_original_inode_and_bytecode_survive_host_eviction(self):
        original = self.pyc.read_bytes()
        inode = self.pyc.stat().st_ino
        previous = self.prepare()
        package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        package.verify_package(self.old, VERSION, self.manifest)
        archived, = (self.base / 'plugins/openahoy-retained-cache').glob('*/original')
        shutil.rmtree(self.old)  # Simulate the host's normal version eviction.
        retained = archived / self.pyc.relative_to(self.old)
        self.assertEqual(retained.read_bytes(), original)
        self.assertEqual(retained.stat().st_ino, inode)
        self.assertFalse(list(self.rollback.rglob('*.pyc')))

    def test_bad_rollback_and_redacted_diagnostics(self):
        self.rollback.mkdir()
        with self.assertRaisesRegex(WCEError, '^UPDATE_ROLLBACK_PACKAGE_INVALID$'):
            self.prepare()
        self.assertEqual(outcome({'state': 'FAILED', 'code': 'UPDATE_ROLLBACK_PACKAGE_INVALID',
                                  'path': str(self.rollback)}), ('FAILED', 'UPDATE_ROLLBACK_PACKAGE_INVALID'))


if __name__ == '__main__':
    unittest.main()
