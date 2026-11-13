"""Trusted TTY enrollment. One validation request; no MCP enrollment route."""
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import time

from .contracts import Secret, WCEError
from .own_bootstrap_security import acquire_pending, path_check, private_read
from .own_connection_policy import (CAPABILITIES, POLICY, atomic_write, load_policy, locked,
                                    read_optional, validate_identity)
from .own_connection_registry import (OWNER, check_snapshot, container, digest, metadata,
    mkdir, publication_locks, sha, snapshot, sync, transaction_path, write)
from .own_connection_token import CachedToken, ContinuousClock
from .own_keychain import KeychainCredential, valid_secret
from .own_store import OwnStore
from .service import canonical


def exclusive(path, value, expected_parent=None):
    parent = path_check(path.parent, True)
    if expected_parent is not None and parent != tuple(expected_parent):
        raise WCEError('CONNECTION_PATH_CHANGED')
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        from .bounded_file import identity
        if identity(os.fstat(directory)) != parent:
            raise WCEError('CONNECTION_PATH_CHANGED')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as out:
                out.write((canonical(value) + '\n').encode()); out.flush(); os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        if path_check(path.parent, True) != parent or metadata(path) != value:
            raise WCEError('CONNECTION_WRITE_UNKNOWN')
    finally:
        os.close(directory)


class PendingIdentity:
    """Private credential adapter bound to this one approved, unpublished root."""
    def __init__(self, reviewed):
        self.reviewed, self.data = reviewed, reviewed['identity']
        self.root = Path(self.data['private_directory'])
        self.root_pin = path_check(self.root, True)
        self.image_pin = path_check(self.root / 'images', True)
        self.database_pin = path_check(self.root / 'state.sqlite3')[:2]
        self.profile_pin = path_check(self.root / 'profile.json')

    def check(self):
        check_snapshot(self.reviewed['base'])
        validate_identity(self.data, self.root)
        if (path_check(self.root, True) != self.root_pin
                or path_check(self.root / 'images', True) != self.image_pin
                or path_check(self.root / 'state.sqlite3')[:2] != self.database_pin
                or path_check(self.root / 'profile.json') != self.profile_pin):
            raise WCEError('CONNECTION_ENROLLMENT_CHANGED')

    def pins(self):
        return {'root': list(self.root_pin), 'images': list(self.image_pin),
                'database': list(self.database_pin), 'profile': list(self.profile_pin)}


def initialize(reviewed, schema=1):
    """Only after the TTY approval; initialization grants no business authority."""
    base = reviewed['base']
    registry = Path(base['registry'])
    with locked(registry.parent / 'connections.lock', nonblocking=True):
        check_snapshot(base)
        if base['owner_disk'] is None:
            exclusive(registry.parent / OWNER, base['owner'], base['parent'])
            base['owner_disk'] = base['owner']
        if base['registry_value'] is None:
            empty = {'schema': 2, 'owner_digest': digest(base['owner']), 'connections': {}, 'entries': {}}
            write(registry, empty, base['parent'])
            base['registry_value'] = empty
        check_snapshot(base)
    pending_dir = container(registry.parent, 'connection-enrollments')
    pending_parent = list(path_check(pending_dir, True))
    pending = pending_dir / (reviewed['identity']['appid'] + '.json')
    reservation = {'schema': 1, 'review': reviewed, 'attempt': 'NOT_SENT',
                   'credential': 'NOT_STORED', 'binding': 'NOT_COMMITTED',
                   'parent': pending_parent}
    if schema == 2:
        from .own_enrollment_checked import initial_record
        reservation = initial_record(reviewed, pending_parent)
    elif schema != 1:
        raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    exclusive(pending, reservation, pending_parent)
    parent = container(registry.parent, 'accounts')
    root = Path(reviewed['identity']['private_directory'])
    if root.parent != parent:
        raise WCEError('CONNECTION_INVALID_IDENTITY')
    mkdir(parent, root.name)
    mkdir(root, 'images')
    atomic_write(root / 'profile.json', reviewed['identity'] | {'schema': 1,
        'source_kind': 'OPERATOR_ATTESTED', 'expires_at': 1})
    OwnStore(root / 'state.sqlite3', 'OPERATOR_ATTESTED', persistent=True)
    sync(root / 'state.sqlite3'); sync(root, True)
    from .draft_revision_guard import initialize_new_account
    # This root was created exclusively above and is not published/enabled.
    initialize_new_account(reviewed['identity'],lambda:check_snapshot(base))
    identity = PendingIdentity(reviewed)
    reservation = reservation | {'pins': identity.pins()}
    write(pending, reservation, pending_parent)
    return identity, pending, reservation


