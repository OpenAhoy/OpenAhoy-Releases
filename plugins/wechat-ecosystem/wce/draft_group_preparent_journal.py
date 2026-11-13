"""Unarmed mechanical PRE_PARENT journal proposal. Never a permission issuer.

The fixed controller must supply its pinned account-wide root, the original
accepted request identity and actual observations. These files do not prove
Owned/H, current rights, NO_EFFECT, a Parent, or permission to drain/spawn/read.
No file is removed on failure or close. Only the fixed first-control normal
commit or historical-recovery receipt may attach a real Parent.
"""
from contextlib import contextmanager
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import threading
from .own_fd_domain import fd_capacity_allowed


ANCHOR_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_ANCHOR_V1'
ACCOUNT_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_ACCOUNT_V1'
RECORD_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_RECORD_V1'
HISTORICAL_RECORD_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_RECORD_V2'
HISTORICAL_ATTACHMENT_ORIGIN = 'HISTORICAL_COMMITTED_GRAPH_OBSERVATION_V1'
HEAD_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_HEAD_V1'
ACTION = 'FIRST_PREPARE'
TRANSIENT_FDS = 35
MAX_FILE_BYTES, MAX_STATE_BYTES = 65536, 64 * 1024 * 1024
MAX_ANCHORS, MAX_STEPS, MAX_NAMES = 32, 32, 2048
EVENTS = frozenset(('RESERVED_PRE_PARENT', 'DRAIN_MAY_EFFECT', 'SPAWN_MAY_EFFECT',
    'READY_PRE_PARENT', 'TOKEN_OR_READ_MAY_EFFECT', 'PREPARE_RESULT_UNKNOWN',
    'PARENT_COMMIT_MAY_EFFECT', 'PARENT_COMMIT_UNKNOWN', 'ATTACHMENT_UNKNOWN',
    'NO_EFFECT_OBSERVED', 'BUSY_OBSERVED', 'OWNER_ABSENCE_OBSERVED',
    'LIFETIME_RELEASE_OBSERVED','BOUND_REAL_PARENT'))
IDENTITY_KEYS = ('tenant', 'principal', 'connection', 'resource', 'account')
ANCHOR_KEYS = ('schema', 'profile', 'authority', 'action', 'binding_identity',
    'original_queue_sha', 'original_request_identity_sha',
    'original_request_set_sha', 'account_partition_sha')
OBSERVATION_KEYS = ('candidate_sha', 'source_sha', 'binding_sha', 'policy_sha',
    'epoch', 'not_after_ms')
RECORD_KEYS = ('schema', 'profile', 'authority', 'anchor', 'anchor_sha',
    'preparation_identity_sha', 'sequence', 'previous_sha', 'event',
    'observation', 'not_after_ms', 'parent_binding', 'allows_automatic_replay')
HEAD_KEYS = ('schema', 'profile', 'authority', 'anchor_sha', 'sequence', 'record_sha')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_SECRET = re.compile(r'(?i)secret|password|authorization|cookie|bearer|api[_-]?key|access[_-]?token|refresh[_-]?token')
_LEAF = re.compile(r'([0-9a-f]{64})\.(?:(head)\.json|([0-9]{4})\.json|(head-next)-([0-9]{4})\.json)\Z')


class PreParentHold(ValueError):
    def __init__(self, code='GROUP_PRE_PARENT_HOLD'):
        super().__init__(code)


def need(value, code='GROUP_PRE_PARENT_HOLD'):
    if value is not True:
        raise PreParentHold(code)


def close_all(callbacks, original=None):
    """Every owner is attempted, even on BaseException; preserve first error."""
    first = None
    for callback in callbacks:
        try:
            callback()
        except BaseException as error:
            if first is None:
                first = error
    if original is None and first is not None:
        raise first


def capacity(additional):
    # Retain the existing transient reserve under the actual OS soft limit.
    need(fd_capacity_allowed(len(os.listdir('/dev/fd')), additional, TRANSIENT_FDS),
         'GROUP_PRE_PARENT_FD_CAPACITY')


