"""Checkpoint-bound revision journal reads; never journal writes or an H grant."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os
import sys
from weakref import WeakSet

from .own_connection_policy import ConnectionPolicy, read_registry
from .own_connection_registry import owner_value
from .own_history_locators import _CheckpointEvidence
from .own_history_source import HeldFiles, connection_source, hold, safe_path
from .own_history_identity import ProofReader
from .service import canonical, digest

_ENTERED = WeakSet()
_CONSTRUCTED = WeakSet()


def ordinary_revision_graph(frame):
    """Recognize only a real read-only revision DB lifetime, never issue H.

    Construction must precede policy proof reads during __enter__. The source
    witness comes from the actual owned SQLite open point, not a caller flag.
    """
    return (type(frame) is _RevisionReadFrame and frame in _CONSTRUCTED
        and not frame.closed and type(frame.policy) is ConnectionPolicy
        and type(frame.files) is _RevisionFiles and frame.source is not None
        and type(frame.reader) is _RevisionProofs and frame.reader.owner is frame
        and frame.reader.directories is frame.files
        and frame.registry == safe_path(frame.policy.value['registry_path'])
        and frame.base == frame.registry.parent and frame.files.base == frame.base
        and connection_source(frame.db) is frame.source
        and frame.source.readonly is True and frame.source.revision_header is True
        and frame.source.path == frame.policy.root / 'draft-revisions/revision.sqlite3')


class _RevisionProofs(ProofReader):
    """Stream complete upgrade proofs without a quota on account history."""
    def __init__(self, owner):
        self.owner = owner
        super().__init__(owner.registry.parent, directories=owner.files, guard=self._guard)

    def _guard(self):
        hold(ordinary_revision_graph(self.owner) and self.owner.reader is self
             and self.directories is self.owner.files)
        self.owner.source.guard()

    def read(self, *args, **kwargs):
        result = super().read(*args, **kwargs)
        self.owner.files.streamed['proof'] = self.streamed
        return result


class _RevisionFiles(HeldFiles):
    def read(self, path, maximum, category, *, force=False):
        path=safe_path(path)
        item=self.file(path)
        size=item['pin']['bytes']
        hold(0<size<=maximum and category in self.budget and item['category'] in (None,category))
        if item['raw'] is not None and not force:
            return item['pin']|{'sha256':sha256(item['raw']).hexdigest()},item['raw']
        hold(size<=self.budget[category])
        os.lseek(item['fd'],0,os.SEEK_SET)
        parts,count=[],0
        while count<size:
            block=os.read(item['fd'],min(65536,size-count))
            hold(bool(block));count+=len(block)
            self.budget[category]-=len(block);self.streamed[category]+=len(block)
            parts.append(block)
        self.check_file(path)
        raw=b''.join(parts)
        hold(count==size and (item['raw'] is None or item['raw']==raw))
        item['raw'],item['category']=raw,category
        return item['pin']|{'sha256':sha256(raw).hexdigest()},raw


def checked(frame, account, db):
    hold(type(frame) is _RevisionReadFrame and frame in _ENTERED and not frame.closed
         and frame.policy.root == Path(account) and frame.db is db
         and connection_source(db) is frame.source and frame.source.readonly is True and frame.source.revision_header is True)
    frame.source.guard()
    return frame


class _RevisionReadFrame(_CheckpointEvidence):
    def __init__(self, policy, db):
        source = connection_source(db)
        hold(type(policy) is ConnectionPolicy and source is not None
             and source.readonly is True and source.revision_header is True
             and source.path == policy.root / 'draft-revisions/revision.sqlite3')
        self.policy, self.db, self.source = policy, db, source
        self.registry = safe_path(policy.value['registry_path'])
        self.base = self.registry.parent
        self.owner = owner_value(self.registry, policy.data['actor'])
        self.files = _RevisionFiles(self.base)
        self.reader = _RevisionProofs(self)
        self.cases, self.checkpoints, self.records = {}, {}, {}
        self.value_refs, self.value_ref_bytes = [], 0
        self.closed = False
        self.journal = None
        self.journal_remaining = 256 * 1024 * 1024
        _CONSTRUCTED.add(self)

    def __enter__(self):
        try:
            hold(ordinary_revision_graph(self) and self not in _ENTERED)
            self.source.guard()
            self.policy.check(readonly=True, proof_reader=self.reader)
            _ENTERED.add(self)
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _registry_value(self):
        return read_registry(self.registry)

    def member(self, identity):
        hold(not self.closed and identity == self.policy.data)
        self.files._capacity()
        self.policy.check(readonly=True, proof_reader=self.reader)
        return self.policy

    def _journal_hash(self, path, expected):
        item = self.files.file(path)
        pin = item['pin']
        hold(pin == {k:v for k,v in expected.items() if k != 'sha256'}
             and 0 < pin['bytes'] <= 128 * 1024 * 1024
             and pin['bytes'] <= self.journal_remaining
             and self.source.identity == (pin['dev'], pin['ino']))
        self.source.guard()
        os.lseek(item['fd'], 0, os.SEEK_SET)
        count, checksum = 0, sha256()
        while count < pin['bytes']:
            block = os.read(item['fd'], min(65536, pin['bytes'] - count))
            hold(bool(block))
            count += len(block)
            self.journal_remaining -= len(block)
            checksum.update(block)
        self.files.check_file(path)
        self.source.guard()
        hold(count == pin['bytes'] and checksum.hexdigest() == expected['sha256'])

    def anchor(self, account, db, value, binding):
        checked(self, account, db)
        from .draft_revision_guard import identity_binding
        hold(binding == digest(identity_binding(self.policy.data, 'OPERATOR_ATTESTED')))
        case = self._case(self.policy)
        path = self.policy.root / 'draft-revision-safety-anchor.json'
        directory = self.policy.root / 'draft-revisions'
        database = directory / 'revision.sqlite3'
        self._witness(case, path, value)
        data = case['data']
        root_pin = data['directories'].get(str(directory))
        db_pin = data['files'].get(str(database))
        hold(type(root_pin) is dict and type(db_pin) is dict
             and self.files.directory(directory) == root_pin
             and canonical(value['root']) == canonical([case['prior']['registry_parent'][0], root_pin['ino']])
             and canonical(value['database']) == canonical([case['prior']['registry_parent'][0], db_pin['ino']]))
        if self.journal is None:
            self._journal_hash(database, db_pin)
            self.journal = (database, db_pin)
        else:
            hold(self.journal == (database, db_pin))
            self.files.check_file(database)
        return True

    def finish(self):
        hold(not self.closed)
        self.member(self.policy.data)
        for value, raw in self.value_refs:
            hold(raw == (canonical(value) + '\n').encode())
        if self.journal is not None:
            self._journal_hash(*self.journal)
        for category in ('proof', 'checkpoint', 'record'):
            self.files.verify(category)
        self.member(self.policy.data)
        # member() can itself read a proof. Verify the complete observed set
        # after that final read, before returning a usable exclusion result.
        self.reader.verify()
        self.source.guard()

    def __exit__(self, kind, value, traceback):
        failure = value
        try:
            if kind is None:
                self.finish()
        except BaseException as error:
            failure = error
            raise
        finally:
            self.closed = True
            _ENTERED.discard(self)
            _CONSTRUCTED.discard(self)
            try:
                self.files.close()
            except BaseException:
                if failure is None:
                    raise


@contextmanager
def revision_read_scope(policy, db):
    hold(type(policy) is ConnectionPolicy)
    if type(policy.value.get('schema')) is int and policy.value['schema'] == 1:
        # Original single-account journals retain all original physical checks.
        yield None
        return
    hold(type(policy.value.get('schema')) is int and policy.value['schema'] == 2)
    with _RevisionReadFrame(policy, db) as frame:
        yield frame
