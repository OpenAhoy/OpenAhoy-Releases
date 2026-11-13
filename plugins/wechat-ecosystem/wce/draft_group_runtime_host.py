"""Private Group host: actual held descriptors, Owned transactions and issue registry.

No public tool, path discovery, migration, credential or network effect lives here.
Objects constructed by callers are facts; only the live host registry issues context.
"""
from . import draft_group_operator_time_v2 as time06
from .own_fd_domain import regular_fd_domain
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import time
from types import MethodType

from .contracts import WCEError
from .bounded_file import FileSource, file_state
from .own_bootstrap_security import path_check
from .own_connection_policy import ConnectionPolicy, locked
from .own_connection_token import TokenCache, CachedToken, ContinuousClock
from .own_connection_broker import AccountService, Broker, _ClientCancellationGuard, locator_client_guard
from .own_connection_workflow import PersistentWorkflow
from .own_store import OwnStore, _check_legacy_history_in
from .own_validation_scope import OwnedConnection, _transaction_marker
from .publication_lock import draft_writer, _writer_guard, _OWNED
from .draft_group_contracts import digest, canonical
from .draft_group_pin_resources import PinPool, CodePins, close_all, capacity as pin_capacity
from .draft_group_artifact_resources import ArtifactResources

_TIME=time.time; _MONOTONIC=time.monotonic; _THREAD=threading.get_ident
_STOP_EVENT=threading.Event;_STOP_IS_SET=threading.Event.is_set;_NATIVE_CANCEL=_ClientCancellationGuard;_CANCEL_DETECTOR=locator_client_guard
_ACTIVE=threading.local()
_REGISTRY={}
_HISTORY_ISSUED={}
_ADMISSION_SCOPE_ISSUED={}
_HOST_NATIVE_TCB=()
_HOST_NATIVE_CLOSURES=()
_HOST_FD_DOMAIN_ALIASES=()


def hold(code='GROUP_HOST_HOLD'):
    raise WCEError(code)


def need(value, code='GROUP_HOST_HOLD'):
    if value is not True: hold(code)


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def _method(value, cls, name):
    selected=getattr(value,name,None)
    return type(value) is cls and name not in getattr(value,'__dict__',{}) and type(selected) is MethodType and selected.__func__ is getattr(cls,name)


_FIXED_REFERENCES=(AccountService._init_mechanical,AccountService._init_storage,AccountService.guard,
    AccountService.profile,AccountService._profile_values,AccountService.set_guard,ConnectionPolicy.check,TokenCache.__init__,TokenCache.valid,
    Broker.guard,Broker._listener_initialized,Broker._accept_loop,PersistentWorkflow.activate,PersistentWorkflow._network,PersistentWorkflow._sender_provenance,
    _STOP_IS_SET,_ClientCancellationGuard.__call__,locator_client_guard)

_FIXED_CODE_REFERENCES=tuple((fn,fn.__code__) for fn in _FIXED_REFERENCES)


def _assert_fixed_references():
    for module,name,original in _HOST_FD_DOMAIN_ALIASES:
        need(vars(module).get(name) is original,'GROUP_FD_DOMAIN_CODE_CHANGED')
    for fn,code,cells in _HOST_NATIVE_CLOSURES:
        need(fn.__code__ is code and all(cell.cell_contents is original for cell,original in cells),
             'GROUP_HOST_NATIVE_CODE_CHANGED')
    for module,functions,classes in _HOST_NATIVE_TCB:
        for name,original,code in functions:
            need(vars(module).get(name)is original and original.__code__ is code,'GROUP_HOST_NATIVE_CODE_CHANGED')
        for name,original,bases,mro,attributes,codes in classes:
            need(vars(module).get(name)is original and original.__bases__==bases and original.__mro__==mro
                 and dict(vars(original))==attributes
                 and all(fn.__code__ is code for fn,code in codes),'GROUP_HOST_NATIVE_CODE_CHANGED')
    need((AccountService._init_mechanical,AccountService._init_storage,AccountService.guard,
        AccountService.profile,AccountService._profile_values,AccountService.set_guard,ConnectionPolicy.check,TokenCache.__init__,TokenCache.valid,
        Broker.guard,Broker._listener_initialized,Broker._accept_loop,PersistentWorkflow.activate,PersistentWorkflow._network,PersistentWorkflow._sender_provenance,
        threading.Event.is_set,_ClientCancellationGuard.__call__,locator_client_guard)==_FIXED_REFERENCES
         and all(fn.__code__ is code for fn,code in _FIXED_CODE_REFERENCES)
         and (GroupExecutionGate.held_pure,GroupExecutionGate.full_guard,GroupExecutionGate.loop_guard)==_GROUP_GATE_REFERENCES
         and all(fn.__code__ is code for fn,code in _GROUP_GATE_CODE_REFERENCES),'GROUP_HOST_CODE_CHANGED')



class PinnedFile:
    """Keep actual NOFOLLOW FD and every parent FD through a joint final fence."""
    def __init__(self,path,expected_sha,maximum,*,pool=None,owner=None):
        self.path=Path(path); self.fds=[]; self.chain=[]; self.closed=False; self._view=None
        if pool is not None:
            need(type(pool) is PinPool and owner is not None,'GROUP_PIN_POOL_REQUIRED')
            try:
                self._view=pool.acquire(self.path,expected_sha,maximum,owner=owner)
                self.fd=self._view.fd;self.parent=pool._leaves[self.path].parent;self.name=self.path.name
                self.pin=file_state(os.fstat(self.fd));self.raw=self._view.raw;self.sha=expected_sha
                self.check();return
            except BaseException as original:
                close_all((self.close,),original);raise
        need(owner is None,'GROUP_PIN_POOL_REQUIRED')
        need(self.path.is_absolute() and '..' not in self.path.parts,'GROUP_HOST_FILE_PATH')
        try:
            parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);self.fds.append(parent)
            for part in self.path.parts[1:-1]:
                fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
                self.fds.append(fd);self.chain.append((parent,part,fd));parent=fd
            self.parent=parent;self.name=self.path.name
            self.fd=os.open(self.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);self.fds.append(self.fd)
            info=os.fstat(self.fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
                 and stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=maximum,'GROUP_HOST_FILE_TYPE')
            self.pin=file_state(info); raw=bytearray()
            while len(raw)<=maximum:
                part=os.read(self.fd,min(65536,maximum+1-len(raw)))
                if not part:break
                raw.extend(part)
            self.raw=bytes(raw)
            need(len(raw)==info.st_size and sha256(raw).hexdigest()==expected_sha,'GROUP_HOST_FILE_SHA')
            self.sha=expected_sha;self.check()
        except BaseException as original:
            close_all((self.close,),original);raise
    def check(self):
        need(not self.closed,'GROUP_HOST_FILE_CLOSED')
        if self._view is not None:
            view=self._view
            view.check()
            # The checked view already authenticated this exact issued record.
            # Read its immutable fields directly, avoiding recursive checks in
            # fd/sha/raw property access within this same mechanical boundary.
            record=view._record
            need(self.path==record.path and self.fd==record.fd and self.sha==record.checksum
                 and self.raw==record.raw and self.pin==file_state(os.fstat(self.fd)),
                 'GROUP_HOST_FILE_CHANGED')
            return
        for parent,name,fd in self.chain:
            a=os.fstat(fd);b=os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISDIR(b.st_mode) and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'GROUP_HOST_FILE_CHANGED')
        a=os.fstat(self.fd);b=os.stat(self.name,dir_fd=self.parent,follow_symlinks=False)
        need(file_state(a)==self.pin==file_state(b) and stat.S_ISREG(b.st_mode)
             and b.st_uid==os.getuid() and stat.S_IMODE(b.st_mode)==0o600,'GROUP_HOST_FILE_CHANGED')
    def close(self):
        if not self.closed:
            self.closed=True
            if self._view is not None:self._view.close()
            else:close_all(tuple(lambda fd=fd:os.close(fd) for fd in reversed(self.fds)))
            self.fds=[]


