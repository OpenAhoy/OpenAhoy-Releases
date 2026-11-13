"""Exact completed-record history sources; never a live cover-read grant.

Only the historical schema3 validator calls this context. Current membership and
the actual SQLite source are checked separately from the immutable old suffix.
No claim about an unvisited current metadata prefix is made here.
"""
from contextlib import contextmanager
from hashlib import sha256
import re
from types import MappingProxyType

from . import own_history_identity as original
from .own_bootstrap_security import decode, private_read
from .own_connection_policy import ConnectionPolicy
from .own_connection_registry import transaction_path, validate_registry, owner_value
from .own_connection_enrollment import published_entry
from .own_cover_authority import filename, historical_profile
from .own_history_locators import checked, history_scope
from .own_history_source import connection_source, safe_path, hold, CHECKPOINT_DIRECTORY
from .own_identity_checkpoint import case_identifier
from .own_identity_recovery import PROOF_FIELDS, validate_relocation_proof
from .service import canonical, digest


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


# Populated from reviewed immutable migration inputs, not from caller settings.
# Values are hashes and opaque technical identifiers, never user article data.
_SOURCES = ()  # New installations have no imported private completed cases.


def _row(db, supplied, entry):
    rows = db.execute('SELECT * FROM own_steps WHERE id=?', (supplied['id'],)).fetchall()
    hold(len(rows) == 1)
    actual = dict(rows[0])
    hold(actual == dict(supplied) and digest(actual) == entry['record_digest']
         and digest(actual['id']) == entry['record_id_digest']
         and actual['state'] == 'SUCCEEDED' and actual['operation'] == 'cover'
         and actual['intent_digest'] == entry['intent_digest']
         and actual['result_digest'] == entry['result_digest'])
    return actual


def _current(w, db, profile, row, intent, result, grant, source, scope):
    policy = getattr(w, 'policy', None)
    hold(type(policy) is ConnectionPolicy and digest(policy.data) == source['identity_digest'])
    scope = checked(scope, policy.value['registry_path'])
    hold(scope is not None)
    hold(scope.policy is policy and scope.db is db and connection_source(db) is scope.source
         and scope.source.path == policy.root / 'state.sqlite3'
         and w.db.path == scope.source.path and not scope.closed)
    scope.source.guard()
    policy.check(readonly=True, proof_reader=scope.reader)
    binding = historical_profile(policy).binding()
    entry = source['record']
    hold(grant['binding'] == profile.binding() == binding
         and digest(binding) == entry['binding_digest'])
    actual = _row(db, row, entry)
    from .own_workflow import stored
    hold(stored(actual['intent'], actual['intent_digest']) == intent
         and stored(actual['result'], actual['result_digest']) == result)
    return policy, scope


def _record_files(scope, policy, row, result, proof, grant, entry):
    grant_path = policy.root / filename(grant['id'])
    proof_path = policy.root / ('reconciliation-' + row['id'] + '-' + grant['id'] + '.json')
    claim_path = policy.root / filename(grant['id'], True)
    hold(result['reconciliation_proof'] == proof_path.name
         and result['reconciliation_proof_sha256'] == entry['proof_sha256']
         and proof['grant_sha256'] == entry['grant_sha256']
         and proof['claimed_sha256'] == entry['claimed_sha256'])
    values = ((grant_path, entry['grant_sha256'], grant),
              (proof_path, entry['proof_sha256'], proof),
              (claim_path, entry['claimed_sha256'], None))
    observed = []
    for path, checksum, value in values:
        meta, raw = scope.files.read(path, 262144, 'record')
        hold(meta['sha256'] == checksum)
        decoded = decode(raw, 262144)
        hold(raw == (canonical(decoded) + '\n').encode()
             and (value is None or decoded == value))
        observed.append((path, meta, raw))
    return observed


