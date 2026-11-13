"""Read-only reconciliation of one original unknown draft; never replay add.

The proof establishes an existing exact object, not which write created it.
Two complete equal scans are conservative checks, not an atomic snapshot.
"""
import os
import stat
from urllib.parse import urlencode

from .contracts import WCEError
from .bounded_file import identity
from .http_transport import HTTPRequest, MAX_BODY
from .own_auth import DRAFT_READ_APIS
from .own_bootstrap_security import private_read, path_check
from .own_body_recovery import code_scope
from .own_draft_wire import response_value, reference_valid, project_news, exact_single
from .own_workflow import encoded, stored
from .prepared_contracts import DIGEST, strict_validate
from .prepared_draft_fixture import decode_json
from .service import digest
from .local_preparation import sha
from . import upload_wire as upload

POLICY = 'DRAFT_EXACT_PROJECTION_READ_V1'
ORIGIN = 'OFFICIAL_DRAFT_READ_MATCH'
MAX_DRAFTS, PAGE_SIZE, MAX_CANDIDATES = 1000, 20, 4
SOURCES = {
    DRAFT_READ_APIS[0]: {'url': 'https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_batchget.html',
        'sha256': 'e39f0212897f0d5ef3f8631feba83abbc43d20515c9a7507c67b4b979899b1a0'},
    DRAFT_READ_APIS[1]: {'url': 'https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_getdraft.html',
        'sha256': '3789d47567bc5a5363d54b7df29f0b330a9535e620a5de47afeab452f7640323'},
}
IDENTITY = ('id', 'tenant', 'principal', 'connection', 'resource', 'request_key', 'operation', 'slot',
    'manifest_digest', 'target', 'approval_id', 'approval_digest', 'intent_digest', 'owner', 'created')


def budget():
    return {'maximum_drafts': MAX_DRAFTS, 'page_size': PAGE_SIZE, 'maximum_lists': 100,
        'maximum_candidates': MAX_CANDIDATES, 'maximum_candidate_gets': 4,
        'maximum_final_gets': 1, 'maximum_independent_gets': 1,
        'maximum_total_reads': 106, 'maximum_remote_writes': 0,
        'list_no_content': 0, 'maximum_response_bytes': MAX_BODY,
        'non_target_content': 'MEMORY_ONLY_DISCARD_AFTER_DIGEST'}


def binding(row, intent, candidate_scope):
    return {'policy': POLICY, 'original': {k: row[k] for k in IDENTITY},
        'candidate_scope': candidate_scope, 'projection_digest': digest(intent['projection']),
        'uploads_digest': digest(intent['uploads']), 'budget': budget(), 'sources': SOURCES}


def validate_policy(db, policy):
    """Pure historical DAG leaf: no _step, authority, network or recursive proof."""
    try:
        strict_validate(policy['candidate_scope'], DIGEST)
        row = db.execute('SELECT * FROM own_steps WHERE id=?', (policy['original']['id'],)).fetchone()
        if row is None or row['operation'] != 'add' or row['slot'] != 'draft':
            raise ValueError()
        intent = stored(row['intent'], row['intent_digest'])
        if encoded(policy) != encoded(binding(row, intent, policy['candidate_scope'])):
            raise ValueError()
        return row, intent
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def snapshot(workflow, db, profile, selector, request_key, *, history_locators=None):
    row = workflow._history(db, profile, request_key, 'add', selector, 'draft', history_locators=history_locators)
    intent, result = workflow._step(db, profile, row, history_locators=history_locators)
    if (row['state'] == 'RESULT_UNKNOWN' and result) or (row['state'] == 'SUCCEEDED'
            and result.get('completion_origin') != ORIGIN):
        raise WCEError('OWN_DRAFT_RECONCILE_STATE')
    return binding(row, intent, code_scope())


