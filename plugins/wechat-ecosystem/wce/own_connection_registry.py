"""Bounded multi-account metadata; no credentials or network operations here."""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets
import stat
import time

from .contracts import WCEError
from .own_body_recovery import code_scope
from .own_bootstrap_security import path_check, private_read, decode
from .own_connection_policy import (CAPABILITIES, POLICY, atomic_write, load_policy,
    locked, read_optional, read_registry, registry_path)
from .prepared_contracts import ID, strict_validate
from .service import canonical, digest

MAX_METADATA = 262144  # Legacy per-record envelope; normal account carriers use actual extent.
OWNER = 'connection-owner.json'
HEX = re.compile(r'[a-f0-9]{64}')
APPID = re.compile(r'wx[a-fA-F0-9]{16}')


def prepare_default_registry():
    """Create only the fixed empty container, after the trusted TTY is checked.

    The home directory need not be private; the new account container must be.
    This does not create an owner, account, policy or credential.
    """
    registry = registry_path()
    parent, home = registry.parent, registry.parent.parent
    if os.path.lexists(parent):
        path_check(parent, True)
        return registry
    current = Path('/')
    for part in home.parts[1:]:
        current /= part
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise WCEError('BOOTSTRAP_UNSAFE_PATH')
    if info.st_uid != os.getuid():
        raise WCEError('BOOTSTRAP_UNSAFE_PATH')
    from .bounded_file import identity
    before = identity(info)
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
        try:
            os.mkdir(parent.name, 0o700, dir_fd=fd)
        except FileExistsError:
            pass
        os.fsync(fd)
        if identity(home.lstat()) != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
    finally:
        os.close(fd)
    path_check(parent, True)
    return registry


def sha(value):
    # This is the existing Keychain identity algorithm, not the business digest.
    import json
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def metadata(path):
    from .own_account_metadata import read_metadata
    return read_metadata(Path(path))


def write(path, value, expected_parent=None):
    atomic_write(Path(path), value, None, expected_parent=expected_parent)


def sync(path, directory=False):
    before = path_check(path, directory)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 (os.O_DIRECTORY if directory else 0))
    try:
        from .bounded_file import identity, file_state
        pin = identity(os.fstat(fd)) if directory else file_state(os.fstat(fd))
        if pin != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
        os.fsync(fd)
        if path_check(path, directory) != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
    finally:
        os.close(fd)


def mkdir(parent, name):
    before = path_check(parent, True)
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        from .bounded_file import identity
        if identity(os.fstat(fd)) != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
        os.mkdir(name, 0o700, dir_fd=fd)
        os.fsync(fd)
        if path_check(parent, True) != before:
            raise WCEError('CONNECTION_PATH_CHANGED')
    finally:
        os.close(fd)
    return path_check(Path(parent) / name, True)


def container(parent, name):
    path = Path(parent) / name
    if not os.path.lexists(path):
        mkdir(parent, name)
    path_check(path, True)
    return path


def owner_value(registry, actor):
    return {'schema': 1, 'uid': os.getuid(), 'registry': str(registry),
        'principal_id': actor['principal_id'], 'tenant_id': actor['tenant_id']}


def validate_owner(registry, value):
    if (type(value) is not dict or set(value) != {'schema', 'uid', 'registry', 'principal_id', 'tenant_id'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['uid']) is not int or value['uid'] != os.getuid()
            or value['registry'] != str(registry)):
        raise WCEError('CONNECTION_OWNER_CONFLICT')
    strict_validate(value['principal_id'], ID)
    strict_validate(value['tenant_id'], ID)
    return value


def validate_registry(path, value):
    if (set(value) != {'schema', 'owner_digest', 'connections', 'entries'}
            or type(value['connections']) is not dict or type(value['entries']) is not dict
            or set(value['connections']) != set(value['entries'])):
        raise WCEError('CONNECTION_INVALID_REGISTRY')
    owner = validate_owner(path, read_optional(path.parent / OWNER))
    if value['owner_digest'] != digest(owner):
        raise WCEError('CONNECTION_OWNER_CONFLICT')
    resources, paths, scopes = set(), set(), set()
    for cid, entry in value['entries'].items():
        strict_validate(cid, ID)
        if (type(entry) is not dict or set(entry) != {'appid', 'label', 'identity_digest',
                'credential_scope', 'policy_digest', 'transaction'}):
            raise WCEError('CONNECTION_INVALID_REGISTRY')
        policy = value['connections'][cid]
        if (type(policy) is not str or not Path(policy).is_absolute()
                or Path(policy).name != 'connection-policy.json' or '..' in Path(policy).parts
                or type(entry['appid']) is not str or APPID.fullmatch(entry['appid']) is None):
            raise WCEError('CONNECTION_INVALID_REGISTRY')
        label(entry['label'])
        for key in ('identity_digest', 'credential_scope', 'policy_digest'):
            if type(entry[key]) is not str or HEX.fullmatch(entry[key]) is None:
                raise WCEError('CONNECTION_INVALID_REGISTRY')
        transaction_path(path, entry['transaction'])
        resource = entry['appid'].lower()
        if resource in resources or policy in paths or entry['credential_scope'] in scopes:
            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
        resources.add(resource); paths.add(policy); scopes.add(entry['credential_scope'])
    return value