def policy_value(identity, base, transaction, revision, enabled):
    import secrets
    return {'schema': 2, 'policy': POLICY, 'id': 'connection-policy-' + secrets.token_hex(16),
        'revision': revision, 'identity': identity, 'candidate_scope': base['scope'],
        'capabilities': CAPABILITIES, 'duration': 'UNTIL_DISCONNECTED', 'enabled': enabled,
        'confirmed_at': time.time(), 'registry_path': base['registry'],
        'owner_digest': digest(base['owner']), 'transaction': transaction}


def published_entry(value, label):
    data = value['identity']
    return {'appid': data['appid'], 'label': label, 'identity_digest': digest(data),
        'credential_scope': sha(data), 'policy_digest': digest(value),
        'transaction': value['transaction']}


def transaction(reviewed, pending):
    base = reviewed['base']
    before = base['registry_value']
    after = {'schema': 2, 'owner_digest': digest(base['owner']),
        'connections': dict(before['connections']), 'entries': dict(before.get('entries', {}))}
    changes = {}
    for path, old in base['policies'].items():
        if reviewed.get('preserve_existing') is True:
            continue
        value = old['value']
        cid = value['identity']['connection_id']
        reenabling = reviewed.get('reenable') == cid
        if value['schema'] == 2 and value['candidate_scope'] == base['scope'] and not reenabling:
            continue
        updated = policy_value(value['identity'], base, reviewed['transaction'],
            value['revision'] + 1, reenabling or (value['enabled'] and not old['revoked']))
        changes[path] = {'before': value, 'after': updated,
                        'pins': {k: old[k] for k in ('root', 'images', 'database', 'profile_sha256', 'revoked')}}
        after['entries'][cid] = published_entry(updated,
            before.get('entries', {}).get(cid, {}).get('label', cid))
    if pending is not None:
        data = reviewed['identity']
        path = str(pending.root / 'connection-policy.json')
        value = policy_value(data, base, reviewed['transaction'], 1, True)
        changes[path] = {'before': None, 'after': value, 'pins': {'root': list(pending.root_pin),
            'images': list(pending.image_pin), 'database': list(pending.database_pin),
            'profile_sha256': sha256(private_read(pending.root / 'profile.json')[0]).hexdigest(), 'revoked': False}}
        after['connections'][data['connection_id']] = path
        after['entries'][data['connection_id']] = published_entry(value, reviewed['label'])
    return {'schema': 1, 'id': reviewed['transaction'], 'state': 'PREPARED',
        'registry': base['registry'], 'registry_parent': base['parent'], 'owner': base['owner'],
        'before': before, 'after': after, 'policies': changes}