def write_once(root, name, value, *, expected_root):
    """Private evidence/attempt admission, created relative to pinned root FD."""
    if type(name) is not str or not name.startswith('draft-') or '/' in name or '\\' in name or not name.endswith('.json'):
        raise WCEError('OWN_DRAFT_RECONCILE_STORAGE')
    if path_check(root, directory=True) != expected_root:
        raise WCEError('OWN_DRAFT_RECONCILE_STORAGE')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned = os.fstat(fd)
        if (identity(pinned) != expected_root or pinned.st_uid != os.getuid()
                or stat.S_IMODE(pinned.st_mode) != 0o700):
            raise WCEError('OWN_DRAFT_RECONCILE_STORAGE')
        def current():
            path_check(root, directory=True)
            now = os.stat(root, follow_symlinks=False)
            if (now.st_dev, now.st_ino, now.st_uid, stat.S_IMODE(now.st_mode)) != (
                    pinned.st_dev, pinned.st_ino, pinned.st_uid, 0o700):
                raise WCEError('OWN_DRAFT_RECONCILE_STORAGE')
        current()
        raw = (encoded(value) + '\n').encode()
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(out, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.fsync(fd)
        current()
        return sha(raw)
    except FileExistsError:
        raise WCEError('OWN_DRAFT_RECONCILE_ATTEMPT_SPENT') from None
    finally:
        os.close(fd)


def validate_proof(workflow, db, profile, row, intent, result):
    if result.get("completion_origin") == ORDINARY_ORIGIN:
        return validate_ordinary_proof(workflow, db, profile, row, intent, result)
    try:
        name = result['reconciliation_proof']
        if (type(name) is not str or not name.startswith('draft-reconciliation-' + row['id'] + '-')
                or '/' in name or '\\' in name or not name.endswith('.json')):
            raise ValueError()
        raw, _ = private_read(workflow.db.path.parent / name)
        if sha(raw) != result['reconciliation_proof_sha256']:
            raise ValueError()
        proof = decode_json(raw, 16384)
        fields = {'schema', 'origin', 'policy', 'approval_id', 'approval_digest', 'reference',
            'list_digest', 'total', 'candidate_count', 'unique_matches', 'projection_digest', 'completed'}
        if (type(proof) is not dict or set(proof) != fields or encoded(proof).encode()+b'\n' != raw
                or type(proof['schema']) is not int or proof['schema'] != 1
                or proof['origin'] != ORIGIN or result['completion_origin'] != ORIGIN
                or proof['reference'] != result['reference']
                or name != 'draft-reconciliation-' + row['id'] + '-' + proof['approval_id'] + '.json'
                or proof['projection_digest'] != digest(intent['projection'])):
            raise ValueError()
        m, d = workflow._bundle(db, profile, intent['selector']['bundle_id'], intent['selector']['version'])
        approval = workflow._approval(db, profile, m, d, proof['approval_id'], False)
        body = stored(approval['body'], approval['body_digest'])
        if (body['schema'] != 6 or body['draft_recovery'] != proof['policy']
                or approval['body_digest'] != proof['approval_digest']
                or body['draft_recovery']['original'] != {k: row[k] for k in IDENTITY}
                or type(proof['completed']) not in (int, float)
                or not row['created'] <= proof['completed'] < body['expires']
                or row['completed'] != proof['completed']):
            raise ValueError()
        strict_validate(proof['list_digest'], DIGEST)
        if (type(proof['total']) is not int or not 1 <= proof['total'] <= MAX_DRAFTS
                or type(proof['candidate_count']) is not int or proof['candidate_count'] != 1
                or type(proof['unique_matches']) is not int or proof['unique_matches'] != 1):
            raise ValueError()
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def active_approval(workflow, db, profile, row, intent, approval_id=None):
    m, d = workflow._bundle(db, profile, intent['selector']['bundle_id'], intent['selector']['version'])
    approval = workflow._approval(db, profile, m, d, approval_id, allow_draft_read=True)
    body = stored(approval['body'], approval['body_digest'])
    if body['schema'] != 6 or body['draft_recovery'] != binding(row, intent, code_scope()):
        raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    return approval


def reconcile(runtime, approval_id):
    runtime.draft_read_context = {'operation': 'LOCAL', 'phase': 'START', 'offset': None,
        'http_status': None, 'wechat_error_code': None}
    try:
        return _reconcile(runtime, approval_id)
    except Exception as exc:
        from .own_run_outcome import safe_code, safe_counts
        reason = safe_code(exc.code if isinstance(exc, WCEError) else 'TRANSPORT_UNDETERMINED')
        runtime.reconcile_diagnostics = safe_counts(runtime.draft_read_context |
            {'reason': 'DRAFT_READ_FAILURE', 'predicate': reason})
        raise


def _reconcile(runtime, approval_id):
    w, p, lease = runtime.workflow, runtime.profile, runtime.lease
    policy = runtime.guided_context[0].data['draft_recovery']
    key = policy['request_key']
    with _history_transaction(w.db) as (db, history_locators):
        row = w._history(db, p, key, history_locators=history_locators)
        intent, result = w._step(db, p, row, history_locators=history_locators)
        approval = active_approval(w, db, p, row, intent, approval_id)
        original = dict(row)
    if row['state'] == 'SUCCEEDED':
        return w._view(p, row)
    synthetic = p.source_kind == 'SYNTHETIC_SETUP'

    def guard():
        runtime._guided_current(approval_id)
        for action in DRAFT_READ_APIS:
            w._network(p, lease, action, read_attempt=True)
        with _history_transaction(w.db) as (db, history_locators):
            now = w._history(db, p, key, history_locators=history_locators)
            if dict(now) != original:
                raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
            lock = db.execute('SELECT kind,owner_id FROM own_resource_locks WHERE tenant=? AND resource=?',
                (p.actor.tenant_id, p.resource_id)).fetchone()
            if lock is None or tuple(lock) != ('step', row['id']):
                raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')

    guard()
    write_once(w.db.path.parent, 'draft-scan-' + approval_id + '.json',
        {'approval_digest': approval['body_digest'], 'step_id': row['id'], 'budget': budget()},
        expected_root=w.state_root_identity)
    calls = {DRAFT_READ_APIS[0]: 0, DRAFT_READ_APIS[1]: 0}

    def read(action, payload, phase):
        runtime.draft_read_context = runtime.draft_read_context | {'operation': 'LIST' if action == DRAFT_READ_APIS[0] else 'GET',
            'phase': phase, 'offset': payload.get('offset'), 'http_status': None, 'wechat_error_code': None}
        guard()
        calls[action] += 1
        if calls[action] > (100 if action == DRAFT_READ_APIS[0] else 5):
            raise WCEError('OWN_DRAFT_RECONCILE_BUDGET')
        endpoint = '/cgi-bin/draft/' + ('batchget' if action == DRAFT_READ_APIS[0] else 'get')
        request = HTTPRequest('POST', endpoint + '?' + urlencode({'access_token': upload.secret_value(lease.token)}),
            {'Content-Type': 'application/json; charset=utf-8'}, encoded(payload).encode())
        if upload.contains_secret(payload, lease.token):
            raise WCEError('RESPONSE_SECRET_REFLECTION')
        response = w._send(p, lease, request, action, read_attempt=True)
        from .http_transport import HTTPResponse
        if type(response) is HTTPResponse:
            runtime.draft_read_context['http_status'] = response.status
        guard()
        value = response_value(response, lease.token, list_response=action == DRAFT_READ_APIS[0])
        if value.get('errcode', 0):
            runtime.draft_read_context['wechat_error_code'] = value['errcode']
            raise WCEError('OWN_DRAFT_RECONCILE_API_REJECTED')
        return value

    def scan(phase):
        offset, total, records, candidates = 0, None, {}, []
        counts = {'total': 0, 'candidate_count': 0, 'title_matches': 0, 'content_matches': 0, 'cover_matches': 0}
        while total is None or offset < total:
            value = read(DRAFT_READ_APIS[0], {'offset': offset, 'count': PAGE_SIZE, 'no_content': 0}, phase)
            n, count, items = (value.get(k) for k in ('total_count', 'item_count', 'item'))
            if (type(n) is not int or not 0 <= n <= MAX_DRAFTS or type(count) is not int
                    or type(items) is not list or count != len(items)
                    or count != min(PAGE_SIZE, max(0, n-offset)) or (total is not None and total != n)):
                raise WCEError('OWN_DRAFT_RECONCILE_INCOMPLETE_LIST')
            total = n
            counts['total'] = total
            runtime.draft_read_context.update(counts)
            for item in items:
                if type(item) is not dict or not reference_valid(item.get('media_id'), synthetic):
                    raise WCEError('OWN_DRAFT_RECONCILE_INVALID_LIST')
                ref, updated = item['media_id'], item.get('update_time')
                if ref in records or type(updated) is not int or updated < 0:
                    raise WCEError('OWN_DRAFT_RECONCILE_INVALID_LIST')
                news = project_news(item.get('content'), synthetic, exclude_non_target=True)
                records[ref] = {'update_time': updated, 'news_digest': digest(news)}
                if len(news) == 1 and news[0]['article_type'] == 'news':
                    for field, count_key in (('title', 'title_matches'), ('content', 'content_matches'), ('thumb_media_id', 'cover_matches')):
                        counts[count_key] += int(news[0][field] == intent['projection'][field])
                if exact_single(news, intent['projection']):
                    candidates.append(ref)
                counts['candidate_count'] = len(candidates)
                runtime.draft_read_context.update(counts)
            offset += count
            if total == 0:
                break
        if len(records) != total:
            raise WCEError('OWN_DRAFT_RECONCILE_INCOMPLETE_LIST')
        return records, candidates

    first, candidates = scan('FIRST_LIST')
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise WCEError('OWN_DRAFT_RECONCILE_NO_UNIQUE_MATCH')
    matches = []
    for reference in candidates:
        news = project_news(read(DRAFT_READ_APIS[1], {'media_id': reference}, 'CANDIDATE_GET'), synthetic)
        if not exact_single(news, intent['projection']):
            raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
        matches.append(reference)
    if len(matches) != 1:
        raise WCEError('OWN_DRAFT_RECONCILE_NO_UNIQUE_MATCH')
    second, _ = scan('SECOND_LIST')
    if first != second:
        raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
    reference = matches[0]
    if not exact_single(project_news(read(DRAFT_READ_APIS[1], {'media_id': reference}, 'FINAL_GET'), synthetic), intent['projection']):
        raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
    runtime.draft_read_context = {'operation': 'LOCAL', 'phase': 'PROOF', 'offset': None,
        'http_status': None, 'wechat_error_code': None}
    guard()
    completed = w.clock()
    proof = {'schema': 1, 'origin': ORIGIN, 'policy': binding(row, intent, code_scope()),
        'approval_id': approval_id, 'approval_digest': approval['body_digest'], 'reference': reference,
        'list_digest': digest(first), 'total': len(first), 'candidate_count': len(candidates),
        'unique_matches': 1, 'projection_digest': digest(intent['projection']), 'completed': completed}
    name = 'draft-reconciliation-' + row['id'] + '-' + approval_id + '.json'
    proof_hash = write_once(w.db.path.parent, name, proof, expected_root=w.state_root_identity)
    guard()
    result = {'reference': reference, 'completion_origin': ORIGIN,
        'reconciliation_proof': name, 'reconciliation_proof_sha256': proof_hash}
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        current = w._history(db, p, key, history_locators=history_locators)
        if dict(current) != original:
            raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
        active_approval(w, db, p, current, intent, approval_id)
        for action in DRAFT_READ_APIS:
            w._network(p, lease, action, read_attempt=True)
        if db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
                "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
                (encoded(result), digest(result), completed, row['id'], row['owner'], row['intent_digest'],
                 row['approval_digest'])).rowcount != 1:
            raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
        if db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? AND kind='step' AND owner_id=?",
                (p.actor.tenant_id, p.resource_id, row['id'])).rowcount != 1:
            raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
        w._step(db, p, db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone(), history_locators=history_locators)
        for action in DRAFT_READ_APIS:
            w._network(p, lease, action, read_attempt=True)
    runtime._guided_current(approval_id)
    return w._view(p, row)


