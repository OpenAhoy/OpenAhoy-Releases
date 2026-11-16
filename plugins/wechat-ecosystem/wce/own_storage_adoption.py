"""Review existing two-account state before confirming a local volume witness."""
from contextlib import ExitStack, closing
from collections import Counter
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import re

from .own_connection_policy import load_policy, read_registry, registry_path
from .own_connection_registry import inspect_storage_binding, metadata, transaction_path
from .own_history_source import CHECKPOINT_DIRECTORY, checkpoint, owned_connection
from .own_identity_checkpoint import Reader, case_identifier, require, existing_lock, check_locks
from .own_identity_recovery import atomic_raw, raw_json, validate_relocation_proof
from .own_volume_identity import ADOPTION_FILE, directory_volume, read_adoption, verify_confirmation
from .service import digest

ARCHIVED_CASE = ('Developer/OpenAhoy Operations/_local/work/'
                 'OA-ISSUE04-handoff/recovery-0657/case-state')


def _original_checkpoint(registry, relocation):
    checksum = relocation['checkpoint_sha256']
    name = case_identifier(registry, checksum)
    require(name == relocation['case_id'], 'SOURCE_UNVERIFIED')
    expected = registry.parent / CHECKPOINT_DIRECTORY / (name + '.json')
    if os.path.lexists(expected):
        source = expected
    else:
        require(registry == registry_path(), 'SOURCE_UNVERIFIED')
        source = Path.home() / ARCHIVED_CASE / 'checkpoint.json'
    info, raw = Reader(source.parent).read(source, keep=True)
    require(info['sha256'] == checksum, 'SOURCE_UNVERIFIED')
    data = checkpoint(raw, registry)
    require(digest({'files': data['files'], 'members': data['members']}) ==
            relocation['preservation_digest'], 'SOURCE_UNVERIFIED')
    return data, raw, expected


def _observed(current, saved, olddev, newdev):
    return (type(saved) is dict and saved.get('dev') == olddev and current.get('dev') == newdev
            and current == saved | {'dev': newdev})