class _GroupMechanicalPins:
    """Actual retained files for mechanical loop checks, never a permission cache.

    Full guards still execute original policy/code/runtime readers. This set
    only detects physical changes between those complete boundaries and keeps
    every descriptor until the same entry closes.
    """
    def __init__(self,entry):
        self.entry=entry;self.fds=[];self.directories={};self.files={};self.absent=[];self.runtime=None;self._code_pins=None
        self.code_root=Path(__file__).resolve().parent
        try:
            self._code_pins=CodePins(self.code_root,entry.pin_pool,owner=entry)
            self.code_names=self._code_pins.names
            policy=entry.policy;self._file(policy.path)
            registry=Path(policy.value['registry_path']);self._file(registry)
            if policy.value['schema']==2:
                from .own_connection_registry import OWNER,transaction_path,revocation_path
                self._file(registry.parent/OWNER);self._file(transaction_path(registry,policy.value['transaction']))
                self._file(policy.root/'profile.json')
                revoked=revocation_path(policy);parent=self._directory(revoked.parent)
                need(not os.path.lexists(revoked),'CONNECTION_DISCONNECTED');self.absent.append((parent,revoked.name))
        except BaseException as original:
            self.close(original=original);raise
    def _directory(self,path):
        if path in self.directories:return self.directories[path][0]
        pool=self.entry.pin_pool;pool._guard(self.entry)
        fd=pool.directory(path,owner=self.entry)
        item=pool._directories[path];info=os.fstat(fd)
        self.directories[path]=(fd,item.parent,item.name,(info.st_dev,info.st_ino,info.st_uid,info.st_mode))
        return fd
    def _file(self,path):
        path=Path(path)
        if path in self.files:return
        parent=self._directory(path.parent)
        pin_capacity(1,persistent=True)
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);self.fds.append(fd)
        info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'GROUP_LOOP_FILE_TYPE')
        self.files[path]=(fd,parent,path.name,file_state(info),info.st_uid,info.st_mode)
    def bind_runtime(self,broker):
        need(self.runtime is None,'GROUP_LOOP_RUNTIME_ALREADY_BOUND')
        from .own_connection_broker import RUNTIME
        self._file(self.entry.policy.root/RUNTIME)
        path=broker.socket_path;parent=self._directory(path.parent);info=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        need(stat.S_ISSOCK(info.st_mode),'GROUP_LOOP_SOCKET_TYPE')
        self.runtime=(broker,broker.stop,path,parent,(info.st_dev,info.st_ino,info.st_uid,info.st_mode),canonical(broker.runtime),broker.runtime_pin,broker.socket_pin)
    def check(self):
        for fd,parent,name,pin in self.directories.values():
            a=os.fstat(fd);b=os.fstat(fd) if parent is None else os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISDIR(b.st_mode) and (a.st_dev,a.st_ino,a.st_uid,a.st_mode)==pin==(b.st_dev,b.st_ino,b.st_uid,b.st_mode),'GROUP_LOOP_ANCESTOR_CHANGED')
        for fd,parent,name,pin,uid,mode in self.files.values():
            a=os.fstat(fd);b=os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISREG(b.st_mode) and file_state(a)==pin==file_state(b)
                 and a.st_uid==uid==b.st_uid and a.st_mode==mode==b.st_mode,'GROUP_LOOP_FILE_CHANGED')
        self._code_pins.check()
        for parent,name in self.absent:
            try:os.stat(name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:hold('CONNECTION_DISCONNECTED')
        if self.runtime is not None:
            broker,stop,path,parent,pin,value,runtime_pin,socket_pin=self.runtime
            need(self.entry.broker is broker and broker.stop is stop and broker.service is self.entry.service
                 and canonical(broker.runtime)==value and broker.runtime_pin==runtime_pin and broker.socket_pin==socket_pin,'GROUP_LOOP_RUNTIME_CHANGED')
            info=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISSOCK(info.st_mode) and (info.st_dev,info.st_ino,info.st_uid,info.st_mode)==pin,'GROUP_LOOP_RUNTIME_CHANGED')
    def close(self,*,original=None):
        callbacks=[lambda fd=fd:os.close(fd) for fd in reversed(self.fds)];self.fds=[]
        if self._code_pins is not None:callbacks.append(self._code_pins.close)
        close_all(callbacks,original)


@dataclass(frozen=True)
class ExistingHistoryStoreView:
    path: Path
    history_policy: ConnectionPolicy


class BootstrapAccountCore:
    """Mechanical fields only. Never an AccountService or a Group grant."""
    def __init__(self,policy):
        need(type(policy) is ConnectionPolicy,'GROUP_BOOTSTRAP_POLICY')
        self.policy,self.tokens=policy,TokenCache(policy)
        self.serial=threading.Lock()
        self._constructor=(AccountService._init_mechanical,AccountService._init_storage,TokenCache)


def _typed_inventory(db):
    tables=db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    result=[]
    def cell(value):
        if type(value) is bytes:return ['blob',len(value),sha256(value).hexdigest()]
        need(value is None or type(value) in (str,int,float),'GROUP_BOOTSTRAP_SQL_CELL')
        if type(value) is float:need(math.isfinite(value),'GROUP_BOOTSTRAP_SQL_CELL')
        return [type(value).__name__,value]
    for table in tables:
        name=table[0];quoted='"'+name.replace('"','""')+'"'
        rows=[[cell(v) for v in row] for row in db.execute('SELECT * FROM '+quoted)]
        rows.sort(key=lambda row:json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False))
        result.append([name,table[1],rows])
    return canonical(result)


