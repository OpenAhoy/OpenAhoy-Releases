from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest import TestCase
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))

from wce import ace_panel
from wce.contracts import WCEError
from wce.own_connection_policy import atomic_write
from wce.suno_panel import scoped_configuration
from wce.video_protocol import AUDIO_IMPORT, AUDIO_MIX, MEDIA_PREPARE, WORKSPACE, VideoRouter


class Catalog:
    catalog = {'get_account': {'inputSchema': {'type': 'object'}}, 'list_songs': {
        'inputSchema': {'properties': {'limit': {'type': 'integer', 'maximum': 8}, 'cursor': {'type': 'string'}}}}}

    def __init__(self, account=None):
        self.account = {'plan': 'free', 'plan_name': 'Free', 'credits': 0,
                        'credits_per_create_song': 4,
                        'models': [{'id': 'model-1', 'name': 'ACE Fixture', 'credits_per_create_song': 0}]}
        if account is not None:
            self.account = account
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == 'get_account':
            return self.account
        if name == 'list_songs':
            return {'songs': [{'song_id': 'original-id', 'title': 'Original', 'status': 'complete',
                               'song_page': 'https://acemusic.ai/song/share-id', 'can_download': True,
                               'playback_url': 'https://acemusic.ai/audio/original-id.mp3'}],
                    'next_cursor': 'page-2'}
        raise AssertionError(name)


class AceMusicRead(TestCase):
    @contextmanager
    def client(self, tool):
        with patch.object(ace_panel, 'codex_client', return_value=self.context(tool)) as mock:
            yield
            mock.assert_called_once_with(ace_panel.ACE)

    @staticmethod
    @contextmanager
    def context(tool):
        yield tool

    def test_unbound_stops_before_starting_remote_client_and_scope_isolated(self):
        ace = ace_panel.ACE
        record = [{'name': ace.name, 'enabled': True, 'transport': {'url': ace.endpoint}, 'auth_status': 'not_logged_in'}]
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(record).encode())
        with patch('pathlib.Path.is_file', return_value=True), patch('wce.suno_panel.subprocess.run', return_value=result) as command, \
             patch('wce.suno_panel.scoped_client') as client:
            self.assertEqual(ace_panel.snapshot(), {'state': 'UNAVAILABLE', 'code': 'ACE_CODEX_AUTH_REQUIRED'})
        client.assert_not_called()
        self.assertIn('mcp_servers.ace-music.url="https://acemusic.ai/mcp"', command.call_args.args[0])
        self.assertNotIn('mcp_servers.suno.url="https://api.suno.com/mcp"', command.call_args.args[0])
        self.assertIn('mcp_servers.suno.url="https://api.suno.com/mcp"', scoped_configuration())

    def test_zero_models_original_track_and_denied_download(self):
        tool = Catalog()
        with self.client(tool):
            result = ace_panel.snapshot('page-1')
        self.assertEqual(result['state'], 'CONNECTED')
        self.assertEqual(result['account']['plan'], 'Free')
        self.assertEqual(result['account']['credits'], 0)
        self.assertEqual(result['account']['generation_cost'], 4)
        self.assertEqual(result['account']['models'][0]['cost'], 0)
        row = result['library']['items'][0]
        self.assertFalse(row['can_download'])
        self.assertTrue(row['play'].endswith('original-id.mp3'))
        self.assertEqual(row['page'], 'https://acemusic.ai/song/share-id')
        self.assertEqual(result['library']['cursor'], 'page-2')
        self.assertEqual(tool.calls, [('get_account', {}), ('list_songs', {'limit': 8, 'cursor': 'page-1'})])

    def test_missing_values_and_paid_permission_are_preserved(self):
        for data in ({}, {'plan': 'Pro', 'can_download': True}):
            tool = Catalog(data)
            with self.client(tool):
                response = ace_panel.snapshot()
            self.assertNotIn('credits', response['account'])
            self.assertNotIn('generation_cost', response['account'])
            self.assertNotIn('models', response['account'])
            self.assertIs(response['library']['items'][0]['can_download'], True)
        self.assertEqual(ace_panel.account_view({'credits': True, 'credits_per_create_song': -1}), {})

    def test_official_song_page_without_file_or_identity_still_supports_listening(self):
        data = {'songs': [{'id': 'internal-id', 'title': 'Already created', 'status': 'ready',
                           'song_page': 'https://acemusic.ai/song/share-code', 'lyrics': 'internal',
                           'cover_url': 'https://acemusic.ai/upload/cover.png'}]}
        self.assertEqual(ace_panel.library_view(data, can_page=False, can_download=False),
                         {'items': [{'id': 'internal-id', 'title': 'Already created', 'status': 'ready',
                                     'page': 'https://acemusic.ai/song/share-code', 'play': '', 'can_download': False}]})

    def test_changed_remote_catalog_is_unavailable_without_guessed_call(self):
        tool = Catalog()
        tool.catalog = {'get_account': {}, 'list_songs': {
            'inputSchema': {'required': ['unrecognized'], 'properties': {}}}}
        with self.client(tool):
            result = ace_panel.snapshot()
        self.assertIsNone(result['library'])
        self.assertEqual(tool.calls, [('get_account', {})])

    def test_bad_links_and_unknown_permission_are_not_promoted(self):
        for value in ('https://other.example/file.mp3', 'http://acemusic.ai/file.mp3',
                      'https://acemusic.ai@other.example/file', 'https://acemusic.ai/\\other.example',
                      'https://acemusic.ai/audio#fragment', 'file:///secret', None):
            self.assertEqual(ace_panel.official_url(value), '')
        result = ace_panel.library_view({'songs': [{'id': 'original', 'status': 'running'}]}, can_page=False)
        self.assertNotIn('can_download', result['items'][0])


