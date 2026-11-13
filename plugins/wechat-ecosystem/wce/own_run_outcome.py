"""Engine facts for its owner; never Terminal output or an authority ticket."""
import os
import re

from .own_bootstrap_security import path_check
from .own_workflow import encoded
from .service import digest
from .own_draft_wire import REASONS as DRAFT_REASONS

PHASES = {'START', 'SNAPSHOT', 'CREDENTIAL', 'REVIEW', 'RECONCILE', 'BODY_RECOVERY', 'BODY_FOLLOWUP', 'BODY_ATTEMPT4', 'BODY_ADOPTION', 'DRAFT_RECONCILE', 'READY', 'STOPPED'}
REASONS = {'METADATA_SHAPE', 'TOTAL_BOUND', 'PAGE_LENGTH', 'PAGE_SHORT', 'TOTAL_DRIFT', 'DUPLICATE_IDS',
           'LIST_JSON', 'LIST_OBJECT', 'LIST_REFLECTION', 'LIST_KEYS', 'ITEM_OBJECT', 'ITEM_KEYS',
           'ITEM_MEDIA_ID', 'ITEM_NAME_TYPE', 'ITEM_NAME_LENGTH', 'ITEM_UPDATE_TIME',
           'ITEM_URL', 'ITEM_URL_HOST', 'ITEM_URL_PORT', 'IMAGE_MATCH_COUNTS', 'PIXEL_MATCH_COUNTS',
           'LIST_API_REJECTED', 'DRAFT_READ_FAILURE'}
LIST_COUNTS = ('offset', 'total', 'item_count', 'page_length', 'limit')
ITEM_COUNTS = ('item_index', 'extra_key_count', 'missing_key_mask', 'media_id_length', 'name_length', 'url_length')
MATCH_COUNTS = ('candidate_count', 'completed_reads', 'size_matches', 'exact_matches',
                'png_signature_count', 'jpeg_signature_count')
PIXEL_COUNTS = ('candidate_count', 'completed_reads', 'decoded_png_count', 'pixel_matches', 'byte_matches')
FIELD_TYPES = frozenset({'NULL', 'BOOL', 'INT', 'FLOAT', 'STRING', 'ARRAY', 'OBJECT', 'OTHER'})


def field_type(value):
    for kind, label in ((type(None), 'NULL'), (bool, 'BOOL'), (int, 'INT'), (float, 'FLOAT'),
                        (str, 'STRING'), (list, 'ARRAY'), (dict, 'OBJECT')):
        if type(value) is kind:
            return label
    return 'OTHER'


