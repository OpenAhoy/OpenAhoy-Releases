"""Local test-only upload admission and atomic typed fixture receipts.

No network route, real token loader, recovery send or model-facing tool.
Admission is the durable commit, not the physical transport entry point.
"""
import json
import math
import re
from threading import Lock
from uuid import uuid4
from urllib.parse import urlsplit

from .contracts import Actor, WCEError
from .http_transport import HTTPResponse
from .local_preparation import ref, MAX_ASSET_BYTES
from .service import canonical, digest
from .upload_preparation import UploadPreparer
from . import upload_wire as wire

PROVENANCE = 'LOCAL_FIXED_FIXTURE'


class FixtureUploadSender:
    """Fixed in-process synthetic replies; captured request never enters repr."""
    mode = 'test'

    def __init__(self):
        self.calls = 0
        self.last_request = None
        self._lock = Lock()

    def send(self, request, timeout):
        path = urlsplit(request.path).path
        if (self.mode != 'test' or request.test_only is not True or request.method != 'POST'
                or timeout != 10 or path not in wire.ENDPOINTS.values()):
            raise WCEError('CANDIDATE_TEST_ONLY')
        with self._lock:
            self.calls += 1
            self.last_request = request
        result = {'url': 'https://fixture.invalid/wce/image', 'errcode': 0}
        if path == wire.ENDPOINTS['permanent_cover']:
            result['media_id'] = 'fixture-upload-media'
        return HTTPResponse(200, canonical(result).encode())


def _selector(bundle, version, content_digest, slot):
    ref(bundle, 'bundle')
    ref(version, 'version')
    if (not isinstance(content_digest, str) or re.fullmatch('[a-f0-9]{64}', content_digest) is None
            or not isinstance(slot, str) or re.fullmatch('[A-Za-z0-9_-]{1,64}', slot) is None):
        raise WCEError('INVALID_UPLOAD_CONTEXT')
    return {'bundle_id': bundle, 'version': version, 'content_digest': content_digest, 'slot': slot}


def _key(value):
    if not isinstance(value, str) or re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is None:
        raise WCEError('INVALID_UPLOAD_CONTEXT')


def _intent(descriptor):
    value = json.loads(descriptor)
    del value['token_revision']
    return value | {'mode': 'test', 'protocol_version': 1}


def _target(intent):
    return digest({'mode': intent['mode'],
                   'binding': {k: intent['binding'][k] for k in ('tenant', 'principal', 'connection', 'resource')},
                   'selector': {k: intent[k] for k in ('bundle_id', 'version', 'content_digest', 'slot')},
                   'purpose': intent['purpose'],
                   'asset': {k: intent['asset'][k] for k in ('asset_ref', 'sha256', 'size')}})