def check_transaction(value):
    """No third values may be overwritten during local recovery."""
    from .own_connection_registry import revoked
    if (type(value) is not dict or set(value) != {'schema', 'id', 'state', 'registry',
            'registry_parent', 'journal_parent', 'owner', 'before', 'after', 'policies'} or value['schema'] != 1
            or value['state'] not in {'PREPARED', 'COMMITTED', 'ROLLED_BACK'}
            or type(value['policies']) is not dict or not value['policies']):
        raise WCEError('CONNECTION_INVALID_TRANSACTION')
    registry = Path(value['registry'])
    if (list(path_check(registry.parent, True)) != value['registry_parent']
            or list(path_check(transaction_path(registry, value['id']).parent, True)) != value['journal_parent']
            or read_optional(registry.parent / OWNER) != value['owner']):
        raise WCEError('CONNECTION_RECOVERY_CONFLICT')
    for path, change in value['policies'].items():
        root, pins = Path(path).parent, change['pins']
        if (list(path_check(root, True)) != pins['root']
                or list(path_check(root / 'images', True)) != pins['images']
                or list(path_check(root / 'state.sqlite3')[:2]) != pins['database']
                or sha256(private_read(root / 'profile.json')[0]).hexdigest() != pins['profile_sha256']
                or metadata(path) not in (change['before'], change['after'])):
            raise WCEError('CONNECTION_RECOVERY_CONFLICT')
        # A post-proposal revocation must never be rolled back by recovery.
        if change['before'] is not None and change['before']['schema'] == 2:
            from dataclasses import replace
            current = load_policy(path, active=False)
            old = replace(current, value=change['before'])
            if revoked(old) != pins['revoked']:
                raise WCEError('CONNECTION_RECOVERY_CONFLICT')
        if metadata(path) == change['after']:
            current = load_policy(path, active=False)
            if revoked(current):
                raise WCEError('CONNECTION_RECOVERY_CONFLICT')
    return registry


def reconcile(path):
    """Explicit metadata-only repair. Never repeats an enrollment/token request."""
    from .own_replacement_batch import maintenance_gate
    value=metadata(Path(path))
    registry=check_transaction(value)
    with maintenance_gate(registry):
        return _reconcile_under_replacement_gate(path)


def _reconcile_under_replacement_gate(path):
    path = Path(path)
    value = metadata(path)
    registry = check_transaction(value)
    if path != transaction_path(registry, value['id']):
        raise WCEError('CONNECTION_INVALID_TRANSACTION')
    roots = {Path(p).parent for p in value['policies']}
    with publication_locks(roots, registry), locked(path.with_suffix('.lock'), nonblocking=True):
        if metadata(path) != value:
            raise WCEError('CONNECTION_RECOVERY_CONFLICT')
        check_transaction(value)
        actual = metadata(registry)
        if actual == value['after']:
            if any(metadata(p) != c['after'] for p, c in value['policies'].items()):
                raise WCEError('CONNECTION_RECOVERY_CONFLICT')
            for p in value['policies']:
                sync(p); sync(Path(p).parent, True)
            sync(registry); sync(registry.parent, True)
            write(path, value | {'state': 'COMMITTED'}, value['journal_parent'])
            return 'COMMITTED'
        if actual != value['before'] or value['state'] == 'COMMITTED':
            raise WCEError('CONNECTION_RECOVERY_CONFLICT')
        for p, c in value['policies'].items():
            if c['before'] is not None and metadata(p) == c['after']:
                write(p, c['before'], c['pins']['root'])
        # The unpublished new root/policy/attempt remain reserved, never reused.
        write(path, value | {'state': 'ROLLED_BACK'}, value['journal_parent'])
        return 'ROLLED_BACK'


def publish(reviewed, pending, held_roots=frozenset()):
    """Return new policy and its still-owned start/lifetime locks for handoff."""
    registry = Path(reviewed['base']['registry'])
    pending.check()
    value = transaction(reviewed, pending)
    directory = container(registry.parent, 'connection-transactions')
    value['journal_parent'] = list(path_check(directory, True))
    path = transaction_path(registry, reviewed['transaction'])
    retained, others = ExitStack(), ExitStack()
    try:
        # Keep the new account locked through the seeded broker's startup.
        for root in sorted({Path(p).parent for p in value['policies']}, key=str):
            if root in held_roots:
                continue
            target = retained if root == pending.root else others
            others.enter_context(locked(root / 'connection-start.lock', nonblocking=True))
            fd = target.enter_context(locked(root / 'connection.lock', nonblocking=True))
            if root == pending.root:
                lifetime = fd
        with ExitStack() as policies:
            for root in sorted({Path(p).parent for p in value['policies']}, key=str):
                policies.enter_context(locked(root / 'connection-policy.lock', nonblocking=True))
            policies.enter_context(locked(registry.parent / 'connections.lock', nonblocking=True))
            policies.enter_context(locked(path.with_suffix('.lock'), nonblocking=True))
            pending.check()
            exclusive(path, value, value['journal_parent'])
            for p, change in value['policies'].items():
                write(p, change['after'], change['pins']['root'])
            write(registry, value['after'], value['registry_parent'])
            write(path, value | {'state': 'COMMITTED'}, value['journal_parent'])
        policy = load_policy(pending.root / 'connection-policy.json')
        return policy, retained, lifetime
    except BaseException:
        retained.close()
        raise
    finally:
        others.close()