def _proof(scope, name):
    path = transaction_path(scope.registry, name)
    meta, raw = scope.reader.read(path, keep=True)
    value = decode(raw, 262144)
    hold(type(value) is dict and type(value.get('schema')) is int
         and value['schema'] in (1, 2)
         and set(value) == PROOF_FIELDS | ({'relocation'} if value['schema'] == 2 else set())
         and value['id'] == name and value['state'] == 'COMMITTED'
         and value['registry'] == str(scope.registry) and value['owner'] == scope.owner
         and raw == (canonical(value) + '\n').encode())
    for registry_value in (value['before'], value['after']):
        validate_registry(scope.registry, registry_value)
    return path, meta, value


def _change(scope, policy, proof, expected, expected_entry):
    cid, path = policy.data['connection_id'], str(policy.path)
    change = proof['policies'].get(path)
    hold(type(change) is dict and set(change) == {'before', 'after', 'pins'}
         and change['after'] == expected and expected['identity'] == policy.data
         and proof['after']['connections'].get(cid) == path
         and proof['after']['entries'].get(cid) == expected_entry
         and expected_entry == published_entry(expected, expected_entry['label']))
    before = change['before']
    hold(type(before) is dict and type(before.get('schema')) is int and before['schema'] == 2
         and type(before.get('revision')) is int and type(expected.get('revision')) is int
         and expected['revision'] == before['revision'] + 1
         and expected['transaction'] == proof['id'] and before['transaction'] != proof['id']
         and all(before.get(k) == expected[k] for k in
                 ('identity', 'policy', 'capabilities', 'duration', 'registry_path', 'owner_digest'))
         and proof['before']['connections'].get(cid) == path
         and proof['before']['entries'].get(cid)
             == published_entry(before, proof['before']['entries'][cid]['label']))
    pins = change['pins']
    hold(type(pins) is dict and set(pins) == {'root', 'images', 'database', 'profile_sha256', 'revoked'}
         and type(pins['revoked']) is bool)
    for key in ('root', 'images', 'database'):
        hold(type(pins[key]) is list and len(pins[key]) == 2
             and all(type(v) is int and v >= 0 for v in pins[key]))
    hold(type(pins['profile_sha256']) is str and re.fullmatch('[a-f0-9]{64}', pins['profile_sha256']))
    return change


