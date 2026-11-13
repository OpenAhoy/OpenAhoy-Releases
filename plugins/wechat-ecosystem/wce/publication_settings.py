"""Proposed trusted-page-only publication review and commit adapter.

Human admission is SettingsBackend's existing one-shot review/commit. No MCP
entry calls this module. Evidence adapters intentionally fail closed until the
real runtime, permission-source and producer ownership contracts exist.
"""
import re
import secrets
from .contracts import WCEError
from .own_connection_policy import resolve
from .own_connection_registry import snapshot
from .publication_contract import CONTRACT, CONTRACT_SHA
from .publication_store import PublicationStore, enable, disable
from .publication_service import PublicationService
from . import publication_settings_journal as journal
from .service import digest

ENABLE = 'PUBLICATION_ENABLE'
DISABLE = 'PUBLICATION_DISABLE'


def _runtime_attestation(policy):
    # OfficialRuntime.inspect_runtime currently cannot prove no inherited MCP.
    # Future replacement must verify the live official runtime's isolation and
    # bounded review receipt, bound to the exact loaded candidate; no UI input.
    raise WCEError('REVIEW_RUNTIME_UNAVAILABLE')


def _permission_evidence(policy):
    # Future trusted-source adapter: preserve actual observed_at/not_after and
    # original source; a checkbox or model assertion is not platform proof.
    raise WCEError('PUBLICATION_ADMISSION_UNKNOWN')


def _producer_root(policy):
    # Future trusted host registry selects the per-account producer root;
    # no model-supplied filesystem path or arbitrary UI path is accepted here.
    raise WCEError('PUBLICATION_PRODUCER_UNAVAILABLE')


def _baseline_commit_guard(policy, inputs):
    # Must later verify the complete pinned baseline under the producer-channel
    # ownership lock across admission and commit, including writer/epoch. A
    # second unlocked scan alone cannot exclude concurrent mutation.
    raise WCEError('PUBLICATION_BASELINE_LOCK_UNAVAILABLE')


def _prepare_baseline(policy, root):
    # Producer.baseline requires the account dispatch lock and an explicit
    # stable DB snapshot; this adapter cannot assert that from an unlocked scan.
    raise WCEError('PUBLICATION_BASELINE_LOCK_UNAVAILABLE')


def _sha(value):
    if type(value) is not str or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise WCEError('PUBLICATION_EVIDENCE_INVALID')
    return value


def _verified_inputs(policy, wall):
    runtime = _runtime_attestation(policy)
    permission = _permission_evidence(policy)
    if (type(runtime) is not dict or set(runtime) != {'sha256', 'expires_ms'} or
        type(runtime['expires_ms']) is not int or int(wall()*1000) >= runtime['expires_ms']):
        raise WCEError('REVIEW_RUNTIME_UNAVAILABLE')
    _sha(runtime['sha256'])
    if (type(permission) is not dict or set(permission) != {'sha256', 'observed_ms', 'not_after_ms'} or
        type(permission['observed_ms']) is not int or type(permission['not_after_ms']) is not int or
        not permission['observed_ms'] <= int(wall()*1000) < permission['not_after_ms'] or
        permission['not_after_ms'] - permission['observed_ms'] > 24*3600*1000):
        raise WCEError('PUBLICATION_ADMISSION_UNKNOWN')
    _sha(permission['sha256'])
    root = _producer_root(policy)
    baseline_value = _prepare_baseline(policy, root)
    return {'runtime': runtime, 'permission': permission, 'root': str(root), 'baseline': baseline_value}


def status(backend, connection_id, check_session):
    backend.check(check_session)
    policy = resolve(connection_id, backend.registry, active=False)
    store = PublicationStore(policy, backend.registry, wall=backend.wall)
    pending = journal.inspect(policy, store)
    recent = journal.recent(policy, store)
    try:
        value = PublicationService(policy, backend.registry).status()
    except WCEError:
        value = {'state':'UNKNOWN','enabled':None,'admission':'UNKNOWN'}
    backend.check(check_session)
    return {'connection_id': connection_id, 'state': value['state'],
            'enabled': value['enabled'], 'admission': value['admission'],
            'qa_runtime': 'REVIEW_RUNTIME_UNAVAILABLE',
            'producer': 'NOT_CONFIGURED', 'baseline': 'UNAVAILABLE',
            'pending_disable': ({'operation_id':pending['operation_id'], 'state':'UNKNOWN'} if pending else None),
            'last_disable': recent,
            'mass': 'UNAVAILABLE_PENDING_HUMAN_SOURCE_AND_ADMISSION'}


