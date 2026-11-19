"""Settings-only, exact-object read authority. No secret or model grant route.

These private records use the existing local host trust model, not a claimed
cryptographic signature. Hashes bind immutable records; they do not authenticate
arbitrary files supplied by a caller. All names are derived below, never input.
"""
from .own_history_source import owned_connection
from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from types import SimpleNamespace
from uuid import uuid4

from .contracts import Actor, WCEError
from .own_auth import READ_APIS
from .own_bootstrap_security import path_check, private_read, decode
from .own_connection_policy import load_policy, locked
from .own_connection_enrollment import exclusive
from .own_workflow import OwnWorkflow, stored, encoded
from .own_store import OwnStore
from .own_png import MAX_INPUT, policy as png_policy
from .own_lineage import seal
from .service import digest

AUTHORITY = 'HUMAN_SCOPED_PERSISTENT_COVER_READ_V1'
JPEG_ORIGIN = 'OFFICIAL_JPEG_BYTES_READ_MATCH'
BUDGET = {'list': 1000, 'image': 5, 'total': 1005, 'writes': 0,
          'max_materials': 10000, 'max_candidates': 4, 'max_workers': 8}
MAX_SECONDS, START_SECONDS = 300, 900
GRANT_ID = re.compile(r'cover-read-[a-f0-9]{32}')


def _grant_policy(mime):
    if mime == 'image/png':
        return {'schema': 1, 'pixel_policy': png_policy()}
    if mime == 'image/jpeg':
        return {'schema': 2, 'match_policy': jpeg_policy()}
    raise WCEError('COVER_READ_AUTHORITY_INVALID')


def jpeg_policy():
    return {'id': 'JPEG_TRANSPORT_EXACT_V1', 'max_input_bytes': MAX_INPUT,
        'comparison': 'ALL_ORIGINAL_TRANSPORT_BYTES'}


def filename(identifier, claimed=False):
    if type(identifier) is not str or GRANT_ID.fullmatch(identifier) is None:
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    return ('cover-read-claimed-' if claimed else 'cover-read-grant-') + identifier + '.json'


def historical_profile(policy):
    data, actor = policy.data, policy.actor
    binding = {'tenant': actor.tenant_id, 'principal': actor.principal_id,
        'client': actor.client_id, 'session': actor.session_id,
        'connection': data['connection_id'], 'account': data['appid'],
        'resource': data['resource_id'], 'generation': data['generation'],
        'epoch': data['epoch'], 'source_kind': 'OPERATOR_ATTESTED'}
    return SimpleNamespace(actor=actor, connection_id=data['connection_id'],
        account_id=data['appid'], resource_id=data['resource_id'],
        source_kind='OPERATOR_ATTESTED', binding=lambda: dict(binding))


@contextmanager
def inspect(policy):
    """Existing records only: no migration, resource insert, lease or provider."""
    policy.check(candidate=False)
    path = policy.root / 'state.sqlite3'
    before = path_check(path)
    if any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise WCEError('COVER_READ_DATABASE_BUSY')
    with owned_connection(path, readonly=True, timeout=2, isolation_level='') as db, _history_scope(policy,db) as history_locators:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA temp_store=MEMORY'); db.execute('BEGIN')
        stop = time.monotonic() + 10
        db.set_progress_handler(lambda: int(time.monotonic() >= stop), 1000)
        if db.execute('PRAGMA user_version').fetchone()[0] not in (5, 6, 7, 8, 9):
            raise WCEError('COVER_READ_DATABASE_UNSUPPORTED')
        OwnStore.check(db, 'OPERATOR_ATTESTED', history_policy=policy, history=history_locators)
        workflow = object.__new__(OwnWorkflow)
        workflow.db = SimpleNamespace(path=path)
        yield workflow, db, historical_profile(policy)
        policy.check(candidate=False)
        if before != path_check(path):
            raise WCEError('COVER_READ_SNAPSHOT_CHANGED')


