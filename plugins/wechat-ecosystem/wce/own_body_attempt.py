"""Terminal body attempt: fixed original root, ordinal four, no recursive budget.

The three legacy admissions are read-only history. Only a fresh committed owner
stack may dispatch once. A restarted or uncertain admission never sends.
"""
from uuid import uuid4

from .contracts import WCEError
from .http_transport import HTTPResponse
from .own_auth import APIS, finite
from .own_body_recovery import code_scope, stored
from . import own_body_followup as legacy
from .prepared_contracts import DIGEST, ID, strict_validate
from .service import canonical, digest
from .upload_wire import (BODY_API_REFERENCE_POLICY, api_reference_reason,
                          inspect_response, validate_inspection_diagnostic)
from . import own_wire as wire

POLICY = 'FINAL_BODY_ATTEMPT4_V1'
SEND = 'SEND_FINAL_ATTEMPT4'
ADOPT = 'ADOPT_FINAL_OBSERVATION_ONLY'
ORIGIN = 'FINAL_BODY_ATTEMPT4_REFERENCE_V2'


def fail():
    raise WCEError('OWN_STATE_CORRUPT')


def legacy_history(db, root_id, source_kind):
    """No current grants, mapping calls or recursion into the terminal journal."""
    root = db.execute('SELECT * FROM own_steps WHERE id=?', (root_id,)).fetchone()
    third = db.execute('SELECT * FROM own_body_followups WHERE original_step_id=?', (root_id,)).fetchone()
    if root is None or third is None:
        fail()
    original, old_intent, _, _ = legacy.validate_record(db, third, source_kind)
    prior = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?', (root_id,)).fetchone()
    if (dict(original) != dict(root) or prior is None
            or any(row['state'] != 'RESULT_UNKNOWN' for row in (root, prior, third))):
        fail()
    observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?', (third['id'],)).fetchone()
    # Existing qualified or quarantined references need their own adoption
    # contract, never an unnecessary fourth POST.
    observed = legacy._observation(db, third, stored(third['intent'], third['intent_digest'])['policy'], observation)
    if observed is not None and observed['url'] is not None:
        raise WCEError('OWN_BODY_ATTEMPT_REFERENCE_EXISTS')
    pins = []
    for ordinal, table, row in ((1, 'own_steps', root), (2, 'own_body_recoveries', prior),
                                (3, 'own_body_followups', third)):
        approval = db.execute('SELECT * FROM own_approvals WHERE id=?', (row['approval_id'],)).fetchone()
        # Cancellation is mutable authority metadata, not a historical response.
        # Pin immutable approval fields so cancelling an old grant cannot erase
        # the independently verified history or invalidate a known completion.
        immutable_approval = {k: approval[k] for k in approval.keys() if k != 'cancelled'}
        pins.append({'ordinal': ordinal, 'table': table, 'id': row['id'],
            'row_digest': digest(dict(row)), 'approval_digest': digest(immutable_approval),
            'observation_digest': digest(dict(observation)) if ordinal == 3 and observation is not None else None})
    diagnostic = db.execute('SELECT * FROM own_step_diagnostics WHERE step_id=?', (root_id,)).fetchone()
    pins[0]['diagnostic_digest'] = digest(dict(diagnostic)) if diagnostic is not None else None
    return root, old_intent, third, pins


def policy_for(db, root_id, source_kind, scope, draft_key, action=SEND):
    strict_validate(scope, DIGEST)
    strict_validate(draft_key, ID)
    if action not in (SEND, ADOPT):
        fail()
    root, old, _, pins = legacy_history(db, root_id, source_kind)
    return {'schema': 1, 'policy': POLICY, 'action': action,
        'response_policy': BODY_API_REFERENCE_POLICY, 'candidate_scope': scope,
        'ordinal': 4, 'maximum_total_admissions': 4, 'maximum_new_sends': 1 if action == SEND else 0,
        'duplicate_image_risk_accepted': True, 'binding': old['binding'],
        'selector': old['selector'], 'asset': old['asset'], 'draft_request_key': draft_key,
        'original_step_id': root['id'], 'original_request_key': root['request_key'], 'history': pins}


