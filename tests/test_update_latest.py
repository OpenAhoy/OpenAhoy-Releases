"""Regression coverage for published stable selection and installation boundaries."""
from hashlib import sha256
from io import BytesIO
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / 'plugins/wechat-ecosystem'))

from wce import own_updates as updates
from wce import own_update_install as installation
from wce.contracts import WCEError
from wce.own_connection_policy import atomic_write

PIN = 'c' * 40
MANIFEST = 'd' * 64


def release_row(version):
    row = json.loads((ROOT / 'RELEASE.json').read_bytes())
    name = f'openahoy-{version}-macos-arm64.zip'
    return dict(row, version=version, tag='v' + version, asset=name,
                asset_url=f'{updates.RELEASES}/download/v{version}/{name}',
                package_manifest_sha256=MANIFEST)


def advert_tags(*versions):
    return ''.join(f'{PIN}\trefs/tags/v{version}\n' for version in versions).encode()


class Discovery(unittest.TestCase):
    def signs(self, installed, versions, release=None, mismatched=False):
        runner = Mock(side_effect=[updates.REMOTE.encode(), advert_tags(*versions)])
        publisher = (lambda: release_row(release)) if release else Mock(
            side_effect=updates.UpdateCheckUnavailable('RELEASE_CHANNEL_UNAVAILABLE'))
        pin = Mock(side_effect=lambda version, revision: release_row(version) | (
            {'sha256': 'b' * 64} if mismatched else {}))
        result = updates.check(installed, runner=runner, publisher=publisher, pinned=pin)
        if release:
            tag = 'refs/tags/v' + release
            self.assertEqual(runner.call_args.args[0], ['--tags', updates.REMOTE, tag, tag + '^{}'])
            if release in versions:
                pin.assert_called_once_with(release, PIN)
            else:
                pin.assert_not_called()
        return result

    def test_skip_releases_and_never_downgrade(self):
        tags = ('0.6.27', '0.6.28', '0.6.63', '0.6.81', '0.6.82', '0.6.83-rc1')
        for version in ('0.6.11', '0.6.28', '0.6.63', '0.6.76', '0.6.81'):
            with self.subTest(version=version):
                row = self.signs(version, tags, '0.6.82')
                self.assertEqual((row['state'], row['latest_version'], row['advertised_revision']),
                                 ('UPDATE_AVAILABLE', '0.6.82', PIN))
                self.assertEqual(row['package_manifest_sha256'], MANIFEST)
        self.assertEqual(self.signs('0.6.82', tags, '0.6.82')['state'], 'UP_TO_DATE')
        self.assertEqual(self.signs('0.6.100', tags, '0.6.82')['state'], 'DEVELOPMENT_AHEAD')

    def test_higher_unpublished_numeric_tags_do_not_hide_the_published_release(self):
        row = self.signs('0.6.76', ['0.6.81','0.6.82','0.6.83','0.6.98'], '0.6.82')
        self.assertEqual((row['state'], row['latest_version']), ('UPDATE_AVAILABLE', '0.6.82'))
        self.assertEqual(self.signs('0.6.82', ['0.6.82','0.6.83'], '0.6.82')['state'], 'UP_TO_DATE')

    def test_missing_tag_disagreement_and_offline_are_never_up_to_date(self):
        for installed, versions, release, reason in [
            ('0.6.80', ['0.6.80'], '0.6.82', 'RELEASE_CHANNEL_CHANGED'),
            ('0.6.80', ['0.6.80'], None, 'RELEASE_CHANNEL_UNAVAILABLE'),
        ]:
            row = self.signs(installed, versions, release)
            self.assertEqual(row['state'], 'CHECK_UNAVAILABLE')
            self.assertEqual(row['diagnostic']['code'], reason)
            self.assertNotIn('latest_version', row)
        row = self.signs('0.6.80', ['0.6.82'], '0.6.82', mismatched=True)
        self.assertEqual(row['state'], 'CHECK_UNAVAILABLE')
        self.assertEqual(row['diagnostic']['code'], 'RELEASE_CHANNEL_CHANGED')

    def test_annotated_release_uses_the_peeled_commit(self):
        base = 'a' * 40
        ref = 'refs/tags/v0.6.82'
        raw = f'{base}\t{ref}\n{PIN}\t{ref}^{{}}\n'.encode()
        runner = Mock(side_effect=[updates.REMOTE.encode(), raw])
        pin = Mock(return_value=release_row('0.6.82'))
        row = updates.check('0.6.76', runner=runner, publisher=lambda: release_row('0.6.82'), pinned=pin)
        self.assertEqual(row['advertised_revision'], PIN)
        pin.assert_called_once_with('0.6.82', PIN)

    def test_fixed_origin_asset_redirection_and_no_cache(self):
        handler = updates.StableRedirect()
        initial = Request(updates.LATEST_MANIFEST_URL)
        pinned = updates.RELEASES + '/download/v0.6.82/RELEASE.json'
        args = (None, 302, 'Found', {})
        forwarded = handler.redirect_request(initial, *args, pinned)
        self.assertEqual(handler.version, '0.6.82')
        self.assertEqual(forwarded.full_url, pinned)
        cdn = 'https://release-assets.githubusercontent.com/synthetic?signature=opaque'
        self.assertEqual(handler.redirect_request(forwarded, *args, cdn).full_url, cdn)
        for bad in ('https://github.com/Other/Repo/releases/download/v0.6.82/RELEASE.json',
                    'http://github.com/OpenAhoy/OpenAhoy-Releases/releases/download/v0.6.82/RELEASE.json',
                    pinned.replace('/v0.6.82/', '/v0.6.82-rc1/'), cdn):
            with self.assertRaisesRegex(updates.UpdateCheckUnavailable, 'REDIRECT_REFUSED'):
                updates.StableRedirect().redirect_request(initial, *args, bad)

        def opener(redirect):
            def open_metadata(probe, *, timeout):
                self.assertEqual(probe.full_url, updates.LATEST_MANIFEST_URL)
                self.assertIn('no-cache', probe.headers['Cache-control'])
                redirect.redirect_request(probe, *args, pinned)
                return BytesIO(json.dumps(release_row('0.6.82')).encode())
            return Mock(open=open_metadata)

        with patch.object(updates.request, 'build_opener', side_effect=opener):
            self.assertEqual(updates.published_stable()['version'], '0.6.82')

    def test_release_metadata_binds_target_platform_and_origin(self):
        item = release_row('0.6.82')
        self.assertEqual(updates.release_metadata(json.dumps(item).encode(), '0.6.82'), item)
        for replacement in ({'tag': 'v0.6.80'}, {'asset_url': 'https://invalid.example/file.zip'},
                            {'schema': True}, {'contains_user_accounts': 0},
                            {'sha256': 'a' * 63}, {'marketplace': 'rewritten'}):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(
                    updates.UpdateCheckUnavailable, 'RELEASE_CHANNEL_INVALID'):
                updates.release_metadata(json.dumps(item | replacement).encode(), '0.6.82')


