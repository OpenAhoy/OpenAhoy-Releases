"""Pinned two-object exception only for the fixed three-case recovery path.

Current admission and immutable evidence have separate validators. Nothing here
creates a grant, deletes a lock, runs a token/API, or accepts caller-chosen keys.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

from .contracts import Actor, WCEError
from .service import canonical, digest
from .own_bootstrap_security import path_check
from . import own_replacement_files as files
from . import own_lineage as lineage

POLICY = 'PINNED_UNRELATED_LOCK_EXCEPTION_V1'
RECEIPT_SHA = 'd5b268362137fcbcd05aaed76226cee8a14f4f64c3c583737853c0fb3089aad7'
RELATION_MODULE_SHA = '6e464e0a2fb09e62dd6198abab9305f5a78d0ef43fdeb6d8e1f9d62afc6aba0a'
RECEIPT_NAME = 'retained-unrelated-locks.json'
_ENTRY = frozenset(('cases','identity','identity_sha','kind','lineage','lock_row','lock_sha',
    'manifest_sha','matrix_sha','observed_policy_sha','observed_scope','ordered_manifest',
    'original_approval','original_approval_sha','original_intent','original_row','original_row_sha',
    'owner_row','owner_row_sha','provider'))
_ROW = frozenset(('approval_digest','approval_id','completed','connection','created','id','intent',
    'intent_digest','manifest_digest','operation','owner','principal','readback','request_key',
    'resource','result','result_digest','slot','state','target','tenant'))
_APPROVAL = frozenset(('binding_fence','body','body_digest','cancelled','connection','expires','id',
    'manifest_digest','principal','resource','tenant'))
_IDENTITY = frozenset(('actor','appid','connection_id','epoch','generation','private_directory','resource_id'))
_PIN_KEYS = ('case_id','identity_sha','policy_sha','manifest_sha','original_row_sha')
_IGNORED_KEYS = ('kind','lock_row','lock_sha','owner_row_sha','original_row_sha','original_approval_sha',
    'manifest_sha','matrix_sha','observed_policy_sha','observed_scope')


def fail(code='OWN_REPLACEMENT_UNRELATED_HOLD'):
    raise WCEError(code)


def exact(value, names):
    if type(value) is not dict or set(value) != set(names): fail()


def hex64(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{64}', value) is None: fail()
    return value


def stored(raw, expected):
    try:
        value = json.loads(raw)
        if canonical(value) != raw or digest(value) != expected: fail()
        return value
    except (TypeError, ValueError):
        fail()


def _registry(registry):
    value = Path(registry)
    if not value.is_absolute() or value.name != 'connections.json' or '..' in value.parts: fail()
    path_check(value.parent, True)
    return value


def _relation():
    # The current batch is approved against this exact existing relation code.
    # A future relation change requires an explicit historical reader decision.
    if lineage.POLICY != 'ARTICLE_LINEAGE_NFKC_V1': fail()
    path = Path(lineage.__file__)
    if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != RELATION_MODULE_SHA: fail()


def _identity(binding, root):
    from .own_workflow import binding_validate
    binding_validate(binding)
    return {'actor': {'tenant_id': binding['tenant'], 'principal_id': binding['principal'],
        'client_id': binding['client'], 'session_id': binding['session']},
        'appid': binding['account'], 'connection_id': binding['connection'],
        'epoch': binding['epoch'], 'generation': binding['generation'],
        'private_directory': root, 'resource_id': binding['resource']}


def _case_groups(cases):
    if type(cases) is not list or len(cases) != 3: fail()
    groups = {}; ids = set(); kinds = set()
    for case in cases:
        if type(case) is not dict: fail()
        try:
            original = case['original']; binding = original['binding']; manifest = case['ordered_manifest']
            identity = _identity(binding, case['root'])
            if (case['identity_sha'] != digest(identity) or case['connection_id'] != identity['connection_id']
                    or case['manifest_sha'] != digest(manifest) or manifest['binding'] != binding
                    or original['lineage']['legacy'] != 0 or binding['account'] != binding['resource']): fail()
            expected = digest({'provider': 'WECHAT_OFFICIAL_ACCOUNT', 'resource': binding['resource'],
                'original_step_id': original['original_step_id'], 'target': original['original_target'],
                'intent_digest': original['original_intent_digest'], 'slot': original['slot'],
                'asset_sha256': original['asset']['sha256']})
            if case['case_id'] != expected or case['case_id'] in ids: fail()
            ids.add(case['case_id']); kinds.add(binding['source_kind'])
            pin = {'case_id': hex64(case['case_id']), 'identity_sha': hex64(case['identity_sha']),
                'policy_sha': hex64(case['policy_sha']), 'manifest_sha': hex64(case['manifest_sha']),
                'original_row_sha': hex64(original['original_row_sha'])}
            item = groups.setdefault(case['connection_id'], {'identity': identity, 'cases': [], 'pins': [],
                'policy_sha': case['policy_sha'], 'root_identity': case['root_identity'],
                'database_identity': case['database_identity']})
            if (identity != item['identity'] or case['policy_sha'] != item['policy_sha']
                    or case['root_identity'] != item['root_identity']
                    or case['database_identity'] != item['database_identity']): fail()
            item['cases'].append(case); item['pins'].append(pin)
        except (KeyError, TypeError, ValueError):
            fail()
    if len(groups) != 2 or len(kinds) != 1 or kinds.pop() not in ('OPERATOR_ATTESTED', 'SYNTHETIC_SETUP'): fail()
    return groups


def _validate_entry(entry):
    exact(entry, _ENTRY)
    row = entry['original_row']; owner = entry['owner_row']; old = entry['ordered_manifest']
    approval = entry['original_approval']; identity = entry['identity']; lock = entry['lock_row']
    exact(row, _ROW); exact(owner, _ROW); exact(approval, _APPROVAL); exact(identity, _IDENTITY)
    for key, value in (('identity_sha', identity), ('lock_sha', lock), ('manifest_sha', old),
        ('matrix_sha', entry['cases']), ('original_approval_sha', approval),
        ('original_row_sha', row), ('owner_row_sha', owner)):
        if digest(value) != hex64(entry[key]): fail()
    hex64(entry['observed_policy_sha']); hex64(entry['observed_scope'])
    intent = stored(row['intent'], row['intent_digest']); body = stored(approval['body'], approval['body_digest'])
    if (intent != entry['original_intent'] or row != owner or row['state'] != 'RESULT_UNKNOWN'
            or row['result'] != '{}' or row['result_digest'] != digest({}) or row['completed'] is not None
            or row['readback'] != 'UNVERIFIED' or row['approval_id'] != approval['id']
            or row['approval_digest'] != approval['body_digest'] or intent['approval_id'] != approval['id']
            or intent['approval_digest'] != approval['body_digest'] or intent['profile_fence'] != approval['binding_fence']
            or old['binding'] != intent['binding'] or body['binding'] != intent['binding']
            or entry['provider'] != 'WECHAT_OFFICIAL_ACCOUNT'
            or identity != _identity(intent['binding'], identity['private_directory'])
            or intent['binding']['account'] != intent['binding']['resource']
            or intent['operation'] != row['operation'] or intent['slot'] != row['slot']
            or any(row[k] != intent['binding'][k] or approval[k] != row[k]
                   for k in ('tenant','principal','connection','resource'))): fail()
    selector = {'bundle_id': old['bundle_id'], 'version': old['version'], 'content_digest': entry['manifest_sha']}
    if (intent['selector'] != selector or row['manifest_digest'] != entry['manifest_sha']
            or approval['manifest_digest'] != entry['manifest_sha']
            or any(body[k] != v for k, v in selector.items()) or body['slots'] != old['assets']
            or row['target'] != digest({'tenant': row['tenant'], 'resource': row['resource'],
                'manifest_digest': entry['manifest_sha'], 'operation': row['operation'], 'slot': row['slot']})): fail()
    lineage_seal = entry['lineage']
    exact(lineage_seal, ('lineage','root_version','normalization_policy','legacy','tenant','resource'))
    if (lineage_seal['normalization_policy'] != lineage.POLICY
            or type(lineage_seal['legacy']) is not int
            or lineage_seal['tenant'] != row['tenant'] or lineage_seal['resource'] != row['resource']): fail()
    if entry['kind'] == 'lineage':
        exact(lock, ('tenant','resource','lineage','owner_id'))
        if row['operation'] != 'cover' or lineage_seal['legacy'] != 0 or lock['lineage'] != lineage_seal['lineage']: fail()
    elif entry['kind'] == 'legacy:step':
        exact(lock, ('tenant','resource','kind','owner_id'))
        if row['operation'] != 'add' or lineage_seal['legacy'] != 1 or lock['kind'] != 'step': fail()
    else: fail()
    if lock['tenant'] != row['tenant'] or lock['resource'] != row['resource'] or lock['owner_id'] != row['id']: fail()
    if type(entry['cases']) is not list or not 1 <= len(entry['cases']) <= 2: fail()
    for case in entry['cases']:
        exact(case, ('case_id','manifest_sha','original_row_sha','related'))
        if case['related'] is not False: fail()
        for name in ('case_id','manifest_sha','original_row_sha'): hex64(case[name])


def _receipt(registry, declared, groups):
    _relation()
    synthetic = all(c['original']['binding']['source_kind'] == 'SYNTHETIC_SETUP'
                    for group in groups.values() for c in group['cases'])
    if declared is None:
        if not synthetic: fail()
        return None
    if declared != RECEIPT_SHA: fail('OWN_REPLACEMENT_UNRELATED_RECEIPT_CHANGED')
    value, observed = files.read(_registry(registry).parent/'lineage-body-replacements'/RECEIPT_NAME)
    if observed != RECEIPT_SHA: fail('OWN_REPLACEMENT_UNRELATED_RECEIPT_CHANGED')
    exact(value, ('schema','relation_policy','relation_module_sha','entries'))
    if (value['schema'] != POLICY or value['relation_policy'] != lineage.POLICY
            or value['relation_module_sha'] != RELATION_MODULE_SHA
            or type(value['entries']) is not list or len(value['entries']) != 2): fail()
    connections = set(); kinds = set()
    try:
        for entry in value['entries']:
            _validate_entry(entry)
            cid = entry['identity']['connection_id']
            if cid in connections or cid not in groups: fail()
            connections.add(cid); kinds.add(entry['kind'])
            group = groups[cid]
            if entry['identity'] != group['identity']: fail()
            matrix = []
            for case in group['cases']:
                related = lineage.related(entry['ordered_manifest'], case['ordered_manifest'])
                if type(related) is not bool or related: fail('OWN_REPLACEMENT_UNRELATED_RELATION_CHANGED')
                matrix.append({'case_id': case['case_id'], 'manifest_sha': case['manifest_sha'],
                    'original_row_sha': case['original']['original_row_sha'], 'related': related})
            if matrix != entry['cases'] or digest(matrix) != entry['matrix_sha']: fail()
    except (KeyError, TypeError, ValueError):
        fail()
    if connections != set(groups) or kinds != {'lineage','legacy:step'}: fail()
    return value


def _context(registry, cases, declared):
    registry = _registry(registry); groups = _case_groups(cases); receipt = _receipt(registry, declared, groups)
    accounts = []
    for cid, group in sorted(groups.items()):
        entries = [] if receipt is None else [e for e in receipt['entries'] if e['identity']['connection_id'] == cid]
        accounts.append({'connection_id': cid, 'identity_sha': digest(group['identity']),
            'policy_sha': group['policy_sha'], 'cases': group['pins'],
            'ignored': [{k: deepcopy(entry[k]) for k in _IGNORED_KEYS} for entry in entries]})
    return {'schema': 1, 'policy': POLICY, 'receipt_sha': declared, 'relation_policy': lineage.POLICY,
        'relation_module_sha': RELATION_MODULE_SHA, 'accounts': accounts}


def build(registry, cases, receipt_sha, *, history_locators=None):
    context = _context(registry, cases, receipt_sha)
    # prepare must catch known drift before asking for a human risk approval.
    manifest = {'registry': str(Path(registry)), 'cases': cases, 'unrelated_context': context,
                'unrelated_context_sha': digest(context)}
    current(registry, manifest, history_locators=history_locators)
    return context


def immutable(registry, manifest):
    try:
        registry = _registry(registry)
        if type(manifest) is not dict or manifest['registry'] != str(registry): fail()
        context = manifest['unrelated_context']
        exact(context, ('schema','policy','receipt_sha','relation_policy','relation_module_sha','accounts'))
        if type(context['schema']) is not int or context['schema'] != 1 or manifest['unrelated_context_sha'] != digest(context): fail()
        expected = _context(registry, manifest['cases'], context['receipt_sha'])
        if context != expected: fail('OWN_REPLACEMENT_UNRELATED_CONTEXT_CHANGED')
        return deepcopy(context)
    except (KeyError, TypeError, ValueError):
        fail()


def _history(db, path, binding, policy):
    from .own_workflow import OwnWorkflow
    p = SimpleNamespace(actor=Actor(binding['tenant'], binding['principal'], binding['client'], binding['session']),
        connection_id=binding['connection'], account_id=binding['account'], resource_id=binding['resource'],
        source_kind=binding['source_kind'], binding=lambda: dict(binding))
    w = object.__new__(OwnWorkflow)
    w.db = SimpleNamespace(path=path, history_policy=policy); w.policy = policy
    return w, p


def _old_current(db, path, policy, entry, *, history_locators=None):
    row = db.execute('SELECT * FROM own_steps WHERE id=?', (entry['original_row']['id'],)).fetchone()
    if row is None or dict(row) != entry['original_row']: fail('OWN_REPLACEMENT_UNRELATED_HISTORY_CHANGED')
    binding = entry['original_intent']['binding']
    w, p = _history(db, path, binding, policy)
    intent, result = w._step(db, p, row, history_locators=history_locators)
    manifest, _ = w._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
    approval = w._approval(db, p, manifest, entry['manifest_sha'], row['approval_id'], active=False)
    if (intent != entry['original_intent'] or result or manifest != entry['ordered_manifest']
            or dict(approval) != entry['original_approval'] or lineage.seal(db, manifest) != entry['lineage']):
        fail('OWN_REPLACEMENT_UNRELATED_HISTORY_CHANGED')


def current(registry, manifest, *, history_locators=None):
    context = immutable(registry, manifest)
    groups = _case_groups(manifest['cases']); receipt = _receipt(registry, context['receipt_sha'], groups)
    # Use the batch authority resolver: the same exact seam used to construct
    # these cases, including its explicit synthetic fixture mapping.
    from .own_replacement_batch import resolve
    from .own_lineage_replacement import schema_check, validate_record
    for cid, group in sorted(groups.items()):
        policy = resolve(cid, Path(registry))
        if policy.fingerprint != group['policy_sha'] or policy.data != group['identity']: fail('OWN_REPLACEMENT_UNRELATED_AUTHORITY_CHANGED')
        path = policy.root/'state.sqlite3'
        if (list(path_check(policy.root, True)) != group['root_identity']
                or list(path_check(path)[:2]) != group['database_identity']): fail()
        with _peer_history_snapshot(policy,path,timeout=2) as (db,peer_history):
            source = db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
            if source is None or source[0] != group['cases'][0]['original']['binding']['source_kind']: fail()
            if db.execute('PRAGMA user_version').fetchone()[0] not in (6, 7, 8, 9): fail()
            # Structural/FK checks only: no OwnStore.check/_resource/validate_all.
            # A same-stack writer may already have fsynced its claim while its
            # new row remains uncommitted and legitimately invisible here.
            schema_check(db, source[0])
            entries = [] if receipt is None else [e for e in receipt['entries'] if e['identity']['connection_id'] == cid]
            for entry in entries: _old_current(db, path, policy, entry, history_locators=peer_history)
            identity = group['identity']; actor = identity['actor']
            actual_lineage = [dict(row) for row in db.execute('SELECT * FROM own_lineage_locks WHERE tenant=? AND resource=?',
                (actor['tenant_id'], identity['resource_id']))]
            expected_own = {}
            for case in group['cases']:
                original = case['original']
                old = db.execute('SELECT * FROM own_steps WHERE id=?', (original['original_step_id'],)).fetchone()
                if old is None or digest(dict(old)) != original['original_row_sha']: fail()
                lock = {'tenant': actor['tenant_id'], 'resource': identity['resource_id'],
                    'lineage': original['lineage']['lineage'], 'owner_id': original['original_step_id']}
                expected_own[lock['owner_id']] = lock
                if lock not in actual_lineage:
                    replacement = db.execute('SELECT * FROM own_lineage_replacements WHERE original_step_id=?', (old['id'],)).fetchone()
                    if replacement is None or replacement['state'] != 'SUCCEEDED': fail('OWN_REPLACEMENT_UNRELATED_LOCKS_CHANGED')
                    # A precise historical validator, never a global claim scan.
                    validate_record(db, replacement, source[0], history_policy=policy, history_locators=peer_history)
            extras = []
            for lock in actual_lineage:
                if lock['owner_id'] in expected_own:
                    if lock != expected_own[lock['owner_id']]: fail()
                else: extras.append(lock)
            expected_extra = [e['lock_row'] for e in entries if e['kind'] == 'lineage']
            actual_legacy = [dict(row) for row in db.execute('SELECT * FROM own_resource_locks WHERE tenant=? AND resource=?',
                (actor['tenant_id'], identity['resource_id']))]
            expected_legacy = [e['lock_row'] for e in entries if e['kind'] == 'legacy:step']
            ordered = lambda rows: sorted(canonical(row) for row in rows)
            if ordered(extras) != ordered(expected_extra) or ordered(actual_legacy) != ordered(expected_legacy):
                fail('OWN_REPLACEMENT_UNRELATED_LOCKS_CHANGED')
            if list(path_check(path)[:2]) != group['database_identity']: fail()
        policy.check()
    return context


def allowed(manifest, connection_id, kind):
    if kind not in ('lineage', 'legacy:step'): fail()
    context = immutable(manifest['registry'], manifest)
    account = next((a for a in context['accounts'] if a['connection_id'] == connection_id), None)
    if account is None: fail()
    return tuple(deepcopy(entry['lock_row']) for entry in account['ignored'] if entry['kind'] == kind)


from .draft_group_history_context import readonly_history_snapshot as _peer_history_snapshot