def validate_policy(db, policy):
    try:
        if type(policy) is not dict:
            fail()
        binding = policy['binding']
        expected = policy_for(db, policy['original_step_id'], binding['source_kind'],
            policy['candidate_scope'], policy['draft_request_key'], policy['action'])
        if policy['action'] == ADOPT:
            row = db.execute('SELECT * FROM own_body_attempts WHERE original_step_id=?',
                (policy['original_step_id'],)).fetchone()
            if row is None:
                fail()
            intent = stored(row['intent'], row['intent_digest'])
            sent = intent['policy']
            # Validate the send policy without following any adoption approval.
            validate_policy(db, sent)
            observation = read_observation(row, sent)
            if (observation is None or observation['url'] is None
                    or sent['draft_request_key'] != policy['draft_request_key']):
                fail()
            expected.update(attempt_id=row['id'], owner=row['owner'], intent_digest=row['intent_digest'],
                            observation_digest=row['observation_digest'])
        if (policy != expected or any(type(policy[k]) is not int for k in
                ('schema', 'ordinal', 'maximum_total_admissions', 'maximum_new_sends'))
                or policy['duplicate_image_risk_accepted'] is not True):
            fail()
        root = db.execute('SELECT * FROM own_steps WHERE id=?', (policy['original_step_id'],)).fetchone()
        return root, stored(root['intent'], root['intent_digest'])
    except WCEError:
        raise
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def read_observation(row, policy):
    value = stored(row['observation'], row['observation_digest'])
    if not value:
        if value != {}:
            fail()
        return None
    fields = {'schema', 'policy', 'root', 'ordinal', 'owner', 'intent_digest', 'binding',
        'selector', 'asset', 'candidate_scope', 'observed_at', 'http_status', 'diagnostic', 'url'}
    if (type(value) is not dict or set(value) != fields or type(value['schema']) is not int
            or value['schema'] != 1 or value['policy'] != BODY_API_REFERENCE_POLICY
            or type(value['ordinal']) is not int or value['ordinal'] != 4
            or value['root'] != row['original_step_id'] or value['owner'] != row['owner']
            or value['intent_digest'] != row['intent_digest']
            or not finite(value['observed_at']) or value['observed_at'] < row['created']
            or any(value[k] != policy[k] for k in ('binding', 'selector', 'asset', 'candidate_scope'))):
        fail()
    diagnostic = validate_inspection_diagnostic(value['diagnostic'])
    status = value['http_status']
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        fail()
    if value['url'] is not None:
        if (api_reference_reason(value['url']) is not None or diagnostic['reason'] != 'PARSED_SUCCESS'
                or diagnostic.get('reference') != {'policy': BODY_API_REFERENCE_POLICY, 'reason': 'REFERENCE_SAFE'}
                or any(state != 'PASS' for _, state in diagnostic['stages'])
                or diagnostic['code_form'] not in ('ABSENT', 'ZERO')
                or type(status) is not int or not 200 <= status < 300):
            fail()
    elif diagnostic['reason'] == 'PARSED_SUCCESS':
        fail()
    return value


def approval_history(db, identifier, fingerprint, policy, fence=None):
    row = db.execute('SELECT * FROM own_approvals WHERE id=?', (identifier,)).fetchone()
    if row is None or row['body_digest'] != fingerprint:
        fail()
    body = stored(row['body'], row['body_digest'])
    manifest = legacy._manifest(db, policy)
    fields = {'schema', 'binding', 'fence', 'bundle_id', 'version', 'content_digest',
        'slots', 'apis', 'expires', 'body_attempt'}
    binding, selector = policy['binding'], policy['selector']
    if (type(body) is not dict or set(body) != fields or type(body['schema']) is not int
            or body['schema'] != 5 or body['body_attempt'] != policy
            or body['binding'] != binding or body['fence'] != row['binding_fence']
            or (fence is not None and body['fence'] != fence)
            or any(body[k] != selector[k] for k in selector) or body['slots'] != manifest['assets']
            or body['apis'] != ([] if policy['action'] == ADOPT else list(APIS))
            or not finite(row['expires']) or body['expires'] != row['expires']
            or row['manifest_digest'] != selector['content_digest']
            or type(row['cancelled']) is not int or row['cancelled'] not in (0, 1)
            or any(row[k] != binding[k] for k in ('tenant', 'principal', 'connection', 'resource'))):
        fail()
    return row


