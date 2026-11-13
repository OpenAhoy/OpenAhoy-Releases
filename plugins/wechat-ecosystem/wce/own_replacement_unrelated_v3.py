"""Sealed complete retained-lock evidence for the fixed two-case recovery path.

Current admission and immutable evidence have separate validators. Nothing here
creates a grant, deletes a lock, runs a token/API, or accepts caller-chosen keys.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

from .contracts import Actor, WCEError
from .service import canonical, digest
from .own_bootstrap_security import path_check
from . import own_replacement_files as files
from . import own_lineage as lineage
from .own_validation_scope import OwnedConnection, content_scope

POLICY = 'PINNED_UNRELATED_LOCK_EXCEPTION_V3'
RELATION_MODULE_SHA = '6e464e0a2fb09e62dd6198abab9305f5a78d0ef43fdeb6d8e1f9d62afc6aba0a'
RECEIPT_PREFIX = 'retained-unrelated-locks-v3-'
_ENTRY = frozenset(('cases','identity','identity_sha','kind','lineage','lock_row','lock_sha',
    'manifest_sha','matrix_sha','observed_policy_sha','observed_scope','ordered_manifest',
    'original_approval','original_approval_sha','original_intent','original_row','original_row_sha',
    'owner_row','owner_row_sha','provider'))
_ADD_ENTRY = _ENTRY | frozenset(('media_dependencies', 'media_dependencies_sha'))
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
    from . import own_replacement_contract as contract
    if type(cases) is not list or len(cases) != 2: fail()
    contract.validate_r2_cases(cases)
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
    try:
        return _validate_entry_checked(entry)
    except (KeyError, TypeError, ValueError, AttributeError):
        fail()


def _validate_entry_checked(entry):
    if type(entry) is not dict or type(entry.get('original_row')) is not dict: fail()
    is_add = entry.get('kind') == 'lineage' and entry['original_row'].get('operation') == 'add'
    exact(entry, _ADD_ENTRY if is_add else _ENTRY)
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
    if row['operation'] in ('cover', 'body'):
        assets = old.get('assets')
        if type(assets) is not list: fail()
        matches = [asset for asset in assets if type(asset) is dict and asset.get('slot') == row['slot']]
        if (len(matches) != 1 or intent.get('asset') != matches[0]
                or matches[0].get('role') != row['operation']
                or intent.get('projection') is not None or intent.get('uploads') != []): fail()
    lineage_seal = entry['lineage']
    exact(lineage_seal, ('lineage','root_version','normalization_policy','legacy','tenant','resource'))
    if (lineage_seal['normalization_policy'] != lineage.POLICY
            or type(lineage_seal['legacy']) is not int
            or lineage_seal['tenant'] != row['tenant'] or lineage_seal['resource'] != row['resource']): fail()
    if entry['kind'] == 'lineage':
        exact(lock, ('tenant','resource','lineage','owner_id'))
        if row['operation'] not in ('cover', 'body', 'add') or lineage_seal['legacy'] != 0 or lock['lineage'] != lineage_seal['lineage']: fail()
    elif entry['kind'] == 'legacy:step':
        exact(lock, ('tenant','resource','kind','owner_id'))
        if row['operation'] != 'add' or lineage_seal['legacy'] != 1 or lock['kind'] != 'step': fail()
    else: fail()
    if is_add:
        from . import own_replacement_media_leaves as media
        if (entry['kind'] != 'lineage' or row['slot'] != 'draft' or intent.get('asset') is not None
                or digest(entry['media_dependencies']) != hex64(entry['media_dependencies_sha'])): fail()
        media.validate_add(intent['binding'], old, entry['manifest_sha'], row, intent,
                           approval, lineage_seal, entry['media_dependencies'])
    if lock['tenant'] != row['tenant'] or lock['resource'] != row['resource'] or lock['owner_id'] != row['id']: fail()
    if type(entry['cases']) is not list or not 1 <= len(entry['cases']) <= 2: fail()
    for case in entry['cases']:
        exact(case, ('case_id','manifest_sha','original_row_sha','related'))
        if case['related'] is not False: fail()
        for name in ('case_id','manifest_sha','original_row_sha'): hex64(case[name])


def _v2_observation(registry):
    from . import own_replacement_unrelated_v2 as v2, own_replacement_contract as contract
    base = _registry(registry).parent/'lineage-body-replacements'
    names = [p.name for p in base.iterdir() if p.name.startswith(v2.RECEIPT_PREFIX)]
    if len(names) > 1: fail('OWN_R3_PREDECESSOR_CHANGED')
    planpath = base/'proposal-r2.json'
    if not names:
        if os.path.lexists(planpath): fail('OWN_R3_PREDECESSOR_CHANGED')
        return {'state':'ABSENT','contract_sha':contract.R2_CONTRACT_SHA,'receipt_sha':None,'proposal_sha':None}
    name=names[0]; pattern=re.escape(v2.RECEIPT_PREFIX)+r'([a-f0-9]{64})\.json'
    match=re.fullmatch(pattern,name)
    if not match: fail('OWN_R3_PREDECESSOR_CHANGED')
    _, checksum=files.read(base/name)
    if checksum!=match.group(1): fail('OWN_R3_PREDECESSOR_CHANGED')
    proposal_sha = None
    if os.path.lexists(planpath):
        plan,proposal_sha=files.read(planpath)
        keys={'schema','registry','candidate_scope','contract_sha','targets','unrelated_receipt_sha'}
        if (type(plan) is not dict or set(plan) not in (keys,keys|{'preview_receipt_sha'})
                or type(plan['schema']) is not int or plan['schema']!=3
                or plan['registry']!=str(registry) or plan['contract_sha']!=contract.R2_CONTRACT_SHA
                or plan['unrelated_receipt_sha']!=checksum or type(plan['targets']) is not list
                or len(plan['targets'])!=2): fail('OWN_R3_PREDECESSOR_CHANGED')
        hex64(plan['candidate_scope'])
        from .own_replacement_prepare_r2 import _prior
        old=_prior(registry)
        if plan['targets']!=old['targets'][1:] or plan.get('preview_receipt_sha')!=old.get('preview_receipt_sha'):
            fail('OWN_R3_PREDECESSOR_CHANGED')
    return {'state':'PRESENT','contract_sha':contract.R2_CONTRACT_SHA,'receipt_sha':checksum,'proposal_sha':proposal_sha}


def _verify_receipt(registry, receipt, groups):
    try:
        return _verify_receipt_checked(registry,receipt,groups)
    except (KeyError, TypeError, ValueError, AttributeError):
        fail()


def _verify_receipt_checked(registry, receipt, groups):
    from . import own_replacement_unrelated as v1, own_replacement_unrelated_v2 as v2
    from . import own_replacement_contract as contract
    _relation()
    base=_registry(registry).parent/'lineage-body-replacements'
    prior,prior_sha=files.read(base/v1.RECEIPT_NAME)
    if prior_sha!=v1.RECEIPT_SHA: fail('OWN_REPLACEMENT_UNRELATED_RECEIPT_CHANGED')
    exact(prior,('schema','relation_policy','relation_module_sha','entries'))
    if (prior['schema']!=v1.POLICY or prior['relation_policy']!=lineage.POLICY
            or prior['relation_module_sha']!=RELATION_MODULE_SHA or type(prior['entries']) is not list
            or len(prior['entries'])!=2): fail()
    for item in prior['entries']: v1._validate_entry(item)
    exact(receipt,('schema','relation_policy','relation_module_sha','predecessor_receipt_sha','v2_predecessor','entries'))
    pred=receipt['v2_predecessor'];exact(pred,('state','contract_sha','receipt_sha','proposal_sha'))
    if (receipt['schema']!=POLICY or receipt['relation_policy']!=lineage.POLICY
            or receipt['relation_module_sha']!=RELATION_MODULE_SHA or receipt['predecessor_receipt_sha']!=prior_sha
            or pred['contract_sha']!=contract.R2_CONTRACT_SHA or pred['state'] not in ('ABSENT','PRESENT')
            or type(receipt['entries']) is not list or len(receipt['entries'])!=5): fail()
    if pred['state']=='ABSENT':
        if pred['receipt_sha'] is not None or pred['proposal_sha'] is not None: fail()
        prior2=None
    else:
        hex64(pred['receipt_sha'])
        if pred['proposal_sha'] is not None:
            hex64(pred['proposal_sha'])
            proposal,proposal_sha=files.read(base/'proposal-r2.json')
            if proposal_sha!=pred['proposal_sha']: fail('OWN_R3_PREDECESSOR_CHANGED')
            hex64(proposal['candidate_scope'])
            from .own_replacement_prepare_r2 import _prior
            old=_prior(registry)
            fields={'schema','registry','candidate_scope','contract_sha','targets','unrelated_receipt_sha'}
            if (type(proposal) is not dict or set(proposal) not in (fields,fields|{'preview_receipt_sha'})
                    or type(proposal['schema']) is not int or proposal['schema']!=3
                    or proposal['registry']!=str(registry) or proposal['contract_sha']!=contract.R2_CONTRACT_SHA
                    or proposal['unrelated_receipt_sha']!=pred['receipt_sha']
                    or proposal['targets']!=old['targets'][1:]
                    or proposal.get('preview_receipt_sha')!=old.get('preview_receipt_sha')): fail()
        prior2=v2._receipt(registry,pred['receipt_sha'],groups)
    def static(entry): return {k:v for k,v in entry.items() if k not in ('cases','matrix_sha')}
    prior_by_id={entry['original_row']['id']:static(entry) for entry in prior['entries']}
    if len(prior_by_id)!=2: fail()
    if prior2 is not None:
        prev_by_id={entry['original_row']['id']:static(entry) for entry in prior2['entries']}
        if len(prev_by_id)!=3: fail()
    expected_add={x['step_id']:x for x in contract.R3_ADDITIONAL_STEPS}
    if len(expected_add)!=2: fail()
    seen=set();seen_prior=set();found_excluded=False;found_add=set()
    for entry in receipt['entries']:
        _validate_entry(entry)
        cid=entry['identity']['connection_id'];row=entry['original_row'];ident=row['id']
        if cid not in groups or entry['identity']!=groups[cid]['identity'] or ident in seen: fail()
        seen.add(ident)
        if ident in prior_by_id:
            if static(entry)!=prior_by_id[ident]: fail()
            seen_prior.add(ident)
        elif ident in contract.R2_EXCLUDED_STEP_IDS:
            if found_excluded or entry['kind']!='lineage' or row['operation']!='body': fail()
            found_excluded=True
        elif ident in expected_add:
            fixed=expected_add[ident]
            doc=entry['ordered_manifest'].get('document',{})
            if (cid!=fixed['connection_id'] or entry['kind']!='lineage' or row['operation']!='add'
                    or row['request_key']!=fixed['request_key'] or entry['original_row_sha']!=fixed['row_sha']
                    or entry['manifest_sha']!=fixed['manifest_sha']
                    or entry['observed_policy_sha']!=groups[cid]['policy_sha']
                    or len(entry['ordered_manifest']['assets'])!=fixed['assets']
                    or type(doc.get('articles')) is not list or len(doc['articles'])!=fixed['articles']): fail()
            found_add.add(ident)
        else: fail()
        if prior2 is not None and ident in prev_by_id and static(entry)!=prev_by_id[ident]: fail()
        matrix=[]
        for case in groups[cid]['cases']:
            related=lineage.related(entry['ordered_manifest'],case['ordered_manifest'])
            if type(related) is not bool or related: fail('OWN_REPLACEMENT_UNRELATED_RELATION_CHANGED')
            matrix.append({'case_id':case['case_id'],'manifest_sha':case['manifest_sha'],
                'original_row_sha':case['original']['original_row_sha'],'related':False})
        if entry['cases']!=matrix or entry['matrix_sha']!=digest(matrix): fail()
    if seen_prior!=set(prior_by_id) or not found_excluded or found_add!=set(expected_add): fail()
    scopes={entry['observed_scope'] for entry in receipt['entries'] if entry['original_row']['id'] in expected_add}
    if len(scopes)!=1: fail('OWN_R3_OBSERVED_SCOPE_CHANGED')
    return receipt


def _receipt(registry, declared, groups):
    hex64(declared)
    base=_registry(registry).parent/'lineage-body-replacements'
    receipt,observed=files.read(base/(RECEIPT_PREFIX+declared+'.json'))
    if observed!=declared: fail('OWN_REPLACEMENT_UNRELATED_RECEIPT_CHANGED')
    return _verify_receipt(registry,receipt,groups)


def _context_value(groups, receipt, declared):
    accounts = []
    for cid, group in sorted(groups.items()):
        entries = [] if receipt is None else [e for e in receipt['entries'] if e['identity']['connection_id'] == cid]
        accounts.append({'connection_id': cid, 'identity_sha': digest(group['identity']),
            'policy_sha': group['policy_sha'], 'cases': group['pins'],
            'ignored': [({k: deepcopy(entry[k]) for k in _IGNORED_KEYS} |
                ({'media_dependencies_sha': entry['media_dependencies_sha']} if 'media_dependencies_sha' in entry else {}))
                for entry in entries]})
    return {'schema': 1, 'policy': POLICY, 'receipt_sha': declared, 'relation_policy': lineage.POLICY,
        'relation_module_sha': RELATION_MODULE_SHA, 'accounts': accounts}


def _context(registry, cases, declared):
    registry=_registry(registry);groups=_case_groups(cases)
    return _context_value(groups,_receipt(registry,declared,groups),declared)


def build(registry, cases, receipt_sha, *, history_locators=None):
    from . import own_replacement_contract as contract
    context = _context(registry, cases, receipt_sha)
    # prepare must catch known drift before asking for a human risk approval.
    receipt=_receipt(registry,receipt_sha,_case_groups(cases))
    scope=next(entry['observed_scope'] for entry in receipt['entries']
               if entry['original_row']['id'] in {x['step_id'] for x in contract.R3_ADDITIONAL_STEPS})
    manifest = {'registry': str(Path(registry)), 'contract_sha': contract.R3_CONTRACT_SHA,
                'candidate_scope':scope,'cases': cases, 'unrelated_context': context,
                'unrelated_context_sha': digest(context)}
    current(registry, manifest, history_locators=history_locators)
    return context


def immutable(registry, manifest):
    try:
        from . import own_replacement_contract as contract
        registry = _registry(registry)
        if (type(manifest) is not dict or manifest['registry'] != str(registry)
                or manifest['contract_sha'] != contract.R3_CONTRACT_SHA): fail()
        context = manifest['unrelated_context']
        exact(context, ('schema','policy','receipt_sha','relation_policy','relation_module_sha','accounts'))
        if type(context['schema']) is not int or context['schema'] != 1 or manifest['unrelated_context_sha'] != digest(context): fail()
        groups=_case_groups(manifest['cases']); receipt=_receipt(registry,context['receipt_sha'],groups)
        expected=_context_value(groups,receipt,context['receipt_sha'])
        add_ids={x['step_id'] for x in contract.R3_ADDITIONAL_STEPS}
        if (context != expected or any(entry['observed_scope']!=manifest['candidate_scope']
                for entry in receipt['entries'] if entry['original_row']['id'] in add_ids)):
            fail('OWN_REPLACEMENT_UNRELATED_CONTEXT_CHANGED')
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
    with content_scope(w.db, db):
        if row['operation']=='add' and entry['kind']=='lineage':
            from . import own_replacement_media_leaves as media
            saved_intent=stored(row['intent'],row['intent_digest'])
            initial_manifest, initial_sha=w._bundle(db,p,saved_intent['selector']['bundle_id'],saved_intent['selector']['version'])
            initial_approval=w._approval(db,p,initial_manifest,initial_sha,row['approval_id'],active=False)
            captured=media.capture(w,db,p,initial_manifest,initial_sha,row,saved_intent,initial_approval, history_locators=history_locators)
            if captured!=entry['media_dependencies']: fail('OWN_REPLACEMENT_UNRELATED_HISTORY_CHANGED')
        intent, result = w._step(db, p, row, history_locators=history_locators)
        manifest, _ = w._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
        approval = w._approval(db, p, manifest, entry['manifest_sha'], row['approval_id'], active=False)
        if (intent != entry['original_intent'] or result or manifest != entry['ordered_manifest']
                or dict(approval) != entry['original_approval'] or lineage.seal(db, manifest) != entry['lineage']):
            fail('OWN_REPLACEMENT_UNRELATED_HISTORY_CHANGED')



def _uncovered_unknown(db, path, policy, binding, row, entries, source_kind, *, history_locators=None):
    # Called only after the complete selected/retained rows and lock sets have
    # passed. One fixed pre-lineage terminal success has its original reader;
    # every other uncovered UNKNOWN still requires the existing replacement.
    from . import own_replacement_legacy_body_v3 as legacy_body
    if (binding['connection'] == legacy_body._PIN['connection_id']
            and row['id'] == legacy_body._PIN['body_id']):
        w, p = _history(db, path, binding, policy)
        with content_scope(w.db, db):
            legacy_body.validate(w, db, p, row, entries, history_locators=history_locators)
        return
    from .own_lineage_replacement import validate_record
    replacement = db.execute('SELECT * FROM own_lineage_replacements WHERE original_step_id=?',
        (row['id'],)).fetchone()
    if row['operation'] != 'body' or replacement is None or replacement['state'] != 'SUCCEEDED':
        fail('OWN_REPLACEMENT_UNRELATED_LOCKS_CHANGED')
    validate_record(db, replacement, source_kind, history_policy=policy, history_locators=history_locators)


def current(registry, manifest, *, history_locators=None):
    context = immutable(registry, manifest)
    groups = _case_groups(manifest['cases']); receipt = _receipt(registry, context['receipt_sha'], groups)
    return _current_receipt(registry,manifest,context,groups,receipt, history_locators=history_locators)


def current_candidate(registry, cases, receipt, *, history_locators=None):
    # For trusted technical preparation only: validate the complete in-memory
    # receipt and actual locked state before creating a new receipt file.
    from . import own_replacement_contract as contract
    registry=_registry(registry);groups=_case_groups(cases)
    _verify_receipt(registry,receipt,groups)
    checksum=sha256((canonical(receipt)+'\n').encode()).hexdigest()
    context=_context_value(groups,receipt,checksum)
    scope=next(entry['observed_scope'] for entry in receipt['entries']
               if entry['original_row']['id'] in {x['step_id'] for x in contract.R3_ADDITIONAL_STEPS})
    manifest={'registry':str(registry),'contract_sha':contract.R3_CONTRACT_SHA,
              'candidate_scope':scope,'cases':cases,'unrelated_context':context,'unrelated_context_sha':digest(context)}
    return _current_receipt(registry,manifest,context,groups,receipt, history_locators=history_locators)


def _current_receipt(registry,manifest,context,groups,receipt, *, history_locators=None):
    if _v2_observation(registry)!=receipt['v2_predecessor']: fail('OWN_R3_PREDECESSOR_CHANGED')
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
            # Previous R2 admissions may not be hidden by a missing proposal or
            # by an orphaned filesystem pointer. Current R3 child rows are
            # allowed only under this very manifest during commit/dispatch.
            from . import own_replacement_contract as contract
            for batch_row in db.execute('SELECT id,manifest,manifest_digest FROM own_replacement_batches'):
                old=stored(batch_row['manifest'],batch_row['manifest_digest'])
                if type(old) is not dict: fail()
                if old.get('contract_sha')==contract.R2_CONTRACT_SHA:
                    fail('OWN_R3_PREDECESSOR_ACTIVE_OR_UNKNOWN')
                if old.get('contract_sha')==contract.R3_CONTRACT_SHA and (
                        manifest.get('batch_id')!=batch_row['id'] or old!=manifest):
                    fail('OWN_R3_PREDECESSOR_ACTIVE_OR_UNKNOWN')
            entries = [] if receipt is None else [e for e in receipt['entries'] if e['identity']['connection_id'] == cid]
            for entry in entries:
                if (entry['original_row']['id'] in {x['step_id'] for x in contract.R3_ADDITIONAL_STEPS}
                        and (entry['observed_policy_sha']!=group['policy_sha']
                             or entry['observed_scope']!=policy.value['candidate_scope'])):
                    fail('OWN_REPLACEMENT_UNRELATED_AUTHORITY_CHANGED')
                _old_current(db, path, policy, entry, history_locators=peer_history)
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
            # A missing lock must not silently hide an UNKNOWN original. The
            # selected and retained owners have already been checked above;
            # any other body must have independently validated success history.
            covered = set(expected_own) | {entry['original_row']['id'] for entry in entries}
            unknown = db.execute("SELECT * FROM own_steps WHERE tenant=? AND resource=? AND state='RESULT_UNKNOWN'",
                (actor['tenant_id'], identity['resource_id'])).fetchall()
            for row in unknown:
                if row['id'] in covered: continue
                _uncovered_unknown(db, path, policy, group['cases'][0]['original']['binding'],
                    row, entries, source[0], history_locators=peer_history)
            if list(path_check(path)[:2]) != group['database_identity']: fail()
        policy.check()
    return context


def allowed(manifest, connection_id, kind):
    if kind not in ('lineage', 'legacy:step'): fail()
    context = immutable(manifest['registry'], manifest)
    account = next((a for a in context['accounts'] if a['connection_id'] == connection_id), None)
    if account is None: fail()
    if account is None: fail('OWN_REPLACEMENT_UNRELATED_AUTHORITY_CHANGED')
    return tuple(deepcopy(entry['lock_row']) for entry in account['ignored'] if entry['kind'] == kind)


from .draft_group_history_context import readonly_history_snapshot as _peer_history_snapshot
