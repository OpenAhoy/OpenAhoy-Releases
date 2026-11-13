"""Host-only, explicitly approved extra body send. Original UNKNOWN is immutable."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from .contracts import WCEError
from .own_auth import APIS, finite
from .own_diagnostics import projection, validate as validate_diagnostic
from .prepared_contracts import DIGEST, strict_validate
from .service import canonical, digest
from . import own_wire as wire

POLICY = 'BODY_ONCE_AFTER_UNKNOWN_V1'
ORIGIN = 'EXPLICIT_BODY_REPLACEMENT_RESPONSE'


def code_scope():
    """Actual packaged Python bytes, not a caller-supplied candidate label."""
    root = Path(__file__).resolve().parent
    files = {}
    for path in sorted(root.glob('*.py')):
        if path.is_symlink() or not path.is_file():
            raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
        files[path.name] = sha256(path.read_bytes()).hexdigest()
    return digest(files)


def stored(raw, fingerprint):
    try:
        value = json.loads(raw)
        if canonical(value) != raw or digest(value) != fingerprint:
            raise ValueError()
        return value
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def policy_for(original, intent, scope):
    strict_validate(scope, DIGEST)
    return {'schema': 1, 'policy': POLICY, 'candidate_scope': scope,
        'maximum_new_sends': 1, 'duplicate_image_risk_accepted': True,
        'binding': intent['binding'], 'selector': intent['selector'], 'asset': intent['asset'],
        'original_step_id': original['id'], 'original_request_key': original['request_key'],
        'original_row_digest': digest(dict(original))}


def validate_policy(db, value):
    if type(value) is not dict or type(value.get('candidate_scope')) is not str:
        raise WCEError('OWN_STATE_CORRUPT')
    original = db.execute('SELECT * FROM own_steps WHERE id=?', (value.get('original_step_id'),)).fetchone()
    if original is None or original['operation'] != 'body' or original['state'] != 'RESULT_UNKNOWN':
        raise WCEError('OWN_STATE_CORRUPT')
    intent = stored(original['intent'], original['intent_digest'])
    expected = policy_for(original, intent, value['candidate_scope'])
    if (value != expected or type(value.get('schema')) is not int or type(value.get('maximum_new_sends')) is not int
            or value.get('duplicate_image_risk_accepted') is not True):
        raise WCEError('OWN_STATE_CORRUPT')
    return original, intent


def snapshot(w, db, p, selector, request_key, *, history_locators=None):
    original = w._history(db, p, request_key, history_locators=history_locators)
    # _history's slot check is explicit below: the host does not choose another image.
    if original is None or original['state'] != 'RESULT_UNKNOWN' or original['operation'] != 'body':
        raise WCEError('OWN_BODY_RECOVERY_UNAVAILABLE')
    intent, _ = w._step(db, p, original, history_locators=history_locators)
    if intent['selector'] != selector:
        raise WCEError('OWN_SNAPSHOT_CHANGED')
    if db.execute('SELECT 1 FROM own_body_recoveries WHERE original_step_id=?', (original['id'],)).fetchone():
        raise WCEError('OWN_BODY_RECOVERY_ALREADY_ADMITTED')
    return policy_for(original, intent, code_scope())


def validate_record(db, row, source_kind):
    """Historical validation: expiry/cancellation never destroys a known result."""
    try:
        intent = stored(row['intent'], row['intent_digest'])
        if (type(intent) is not dict or set(intent) != {'schema', 'policy', 'fence', 'approval_id', 'approval_digest'}
                or type(intent['schema']) is not int or intent['schema'] != 1
                or intent['approval_id'] != row['approval_id'] or intent['approval_digest'] != row['approval_digest']):
            raise ValueError()
        policy = intent['policy']
        original, original_intent = validate_policy(db, policy)
        if (row['original_step_id'] != original['id'] or row['tenant'] != original['tenant']
                or row['resource'] != original['resource'] or policy['binding']['source_kind'] != source_kind
                or not finite(row['created']) or row['created'] < original['created']):
            raise ValueError()
        approval = db.execute('SELECT * FROM own_approvals WHERE id=?', (row['approval_id'],)).fetchone()
        body = stored(approval['body'], approval['body_digest'])
        if (body.get('schema') != 3 or body.get('body_recovery') != policy
                or approval['body_digest'] != row['approval_digest'] or body['fence'] != intent['fence']
                or body['binding'] != policy['binding'] or body['content_digest'] != policy['selector']['content_digest']
                or any(body[k] != policy['selector'][k] for k in ('bundle_id', 'version'))
                or any(approval[k] != original[k] for k in ('tenant', 'principal', 'connection', 'resource'))):
            raise ValueError()
        manifest_row = db.execute('SELECT * FROM own_articles WHERE bundle=? AND version=?',
            (policy['selector']['bundle_id'], policy['selector']['version'])).fetchone()
        if manifest_row is None:
            raise ValueError()
        from .own_group_json import read as read_manifest
        manifest = read_manifest(manifest_row['manifest'], manifest_row['digest'])
        if (set(body) != {'schema', 'binding', 'fence', 'bundle_id', 'version', 'content_digest',
                'slots', 'apis', 'expires', 'body_recovery'} or type(body['schema']) is not int
                or body['schema'] != 3 or body['fence'] != approval['binding_fence']
                or approval['manifest_digest'] != policy['selector']['content_digest']
                or manifest_row['digest'] != policy['selector']['content_digest']
                or manifest['binding'] != policy['binding'] or body['slots'] != manifest['assets']
                or body['apis'] != list(APIS) or not finite(approval['expires'])
                or not finite(body['expires']) or body['expires'] != approval['expires']
                or type(approval['cancelled']) is not int or approval['cancelled'] not in (0, 1)):
            raise ValueError()
        result = stored(row['result'], row['result_digest'])
        diag = stored(row['diagnostic'], row['diagnostic_digest'])
        if diag:
            validate_diagnostic(diag)
        if row['state'] == 'RESULT_UNKNOWN':
            if result or row['completed'] is not None:
                raise ValueError()
        elif row['state'] == 'SUCCEEDED':
            if (type(result) is not dict or set(result) != {'url'}
                    or not wire.image_url(result['url'], source_kind == 'SYNTHETIC_SETUP')
                    or not finite(row['completed']) or row['completed'] < row['created']):
                raise ValueError()
        else:
            raise ValueError()
        return original, original_intent, intent, result
    except WCEError:
        raise
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def mapping(w, db, p, original, *, history_locators=None):
    from .own_step_history import validate_original_upload_in
    r = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?', (original['id'],)).fetchone()
    if r is None:
        return None
    validate_original_upload_in(w, db, p, original, history_locators=history_locators)
    _, i, _, result = validate_record(db, r, p.source_kind)
    m, d = w._bundle(db, p, i['selector']['bundle_id'], i['selector']['version'])
    w._approval(db, p, m, d, r['approval_id'], active=False)
    if r['state'] != 'SUCCEEDED':
        if db.execute('PRAGMA user_version').fetchone()[0] >= 4:
            attempt = db.execute('SELECT 1 FROM own_body_attempts WHERE original_step_id=?', (original['id'],)).fetchone()
            if attempt is not None:
                from .own_body_attempt import mapping as terminal_mapping
                return terminal_mapping(w, db, p, original, history_locators=history_locators)
        if db.execute('PRAGMA user_version').fetchone()[0] >= 3:
            from .own_body_followup import mapping as followup_mapping
            return followup_mapping(w, db, p, original, history_locators=history_locators)
        return None
    return result, {'source': ORIGIN, 'recovery_id': r['id'], 'original_step_id': original['id'],
        'intent_digest': r['intent_digest'], 'result_digest': r['result_digest']}


def check_history_blockers(w, db, p, current_step_id=None, *, history_locators=None):
    """Exclude only each fully validated, successfully replaced body history.

    This supplies no new grant. The caller separately validates its own current
    exact approval and activity lock. An in-flight caller may exclude only its
    already verified current step, never a key/slot/selector alias.
    """
    rows = db.execute("SELECT * FROM own_steps WHERE tenant=? AND resource=? AND state='RESULT_UNKNOWN'",
        (p.actor.tenant_id, p.resource_id)).fetchall()
    for original in rows:
        if original['id'] == current_step_id:
            continue
        i, _ = w._step(db, p, original, history_locators=history_locators)
        if original['operation'] != 'body' or mapping(w, db, p, original, history_locators=history_locators) is None:
            raise WCEError('OWN_RESOURCE_RESULT_UNKNOWN')
        m, d = w._bundle(db, p, i['selector']['bundle_id'], i['selector']['version'])
        # The old selector's complete material chain includes its cover proof;
        # checking only the replacement URL would miss a damaged cover origin.
        w._uploads(db, p, m, d, history_locators=history_locators)


def check_resource_write(w, db, p, *, history_locators=None):
    check_history_blockers(w, db, p, history_locators=history_locators)
    if db.execute('SELECT 1 FROM own_resource_locks WHERE tenant=? AND resource=?',
            (p.actor.tenant_id, p.resource_id)).fetchone():
        raise WCEError('OWN_RESOURCE_RESULT_UNKNOWN')


def view(w, db, p, row, *, history_locators=None):
    original, i, _, result = validate_record(db, row, p.source_kind)
    w._step(db, p, original, history_locators=history_locators)
    m, d = w._bundle(db, p, i['selector']['bundle_id'], i['selector']['version'])
    w._approval(db, p, m, d, row['approval_id'], active=False)
    return {'recovery_id': row['id'], 'original_step_id': original['id'],
        'original_request_key': original['request_key'], 'original_state': 'RESULT_UNKNOWN',
        'state': row['state'], 'completion_origin': ORIGIN if result else 'UNDETERMINED',
        'result': result, 'response_diagnostic': stored(row['diagnostic'], row['diagnostic_digest'])
        or {'reason': 'NOT_RECORDED'}}


def execute(w, p, lease, approval_id):
    """Only the stack committing a fresh admission may reach the sender."""
    action = APIS[1]
    w._network(p, lease, action, True)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        approval = db.execute('SELECT * FROM own_approvals WHERE id=?', (approval_id,)).fetchone()
        if approval is None:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        body = stored(approval['body'], approval['body_digest'])
        if body.get('schema') != 3:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        policy = body['body_recovery']
        original, old_intent = validate_policy(db, policy)
        w._step(db, p, original, history_locators=history_locators)
        selector = policy['selector']
        m, d = w._bundle(db, p, selector['bundle_id'], selector['version'])
        w._approval(db, p, m, d, approval_id)
        if policy['candidate_scope'] != code_scope():
            raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
        previous = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?', (original['id'],)).fetchone()
        if previous is not None:
            return view(w, db, p, previous, history_locators=history_locators)
        unknowns = db.execute("SELECT id FROM own_steps WHERE tenant=? AND resource=? AND state='RESULT_UNKNOWN'",
            (p.actor.tenant_id, p.resource_id)).fetchall()
        if len(unknowns) != 1 or unknowns[0]['id'] != original['id']:
            raise WCEError('OWN_RESOURCE_RESULT_UNKNOWN')
        _, data = w._asset(db, p.binding(), policy['asset']['asset_ref'], 'body')
        request = wire.encode_upload('article_body', policy['asset']['declared_type'], data, lease.token)
        intent = {'schema': 1, 'policy': policy, 'fence': p.fence(),
            'approval_id': approval_id, 'approval_digest': approval['body_digest']}
        identifier, owner = 'own-body-recovery-' + uuid4().hex, uuid4().hex
        w._network(p, lease, action, True)
        from .draft_group_store import check_account_writer
        check_account_writer(db, history_locators=history_locators)
        db.execute('INSERT INTO own_body_recoveries(id,original_step_id,tenant,resource,owner,approval_id,'
            'approval_digest,intent,intent_digest,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (identifier, original['id'], p.actor.tenant_id, p.resource_id, owner, approval_id,
             approval['body_digest'], canonical(intent), digest(intent), 'RESULT_UNKNOWN', w.clock()))
        changed = db.execute("UPDATE own_resource_locks SET kind='recovery',owner_id=? "
            "WHERE tenant=? AND resource=? AND kind='step' AND owner_id=?",
            (identifier, p.actor.tenant_id, p.resource_id, original['id'])).rowcount
        if changed != 1:
            raise WCEError('OWN_STATE_CORRUPT')
    # A failed/unknown COMMIT never reaches this line. An admitted but unsent
    # attempt stays UNKNOWN; no restart can claim this stack's owner capability.
    def guard():
        w._network(p, lease, action, True)
        if policy['candidate_scope'] != code_scope():
            raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
        with _history_transaction(w.db) as (db, history_locators):
            w._resource(db, p, history_locators=history_locators)
            r = db.execute('SELECT * FROM own_body_recoveries WHERE id=?', (identifier,)).fetchone()
            if r is None or r['owner'] != owner or r['intent_digest'] != digest(intent):
                raise WCEError('OWN_STATE_CORRUPT')
            validate_record(db, r, p.source_kind)
            w._approval(db, p, m, d, approval_id)
    guard()
    # The dispatch point is the last authorization check before send. Revocation
    # cannot recall an already dispatched HTTP request; it blocks result commit.
    response = w._send(p, lease, request, action, True)
    reply = wire.parse('body', response, lease.token, p.source_kind == 'SYNTHETIC_SETUP')
    diag = projection(reply, response)
    try:
        with w.db.transaction(write=True) as db:
            db.execute("UPDATE own_body_recoveries SET diagnostic=?,diagnostic_digest=? "
                "WHERE id=? AND owner=? AND diagnostic='{}'", (canonical(diag), digest(diag), identifier, owner))
    except Exception:
        pass
    guard()
    if reply.result is not None:
        with _history_transaction(w.db, write=True) as (db, history_locators):
            w._resource(db, p, history_locators=history_locators)
            w._network(p, lease, action, True)
            w._approval(db, p, m, d, approval_id)
            changed = db.execute("UPDATE own_body_recoveries SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
                "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=?",
                (canonical(reply.result), digest(reply.result), w.clock(), identifier, owner, digest(intent))).rowcount
            if changed != 1:
                raise WCEError('OWN_STATE_CORRUPT')
            if db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? AND kind='recovery' AND owner_id=?",
                    (p.actor.tenant_id, p.resource_id, identifier)).rowcount != 1:
                raise WCEError('OWN_STATE_CORRUPT')
            w._network(p, lease, action, True)
            w._approval(db, p, m, d, approval_id)
            if policy['candidate_scope'] != code_scope():
                raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
    guard()
    with _history_transaction(w.db) as (db, history_locators):
        r = db.execute('SELECT * FROM own_body_recoveries WHERE id=?', (identifier,)).fetchone()
        return view(w, db, p, r, history_locators=history_locators)


from .draft_group_history_context import history_transaction as _history_transaction