def _preserved_main(registry, current, expected, current_meta):
    """Require the original captured receipt rows, then allow valid later rows."""
    require(registry == registry_path(),'SOURCE_UNVERIFIED')
    backup = Path.home() / ARCHIVED_CASE / 'backup'
    original = backup / current.relative_to(registry.parent)
    reader = Reader(backup)
    old, original_bytes = reader.read(original,keep=True)
    require(type(expected) is dict and old['sha256'] == expected['sha256'],
            'SOURCE_UNVERIFIED')
    # The SQL view must read precisely the bytes already checked against the
    # original receipt, even if the backup is replaced between these steps.
    with closing(sqlite3.connect(':memory:')) as prior, \
            owned_connection(current,readonly=True,timeout=0,isolation_level=None) as live:
        prior.deserialize(original_bytes)
        for db in (prior,live):
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            require(db.execute('PRAGMA quick_check').fetchall()==[('ok',)],'SOURCE_UNVERIFIED')
        names = [row[0] for row in prior.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'own_*' ORDER BY name")]
        require(bool(names) and 'own_steps' in names and 'own_inputs' in names,'SOURCE_UNVERIFIED')
        live.execute('BEGIN')
        for name in names:
            require(re.fullmatch(r'own_[a-z0-9_]+',name) is not None,'SOURCE_UNVERIFIED')
            query = 'SELECT * FROM "'+name+'"'
            earlier = Counter(prior.execute(query))
            later = Counter(live.execute(query))
            require(not earlier-later,'HISTORICAL_RECEIPT_CHANGED')
        live.rollback()
    require(reader.read(original)[0] == old and Reader(registry.parent).read(current)[0] == current_meta,
            'STATE_CHANGED')


def review(registry):
    from .own_account_metadata import metadata_bytes
    from .draft_revision_guard import policy_binding
    from .draft_revision_store import RevisionStore, ZERO, DDL, APP_ID

    registry = Path(registry)
    reg = read_registry(registry)
    require(reg['schema'] == 2 and len(reg['connections']) == 2, 'SOURCE_UNVERIFIED')
    volume, root_pin = directory_volume(registry.parent)
    require(volume is not None, 'SOURCE_UNVERIFIED')
    by_schema = {}
    for cid, path in reg['connections'].items():
        require(inspect_storage_binding(registry, cid) == 'CONSISTENT_DEVICE_REMAP_UNPROVEN',
                'SOURCE_UNVERIFIED')
        policy = load_policy(path, active=False)
        proof_path = transaction_path(registry, policy.value['transaction'])
        proof = metadata(proof_path)
        require(proof['schema'] not in by_schema, 'SOURCE_UNVERIFIED')
        by_schema[proof['schema']] = (cid, policy, proof_path, proof)
    require(set(by_schema) == {1, 2}, 'SOURCE_UNVERIFIED')
    first, first_policy, _, earlier = by_schema[2]
    newer, newer_policy, _, later = by_schema[1]
    validate_relocation_proof(earlier)
    require(later['policies'][str(newer_policy.path)]['before'] is None
            and newer_policy.value['revision'] == 1
            and later['before'] == earlier['after']
            and set(earlier['after']['connections']) == {first}
            and later['after'] == reg, 'SOURCE_UNVERIFIED')
    data, raw, target = _original_checkpoint(registry, earlier['relocation'])
    olddev = earlier['registry_parent'][0]
    newdev = root_pin[0]
    require(later['registry_parent'] == earlier['registry_parent']
            and [olddev, root_pin[1]] == earlier['registry_parent'], 'SOURCE_UNVERIFIED')
    reader = Reader(registry.parent)
    revisions, proofs, original_apps, guard_facts = {}, {}, [], []
    for cid, policy, proof_path, proof in by_schema.values():
        require(proof['owner'] == earlier['owner'], 'SOURCE_UNVERIFIED')
        current = proof['policies'][str(policy.path)]['pins']
        for key, path, directory in [('root',policy.root,True), ('images',policy.root/'images',True),
                                     ('database',policy.root/'state.sqlite3',False)]:
            saved_meta = data['directories' if directory else 'files'].get(str(path))
            require(type(saved_meta) is dict and
                    [saved_meta['dev'], saved_meta['ino']] == current[key], 'SOURCE_UNVERIFIED')
        profile = policy.root / 'profile.json'
        meta, _ = reader.read(profile)
        require(_observed(meta,data['files'].get(str(profile)),olddev,newdev), 'SOURCE_UNVERIFIED')
        require(meta['sha256'] == current['profile_sha256'], 'SOURCE_UNVERIFIED')
        store = RevisionStore(policy.root, digest(policy_binding(policy,'OPERATOR_ATTESTED')), lambda: True)
        anchor, fixed = store._head()
        require(anchor['seq'] == anchor['confirmed_seq'] == 0 and anchor['event_sha'] == ZERO,
                'SOURCE_UNVERIFIED')
        for path in (store.anchor, store.path):
            seen, _ = reader.read(path)
            require(_observed(seen,data['files'].get(str(path)),olddev,newdev), 'SOURCE_UNVERIFIED')
        for path in (store.root, store.root/'proofs', store.root/'events'):
            current_volume, pin = directory_volume(path)
            require(current_volume == volume and data['directories'][str(path)]['dev'] == olddev
                    and data['directories'][str(path)]['ino'] == pin[1], 'SOURCE_UNVERIFIED')
            if path != store.root:
                require(data['members'][str(path)] == [] and not list(path.iterdir()), 'SOURCE_UNVERIFIED')
        prior_root = data['directories'][str(store.root)]
        prior_db = data['files'][str(store.path)]
        predecessor_dev = metadata(transaction_path(
            registry, earlier['policies'][str(first_policy.path)]['before']['transaction']))['registry_parent'][0]
        require(anchor['root'] == [predecessor_dev,prior_root['ino']]
                and anchor['database'] == [predecessor_dev,prior_db['ino']], 'SOURCE_UNVERIFIED')
        with owned_connection(store.path, readonly=True, timeout=0, isolation_level=None,
                              _revision_header=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            require(db.execute('PRAGMA application_id').fetchone()[0] == APP_ID
                    and db.execute('PRAGMA user_version').fetchone()[0] in (4,5)
                    and tuple(row[0] for row in db.execute(
                        "SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql")) ==
                        tuple(sorted(DDL)), 'SOURCE_UNVERIFIED')
            db.execute('BEGIN')
            store._verify(db,anchor)
            db.rollback()
        main_path = policy.root/'state.sqlite3'
        main, _ = reader.read(main_path)
        _preserved_main(registry,main_path,data['files'].get(str(main_path)),main)
        policy_raw = metadata_bytes(policy.path)[0]
        guard_facts.append((cid, main, policy_raw, fixed))
        proofs[proof['id']] = digest(proof)
        revisions[str(store.root)] = {'schema':1,'volume':volume,'binding':anchor['binding'],
                                      'root':anchor['root'],'database':anchor['database']}
        original_apps.append(policy.data['appid'])
    value = {'schema':1,'volume':volume,'proofs':proofs,'revisions':revisions,
             'review':digest({'registry':reg,'observed':guard_facts,
                              'checkpoint_sha256': sha256(raw).hexdigest()})}
    return value, raw, target, sorted(original_apps)


def apply_reviewed(registry, reviewed):
    from .own_connection_registry import container

    value, raw, target, _ = reviewed
    verify_confirmation(digest(value))
    roots = sorted({Path(p).parent for p in read_registry(registry)['connections'].values()})
    held = []
    with ExitStack() as stack:
        paths = [registry.parent/'connection-setup.lock']
        for root in roots:
            paths.extend(root/name for name in ('connection-start.lock','connection.lock'))
        for root in roots:
            paths.extend(root/name for name in ('connection-import.lock','connection-token.lock',
                'cover-read-authority.lock','presentation.lock','publication-settings-ops.lock',
                'publication-dispatch.lock') if os.path.lexists(root/name))
            paths.append(root/'draft-revision-journal.lock')
        paths.extend(root/'connection-policy.lock' for root in roots)
        paths.append(registry.parent/'connections.lock')
        for path in paths:
            stack.enter_context(existing_lock(path,held))
        def boundary():
            check_locks(held)
            for root in roots:
                require(not any(os.path.lexists(str(root/db)+ext)
                                for db in ('state.sqlite3','draft-revisions/revision.sqlite3',
                                           'current-draft-management/operations.sqlite3')
                                for ext in ('-wal','-shm','-journal')), 'STATE_CHANGED')
            require(review(registry) == reviewed, 'STATE_CHANGED')
            check_locks(held)
        if read_adoption(registry.parent) == value:
            return
        require(read_adoption(registry.parent) is None, 'STATE_CHANGED')
        boundary()
        container(registry.parent,CHECKPOINT_DIRECTORY)
        if os.path.lexists(target):
            _, current = Reader(target.parent).read(target,keep=True)
            require(current == raw, 'STATE_CHANGED')
        else:
            atomic_raw(target,raw,None,exclusive=True)
        atomic_raw(registry.parent/ADOPTION_FILE,raw_json(value),None,exclusive=True,final_check=boundary)
    for path in read_registry(registry)['connections'].values():
        load_policy(path,active=False).check(readonly=True)


def verify_adopted(registry):
    from .draft_revision_guard import policy_binding
    from .draft_revision_store import RevisionStore
    from .own_selected_history import readonly_prepared_history

    adopted = read_adoption(registry.parent)
    require(adopted is not None, 'SOURCE_UNVERIFIED')
    for path in read_registry(registry)['connections'].values():
        policy=load_policy(path,active=False)
        policy.check(readonly=True)
        store=RevisionStore(policy.root,digest(policy_binding(policy,'OPERATOR_ATTESTED')),
                            lambda:policy.check(readonly=True))
        store.guard_targets_readonly(policy,[])
        with readonly_prepared_history(policy) as history:
            history.check()
