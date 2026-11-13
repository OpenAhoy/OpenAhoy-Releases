"""Human-reviewed, host-only reconciliation of one unknown permanent cover.

No model route, arbitrary URL, upload retry, alias, credential acquisition or
negative-result promotion. Success means an existing object was read and its
approved exact bytes or PNG8 RGBA matched, not that the original upload response was received.
"""
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urlsplit

from .contracts import WCEError
from .http_transport import HTTPRequest, HTTPResponse
from .own_auth import READ_APIS
from .own_bootstrap_security import private_read
from .own_workflow import encoded
from .prepared_draft_fixture import decode_json
from .service import digest
from .local_preparation import sha, image_check
from .own_png import decode_png, recovery_binding, policy as png_policy, ORIGIN as PIXEL_ORIGIN, MAX_INPUT
from . import own_wire as wire
from . import upload_wire as upload

MAX_MATERIALS = 10000
MAX_READ_WORKERS = 8
PAGE_SIZE = 20
MAX_CANDIDATES = 4
ITEM_FIELDS = ('media_id', 'name', 'update_time', 'url')
SOURCES = {
    READ_APIS[0]: ('https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_batchgetmaterial.html',
                   'ec17df249fd1360fe79ea394ae8eeff906ab92889b28632b9ff64f6cba39fe88'),
    READ_APIS[1]: ('https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_getmaterial.html',
                   'a6bab4bdbd7faee0715d83d46b2477e059374fc9b42181abd375c32f6a2fa601'),
}


def diagnostic(runtime, facts):
    """Best-effort facts cannot replace the already determined failure."""
    try:
        from .own_run_outcome import safe_counts
        runtime.reconcile_diagnostics = safe_counts(facts)
    except BaseException:
        pass


def item_issue(item, synthetic):
    """Identify a rejected predicate without returning any material content."""
    from .own_run_outcome import field_type
    if type(item) is not dict:
        return 'ITEM_OBJECT', {'field_type': field_type(item)}
    if not set(ITEM_FIELDS).issubset(item):
        return 'ITEM_KEYS', {'extra_key_count': len(set(item) - set(ITEM_FIELDS)),
            'missing_key_mask': sum(1 << n for n, field in enumerate(ITEM_FIELDS) if field not in item)}
    if not wire.identifier(item['media_id'], synthetic):
        return 'ITEM_MEDIA_ID', {'field_type': field_type(item['media_id']),
            'media_id_length': len(item['media_id']) if type(item['media_id']) is str else None}
    if type(item['name']) is not str:
        return 'ITEM_NAME_TYPE', {'field_type': field_type(item['name'])}
    if len(item['name']) > 256:
        return 'ITEM_NAME_LENGTH', {'name_length': len(item['name'])}
    if type(item['update_time']) is not int or item['update_time'] < 0:
        return 'ITEM_UPDATE_TIME', {'field_type': field_type(item['update_time'])}
    if not wire.image_url(item['url'], synthetic):
        return 'ITEM_URL', {'field_type': field_type(item['url']),
            'url_length': len(item['url']) if type(item['url']) is str else None}
    if not synthetic:
        parts = urlsplit(item['url'])
        if parts.hostname != 'mmbiz.qpic.cn':
            return 'ITEM_URL_HOST', {'url_length': len(item['url'])}
        if parts.port not in (None, 80 if parts.scheme == 'http' else 443):
            return 'ITEM_URL_PORT', {'url_length': len(item['url'])}
    return None