def enroll(reviewed, read_secret, acquire=acquire_pending, credential_factory=KeychainCredential,
           wall=time.time, continuous=None):
    from .own_replacement_batch import maintenance_gate
    with maintenance_gate(Path(reviewed['base']['registry'])):
        return _enroll_under_replacement_gate(reviewed,read_secret,acquire,credential_factory,wall,continuous)


def _enroll_under_replacement_gate(reviewed, read_secret, acquire, credential_factory, wall, continuous):
    """Caller has just obtained exact human approval. No retry is performed."""
    continuous = continuous or ContinuousClock()
    registry = Path(reviewed['base']['registry'])
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True), ExitStack() as upgrade_locks:
        check_snapshot(reviewed['base'])
        held_roots = hold_upgrades(reviewed, upgrade_locks)
        pending, record_path, record = initialize(reviewed)
        pending.check()
        secret = read_secret()
        try:
            if not valid_secret(secret):
                raise WCEError('BOOTSTRAP_CREDENTIAL_INVALID')
            pending.check()
            record = record | {'attempt': 'SPENT_RESULT_UNKNOWN'}
            write(record_path, record, record['parent'])
            pending.check()
            before_wall, before_cont = wall(), continuous()
            token, deadline, _ = acquire(pending.data['appid'], secret)
            if type(token) is not Secret or not 30 < deadline - before_wall <= 7200.1:
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            cached = CachedToken(token, before_wall, before_cont, deadline,
                                 before_cont + deadline - before_wall)
            pending.check()
            if (wall() + 30 >= deadline or continuous() + 30 >= cached.continuous_deadline
                    or wall() < before_wall or continuous() < before_cont
                    or abs((wall() - before_wall) - (continuous() - before_cont)) >= 5):
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            record = record | {'attempt': 'VALIDATED', 'credential': 'STORE_ATTEMPT_UNKNOWN'}
            write(record_path, record, record['parent'])
            credential_factory(pending).store(secret)
            pending.check()
            record = record | {'credential': 'STORED'}
            write(record_path, record, record['parent'])
        finally:
            secret = None
        policy, retained, lifetime = publish(reviewed, pending, held_roots)
        try:
            record = record | {'binding': 'COMMITTED'}
            write(record_path, record, record['parent'])
            return policy, cached, retained, lifetime
        except BaseException:
            retained.close()
            raise


def hold_upgrades(reviewed, stack):
    if reviewed.get('preserve_existing') is True:
        check_snapshot(reviewed['base'])
        return frozenset()
    roots = {Path(p).parent for p, old in reviewed['base']['policies'].items()
        if old['value']['schema'] == 1 or old['value']['candidate_scope'] != reviewed['base']['scope']}
    for root in sorted(roots, key=str):
        stack.enter_context(locked(root / 'connection-start.lock', nonblocking=True))
        stack.enter_context(locked(root / 'connection.lock', nonblocking=True))
    check_snapshot(reviewed['base'])
    return roots


def resume_publication(name, registry):
    """Local-only completion after validated/stored enrollment lost its process.

    It deliberately returns BOUND_IDLE: the validation token was never persisted.
    """
    from .own_replacement_batch import maintenance_gate
    with maintenance_gate(Path(registry)):
        return _resume_publication_under_replacement_gate(name,registry)