@contextmanager
def cold_history_snapshot_fixed(policy,entry):
    """Owned read-only full schema9/legacy validation; no business constructor."""
    entry.held_pure();need(type(policy) is ConnectionPolicy and policy is entry.policy)
    path=policy.root/'state.sqlite3';pin=path_check(path)
    from .own_history_source import owned_connection
    from .own_history_locators import history_scope
    with owned_connection(path,readonly=True,isolation_level=None) as db:
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            from .draft_group_history_context import history_policy_context,physical_material_scope
            with history_policy_context(path,db,policy), physical_material_scope(db,policy,entry), history_scope(policy,db) as history_locators:
                need(db.execute('PRAGMA user_version').fetchone()[0]==9,'GROUP_BOOTSTRAP_SCHEMA9_REQUIRED')
                source_kind=getattr(entry,'source_kind',None)
                need(source_kind==db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0],'GROUP_BOOTSTRAP_SOURCE_KIND')
                OwnStore.check(db,source_kind,policy,history=history_locators)
                _check_legacy_history_in(db,source_kind,ExistingHistoryStoreView(path,policy),history=history_locators)
                account=policy.data['appid']
                rows=db.execute('SELECT * FROM own_resources WHERE account=?',(account,)).fetchall()
                need(len(rows)==1 and rows[0]['resource']==policy.data['resource_id'],'GROUP_BOOTSTRAP_RESOURCE_REQUIRED')
                entry.held_pure();need(path_check(path)==pin,'GROUP_BOOTSTRAP_DB_CHANGED')
                yield db,history_locators
                entry.held_pure();need(path_check(path)==pin,'GROUP_BOOTSTRAP_DB_CHANGED')
        finally:
            if db.in_transaction:db.rollback()

@dataclass(frozen=True,eq=False)
class BootstrapStorageQualification:
    entry: object=field(repr=False)
    inventory: bytes=field(repr=False)
    source: object=field(repr=False)


@dataclass(frozen=True,eq=False)
class BootstrapSourceInspection:
    host: object=field(repr=False)
    entry: object=field(repr=False)
    facts_sha: str
    semantic_scope_sha: str
    not_after: float
    authority: bool=False


@dataclass(frozen=True,eq=False)
class QualifiedGroupSource:
    host: object=field(repr=False)
    entry: object=field(repr=False)
    facts_sha: str
    semantic_scope_sha: str
    not_after: float
    authority: bool=False


@dataclass(frozen=True,eq=False)
class TokenUseScope:
    source: QualifiedGroupSource=field(repr=False)
    family_id: str
    registration_id: str
    purpose_instance_id: str
    phase: str
    use: dict=field(repr=False)
    authority: bool=False


@dataclass(frozen=True,eq=False)
class GroupCurrentContext:
    entry_id: str
    thread_id: int
    db: object=field(repr=False)
    transaction_epoch: object=field(repr=False)
    binding_sha: str
    platform_account_sha: str
    credential_binding_sha: str
    source_snapshot_sha: str
    source_rights_expiry: object
    semantic_scope_sha: str
    family_id: str
    registration_id: str
    purpose_instance_id: str
    phase: str
    host: object=field(repr=False)
    source: object=field(repr=False)
    token_use: object=field(repr=False)
    authority: bool=False


