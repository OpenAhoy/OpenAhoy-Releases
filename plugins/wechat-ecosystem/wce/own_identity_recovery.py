"""Explicit, checkpoint-bound local identity relocation for a trusted host.

No MCP tool or default checkpoint is exposed. Ordinary member validation never
falls back here. Only a fresh human review can consume an external case.
"""
import base64
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time

from .contracts import WCEError
from .own_body_recovery import code_scope
from .own_bootstrap_security import path_check
from .own_connection_policy import CAPABILITIES, POLICY, load_policy, read_registry
from .own_connection_registry import (OWNER, digest, metadata, owner_value, revoked,
    sha, transaction_path, validate_owner)
from .own_connection_enrollment import policy_value, published_entry
from .own_identity_checkpoint import (HEX, Reader, TrustedCase, check_locks,
    checkpoint_locks, existing_lock, file_metadata, require, verify_snapshot)
from .service import canonical

PROOF_FIELDS = {'schema', 'id', 'state', 'registry', 'registry_parent', 'journal_parent',
                'owner', 'before', 'after', 'policies'}
RELOCATION_FIELDS = {'schema', 'checkpoint_sha256', 'case_id', 'prior_proofs', 'preservation_digest'}


def raw_json(value):
    return (canonical(value) + '\n').encode()


def validate_relocation_proof(proof, *, reader=None):
    """Extra normal-read checks, in addition to every original member check."""
    try:
        return _validate_relocation_proof(proof, reader=reader)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise WCEError('CONNECTION_RELOCATION_PROOF_INVALID') from None


def _validate_relocation_proof(proof, *, reader=None):
    require(type(proof) is dict and set(proof) == PROOF_FIELDS | {'relocation'} and
            type(proof['schema']) is int and proof['schema'] == 2 and
            proof['state'] in {'PREPARED', 'COMMITTED', 'ABORTED'}, 'PROOF_INVALID')
    relocation = proof['relocation']
    require(type(relocation) is dict and set(relocation) == RELOCATION_FIELDS and
            type(relocation['schema']) is int and relocation['schema'] == 1, 'PROOF_INVALID')
    for name in ('checkpoint_sha256', 'case_id', 'preservation_digest'):
        require(type(relocation[name]) is str and HEX.fullmatch(relocation[name]) is not None, 'PROOF_INVALID')
    from .own_identity_checkpoint import case_identifier
    require(relocation['case_id'] == case_identifier(proof['registry'], relocation['checkpoint_sha256']), 'PROOF_INVALID')
    before, after, changes = proof['before'], proof['after'], proof['policies']
    registry = Path(proof['registry']); transaction_path(registry, proof['id'])
    require(type(before) is dict and type(after) is dict and
            set(before) == set(after) == {'schema', 'owner_digest', 'connections', 'entries'} and
            type(before['schema']) is int and before['schema'] == 2 and
            type(after['schema']) is int and after['schema'] == 2 and
            before['owner_digest'] == after['owner_digest'] == digest(proof['owner']), 'PROOF_INVALID')
    require(type(before['connections']) is dict and type(after['connections']) is dict and
            before['connections'] == after['connections'] and
            type(before['entries']) is dict and type(after['entries']) is dict and
            set(before['entries']) == set(after['entries']) == set(before['connections']) and
            bool(before['entries']) and type(changes) is dict and
            set(changes) == set(before['connections'].values()), 'PROOF_INVALID')
    expected_paths = {str(transaction_path(registry, entry['transaction'])) for entry in before['entries'].values()}
    require(type(relocation['prior_proofs']) is dict and set(relocation['prior_proofs']) == expected_paths and
            str(transaction_path(registry, proof['id'])) not in expected_paths, 'PROOF_INVALID')
    predecessors = {}
    from .own_account_metadata import AccountMetadataReader
    reader = reader if reader is not None else AccountMetadataReader(registry.parent)
    for name, expected in relocation['prior_proofs'].items():
        require(type(expected) is str and HEX.fullmatch(expected) is not None, 'PROOF_INVALID')
        observed, raw = reader.read(Path(name), keep=True)
        require(observed['sha256'] == expected, 'PREDECESSOR_CHANGED')
        from .own_bootstrap_security import decode
        from .own_account_metadata import decode_metadata
        prior = decode_metadata(raw)
        require(type(prior) is dict and set(prior) == PROOF_FIELDS and
                type(prior['schema']) is int and prior['schema'] == 1 and prior['state'] == 'COMMITTED' and
                prior['owner'] == proof['owner'] and prior['registry'] == str(registry) and
                str(transaction_path(registry, prior['id'])) == name, 'PREDECESSOR_UNSUPPORTED')
        predecessors[name] = prior
    for cid, path in before['connections'].items():
        change = changes[path]
        require(type(change) is dict and set(change) == {'before', 'after', 'pins'} and
                type(change['before']) is dict and type(change['after']) is dict and
                type(change['pins']) is dict and set(change['pins']) ==
                {'root', 'images', 'database', 'profile_sha256', 'revoked'} and
                type(change['pins']['revoked']) is bool, 'PROOF_INVALID')
        old, new, pins = change['before'], change['after'], change['pins']
        require(type(old.get('schema')) is int and old['schema'] == 2 and
                set(new) == set(old) and new['schema'] == 2 and
                old['identity'] == new['identity'] and new['identity']['connection_id'] == cid and
                new['identity']['private_directory'] == str(Path(path).parent) and
                owner_value(registry, new['identity']['actor']) == proof['owner'] and
                new['owner_digest'] == old['owner_digest'] == digest(proof['owner']) and
                new['registry_path'] == old['registry_path'] == str(registry) and
                new['policy'] == old['policy'] == POLICY and
                new['capabilities'] == old['capabilities'] == CAPABILITIES and
                new['duration'] == old['duration'] == 'UNTIL_DISCONNECTED' and
                type(new['revision']) is int and new['revision'] == old['revision'] + 1 and
                type(new['enabled']) is bool and new['enabled'] == (old['enabled'] and not pins['revoked']) and
                new['transaction'] == proof['id'] and old['transaction'] == before['entries'][cid]['transaction'], 'PROOF_INVALID')
        require(before['entries'][cid] == published_entry(old, before['entries'][cid]['label']) and
                after['entries'][cid] == published_entry(new, before['entries'][cid]['label']), 'PROOF_INVALID')
        prior = predecessors[str(transaction_path(registry, old['transaction']))]
        require(prior.get('after', {}).get('entries', {}).get(cid) == before['entries'][cid] and
                prior.get('policies', {}).get(path, {}).get('after') == old, 'PREDECESSOR_CHANGED')
    return True