def independent_readback(w, p, lease, row, intent, result):
    """One fresh GET per explicit approval; an unknown read never replays itself."""
    with w.db.transaction() as db:
        approval = active_approval(w, db, p, row, intent)

    def guard(db, *, history_locators=None):
        w._resource(db, p, history_locators=history_locators)
        current = w._history(db, p, row['request_key'], history_locators=history_locators)
        if (current['state'] != 'SUCCEEDED' or current['id'] != row['id']
                or current['intent_digest'] != row['intent_digest'] or current['result_digest'] != row['result_digest']):
            raise WCEError('OWN_DRAFT_RECONCILE_CHANGED')
        active_approval(w, db, p, current, intent, approval['id'])
        w._network(p, lease, DRAFT_READ_APIS[1], read_attempt=True)

    with _history_transaction(w.db) as (db,history_locators):
        guard(db,history_locators=history_locators)
    write_once(w.db.path.parent, 'draft-readback-' + approval['id'] + '.json',
        {'approval_digest': approval['body_digest'], 'step_id': row['id'], 'result_digest': row['result_digest']},
        expected_root=w.state_root_identity)
    with _history_transaction(w.db) as (db,history_locators):
        guard(db,history_locators=history_locators)
    from . import own_wire as wire
    request = wire.encode_draft('get', {'media_id': result['reference']}, lease.token)
    response = w._send(p, lease, request, DRAFT_READ_APIS[1], read_attempt=True)
    reply = wire.parse('get', response, lease.token, p.source_kind == 'SYNTHETIC_SETUP', result['reference'])
    state = 'MATCHED' if reply.result == intent['projection'] else 'UNVERIFIED'
    with _history_transaction(w.db,write=True) as (db,history_locators):
        guard(db,history_locators=history_locators)
        db.execute('UPDATE own_steps SET readback=? WHERE id=?', (state, row['id']))
        guard(db,history_locators=history_locators)
    view = w._view(p, row)
    with _history_transaction(w.db) as (db,history_locators):
        guard(db,history_locators=history_locators)
    from .own_diagnostics import projection
    return view | {'readback_state': state, 'readback_diagnostic': projection(reply, response)}