def _legacy_checkpoint(raw, registry, entry):
    """One original bounded IDREC snapshot, not a modern closed-set parser."""
    hold(0 < len(raw) <= 65536 and sha256(raw).hexdigest() == entry['checkpoint_sha256'])
    value = decode(raw, 65536)
    hold(type(value) is dict and set(value) ==
         {'accounts', 'backup', 'catalog', 'catalog_metadata', 'config', 'directories', 'installed', 'release_sha256'})
    data = value['accounts']
    hold(type(data) is dict and set(data) ==
         {'files', 'members', 'directories', 'keychain_access', 'business_write'}
         and data['keychain_access'] is False and data['business_write'] is False
         and all(type(data[k]) is dict for k in ('files', 'members', 'directories'))
         and len(data['files']) <= 256 and len(data['members']) <= 64 and len(data['directories']) <= 64)
    base = registry.parent
    for name, pin in data['files'].items():
        hold(safe_path(name).is_relative_to(base))
        if pin is None:
            continue
        hold(type(pin) is dict and set(pin) ==
             {'dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'bytes', 'mtime_ns', 'ctime_ns', 'sha256'}
             and all(type(v) is int and v >= 0 for k, v in pin.items() if k != 'sha256')
             and type(pin['sha256']) is str and re.fullmatch('[a-f0-9]{64}', pin['sha256']))
    metadata_only = []
    for name, pin in data['directories'].items():
        if not safe_path(name).is_relative_to(base):
            metadata_only.append(name)
        hold(pin is None or (type(pin) is dict and set(pin) == {'dev', 'ino', 'mode', 'uid', 'gid'}
                             and all(type(v) is int and v >= 0 for v in pin.values())))
    # The original bounded source also recorded ancillary ancestor/project
    # directory metadata. Preserve it without opening those paths at runtime.
    hold(digest(sorted(metadata_only)) == entry['metadata_only_directory_names_sha256'])
    for name, names in data['members'].items():
        hold(safe_path(name).is_relative_to(base))
        hold(names is None or (type(names) is list and names == sorted(set(names))
             and len(names) <= 1024 and all(type(v) is str and v not in ('', '.', '..')
                 and '/' not in v and '\\' not in v and not any(ord(c) < 32 or ord(c) == 127 for c in v)
                 for v in names)))
    return data


def _schema1_peers(scope, proof, physical):
    """This fixed migration suffix consists of complete ordinary upgrades."""
    hold(proof['schema'] == 1 and set(proof['policies'])
         == set(proof['before']['connections'].values())
         == set(proof['after']['connections'].values()) == set(physical))
    for path, change in proof['policies'].items():
        hold(type(change) is dict and set(change) == {'before', 'after', 'pins'})
        before, after = change['before'], change['after']
        hold(type(before) is dict and type(after) is dict
             and type(before.get('schema')) is int and before['schema'] == 2
             and type(after.get('schema')) is int and after['schema'] == 2
             and set(before) == set(after)
             and type(before.get('revision')) is int and type(after.get('revision')) is int
             and after['revision'] == before['revision'] + 1
             and after['transaction'] == proof['id'] and before['transaction'] != proof['id']
             and all(after[k] == before[k] for k in
                     ('identity', 'policy', 'capabilities', 'duration', 'registry_path', 'owner_digest', 'enabled'))
             and before['registry_path'] == str(scope.registry)
             and before['owner_digest'] == digest(scope.owner)
             and owner_value(scope.registry, before['identity']['actor']) == scope.owner
             and change['pins'] == physical[path])
        cid = after['identity']['connection_id']
        hold(after['identity']['private_directory'] == str(safe_path(path).parent)
             and proof['before']['connections'].get(cid) == path
             and proof['after']['connections'].get(cid) == path
             and proof['before']['entries'].get(cid)
                 == published_entry(before, proof['before']['entries'][cid]['label'])
             and proof['after']['entries'].get(cid)
                 == published_entry(after, proof['after']['entries'][cid]['label']))


def _checkpoint(scope, proof, entry):
    relation = proof['relocation']
    hold(proof['id'] == entry['transaction']
         and relation['case_id'] == entry['case_id']
         and relation['checkpoint_sha256'] == entry['checkpoint_sha256']
         and relation['preservation_digest'] == entry['preservation_digest']
         and relation['case_id'] == case_identifier(scope.registry, relation['checkpoint_sha256']))
    if entry['format'] == 'CLOSED_SET_V2':
        data = scope._checkpoint(proof)
    else:
        hold(entry['format'] == 'IDREC_CHECKPOINT_V1_BOUNDED')
        path = scope.base / CHECKPOINT_DIRECTORY / (entry['case_id'] + '.legacy-bounded-v1.json')
        meta, raw = scope.files.read(path, 65536, 'checkpoint')
        hold(meta['sha256'] == entry['checkpoint_sha256'])
        data = _legacy_checkpoint(raw, scope.registry, entry)
    hold(digest({'files': data['files'], 'members': data['members']}) == relation['preservation_digest'])
    return data


def _adoption(scope, policy, proof, change, data, *, live=False):
    hold(set(proof['policies']) == set(proof['before']['connections'].values())
         == set(proof['after']['connections'].values()))
    for policy_path, peer in proof['policies'].items():
        peer_root = safe_path(policy_path).parent
        hold(peer_root.is_relative_to(scope.base)
             and peer['after']['identity']['private_directory'] == str(peer_root))
        pins = peer['pins']
        for key, target, category in (
                ('root', peer_root, 'directories'), ('images', peer_root / 'images', 'directories'),
                ('database', peer_root / 'state.sqlite3', 'files')):
            item = data[category].get(str(target))
            hold(type(item) is dict and pins[key] == [item['dev'], item['ino']])
            if live:
                if category == 'directories':
                    hold(scope.files.directory(target) == item)
                else:
                    actual = scope.files.file(target, mutable=True)['pin']
                    hold(all(actual[k] == item[k] for k in ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink')))
        profile_path = peer_root / 'profile.json'
        profile = data['files'].get(str(profile_path))
        hold(type(profile) is dict and pins['profile_sha256'] == profile['sha256'])
        if live:
            meta, raw = scope.files.read(profile_path, 262144, 'record')
            hold(meta['sha256'] == profile['sha256'])
    for target, recorded in ((scope.base, proof['registry_parent']),
                             (transaction_path(scope.registry, proof['id']).parent, proof['journal_parent'])):
        item = data['directories'].get(str(target))
        hold(type(item) is dict and recorded == [item['dev'], item['ino']])
        if live:
            hold(scope.files.directory(target) == item)


def _retained(outer, path, meta, phase=None):
    # The outer full snapshot describes the files now actually held. Older
    # snapshots authenticate their own historical bytes, not current metadata.
    hold(outer['files'].get(str(path)) == meta)
    if phase is not None:
        old = phase['files'].get(str(path))
        hold(type(old) is dict and old['sha256'] == meta['sha256'])


def _prior_phase(scope, policy, proof, change, checkpoint, outer, visited):
    original.check_relocation_predecessors(proof, visited)
    path, meta, prior = _proof(scope, change['before']['transaction'])
    hold(proof['relocation']['prior_proofs'].get(str(path)) == meta['sha256']
         and prior['schema'] == 1)
    _retained(outer, path, meta, checkpoint)
    cid = policy.data['connection_id']
    old = prior['policies'].get(str(policy.path))
    hold(type(old) is dict and old.get('after') == change['before']
         and prior['after']['entries'].get(cid) == proof['before']['entries'][cid]
         and prior['after'] == proof['before']
         and {path: item['after'] for path, item in prior['policies'].items()}
             == {path: item['before'] for path, item in proof['policies'].items()})
    # Recovery preserves these inodes. Original device numbers are retained;
    # no device alias is created or applied to either member or the grant.
    hold(set(prior['policies']) == set(proof['before']['connections'].values()))
    for policy_path, peer in prior['policies'].items():
        hold(type(peer) is dict and set(peer) == {'before', 'after', 'pins'})
        peer_root = safe_path(policy_path).parent
        for key, target, category in (
                ('root', peer_root, 'directories'), ('images', peer_root / 'images', 'directories'),
                ('database', peer_root / 'state.sqlite3', 'files')):
            item = checkpoint[category].get(str(target))
            hold(type(item) is dict and type(peer['pins'].get(key)) is list
                 and len(peer['pins'][key]) == 2 and peer['pins'][key][1] == item['ino'])
        profile = checkpoint['files'].get(str(peer_root / 'profile.json'))
        hold(type(profile) is dict and peer['pins']['profile_sha256'] == profile['sha256'])
    for target, recorded in ((scope.base, prior['registry_parent']),
                             (path.parent, prior['journal_parent'])):
        item = checkpoint['directories'].get(str(target))
        hold(type(item) is dict and type(recorded) is list and len(recorded) == 2
             and all(type(v) is int and v >= 0 for v in recorded) and recorded[1] == item['ino'])
    return prior, meta


def _walk(scope, policy, grant, source):
    entries = source['recoveries']
    outer_entry = entries[0]
    path, meta, proof = _proof(scope, outer_entry['transaction'])
    hold(meta['sha256'] == outer_entry['proof_sha256'] and proof['schema'] == 2)
    cid = policy.data['connection_id']
    expected = proof['policies'][str(policy.path)]['after']
    hold(digest(expected) == outer_entry['after_policy_digest']
         and digest(proof['owner']) == outer_entry['owner_digest']
         and proof['owner'] == owner_value(scope.registry, policy.data['actor']))
    change = _change(scope, policy, proof, expected, proof['after']['entries'][cid])
    hold(digest(change['before']) == outer_entry['before_policy_digest']
         and all(expected[k] == policy.value[k] for k in
                 ('identity', 'policy', 'capabilities', 'duration', 'registry_path', 'owner_digest', 'enabled'))
         and change['pins']['root'] == list(policy.root_pin)
         and change['pins']['images'] == list(policy.image_pin)
         and change['pins']['database'] == list(policy.database_pin[:2])
         and change['pins']['profile_sha256'] == sha256(private_read(policy.root / 'profile.json')[0]).hexdigest())
    visited = {proof['id']}
    original.check_relocation_predecessors(proof, visited)
    validate_relocation_proof(proof, reader=scope.reader)
    outer = _checkpoint(scope, proof, outer_entry)
    _adoption(scope, policy, proof, change, outer, live=True)
    phase = outer
    recoveries_seen = {proof['id']}
    prior, prior_meta = _prior_phase(scope, policy, proof, change, phase, outer, visited)
    expected, expected_entry = change['before'], proof['before']['entries'][cid]
    expected_registry = proof['before']
    expected_policies = {path: item['before'] for path, item in proof['policies'].items()}
    physical = (prior['registry_parent'], prior['journal_parent'],
                {path: item['pins'] for path, item in prior['policies'].items()})
    while True:
        hold(expected['transaction'] not in visited)
        path, meta, proof = _proof(scope, expected['transaction'])
        visited.add(proof['id'])
        _retained(outer, path, meta, phase)
        hold(proof['after'] == expected_registry
             and {path: item['after'] for path, item in proof['policies'].items()} == expected_policies)
        change = _change(scope, policy, proof, expected, expected_entry)
        hold(proof['registry_parent'] == physical[0] and proof['journal_parent'] == physical[1]
             and change['pins'] == physical[2][str(policy.path)])
        if proof['schema'] == 1:
            _schema1_peers(scope, proof, physical[2])
        if proof['schema'] == 1 and grant['root_pin'] == change['pins']['root'] \
                and grant['database_pin'] == change['pins']['database']:
            hold(recoveries_seen == {entry['transaction'] for entry in entries})
            return outer
        if proof['schema'] == 2:
            candidates = [entry for entry in entries[1:] if entry['transaction'] == proof['id']]
            hold(len(candidates) == 1)
            entry = candidates[0]
            hold(proof['id'] not in recoveries_seen)
            recoveries_seen.add(proof['id'])
            hold(meta['sha256'] == entry['proof_sha256']
                 and digest(change['after']) == entry['after_policy_digest']
                 and digest(change['before']) == entry['before_policy_digest']
                 and digest(proof['owner']) == entry['owner_digest'])
            original.check_relocation_predecessors(proof, visited)
            validate_relocation_proof(proof, reader=scope.reader)
            phase = _checkpoint(scope, proof, entry)
            _adoption(scope, policy, proof, change, phase)
            prior, prior_meta = _prior_phase(scope, policy, proof, change, phase, outer, visited)
            physical = (prior['registry_parent'], prior['journal_parent'],
                        {path: item['pins'] for path, item in prior['policies'].items()})
        expected, expected_entry = change['before'], proof['before']['entries'][cid]
        expected_registry = proof['before']
        expected_policies = {path: item['before'] for path, item in proof['policies'].items()}


@contextmanager
def completed_record_identity(w, db, profile, row, intent, result, proof, grant):
    candidates = [source for source in _SOURCES
                  if digest(row['id']) == source['record']['record_id_digest']]
    if not candidates:
        with original.historical_identity(w, profile, grant):
            yield
        return
    hold(len(candidates) == 1)
    source = candidates[0]
    policy = getattr(w, 'policy', None)
    hold(type(policy) is ConnectionPolicy)
    # Constructor history reuses its entered H scope. A runtime status call
    # creates one for its real owned DB; it never edits shared workflow state.
    with history_scope(policy, db, getattr(w, 'history_locators', None)) as scope:
        policy, scope = _current(w, db, profile, row, intent, result, grant, source, scope)
        files = _record_files(scope, policy, row, result, proof, grant, source['record'])
        outer = _walk(scope, policy, grant, source)
        for path, meta, raw in files:
            _retained(outer, path, meta)
        yield
        _current(w, db, profile, row, intent, result, grant, source, scope)
        for path, meta, raw in _record_files(scope, policy, row, result, proof, grant, source['record']):
            _retained(outer, path, meta)
        scope.source.guard()
