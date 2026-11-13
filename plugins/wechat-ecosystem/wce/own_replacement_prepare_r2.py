"""Trusted-host-only preparation of the fixed R2 proposal; no send grant.

The installer must supply a guard that revalidates the exact installed package,
completed metadata transition and its bounded maintenance authority.  No caller
may supply targets, asset paths, policy, receipt data, or a request budget.
"""
from contextlib import ExitStack, closing
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from .contracts import WCEError
from .service import canonical, digest
from .own_connection_policy import locked
from .own_cover_authority import historical_profile
from .own_workflow import OwnWorkflow
from . import own_replacement_batch as batch, own_replacement_files as files
from . import own_replacement_contract as contract, own_replacement_unrelated as v1
from . import own_replacement_unrelated_v2 as v2, own_lineage as lineage


def fail(code='OWN_R2_PREPARATION_HOLD'):
    raise WCEError(code)


def _prior(registry):
    plan,plan_sha=files.read(batch.base(registry)/'proposal.json')
    keys={'schema','registry','candidate_scope','contract_sha','targets','unrelated_receipt_sha'}
    if (plan_sha!=contract.R2_PREDECESSOR_SHA or type(plan) is not dict
            or set(plan) not in (keys,keys|{'preview_receipt_sha'})
            or plan['schema']!=2 or plan['registry']!=str(registry)
            or plan['contract_sha']!=batch.CONTRACT_SHA
            or type(plan['targets']) is not list or len(plan['targets'])!=3
            or plan['unrelated_receipt_sha']!=v1.RECEIPT_SHA): fail()
    for target in plan['targets']:
        if type(target) is not dict or set(target)!={'connection_id','request_key','label','source_counts'}: fail()
    return plan


def _body_descriptor(policy, case, guard, *, history_locators=None):
    original=case['original']; path=policy.root/'state.sqlite3'
    guard();policy.check()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('BEGIN')
        row=db.execute('SELECT * FROM own_steps WHERE id=?',(original['original_step_id'],)).fetchone()
        if row is None: fail()
        row=dict(row)
        if row['id'] not in contract.R2_EXCLUDED_STEP_IDS or digest(row)!=original['original_row_sha']: fail()
        p=historical_profile(policy)
        source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if source is None or source[0] not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'): fail()
        if source[0]=='SYNTHETIC_SETUP':
            b=p.binding();b['source_kind']=source[0];p.source_kind=source[0];p.binding=lambda:dict(b)
        if row['operation']!='body' or row['state']!='RESULT_UNKNOWN': fail()
        w=object.__new__(OwnWorkflow);w.db=SimpleNamespace(path=path,history_policy=policy)
        intent,result=w._step(db,p,row, history_locators=history_locators)
        manifest,manifest_sha=w._bundle(db,p,intent['selector']['bundle_id'],intent['selector']['version'])
        approval=w._approval(db,p,manifest,manifest_sha,row['approval_id'],False)
        lock=db.execute('SELECT * FROM own_lineage_locks WHERE owner_id=?',(row['id'],)).fetchone()
        if result or lock is None or digest(manifest)!=case['manifest_sha']: fail()
        lock=dict(lock);approval=dict(approval);seal=lineage.seal(db,manifest)
        identity=deepcopy(policy.data)
        entry={'cases':[], 'identity':identity,'identity_sha':digest(identity),'kind':'lineage',
            'lineage':seal,'lock_row':lock,'lock_sha':digest(lock),'manifest_sha':manifest_sha,
            'matrix_sha':digest([]),'observed_policy_sha':policy.fingerprint,'observed_scope':policy.value['candidate_scope'],
            'ordered_manifest':manifest,'original_approval':approval,'original_approval_sha':digest(approval),
            'original_intent':intent,'original_row':row,'original_row_sha':digest(row),
            'owner_row':deepcopy(row),'owner_row_sha':digest(row),'provider':'WECHAT_OFFICIAL_ACCOUNT'}
        guard();policy.check()
    return entry


def _matrix(entry,cases):
    result=[]
    for case in cases:
        if entry['identity']['connection_id']!=case['connection_id']:continue
        related=lineage.related(entry['ordered_manifest'],case['ordered_manifest'])
        if type(related) is not bool or related: fail('OWN_REPLACEMENT_UNRELATED_RELATION_CHANGED')
        result.append({'case_id':case['case_id'],'manifest_sha':case['manifest_sha'],
            'original_row_sha':case['original']['original_row_sha'],'related':False})
    if not result: fail()
    entry=deepcopy(entry);entry['cases']=result;entry['matrix_sha']=digest(result)
    return entry


def _put_or_verify(path,value,guard):
    guard()
    if os.path.lexists(path):
        prior,_=files.read(path)
        if prior!=value: fail('OWN_R2_PREPARATION_EXISTING_CHANGED')
        files.durable(path)
    else: files.exclusive(path,value)
    actual=files.read(path)[1]
    guard()
    return actual


