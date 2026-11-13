"""Trusted prepared news -> local durable add, followed by explicit actual GET.

No model route, platform material mapping, recovery send or live transport.
Admission commit authorizes one live invocation; two database commits are not
atomic. UNKNOWN is persistent and cannot be consumed as a new send claim.
"""
from dataclasses import dataclass
from html import escape
import json
import math
import re
from urllib.parse import urlencode
from uuid import uuid4

from .contracts import WCEError
from .draft_wire import DraftGetCodec
from .http_transport import HTTPRequest, HTTPResponse
from .local_preparation import ref
from .prepared_draft_fixture import (FixturePreparedDraftSender, _FixtureContext,
                                    decode_json, reference_valid, validate_article, PROVENANCE)
from .service import canonical, digest
from .upload_executor import UploadExecutor
from . import upload_wire as wire

PURPOSE = 'prepared-draft-create'
RENDERER_VERSION = PROTOCOL_VERSION = 1
SOURCES = {
    'add': {'url': 'https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html',
            'sha256': 'cb18600f28cf8a2bfbe5680f27eb077f7722d8d3728f26e21888cd3565f784bc'},
    'get': {'url': 'https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_getdraft.html',
            'sha256': '2a020ac8630f53d6eccdad4243786db34ddabfb5851424c9842302224ac52192'},
}
ROW_FIELDS = ('id', 'mode', 'provenance', 'tenant', 'principal', 'connection', 'resource', 'request_key',
              'purpose', 'selector', 'intent', 'fingerprint', 'target', 'fence', 'token_revision', 'owner',
              'state', 'created', 'completed', 'renderer_version', 'protocol_version', 'projection_digest',
              'uploads', 'reference')
UPLOAD_FIELDS = ('id', 'mode', 'provenance', 'tenant', 'principal', 'connection', 'resource', 'request_key',
                 'purpose', 'selector', 'intent', 'fingerprint', 'target', 'fence', 'token_revision', 'owner',
                 'state', 'created', 'completed', 'cover_media_id', 'cover_url', 'body_url')


def _key(value):
    if not isinstance(value, str) or re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is None:
        raise WCEError('INVALID_PREPARED_DRAFT_CONTEXT')