def _resume_publication_under_replacement_gate(name, registry):
    registry = Path(registry)
    path = transaction_path(registry, name)
    if os.path.lexists(path):
        return reconcile(path)
    directory = registry.parent / 'connection-enrollments'
    path_check(directory, True)
    matches = []
    for p in directory.iterdir():
        record = metadata(p)
        if type(record) is dict and type(record.get('review')) is dict and record['review'].get('transaction') == name:
            matches.append((p, record))
        elif type(record) is dict and record.get('schema') in {2,3}:
            from .own_enrollment_checked import publication_match, resume_checked_publication
            if publication_match(record, name):
                matches.append((p, record))
    if len(matches) != 1:
        raise WCEError('CONNECTION_ENROLLMENT_REQUIRES_RECONCILIATION')
    record_path, record = matches[0]
    if record.get('schema') in {2,3}:
        return resume_checked_publication(record_path, record, registry)
    if list(path_check(directory, True)) != record.get('parent'):
        raise WCEError('CONNECTION_RECOVERY_CONFLICT')
    if record.get('attempt') != 'VALIDATED' or record.get('credential') != 'STORED':
        raise WCEError('CONNECTION_ENROLLMENT_REQUIRES_HUMAN_DECISION')
    reviewed = record['review']
    if reviewed.get('base', {}).get('registry') != str(registry):
        raise WCEError('CONNECTION_RECOVERY_CONFLICT')
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True), ExitStack() as upgrade_locks:
        check_snapshot(reviewed['base'])
        pending = PendingIdentity(reviewed)
        if pending.pins() != record.get('pins') or metadata(record_path) != record:
            raise WCEError('CONNECTION_RECOVERY_CONFLICT')
        held_roots = hold_upgrades(reviewed, upgrade_locks)
        policy, retained, _ = publish(reviewed, pending, held_roots)
        with retained:
            write(record_path, record | {'binding': 'COMMITTED'}, record['parent'])
        return 'COMMITTED_BOUND_IDLE'


def enable_existing(reviewed):
    """Exact TTY re-enable/upgrade, preserving identity and all credential scopes."""
    value = update_existing(reviewed, upgrade_only=False)
    return load_policy(value['connections'][reviewed['reenable']])


def upgrade_existing(reviewed):
    """Metadata-only scope upgrade; never turns a disconnected account back on."""
    value = update_existing(reviewed, upgrade_only=True)
    return {'state': 'UPGRADED', 'connection_ids': sorted(value['connections'])}


def update_existing(reviewed, upgrade_only):
    from .own_replacement_batch import maintenance_gate
    if type(reviewed) is not dict or type(reviewed.get('base')) is not dict or 'registry' not in reviewed['base']:
        raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    with maintenance_gate(Path(reviewed['base']['registry'])):
        return _update_existing_under_replacement_gate(reviewed,upgrade_only)


def _update_existing_under_replacement_gate(reviewed, upgrade_only):
    required = {'base', 'transaction', 'intent'} if upgrade_only else {'base', 'transaction', 'reenable'}
    if (type(reviewed) is not dict or set(reviewed) != required
            or (upgrade_only and reviewed['intent'] != 'UPGRADE_ONLY')):
        raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    registry = Path(reviewed['base']['registry'])
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True):
        check_snapshot(reviewed['base'])
        before = reviewed['base']['registry_value']
        if before is None or (not upgrade_only and reviewed['reenable'] not in before['connections']):
            raise WCEError('CONNECTION_NOT_BOUND')
        value = transaction(reviewed, None)
        if not value['policies']:
            return before
        directory = container(registry.parent, 'connection-transactions')
        value['journal_parent'] = list(path_check(directory, True))
        path = transaction_path(registry, reviewed['transaction'])
        with publication_locks({Path(p).parent for p in value['policies']}, registry), \
                locked(path.with_suffix('.lock'), nonblocking=True):
            check_snapshot(reviewed['base'])
            if reviewed['base']['owner_disk'] is None:
                exclusive(registry.parent / OWNER, reviewed['base']['owner'], reviewed['base']['parent'])
            exclusive(path, value, value['journal_parent'])
            for p, change in value['policies'].items():
                write(p, change['after'], change['pins']['root'])
            write(registry, value['after'], value['registry_parent'])
            write(path, value | {'state': 'COMMITTED'}, value['journal_parent'])
        # An upgrade of an entirely revoked set is valid. Reading it as active
        # would incorrectly report failure after the local commit already succeeded.
        return value['after']