def historic_base(case):
    """Pinned historical relationship only. This function grants no membership."""
    registry = case.registry
    data = read_registry(registry)
    require(data['schema'] == 2 and set(data['connections']) == set(case.value['targets']), 'SOURCE_CHANGED')
    owner = validate_owner(registry, metadata(registry.parent / OWNER))
    policies, prior_proofs, raw_before, mismatches = {}, {}, {}, {}
    reader = Reader(case.base)
    _, raw = reader.read(registry, keep=True); raw_before[str(registry)] = base64.b64encode(raw).decode('ascii')
    for cid, path in data['connections'].items():
        policy = load_policy(path, active=False); value = policy.value; entry = data['entries'][cid]
        require(value['schema'] == 2 and policy.data['connection_id'] == cid and
                value['owner_digest'] == digest(owner) and owner_value(registry, policy.data['actor']) == owner and
                entry == published_entry(value, entry['label']) and value['registry_path'] == str(registry), 'IDENTITY_CHANGED')
        profile_meta, _ = reader.read(policy.root / 'profile.json')
        proof_path = transaction_path(registry, value['transaction'])
        require(proof_path in case.files and case.files[proof_path] is not None, 'SOURCE_UNVERIFIED')
        proof_meta, _ = reader.read(proof_path)
        proof = metadata(proof_path)
        require(type(proof) is dict and set(proof) == PROOF_FIELDS and type(proof['schema']) is int and
                proof['schema'] == 1 and proof['state'] == 'COMMITTED' and proof['id'] == value['transaction'] and
                proof['registry'] == str(registry) and proof['owner'] == owner and
                proof.get('after', {}).get('entries', {}).get(cid) == entry and
                proof.get('policies', {}).get(path, {}).get('after') == value, 'PREDECESSOR_UNSUPPORTED')
        pins = proof['policies'][path]['pins']
        require(pins['profile_sha256'] == profile_meta['sha256'], 'IDENTITY_CHANGED')
        mismatch = {'journal_parent': proof['journal_parent'] != list(path_check(proof_path.parent, True)),
                    'root': pins['root'] != list(policy.root_pin), 'images': pins['images'] != list(policy.image_pin),
                    'database': pins['database'] != list(policy.database_pin[:2])}
        mismatches[cid] = mismatch
        prior_proofs[str(proof_path)] = proof_meta['sha256']
        _, raw = reader.read(policy.path, keep=True)
        require(len(raw) <= 16384, 'LIMIT')
        raw_before[path] = base64.b64encode(raw).decode('ascii')
        policies[path] = {'value': value, 'root': list(policy.root_pin), 'images': list(policy.image_pin),
                          'database': list(policy.database_pin[:2]), 'profile_sha256': profile_meta['sha256'],
                          'revoked': revoked(policy)}
    require(any(any(v.values()) for v in mismatches.values()), 'NOT_REQUIRED')
    return {'registry': str(registry), 'registry_value': data, 'owner': owner, 'policies': policies,
            'scope': code_scope(), 'parent': list(path_check(registry.parent, True))}, prior_proofs, raw_before, mismatches


