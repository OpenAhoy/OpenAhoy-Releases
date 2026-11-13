"""Trusted-host checkpoint acquisition. No model route, credentials or network.

A digest is a byte binding, not its own authority. The caller must be the
reviewed operator whose immutable reservation was independently pinned.
"""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat

from .contracts import WCEError
from .own_bootstrap_security import decode, path_check
from .own_connection_registry import transaction_path
from .service import canonical, digest

HEX = re.compile(r'[a-f0-9]{64}')
PROOF = re.compile(r'(?:reconciliation|draft-scan|draft-readback|draft-reconciliation|connection-revoked)-[A-Za-z0-9_-]+\.json')
GRANT = re.compile(r'cover-read-(?:grant|claimed)-cover-read-[a-f0-9]{32}\.json')
SECURITY_PREFIXES = ('reconciliation-', 'draft-scan-', 'draft-readback-',
                     'draft-reconciliation-', 'connection-revoked-', 'cover-read-')
SIDE_LOCKS = ('connection-import.lock', 'connection-token.lock',
              'cover-read-authority.lock', 'presentation.lock')
ROOT_LOCKS = ('connection-start.lock', 'connection.lock', 'connection-policy.lock', *SIDE_LOCKS)
RUNTIMES = {'connection-runtime.json', 'connection.sock', 'runtime.json', 'operator.sock',
            'state.sqlite3-wal', 'state.sqlite3-shm', 'state.sqlite3-journal'}
LEGACY = re.compile(r'(?:[a-z0-9-]+-before-(?:profile\.json|review\.json|state\.sqlite3|启动公众号安全终端\.command|proof-reconciliation[-A-Za-z0-9_]+\.json|seal-[a-f0-9]{64}\.json)|state-before-schema5-[a-f0-9]{64}\.sqlite3|(?:qualification|quota|egress|material\.add_material|media\.uploadimg|draft\.add|draft\.get)\.statement\.txt|review\.json|启动公众号安全终端\.command|本人接入操作卡\.txt|run-outcome-[0-9]{1,10}-[a-f0-9]{32}\.json)')


def require(condition, code='SOURCE_UNVERIFIED'):
    if not condition:
        raise WCEError('CONNECTION_RELOCATION_' + code)


