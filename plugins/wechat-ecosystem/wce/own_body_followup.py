"""One separately approved body POST, with immutable safe response observation.

The original step and its spent recovery remain UNKNOWN. Only the stack whose
new admission committed may send. Adoption consumes an existing observation and
never obtains a token or performs a network request.
"""
from uuid import uuid4

from .contracts import WCEError
from .http_transport import HTTPResponse
from .own_auth import APIS, finite
from .own_body_recovery import code_scope, stored
from .prepared_contracts import DIGEST, ID, strict_validate
from .service import canonical, digest
from .upload_wire import (BODY_API_REFERENCE_POLICY, REFERENCE_COMPATIBILITY_REASONS,
    ReferenceAssessment, api_reference_reason, body_reference_reason,
    body_reference_url, validate_inspection_diagnostic)
from . import own_wire as wire

POLICY = 'BODY_URL_RESPONSE_V1'
SEND_ONCE = 'SEND_ONCE'
ADOPT_OBSERVATION_ONLY = 'ADOPT_OBSERVATION_ONLY'
ORIGIN = POLICY
API_PATH = '/cgi-bin/media/uploadimg'


def _fail():
    raise WCEError('OWN_STATE_CORRUPT')


def _policy(original, old_intent, prior, scope, action=SEND_ONCE):
    strict_validate(scope, DIGEST)
    if action not in {SEND_ONCE, ADOPT_OBSERVATION_ONLY}:
        _fail()
    return {'schema': 1, 'policy': POLICY, 'action': action,
        'candidate_scope': scope, 'maximum_new_sends': 1 if action == SEND_ONCE else 0,
        'duplicate_image_risk_accepted': True, 'binding': old_intent['binding'],
        'selector': old_intent['selector'], 'asset': old_intent['asset'],
        'original_step_id': original['id'], 'original_request_key': original['request_key'],
        'original_row_digest': digest(dict(original)),
        'prior_recovery_id': prior['id'], 'prior_recovery_digest': digest(dict(prior))}


def _parents(db, value):
    from .own_body_recovery import validate_record as validate_recovery
    if type(value) is not dict:
        _fail()
    original = db.execute('SELECT * FROM own_steps WHERE id=?',
        (value.get('original_step_id'),)).fetchone()
    prior = db.execute('SELECT * FROM own_body_recoveries WHERE id=?',
        (value.get('prior_recovery_id'),)).fetchone()
    if (original is None or prior is None or original['operation'] != 'body'
            or original['state'] != 'RESULT_UNKNOWN' or prior['state'] != 'RESULT_UNKNOWN'
            or prior['original_step_id'] != original['id']):
        _fail()
    old, old_intent, _, _ = validate_recovery(db, prior,
        stored(original['intent'], original['intent_digest'])['binding']['source_kind'])
    if dict(old) != dict(original):
        _fail()
    return original, old_intent, prior


def validate_policy(db, value):
    """Validate historical pins; an ADOPT policy never replaces the send intent."""
    try:
        original, old_intent, prior = _parents(db, value)
        action = value.get('action')
        expected = _policy(original, old_intent, prior, value.get('candidate_scope'), action)
        if action == ADOPT_OBSERVATION_ONLY:
            followup = db.execute('SELECT * FROM own_body_followups WHERE id=?',
                (value.get('followup_id'),)).fetchone()
            if followup is None or followup['original_step_id'] != original['id']:
                _fail()
            send_intent = stored(followup['intent'], followup['intent_digest'])
            send_policy = send_intent['policy']
            if type(send_policy) is not dict or send_policy.get('action') != SEND_ONCE:
                _fail()
            send_original, _ = validate_policy(db, send_policy)
            observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
                (followup['id'],)).fetchone()
            if (send_policy['action'] != SEND_ONCE or send_original['id'] != original['id']
                    or followup['prior_recovery_id'] != prior['id'] or observation is None):
                _fail()
            payload = _observation(db, followup, send_policy, observation)
            if payload['url'] is None or payload['schema'] != 1:
                _fail()
            expected.update(followup_id=followup['id'], intent_digest=followup['intent_digest'],
                observation_digest=observation['payload_digest'])
        if (value != expected or type(value.get('schema')) is not int
                or type(value.get('maximum_new_sends')) is not int
                or value.get('duplicate_image_risk_accepted') is not True):
            _fail()
        return original, old_intent
    except WCEError:
        raise
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def _manifest(db, policy):
    selector = policy['selector']
    row = db.execute('SELECT * FROM own_articles WHERE bundle=? AND version=?',
        (selector['bundle_id'], selector['version'])).fetchone()
    if (row is None or row['digest'] != selector['content_digest']
            or row['binding'] != canonical(policy['binding'])):
        _fail()
    from .own_group_json import read as read_manifest
    manifest = read_manifest(row['manifest'], row['digest'])
    if (manifest['binding'] != policy['binding'] or manifest['bundle_id'] != selector['bundle_id']
            or manifest['version'] != selector['version'] or policy['asset'] not in manifest['assets']):
        _fail()
    return manifest


