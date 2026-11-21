"""Recover an existing AutoDL task through the ordinary status route."""
from hashlib import sha256
import errno
import io
import json
from pathlib import Path
import socket
import ssl
import sys
from tempfile import TemporaryDirectory
from typing import NamedTuple
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))
from wce.contracts import Secret
from wce.own_connection_policy import atomic_write
from wce.support_protocol import PREVIEW, SupportRouter
from wce.video_jobs import Jobs, PROMO_DIR, media_facts
from wce.video_protocol import STATUS, WORKSPACE, VideoRouter
from wce.video_relay import (
    OFFICIAL_AUTODL_HOST, OFFICIAL_AUTODL_MEDIA_HOST, PUBLIC_DNS_REQUIRED,
    RELAY_MODEL, WORKFLOW, AutoDLMediaHTTPSConnection, PublicDestinationError, Relay,
    autodl_public_addresses, public_destination,
)
from wce.video_seedance import MAX_RESULT

PROJECT = '1' * 32
ATTEMPT = 'relay-original-attempt'
TASK = 'relay-original-task'
ORIGIN = 'https://relay.example.com'
QUERY = ORIGIN + WORKFLOW + 'result/' + TASK
OLD = 'https://cdn.example.com/old.mp4?sig=private-test-url'
NEW = 'https://cdn.example.com/new.mp4?sig=private-test-url'
KEY = 'private-test-authorization'
LEGACY_ALIAS = 'tos7-public.cn-beijing.tos.volces.com'
OBSERVED_ALIAS = 'tos27-cp-public.cn-beijing.tos.volces.com'
PUBLIC_IP = '116.136.45.114'
FAKE_IP = '198.18.0.10'


def dns_payload(alias=None, *, host=OFFICIAL_AUTODL_MEDIA_HOST, addresses=(PUBLIC_IP,)):
    answers = [{'name': host + '.', 'type': 5, 'data': alias}] if alias is not None else []
    owner = alias.removesuffix('.') if alias is not None else host
    answers.extend({'name': owner + '.', 'type': 1, 'data': ip} for ip in addresses)
    return {'Status': 0, 'TC': False, 'Question': [{'name': host + '.', 'type': 1}], 'Answer': answers}


def dns_reply(payload):
    response = Mock()
    response.status = 200
    response.getheader.return_value = 'application/dns-json; charset=utf-8'
    response.read.return_value = json.dumps(payload).encode()
    return response


def socket_rows(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in addresses]


