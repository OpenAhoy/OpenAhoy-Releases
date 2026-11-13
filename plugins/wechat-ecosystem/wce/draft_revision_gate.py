"""Revision uses the same account writer and policy lock order as old writers."""
from contextlib import contextmanager
from contextvars import ContextVar
import math,os,threading,time,uuid
from .contracts import WCEError
from .bounded_file import identity
from .own_connection_policy import locked
from .own_fd_domain import regular_fd_domain

_ACTIVE=ContextVar('wce_revision_execution_gate',default=None)
_SOURCE_OBSERVATIONS=ContextVar('wce_revision_source_observations',default=None)

def hold():raise WCEError('DRAFT_REVISION_EXECUTION_LOCK_REQUIRED')

def guard_current(service):
    """Call-stack cancellation only; never replace shared workflow guards."""
    active=_ACTIVE.get()
    if active is not None and active[0].service is service:
        guard=active[0].cancel_guard
        if guard is not None:guard()

class RevisionExecutionGate:
    def __init__(self,service,deadline,*,cancel_guard=None):
        from .own_connection_broker import AccountService
        if (type(service) is not AccountService or type(deadline) not in (int,float)
                or not math.isfinite(deadline) or (cancel_guard is not None and not callable(cancel_guard))):hold()
        self.service,self.deadline=service,deadline
        self.cancel_guard=cancel_guard
        self._active_entry=None
        self.entry_id=None
        self._review_epoch_states=None

    def held(self):
        active=_ACTIVE.get()
        if (active is None or active[0] is not self or active is not self._active_entry
                or active[1]!=threading.get_ident()):return False
        fd,pin=active[2:]
        self.service.guard(self.deadline)
        current=os.fstat(fd);path=self.service.policy.root/'connection-policy.lock'
        return (identity(current)==pin==identity(path.lstat()) and current.st_nlink==1)

    @contextmanager
    def __call__(self):
        with regular_fd_domain(deadline=self.deadline):
            if _ACTIVE.get() is not None:hold()
            remaining=self.deadline-time.monotonic()
            if remaining<=0 or not self.service.serial.acquire(timeout=min(60,remaining)):hold()
            try:
                if self.cancel_guard is not None:self.cancel_guard()
                from .publication_lock import draft_writer
                with draft_writer(self.service.policy.root,self.service.policy.data['appid']):
                    with locked(self.service.policy.root/'connection-policy.lock',nonblocking=True) as fd:
                        self.service.guard(self.deadline)
                        active=(self,threading.get_ident(),fd,identity(os.fstat(fd)))
                        self._active_entry=active
                        # An audit correlation value, never an authorization token.
                        self.entry_id=uuid.uuid4().hex
                        self._review_epoch_states={}
                        token=_ACTIVE.set(active)
                        observations={}
                        observations_token=_SOURCE_OBSERVATIONS.set((active,observations))
                        try:
                            if not self.held():hold()
                            yield
                            if not self.held():hold()
                        finally:
                            self._active_entry=None
                            self.entry_id=None
                            self._review_epoch_states.clear()
                            self._review_epoch_states=None
                            observations.clear()
                            _SOURCE_OBSERVATIONS.reset(observations_token)
                            _ACTIVE.reset(token)
            finally:self.service.serial.release()
