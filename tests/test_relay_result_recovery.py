"""Recover an existing AutoDL task through the ordinary status route."""
from hashlib import sha256
import errno
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import NamedTuple
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))
from wce.contracts import Secret
from wce.own_connection_policy import atomic_write
from wce.support_protocol import PREVIEW, SupportRouter
from wce.video_jobs import Jobs, PROMO_DIR, media_facts
from wce.video_protocol import STATUS, WORKSPACE, VideoRouter
from wce.video_relay import RELAY_MODEL, WORKFLOW, Relay

PROJECT = '1' * 32
ATTEMPT = 'relay-original-attempt'
TASK = 'relay-original-task'
ORIGIN = 'https://relay.example.com'
QUERY = ORIGIN + WORKFLOW + 'result/' + TASK
OLD = 'https://cdn.example.com/old.mp4?sig=private-test-url'
NEW = 'https://cdn.example.com/new.mp4?sig=private-test-url'
KEY = 'private-test-authorization'


class Response:
    def __init__(self, data, *, length=None, disconnected=False, media='video/mp4'):
        self.data = io.BytesIO(data)
        self.status = 200
        self.headers = {'Content-Type': media, 'Content-Length': str(len(data) if length is None else length)}
        self.disconnected = disconnected

    def read(self, size):
        chunk = self.data.read(size)
        if not chunk and self.disconnected:
            raise ConnectionResetError('private-test-error')
        return chunk

    read1 = read

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.data.close()


class Entry(NamedTuple):
    url: str
    answer: object


class Opener:
    def __init__(self, test):
        self.test = test
        self.entries = []
        self.requests = []

    def open(self, request, *, timeout):
        self.test.assertTrue(self.entries, 'unexpected second recovery request or submission')
        entry = self.entries.pop(0)
        self.requests.append(request.full_url)
        self.test.assertEqual(request.get_method(), 'GET')
        self.test.assertEqual(request.full_url, entry.url)
        self.test.assertEqual(request.get_header('Authorization'), KEY if entry.url == QUERY else None)
        if isinstance(entry.answer, Exception):
            raise entry.answer
        return entry.answer


def status_result(*urls, task=TASK, status='success'):
    return Entry(QUERY, Response(json.dumps({'code': 'Success', 'data': {
        'task_id': task, 'status': status, 'results': list(urls)}}).encode(), media='application/json'))


class NoOtherTools:
    def list_tools(self):
        return []


