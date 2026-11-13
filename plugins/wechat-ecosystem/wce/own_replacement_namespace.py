"""R3 sender-only full namespace gate. No historical or model authorization.

Caller has checked the original approval, live authority, state, deadlines and
same-stack permit. This gate never dispatches, mutates files or repairs history.
"""
from contextlib import closing,contextmanager
from contextvars import ContextVar
import threading
from pathlib import Path
import os
import re
import sqlite3
import stat

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .service import digest
from . import own_replacement_files as files

_ERROR='OWN_R3_SENDER_NAMESPACE_HOLD'
_HEX=re.compile(r'[a-f0-9]{64}')
_CASE_FILE=re.compile(r'[a-f0-9]{64}\.json')
_BATCH=re.compile(r'replacement-batch-[a-f0-9]{32}')
_REPLACEMENT=re.compile(r'lineage-replacement-[a-f0-9]{32}')
_OWNER=re.compile(r'[a-f0-9]{32}')
_EXECUTION_SCOPE=ContextVar('wce_r3_execution_scope',default=None)
_CLAIM_SCOPE=ContextVar('wce_r3_claim_scope',default=None)
_CLAIM_KEYS=frozenset(('schema','policy','case_id','resource','original_step_id','original_step_sha',
    'batch_id','approval_digest','replacement_id','owner','row_pin_sha','intent_digest',
    'candidate_scope','contract_sha','unrelated_context_sha','unrelated_receipt_sha'))


def fail():
    raise WCEError(_ERROR)


def _claim_shape(claim,case,manifest,approval_body):
    if type(claim) is not dict or set(claim)!=_CLAIM_KEYS: fail()
    orig=case['original']
    expected={'schema':2,'policy':'STABLE_LINEAGE_BODY_REPLACEMENT_SPENT_V1',
        'case_id':case['case_id'],'resource':orig['binding']['resource'],
        'original_step_id':orig['original_step_id'],'original_step_sha':orig['original_row_sha'],
        'batch_id':manifest['batch_id'],'approval_digest':digest(approval_body),
        'candidate_scope':manifest['candidate_scope'],'contract_sha':manifest['contract_sha'],
        'unrelated_context_sha':manifest['unrelated_context_sha'],
        'unrelated_receipt_sha':manifest['unrelated_context']['receipt_sha']}
    if (type(claim['schema']) is not int or any(claim[k]!=v for k,v in expected.items())
            or type(claim['replacement_id']) is not str or _REPLACEMENT.fullmatch(claim['replacement_id']) is None
            or type(claim['owner']) is not str or _OWNER.fullmatch(claim['owner']) is None
            or any(type(claim[k]) is not str or _HEX.fullmatch(claim[k]) is None
                   for k in ('row_pin_sha','intent_digest'))): fail()


class _LockScope:
    def __init__(self,registry,fd,case_id,root_identity):
        if type(fd) is not int: fail()
        st=os.fstat(fd)
        self.pid=os.getpid();self.thread=threading.get_ident();self.registry=str(Path(registry))
        self.fd=fd;self.identity=(st.st_dev,st.st_ino);self.case_id=case_id;self.enforced=False
        self.root_identity=root_identity



def _held_lock(value,registry,path,case_id=None):
    try:
        return _held_lock_checked(value,registry,path,case_id)
    except Exception:
        # Scope-finally checks also run outside current(); never leak paths.
        raise WCEError(_ERROR) from None


def _held_lock_checked(value,registry,path,case_id=None):
    if (type(value) is not _LockScope or value.pid!=os.getpid() or value.thread!=threading.get_ident()
            or value.registry!=str(Path(registry)) or value.case_id!=case_id): fail()
    root_identity=files.folder(path.parent)
    if value.root_identity is None or value.root_identity!=root_identity: fail()
    owned=os.fstat(value.fd);path_info=path.lstat()
    if ((owned.st_dev,owned.st_ino)!=value.identity or (path_info.st_dev,path_info.st_ino)!=value.identity
            or not stat.S_ISREG(owned.st_mode) or not stat.S_ISREG(path_info.st_mode)
            or owned.st_uid!=os.getuid() or path_info.st_uid!=os.getuid()
            or stat.S_IMODE(owned.st_mode)!=0o600 or stat.S_IMODE(path_info.st_mode)!=0o600
            or owned.st_nlink!=1 or path_info.st_nlink!=1 or owned.st_size!=0 or path_info.st_size!=0): fail()
    value.enforced=True
    return value.identity


@contextmanager
def execution_scope(registry,fd,root_identity):
    prior=_EXECUTION_SCOPE.get()
    if prior is not None: fail()
    value=_LockScope(registry,fd,None,root_identity);token=_EXECUTION_SCOPE.set(value)
    try: yield
    finally:
        try:
            if value.enforced:
                from .own_replacement_batch import base
                _held_lock(value,registry,base(registry)/'execution.lock')
        finally: _EXECUTION_SCOPE.reset(token)