def label(value):
    if (type(value) is not str or not 1 <= len(value) <= 64
            or any(not c.isprintable() for c in value)):
        raise WCEError('CONNECTION_INVALID_LABEL')
    return value


def transaction_path(registry, name):
    if type(name) is not str or re.fullmatch(r'txn-[a-f0-9]{32}', name) is None:
        raise WCEError('CONNECTION_INVALID_TRANSACTION')
    return registry.parent / 'connection-transactions' / (name + '.json')


def revocation_path(policy):
    return policy.root / ('connection-revoked-' + policy.fingerprint + '.json')


def revoked(policy):
    value = read_optional(revocation_path(policy))
    if value is None:
        return False
    if value != {'schema': 1, 'policy_digest': policy.fingerprint, 'id': policy.value['id']}:
        raise WCEError('CONNECTION_REVOCATION_INVALID')
    return True


PROOF_CHECKS = frozenset({'REGISTRY_MEMBER', 'COMMIT_STATE', 'JOURNAL_DIRECTORY',
                          'PROOF_OWNER_OR_REGISTRY', 'PROOF_MEMBER', 'PROOF_POLICY',
                          'ACCOUNT_ROOT', 'IMAGE_DIRECTORY', 'DATABASE', 'PROFILE'})


class MembershipProofError(WCEError):
    """Nonsecret failing predicate for support. The caller still gets the existing code."""
    def __init__(self, check, *, identity_changed=False):
        super().__init__('CONNECTION_COMMITTED_IDENTITY_CHANGED' if identity_changed else 'CONNECTION_NOT_COMMITTED')
        self.check = check


def inspect_storage_binding(registry, connection_id):
    """Describe stored and current identity pins without adopting either."""
    from .own_connection_policy import load_policy

    data = read_registry(registry)
    entry = data.get('entries', {}).get(connection_id)
    if entry is None:
        return 'PROOF_INCOMPLETE'
    policy = load_policy(data['connections'][connection_id], active=False)
    owner = validate_owner(registry, read_optional(registry.parent / OWNER))
    if not policy.value['enabled'] or revoked(policy):
        return 'PROOF_INCOMPLETE'
    path = transaction_path(registry, policy.value['transaction'])
    with locked(path.with_suffix('.lock'), nonblocking=True, shared=True, existing=True, readonly=True):
        proof = metadata(path) or {}
        change = (proof.get('policies') or {}).get(str(policy.path)) or {}
        pins = change.get('pins') or {}
        if (type(proof.get('schema')) is not int or proof['schema'] not in (1, 2)
                or proof.get('state') != 'COMMITTED' or proof.get('id') != policy.value['transaction']
                or proof.get('owner') != owner or proof.get('registry') != str(registry)
                or owner_value(registry, policy.data['actor']) != owner
                or policy.value['owner_digest'] != digest(owner)
                or policy.value['registry_path'] != str(registry) or policy.data['connection_id'] != connection_id
                or (proof.get('after') or {}).get('entries', {}).get(connection_id) != entry
                or change.get('after') != policy.value
                or entry.get('policy_digest') != policy.fingerprint
                or entry.get('identity_digest') != digest(policy.data)
                or entry.get('credential_scope') != sha(policy.data)
                or entry.get('appid') != policy.data['appid'] or entry.get('transaction') != policy.value['transaction']
                or pins.get('profile_sha256') != sha256(private_read(policy.root / 'profile.json')[0]).hexdigest()):
            return 'PROOF_INCOMPLETE'
        pairs = [(proof.get('registry_parent'), path_check(registry.parent, True)),
                 (proof.get('journal_parent'), path_check(path.parent, True)),
                 (pins.get('root'), policy.root_pin), (pins.get('images'), policy.image_pin),
                 (pins.get('database'), policy.database_pin[:2])]
        if not all(type(old) is list and len(old) == 2
                   and all(type(value) is int and value >= 0 for value in old) for old, _ in pairs):
            return 'PROOF_INCOMPLETE'
        if (all(old[1] == new[1] and old[0] != new[0] for old, new in pairs)
                and len({(old[0], new[0]) for old, new in pairs}) == 1):
            return 'CONSISTENT_DEVICE_REMAP_UNPROVEN'
    return 'STORAGE_IDENTITY_UNVERIFIED'


