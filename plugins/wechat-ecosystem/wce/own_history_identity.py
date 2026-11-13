"""Bounded historical physical identity proof; never a live grant provider."""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import os
import stat
from pathlib import Path

from .contracts import WCEError
from .own_bootstrap_security import decode, path_check, private_read
from .own_connection_policy import ConnectionPolicy, locked
from .own_connection_registry import transaction_path, validate_registry
from .own_identity_checkpoint import Reader
from .own_identity_recovery import PROOF_FIELDS, validate_relocation_proof
from .own_connection_enrollment import published_entry


class ProofReader(Reader):
    """Sequential complete proof reads, with exact two-pass identity snapshots.

    Retain small physical metadata+SHA, not an FD/lock/raw copy per update. The
    account metadata extent is checked exactly; history has no total quota.
    """
    def __init__(self, root, locks=None, *, directories=None, guard=lambda:None):
        super().__init__(root)
        self.registry=Path(root)/'connections.json'
        self.locks=locks;self.directories=directories;self.guard=guard
        self.locked_paths=self.names=set();self.lock_pins={};self.observed={}
        self.streamed=0;self.peak_fds=0

    def _capacity(self, additional=0):
        from .own_fd_domain import fd_capacity_allowed
        from .own_history_source import TRANSIENT_FDS
        count=len(os.listdir('/dev/fd'));self.peak_fds=max(self.peak_fds,count)
        require(fd_capacity_allowed(count,additional,TRANSIENT_FDS))
        if self.directories is not None:
            self.directories._capacity(additional)

    @contextmanager
    def lock(self,path):
        path=Path(path)
        require(path==transaction_path(self.registry,path.stem))
        self.guard()
        if self.directories is not None:self.directories.parent(path.parent)
        self._capacity(2)
        lock=path.with_suffix('.lock')
        with locked(lock,nonblocking=True,shared=True,existing=True,readonly=True) as fd:
            from .own_identity_checkpoint import file_metadata
            pin=file_metadata(os.fstat(fd))
            if lock in self.lock_pins:require(self.lock_pins[lock]==pin)
            else:self.lock_pins[lock]=pin
            self.names.add(path);self._capacity();self.guard()
            yield
            require(file_metadata(os.fstat(fd))==pin)
            if self.directories is not None:self.directories.check_directories()
            self.guard()

    def _held_read(self,path):
        from .own_account_metadata import read_at
        parent=self.directories.parent(path.parent)
        self._capacity(1)
        result=read_at(parent,path.name,self.guard)
        self.directories.check_directories();self._capacity();self.guard()
        return result

    def read(self,path,keep=False,optional=False):
        path=Path(path)
        with self.lock(path):
            if self.directories is None:
                from .own_account_metadata import read_at
                with self.directory(path.parent) as parent:
                    meta,raw=read_at(parent,path.name,self.guard)
            else:meta,raw=self._held_read(path)
            self.streamed+=len(raw)
            if path in self.observed:require(self.observed[path]==meta)
            else:self.observed[path]=meta
            self.guard()
            return meta,raw if keep else None

    def verify(self):
        from .own_identity_checkpoint import file_metadata
        for path in sorted(self.names):self.read(path)
        # Detect an already-reread proof changed while a later file was being
        # verified. This metadata sweep retains no per-update file descriptor.
        for path in sorted(self.observed):
            with self.lock(path):
                if self.directories is not None:
                    parent=self.directories.parent(path.parent)
                    pin=file_metadata(os.stat(path.name,dir_fd=parent,follow_symlinks=False))
                else:
                    with self.directory(path.parent) as parent:
                        pin=file_metadata(os.stat(path.name,dir_fd=parent,follow_symlinks=False))
                require(pin=={k:v for k,v in self.observed[path].items() if k!='sha256'})
        if self.directories is not None:self.directories.check_directories()
        self._capacity();self.guard()


def require(value):
    if not value:
        raise WCEError('OWN_STATE_CORRUPT')


def check_relocation_predecessors(proof, visited):
    """Each peer is a separate next branch, not an aggregate chain step.

    The original relocation validator reads these files implicitly. Check
    the shared linear prefix before any of those reads; its complete shape,
    hashes and peer relationships remain the original validator's job.
    """
    require(type(visited) is set)
    _check_relocation_predecessor_stems(proof, visited)


def _check_relocation_predecessor_stems(proof, visited):
    require(type(visited) is set)
    for name in proof['relocation']['prior_proofs']:
        require(Path(name).stem not in visited)