def file_metadata(info):
    return {'dev': info.st_dev, 'ino': info.st_ino, 'mode': stat.S_IMODE(info.st_mode),
            'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
            'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


class Reader:
    """FD-relative nonsymlink traversal; private ownership plus bounded hashing."""
    def __init__(self, private_root=None):
        self.private_root = Path(private_root) if private_root else None
        self.remaining = 256 * 1024 * 1024

    @contextmanager
    def directory(self, path):
        path = Path(path)
        require(path.is_absolute() and '..' not in path.parts and len(path.parts) <= 32, 'UNSAFE_PATH')
        descriptors, chain = [], []
        try:
            try:
                fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                descriptors.append(fd)
                current = Path('/')
                for part in path.parts[1:]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    descriptors.append(child); chain.append((fd, part, child)); fd = child; current /= part
                    info = os.fstat(fd)
                    if self.private_root and current.is_relative_to(self.private_root):
                        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'UNSAFE_PATH')
            except OSError:
                raise WCEError('CONNECTION_RELOCATION_UNSAFE_PATH') from None
            # Exceptions from the protected operation must retain their original kind.
            yield fd
            try:
                for parent, name, child in chain:
                    entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    require(stat.S_ISDIR(entry.st_mode) and (entry.st_dev, entry.st_ino) ==
                            (os.fstat(child).st_dev, os.fstat(child).st_ino), 'PATH_CHANGED')
            except OSError:
                raise WCEError('CONNECTION_RELOCATION_PATH_CHANGED') from None
        finally:
            for fd in reversed(descriptors): os.close(fd)

    def names(self, path, optional=False):
        if optional and not os.path.lexists(path): return None
        with self.directory(path) as parent:
            names = sorted(os.listdir(parent))
            require(len(names) <= 1024, 'LIMIT')
            return names

    def read(self, path, keep=False, optional=False):
        path = Path(path)
        with self.directory(path.parent) as parent:
            try: fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            except FileNotFoundError:
                require(optional, 'SOURCE_MISSING'); return None, None
            except OSError:
                raise WCEError('CONNECTION_RELOCATION_UNSAFE_PATH') from None
            try:
                info = os.fstat(fd); before = file_metadata(info)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid(), 'UNSAFE_PATH')
                if self.private_root and path.is_relative_to(self.private_root): require(before['mode'] == 0o600, 'UNSAFE_PATH')
                require(info.st_size <= min(self.remaining, 32 * 1024 * 1024), 'LIMIT')
                hasher, chunks, length = sha256(), [], 0
                while True:
                    block = os.read(fd, 65536)
                    if not block: break
                    length += len(block); self.remaining -= len(block)
                    require(length <= 32 * 1024 * 1024 and self.remaining >= 0, 'LIMIT')
                    hasher.update(block)
                    if keep: chunks.append(block)
                require(length == before['bytes'] and file_metadata(os.fstat(fd)) == before and
                        file_metadata(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == before, 'PATH_CHANGED')
                return before | {'sha256': hasher.hexdigest()}, b''.join(chunks) if keep else None
            finally: os.close(fd)


def case_identifier(registry, checkpoint_sha256):
    return digest({'domain': 'WCE_IDREC_CHECKPOINT_V1', 'registry': str(registry),
                   'checkpoint_sha256': checkpoint_sha256})


class TrustedCase:
    """Only a reviewed host supplies the reservation path and pinned digest.

    There is deliberately no reserve/reset/create/default provider API. A
    missing ledger is an error, never an invitation to start a new case.
    """
    def __init__(self, reservation_path, expected_digest):
        require(type(expected_digest) is str and HEX.fullmatch(expected_digest) is not None)
        self.reservation_path = Path(reservation_path)
        self.expected_digest = expected_digest
        reader = Reader()
        meta, raw = reader.read(self.reservation_path, keep=True)
        require(meta['mode'] == 0o600 and meta['sha256'] == expected_digest)
        self.value = decode(raw, 262144)
        require(type(self.value) is dict and set(self.value) == {
            'schema', 'domain', 'checkpoint_path', 'checkpoint_sha256', 'registry', 'targets',
            'ignored_root_names', 'case_id', 'case_root_pin', 'transaction', 'candidate_scope', 'source_chain'})
        value = self.value
        require(type(value['schema']) is int and value['schema'] == 1 and value['domain'] == 'WCE_IDREC_CHECKPOINT_V1')
        for field in ('checkpoint_sha256', 'candidate_scope', 'case_id'):
            require(type(value[field]) is str and HEX.fullmatch(value[field]) is not None)
        self.registry = Path(value['registry']); self.base = self.registry.parent
        require(self.registry.name == 'connections.json' and self.registry.is_absolute() and '..' not in self.registry.parts)
        require(value['case_id'] == case_identifier(self.registry, value['checkpoint_sha256']))
        self.root = self.reservation_path.parent
        require(self.reservation_path.name == 'reservation.json' and self.root.name == value['case_id'] and not self.root.is_relative_to(self.base))
        require(list(path_check(self.root, True)) == value['case_root_pin'])
        require(path_check(self.root, True)[0] == path_check(self.base, True)[0], 'DIFFERENT_FILESYSTEM')
        require(type(value['targets']) is list and 1 <= len(value['targets']) <= 8 and
                len(value['targets']) == len(set(value['targets'])) and all(type(x) is str for x in value['targets']))
        transaction_path(self.registry, value['transaction'])
        require(type(value['source_chain']) is list and 1 <= len(value['source_chain']) <= 4)
        for source in value['source_chain']:
            require(type(source) is dict and set(source) == {'path', 'sha256'})
            source_meta, _ = reader.read(Path(source['path']))
            require(source_meta['sha256'] == source['sha256'])
        checkpoint = Path(value['checkpoint_path'])
        require(not checkpoint.is_relative_to(self.base))
        checkpoint_meta, checkpoint_raw = reader.read(checkpoint, keep=True)
        require(checkpoint_meta['sha256'] == value['checkpoint_sha256'])
        baseline = decode(checkpoint_raw, 262144)
        require(type(baseline) is dict and type(baseline.get('accounts')) is dict)
        self.snapshot = baseline['accounts']
        require(set(self.snapshot) == {'files', 'members', 'directories', 'keychain_access', 'business_write'})
        require(self.snapshot['keychain_access'] is False and self.snapshot['business_write'] is False)
        require(len(self.snapshot['files']) <= 256 and len(self.snapshot['members']) <= 64)
        self.files = {Path(name): pin for name, pin in self.snapshot['files'].items()}
        for path in (*self.files, *(Path(p) for p in self.snapshot['members'])):
            require(path.is_relative_to(self.base) and '..' not in path.parts)
        registry_pin = self.files.get(self.registry)
        require(type(registry_pin) is dict and HEX.fullmatch(registry_pin.get('sha256', '')) is not None)
        self.reservation_meta = meta
        self.ledger_path = self.root / 'ledger.json'
        self.ledger()  # Must already exist, including on the first proposal.

    def check(self):
        meta, _ = Reader().read(self.reservation_path)
        require(meta == self.reservation_meta and meta['sha256'] == self.expected_digest, 'SOURCE_CHANGED')
        require(list(path_check(self.root, True)) == self.value['case_root_pin'], 'SOURCE_CHANGED')
        for source in [*self.value['source_chain'], {'path': self.value['checkpoint_path'], 'sha256': self.value['checkpoint_sha256']}]:
            meta, _ = Reader().read(Path(source['path']))
            require(meta['sha256'] == source['sha256'], 'SOURCE_CHANGED')

    def ledger(self):
        meta, raw = Reader(self.root).read(self.ledger_path, keep=True)
        require(meta['mode'] == 0o600 and meta['bytes'] <= 512 * 1024, 'CASE_INVALID')
        value = decode(raw, 512 * 1024)
        require(type(value) is dict and value.get('case_id') == self.value['case_id'] and
                value.get('reservation_sha256') == self.expected_digest and value.get('state') in
                {'RESERVED', 'CLAIMED', 'COMMITTED', 'SPENT_ABORTED'}, 'CASE_INVALID')
        if value['state'] == 'RESERVED':
            require(set(value) == {'schema', 'state', 'case_id', 'reservation_sha256'} and type(value['schema']) is int and value['schema'] == 1, 'CASE_INVALID')
        else:
            require(set(value) == {'schema', 'state', 'case_id', 'reservation_sha256', 'proof', 'raw_before'} and
                    type(value['schema']) is int and value['schema'] == 1, 'CASE_INVALID')
            from .own_identity_recovery import validate_case_record
            validate_case_record(self, value)
        return value


@contextmanager
def existing_lock(path, held, shared=False):
    """Never create a missing lock. Keep its exact descriptor through the phase."""
    path = Path(path); reader = Reader()
    with reader.directory(path.parent) as parent:
        try: fd = os.open(path.name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            raise WCEError('CONNECTION_RELOCATION_LOCK_REQUIRED') from None
        except OSError:
            raise WCEError('CONNECTION_RELOCATION_LOCK_INVALID') from None
        try:
            info = os.fstat(fd); pin = file_metadata(info)
            require(stat.S_ISREG(info.st_mode) and pin['uid'] == os.getuid() and pin['nlink'] == 1 and pin['mode'] == 0o600 and pin['bytes'] == 0, 'LOCK_INVALID')
            try: fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            except BlockingIOError: raise WCEError('CONNECTION_BUSY') from None
            held.append((path, fd, pin))
            yield fd
        finally: os.close(fd)


def check_locks(held):
    for path, fd, pin in held:
        require(file_metadata(os.fstat(fd)) == pin and Reader().read(path)[0] ==
                pin | {'sha256': sha256(b'').hexdigest()}, 'LOCK_CHANGED')


@contextmanager
def checkpoint_locks(case, policies):
    """Same shared order as publication; added independent writers are excluded."""
    held = []
    with ExitStack() as stack:
        paths = [case.root / 'case.lock', case.base / 'connection-setup.lock']
        roots = sorted({Path(p).parent for p in policies}, key=str)
        for root in roots: paths += [root / 'connection-start.lock', root / 'connection.lock']
        for root in roots: paths += [root / name for name in SIDE_LOCKS]
        if case.files.get(case.base / 'connection-check-budget.json') is not None:
            paths.append(case.base / 'connection-check-budget.lock')
        paths += [root / 'connection-policy.lock' for root in roots]
        paths.append(case.base / 'connections.lock')
        for path in paths: stack.enter_context(existing_lock(path, held))
        # The old proof locks are added by the caller after reading pinned policies.
        def old_proofs(names):
            for path in sorted(set(names), key=str): stack.enter_context(existing_lock(path.with_suffix('.lock'), held, True))
        check_locks(held)
        yield held, old_proofs
        check_locks(held)


def verify_snapshot(case, substitutions=None, additions=None):
    """Exact known bytes/members, with only this transaction's finite projection."""
    case.check()
    substitutions, additions = substitutions or {}, additions or {}
    reader = Reader(case.base)
    observed, observed_names, observed_directories = {}, {}, {}
    for path, expected in case.files.items():
        actual, _ = reader.read(path, optional=expected is None)
        if path in substitutions:
            require(actual is not None and actual['mode'] == 0o600 and
                    actual['sha256'] in substitutions[path], 'STATE_CHANGED')
        else: require(actual == expected, 'STATE_CHANGED')
        observed[str(path)] = actual
    members = case.snapshot['members']
    roots = sorted({path.parent for path in case.files if path.name == 'connection-policy.json'}, key=str)
    require(len(roots) == len(case.value['targets']), 'SOURCE_UNVERIFIED')
    ignored = case.value['ignored_root_names']
    require(type(ignored) is dict and set(ignored) == {str(p) for p in roots})
    for root in roots:
        require(type(ignored[str(root)]) is list and all(type(n) is str and LEGACY.fullmatch(n) for n in ignored[str(root)]))
        names = reader.names(root)
        observed_names[root] = names
        require(not set(names) & RUNTIMES, 'BUSY')
        expected_safe = set(members.get(str(root), []))
        actual_safe = {n for n in names if PROOF.fullmatch(n) or GRANT.fullmatch(n)}
        require(actual_safe == expected_safe, 'STATE_CHANGED')
        for name in names:
            if name.startswith(SECURITY_PREFIXES) and name not in ROOT_LOCKS:
                require(name in actual_safe, 'SOURCE_UNVERIFIED')
        allowed = {p.name for p in case.files if p.parent == root} | set(ROOT_LOCKS) | {'images'}
        allowed |= {Path(p).name for p in members if Path(p).parent == root and members[p] is not None}
        allowed |= set(ignored[str(root)])
        require(set(names) <= allowed, 'SOURCE_UNVERIFIED')
    for name, expected in members.items():
        path = Path(name)
        if path in roots: continue
        actual = reader.names(path, optional=expected is None)
        observed_names[path] = actual
        allowed_additions = set(additions.get(path, {}))
        require(actual is None if expected is None else set(actual or []) == set(expected) | allowed_additions, 'STATE_CHANGED')
        if actual is not None:
            pattern = (r'(?:import-[a-f0-9]{64}|cover|body)\.(?:png|jpg)' if path.name == 'images' else
                       r'txn-[a-f0-9]{32}\.(?:json|lock)' if path.name == 'connection-transactions' else
                       r'wx[a-f0-9]{16}\.json' if path.name == 'connection-enrollments' else
                       r'txn-[a-f0-9]{32}\.json' if path.name == 'connection-checks' else r'[a-f0-9]{64}\.json')
            require(all(re.fullmatch(pattern, n) for n in actual), 'SOURCE_UNVERIFIED')
        for member, hashes in additions.get(path, {}).items():
            meta, _ = reader.read(path / member)
            require(meta['sha256'] in hashes and meta['mode'] == 0o600, 'STATE_CHANGED')
    # Pin every private directory recorded in the trusted checkpoint.
    for name, expected in case.snapshot['directories'].items():
        path = Path(name)
        if not path.is_relative_to(case.base): continue
        with reader.directory(path) as fd:
            meta = file_metadata(os.fstat(fd))
            observed_directories[path] = {k: meta[k] for k in ('dev', 'ino', 'mode', 'uid', 'gid')}
            require(observed_directories[path] == expected, 'PATH_CHANGED')
            # Intermediate containers (for example accounts/ and own/) are also
            # closed sets; an unregistered child must not hide security state.
            if path != case.base and path not in roots and str(path) not in members:
                known = {p.name for p in case.files if p.parent == path}
                known |= {Path(p).name for p in case.snapshot['directories'] if Path(p).parent == path}
                observed_names[path] = reader.names(path)
                require(set(observed_names[path]) == known, 'SOURCE_UNVERIFIED')
    top = {case.registry.name, 'connection-owner.json', 'connection-setup.lock', 'connections.lock'}
    for path in (*case.files, *(Path(p) for p in members), *roots):
        if path != case.base: top.add(path.relative_to(case.base).parts[0])
    if case.files.get(case.base / 'connection-check-budget.json') is not None: top.add('connection-check-budget.lock')
    observed_names[case.base] = reader.names(case.base)
    require(set(observed_names[case.base]) == top, 'SOURCE_UNVERIFIED')
    # Second pass prevents drift during the first full scan; no values are emitted.
    for name, meta in observed.items(): require(reader.read(Path(name), optional=meta is None)[0] == meta, 'STATE_CHANGED')
    for path, names in observed_names.items():
        require(reader.names(path, optional=names is None) == names, 'STATE_CHANGED')
    for path, expected in observed_directories.items():
        with reader.directory(path) as fd:
            meta = file_metadata(os.fstat(fd))
            require({k: meta[k] for k in expected} == expected, 'PATH_CHANGED')
    return digest({'files': observed, 'members': members})