from .draft_group_history_context import history_transaction as _history_transaction

# Ordinary persistent delegation is independent of the old guided schema6 grant.
# This is request-local read accounting, not an issuer/Case/permission factory.
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import threading
import time
import math
from uuid import uuid4

ORDINARY_ORIGIN = 'OFFICIAL_DRAFT_READ_MATCH_ORDINARY_V2'
ORDINARY_POLICY = 'ORDINARY_DRAFT_EXACT_PROJECTION_READ_V2'


def _ordinary_need(value, code='OWN_DRAFT_ORDINARY_READ_HOLD'):
    if value is not True:
        raise WCEError(code)


def _ordinary_policy(w, p):
    from .own_connection_workflow import PersistentWorkflow
    from .own_connection_policy import ConnectionPolicy
    policy = getattr(w, 'policy', getattr(w.db, 'history_policy', None))
    _ordinary_need(type(policy) is ConnectionPolicy and policy.data['connection_id'] == p.connection_id)
    return policy


def _ordinary_delegation(w, db, p, history, value=None):
    """Bind actual normal COMMITTED policy evidence; never construct a policy."""
    from .own_history_locators import borrow_entered_history
    from .own_connection_registry import transaction_path, owner_value, validate_registry
    from .own_connection_enrollment import published_entry
    from .own_identity_recovery import PROOF_FIELDS
    from .own_connection_policy import CAPABILITIES
    policy = _ordinary_policy(w, p)
    if history is None:
        history = borrow_entered_history(policy, db)
    _ordinary_need(history is not None)
    if value is None:
        policy.check(readonly=True, proof_reader=history.reader)
        old = deepcopy(policy.value)
    else:
        _ordinary_need(type(value) is dict and set(value) == {'policy_path','policy','transaction_sha256'})
        _ordinary_need(value['policy_path'] == str(policy.path))
        old = value['policy']
    _ordinary_need(type(old) is dict and set(old) == set(policy.value)
        and old.get('schema') == 2 and type(old['schema']) is int
        and old['identity'] == policy.data
        and old['registry_path'] == policy.value['registry_path']
        and old['owner_digest'] == policy.value['owner_digest']
        and old['enabled'] is True and old['capabilities'] == CAPABILITIES
        and old['duration'] == 'UNTIL_DISCONNECTED')
    registry = Path(policy.value['registry_path'])
    path = transaction_path(registry, old['transaction'])
    meta, raw = history.reader.read(path, keep=True)
    txn = decode_json(raw, 262144, max_nodes=16384)
    _ordinary_need(type(txn) is dict and type(txn.get('schema')) is int
        and txn['schema'] in (1,2) and set(txn) == PROOF_FIELDS | ({'relocation'} if txn['schema']==2 else set())
        and txn['state'] == 'COMMITTED' and txn['id'] == old['transaction']
        and txn['registry'] == str(registry) and txn['owner'] == owner_value(registry, policy.data['actor']))
    validate_registry(registry, txn['before']);validate_registry(registry, txn['after'])
    cid = p.connection_id
    _ordinary_need(txn['policies'][str(policy.path)]['after'] == old
        and txn['after']['connections'][cid] == str(policy.path)
        and txn['after']['entries'][cid] == published_entry(old, txn['after']['entries'][cid]['label']))
    observed = {'policy_path': str(policy.path), 'policy': old, 'transaction_sha256': meta['sha256']}
    if value is not None:
        _ordinary_need(observed == value)
    return observed


def _ordinary_expected(intent):
    value = intent['projection']
    rows = value.get('articles') if type(value) is dict and 'articles' in value else [value]
    _ordinary_need(type(rows) is list and 1 <= len(rows) <= 8
        and all(type(row) is dict for row in rows))
    return rows


