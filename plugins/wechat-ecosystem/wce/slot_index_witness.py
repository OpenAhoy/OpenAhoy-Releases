"""Private index row observations, bounded to one actual Source fence.

Only duplicate index subprocess reads are shared. Source bytes, creators,
metadata, guards, and physical lookup checks still run at every original call.
There is no persisted witness and no caller flag or authorization cache.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import asyncio
import inspect
import os
import threading
from types import CodeType
from .draft_revision_native_source import require, checked_guard

_ACTIVE = ContextVar('slot_single_fence_index_rows', default=None)
_SEAL = object()


def _task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


@dataclass(frozen=True)
class _RowWitness:
    lookup: object
    configuration: tuple
    identity: tuple
    thread: str
    row: tuple
    seal: object

    def __post_init__(self):
        require(self.seal is _SEAL, 'HOST_UNCHECKED_INDEX_ROW')


# Imported lazily by NativeThreadLookup after its class has been defined.
from . import draft_revision_native_lookup as _native
from . import draft_revision_index_client as _transport
_LOOKUP = _native.NativeThreadLookup
_ROW = _LOOKUP._row
_ROW_LOCKED = _LOOKUP._row_locked
_QUERY = _native.query_index
_EXCHANGE = _transport._exchange
_QUERY_CODE, _EXCHANGE_CODE = _QUERY.__code__, _EXCHANGE.__code__
_ROW_CODE, _ROW_LOCKED_CODE = _ROW.__code__, _ROW_LOCKED.__code__
from .slot_source_provider import SourceProvider as _PROVIDER
_FREEZE, _FREEZE_CODE = _PROVIDER._freeze, _PROVIDER._freeze.__code__
_CHECK_CODE = next(c for c in _FREEZE_CODE.co_consts
    if type(c) is CodeType and c.co_name == 'check')


def _original(lookup):
    return (type(lookup) is _LOOKUP and _native.NativeThreadLookup is _LOOKUP
        and _LOOKUP._row is _ROW and _LOOKUP._row_locked is _ROW_LOCKED
        and _ROW.__code__ is _ROW_CODE and _ROW_LOCKED.__code__ is _ROW_LOCKED_CODE
        and '_row' not in vars(lookup) and '_row_locked' not in vars(lookup)
        and _native.query_index is _QUERY and _transport.query_index is _QUERY
        and _QUERY.__code__ is _QUERY_CODE and _transport._exchange is _EXCHANGE
        and _EXCHANGE.__code__ is _EXCHANGE_CODE)


def _configuration(lookup):
    return (lookup.state_path, lookup.session_root, lookup.owner_thread,
        lookup.allowed_threads, lookup.guard, lookup.deadline)


def _same_configuration(lookup, expected):
    current = _configuration(lookup)
    return (current[:4] == expected[:4] and current[4] is expected[4]
        and current[5] == expected[5])


def _owner(frame, provider):
    from .slot_source_provider import SourceProvider
    return (SourceProvider is _PROVIDER and type(provider) is _PROVIDER
        and _PROVIDER._freeze is _FREEZE and _FREEZE.__code__ is _FREEZE_CODE
        and frame.f_code is _CHECK_CODE and frame.f_locals.get('self') is provider)


class _Scope:
    def __init__(self, provider):
        self.provider = provider
        self.active = False
        self.entries = {}
        self.pending = {}
        self.token = None
        self.frame = None

    def __enter__(self):
        frame = inspect.currentframe().f_back
        if not _owner(frame, self.provider):
            return self  # Unrecognized callers retain the original full path.
        self.frame = frame
        self.pid, self.thread, self.task = os.getpid(), threading.get_ident(), _task()
        self.active = True
        self.token = _ACTIVE.set(self)
        return self

    def current(self):
        if (not self.active or self.pid != os.getpid()
                or self.thread != threading.get_ident() or self.task is not _task()
                or not _owner(self.frame, self.provider)):
            return False
        frame = inspect.currentframe()
        try:
            while frame is not None:
                if frame is self.frame:
                    return True
                frame = frame.f_back
            return False
        finally:
            del frame

    def finish(self):
        # No memo is visible to the exit observations. Each original _row
        # recalculates its own query work deadline under the current guard.
        token = _ACTIVE.set(None)
        try:
            for witness in self.entries.values():
                lookup = witness.lookup
                require(_original(lookup) and _same_configuration(lookup, witness.configuration),
                    'HOST_NATIVE_POINTER_CHANGED')
                checked_guard(lookup.guard)
                info = lookup.state_path.lstat()
                require((info.st_dev, info.st_ino) == witness.identity, 'HOST_NATIVE_INDEX_CHANGED')
                row = _ROW(lookup, witness.thread)
                require(row == witness.row, 'HOST_NATIVE_POINTER_CHANGED')
                info = lookup.state_path.lstat()
                require((info.st_dev, info.st_ino) == witness.identity, 'HOST_NATIVE_INDEX_CHANGED')
                checked_guard(lookup.guard)
        finally:
            _ACTIVE.reset(token)

    def __exit__(self, kind, value, traceback):
        try:
            if self.active and kind is None:
                require(self.current(), 'HOST_NATIVE_POINTER_CHANGED')
                self.finish()
        finally:
            self.active = False
            self.entries.clear()
            self.pending.clear()
            self.frame = None
            if self.token is not None:
                _ACTIVE.reset(self.token)
                self.token = None
        return False


def _source_fence_scope(provider):
    return _Scope(provider)


def _scope(lookup):
    scope = _ACTIVE.get()
    if type(scope) is not _Scope or not scope.current():
        return None
    if not _original(lookup):
        require(not scope.entries and not scope.pending, 'HOST_NATIVE_POINTER_CHANGED')
        return None
    frame = inspect.currentframe().f_back.f_back
    if frame.f_code is not _ROW_LOCKED.__code__ or frame.f_locals.get('self') is not lookup:
        return None
    return scope


def _query_row(lookup, thread, identity, deadline):
    scope = _scope(lookup)
    key = (lookup, thread)
    configuration = _configuration(lookup)
    if scope is not None:
        witness = scope.entries.get(key)
        if witness is not None:
            require(_same_configuration(lookup, witness.configuration) and witness.identity == identity,
                'HOST_NATIVE_POINTER_CHANGED')
            checked_guard(lookup.guard)
            return witness.row
    # The unrecognized/no-scope legacy route uses exactly the original query.
    row = _native.query_index(lookup.state_path, lookup.session_root, identity,
        thread, lookup.owner_thread, lookup.guard, deadline=deadline)
    if scope is not None:
        scope.pending[key] = _RowWitness(lookup, configuration, identity, thread, row, _SEAL)
    return row


def _verified_row(lookup, thread, row):
    """Publish only after the original full _row_locked checks have passed."""
    scope = _scope(lookup)
    if scope is None:
        return
    key = (lookup, thread)
    witness = scope.pending.pop(key, None)
    if witness is not None:
        require(witness.row == row and _same_configuration(lookup, witness.configuration),
            'HOST_NATIVE_POINTER_CHANGED')
        scope.entries[key] = witness