def validate_record(db, row, source_kind):
    try:
        intent = stored(row['intent'], row['intent_digest'])
        if (type(intent) is not dict or set(intent) != {'schema', 'policy', 'fence', 'approval_id', 'approval_digest'}
                or type(intent['schema']) is not int or intent['schema'] != 1
                or intent['approval_id'] != row['approval_id'] or intent['approval_digest'] != row['approval_digest']
                or type(row['ordinal']) is not int or row['ordinal'] != 4):
            fail()
        policy = intent['policy']
        root, old = validate_policy(db, policy)
        if (policy['action'] != SEND or policy['binding']['source_kind'] != source_kind
                or row['original_step_id'] != root['id'] or row['tenant'] != root['tenant']
                or row['resource'] != root['resource'] or not finite(row['created'])
                or row['created'] < max(db.execute('SELECT created FROM own_body_followups WHERE original_step_id=?',
                    (root['id'],)).fetchone()[0], root['created'])):
            fail()
        for k in ('id', 'owner', 'approval_id'):
            strict_validate(row[k], ID)
        approval_history(db, row['approval_id'], row['approval_digest'], policy, intent['fence'])
        observation = read_observation(row, policy)
        result = stored(row['result'], row['result_digest'])
        if row['state'] == 'RESULT_UNKNOWN':
            if result != {} or row['completed'] is not None:
                fail()
        elif row['state'] == 'SUCCEEDED':
            fields = {'url', 'completion_origin', 'observation_digest', 'adoption_approval_id', 'adoption_approval_digest'}
            if (type(result) is not dict or set(result) != fields or observation is None or observation['url'] is None
                    or result['url'] != observation['url'] or result['completion_origin'] != ORIGIN
                    or result['observation_digest'] != row['observation_digest']
                    or not finite(row['completed']) or row['completed'] < observation['observed_at']):
                fail()
            approved = db.execute('SELECT * FROM own_approvals WHERE id=?', (result['adoption_approval_id'],)).fetchone()
            if approved is None:
                fail()
            adoption = stored(approved['body'], approved['body_digest'])['body_attempt']
            validate_policy(db, adoption)
            approval_history(db, approved['id'], result['adoption_approval_digest'], adoption)
            if adoption['action'] == SEND:
                if approved['id'] != row['approval_id'] or adoption != policy:
                    fail()
            elif (adoption['attempt_id'] != row['id'] or adoption['owner'] != row['owner'] or adoption['intent_digest'] != row['intent_digest']
                    or adoption['observation_digest'] != row['observation_digest']):
                fail()
        else:
            fail()
        return root, old, intent, result
    except WCEError:
        raise
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def history(w, db, p, row, *, history_locators=None):
    root, old, intent, result = validate_record(db, row, p.source_kind)
    manifest, fingerprint = legacy._materials(w, db, p, root, old, history_locators=history_locators)
    w._approval(db, p, manifest, fingerprint, row['approval_id'], active=False)
    return root, old, intent, result, manifest, fingerprint