class GroupExecutionGate:
    """Independent acquisition. Does not enter or inherit RevisionExecutionGate."""
    def __init__(self,service,received_deadline,native_cancel,*,broker=None):
        need(type(service) in (AccountService,BootstrapAccountCore),'GROUP_SERVICE_REQUIRED')
        need(_finite(received_deadline) and _MONOTONIC()<received_deadline<=_MONOTONIC()+300.001,'GROUP_DEADLINE')
        if type(service) is AccountService:need(type(service.workflow) is PersistentWorkflow,'GROUP_SERVICE_REQUIRED')
        self.service=service;self.core=service;self.policy=service.policy;self.broker=broker
        self.deadline=received_deadline;self.cancel=native_cancel;self.stack=ExitStack();self.closed=True;self.poisoned=False
        self.thread=_THREAD();self.id=os.urandom(24).hex();self.issued={};self.pins=[];self.observer=None
        self.pre_storage=type(service) is BootstrapAccountCore;self._bound=False;self.listener_bound=type(service) is AccountService and broker is not None
    def __enter__(self):
        need(getattr(_ACTIVE,'entry',None) is None,'GROUP_ENTRY_NESTED')
        need(type(self.policy) is ConnectionPolicy,'GROUP_POLICY_REQUIRED')
        try:
            self.stack.enter_context(regular_fd_domain(deadline=self.deadline,
                stop=None if self.broker is None else self.broker.stop))
            remaining=self.deadline-_MONOTONIC();need(remaining>0,'GROUP_DEADLINE')
            need(self.core.serial.acquire(timeout=remaining),'GROUP_QUEUE_EXPIRED')
            self.stack.callback(self.core.serial.release)
            self.stack.enter_context(draft_writer(self.policy.root,self.policy.data['appid']))
            self.writer_guard=_writer_guard(self.policy.root,self.policy.data['appid'])
            self.policy_fd=self.stack.enter_context(locked(self.policy.root/'connection-policy.lock',nonblocking=True))
            self.policy_pin=path_check(self.policy.root/'connection-policy.lock')
            key=(str(self.policy.root.absolute()),self.policy.data['appid'].casefold())
            self.writer_descriptors=_OWNED.fd_scopes[key]
            self.writer_marker=_OWNED.scopes[key]
            from .draft_group_input_files import _plain
            _plain(self.policy.value);_plain(self.policy.data)
            self.policy_value=canonical(self.policy.value);self.policy_data=canonical(self.policy.data)
            self.closed=False;_ACTIVE.entry=self;_REGISTRY[self.id]=self
            self.pin_pool=PinPool(self)
            self.artifact_resources=ArtifactResources(self.pin_pool,owner=self)
            self._mechanical_pins=_GroupMechanicalPins(self)
            if self.listener_bound:self._mechanical_pins.bind_runtime(self.broker)
            self.full_guard();return self
        except BaseException as original:
            self.close(original=original);raise
    def __exit__(self,kind,original,tb):self.close(original=original)
    def held_pure(self):
        _assert_fixed_references()
        need(not self.closed and not self.poisoned and self.thread==_THREAD()
             and getattr(_ACTIVE,'entry',None) is self and _REGISTRY.get(self.id) is self,'GROUP_ENTRY_NOT_HELD')
        need(self.core.serial is self.service.serial and self.core.tokens is self.service.tokens
             and self.core.policy is self.policy is self.service.policy,'GROUP_ENTRY_OBJECT_CHANGED')
        need(_method(self.policy,ConnectionPolicy,'check'),'GROUP_POLICY_CODE_CHANGED')
        if not self.pre_storage:
            need(_method(self.service,AccountService,'guard') and _method(self.service,AccountService,'profile') and _method(self.service.workflow,PersistentWorkflow,'activate'),'GROUP_SERVICE_CODE_CHANGED')
            need(_method(self.service.workflow,PersistentWorkflow,'_network') and _method(self.service.workflow,PersistentWorkflow,'_sender_provenance'),'GROUP_SERVICE_CODE_CHANGED')
        need(canonical(self.policy.value)==self.policy_value and canonical(self.policy.data)==self.policy_data,'GROUP_POLICY_CHANGED')
        path=self.policy.root/'connection-policy.lock';info=os.fstat(self.policy_fd);actual=path.lstat()
        need(file_state(info)[:2]==self.policy_pin[:2]==file_state(actual)[:2] and info.st_nlink==actual.st_nlink==1
             and stat.S_IMODE(info.st_mode)==stat.S_IMODE(actual.st_mode)==0o600 and info.st_uid==actual.st_uid==os.getuid(),'GROUP_LOCK_CHANGED')
        for path,fd,pin in self.writer_descriptors:
            a=os.fstat(fd);b=path.lstat()
            need((a.st_dev,a.st_ino)==pin==(b.st_dev,b.st_ino) and a.st_nlink==b.st_nlink==1
                 and stat.S_IMODE(a.st_mode)==stat.S_IMODE(b.st_mode)==0o600 and a.st_uid==b.st_uid==os.getuid(),'GROUP_LOCK_CHANGED')
        key=(str(self.policy.root.absolute()),self.policy.data['appid'].casefold())
        need(_OWNED.fd_scopes.get(key) is self.writer_descriptors and _OWNED.scopes.get(key)==self.writer_marker,'GROUP_LOCK_CHANGED')
        need(_MONOTONIC()<self.deadline,'GROUP_DEADLINE')
        if self.broker is not None:
            stop=self.broker.stop
            need(threading.Event is _STOP_EVENT and type(stop) is _STOP_EVENT and 'is_set' not in vars(stop),'GROUP_LOOP_STOP_TCB')
            need(not _STOP_IS_SET(stop),'CONNECTION_STOPPED')
        for pin in self.pins:pin.check()
        mechanical=getattr(self,'_mechanical_pins',None)
        if mechanical is not None:mechanical.check()
        return True
    def _fixed_live_chain(self):
        if self.pre_storage or not self.listener_bound or type(self.broker) is not Broker:return False
        live=self.service.workflow.live_guard
        return (_method(self.service,AccountService,'guard') and _method(self.broker,Broker,'guard')
            and type(live) is MethodType and live.__self__ is self.broker and live.__func__ is Broker.guard
            and self.broker.service is self.service and self.broker.policy is self.policy)
    def full_guard(self):
        self.held_pure();self.writer_guard()
        if self._fixed_live_chain():
            # This original service guard includes its original policy check,
            # actual Broker.guard and read_runtime's complete policy check.
            # Do not run that identical chain twice in this fixed function.
            if self.cancel is not None:self.cancel()
            self.service.guard(self.deadline)
        else:
            self.policy.check()
            if self.cancel is not None:self.cancel()
            if not self.pre_storage:self.service.guard(self.deadline)
            if self.broker is not None and self.listener_bound:self.broker.guard()
        self.held_pure();return True
    def loop_guard(self):
        # Unknown callbacks retain the complete original mechanical path.
        if self.cancel is not None and type(self.cancel) is not _NATIVE_CANCEL:return self.full_guard()
        if not self.pre_storage and not self._fixed_live_chain():return self.full_guard()
        self.held_pure()
        if self.broker is not None:
            stop=self.broker.stop
            need(threading.Event is _STOP_EVENT and type(stop) is _STOP_EVENT and 'is_set' not in vars(stop),'GROUP_LOOP_STOP_TCB')
            need(not _STOP_IS_SET(stop),'CONNECTION_STOPPED')
        if self.cancel is not None:_CANCEL_DETECTOR(self.cancel.client)
        self.held_pure();return True
    def bind_complete_service(self,service,qualification):
        self.held_pure()
        need(self.pre_storage and not self._bound and type(service) is AccountService
             and self.issued.get(id(qualification)) is qualification,'GROUP_BOOTSTRAP_QUALIFICATION')
        need(service.policy is self.policy and service.tokens is self.core.tokens and service.serial is self.core.serial
             and type(service.workflow) is PersistentWorkflow,'GROUP_BOOTSTRAP_SERVICE')
        self.service=service;self.pre_storage=False;self._bound=True
        self.issued.pop(id(qualification));self.held_pure()
    @classmethod
    def from_bound_bootstrap(cls,entry,complete_binding):
        need(type(entry) is cls and entry._bound and entry.issued.get(id(complete_binding)) is complete_binding,'GROUP_BOOTSTRAP_BINDING')
        entry.full_guard();return entry
    def close(self,*,original=None):
        if self.closed:
            close_all((self.stack.close,),original);return
        pins=tuple(self.pins)
        def clear_before():
            if type(self.service) is AccountService:
                self.service.workflow.active_lease=None;self.service.workflow.active_token=None;self.service.workflow.execution_deadline=None
            try:
                from .draft_group_transport import discard_current_thread_prepared
                discard_current_thread_prepared()
            except ImportError:pass
            for key,value in tuple(_ADMISSION_SCOPE_ISSUED.items()):
                if value[0].entry is self:_ADMISSION_SCOPE_ISSUED.pop(key,None)
            self.issued.clear()
        def clear_after():
            self.pins=[];self.closed=True;_REGISTRY.pop(self.id,None)
            from . import draft_group_token_runtime as tr
            for key,value in tuple(tr._CONTROLLERS.items()):
                if value.entry is self:tr._CONTROLLERS.pop(key,None);tr._CONTINUATIONS.pop(key,None)
            for key,value in tuple(tr._OWNERS.items()):
                if value.controller.entry is self:
                    tr._OWNERS.pop(key,None);tr._OWNER_FACTS.pop(key,None);tr._OWNER_USED.discard(key)
            for key,value in tuple(_BUSINESS_CONTINUATIONS.items()):
                if value.scope.entry is self:
                    _BUSINESS_CONTINUATIONS.pop(key,None);_PENDING_CONTINUATIONS.pop(id(value.pending),None);_CONTINUATION_OWNERS.pop(key,None)
            for key,value in tuple(_BUSINESS_OWNERS.items()):
                if value.continuation.scope.entry is self:_BUSINESS_OWNERS.pop(key,None)
            if getattr(_ACTIVE,'entry',None) is self:_ACTIVE.entry=None
        callbacks=([self.observer.close] if self.observer is not None else [])
        callbacks += [clear_before,*[pin.close for pin in pins],clear_after]
        # Keep each new resource close at this level: ExitStack would replace
        # its first cleanup failure with a later callback failure.
        mechanical=getattr(self,'_mechanical_pins',None)
        artifacts=getattr(self,'artifact_resources',None)
        pool=getattr(self,'pin_pool',None)
        if mechanical is not None:callbacks.append(lambda:mechanical.close(original=original))
        if artifacts is not None:callbacks.append(lambda:artifacts.close(original=original))
        if pool is not None:callbacks.append(lambda:pool.close(owner=self,original=original))
        callbacks.append(self.stack.close)
        close_all(callbacks,original)



_GROUP_GATE_REFERENCES=(GroupExecutionGate.held_pure,GroupExecutionGate.full_guard,GroupExecutionGate.loop_guard)
_GROUP_GATE_CODE_REFERENCES=tuple((fn,fn.__code__) for fn in _GROUP_GATE_REFERENCES)


def validate_current_context(context,*,db=None,entry=None):
    need(type(context) is GroupCurrentContext,'GROUP_CURRENT_CONTEXT_REQUIRED')
    actual=_REGISTRY.get(context.entry_id)
    need(actual is not None and (entry is None or actual is entry) and actual.issued.get(id(context)) is context,'GROUP_CURRENT_CONTEXT_UNISSUED')
    actual.held_pure();need(not actual.pre_storage and actual.listener_bound,'GROUP_COMPLETE_LISTENER_REQUIRED');need(context.thread_id==_THREAD(),'GROUP_CURRENT_CONTEXT_THREAD')
    need(type(context.db) is OwnedConnection and context.db.in_transaction and _transaction_marker(context.db)==context.transaction_epoch
         and (db is None or context.db is db),'GROUP_CURRENT_CONTEXT_TRANSACTION')
    need(context.host.entry is actual and actual.issued.get(id(context.source)) is context.source,'GROUP_CURRENT_CONTEXT_SOURCE')
    return context