def _approval_history(db, identifier, fingerprint, policy, fence=None):
    row = db.execute('SELECT * FROM own_approvals WHERE id=?', (identifier,)).fetchone()
    if row is None or row['body_digest'] != fingerprint:
        _fail()
    body = stored(row['body'], row['body_digest'])
    fields = {'schema', 'binding', 'fence', 'bundle_id', 'version', 'content_digest',
        'slots', 'apis', 'expires', 'body_followup'}
    binding, selector = policy['binding'], policy['selector']
    manifest = _manifest(db, policy)
    if (type(body) is not dict or set(body) != fields or type(body['schema']) is not int
            or body['schema'] != 4 or body['body_followup'] != policy
            or body['binding'] != binding or body['fence'] != row['binding_fence']
            or (fence is not None and body['fence'] != fence)
            or any(body[k] != selector[k] for k in ('bundle_id', 'version', 'content_digest'))
            or body['slots'] != manifest['assets']
            or body['apis'] != ([] if policy['action'] == ADOPT_OBSERVATION_ONLY else list(APIS))
            or not finite(row['expires']) or body['expires'] != row['expires']
            or type(row['cancelled']) is not int or row['cancelled'] not in (0, 1)
            or row['manifest_digest'] != selector['content_digest']
            or any(row[k] != binding[k] for k in ('tenant', 'principal', 'connection', 'resource'))):
        _fail()
    return row


def _observation(db, followup, policy, row=None):
    row = row if row is not None else db.execute(
        'SELECT * FROM own_body_observations WHERE followup_id=?', (followup['id'],)).fetchone()
    if row is None:
        return None
    payload = stored(row['payload'], row['payload_digest'])
    fields = {'schema', 'policy', 'candidate_scope', 'binding', 'selector', 'asset',
        'original_step_id', 'original_row_digest', 'prior_recovery_id',
        'prior_recovery_digest', 'api_method', 'api_path', 'diagnostic',
        'code_form', 'http_status', 'url', 'observed_at'}
    schema = payload.get('schema') if type(payload) is dict else None
    if schema == 2:
        fields |= {'reference_policy', 'reference_state', 'reference_reason'}
    if (row['followup_id'] != followup['id'] or row['owner'] != followup['owner']
            or row['intent_digest'] != followup['intent_digest']
            or not finite(row['observed_at']) or row['observed_at'] < followup['created']
            or type(payload) is not dict or set(payload) != fields
            or type(payload['schema']) is not int or payload['schema'] not in (1, 2)
            or not finite(payload['observed_at']) or payload['observed_at'] != row['observed_at']
            or payload['policy'] != POLICY or payload['api_method'] != 'POST'
            or payload['api_path'] != API_PATH):
        _fail()
    for key in ('candidate_scope', 'binding', 'selector', 'asset', 'original_step_id',
            'original_row_digest', 'prior_recovery_id', 'prior_recovery_digest'):
        if payload[key] != policy[key]:
            _fail()
    diagnostic = validate_inspection_diagnostic(payload['diagnostic'])
    status = payload['http_status']
    if (payload['code_form'] != diagnostic['code_form']
            or (status is not None and (type(status) is not int or not 100 <= status <= 599))):
        _fail()
    if schema == 2:
        trace = dict(diagnostic['stages'])
        if (payload['reference_policy'] != BODY_API_REFERENCE_POLICY
                or payload['reference_state'] != 'QUARANTINED'
                or payload['reference_reason'] != 'REFERENCE_SAFE'
                or diagnostic['schema'] != 3 or diagnostic['reference'] != {
                    'policy': BODY_API_REFERENCE_POLICY, 'reason': 'REFERENCE_SAFE'}
                or diagnostic['reason'] not in REFERENCE_COMPATIBILITY_REASONS
                or trace['production'] != 'FAIL'
                or any(state != 'PASS' for stage, state in diagnostic['stages'] if stage != 'production')
                or payload['code_form'] not in {'ABSENT', 'ZERO'}
                or type(status) is not int or not 200 <= status < 300
                or payload['url'] is None or api_reference_reason(payload['url']) is not None
                or body_reference_reason(payload['url']) != diagnostic['reason']):
            _fail()
    elif payload['url'] is not None:
        if (not body_reference_url(payload['url']) or diagnostic['reason'] != 'PARSED_SUCCESS'
                or payload['code_form'] not in {'ABSENT', 'ZERO'}
                or any(stage[1] != 'PASS' for stage in diagnostic['stages'])
                or type(status) is not int or not 200 <= status < 300):
            _fail()
    elif diagnostic['reason'] == 'PARSED_SUCCESS':
        _fail()
    return payload