def _hex(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def _selector(bundle, version, content_digest):
    ref(bundle, 'bundle')
    ref(version, 'version')
    if not _hex(content_digest):
        raise WCEError('INVALID_PREPARED_DRAFT_CONTEXT')
    return {'bundle_id': bundle, 'version': version, 'content_digest': content_digest}


def _target(intent):
    return digest({'mode': 'test', 'purpose': PURPOSE, 'selector': intent['selector'],
                   'binding': {k: intent['binding'][k] for k in ('tenant', 'principal', 'connection', 'resource')}})


def _mapping(uploads):
    return [{'slot': item['slot'], 'upload_id': item['row']['id'],
             'asset': json.loads(item['row']['intent'])['asset'],
             'selector': json.loads(item['row']['selector']), 'intent': json.loads(item['row']['intent']),
             'fingerprint': item['row']['fingerprint'], 'target': item['row']['target'],
             'cover_media_id': item['row']['cover_media_id'], 'cover_url': item['row']['cover_url'],
             'body_url': item['row']['body_url']} for item in uploads]


def render_article(article, uploads, renderer_version=1):
    """Version 1: text LF -> br, text HT literal; alt LF/HT -> numeric entities."""
    if type(renderer_version) is int and renderer_version == 2:
        from .documents import normalize, render_projection
        document = normalize(article)
        mappings = {i['slot']: ({'media_id': i['row']['cover_media_id']} if i['row'].get('cover_media_id') else
                               {'url': i['row']['body_url']}) for i in uploads}
        return render_projection(document, mappings)
    if type(renderer_version) is not int or renderer_version != RENDERER_VERSION:
        raise WCEError('PREPARED_RENDERER_UNSUPPORTED')
    if not isinstance(article['title'], str) or len(article['title']) > 32:
        raise WCEError('INVALID_PREPARED_NEWS')
    selected = {item['slot']: item['row'] for item in uploads}
    result = []
    tags = {'paragraph': 'p', 'heading': 'h2', 'quote': 'blockquote'}
    for block in article['blocks']:
        if block['type'] in tags:
            tag = tags[block['type']]
            text = escape(block['text'], quote=True).replace('\n', '<br>')
            result.append(f'<{tag}>{text}</{tag}>')
        else:
            url = selected[block['slot']]['body_url']
            if not wire._url(url):
                raise WCEError('PREPARED_UPLOAD_MAPPING_INVALID')
            alt = escape(block['alt'], quote=True).replace('\n', '&#10;').replace('\t', '&#9;')
            result.append('<img src="' + escape(url, quote=True) + '" alt="' + alt + '">')
    projected = {'title': article['title'], 'content': ''.join(result),
                 'thumb_media_id': selected['cover']['cover_media_id']}
    validate_article(projected)
    return projected


def _request(kind, payload, secret):
    return HTTPRequest('POST', '/cgi-bin/draft/' + kind + '?' + urlencode({'access_token': wire.secret_value(secret)}),
                       {'Content-Type': 'application/json; charset=utf-8'}, canonical(payload).encode(), test_only=True)


def _response_value(response, secret):
    if (type(response) is not HTTPResponse or type(response.status) is not int
            or not 200 <= response.status < 300 or wire.contains_secret(response.body, secret)):
        raise WCEError('INVALID_PREPARED_DRAFT_RESPONSE')
    value = decode_json(response.body)
    if not isinstance(value, dict) or wire.contains_secret(value, secret) or type(value.get('errcode', 0)) is not int:
        raise WCEError('INVALID_PREPARED_DRAFT_RESPONSE')
    if value.get('errcode', 0) != 0:
        raise WCEError('PREPARED_DRAFT_EFFECT_UNKNOWN')
    if 'errmsg' in value and (not isinstance(value['errmsg'], str) or len(value['errmsg']) > 2048):
        raise WCEError('INVALID_PREPARED_DRAFT_RESPONSE')
    return value


def _add_reply(response, secret):
    try:
        value = _response_value(response, secret)
        if set(value) - {'media_id', 'errcode', 'errmsg'} or not reference_valid(value.get('media_id')):
            return None
        return value['media_id']
    except Exception:
        return None


def _get_reply(response, secret, reference):
    try:
        value = _response_value(response, secret)
        if set(value) - {'news_item', 'errcode', 'errmsg'}:
            return None
        reply = DraftGetCodec(reference).response(response)
        if reply.state != 'SUCCEEDED' or len(reply.items) != 1:
            return None
        return {k: reply.items[0][k] for k in ('title', 'content', 'thumb_media_id')}
    except Exception:
        return None


@dataclass(frozen=True, repr=False)
class _Snapshot:
    intent: str
    uploads: str
    article: str
    fence: str
    secret_ref: str
    token_revision: int

    def context(self):
        intent = json.loads(self.intent)
        scope = {k: intent['binding'][k] for k in ('tenant', 'principal', 'connection', 'resource')}
        return _FixtureContext(canonical(scope), canonical(intent['selector']),
                               intent['renderer_version'], intent['projection_digest'])


class PreparedDraftExecutor:
    mode = 'test'

    def __init__(self, service, sender=None):
        self.service = service
        self._service_guard()
        self.uploads = UploadExecutor(service)
        self.sender = sender if sender is not None else FixturePreparedDraftSender(
            str(service.db.path) + '.prepared-fixture.sqlite', service.clock)
        self._sender_guard()

    def _service_guard(self):
        if (self.mode != 'test' or self.service.adapter.mode != 'mock'
                or self.service.adapter.workflow_mode not in {'offline', 'fixture'}):
            raise WCEError('CANDIDATE_TEST_ONLY')

    def _sender_guard(self):
        self._service_guard()
        if (type(self.sender) is not FixturePreparedDraftSender or self.sender.mode != 'test'
                or self.sender.store.path.resolve() == self.service.db.path.resolve()):
            raise WCEError('CANDIDATE_TEST_ONLY')

    def _deadline(self, db, actor, connection):
        values = (db.execute('SELECT expires FROM sessions WHERE id=?', (actor.session_id,)).fetchone()[0],
                  db.execute('SELECT expires FROM grants WHERE connection=? AND principal=?',
                             (connection, actor.principal_id)).fetchone()[0],
                  db.execute('SELECT expires FROM connections WHERE id=?', (connection,)).fetchone()[0],
                  self.service.lifecycle.registry(db, connection)['token_expires'])
        now = self.service.clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or any(type(x) not in (int, float) or not math.isfinite(x) or x <= now for x in values)):
            raise WCEError('PREPARED_DRAFT_LEASE_EXPIRED')
        return min(values)

    def _lease(self, deadline):
        now = self.service.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now >= deadline:
            raise WCEError('PREPARED_DRAFT_LEASE_EXPIRED')

    def _authorization(self, db, actor, connection, write=False, fence=None):
        try:
            binding, actual = self.service.local._guard(db, actor, connection, write)
            deadline = self._deadline(db, actor, connection)
        except (ValueError, TypeError, OverflowError, RecursionError):
            raise WCEError('PREPARED_DRAFT_AUTHORIZATION_INVALID') from None
        if fence is not None and fence != actual:
            raise WCEError('AUTHORIZATION_CHANGED')
        return binding, actual, deadline

    def _validated(self, row):
        try:
            if set(row.keys()) != set(ROW_FIELDS):
                raise ValueError()
            intent = decode_json(row['intent'].encode(), 131072)
            selector = decode_json(row['selector'].encode(), 2048)
            uploads = decode_json(row['uploads'].encode(), 131072)
            if any(canonical(value) != row[key] for key, value in
                   (('intent', intent), ('selector', selector), ('uploads', uploads))):
                raise ValueError()
            if (set(selector) != {'bundle_id', 'version', 'content_digest'}
                    or _selector(**{'bundle': selector['bundle_id'], 'version': selector['version'],
                                    'content_digest': selector['content_digest']}) != selector
                    or not isinstance(intent, dict) or set(intent) != {'schema', 'mode', 'purpose', 'selector',
                        'binding', 'renderer_version', 'protocol_version', 'projection_digest', 'mapping', 'sources'}
                    or type(intent['schema']) is not int or intent['schema'] != 1
                    or type(intent['renderer_version']) is not int or intent['renderer_version'] != 1
                    or type(intent['protocol_version']) is not int or intent['protocol_version'] != 1
                    or intent['mode'] != 'test' or intent['purpose'] != PURPOSE or intent['sources'] != SOURCES
                    or intent['selector'] != selector or row['mode'] != 'test' or row['provenance'] != PROVENANCE
                    or row['purpose'] != PURPOSE or type(row['renderer_version']) is not int or row['renderer_version'] != 1
                    or type(row['protocol_version']) is not int or row['protocol_version'] != 1
                    or not _hex(row['projection_digest']) or row['projection_digest'] != intent['projection_digest']):
                raise ValueError()
            binding = intent['binding']
            if (not isinstance(binding, dict) or set(binding) != {'tenant', 'principal', 'connection', 'resource', 'generation', 'epoch'}
                    or any(not isinstance(binding[k], str) or not binding[k] or len(binding[k]) > 128
                           or row[k] != binding[k] for k in ('tenant', 'principal', 'connection', 'resource'))
                    or any(type(binding[k]) is not int or binding[k] < 0 for k in ('generation', 'epoch'))
                    or not isinstance(uploads, list) or not 1 <= len(uploads) <= 5):
                raise ValueError()
            slots, ids, assets = [], set(), set()
            for item in uploads:
                if not isinstance(item, dict) or set(item) != {'slot', 'row'} or set(item['row']) != set(UPLOAD_FIELDS):
                    raise ValueError()
                u = item['row']
                selected = self.uploads._validated(u)
                original = json.loads(u['intent'])
                if (selected != selector | {'slot': item['slot']} or original['binding'] != binding
                        or u['state'] != 'FIXTURE_SUCCEEDED' or u['id'] in ids
                        or original['asset']['asset_ref'] in assets):
                    raise ValueError()
                ids.add(u['id'])
                assets.add(original['asset']['asset_ref'])
                slots.append(item['slot'])
            if (slots[0] != 'cover' or len(slots) != len(set(slots)) or _mapping(uploads) != intent['mapping']
                    or digest(intent) != row['fingerprint'] or _target(intent) != row['target']
                    or re.fullmatch('local-prepared-draft-[a-f0-9]{32}', row['id']) is None
                    or re.fullmatch('[a-f0-9]{32}', row['owner']) is None or not _hex(row['fence'])
                    or type(row['token_revision']) is not int or row['token_revision'] < 0
                    or type(row['created']) not in (int, float) or not math.isfinite(row['created'])):
                raise ValueError()
            _key(row['request_key'])
            if row['state'] == 'RESULT_UNKNOWN':
                if row['completed'] is not None or row['reference'] is not None:
                    raise ValueError()
            elif row['state'] == 'FIXTURE_SAVED':
                if (type(row['completed']) not in (int, float) or not math.isfinite(row['completed'])
                        or not reference_valid(row['reference'])):
                    raise ValueError()
            else:
                raise ValueError()
            return intent, selector
        except Exception:
            raise WCEError('PREPARED_DRAFT_JOURNAL_CORRUPT') from None

    def _view(self, row):
        _, selector = self._validated(row)
        return {'attempt_id': row['id'], 'request_key': row['request_key'], 'state': row['state'],
                'connection_id': row['connection'], 'resource_id': row['resource'], 'selector': selector,
                'fingerprint': row['fingerprint'], 'reference': row['reference'], 'mode': 'test',
                'provenance': PROVENANCE, 'test_only': True, 'platform_verified': False,
                'platform_ready': False, 'connected': False}

    def _history(self, db, actor, connection, key, selector=None):
        binding, fence, deadline = self._authorization(db, actor, connection)
        row = db.execute("SELECT * FROM prepared_draft_attempts WHERE mode='test' AND tenant=? AND principal=? "
                         'AND connection=? AND request_key=?',
                         (actor.tenant_id, actor.principal_id, connection, key)).fetchone()
        if row is None:
            return None
        _, saved = self._validated(row)
        if row['resource'] != binding['resource']:
            raise WCEError('ACCESS_DENIED')
        if selector is not None and saved != selector:
            raise WCEError('IDEMPOTENCY_CONFLICT')
        self._view(row)
        self._authorization(db, actor, connection, fence=fence)
        self._lease(deadline)
        return dict(row)

    def status(self, actor, connection_id, request_key):
        _key(request_key)
        with self.service.db.transaction(write=True) as db:
            row = self._history(db, actor, connection_id, request_key)
            if row is None:
                raise WCEError('PREPARED_DRAFT_NOT_FOUND')
            return self._view(row)

    def _snapshot(self, db, actor, connection, selector, write, saved=None):
        binding, fence, deadline = self._authorization(db, actor, connection, write)
        local = self.service.local
        manifest, content_digest = local._bundle(db, binding, selector['bundle_id'], selector['version'])
        if content_digest != selector['content_digest']:
            raise WCEError('PREPARED_DRAFT_CONTENT_MISMATCH')
        original = manifest['binding']
        if write:
            latest = db.execute('SELECT version FROM prepared_versions WHERE bundle=? AND tenant=? AND principal=? '
                                'AND connection=? AND resource=? ORDER BY revision DESC LIMIT 1',
                                (selector['bundle_id'],) + local._scope(binding)).fetchone()
            if latest is None or latest[0] != selector['version']:
                raise WCEError('PREPARED_DRAFT_VERSION_STALE')
            if any(original[k] != binding[k] for k in ('generation', 'epoch')):
                raise WCEError('ASSET_AUTHORIZATION_STALE')
        slots = [('cover', manifest['article']['cover_asset_ref'], 'permanent_cover')]
        slots += [(b['slot'], b['asset_ref'], 'article_body') for b in manifest['article']['blocks'] if b['type'] == 'image']
        assets = {a['asset_ref']: a for a in manifest['assets']}
        uploads = []
        for slot, asset, purpose in slots:
            selected = selector | {'slot': slot}
            rows = db.execute('SELECT * FROM upload_attempts WHERE tenant=? AND principal=? AND connection=? '
                              'AND resource=? AND selector=? AND purpose=?',
                              local._scope(original) + (canonical(selected), purpose)).fetchall()
            if len(rows) != 1:
                raise WCEError('PREPARED_UPLOAD_REQUIRED')
            row = dict(rows[0])
            self.uploads._validated(row)
            expected = {'schema': 1, 'mode': 'test', 'protocol_version': 1, **selected, 'purpose': purpose,
                        'binding': original, 'asset': assets[asset], 'path': wire.ENDPOINTS[purpose],
                        'official_source': wire.SOURCE_URLS[purpose], 'official_source_sha256': wire.SOURCE_HASHES[purpose]}
            if row['state'] != 'FIXTURE_SUCCEEDED' or row['intent'] != canonical(expected):
                raise WCEError('PREPARED_UPLOAD_MAPPING_INVALID')
            uploads.append({'slot': slot, 'row': row})
        renderer = saved['renderer_version'] if saved is not None else RENDERER_VERSION
        article = render_article(manifest['article'], uploads, renderer)
        intent = {'schema': 1, 'mode': 'test', 'purpose': PURPOSE, 'selector': selector, 'binding': original,
                  'renderer_version': renderer, 'protocol_version': PROTOCOL_VERSION,
                  'projection_digest': digest(article), 'mapping': _mapping(uploads), 'sources': SOURCES}
        if saved is not None and (canonical(intent) != saved['intent'] or canonical(uploads) != saved['uploads']
                                  or digest(article) != saved['projection_digest']):
            raise WCEError('PREPARED_DRAFT_SNAPSHOT_CHANGED')
        registry = self.service.lifecycle.registry(db, connection)
        snapshot = _Snapshot(canonical(intent), canonical(uploads), canonical(article), fence,
                             db.execute('SELECT secret_ref FROM connections WHERE id=?', (connection,)).fetchone()[0],
                             registry['token_revision'])
        self._authorization(db, actor, connection, write, fence)
        self._lease(deadline)
        return snapshot, deadline

    def _recheck(self, db, actor, connection, selector, snapshot, deadline, write, saved=None):
        current, _ = self._snapshot(db, actor, connection, selector, write, saved)
        if current != snapshot:
            raise WCEError('PREPARED_DRAFT_CONTEXT_CHANGED')
        if saved is not None:
            row = db.execute('SELECT * FROM prepared_draft_attempts WHERE id=?', (saved['id'],)).fetchone()
            if row is None or dict(row) != saved:
                raise WCEError('PREPARED_DRAFT_CLAIM_CHANGED')
        self._authorization(db, actor, connection, write, snapshot.fence)
        self._lease(deadline)

    def _secret(self, actor, connection, snapshot):
        try:
            secret = self.service.secrets.get(actor.tenant_id, connection, snapshot.secret_ref)
            wire.secret_value(secret)
            return secret
        except Exception:
            raise WCEError('PREPARED_DRAFT_SECRET_UNAVAILABLE') from None

    @staticmethod
    def _taint(secret, *values):
        if any(wire.contains_secret(value, secret) for value in values):
            raise WCEError('PREPARED_DRAFT_SECRET_CONTAMINATION')

    def save(self, actor, connection_id, bundle_id, version, content_digest, request_key):
        self._sender_guard()
        _key(request_key)
        selector = _selector(bundle_id, version, content_digest)
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection_id, request_key, selector)
            if old is not None:
                return self._view(old)
            snapshot, deadline = self._snapshot(db, actor, connection_id, selector, True)
        intent = json.loads(snapshot.intent)
        secret = self._secret(actor, connection_id, snapshot)
        self._taint(secret, intent, json.loads(snapshot.uploads), json.loads(snapshot.article), request_key)
        request = _request('add', {'articles': [json.loads(snapshot.article)]}, secret)
        binding = intent['binding']
        admission = dict(zip(ROW_FIELDS, ('local-prepared-draft-' + uuid4().hex, 'test', PROVENANCE,
            binding['tenant'], binding['principal'], connection_id, binding['resource'], request_key,
            PURPOSE, canonical(selector), snapshot.intent, digest(intent), _target(intent), snapshot.fence,
            snapshot.token_revision, uuid4().hex, 'RESULT_UNKNOWN', self.service.clock(), None,
            RENDERER_VERSION, PROTOCOL_VERSION, intent['projection_digest'], snapshot.uploads, None)))
        self._validated(admission)
        self._taint(secret, admission)
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection_id, request_key, selector)
            if old is not None:
                result = self._view(old)
                self._taint(secret, result)
                return result
            self._sender_guard()
            self._recheck(db, actor, connection_id, selector, snapshot, deadline, True)
            if db.execute('SELECT 1 FROM prepared_draft_attempts WHERE target=?', (admission['target'],)).fetchone():
                raise WCEError('PREPARED_DRAFT_TARGET_REGISTERED')
            if db.execute("SELECT 1 FROM prepared_draft_attempts WHERE mode='test' AND tenant=? AND resource=? "
                          "AND purpose=? AND state='RESULT_UNKNOWN'", (binding['tenant'], binding['resource'], PURPOSE)).fetchone():
                raise WCEError('UNRESOLVED_PREPARED_DRAFT')
            db.execute('INSERT INTO prepared_draft_attempts VALUES(' + ','.join('?' for _ in ROW_FIELDS) + ')',
                       tuple(admission[k] for k in ROW_FIELDS))
            self._authorization(db, actor, connection_id, True, snapshot.fence)
            self._lease(deadline)
        # Only this current winner can dispatch. No lock spans sender/store I/O.
        try:
            self._sender_guard()
            response = self.sender.send(request, snapshot.context(), timeout=10)
            reference = _add_reply(response, secret)
            if reference is not None:
                with self.service.db.transaction(write=True) as db:
                    self._recheck(db, actor, connection_id, selector, snapshot, deadline, True)
                    self._taint(secret, reference)
                    changed = db.execute("UPDATE prepared_draft_attempts SET state='FIXTURE_SAVED',completed=?,reference=? WHERE "
                        + ' AND '.join(k + ' IS ?' for k in ROW_FIELDS),
                        (self.service.clock(), reference) + tuple(admission[k] for k in ROW_FIELDS))
                    if changed.rowcount != 1:
                        raise WCEError('PREPARED_DRAFT_CLAIM_CHANGED')
                    row = db.execute('SELECT * FROM prepared_draft_attempts WHERE id=?', (admission['id'],)).fetchone()
                    self._taint(secret, self._view(row))
                    self._recheck(db, actor, connection_id, selector, snapshot, deadline, True)
        except Exception:
            pass  # committed UNKNOWN; never inspect remote store or retry
        result = self.status(actor, connection_id, request_key)
        self._taint(secret, result)
        return result

    def readback(self, actor, connection_id, request_key):
        self._sender_guard()
        _key(request_key)
        with self.service.db.transaction(write=True) as db:
            saved = self._history(db, actor, connection_id, request_key)
            if saved is None:
                raise WCEError('PREPARED_DRAFT_NOT_FOUND')
            if saved['state'] == 'RESULT_UNKNOWN':
                return self._view(saved)  # local status only; no reference guess/get
            _, selector = self._validated(saved)
            snapshot, deadline = self._snapshot(db, actor, connection_id, selector, False, saved)
        secret = self._secret(actor, connection_id, snapshot)
        context = snapshot.context()
        view = self._view(saved)
        self._taint(secret, json.loads(snapshot.article), context.value(), view)
        request = _request('get', {'media_id': saved['reference']}, secret)
        self._taint(secret, {'path': '/cgi-bin/draft/get', 'headers': request.headers, 'body': request.body})
        matched = False
        try:
            self._sender_guard()
            response = self.sender.send(request, context, timeout=10)
            matched = _get_reply(response, secret, saved['reference']) == json.loads(snapshot.article)
        except Exception:
            pass
        with self.service.db.transaction(write=True) as db:
            self._recheck(db, actor, connection_id, selector, snapshot, deadline, False, saved)
            result = view | {'readback_state': 'READBACK_MATCHED' if matched else 'READBACK_UNVERIFIED'}
            self._taint(secret, result)
            self._authorization(db, actor, connection_id, fence=snapshot.fence)
            self._lease(deadline)
        return result
