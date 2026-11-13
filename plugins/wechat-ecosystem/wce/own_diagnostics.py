"""Bounded write-response diagnostics, never raw HTTP or credential data."""
import json
from hashlib import sha256

from .contracts import WCEError
from .http_transport import HTTPResponse, TransportFailure, valid_transport_failure
from .service import canonical, digest
from .upload_wire import RESPONSE_REASONS, ResponseInspection, validate_inspection_diagnostic
from .own_draft_wire import REASONS as DRAFT_REASONS, reference_valid

REASONS = frozenset({'PARSED_SUCCESS', 'PLATFORM_ERROR', 'TRANSPORT_UNDETERMINED',
    'NON_SUCCESS_HTTP', 'RESPONSE_SECRET_REFLECTION', 'INVALID_JSON_SHAPE',
    'INVALID_IMAGE_RESPONSE', 'INVALID_MEDIA_IDENTIFIER', 'INVALID_JSON_OR_RESPONSE',
    'RESPONSE_UNDETERMINED'}) | RESPONSE_REASONS | DRAFT_REASONS


def readback_comparison(expected, actual):
    """Fixed comparison facts only; no article values or response fragments.

    The caller retains its original full-dictionary equality decision. Lengths
    count Unicode code points and saturate; they are never acceptance criteria.
    """
    fields = {'title': 'title', 'content': 'content', 'cover': 'thumb_media_id'}
    required = set(fields.values())
    available = all(type(value) is dict and set(value) == required
                    and all(type(value[key]) is str for key in required)
                    for value in (expected, actual))
    limit = 1_000_000
    result = {'schema': 1, 'state': 'COMPARED' if available else 'UNAVAILABLE',
              'length_unit': 'UNICODE_CODE_POINTS_SATURATED', 'length_limit': limit}
    for label, key in fields.items():
        result[label + '_equal'] = expected[key] == actual[key] if available else None
        for side, value in (('expected', expected), ('actual', actual)):
            result[label + '_' + side + '_chars'] = (
                min(len(value[key]), limit) if available else None)
    return result


def projection(reply, response):
    if type(response) is TransportFailure:
        if reply.result is not None:
            raise WCEError('OWN_STATE_CORRUPT')
        value = {'schema': 4, 'reason': 'TRANSPORT_UNDETERMINED',
            'http_status': response.http_status, 'wechat_code': None,
            'transport_failure': {'stage': response.stage, 'kind': response.kind}}
        validate(value)
        return value
    reason = ('PARSED_SUCCESS' if reply.result is not None else
              'PLATFORM_ERROR' if type(reply.error_code) is int and reply.error_code != 0 else reply.diagnostic)
    status = response.status if type(response) is HTTPResponse else None
    code = reply.error_code
    value = {'schema': 1, 'reason': reason if reason in REASONS else 'RESPONSE_UNDETERMINED',
             'http_status': status if type(status) is int and 100 <= status <= 599 else None,
             'wechat_code': code if type(code) is int and -(2**31) <= code < 2**31 and code != 0 else None}
    if type(reply.inspection) is ResponseInspection:
        value.update(schema=2, inspection=reply.inspection.diagnostic())
    validate(value)
    return value


def validate(value):
    if (type(value) is not dict or set(value) != ({'schema', 'reason', 'http_status', 'wechat_code'} |
                ({'inspection'} if value.get('schema') == 2 else {'draft_observation'} if value.get('schema') == 3 else {'transport_failure'} if value.get('schema') == 4 else set()))
            or type(value['schema']) is not int or value['schema'] not in (1, 2, 3, 4)
            or type(value['reason']) is not str or value['reason'] not in REASONS
            or (value['http_status'] is not None and
                (type(value['http_status']) is not int or not 100 <= value['http_status'] <= 599))
            or (value['wechat_code'] is not None and
                (type(value['wechat_code']) is not int or not -(2**31) <= value['wechat_code'] < 2**31
                 or value['wechat_code'] == 0))):
        raise WCEError('OWN_STATE_CORRUPT')
    if value['schema'] == 4:
        failure = value['transport_failure']
        if (value['reason'] != 'TRANSPORT_UNDETERMINED' or value['wechat_code'] is not None
                or type(failure) is not dict or set(failure) != {'stage', 'kind'}
                or not valid_transport_failure(failure['stage'], failure['kind'], value['http_status'])):
            raise WCEError('OWN_STATE_CORRUPT')
    if value['schema'] == 2:
        validate_inspection_diagnostic(value['inspection'])
        if value['inspection']['reason'] != value['reason']:
            raise WCEError('OWN_STATE_CORRUPT')
    if value['schema'] == 3:
        observation = value['draft_observation']
        if (value['reason'] != 'PARSED_SUCCESS' or type(observation) is not dict
                or set(observation) != {'policy', 'reference'}
                or observation['policy'] != 'DRAFT_JSON_REFERENCE_V1'
                or not reference_valid(observation['reference'], True)):
            raise WCEError('OWN_STATE_CORRUPT')
    return value


def record(workflow, row, reply, response):
    """One insert after a send; diagnostic failure never permits a replay."""
    value = projection(reply, response)
    if row['operation'] == 'add' and reply.result is not None:
        # Qualified response data is durable before post-send authority checks;
        # this observation alone never changes the original business outcome.
        value.update(schema=3, draft_observation={
            'policy': 'DRAFT_JSON_REFERENCE_V1', 'reference': reply.result['reference']})
        validate(value)
    try:
        with workflow.db.transaction(write=True) as db:
            current = db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone()
            if current is None or any(current[k] != row[k] for k in ('owner', 'intent_digest')):
                raise WCEError('OWN_STATE_CORRUPT')
            db.execute('INSERT INTO own_step_diagnostics VALUES(?,?,?,?,?)',
                (row['id'], row['owner'], row['intent_digest'], canonical(value), digest(value)))
    except Exception:
        # Absence is reported as NOT_RECORDED, never guessed from status.
        return False
    return True


def read(db, row):
    r = db.execute('SELECT * FROM own_step_diagnostics WHERE step_id=?', (row['id'],)).fetchone()
    if r is None:
        return {'reason': 'NOT_RECORDED'}
    try:
        value = json.loads(r['payload'])
        if (r['owner'] != row['owner'] or r['intent_digest'] != row['intent_digest']
                or canonical(value) != r['payload'] or digest(value) != r['payload_digest']):
            raise ValueError()
        validate(value)
        if value['schema'] == 3:
            value = dict(value)
            observation = value.pop('draft_observation')
            value.update(schema=1, qualified_reference_observation=True,
                         reference_digest=digest(observation['reference']))
        return value
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None
