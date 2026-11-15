"""Human-created persistent delegation; no enablement route in MCP.

Private files protect against accidental cross-user/cross-instance use. They do
not sandbox malicious processes already running as the same OS user.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time

from .bounded_file import identity, FileSource, file_state
from .contracts import Actor, WCEError
from .own_body_recovery import code_scope
from .own_bootstrap_security import decode, path_check, private_read
from .own_keychain import credential_scope
from .prepared_contracts import ID, strict_validate
from .service import canonical, digest

POLICY = 'PERSONAL_DRAFT_DELEGATION_V1'
CAPABILITIES = ['connection', 'local_inputs', 'draft_images', 'draft_save', 'draft_read']
IDENTITY_FIELDS = {'actor', 'connection_id', 'appid', 'resource_id', 'generation', 'epoch', 'private_directory'}


def registry_path():
    return Path.home() / '.wce' / 'connections.json'


def read_optional(path, maximum=16384):
    if not os.path.lexists(path):
        return None
    if maximum == 16384:
        raw, _ = private_read(path)
    else:
        before = path_check(path)
        if not 0 < before[2] <= maximum:
            raise WCEError('CONNECTION_METADATA_LIMIT')
        raw = FileSource(Path(path).parent).read(Path(path).name)
        if before != path_check(path):
            raise WCEError('CONNECTION_PATH_CHANGED')
    return decode(raw, maximum)


@contextmanager
def locked(path, nonblocking=False, shared=False, existing=False, *, readonly=False):
    if readonly and not (existing and shared):
        raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    path = Path(path)
    parent = path_check(path.parent, True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    if identity(os.fstat(directory)) != parent:
        os.close(directory)
        raise WCEError('CONNECTION_PATH_CHANGED')
    try:
        flags = (os.O_RDONLY if readonly else os.O_RDWR) | os.O_NOFOLLOW | os.O_NONBLOCK
        if existing:
            fd = os.open(path.name, flags, dir_fd=directory)
        else:
            try:
                fd = os.open(path.name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
            except FileExistsError:
                fd = os.open(path.name, flags, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or (existing and info.st_size != 0)):
            raise WCEError('CONNECTION_UNSAFE_LOCK')
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
                        | (fcntl.LOCK_NB if nonblocking else 0))
        except BlockingIOError:
            raise WCEError('CONNECTION_BUSY') from None
        current = os.fstat(fd)
        if (parent != path_check(path.parent, True) or identity(info) != identity(path.lstat())
                or current.st_nlink != 1 or stat.S_IMODE(current.st_mode) != 0o600
                or current.st_uid != os.getuid()):
            raise WCEError('CONNECTION_PATH_CHANGED')
        yield fd
        if existing:
            current = os.fstat(fd)
            if (parent != path_check(path.parent, True)
                    or file_state(info) != file_state(current)
                    or file_state(info) != file_state(path.lstat())):
                raise WCEError('CONNECTION_PATH_CHANGED')
    finally:
        os.close(fd)


def atomic_write(path, value, maximum=16384, expected_parent=None):
    """Caller holds the independent writer lock; directory pin covers replacement."""
    path = Path(path)
    parent_pin = path_check(path.parent, True)
    if expected_parent is not None and tuple(expected_parent) != parent_pin:
        raise WCEError('CONNECTION_PATH_CHANGED')
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.wce-' + secrets.token_hex(16)
    try:
        if identity(os.fstat(parent)) != parent_pin:
            raise WCEError('CONNECTION_PATH_CHANGED')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            data = (canonical(value) + '\n').encode()
            if maximum is not None and len(data) > maximum:
                raise WCEError('CONNECTION_METADATA_LIMIT')
            with os.fdopen(fd, 'wb', closefd=False) as out:
                out.write(data); out.flush(); os.fsync(fd)
        finally:
            os.close(fd)
        if parent_pin != path_check(path.parent, True):
            raise WCEError('CONNECTION_PATH_CHANGED')
        os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        if maximum is None:
            from .own_account_metadata import read_metadata
            observed=read_metadata(path)
        else:observed=read_optional(path,maximum)
        if parent_pin != path_check(path.parent, True) or observed != value:
            raise WCEError('CONNECTION_WRITE_UNKNOWN')
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def validate_identity(data, root):
    if (type(data) is not dict or set(data) != IDENTITY_FIELDS
            or data['private_directory'] != str(root) or data['resource_id'] != data['appid']
            or type(data['appid']) is not str or re.fullmatch(r'wx[a-fA-F0-9]{16}', data['appid']) is None
            or type(data['actor']) is not dict
            or set(data['actor']) != {'tenant_id', 'principal_id', 'client_id', 'session_id'}
            or type(data['generation']) is not int or not 1 <= data['generation'] < 2**63
            or type(data['epoch']) is not int or not 0 <= data['epoch'] < 2**63):
        raise WCEError('CONNECTION_INVALID_IDENTITY')
    for value in (*data['actor'].values(), data['connection_id']):
        strict_validate(value, ID)
    path_check(root, True)
    path_check(root / 'images', True)
    path_check(root / 'state.sqlite3')
    return data


def proposal(profile):
    """Read expired legacy identity as historical data, never as a live grant."""
    profile = Path(profile)
    raw, _ = private_read(profile)
    old = decode(raw)
    if (type(old) is not dict or set(old) != IDENTITY_FIELDS | {'schema', 'source_kind', 'expires_at'}
            or type(old['schema']) is not int or old['schema'] != 1
            or old['source_kind'] != 'OPERATOR_ATTESTED'):
        raise WCEError('CONNECTION_INVALID_IDENTITY')
    data = validate_identity({k: old[k] for k in IDENTITY_FIELDS}, profile.parent)
    prior_path = profile.parent / 'connection-policy.json'
    previous = None
    if os.path.lexists(prior_path):
        load_policy(prior_path, active=False)
        previous = sha256(private_read(prior_path)[0]).hexdigest()
    return {'profile_path': str(profile), 'profile_digest': sha256(raw).hexdigest(), 'identity': data,
            'root_pin': list(path_check(profile.parent, True)),
            'previous': previous, 'candidate_scope': code_scope(), 'policy': POLICY,
            'capabilities': CAPABILITIES, 'duration': 'UNTIL_DISCONNECTED'}


def enable(reviewed, registry=None):
    """Trusted TTY setup calls this only after its fresh challenge succeeds."""
    root = Path(reviewed['identity']['private_directory'])
    registry = Path(registry or registry_path())
    # Publish the registry pointer first, enabled policy last. An interrupted
    # first binding is unbound, never an enabled policy outside the registry.
    with locked(root / 'connection-policy.lock'), locked(registry.parent / 'connections.lock'):
        if proposal(reviewed['profile_path']) != reviewed:
            raise WCEError('CONNECTION_REVIEW_CHANGED')
        path = root / 'connection-policy.json'
        prior = read_optional(path)
        value = {'schema': 1, 'policy': POLICY, 'id': 'connection-policy-' + secrets.token_hex(16),
                 'revision': 1 if prior is None else prior['revision'] + 1,
                 'identity': reviewed['identity'], 'candidate_scope': code_scope(),
                 'capabilities': CAPABILITIES, 'duration': 'UNTIL_DISCONNECTED',
                 'enabled': True, 'confirmed_at': time.time()}
        data = read_registry(registry)
        if data['schema'] != 1:
            raise WCEError('CONNECTION_MULTI_ACCOUNT_SETUP_REQUIRED')
        cid = value['identity']['connection_id']
        if cid in data['connections'] and data['connections'][cid] != str(path):
            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
        # One-account edition does not silently collect or select other accounts.
        if any(k != cid for k in data['connections']):
            raise WCEError('CONNECTION_SINGLE_ACCOUNT_ONLY')
        from .draft_revision_guard import identity_binding
        from .draft_revision_store import RevisionStore
        # A legacy profile/database is already an account. Missing policy does
        # not prove it is a new identity, and may not reset sticky revision state.
        # Complete this check before publishing any registry or policy pointer.
        try:
            with RevisionStore(root,digest(identity_binding(value['identity'],'OPERATOR_ATTESTED')),
                    lambda:None).connection():pass
        except OSError:raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD') from None
        data['connections'][cid] = str(path)
        atomic_write(registry, data)
        if proposal(reviewed['profile_path']) != reviewed:
            raise WCEError('CONNECTION_REVIEW_CHANGED')
        atomic_write(path, value)
    return load_policy(path)


def read_registry(path=None):
    path = Path(path or registry_path())
    from .own_account_metadata import read_metadata
    data = read_metadata(path)
    if data is None:
        if os.path.lexists(path.parent / 'connection-owner.json'):
            raise WCEError('CONNECTION_REGISTRY_MISSING')
        return {'schema': 1, 'connections': {}}
    if type(data) is dict and type(data.get('schema')) is int and data['schema'] == 2:
        from .own_connection_registry import validate_registry
        return validate_registry(path, data)
    if (type(data) is not dict or set(data) != {'schema', 'connections'}
            or type(data['schema']) is not int or data['schema'] != 1
            or type(data['connections']) is not dict or len(data['connections']) > 1):
        raise WCEError('CONNECTION_INVALID_REGISTRY')
    for key, value in data['connections'].items():
        strict_validate(key, ID)
        if type(value) is not str or not Path(value).is_absolute() or Path(value).name != 'connection-policy.json':
            raise WCEError('CONNECTION_INVALID_REGISTRY')
    return data


@dataclass(frozen=True)
class ConnectionPolicy:
    path: Path
    value: dict
    pin: tuple
    root_pin: tuple
    image_pin: tuple
    database_pin: tuple

    @property
    def root(self):
        return self.path.parent

    @property
    def data(self):
        return self.value['identity']

    @property
    def actor(self):
        return Actor(**self.data['actor'])

    @property
    def fingerprint(self):
        return digest(self.value)

    def check(self, candidate=True, *, readonly=False, proof_reader=None, allow_disconnected=False):
        if (path_check(self.path) != self.pin or path_check(self.root, True) != self.root_pin
                or path_check(self.root / 'images', True) != self.image_pin
                or path_check(self.root / 'state.sqlite3')[:2] != self.database_pin[:2]):
            raise WCEError('CONNECTION_POLICY_CHANGED')
        if allow_disconnected and not readonly:
            raise WCEError('CONNECTION_INVALID_ARGUMENTS')
        if not self.value['enabled'] and not allow_disconnected:
            raise WCEError('CONNECTION_DISCONNECTED')
        if self.value['schema'] == 2:
            from .own_connection_registry import check_member
            check_member(self, revocation=not allow_disconnected, readonly=readonly, proof_reader=proof_reader)
        # A managed software update keeps the existing account delegation.
        # Account membership, identity and disconnection are checked above.
        return True

    def delegation(self):
        self.check()
        return {'id': self.value['id'], 'revision': self.value['revision'],
                'policy_digest': self.fingerprint, 'candidate_scope': self.value['candidate_scope']}


def load_policy(path, active=True):
    path = Path(path)
    raw, pin = private_read(path)
    value = decode(raw)
    expected = {'schema', 'policy', 'id', 'revision', 'identity', 'candidate_scope', 'capabilities',
                'duration', 'enabled', 'confirmed_at'}
    if type(value) is dict and type(value.get('schema')) is int and value['schema'] == 2:
        expected |= {'registry_path', 'owner_digest', 'transaction'}
    if (type(value) is not dict or set(value) != expected or type(value['schema']) is not int
            or value['schema'] not in (1, 2) or value['policy'] != POLICY or type(value['enabled']) is not bool
            or type(value['revision']) is not int or value['revision'] < 1
            or value['capabilities'] != CAPABILITIES or value['duration'] != 'UNTIL_DISCONNECTED'
            or type(value['confirmed_at']) not in (int, float)
            or not math.isfinite(value['confirmed_at']) or value['confirmed_at'] <= 0
            or type(value['candidate_scope']) is not str
            or re.fullmatch('[a-f0-9]{64}', value['candidate_scope']) is None):
        raise WCEError('CONNECTION_INVALID_POLICY')
    strict_validate(value['id'], ID)
    if value['schema'] == 2:
        if (type(value['registry_path']) is not str
                or not Path(value['registry_path']).is_absolute()
                or Path(value['registry_path']).name != 'connections.json'
                or '..' in Path(value['registry_path']).parts
                or type(value['owner_digest']) is not str
                or re.fullmatch('[a-f0-9]{64}', value['owner_digest']) is None
                or type(value['transaction']) is not str
                or re.fullmatch('txn-[a-f0-9]{32}', value['transaction']) is None):
            raise WCEError('CONNECTION_INVALID_POLICY')
    validate_identity(value['identity'], path.parent)
    policy = ConnectionPolicy(path, value, pin, path_check(path.parent, True),
        path_check(path.parent / 'images', True), path_check(path.parent / 'state.sqlite3'))
    if active:
        policy.check()
    return policy


def resolve(connection_id, registry=None, active=True, *, readonly=False):
    selected = Path(registry or registry_path())
    data = read_registry(selected)
    path = data['connections'].get(connection_id)
    if path is None:
        raise WCEError('CONNECTION_NOT_BOUND')
    policy = load_policy(path, active=active)
    if policy.data['connection_id'] != connection_id:
        raise WCEError('CONNECTION_REGISTRY_CONFLICT')
    if data['schema'] == 2:
        from .own_connection_registry import check_member
        if policy.value.get('registry_path') != str(selected):
            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
        check_member(policy, revocation=False, readonly=readonly)
    return policy


def disconnect(policy):
    if policy.value['schema'] == 2:
        from .own_connection_registry import revoke
        return revoke(policy)
    from .own_replacement_batch import revocation_gate
    with revocation_gate(policy):
        return _disconnect_legacy_under_replacement_gate(policy)


def _disconnect_legacy_under_replacement_gate(policy):
    with locked(policy.root / 'connection-policy.lock'):
        current = load_policy(policy.path, active=False)
        if current.fingerprint != policy.fingerprint:
            raise WCEError('CONNECTION_POLICY_CHANGED')
        if current.value['enabled']:
            atomic_write(policy.path, current.value | {'enabled': False, 'revision': current.value['revision'] + 1})
    return {'connection_id': policy.data['connection_id'], 'state': 'DISCONNECTED'}