def check_member(policy, revocation=True, durable=False, *, readonly=False, proof_reader=None):
    value = policy.value
    registry = Path(value['registry_path'])
    if not registry.is_absolute() or registry.name != 'connections.json':
        raise WCEError('CONNECTION_INVALID_REGISTRY')
    data = read_registry(registry)
    cid = policy.data['connection_id']
    entry = data.get('entries', {}).get(cid)
    owner = validate_owner(registry, read_optional(registry.parent / OWNER))
    if (value['owner_digest'] != digest(owner) or data['schema'] != 2
            or owner_value(registry, policy.data['actor']) != owner
            or data['connections'].get(cid) != str(policy.path)
            or type(entry) is not dict or entry['policy_digest'] != policy.fingerprint
            or entry['identity_digest'] != digest(policy.data)
            or entry['credential_scope'] != sha(policy.data)
            or entry['appid'] != policy.data['appid'] or entry['transaction'] != value['transaction']):
        raise MembershipProofError('REGISTRY_MEMBER')
    path = transaction_path(registry, value['transaction'])
    if readonly and durable:
        raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    lock_options = {'nonblocking': True, 'shared': True, 'existing': readonly}
    if readonly:
        lock_options['readonly'] = True
    manager = locked(path.with_suffix('.lock'), **lock_options)
    if readonly and proof_reader is not None:
        from .own_history_locators import _Proofs
        if type(proof_reader) is _Proofs:
            manager = proof_reader.lock(path)
    with manager:
        if proof_reader is None:
            proof = metadata(path)
        else:
            _, raw = proof_reader.read(path, keep=True)
            from .own_account_metadata import decode_metadata
            proof = decode_metadata(raw)
        if type(proof) is not dict or proof.get('state') != 'COMMITTED':
            raise MembershipProofError('COMMIT_STATE')
        if proof.get('journal_parent') != list(path_check(path.parent, True)):
            raise MembershipProofError('JOURNAL_DIRECTORY')
        if proof.get('owner') != owner or proof.get('registry') != str(registry):
            raise MembershipProofError('PROOF_OWNER_OR_REGISTRY')
        after = proof.get('after')
        if type(after) is not dict or type(after.get('entries')) is not dict or after['entries'].get(cid) != entry:
            raise MembershipProofError('PROOF_MEMBER')
        policies = proof.get('policies')
        change = policies.get(str(policy.path)) if type(policies) is dict else None
        if type(change) is not dict or change.get('after') != value:
            raise MembershipProofError('PROOF_POLICY')
        pins = change.get('pins')
        if type(pins) is not dict or pins.get('root') != list(policy.root_pin):
            raise MembershipProofError('ACCOUNT_ROOT', identity_changed=True)
        if pins.get('images') != list(policy.image_pin):
            raise MembershipProofError('IMAGE_DIRECTORY', identity_changed=True)
        if pins.get('database') != list(policy.database_pin[:2]):
            raise MembershipProofError('DATABASE', identity_changed=True)
        if pins.get('profile_sha256') != sha256(private_read(policy.root / 'profile.json')[0]).hexdigest():
            raise MembershipProofError('PROFILE', identity_changed=True)
        if type(proof.get('schema')) is not int or proof['schema'] not in (1, 2):
            raise WCEError('CONNECTION_INVALID_TRANSACTION')
        if proof['schema'] == 2:
            from .own_identity_recovery import validate_relocation_proof
            validate_relocation_proof(proof, reader=proof_reader)
        if durable:
            for item in (registry.parent / OWNER, policy.path, registry, path):
                sync(item); sync(item.parent, True)
    if revocation and revoked(policy):
        raise WCEError('CONNECTION_DISCONNECTED')
    return entry


def revoke(policy):
    from .own_replacement_batch import revocation_gate
    with revocation_gate(policy):
        return _revoke_under_replacement_gate(policy)


def _revoke_under_replacement_gate(policy):
    with locked(policy.root / 'connection-policy.lock'):
        current = load_policy(policy.path, active=False)
        if current.fingerprint != policy.fingerprint:
            raise WCEError('CONNECTION_POLICY_CHANGED')
        check_member(current, revocation=False)
        atomic_write(revocation_path(current), {'schema': 1,
            'policy_digest': current.fingerprint, 'id': current.value['id']}, expected_parent=policy.root_pin)
    return {'connection_id': policy.data['connection_id'], 'state': 'DISCONNECTED'}