def qualify_bootstrap_storage(host,core,entry):
    need(type(core) is BootstrapAccountCore and entry.core is core and entry.pre_storage,'GROUP_BOOTSTRAP_CORE')
    source=host.qualify_current_group_source(initial=True)
    with cold_history_snapshot_fixed(core.policy,entry) as (db, history_locators):
        host.validate_history_in(db, history_locators=history_locators)
        inventory=_typed_inventory(db)
    entry.held_pure()
    value=BootstrapStorageQualification(entry,inventory,source);entry.issued[id(value)]=value
    return value


def from_verified_bootstrap(core,entry,qualification):
    need(type(core) is BootstrapAccountCore and type(qualification) is BootstrapStorageQualification
         and qualification.entry is entry and entry.core is core,'GROUP_BOOTSTRAP_QUALIFICATION')
    entry.held_pure();need(entry.issued.get(id(qualification)) is qualification,'GROUP_BOOTSTRAP_QUALIFICATION')
    need(core.tokens.cached is None and core.tokens.credential is None,'GROUP_BOOTSTRAP_TOKEN_FORBIDDEN')
    qualification.source.host.current_no_token_in(None,qualification.source,initial=True, history_locators=None)
    service=object.__new__(AccountService)
    service.policy,service.tokens,service.serial=core.policy,core.tokens,core.serial
    if entry.source_kind=='SYNTHETIC_SETUP':
        from .draft_group_rich_syn_fixture import rich_syn_storage_profile_in
        with rich_syn_storage_profile_in(service,core,entry,qualification):service._init_storage(core.policy,physical_resources=entry)
    else:service._init_storage(core.policy,physical_resources=entry)
    entry.held_pure()
    with cold_history_snapshot_fixed(core.policy,entry) as (db, history_locators):
        qualification.source.host.validate_history_in(db, history_locators=history_locators)
        need(_typed_inventory(db)==qualification.inventory,'GROUP_BOOTSTRAP_INVENTORY_CHANGED')
    need(core.tokens.cached is None,'GROUP_BOOTSTRAP_TOKEN_FORBIDDEN')
    entry.bind_complete_service(service,qualification)
    return service


# Keep the factory private and exact; ordinary __init__ still calls both leaves.
AccountService._from_verified_bootstrap=staticmethod(from_verified_bootstrap)


def validate_source_fact_admission(context,*,db,candidate, history_locators=None):
    ctx=validate_current_context(context,db=db)
    ctx.host.current_no_token_in(db,ctx.source,token_use=ctx.token_use, history_locators=history_locators)
    expected=getattr(ctx.host.entry,'source_candidates',{}).get(digest(candidate))
    need(expected is not None and expected[0] is ctx and expected[1]==canonical(candidate),'GROUP_SOURCE_FACT_NOT_ISSUED')


def validate_token_admission(context,*,db,candidate, history_locators=None):
    ctx=validate_current_context(context,db=db)
    if ctx.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP':
        from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
        require_rich_syn_domain_for_entry(ctx.host.entry)
    need(ctx.token_use is not None and ctx.host.entry.issued.get(id(ctx.token_use)) is ctx.token_use,'GROUP_TOKEN_USE_REQUIRED')
    ctx.host.current_no_token_in(db,ctx.source,token_use=ctx.token_use, history_locators=history_locators)
    expected=getattr(ctx.host.entry,'token_candidates',{}).get(digest(candidate))
    need(expected is not None and expected[0] is ctx and expected[1]==canonical(candidate),'GROUP_TOKEN_CANDIDATE_NOT_ISSUED')
    need(canonical(candidate['use'])==canonical(ctx.token_use.use),'GROUP_TOKEN_USE_CHANGED')


def validate_source_fact_history_in(db,candidate,history_policy):
    from .draft_group_host_history import validate_source_fact_history_in as check
    return check(db,candidate,history_policy)


def validate_token_history_in(db,candidate,history_policy):
    from .draft_group_host_history import validate_token_history_in as check
    return check(db,candidate,history_policy)


def validate_token_historical_receipt(receipt,*,db):
    value=_HISTORY_ISSUED.get(id(receipt))
    need(value is not None and value[0] is receipt and value[1] is db and value[2]==_THREAD(),'GROUP_TOKEN_HISTORY_RECEIPT_REQUIRED')
    return json.loads(value[3])


def validate_used_transport_owner(owner,prepared):
    from .draft_group_token_runtime import _validate_used_owner
    return _validate_used_owner(owner,prepared)


@dataclass(frozen=True,eq=False)
class GroupHistoryContext:
    entry: object=field(repr=False)
    policy: object=field(repr=False)
    db: object=field(repr=False)
    transaction_epoch: object=field(repr=False)
    thread_id: int


def issue_history_context_in(host,db):
    host.entry.held_pure()
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'GROUP_HISTORY_TRANSACTION')
    from .draft_group_history_context import current_history_policy
    need(current_history_policy(db) is host.entry.policy,'GROUP_HISTORY_POLICY_REQUIRED')
    value=GroupHistoryContext(host.entry,host.entry.policy,db,_transaction_marker(db),_THREAD())
    host.entry.issued[id(value)]=value
    return value


def validate_history_context(actual_history_policy,actual_writer_context,db=None):
    x=actual_writer_context
    need(type(x) is GroupHistoryContext and type(actual_history_policy) is ConnectionPolicy
         and x.policy is actual_history_policy and x.thread_id==_THREAD()
         and _REGISTRY.get(x.entry.id) is x.entry and x.entry.issued.get(id(x)) is x,'GROUP_HISTORY_CONTEXT_UNISSUED')
    # Already admitted result archival survives source invalidation. It retains
    # its original live descriptors and never creates a new effect owner.
    need(not x.entry.closed and x.entry.thread==_THREAD() and x.db.in_transaction
         and _transaction_marker(x.db)==x.transaction_epoch and (db is None or db is x.db),'GROUP_HISTORY_CONTEXT_TRANSACTION')
    for path,fd,pin in x.entry.writer_descriptors:
        info=os.fstat(fd);actual=path.lstat()
        need((info.st_dev,info.st_ino)==pin==(actual.st_dev,actual.st_ino),'GROUP_HISTORY_LOCK_CHANGED')
    return x


def validate_token_query_context(db,history_reader,root_closure,token_job_id):
    from .draft_group_read_family_store import require_closure,recover_family_in
    need(type(db) is OwnedConnection and db.in_transaction and root_closure is not None,'GROUP_TOKEN_ROOT_REQUIRED')
    require_closure(root_closure,db,root_closure.files)
    need(root_closure.files.policy is not None,'GROUP_TOKEN_ROOT_REQUIRED')
    original=json.loads(root_closure.origin_raw)
    result=recover_family_in(db,root_closure.files,original['origin_request_identity_sha'],
        root_closure=root_closure,guard=root_closure.lock_guard)
    from .draft_group_token_attempt_store import build_token_job_id
    expected=build_token_job_id(root_closure.files.publication.key,result['covenant']['family_anchor_id'],original['origin_request_identity_sha'])
    need(token_job_id==expected,'GROUP_TOKEN_JOB_BINDING')
    return result