def snapshot(w, db, p, selector, request_key, draft_key, action=SEND, *, history_locators=None):
    root = w._history(db, p, request_key, history_locators=history_locators)
    if root is None or root['operation'] != 'body' or root['state'] != 'RESULT_UNKNOWN':
        raise WCEError('OWN_BODY_ATTEMPT_UNAVAILABLE')
    old, _ = w._step(db, p, root, history_locators=history_locators)
    if old['selector'] != selector:
        raise WCEError('OWN_SNAPSHOT_CHANGED')
    legacy._materials(w, db, p, root, old, history_locators=history_locators)
    policy = policy_for(db, root['id'], p.source_kind, code_scope(), draft_key, action)
    row = db.execute('SELECT * FROM own_body_attempts WHERE original_step_id=?', (root['id'],)).fetchone()
    if action == SEND:
        if row is not None:
            raise WCEError('OWN_BODY_ATTEMPT_BUDGET_EXHAUSTED')
    elif action == ADOPT:
        if row is None or row['state'] != 'RESULT_UNKNOWN':
            raise WCEError('OWN_BODY_ATTEMPT_UNAVAILABLE')
        history(w, db, p, row, history_locators=history_locators)
        observation = read_observation(row, stored(row['intent'], row['intent_digest'])['policy'])
        if observation is None or observation['url'] is None:
            raise WCEError('OWN_BODY_OBSERVATION_UNAVAILABLE')
        policy.update(attempt_id=row['id'], owner=row['owner'], intent_digest=row['intent_digest'], observation_digest=row['observation_digest'])
    validate_policy(db, policy)
    return policy


def mapping(w, db, p, original, *, history_locators=None):
    row = db.execute('SELECT * FROM own_body_attempts WHERE original_step_id=?', (original['id'],)).fetchone()
    if row is None:
        return None
    root, _, intent, result, _, _ = history(w, db, p, row, history_locators=history_locators)
    if dict(root) != dict(original):
        fail()
    if row['state'] != 'SUCCEEDED':
        return None
    return {'url': result['url']}, {'source': ORIGIN, 'attempt_id': row['id'], 'ordinal': 4,
        'original_step_id': root['id'], 'history_digest': digest(intent['policy']['history']),
        'intent_digest': row['intent_digest'], 'observation_digest': row['observation_digest'],
        'result_digest': row['result_digest']}


def view(w, db, p, row, *, history_locators=None):
    _, _, intent, result, _, _ = history(w, db, p, row, history_locators=history_locators)
    observation = read_observation(row, intent['policy'])
    return {'attempt_id': row['id'], 'original_step_id': row['original_step_id'], 'ordinal': 4,
        'maximum_total_admissions': 4, 'remaining_new_sends': 0, 'state': row['state'],
        'completion_origin': ORIGIN if result else 'UNDETERMINED',
        'original_states': ['RESULT_UNKNOWN'] * 3, 'intent_digest': row['intent_digest'],
        'result_digest': row['result_digest'], 'observation_digest': row['observation_digest'],
        'observation_state': 'QUALIFIED_V2' if observation and observation['url'] is not None else 'NO_REFERENCE',
        'response_diagnostic': observation['diagnostic'] if observation else {'reason': 'NOT_RECORDED'}}


def check_draft_key(db, p, selector, key):
    for row in db.execute('SELECT * FROM own_body_attempts WHERE tenant=? AND resource=?',
                         (p.actor.tenant_id, p.resource_id)):
        _, _, intent, _ = validate_record(db, row, p.source_kind)
        if intent['policy']['selector'] == selector and intent['policy']['draft_request_key'] != key:
            raise WCEError('OWN_BODY_ATTEMPT_DRAFT_KEY_CHANGED')


def active(w, db, p, approval_id, local=False, *, history_locators=None):
    row = db.execute('SELECT * FROM own_approvals WHERE id=?', (approval_id,)).fetchone()
    if row is None:
        raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    body = stored(row['body'], row['body_digest'])
    if type(body) is not dict or body.get('schema') != 5 or 'body_attempt' not in body:
        raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    policy = body['body_attempt']
    root, old = validate_policy(db, policy)
    manifest, fingerprint = legacy._materials(w, db, p, root, old, history_locators=history_locators)
    w._approval(db, p, manifest, fingerprint, approval_id, allow_local_adoption=local)
    if policy['candidate_scope'] != code_scope():
        raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
    return row, policy


def current(w, p, lease=None):
    w._profile(p.actor, p.connection_id, 'local.write', p)
    if lease is not None:
        w._network(p, lease, APIS[1], True)


def lock(db, p, row):
    actual = db.execute('SELECT kind,owner_id FROM own_resource_locks WHERE tenant=? AND resource=?',
        (p.actor.tenant_id, p.resource_id)).fetchone()
    if actual is None or tuple(actual) != ('body_attempt', row['id']):
        fail()