def validate_record(db, row, source_kind):
    """Validate durable history independently of expired leases or old fences."""
    try:
        intent = stored(row['intent'], row['intent_digest'])
        if (type(intent) is not dict or set(intent) != {
                'schema', 'policy', 'fence', 'approval_id', 'approval_digest'}
                or type(intent['schema']) is not int or intent['schema'] != 1
                or intent['approval_id'] != row['approval_id']
                or intent['approval_digest'] != row['approval_digest']):
            _fail()
        policy = intent['policy']
        original, old_intent = validate_policy(db, policy)
        prior = db.execute('SELECT * FROM own_body_recoveries WHERE id=?',
            (policy['prior_recovery_id'],)).fetchone()
        if (policy['action'] != SEND_ONCE or row['original_step_id'] != original['id']
                or row['prior_recovery_id'] != prior['id']
                or row['tenant'] != original['tenant'] or row['resource'] != original['resource']
                or policy['binding']['source_kind'] != source_kind
                or not finite(row['created']) or row['created'] < prior['created']):
            _fail()
        for key in ('id', 'owner', 'approval_id'):
            strict_validate(row[key], ID)
        _approval_history(db, row['approval_id'], row['approval_digest'], policy, intent['fence'])
        observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
            (row['id'],)).fetchone()
        payload = _observation(db, row, policy, observation)
        result = stored(row['result'], row['result_digest'])
        if row['state'] == 'RESULT_UNKNOWN':
            if result != {} or row['completed'] is not None:
                _fail()
        elif row['state'] == 'SUCCEEDED':
            if (type(result) is not dict or set(result) != {'url', 'completion_origin',
                    'observation_digest', 'adoption_approval_id', 'adoption_approval_digest'}
                    or payload is None or payload['schema'] != 1 or payload['url'] is None or result['url'] != payload['url']
                    or result['completion_origin'] != ORIGIN
                    or result['observation_digest'] != observation['payload_digest']
                    or not finite(row['completed']) or row['completed'] < observation['observed_at']):
                _fail()
            adopted = db.execute('SELECT * FROM own_approvals WHERE id=?',
                (result['adoption_approval_id'],)).fetchone()
            if adopted is None:
                _fail()
            adoption_policy = stored(adopted['body'], adopted['body_digest'])['body_followup']
            validate_policy(db, adoption_policy)
            _approval_history(db, adopted['id'], result['adoption_approval_digest'], adoption_policy)
            if adoption_policy['action'] == SEND_ONCE:
                if adopted['id'] != row['approval_id'] or adoption_policy != policy:
                    _fail()
            elif (adoption_policy['followup_id'] != row['id']
                    or adoption_policy['intent_digest'] != row['intent_digest']
                    or adoption_policy['observation_digest'] != observation['payload_digest']):
                _fail()
        else:
            _fail()
        return original, old_intent, intent, result
    except WCEError:
        raise
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def _materials(w, db, p, original, old_intent, *, history_locators=None):
    """Verify the old cover proof without recursing through this body mapping."""
    from .own_step_history import validate_original_upload_in
    validate_original_upload_in(w, db, p, original, history_locators=history_locators)
    selector = old_intent['selector']
    manifest, content_digest = w._bundle(db, p, selector['bundle_id'], selector['version'])
    if content_digest != selector['content_digest']:
        _fail()
    for asset in manifest['assets']:
        if asset == old_intent['asset']:
            w._asset(db, p.binding(), asset['asset_ref'], 'body')
            continue
        operation = 'cover' if asset['slot'] == 'cover' else 'body'
        row = db.execute('SELECT * FROM own_steps WHERE target=?',
            (w._target(p, content_digest, operation, asset['slot']),)).fetchone()
        if row is None or row['state'] != 'SUCCEEDED':
            raise WCEError('OWN_UPLOADS_INCOMPLETE')
        validate_original_upload_in(w, db, p, row, history_locators=history_locators)
    return manifest, content_digest


