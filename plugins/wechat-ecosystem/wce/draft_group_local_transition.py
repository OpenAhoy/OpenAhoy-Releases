"""Fixed NEW_ONLY SWITCH/COMPLETE from genuine original archived GETs.

No new GET, token acquisition, upload, publication or caller-selected proof.
The original GroupStore remains the phase/freshness/budget reducer. This
issuer supplies its actual Host verifier with the original physical receipts.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
import json
import threading
import time

from .contracts import WCEError
from .service import canonical, digest
from .own_validation_scope import OwnedConnection, _transaction_marker

_CURRENT = ContextVar('group_original_local_transition', default=None)
_ISSUED = {}
_THREAD, _TIME = threading.get_ident, time.time


def need(value, code='GROUP_LOCAL_TRANSITION_HOLD'):
    if value is not True:
        raise WCEError(code)


@dataclass(frozen=True)
class _Record:
    value: object
    host: object
    scope: object
    db: object
    epoch: int
    thread: int
    action: str
    payload_json: str
    files: object
    original_claim_json: str
    original_state_sha: str
    original_seq: int
    original_head: str
    observed_ms: int
    not_after_ms: int
    phase: str = 'READY'
    result_head: str | None = None


def _record(value):
    need(type(value) is LocalTransition, 'GROUP_LOCAL_TRANSITION_ISSUER_REQUIRED')
    record = _ISSUED.get(id(value))
    need(record is not None and record.value is value and record.thread == _THREAD()
         and record.host.entry.issued.get(id(value)) is value,
         'GROUP_LOCAL_TRANSITION_UNISSUED')
    record.host.entry.held_pure()
    need(type(record.db) is OwnedConnection and record.db.in_transaction
         and _transaction_marker(record.db) == record.epoch,
         'GROUP_LOCAL_TRANSITION_TRANSACTION_CHANGED')
    return record


def _late(record):
    workflow = record.host.entry.service.workflow
    need(workflow.active_token is None and workflow.active_lease is None,
         'GROUP_LOCAL_TRANSITION_NO_TOKEN')
    now = int(_TIME() * 1000)
    need(0 <= now - record.observed_ms <= 60000 and now < record.not_after_ms,
         'GROUP_LOCAL_TRANSITION_EXPIRED')


def _receipt(host, db, scope, action, files, *, history_locators=None):
    from .draft_group_runtime_host import validate_admission_scope, resolve_group_reference_in
    from .draft_group_parent import validate_parent_execution_in, validate_issued_parent_execution_in
    from .draft_group_store import _load, _current_child, _claim, _fresh
    from .draft_group_contracts import budget_for
    from .draft_group_response_history import load_original_locator_in
    validate_admission_scope(scope, db=db, history_locators=history_locators)
    need(scope.host is host and scope.details['ledger_kind'] == 'CHILD',
         'GROUP_LOCAL_TRANSITION_SCOPE_REQUIRED')
    parent = validate_parent_execution_in(host, db, scope.details['operation_id'], history_locators=history_locators)
    validate_issued_parent_execution_in(parent, host, db, history_locators=history_locators)
    need(parent.route == 'NEW_ONLY_EXISTING_DELEGATION', 'GROUP_LOCAL_NEW_ONLY_REQUIRED')
    state, seq, head = _load(db, scope.details['account_key'])
    operation, _ = _current_child(state, scope.details['operation_id'])
    need(not operation['old_refs'] and operation['plan']['route'] == 'CREATE_NEW'
         and canonical(operation['plan']['budget']) == canonical(budget_for(0)),
         'GROUP_LOCAL_NEW_ONLY_REQUIRED')
    slot = 'NEW' if action == 'SWITCH' else 'FINAL_NEW'
    claim = _claim(operation, 'GET', slot)
    need(claim is not None and claim['state'] == 'OBSERVED' and claim['outcome'] == 'MATCHED',
         'GROUP_LOCAL_ORIGINAL_GET_REQUIRED')
    now = int(_TIME() * 1000)
    _fresh(operation, [slot], scope.details['source_epoch'], now)
    reference = resolve_group_reference_in(db, host.entry.policy, scope, operation['new_ref_sha'], history_locators=history_locators)
    locator = load_original_locator_in(files, db, state, claim['id'], reference=reference)
    primary = files.read_primary(locator)
    snapshot = files.read_snapshot(locator, primary)
    observation = primary.value['observation']
    need(snapshot is not None and primary.sha256 == claim['proof_sha']
         and observation['outcome'] == 'MATCHED'
         and observation['projection_sha'] == operation['pins']['target_projection_sha'],
         'GROUP_LOCAL_ORIGINAL_GET_CHANGED')
    proof = {'profile': 'GROUP_NEW_ONLY_LOCAL_TRANSITION_V1', 'action': action,
             'binding_sha': state['binding_sha'], 'operation_id': parent.operation_id,
             'parent_grant_sha': parent.parent_grant_sha, 'capsule_sha': parent.capsule_sha,
             'source_epoch': scope.details['source_epoch'], 'claim_id': claim['id'],
             'primary_sha': primary.sha256, 'snapshot_sha': snapshot.sha256,
             'target_projection_sha': operation['pins']['target_projection_sha']}
    payload = {'operation_id': parent.operation_id, 'proof_sha': digest(proof),
               'epoch': scope.details['source_epoch'], 'at_ms': now}
    if action == 'SWITCH':
        payload['expected_head'] = state['pool']['head']
    files.collective_fence()
    host.pure_release_fence()
    return state, seq, head, claim, parent, payload


class LocalTransition:
    __slots__ = ()

    def __init__(self):
        raise WCEError('GROUP_LOCAL_TRANSITION_ISSUER_REQUIRED')

    def apply(self, *, history_locators=None):
        from .draft_group_store import GroupStore
        record = _record(self)
        need(record.phase == 'READY', 'GROUP_LOCAL_TRANSITION_ALREADY_SUBMITTED')
        store = GroupStore(record.scope.details['account_key'], _history_partial(record.host.verify_in, history_locators=history_locators))
        payload = json.loads(record.payload_json)
        operation = payload.pop('operation_id')
        if record.action == 'SWITCH':
            result = store.switch_in(record.db, operation, **payload, history_locators=history_locators)
        else:
            result = store.complete_in(record.db, operation, **payload, history_locators=history_locators)
        record = _record(self)
        need(record.phase == 'CHECKED', 'GROUP_LOCAL_FIXED_VERIFIER_REQUIRED')
        head = _finish(record, history_locators=history_locators)
        _ISSUED[id(self)] = replace(record, phase='FINISHED', result_head=head)
        return result


def _finish(record, *, history_locators=None):
    from .draft_group_store import _load
    record.host.current_no_token_in(record.db, record.scope.source, history_locators=history_locators)
    state, seq, head = _load(record.db, record.scope.details['account_key'])
    row = record.db.execute('SELECT kind,payload FROM group_events WHERE account_key=? AND seq=?',
                            (record.scope.details['account_key'], record.original_seq + 1)).fetchone()
    need(seq == record.original_seq + 1 and row is not None
         and row['kind'] == record.action and row['payload'] == record.payload_json
         and (record.result_head is None or record.result_head == head),
         'GROUP_LOCAL_TRANSITION_EVENT_CHANGED')
    operation = state['operations'][record.scope.details['operation_id']]
    slot = 'NEW' if record.action == 'SWITCH' else 'FINAL_NEW'
    claims = [c for c in operation['claims'] if c['kind'] == 'GET' and c['slot'] == slot]
    need(len(claims) == 1 and canonical(claims[0]) == record.original_claim_json,
         'GROUP_LOCAL_TRANSITION_ORIGINAL_GET_CHANGED')
    record.files.collective_fence()
    record.host.pure_release_fence()
    _record(record.value)
    _late(record)
    return head


@contextmanager
def new_only_local_transition_in(host, db, scope, action, *, history_locators=None):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import response_history_context_in
    from .draft_group_response_files import GroupResponseFiles
    need(type(host) is GroupRuntimeHost and type(db) is OwnedConnection and db.in_transaction
         and action in ('SWITCH', 'COMPLETE') and _CURRENT.get() is None,
         'GROUP_LOCAL_TRANSITION_CONTEXT_REQUIRED')
    files = GroupResponseFiles.from_history_context(host.entry.policy,
                                                    response_history_context_in(db, host.entry.policy))
    state, seq, head, claim, parent, payload = _receipt(host, db, scope, action, files, history_locators=history_locators)
    value = object.__new__(LocalTransition)
    record = _Record(value, host, scope, db, _transaction_marker(db), _THREAD(), action,
        canonical(payload), files, canonical(claim), digest(state), seq, head, claim['at_ms'],
        min(parent.original_not_after_ms, scope.details['qualified_not_after_ms']))
    _late(record)
    _ISSUED[id(value)] = record
    host.entry.issued[id(value)] = value
    token = _CURRENT.set(value)
    try:
        yield value
        final = _record(value)
        need(final.phase == 'FINISHED', 'GROUP_LOCAL_TRANSITION_NOT_FINISHED')
        _finish(final, history_locators=history_locators)
    finally:
        _CURRENT.reset(token)
        _ISSUED.pop(id(value), None)
        host.entry.issued.pop(id(value), None)


def validate_local_transition_in(host, db, action, details, *, history_locators=None):
    value = _CURRENT.get()
    record = _record(value)
    need(record.host is host and record.db is db and record.action == action
         and record.phase == 'READY' and canonical(details) == record.payload_json,
         'GROUP_LOCAL_TRANSITION_CHANGED')
    state, seq, head, claim, parent, payload = _receipt(host, db, record.scope, action, record.files, history_locators=history_locators)
    # The original event timestamp is retained, never replaced with this later
    # validation sample. Freshness is additionally checked against real now.
    payload['at_ms'] = json.loads(record.payload_json)['at_ms']
    need(digest(state) == record.original_state_sha and seq == record.original_seq
         and head == record.original_head and canonical(claim) == record.original_claim_json
         and canonical(payload) == record.payload_json, 'GROUP_LOCAL_ORIGINAL_HEAD_CHANGED')
    record.files.collective_fence()
    host.pure_release_fence()
    _record(value)
    _late(record)
    _ISSUED[id(value)] = replace(record, phase='CHECKED')
    return None


from functools import partial as _history_partial