def _no_orphan_batch(registry):
    if batch.find_batch(registry) is not None:
        fail('OWN_REPLACEMENT_ALREADY_REVIEWED_QUERY_ORIGINAL')
    for path in batch.base(registry).iterdir():
        if path.name.startswith('replacement-batch-'):
            fail('OWN_R2_PREPARATION_ORPHAN_BATCH')


def prepare_r2_proposal(registry, trusted_guard, *, history_locators=None):
    registry=Path(registry)
    if not callable(trusted_guard): fail()
    def guard():
        trusted_guard()
    guard()
    old=_prior(registry)
    preview=None
    if 'preview_receipt_sha' in old:
        from .own_replacement_preview_policy import load
        preview=load(batch.base(registry)/'preview-inputs.json',old['preview_receipt_sha'])
    roots=[]; policies={}
    for target in old['targets']:
        policy=batch.resolve(target['connection_id'],registry);policy.check()
        if target['connection_id'] in policies and policies[target['connection_id']].fingerprint!=policy.fingerprint: fail()
        policies[target['connection_id']]=policy
        if policy.root not in roots: roots.append(policy.root)
    if len(roots)!=2: fail()
    with batch.execution_gate(registry), locked(registry.parent/'connection-setup.lock',nonblocking=True), ExitStack() as locks:
        for root in sorted(roots,key=str):
            locks.enter_context(locked(root/'connection-start.lock',nonblocking=True))
            locks.enter_context(locked(root/'connection.lock',nonblocking=True))
        guard()
        _no_orphan_batch(registry)
        if _prior(registry)!=old: fail()
        cases=[batch._case(policies[t['connection_id']],t,guard,preview) for t in old['targets']]
        contract.validate_r2_cases(cases[1:])
        if tuple([cases[0]['original']['original_step_id']])!=contract.R2_EXCLUDED_STEP_IDS: fail()
        if len({case['case_id'] for case in cases})!=3: fail()
        groups=v2._case_groups(cases[1:])
        prior,prior_sha=files.read(batch.base(registry)/v1.RECEIPT_NAME)
        if prior_sha!=v1.RECEIPT_SHA or type(prior) is not dict: fail()
        v1.exact(prior,('schema','relation_policy','relation_module_sha','entries'))
        if (prior['schema']!=v1.POLICY or prior['relation_policy']!=lineage.POLICY
                or prior['relation_module_sha']!=v1.RELATION_MODULE_SHA
                or type(prior['entries']) is not list or len(prior['entries'])!=2): fail()
        for entry in prior['entries']:v1._validate_entry(entry)
        excluded=_body_descriptor(policies[cases[0]['connection_id']],cases[0],guard, history_locators=history_locators)
        entries=[_matrix(entry,cases[1:]) for entry in prior['entries']+[excluded]]
        receipt={'schema':v2.POLICY,'relation_policy':lineage.POLICY,'relation_module_sha':v1.RELATION_MODULE_SHA,
                 'predecessor_receipt_sha':prior_sha,'entries':entries}
        checksum=sha256((canonical(receipt)+'\n').encode()).hexdigest()
        path=batch.base(registry)/(v2.RECEIPT_PREFIX+checksum+'.json')
        plan={'schema':3,'registry':str(registry),'candidate_scope':batch.code_scope(),
              'contract_sha':contract.R2_CONTRACT_SHA,'targets':deepcopy(old['targets'][1:]),
              'unrelated_receipt_sha':checksum}
        if 'preview_receipt_sha' in old:plan['preview_receipt_sha']=old['preview_receipt_sha']
        target=batch.base(registry)/'proposal-r2.json'
        # Never mint a second receipt around unknown prior preparation. Exact
        # byte-equivalent recovery is the sole allowed receipt-only continuation.
        existing=[item for item in batch.base(registry).iterdir() if item.name.startswith(v2.RECEIPT_PREFIX)]
        if any(item.name!=path.name for item in existing) or len(existing)>1:
            fail('OWN_R2_PREPARATION_RECEIPT_ORPHAN')
        if os.path.lexists(target):
            if not os.path.lexists(path) or files.read(target)[0]!=plan:
                fail('OWN_R2_PREPARATION_EXISTING_CHANGED')
        guard(); _put_or_verify(path,receipt,guard)
        context=v2.build(registry,cases[1:],checksum, history_locators=history_locators)
        manifest={'registry':str(registry),'contract_sha':contract.R2_CONTRACT_SHA,
                  'cases':cases[1:],'unrelated_context':context,'unrelated_context_sha':digest(context)}
        for case in cases[1:]: batch._check_prepared_case(registry,case,manifest,guard)
        for policy in policies.values():policy.check()
        guard()
        _no_orphan_batch(registry)
        if _prior(registry)!=old: fail()
        proposal_sha=_put_or_verify(target,plan,guard)
        checked=batch._inputs(registry,guard,contract.R2_CONTRACT_SHA)
        if checked['proposal_sha']!=proposal_sha or checked['unrelated_context']!=context: fail()
        guard()
        return {'state':'PREPARED_NO_GRANT','proposal_sha256':proposal_sha,'receipt_sha256':checksum,
                'contract_sha256':contract.R2_CONTRACT_SHA,'cases':2,'maximum_new_sends':0}