class Install(unittest.TestCase):
    def test_cli_uses_unique_enabled_market_and_reports_read_timeout(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CODEX_HOME=directory):
            config = Path(directory) / 'config.toml'
            config.write_text('[plugins."wechat-ecosystem@shared"]\nenabled=true\n'
                              '[plugins."wechat-ecosystem@old"]\nenabled=false\n')
            config.chmod(0o600)
            process = Mock(returncode=0, stdout=b'{"installed":[]}')
            with patch.object(installation.subprocess, 'run', return_value=process) as run:
                installation.cli('list')
                self.assertEqual(run.call_args.args[0][1:], ['plugin', 'list', '--marketplace', 'shared', '--json'])
                config.write_text(config.read_text().replace('enabled=false', 'enabled=true'))
                with self.assertRaisesRegex(WCEError, 'UPDATE_INSTALLED_VERSION_CHANGED'):
                    installation.cli('list')
                self.assertEqual(run.call_count, 1)
                run.side_effect = subprocess.TimeoutExpired('codex', 90)
                with self.assertRaisesRegex(WCEError, 'UPDATE_CLI_LIST_TIMEOUT'):
                    installation.cli('list', '--marketplace', 'shared')
                with self.assertRaises(subprocess.TimeoutExpired):
                    installation.cli('add', 'wechat-ecosystem@shared')

    def test_display_phase_distinguishes_preinstall_read_from_unknown_write(self):
        for phase, error, state, code in (
            ('STAGED', WCEError('UPDATE_CLI_LIST_TIMEOUT'), 'FAILED', 'UPDATE_CLI_LIST_TIMEOUT'),
            ('INSTALLING', subprocess.TimeoutExpired('codex', 90), 'INSTALL_UNKNOWN', 'UPDATE_CLI_ACTION_TIMEOUT'),
        ):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                def stop(previous, version, target, manifest, registry, folder, progress):
                    progress(phase)
                    raise error
                worker = installation.UpdateInstaller(
                    '0.7.107', Path(directory) / 'connections.json', switch=stop,
                    download=lambda _v, _r, where, _p: (where / 'payload', MANIFEST),
                    checker=lambda _: {'state':'UPDATE_AVAILABLE', 'latest_version':'0.7.108',
                                       'advertised_revision':PIN})
                request = os.urandom(16).hex()
                worker.start('0.7.108', PIN, request)
                self.join_workers()
                receipt = json.loads((worker.root / 'status.json').read_bytes())
                self.assertEqual((receipt['state'], receipt['code'], receipt['failed_phase']), (state, code, phase))

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name).resolve()
        self.workers = []
        native_thread = installation.Thread

        def remember_worker(*args, **kwargs):
            worker = native_thread(*args, **kwargs)
            self.workers.append(worker)
            return worker

        tracker = patch.object(installation, 'Thread', side_effect=remember_worker)
        tracker.start()
        self.addCleanup(tracker.stop)
        self.addCleanup(self.join_workers)

    def join_workers(self):
        for worker in self.workers:
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def await_status(self, worker, request_id):
        for _ in range(200):
            row = worker.status(request_id)
            if row['state'] not in installation.ACTIVE:
                return row
            time.sleep(.01)
        self.fail('The isolated worker did not reach a terminal receipt')

    def test_selected_version_is_rechecked_before_download(self):
        for advertisement, code in [
            ({'state': 'CHECK_UNAVAILABLE'}, 'UPDATE_CHECK_UNAVAILABLE'),
            ({'state': 'UPDATE_AVAILABLE', 'latest_version': '0.6.83', 'advertised_revision': PIN},
             'UPDATE_ADVERTISEMENT_CHANGED'),
            ({'state': 'UPDATE_AVAILABLE', 'latest_version': '0.6.82', 'advertised_revision': 'b' * 40},
             'UPDATE_ADVERTISEMENT_CHANGED'),
        ]:
            with self.subTest(code=code):
                worker = installation.UpdateInstaller(
                    '0.6.76', self.path / 'connections.json', checker=Mock(return_value=advertisement),
                    download=Mock(), switch=Mock())
                request_id = os.urandom(16).hex()
                worker.start('0.6.82', PIN, request_id)
                self.assertEqual(self.await_status(worker, request_id)['code'], code)
                worker.download.assert_not_called()
                worker.switch.assert_not_called()

    def test_download_with_a_different_manifest_never_reaches_the_switch(self):
        def download(_, __, stage, progress):
            return stage / 'payload', 'e' * 64
        worker = installation.UpdateInstaller(
            '0.6.81', self.path / 'connections.json', switch=Mock(), download=download,
            checker=Mock(return_value={'state': 'UPDATE_AVAILABLE', 'latest_version': '0.6.82',
                                       'advertised_revision': PIN, 'package_manifest_sha256': MANIFEST}))
        request_id = '1' * 32
        worker.start('0.6.82', PIN, request_id)
        self.assertEqual(self.await_status(worker, request_id)['code'], 'UPDATE_MANIFEST_MISMATCH')
        worker.switch.assert_not_called()
        self.assertFalse((worker.root / ('0.6.82-' + PIN) / 'verified.json').exists())

    def test_existing_unknown_install_cannot_be_overwritten_by_a_new_version(self):
        worker = installation.UpdateInstaller('0.6.76', self.path / 'connections.json',
                                              checker=Mock(), download=Mock(), switch=Mock())
        worker.root.mkdir(mode=0o700)
        previous = {'state': 'INSTALL_UNKNOWN', 'request_id': 'a' * 32, 'version': '0.6.81',
                    'revision': PIN, 'code': 'UPDATE_INSTALL_READBACK_FAILED'}
        record = worker.root / 'status.json'
        atomic_write(record, previous)
        original = record.read_bytes()
        self.assertEqual(worker.start('0.6.82', PIN, 'b' * 32), previous)
        self.assertEqual(record.read_bytes(), original)
        worker.checker.assert_not_called()

    def test_older_receipt_without_an_id_is_archived_before_a_new_attempt(self):
        worker = installation.UpdateInstaller('0.6.81', self.path / 'connections.json',
            checker=Mock(return_value={'state': 'CHECK_UNAVAILABLE'}), download=Mock(), switch=Mock())
        worker.root.mkdir(mode=0o700)
        receipt = worker.root / 'status.json'
        atomic_write(receipt, {'state': 'INSTALLED_RELOAD_REQUIRED', 'version': '0.6.81'})
        original = receipt.read_bytes()
        request_id = '3' * 32
        worker.start('0.6.82', PIN, request_id)
        self.assertEqual(self.await_status(worker, request_id)['code'], 'UPDATE_CHECK_UNAVAILABLE')
        archived = worker.root / ('retained-' + sha256(original).hexdigest() + '.json')
        self.assertEqual(archived.read_bytes(), original)

    def test_default_branch_gets_verified_previous_tag_before_switch(self):
        prior = b'original verified manifest bytes'
        digest = sha256(prior).hexdigest()
        with patch.object(installation, 'build_opener') as build:
            fetch = build.return_value.open
            fetch.return_value = BytesIO(prior)
            self.assertEqual(installation._stable_rollback_ref('0.6.81', None, digest), 'v0.6.81')
            self.assertTrue(fetch.call_args.args[0].endswith('/v0.6.81/package-manifest.json'))
            fetch.return_value = BytesIO(b'wrong package')
            with self.assertRaisesRegex(WCEError, 'UPDATE_ROLLBACK_REF_UNAVAILABLE'):
                installation._stable_rollback_ref('0.6.81', 'main', digest)
        self.assertEqual(installation._stable_rollback_ref('0.6.81', 'v0.6.81', digest), 'v0.6.81')
        with self.assertRaisesRegex(WCEError, 'UPDATE_MARKETPLACE_UNSUPPORTED'):
            installation._stable_rollback_ref('0.6.81', 'elsewhere', digest)


if __name__ == '__main__':
    unittest.main()
