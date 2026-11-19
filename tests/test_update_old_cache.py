"""Distinguish a Codex-installed cache from release and rollback payloads."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/wechat-ecosystem'))

from wce import own_update_package as package
from wce.contracts import WCEError
from wce.support_protocol import outcome
from wce.support_privacy import redact

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

    @unittest.skipUnless(sys.platform == 'darwin', 'Codex macOS cache retention')
    def test_atime_diff_is_ignored_and_host_eviction_restores_start_path(self):
        previous = self.prepare()
        original = previous.declared['plugin.json']
        # Deliberately change only the observation that normal file reads can update.
        earlier = SimpleNamespace(**{name: getattr(original, name) for name in (
            'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')},
            st_atime=0)
        previous = replace(previous, declared=previous.declared | {'plugin.json': earlier})
        container = package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        shutil.rmtree(self.old)
        package.restore_previous_launch(self.old, VERSION, self.manifest, container, lambda _: None)
        package.verify_package(self.old, VERSION, self.manifest)
        archive = self.base / 'plugins' / package.RETENTION_PARENT / container / 'original'
        self.assertEqual(archive.stat().st_ino, previous.root_pin[1])
        self.assertTrue((archive / self.pyc.relative_to(self.old)).is_file())
        # A later same-version host activation may evict the compatibility path again.
        shutil.rmtree(self.old)
        package.restore_previous_launch(self.old, VERSION, self.manifest, container, lambda _: None)
        package.verify_package(self.old, VERSION, self.manifest)
        self.assertTrue((archive / self.pyc.relative_to(self.old)).is_file())

    @unittest.skipUnless(sys.platform == 'darwin', 'Codex macOS cache retention')
    def test_unexpected_entry_at_old_path_is_never_overwritten(self):
        previous = self.prepare()
        container = package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        shutil.rmtree(self.old)
        self.old.symlink_to(self.rollback)
        with self.assertRaisesRegex(WCEError, '^UPDATE_CACHE_OLD_LAUNCH_RESTORE$'):
            package.restore_previous_launch(self.old, VERSION, self.manifest, container, lambda _: None)
        self.assertTrue(self.old.is_symlink())

    def test_retention_reports_the_failing_step_without_archive_swap(self):
        previous = self.prepare()
        parent = self.base / 'plugins' / package.RETENTION_PARENT
        parent.mkdir(mode=0o755)
        with self.assertRaisesRegex(WCEError, '^UPDATE_CACHE_ARCHIVE_DIRECTORY$'):
            package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        parent.chmod(0o700)
        (self.old / 'wce/example.py').write_text('replacement = True')
        with self.assertRaisesRegex(WCEError, '^UPDATE_CACHE_RECHECK_CHANGED$'):
            package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        self.assertEqual(self.old.stat().st_ino, previous.root_pin[1])

    def test_failed_swap_keeps_source_and_has_distinct_code(self):
        previous = self.prepare()
        with patch.object(package, 'rename_directory', side_effect=OSError('fixture blocked swap')):
            with self.assertRaisesRegex(WCEError, '^UPDATE_CACHE_ARCHIVE_SWAP$'):
                package.retain_previous_cache(self.old, VERSION, previous, self.rollback)
        self.assertEqual(self.old.stat().st_ino, previous.root_pin[1])

    def test_only_exact_known_codes_escape_general_redaction(self):
        code = 'UPDATE_OLD_CACHE_RETENTION_FAILED'
        secret = 'test-token-value-' + '0' * 32
        self.assertEqual(redact(f'{code} {secret}'), f'{code} [账号或凭据值已移除]')
        self.assertEqual(redact(code + '_OTHER'), '[账号或凭据值已移除]')
        self.assertEqual(redact('token: ' + code), '[秘密字段已移除]')
        self.assertEqual(outcome({'state': 'INSTALL_UNKNOWN', 'code': 'UPDATE_CACHE_OLD_LAUNCH_RESTORE'}),
                         ('UNKNOWN', 'UPDATE_CACHE_OLD_LAUNCH_RESTORE'))

    def test_bad_rollback_and_redacted_diagnostics(self):
        self.rollback.mkdir()
        with self.assertRaisesRegex(WCEError, '^UPDATE_ROLLBACK_PACKAGE_INVALID$'):
            self.prepare()
        self.assertEqual(outcome({'state': 'FAILED', 'code': 'UPDATE_ROLLBACK_PACKAGE_INVALID',
                                  'path': str(self.rollback)}), ('FAILED', 'UPDATE_ROLLBACK_PACKAGE_INVALID'))


if __name__ == '__main__':
    unittest.main()