CODES = frozenset({
    'OWN_DRAFT_RECONCILE_STATE', 'OWN_DRAFT_RECONCILE_STORAGE',
    'OWN_DRAFT_RECONCILE_ATTEMPT_SPENT', 'OWN_DRAFT_RECONCILE_CHANGED',
    'OWN_DRAFT_RECONCILE_BUDGET', 'OWN_DRAFT_RECONCILE_API_REJECTED',
    'OWN_DRAFT_RECONCILE_INCOMPLETE_LIST', 'OWN_DRAFT_RECONCILE_INVALID_LIST',
    'OWN_DRAFT_RECONCILE_NO_UNIQUE_MATCH',

    'BOOTSTRAP_KEYCHAIN_ACCESS_DENIED',
    'BOOTSTRAP_KEYCHAIN_UNLOCK_OR_ACCESS_REQUIRED',
    'BOOTSTRAP_KEYCHAIN_ITEM_EXISTS',
    'BOOTSTRAP_BRIDGE_UNAVAILABLE',
    'BOOTSTRAP_CONFIG_EXPIRED',
    'BOOTSTRAP_CONFIG_REQUIRED',
    'BOOTSTRAP_CONFIRMATION_DENIED',
    'BOOTSTRAP_CREDENTIAL_INVALID',
    'BOOTSTRAP_ENDPOINT_CHANGED',
    'BOOTSTRAP_ENDPOINT_EXISTS',
    'BOOTSTRAP_ENDPOINT_UNAVAILABLE',
    'BOOTSTRAP_EVIDENCE_INVALID',
    'BOOTSTRAP_FRAME_LIMIT',
    'BOOTSTRAP_INVALID_CONFIG',
    'BOOTSTRAP_INVALID_INPUT',
    'BOOTSTRAP_INVALID_JSON',
    'BOOTSTRAP_IPC_DENIED',
    'BOOTSTRAP_IPC_RESULT_UNKNOWN',
    'BOOTSTRAP_KEYCHAIN_INVALID_ITEM',
    'BOOTSTRAP_KEYCHAIN_OPERATION_FAILED',
    'BOOTSTRAP_KEYCHAIN_SCOPE_CHANGED',
    'BOOTSTRAP_KEYCHAIN_UNAVAILABLE',
    'BOOTSTRAP_PATH_CHANGED',
    'BOOTSTRAP_PEER_DENIED',
    'BOOTSTRAP_PEER_UNAVAILABLE',
    'BOOTSTRAP_REVIEW_CHANGED',
    'BOOTSTRAP_REVIEW_EXPIRED',
    'BOOTSTRAP_REVIEW_INVALID',
    'BOOTSTRAP_REVIEW_UNAVAILABLE',
    'BOOTSTRAP_RUNTIME_CHANGED',
    'BOOTSTRAP_RUNTIME_INVALID',
    'BOOTSTRAP_RUN_UNDETERMINED',
    'BOOTSTRAP_SCOPE_MISMATCH',
    'BOOTSTRAP_SECRET_INPUT_DENIED',
    'BOOTSTRAP_SECRET_OUTPUT_DENIED',
    'BOOTSTRAP_SENDER_INVALID',
    'BOOTSTRAP_SOURCE_INVALID',
    'BOOTSTRAP_STOPPED',
    'BOOTSTRAP_TOKEN_ADMIN_DENIED',
    'BOOTSTRAP_TOKEN_ADMIN_PENDING',
    'BOOTSTRAP_TOKEN_EXPIRED',
    'BOOTSTRAP_TOKEN_HTTP_FAILED',
    'BOOTSTRAP_TOKEN_INVALID_RESPONSE',
    'BOOTSTRAP_TOKEN_IP_DENIED',
    'BOOTSTRAP_TOKEN_QUOTA_DENIED',
    'BOOTSTRAP_TOKEN_REJECTED',
    'BOOTSTRAP_TOKEN_RESULT_UNKNOWN',
    'BOOTSTRAP_TTY_MISMATCH',
    'BOOTSTRAP_TTY_REQUIRED',
    'BOOTSTRAP_UNSAFE_PATH',
    'OWN_ACCESS_DENIED',
    'OWN_APPROVAL_UNAVAILABLE',
    'OWN_ASSET_ROLE_MISMATCH',
    'OWN_AUTHORIZATION_CHANGED',
    'OWN_AUTHORIZATION_UNAVAILABLE',
    'OWN_CONSERVATIVE_NEWS_LIMIT',
    'OWN_HTTP_DISABLED',
    'OWN_IMAGE_LIMIT',
    'OWN_INPUT_NOT_FOUND',
    'OWN_INVALID_ARTICLE',
    'OWN_INVALID_DRAFT_WIRE',
    'OWN_INVALID_IMAGE',
    'OWN_INVALID_SLOT',
    'OWN_MULTIPART_COLLISION',
    'OWN_PLATFORM_CONDITION_UNVERIFIED',
    'OWN_PROVENANCE_MISMATCH',
    'OWN_RECONCILE_API_REJECTED',
    'OWN_RECONCILE_CHANGED',
    'OWN_RECONCILE_IMAGE_CHANGED',
    'OWN_RECONCILE_INCOMPLETE_LIST',
    'OWN_RECONCILE_INVALID_LIST',
    'OWN_RECONCILE_LIST_CHANGED',
    'OWN_RECONCILE_MEDIA_UNDETERMINED',
    'OWN_RECONCILE_NOT_UNKNOWN',
    'OWN_RECONCILE_NO_UNIQUE_CANDIDATE',
    'OWN_RECONCILE_NO_UNIQUE_MATCH',
    'OWN_RECONCILE_PROOF_EXISTS',
    'OWN_RECONCILE_PNG_UNSUPPORTED',
    'OWN_RECONCILE_READ_UNDETERMINED',
    'OWN_RESOURCE_MISMATCH',
    'OWN_RESOURCE_RESULT_UNKNOWN',
    'OWN_BODY_SPENT_UNVERIFIED', 'OWN_BODY_ATTEMPT_UNAVAILABLE',
    'OWN_BODY_ATTEMPT_BUDGET_EXHAUSTED', 'OWN_BODY_ATTEMPT_REFERENCE_EXISTS',
    'OWN_BODY_ATTEMPT_DRAFT_KEY_CHANGED',
    'OWN_BODY_FOLLOWUP_UNAVAILABLE',
    'OWN_BODY_FOLLOWUP_ALREADY_ADMITTED',
    'OWN_BODY_FOLLOWUP_RESULT_UNKNOWN', 'OWN_BODY_ATTEMPT_RESULT_UNKNOWN',
    'OWN_BODY_OBSERVATION_UNAVAILABLE',
    'OWN_BODY_RECOVERY_UNAVAILABLE',
    'OWN_BODY_RECOVERY_ALREADY_ADMITTED',
    'OWN_BODY_RECOVERY_RESULT_UNKNOWN',
    'OWN_RECOVERY_CANDIDATE_CHANGED',
    'OWN_SNAPSHOT_CHANGED',
    'OWN_STATE_CORRUPT',
    'OWN_STATE_UNVERIFIED',
    'OWN_STEP_NOT_FOUND',
    'OWN_STEP_ORDER',
    'OWN_TOKEN_UNAVAILABLE',
    'OWN_UNCONFIGURED',
    'OWN_UPLOADS_INCOMPLETE',
    'OWN_VERSION_CONFLICT',
}) | DRAFT_REASONS | frozenset({'TRANSPORT_UNDETERMINED', 'NON_SUCCESS_HTTP',
    'RESPONSE_SECRET_REFLECTION', 'INVALID_JSON_SHAPE'})


