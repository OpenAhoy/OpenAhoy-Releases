"""Explicit restoration contract, independent of the ordinary draft delegation."""
from .publication_contract import exact, strict_json
from .contracts import WCEError
from .service import digest

POLICY = 'KNOWN_SUCCEEDED_REMOVED_DRAFT_RESTORE_V1'
ORIGIN = 'KNOWN_REMOVED_DRAFT_NEW_INTENT_RESPONSE_V1'
CONTRACT = {'schema': 1, 'policy': POLICY, 'parent_state': 'SUCCEEDED',
    'clear_source': 'TRUSTED_HUMAN_REVIEW', 'clear_order': 'ALL_RELATED_SUCCESSES_BEFORE_CLEAR_WINDOW', 'new_intent': True,
    'old_result_changed': False, 'unknown_replay': False,
    'media': 'EXACT_SAME_ACCOUNT_PARENT_PROOFS', 'new_uploads': 0,
    'per_grant_save_attempts': 1, 'per_grant_read_attempts': 5,
    'nonvisual_diagnostic': 'PURE_CURRENT_GET_NO_EXTRA_READ_V1',
    'metadata_reconcile': 'CAPTURED_ORIGINAL_RESPONSE_ONLY', 'readback': 'INDEPENDENT_NEW_REFERENCE',
    'public_publication': False, 'mass': False}
V1_CONTRACT = CONTRACT
V1_CONTRACT_SHA = digest(V1_CONTRACT)
V1_POLICY = POLICY
CONTRACT = dict(V1_CONTRACT, schema=2, policy='KNOWN_SUCCEEDED_REMOVED_DRAFT_RESTORE_COMMENTS_V2',
                restore_metadata='RESTORE_COMMENT_DEFAULTS_1_0_V1', original_payload_immutable=True)
POLICY = CONTRACT['policy']
CONTRACT_SHA = digest(CONTRACT)
SUPPORTED_CONTRACTS = (V1_CONTRACT_SHA, CONTRACT_SHA)
EMPTY = digest({})


def fail(code='DRAFT_RESTORE_HOLD'):
    raise WCEError(code)


def stored(raw, checksum):
    if type(raw) is not str or type(checksum) is not str:
        fail()
    value = strict_json(raw.encode(), 2 * 1024 * 1024)
    if digest(value) != checksum:
        fail()
    return value


def parent_pin(row):
    # Independent readback may evolve; the original write receipt never does.
    keys = ('id','tenant','principal','connection','resource','request_key','operation',
            'slot','manifest_digest','target','approval_id','approval_digest',
            'intent_digest','owner','state','result_digest','created','completed')
    return digest({key: row[key] for key in keys})


def clear_window(value):
    import math
    if (type(value) is not dict or set(value)!={'not_before','not_after'}
            or any(type(value[k]) not in (int,float) or not math.isfinite(value[k]) for k in value)
            or not 0 < value['not_before'] <= value['not_after']):
        fail('DRAFT_RESTORE_CLEAR_TIME_REQUIRED')
    return value


def clear_event_id(source_sha, window):
    clear_window(window)
    return 'draft-clear-'+digest({'source_sha':source_sha})


def check_clear_order(context, window):
    import math
    window=clear_window(window)
    times=[context['completed']]
    times.extend(x['completed'] for x in context['prior_restorations'])
    times.extend(x['completed'] for x in context['related_successes'])
    if any(type(t) not in (int,float) or not math.isfinite(t) or not 0 < t < window['not_before'] for t in times):
        fail('DRAFT_RESTORE_CLEAR_ORDER_UNPROVEN')