def snapshot(registry, *, readonly=False, proof_reader=None):
    registry = Path(registry)
    parent = path_check(registry.parent, True)
    data = read_registry(registry)
    owner = read_optional(registry.parent / OWNER)
    if owner is not None:
        validate_owner(registry, owner)
    policies, roots, databases, resources, scopes = {}, set(), set(), set(), set()
    for cid, path in data['connections'].items():
        policy = load_policy(path, active=False)
        if policy.data['connection_id'] != cid:
            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
        implied = owner_value(registry, policy.data['actor'])
        if owner is None:
            owner = implied
        if owner != implied:
            raise WCEError('CONNECTION_OWNER_CONFLICT')
        if policy.value['schema'] == 2:
            check_member(policy, revocation=False, readonly=readonly, proof_reader=proof_reader)
        resource, scope = policy.data['appid'].lower(), sha(policy.data)
        if (policy.root_pin in roots or policy.database_pin[:2] in databases
                or resource in resources or scope in scopes):
            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
        roots.add(policy.root_pin); databases.add(policy.database_pin[:2])
        resources.add(resource); scopes.add(scope)
        profile, _ = private_read(policy.root / 'profile.json')
        from .own_connection_policy import proposal
        if proposal(policy.root / 'profile.json')['identity'] != policy.data:
            raise WCEError('CONNECTION_INVALID_IDENTITY')
        policies[path] = {'value': policy.value, 'root': list(policy.root_pin),
            'images': list(policy.image_pin), 'database': list(policy.database_pin[:2]),
            'profile_sha256': sha256(profile).hexdigest(),
            'revoked': revoked(policy) if policy.value['schema'] == 2 else not policy.value['enabled']}
    return {'registry': str(registry), 'registry_value': metadata(registry),
        'parent': list(parent), 'owner_disk': read_optional(registry.parent / OWNER),
        'owner': owner, 'policies': policies, 'scope': code_scope()}


def derived_identity(base, appid):
    """The sole deterministic owner/resource mapping for new and resumed setup."""
    registry = Path(base['registry'])
    validate_owner(registry, base['owner'])
    key = sha({'owner': base['owner'], 'appid': appid})[:24]
    root = registry.parent / 'accounts' / key
    if len(os.fsencode(root / 'connection.sock')) > 100:
        raise WCEError('CONNECTION_SOCKET_PATH_TOO_LONG')
    actor = {'principal_id': base['owner']['principal_id'], 'tenant_id': base['owner']['tenant_id'],
        'client_id': 'local-client-' + key, 'session_id': 'resource-session-' + key}
    return {'actor': actor, 'connection_id': 'own-' + key, 'appid': appid, 'resource_id': appid,
        'generation': 1, 'epoch': 0, 'private_directory': str(root)}


def propose(appid, display_label, registry=None):
    registry = Path(registry or registry_path())
    if type(appid) is not str or APPID.fullmatch(appid) is None:
        raise WCEError('CONNECTION_INVALID_APPID')
    appid = appid.lower()
    label(display_label)
    base = snapshot(registry)
    for old in base['policies'].values():
        if old['value']['identity']['appid'].lower() == appid:
            raise WCEError('CONNECTION_RESOURCE_ALREADY_BOUND')
    if base['owner'] is None:
        # Missing owner in a previous enrollment is never a fresh installation.
        if os.path.lexists(registry.parent / 'connection-enrollments'):
            raise WCEError('CONNECTION_OWNER_REQUIRED')
        base['owner'] = owner_value(registry, {'principal_id': 'local-owner-' + secrets.token_hex(12),
            'tenant_id': 'local-install-' + secrets.token_hex(12)})
    identity = derived_identity(base, appid)
    root = Path(identity['private_directory'])
    pending = registry.parent / 'connection-enrollments' / (appid + '.json')
    if os.path.lexists(pending.parent):
        path_check(pending.parent, True)
    if os.path.lexists(root) or os.path.lexists(pending):
        raise WCEError('CONNECTION_ENROLLMENT_REQUIRES_RECONCILIATION')
    return {'base': base, 'identity': identity, 'label': display_label,
        'transaction': 'txn-' + secrets.token_hex(16)}


def check_snapshot(base, *, proof_reader=None):
    actual = snapshot(Path(base['registry']), proof_reader=proof_reader)
    # A proposed fresh owner is not yet on disk; all other observations are exact.
    expected = dict(base)
    if expected['owner_disk'] is None and not expected['policies']:
        expected['owner'] = None
    if actual != expected:
        raise WCEError('CONNECTION_REVIEW_CHANGED')


@contextmanager
def publication_locks(roots, registry):
    with ExitStack() as stack:
        for root in sorted(roots, key=str):
            stack.enter_context(locked(root / 'connection-start.lock', nonblocking=True))
            stack.enter_context(locked(root / 'connection.lock', nonblocking=True))
        for root in sorted(roots, key=str):
            stack.enter_context(locked(root / 'connection-policy.lock', nonblocking=True))
        stack.enter_context(locked(registry.parent / 'connections.lock', nonblocking=True))
        yield stack