@dataclass(frozen=True,eq=False)
class GroupAdmissionScope:
    host: object=field(repr=False)
    entry: object=field(repr=False)
    source: object=field(repr=False)
    context: object=field(repr=False)
    details: dict
    db: object=field(repr=False)
    transaction_epoch: object=field(repr=False)


def _validate_admission_scope_identity_in(scope,db=None):
    need(type(scope) is GroupAdmissionScope and scope.entry.issued.get(id(scope)) is scope,'GROUP_ADMISSION_SCOPE_UNISSUED')
    pin=_ADMISSION_SCOPE_ISSUED.get(id(scope))
    need(pin is not None and pin[0] is scope and pin[1] is scope.source and pin[2] is scope.context
         and pin[3]==canonical(scope.details),'GROUP_ADMISSION_SCOPE_CHANGED')
    scope.entry.held_pure();need(scope.host.entry is scope.entry and scope.source is scope.context.source,'GROUP_ADMISSION_SCOPE_CHANGED')
    if db is not None:
        need(type(db) is OwnedConnection and db.in_transaction,'GROUP_ADMISSION_TRANSACTION')


def _validate_admission_scope_and_current(scope,db=None, *, history_locators=None):
    _validate_admission_scope_identity_in(scope,db)
    # Return this call's actual observation to the fixed TokenUse issuer. It is
    # neither persisted nor reused by another call or effect stage.
    current=None
    if db is not None:
        current=scope.host.current_no_token_in(db,scope.source, history_locators=history_locators)
        scope.host._validate_scope_details_in(db,scope.details, history_locators=history_locators)
    return scope,current


def validate_admission_scope(scope,db=None, *, history_locators=None):
    return _validate_admission_scope_and_current(scope,db, history_locators=history_locators)[0]


def qualify_preview_read_delegation(host,source,first,purpose,db, *, history_locators=None):
    """Recover the actual FIRST purpose/activation/grant, never caller budget."""
    from .draft_group_read_family_store import _gid
    host.current_no_token_in(db,source, history_locators=history_locators)
    info=host._family_in(db, history_locators=history_locators)
    covenant=info['covenant'];matches=[x for x in covenant['purposes'] if x['source_grant_sha']==purpose]
    need(len(matches)==1,'GROUP_PURPOSE_UNRESOLVED');p=matches[0]
    need(p['source_grant_sha'] in info['activations'] and not info['unknown'],'GROUP_PURPOSE_INACTIVE')
    gid=_gid(info['account'],p);state=host._group_state_in(db)
    grant=state['preview_grants'].get(gid);need(grant is not None,'GROUP_PURPOSE_GRANT_REQUIRED')
    preview_id='group-read-purpose-'+p['source_grant_sha']
    details={'ledger_kind':'PREVIEW','account_key':info['account'],'family_id':covenant['family_anchor_id'],
        'purpose_key':p['source_grant_sha'],'gid':gid,'grant_id':gid,'preview_id':preview_id,'operation_id':None,
        'group_input_sha':host._registration['registration_sha'],'source_epoch':digest({'profile':'GROUP_ENTRY_EPOCH_V1','entry_id':host.entry.id}),
        'qualified_not_after_ms':int(min(source.not_after,time.time()+max(0,host.entry.deadline-time.monotonic()))*1000)}
    context=host.current_context_in(db,source, history_locators=history_locators);scope=GroupAdmissionScope(host,host.entry,source,context,details,db,_transaction_marker(db))
    host.entry.issued[id(scope)]=scope
    _ADMISSION_SCOPE_ISSUED[id(scope)]=(scope,source,context,canonical(details));return scope


def qualify_target_preparation(host,source,current,coverage,child,db, *, history_locators=None):
    # The fixed Parent reader issues the exact original execution facts only
    # after its complete persistent/current checks. No plan-dict fallback.
    from .draft_group_parent import validate_parent_execution_in,validate_issued_parent_execution_in
    host.current_no_token_in(db,source, history_locators=history_locators);state=host._group_state_in(db)
    need(type(child) is str and child in state['operations'],'GROUP_CHILD_REQUIRED')
    operation=state['operations'][child];need(operation['state'] not in ('UNKNOWN','HOLD'),'GROUP_RESULT_UNKNOWN')
    execution=validate_parent_execution_in(host,db,child, history_locators=history_locators)
    validate_issued_parent_execution_in(execution,host,db, history_locators=history_locators)
    need(execution.operation_id==child and type(execution.original_not_after_ms) is int
         and execution.original_not_after_ms>0,'GROUP_PARENT_EXECUTION_REQUIRED')
    capsule=execution.capsule_sha
    need(type(capsule) is str and len(capsule)==64,'GROUP_PARENT_EXECUTION_REQUIRED')
    info=host._family_in(db, history_locators=history_locators)
    not_after_ms=min(execution.original_not_after_ms,int(source.not_after*1000),
        int((time.time()+max(0,host.entry.deadline-time.monotonic()))*1000))
    need(time.time()*1000<not_after_ms,'GROUP_PARENT_EXPIRED')
    details={'ledger_kind':'CHILD','account_key':info['account'],'family_id':info['covenant']['family_anchor_id'],
        'purpose_key':'child-'+digest({'family':info['covenant']['family_anchor_id'],'operation':child}),
        'gid':None,'grant_id':None,'preview_id':None,'operation_id':child,'group_input_sha':capsule,
        'source_epoch':digest({'profile':'GROUP_ENTRY_EPOCH_V1','entry_id':host.entry.id}),'qualified_not_after_ms':not_after_ms}
    context=host.current_context_in(db,source, history_locators=history_locators);scope=GroupAdmissionScope(host,host.entry,source,context,details,db,_transaction_marker(db))
    host.entry.issued[id(scope)]=scope
    _ADMISSION_SCOPE_ISSUED[id(scope)]=(scope,source,context,canonical(details));return scope


def validate_target_scope(scope,workflow,db,child, *, history_locators=None):
    validate_admission_scope(scope,db=db, history_locators=history_locators)
    need(scope.details['ledger_kind']=='CHILD' and scope.details['operation_id']==child
         and workflow is scope.entry.service.workflow,'GROUP_TARGET_SCOPE_CHANGED')
    return None


@dataclass(frozen=True,eq=False)
class GroupReaderHistoryContext:
    policy: object=field(repr=False)
    db: object=field(repr=False)
    transaction_epoch: object
    thread_id: int
    database_pin: tuple


_READER_HISTORY={}


def response_history_context_in(db,policy):
    from .draft_group_history_context import current_history_policy
    need(type(policy) is ConnectionPolicy and type(db) is OwnedConnection and db.in_transaction
         and current_history_policy(db) is policy,'GROUP_HISTORY_POLICY_REQUIRED')
    entry=getattr(_ACTIVE,'entry',None)
    if entry is not None and entry.policy is policy:
        value=GroupHistoryContext(entry,policy,None,None,_THREAD());entry.issued[id(value)]=value;return value
    # Complete historical query already holds the actual Owned read transaction.
    # This context authorizes immutable historical reads only, never a writer.
    need(db.execute('PRAGMA query_only').fetchone()[0]==1,'GROUP_HISTORY_READER_REQUIRED')
    value=GroupReaderHistoryContext(policy,db,_transaction_marker(db),_THREAD(),path_check(policy.root/'state.sqlite3'))
    _READER_HISTORY[id(value)]=value;return value


