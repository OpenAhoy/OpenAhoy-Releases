"""Conservative spent seal outside SQLite's rollback domain, never a send grant.

Supported new-code starts reject restored databases missing an existing seal's
admission. This cannot detect manually running old code plus old database, or
rolling the entire machine and seal back together. No seal deletion API exists.
"""
import os
from pathlib import Path
import stat
import time

from .bounded_file import FileSource, file_state, identity
from .contracts import WCEError
from .own_body_recovery import stored
from .service import canonical, digest

DIRECTORY = 'body-attempt-spent'


def directory(db):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2]).absolute()
    return path.parent / DIRECTORY


def folder_check(path):
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise WCEError('OWN_BODY_SPENT_UNVERIFIED')


def seal_for(row):
    intent = stored(row['intent'], row['intent_digest'])
    policy = intent['policy']
    return {'schema': 1, 'policy': 'FINAL_BODY_ATTEMPT4_SPENT_V1', 'ordinal': 4,
        'root': row['original_step_id'], 'tenant': row['tenant'], 'resource': row['resource'],
        'account': policy['binding']['account'], 'attempt_id': row['id'], 'owner': row['owner'],
        'intent_digest': row['intent_digest'], 'candidate_scope': policy['candidate_scope']}


def filename(value):
    return digest({k: value[k] for k in ('root', 'tenant', 'resource', 'account')}) + '.json'


def create(db, row):
    path = directory(db)
    source = FileSource(path.parent)
    descriptors, chain = [], []
    try:
        parent = source._root(descriptors, chain)
        root = os.fstat(parent)
        if (identity(root) != source.root_identity or root.st_uid != os.getuid()
                or stat.S_IMODE(root.st_mode) != 0o700):
            raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
        try:
            os.mkdir(DIRECTORY, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
        # An earlier interrupted mkdir may have left a visible empty directory.
        # Existence alone is not proof that its parent entry was persisted.
        os.fsync(parent)
        folder = source._directory(parent, DIRECTORY, descriptors, chain)
        before = os.fstat(folder)
        if before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o700:
            raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
        value = seal_for(row)
        raw = canonical(value).encode()
        fd = os.open(filename(value), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=folder)
        descriptors.append(fd)
        pending = memoryview(raw)
        while pending:
            written = os.write(fd, pending)
            if written <= 0:
                raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
            pending = pending[written:]
        os.fsync(fd)
        os.fsync(folder)
        after = os.fstat(folder)
        end_root = os.fstat(parent)
        if (identity(before) != identity(after) or after.st_uid != os.getuid()
                or stat.S_IMODE(after.st_mode) != 0o700
                or identity(end_root) != source.root_identity or end_root.st_uid != os.getuid()
                or stat.S_IMODE(end_root.st_mode) != 0o700):
            raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
        source._check_chain(chain)
        # The same DB transaction sees the uncommitted admission. Any error
        # leaves the seal in place; never unlink it to reclaim sending budget.
        check(db)
    finally:
        source._close(descriptors)



def read_seal(source, name):
    """Validate the actual opened descriptor, including permissions and bounds."""
    descriptors, chain = [], []
    def state(info):
        return file_state(info) + (info.st_uid, info.st_gid, info.st_mode)
    try:
        parent = source._root(descriptors, chain)
        root_info = os.fstat(parent)
        if (identity(root_info) != source.root_identity or root_info.st_uid != os.getuid()
                or stat.S_IMODE(root_info.st_mode) != 0o700):
            raise ValueError()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= 8192):
            raise ValueError()
        raw = bytearray()
        deadline = time.monotonic() + 2
        while True:
            if time.monotonic() >= deadline:
                raise ValueError()
            chunk = os.read(fd, 8193 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 8192:
                raise ValueError()
        after = os.fstat(fd)
        entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
        end_root = os.fstat(parent)
        if (state(before) != state(after) or state(after) != state(entry)
                or len(raw) != after.st_size or identity(end_root) != source.root_identity
                or end_root.st_uid != os.getuid() or stat.S_IMODE(end_root.st_mode) != 0o700):
            raise ValueError()
        source._check_chain(chain)
        return bytes(raw)
    finally:
        source._close(descriptors)


def check(db):
    path = directory(db)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rows = list(db.execute('SELECT * FROM own_body_attempts')) if 'own_body_attempts' in tables else []
    if not os.path.lexists(path):
        if rows:
            raise WCEError('OWN_BODY_SPENT_UNVERIFIED')
        return
    try:
        folder_check(path)
        paths = list(path.iterdir())
        if len(paths) > 1024:
            raise ValueError()
        expected = {filename(seal_for(row)): seal_for(row) for row in rows}
        if set(expected) != {p.name for p in paths}:
            raise ValueError()
        source = FileSource(path)
        for item in paths:
            info = item.lstat()
            if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 8192):
                raise ValueError()
            raw = read_seal(source, item.name)
            if raw != canonical(expected[item.name]).encode():
                raise ValueError()
    except Exception:
        raise WCEError('OWN_BODY_SPENT_UNVERIFIED') from None