def _ordinary_observe(response, secret, synthetic, reference, intent):
    """Keep valid base HTML even when requested crop/comments are unavailable."""
    from . import own_wire as wire
    from .own_draft_wire import comment_comparison
    from .editor_contracts import crop_info
    reply = wire.parse_group_get(response, secret, synthetic, reference, requested_cover_indices=())
    _ordinary_need(type(reply.result) is dict and 'articles' in reply.result,
                   'DRAFT_INVALID_JSON')
    raw = response_value(response, secret)
    expected = _ordinary_expected(intent)
    actual = deepcopy(reply.result)
    comparisons=[];strict=len(actual['articles'])==len(expected)
    for index, desired in enumerate(expected):
        fields={};seen=actual['articles'][index] if index<len(actual['articles']) else {}
        rawrow=raw['news_item'][index] if index<len(raw['news_item']) else {}
        for key in ('author','digest','content_source_url'):
            if key not in rawrow:seen.pop(key,None)
        for key in ('article_type','title','content','thumb_media_id','author','digest','content_source_url'):
            if key not in desired and key!='article_type':continue
            want=desired.get(key,'news');got=seen.get(key)
            present=key=='article_type' or key in rawrow
            fields[key]={'state':('VERIFIED' if got==want else 'MISMATCH') if present else 'UNVERIFIED'}
            strict = strict and present and got==want
        if 'cover_info' in desired:
            try:
                crop=crop_info(rawrow.get('cover_info'))
                seen['cover_info']=crop
                equal=crop==desired['cover_info']
                fields['cover_info']={'state':'VERIFIED' if equal else 'MISMATCH','present':'cover_info'in rawrow,'type':type(rawrow.get('cover_info')).__name__}
                strict=strict and equal
            except WCEError:
                fields['cover_info']={'state':'UNVERIFIED','present':'cover_info'in rawrow,'type':type(rawrow.get('cover_info')).__name__}
                strict=False
        if any(key in desired for key in ('need_open_comment','only_fans_can_comment')):
            wanted=[{key:desired[key]for key in ('need_open_comment','only_fans_can_comment')}]
            observations=getattr(reply,'comment_observation',())
            comparison=comment_comparison(wanted,observations[index:index+1])
            fields['comments']=comparison['articles'][0]
            strict=strict and comparison['count_match'] and fields['comments']['state']=='VERIFIED'
            for key,info in fields['comments']['fields'].items():
                if info['type']=='integer' and info['actual_value'] is not None:
                    seen[key]=info['actual_value']
        comparisons.append({'index':index,'fields':fields})
    original=intent['projection'].get('articles')if 'articles'in intent['projection']else[intent['projection']]
    matched_rows=[{key:(actual['articles'][i].get(key) if i<len(actual['articles'])else None) for key in wanted}for i,wanted in enumerate(original)]
    matched={'articles':matched_rows} if 'articles' in intent['projection']else matched_rows[0]
    # The expected projection is reconstructed from the original successful
    # upload mappings by validate_step_in on every current-context guard. These
    # are per-article, per-position bindings, never a batch URL allowlist.
    from .own_platform_representation import compare_platform_representation, _HTML
    representation_expected={'articles':deepcopy(expected)}
    bindings=[]
    try:
        for article in representation_expected['articles']:
            article.setdefault('article_type','news')
            parsed=_HTML(article['content'])
            bindings.append([dict(attributes)['src'] for _,attributes in parsed.images])
        representation=compare_platform_representation(representation_expected,actual,bindings)
    except (ValueError,TypeError,KeyError,IndexError,RecursionError,UnicodeError):
        representation=compare_platform_representation({},actual,[])
    representation.update(expected_projection_sha256=digest(intent['projection']),
        actual_projection_sha256=digest(actual),actual_response_sha256=sha(response.body))
    return {'projection':actual,'matched_projection':matched,'strict':bool(strict),
        'comparison':{'count_match':len(actual['articles'])==len(expected),'articles':comparisons},
        'platform_representation':representation}


def _ordinary_coarse(content, expected, synthetic):
    rows=content.get('news_item') if type(content)is dict else None
    if type(rows)is not list or len(rows)!=len(expected):return False
    for seen,wanted in zip(rows,expected):
        if type(seen)is not dict or seen.get('article_type','news')!='news':return False
        for key in ('title','thumb_media_id','author','content_source_url'):
            if key in wanted and wanted[key] and seen.get(key)!=wanted[key]:return False
        if not reference_valid(seen.get('thumb_media_id'),synthetic):return False
    return True