def full(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def closed(value, keys):
    need(type(value) is dict and set(value) == set(keys))


def checksum(value):
    need(type(value) is str and _SHA.fullmatch(value) is not None)


def integer(value, low=0, high=2**63-1):
    need(type(value) is int and low <= value <= high)


def identity(value):
    closed(value, IDENTITY_KEYS)
    for item in value.values():
        need(type(item) is str and _ID.fullmatch(item) is not None
             and _SECRET.search(item) is None)


def _plain(value, depth=0):
    need(depth <= 12)
    if type(value) is dict:
        need(len(value) <= 64)
        for key, item in value.items():
            need(type(key) is str)
            _plain(key, depth+1); _plain(item, depth+1)
    elif type(value) is list:
        need(len(value) <= MAX_STEPS)
        for item in value:
            _plain(item, depth+1)
    elif type(value) is str:
        need(len(value) <= 256 and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    elif type(value) is int:
        integer(value)
    else:
        need(type(value) in (bool, type(None)))


def canonical(value):
    _plain(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError):
        raise PreParentHold() from None
    need(0 < len(raw) <= MAX_FILE_BYTES)
    return raw


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        need(key not in result)
        result[key] = value
    return result


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_FILE_BYTES)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
            parse_constant=lambda _: need(False), parse_float=lambda _: need(False))
    except (UnicodeError, ValueError, RecursionError):
        raise PreParentHold() from None
    need(canonical(value) == raw)
    return value


def validate_anchor(value):
    closed(value, ANCHOR_KEYS)
    need(type(value['schema']) is int and value['schema'] == 1
         and value['profile'] == ANCHOR_PROFILE and value['authority'] is False
         and value['action'] == ACTION)
    identity(value['binding_identity'])
    for key in ('original_queue_sha', 'original_request_identity_sha',
                'original_request_set_sha', 'account_partition_sha'):
        checksum(value[key])
    return decode(canonical(value))


def preparation_identity(anchor):
    """No caller-chosen new ID, C/source/epoch/D/path/PID in the stable key."""
    value = validate_anchor(anchor)
    return digest({'profile': 'GROUP_OPERATOR_TECHNICAL_PREPARATION_ID_V1',
                   'anchor': value})


def validate_observation(value):
    closed(value, OBSERVATION_KEYS)
    for key in ('candidate_sha', 'source_sha', 'binding_sha', 'policy_sha'):
        checksum(value[key])
    integer(value['epoch'], 0); integer(value['not_after_ms'], 1)
    return decode(canonical(value))


def _technical_observation(value):
    from . import draft_group_first_time_values as t
    if t.is_time06_observation(value):
        return t.validate_observation(value,OBSERVATION_KEYS,validate_observation)
    return validate_observation(value)


class ParentReadbackReceipt:
    """Legacy unarmed placeholder, never accepted by the actual first-control issuer."""
    def __init__(self, *args, **kwargs):
        raise NotImplementedError('GROUP_PRE_PARENT_READBACK_ISSUER_NOT_IMPLEMENTED')


def require_parent_readback_receipt(receipt, *, anchor, expected_head_sha):
    from .draft_group_first_control import require_parent_readback_receipt as actual
    return actual(receipt, anchor=anchor, expected_head_sha=expected_head_sha)


def attachment_receipt_scope(receipt, *, anchor, expected_head_sha):
    from .draft_group_first_control import attachment_receipt_scope as actual
    return actual(receipt, anchor=anchor, expected_head_sha=expected_head_sha)