class RelayResultRecovery(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.project_root = self.root / 'project'
        self.project_root.mkdir(mode=0o700)
        self.opener = Opener(self)
        self.connection = 'fixture-original-connection'
        self.jobs = Jobs(self.root / 'connections.json',
                         relay_credential=lambda: (ORIGIN, self.connection, Secret(KEY)),
                         relay=lambda origin: Relay(origin, opener=self.opener))
        project = {'id': PROJECT, 'name': 'Fixture project', 'root': str(self.project_root)}
        self.jobs._directory()
        self.project_view = patch.object(self.jobs.projects, 'view', return_value={'projects': [project]})
        self.project_view.start()
        self.addCleanup(self.project_view.stop)
        self.receipt, self.artifact = self.jobs._paths(ATTEMPT)
        stat = self.project_root.stat()
        self.original = {'generation_attempt_id': ATTEMPT, 'created_at': 1, 'state': 'SAVE_PENDING',
                         'request': {'project_id': PROJECT, 'model': RELAY_MODEL, 'mode': 'workflow'},
                         'provider_task_id': TASK, 'relay_connection': self.connection,
                         'download_error': 'VIDEO_DOWNLOAD_INCOMPLETE',
                         'project_video_root': [stat.st_dev, stat.st_ino]}
        atomic_write(self.receipt, self.original)
        self.fixture = (PROMO_DIR / 'openahoy-intro.mp4').read_bytes()
        router = VideoRouter(NoOtherTools(), registry=self.root / 'connections.json')
        router.video_jobs = self.jobs
        self.router = SupportRouter(router, version='0.6.89', registry=self.root / 'connections.json')

    def run_status(self, project=PROJECT):
        return self.router.call(STATUS, {'generation_attempt_id': ATTEMPT, 'project_id': project, 'poll': True})

    def assert_ready(self, expected_requests):
        self.assertEqual(self.run_status()['state'], 'ASSET_READY')
        expected_hash = sha256(self.fixture).hexdigest()
        self.assertEqual(sha256(self.artifact.read_bytes()).hexdigest(), expected_hash)
        self.assertTrue(media_facts(self.artifact)['playable'])
        self.assertEqual(self.run_status()['state'], 'ASSET_READY')
        saved = list(self.project_root.rglob('*.mp4'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(sha256(saved[0].read_bytes()).hexdigest(), expected_hash)
        self.assertEqual(self.opener.requests, expected_requests)
        self.assertFalse(self.opener.entries)
        self.assertEqual(list(self.jobs.root.glob('.video-*')), [])
        row = json.loads(self.receipt.read_text())
        self.assertEqual(row['provider_task_id'], TASK)
        self.assertEqual(row['relay_connection'], self.connection)
        self.assertNotIn('download_diagnostic', row)
        self.assertNotIn('download_error', row)

    def test_healthy_existing_result_is_ready_and_no_second_request_on_repeat(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(self.fixture))]
        self.assert_ready([QUERY, OLD])

    def test_interrupted_stream_requeries_same_task_and_commits_only_the_complete_file(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(self.fixture[:4096], disconnected=True)),
                               status_result(NEW), Entry(NEW, Response(self.fixture))]
        self.assert_ready([QUERY, OLD, QUERY, NEW])

    def test_expired_or_temporarily_unavailable_url_recovers_from_the_original_task(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, HTTPError(OLD, 403, 'expired', {}, io.BytesIO(b''))),
                               status_result(NEW), Entry(NEW, Response(self.fixture))]
        self.assert_ready([QUERY, OLD, QUERY, NEW])

    def test_two_short_downloads_remain_pending_and_feedback_sanitizes_evidence(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(b'first', length=200)),
                               status_result(NEW), Entry(NEW, Response(b'part', length=200))]
        result = self.router.call(WORKSPACE, {'action': 'status', 'project_id': PROJECT,
                                              'generation_attempt_id': ATTEMPT})
        self.assertEqual(result['state'], 'SAVE_PENDING')
        stored = json.loads(self.receipt.read_text())
        self.assertEqual(stored['download_error'], 'VIDEO_RELAY_DOWNLOAD_LENGTH_MISMATCH')
        self.assertEqual(stored['download_diagnostic'], {'http_status': 200, 'received_bytes': 4})
        self.assertEqual(stored['provider_task_id'], TASK)
        self.assertFalse(self.artifact.exists())
        self.assertEqual(list(self.jobs.root.glob('.video-*')), [])
        event = self.router.support.logs.snapshot()['events'][-1]
        self.assertEqual((event['code'], event['http_status'], event['received_bytes']),
                         ('VIDEO_RELAY_DOWNLOAD_LENGTH_MISMATCH', 200, 4))
        self.assertEqual(self.router.call(PREVIEW, {'description': 'Synthetic interrupted download'})['state'],
                         'PREPARED')
        for secret in (OLD, NEW, KEY, TASK, str(self.root)):
            self.assertNotIn(secret, json.dumps(event))

    def test_local_staging_failure_does_not_request_a_second_result(self):
        self.opener.entries = [status_result(OLD)]
        with patch('wce.video_jobs.tempfile.mkstemp', side_effect=OSError(errno.ENOSPC, 'fixture')):
            result = self.run_status()
        self.assertEqual(result['state'], 'SAVE_PENDING')
        self.assertEqual(result['download_error'], 'VIDEO_ASSET_SAVE_FAILED')
        self.assertEqual(self.opener.requests, [QUERY])

    def test_receipt_write_failure_is_reported_as_local_with_original_preserved(self):
        row = dict(self.original, state='RUNNING',
                   download_diagnostic={'http_status': 200, 'received_bytes': 12})
        atomic_write(self.receipt, row)
        self.opener.entries = [status_result(OLD)]
        with patch('wce.video_jobs.atomic_write', side_effect=OSError(errno.ENOSPC, 'fixture')):
            result = self.run_status()
        self.assertEqual(result['state'], 'SAVE_PENDING')
        self.assertEqual(result['download_error'], 'VIDEO_ASSET_SAVE_FAILED')
        self.assertFalse(result['diagnostic_persisted'])
        self.assertNotIn('download_diagnostic', result)
        self.assertEqual(json.loads(self.receipt.read_text()), row)
        self.assertEqual(self.opener.requests, [QUERY])

    def test_receipt_finalization_failure_keeps_verified_file_and_recovers_from_disk(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(self.fixture))]

        def write(path, row, **options):
            if row['state'] == 'ASSET_READY':
                raise OSError(errno.ENOSPC, 'fixture')
            atomic_write(path, row, **options)

        with patch('wce.video_jobs.atomic_write', side_effect=write):
            result = self.run_status()
        self.assertEqual(result['state'], 'SAVE_PENDING')
        self.assertEqual(result['download_error'], 'VIDEO_ASSET_SAVE_FAILED')
        self.assertFalse(result['diagnostic_persisted'])
        self.assertTrue(self.artifact.exists())
        self.assert_ready([QUERY, OLD])

    def test_download_checks_deadline_between_incremental_reads(self):
        media = Response(self.fixture)

        def no_full_read(size):
            self.fail('Download attempted a full buffered read')

        media.read = no_full_read
        self.opener.entries = [status_result(OLD), Entry(OLD, media), status_result(NEW),
                               Entry(NEW, Response(self.fixture))]
        with patch('wce.video_relay.monotonic', side_effect=[0, 0, 45, 90, *([91] * 256)]):
            self.assert_ready([QUERY, OLD, QUERY, NEW])

    def test_mismatched_identity_and_ambiguous_result_never_download(self):
        self.assertEqual(self.run_status('2' * 32)['state'], 'NOT_FOUND')
        self.connection = 'fixture-other-connection'
        self.assertEqual(self.run_status()['query_error'], 'VIDEO_RELAY_CONNECTION_CHANGED')
        self.assertEqual(self.opener.requests, [])
        self.connection = 'fixture-original-connection'
        self.opener.entries = [status_result(OLD, task='different-task'), status_result(OLD, NEW)]
        self.assertEqual(self.run_status()['query_error'], 'VIDEO_TASK_ID_MISMATCH')
        self.assertEqual(self.run_status()['download_error'], 'VIDEO_RELAY_RESULT_UNAVAILABLE')
        self.assertEqual(self.opener.requests, [QUERY, QUERY])
        self.assertFalse(self.artifact.exists())

    def test_complete_nonvideo_is_rejected_without_a_retry(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(b'not a playable mp4'))]
        self.assertEqual(self.run_status()['download_error'], 'VIDEO_RESULT_INVALID')
        self.assertFalse(self.artifact.exists())
        self.assertEqual(self.opener.requests, [QUERY, OLD])

    def test_unchecked_media_redirect_is_rejected_without_following_location(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, HTTPError(
            OLD, 302, 'redirect', {'Location': 'https://unchecked.example.com'}, io.BytesIO(b'')))]
        self.assertEqual(self.run_status()['download_error'], 'VIDEO_RELAY_DOWNLOAD_RESPONSE_INVALID')
        self.assertEqual(self.opener.requests, [QUERY, OLD])

    def test_readback_during_recovery_keeps_last_verified_remote_success(self):
        self.opener.entries = [status_result(OLD), Entry(OLD, Response(b'fragment', disconnected=True)),
                               status_result(task='another-task')]
        result = self.run_status()
        self.assertEqual(result['state'], 'SAVE_PENDING')
        self.assertEqual(result['query_error'], 'VIDEO_TASK_ID_MISMATCH')
        self.assertEqual(result['download_error'], 'VIDEO_RELAY_DOWNLOAD_STREAM_LOST')
        self.assertFalse(self.artifact.exists())