def finish(w, p, approval_id, row_id, lease=None, local_guard=None):
    if local_guard:
        local_guard()
    current(w, p, lease)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        approval, policy = active(w, db, p, approval_id, lease is None, history_locators=history_locators)
        row = db.execute('SELECT * FROM own_body_attempts WHERE id=?', (row_id,)).fetchone()
        if row is None:
            fail()
        _, _, intent, _, _, _ = history(w, db, p, row, history_locators=history_locators)
        if policy['action'] == SEND:
            if approval_id != row['approval_id'] or policy != intent['policy'] or lease is None:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        elif policy['attempt_id'] != row['id'] or policy['owner'] != row['owner'] or policy['intent_digest'] != row['intent_digest']:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if row['state'] == 'SUCCEEDED':
            return view(w, db, p, row, history_locators=history_locators)
        observation = read_observation(row, intent['policy'])
        if observation is None or observation['url'] is None:
            raise WCEError('OWN_BODY_OBSERVATION_UNAVAILABLE')
        if policy['action'] == ADOPT and policy['observation_digest'] != row['observation_digest']:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        lock(db, p, row)
        current(w, p, lease)
        result = {'url': observation['url'], 'completion_origin': ORIGIN, 'observation_digest': row['observation_digest'],
            'adoption_approval_id': approval_id, 'adoption_approval_digest': approval['body_digest']}
        changed = db.execute("UPDATE own_body_attempts SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
            "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND observation_digest=?",
            (canonical(result), digest(result), w.clock(), row['id'], row['owner'], row['intent_digest'], row['observation_digest'])).rowcount
        if changed != 1:
            fail()
        if db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? AND kind='body_attempt' AND owner_id=?",
                (p.actor.tenant_id, p.resource_id, row['id'])).rowcount != 1:
            fail()
        current(w, p, lease)
        active(w, db, p, approval_id, lease is None, history_locators=history_locators)
        validate_record(db, db.execute('SELECT * FROM own_body_attempts WHERE id=?', (row_id,)).fetchone(), p.source_kind)
        if local_guard:
            local_guard()
    if local_guard:
        local_guard()
    current(w, p, lease)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        active(w, db, p, approval_id, lease is None, history_locators=history_locators)
        return view(w, db, p, db.execute('SELECT * FROM own_body_attempts WHERE id=?', (row_id,)).fetchone(), history_locators=history_locators)