class RelayMediaDNS(unittest.TestCase):
    def setUp(self):
        resolver = patch('wce.video_relay.HTTPSConnection')
        self.resolver = resolver.start()
        self.addCleanup(resolver.stop)

    def test_both_observed_cnames_and_direct_a_answers_resolve(self):
        for alias in (LEGACY_ALIAS, LEGACY_ALIAS + '.', OBSERVED_ALIAS, OBSERVED_ALIAS + '.', None):
            with self.subTest(alias=alias):
                self.resolver.return_value.getresponse.return_value = dns_reply(dns_payload(alias))
                self.assertEqual(list(map(str, autodl_public_addresses(OFFICIAL_AUTODL_MEDIA_HOST))),
                                 [PUBLIC_IP])
        self.resolver.assert_called_with('1.1.1.1', timeout=5)
        self.resolver.return_value.request.assert_called_with(
            'GET', f'/dns-query?name={OFFICIAL_AUTODL_MEDIA_HOST}&type=A',
            headers={'Accept': 'application/dns-json'})

    def test_unexpected_cname_or_wrong_a_owner_are_rejected(self):
        wrong_owner = dns_payload(OBSERVED_ALIAS)
        wrong_owner['Answer'][-1]['name'] = LEGACY_ALIAS + '.'
        multiple = dns_payload(OBSERVED_ALIAS)
        multiple['Answer'].insert(1, dict(multiple['Answer'][0], data=LEGACY_ALIAS + '.'))
        invalid_alias = dns_payload(LEGACY_ALIAS)
        invalid_alias['Answer'][0]['data'] = {'invalid': True}
        for payload in (dns_payload('unknown.cn-beijing.tos.volces.com'), wrong_owner, multiple, invalid_alias):
            with self.subTest(answers=payload['Answer']):
                self.resolver.return_value.getresponse.return_value = dns_reply(payload)
                with self.assertRaises(ValueError):
                    autodl_public_addresses(OFFICIAL_AUTODL_MEDIA_HOST)

    def test_fallback_checks_every_address_and_does_not_expand_the_media_host_rule(self):
        rows = Mock(return_value=socket_rows(FAKE_IP))
        self.resolver.return_value.getresponse.return_value = dns_reply(
            dns_payload(OBSERVED_ALIAS, addresses=(PUBLIC_IP, '192.168.1.1')))
        with self.assertRaises(PublicDestinationError) as error:
            public_destination(OFFICIAL_AUTODL_MEDIA_HOST, 443, resolve=rows,
                               fallback_host=OFFICIAL_AUTODL_MEDIA_HOST)
        self.assertEqual(str(error.exception), 'Relay destination must resolve to a public address')
        self.resolver.reset_mock()
        for host, port in (('other.example.com', 443), (OBSERVED_ALIAS, 443),
                           (OFFICIAL_AUTODL_MEDIA_HOST, 8443)):
            with self.subTest(host=host, port=port), self.assertRaises(PublicDestinationError):
                public_destination(host, port, resolve=rows, fallback_host=OFFICIAL_AUTODL_MEDIA_HOST)
        self.resolver.assert_not_called()
        self.resolver.return_value.getresponse.return_value = dns_reply(
            dns_payload(OBSERVED_ALIAS, host=OFFICIAL_AUTODL_HOST))
        with self.assertRaises(ValueError):
            autodl_public_addresses(OFFICIAL_AUTODL_HOST)

    def test_public_ip_is_pinned_and_tls_verifies_original_media_hostname(self):
        self.resolver.return_value.getresponse.return_value = dns_reply(dns_payload(OBSERVED_ALIAS))
        context = ssl.create_default_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        connection = AutoDLMediaHTTPSConnection(OFFICIAL_AUTODL_MEDIA_HOST, timeout=25, context=context)
        with patch('wce.video_relay.socket.getaddrinfo', return_value=socket_rows(FAKE_IP)), \
                patch('wce.video_relay.socket.create_connection') as dial, \
                patch.object(context, 'wrap_socket', side_effect=ssl.SSLCertVerificationError) as tls:
            with self.assertRaises(ssl.SSLCertVerificationError):
                connection.connect()
        dial.assert_called_once_with((PUBLIC_IP, 443), 25, None)
        tls.assert_called_once_with(dial.return_value, server_hostname=OFFICIAL_AUTODL_MEDIA_HOST)


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

    def test_original_task_survives_public_dns_timeout_then_recovers_with_observed_cname(self):
        media = 'https://' + OFFICIAL_AUTODL_MEDIA_HOST + '/synthetic-result.mp4'
        self.opener.entries = [status_result(media), Entry(media, Response(self.fixture)),
                               status_result(media), Entry(media, Response(self.fixture))]
        open_fixture = self.opener.open

        def open_with_dns(request, *, timeout):
            response = open_fixture(request, timeout=timeout)
            if request.host == OFFICIAL_AUTODL_MEDIA_HOST:
                try:
                    AutoDLMediaHTTPSConnection.connect_public((request.host, 443), timeout, None)
                except PublicDestinationError as error:
                    response.data.close()
                    raise URLError(error) from None
            return response

        with patch.object(self.opener, 'open', side_effect=open_with_dns), \
                patch('wce.video_relay.HTTPSConnection') as resolver, \
                patch('wce.video_relay.socket.getaddrinfo', return_value=socket_rows(FAKE_IP)), \
                patch('wce.video_relay.socket.create_connection') as dial:
            resolver.return_value.request.side_effect = [TimeoutError, None]
            resolver.return_value.getresponse.return_value = dns_reply(dns_payload(OBSERVED_ALIAS + '.'))
            result = self.run_status()
            self.assertEqual(result['state'], 'SAVE_PENDING')
            self.assertEqual(result['download_error'], PUBLIC_DNS_REQUIRED)
            self.assertFalse(self.artifact.exists())
            dial.assert_not_called()
            self.assertEqual(self.opener.requests, [QUERY, media])
            row = json.loads(self.receipt.read_text())
            for field in ('generation_attempt_id', 'provider_task_id', 'relay_connection'):
                self.assertEqual(row[field], self.original[field])
            self.assert_ready([QUERY, media, QUERY, media])
            dial.assert_called_once_with((PUBLIC_IP, 443), 25, None)

    def test_advertised_oversize_stays_pending_without_downloading_or_requerying(self):
        response = Response(self.fixture, length=MAX_RESULT + 1)
        response.read1 = Mock(side_effect=AssertionError('Oversize content must not be read'))
        self.opener.entries = [status_result(OLD), Entry(OLD, response)]
        result = self.run_status()
        self.assertEqual((result['state'], result['download_error']), ('SAVE_PENDING', 'VIDEO_RESULT_TOO_LARGE'))
        self.assertFalse(self.artifact.exists())
        self.assertEqual(self.opener.requests, [QUERY, OLD])
        response.read1.assert_not_called()

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