class UploadExecutor:
    mode = 'test'

    def __init__(self, service, sender=None):
        self.service = service
        self.preparer = UploadPreparer(service)
        self.sender = FixtureUploadSender() if sender is None else sender
        self._sender_guard()

    def _sender_guard(self):
        if (self.mode != 'test' or type(self.sender) is not FixtureUploadSender or self.sender.mode != 'test'
                or self.service.adapter.mode != 'mock'
                or self.service.adapter.workflow_mode not in {'offline', 'fixture'}):
            raise WCEError('CANDIDATE_TEST_ONLY')

    def _deadline(self, db, actor, connection):
        values = (db.execute('SELECT expires FROM sessions WHERE id=?', (actor.session_id,)).fetchone()[0],
                  db.execute('SELECT expires FROM grants WHERE connection=? AND principal=?',
                             (connection, actor.principal_id)).fetchone()[0],
                  db.execute('SELECT expires FROM connections WHERE id=?', (connection,)).fetchone()[0],
                  self.service.lifecycle.registry(db, connection)['token_expires'])
        now = self.service.clock()
        if (not isinstance(now, (int, float)) or not math.isfinite(now)
                or any(type(x) not in (int, float) or not math.isfinite(x) or x <= now for x in values)):
            raise WCEError('UPLOAD_LEASE_EXPIRED')
        return min(values)

    def _lease_gate(self, deadline):
        now = self.service.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now >= deadline:
            raise WCEError('UPLOAD_LEASE_EXPIRED')

    def _validated(self, row):
        try:
            if len(row['intent'].encode()) > 16384 or len(row['selector'].encode()) > 1024:
                raise ValueError()
            intent, selector = json.loads(row['intent']), json.loads(row['selector'])
            if canonical(intent) != row['intent'] or canonical(selector) != row['selector']:
                raise ValueError()
            if set(intent) != {'schema', 'mode', 'protocol_version', 'bundle_id', 'version', 'content_digest',
                               'slot', 'purpose', 'binding', 'asset', 'path', 'official_source', 'official_source_sha256'}:
                raise ValueError()
            selected = _selector(intent['bundle_id'], intent['version'], intent['content_digest'], intent['slot'])
            b, asset, purpose = intent['binding'], intent['asset'], intent['purpose']
            if (selected != selector or type(intent['schema']) is not int or intent['schema'] != 1
                    or type(intent['protocol_version']) is not int or intent['protocol_version'] != 1
                    or intent['mode'] != 'test' or row['mode'] != 'test' or row['provenance'] != PROVENANCE
                    or set(b) != {'tenant', 'principal', 'connection', 'resource', 'generation', 'epoch'}
                    or any(not isinstance(b[k], str) or not b[k] or len(b[k]) > 128
                           for k in ('tenant', 'principal', 'connection', 'resource'))
                    or any(type(b[k]) is not int or b[k] < 0 for k in ('generation', 'epoch'))
                    or any(row[k] != b[k] for k in ('tenant', 'principal', 'connection', 'resource'))
                    or purpose not in wire.ENDPOINTS or purpose != row['purpose']
                    or intent['path'] != wire.ENDPOINTS[purpose]
                    or intent['official_source'] != wire.SOURCE_URLS[purpose]
                    or intent['official_source_sha256'] != wire.SOURCE_HASHES[purpose]
                    or set(asset) != {'asset_ref', 'role', 'declared_type', 'size', 'sha256'}
                    or asset['declared_type'] not in {'image/png', 'image/jpeg'}
                    or asset['role'] != ('cover' if purpose == 'permanent_cover' else 'body')
                    or (intent['slot'] == 'cover') != (purpose == 'permanent_cover')
                    or type(asset['size']) is not int or not 0 < asset['size'] <= MAX_ASSET_BYTES
                    or re.fullmatch('[a-f0-9]{64}', asset['sha256']) is None
                    or digest(intent) != row['fingerprint'] or _target(intent) != row['target']
                    or re.fullmatch('local-upload-[a-f0-9]{32}', row['id']) is None
                    or re.fullmatch('[a-f0-9]{64}', row['fence']) is None
                    or re.fullmatch('[a-f0-9]{32}', row['owner']) is None
                    or type(row['token_revision']) is not int or row['token_revision'] < 0
                    or type(row['created']) not in (int, float) or not math.isfinite(row['created'])):
                raise ValueError()
            ref(asset['asset_ref'], 'asset')
            _key(row['request_key'])
            fields = (row['cover_media_id'], row['cover_url'], row['body_url'])
            if row['state'] == 'RESULT_UNKNOWN':
                if fields != (None, None, None) or row['completed'] is not None:
                    raise ValueError()
            elif row['state'] == 'FIXTURE_SUCCEEDED':
                if type(row['completed']) not in (int, float) or not math.isfinite(row['completed']):
                    raise ValueError()
                if purpose == 'permanent_cover':
                    if (not isinstance(fields[0], str) or re.fullmatch('[A-Za-z0-9_-]{1,128}', fields[0]) is None
                            or not wire._url(fields[1]) or fields[2] is not None):
                        raise ValueError()
                elif fields[:2] != (None, None) or not wire._url(fields[2]):
                    raise ValueError()
            else:
                raise ValueError()
            return selector
        except Exception:
            raise WCEError('UPLOAD_JOURNAL_CORRUPT') from None

    def _view(self, row):
        selector = self._validated(row)
        return {'attempt_id': row['id'], 'request_key': row['request_key'], 'state': row['state'],
                'mode': 'test', 'provenance': PROVENANCE, 'connection_id': row['connection'],
                'resource_id': row['resource'], 'selector': selector, 'fingerprint': row['fingerprint'],
                'cover_media_id': row['cover_media_id'], 'cover_url': row['cover_url'], 'body_url': row['body_url'],
                'test_only': True, 'platform_verified': False, 'platform_ready': False, 'connected': False}

    def _history(self, db, actor, connection, request_key, selector=None):
        try:
            binding, fence = self.service.local._guard(db, actor, connection)
        except (ValueError, TypeError, OverflowError):
            raise WCEError('UPLOAD_AUTHORIZATION_INVALID') from None
        self._deadline(db, actor, connection)
        row = db.execute("SELECT * FROM upload_attempts WHERE mode='test' AND tenant=? AND principal=? "
                         'AND connection=? AND request_key=?',
                         (actor.tenant_id, actor.principal_id, connection, request_key)).fetchone()
        if row is not None:
            saved = self._validated(row)
            if row['resource'] != binding['resource']:
                raise WCEError('ACCESS_DENIED')
            if selector is not None and saved != selector:
                raise WCEError('IDEMPOTENCY_CONFLICT')
            view = self._view(row)
            self.service.local._final(db, actor, connection, fence)
            self._deadline(db, actor, connection)
            return view
        return None

    def status(self, actor, connection_id, request_key):
        _key(request_key)
        with self.service.db.transaction(write=True) as db:
            result = self._history(db, actor, connection_id, request_key)
            if result is None:
                raise WCEError('UPLOAD_NOT_FOUND')
            return result

    def _snapshot(self, db, actor, connection, selector):
        try:
            snapshot = self.preparer._snapshot(db, actor, connection, **{
                'bundle': selector['bundle_id'], 'version': selector['version'],
                'content_digest': selector['content_digest'], 'slot': selector['slot']})
        except (ValueError, TypeError, OverflowError):
            raise WCEError('UPLOAD_AUTHORIZATION_INVALID') from None
        return snapshot, self._deadline(db, actor, connection)

    def _recheck(self, db, actor, connection, selector, snapshot, deadline):
        current, _ = self._snapshot(db, actor, connection, selector)
        if current != snapshot:
            raise WCEError('UPLOAD_CONTEXT_CHANGED')
        self.service.local._final(db, actor, connection, snapshot[2], True)
        self._lease_gate(deadline)

    def execute(self, actor, connection_id, bundle_id, version, content_digest, slot, request_key):
        self._sender_guard()
        _key(request_key)
        selector = _selector(bundle_id, version, content_digest, slot)
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection_id, request_key, selector)
            if old is not None:
                return old
            snapshot, deadline = self._snapshot(db, actor, connection_id, selector)
        descriptor, data, fence, secret_ref = snapshot
        context, intent = json.loads(descriptor), _intent(descriptor)
        try:
            secret = self.service.secrets.get(actor.tenant_id, connection_id, secret_ref)
            wire.secret_value(secret)
        except Exception:
            raise WCEError('UPLOAD_SECRET_UNAVAILABLE') from None
        metadata = {'intent': intent, 'selector': selector, 'request_key': request_key}
        if wire.contains_secret(metadata, secret):
            raise WCEError('UPLOAD_SECRET_CONTAMINATION')
        request = wire.build_request(context['purpose'], context['asset']['declared_type'], data, secret)
        fingerprint, target, owner = digest(intent), _target(intent), uuid4().hex
        attempt_id = 'local-upload-' + uuid4().hex
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection_id, request_key, selector)
            if old is not None:
                return old
            self._sender_guard()
            self._recheck(db, actor, connection_id, selector, snapshot, deadline)
            if db.execute('SELECT 1 FROM upload_attempts WHERE target=?', (target,)).fetchone():
                raise WCEError('UPLOAD_TARGET_REGISTERED')
            b = intent['binding']
            if db.execute("SELECT 1 FROM upload_attempts WHERE mode='test' AND tenant=? AND resource=? "
                          "AND purpose=? AND state='RESULT_UNKNOWN'", (b['tenant'], b['resource'], context['purpose'])).fetchone():
                raise WCEError('UNRESOLVED_UPLOAD')
            values = (attempt_id, 'test', PROVENANCE, b['tenant'], b['principal'], connection_id, b['resource'],
                      request_key, context['purpose'], canonical(selector), canonical(intent), fingerprint, target,
                      fence, context['token_revision'], owner, 'RESULT_UNKNOWN', self.service.clock())
            if wire.contains_secret(values, secret):
                raise WCEError('UPLOAD_SECRET_CONTAMINATION')
            db.execute('INSERT INTO upload_attempts VALUES(' + ','.join('?' for _ in range(18)) + ',NULL,NULL,NULL,NULL)', values)
            self.service.local._final(db, actor, connection_id, fence, True)
            self._lease_gate(deadline)
        # Only this successful admission may send; no DB lock during I/O.
        try:
            self._sender_guard()
            response = self.sender.send(request, timeout=10)
            reply = wire.parse_response(context['purpose'], response, secret)
            if reply.classification == 'PARSED_SUCCESS':
                with self.service.db.transaction(write=True) as db:
                    self._recheck(db, actor, connection_id, selector, snapshot, deadline)
                    fields = (reply.media_id, reply.url, None) if context['purpose'] == 'permanent_cover' else (None, None, reply.url)
                    if wire.contains_secret(fields, secret):
                        raise WCEError('UPLOAD_SECRET_CONTAMINATION')
                    changed = db.execute("UPDATE upload_attempts SET state='FIXTURE_SUCCEEDED',completed=?,"
                                         'cover_media_id=?,cover_url=?,body_url=? WHERE id=? AND owner=? '
                                         "AND state='RESULT_UNKNOWN' AND fingerprint=? AND target=? AND fence=? AND intent=? "
                                         'AND request_key=? AND selector=? AND token_revision=? AND created=? '
                                         'AND mode=? AND provenance=? AND tenant=? AND principal=? AND connection=? '
                                         'AND resource=? AND purpose=?',
                                         (self.service.clock(),) + fields + (attempt_id, owner, fingerprint, target, fence, canonical(intent),
                                         request_key, canonical(selector), context['token_revision'], values[-1], 'test', PROVENANCE,
                                         b['tenant'], b['principal'], connection_id, b['resource'], context['purpose']))
                    if changed.rowcount != 1:
                        raise WCEError('UPLOAD_CLAIM_CHANGED')
                    row = db.execute('SELECT * FROM upload_attempts WHERE id=?', (attempt_id,)).fetchone()
                    self._validated(row)
                    if wire.contains_secret(self._view(row), secret):
                        raise WCEError('UPLOAD_SECRET_CONTAMINATION')
                    self.service.local._final(db, actor, connection_id, fence, True)
                    self._lease_gate(deadline)
        except Exception:
            pass  # Retain the committed UNKNOWN; no refresh, retry or exception text.
        return self.status(actor, connection_id, request_key)