class _OrdinaryDraftRead:
    def __init__(self,w,p,lease,a,row,intent):
        from .own_connection_workflow import PersistentWorkflow
        _ordinary_need(type(w)is PersistentWorkflow and type(a)is dict and set(a)<= {'connection_id','request_key','include_projection'}
            and a.get('connection_id')==p.connection_id and a.get('request_key')==row['request_key']
            and type(a.get('include_projection',False))is bool and lease is not None
            and lease is w.active_lease and set(DRAFT_READ_APIS)<=p.granted_actions)
        self.w,self.p,self.lease=w,p,lease
        self.original=dict(row);self.expected=dict(row);self.intent=deepcopy(intent)
        self.pid,self.thread=os.getpid(),threading.get_ident();self.active=True
        self.calls={'list':0,'get':0};self.observations=[];self.candidate_count=0
        self.started=w.clock();self.deadline=getattr(w,'execution_deadline',None)
        _ordinary_need(type(self.deadline)in(int,float) and self.deadline>time.monotonic())
        self.not_after=min(p.expires,p.session_expires,p.grant_expires,p.credential_expires,
                           lease.expires_at,self.started+min(300,self.deadline-time.monotonic()))
        self.delegation=None;self.proof=None;self.last_read=None
        self.inventory_scans={};self.inventory_drift=None

    def current(self):
        _ordinary_need(self.active and self.pid==os.getpid() and self.thread==threading.get_ident()
            and getattr(self.w,'ordinary_draft_read_context',None)is self)
        policy=_ordinary_policy(self.w,self.p)
        _ordinary_need('draft_read'in policy.value['capabilities'] and self.w.active_lease is self.lease)
        self.w._current(self.p,self.lease)
        _ordinary_need(self.w.clock()<self.not_after and time.monotonic()<self.deadline,
                       'OWN_DRAFT_ORDINARY_READ_EXPIRED')

    def guard_in(self,db,history):
        self.current();w,p=self.w,self.p
        w._resource(db,p,history_locators=history)
        row=w._history(db,p,self.original['request_key'],history_locators=history)
        _ordinary_need(dict(row)==self.expected,'OWN_DRAFT_RECONCILE_CHANGED')
        intent,_=w._step(db,p,row,history_locators=history)
        _ordinary_need(intent==self.intent)
        m,d=w._bundle(db,p,intent['selector']['bundle_id'],intent['selector']['version'])
        _ordinary_need(d==row['manifest_digest'])
        approval=w._approval(db,p,m,d,row['approval_id'],False)
        _ordinary_need(stored(approval['body'],approval['body_digest']).get('schema')==7,
                       'OWN_DRAFT_ORDINARY_ORIGIN_REQUIRED')
        if row['state']=='RESULT_UNKNOWN':w._owned_lock(db,p,m,row['id'])
        else:_ordinary_need(row['state']=='SUCCEEDED' and stored(row['result'],row['result_digest']).get('completion_origin')==ORDINARY_ORIGIN)
        delegation=_ordinary_delegation(w,db,p,history)
        if self.delegation is None:self.delegation=delegation
        else:_ordinary_need(self.delegation==delegation,'OWN_DELEGATION_UNAVAILABLE')
        return row,m

    def guard(self):
        with _history_transaction(self.w.db)as(db,h):self.guard_in(db,h)

    def read(self,kind,payload,phase):
        self.guard();self.calls[kind]+=1
        _ordinary_need(self.calls['list']<=100 and self.calls['get']<=6 and sum(self.calls.values())<=106,
                       'OWN_DRAFT_RECONCILE_BUDGET')
        action=DRAFT_READ_APIS[0 if kind=='list'else 1]
        endpoint='/cgi-bin/draft/'+('batchget'if kind=='list'else'get')
        request=HTTPRequest('POST',endpoint+'?'+urlencode({'access_token':upload.secret_value(self.lease.token)}),
                            {'Content-Type':'application/json; charset=utf-8'},encoded(payload).encode())
        _ordinary_need(not upload.contains_secret(payload,self.lease.token),'RESPONSE_SECRET_REFLECTION')
        from .http_transport import HTTPResponse, TransportFailure
        self.last_read={'kind':kind,'phase':phase,'offset':payload.get('offset'),
                        'http_status':None,'wechat_code':None,'reason':'RESPONSE_UNDETERMINED'}
        response=self.w._send(self.p,self.lease,request,action,read_attempt=True)
        if type(response)is HTTPResponse:
            status=response.status
            self.last_read['http_status']=status if type(status)is int and 100<=status<=599 else None
        elif type(response)is TransportFailure:
            from .http_transport import valid_transport_failure
            if valid_transport_failure(response.stage,response.kind,response.http_status):
                self.last_read.update(reason='TRANSPORT_UNDETERMINED',http_status=response.http_status,
                    transport_failure={'stage':response.stage,'kind':response.kind})
        self.guard()
        value=response_value(response,self.lease.token,list_response=kind=='list')
        code=value.get('errcode',0)
        if type(code)is int and -(2**31)<=code<2**31 and code!=0:
            self.last_read.update(wechat_code=code,reason='PLATFORM_ERROR')
        if code:raise WCEError('OWN_DRAFT_RECONCILE_API_REJECTED')
        self.last_read['reason']='PARSED_SUCCESS'
        return response,value


@contextmanager
def _ordinary_context(w,p,lease,a,row,intent):
    _ordinary_need(getattr(w,'ordinary_draft_read_context',None)is None)
    context=_OrdinaryDraftRead(w,p,lease,a,row,intent)
    w.ordinary_draft_read_context=context
    try:
        context.guard();yield context
    finally:
        context.active=False;context.inventory_scans.clear()
        w.ordinary_draft_read_context=None


def checked_ordinary_context(w,p,lease):
    context=getattr(w,'ordinary_draft_read_context',None)
    if context is None:return None
    _ordinary_need(type(context)is _OrdinaryDraftRead and context.w is w and context.p is p and context.lease is lease)
    context.current();return context


def _ordinary_result(ctx,a,state,reason,observation=None,reference=None):
    ctx.guard()
    output=ctx.w._view(ctx.p,ctx.expected)|{'readback_state':state,'reconciliation_origin':ORDINARY_ORIGIN,
        'reconciliation_reason':reason,'read_counts':dict(ctx.calls),'candidate_count':ctx.candidate_count,
        'candidate_comparisons':[{'reference':ref,'comparison':obs['comparison']}for ref,obs in ctx.observations]}
    if ctx.last_read is not None:output['readback_diagnostic']=deepcopy(ctx.last_read)
    if getattr(ctx,'inventory_drift',None) is not None:
        output['inventory_drift_diagnostic']=deepcopy(ctx.inventory_drift)
    if reference is not None:output['observed_reference']=reference
    if observation is not None:
        output['readback_comparison']=observation['comparison']
        if 'platform_representation' in observation:
            output['platform_representation']=deepcopy(observation['platform_representation'])
        if a.get('include_projection',False):output.update(actual_projection_policy='ACTUAL_DOCUMENT_PROJECTION_V2',actual_projection=observation['projection'])
    elif a.get('include_projection',False):output['actual_projection']=None
    return output