class PreParentJournal:
    """Bounded account-wide technical files, not runtime/Parent authority.

    Lock order is the existing actual startup gate, then this short account
    lock. No gate/drain/Popen/SQL/Token is implemented. Every effect still needs
    its fixed controller's actual rights and freshly acknowledged pre-write.
    """
    def __init__(self, root, *, binding_identity, existing_only=False, readonly=False):
        identity(binding_identity)
        need(type(existing_only) is bool and type(readonly) is bool)
        self.readonly, self.existing_only = readonly, existing_only or readonly
        self._lock_depth = 0
        self.binding_identity = decode(canonical(binding_identity))
        self.root = Path(root)
        need(self.root.is_absolute() and '..' not in self.root.parts
             and len(self.root.parts) <= 32 and len(str(self.root)) <= 4096)
        self.owner = os.getpid(), threading.get_ident()
        self.fds, self.parent, self.lock_fd = [], None, None
        self.closed, self.poisoned = False, False
        self.root_pin = self.lock_pin = None

    def _open(self, path, flags, mode=0o600, *, directory=None):
        if self.readonly:
            need(flags & os.O_ACCMODE == os.O_RDONLY
                 and not flags & (os.O_CREAT|os.O_EXCL|os.O_TRUNC|os.O_APPEND),
                 'GROUP_PRE_PARENT_READONLY')
        fd = None
        try:
            capacity(1)
            fd = os.open(path, flags, mode, dir_fd=directory)
            self.fds.append(fd)
            return fd
        except BaseException as original:
            if fd is not None and fd not in self.fds:
                close_all([lambda: os.close(fd)], original)
            raise

    def _release(self, fd):
        self.fds.remove(fd)  # Never retry a close whose outcome is unknown.
        try:
            os.close(fd)
        except BaseException:
            self.poisoned = True
            raise

    def __enter__(self):
        need(self.parent is None and not self.closed)
        try:
            # Walk without symlink traversal; at most two walking descriptors.
            directory = self._open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for part in self.root.parts[1:]:
                next_fd = self._open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                     | os.O_NONBLOCK, directory=directory)
                self._release(directory)
                directory = next_fd
            self.parent = directory
            info = os.fstat(directory)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o700)
            self.root_pin = full(info)[:5]
            if self.existing_only:
                self.lock_fd = self._open('account.lock', (os.O_RDONLY if self.readonly else os.O_RDWR)
                    | os.O_NOFOLLOW | os.O_NONBLOCK, directory=self.parent)
            else:
                self._initialize_lock()
            self.lock_pin = full(os.fstat(self.lock_fd))
            self.check()
            with self._locked():
                value = {'schema': 1, 'profile': ACCOUNT_PROFILE, 'authority': False,
                         'binding_identity': self.binding_identity}
                if 'account.json' not in os.listdir(self.parent):
                    need(not self.existing_only,'GROUP_PRE_PARENT_EXISTING_REQUIRED')
                    need(set(os.listdir(self.parent)) == {'account.lock'})
                    self._create('account.json', canonical(value))
                existing, _, _ = self._read('account.json')
                need(canonical(existing) == canonical(value))
                self._inventory()
            return self
        except BaseException as original:
            self.close(original=original)
            raise

    def _initialize_lock(self):
        need(not self.readonly and not self.existing_only,'GROUP_PRE_PARENT_EXISTING_REQUIRED')
        try:
            self.lock_fd = self._open('account.lock', os.O_RDWR | os.O_NOFOLLOW
                | os.O_NONBLOCK | os.O_CREAT | os.O_EXCL, directory=self.parent)
        except FileExistsError:
            self.lock_fd = self._open('account.lock', os.O_RDWR | os.O_NOFOLLOW
                                     | os.O_NONBLOCK, directory=self.parent)

    def check(self):
        need(not self.closed and not self.poisoned and self.owner ==
             (os.getpid(), threading.get_ident()))
        current = Path('/')
        for part in self.root.parts[1:]:
            current = current / part
            need(stat.S_ISDIR(current.lstat().st_mode))
        need(self.root_pin == full(os.fstat(self.parent))[:5]
             == full(self.root.lstat())[:5])
        lock = os.fstat(self.lock_fd)
        need(stat.S_ISREG(lock.st_mode) and lock.st_uid == os.getuid()
             and stat.S_IMODE(lock.st_mode) == 0o600 and lock.st_nlink == 1
             and lock.st_size == 0 and self.lock_pin == full(lock)
             == full(os.stat('account.lock', dir_fd=self.parent, follow_symlinks=False)))

    @contextmanager
    def _locked(self):
        self.check()
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
                self.check()
            finally:self._lock_depth -= 1
            return
        try:
            fcntl.flock(self.lock_fd, (fcntl.LOCK_SH if self.readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PreParentHold('GROUP_PRE_PARENT_BUSY') from None
        original = None
        self._lock_depth = 1
        try:
            self.check()
            yield
            self.check()
        except BaseException as error:
            original = error
            raise
        finally:
            def unlock():
                self._lock_depth = 0
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                except BaseException:
                    self.poisoned = True
                    raise
            close_all([unlock], original)

    @contextmanager
    def hold(self):
        """Mechanical account lock before shared history; never permission."""
        with self._locked():yield self

    def _writable(self):
        self.check()
        need(not self.readonly,'GROUP_PRE_PARENT_READONLY')

    def _read(self, name):
        self.check()
        fd = self._open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        directory=self.parent)
        original = None
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                 and 0 < info.st_size <= MAX_FILE_BYTES)
            raw = os.pread(fd, info.st_size + 1, 0)
            need(len(raw) == info.st_size and full(info) == full(os.fstat(fd))
                 == full(os.stat(name, dir_fd=self.parent, follow_symlinks=False)))
            return decode(raw), sha256(raw).hexdigest(), full(info)
        except BaseException as error:
            original = error
            raise
        finally:
            close_all([lambda: self._release(fd)], original)

    def _create(self, name, raw):
        self._writable()
        fd = self._open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                        | os.O_NONBLOCK, directory=self.parent)
        original = None
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)
            remaining = memoryview(raw)
            while remaining:
                amount = os.write(fd, remaining)
                need(type(amount) is int and amount > 0)
                remaining = remaining[amount:]
            info = os.fstat(fd)
            need(info.st_size == len(raw) and os.pread(fd, len(raw)+1, 0) == raw
                 and full(info) == full(os.stat(name, dir_fd=self.parent, follow_symlinks=False)))
            os.fsync(fd)
            os.fsync(self.parent)
            need(full(info) == full(os.fstat(fd))
                 == full(os.stat(name, dir_fd=self.parent, follow_symlinks=False)))
        except BaseException as error:
            self.poisoned = True
            original = error
            raise
        finally:
            close_all([lambda: self._release(fd)], original)

    def _inventory(self):
        self.check()
        account, _, account_pin = self._read('account.json')
        need(canonical(account) == canonical({'schema': 1, 'profile': ACCOUNT_PROFILE,
            'authority': False, 'binding_identity': self.binding_identity}))
        names = os.listdir(self.parent)
        need(len(names) <= MAX_NAMES)
        anchors, files, total = set(), {}, 0
        for name in names:
            if name in ('account.lock', 'account.json'):
                continue
            match = _LEAF.fullmatch(name)
            need(match is not None and match[4] is None,
                 'GROUP_PRE_PARENT_PARTIAL_OR_UNKNOWN')
            anchors.add(match[1])
            info = os.stat(name, dir_fd=self.parent, follow_symlinks=False)
            total += info.st_size
            need(0 < info.st_size <= MAX_FILE_BYTES and total <= MAX_STATE_BYTES)
            files[name] = self._read(name)
        need(len(anchors) <= MAX_ANCHORS)
        results = {}
        for key in sorted(anchors):
            head_name = key + '.head.json'
            need(head_name in files, 'GROUP_PRE_PARENT_PARTIAL_OR_UNKNOWN')
            head, head_sha, head_pin = files[head_name]
            closed(head, HEAD_KEYS)
            need(type(head['schema']) is int and head['schema'] == 1
                 and head['profile'] == HEAD_PROFILE and head['authority'] is False
                 and head['anchor_sha'] == key)
            integer(head['sequence'], 0, MAX_STEPS-1); checksum(head['record_sha'])
            expected_names = {head_name} | {f'{key}.{seq:04d}.json'
                                            for seq in range(head['sequence']+1)}
            need({name for name in files if name.startswith(key + '.')} == expected_names,
                 'GROUP_PRE_PARENT_PARTIAL_OR_UNKNOWN')
            previous, events, original_anchor, deadline = None, [], None, None
            records = []; parent_binding = None; model=None; result=None
            for seq in range(head['sequence']+1):
                row, row_sha, _ = files[f'{key}.{seq:04d}.json']
                from . import draft_group_first_time_values as t
                time06=type(row) is dict and row.get('profile')==t.RECORD_PROFILE
                if model is None:model=time06
                need(model is time06,'GROUP_PRE_PARENT_TIME_MODEL_MIXED')
                if time06:
                    closed(row,RECORD_KEYS+t.EXTRA_RECORD_KEYS)
                    need(type(row['schema']) is int and row['schema']==3
                         and row['time_model']==t.TIME_MODEL
                         and row['attachment_origin'] in (None,HISTORICAL_ATTACHMENT_ORIGIN))
                elif type(row) is dict and row.get('schema')==2:
                    closed(row, RECORD_KEYS+('attachment_origin',))
                    need(row['profile']==HISTORICAL_RECORD_PROFILE
                         and row['event']=='BOUND_REAL_PARENT'
                         and row['attachment_origin']==HISTORICAL_ATTACHMENT_ORIGIN)
                else:closed(row, RECORD_KEYS)
                anchor = validate_anchor(row['anchor'])
                observation = _technical_observation(row['observation'])
                need(t.is_time06_observation(observation) is time06)
                if time06 and records:t.require_same_lifecycle(records[0]['observation'],observation)
                need(type(row['schema']) is int and row['schema'] in ((3,) if time06 else (1,2))
                     and row['profile'] == (t.RECORD_PROFILE if time06 else RECORD_PROFILE if row['schema']==1 else HISTORICAL_RECORD_PROFILE) and row['authority'] is False
                     and type(row['sequence']) is int and row['sequence'] == seq
                     and row['anchor_sha'] == key == digest(anchor)
                     and row['preparation_identity_sha'] == preparation_identity(anchor)
                     and row['previous_sha'] == previous
                     and row['allows_automatic_replay'] is False
                     and anchor['binding_identity'] == self.binding_identity)
                need(original_anchor is None or anchor == original_anchor)
                self._event(row['event'], events,time06=time06)
                if row['event']=='BOUND_REAL_PARENT':
                    from .draft_group_first_control import validate_attachment_mapping
                    parent_binding=validate_attachment_mapping(row['parent_binding'])
                    need(parent_binding['anchor_sha']==key
                         and parent_binding['preparation_identity_sha']==preparation_identity(anchor)
                         and parent_binding['operator_request_identity_sha']==anchor['original_request_identity_sha']
                         and parent_binding['original_request_set_sha']==anchor['original_request_set_sha']
                         and parent_binding['account_partition_sha']==anchor['account_partition_sha'])
                    need((parent_binding['profile']==t.MAPPING_PROFILE) is time06,
                         'GROUP_PRE_PARENT_TIME_MODEL_MIXED')
                    if time06:
                        need(parent_binding['first_absence_sha']==observation['first_absence_sha']
                             and parent_binding['source_lifetime_not_after_ms']<=observation['source_lifetime_not_after_ms']
                             and parent_binding['original_technical_not_after_ms']==observation['not_after_ms'])
                    else:
                        deadline=(parent_binding['not_after_ms'] if deadline is None else
                                  min(deadline,parent_binding['not_after_ms']))
                else:need(row['parent_binding'] is None)
                if time06:
                    need(row['source_lifetime_not_after_ms']==observation['source_lifetime_not_after_ms']
                         and row['original_technical_not_after_ms']==observation['not_after_ms'])
                    if row['event']==t.KNOWN_EVENT:
                        result=t.validate_result(row['prepare_result'])
                        need(parent_binding is not None and result['parent_mapping_sha']==digest(parent_binding)
                             and result['preparation_identity_sha']==preparation_identity(anchor)
                             and result['original_technical_not_after_ms']==observation['not_after_ms'])
                    else:need(row['prepare_result'] is None)
                    need(row['attachment_origin'] is None or row['event']=='BOUND_REAL_PARENT')
                deadline = observation['not_after_ms'] if deadline is None else min(
                    deadline, observation['not_after_ms'])
                need(type(row['not_after_ms']) is int and row['not_after_ms'] == deadline)
                original_anchor, previous = anchor, row_sha
                events.append(row['event']); records.append(row)
            need(previous == head['record_sha'])
            results[key] = {'authority': False, 'anchor': original_anchor,
                'preparation_identity_sha': preparation_identity(original_anchor),
                'head_sha': head_sha, 'head_pin': head_pin, 'head': head,
                'records': records, 'events': events, 'not_after_ms': deadline,
                'parent_binding': parent_binding, 'state': ('NOT_CREATED' if parent_binding is None else 'BOUND_REAL_PARENT'),
                'allows_automatic_replay': False,
                **({'time_model':t.TIME_MODEL,'source_lifetime_not_after_ms':records[0]['source_lifetime_not_after_ms'],
                    'original_technical_not_after_ms':records[0]['original_technical_not_after_ms'],
                    'prepare_result':result} if model else {})}
        need(set(names) == set(os.listdir(self.parent)) and account_pin == full(
            os.stat('account.json', dir_fd=self.parent, follow_symlinks=False)))
        for name, (_, _, pin) in files.items():
            need(pin == full(os.stat(name, dir_fd=self.parent, follow_symlinks=False)))
        self.check()
        return results

    def _event(self, event, previous, *, time06=False):
        from .draft_group_first_time_values import KNOWN_EVENT
        if time06 and event==KNOWN_EVENT:
            need('BOUND_REAL_PARENT' in previous and KNOWN_EVENT not in previous)
            return
        need(type(event) is str and event in EVENTS and event not in previous
             and 'BOUND_REAL_PARENT' not in previous)
        need((not previous and event == 'RESERVED_PRE_PARENT') or
             (bool(previous) and event != 'RESERVED_PRE_PARENT'))
        if event == 'SPAWN_MAY_EFFECT':
            need('DRAIN_MAY_EFFECT' in previous or 'OWNER_ABSENCE_OBSERVED' in previous)
        if event == 'READY_PRE_PARENT':
            need('SPAWN_MAY_EFFECT' in previous)
        if event in ('TOKEN_OR_READ_MAY_EFFECT', 'PARENT_COMMIT_MAY_EFFECT'):
            need('READY_PRE_PARENT' in previous)
        if event in ('PARENT_COMMIT_UNKNOWN', 'ATTACHMENT_UNKNOWN','BOUND_REAL_PARENT'):
            need('PARENT_COMMIT_MAY_EFFECT' in previous)

    def inspect(self):
        """All account anchors; no filtering away another request's unknown."""
        with self._locked():
            return decode(canonical(self._public_inventory(self._inventory())))

    @staticmethod
    def _public_inventory(values):
        # Strip implementation pins; returned values remain detached facts only.
        return {key: {field: value for field, value in row.items()
                      if field != 'head_pin'} for key, row in values.items()}

    def _row(self, anchor, observation, sequence, previous, event, deadline):
        value={'schema': 1, 'profile': RECORD_PROFILE, 'authority': False,
            'anchor': anchor, 'anchor_sha': digest(anchor),
            'preparation_identity_sha': preparation_identity(anchor),
            'sequence': sequence, 'previous_sha': previous, 'event': event,
            'observation': observation, 'not_after_ms': deadline,
            'parent_binding': None, 'allows_automatic_replay': False}
        from . import draft_group_first_time_values as t
        if t.is_time06_observation(observation):
            value.update(schema=3,profile=t.RECORD_PROFILE,time_model=t.TIME_MODEL,
                source_lifetime_not_after_ms=observation['source_lifetime_not_after_ms'],
                original_technical_not_after_ms=observation['not_after_ms'],
                attachment_origin=None,prepare_result=None)
        return value

    def _head(self, key, seq, row_sha):
        return {'schema': 1, 'profile': HEAD_PROFILE, 'authority': False,
                'anchor_sha': key, 'sequence': seq, 'record_sha': row_sha}

    def reserve(self, anchor, observation):
        validate_observation(observation) # Old API can never issue the new model.
        return self._reserve(anchor,observation)

    def reserve_time06(self, anchor, observation, *, receipt):
        from .draft_group_first_control import time06_first_reservation_scope
        with time06_first_reservation_scope(receipt,self,anchor,observation) as fence:
            fence()
            result=self._reserve(anchor,observation)
            fence(result)
            return result

    def _reserve(self, anchor, observation):
        self._writable()
        anchor, observation = validate_anchor(anchor), _technical_observation(observation)
        from .draft_group_first_time_values import is_time06_observation
        if is_time06_observation(observation):
            from .draft_group_first_control import require_time06_reserve_in_progress
            require_time06_reserve_in_progress(self,anchor,observation)
        need(anchor['binding_identity'] == self.binding_identity)
        key = digest(anchor)
        with self._locked():
            values = self._inventory()
            need(not values or set(values) == {key}, 'GROUP_PRE_PARENT_RELATED_UNRESOLVED')
            if key in values:
                return {'authority': False, 'created': False, 'head_sha': values[key]['head_sha'],
                        'preparation_identity_sha': preparation_identity(anchor),
                        'allows_automatic_replay': False}
            row = self._row(anchor, observation, 0, None, 'RESERVED_PRE_PARENT',
                            observation['not_after_ms'])
            self._create(key + '.0000.json', canonical(row))
            head = self._head(key, 0, digest(row))
            self._create(key + '.head.json', canonical(head))
            self._inventory()
            return {'authority': False, 'created': True, 'head_sha': digest(head),
                    'preparation_identity_sha': preparation_identity(anchor),
                    'allows_automatic_replay': False}

    def note(self, anchor, *, expected_head_sha, event, observation):
        """CAS observation before a possible effect; never an execution permit."""
        self._writable()
        anchor, observation = validate_anchor(anchor), _technical_observation(observation)
        checksum(expected_head_sha)
        key = digest(anchor)
        with self._locked():
            values = self._inventory()
            need(set(values) == {key}, 'GROUP_PRE_PARENT_RELATED_UNRESOLVED')
            current = values[key]
            need(current['head_sha'] == expected_head_sha, 'GROUP_PRE_PARENT_HEAD_CAS')
            from . import draft_group_first_time_values as t
            time06=t.is_time06_observation(observation)
            need(time06 is ('time_model' in current),'GROUP_PRE_PARENT_TIME_MODEL_MIXED')
            if time06:t.require_same_lifecycle(current['records'][0]['observation'],observation)
            need(event!=t.KNOWN_EVENT,'GROUP_PRE_PARENT_RESULT_ISSUER_REQUIRED')
            self._event(event, current['events'],time06=time06)
            sequence = current['head']['sequence'] + 1
            need(sequence < MAX_STEPS)
            row = self._row(anchor, observation, sequence,
                current['head']['record_sha'], event,
                min(current['not_after_ms'], observation['not_after_ms']))
            self._create(f'{key}.{sequence:04d}.json', canonical(row))
            head = self._head(key, sequence, digest(row))
            pending = f'{key}.head-next-{sequence:04d}.json'
            self._create(pending, canonical(head))
            try:
                _, actual_sha, actual_pin = self._read(key + '.head.json')
                need(actual_sha == expected_head_sha and actual_pin == current['head_pin'],
                     'GROUP_PRE_PARENT_HEAD_CAS')
                os.replace(pending, key + '.head.json', src_dir_fd=self.parent,
                           dst_dir_fd=self.parent)
                os.fsync(self.parent)
                self._inventory()
            except BaseException:
                self.poisoned = True
                raise
            return {'authority': False, 'created': True, 'head_sha': digest(head),
                    'preparation_identity_sha': preparation_identity(anchor),
                    'allows_automatic_replay': False}

    def bind_parent(self, anchor, *, expected_head_sha, receipt):
        self._writable()
        anchor=validate_anchor(anchor);checksum(expected_head_sha);key=digest(anchor)
        with self._locked():
            values=self._inventory()
            need(set(values)=={key},'GROUP_PRE_PARENT_RELATED_UNRESOLVED')
            current=values[key]
            need(current['head_sha']==expected_head_sha,'GROUP_PRE_PARENT_HEAD_CAS')
            with attachment_receipt_scope(receipt,anchor=anchor,
                    expected_head_sha=expected_head_sha) as (checked,fence,origin):
                closed(checked,('authority','parent_binding','original_head_sha'))
                need(checked['authority'] is False);checksum(checked['original_head_sha'])
                mapping=checked['parent_binding']
                from .draft_group_first_control import validate_attachment_mapping
                mapping=validate_attachment_mapping(mapping)
                need(mapping['anchor_sha']==key and mapping['preparation_identity_sha']==preparation_identity(anchor)
                     and mapping['operator_request_identity_sha']==anchor['original_request_identity_sha']
                     and mapping['original_request_set_sha']==anchor['original_request_set_sha']
                     and mapping['account_partition_sha']==anchor['account_partition_sha'])
                if current['parent_binding'] is not None:
                    need(canonical(mapping)==canonical(current['parent_binding']),
                         'GROUP_PRE_PARENT_MAPPING_CONFLICT')
                    return {'authority':False,'created':False,'head_sha':current['head_sha'],
                            'state':'BOUND_REAL_PARENT','allows_automatic_replay':False}
                need(checked['original_head_sha']==expected_head_sha,'GROUP_PRE_PARENT_HEAD_CAS')
                self._event('BOUND_REAL_PARENT',current['events'],time06='time_model' in current)
                seq=current['head']['sequence']+1;need(seq<MAX_STEPS)
                row=self._row(anchor,current['records'][-1]['observation'],seq,
                    current['head']['record_sha'],'BOUND_REAL_PARENT',
                    current['not_after_ms'] if 'time_model' in current else min(current['not_after_ms'],mapping['not_after_ms']))
                row['parent_binding']=mapping
                if origin is not None:
                    need(origin==HISTORICAL_ATTACHMENT_ORIGIN)
                    if 'time_model' in current:row['attachment_origin']=origin
                    else:row.update(schema=2,profile=HISTORICAL_RECORD_PROFILE,attachment_origin=origin)
                fence()
                self._create(f'{key}.{seq:04d}.json',canonical(row))
                head=self._head(key,seq,digest(row));pending=f'{key}.head-next-{seq:04d}.json'
                fence();self._create(pending,canonical(head))
                try:
                    _,actual_sha,actual_pin=self._read(key+'.head.json')
                    need(actual_sha==expected_head_sha and actual_pin==current['head_pin'],
                         'GROUP_PRE_PARENT_HEAD_CAS')
                    fence()
                    os.replace(pending,key+'.head.json',src_dir_fd=self.parent,dst_dir_fd=self.parent)
                    os.fsync(self.parent);self._inventory();fence()
                except BaseException:
                    self.poisoned=True
                    raise
                return {'authority':False,'created':True,'head_sha':digest(head),
                        'state':'BOUND_REAL_PARENT','allows_automatic_replay':False}

    def note_prepare_known(self,anchor,*,expected_head_sha,receipt):
        # Only the actual original F socket/Popen/BOUND observation can supply
        # this in-process receipt. No status/PASS or recovered Parent implies it.
        from .draft_group_first_control import time06_prepare_result_scope
        from . import draft_group_first_time_values as t
        self._writable();anchor=validate_anchor(anchor);checksum(expected_head_sha)
        key=digest(anchor)
        with self._locked():
            values=self._inventory();need(set(values)=={key})
            current=values[key]
            need('time_model' in current and current['head_sha']==expected_head_sha,
                 'GROUP_PRE_PARENT_HEAD_CAS')
            with time06_prepare_result_scope(receipt,self,anchor,current) as (result,fence):
                fence();self._event(t.KNOWN_EVENT,current['events'],time06=True)
                seq=current['head']['sequence']+1;need(seq<MAX_STEPS)
                row=self._row(anchor,current['records'][0]['observation'],seq,
                    current['head']['record_sha'],t.KNOWN_EVENT,current['not_after_ms'])
                row['prepare_result']=t.validate_result(result)
                self._create(f'{key}.{seq:04d}.json',canonical(row));fence()
                head=self._head(key,seq,digest(row));pending=f'{key}.head-next-{seq:04d}.json'
                self._create(pending,canonical(head));fence()
                try:
                    _,actual,pin=self._read(key+'.head.json')
                    need(actual==expected_head_sha and pin==current['head_pin'],'GROUP_PRE_PARENT_HEAD_CAS')
                    os.replace(pending,key+'.head.json',src_dir_fd=self.parent,dst_dir_fd=self.parent)
                    os.fsync(self.parent);self._inventory();fence()
                except BaseException:
                    self.poisoned=True;raise
                return {'authority':False,'head_sha':digest(head),'allows_automatic_replay':False}

    def close(self, *, original=None):
        if not self.closed:
            self.closed = True
            owned, self.fds = self.fds, []
            close_all([lambda fd=fd: os.close(fd) for fd in reversed(owned)], original)

    def __exit__(self, kind, error, traceback):
        self.close(original=error)
        return False