def durable_state(backend, reviewed):
    """Exact operation receipt only; a current OFF state is not a receipt."""
    operation_id = reviewed['proposed']['transaction']
    if not re.fullmatch(r'pub-setting-[a-f0-9]{32}', operation_id):
        raise WCEError('PUBLICATION_OPERATION_ID_INVALID')
    policy = resolve(reviewed['target'], backend.registry, active=False)
    store = PublicationStore(policy, backend.registry, wall=backend.wall)
    return journal.result(policy, store, operation_id)


def recover_pending(backend, connection_id, check_session):
    backend.check(check_session)
    policy = resolve(connection_id, backend.registry, active=False)
    pending = journal.inspect(policy, PublicationStore(policy, backend.registry, wall=backend.wall))
    backend.check(check_session)
    if pending is None:
        return None
    return {'intent': DISABLE, 'target': connection_id,
            'proposed': {'transaction': pending['operation_id']}}


def admit_disable(backend, reviewed, check_session):
    policy = resolve(reviewed['target'], backend.registry, active=False)
    store = PublicationStore(policy, backend.registry, wall=backend.wall)
    def guard():
        backend.check(check_session)
        if backend.state != 'ACTIVE' or backend.selected != reviewed['target'] or backend.generation != reviewed['generation']:
            raise WCEError('SETTINGS_REVIEW_CHANGED')
    journal.admit(policy, store, reviewed, guard)


def prepare(backend, value, check_session):
    """Invoked solely inside SettingsBackend.prepare while its lock is held."""
    backend.check(check_session)
    if backend.state != 'READY' or backend.pending_recovery is not None or backend.navigation_pending:
        raise WCEError('SETTINGS_BUSY')
    if type(value) is not dict:
        raise WCEError('SETTINGS_INVALID_REQUEST')
    intent = value.get('intent')
    fields = {'intent', 'connection_id'} if intent == DISABLE else {'intent', 'connection_id', 'summary_mode', 'originality'}
    if intent not in {ENABLE, DISABLE} or set(value) != fields:
        raise WCEError('SETTINGS_INVALID_REQUEST')
    cid = value['connection_id']
    if type(cid) is not str or backend.selected != cid:
        raise WCEError('SETTINGS_REVIEW_CHANGED')
    if intent == ENABLE and (value['summary_mode'] not in {'PLATFORM_AUTO_ACCEPTED', 'CUSTOM_REQUIRED', 'EMPTY_REQUIRED'} or value['originality'] not in {'not_requested', 'required'}):
        raise WCEError('SETTINGS_INVALID_REQUEST')
    policy = resolve(cid, backend.registry, active=(intent == ENABLE))
    store = PublicationStore(policy, backend.registry, wall=backend.wall)
    if journal.inspect(policy, store) is not None:
        raise WCEError('PUBLICATION_DISABLE_RESULT_UNKNOWN')
    expected_policy = store.setting_policy() if intent == DISABLE else None
    base = snapshot(backend.registry)
    if cid not in base['registry_value']['connections']:
        raise WCEError('CONNECTION_NOT_BOUND')
    inputs = _verified_inputs(policy, backend.wall) if intent == ENABLE else None
    display = {'intent': intent, 'connection_id': cid, 'contract': CONTRACT,
               'contract_sha': CONTRACT_SHA, 'default_enabled': False,
               'normal_publication': 'FREEPUBLISH_NO_PUSH',
               'mass': 'EXPLICIT_HUMAN_INTENT_ONLY_NOT_IMPLEMENTED',
               'backlog': False, 'external_edit_cas': False,
               'disable_cannot_retract_dispatched': True}
    if intent == ENABLE:
        display.update(summary_mode=value['summary_mode'], originality=value['originality'],
            permission_source='TRUSTED_SOURCE_NOT_PLATFORM_ASSERTION',
            permission_observed_ms=inputs['permission']['observed_ms'],
            permission_not_after_ms=inputs['permission']['not_after_ms'],
            producer_root=inputs['root'], baseline_sha=digest(inputs['baseline']))
    backend.clear_target()
    backend.selected = cid
    proposed = {'base': base, 'transaction': 'pub-setting-' + secrets.token_hex(16)}
    backend.review = {'id': secrets.token_urlsafe(24), 'approval': secrets.token_urlsafe(32),
        'intent': intent, 'proposed': proposed, 'created': backend.clock(), 'wall': backend.wall(),
        'generation': backend.generation, 'target': cid, 'publication_inputs': inputs,
        'publication_expected_policy': expected_policy,
        'publication_settings': {k:value[k] for k in ('summary_mode','originality')} if intent == ENABLE else None,
        'publication_display_sha': digest(display)}
    backend.state = 'REVIEW'
    return {'review_id': backend.review['id'], 'approval': backend.review['approval'],
            'expires_in_seconds': 120, 'review': display}