def safe_code(code):
    return code if type(code) is str and code in CODES else 'BOOTSTRAP_RUN_UNDETERMINED'


def safe_counts(facts):
    if (type(facts) is not dict or type(facts.get('reason')) is not str
            or facts['reason'] not in REASONS):
        return {}
    result = {'reason': facts['reason']}
    if facts['reason'] == 'DRAFT_READ_FAILURE':
        result['predicate'] = safe_code(facts.get('predicate'))
        result['operation'] = facts.get('operation') if facts.get('operation') in ('LIST', 'GET', 'LOCAL') else 'LOCAL'
        result['phase'] = facts.get('phase') if facts.get('phase') in ('START', 'FIRST_LIST', 'CANDIDATE_GET', 'SECOND_LIST', 'FINAL_GET', 'PROOF') else 'START'
        offset, status, code = (facts.get(k) for k in ('offset', 'http_status', 'wechat_error_code'))
        result['offset'] = offset if type(offset) is int and 0 <= offset < 1000 else None
        result['http_status'] = status if type(status) is int and 100 <= status <= 599 else None
        result['wechat_error_code'] = code if type(code) is int and -(2**31) <= code < 2**31 and code != 0 else None
        for key in ('total', 'candidate_count', 'title_matches', 'content_matches', 'cover_matches'):
            value = facts.get(key)
            result[key] = value if type(value) is int and 0 <= value <= 1000 else None
        return result
    if facts['reason'] == 'LIST_API_REJECTED':
        offset, code = facts.get('offset'), facts.get('wechat_error_code')
        result['offset'] = offset if type(offset) is int and 0 <= offset <= 2**31 - 1 else None
        # Official numeric errors only: no response text or credential-like
        # unbounded integers, and zero cannot describe a rejected API response.
        result['wechat_error_code'] = code if type(code) is int and -(2**31) <= code <= 2**31 - 1 and code != 0 else None
        if type(facts.get('field_type')) is str and facts['field_type'] in FIELD_TYPES:
            result['field_type'] = facts['field_type']
        return result
    if facts['reason'] in {'IMAGE_MATCH_COUNTS', 'PIXEL_MATCH_COUNTS'}:
        for key in (MATCH_COUNTS if facts['reason'] == 'IMAGE_MATCH_COUNTS' else PIXEL_COUNTS):
            value = facts.get(key)
            result[key] = value if type(value) is int and 0 <= value <= 4 else None
        return result
    for key in LIST_COUNTS + ITEM_COUNTS:
        value = facts.get(key)
        if key in LIST_COUNTS or key in facts:
            result[key] = value if type(value) is int and 0 <= value <= 2**31 - 1 else None
    if type(facts.get('field_type')) is str and facts['field_type'] in FIELD_TYPES:
        result['field_type'] = facts['field_type']
    return result


def write_outcome(runtime):
    # Identity checks remain even after a short deadline expires. No credential,
    # business authorization or network operation is obtained by this write.
    config = runtime.config
    if (path_check(config.path) != config.file_pin
            or path_check(config.root, True) != config.directory_pin):
        return False
    if type(runtime.diagnostic_id) is not str or re.fullmatch('[a-f0-9]{32}', runtime.diagnostic_id) is None:
        return False
    result = {'schema': 1, 'binding_digest': digest(runtime.profile.binding()),
              'config_digest': runtime.info['config_digest'], 'diagnostic_id': runtime.diagnostic_id,
              'pid': runtime.info['pid'], 'phase': runtime.run_phase if type(runtime.run_phase) is str and runtime.run_phase in PHASES else 'START',
              'outcome': 'FAILED' if runtime.run_failure else 'STOPPED',
              'keychain_state': runtime.keychain_state if type(runtime.keychain_state) is str and runtime.keychain_state in {'UNUSED', 'STORED', 'LOADED'} else 'UNUSED',
              'error_code': safe_code(runtime.run_failure) if runtime.run_failure else None,
              'diagnostic': safe_counts(runtime.reconcile_diagnostics),
              'business_success': False, 'credential_value_included': False}
    path = config.root / ('run-outcome-' + str(runtime.info['pid']) + '-' + runtime.diagnostic_id + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write((encoded(result) + '\n').encode()); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(config.root, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return True