_original_validate_history_context=validate_history_context


def validate_history_context(actual_history_policy,actual_writer_context,db=None):
    x=actual_writer_context
    if type(x) is GroupReaderHistoryContext:
        need(_READER_HISTORY.get(id(x)) is x and x.policy is actual_history_policy and x.thread_id==_THREAD()
             and x.db.in_transaction and _transaction_marker(x.db)==x.transaction_epoch
             and path_check(x.policy.root/'state.sqlite3')==x.database_pin and (db is None or db is x.db),'GROUP_HISTORY_READER_CHANGED')
        return x
    if type(x) is GroupHistoryContext and x.db is None:
        need(x.entry.issued.get(id(x)) is x and not x.entry.closed and x.entry.thread==_THREAD()
             and x.policy is actual_history_policy and _REGISTRY.get(x.entry.id) is x.entry,'GROUP_HISTORY_CONTEXT_UNISSUED')
        for path,fd,pin in x.entry.writer_descriptors:
            a=os.fstat(fd);b=path.lstat();need((a.st_dev,a.st_ino)==pin==(b.st_dev,b.st_ino),'GROUP_HISTORY_LOCK_CHANGED')
        if db is not None:
            from .draft_group_history_context import current_history_policy
            need(type(db) is OwnedConnection and db.in_transaction and current_history_policy(db) is x.policy,'GROUP_HISTORY_TRANSACTION')
        return x
    return _original_validate_history_context(actual_history_policy,x,db=db)


@dataclass(eq=False)
class GroupBusinessContinuation:
    scope: GroupAdmissionScope=field(repr=False)
    pending: object=field(repr=False)
    facts: object=field(repr=False)
    used: bool=False


@dataclass(eq=False)
class GroupBusinessOwner:
    continuation: GroupBusinessContinuation=field(repr=False)
    prepared: object=field(repr=False)
    used: bool=False
    def consume(self,stage,prepared):
        need(stage=='BUSINESS' and prepared is self.prepared and _BUSINESS_OWNERS.get(id(self)) is self
             and not self.used and not self.continuation.used,'GROUP_BUSINESS_OWNER_REQUIRED')
        self.used=True;self.continuation.used=True;return self


_BUSINESS_CONTINUATIONS={};_BUSINESS_OWNERS={};_PENDING_CONTINUATIONS={};_CONTINUATION_OWNERS={}


def mark_known_commit(scope,pending,readback=None):
    validate_admission_scope(scope, history_locators=None)
    from .draft_group_provider import validate_known_commit_pending,KnownCommitFacts
    facts=validate_known_commit_pending(pending,scope)
    need(type(facts) is KnownCommitFacts and facts.scope is scope and facts.normal_commit is True,'GROUP_KNOWN_COMMIT_REQUIRED')
    existing=_PENDING_CONTINUATIONS.get(id(pending))
    if existing is not None:
        need(existing.pending is pending and existing.scope is scope,'GROUP_PENDING_CONTINUATION_CHANGED')
        return existing
    value=GroupBusinessContinuation(scope,pending,facts);_BUSINESS_CONTINUATIONS[id(value)]=value;_PENDING_CONTINUATIONS[id(pending)]=value
    return value


def obtain_group_cached_token(scope):
    validate_admission_scope(scope, history_locators=None)
    from .draft_group_token_runtime import qualify_token_use,GroupTokenAcquisitionController
    host=scope.host
    # Identity above is the original issued-scope gate. This pure material seal
    # selects only an already-mandatory SYN refusal before opening a new SQL
    # owner; positive paths retain every original qualification below.
    from .draft_group_input_files import _plain
    config=host.chain.config
    _plain(config)
    need((canonical(config)+'\n').encode()==host.chain.files['configuration'].raw,
         'GROUP_HOST_MATERIAL_OBJECT_CHANGED')
    kind=config['binding']['source_kind']
    need(kind in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED') and host.entry.source_kind==kind,
         'GROUP_HOST_ACCOUNT_BINDING')
    if kind=='SYNTHETIC_SETUP':
        from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
        require_rich_syn_domain_for_entry(host.entry)
    with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
        use=qualify_token_use(host,scope.source,scope,db, history_locators=history_locators)
    controller=GroupTokenAcquisitionController(host,scope.source,use)
    value=host.entry.service.tokens._get_for_group(controller)
    host._active_group_token=value
    activate_group_token(host,value)
    return value


def issue_business_owner(continuation,prepared):
    need(type(continuation) is GroupBusinessContinuation and _BUSINESS_CONTINUATIONS.get(id(continuation)) is continuation
         and not continuation.used and continuation.facts.prepared is prepared,'GROUP_BUSINESS_CONTINUATION_REQUIRED')
    need(id(continuation) not in _CONTINUATION_OWNERS,'GROUP_BUSINESS_OWNER_ALREADY_ISSUED')
    scope=validate_admission_scope(continuation.scope, history_locators=None);host=scope.host;entry=scope.entry
    from .draft_group_provider import validate_known_commit_pending
    # Any provider bookkeeping/callback/SQL work is before final common fence.
    validate_known_commit_pending(continuation.pending,scope)
    with _history_transaction(entry.service.workflow.db,physical_resources=entry) as (db, history_locators):
        host.current_no_token_in(db,scope.source, history_locators=history_locators)
    token=host._active_group_token;cache=entry.service.tokens
    need(cache.cached is token,'GROUP_TOKEN_CACHE_CHANGED');cache.valid(token,margin=0)
    entry.full_guard();host.observer.prepare_release(host.chain.files['source'].raw)
    from .draft_group_transport import validate_prepared
    validate_prepared(prepared);host.pure_release_fence()
    from .draft_group_token_runtime import _token_pure_valid
    _token_pure_valid(cache,token,0)
    need(_MONOTONIC()<entry.deadline and _TIME()<scope.source.not_after and _MONOTONIC()<prepared.deadline.deadline,'GROUP_BUSINESS_DEADLINE')
    owner=GroupBusinessOwner(continuation,prepared);_BUSINESS_OWNERS[id(owner)]=owner;_CONTINUATION_OWNERS[id(continuation)]=owner;return owner


_token_owner_validate=validate_used_transport_owner


def validate_used_transport_owner(owner,prepared):
    if type(owner) is GroupBusinessOwner:
        need(_BUSINESS_OWNERS.get(id(owner)) is owner and owner.used and owner.continuation.used
             and owner.prepared is prepared and owner.continuation.scope.entry.thread==_THREAD()
             and not owner.continuation.scope.entry.closed,'GROUP_BUSINESS_USED_OWNER_REQUIRED')
        return owner
    return _token_owner_validate(owner,prepared)