def _history(w, db, p, row, *, history_locators=None):
    original, old_intent, intent, result = validate_record(db, row, p.source_kind)
    manifest, content_digest = _materials(w, db, p, original, old_intent, history_locators=history_locators)
    w._approval(db, p, manifest, content_digest, row['approval_id'], active=False)
    return original, old_intent, intent, result, manifest, content_digest


def snapshot(w, db, p, selector, request_key, action=SEND_ONCE, *, history_locators=None):
    if action not in {SEND_ONCE, ADOPT_OBSERVATION_ONLY}:
        raise WCEError('OWN_BODY_FOLLOWUP_UNAVAILABLE')
    original = w._history(db, p, request_key, history_locators=history_locators)
    if original is None or original['operation'] != 'body' or original['state'] != 'RESULT_UNKNOWN':
        raise WCEError('OWN_BODY_FOLLOWUP_UNAVAILABLE')
    old_intent, _ = w._step(db, p, original, history_locators=history_locators)
    if old_intent['selector'] != selector:
        raise WCEError('OWN_SNAPSHOT_CHANGED')
    prior = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?',
        (original['id'],)).fetchone()
    if prior is None or prior['state'] != 'RESULT_UNKNOWN':
        raise WCEError('OWN_BODY_FOLLOWUP_UNAVAILABLE')
    policy = _policy(original, old_intent, prior, code_scope(), action)
    _materials(w, db, p, original, old_intent, history_locators=history_locators)
    row = db.execute('SELECT * FROM own_body_followups WHERE original_step_id=?',
        (original['id'],)).fetchone()
    if action == SEND_ONCE:
        validate_policy(db, policy)
        if row is not None:
            raise WCEError('OWN_BODY_FOLLOWUP_ALREADY_ADMITTED')
    else:
        if row is None or row['state'] != 'RESULT_UNKNOWN':
            raise WCEError('OWN_BODY_FOLLOWUP_UNAVAILABLE')
        _history(w, db, p, row, history_locators=history_locators)
        observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
            (row['id'],)).fetchone()
        payload = _observation(db, row, stored(row['intent'], row['intent_digest'])['policy'], observation)
        if payload is None or payload['schema'] != 1 or payload['url'] is None:
            raise WCEError('OWN_BODY_OBSERVATION_UNAVAILABLE')
        policy.update(followup_id=row['id'], intent_digest=row['intent_digest'],
            observation_digest=observation['payload_digest'])
        validate_policy(db, policy)
    return policy


def mapping(w, db, p, original, *, history_locators=None):
    row = db.execute('SELECT * FROM own_body_followups WHERE original_step_id=?',
        (original['id'],)).fetchone()
    if row is None:
        return None
    actual, _, intent, result, _, _ = _history(w, db, p, row, history_locators=history_locators)
    if dict(actual) != dict(original):
        _fail()
    if row['state'] != 'SUCCEEDED':
        return None
    policy = intent['policy']
    return {'url': result['url']}, {'source': ORIGIN, 'followup_id': row['id'],
        'original_step_id': original['id'], 'original_row_digest': policy['original_row_digest'],
        'prior_recovery_id': policy['prior_recovery_id'],
        'prior_recovery_digest': policy['prior_recovery_digest'],
        'intent_digest': row['intent_digest'], 'observation_digest': result['observation_digest'],
        'result_digest': row['result_digest']}