@contextmanager
def historical_identity(w, profile, grant):
    root, database = w.db.path.parent, w.db.path
    if (grant['root_pin'] == list(path_check(root, True))
            and grant['database_pin'] == list(path_check(database)[:2])):
        yield
        return
    policy = getattr(w, 'policy', None)
    require(type(policy) is ConnectionPolicy)
    require(policy.root == root and database == root / 'state.sqlite3')
    identity = policy.data
    binding = {'tenant': identity['actor']['tenant_id'], 'principal': identity['actor']['principal_id'],
        'client': identity['actor']['client_id'], 'session': identity['actor']['session_id'],
        'connection': identity['connection_id'], 'account': identity['appid'],
        'resource': identity['resource_id'], 'generation': identity['generation'],
        'epoch': identity['epoch'], 'source_kind': profile.source_kind}
    require(grant['binding'] == profile.binding() == binding and policy.value['schema'] == 2)
    registry = Path(policy.value['registry_path'])
    visited = set()
    expected_entry = None
    expected = policy.value
    cid, policy_path = identity['connection_id'], str(policy.path)
    live_pins = {'root': list(policy.root_pin), 'images': list(policy.image_pin),
        'database': list(policy.database_pin[:2]),
        'profile_sha256': sha256(private_read(root / 'profile.json')[0]).hexdigest()}
    with ExitStack() as locks:
        scope = getattr(w, 'history_locators', None)
        if scope is not None:
            from .own_history_locators import HistoricalLocators
            require(type(scope) is HistoricalLocators and not scope.closed and scope.policy is policy)
            reader = scope.reader
        else:
            reader = ProofReader(registry.parent, locks)
        # Normal member validation remains authoritative and uses no-create locks
        # and the same per-file proof format bound even for its implicit relocation reads.
        policy.check(readonly=True, proof_reader=reader)
        while True:
            name = expected['transaction']
            require(name not in visited)
            visited.add(name)
            path = transaction_path(registry, name)
            _, raw = reader.read(path, keep=True)
            from .own_account_metadata import decode_metadata
            proof = decode_metadata(raw)
            require(type(proof) is dict and type(proof.get('schema')) is int
                and proof['schema'] in (1, 2) and proof.get('id') == name
                and proof.get('state') == 'COMMITTED' and proof.get('registry') == str(registry)
                and proof.get('registry_parent') == list(path_check(registry.parent, True))
                and proof.get('journal_parent') == list(path_check(path.parent, True))
                and proof.get('owner') == head_owner(policy))
            require(set(proof) == (PROOF_FIELDS | ({'relocation'} if proof['schema'] == 2 else set())))
            for registry_value in (proof['before'], proof['after']):
                require(type(registry_value) is dict and type(registry_value.get('schema')) is int
                    and registry_value['schema'] == 2)
                validate_registry(registry, registry_value)
            change = proof['policies'].get(policy_path)
            require(type(change) is dict and set(change) == {'before', 'after', 'pins'}
                and change['after'] == expected
                and (expected_entry is None or proof['after']['entries'].get(cid) == expected_entry)
                and proof['after']['connections'].get(cid) == policy_path
                and proof['after']['entries'].get(cid) == published_entry(expected, proof['after']['entries'][cid]['label'])
                and all(change['pins'].get(k) == v for k, v in live_pins.items()))
            if proof['schema'] == 2:
                check_relocation_predecessors(proof, visited)
                # Every predecessor is independently locked, fully read and
                # fingerprinted by reader; the complete final reread still
                # precedes returning usable history to the caller.
                for parent_name in sorted(proof['relocation']['prior_proofs']):
                    require(Path(parent_name).parent==path.parent)
                validate_relocation_proof(proof, reader=reader)
                parent_path = transaction_path(registry, change['before']['transaction'])
                require(str(parent_path) in proof['relocation']['prior_proofs']
                    and parent_path.stem not in visited)
                visited.add(parent_path.stem)
                meta, raw = reader.read(parent_path, keep=True)
                require(meta['sha256'] == proof['relocation']['prior_proofs'][str(parent_path)])
                parent = decode_metadata(raw)
                old = parent['policies'][policy_path]
                require(parent['schema'] == 1 and parent['state'] == 'COMMITTED'
                    and old['after'] == change['before']
                    and old['after']['identity'] == identity
                    and grant['root_pin'] == old['pins']['root']
                    and grant['database_pin'] == old['pins']['database'])
                # Retain every original fingerprint throughout target, claimed-record
                # and PNG verification; complete revalidation follows yield.
                yield
                policy.check(readonly=True, proof_reader=reader)
                reader.verify()
                policy.check(readonly=True, proof_reader=reader)
                return
            before = change['before']
            require(type(before) is dict and before.get('schema') == 2
                and type(before.get('revision')) is int and expected['revision'] == before['revision'] + 1
                and before['transaction'] != name
                and all(before.get(k) == expected[k] for k in
                    ('identity', 'policy', 'capabilities', 'duration', 'registry_path', 'owner_digest'))
                and proof['before']['connections'].get(cid) == policy_path
                and proof['before']['entries'].get(cid) == published_entry(before, proof['before']['entries'][cid]['label']))
            expected_entry = proof['before']['entries'][cid]
            expected = before


def head_owner(policy):
    from .own_connection_registry import owner_value
    return owner_value(Path(policy.value['registry_path']), policy.data['actor'])


def historical_pins_match(w, profile, grant):
    """Pure predicate convenience for offline checks; runtime holds the context."""
    with historical_identity(w, profile, grant):
        return True
