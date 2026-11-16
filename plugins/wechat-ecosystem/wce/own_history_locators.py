"""Explicit, checkpoint-bound history locators; never live execution rights."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from hashlib import sha256
import re
import sqlite3
import sys
from weakref import WeakSet

from .own_bootstrap_security import decode, private_read
from .own_connection_policy import ConnectionPolicy, load_policy, read_registry, locked
from .own_connection_registry import transaction_path, owner_value, validate_registry
from .own_connection_enrollment import published_entry
from .own_identity_checkpoint import case_identifier
from .own_identity_recovery import validate_relocation_proof, PROOF_FIELDS
from .own_history_source import (HeldFiles, CHECKPOINT_DIRECTORY, checkpoint, connection_source,
                                 owned_connection, safe_path, hold)
from .service import canonical, digest


_ENTERED_SCOPES = WeakSet()
_CONSTRUCTED_SCOPES = WeakSet()


def checked(history, registry):
    if history is None:
        return None
    hold(type(history) is HistoricalLocators and history in _ENTERED_SCOPES
         and not history.closed and history.registry == Path(registry))
    history.source.guard()
    return history


def borrow_entered_history(policy,db):
    """Return this exact open transaction's existing H; never enter or issue H.

    Historical replay has no caller-supplied scope argument. It may borrow the
    unique scope already owned by its real DB lifetime, without opening a new
    file graph or extending any source or authorization lifetime.
    """
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import current_history_policy
    hold(type(policy) is ConnectionPolicy and type(db) is OwnedConnection
         and _transaction_marker(db) is not None and current_history_policy(db) is policy)
    schema=policy.value.get('schema')
    hold(type(schema) is int and schema in (1,2))
    if schema==1:return None
    source=connection_source(db)
    hold(source is not None)
    scopes=[scope for scope in _ENTERED_SCOPES if type(scope) is HistoricalLocators
            and not scope.closed and scope.db is db and scope.policy is policy
            and scope.source is source]
    hold(len(scopes)==1)
    history=scopes[0];checked(history,policy.value['registry_path'])
    with history_scope(policy,db,history) as actual:hold(actual is history)
    source.guard()
    return history


class _Proofs:
    def __init__(self, owner):
        self.owner, self.names = owner, set()

    @property
    def remaining(self):
        return self.owner.files.budget['proof']

    @contextmanager
    def lock(self, path):
        path = safe_path(path)
        hold(path == transaction_path(self.owner.registry, path.stem))
        from .own_authority_history import metadata_proof_aggregate
        metadata_graph = metadata_proof_aggregate(self.owner, reader=self)
        if type(self.owner) is HistoricalLocators:
            # First policy reads happen during __enter__, before registration
            # as entered H. Only the real constructor may select this domain.
            hold(self.owner in _CONSTRUCTED_SCOPES and self.owner.closed is False
                 and self.owner.reader is self and type(self.owner.files) is HeldFiles
                 and type(self.owner.policy) is ConnectionPolicy
                 and connection_source(self.owner.db) is self.owner.source
                 and self.owner.source is not None
                 and self.owner.source.path == self.owner.policy.root / 'state.sqlite3')
        nodes = getattr(self.owner, 'proof_nodes', None)
        if nodes is not None and path not in nodes:
            hold(metadata_graph or len(nodes) < 32)
            nodes.add(path)
        if path not in self.names:
            # Ordinary Owned/H snapshots can join multiple bounded chains.
            # Keep their entire lock graph under HeldFiles' real FD/byte
            # budgets; an aggregate is not one 32-node history chain.
            # Authority and unknown owners retain both original 32-node gates.
            if type(self.owner) is not HistoricalLocators and not metadata_graph:
                hold(len(self.names) < 32)
            self.owner.files.proof_lock(path.with_suffix('.lock'))
            self.names.add(path)
        # HeldFiles keeps the entire legacy FileSource ancestor-chain peak
        # reserved, including reads which happen before this proof lock.
        self.owner.files._capacity()
        self.owner.source.guard()
        yield

    def read(self, path, keep=False, optional=False):
        path = safe_path(path)
        with self.lock(path):
            meta, raw = self.owner.files.read(path, 262144, 'proof')
            return meta, raw if keep else None

    def verify(self):
        # Inner legacy validators reuse held bytes; the whole scope performs
        # its one mandatory full reread before any result can become usable.
        self.owner.files.check_directories()
        for path in self.names:
            self.owner.files.check_file(path)
        self.owner.source.guard()


def _ordinary_history(owner):
    return (type(owner) is HistoricalLocators and owner in _CONSTRUCTED_SCOPES
        and not owner.closed and type(owner.policy) is ConnectionPolicy
        and type(owner.files) is HeldFiles and owner.source is not None
        and connection_source(owner.db) is owner.source
        and owner.source.path==owner.policy.root/'state.sqlite3')


from .own_history_identity import ProofReader as _SequentialProofReader

class _OrdinaryProofs(_SequentialProofReader):
    def __init__(self,owner):
        self.owner=owner
        super().__init__(owner.registry.parent,directories=owner.files,guard=self._guard)

    def _guard(self):
        hold(_ordinary_history(self.owner) and self.owner.reader is self
            and self.directories is self.owner.files)
        self.owner.source.guard()

    def read(self,*args,**kwargs):
        result=super().read(*args,**kwargs)
        self.owner.files.streamed['proof']=self.streamed
        return result


class _CheckpointEvidence:
    """Pure bounded relationships; this base issues no H or execution rights."""
    def _case(self, policy):
        self.member(policy.data)
        cid = policy.data['connection_id']
        if cid in self.cases:
            return self.cases[cid]
        from .own_authority_history import metadata_evidence_graph, check_metadata_relocation_predecessors
        metadata_graph = metadata_evidence_graph(self)
        from .own_revision_history import ordinary_revision_graph
        ordinary_graph = _ordinary_history(self) or ordinary_revision_graph(self)
        expected, visited = policy.value, set()
        current = self._registry_value()
        entry = current['entries'][cid]
        live_pins = {'root': list(policy.root_pin), 'images': list(policy.image_pin),
                     'database': list(policy.database_pin[:2]),
                     'profile_sha256': sha256(private_read(policy.root / 'profile.json')[0]).hexdigest()}
        while True:
            if metadata_graph:
                hold(metadata_evidence_graph(self))
            name = expected['transaction']
            hold(name not in visited and (metadata_graph or ordinary_graph or len(visited) < 32))
            visited.add(name)
            path = transaction_path(self.registry, name)
            _, raw = self.reader.read(path, keep=True)
            from .own_account_metadata import decode_metadata
            proof = decode_metadata(raw)
            hold(type(proof) is dict and proof.get('schema') in (1, 2)
                 and type(proof.get('schema')) is int and proof.get('state') == 'COMMITTED'
                 and proof.get('id') == name and proof.get('registry') == str(self.registry)
                 and proof.get('owner') == self.owner)
            hold(set(proof) == PROOF_FIELDS | ({'relocation'} if proof['schema'] == 2 else set()))
            for data in (proof['before'], proof['after']):
                validate_registry(self.registry, data)
            parent_pin = self.files.directory(self.base)
            journal_pin = self.files.directory(path.parent)
            change = proof['policies'].get(str(policy.path))
            hold(type(change) is dict and set(change) == {'before', 'after', 'pins'}
                 and change['after'] == expected and proof['after']['connections'].get(cid) == str(policy.path)
                 and proof['after']['entries'].get(cid) == entry
                 and entry == published_entry(expected, entry['label'])
                 and type(change['pins']) is dict
                 and change['pins'].get('profile_sha256') == live_pins['profile_sha256'])
            from .own_volume_identity import matches as match_volume
            triples = [
                (self.base, proof['registry_parent'], (parent_pin['dev'], parent_pin['ino'])),
                (path.parent, proof['journal_parent'], (journal_pin['dev'], journal_pin['ino'])),
                (policy.root, change['pins'].get('root'), policy.root_pin),
                (policy.root/'images', change['pins'].get('images'), policy.image_pin),
                (policy.root/'state.sqlite3', change['pins'].get('database'), policy.database_pin[:2]),
            ]
            witnessed = match_volume(self.registry, proof, triples)
            hold(witnessed or all(old == list(current) for _, old, current in triples))
            before = change['before']
            hold(type(before) is dict and before.get('schema') == 2
                 and before.get('identity') == policy.data
                 and type(before.get('revision')) is int
                 and expected['revision'] == before['revision'] + 1
                 and all(before.get(k) == expected[k] for k in
                         ('identity', 'policy', 'capabilities', 'duration', 'registry_path', 'owner_digest'))
                 and expected['enabled'] is True and before.get('enabled') is True
                 and before['transaction'] != name
                 and proof['before']['connections'].get(cid) == str(policy.path)
                 and proof['before']['entries'].get(cid) == published_entry(before, proof['before']['entries'][cid]['label']))
            if proof['schema'] == 2:
                # The relocation validator reads this linear predecessor
                # implicitly. Count it before that read, just like a loop
                # predecessor; the aggregate reader no longer supplies this
                # per-chain boundary as an accidental side effect.
                prior_name = before['transaction']
                hold(prior_name not in visited and (metadata_graph or ordinary_graph or len(visited) < 32))
                from .own_history_identity import check_relocation_predecessors
                if metadata_graph:
                    check_metadata_relocation_predecessors(self, proof, visited)
                else:
                    check_relocation_predecessors(proof, visited)
                visited.add(prior_name)
                validate_relocation_proof(proof, reader=self.reader)
                prior_path = transaction_path(self.registry, prior_name)
                meta, prior_raw = self.reader.read(prior_path, keep=True)
                hold(proof['relocation']['prior_proofs'].get(str(prior_path)) == meta['sha256'])
                prior = decode_metadata(prior_raw)
                hold(prior['schema'] == 1 and prior['state'] == 'COMMITTED'
                     and prior['policies'][str(policy.path)]['after'] == before)
                case = self._checkpoint(proof)
                # The relocation adoption must itself describe this exact full
                # checkpoint, even when this caller only needs a marker pin.
                for key, target in (('root', policy.root), ('images', policy.root / 'images')):
                    adopted = case['directories'].get(str(target))
                    hold(self._observed(target,self.files.directory(target),adopted,proof if witnessed else None))
                adopted_db = case['files'].get(str(policy.root / 'state.sqlite3'))
                adopted_profile = case['files'].get(str(policy.root / 'profile.json'))
                hold(type(adopted_db) is dict and type(adopted_profile) is dict
                     and (witnessed or live_pins['database'] == [adopted_db['dev'], adopted_db['ino']])
                     and live_pins['profile_sha256'] == adopted_profile['sha256'])
                result = {'data': case, 'prior': prior, 'policy': policy}
                if witnessed:
                    result['volume_proof'] = proof
                self._pin(result,
                          prior['policies'][str(policy.path)]['pins']['database'],
                          policy.root / 'state.sqlite3', 'database')
                for old_path, checksum in proof['relocation']['prior_proofs'].items():
                    old_meta, _ = self.reader.read(Path(old_path))
                    pin = case['files'].get(old_path)
                    hold(type(pin) is dict and pin['sha256'] == checksum == old_meta['sha256'])
                self.cases[cid] = result
                return result
            expected = before
            entry = proof['before']['entries'][cid]

    def _checkpoint(self, proof):
        relation = proof['relocation']
        case_id = relation['case_id']
        hold(case_id == case_identifier(self.registry, relation['checkpoint_sha256'])
             and re.fullmatch('[a-f0-9]{64}', case_id) is not None)
        if case_id not in self.checkpoints:
            hold(len(self.checkpoints) < 8)
            path = self.base / CHECKPOINT_DIRECTORY / (case_id + '.json')
            meta, raw = self.files.read(path, 4 * 1024 * 1024, 'checkpoint')
            hold(meta['sha256'] == relation['checkpoint_sha256'])
            data = checkpoint(raw, self.registry)
            hold(digest({'files': data['files'], 'members': data['members']}) == relation['preservation_digest'])
            self.checkpoints[case_id] = (meta['sha256'], relation['preservation_digest'], data)
        checksum, preservation, data = self.checkpoints[case_id]
        hold(checksum == relation['checkpoint_sha256'] and preservation == relation['preservation_digest'])
        return data

    def _witness(self, case, path, value):
        path = safe_path(path)
        hold(path.is_relative_to(self.base))
        maximum = 16384 if path.name in ('replacement-registry.json', 'body5-recovery-anchor.json') else 2 * 1024 * 1024
        if path not in self.records:
            hold(len(self.records) < 64)
        meta, raw = self.files.read(path, maximum, 'record')
        pin = case['data']['files'].get(str(path))
        hold(self._observed(path,meta,pin,case.get('volume_proof')) and raw == (canonical(value) + '\n').encode())
        previous = self.records.get(path)
        if previous is not None:
            hold(previous[1] == raw)
        self.records[path] = (value, raw)
        if not any(saved is value for saved, _ in self.value_refs):
            self.value_ref_bytes += len(raw)
            hold(len(self.value_refs) < 256 and self.value_ref_bytes <= 32 * 1024 * 1024)
            self.value_refs.append((value, raw))

    def _pin(self, case, old, target, direct=None):
        hold(type(old) is list and len(old) == 2 and all(type(v) is int and v >= 0 for v in old))
        target = safe_path(target)
        hold(target.is_relative_to(self.base))
        data, prior, policy = case['data'], case['prior'], case['policy']
        directory = str(target) in data['directories']
        if directory:
            pin = data['directories'][str(target)]
            hold(self._observed(target,self.files.directory(target),pin,case.get('volume_proof')))
        else:
            hold(target == policy.root / 'state.sqlite3')
            pin = data['files'].get(str(target))
            hold(type(pin) is dict)
            current = self.files.file(target, mutable=True)['pin']
            keys = ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink')
            hold(self._observed(target,{k:current[k] for k in keys},{k:pin[k] for k in keys},case.get('volume_proof')))
        hold(old[1] == pin['ino'])
        if direct == 'registry':
            hold(old == prior['registry_parent'])
        elif direct in ('root', 'database'):
            hold(old == prior['policies'][str(policy.path)]['pins'][direct])
        else:
            # This is only an additional old numeric constraint. It is not a
            # claim about historical volume authenticity or a device alias.
            hold(old[0] == prior['registry_parent'][0])

    def _observed(self, path, current, expected, proof):
        if current == expected:
            return True
        if (proof is None or type(expected) is not dict
                or current != expected | {'dev': current['dev']}):
            return False
        from .own_volume_identity import matches as match_volume
        return match_volume(self.registry,proof,[(path,[expected['dev'],expected['ino']],
                                                  (current['dev'],current['ino']))]) is True



class HistoricalLocators(_CheckpointEvidence):
    """Internal explicit scope. Only the factory below can supply its real DB source."""
    def __init__(self, policy, db, source):
        hold(type(policy) is ConnectionPolicy and connection_source(db) is source and source is not None)
        hold(source.path == policy.root / 'state.sqlite3')
        self.policy, self.db, self.source = policy, db, source
        self.registry = safe_path(policy.value['registry_path'])
        self.base = self.registry.parent
        self.owner = owner_value(self.registry, policy.data['actor'])
        self.files, self.stack = HeldFiles(self.base), ExitStack()
        # Ordinary proof history is sequential, not a lifetime update quota.
        # Checkpoint/record formats keep their independent original readers.
        self.reader = _OrdinaryProofs(self)
        self.members = {policy.data['connection_id']: policy}
        self.sources = {policy.data['connection_id']: source}
        self.databases = {policy.data['connection_id']: db}
        self.cases, self.checkpoints, self.records = {}, {}, {}
        self.closed = False
        self.value_refs = []
        self.value_ref_bytes = 0
        _CONSTRUCTED_SCOPES.add(self)

    def __enter__(self):
        try:
            self.source.guard()
            self.files._capacity()
            self.policy.check(readonly=True, proof_reader=self.reader)
            _ENTERED_SCOPES.add(self)
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _registry_value(self):
        return read_registry(self.registry)

    def member(self, identity):
        hold(not self.closed and type(identity) is dict)
        self.files._capacity()
        cid = identity.get('connection_id')
        if cid not in self.members:
            data = read_registry(self.registry)
            hold(cid in data['connections'] and len(self.members) < 8)
            policy = load_policy(data['connections'][cid], active=False)
            hold(policy.data == identity and policy.value['registry_path'] == str(self.registry)
                 and owner_value(self.registry, policy.data['actor']) == self.owner)
            self.members[cid] = policy
        policy = self.members[cid]
        hold(policy.data == identity)
        policy.check(readonly=True, proof_reader=self.reader)
        return policy

    def marker(self, path, value):
        from .own_replacement_batch import MARKER, base
        policy = self.policy
        hold(Path(path) == policy.root / MARKER and value.get('identity') == policy.data
             and value.get('identity_sha') == digest(policy.data) and value.get('registry') == str(self.registry))
        case = self._case(policy)
        self._witness(case, path, value)
        self._pin(case, value['root_identity'], policy.root, 'root')
        self._pin(case, value['registry_parent'], self.base, 'registry')
        self._pin(case, value['base_identity'], base(self.registry))
        return True

    def anchor(self, path, value, *, policy=None):
        from .own_body5_family import ANCHOR, root
        hold(Path(path) == self.base / ANCHOR and value.get('registry') == str(self.registry))
        case = self._case(policy or self.policy)
        self._witness(case, path, value)
        self._pin(case, value['registry_parent'], self.base, 'registry')
        self._pin(case, value['root_identity'], root(self.registry))
        return True

    def receipt(self, path, value):
        # Retained-receipt physical relocation is outside this delivery.
        # The caller invokes this only after its original direct-pin check fails.
        hold(False)

    def approval_manifest(self, path, value):
        # Shared-approval physical relocation has no accepted full positive yet.
        hold(False)

    def case_identity(self, entry):
        from .own_replacement_unrelated_v3 import _identity
        identity = _identity(entry['original']['binding'], entry['root'])
        hold(digest(identity) == entry['identity_sha']
             and identity['connection_id'] == entry['connection_id'])
        return identity

    def approval_case(self, path, value, index):
        # Current physical pins still use the caller's complete original checks.
        hold(False)

    def peer_db(self, identity, current_db):
        hold(current_db is self.db)
        policy = self.member(identity)
        cid = identity['connection_id']
        if cid not in self.databases:
            db = self.stack.enter_context(owned_connection(policy.root / 'state.sqlite3', readonly=True, timeout=0))
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            source = connection_source(db)
            hold(source is not None)
            self.databases[cid], self.sources[cid] = db, source
        self.sources[cid].guard()
        return self.databases[cid]

    def finish(self):
        hold(not self.closed)
        for policy in self.members.values():
            self.files._capacity()
            policy.check(readonly=True, proof_reader=self.reader)
        for source in self.sources.values():
            source.guard()
        for value, raw in self.value_refs:
            hold(raw == (canonical(value) + '\n').encode())
        self.reader.verify()
        self.files.verify('proof')
        self.files.verify('checkpoint')
        self.files.verify('record')
        for policy in self.members.values():
            self.files._capacity()
            policy.check(readonly=True, proof_reader=self.reader)
        for source in self.sources.values():
            source.guard()

    def __exit__(self, kind, value, traceback):
        original = value
        try:
            if kind is None:
                self.finish()
        except BaseException as error:
            original = error
            raise
        finally:
            self.closed = True
            _ENTERED_SCOPES.discard(self)
            _CONSTRUCTED_SCOPES.discard(self)
            cleanup_error = None
            try:
                self.files.close()
            except BaseException as error:
                cleanup_error = error
            try:
                self.stack.close()
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
            if original is None and cleanup_error is not None:
                raise cleanup_error


@contextmanager
def history_scope(policy, db, existing=None):
    if existing is not None:
        hold(type(existing) is HistoricalLocators and existing in _ENTERED_SCOPES and not existing.closed
             and existing.db is db and existing.policy is policy)
        yield existing
        return
    if policy is None or type(policy) is not ConnectionPolicy:
        # No bridge is issued for fixture/foreign policy objects. Their original
        # strict validation still applies; they can never obtain an allowance.
        yield None
        return
    schema = policy.value.get('schema')
    hold(type(schema) is int and schema in (1, 2))
    if schema == 1:
        # Legacy single-account delegation has no registry member or relocation
        # chain. Preserve its old strict validators; it gets no bridge.
        yield None
        return
    source = connection_source(db)
    # A real policy requires a source issued at the actual SQLite open point.
    # Ambiguous or caller-opened connections cannot silently lose this fence.
    hold(source is not None)
    with HistoricalLocators(policy, db, source) as scope:
        yield scope