def view(w, db, p, row, *, history_locators=None):
    original, _, _, result, _, _ = _history(w, db, p, row, history_locators=history_locators)
    observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
        (row['id'],)).fetchone()
    payload = _observation(db, row, stored(row['intent'], row['intent_digest'])['policy'], observation)
    return {'followup_id': row['id'], 'original_step_id': original['id'],
        'prior_recovery_id': row['prior_recovery_id'], 'original_state': 'RESULT_UNKNOWN',
        'prior_recovery_state': 'RESULT_UNKNOWN', 'state': row['state'],
        'completion_origin': ORIGIN if result else 'UNDETERMINED',
        'intent_digest': row['intent_digest'], 'result_digest': row['result_digest'],
        'observation_digest': observation['payload_digest'] if observation is not None else None,
        'observation_state': ('QUARANTINED' if payload is not None and payload['schema'] == 2 else
            'QUALIFIED' if payload is not None and payload['url'] is not None else 'NO_REFERENCE'),
        'response_diagnostic': payload['diagnostic'] if payload is not None else {'reason': 'NOT_RECORDED'}}


def _current(w, p, lease=None):
    w._profile(p.actor, p.connection_id, 'local.write', p)
    if lease is not None:
        w._network(p, lease, APIS[1], True)


def _active_approval(w, db, p, approval_id, allow_local_adoption=False, *, history_locators=None):
    approval = db.execute('SELECT * FROM own_approvals WHERE id=?', (approval_id,)).fetchone()
    if approval is None:
        raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    body = stored(approval['body'], approval['body_digest'])
    if type(body) is not dict or body.get('schema') != 4 or 'body_followup' not in body:
        raise WCEError('OWN_APPROVAL_UNAVAILABLE')
    policy = body['body_followup']
    original, old_intent = validate_policy(db, policy)
    manifest, content_digest = _materials(w, db, p, original, old_intent, history_locators=history_locators)
    if allow_local_adoption:
        w._approval(db, p, manifest, content_digest, approval_id, allow_local_adoption=True)
    else:
        w._approval(db, p, manifest, content_digest, approval_id)
    if policy['candidate_scope'] != code_scope():
        raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
    return approval, policy, original, old_intent


def _lock(db, p, row):
    lock = db.execute('SELECT * FROM own_resource_locks WHERE tenant=? AND resource=?',
        (p.actor.tenant_id, p.resource_id)).fetchone()
    if lock is None or lock['kind'] != 'body_followup' or lock['owner_id'] != row['id']:
        _fail()