def _ordinary_scan(ctx,phase):
    from .own_inventory_drift import fingerprint_inventory_item
    offset=0;total=None;records={};candidates=[];expected=_ordinary_expected(ctx.intent)
    sidecars={}
    while total is None or offset<total:
        _,value=ctx.read('list',{'offset':offset,'count':PAGE_SIZE,'no_content':0},phase)
        n,count,items=(value.get(k)for k in('total_count','item_count','item'))
        _ordinary_need(type(n)is int and 0<=n<=MAX_DRAFTS and type(count)is int and type(items)is list
            and count==len(items)==min(PAGE_SIZE,max(0,n-offset)) and(total is None or n==total),'OWN_DRAFT_RECONCILE_INCOMPLETE_LIST')
        total=n
        for item in items:
            _ordinary_need(type(item)is dict and reference_valid(item.get('media_id'),ctx.p.source_kind=='SYNTHETIC_SETUP')
                and type(item.get('update_time'))is int and item['update_time']>=0,'OWN_DRAFT_RECONCILE_INVALID_LIST')
            ref=item['media_id'];_ordinary_need(ref not in records,'OWN_DRAFT_RECONCILE_INVALID_LIST')
            content=item.get('content')
            _ordinary_need(type(content)is dict and type(content.get('news_item'))is list and 1<=len(content['news_item'])<=10,'DRAFT_NEWS_SHAPE')
            records[ref]={'update_time':item['update_time'],'content_sha256':digest(content)}
            if sidecars is not None:
                try:sidecars[ref]=fingerprint_inventory_item(content)
                except Exception:sidecars=None
            if _ordinary_coarse(content,expected,ctx.p.source_kind=='SYNTHETIC_SETUP'):candidates.append(ref)
        offset+=count
    _ordinary_need(len(records)==total,'OWN_DRAFT_RECONCILE_INCOMPLETE_LIST')
    ctx.inventory_scans[phase]=sidecars
    return records,candidates


def _ordinary_get(ctx,reference,phase):
    response,_=ctx.read('get',{'media_id':reference},phase)
    return _ordinary_observe(response,ctx.lease.token,ctx.p.source_kind=='SYNTHETIC_SETUP',reference,ctx.intent)


def ordinary_reconcile(w,p,lease,row,intent,a):
    _ordinary_need(row['operation']=='add' and row['slot']=='draft' and row['state']=='RESULT_UNKNOWN')
    with _ordinary_context(w,p,lease,a,row,intent)as ctx:
        observation=None;reference=None
        try:
            first,candidates=_ordinary_scan(ctx,'FIRST_LIST');ctx.candidate_count=len(candidates)
            _ordinary_need(len(candidates)<=MAX_CANDIDATES,'OWN_DRAFT_RECONCILE_NO_UNIQUE_MATCH')
            matches=[]
            for ref in candidates:
                current=_ordinary_get(ctx,ref,'CANDIDATE_GET');ctx.observations.append((ref,current))
                if current['strict']:matches.append((ref,current))
            # Retain the already read unique target even if the later inventory
            # changes. The error return still rechecks current authority and
            # remains UNVERIFIED; none of the strict CAS conditions are relaxed.
            if len(ctx.observations)==1:reference,observation=ctx.observations[0]
            second,_=_ordinary_scan(ctx,'SECOND_LIST')
            if first!=second:
                # Diagnosis cannot modify the original equality decision or
                # become a new failure gate. Fingerprints never leave memory.
                from .own_inventory_drift import compare_inventory_snapshots, POLICY as DRIFT_POLICY
                try:
                    scans=ctx.inventory_scans
                    ctx.inventory_drift=compare_inventory_snapshots(first,second,
                        scans['FIRST_LIST'],scans['SECOND_LIST'],
                        [ref for ref,_ in ctx.observations])
                except Exception:
                    ctx.inventory_drift={'policy':DRIFT_POLICY,'state':'UNAVAILABLE'}
            _ordinary_need(first==second,'OWN_DRAFT_RECONCILE_CHANGED')
            if len(matches)!=1:
                return _ordinary_result(ctx,a,'UNVERIFIED','NO_UNIQUE_STRICT_MATCH',observation,reference)
            reference,observation=matches[0]
            final=_ordinary_get(ctx,reference,'FINAL_GET')
            if not final['strict']:
                return _ordinary_result(ctx,a,'UNVERIFIED','FINAL_GET_MISMATCH',final,reference)
            ctx.guard();completed=w.clock()
            proof={'schema':2,'origin':ORDINARY_ORIGIN,'policy':ORDINARY_POLICY,
                'original':{k:row[k]for k in IDENTITY},'selector':deepcopy(intent['selector']),
                'projection_digest':digest(intent['projection']),'uploads_digest':digest(intent['uploads']),
                'delegation':ctx.delegation,'started':ctx.started,'not_after':ctx.not_after,'completed':completed,
                'reference':reference,'scan_digest':digest(first),'inventory_total':len(first),'candidate_count':len(candidates),
                'unique_matches':1,'strict_projection_digest':digest(final['matched_projection']),'calls':dict(ctx.calls)}
            name='draft-ordinary-'+row['id']+'-'+uuid4().hex+'.json'
            _ordinary_need(len((encoded(proof)+'\n').encode())<=32768,'OWN_DRAFT_RECONCILE_BUDGET')
            proof_hash=write_once(w.db.path.parent,name,proof,expected_root=w.state_root_identity)
            result={'reference':reference,'completion_origin':ORDINARY_ORIGIN,'reconciliation_proof':name,'reconciliation_proof_sha256':proof_hash}
            with _history_transaction(w.db,write=True)as(db,h):
                current,m=ctx.guard_in(db,h)
                _ordinary_need(current['state']=='RESULT_UNKNOWN' and stored(current['result'],current['result_digest'])=={})
                changed=db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND result='{}' AND intent_digest=? AND approval_digest=?",
                    (encoded(result),digest(result),completed,row['id'],row['owner'],row['intent_digest'],row['approval_digest'])).rowcount
                _ordinary_need(changed==1,'OWN_DRAFT_RECONCILE_CHANGED')
                fresh=db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone()
                w._step(db,p,fresh,history_locators=h)
                w._release_lock(db,p,m,row['id'])
                ctx.expected=dict(fresh);ctx.current()
            independent=_ordinary_get(ctx,reference,'INDEPENDENT_GET')
            state='MATCHED'if independent['strict']else'UNVERIFIED'
            with _history_transaction(w.db,write=True)as(db,h):
                ctx.guard_in(db,h);db.execute('UPDATE own_steps SET readback=? WHERE id=?',(state,row['id']))
                ctx.expected=dict(db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone());ctx.current()
            return _ordinary_result(ctx,a,state,'EXACT_MATCH'if independent['strict']else'INDEPENDENT_GET_MISMATCH',independent,reference)
        except WCEError as error:
            # Fresh authority is still required before releasing observations.
            return _ordinary_result(ctx,a,'UNVERIFIED',error.code,observation,reference)


