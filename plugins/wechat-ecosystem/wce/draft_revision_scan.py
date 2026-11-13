"""Loop-only liveness checks inside the exact held revision execution gate.

No grant, cached source/policy proof or send check. Full guards remain at all
scan boundaries; absent/unknown execution contexts keep the original guard.
"""
import os,stat,threading,time
from .contracts import WCEError
from .own_bootstrap_security import path_check,private_read,decode
from .bounded_file import identity
from .draft_revision_scan_paths import PreparedPolicyPaths


def hold():raise WCEError('DRAFT_REVISION_SCAN_HOLD')

class RevisionScanGuard:
    def __init__(self,service,deadline,full,active):
        self.service,self.deadline,self.original,self.active=service,deadline,full,active
        from .publication_lock import _writer_guard
        self.writer_guard=_writer_guard(service.policy.root,service.policy.data['appid'])
        self.prepared_paths=PreparedPolicyPaths(service.policy)
        self.full()
    def full(self):
        self._held()
        result=self.original()
        if result is not True:hold()
        self._held()
        return True
    def _held(self):
        from .draft_revision_gate import _ACTIVE,RevisionExecutionGate
        active=_ACTIVE.get();gate=self.active[0];policy=self.service.policy
        if (active is not self.active or type(gate) is not RevisionExecutionGate
                or gate._active_entry is not active
                or gate.service is not self.service or active[1]!=threading.get_ident()
                or gate.deadline!=self.deadline or time.monotonic()>=self.deadline):hold()
        if gate.cancel_guard is not None:gate.cancel_guard()
        fd,pin=active[2:];info=os.fstat(fd);path=policy.root/'connection-policy.lock';current=path.lstat()
        if (identity(info)!=pin or identity(current)!=pin or info.st_nlink!=1
                or info.st_uid!=os.getuid() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode)!=0o600 or current.st_mode!=info.st_mode):hold()
        if not self.service.serial.locked() or self.writer_guard() is not True:hold()
    def __call__(self):
        self._held();policy=self.service.policy
        if (self.prepared_paths.check('policy',policy)!=policy.pin or self.prepared_paths.check('root',policy)!=policy.root_pin
                or self.prepared_paths.check('images',policy)!=policy.image_pin
                or self.prepared_paths.check('database',policy)[:2]!=policy.database_pin[:2]
                or not policy.value['enabled']):hold()
        from .own_connection_registry import revoked
        if revoked(policy):hold()
        live=self.service.workflow.live_guard
        if live is not None:
            from .own_connection_broker import Broker,RUNTIME,decode as decode_runtime,socket_pin
            owner=getattr(live,'__self__',None)
            if (type(owner) is not Broker or getattr(live,'__func__',None) is not Broker.guard
                    or owner.service is not self.service or owner.policy is not policy):
                live()  # Preserve every unknown/custom liveness check.
            else:
                if owner.stop.is_set():hold()
                raw,runtime_pin=private_read(policy.root/RUNTIME)
                if (decode_runtime(raw)!=owner.runtime or runtime_pin!=owner.runtime_pin
                        or socket_pin(owner.socket_path)!=owner.socket_pin):hold()
        return True


def for_adapter(adapter):
    """Only exact concrete, same-thread held gates can get a loop guard."""
    from .draft_revision_gate import _ACTIVE,RevisionExecutionGate
    from .draft_revision_input import RevisionInputAdapter
    active=_ACTIVE.get()
    if (type(adapter) is not RevisionInputAdapter or active is None
            or type(active[0]) is not RevisionExecutionGate
            or active[0].service is not adapter.service or active[1]!=threading.get_ident()
            or active[0].deadline!=adapter.deadline):return adapter._guard
    policy=adapter.service.policy
    from .own_connection_policy import ConnectionPolicy
    if (type(policy) is not ConnectionPolicy
            or getattr(policy.check,'__func__',None) is not ConnectionPolicy.check or len(policy.pin)<2 or len(policy.root_pin)!=2
            or len(policy.image_pin)!=2 or len(policy.database_pin)<2):return adapter._guard
    if not active[0].held():hold()
    return RevisionScanGuard(adapter.service,adapter.deadline,adapter._guard,active)


def full(guard):
    from .draft_revision_native_source import checked_guard
    checked_guard(guard.full if type(guard) in (RevisionScanGuard,_BootstrapScanGuard) else guard)


class _BootstrapScanGuard(RevisionScanGuard):
    def __init__(self,service,deadline,full,active,check_stack):
        self.check_stack=check_stack
        super().__init__(service,deadline,full,active)
    def full(self):
        self.check_stack()
        result=super().full()
        self.check_stack()
        return result
    def __call__(self):
        self.check_stack()
        result=super().__call__()
        self.check_stack()
        return result


def for_service_bootstrap(service,deadline):
    """Same-thread genuine gate only; no caller-supplied grant/guard."""
    from .draft_revision_gate import _ACTIVE,RevisionExecutionGate
    from .own_connection_broker import AccountService,Broker
    from .own_connection_policy import ConnectionPolicy
    from .own_connection_workflow import PersistentWorkflow
    from .current_publication_service import _ACCOUNT_GUARD,_POLICY_CHECK,_BROKER_GUARD
    active=_ACTIVE.get()
    if (type(service) is not AccountService or active is None or type(active) is not tuple
            or len(active)!=4 or type(active[0]) is not RevisionExecutionGate
            or active[0].service is not service or active[1]!=threading.get_ident()
            or active[0].deadline!=deadline or not active[0].held()):hold()
    gate=active[0];policy=service.policy;workflow=service.workflow
    from types import MethodType
    live=workflow.live_guard;owner=getattr(live,'__self__',None)
    if type(owner) is not Broker:hold()
    stop=owner.stop;serial=service.serial;lock_type=type(threading.Lock())
    def check_stack():
        if (_ACTIVE.get() is not active or threading.get_ident()!=active[1]
                or type(service) is not AccountService or AccountService.guard is not _ACCOUNT_GUARD
                or 'guard' in vars(service) or getattr(service.guard,'__func__',None) is not _ACCOUNT_GUARD
                or service.policy is not policy or type(policy) is not ConnectionPolicy
                or ConnectionPolicy.check is not _POLICY_CHECK or 'check' in vars(policy)
                or getattr(policy.check,'__func__',None) is not _POLICY_CHECK
                or service.workflow is not workflow or type(workflow) is not PersistentWorkflow
                or workflow.policy is not policy or type(owner) is not Broker
                or Broker.guard is not _BROKER_GUARD or 'guard' in vars(owner)
                or getattr(workflow.live_guard,'__self__',None) is not owner
                or getattr(workflow.live_guard,'__func__',None) is not _BROKER_GUARD
                or type(workflow.live_guard) is not MethodType
                or owner.service is not service or owner.policy is not policy
                or owner.stop is not stop or type(stop) is not threading.Event
                or service.serial is not serial or type(serial) is not lock_type or not serial.locked()
                or threading.Event.is_set(stop) or time.monotonic()>=deadline):hold()
        return True
    def full_check():
        check_stack()
        if not gate.held():hold()
        service.guard(deadline)
        if not gate.held():hold()
        return check_stack()
    return _BootstrapScanGuard(service,deadline,full_check,active,check_stack)