def _finish(w, p, approval_id, row_id, lease=None, local_guard=None):
    if local_guard is not None:
        local_guard()
    _current(w, p, lease)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        approval, adoption_policy, _, _ = _active_approval(w, db, p, approval_id,
            allow_local_adoption=lease is None, history_locators=history_locators)
        row = db.execute('SELECT * FROM own_body_followups WHERE id=?', (row_id,)).fetchone()
        if row is None:
            raise WCEError('OWN_BODY_FOLLOWUP_UNAVAILABLE')
        _, _, intent, _, _, _ = _history(w, db, p, row, history_locators=history_locators)
        if adoption_policy['action'] == SEND_ONCE:
            if approval_id != row['approval_id'] or adoption_policy != intent['policy'] or lease is None:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        elif (adoption_policy['followup_id'] != row['id']
                or adoption_policy['intent_digest'] != row['intent_digest']):
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if row['state'] == 'SUCCEEDED':
            return view(w, db, p, row, history_locators=history_locators)
        observation = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
            (row['id'],)).fetchone()
        payload = _observation(db, row, intent['policy'], observation)
        if payload is None or payload['schema'] != 1 or payload['url'] is None:
            raise WCEError('OWN_BODY_OBSERVATION_UNAVAILABLE')
        if (adoption_policy['action'] == ADOPT_OBSERVATION_ONLY
                and adoption_policy['observation_digest'] != observation['payload_digest']):
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        _lock(db, p, row)
        _current(w, p, lease)
        result = {'url': payload['url'], 'completion_origin': ORIGIN,
            'observation_digest': observation['payload_digest'],
            'adoption_approval_id': approval['id'], 'adoption_approval_digest': approval['body_digest']}
        changed = db.execute("UPDATE own_body_followups SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
            "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
            (canonical(result), digest(result), w.clock(), row['id'], row['owner'],
             row['intent_digest'], row['approval_digest'])).rowcount
        if changed != 1:
            _fail()
        changed = db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? "
            "AND kind='body_followup' AND owner_id=?",
            (p.actor.tenant_id, p.resource_id, row['id'])).rowcount
        if changed != 1:
            _fail()
        _current(w, p, lease)
        _active_approval(w, db, p, approval_id, allow_local_adoption=lease is None, history_locators=history_locators)
        completed = db.execute('SELECT * FROM own_body_followups WHERE id=?', (row['id'],)).fetchone()
        validate_record(db, completed, p.source_kind)
        if local_guard is not None:
            local_guard()
    # A release failure cannot undo a committed success or delete a later owner.
    if local_guard is not None:
        local_guard()
    _current(w, p, lease)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        _active_approval(w, db, p, approval_id, allow_local_adoption=lease is None, history_locators=history_locators)
        row = db.execute('SELECT * FROM own_body_followups WHERE id=?', (row_id,)).fetchone()
        return view(w, db, p, row, history_locators=history_locators)


def _capture(w, row_id, owner, intent_digest, inspection, response):
    """Append only this admitted response, without reviving an expired grant."""
    diagnostic = inspection.diagnostic()
    validate_inspection_diagnostic(diagnostic)
    url = inspection.reply.url if inspection.reply.classification == 'PARSED_SUCCESS' else None
    assessment = inspection.reference
    quarantine = (inspection.reason in REFERENCE_COMPATIBILITY_REASONS
        and all(state == ('FAIL' if stage == 'production' else 'PASS')
                for stage, state in inspection.stages)
        and type(assessment) is ReferenceAssessment
        and assessment.policy == BODY_API_REFERENCE_POLICY
        and assessment.reason == 'REFERENCE_SAFE' and assessment.url is not None)
    if quarantine:
        url = assessment.url
    status = response.status if type(response) is HTTPResponse else None
    with w.db.transaction(write=True) as db:
        row = db.execute('SELECT * FROM own_body_followups WHERE id=?', (row_id,)).fetchone()
        if (row is None or row['owner'] != owner or row['intent_digest'] != intent_digest
                or row['state'] != 'RESULT_UNKNOWN'):
            _fail()
        _, _, intent, _ = validate_record(db, row,
            stored(row['intent'], row['intent_digest'])['policy']['binding']['source_kind'])
        policy = intent['policy']
        payload = {key: policy[key] for key in ('candidate_scope', 'binding', 'selector', 'asset',
            'original_step_id', 'original_row_digest', 'prior_recovery_id', 'prior_recovery_digest')}
        observed_at = w.clock()
        payload.update(schema=1, policy=POLICY, api_method='POST', api_path=API_PATH, observed_at=observed_at,
            diagnostic=diagnostic, code_form=inspection.code_form,
            http_status=status if type(status) is int and 100 <= status <= 599 else None, url=url)
        if quarantine:
            payload.update(schema=2, reference_policy=assessment.policy,
                reference_state='QUARANTINED', reference_reason=assessment.reason)
        proposed = {'followup_id': row_id, 'owner': owner, 'intent_digest': intent_digest,
            'payload': canonical(payload), 'payload_digest': digest(payload), 'observed_at': observed_at}
        _observation(db, row, policy, proposed)
        existing = db.execute('SELECT * FROM own_body_observations WHERE followup_id=?',
            (row_id,)).fetchone()
        if existing is not None:
            if any(existing[key] != proposed[key] for key in (
                    'owner', 'intent_digest', 'payload', 'payload_digest')):
                _fail()
            _observation(db, row, policy, existing)
        else:
            db.execute('INSERT INTO own_body_observations VALUES(?,?,?,?,?,?)',
                (row_id, owner, intent_digest, proposed['payload'], proposed['payload_digest'], observed_at))