class AceMusicAuthorization(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.lock = Path(temp.name) / 'ace.lock'
        self.spawned = []

    def fixture(self, seconds=3, exit_after=False):
        def spawn(command, **options):
            self.spawned.append((command, options))
            return subprocess.Popen([sys.executable, '-IB', '-c',
                                     'import time; time.sleep(0.05)' if exit_after else 'import time; time.sleep(30)'],
                                    **options)
        instance = ace_panel.Authorizer(lock_path=self.lock, popen=spawn, timeout=seconds)
        self.addCleanup(instance.cancel)
        return instance

    def terminal(self, instance, expected):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            state = instance.status()['state']
            if state == expected:
                return
            time.sleep(0.02)
        self.fail(f'Expected {expected}, got {state}')

    def test_one_listener_across_open_close_cancel_and_retry(self):
        owner = self.fixture()
        other = self.fixture()
        with patch.object(ace_panel, 'codex_binary', return_value=Path('/isolated/codex')):
            self.assertEqual(owner.begin(), {'state': 'AUTHORIZING'})
            self.assertEqual(owner.status(), {'state': 'AUTHORIZING'})
            self.assertEqual(owner.begin(), {'state': 'AUTHORIZING'})
            self.assertEqual(other.begin(), {'state': 'AUTHORIZING_ELSEWHERE'})
            self.assertEqual(len(self.spawned), 1)
            self.assertEqual(owner.cancel(), {'state': 'CANCELLING'})
            self.terminal(owner, 'CANCELLED')
            self.assertEqual(other.begin(), {'state': 'AUTHORIZING'})
        self.assertEqual(len(self.spawned), 2)
        command, options = self.spawned[0]
        self.assertEqual(command[1:6], ['mcp', 'login', 'ace-music', '--scopes', 'songs:read,songs:create'])
        self.assertEqual(options['env']['CODEX_HOME'], options['cwd'])
        self.assertEqual(options['stdout'], subprocess.DEVNULL)

    def test_success_and_expired_attempt(self):
        successful = self.fixture(exit_after=True)
        expired = self.fixture(seconds=0.08)
        with patch.object(ace_panel, 'codex_binary', return_value=Path('/isolated/codex')):
            successful.begin()
            self.terminal(successful, 'AUTHORIZED')
            expired.begin()
            self.terminal(expired, 'AUTH_EXPIRED')


class AceMusicAssets(TestCase):
    def test_import_and_mix_reuse_original_assets(self):
        with TemporaryDirectory() as location:
            private = Path(location).resolve() / 'private'
            router = VideoRouter(None, private / 'connections.json')
            project = router.call(MEDIA_PREPARE, {})
            root = Path(project['root'])
            source = root / 'fixture.wav'
            with wave.open(str(source), 'wb') as output:
                output.setparams((1, 2, 16000, 32000, 'NONE', 'not compressed'))
                output.writeframes(bytes(64000))
            track_hash = sha256(source.read_bytes()).hexdigest()
            args = {'project_id': project['project_id'], 'attempt_id': 'audio-first', 'title': 'Fixture',
                    'audio': {'path': 'fixture.wav', 'sha256': track_hash}, 'provider': 'ace-music',
                    'provider_id': 'original-song'}
            row = router.call(AUDIO_IMPORT, args)
            self.assertEqual(row, router.call(AUDIO_IMPORT, args))
            self.assertEqual(row['provider_id'], 'original-song')
            self.assertEqual(router.call(WORKSPACE, {'action': 'audio_library'})['assets'][0]['provider'], 'ace-music')
            self.assertEqual(sha256((root / row['file']).read_bytes()).hexdigest(), track_hash)
            with self.assertRaisesRegex(WCEError, 'AUDIO_ATTEMPT_CONFLICT'):
                router.call(AUDIO_IMPORT, dict(args, provider='suno'))

            jobs = router.video_jobs
            jobs._directory()
            receipt, file = jobs._paths('original-video')
            subprocess.run(['/opt/homebrew/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=blue:s=160x90:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(file)],
                           check=True, timeout=15)
            file.chmod(0o600)
            content = file.read_bytes()
            video_hash = sha256(content).hexdigest()
            atomic_write(receipt, {'generation_attempt_id': 'original-video', 'state': 'ASSET_READY',
                                   'request': {'project_id': project['project_id']},
                                   'asset': {'sha256': video_hash, 'bytes': len(content), 'seconds': 1.0,
                                             'width': 160, 'height': 90}})
            mixed = router.call(AUDIO_MIX, {'project_id': project['project_id'], 'attempt_id': 'first-mix',
                'title': 'Mixed', 'song_attempt_id': row['attempt_id'], 'video_attempt_id': 'original-video',
                'timeline': {'video_start_ms': 0, 'music_offset_ms': 0, 'fade_in_ms': 0,
                             'fade_out_ms': 0, 'volume_percent': 50, 'keep_original': False}})
            self.assertEqual(mixed['state'], 'ASSET_READY')
            self.assertEqual(mixed['video_sha256'], video_hash)
            self.assertEqual(sha256(file.read_bytes()).hexdigest(), video_hash)
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), track_hash)