def validate_proof(workflow, db, profile, row, intent, result):
    """A recovered success retains verifiable origin after process restart."""
    try:
        name = result['reconciliation_proof']
        expected = 'reconciliation-' + row['id'] + '-'
        if (result['completion_origin'] not in ('OFFICIAL_READ_MATCH', PIXEL_ORIGIN) or type(name) is not str
                or not name.startswith(expected) or '/' in name or '\\' in name or not name.endswith('.json')):
            raise ValueError()
        raw, _ = private_read(workflow.db.path.parent / name)
        if sha(raw) != result['reconciliation_proof_sha256']:
            raise ValueError()
        proof = decode_json(raw, 8192)
        if encoded(proof).encode() + b'\n' != raw:
            raise ValueError()
        if type(proof.get('schema')) is int and proof['schema'] == 3:
            from .own_connection_reconcile import validate_proof as validate_personal
            validate_personal(workflow, db, profile, row, intent, result, proof)
            return
        pixel = result['completion_origin'] == PIXEL_ORIGIN
        expected_provenance = ('SYNTHETIC_OWN_' if profile.source_kind == 'SYNTHETIC_SETUP' else 'OWN_OFFICIAL_') + ('PIXEL_READ_MATCH' if pixel else 'READ_MATCH')
        if (type(proof['schema']) is not int or proof['schema'] != (2 if pixel else 1) or proof['provenance'] != expected_provenance
                or proof['original_state'] != 'RESULT_UNKNOWN' or proof['original_attempt_id'] != row['id']
                or proof['request_key'] != row['request_key'] or proof['binding'] != profile.binding()
                or proof['selector'] != intent['selector'] or proof['original_intent_digest'] != row['intent_digest']
                or proof['original_approval_digest'] != row['approval_digest']
                or proof['asset_sha256'] != intent['asset']['sha256'] or proof['asset_size'] != intent['asset']['size']
                or proof['result'] != {k: result[k] for k in ('media_id', 'url')}
                or proof['sources'] != {k: {'url': v[0], 'sha256': v[1]} for k, v in SOURCES.items()}):
            raise ValueError()
        manifest, content_digest = workflow._bundle(db, profile,
            intent['selector']['bundle_id'], intent['selector']['version'])
        approval = workflow._approval(db, profile, manifest, content_digest, proof['current_approval_id'], False)
        if proof['current_fence'] != approval['binding_fence'] or name != expected + approval['id'] + '.json':
            raise ValueError()
        from .own_workflow import stored
        approval_body = stored(approval['body'], approval['body_digest'])
        if pixel:
            base_fields = {'schema', 'provenance', 'original_state', 'original_attempt_id', 'request_key',
                'binding', 'selector', 'original_intent_digest', 'original_approval_digest', 'current_approval_id',
                'current_fence', 'asset_sha256', 'asset_size', 'result', 'update_time', 'complete_list_digest',
                'material_count', 'sources'}
            if set(proof) != base_fields | {'recovery_policy', 'raster', 'remote_input_sha256',
                    'remote_input_size', 'unique_matches', 'final_remote_raw_equal'}:
                raise ValueError()
            binding = recovery_binding(row, intent)
            if (approval_body['schema'] != 2 or approval_body['recovery_policy'] != binding
                    or encoded(proof['recovery_policy']) != encoded(binding)
                    or type(proof['unique_matches']) is not int or proof['unique_matches'] != 1
                    or proof['final_remote_raw_equal'] is not True
                    or type(proof['remote_input_size']) is not int or not 0 < proof['remote_input_size'] <= MAX_INPUT):
                raise ValueError()
            import re
            if type(proof['remote_input_sha256']) is not str or re.fullmatch('[a-f0-9]{64}', proof['remote_input_sha256']) is None:
                raise ValueError()
            if (type(proof['complete_list_digest']) is not str
                    or re.fullmatch('[a-f0-9]{64}', proof['complete_list_digest']) is None
                    or type(proof['material_count']) is not int or not 1 <= proof['material_count'] <= MAX_MATERIALS
                    or type(proof['update_time']) is not int or proof['update_time'] < 0):
                raise ValueError()
            _, original = workflow._asset(db, profile.binding(), intent['asset']['asset_ref'], 'cover')
            if encoded(proof['raster']) != encoded(original_fingerprint(workflow, original)):
                raise ValueError()
        elif approval_body['schema'] != 1:
            # A pixel-mode approval cannot become a legacy byte-mode proof.
            raise ValueError()

    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def original_fingerprint(workflow, data, guard=lambda: None):
    """One exact immutable input per workflow; no proof or authority cache.

    File reads, hash checks, asset validation and authorization still run at
    every caller. Only the expensive pure PNG computation can be reused.
    """
    guard()
    cached = getattr(workflow, '_original_png_fingerprint', None)
    if type(data) is not bytes or not 0 < len(data) <= MAX_INPUT:
        raise WCEError('OWN_RECONCILE_PNG_UNSUPPORTED')
    if cached is not None and cached[0] == data:
        value = {'width': cached[1], 'height': cached[2], 'rgba_sha256': cached[3]}
    else:
        value = decode_png(data, guard).fingerprint()
        guard()
        workflow._original_png_fingerprint = (data, value['width'], value['height'], value['rgba_sha256'])
        return value
    guard()
    return value