def execute(w, p, lease, approval_id):
    _current(w, p, lease)
    with _history_transaction(w.db, write=True) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        approval, policy, original, old_intent = _active_approval(w, db, p, approval_id, history_locators=history_locators)
        if policy['action'] != SEND_ONCE:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        prior = db.execute('SELECT * FROM own_body_recoveries WHERE id=?',
            (policy['prior_recovery_id'],)).fetchone()
        existing = db.execute('SELECT * FROM own_body_followups WHERE original_step_id=?',
            (original['id'],)).fetchone()
        if existing is not None:
            return view(w, db, p, existing, history_locators=history_locators)
        unknowns = db.execute("SELECT id FROM own_steps WHERE tenant=? AND resource=? AND state='RESULT_UNKNOWN'",
            (p.actor.tenant_id, p.resource_id)).fetchall()
        if len(unknowns) != 1 or unknowns[0]['id'] != original['id']:
            raise WCEError('OWN_RESOURCE_RESULT_UNKNOWN')
        _, data = w._asset(db, p.binding(), policy['asset']['asset_ref'], 'body')
        request = wire.encode_upload('article_body', policy['asset']['declared_type'], data, lease.token)
        intent = {'schema': 1, 'policy': policy, 'fence': p.fence(),
            'approval_id': approval_id, 'approval_digest': approval['body_digest']}
        identifier, owner = 'own-body-followup-' + uuid4().hex, uuid4().hex
        _current(w, p, lease)
        from .draft_group_store import check_account_writer
        check_account_writer(db, history_locators=history_locators)
        db.execute('INSERT INTO own_body_followups(id,original_step_id,prior_recovery_id,tenant,resource,'
            'owner,approval_id,approval_digest,intent,intent_digest,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (identifier, original['id'], prior['id'], p.actor.tenant_id, p.resource_id, owner,
             approval_id, approval['body_digest'], canonical(intent), digest(intent), 'RESULT_UNKNOWN', w.clock()))
        changed = db.execute("UPDATE own_resource_locks SET kind='body_followup',owner_id=? "
            "WHERE tenant=? AND resource=? AND kind='recovery' AND owner_id=?",
            (identifier, p.actor.tenant_id, p.resource_id, prior['id'])).rowcount
        if changed != 1:
            _fail()

    def guard():
        _current(w, p, lease)
        with _history_transaction(w.db) as (db, history_locators):
            w._resource(db, p, history_locators=history_locators)
            _active_approval(w, db, p, approval_id, history_locators=history_locators)
            row = db.execute('SELECT * FROM own_body_followups WHERE id=?', (identifier,)).fetchone()
            if (row is None or row['owner'] != owner or row['intent_digest'] != digest(intent)
                    or row['state'] != 'RESULT_UNKNOWN'):
                _fail()
            _history(w, db, p, row, history_locators=history_locators)
            _lock(db, p, row)

    # A failed/unknown admission COMMIT never reaches the dispatch stack.
    guard()
    response = w._send(p, lease, request, APIS[1], True)
    inspection = wire.inspect_body_response(response, lease.token)
    # Persist safe facts before current authorization can reject the response.
    _capture(w, identifier, owner, digest(intent), inspection, response)
    guard()
    if inspection.reply.classification == 'PARSED_SUCCESS':
        return _finish(w, p, approval_id, identifier, lease)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        row = db.execute('SELECT * FROM own_body_followups WHERE id=?', (identifier,)).fetchone()
        return view(w, db, p, row, history_locators=history_locators)


def adopt(w, p, approval_id, local_guard=None):
    """Pure local adoption: no broker, token acquisition, sender or CDN access."""
    _current(w, p)
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        _, policy, _, _ = _active_approval(w, db, p, approval_id, allow_local_adoption=True, history_locators=history_locators)
        if policy['action'] != ADOPT_OBSERVATION_ONLY:
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        identifier = policy['followup_id']
    return _finish(w, p, approval_id, identifier, local_guard=local_guard)


from .draft_group_history_context import history_transaction as _history_transaction