def resolve_group_reference_in(db,history_policy,source_fact,subject_sha, *, history_locators=None):
    from .draft_group_history_context import current_history_policy
    from .draft_group_host_history import validate_source_fact_history_in
    from .draft_group_wire import reference_sha
    from .own_workflow import stored
    need(type(db) is OwnedConnection and db.in_transaction and current_history_policy(db) is history_policy,'GROUP_REFERENCE_HISTORY_CONTEXT')
    issued_scope=source_fact if type(source_fact) is GroupAdmissionScope else None
    if issued_scope is not None:
        validate_admission_scope(issued_scope,db=db, history_locators=history_locators)
        details=issued_scope.details
        source_fact={'binding_sha':details['account_key'],'gid':details['gid'],'operation_id':details['operation_id'],
            'claim_selector':{'ledger_kind':details['ledger_kind']},
            'source_descriptor':{'configuration_sha':issued_scope.host.pins.configuration_sha}}
    else:validate_source_fact_history_in(db,source_fact,history_policy)
    from .draft_group_store import _load
    state,_,_=_load(db,source_fact['binding_sha']);need(state is not None,'GROUP_REFERENCE_POOL')
    selector=source_fact['claim_selector'];allowed=set()
    if selector['ledger_kind']=='PREVIEW':
        grant=state['preview_grants'].get(source_fact['gid']);need(grant is not None,'GROUP_REFERENCE_GRANT')
        allowed.update(grant.get('subjects') or grant['registration'].get('subjects') or ())
    elif selector['ledger_kind']=='CHILD':
        op=state['operations'].get(source_fact['operation_id']);need(op is not None,'GROUP_REFERENCE_OPERATION')
        for old in op['old_refs']:allowed.add(old['ref_sha'] if type(old) is dict else old)
        if op.get('new_ref_sha'):allowed.add(op['new_ref_sha'])
    else:hold('GROUP_REFERENCE_SELECTOR')
    need(subject_sha in allowed,'GROUP_REFERENCE_SUBJECT_NOT_ALLOWED')
    values=[];synthetic=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]=='SYNTHETIC_SETUP'
    for row in db.execute("SELECT * FROM own_steps WHERE state='SUCCEEDED' AND operation='add' AND resource=?",(history_policy.data['resource_id'],)):
        result=stored(row['result'],row['result_digest']);reference=result.get('reference')
        if type(reference) is str and reference_sha(reference,synthetic=synthetic)==subject_sha:values.append(reference)
    from .draft_group_operator_semantics import is_operator
    operator_source=(issued_scope is not None and is_operator(issued_scope.host)) or source_fact.get('profile') in ('GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1',time06.SOURCE_FACTS_PROFILE_V2)
    if operator_source:
        if selector['ledger_kind']=='PREVIEW' and grant['registration']['phase']=='DISCOVER':
            from .draft_group_response_files import GroupResponseFiles
            from .draft_group_coverage import _collect_lists
            files=GroupResponseFiles.from_history_context(history_policy,response_history_context_in(db,history_policy))
            compared,_,_=_collect_lists(db,state,grant,files)
            need(list(compared['subject_shas'])==grant['subjects'],'GROUP_REFERENCE_LIST_SUBJECTS_CHANGED')
            values.extend(reference for reference in compared['references']
                          if reference_sha(reference,synthetic=synthetic)==subject_sha)
            files.collective_fence()
        # Reading an exact listed reference does not adopt its content into the
        # managed pool. NEW_ONLY eligibility is still decided after full GET.
        need(len(set(values))==1,'GROUP_OPERATOR_REFERENCE_UNREGISTERED_HOLD')
        return values[0]
    # Old imported saved drafts can be carried by exact adopted local evidence.
    from .draft_group_host_history import _materials
    material_row,paths,config,semantic,source=_materials(history_policy,source_fact['source_descriptor']['configuration_sha'])
    roots=dict(material_row[5])
    for artifact in semantic['artifact_inventory']:
        if artifact['media_type']!='application/json':continue
        root=Path(roots[artifact['root_sha']]);pin=PinnedFile(root/artifact['relative_path'],artifact['sha256'],2*1024*1024)
        try:value=json.loads(pin.raw)
        finally:pin.close()
        if type(value) is dict and value.get('profile') in ('REGISTERED_SAVED_DRAFT_EVIDENCE_V1','GROUP_ORIGINAL_SAVE_EVIDENCE_V1'):
            reference=value.get('reference')
            if type(reference) is str and reference_sha(reference,synthetic=synthetic)==subject_sha:values.append(reference)
    need(len(set(values))==1,'GROUP_REFERENCE_UNRESOLVED')
    return values[0]


# Local D creator gate is deliberately a different type from network scope.
from .draft_group_target_scope import TargetPreparationScope,target_preparation_in,validate_target_preparation_scope


def activate_group_token(host,cached):
    from .draft_group_token_runtime import _token_pure_valid
    entry=host.entry;entry.full_guard();need(type(cached) is CachedToken and entry.service.tokens.cached is cached,'GROUP_TOKEN_ACTIVATION_REQUIRED')
    workflow=entry.service.workflow
    if workflow.active_token is cached and workflow.execution_deadline==entry.deadline:
        return next(iter(workflow.registry.profiles.values())),workflow.active_lease
    host.current_no_token_in(None,host._source, history_locators=None)
    _token_pure_valid(entry.service.tokens,cached,0)
    profile=entry.service.profile(cached)
    workflow.activate(profile,cached,entry.deadline)
    entry.full_guard();return profile,workflow.active_lease

from .draft_group_target_scope import GroupApprovalScope,group_approval_in


def deactivate_group_token_for_local(host):
    entry=host.entry;entry.full_guard();workflow=entry.service.workflow
    profile=next(iter(workflow.registry.profiles.values()));binding=canonical(profile.binding());fence=profile.fence()
    active=workflow.active_token;lease=workflow.active_lease
    if active is not None:
        from .draft_group_token_runtime import _token_pure_valid
        need(entry.service.tokens.cached is active and type(active) is CachedToken,'GROUP_LOCAL_PHASE_TOKEN_CHANGED')
        _token_pure_valid(entry.service.tokens,active,0)
        need(lease is not None and lease.token is active.token and workflow.execution_deadline==entry.deadline,'GROUP_LOCAL_PHASE_LEASE_CHANGED')
    else:need(lease is None,'GROUP_LOCAL_PHASE_LEASE_CHANGED')
    host.current_no_token_in(None,host._source, history_locators=None)
    workflow.active_lease=None;workflow.active_token=None;workflow.execution_deadline=None
    need(profile is next(iter(workflow.registry.profiles.values())) and canonical(profile.binding())==binding and profile.fence()==fence,'GROUP_LOCAL_PHASE_PROFILE_CHANGED')
    entry.full_guard();return profile,None


def publish_first_current(host):
    from .draft_group_host_publisher import publish_first_current as publish
    return publish(host)


def register_first_current_in(host,db,pack, *, history_locators=None):
    from .draft_group_host_publisher import register_first_current_in as register
    return register(host,db,pack, history_locators=history_locators)


from .draft_group_target_scope import (target_before_event_in,target_after_event_in,check_target_designations_in,
    validate_target_write_in,validate_target_approval_in,validate_target_dispatch_in)


from .draft_group_history_context import history_transaction as _history_transaction


from .draft_group_history_context import locator_scope as _history_scope