def cover_snapshot(runtime, key, selector):
    runtime.paths_current()
    w, p = runtime.workflow, runtime.profile
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        row = w._history(db, p, key, 'cover', selector, 'cover', history_locators=history_locators)
        if row is None:
            raise WCEError('OWN_STEP_NOT_FOUND')
        intent, result = w._step(db, p, row, history_locators=history_locators)
        if row['state'] != 'RESULT_UNKNOWN' or result:
            raise WCEError('OWN_RECONCILE_NOT_UNKNOWN')
        _, data = w._asset(db, p.binding(), intent['asset']['asset_ref'], 'cover')
        return dict(row), intent, data


def reconcile_cover(runtime, approval):
    review = runtime.guided_context[0]
    selector, key = review.data['selector'], review.data['reconcile_cover']['request_key']
    row, intent, original = cover_snapshot(runtime, key, selector)
    w, p, lease = runtime.workflow, runtime.profile, runtime.lease
    synthetic = p.source_kind == 'SYNTHETIC_SETUP'
    read_stop = threading.Event()

    def guard():
        if read_stop.is_set():
            raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
        runtime._guided_current(approval)
        for action in READ_APIS:
            w._network(p, lease, action, read_attempt=True)
        actual, _, data = cover_snapshot(runtime, key, selector)
        if (actual != row or data != original):
            raise WCEError('OWN_RECONCILE_CHANGED')

    def read(action, payload):
        guard()
        endpoint = '/cgi-bin/material/' + ('batchget_material' if action == READ_APIS[0] else 'get_material')
        request = HTTPRequest('POST', endpoint + '?' + urlencode({'access_token': upload.secret_value(lease.token)}),
            {'Content-Type': 'application/json; charset=utf-8'}, encoded(payload).encode())
        if read_stop.is_set():
            raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
        response = w._send(p, lease, request, action, read_attempt=True)
        guard()
        if (type(response) is not HTTPResponse or not 200 <= response.status < 300
                or type(response.body) is not bytes or not 0 < len(response.body) <= 2097152
                or upload.contains_secret(response.body, lease.token)):
            raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
        return response.body

    pixel = review.data['schema'] == 3
    # The policy must be in the actual durable human approval, not just a
    # mutable review object or a proof's self-reported label.
    with w.db.transaction() as db:
        from .own_workflow import stored
        manifest, content_digest = w._bundle(db, p, selector['bundle_id'], selector['version'])
        approved = w._approval(db, p, manifest, content_digest, approval)
        approved_body = stored(approved['body'], approved['body_digest'])
        if pixel:
            if (review.data['reconcile_cover'].get('match_policy') != png_policy()['id']
                    or approved_body['schema'] != 2
                    or approved_body.get('recovery_policy') != recovery_binding(row, intent)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        elif approved_body['schema'] != 1:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    from .own_cover_match import match_cover
    observation = match_cover(read, guard, lambda facts: diagnostic(runtime, facts),
        runtime._failure, read_stop, row, intent, original, pixel, synthetic, lease.token,
        executor_factory=ThreadPoolExecutor)
    result = observation['result']
    proof = {'schema': 1, 'provenance': 'OWN_OFFICIAL_READ_MATCH' if not synthetic else 'SYNTHETIC_OWN_READ_MATCH',
        'original_state': 'RESULT_UNKNOWN', 'original_attempt_id': row['id'], 'request_key': key,
        'binding': p.binding(), 'selector': selector, 'original_intent_digest': row['intent_digest'],
        'original_approval_digest': row['approval_digest'], 'current_approval_id': approval,
        'current_fence': p.fence(), 'asset_sha256': intent['asset']['sha256'], 'asset_size': len(original),
        'result': result, 'update_time': observation['update_time'], 'complete_list_digest': observation['complete_list_digest'],
        'material_count': observation['material_count'], 'sources': {k: {'url': v[0], 'sha256': v[1]} for k, v in SOURCES.items()}}
    if pixel:
        proof.update(schema=2,
            provenance='SYNTHETIC_OWN_PIXEL_READ_MATCH' if synthetic else 'OWN_OFFICIAL_PIXEL_READ_MATCH',
            recovery_policy=recovery_binding(row, intent), raster=observation['raster'],
            remote_input_sha256=observation['remote_input_sha256'], remote_input_size=observation['remote_input_size'],
            unique_matches=1, final_remote_raw_equal=True)
    if upload.contains_secret(proof, lease.token):
        raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
    guard()
    # The immutable, fsynced proof precedes CAS. A crash before commit retains
    # UNKNOWN; an unknown commit is resolved by the original key status only.
    path = runtime.config.root / ('reconciliation-' + row['id'] + '-' + approval + '.json')
    raw = (encoded(proof) + '\n').encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        # Existence alone does not prove a prior fsync completed. A fresh human
        # review gets its own proof filename; never reuse a partial durable claim.
        raise WCEError('OWN_RECONCILE_PROOF_EXISTS') from None
    else:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    guard()
    completed_result = result | {'completion_origin': PIXEL_ORIGIN if pixel else 'OFFICIAL_READ_MATCH',
        'reconciliation_proof': path.name, 'reconciliation_proof_sha256': sha(raw)}
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        current = w._history(db, p, key, 'cover', selector, 'cover', history_locators=history_locators)
        w._step(db, p, current, history_locators=history_locators)
        if dict(current) != row:
            raise WCEError('OWN_RECONCILE_CHANGED')
        manifest, content_digest = w._bundle(db, p, selector['bundle_id'], selector['version'])
        w._approval(db, p, manifest, content_digest, approval)
        for action in READ_APIS:
            w._network(p, lease, action, read_attempt=True)
        changed = db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
            "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
            (encoded(completed_result), digest(completed_result), runtime.clock(), row['id'], row['owner'],
             row['intent_digest'], row['approval_digest'])).rowcount
        if changed != 1:
            raise WCEError('OWN_RECONCILE_CHANGED')
        if db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? AND kind='step' AND owner_id=?",
                (p.actor.tenant_id, p.resource_id, row['id'])).rowcount != 1:
            raise WCEError('OWN_RECONCILE_CHANGED')
        w._step(db, p, db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone(), history_locators=history_locators)
        for action in READ_APIS:
            w._network(p, lease, action, read_attempt=True)
    runtime._guided_current(approval)
    for action in READ_APIS:
        w._network(p, lease, action, read_attempt=True)
    return {'state': 'EXISTING_COVER_READ_MATCHED', 'original_write_response': 'RESULT_UNKNOWN',
            'request_key': key, 'attempt_id': row['id'], 'proof_sha256': sha(raw), 'result': result}


from .draft_group_history_context import history_transaction as _history_transaction
