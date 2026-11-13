"""Child-only fixed-program issuer for the short Operator image session.

A peer dataclass, pinned JSON, or direct Python call cannot mint this entry.
Issuance requires the immediate canonical wrapper/bootstrap/run call chain and
an authenticated inherited socket. The entry grants no slot or Group right.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import inspect
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .draft_group_pin_resources import close_all, full
from . import own_preupload_sources as sources
from . import own_preupload_protocol as protocol
from .own_bootstrap_ipc import peer

_ISSUED = WeakKeyDictionary()
_ACTIVE = None


def need(value):
    if value is not True:
        raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')


@dataclass(frozen=True, eq=False, init=False)
class FixedPreuploadEntry:
    authority: bool = False

    def __init__(self, *args, **kwargs):
        raise WCEError('PREUPLOAD_ENTRY_ISSUER_REQUIRED')


@dataclass
class _EntryRecord:
    resources: object
    connection: object
    stream: object
    observation: object
    wrapper_values: dict
    pid: int
    thread: int
    socket_pin: tuple
    lifetime_pin: tuple
    active: bool = True
    consumed: bool = False
    service: object = None
    core: object = None
    sequence: int = 0
    active_request: object = None
    initialization_sent: bool = False


@dataclass(frozen=True)
class EntryView:
    """Identity/input view only; cannot be used to issue another entry."""
    candidate_scope: str
    selection_sha256: str
    resume_sha256: str
    deadline: float
    policy_path: Path
    selection_raw: bytes = field(repr=False)
    resume_raw: bytes = field(repr=False)
    slot_qualification: str = 'NOT_ASSERTED'
    group_entitlement: str = 'NOT_ASSERTED'
    authority: bool = False


def _check_program(values, raw):
    need(type(raw) is bytes and 0 < len(raw) <= sources.MAX_SOURCE)
    fd = values['BOOTSTRAP_FD']
    need(type(fd) is int and fd >= 3)
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
         and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
         and full(before) == values['BOOTSTRAP_PIN']
         and full(os.stat(values['BOOTSTRAP_PATH'], follow_symlinks=False)) == full(before)
         and len(raw) == values['BOOTSTRAP_SIZE'] == before.st_size
         and sha256(raw).hexdigest() == values['BOOTSTRAP_SHA'])
    # pread does not change the held descriptor position used by the wrapper.
    actual = os.pread(fd, len(raw)+1, 0)
    need(actual == raw and full(os.fstat(fd)) == full(before)
         and full(os.stat(values['BOOTSTRAP_PATH'], follow_symlinks=False)) == full(before))


def _preflight_fixed_frames():
    issue = inspect.currentframe().f_back
    run = issue.f_back
    bootstrap = run.f_back if run is not None else None
    wrapper = bootstrap.f_back if bootstrap is not None else None
    need(issue.f_code is _ISSUE_CODE and run is not None and run.f_code is _RUN_CODE
         and bootstrap is not None and wrapper is not None and wrapper.f_code.co_filename == '<string>')
    values = {key: wrapper.f_locals.get(key) for key in sources.WRAPPER_KEYS}
    wrapper_raw = sources.render_wrapper_values(values)
    need(wrapper.f_code == compile(wrapper_raw, '<string>', 'exec', dont_inherit=True)
         and type(wrapper.f_locals.get('_program')) is type(wrapper.f_code)
         and wrapper.f_locals['_program'] is bootstrap.f_code)
    raw = wrapper.f_locals.get('_raw')
    _check_program(values, raw)
    runtime = sources.installed_runtime()
    need(values['BOOTSTRAP_PATH'] == str(runtime.bootstrap)
         and values['CORE_ROOT'] == str(runtime.root) and values['CORE_SCOPE'] == runtime.scope
         and sys.argv == [str(runtime.bootstrap)]
         and bootstrap.f_globals.get('__name__') == '__main__'
         and bootstrap.f_globals.get('__file__') == str(runtime.bootstrap)
         and bootstrap.f_code == compile(raw, str(runtime.bootstrap), 'exec', dont_inherit=True))
    program = sources.parse_bootstrap(raw)
    need(all(bootstrap.f_globals.get(key) == program[key] for key in sources.BOOTSTRAP_KEYS)
         and program['CORE_ROOT'] == values['CORE_ROOT']
         and program['CORE_SCOPE'] == values['CORE_SCOPE']
         and program['BINDING_SHA256'] == values['BINDING_SHA256'])
    sources.need(type(values['ABSOLUTE_DEADLINE']) in (int, float)
                 and time.monotonic() < values['ABSOLUTE_DEADLINE'] <= time.monotonic()+300)
    fds = (values['BOOTSTRAP_FD'], values['SESSION_FD'], values['LIFETIME_READER'])
    need(all(type(fd) is int and fd >= 3 for fd in fds) and len(set(fds)) == 3
         and stat.S_ISSOCK(os.fstat(fds[1]).st_mode)
         and stat.S_ISFIFO(os.fstat(fds[2]).st_mode) and os.getppid() > 1)
    return values, raw


def _issue_fixed_entry():
    global _ACTIVE
    if (_assert_integrity is not _INTEGRITY_FUNCTION
            or _assert_integrity.__code__ is not _INTEGRITY_CODE):
        raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    _assert_integrity()
    need(_ACTIVE is None)
    values, raw = _preflight_fixed_frames()
    resources = connection = None
    try:
        resources = sources.acquire_fixed_sources()
        need(resources.bootstrap.raw == raw and resources.bootstrap.sha == values['BOOTSTRAP_SHA']
             and resources.binding.sha == values['BINDING_SHA256'])
        connection = socket.socket(fileno=values['SESSION_FD'])
        need(connection.family == socket.AF_UNIX and connection.type == socket.SOCK_STREAM
             and connection.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 0)
        observation, stream = protocol.child_handshake(connection,
            program_sha256=resources.bootstrap.sha, selection_sha256=resources.selection.sha,
            resume_sha256=resources.resume.sha, candidate_scope=resources.runtime.scope,
            deadline=values['ABSOLUTE_DEADLINE'])
        resources.guard()
        _check_program(values, raw)
        entry = object.__new__(FixedPreuploadEntry)
        record = _EntryRecord(resources, connection, stream, observation, values,
            os.getpid(), threading.get_ident(), full(os.fstat(connection.fileno())),
            full(os.fstat(values['LIFETIME_READER'])))
        _ISSUED[entry] = record
        _ACTIVE = entry
        require_fixed_entry(entry)
        return entry
    except BaseException as original:
        if _ACTIVE is not None:
            close_fixed_entry(_ACTIVE, original=original)
        else:
            close_all(([connection.close] if connection is not None else []) +
                      ([lambda: resources.close(original=original)] if resources is not None else []), original)
        raise


def _record(entry):
    if (_assert_integrity is not _INTEGRITY_FUNCTION
            or _assert_integrity.__code__ is not _INTEGRITY_CODE):
        raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    _assert_integrity()
    need(type(entry) is FixedPreuploadEntry)
    record = _ISSUED.get(entry)
    need(record is not None and _ACTIVE is entry and record.active
         and record.pid == os.getpid() and record.thread == threading.get_ident())
    observation = record.observation
    need(time.monotonic() < observation.absolute_deadline
         and os.getppid() == observation.parent_pid
         and peer(record.connection) == (observation.parent_pid, os.getuid())
         and full(os.fstat(record.connection.fileno())) == record.socket_pin
         and full(os.fstat(record.wrapper_values['LIFETIME_READER'])) == record.lifetime_pin)
    record.resources.guard()
    _check_program(record.wrapper_values, record.resources.bootstrap.raw)
    return record


def require_fixed_entry(entry, *, service=None):
    record = _record(entry)
    if service is not None:
        need(record.service is service)
    r, o = record.resources, record.observation
    return EntryView(r.runtime.scope, r.selection.sha, r.resume.sha,
        o.absolute_deadline, r.policy_file.path, r.selection.raw, r.resume.raw)


def consume_service_construction(entry, service):
    record = _record(entry)
    from .own_preupload_domain import PreuploadSessionService
    caller = inspect.currentframe().f_back
    need(caller.f_code is PreuploadSessionService.__init__.__code__
         and type(service) is PreuploadSessionService and not record.consumed)
    record.consumed = True  # Failure consumes construction; no second core.
    record.service = service
    return require_fixed_entry(entry, service=service)


def bind_service(entry, service, core):
    record = _record(entry)
    from .own_connection_broker import AccountService
    from .own_preupload_domain import PreuploadSessionService
    from .own_connection_workflow import PersistentWorkflow
    need(inspect.currentframe().f_back.f_code is PreuploadSessionService.__init__.__code__
         and record.consumed and record.service is service and record.core is None
         and type(core) is AccountService and type(core.workflow) is PersistentWorkflow
         and core.policy.path == record.resources.policy_file.path)
    core.policy.check()
    record.core = core


def require_service_entry(entry, service, core):
    record = _record(entry)
    need(record.consumed and record.service is service and record.core is core
         and core.policy is service.policy and core.workflow is service.workflow)
    core.policy.check()
    return require_fixed_entry(entry, service=service)


def send_initialization(entry,service=None,*,error=None):
    from .own_bootstrap_ipc import send
    from .own_preupload_domain import serve_in_fixed_entry
    need(inspect.currentframe().f_back.f_code is serve_in_fixed_entry.__code__)
    record=_record(entry)
    need(record.initialization_sent is False)
    if error is None:
        require_service_entry(entry,service,service.core)
        service.guard()
        from .own_preupload_qa import require_preupload_qa
        require_preupload_qa(service.qa,entry=entry,service=service)
    record.initialization_sent=True
    send(record.stream,protocol.initialization_frame(record.observation,error=error))


def receive_service_request(entry, service, core):
    from .own_bootstrap_ipc import receive
    require_service_entry(entry, service, core)
    record = _record(entry)
    need(record.initialization_sent is True and record.active_request is None)
    frame = receive(record.stream)
    method, arguments = protocol.validate_request(frame, observation=record.observation,
                                                  expected_sequence=record.sequence+1)
    record.sequence += 1
    encoded = sources.canonical(arguments)
    record.active_request = (record.sequence, method, encoded)
    return record.sequence, method, arguments


def require_service_request(entry, service, core, method, arguments):
    view = require_service_entry(entry, service, core)
    record = _record(entry)
    need(record.active_request == (record.sequence, method, sources.canonical(arguments)))
    # The parent uses one request/response at a time. EOF or a pipelined frame
    # is cancellation/protocol failure; the guard never consumes another RPC.
    from .own_connection_broker import locator_client_guard
    locator_client_guard(record.connection)
    return view


def respond_service_request(entry, service, core, *, value=None, error=None):
    from .own_bootstrap_ipc import send
    require_service_entry(entry, service, core)
    record = _record(entry)
    need(record.active_request is not None)
    response = protocol.response_frame(record.observation, record.sequence, value=value, error=error)
    send(record.stream, response)
    record.active_request = None


def close_fixed_entry(entry, *, original=None):
    global _ACTIVE
    record = _ISSUED.pop(entry, None)
    if record is None:
        return
    record.active = False
    if _ACTIVE is entry:
        _ACTIVE = None
    callbacks = [record.connection.close,
                 lambda: record.resources.close(original=original)]
    # The lifetime reader remains open while cleanup runs; the only watcher is
    # the daemon in this short process. Closing it cannot affect another owner.
    callbacks.extend((lambda: os.close(record.wrapper_values['BOOTSTRAP_FD']),
                      lambda: os.close(record.wrapper_values['LIFETIME_READER'])))
    close_all(callbacks, original)


def run_fixed_entry():
    entry = _issue_fixed_entry()
    try:
        from .own_preupload_domain import serve_in_fixed_entry
        serve_in_fixed_entry(entry)
    except BaseException as original:
        close_fixed_entry(entry, original=original)
        raise
    else:
        close_fixed_entry(entry)


_RUN_CODE = run_fixed_entry.__code__
_ISSUE_CODE = _issue_fixed_entry.__code__


# Freeze the actual SDK call implementations used by this issuer. Disk C is
# necessary but does not detect a runtime function override. This is an
# integrity guard, not an OS sandbox against arbitrary same-UID memory writes.
from . import own_preupload_qa as _qa_module
from . import own_preupload_domain as _domain_module
from . import own_preupload_inputs as _inputs_module
from . import own_preupload_selected_files as _selected_module
from . import own_preupload_derivation as _derivation_module
from . import own_preupload_journal as _journal_module
from . import own_preupload_child_journal as _child_journal_module
_INTEGRITY_MODULES = (sources, protocol, _qa_module, _domain_module,
    _inputs_module, _selected_module, _derivation_module, _journal_module, _child_journal_module)


def _snapshot_calls():
    calls, classes = [], []
    for namespace in (globals(), *(vars(module) for module in _INTEGRITY_MODULES)):
        for name, value in tuple(namespace.items()):
            if inspect.isfunction(value) and value.__module__.startswith('wce.'):
                calls.append((namespace, name, value, value.__code__, value.__defaults__,
                              None if value.__kwdefaults__ is None else dict(value.__kwdefaults__)))
            elif inspect.isclass(value) and value.__module__.startswith('wce.'):
                classes.append((namespace, name, value))
                for method_name, method in tuple(vars(value).items()):
                    if inspect.isfunction(method):
                        calls.append((vars(value), method_name, method, method.__code__,
                            method.__defaults__, None if method.__kwdefaults__ is None
                            else dict(method.__kwdefaults__)))
    return tuple(calls), tuple(classes)


def _assert_integrity():
    for module,name,items in _FROZEN_DATA_ITEMS:
        if tuple(sorted(getattr(module,name).items()))!=items:
            raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    for namespace, name, value in _FROZEN_LITERALS:
        if namespace.get(name) is not value:
            raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    for namespace, name, original_class in _FROZEN_CLASSES:
        if namespace.get(name) is not original_class:
            raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    for namespace, name, function, code, defaults, keyword_defaults in _FROZEN_CALLS:
        if (namespace.get(name) is not function or function.__code__ is not code
                or function.__defaults__ != defaults or function.__kwdefaults__ != keyword_defaults):
            raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')
    for namespace, name, descriptor, function, code in _FROZEN_DESCRIPTORS:
        if namespace.get(name) is not descriptor or function.__code__ is not code:
            raise WCEError('PREUPLOAD_FIXED_ENTRY_HOLD')


_INTEGRITY_FUNCTION = _assert_integrity
_INTEGRITY_CODE = _assert_integrity.__code__
_FROZEN_CALLS, _FROZEN_CLASSES = _snapshot_calls()
_FROZEN_DESCRIPTORS = tuple((vars(value),name,descriptor,descriptor.__func__,descriptor.__func__.__code__)
    for module in _INTEGRITY_MODULES for value in tuple(vars(module).values())
    if inspect.isclass(value) and value.__module__.startswith('wce.')
    for name,descriptor in tuple(vars(value).items())
    if type(descriptor) in (classmethod,staticmethod) and inspect.isfunction(descriptor.__func__))
_FROZEN_DATA_ITEMS = tuple((_inputs_module,name,tuple(sorted(getattr(_inputs_module,name).items())))
    for name in ('_FIXED_PHASE_SHAS','_LIMITS'))

_FROZEN_LITERALS = tuple((vars(module), name, getattr(module, name))
    for module, names in ((sources, ('PREUPLOAD_ENTRY_ADOPTION', 'BOOTSTRAP_KEYS', 'BOOTSTRAP_BODY',
        'WRAPPER_KEYS', 'WRAPPER_BODY', 'MAX_SOURCE', '_HASH')),
        (protocol, ('PURPOSE', 'METHODS', 'MAX_SEQUENCE', '_HASH', '_ID', '_COMMON')),
        (_qa_module, ('CONSUMER_FILES','CONTRACT_SHA256','_QUALIFIED')),
        (_inputs_module, ('KEY_TABLE_SHA','JOURNAL_SHA','_ORIGINAL_KEYS')))
    for name in names)
