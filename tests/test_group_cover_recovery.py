"""Exercise persisted original group cover recovery with an offline provider."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))

from wce import own_cover_authority as auth
from wce.contracts import Secret, WCEError
from wce.draft_revision_guard import identity_binding
from wce.draft_revision_store import RevisionStore
from wce.http_transport import HTTPResponse, HTTPSender
from wce.own_connection_broker import AccountService
from wce.own_connection_policy import atomic_write, enable, proposal
from wce.own_connection_tools import ConnectionRouter
from wce.own_store import OwnStore
from wce.service import digest


def png(color, level=6):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 5, 4, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\x00' + bytes([color, 40, 190]) * 5) * 4, level))
            + chunk(b'IEND', b''))


def source(title, mime, data):
    encoded = base64.b64encode(data).decode()
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>'
            '<style>body{margin:0;font-size:16px;line-height:1.45}'
            'article{display:flex;flex-direction:column;max-width:640px;margin:auto}</style></head>'
            f'<body><article><p>{title} body</p><img src="data:{mime};base64,{encoded}" alt="Sample">'
            '</article></body></html>').encode()


def response(value):
    return HTTPResponse(200, json.dumps(value).encode())


class GroupCoverRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix='openahoy-cover-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / 'images').mkdir(mode=0o700)
        db = self.root / 'state.sqlite3'
        db.touch(mode=0o600)
        self.profile = self.root / 'profile.json'
        self.registry = self.root / 'connections.json'
        identity = {'actor': {'tenant_id': 'test-tenant', 'principal_id': 'test-owner',
                              'client_id': 'test-client', 'session_id': 'test-session'},
                    'connection_id': 'test-connection', 'appid': 'wx0000000000000000',
                    'resource_id': 'wx0000000000000000', 'generation': 1, 'epoch': 0,
                    'private_directory': str(self.root)}
        atomic_write(self.profile, identity | {'schema': 1, 'source_kind': 'OPERATOR_ATTESTED', 'expires_at': 1})
        RevisionStore(self.root, digest(identity_binding(identity, 'OPERATOR_ATTESTED')), lambda: None).initialize()
        self.enterContext(patch('wce.own_connection_policy.code_scope', return_value='d' * 64))
        self.policy = enable(proposal(self.profile), self.registry)
        OwnStore(db, 'OPERATOR_ATTESTED')
        self.sender = self.enterContext(patch.object(HTTPSender, 'send', side_effect=AssertionError('UNEXPECTED_REQUEST')))
        self.enterContext(patch.object(socket, 'socket', side_effect=AssertionError('NETWORK_FORBIDDEN')))
        self.token_reads = 0
        self.start_service()

    def start_service(self):
        self.service = AccountService(self.policy)
        token = SimpleNamespace(token=Secret('FIXTURE_ONLY_TOKEN'), wall_deadline=time.time()+3600)

        def get(guard, *, minimum_validity_seconds=30):
            guard()
            self.token_reads += 1
            return token

        fake = SimpleNamespace(get=get, valid=lambda _: True, clear=lambda: None)
        self.service.tokens = self.service.workflow.token_cache = fake

    def call(self, name, **arguments):
        args = {'connection_id': self.policy.data['connection_id']} | arguments
        return self.service.call(name, args, time.monotonic()+300)

    def prepare(self, key, articles):
        sources = []
        for article_id, title, mime, data in articles:
            raw = source(title, mime, data)
            path = self.root / f'{key}-{article_id}.html'
            path.write_bytes(raw)
            sources.append({'absolute_path': str(path), 'article_id': article_id,
                'expected_sha256': sha256(raw).hexdigest(), 'metadata': {'author': '测试', 'digest': ''}})
        router = ConnectionRouter(launcher=self.root / 'fixture-do-not-start.py')
        with (patch('wce.own_connection_tools.resolve', return_value=self.policy),
              patch('wce.own_connection_tools.ensure_started'),
              patch('wce.own_connection_tools.call', side_effect=lambda policy, name, args: self.call(name, **args))):
            prepared = router.call('own.documents.prepare', {'connection_id': self.policy.data['connection_id'],
                'request_key': key, 'html_sources': sources})
        return {k: prepared[k] for k in ('bundle_id', 'version', 'content_digest')}

    def upload(self, selector, key, slot, payload):
        before = self.sender.side_effect
        self.sender.side_effect = lambda request, timeout: response(payload)
        try:
            return self.call('own.uploads.execute', request_key=key, slot=slot, **selector)
        finally:
            self.sender.side_effect = before

    def prepare_group(self, raw, mime='image/png', first=None):
        selector = self.prepare('group', [('first', 'First article', 'image/png', first or png(21)),
                                         ('second', 'Second article', mime, raw)])
        first = self.upload(selector, 'first-cover', 'first--cover',
            {'media_id': 'offline-first-cover', 'url': 'https://mmbiz.qpic.cn/mmbiz_png/first/0?wx_fmt=png'})
        self.assertEqual(first['state'], 'SUCCEEDED', first)
        body = self.upload(selector, 'first-body', 'first--body1',
            {'url': 'https://mmbiz.qpic.cn/mmbiz_png/body/0?wx_fmt=png'})
        self.assertEqual(body['state'], 'SUCCEEDED', body)
        second = self.upload(selector, 'second-cover', 'second--cover', {'errcode': -1})
        self.assertEqual(second['state'], 'RESULT_UNKNOWN', second)
        self.sender.reset_mock()
        self.token_reads = 0
        return selector, second

    def row(self, key='second-cover'):
        with self.service.workflow.db.transaction() as db:
            return dict(db.execute('SELECT * FROM own_steps WHERE request_key=?', (key,)).fetchone())

    def grant(self):
        reviewed = auth.proposal(self.policy, 'second-cover')
        self.assertEqual(reviewed['target']['title'], 'Second article')
        self.assertEqual(reviewed['target']['asset']['slot'], 'second--cover')
        return auth.publish(self.policy, reviewed, 'fixture-review', time.time())

    def material(self, data, *, media_id='offline-second-cover', name='cover.png'):
        material = {'media_id': media_id, 'name': name, 'update_time': int(self.row()['created']),
                    'url': 'https://mmbiz.qpic.cn/mmbiz_png/target/0?wx_fmt=png'}

        def dispatch(request, _timeout):
            path = urlsplit(request.path).path
            if path.endswith('/batchget_material'):
                return response({'total_count': 1, 'item_count': 1, 'item': [material]})
            if path.endswith('/get_material'):
                assert json.loads(request.body) == {'media_id': media_id}
                return HTTPResponse(200, data)
            raise AssertionError('RECOVERY_REPEATED_A_WRITE')

        self.sender.side_effect = dispatch

    def reconcile(self):
        return self.call('own.uploads.reconcile', request_key='second-cover')

    def assert_cached(self, attempt_id):
        self.sender.reset_mock()
        before = self.token_reads
        cached = self.reconcile()
        self.assertEqual((cached['attempt_id'], cached['state']), (attempt_id, 'SUCCEEDED'))
        self.start_service()
        cold = self.reconcile()
        self.assertEqual((cold['attempt_id'], cold['slot'], cold['state']), (attempt_id, 'second--cover', 'SUCCEEDED'))
        self.assertEqual(self.sender.call_count, 0)
        self.assertEqual(self.token_reads, before)

    def test_html_second_slot_uses_exact_approval_and_preserves_original(self):
        _, receipt = self.prepare_group(png(22))
        before = self.row()
        self.assertEqual([(a['title'], a['request_key']) for a in auth.candidates(self.registry)],
                         [('Second article', 'second-cover')])
        with self.assertRaisesRegex(WCEError, 'COVER_READ_REVIEW_REQUIRED'):
            self.reconcile()
        with self.assertRaisesRegex(WCEError, 'CONNECTION_SCOPE_MISMATCH'):
            self.call('own.uploads.reconcile', connection_id='different-account', request_key='second-cover')
        self.assertEqual(self.token_reads, 0)
        self.assertEqual(self.sender.call_count, 0)
        grant = self.grant()
        value = json.loads((self.root / auth.filename(grant)).read_bytes())
        self.assertEqual(value['schema'], 1)
        self.assertEqual(value['pixel_policy'], auth.png_policy())
        self.material(png(22, level=0))
        recovered = self.reconcile()
        self.assertEqual(recovered['state'], 'EXISTING_COVER_READ_MATCHED')
        self.assertEqual(recovered['attempt_id'], receipt['attempt_id'])
        self.assertEqual(recovered['read_counts'], {'list': 2, 'image': 2})
        after = self.row()
        self.assertEqual(after['state'], 'SUCCEEDED')
        for key in ('id', 'slot', 'request_key', 'target', 'owner', 'approval_digest', 'intent_digest'):
            self.assertEqual(after[key], before[key])
        result = json.loads(after['result'])
        proof = json.loads((self.root / result['reconciliation_proof']).read_bytes())
        self.assertEqual(proof['schema'], 3)
        self.assertEqual(self.row('first-cover')['state'], 'SUCCEEDED')
        self.assert_cached(receipt['attempt_id'])

    def test_multipage_inventory_completes_both_original_material_reads(self):
        original = png(32)
        _, receipt = self.prepare_group(original)
        self.grant()
        created = int(self.row()['created'])
        items = [{'media_id': f'material-{i}', 'name': 'earlier.png', 'update_time': created - 40,
                  'url': f'https://mmbiz.qpic.cn/mmbiz_png/material-{i}/0?wx_fmt=png'}
                 for i in range(40)]
        items.append({'media_id': 'the-second-cover', 'name': 'cover.png', 'update_time': created,
                      'url': 'https://mmbiz.qpic.cn/mmbiz_png/the-second-cover/0?wx_fmt=png'})
        offsets, images = [], []

        def dispatch(request, _timeout):
            path = urlsplit(request.path).path
            query = json.loads(request.body)
            if path.endswith('/batchget_material'):
                start = query['offset']
                page = items[start:start+query['count']]
                offsets.append(start)
                return response({'total_count': len(items), 'item_count': len(page), 'item': page})
            if path.endswith('/get_material'):
                images.append(query['media_id'])
                return HTTPResponse(200, original)
            self.fail('recovery dispatched a write')

        self.sender.side_effect = dispatch
        matched = self.reconcile()
        self.assertEqual(matched['state'], 'EXISTING_COVER_READ_MATCHED', matched)
        self.assertEqual(matched['attempt_id'], receipt['attempt_id'])
        self.assertEqual(offsets, [0, 20, 40, 0, 20, 40])
        self.assertEqual(images, ['the-second-cover'] * 2)
        self.assert_cached(receipt['attempt_id'])

    def test_rejects_reusing_other_slot_media_even_if_its_raster_matches(self):
        self.prepare_group(png(22), first=png(22))
        self.grant()
        self.material(png(22), media_id='offline-first-cover')
        self.assertEqual(self.reconcile()['error'], 'OWN_RECONCILE_MATERIAL_ALREADY_ASSOCIATED')
        self.assertEqual(self.row()['state'], 'RESULT_UNKNOWN')
        self.assertFalse(list(self.root.glob('reconciliation-*.json')))

    def test_overlapping_unresolved_write_with_same_pixels_is_ambiguous(self):
        competitor = self.prepare('competitor', [('other', 'Unrelated title', 'image/png', png(22, level=0))])
        first = self.upload(competitor, 'other-cover', 'other--cover', {'errcode': -1})
        self.assertEqual(first['state'], 'RESULT_UNKNOWN')
        self.prepare_group(png(22))
        self.grant()
        self.material(png(22))
        self.assertEqual(self.reconcile()['error'], 'OWN_RECONCILE_COMPETING_ORIGINAL')
        self.assertEqual(self.row()['state'], 'RESULT_UNKNOWN')
        self.assertEqual(self.row('other-cover')['state'], 'RESULT_UNKNOWN')
        self.assertFalse(list(self.root.glob('reconciliation-*.json')))

    @unittest.skipUnless(Path('/usr/bin/sips').is_file(), 'JPEG HTML preparation uses macOS sips')
    def test_jpeg_uses_exact_transport_bytes_and_cold_proof(self):
        png_file, jpeg_file = self.root / 'sample.png', self.root / 'sample.jpg'
        png_file.write_bytes(png(22))
        subprocess.run(['/usr/bin/sips', '-s', 'format', 'jpeg', str(png_file), '-o', str(jpeg_file)],
                       check=True, capture_output=True)
        raw = jpeg_file.read_bytes()
        _, receipt = self.prepare_group(raw, 'image/jpeg')
        grant = self.grant()
        value = json.loads((self.root / auth.filename(grant)).read_bytes())
        self.assertEqual(value['schema'], 2)
        self.assertEqual(value['match_policy'], auth.jpeg_policy())
        self.material(raw[:2] + b'\xff\xfe\x00\x05alt' + raw[2:], name='cover.jpg')
        self.assertEqual(self.reconcile()['error'], 'OWN_RECONCILE_NO_UNIQUE_MATCH')
        self.assertEqual(self.row()['state'], 'RESULT_UNKNOWN')
        self.grant()  # A fresh simulated Settings grant for the second test.
        self.material(raw, name='cover.jpg')
        self.assertEqual(self.reconcile()['state'], 'EXISTING_COVER_READ_MATCHED')
        result = json.loads(self.row()['result'])
        proof = json.loads((self.root / result['reconciliation_proof']).read_bytes())
        self.assertEqual(result['completion_origin'], auth.JPEG_ORIGIN)
        self.assertEqual(proof['schema'], 4)
        self.assertEqual(proof['observation']['remote_input_sha256'], sha256(raw).hexdigest())
        self.assert_cached(receipt['attempt_id'])
