"""Archive a qualified original response before dynamic result-release gates.

This is historical accounting, never a new dispatch or permission grant. Proofs
contain the qualified minimal result, not raw HTTP, token or request URL. Only
an admitted persistent one-shot stack can create one; recovery never sends.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
import sys
import threading
import weakref
from types import MappingProxyType
from pathlib import Path

from .contracts import WCEError
from .bounded_file import identity, file_state
from .http_transport import HTTPRequest, HTTPResponse
from .own_bootstrap_security import path_check, private_read
from .prepared_draft_fixture import decode_json
from .service import canonical, digest
from . import own_wire as wire
from .upload_wire import contains_secret, inspect_response, BODY_API_REFERENCE_POLICY, COVER_RESPONSE_POLICY

ORIGIN = 'ORIGINAL_RESPONSE_ARCHIVE'
POLICY = 'ADMITTED_RESPONSE_ARCHIVE_V1'
_FIELDS = ('id', 'tenant', 'principal', 'connection', 'resource', 'request_key',
           'operation', 'slot', 'manifest_digest', 'target', 'approval_id',
           'approval_digest', 'intent_digest', 'owner', 'created')


def fail(code='OWN_RESPONSE_PROOF_INVALID'):
    raise WCEError(code)


def row_pin(row):
    return {k: row[k] for k in _FIELDS}


def filename(row):
    from .prepared_contracts import strict_validate, ID
    strict_validate(row['id'], ID)
    strict_validate(row['owner'], ID)
    return 'response-' + row['id'] + '-' + row['owner'] + '.json'


@dataclass(frozen=True, eq=False)
class DispatchPin:
    row: dict
    binding: dict
    request_sha256: str
    root_identity: tuple


# Internal issued current-stack facts. No JSON/dataclass constructor can mint
# a parser frame; only the original committed _execute continuation can.
_DISPATCH_FRAMES = weakref.WeakKeyDictionary()
_WIRE_PARSE = wire.parse
_INSPECT_RESPONSE = inspect_response


def _current_stack(w, p, row, request=None, expected=None):
    from .own_workflow import OwnWorkflow
    post = execute = None
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code is OwnWorkflow._execute_postcommit.__code__ and frame.f_locals.get('self') is w:
                post = frame
                execute = frame.f_back
                break
            frame = frame.f_back
        if (post is None or execute is None or execute.f_code is not OwnWorkflow._execute.__code__
                or execute.f_locals.get('self') is not w or post.f_locals.get('p') is not p
                or post.f_locals.get('row') is not row or execute.f_locals.get('row') is not row
                or execute.f_locals.get('request') is not post.f_locals.get('request')
                or (request is not None and request is not post.f_locals.get('request'))):
            fail('OWN_RESPONSE_DISPATCH_FRAME_REQUIRED')
        identifiers = (id(post), id(execute), id(row))
        if expected is not None and identifiers != expected:
            fail('OWN_RESPONSE_DISPATCH_FRAME_CHANGED')
        return identifiers
    finally:
        del frame, post, execute


def _frame(w, p, row, dispatch):
    if type(dispatch) is not DispatchPin:
        fail('OWN_RESPONSE_DISPATCH_FRAME_REQUIRED')
    facts = _DISPATCH_FRAMES.get(dispatch)
    if (facts is None or facts['workflow']() is not w or facts['pid'] != os.getpid()
            or facts['thread'] != threading.get_ident()
            or facts['row'] != canonical(row_pin(row)) or facts['row'] != canonical(dispatch.row)
            or facts['binding'] != canonical(p.binding()) or facts['binding'] != canonical(dispatch.binding)
            or facts['request_sha256'] != dispatch.request_sha256
            or facts['root_identity'] != dispatch.root_identity
            or facts['root_path'] != str(w.db.path.parent) or facts['source_kind'] != p.source_kind):
        fail('OWN_RESPONSE_DISPATCH_FRAME_CHANGED')
    _current_stack(w, p, row, expected=facts['stack'])
    return facts


def parse_captured_response(w, p, row, dispatch, response, token):
    facts = _frame(w, p, row, dispatch)
    if facts['parsed'] is not None:
        fail('OWN_RESPONSE_DISPATCH_FRAME_CONSUMED')
    branch, operation, policy = facts['parser']
    synthetic = facts['source_kind'] == 'SYNTHETIC_SETUP'
    if branch == 'BODY':
        inspected = _INSPECT_RESPONSE('article_body', response, token, policy=policy, production=not synthetic)
        value = inspected.reply
        reply = wire.OwnReply({'url': value.url} if value.classification == 'PARSED_SUCCESS' else None,
            value.error_code, value.requires_credential_update, inspected.reason, inspected)
    elif branch == 'COVER':
        inspected = _INSPECT_RESPONSE('permanent_cover', response, token, policy=policy, production=not synthetic)
        value = inspected.reply
        reply = wire.OwnReply({'media_id': value.media_id, 'url': value.url}
            if value.classification == 'PARSED_SUCCESS' else None,
            value.error_code, value.requires_credential_update, inspected.reason, inspected)
    else:
        reply = _WIRE_PARSE(operation, response, token, synthetic)
    # Only qualified minimal data/digests are kept in this ephemeral frame.
    updated = dict(facts)
    updated['parsed'] = (sha256(response.body).hexdigest() if type(response) is HTTPResponse else None,
                         canonical(reply.result))
    _DISPATCH_FRAMES[dispatch] = MappingProxyType(updated)
    return reply


def release_dispatch(dispatch):
    if type(dispatch) is DispatchPin:
        _DISPATCH_FRAMES.pop(dispatch, None)


def eligible(w, db, p, row, *, history_locators=None):
    intent, _ = w._step(db, p, row, history_locators=history_locators)
    m, d = w._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
    approval = w._approval(db, p, m, d, row['approval_id'], False)
    from .own_lineage import seal
    if (json.loads(approval['body'])['schema'] != 7 or seal(db, m)['legacy'] != 0):
        fail('OWN_RESPONSE_ARCHIVE_NOT_DELEGATED')
    return intent, m


def capture(w, p, row, request):
    if type(request) is not HTTPRequest or request.method != 'POST':
        fail()
    stack = _current_stack(w, p, row, request)
    with _history_transaction(w.db) as (db, history_locators):
        current = db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone()
        intent, manifest = eligible(w, db, p, current, history_locators=history_locators)
        if dict(current) != dict(row) or row['state'] != 'RESULT_UNKNOWN':
            fail()
        approval = w._approval(db, p, manifest, row['manifest_digest'], row['approval_id'], False)
        if approval['body_digest'] != row['approval_digest']:
            fail('OWN_RESPONSE_DISPATCH_FRAME_CHANGED')
        body = json.loads(approval['body'])
        cover_policy = body.get('delegated', {}).get('cover_response_policy')
    operation = row['operation']
    # BODY keeps the existing fixed reference policy. Only COVER selects new
    # versus legacy semantics from its actual immutable admitted approval.
    parser = (('BODY', operation, BODY_API_REFERENCE_POLICY) if operation == 'body' else
              ('COVER', operation, COVER_RESPONSE_POLICY) if operation == 'cover' and cover_policy == COVER_RESPONSE_POLICY else
              ('LEGACY', operation, None))
    dispatch = DispatchPin(row_pin(row), p.binding(), sha256(request.body).hexdigest(), path_check(w.db.path.parent, True))
    _DISPATCH_FRAMES[dispatch] = MappingProxyType({'workflow': weakref.ref(w), 'pid': os.getpid(),
        'thread': threading.get_ident(), 'stack': stack, 'row': canonical(dispatch.row),
        'binding': canonical(dispatch.binding), 'request_sha256': dispatch.request_sha256,
        'root_identity': dispatch.root_identity, 'root_path': str(w.db.path.parent),
        'source_kind': p.source_kind, 'parser': parser, 'parsed': None})
    return dispatch


def _read(w, p, row, db=None):
    path = w.db.path.parent / filename(row)
    if not os.path.lexists(path):
        fail('OWN_RESPONSE_PROOF_MISSING')
    raw, pin = private_read(path)
    index_raw, _ = private_read(path.with_name('response-index-' + row['id'] + '-' + row['owner'] + '.json'))
    index = decode_json(index_raw, 1024)
    if (type(index) is not dict or set(index) != {'schema', 'row_sha256', 'proof_sha256'}
            or type(index['schema']) is not int or index['schema'] != 1
            or index['row_sha256'] != digest(row_pin(row))
            or index['proof_sha256'] != sha256(raw).hexdigest()
            or (canonical(index) + '\n').encode() != index_raw):
        fail()
    proof = decode_json(raw, 8192)
    if type(proof) is dict and type(proof.get('schema')) is int and proof['schema'] == 2:
        from .own_group_response_archive import read_group_archive
        return read_group_archive(w,p,row,proof,raw,pin,db)
    if (type(proof) is not dict or set(proof) != {'schema', 'policy', 'provenance',
            'binding', 'row', 'request_sha256', 'response_sha256', 'result'}
            or type(proof['schema']) is not int or proof['schema'] != 1
            or proof['policy'] != POLICY or proof['binding'] != p.binding()
            or proof['row'] != row_pin(row)
            or proof['provenance'] != ('SYNTHETIC_OWN_WIRE' if p.source_kind == 'SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE')
            or (canonical(proof) + '\n').encode() != raw):
        fail()
    from .prepared_contracts import strict_validate, DIGEST
    for key in ('request_sha256', 'response_sha256'):
        strict_validate(proof[key], DIGEST)
    result = proof['result']
    expected = {'url'} if row['operation'] == 'body' else {'media_id', 'url'} if row['operation'] == 'cover' else {'reference'}
    if type(result) is not dict or set(result) != expected:
        fail()
    synthetic = p.source_kind == 'SYNTHETIC_SETUP'
    if 'url' in result and not wire.image_url(result['url'], synthetic):
        fail()
    if row['operation'] == 'body':
        from .upload_wire import api_reference_reason
        if api_reference_reason(result['url']) is not None:
            fail()
    if 'media_id' in result and not wire.identifier(result['media_id'], synthetic):
        fail()
    if 'reference' in result:
        from .own_draft_wire import reference_valid
        if not reference_valid(result['reference'], synthetic):
            fail()
    return proof, raw, pin


def completed(proof, raw, row):
    return proof['result'] | {'completion_origin': ORIGIN,
        'reconciliation_proof': filename(row),
        'reconciliation_proof_sha256': sha256(raw).hexdigest()}


def validate_proof(w, db, p, row, intent, result):
    # Do not recurse into _step: it is the caller of this validator.
    proof, raw, _ = _read(w, p, row, db=db)
    from .own_group_response_archive import require_group_branch_in
    require_group_branch_in(db,row,proof)
    if result != completed(proof, raw, row):
        fail()
    m, d = w._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
    a = w._approval(db, p, m, d, row['approval_id'], False)
    from .own_lineage import seal
    if json.loads(a['body'])['schema'] != 7 or seal(db, m)['legacy'] != 0:
        fail()


def _durable(w, row):
    """Re-establish durability, including after unknown fsync/commit outcomes."""
    parent = w.db.path.parent
    root_pin = path_check(parent, True)
    path = parent / filename(row)
    index = path.with_name('response-index-' + row['id'] + '-' + row['owner'] + '.json')
    index_before = path_check(index)
    before = path_check(path)
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(directory)) != root_pin:
            fail()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if file_state(os.fstat(fd)) != before or path_check(path) != before:
                fail()
            os.fsync(fd)
            if file_state(os.fstat(fd)) != before:
                fail()
        finally:
            os.close(fd)
        index_fd = os.open(index.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if file_state(os.fstat(index_fd)) != index_before or path_check(index) != index_before:
                fail()
            os.fsync(index_fd)
            if file_state(os.fstat(index_fd)) != index_before:
                fail()
        finally:
            os.close(index_fd)
        os.fsync(directory)
        if path_check(index) != index_before:
            fail()
        if path_check(parent, True) != root_pin or path_check(path) != before:
            fail()
    finally:
        os.close(directory)


def _group_result(db, row, result, proof_sha, *, existing):
    # Fixed module functions, never a model-supplied callback. A group ACK is
    # historical accounting in THIS result transaction, not new authority.
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 9:
        from .draft_group_store import observe_own_step_result, verify_existing_own_step_result
        leaf = verify_existing_own_step_result if existing else observe_own_step_result
        leaf(db, row, archive_proof_sha=proof_sha, result=result)
    elif version not in (4,5,6,7,8):
        fail()



def reconcile(w, p, row):
    """Local proof-only CAS; caller owns serial queue/current read admission."""
    proof, raw, pin = _read(w, p, row)
    if proof['schema'] == 2:
        from .own_group_response_archive import reconcile_group_archive
        return reconcile_group_archive(w,p,row,proof,raw)
    _durable(w, row)
    if _read(w, p, row)[1:] != (raw, pin):
        fail()
    result = completed(proof, raw, row)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        current = db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone()
        intent, m = eligible(w, db, p, current, history_locators=history_locators)
        if row_pin(current) != row_pin(row):
            fail()
        if current['state'] == 'SUCCEEDED':
            if json.loads(current['result']) != result:
                fail('OWN_RESPONSE_PROOF_CONFLICT')
            _group_result(db, current, result, sha256(raw).hexdigest(), existing=True)
            return
        if current['state'] != 'RESULT_UNKNOWN' or json.loads(current['result']) != {}:
            fail()
        w._owned_lock(db, p, m, row['id'])
        if _read(w, p, row)[1:] != (raw, pin):
            fail()
        changed = db.execute("UPDATE own_steps SET state='SUCCEEDED', result=?,result_digest=?,completed=? "
            "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
            (canonical(result), digest(result), max(w.clock(), row['created']), row['id'], row['owner'],
             row['intent_digest'], row['approval_digest'])).rowcount
        if changed != 1:
            fail('OWN_RESPONSE_PROOF_CONFLICT')
        updated = db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone()
        _group_result(db, updated, result, sha256(raw).hexdigest(), existing=False)
        w._release_lock(db, p, m, row['id'])
        w._step(db, p, db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone(), history_locators=history_locators)


def archive(w, p, row, dispatch, response, reply, token):
    if reply.result is None:
        return False
    if (type(dispatch) is not DispatchPin or dispatch.row != row_pin(row)
            or dispatch.binding != p.binding() or dispatch.root_identity != path_check(w.db.path.parent, True)
            or type(response) is not HTTPResponse or response.status != 200
            or contains_secret(reply.result, token)):
        fail()
    facts = _frame(w, p, row, dispatch)
    if facts['parsed'] != (sha256(response.body).hexdigest(), canonical(reply.result)):
        fail('OWN_RESPONSE_DISPATCH_FRAME_CHANGED')
    proof = {'schema': 1, 'policy': POLICY,
        'provenance': 'SYNTHETIC_OWN_WIRE' if p.source_kind == 'SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE',
        'binding': dispatch.binding, 'row': dispatch.row,
        'request_sha256': dispatch.request_sha256,
        'response_sha256': sha256(response.body).hexdigest(), 'result': reply.result}
    raw = (canonical(proof) + '\n').encode()
    if len(raw) > 8192:
        fail()
    path = w.db.path.parent / filename(row)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if (identity(os.fstat(directory)) != dispatch.root_identity
                or path_check(path.parent, True) != dispatch.root_identity):
            fail()
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        index_raw = (canonical({'schema': 1, 'row_sha256': digest(row_pin(row)),
            'proof_sha256': sha256(raw).hexdigest()}) + '\n').encode()
        index_name = 'response-index-' + row['id'] + '-' + row['owner'] + '.json'
        index_fd = os.open(index_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(index_fd, 'wb') as f:
            f.write(index_raw)
            f.flush()
            os.fsync(f.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    reconcile(w, p, row)
    return True


from .draft_group_history_context import history_transaction as _history_transaction