@contextmanager
def claim_scope(registry,case_id,fd):
    prior=_CLAIM_SCOPE.get()
    if type(case_id) is not str or prior is not None: fail()
    execution=_EXECUTION_SCOPE.get()
    root_identity=execution.root_identity if type(execution) is _LockScope else None
    value=_LockScope(registry,fd,case_id,root_identity);token=_CLAIM_SCOPE.set(value)
    try: yield
    finally:
        try:
            if value.enforced:
                from .own_replacement_batch import base
                _held_lock(value,registry,base(registry)/('claim-lock-'+case_id+'.lock'),case_id)
        finally: _CLAIM_SCOPE.reset(token)


def _empty_lock(path):
    before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
            or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1 or before.st_size!=0): fail()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        current=os.fstat(fd);after=path.lstat()
        if ((before.st_dev,before.st_ino)!=(current.st_dev,current.st_ino)
                or (after.st_dev,after.st_ino)!=(current.st_dev,current.st_ino)
                or current.st_uid!=os.getuid() or stat.S_IMODE(current.st_mode)!=0o600
                or current.st_nlink!=1 or current.st_size!=0): fail()
    finally: os.close(fd)
    return (current.st_dev,current.st_ino)


def _spent_snapshot(path):
    files.folder(path)
    entries=list(path.iterdir())
    if len(entries)>2 or any(_CASE_FILE.fullmatch(item.name) is None for item in entries): fail()
    claims={}
    for item in entries:
        value,checksum=files.read(item,16384)
        if type(value) is not dict or type(value.get('case_id')) is not str or value['case_id']+'.json'!=item.name: fail()
        claims[value['case_id']]=(value,checksum)
    return claims


def _stop_snapshot(path,manifest):
    files.folder(path)
    blocked={'batch-'+manifest['batch_id']+'.json'} | {
        'policy-'+case['policy_sha']+'.json' for case in manifest['cases']}
    paths=list(path.iterdir())
    if len(paths)>2048: fail()
    result=[];total=0
    for item in paths:
        if (re.fullmatch(r'(?:policy-[a-f0-9]{64}|batch-replacement-batch-[a-f0-9]{32})\.json',item.name) is None
                or item.name in blocked): fail()
        value,checksum=files.read(item)
        if (type(value) is not dict or set(value)!={'schema','reason'}
                or type(value['schema']) is not int or value['schema']!=1
                or type(value['reason']) is not str): fail()
        from .service import canonical
        total+=len((canonical(value)+'\n').encode())
        if total>64*1024*1024: fail()
        result.append((item.name,checksum))
    return tuple(sorted(result))


def _closed_root(root,manifest):
    from . import own_replacement_contract as contract, own_replacement_unrelated as v1
    from . import own_replacement_unrelated_v2 as v2, own_replacement_unrelated_v3 as v3
    from .own_lineage_replacement import stable_case
    receipt_sha=manifest['unrelated_context']['receipt_sha']
    if type(receipt_sha) is not str or _HEX.fullmatch(receipt_sha) is None: fail()
    receipt_name=v3.RECEIPT_PREFIX+receipt_sha+'.json'
    receipt,receipt_observed=files.read(root/receipt_name)
    if receipt_observed!=receipt_sha: fail()
    pred=receipt['v2_predecessor']
    if (type(pred) is not dict or set(pred)!={'state','contract_sha','receipt_sha','proposal_sha'}
            or pred['contract_sha']!=contract.R2_CONTRACT_SHA or pred['state'] not in ('ABSENT','PRESENT')): fail()
    required={'proposal.json','proposal-r3.json',v1.RECEIPT_NAME,receipt_name,
              'active-batch.json','execution.lock','spent','stops',manifest['batch_id']}
    prior,prior_sha=files.read(root/'proposal.json')
    if prior_sha!=contract.R2_PREDECESSOR_SHA: fail()
    _,v1sha=files.read(root/v1.RECEIPT_NAME)
    if v1sha!=v1.RECEIPT_SHA: fail()
    plan,plan_sha=files.read(root/'proposal-r3.json')
    if (plan_sha!=manifest['proposal_sha'] or type(plan) is not dict
            or plan.get('unrelated_receipt_sha')!=receipt_sha): fail()
    if 'preview_receipt_sha' in plan:
        if prior.get('preview_receipt_sha')!=plan['preview_receipt_sha']: fail()
        _,preview_sha=files.read(root/'preview-inputs.json')
        if preview_sha!=plan['preview_receipt_sha']: fail()
        required.add('preview-inputs.json')
    elif 'preview_receipt_sha' in prior: fail()
    if pred['state']=='ABSENT':
        if pred['receipt_sha'] is not None or pred['proposal_sha'] is not None: fail()
    else:
        value=pred['receipt_sha']
        if type(value) is not str or _HEX.fullmatch(value) is None: fail()
        name=v2.RECEIPT_PREFIX+value+'.json';_,actual=files.read(root/name)
        if actual!=value: fail()
        required.add(name)
        if pred['proposal_sha'] is not None:
            _,actual=files.read(root/'proposal-r2.json')
            if actual!=pred['proposal_sha']: fail()
            required.add('proposal-r2.json')
    allowed_locks={'claim-lock-'+case['case_id']+'.lock' for case in manifest['cases']}
    excluded=[e for e in receipt['entries'] if e['original_row']['id'] in contract.R2_EXCLUDED_STEP_IDS]
    if len(excluded)!=1: fail()
    excluded_id=stable_case(excluded[0]['original_row'],excluded[0]['original_intent'])
    allowed_locks.add('claim-lock-'+excluded_id+'.lock')
    entries={item.name:item for item in root.iterdir()}
    if not required.issubset(entries) or set(entries)-required-allowed_locks: fail()
    locks={'execution.lock':_empty_lock(entries['execution.lock'])}
    for name in set(entries)&allowed_locks: locks[name]=_empty_lock(entries[name])
    stops_pin=files.folder(entries['stops'])
    stops_snapshot=_stop_snapshot(entries['stops'],manifest)
    if files.folder(entries['stops'])!=stops_pin: fail()
    return frozenset(entries),stops_snapshot,tuple(sorted(locks.items())),stops_pin