def target(workflow, db, profile, row, intent):
    """Stable original identity, usable before and after the single recovery CAS."""
    m, d = workflow._bundle(db, profile, intent['selector']['bundle_id'], intent['selector']['version'])
    approval = workflow._approval(db, profile, m, d, row['approval_id'], False)
    slot, asset = row['slot'], intent['asset']
    if (stored(approval['body'], approval['body_digest'])['schema'] != 7
            or row['operation'] != 'cover' or type(asset) is not dict
            or asset.get('role') != 'cover' or asset.get('slot') != slot
            or asset.get('declared_type') not in ('image/png', 'image/jpeg')):
        raise WCEError('COVER_READ_TARGET_UNSUPPORTED')
    if m['schema'] == 1:
        article = m['article'] if slot == 'cover' else None
    else:
        article = next((a for a in m['document']['articles'] if a['id'] + '--cover' == slot), None)
    if article is None or article['cover_asset_ref'] != asset['asset_ref']:
        raise WCEError('COVER_READ_TARGET_UNSUPPORTED')
    lineage = seal(db, m)
    if lineage['legacy'] != 0:
        raise WCEError('COVER_READ_TARGET_UNSUPPORTED')
    from .own_diagnostics import read
    original = dict(row)
    original.update(state='RESULT_UNKNOWN', result='{}', result_digest=digest({}),
                    completed=None, readback='UNVERIFIED')
    return {'request_key': row['request_key'], 'attempt_id': row['id'],
        'original_row_digest': digest(original), 'original_intent_digest': row['intent_digest'],
        'original_approval_id': row['approval_id'], 'original_approval_digest': row['approval_digest'],
        'owner': row['owner'], 'target': row['target'], 'created': row['created'],
        'selector': intent['selector'], 'asset': intent['asset'], 'lineage': lineage,
        'diagnostic_digest': digest(read(db, row)), 'title': article['title']}


def unknown(workflow, db, profile, key, *, history_locators=None):
    row = workflow._history(db, profile, key, history_locators=history_locators)
    if row is None:
        raise WCEError('OWN_STEP_NOT_FOUND')
    intent, result = workflow._step(db, profile, row, history_locators=history_locators)
    if row['state'] != 'RESULT_UNKNOWN' or result:
        raise WCEError('OWN_RECONCILE_NOT_UNKNOWN')
    value = target(workflow, db, profile, row, intent)
    lock = db.execute('SELECT owner_id FROM own_lineage_locks WHERE tenant=? AND resource=? AND lineage=?',
        (profile.actor.tenant_id, profile.resource_id, value['lineage']['lineage'])).fetchone()
    if lock is None or lock['owner_id'] != row['id']:
        raise WCEError('OWN_LINEAGE_CORRUPT')
    return dict(row), intent, value


def candidates(registry, *, history_locators=None):
    from .own_connection_policy import read_registry
    data = read_registry(registry)
    result = []
    for cid, path in data['connections'].items():
        p = load_policy(path, active=False)
        if not p.value['enabled']:
            continue
        with inspect(p) as (w, db, profile):
            rows = db.execute("SELECT * FROM own_steps WHERE state='RESULT_UNKNOWN' AND operation='cover' ORDER BY created DESC LIMIT 33").fetchall()
            if len(rows) > 32:
                raise WCEError('COVER_READ_TARGET_LIMIT')
            for row in rows:
                intent, _ = w._step(db, profile, row, history_locators=history_locators)
                try:
                    _, _, original = unknown(w, db, profile, row['request_key'], history_locators=history_locators)
                except WCEError as error:
                    if error.code == 'COVER_READ_TARGET_UNSUPPORTED':
                        continue
                    raise
                entries = grants(p.root)
                consumed = sum(int(g['target']['request_key'] == row['request_key'] and
                    os.path.lexists(p.root / filename(g['id'], True))) for g, _, _ in entries)
                result.append({'connection_id': cid, 'request_key': row['request_key'],
                    'label': data.get('entries', {}).get(cid, {}).get('label', cid),
                    'title': original['title'], 'prior_read_attempts': consumed})
    return result


def validate_grant(value):
    keys = {'authority', 'id', 'transaction', 'binding', 'policy', 'root_pin',
        'database_pin', 'target', 'apis', 'budget', 'confirmed_at',
        'expires_at', 'maximum_execution_seconds'}
    if type(value) is not dict or type(value.get('target')) is not dict or type(value['target'].get('asset')) is not dict:
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    policy_fields = _grant_policy(value['target']['asset'].get('declared_type'))
    if (set(value) != keys | set(policy_fields) or value['authority'] != AUTHORITY
            or encoded(value['budget']) != encoded(BUDGET) or value['apis'] != list(READ_APIS)
            or encoded({key: value[key] for key in policy_fields}) != encoded(policy_fields)
            or type(value['maximum_execution_seconds']) is not int
            or value['maximum_execution_seconds'] != MAX_SECONDS):
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    filename(value['id'])
    from .prepared_contracts import ID, DIGEST, strict_validate
    from .own_workflow import binding_validate
    strict_validate(value['transaction'], ID); binding_validate(value['binding'])
    policy = value['policy']
    if type(policy) is not dict or set(policy) != {'id', 'revision', 'policy_digest', 'candidate_scope'}:
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    strict_validate(policy['id'], ID)
    if type(policy['revision']) is not int or policy['revision'] < 1:
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    for k in ('policy_digest', 'candidate_scope'): strict_validate(policy[k], DIGEST)
    for k in ('root_pin', 'database_pin'):
        if type(value[k]) is not list or len(value[k]) != 2 or any(type(v) is not int or v < 0 for v in value[k]):
            raise WCEError('COVER_READ_AUTHORITY_INVALID')
    start, end = value['confirmed_at'], value['expires_at']
    if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end) or not 0 < start < end
            or end - start > START_SECONDS):
        raise WCEError('COVER_READ_AUTHORITY_INVALID')
    return value


