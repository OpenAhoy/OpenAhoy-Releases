"""Fixed local pool adoption from an actual entry-issued ACCOUNT coverage.

Foreign platform drafts are observations, never silently enrolled as managed
groups. A first pool starts with no managed groups; subsequent transitions
refresh the existing pool through its original reducer. No HTTP or commit.
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

_CURRENT = ContextVar('group_original_account_pool_transition', default=None)
_ISSUED = {}
_THREAD = threading.get_ident
_TIME = time.time
_MONOTONIC = time.monotonic


def need(value, code='GROUP_POOL_ISSUER_REQUIRED'):
    if value is not True:
        raise WCEError(code)


@dataclass(frozen=True)
class _Record:
    value: object
    host: object
    entry: object
    db: object
    epoch: int
    thread: int
    coverage: object
    action: str
    event_kind: str
    payload_json: str
    before_state_sha: str
    before_seq: int
    before_head: str | None
    phase: str = 'READY'
    after_head: str | None = None


def _record(value):
    need(type(value) is PoolTransition)
    record = _ISSUED.get(id(value))
    need(record is not None and record.value is value
         and record.thread == _THREAD() and record.host.entry is record.entry
         and record.entry.issued.get(id(value)) is value,
         'GROUP_POOL_ISSUER_UNISSUED')
    record.entry.held_pure()
    need(type(record.db) is OwnedConnection and record.db.in_transaction
         and _transaction_marker(record.db) == record.epoch,
         'GROUP_POOL_TRANSACTION_CHANGED')
    return record


def _state(host, db):
    from .draft_group_store import _load
    return _load(db, digest(host.chain.config['binding']))


def _current(record, *, history_locators=None):
    from .draft_group_coverage import verify_account_coverage
    record.host.current_no_token_in(record.db, record.host._source, history_locators=history_locators)
    verify_account_coverage(record.coverage, record.host, record.db, history_locators=history_locators)
    workflow = record.entry.service.workflow
    profiles = tuple(workflow.registry.profiles.values())
    need(len(profiles) == 1 and workflow.active_token is None
         and workflow._lease(profiles[0]) is None, 'GROUP_POOL_LOCAL_NO_TOKEN')


def _late_deadline(record):
    # No source/history/file preparation may follow these original primitive
    # samples. Never turn a later coverage check into a new oldest baseline.
    from .draft_group_coverage import _record as coverage_record
    original = coverage_record(record.coverage)
    workflow = record.entry.service.workflow
    need(workflow.active_token is None and workflow.active_lease is None,
         'GROUP_POOL_LOCAL_NO_TOKEN')
    now, monotonic = int(_TIME() * 1000), _MONOTONIC()
    need(0 <= now - original.observed_at_ms <= 60000
         and monotonic < record.entry.deadline
         and now < int(record.host._source.not_after * 1000),
         'GROUP_POOL_COVERAGE_EXPIRED')


def _finished_event(record, *, history_locators=None):
    _current(record, history_locators=history_locators)
    account = digest(record.host.chain.config['binding'])
    row = record.db.execute('SELECT seq,kind,payload,event_sha FROM group_events WHERE account_key=? '
                            'ORDER BY seq DESC LIMIT 1', (account,)).fetchone()
    need(row is not None and row['seq'] == record.before_seq + 1
         and row['kind'] == record.event_kind and row['payload'] == record.payload_json
         and (record.after_head is None or row['event_sha'] == record.after_head),
         'GROUP_POOL_COMMIT_CANDIDATE_CHANGED')
    _, seq, head = _state(record.host, record.db)
    need(seq == record.before_seq + 1 and head == row['event_sha'],
         'GROUP_POOL_ORIGINAL_HEAD_CHANGED')
    record.host.pure_release_fence()
    _record(record.value)
    _late_deadline(record)
    return head


class PoolTransition:
    __slots__ = ()

    def __init__(self):
        raise WCEError('GROUP_POOL_ISSUER_REQUIRED')

    def apply(self, *, history_locators=None):
        from .draft_group_store import GroupStore
        record = _record(self)
        need(record.phase == 'READY', 'GROUP_POOL_ALREADY_SUBMITTED')
        _current(record, history_locators=history_locators)
        store = GroupStore(digest(record.host.chain.config['binding']), _history_partial(record.host.verify_in, history_locators=history_locators))
        value = json.loads(record.payload_json)
        if record.action == 'POOL_REGISTER':
            result = store.initialize_pool_in(record.db, source_kind=value['source_kind'],
                groups=(), coverage=record.coverage.candidate, proof_sha=value['proof_sha'], history_locators=history_locators)
        else:
            result = store.refresh_coverage_in(record.db, coverage=record.coverage.candidate,
                                               proof_sha=value['proof_sha'], history_locators=history_locators)
        record = _record(self)
        need(record.phase == 'CHECKED', 'GROUP_POOL_FIXED_VERIFIER_REQUIRED')
        after_head = _finished_event(record, history_locators=history_locators)
        _ISSUED[id(self)] = replace(record, phase='FINISHED', after_head=after_head)
        return result


@contextmanager
def account_pool_transition_in(host, db, coverage, *, history_locators=None):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_coverage import AccountCoverage, verify_account_coverage
    need(type(host) is GroupRuntimeHost and type(db) is OwnedConnection
         and type(coverage) is AccountCoverage and db.in_transaction
         and _transaction_marker(db) is not None, 'GROUP_POOL_ACTUAL_CONTEXT_REQUIRED')
    need(_CURRENT.get() is None, 'GROUP_POOL_REENTRANT')
    host.current_no_token_in(db, host._source, history_locators=history_locators)
    verify_account_coverage(coverage, host, db, history_locators=history_locators)
    state, seq, head = _state(host, db)
    need(state is not None, 'GROUP_POOL_FIRST_REQUIRED')
    binding = host.chain.config['binding']
    if state['pool'] is None:
        action, kind = 'POOL_REGISTER', 'POOL'
        payload = {'binding_sha': digest(binding), 'source_kind': binding['source_kind'],
                   'groups': [], 'coverage': coverage.candidate.value(), 'proof_sha': coverage.proof_sha}
    else:
        action = kind = 'COVERAGE_REFRESH'
        payload = {'coverage': coverage.candidate.value(), 'proof_sha': coverage.proof_sha}
    value = object.__new__(PoolTransition)
    record = _Record(value, host, host.entry, db, _transaction_marker(db), _THREAD(), coverage,
                     action, kind, canonical(payload), digest(state), seq, head)
    _ISSUED[id(value)] = record
    host.entry.issued[id(value)] = value
    token = _CURRENT.set(value)
    try:
        _current(record, history_locators=history_locators)
        yield value
        final = _record(value)
        need(final.phase == 'FINISHED', 'GROUP_POOL_TRANSITION_NOT_FINISHED')
        _finished_event(final, history_locators=history_locators)
    finally:
        _CURRENT.reset(token)
        _ISSUED.pop(id(value), None)
        host.entry.issued.pop(id(value), None)


def validate_pool_transition_in(host, db, action, details, *, history_locators=None):
    value = _CURRENT.get()
    record = _record(value)
    need(record.host is host and record.db is db and record.phase == 'READY'
         and action == record.action and canonical(details) == record.payload_json,
         'GROUP_POOL_TRANSITION_CHANGED')
    _current(record, history_locators=history_locators)
    state, seq, head = _state(host, db)
    need(digest(state) == record.before_state_sha and seq == record.before_seq
         and head == record.before_head, 'GROUP_POOL_ORIGINAL_HEAD_CHANGED')
    host.pure_release_fence()
    _record(record.value)
    _late_deadline(record)
    _ISSUED[id(value)] = replace(record, phase='CHECKED')
    return None


from functools import partial as _history_partial