def execute(backend, reviewed, check_session):
    """Only called after SettingsBackend.admit consumed the human review."""
    def guard():
        with backend.lock:
            backend.check(check_session)
            if backend.state != 'ACTIVE' or reviewed['target'] != backend.selected or reviewed['generation'] != backend.generation:
                raise WCEError('SETTINGS_REVIEW_CHANGED')
    guard()
    policy = resolve(reviewed['target'], backend.registry, active=(reviewed['intent'] == ENABLE))
    store = PublicationStore(policy, backend.registry, wall=backend.wall)
    if reviewed['intent'] == DISABLE:
        result = disable(store, guard, operation_id=reviewed['proposed']['transaction'],
                         expected_policy=reviewed['publication_expected_policy'])
        if (result.get('state') == 'OFF' and result.get('enabled') is False and
                result.get('operation_id') == reviewed['proposed']['transaction'] and
                result.get('durable') == {'state': 'NO_CHANGE', 'publication': 'DISABLE'}):
            journal.no_change(policy, store, reviewed, result)
        return result
    if reviewed['intent'] != ENABLE:
        raise WCEError('SETTINGS_INVALID_REQUEST')
    inputs = _verified_inputs(policy, backend.wall)
    if inputs != reviewed['publication_inputs']:
        raise WCEError('PUBLICATION_ENABLE_EVIDENCE_CHANGED')
    guard()
    # Existing human one-shot confirmation binds display, account, choice and
    # independently checked evidence. This digest is not platform verification.
    human_source = digest({'contract_sha': CONTRACT_SHA, 'connection_id': reviewed['target'],
        'display_sha': reviewed['publication_display_sha'], 'confirmed_at': reviewed['confirmed_at'],
        'nonce_sha': digest({'id': reviewed['id'], 'approval': reviewed['approval']}),
        'permission_source_sha': inputs['permission']['sha256']})
    proposal = {'human_source_sha': human_source, 'producer_root': inputs['root'],
        'summary_mode': reviewed['publication_settings']['summary_mode'],
        'originality': reviewed['publication_settings']['originality'],
        'permission_observed_ms': inputs['permission']['observed_ms'],
        'permission_not_after_ms': inputs['permission']['not_after_ms'],
        'permission_source_sha': inputs['permission']['sha256'],
        'runtime_receipt_sha': inputs['runtime']['sha256'],
        'runtime_expires_ms': inputs['runtime']['expires_ms']}
    def final_guard():
        guard()
        if (_runtime_attestation(policy) != inputs['runtime'] or
                _permission_evidence(policy) != inputs['permission'] or
                not inputs['permission']['observed_ms'] <= int(backend.wall()*1000) < inputs['permission']['not_after_ms'] or
                int(backend.wall()*1000) >= inputs['runtime']['expires_ms']):
            raise WCEError('PUBLICATION_ENABLE_EVIDENCE_CHANGED')
        _baseline_commit_guard(policy, inputs)
    final_guard()
    return enable(store, proposal, inputs['baseline'], final_guard)
