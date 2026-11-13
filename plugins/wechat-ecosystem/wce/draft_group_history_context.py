"""Actual connection-bound historical policy selector. Never authorization."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os,threading,sqlite3
from .own_validation_scope import OwnedConnection
from .contracts import WCEError
_CONTEXT=ContextVar('fixed_actual_connection_history_policy',default=None)

@contextmanager
def history_policy_context(path,db,policy):
    from .own_connection_policy import ConnectionPolicy
    value=None
    try:
        if type(policy) is ConnectionPolicy and type(db) in (sqlite3.Connection,OwnedConnection):
            from .draft_group_input_files import _plain
            from .draft_group_contracts import canonical
            _plain(policy.value)
            selected=Path(path)
            actual=db.execute('PRAGMA database_list').fetchone()[2]
            if actual and selected==policy.root/'state.sqlite3' and str(selected)==actual:
                info=selected.stat(follow_symlinks=False)
                value=(db,policy,threading.get_ident(),selected,(info.st_dev,info.st_ino),canonical(policy.data),canonical(policy.value),policy.path)
    except (OSError,sqlite3.Error,WCEError,TypeError,ValueError,KeyError,AttributeError):
        # No new earlier error for an unsupported legacy context. Family data
        # still requires a genuine policy at the actual full replay boundary.
        value=None
    token=_CONTEXT.set(value)
    try:yield
    finally:_CONTEXT.reset(token)


def current_history_policy(db):
    from .own_connection_policy import ConnectionPolicy
    value=_CONTEXT.get()
    if value is None:return None
    if value[0] is not db or value[2]!=threading.get_ident():raise WCEError('GROUP_HISTORY_CONTEXT_CHANGED')
    try:
        from .draft_group_input_files import _plain
        from .draft_group_contracts import canonical
        _plain(value[1].value)
        info=value[3].stat(follow_symlinks=False)
        if ((info.st_dev,info.st_ino)!=value[4] or db.execute('PRAGMA database_list').fetchone()[2]!=str(value[3])
            or value[1].root!=value[3].parent or canonical(value[1].data)!=value[5]):raise WCEError('GROUP_HISTORY_CONTEXT_CHANGED')
    except (OSError,sqlite3.Error,TypeError,ValueError,KeyError,AttributeError):
        raise WCEError('GROUP_HISTORY_CONTEXT_CHANGED') from None
    return value[1]


def require_history(policy,db,history_locators):
    """Borrow one entered real DB scope; never issue one at a consumer."""
    from .own_connection_policy import ConnectionPolicy
    from .own_history_source import connection_source
    from .own_history_locators import history_scope
    if type(policy) is not ConnectionPolicy or connection_source(db) is None:
        raise WCEError('GROUP_HISTORY_OWNED_REQUIRED')
    if policy.value.get('schema') == 2 and history_locators is None:
        raise WCEError('GROUP_HISTORY_SCOPE_REQUIRED')
    with history_scope(policy,db,history_locators) as actual:
        if actual is not history_locators:
            raise WCEError('GROUP_HISTORY_SCOPE_REQUIRED')
    return actual


@contextmanager
def history_transaction(store,*,write=False,physical_resources=None):
    """The original SQL transaction owns one H, through all consumer fences."""
    scope=(store.transaction_with_history(write=write) if physical_resources is None else
           store.transaction_with_history(write=write,physical_resources=physical_resources))
    with scope as pair:
        yield pair


@contextmanager
def locator_scope(policy,db,existing=None):
    """Lazy original H entry; used only at explicit SQL ownership boundaries."""
    from .own_history_locators import history_scope
    with history_scope(policy,db,existing) as scope:
        yield scope


@contextmanager
def readonly_history_snapshot(policy,path,*,timeout=2):
    """An independent peer owns its actual RO connection and its own H."""
    from .own_history_source import owned_connection
    from .own_history_locators import history_scope
    path=Path(path)
    if path!=policy.root/'state.sqlite3':
        raise WCEError('GROUP_HISTORY_DATABASE_CHANGED')
    with owned_connection(path,readonly=True,timeout=timeout,isolation_level='') as db:
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('BEGIN')
            with history_policy_context(path,db,policy),history_scope(policy,db) as peer_history:
                yield db,peer_history
        finally:
            if db.in_transaction:db.rollback()


_PHYSICAL=ContextVar('actual_sql_physical_material_resources',default=None)
from weakref import WeakKeyDictionary
_PHYSICAL_LEASES=WeakKeyDictionary()


class _PhysicalLease:
    def __init__(self,*args,**kwargs):
        raise WCEError('GROUP_HISTORY_PHYSICAL_ISSUER_REQUIRED')
    def check(self):
        facts=_PHYSICAL_LEASES.get(self)
        if facts is None:raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
        db,policy,owner,pool,artifacts,source,epoch,pid,thread,path,identity,data,value,policy_path=facts
        from .own_history_source import connection_source
        from .own_validation_scope import _transaction_marker
        from .draft_group_contracts import canonical
        if (pid!=os.getpid() or thread!=threading.get_ident() or owner.closed
                or owner.policy is not policy or owner.pin_pool is not pool
                or owner.artifact_resources is not artifacts or pool.owner is not owner
                or artifacts.owner is not owner or artifacts.pool is not pool
                or connection_source(db) is not source or _transaction_marker(db)!=epoch
                or current_history_policy(db) is not policy
                or Path(db.execute('PRAGMA database_list').fetchone()[2])!=path
                or policy.root/'state.sqlite3'!=path or canonical(policy.data)!=data
                or policy.path!=policy_path or canonical(policy.value)!=value):
            raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
        info=path.stat(follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=identity:raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
        pool._guard(owner);artifacts._guard()
        return pool,owner,artifacts


@contextmanager
def physical_material_scope(db,policy,owner):
    """Explicit actual SQL owner; physical immutable resources, never authority."""
    if owner is None:
        yield
        return
    from .draft_group_runtime_host import GroupExecutionGate
    from .own_history_source import connection_source
    from .own_validation_scope import _transaction_marker
    from .draft_group_pin_resources import PinPool
    from .draft_group_artifact_resources import ArtifactResources
    from .draft_group_contracts import canonical
    if type(owner) is not GroupExecutionGate or type(db) is not OwnedConnection:
        raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
    source=connection_source(db);epoch=_transaction_marker(db)
    if source is None or epoch is None or current_history_policy(db) is not policy:
        raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
    pool,artifacts=owner.pin_pool,owner.artifact_resources
    if type(pool) is not PinPool or type(artifacts) is not ArtifactResources:
        raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
    path=policy.root/'state.sqlite3';info=path.stat(follow_symlinks=False)
    lease=object.__new__(_PhysicalLease)
    _PHYSICAL_LEASES[lease]=(db,policy,owner,pool,artifacts,source,epoch,os.getpid(),
        threading.get_ident(),path,(info.st_dev,info.st_ino),canonical(policy.data),canonical(policy.value),policy.path)
    token=None;body_error=None
    try:
        lease.check();token=_PHYSICAL.set(lease)
        yield lease
        lease.check()
    except BaseException as original:
        body_error=original
        raise
    finally:
        from .draft_group_pin_resources import close_all
        callbacks=[]
        if token is not None:callbacks.append(lambda:_PHYSICAL.reset(token))
        callbacks.append(lambda:_PHYSICAL_LEASES.pop(lease,None))
        close_all(callbacks,body_error)


def current_physical_material_resources(db,policy):
    """None only means no explicit loan; malformed/wrong/stale loans refuse."""
    lease=_PHYSICAL.get()
    if lease is None:return None
    if type(lease) is not _PhysicalLease:
        raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
    facts=_PHYSICAL_LEASES.get(lease)
    if facts is None or facts[0] is not db or facts[1] is not policy:
        raise WCEError('GROUP_HISTORY_PHYSICAL_CHANGED')
    lease.check()
    return lease