def validate_case_record(case, record):
    """Bind restart evidence to the original reservation, never to live defaults."""
    proof = record['proof']
    validate_relocation_proof(proof)
    require(proof['state'] == 'PREPARED' and proof['id'] == case.value['transaction'] and
            proof['registry'] == str(case.registry) and
            set(proof['before']['connections']) == set(case.value['targets']) and
            proof['relocation']['case_id'] == case.value['case_id'] and
            proof['relocation']['checkpoint_sha256'] == case.value['checkpoint_sha256'] and
            proof['relocation']['preservation_digest'] == digest({'files': case.snapshot['files'],
                                                                 'members': case.snapshot['members']}), 'CASE_INVALID')
    originals = record['raw_before']
    require(type(originals) is dict and set(originals) == set(proof['policies']) | {str(case.registry)}, 'CASE_INVALID')
    for name, encoded in originals.items():
        limit = case.files.get(Path(name), {}).get('bytes', 0) if name == str(case.registry) else 16384
        require(type(encoded) is str and len(encoded) <= 4 * ((limit + 2) // 3), 'CASE_INVALID')
        try: raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError): raise WCEError('CONNECTION_RELOCATION_CASE_INVALID') from None
        require(base64.b64encode(raw).decode('ascii') == encoded and len(raw) <= limit and
                sha256(raw).hexdigest() == case.files.get(Path(name), {}).get('sha256'), 'CASE_INVALID')
        from .own_bootstrap_security import decode
        require(decode(raw, limit) == (proof['before'] if name == str(case.registry)
                                     else proof['policies'][name]['before']), 'CASE_INVALID')
    for change in proof['policies'].values():
        require(change['after']['candidate_scope'] == case.value['candidate_scope'], 'CASE_INVALID')
    for name, expected in proof['relocation']['prior_proofs'].items():
        require(case.files.get(Path(name), {}).get('sha256') == expected, 'CASE_INVALID')


def atomic_raw(path, raw, expected_hash, before_replace=lambda: None, exclusive=False, temporary_root=None,
               publication_gate=None, after_publish=lambda: None, final_check=lambda: None):
    """A raw CAS; caller owns all locks and the cancellation linearization gate."""
    path = Path(path); reader = Reader()
    scratch = Path(temporary_root or path.parent)
    with reader.directory(path.parent) as parent, reader.directory(scratch) as scratch_fd:
        require(os.fstat(parent).st_dev == os.fstat(scratch_fd).st_dev, "DIFFERENT_FILESYSTEM")
        name = '.wce-relocate-' + secrets.token_hex(16)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=scratch_fd)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(raw); stream.flush(); os.fsync(fd)
            # Slow preparation stays cancellable; publication alone owns the gate.
            with publication_gate if publication_gate is not None else nullcontext():
                before_replace()
                meta, _ = reader.read(path, optional=exclusive)
                require(meta is None if exclusive else meta is not None and meta['sha256'] == expected_hash, 'CAS_CONFLICT')
                final_check()
                if exclusive:
                    os.link(name, path.name, src_dir_fd=scratch_fd, dst_dir_fd=parent, follow_symlinks=False)
                    os.unlink(name, dir_fd=scratch_fd)
                else: os.replace(name, path.name, src_dir_fd=scratch_fd, dst_dir_fd=parent)
                # A visible COMMITTED marker is already too late to report cancellation,
                # including when a later fsync/readback fails and durability is unknown.
                after_publish()
                os.fsync(parent); os.fsync(scratch_fd)
                meta, actual = reader.read(path, keep=True)
                require(actual == raw and meta['mode'] == 0o600, 'WRITE_UNKNOWN')
        finally:
            os.close(fd)
            try: os.unlink(name, dir_fd=scratch_fd)
            except FileNotFoundError: pass