def _closed_batch(path,manifest,state):
    pin=files.folder(path)
    live,head=files.state(path)
    approval,approval_sha=files.read(path/'approval.json')
    if live!=state or type(approval) is not dict or approval.get('manifest')!=manifest: fail()
    expected={'approval.json','state.json'} | {
        'state-event-'+str(i).zfill(4)+'.json' for i in range(1,head['seq']+1)}
    if {item.name for item in path.iterdir()}!=expected or files.folder(path)!=pin: fail()
    return pin,head,approval_sha


def current(registry,manifest,state,permit, *, history_locators=None):
    try:
        return _current(registry,manifest,state,permit, history_locators=history_locators)
    except Exception:
        # Fixed error only; never expose private claim, account path or raw data.
        raise WCEError(_ERROR) from None


def _current(registry,manifest,state,permit, *, history_locators=None):
    from . import own_replacement_batch as batch, own_replacement_contract as contract
    from .own_lineage_replacement import validate_approval,validate_record
    from .own_replacement_executor import AdmissionPermit
    if (type(manifest) is not dict or manifest.get('contract_sha')!=contract.R3_CONTRACT_SHA
            or manifest.get('registry')!=str(Path(registry))): fail()
    batch.validate_state(state,manifest)
    if type(state.get('schema')) is not int or state['schema']!=1: fail()
    if state['phase'] not in ('READY','IN_FLIGHT','COMPLETE'): fail()
    batch_id=manifest['batch_id']
    if type(batch_id) is not str or _BATCH.fullmatch(batch_id) is None: fail()
    root=batch.base(registry);root_pin=files.folder(root)
    root_snapshot=_closed_root(root,manifest)
    execution_pin=_held_lock(_EXECUTION_SCOPE.get(),registry,root/'execution.lock')
    pointer,pointer_sha=files.read(root/'active-batch.json',16384)
    if (type(pointer) is not dict or set(pointer)!={'schema','batch_id','proposal_sha'}
            or type(pointer['schema']) is not int or pointer['schema']!=1
            or pointer['batch_id']!=batch_id or pointer['proposal_sha']!=manifest['proposal_sha']): fail()
    batches=[p for p in root.iterdir() if p.name.startswith('replacement-batch-')]
    if len(batches)!=1 or batches[0].name!=batch_id: fail()
    batch_snapshot=_closed_batch(batches[0],manifest,state)
    spent=root/'spent';spent_pin=files.folder(spent)
    claims=_spent_snapshot(spent)
    if len({case['connection_id'] for case in manifest['cases']})!=len(manifest['cases']): fail()
    completed={item['case_id']:item for item in state['completed']}
    if len(completed)!=len(state['completed']): fail()
    inflight=None;bound=None;bound_sha=None;written=False
    if state['phase']=='IN_FLIGHT':
        if type(permit) is not AdmissionPermit or permit._same_stack() is not True: fail()
        inflight=state['inflight']
        if (type(inflight) is not dict or set(inflight)!={'case_id','admission_owner','replacement_id','intent_sha','claim_sha'}
                or type(inflight['admission_owner']) is not str or _OWNER.fullmatch(inflight['admission_owner']) is None): fail()
        bound,bound_sha,written=permit.claim_snapshot()
        fields=(inflight['replacement_id'],inflight['intent_sha'],inflight['claim_sha'])
        if fields!=(None,None,None):
            if (bound is None or not written or fields!=(bound.get('replacement_id'),bound.get('intent_digest'),bound_sha)): fail()
        if bound is None and (bound_sha is not None or written or fields!=(None,None,None)): fail()
        claim_binding=_CLAIM_SCOPE.get()
        if claim_binding is not None or bound is not None:
            _held_lock(claim_binding,registry,root/('claim-lock-'+inflight['case_id']+'.lock'),inflight['case_id'])
    elif permit is not None or _CLAIM_SCOPE.get() is not None: fail()
    expected=set(completed)
    if bound is not None and written: expected.add(inflight['case_id'])
    if set(claims)!=expected: fail()
    if bound is not None and written and claims[inflight['case_id']]!=(bound,bound_sha): fail()
    seen_rows=set();resolved={}
    for case in manifest['cases']:
        cid=case['connection_id']
        if cid not in resolved:
            policy=batch.resolve(cid,Path(registry));policy.check()
            if (policy.fingerprint!=case['policy_sha'] or digest(policy.data)!=case['identity_sha']
                    or policy.root!=Path(case['root'])
                    or list(path_check(policy.root,True))!=case['root_identity']
                    or list(path_check(policy.root/'state.sqlite3')[:2])!=case['database_identity']): fail()
            resolved[cid]=policy
        policy=resolved[cid];path=policy.root/'state.sqlite3'
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('BEGIN')
            source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
            if source is None or source[0]!=case['original']['binding']['source_kind']: fail()
            approval=db.execute('SELECT * FROM own_lineage_replacement_approvals WHERE id=?',(case['approval_id'],)).fetchone()
            if approval is None: fail()
            _,body,approval_batch=validate_approval(db,approval,source[0])
            if (approval_batch['id']!=batch_id or approval['case_id']!=case['case_id']
                    or approval_batch['manifest_digest']!=digest(manifest)): fail()
            row=db.execute('SELECT * FROM own_lineage_replacements WHERE case_id=?',(case['case_id'],)).fetchone()
            for item in db.execute('SELECT r.id,r.case_id FROM own_lineage_replacements r '
                    'JOIN own_lineage_replacement_approvals a ON a.id=r.approval_id WHERE a.batch_id=?',(batch_id,)):
                if row is None or item['case_id']!=case['case_id'] or item['id']!=row['id']: fail()
            is_done=case['case_id'] in completed
            is_inflight=inflight is not None and case['case_id']==inflight['case_id']
            if not is_done and not is_inflight:
                if row is not None: fail()
            elif is_done:
                if row is None or row['id']!=completed[case['case_id']]['replacement_id'] or row['state']!='SUCCEEDED' \
                        or row['proof_sha']!=completed[case['case_id']]['proof_sha']: fail()
                validate_record(db,row,source[0],history_policy=policy, history_locators=history_locators)
                if claims[case['case_id']][0]!=batch.claim_value(row,body,manifest): fail()
                seen_rows.add(row['id'])
            else:
                if bound is None:
                    if row is not None or case['case_id'] in claims: fail()
                else:
                    _claim_shape(bound,case,manifest,body)
                    if row is None:
                        # Only the exact same-stack bound claim may be temporarily
                        # invisible in a fresh RO connection before writer commit.
                        if inflight['replacement_id'] is not None: fail()
                    else:
                        if not written or row['id']!=bound['replacement_id'] or row['state'] not in ('RESULT_UNKNOWN','SUCCEEDED'): fail()
                        validate_record(db,row,source[0],history_policy=policy, history_locators=history_locators)
                        if batch.claim_value(row,body,manifest)!=bound: fail()
                        seen_rows.add(row['id'])
            if list(path_check(path)[:2])!=case['database_identity']: fail()
        policy.check()
    if (files.folder(root)!=root_pin or files.folder(spent)!=spent_pin
            or files.read(root/'active-batch.json',16384)!=(pointer,pointer_sha)
            or _closed_root(root,manifest)!=root_snapshot
            or _held_lock(_EXECUTION_SCOPE.get(),registry,root/'execution.lock')!=execution_pin
            or _spent_snapshot(spent)!=claims
            or _closed_batch(batches[0],manifest,state)!=batch_snapshot): fail()
    if inflight is not None and _CLAIM_SCOPE.get() is not None:
        _held_lock(_CLAIM_SCOPE.get(),registry,root/('claim-lock-'+inflight['case_id']+'.lock'),inflight['case_id'])
    return True