def execute(w, p, lease, approval_id):
    current(w, p, lease)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        approval, policy = active(w, db, p, approval_id, history_locators=history_locators)
        if policy['action'] != SEND:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        root, old, third, _ = legacy_history(db, policy['original_step_id'], p.source_kind)
        existing = db.execute('SELECT * FROM own_body_attempts WHERE original_step_id=?', (root['id'],)).fetchone()
        if existing is not None:
            return view(w, db, p, existing, history_locators=history_locators)
        unknowns = db.execute("SELECT id FROM own_steps WHERE tenant=? AND resource=? AND state='RESULT_UNKNOWN'",
            (p.actor.tenant_id, p.resource_id)).fetchall()
        if len(unknowns) != 1 or unknowns[0]['id'] != root['id']:
            raise WCEError('OWN_RESOURCE_RESULT_UNKNOWN')
        _, data = w._asset(db, p.binding(), policy['asset']['asset_ref'], 'body')
        request = wire.encode_upload('article_body', policy['asset']['declared_type'], data, lease.token)
        identifier, owner = 'own-body-attempt-' + uuid4().hex, uuid4().hex
        intent = {'schema': 1, 'policy': policy, 'fence': p.fence(), 'approval_id': approval_id,
                  'approval_digest': approval['body_digest']}
        current(w, p, lease)
        from .draft_group_store import check_account_writer
        check_account_writer(db, history_locators=history_locators)
        db.execute('INSERT INTO own_body_attempts(id,original_step_id,ordinal,tenant,resource,owner,approval_id,'
            'approval_digest,intent,intent_digest,state,created) VALUES(?,?,4,?,?,?,?,?,?,?,?,?)',
            (identifier, root['id'], p.actor.tenant_id, p.resource_id, owner, approval_id,
             approval['body_digest'], canonical(intent), digest(intent), 'RESULT_UNKNOWN', w.clock()))
        if db.execute("UPDATE own_resource_locks SET kind='body_attempt',owner_id=? WHERE tenant=? AND resource=? "
                "AND kind='body_followup' AND owner_id=?", (identifier, p.actor.tenant_id, p.resource_id, third['id'])).rowcount != 1:
            fail()
        from .own_body_spent import create as create_spent
        admitted = db.execute('SELECT * FROM own_body_attempts WHERE id=?', (identifier,)).fetchone()
        create_spent(db, admitted)
        # The seal and uncommitted row/lock are checked against THIS transaction
        # view before COMMIT. No new connection or resumed stack gains a sender.
        w._resource(db, p, history_locators=history_locators)
        active(w, db, p, approval_id, history_locators=history_locators)
        history(w, db, p, admitted, history_locators=history_locators)
        lock(db, p, admitted)
        current(w, p, lease)

    def guard():
        current(w, p, lease)
        with _history_transaction(w.db) as (db, history_locators):
            w._resource(db, p, history_locators=history_locators)
            active(w, db, p, approval_id, history_locators=history_locators)
            row = db.execute('SELECT * FROM own_body_attempts WHERE id=?', (identifier,)).fetchone()
            if (row is None or row['owner'] != owner or row['intent_digest'] != digest(intent)
                    or row['state'] != 'RESULT_UNKNOWN'):
                fail()
            history(w, db, p, row, history_locators=history_locators)
            lock(db, p, row)

    guard()  # Only this acknowledged admission stack reaches the sender.
    response = w._send(p, lease, request, APIS[1], True)
    inspection = inspect_response('article_body', response, lease.token,
        policy=BODY_API_REFERENCE_POLICY, production=True)
    with w.db.transaction(write=True) as db:
        row = db.execute('SELECT * FROM own_body_attempts WHERE id=?', (identifier,)).fetchone()
        validate_record(db, row, p.source_kind)
        if row['owner'] != owner or row['intent_digest'] != digest(intent) or row['state'] != 'RESULT_UNKNOWN':
            fail()
        observation = {'schema': 1, 'policy': BODY_API_REFERENCE_POLICY, 'root': root['id'], 'ordinal': 4,
            'owner': owner, 'intent_digest': digest(intent), **{k: policy[k] for k in
                ('binding', 'selector', 'asset', 'candidate_scope')}, 'observed_at': w.clock(),
            'http_status': response.status if type(response) is HTTPResponse and type(response.status) is int and 100 <= response.status <= 599 else None,
            'diagnostic': inspection.diagnostic(), 'url': inspection.reply.url if inspection.reply.classification == 'PARSED_SUCCESS' else None}
        proposed = dict(row) | {'observation': canonical(observation), 'observation_digest': digest(observation)}
        read_observation(proposed, policy)
        if stored(row['observation'], row['observation_digest']) != {}:
            fail()
        if db.execute('UPDATE own_body_attempts SET observation=?,observation_digest=? WHERE id=? AND owner=? '
                'AND intent_digest=? AND observation=?', (canonical(observation), digest(observation), identifier,
                 owner, digest(intent), '{}')).rowcount != 1:
            fail()
    guard()  # Observation is durable even if current authority was revoked.
    if inspection.reply.classification == 'PARSED_SUCCESS':
        return finish(w, p, approval_id, identifier, lease)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        return view(w, db, p, db.execute('SELECT * FROM own_body_attempts WHERE id=?', (identifier,)).fetchone(), history_locators=history_locators)


def adopt(w, p, approval_id, local_guard=None):
    current(w, p)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        _, policy = active(w, db, p, approval_id, True, history_locators=history_locators)
        if policy['action'] != ADOPT:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        identifier = policy['attempt_id']
    return finish(w, p, approval_id, identifier, local_guard=local_guard)


from .draft_group_history_context import history_transaction as _history_transaction