def write_ledger(case, previous, value):
    require(case.ledger() == previous, 'CASE_CHANGED')
    data = raw_json(value); require(len(data) <= 512 * 1024, 'LIMIT')
    old, _ = Reader(case.root).read(case.ledger_path)
    atomic_raw(case.ledger_path, data, old['sha256'], temporary_root=case.root)


class RecoverySession:
    """The trusted TTY owns this object and never exposes it to MCP."""
    def __init__(self, case=None, *, wall=time.time, clock=time.monotonic, fault=lambda stage: None):
        require(isinstance(case, TrustedCase), 'TRUSTED_CHECKPOINT_REQUIRED')
        self.case, self.wall, self.clock, self.fault = case, wall, clock, fault
        self.gate = threading.RLock(); self.closed = False; self.committed = False
        self.generation = 0; self.proposed = None

    def close(self):
        with self.gate:
            self.closed = True; self.generation += 1
            return 'ALREADY_COMMITTED' if self.committed else 'CANCELLED'

    def prepare(self):
        case = self.case
        policies = [p for p in case.files if p.name == 'connection-policy.json']
        with checkpoint_locks(case, policies) as (held, old_locks):
            require(case.ledger()['state'] == 'RESERVED', 'CASE_SPENT')
            fingerprint = verify_snapshot(case)
            base, prior, originals, mismatches = historic_base(case)
            old_locks([Path(p) for p in prior]); check_locks(held)
            require(base['scope'] == case.value['candidate_scope'], 'SCOPE_CHANGED')
            require(verify_snapshot(case) == fingerprint, 'STATE_CHANGED')
        with self.gate:
            require(not self.closed, 'CANCELLED')
            self.generation += 1
            self.proposed = {'base': base, 'prior': prior, 'raw_before': originals,
                'fingerprint': fingerprint, 'created': self.clock(), 'wall': self.wall(),
                'generation': self.generation, 'challenge': 'recover ' + secrets.token_hex(16)}
            return {'checkpoint_sha256': case.value['checkpoint_sha256'], 'candidate_scope': base['scope'],
                'accounts': [{'connection_id': old['value']['identity']['connection_id'],
                    'appid': old['value']['identity']['appid'],
                    'label': base['registry_value']['entries'][old['value']['identity']['connection_id']]['label'],
                    'pin_mismatches': mismatches[old['value']['identity']['connection_id']],
                    'enabled_after': old['value']['enabled'] and not old['revoked']} for old in base['policies'].values()],
                'scope_of_proof': 'EXACT_OBSERVED_LOCAL_CHECKPOINT_ONLY', 'precheckpoint_history': 'NOT_PROVEN',
                'network_requests': 0, 'business_requests': 0, 'expires_in_seconds': 120}

    def _live(self, proposed):
        require(code_scope() == self.case.value['candidate_scope'], 'SCOPE_CHANGED')
        require(not self.closed and proposed['generation'] == self.generation, 'CANCELLED')
        elapsed, wall_elapsed = self.clock() - proposed['created'], self.wall() - proposed['wall']
        require(0 <= elapsed < 120 and 0 <= wall_elapsed < 120 and abs(elapsed - wall_elapsed) < 5, 'EXPIRED')

    def commit(self, answer):
        case = self.case; proposed = self.proposed
        require(type(proposed) is dict and type(answer) is str and
                hmac.compare_digest(answer, proposed['challenge']), 'CONFIRMATION_REQUIRED')
        base = proposed['base']; paths = list(base['policies'])
        with checkpoint_locks(case, paths) as (held, old_locks):
            old_locks([Path(p) for p in proposed['prior']])
            with self.gate:
                self._live(proposed); check_locks(held)
                previous = case.ledger(); require(previous['state'] == 'RESERVED', 'CASE_SPENT')
                require(verify_snapshot(case) == proposed['fingerprint'], 'STATE_CHANGED')
                proof = self._proof(proposed)
                validate_relocation_proof(proof)
                claimed = {'schema': 1, 'state': 'CLAIMED', 'case_id': case.value['case_id'],
                    'reservation_sha256': case.expected_digest, 'proof': proof,
                    'raw_before': proposed['raw_before']}
                # Immutable raw backups are in the durable external claim before any .wce writes.
                self.fault('before_claim'); self._live(proposed); write_ledger(case, previous, claimed)
            self.fault('after_claim')
            proof_path = transaction_path(case.registry, proof['id'])
            lock_path = proof_path.with_suffix('.lock')
            with Reader(case.base).directory(lock_path.parent) as parent:
                fd = os.open(lock_path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                os.close(fd); os.fsync(parent)
            new_held = []
            with existing_lock(lock_path, new_held):
                all_held = [*held, *new_held]
                def guard():
                    self._live(proposed); check_locks(all_held)
                    require(case.ledger() == claimed, 'CASE_CHANGED')
                    self._check_projection(claimed)
                self.fault('before_proof'); guard()
                atomic_raw(proof_path, raw_json(proof), None, guard, exclusive=True, temporary_root=case.root,
                           final_check=lambda:self._live(proposed))
                self.fault('after_proof')
                for index, (path, change) in enumerate(proof['policies'].items()):
                    guard(); self.fault('before_policy_' + str(index)); guard()
                    before_raw = base64.b64decode(claimed['raw_before'][path], validate=True)
                    atomic_raw(Path(path), raw_json(change['after']), sha256(before_raw).hexdigest(), guard, temporary_root=case.root,
                               final_check=lambda:self._live(proposed))
                    self.fault('after_policy_' + str(index))
                guard(); self.fault('before_registry'); guard()
                original = base64.b64decode(claimed['raw_before'][str(case.registry)], validate=True)
                atomic_raw(case.registry, raw_json(proof['after']), sha256(original).hexdigest(), guard, temporary_root=case.root,
                           final_check=lambda:self._live(proposed))
                self.fault('after_registry')
                # Cancellation and final publication share one linearization gate.
                guard(); self.fault('before_commit')
                completed = proof | {'state': 'COMMITTED'}
                def publication_guard():
                    self.fault('before_publication'); guard(); self._require_after(proof)
                def published(): self.committed = True
                atomic_raw(proof_path, raw_json(completed), sha256(raw_json(proof)).hexdigest(), publication_guard,
                           temporary_root=case.root, publication_gate=self.gate, after_publish=published,
                           final_check=lambda:self._live(proposed))
                self.fault('after_commit')
                write_ledger(case, claimed, claimed | {'state': 'COMMITTED'})
                self.fault('after_ledger_commit')
                check_locks(all_held)
        return {'state': 'COMMITTED', 'network_requests': 0, 'business_requests': 0}

    def _proof(self, proposed):
        case = self.case; base = proposed['base']; transaction = case.value['transaction']
        after = deepcopy(base['registry_value']); changes = {}
        for path, old in base['policies'].items():
            value = old['value']
            updated = policy_value(value['identity'], base, transaction, value['revision'] + 1,
                                   value['enabled'] and not old['revoked'])
            updated['confirmed_at'] = self.wall()
            pins = {k: old[k] for k in ('root', 'images', 'database', 'profile_sha256', 'revoked')}
            changes[path] = {'before': value, 'after': updated, 'pins': pins}
            cid = value['identity']['connection_id']
            after['entries'][cid] = published_entry(updated, after['entries'][cid]['label'])
        return {'schema': 2, 'id': transaction, 'state': 'PREPARED', 'registry': str(case.registry),
            'registry_parent': list(path_check(case.base, True)),
            'journal_parent': list(path_check(case.base / 'connection-transactions', True)),
            'owner': base['owner'], 'before': base['registry_value'], 'after': after, 'policies': changes,
            'relocation': {'schema': 1, 'checkpoint_sha256': case.value['checkpoint_sha256'],
                'case_id': case.value['case_id'], 'prior_proofs': proposed['prior'],
                'preservation_digest': proposed['fingerprint']}}

    def _check_projection(self, record):
        proof = record['proof']; proof_path = transaction_path(self.case.registry, proof['id'])
        substitutions = {Path(path): {sha256(base64.b64decode(raw, validate=True)).hexdigest()}
                         for path, raw in record['raw_before'].items()}
        for path, change in proof['policies'].items(): substitutions[Path(path)].add(sha256(raw_json(change['after'])).hexdigest())
        substitutions[self.case.registry].add(sha256(raw_json(proof['after'])).hexdigest())
        additions = {}
        if os.path.lexists(proof_path):
            additions[proof_path.name] = {sha256(raw_json(proof | {'state': s})).hexdigest()
                                         for s in ('PREPARED', 'COMMITTED', 'ABORTED')}
        if os.path.lexists(proof_path.with_suffix('.lock')): additions[proof_path.with_suffix('.lock').name] = {sha256(b'').hexdigest()}
        return verify_snapshot(self.case, substitutions, {proof_path.parent: additions})

    def reconcile(self):
        """Explicit original-case reconciliation. A new process never rolls forward."""
        case = self.case; record = case.ledger()
        if record['state'] == 'RESERVED': return {'state': 'NOT_ADMITTED'}
        proof = record.get('proof'); validate_relocation_proof(proof)
        require(set(record.get('raw_before', {})) == set(proof['policies']) | {str(case.registry)}, 'CASE_INVALID')
        paths = list(proof['policies']); proof_path = transaction_path(case.registry, proof['id'])
        with checkpoint_locks(case, paths) as (held, old_locks):
            old_locks([Path(p) for p in proof['relocation']['prior_proofs']])
            self._check_projection(record); check_locks(held)
            require(case.ledger() == record, 'CASE_CHANGED')
            if not os.path.lexists(proof_path.with_suffix('.lock')):
                require(not os.path.lexists(proof_path) and all(Reader().read(Path(path), keep=True)[1] ==
                    base64.b64decode(raw, validate=True) for path, raw in record['raw_before'].items()), 'CAS_CONFLICT')
                write_ledger(case, record, record | {'state': 'SPENT_ABORTED'})
                return {'state': 'SPENT_ABORTED'}
            new_held = []
            with existing_lock(proof_path.with_suffix('.lock'), new_held):
                all_held = [*held, *new_held]
                actual = metadata(proof_path) if os.path.lexists(proof_path) else None
                if actual is not None and actual['state'] == 'COMMITTED':
                    require(actual == proof | {'state': 'COMMITTED'}, 'CAS_CONFLICT')
                    self._require_after(proof)
                    check_locks(all_held)
                    if record['state'] != 'COMMITTED': write_ledger(case, record, record | {'state': 'COMMITTED'})
                    return {'state': 'COMMITTED'}
                require(record['state'] != 'COMMITTED', 'COMMIT_PROOF_MISSING')
                if actual is not None: require(actual == proof or actual == proof | {'state': 'ABORTED'}, 'CAS_CONFLICT')
                for path, raw in record['raw_before'].items():
                    before = base64.b64decode(raw, validate=True)
                    current_meta, current = Reader().read(Path(path), keep=True)
                    after = raw_json(proof['after'] if Path(path) == case.registry else proof['policies'][path]['after'])
                    require(current in (before, after), 'CAS_CONFLICT')
                    if current == after:
                        def rollback_guard():
                            check_locks(all_held); require(case.ledger() == record, 'CASE_CHANGED'); self._check_projection(record)
                        self.fault('before_rollback'); rollback_guard()
                        atomic_raw(Path(path), before, current_meta['sha256'], rollback_guard, temporary_root=case.root)
                        self.fault('after_rollback')
                self._check_projection(record); check_locks(all_held)
                aborted = raw_json(proof | {'state': 'ABORTED'})
                atomic_raw(proof_path, aborted, sha256(raw_json(actual)).hexdigest() if actual else None,
                           lambda: check_locks(all_held), exclusive=actual is None, temporary_root=case.root)
                write_ledger(case, record, record | {'state': 'SPENT_ABORTED'})
                return {'state': 'SPENT_ABORTED'}

    @staticmethod
    def _require_after(proof):
        require(metadata(proof['registry']) == proof['after'] and all(metadata(path) == change['after']
                for path, change in proof['policies'].items()), 'CAS_CONFLICT')
