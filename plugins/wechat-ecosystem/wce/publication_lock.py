"""One lock order for draft writers and the optional public dispatcher.

An account which has never enabled publication still takes its ordinary local
writer lock. Trusted enablement publishes the coordination pin while holding
that lock; later writers also take the stable platform-account lock first.
This file does not enable publication or discover any account at import time.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading
import weakref

from .own_connection_policy import atomic_write, locked
from .own_bootstrap_security import path_check
from .publication_contract import exact, fail, stable_account

MARKER = 'publication-coordination.json'
_LOCAL_MUTEXES=weakref.WeakValueDictionary()
_LOCAL_MUTEX_GUARD=threading.Lock()
_OWNED=threading.local()


def _mutex(key):
    with _LOCAL_MUTEX_GUARD:
        value=_LOCAL_MUTEXES.get(key)
        if value is None:
            value=threading.RLock();_LOCAL_MUTEXES[key]=value
        return value


def _marker(root, account_id):
    from .publication_store import read_file
    path = Path(root) / MARKER
    if not os.path.lexists(path):
        return None
    value = read_file(path, 16384)
    exact(value, 'schema account_key anchor anchor_identity')
    if (value['schema'] != 1 or value['account_key'] != stable_account({'appid': account_id})
            or type(value['anchor']) is not str):
        fail('PUBLICATION_COORDINATION_UNVERIFIED')
    anchor = Path(value['anchor'])
    if (not anchor.is_absolute() or anchor.name != value['account_key']
            or anchor.parent.name != 'publication-anchors'
            or list(path_check(anchor, True)) != value['anchor_identity']):
        fail('PUBLICATION_COORDINATION_UNVERIFIED')
    return value


def _require_pin_if_migrated(root, marker):
    # Read-only observation is closed before taking any OS lock. A missing pin
    # in a migrated account is corruption, never a reason to use weaker locks.
    if marker is not None:
        return
    path = Path(root) / 'state.sqlite3'
    path_check(path)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('PRAGMA user_version').fetchone()[0] >= 7:
            fail('PUBLICATION_COORDINATION_UNVERIFIED')
    finally:
        connection.close()


def install_pin(store):
    """Trusted enablement only; caller already owns stable then local locks."""
    value = {'schema': 1, 'account_key': store.key, 'anchor': str(store.anchor),
             'anchor_identity': list(path_check(store.anchor, True))}
    path = store.policy.root / MARKER
    previous = _marker(store.policy.root, store.policy.data['appid'])
    if previous is not None and previous != value:
        fail('PUBLICATION_REASSIGNMENT_HOLD')
    if previous is None:
        atomic_write(path, value)


def verify_pin(store, *, required):
    value = _marker(store.policy.root, store.policy.data['appid'])
    if value is None:
        if required:
            fail('PUBLICATION_COORDINATION_UNVERIFIED')
        return
    if (value['anchor'] != str(store.anchor) or value['account_key'] != store.key
            or value['anchor_identity'] != list(path_check(store.anchor, True))):
        fail('PUBLICATION_COORDINATION_UNVERIFIED')


@contextmanager
def draft_writer(root, account_id):
    # Serialize local threads without changing the nonblocking OS exclusion
    # against other processes/dispatchers. Reentrant same-thread callbacks
    # reuse exactly the held scope, never a caller-selected skip-lock flag.
    root=Path(root)
    if type(account_id) is not str or not account_id:fail('PUBLICATION_ACCOUNT_UNVERIFIED')
    key=(str(root.absolute()),account_id.casefold())
    with _mutex(key):
        owned=getattr(_OWNED,'scopes',None)
        if owned is None:owned={};_OWNED.scopes=owned
        if key in owned:
            if _marker(root,account_id)!=owned[key]:fail('PUBLICATION_COORDINATION_UNVERIFIED')
            _require_pin_if_migrated(root,owned[key])
            yield
            return
        with _os_draft_writer(root,account_id) as descriptors:
            owned[key]=_marker(root,account_id)
            fd_scopes=getattr(_OWNED,'fd_scopes',None)
            if fd_scopes is None:fd_scopes={};_OWNED.fd_scopes=fd_scopes
            fd_scopes[key]=descriptors
            try:yield
            finally:
                del fd_scopes[key]
                del owned[key]


@contextmanager
def _os_draft_writer(root, account_id):
    root = Path(root)
    initial = _marker(root, account_id)
    _require_pin_if_migrated(root, initial)
    local = root / 'publication-dispatch.lock'
    if initial is None:
        with locked(local, nonblocking=True) as local_fd:
            # If first enablement won the local lock, release it before taking
            # the now-required stable lock. Never wait stable while owning local.
            if _marker(root, account_id) is None:
                _require_pin_if_migrated(root, None)
                yield ((local,local_fd,_lock_identity(local_fd)),)
                return
        initial = _marker(root, account_id)
        if initial is None:
            fail('PUBLICATION_COORDINATION_UNVERIFIED')
    anchor = Path(initial['anchor'])
    with locked(anchor / 'publication.lock', nonblocking=True, existing=True) as stable_fd:
        with locked(local, nonblocking=True) as local_fd:
            if _marker(root, account_id) != initial:
                fail('PUBLICATION_COORDINATION_UNVERIFIED')
            yield ((anchor/'publication.lock',stable_fd,_lock_identity(stable_fd)),
                   (local,local_fd,_lock_identity(local_fd)))


def _lock_identity(fd):
    value=os.fstat(fd)
    return (value.st_dev,value.st_ino)


def _writer_guard(root,account_id):
    """Private same-context FD liveness, not an adversarial flock oracle."""
    import stat
    root=Path(root);thread=threading.get_ident();key=(str(root.absolute()),account_id.casefold())
    owned=getattr(_OWNED,'scopes',{});descriptors=getattr(_OWNED,'fd_scopes',{}).get(key)
    if key not in owned or not descriptors:fail('PUBLICATION_COORDINATION_UNVERIFIED')
    marker=owned[key]
    def current():
        if (threading.get_ident()!=thread or getattr(_OWNED,'fd_scopes',{}).get(key) is not descriptors
                or key not in getattr(_OWNED,'scopes',{}) or _marker(root,account_id)!=marker):
            fail('PUBLICATION_COORDINATION_UNVERIFIED')
        for path,fd,pin in descriptors:
            info=os.fstat(fd);actual=path.lstat()
            if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(actual.st_mode)
                    or (info.st_dev,info.st_ino)!=pin or (actual.st_dev,actual.st_ino)!=pin
                    or info.st_uid!=os.getuid() or actual.st_uid!=os.getuid()
                    or stat.S_IMODE(info.st_mode)!=0o600 or stat.S_IMODE(actual.st_mode)!=0o600
                    or info.st_nlink!=1 or actual.st_nlink!=1):
                fail('PUBLICATION_COORDINATION_UNVERIFIED')
        return True
    current();return current