def ordinary_independent_readback(w,p,lease,row,intent,result,a):
    _ordinary_need(row['state']=='SUCCEEDED' and result.get('completion_origin')==ORDINARY_ORIGIN)
    with _ordinary_context(w,p,lease,a,row,intent)as ctx:
        observation=None
        try:
            observation=_ordinary_get(ctx,result['reference'],'INDEPENDENT_GET')
            state='MATCHED'if observation['strict']else'UNVERIFIED'
            with _history_transaction(w.db,write=True)as(db,h):
                ctx.guard_in(db,h);db.execute('UPDATE own_steps SET readback=? WHERE id=?',(state,row['id']))
                ctx.expected=dict(db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone());ctx.current()
            return _ordinary_result(ctx,a,state,'INDEPENDENT_GET',observation,result['reference'])
        except WCEError as error:
            return _ordinary_result(ctx,a,'UNVERIFIED',error.code,observation,result['reference'])


def validate_ordinary_proof(w,db,p,row,intent,result):
    try:
        _ordinary_need(type(result)is dict and set(result)=={'reference','completion_origin','reconciliation_proof','reconciliation_proof_sha256'}
            and result['completion_origin']==ORDINARY_ORIGIN)
        name=result['reconciliation_proof']
        _ordinary_need(type(name)is str and name.startswith('draft-ordinary-'+row['id']+'-') and name.endswith('.json') and '/'not in name and '\\'not in name)
        raw,_=private_read(w.db.path.parent/name)
        _ordinary_need(sha(raw)==result['reconciliation_proof_sha256'])
        proof=decode_json(raw,32768,max_nodes=4096)
        keys={'schema','origin','policy','original','selector','projection_digest','uploads_digest','delegation','started','not_after','completed','reference','scan_digest','inventory_total','candidate_count','unique_matches','strict_projection_digest','calls'}
        _ordinary_need(type(proof)is dict and set(proof)==keys and type(proof['schema'])is int and proof['schema']==2
            and proof['origin']==ORDINARY_ORIGIN and proof['policy']==ORDINARY_POLICY
            and raw==(encoded(proof)+'\n').encode() and proof['original']=={k:row[k]for k in IDENTITY}
            and proof['selector']==intent['selector'] and proof['projection_digest']==proof['strict_projection_digest']==digest(intent['projection'])
            and proof['uploads_digest']==digest(intent['uploads']) and proof['reference']==result['reference']
            and reference_valid(proof['reference'],p.source_kind=='SYNTHETIC_SETUP'))
        _ordinary_need(all(type(proof[k])in(int,float)and math.isfinite(proof[k])for k in('started','not_after','completed'))
            and row['created']<=proof['started']<=proof['completed']<proof['not_after'] and row['completed']==proof['completed'])
        _ordinary_need(type(proof['candidate_count'])is int and 1<=proof['candidate_count']<=4
            and proof['candidate_count']<=proof['inventory_total']
            and type(proof['unique_matches'])is int and proof['unique_matches']==1
            and type(proof['calls'])is dict and set(proof['calls'])=={'list','get'}
            and all(type(v)is int for v in proof['calls'].values())
            and type(proof['inventory_total'])is int and 1<=proof['inventory_total']<=MAX_DRAFTS
            and proof['calls']['list']==2*max(1,(proof['inventory_total']+PAGE_SIZE-1)//PAGE_SIZE)
            and proof['calls']['get']==proof['candidate_count']+1
            and sum(proof['calls'].values())<=105)
        strict_validate(proof['scan_digest'],DIGEST)
        _ordinary_delegation(w,db,p,None,proof['delegation'])
        # No active schema6 approval, old expiry renewal or current code-scope equality.
        m,d=w._bundle(db,p,intent['selector']['bundle_id'],intent['selector']['version'])
        approval=w._approval(db,p,m,d,row['approval_id'],False)
        _ordinary_need(stored(approval['body'],approval['body_digest'])['schema']==7)
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT')from None