def grants(root):
    names = []
    with os.scandir(root) as entries:
        for n, entry in enumerate(entries):
            if n >= 2048: raise WCEError('COVER_READ_METADATA_LIMIT')
            if entry.name.startswith('cover-read-grant-'):
                names.append(entry.name)
    if len(names) > 64: raise WCEError('COVER_READ_METADATA_LIMIT')
    result = []
    for name in sorted(names):
        raw, pin = private_read(root / name)
        value = validate_grant(decode(raw))
        if filename(value['id']) != name or (encoded(value) + '\n').encode() != raw:
            raise WCEError('COVER_READ_AUTHORITY_INVALID')
        result.append((value, sha256(raw).hexdigest(), pin))
    return result


def proposal(policy, key, *, history_locators=None):
    with inspect(policy) as (w, db, p):
        _, _, value = unknown(w, db, p, key, history_locators=history_locators)
        return {'binding': p.binding(), 'root_pin': list(policy.root_pin),
            'database_pin': list(policy.database_pin[:2]), 'target': value,
            'prior_read_attempts': sum(int(g['target'].get('request_key') == key and
                os.path.lexists(policy.root / filename(g['id'], True))) for g, _, _ in grants(policy.root))}


def publish(policy, reviewed, transaction, confirmed_at, *, history_locators=None):
    """Only SettingsBackend.execute after its fresh human admission calls this."""
    policy.check()
    if encoded(proposal(policy, reviewed['target']['request_key'], history_locators=history_locators)) != encoded(reviewed):
        raise WCEError('COVER_READ_SNAPSHOT_CHANGED')
    with locked(policy.root / 'cover-read-authority.lock', nonblocking=True):
        if len(grants(policy.root)) >= 64: raise WCEError('COVER_READ_METADATA_LIMIT')
        identifier = 'cover-read-' + uuid4().hex
        value = {'authority': AUTHORITY, 'id': identifier,
            'transaction': transaction, 'binding': reviewed['binding'],
            'policy': policy.delegation(), 'root_pin': reviewed['root_pin'],
            'database_pin': reviewed['database_pin'], 'target': reviewed['target'],
            'apis': list(READ_APIS), 'budget': BUDGET,
            'confirmed_at': confirmed_at, 'expires_at': confirmed_at + START_SECONDS,
            'maximum_execution_seconds': MAX_SECONDS} | _grant_policy(reviewed['target']['asset']['declared_type'])
        validate_grant(value)
        policy.check()
        exclusive(policy.root / filename(identifier), value, policy.root_pin)
        policy.check()
        return identifier


def active(policy, original, now):
    policy.check()
    found = []
    for value, checksum, pin in grants(policy.root):
        if (encoded(value['target']) != encoded(original)
                or encoded(value['binding']) != encoded(historical_profile(policy).binding())):
            continue
        if value['policy'] != policy.delegation():
            continue
        if value['root_pin'] != list(policy.root_pin) or value['database_pin'] != list(policy.database_pin[:2]):
            raise WCEError('COVER_READ_AUTHORITY_INVALID')
        if not value['confirmed_at'] <= now < value['expires_at']:
            continue
        if not os.path.lexists(policy.root / filename(value['id'], True)):
            found.append((value, checksum, pin))
    if len(found) != 1:
        raise WCEError('COVER_READ_REVIEW_REQUIRED' if not found else 'COVER_READ_AUTHORITY_AMBIGUOUS')
    return found[0]


def claim(policy, grant, checksum, now):
    """Consume the whole one-shot budget before token acquisition or first read."""
    value = {'schema': 1, 'authority': AUTHORITY, 'grant_id': grant['id'],
        'grant_sha256': checksum, 'activated_at': now, 'maximum_execution_seconds': MAX_SECONDS}
    policy.check()
    with locked(policy.root / 'cover-read-authority.lock', nonblocking=True):
        if active(policy, grant['target'], now)[:2] != (grant, checksum):
            raise WCEError('COVER_READ_AUTHORITY_CHANGED')
        exclusive(policy.root / filename(grant['id'], True), value, policy.root_pin)
    policy.check()
    return value


from .draft_group_history_context import locator_scope as _history_scope
