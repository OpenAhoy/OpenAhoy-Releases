"""GROUP08 private same-business-transaction journal proposal.

No connection/path creation, migration, commit, file proof, token, network, or
grant producer lives here. The integrating trusted service retains the common
writer lock and verifies real current/source/qualification/grant/capture files.
Integrity checks and Python values here are not platform authority or a seal.
"""
from copy import deepcopy
from contextlib import closing, contextmanager
from contextvars import ContextVar
from hashlib import sha256 as _sha256
import json
import math
import sqlite3

from .contracts import WCEError
from .draft_group_contracts import (Article, CandidateError, Coverage, LegacyMerge, PoolGroup,
    budget_for, canonical, digest, identifier as _identifier, integer as _integer,
    retirement_reserve, sha as _value_sha)
from .draft_group_planner import normalize_preview

SCHEMA = """
CREATE TABLE group_pools(account_key TEXT PRIMARY KEY, source_kind TEXT NOT NULL CHECK(source_kind IN ('SYNTHETIC_SETUP','OPERATOR_ATTESTED')), seq INTEGER NOT NULL CHECK(typeof(seq)='integer' AND seq>0), head TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL);
CREATE TABLE group_events(account_key TEXT NOT NULL REFERENCES group_pools(account_key), seq INTEGER NOT NULL CHECK(typeof(seq)='integer' AND seq>0), kind TEXT NOT NULL, payload TEXT NOT NULL, previous_sha TEXT NOT NULL, event_sha TEXT NOT NULL, PRIMARY KEY(account_key,seq));
CREATE TABLE group_batches(account_key TEXT NOT NULL REFERENCES group_pools(account_key), batch_id TEXT NOT NULL, request_key TEXT NOT NULL, state TEXT NOT NULL, next_ordinal INTEGER NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,batch_id), UNIQUE(account_key,request_key));
CREATE UNIQUE INDEX group_one_parent ON group_batches(account_key) WHERE state IN ('PLANNED','ACTIVE','HOLD','UNKNOWN','CANCELLED_WITH_RESIDUE');
CREATE TABLE group_operations(account_key TEXT NOT NULL, operation_id TEXT NOT NULL, batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL, child_key TEXT NOT NULL, state TEXT NOT NULL, cancelled INTEGER NOT NULL CHECK(typeof(cancelled)='integer' AND cancelled IN (0,1)), value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,operation_id), UNIQUE(account_key,batch_id,ordinal), UNIQUE(account_key,child_key), FOREIGN KEY(account_key,batch_id) REFERENCES group_batches(account_key,batch_id));
CREATE UNIQUE INDEX group_one_active ON group_operations(account_key) WHERE state IN ('PLANNED','BASELINES_OBSERVED','ADD_ADMITTED','NEW_OBSERVED','NEW_VERIFIED','OLD_BASELINES_RECHECKED','SWITCHED_OLD_RETAINED','RETIRING','UNKNOWN','HOLD');
CREATE TABLE group_operation_old_refs(account_key TEXT NOT NULL, operation_id TEXT NOT NULL, old_index INTEGER NOT NULL CHECK(typeof(old_index)='integer' AND old_index BETWEEN 0 AND 7), ref_sha TEXT NOT NULL, reserved INTEGER NOT NULL CHECK(typeof(reserved)='integer' AND reserved IN (0,1)), state TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,operation_id,old_index), FOREIGN KEY(account_key,operation_id) REFERENCES group_operations(account_key,operation_id));
CREATE UNIQUE INDEX group_one_old_ref ON group_operation_old_refs(account_key,ref_sha) WHERE reserved=1;
CREATE TABLE group_member_origins(account_key TEXT NOT NULL, operation_id TEXT NOT NULL, position INTEGER NOT NULL CHECK(typeof(position)='integer' AND position BETWEEN 0 AND 7), article_id TEXT NOT NULL, old_index INTEGER, old_position INTEGER, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,operation_id,position), UNIQUE(account_key,operation_id,article_id), UNIQUE(account_key,operation_id,old_index,old_position), FOREIGN KEY(account_key,operation_id) REFERENCES group_operations(account_key,operation_id));
CREATE TABLE group_active_members(account_key TEXT NOT NULL REFERENCES group_pools(account_key), article_id TEXT NOT NULL, group_id TEXT NOT NULL, version_sha TEXT NOT NULL, PRIMARY KEY(account_key,article_id));
CREATE TABLE group_queue(account_key TEXT NOT NULL REFERENCES group_pools(account_key), article_id TEXT NOT NULL, version_sha TEXT NOT NULL, batch_id TEXT NOT NULL, operation_id TEXT NOT NULL, state TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,article_id));
CREATE TABLE group_claims(account_key TEXT NOT NULL, claim_id TEXT NOT NULL, operation_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('GET','ADD','DELETE')), slot TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(typeof(ordinal)='integer' AND ordinal>0), state TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,claim_id), UNIQUE(account_key,operation_id,kind,slot), FOREIGN KEY(account_key,operation_id) REFERENCES group_operations(account_key,operation_id));
CREATE UNIQUE INDEX group_one_add ON group_claims(account_key,operation_id) WHERE kind='ADD';
CREATE TABLE group_own_step_links(account_key TEXT NOT NULL, operation_id TEXT NOT NULL, claim_id TEXT NOT NULL, step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id), value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,operation_id), FOREIGN KEY(account_key,operation_id) REFERENCES group_operations(account_key,operation_id), FOREIGN KEY(account_key,claim_id) REFERENCES group_claims(account_key,claim_id));
CREATE TABLE group_previews(account_key TEXT NOT NULL REFERENCES group_pools(account_key), preview_id TEXT NOT NULL, input_sha TEXT NOT NULL, request_key TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,preview_id));
CREATE TABLE group_preview_read_grants(account_key TEXT NOT NULL REFERENCES group_pools(account_key), grant_id TEXT NOT NULL, source_grant_sha TEXT NOT NULL, phase TEXT NOT NULL CHECK(phase IN ('QUALIFY','DISCOVER')), scope_sha TEXT NOT NULL, list_cap INTEGER NOT NULL CHECK(typeof(list_cap)='integer' AND list_cap BETWEEN 0 AND 20), get_cap INTEGER NOT NULL CHECK(typeof(get_cap)='integer' AND get_cap BETWEEN 0 AND 200), value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,grant_id), UNIQUE(account_key,source_grant_sha,phase,scope_sha));
CREATE TABLE group_preview_read_claims(account_key TEXT NOT NULL, claim_id TEXT NOT NULL, grant_id TEXT NOT NULL, preview_id TEXT NOT NULL, api TEXT NOT NULL CHECK(api IN ('LIST','GET')), ordinal INTEGER NOT NULL CHECK(typeof(ordinal)='integer' AND ordinal>0), state TEXT NOT NULL, value TEXT NOT NULL, value_sha TEXT NOT NULL, PRIMARY KEY(account_key,claim_id), UNIQUE(account_key,grant_id,api,ordinal), FOREIGN KEY(account_key,grant_id) REFERENCES group_preview_read_grants(account_key,grant_id), FOREIGN KEY(account_key,preview_id) REFERENCES group_previews(account_key,preview_id));
"""
ZERO = '0' * 64
_ADMITTING=ContextVar('fixed_group_add_transaction',default=None)
_WORKFLOW_ADD=ContextVar('fixed_group_workflow_add_check',default=None)
ACTIVE = frozenset(('PLANNED','BASELINES_OBSERVED','ADD_ADMITTED','NEW_OBSERVED',
    'NEW_VERIFIED','OLD_BASELINES_RECHECKED','SWITCHED_OLD_RETAINED','RETIRING','UNKNOWN','HOLD'))
TERMINAL = frozenset(('COMPLETE','CANCELLED_BEFORE_ADMISSION'))
_PIN_FIELDS = ('id','tenant','principal','connection','resource','request_key','operation',
    'slot','manifest_digest','target','approval_id','approval_digest','intent_digest','owner','created')

def fail(code='GROUP_STATE_UNVERIFIED'):
    raise WCEError(code)

def sha(value):
    try:return _value_sha(value)
    except CandidateError:fail('GROUP_VALUE_INVALID')

def identifier(value):
    try:return _identifier(value)
    except CandidateError:fail('GROUP_VALUE_INVALID')

def integer(value,low=0,high=2**63-1):
    try:return _integer(value,low,high)
    except CandidateError:fail('GROUP_VALUE_INVALID')

def _json(value, *, maximum=2*1024*1024):
    """Check exact JSON types before hashing, equality, coercion or hooks."""
    left=[200000]
    def visit(v, depth):
        left[0]-=1
        if left[0]<0 or depth>64:fail()
        kind=type(v)
        if kind is dict:
            if any(type(k) is not str for k in v):fail()
            for k,item in v.items():visit(k,depth+1);visit(item,depth+1)
        elif kind is list:
            for item in v:visit(item,depth+1)
        elif kind is str:
            if len(v)>maximum:fail()
        elif kind is int:
            if not -(2**63)<v<2**63:fail()
        elif kind is float:
            if not math.isfinite(v):fail()
        elif kind not in (bool,type(None)):fail()
    visit(value,0)
    try:size=len(canonical(value).encode())
    except (ValueError,UnicodeError):fail()
    if size>maximum:fail()
    return value

def _closed(value, keys):
    _json(value)
    if type(value) is not dict or set(value)!=set(keys):fail()
    return value

def _enum(value, choices):
    if type(value) is not str or value not in choices:fail()
    return value

def _clone(value):return json.loads(canonical(_json(value)))
def _rowpin(row):return {k:row[k] for k in _PIN_FIELDS}
def _same(left,right):
    """Exact JSON-type equality, including SQLite REAL created timestamps."""
    _json(left);_json(right)
    if type(left) is not type(right):return False
    if type(left) is dict:
        return left.keys()==right.keys() and all(_same(left[k],right[k]) for k in left)
    if type(left) is list:return len(left)==len(right) and all(_same(a,b) for a,b in zip(left,right))
    return left==right
def _ref_sha(reference):
    if type(reference) is not str or not 0<len(reference)<=128:fail()
    return _sha256(reference.encode('utf-8')).hexdigest()

def _group_layout(db):
    # These exact three objects belong to own_group_schema's full9 validator.
    return [tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'group_%' AND name NOT IN ('group_schema_migrations','group_schema_migration_no_update','group_schema_migration_no_delete') ORDER BY type,name")]

def _check_group_layout(db):
    with closing(sqlite3.connect(':memory:')) as template:
        for statement in SCHEMA.split(';'):
            if statement.strip():template.execute(statement)
        expected=_group_layout(template)
    if _group_layout(db)!=expected:fail('GROUP_SCHEMA_UNVERIFIED')

def check_layout9(db, source_kind):
    """Full9 layout/ancestor ownership belongs to the independent migration module."""
    from .own_group_schema import check_layout
    check_layout(db,source_kind,group_schema=SCHEMA)

def _tx(db):
    if (not isinstance(db,sqlite3.Connection) or not db.in_transaction
            or db.execute('PRAGMA user_version').fetchone()[0]!=9
            or db.execute('PRAGMA application_id').fetchone()[0]!=0x57434f31):fail('GROUP_TRANSACTION_REQUIRED')
    _check_group_layout(db)

def _op(state, operation_id):
    identifier(operation_id)
    op=state['operations'].get(operation_id)
    if op is None:fail('GROUP_OPERATION_NOT_FOUND')
    return op

def _current_child(state, operation_id, *, allow_cancelled=False, allow_cancelled_terminal=False):
    op=_op(state,operation_id);batch=state['batches'][op['batch_id']]
    if op['ordinal']!=batch['next_ordinal'] or op['state']=='WAITING':fail('GROUP_PHASE_CONFLICT')
    if (op['cancelled'] or batch['cancelled']) and not allow_cancelled:fail('GROUP_CANCELLED')
    if op['state'] in TERMINAL and not (allow_cancelled_terminal and op['cancelled']
            and op['state']=='CANCELLED_BEFORE_ADMISSION'):fail('GROUP_PHASE_CONFLICT')
    return op,batch

def _claims(op,kind):return [v for v in op['claims'] if v['kind']==kind]
def _claim(op,kind,slot):return next((v for v in op['claims'] if v['kind']==kind and v['slot']==slot),None)

def _sticky_read_failure(op):
    """A fresh pair refreshes healthy evidence; it never erases a read outcome.

    Conservative contract: UNKNOWN also stops future reads/admissions. No
    source-review/clear-HOLD operation is defined here. Original known response
    archives may still be recorded as facts, without reopening dispatch.
    """
    return next((c for c in _claims(op,'GET') if c['outcome'] in
        ('MISMATCH','KNOWN_REJECTED','UNKNOWN')),None)

def _require_read_safety(op):
    failure=_sticky_read_failure(op)
    if failure is not None:
        fail('GROUP_RESULT_UNKNOWN' if failure['outcome']=='UNKNOWN' else 'GROUP_SOURCE_DRIFT')

def _effective(op,slot):
    found=_claim(op,'GET',slot)
    if found is not None and found['outcome'] in ('MISMATCH','KNOWN_REJECTED','UNKNOWN'):
        return found
    recovery='RECOVERY_NEW' if slot in ('NEW',) or slot.startswith('NEW_REFRESH:') else 'RECOVERY_OLD'
    candidate=_claim(op,'GET',recovery)
    if (candidate is not None and candidate['state']=='OBSERVED'
            and candidate['cursor']==op['cursor']
            and candidate['subject_sha']==_subject(op,slot)
            and (found is None or candidate['at_ms']>=found['at_ms'])):
        return candidate
    return found

def _fresh(op,slots,epoch,now_ms):
    sha(epoch);integer(now_ms)
    for slot in slots:
        value=_effective(op,slot)
        if (value is None or value['state']!='OBSERVED' or value['outcome']!='MATCHED'
                or value['epoch']!=epoch or not 0<=now_ms-value['at_ms']<=60000):
            fail('GROUP_FRESH_READ_REQUIRED')

def _subject(op,slot):
    if slot.startswith(('OLD_BASELINE:','OLD_PRE_SWITCH:','OLD_INVALID:','OLD_REFRESH:')):
        return op['plan']['old_ref_set'][int(slot.split(':')[1])]['ref_sha']
    if slot=='RECOVERY_OLD':return op['plan']['old_ref_set'][op['cursor']]['ref_sha']
    if op['new_ref_sha'] is None:fail('GROUP_NEW_REFERENCE_REQUIRED')
    return op['new_ref_sha']

def _empty_account(binding_sha,source_kind):
    sha(binding_sha);_enum(source_kind,('SYNTHETIC_SETUP','OPERATOR_ATTESTED'))
    return {'schema':1,'binding_sha':binding_sha,'source_kind':source_kind,'pool':None,
        'active_members':{},'queue':{},'batches':{},'operations':{},'previews':{},'preview_grants':{}}

def _new_pool(binding_sha,source_kind,groups,coverage,proof_sha):
    sha(binding_sha);sha(proof_sha)
    _enum(source_kind,('SYNTHETIC_SETUP','OPERATOR_ATTESTED'))
    if coverage['binding_sha']!=binding_sha:fail()
    members={}
    for g in groups:
        if g['binding_sha']!=binding_sha:fail()
        if g['state']!='PUBLISHED':
            for m in g['members']:
                if m['article_id'] in members:fail('GROUP_ACTIVE_MEMBERSHIP_CONFLICT')
                members[m['article_id']]={'group_id':g['group_id'],'version_sha':m['version_sha']}
    if len({g['group_id'] for g in groups})!=len(groups):fail()
    return {'schema':1,'binding_sha':binding_sha,'source_kind':source_kind,
        'pool':{'coverage':coverage,'coverage_proof_sha':proof_sha,
                'generation':coverage['pool_generation'],'head':coverage['pool_head_sha'],
                'groups':{g['group_id']:g for g in groups},'generations':[]},
        'active_members':members,'queue':{},'batches':{},'operations':{},'previews':{},'preview_grants':{}}

def _preview(state,p):
    _closed(p,('binding_sha','source_kind','preview_id','input_sha','request_key','scope_sha','candidate','evidence_sha'))
    if state is None:state=_empty_account(p['binding_sha'],p['source_kind'])
    if p['binding_sha']!=state['binding_sha'] or p['source_kind']!=state['source_kind']:fail()
    identifier(p['preview_id']);identifier(p['request_key'])
    for key in ('input_sha','scope_sha','evidence_sha'):sha(p[key])
    old=state['previews'].get(p['preview_id'])
    if old is not None and not _same(old,p):fail('GROUP_PREVIEW_CONFLICT')
    state['previews'][p['preview_id']]=p
    return state

def _preview_grant(state,p):
    _closed(p,('source_grant_sha','phase','scope_sha','subjects','list_cap','get_cap'))
    sha(p['source_grant_sha']);sha(p['scope_sha']);_enum(p['phase'],('QUALIFY','DISCOVER'))
    integer(p['list_cap'],0,20);integer(p['get_cap'],0,200)
    if p['phase']=='QUALIFY':
        if type(p['subjects']) is not list or not 1<=len(p['subjects'])<=8 or p['list_cap']!=0 or p['get_cap']>len(p['subjects']):fail('GROUP_READ_GRANT_INVALID')
    elif p['subjects'] is not None or p['list_cap']<2:fail('GROUP_READ_GRANT_INVALID')
    if p['subjects'] is not None:
        for subject in p['subjects']:sha(subject)
        if len(set(p['subjects']))!=len(p['subjects']):fail()
    gid=digest({'binding_sha':state['binding_sha'],'source_grant_sha':p['source_grant_sha'],
        'phase':p['phase'],'scope_sha':p['scope_sha']})
    # Identity deliberately excludes preview_id, input generation and request key.
    old=state['preview_grants'].get(gid)
    if old is not None:
        if not _same(old['registration'],p):fail('GROUP_READ_GRANT_CONFLICT')
        return
    state['preview_grants'][gid]={'grant_id':gid,'registration':p,'subjects':p['subjects'],
        'subjects_proof_sha':None,'claims':[],'hold':False}

def _preview_read(state,p):
    _closed(p,('grant_id','preview_id','api','request_sha','epoch','at_ms'))
    sha(p['grant_id']);identifier(p['preview_id']);sha(p['request_sha']);sha(p['epoch']);integer(p['at_ms'])
    _enum(p['api'],('LIST','GET'))
    grant=state['preview_grants'].get(p['grant_id']);preview=state['previews'].get(p['preview_id'])
    if grant is None or preview is None or preview['scope_sha']!=grant['registration']['scope_sha']:fail('GROUP_READ_GRANT_REQUIRED')
    if grant['hold'] or any(c['state']=='CONSUMED_UNKNOWN' for c in grant['claims']):fail('GROUP_RESULT_UNKNOWN')
    used=[c for c in grant['claims'] if c['api']==p['api']];ordinal=len(used)+1
    cap=grant['registration']['list_cap' if p['api']=='LIST' else 'get_cap']
    if ordinal>cap:fail('GROUP_BUDGET_EXHAUSTED')
    if p['api']=='LIST':
        if grant['subjects'] is not None:fail('GROUP_PHASE_CONFLICT')
        subject=digest({'scope_sha':preview['scope_sha'],'list_ordinal':ordinal,'count':20})
    else:
        if grant['subjects'] is None or ordinal>len(grant['subjects']):fail('GROUP_DISCOVERY_PROOF_REQUIRED')
        subject=grant['subjects'][ordinal-1]
    claim=dict(p,ordinal=ordinal,subject_sha=subject,state='CONSUMED_UNKNOWN',proof_sha=None,outcome=None)
    claim['id']=digest({'binding_sha':state['binding_sha'],'grant_id':p['grant_id'],'api':p['api'],'ordinal':ordinal})
    grant['claims'].append(claim)

def _preview_read_result(state,p):
    _closed(p,('grant_id','claim_id','outcome','proof_sha'))
    sha(p['grant_id']);sha(p['claim_id']);sha(p['proof_sha']);_enum(p['outcome'],('OBSERVED','UNKNOWN','KNOWN_REJECTED'))
    grant=state['preview_grants'].get(p['grant_id'])
    if grant is None:fail()
    claim=next((c for c in grant['claims'] if c['id']==p['claim_id']),None)
    if claim is None or claim['state']!='CONSUMED_UNKNOWN':fail('GROUP_PHASE_CONFLICT')
    claim.update(state=p['outcome'],outcome=p['outcome'],proof_sha=p['proof_sha'])
    if p['outcome']!='OBSERVED':grant['hold']=True

def _preview_subjects(state,p):
    _closed(p,('grant_id','subjects','proof_sha'));sha(p['grant_id']);sha(p['proof_sha'])
    grant=state['preview_grants'].get(p['grant_id'])
    if (grant is None or grant['registration']['phase']!='DISCOVER' or grant['subjects'] is not None
            or grant['hold'] or len(grant['claims'])<2
            or any(c['api']!='LIST' or c['state']!='OBSERVED' for c in grant['claims'])):fail('GROUP_DISCOVERY_PROOF_REQUIRED')
    if type(p['subjects']) is not list or len(p['subjects'])>200:fail()
    for subject in p['subjects']:sha(subject)
    if len(set(p['subjects']))!=len(p['subjects']):fail()
    # Actual two-pass completeness/total/order/drift proof is the verifier's duty.
    grant.update(subjects=p['subjects'],subjects_proof_sha=p['proof_sha'])

def _typed(value,kind):
    if kind is Article:return Article(**value)
    if kind is PoolGroup:
        v=dict(value);v['members']=tuple(Article(**m) for m in v['members'])
        return PoolGroup(**v)
    if kind is LegacyMerge:return LegacyMerge(tuple(value['source_group_ids']),value['map_source_sha'])
    return Coverage(**value)

def _plan(state,payload):
    _closed(payload,('candidate','articles','groups','coverage','legacy','execution'))
    plan=payload['candidate'];_json(plan)
    normalize_preview(plan,binding_sha=state['binding_sha'],request_key=plan['request_key'],
        articles=tuple(_typed(v,Article) for v in payload['articles']),
        groups=tuple(_typed(v,PoolGroup) for v in payload['groups']),
        coverage=_typed(payload['coverage'],Coverage),
        legacy=None if payload['legacy'] is None else _typed(payload['legacy'],LegacyMerge))
    if plan['plan_state']!='CANDIDATE_ALLOCATED' or not plan['children']:fail('GROUP_PREVIEW_HOLD')
    bid=plan['batch_id'];existing=state['batches'].get(bid)
    if existing is not None:
        if not _same(existing['candidate'],plan) or not _same(existing['execution'],payload['execution']):fail('GROUP_REQUEST_CONFLICT')
        return
    if any(b['state'] not in TERMINAL for b in state['batches'].values()):fail('GROUP_PARENT_ACTIVE')
    if (payload['coverage']!=state['pool']['coverage']
            or payload['coverage']['scope']!='ACCOUNT'
            or payload['coverage']['pool_head_sha']!=state['pool']['head']):fail('GROUP_POOL_COVERAGE_HOLD')
    visible=[g for g in state['pool']['groups'].values() if g['state'] in ('OPEN','FULL','PUBLISHED','HOLD','UNKNOWN')]
    if sorted(payload['groups'],key=lambda g:g['group_id'])!=sorted(visible,key=lambda g:g['group_id']):fail('GROUP_SOURCE_DRIFT')
    execution=payload['execution']
    _closed(execution,('parent_grant_sha','preview_sha','settings_sha','source_scope_sha','child_pins'))
    for k in ('parent_grant_sha','preview_sha','settings_sha','source_scope_sha'):sha(execution[k])
    if len(execution['child_pins'])!=len(plan['children']):fail()
    for child,pins in zip(plan['children'],execution['child_pins']):
        _closed(pins,('operation_id','target_projection_sha','old_projection_shas'))
        if pins['operation_id']!=child['operation_id']:fail()
        sha(pins['target_projection_sha'])
        if len(pins['old_projection_shas'])!=len(child['old_ref_set']):fail()
        for value in pins['old_projection_shas']:sha(value)
        for member in child['members']:
            aid=member['article_id']
            active=state['active_members'].get(aid)
            queued=state['queue'].get(aid)
            inherited=(active is not None and member['origin']=='LEGACY_REGISTERED'
                and active['version_sha']==member['version_sha']
                and active['group_id'] in {o['group_id'] for o in child['old_ref_set']})
            if queued is not None and not (queued['state']=='COMPLETE' and inherited):fail('GROUP_ARTICLE_RESERVED')
            if active is not None and (member['origin']!='LEGACY_REGISTERED'
                    or active['version_sha']!=member['version_sha']
                    or active['group_id'] not in {o['group_id'] for o in child['old_ref_set']}):
                fail('GROUP_ACTIVE_MEMBERSHIP_CONFLICT')
            state['queue'][aid]={'article_id':aid,'version_sha':member['version_sha'],
                'batch_id':bid,'operation_id':child['operation_id'],'state':'RESERVED'}
        for old in child['old_ref_set']:
            for op in state['operations'].values():
                if any(v['ref_sha']==old['ref_sha'] and v['reserved'] for v in op['old_refs']):
                    fail('GROUP_OLD_REF_RESERVED')
        state['operations'][child['operation_id']]={'plan':child,'batch_id':bid,'ordinal':child['ordinal'],
            'state':child['candidate_activation'],'cancelled':False,'pins':pins,'claims':[],
            'new_ref_sha':None,'expected_own_step_id':None,'own_link':None,'add_result':None,
            'cursor':0,'switched':False,'completion_proof_sha':None,
            'old_refs':[dict(old,state='RETAINED',reserved=True) for old in child['old_ref_set']]}
    state['batches'][bid]={'candidate':plan,'execution':execution,'state':'PLANNED',
        'cancelled':False,'next_ordinal':0,'expected_head':state['pool']['head']}

def _advance(op):
    if _sticky_read_failure(op) is not None:
        op['state']='HOLD'
        return
    if op['cancelled']:return
    n=len(op['old_refs'])
    if op['switched']:
        if op['cursor']<n:op['state']='RETIRING'
        return
    if op['new_ref_sha'] is None:
        if n and all((_effective(op,'OLD_BASELINE:'+str(i)) or {}).get('outcome')=='MATCHED' for i in range(n)):
            op['state']='BASELINES_OBSERVED'
        return
    if (_effective(op,'NEW') or {}).get('outcome')=='MATCHED':
        op['state']='NEW_VERIFIED'
        if n and all((_effective(op,'OLD_PRE_SWITCH:'+str(i)) or {}).get('outcome')=='MATCHED' for i in range(n)):
            op['state']='OLD_BASELINES_RECHECKED'

def _get_claim(state,op,p):
    _closed(p,('operation_id','slot','epoch','at_ms','request_sha'));sha(p['request_sha'])
    slot=p['slot'];sha(p['epoch']);integer(p['at_ms'])
    budget=op['plan']['budget'];healthy=[s['key'] for s in budget['healthy_reads']]
    recovery=[s['key'] for s in budget['recovery_reads']]
    _enum(slot,healthy+recovery)
    if (any(c['state']=='UNKNOWN' for c in _claims(op,'DELETE'))
            and slot!='OLD_INVALID:'+str(op['cursor'])):
        fail('GROUP_RESULT_UNKNOWN')
    reads=_claims(op,'GET');ordinary=[c['slot'] for c in reads if c['slot'] not in recovery]
    if op['state'] in ('HOLD','UNKNOWN') and slot not in recovery and not slot.startswith('OLD_INVALID:'):
        fail('GROUP_RESULT_UNKNOWN')
    if _claim(op,'GET',slot) is not None:fail('GROUP_CLAIM_ALREADY_CONSUMED')
    if len(reads)>=budget['get_cap']:fail('GROUP_BUDGET_EXHAUSTED')
    used_recovery=[c['slot'] for c in reads if c['slot'] in recovery]
    if len(used_recovery)==1 and slot!='RECOVERY_OLD':fail('GROUP_PHASE_CONFLICT')
    if any(c['state']=='CONSUMED_UNKNOWN' for c in op['claims']):fail('GROUP_RESULT_UNKNOWN')
    if slot in recovery:
        used=[c['slot'] for c in reads if c['slot'] in recovery]
        if (not op['new_ref_sha'] or not op['old_refs'] or op['cursor']>=len(op['old_refs'])
                or used!=recovery[:len(used)] or len(used)>=len(recovery) or slot!=recovery[len(used)]):fail('GROUP_PHASE_CONFLICT')
        if slot=='RECOVERY_OLD':
            previous=reads[-1]
            if (previous['slot']!='RECOVERY_NEW' or previous['epoch']!=p['epoch'] or previous['cursor']!=op['cursor']
                    or previous['state']!='OBSERVED' or previous['outcome']!='MATCHED'):fail('GROUP_PHASE_CONFLICT')
        # Preserve all remaining healthy slots, especially INVALID/FINAL.
        if budget['get_cap']-len(reads)-1 < len(healthy)-len(ordinary)+(1 if slot=='RECOVERY_NEW' else 0):fail('GROUP_BUDGET_EXHAUSTED')
    else:
        if len(ordinary)>=len(healthy) or slot!=healthy[len(ordinary)]:fail('GROUP_PHASE_CONFLICT')
        if slot=='NEW' and op['add_result'] is None:fail('GROUP_PHASE_CONFLICT')
        if slot.startswith('OLD_PRE_SWITCH:') and (_effective(op,'NEW') or {}).get('outcome')!='MATCHED':fail('GROUP_PHASE_CONFLICT')
        if slot.startswith(('NEW_REFRESH:','OLD_REFRESH:')):
            if not op['switched'] or int(slot.split(':')[1])!=op['cursor']:fail('GROUP_PHASE_CONFLICT')
        if slot.startswith('OLD_INVALID:'):
            index=int(slot.split(':')[1]);delete=_claim(op,'DELETE','DELETE:'+str(index))
            if index!=op['cursor'] or delete is None or delete['state']=='CONSUMED_UNKNOWN':fail('GROUP_PHASE_CONFLICT')
        if slot=='FINAL_NEW':
            if not op['switched'] or any(old['state']!='INVALIDATED_OBSERVED' for old in op['old_refs']):fail('GROUP_PHASE_CONFLICT')
    claim={'kind':'GET','slot':slot,'ordinal':len(reads)+1,'subject_sha':_subject(op,slot),
        'epoch':p['epoch'],'at_ms':p['at_ms'],'request_sha':p['request_sha'],'cursor':op['cursor'],'state':'CONSUMED_UNKNOWN',
        'outcome':None,'proof_sha':None,'snapshot_sha':None,'code':None}
    claim['id']=digest({'binding_sha':state['binding_sha'],'operation_id':p['operation_id'],'kind':'GET','slot':slot})
    op['claims'].append(claim)

def _get_result(op,p):
    _closed(p,('operation_id','claim_id','outcome','proof_sha','snapshot_sha','code','at_ms'))
    sha(p['claim_id']);sha(p['proof_sha']);integer(p['at_ms'])
    claim=next((c for c in _claims(op,'GET') if c['id']==p['claim_id']),None)
    if claim is None or claim['state']!='CONSUMED_UNKNOWN':fail('GROUP_PHASE_CONFLICT')
    _enum(p['outcome'],('MATCHED','INVALID_REF','MISMATCH','UNKNOWN','KNOWN_REJECTED'))
    if p['at_ms']<claim['at_ms']:fail()
    if p['outcome']=='MATCHED':
        expected=(op['pins']['old_projection_shas'][int(claim['slot'].split(':')[1])]
            if claim['slot'].startswith(('OLD_BASELINE:','OLD_PRE_SWITCH:','OLD_REFRESH:'))
            else op['pins']['old_projection_shas'][claim['cursor']] if claim['slot']=='RECOVERY_OLD'
            else op['pins']['target_projection_sha'])
        sha(p['snapshot_sha'])
        if p['snapshot_sha']!=expected or p['code'] is not None:fail('GROUP_SOURCE_DRIFT')
    elif p['outcome']=='INVALID_REF':
        if not claim['slot'].startswith('OLD_INVALID:') or type(p['code']) is not int or p['code']!=40007 or p['snapshot_sha'] is not None:fail('GROUP_RETIREMENT_PROOF_HOLD')
    else:
        if p['snapshot_sha'] is not None:sha(p['snapshot_sha'])
        if p['code'] is not None:
            integer(p['code'],-2**31,2**31-1)
            if p['code']==0:fail()
    claim.update(state='UNKNOWN' if p['outcome']=='UNKNOWN' else 'KNOWN_REJECTED' if p['outcome']=='KNOWN_REJECTED' else 'OBSERVED',
        outcome=p['outcome'],proof_sha=p['proof_sha'],snapshot_sha=p['snapshot_sha'],code=p['code'],at_ms=p['at_ms'])
    if claim['slot'].startswith('OLD_INVALID:'):
        i=int(claim['slot'].split(':')[1]);delete=_claim(op,'DELETE','DELETE:'+str(i))
        if p['outcome']=='INVALID_REF' and delete['state']=='ACK_OK':
            op['old_refs'][i]['state']='INVALIDATED_OBSERVED';op['cursor']+=1
        else:op['state']='HOLD'
    elif p['outcome'] in ('MISMATCH','UNKNOWN','KNOWN_REJECTED'):op['state']='HOLD'
    elif p['outcome']=='INVALID_REF':fail()
    if p['outcome']=='MATCHED' or (p['outcome']=='INVALID_REF' and op['old_refs'][i]['state']=='INVALIDATED_OBSERVED'):
        _advance(op)

def _add_claim(state,op,p):
    _closed(p,('operation_id','epoch','at_ms','link'))
    if op['own_link'] is not None or _claims(op,'ADD'):fail('GROUP_CLAIM_ALREADY_CONSUMED')
    if op['state'] not in ('PLANNED','BASELINES_OBSERVED'):fail('GROUP_PHASE_CONFLICT')
    n=len(op['old_refs']);_fresh(op,['OLD_BASELINE:'+str(i) for i in range(n)],p['epoch'],p['at_ms'])
    link=p['link'];_closed(link,('step_pin','request_sha','manifest_sha'))
    _closed(link['step_pin'],_PIN_FIELDS)
    if any(type(link['step_pin'][k]) is not str for k in _PIN_FIELDS if k!='created'):
        fail('GROUP_OWN_STEP_LINK_HOLD')
    if type(link['step_pin']['created']) is not float or not math.isfinite(link['step_pin']['created']):
        fail('GROUP_OWN_STEP_LINK_HOLD')
    for k in ('request_sha','manifest_sha'):sha(link[k])
    if link['step_pin']['operation']!='add' or link['step_pin']['slot']!='draft':fail()
    claim={'kind':'ADD','slot':'ADD','ordinal':1,'state':'CONSUMED_UNKNOWN',
        'epoch':p['epoch'],'at_ms':p['at_ms'],'outcome':None,'proof_sha':None,
        'id':digest({'binding_sha':state['binding_sha'],'operation_id':p['operation_id'],'kind':'ADD','slot':'ADD'})}
    op['claims'].append(claim);op['own_link']=link;op['expected_own_step_id']=link['step_pin']['id'];op['state']='ADD_ADMITTED'

def _add_result(op,p):
    _closed(p,('operation_id','step_pin','archive_proof_sha','result'))
    sha(p['archive_proof_sha'])
    if op['own_link'] is None or not _same(p['step_pin'],op['own_link']['step_pin']):fail('GROUP_OWN_STEP_LINK_HOLD')
    result=p['result'];_closed(result,('reference','completion_origin','reconciliation_proof','reconciliation_proof_sha256'))
    sha(result['reconciliation_proof_sha256'])
    if (result['reconciliation_proof_sha256']!=p['archive_proof_sha']
            or result['completion_origin']!='ORIGINAL_RESPONSE_ARCHIVE'
            or result['reconciliation_proof']!='response-'+p['step_pin']['id']+'-'+p['step_pin']['owner']+'.json'):
        fail('GROUP_OWN_STEP_LINK_HOLD')
    reference_sha=_ref_sha(result['reference'])
    if op['add_result'] is not None:
        if not _same(op['add_result'],p):fail('GROUP_ARCHIVE_CONFLICT')
        return
    claim=_claim(op,'ADD','ADD')
    if claim is None or claim['state'] not in ('CONSUMED_UNKNOWN','UNKNOWN'):fail()
    if any(other['ref_sha']==reference_sha for other in op['old_refs']):fail('GROUP_REFERENCE_REUSED')
    claim.update(state='OBSERVED',outcome='KNOWN_SUCCESS',proof_sha=p['archive_proof_sha'])
    op.update(add_result=p,new_ref_sha=reference_sha,state='NEW_OBSERVED')

def _switch(state,op,p):
    _closed(p,('operation_id','expected_head','epoch','at_ms','proof_sha'))
    sha(p['proof_sha']);sha(p['expected_head'])
    n=len(op['old_refs']);batch=state['batches'][op['batch_id']]
    if op['switched'] or op['state'] not in ('NEW_VERIFIED','OLD_BASELINES_RECHECKED'):fail('GROUP_PHASE_CONFLICT')
    _fresh(op,['NEW']+['OLD_PRE_SWITCH:'+str(i) for i in range(n)],p['epoch'],p['at_ms'])
    pool=state['pool']
    if p['expected_head']!=pool['head'] or p['expected_head']!=batch['expected_head']:fail('GROUP_POOL_CAS_CONFLICT')
    for old in op['old_refs']:
        source=pool['groups'].get(old['group_id'])
        if (source is None or source['generation']!=old['generation'] or source['row_version']!=old['row_version']
                or source['ref_sha']!=old['ref_sha']):fail('GROUP_POOL_CAS_CONFLICT')
        pool['generations'].append({'kind':'RETAINED_OLD','group':deepcopy(source),'operation_id':p['operation_id']})
        source['state']='MERGED_OLD_RETAINED';source['row_version']+=1
    plan=op['plan'];gid=plan['target_group_id'];prior=pool['groups'].get(gid)
    if not n and prior is not None:fail('GROUP_POOL_CAS_CONFLICT')
    members=[]
    for position,m in enumerate(plan['members']):
        article={k:m[k] for k in Article.__slots__}
        article.update(origin='LEGACY_REGISTERED',old_ref_sha=op['new_ref_sha'],old_position=position)
        members.append(article)
        state['active_members'][m['article_id']]={'group_id':gid,'version_sha':m['version_sha']}
    group={'binding_sha':state['binding_sha'],'group_id':gid,'created_seq':prior['created_seq'] if prior else
        max((g['created_seq'] for g in pool['groups'].values()),default=-1)+1,
        'generation':plan['target_generation'],'row_version':prior['row_version'] if prior else 1,
        'state':'FULL' if len(members)==8 else 'OPEN','ref_sha':op['new_ref_sha'],
        'members':members,'main_article_id':plan['main_article_id']}
    pool['groups'][gid]=group
    pool['generations'].append({'kind':'NEW_CURRENT','group':deepcopy(group),'operation_id':p['operation_id'],'proof_sha':p['proof_sha']})
    pool['generation']+=1
    pool['head']=digest({'previous':pool['head'],'generation':pool['generation'],'operation_id':p['operation_id'],'group':group})
    batch['expected_head']=pool['head'];op.update(switched=True,state='SWITCHED_OLD_RETAINED')

def _delete_claim(state,op,p):
    _closed(p,('operation_id','old_index','epoch','at_ms','request_sha'));sha(p['request_sha'])
    i=integer(p['old_index'],0,len(op['old_refs'])-1)
    if not op['switched'] or i!=op['cursor']:fail('GROUP_PHASE_CONFLICT')
    if _claim(op,'DELETE','DELETE:'+str(i)) is not None:fail('GROUP_CLAIM_ALREADY_CONSUMED')
    reserve=retirement_reserve(len(op['old_refs']),i,tuple(c['slot'] for c in _claims(op,'GET')))
    if reserve['arithmetic_state']!='ALLOCATED':fail(reserve['reason'])
    required=(['NEW','OLD_PRE_SWITCH:0'] if i==0 else ['NEW_REFRESH:'+str(i),'OLD_REFRESH:'+str(i)])
    _fresh(op,required,p['epoch'],p['at_ms'])
    if any(c['state'] in ('CONSUMED_UNKNOWN','UNKNOWN') for c in _claims(op,'DELETE')):fail('GROUP_RESULT_UNKNOWN')
    claim={'kind':'DELETE','slot':'DELETE:'+str(i),'ordinal':i+1,'old_index':i,
        'subject_sha':op['old_refs'][i]['ref_sha'],'epoch':p['epoch'],'at_ms':p['at_ms'],
        'request_sha':p['request_sha'],
        'state':'CONSUMED_UNKNOWN','outcome':None,'proof_sha':None,
        'id':digest({'binding_sha':state['binding_sha'],'operation_id':p['operation_id'],'kind':'DELETE','slot':'DELETE:'+str(i)})}
    op['claims'].append(claim);op['old_refs'][i]['state']='DELETE_ADMITTED';op['state']='RETIRING'

def _delete_result(op,p):
    _closed(p,('operation_id','claim_id','outcome','proof_sha','code'))
    sha(p['claim_id']);sha(p['proof_sha'])
    _enum(p['outcome'],('ACK_OK','UNKNOWN','KNOWN_REJECTED'))
    claim=next((c for c in _claims(op,'DELETE') if c['id']==p['claim_id']),None)
    if claim is None or claim['state']!='CONSUMED_UNKNOWN':fail('GROUP_PHASE_CONFLICT')
    if p['outcome']=='ACK_OK':
        if type(p['code']) is not int or p['code']!=0:fail('GROUP_DELETE_ACK_REQUIRED')
    elif p['code'] is not None:
        integer(p['code'],-2**31,2**31-1)
        if p['code']==0:fail()
    claim.update(state=p['outcome'],outcome=p['outcome'],proof_sha=p['proof_sha'],code=p['code'])
    op['old_refs'][claim['old_index']]['state']='DELETE_'+p['outcome']
    if p['outcome']!='ACK_OK':op['state']='UNKNOWN' if p['outcome']=='UNKNOWN' else 'HOLD'

def _recover_delete_ack(state,op,p):
    _closed(p,('operation_id','claim_id','archive'))
    sha(p['claim_id']);archive=p['archive']
    _closed(archive,('binding_sha','operation_id','claim_id','request_sha','subject_sha','proof_sha','response_code','origin'))
    for key in ('binding_sha','claim_id','request_sha','subject_sha','proof_sha'):sha(archive[key])
    claim=next((c for c in _claims(op,'DELETE') if c['id']==p['claim_id']),None)
    if claim is None:fail('GROUP_DELETE_ACK_REQUIRED')
    expected={'binding_sha':state['binding_sha'],'operation_id':p['operation_id'],
        'claim_id':claim['id'],'request_sha':claim['request_sha'],'subject_sha':claim['subject_sha'],
        'proof_sha':archive['proof_sha'],'response_code':0,'origin':'ORIGINAL_GROUP_DELETE_RESPONSE_ARCHIVE'}
    if not _same(archive,expected):fail('GROUP_DELETE_ACK_REQUIRED')
    if claim['state']=='ACK_OK':
        if claim['proof_sha']!=archive['proof_sha']:fail('GROUP_ARCHIVE_CONFLICT')
        return
    if claim['state'] not in ('CONSUMED_UNKNOWN','UNKNOWN'):fail('GROUP_PHASE_CONFLICT')
    claim.update(previous_unknown_proof_sha=claim['proof_sha'],state='ACK_OK',outcome='KNOWN_SUCCESS_ARCHIVE',
        proof_sha=archive['proof_sha'],code=0)
    i=claim['old_index'];old=op['old_refs'][i];old['state']='DELETE_ACK_OK'
    invalid=_claim(op,'GET','OLD_INVALID:'+str(i))
    if invalid is not None and invalid['outcome']=='INVALID_REF' and invalid['code']==40007:
        old['state']='INVALIDATED_OBSERVED';op['cursor']+=1
    op['state']='RETIRING'

def _finish(state,op,p):
    _closed(p,('operation_id','proof_sha','epoch','at_ms'));sha(p['proof_sha'])
    final=_claim(op,'GET','FINAL_NEW')
    if (not op['switched'] or final is None or final['state']!='OBSERVED' or final['outcome']!='MATCHED'
            or any(old['state']!='INVALIDATED_OBSERVED' for old in op['old_refs'])):fail('GROUP_FINAL_READ_REQUIRED')
    _fresh(op,['FINAL_NEW'],p['epoch'],p['at_ms'])
    for i in range(len(op['old_refs'])):
        delete=_claim(op,'DELETE','DELETE:'+str(i));invalid=_claim(op,'GET','OLD_INVALID:'+str(i))
        if (delete is None or delete['state']!='ACK_OK' or invalid is None or invalid['outcome']!='INVALID_REF'
                or invalid['code']!=40007):fail('GROUP_DELETE_ACK_REQUIRED')
        op['old_refs'][i].update(state='RETIREMENT_VERIFIED',reserved=False)
        gid=op['old_refs'][i]['group_id']
        if gid!=op['plan']['target_group_id']:state['pool']['groups'][gid]['state']='RETIRED_SOURCE'
    op.update(state='COMPLETE',completion_proof_sha=p['proof_sha'])
    for member in op['plan']['members']:state['queue'][member['article_id']]['state']='COMPLETE'
    batch=state['batches'][op['batch_id']]
    if op['ordinal']==len(batch['candidate']['children'])-1:batch['state']='COMPLETE'

def _reduce(previous,kind,p):
    _json(p)
    if kind=='PREVIEW':return _preview(None if previous is None else _clone(previous),p)
    if kind=='POOL':
        if previous is not None and previous['pool'] is not None:fail()
        _closed(p,('binding_sha','source_kind','groups','coverage','proof_sha'))
        groups=[_typed(g,PoolGroup).value() for g in p['groups']]
        coverage=_typed(p['coverage'],Coverage).value()
        result=_new_pool(p['binding_sha'],p['source_kind'],groups,coverage,p['proof_sha'])
        if previous is not None:
            if previous['binding_sha']!=p['binding_sha'] or previous['source_kind']!=p['source_kind']:fail()
            result.update(previews=previous['previews'],preview_grants=previous['preview_grants'])
        return result
    if previous is None:fail()
    state=_clone(previous)
    if kind=='PREVIEW_GRANT':_preview_grant(state,p);return state
    if kind=='PREVIEW_READ':_preview_read(state,p);return state
    if kind=='PREVIEW_READ_RESULT':_preview_read_result(state,p);return state
    if kind=='PREVIEW_SUBJECTS':_preview_subjects(state,p);return state
    if state['pool'] is None:fail('GROUP_POOL_NOT_INITIALIZED')
    if kind=='COVERAGE_REFRESH':
        _closed(p,('coverage','proof_sha'));sha(p['proof_sha'])
        coverage=_typed(p['coverage'],Coverage).value();pool=state['pool']
        if (coverage['binding_sha']!=state['binding_sha'] or coverage['pool_head_sha']!=pool['head']
                or coverage['pool_generation']!=pool['generation']):fail('GROUP_POOL_COVERAGE_HOLD')
        if any(b['state'] not in TERMINAL for b in state['batches'].values()):fail('GROUP_PARENT_ACTIVE')
        pool.update(coverage=coverage,coverage_proof_sha=p['proof_sha'])
        return state
    if kind=='PLAN':_plan(state,p);return state
    if kind=='CANCEL':
        _closed(p,('batch_id','proof_sha'));sha(p['proof_sha'])
        batch=state['batches'].get(p['batch_id'])
        if batch is None:fail('GROUP_BATCH_NOT_FOUND')
        if batch['state']=='COMPLETE':return state
        batch['cancelled']=True;residue=False
        for plan in batch['candidate']['children']:
            op=state['operations'][plan['operation_id']];op['cancelled']=True
            if _claims(op,'ADD') or _claims(op,'DELETE'):residue=True
            elif op['state']!='COMPLETE':
                op['state']='CANCELLED_BEFORE_ADMISSION'
                for old in op['old_refs']:old['reserved']=False
                for m in op['plan']['members']:state['queue'][m['article_id']]['state']='CANCELLED'
        batch['state']='CANCELLED_WITH_RESIDUE' if residue else 'CANCELLED_BEFORE_ADMISSION'
        return state
    if kind=='PROMOTE':
        _closed(p,('batch_id','expected_ordinal','expected_head','coverage_proof_sha'))
        sha(p['coverage_proof_sha']);sha(p['expected_head']);integer(p['expected_ordinal'])
        batch=state['batches'].get(p['batch_id'])
        if (batch is None or batch['cancelled'] or batch['next_ordinal']!=p['expected_ordinal']
                or batch['expected_head']!=p['expected_head'] or state['pool']['head']!=p['expected_head']):fail('GROUP_PROMOTION_CAS_CONFLICT')
        plans=batch['candidate']['children'];i=batch['next_ordinal']
        if i+1>=len(plans) or state['operations'][plans[i]['operation_id']]['state']!='COMPLETE':fail('GROUP_PHASE_CONFLICT')
        nxt=state['operations'][plans[i+1]['operation_id']]
        if nxt['state']!='WAITING':fail('GROUP_PHASE_CONFLICT')
        batch['next_ordinal']+=1;batch['state']='ACTIVE';nxt['state']='PLANNED'
        return state
    _json(p)
    op,batch=_current_child(state,p.get('operation_id'),allow_cancelled=kind in ('GET_RESULT','ADD_RESULT','DELETE_RESULT','DELETE_ARCHIVE_ACK','ADD_UNKNOWN'),
        allow_cancelled_terminal=kind=='GET_RESULT')
    cancelled_before_admission=op['cancelled'] and op['state']=='CANCELLED_BEFORE_ADMISSION'
    if kind in ('GET_CLAIM','ADD_CLAIM','SWITCH','DELETE_CLAIM','COMPLETE'):
        _require_read_safety(op)
    if kind=='GET_CLAIM':_get_claim(state,op,p)
    elif kind=='GET_RESULT':_get_result(op,p)
    elif kind=='ADD_CLAIM':_add_claim(state,op,p)
    elif kind=='ADD_RESULT':
        ref_sha=_ref_sha(p['result']['reference'])
        if (any(g['ref_sha']==ref_sha for g in state['pool']['groups'].values())
                or any(o is not op and o['new_ref_sha']==ref_sha for o in state['operations'].values())):
            fail('GROUP_REFERENCE_REUSED')
        _add_result(op,p)
    elif kind=='ADD_UNKNOWN':
        _closed(p,('operation_id','proof_sha'));sha(p['proof_sha'])
        claim=_claim(op,'ADD','ADD')
        if claim is None or claim['state']!='CONSUMED_UNKNOWN':fail()
        claim.update(state='UNKNOWN',outcome='UNKNOWN',proof_sha=p['proof_sha']);op['state']='UNKNOWN'
    elif kind=='SWITCH':_switch(state,op,p)
    elif kind=='DELETE_CLAIM':_delete_claim(state,op,p)
    elif kind=='DELETE_RESULT':_delete_result(op,p)
    elif kind=='DELETE_ARCHIVE_ACK':_recover_delete_ack(state,op,p)
    elif kind=='COMPLETE':_finish(state,op,p)
    else:fail()
    if cancelled_before_admission:op['state']='CANCELLED_BEFORE_ADMISSION'
    elif _sticky_read_failure(op) is not None:op['state']='HOLD'
    if not batch['cancelled']:
        if op['state'] in ('HOLD','UNKNOWN'):batch['state']=op['state']
        elif batch['state'] not in TERMINAL:batch['state']='ACTIVE'
    return state

def _projection_rows(state,seq,head):
    account=state['binding_sha'];raw=canonical(state)
    rows={'group_pools':[(account,state['source_kind'],seq,head,raw,digest(state))],
        'group_batches':[],'group_operations':[],'group_operation_old_refs':[],
        'group_member_origins':[],'group_active_members':[],'group_queue':[],
        'group_claims':[],'group_own_step_links':[]}
    rows.update(group_previews=[],group_preview_read_grants=[],group_preview_read_claims=[])
    for pid,preview in state['previews'].items():
        rows['group_previews'].append((account,pid,preview['input_sha'],preview['request_key'],canonical(preview),digest(preview)))
    for gid,grant in state['preview_grants'].items():
        reg=grant['registration']
        rows['group_preview_read_grants'].append((account,gid,reg['source_grant_sha'],reg['phase'],reg['scope_sha'],reg['list_cap'],reg['get_cap'],canonical(grant),digest(grant)))
        for claim in grant['claims']:
            rows['group_preview_read_claims'].append((account,claim['id'],gid,claim['preview_id'],claim['api'],claim['ordinal'],claim['state'],canonical(claim),digest(claim)))
    for bid,b in state['batches'].items():
        rows['group_batches'].append((account,bid,b['candidate']['request_key'],b['state'],b['next_ordinal'],canonical(b),digest(b)))
    for oid,o in state['operations'].items():
        plan=o['plan']
        rows['group_operations'].append((account,oid,o['batch_id'],o['ordinal'],plan['child_key'],o['state'],int(o['cancelled']),canonical(o),digest(o)))
        for old in o['old_refs']:
            rows['group_operation_old_refs'].append((account,oid,old['old_index'],old['ref_sha'],int(old['reserved']),old['state'],canonical(old),digest(old)))
        for m in plan['members']:
            rows['group_member_origins'].append((account,oid,m['target_position'],m['article_id'],m['source_old_index'],m['old_position'],canonical(m),digest(m)))
        for c in o['claims']:
            rows['group_claims'].append((account,c['id'],oid,c['kind'],c['slot'],c['ordinal'],c['state'],canonical(c),digest(c)))
        if o['own_link'] is not None:
            link=o['own_link'];claim=_claim(o,'ADD','ADD')
            rows['group_own_step_links'].append((account,oid,claim['id'],o['expected_own_step_id'],canonical(link),digest(link)))
    for aid,m in state['active_members'].items():
        rows['group_active_members'].append((account,aid,m['group_id'],m['version_sha']))
    for aid,q in state['queue'].items():
        rows['group_queue'].append((account,aid,q['version_sha'],q['batch_id'],q['operation_id'],q['state'],canonical(q),digest(q)))
    return rows

def _verify_links(db,state,*,pending_archive=None):
    for op in state['operations'].values():
        if op['own_link'] is None:
            if op['expected_own_step_id'] is not None or _claims(op,'ADD'):fail('GROUP_OWN_STEP_LINK_HOLD')
            continue
        row=db.execute('SELECT * FROM own_steps WHERE id=?',(op['expected_own_step_id'],)).fetchone()
        if row is None or not _same(_rowpin(row),op['own_link']['step_pin']):fail('GROUP_OWN_STEP_LINK_HOLD')
        intent=json.loads(row['intent'])
        if digest(intent)!=row['intent_digest'] or digest(intent.get('binding'))!=state['binding_sha']:
            fail('GROUP_OWN_STEP_LINK_HOLD')
        if any(row[k]!=intent['binding'][k] for k in ('tenant','principal','connection','resource')):
            fail('GROUP_OWN_STEP_LINK_HOLD')
        if row['operation']!='add' or row['slot']!='draft' or row['manifest_digest']!=op['own_link']['manifest_sha']:fail('GROUP_OWN_STEP_LINK_HOLD')
        if op['add_result'] is None:
            if (pending_archive is not None and row['id']==pending_archive['step_id']):
                result=json.loads(row['result'])
                if (row['state']!='SUCCEEDED' or not _same(result,pending_archive['result'])
                        or digest(result)!=row['result_digest']):fail('GROUP_ARCHIVE_REQUIRED')
            elif row['state']!='RESULT_UNKNOWN' or row['result']!='{}':fail('GROUP_ARCHIVE_REQUIRED')
        else:
            result=json.loads(row['result'])
            if (row['state']!='SUCCEEDED' or not _same(result,op['add_result']['result'])
                    or digest(result)!=row['result_digest'] or _ref_sha(result['reference'])!=op['new_ref_sha']):
                fail('GROUP_OWN_STEP_LINK_HOLD')

def _load_unchecked(db,account,*,pending_archive=None):
    sha(account);stored=db.execute('SELECT * FROM group_pools WHERE account_key=?',(account,)).fetchone()
    if stored is None:return None,None,None
    state=None;seq=0;head=ZERO
    for row in db.execute('SELECT * FROM group_events WHERE account_key=? ORDER BY seq',(account,)):
        seq+=1
        if row['seq']!=seq or row['previous_sha']!=head:fail()
        payload=json.loads(row['payload']);_json(payload)
        if canonical(payload)!=row['payload']:fail()
        event={'account_key':account,'seq':seq,'kind':row['kind'],'payload':payload,'previous_sha':head}
        if digest(event)!=row['event_sha']:fail()
        state=_reduce(state,row['kind'],payload);head=row['event_sha']
        if state['binding_sha']!=account:fail()
    if state is None or seq!=stored['seq'] or head!=stored['head']:fail()
    expected=_projection_rows(state,seq,head)
    for table,rows in expected.items():
        actual=[tuple(row) for row in db.execute('SELECT * FROM '+table+' WHERE account_key=?',(account,))]
        if sorted(actual,key=canonical)!=sorted(rows,key=canonical):fail('GROUP_PROJECTION_UNVERIFIED')
    _verify_links(db,state,pending_archive=pending_archive)
    return state,seq,head

def _load(db,account,*,pending_archive=None):
    try:return _load_unchecked(db,account,pending_archive=pending_archive)
    except WCEError:raise
    except Exception:fail()

def check_records9(db,source_kind,history_policy=None, *, history_locators=None):
    if history_policy is None:
        from .draft_group_read_family_store import resolve_history_policy
        history_policy=resolve_history_policy(db)
    """Read-only integrity/link replay; never verifies a pure dict as a grant.

    Legacy row/proof validators and the marker bridge run in the caller's full
    schema9 check. This leaf does not recurse into OwnStore.check or repair data.
    """
    try:
        _enum(source_kind,('SYNTHETIC_SETUP','OPERATOR_ATTESTED'));_check_group_layout(db)
        accounts=[row[0] for row in db.execute('SELECT account_key FROM group_pools')]
        for account in accounts:
            state,_,_=_load(db,account)
            if state['source_kind']!=source_kind:fail()
        # FK checks must include orphan materialized/events rows, not just pools.
        for table in ('group_events','group_batches','group_operations','group_operation_old_refs',
                'group_member_origins','group_active_members','group_queue','group_claims','group_own_step_links',
                'group_previews','group_preview_read_grants','group_preview_read_claims'):
            if db.execute('SELECT 1 FROM '+table+' LEFT JOIN group_pools USING(account_key) WHERE group_pools.account_key IS NULL').fetchone():fail()
        if db.execute('PRAGMA foreign_key_check').fetchone():fail()
        from .draft_group_read_family_store import check_family_records_in
        states={a:_load(db,a) for a in accounts}
        check_family_records_in(db,states,history_policy)
        from .draft_group_source_review import check_source_review_records_in
        check_source_review_records_in(db,states,history_policy)
        from .draft_group_source_facts import check_source_fact_records_in
        from .draft_group_token_attempt_store import check_token_records_in
        check_source_fact_records_in(db,states,history_policy)
        check_token_records_in(db,states,history_policy)
        from .draft_group_target_scope import check_target_designations_in
        from .draft_group_parent import check_parent_records_in
        from .draft_group_response_history import check_group_response_records_in
        check_target_designations_in(db,states,history_policy, history_locators=history_locators)
        check_parent_records_in(db,states,history_policy, history_locators=history_locators)
        check_group_response_records_in(db,states,history_policy, history_locators=history_locators)
    except WCEError:raise
    except Exception:fail()

def _write_projection(db,state,seq,head):
    rows=_projection_rows(state,seq,head);account=state['binding_sha']
    pool=rows.pop('group_pools')[0]
    db.execute('INSERT INTO group_pools VALUES(?,?,?,?,?,?) ON CONFLICT(account_key) DO UPDATE SET source_kind=excluded.source_kind,seq=excluded.seq,head=excluded.head,value=excluded.value,value_sha=excluded.value_sha',pool)
    for table in ('group_preview_read_claims','group_preview_read_grants','group_previews','group_own_step_links','group_claims','group_member_origins','group_operation_old_refs',
            'group_operations','group_queue','group_active_members','group_batches'):
        db.execute('DELETE FROM '+table+' WHERE account_key=?',(account,))
    for table in ('group_batches','group_operations','group_operation_old_refs','group_member_origins',
            'group_active_members','group_queue','group_claims','group_own_step_links',
            'group_previews','group_preview_read_grants','group_preview_read_claims'):
        for row in rows[table]:
            db.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in row)+')',row)

def _event(db,account,kind,payload, *, history_locators=None):
    _tx(db);_json(payload)
    before,seq,head=_load(db,account);seq=0 if seq is None else seq;head=ZERO if head is None else head
    from .draft_group_read_family_store import before_event_in
    before_event_in(db,account,kind,payload)
    from .draft_group_source_review import source_review_before_event_in
    source_review_before_event_in(db,account,kind,payload)
    from .draft_group_source_facts import before_event_in as source_before_event_in
    from .draft_group_token_attempt_store import token_before_event_in
    source_before_event_in(db,account,kind,payload, history_locators=history_locators)
    token_before_event_in(db,account,kind,payload, history_locators=history_locators)
    from .draft_group_target_scope import target_before_event_in
    from .draft_group_parent import before_event_in as parent_before_event_in
    target_before_event_in(db,account,kind,payload)
    parent_before_event_in(db,account,kind,payload, history_locators=history_locators)
    return _append_event(db,account,before,seq,head,kind,payload, history_locators=history_locators)

def _append_event(db,account,before,seq,head,kind,payload, *, history_locators=None):
    try:after=_reduce(before,kind,payload)
    except CandidateError:fail('GROUP_VALUE_INVALID')
    event={'account_key':account,'seq':seq+1,'kind':kind,'payload':payload,'previous_sha':head}
    checksum=digest(event)
    _write_projection(db,after,seq+1,checksum)
    db.execute('INSERT INTO group_events VALUES(?,?,?,?,?,?)',(account,seq+1,kind,canonical(payload),head,checksum))
    _verify_links(db,after)
    from .draft_group_target_scope import target_after_event_in
    if target_after_event_in(db,account=account,kind=kind,payload=payload):
        # Only the fixed issued D scope can enter this SQL-only gap. Its caller
        # must immediately perform the original INSERT, then finish full history.
        # No file/current/source callback is allowed before that INSERT.
        return _clone(after)
    from .draft_group_read_family_store import after_event_in
    after_event_in(db)
    from .draft_group_source_review import source_review_after_event_in
    source_review_after_event_in(db,account=account,kind=kind,payload=payload)
    from .draft_group_source_facts import after_event_in as source_after_event_in
    from .draft_group_token_attempt_store import token_after_event_in
    source_after_event_in(db,account=account,kind=kind,payload=payload)
    token_after_event_in(db,account=account,kind=kind,payload=payload)
    from .draft_group_parent import after_event_in as parent_after_event_in
    parent_after_event_in(db,account=account,kind=kind,payload=payload, history_locators=history_locators)
    return _clone(after)

class GroupStore:
    """Private leaves. ``verify`` is trusted service code, not a user grant.

    verify(db, action, binding_sha, details) must freshly validate the actual
    full9 store, principal/scope/source/route, grant and proof files, writer-lock
    epoch and deadlines. Exact True is required. A synthetic True stub only
    exercises component logic; no object here can enable production by itself.
    Caller owns BEGIN IMMEDIATE/COMMIT/ROLLBACK and invokes no network in them.
    """
    def __init__(self,binding_sha,verify):
        sha(binding_sha)
        if not callable(verify):fail('GROUP_TRUSTED_VERIFIER_REQUIRED')
        self.binding_sha=binding_sha;self.verify=verify

    def _verify(self,db,action,details):
        _tx(db);_json(details)
        if self.verify(db,action,self.binding_sha,_clone(details)) is not True:fail('GROUP_AUTHORIZATION_REQUIRED')

    def initialize_pool_in(self,db,*,source_kind,groups,coverage,proof_sha, history_locators=None):
        if type(groups) is not tuple or any(type(g) is not PoolGroup for g in groups) or type(coverage) is not Coverage:fail()
        p={'binding_sha':self.binding_sha,'source_kind':source_kind,'groups':[g.value() for g in groups],
           'coverage':coverage.value(),'proof_sha':proof_sha}
        self._verify(db,'POOL_REGISTER',p)
        return _event(db,self.binding_sha,'POOL',p, history_locators=history_locators)

    def plan_in(self,db,candidate,*,articles,groups,coverage,legacy=None,execution, history_locators=None):
        if (type(articles) is not tuple or any(type(a) is not Article for a in articles)
                or type(groups) is not tuple or any(type(g) is not PoolGroup for g in groups)
                or type(coverage) is not Coverage or (legacy is not None and type(legacy) is not LegacyMerge)):fail()
        p={'candidate':candidate,'articles':[a.value() for a in articles],'groups':[g.value() for g in groups],
            'coverage':coverage.value(),'legacy':None if legacy is None else legacy.value(),'execution':execution}
        self._verify(db,'PLAN_EXACT_PARENT',p)
        current,_,_=_load(db,self.binding_sha)
        if current is None or current['pool'] is None:fail('GROUP_POOL_NOT_INITIALIZED')
        if candidate['batch_id'] in current['batches']:
            try:_plan(_clone(current),p)  # Validate immutable duplicate bindings.
            except CandidateError:fail('GROUP_VALUE_INVALID')
            return current
        return _event(db,self.binding_sha,'PLAN',p, history_locators=history_locators)

    def status(self,db,operation_id=None,*,history_policy=None, history_locators=None):
        """Journal status plus fixed historical integrity reads; no migration or rights."""
        _check_group_layout(db)
        row=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if row is None:fail()
        check_records9(db,row[0],history_policy, history_locators=history_locators)
        state,_,_=_load(db,self.binding_sha)
        if state is None:return {'state':'NOT_FOUND','authority':'NONE'}
        if operation_id is None:return _clone(state)
        op=state['operations'].get(identifier(operation_id))
        if op is None:return {'state':'NOT_FOUND','authority':'NONE'}
        used={k:len(_claims(op,k)) for k in ('GET','ADD','DELETE')}
        return {'state':op['state'],'cancelled':op['cancelled'],'operation_id':operation_id,
            'counts':used,'budget':_clone(op['plan']['budget']),'cursor':op['cursor'],
            'new_ref_sha':op['new_ref_sha'],'old_refs':_clone(op['old_refs']),
            'authority':'NONE_JOURNAL_ONLY','platform_verified':False}

    def _command(self,db,kind,p, *, history_locators=None):
        self._verify(db,kind,p)
        return _event(db,self.binding_sha,kind,p, history_locators=history_locators)

    def register_preview_in(self,db,preview_id,*,source_kind,input_sha,request_key,scope_sha,candidate,evidence_sha, history_locators=None):
        return self._command(db,'PREVIEW',dict(binding_sha=self.binding_sha,source_kind=source_kind,
            preview_id=preview_id,input_sha=input_sha,request_key=request_key,scope_sha=scope_sha,candidate=candidate,evidence_sha=evidence_sha), history_locators=history_locators)

    def refresh_coverage_in(self,db,coverage,*,proof_sha, history_locators=None):
        """Only fresh externally verified coverage of the unchanged current pool.

        Does not self-sign ACCOUNT coverage or enroll/overwrite outside objects.
        An externally changed group requires a separate reviewed enrollment or
        drift/HOLD contract, not this leaf pretending its old projection current.
        """
        if type(coverage) is not Coverage:fail()
        return self._command(db,'COVERAGE_REFRESH',dict(coverage=coverage.value(),proof_sha=proof_sha), history_locators=history_locators)

    def register_preview_read_grant_in(self,db,*,source_grant_sha,phase,scope_sha,subjects,list_cap,get_cap, history_locators=None):
        p=dict(source_grant_sha=source_grant_sha,phase=phase,scope_sha=scope_sha,subjects=subjects,list_cap=list_cap,get_cap=get_cap)
        self._command(db,'PREVIEW_GRANT',p, history_locators=history_locators)
        return digest({'binding_sha':self.binding_sha,'source_grant_sha':source_grant_sha,'phase':phase,'scope_sha':scope_sha})

    def claim_preview_read_in(self,db,grant_id,preview_id,api,*,request_sha,epoch,at_ms, history_locators=None):
        state=self._command(db,'PREVIEW_READ',dict(grant_id=grant_id,preview_id=preview_id,api=api,request_sha=request_sha,epoch=epoch,at_ms=at_ms), history_locators=history_locators)
        return _clone(state['preview_grants'][grant_id]['claims'][-1])

    def observe_preview_read_in(self,db,grant_id,claim_id,*,outcome,proof_sha, history_locators=None):
        return self._command(db,'PREVIEW_READ_RESULT',dict(grant_id=grant_id,claim_id=claim_id,outcome=outcome,proof_sha=proof_sha), history_locators=history_locators)

    def bind_discovery_subjects_in(self,db,grant_id,*,subjects,proof_sha, history_locators=None):
        return self._command(db,'PREVIEW_SUBJECTS',dict(grant_id=grant_id,subjects=subjects,proof_sha=proof_sha), history_locators=history_locators)

    def claim_get_in(self,db,operation_id,slot,*,epoch,at_ms,request_sha, history_locators=None):
        result=self._command(db,'GET_CLAIM',{'operation_id':operation_id,'slot':slot,'epoch':epoch,'at_ms':at_ms,'request_sha':request_sha}, history_locators=history_locators)
        return _clone(result['operations'][operation_id]['claims'][-1])

    def observe_get_in(self,db,operation_id,claim_id,*,outcome,proof_sha,snapshot_sha=None,code=None,at_ms, history_locators=None):
        return self._command(db,'GET_RESULT',dict(operation_id=operation_id,claim_id=claim_id,outcome=outcome,
            proof_sha=proof_sha,snapshot_sha=snapshot_sha,code=code,at_ms=at_ms), history_locators=history_locators)

    def switch_in(self,db,operation_id,*,expected_head,epoch,at_ms,proof_sha, history_locators=None):
        return self._command(db,'SWITCH',dict(operation_id=operation_id,expected_head=expected_head,epoch=epoch,at_ms=at_ms,proof_sha=proof_sha), history_locators=history_locators)

    def claim_delete_in(self,db,operation_id,old_index,*,epoch,at_ms,request_sha, history_locators=None):
        result=self._command(db,'DELETE_CLAIM',dict(operation_id=operation_id,old_index=old_index,epoch=epoch,at_ms=at_ms,request_sha=request_sha), history_locators=history_locators)
        return _clone(result['operations'][operation_id]['claims'][-1])

    def observe_delete_in(self,db,operation_id,claim_id,*,outcome,proof_sha,code=None, history_locators=None):
        return self._command(db,'DELETE_RESULT',dict(operation_id=operation_id,claim_id=claim_id,outcome=outcome,proof_sha=proof_sha,code=code), history_locators=history_locators)

    def recover_delete_ack_in(self,db,operation_id,claim_id,*,archive, history_locators=None):
        """Caller verifies the original same-stack durable capture, never resends.

        Descriptor consistency alone is not proof or permission. The trusted
        verifier must inspect the actual original archive/file+dir durability,
        request/response and exact historical claim, even after cancellation.
        """
        return self._command(db,'DELETE_ARCHIVE_ACK',dict(operation_id=operation_id,claim_id=claim_id,archive=archive), history_locators=history_locators)

    def complete_in(self,db,operation_id,*,proof_sha,epoch,at_ms, history_locators=None):
        return self._command(db,'COMPLETE',dict(operation_id=operation_id,proof_sha=proof_sha,epoch=epoch,at_ms=at_ms), history_locators=history_locators)

    def promote_in(self,db,batch_id,*,expected_ordinal,expected_head,coverage_proof_sha, history_locators=None):
        return self._command(db,'PROMOTE',dict(batch_id=batch_id,expected_ordinal=expected_ordinal,expected_head=expected_head,coverage_proof_sha=coverage_proof_sha), history_locators=history_locators)

    def cancel_in(self,db,batch_id,*,proof_sha, history_locators=None):
        # The trusted cancel source is checked, not a new remote permission.
        return self._command(db,'CANCEL',dict(batch_id=batch_id,proof_sha=proof_sha), history_locators=history_locators)

    def add_unknown_in(self,db,operation_id,*,proof_sha, history_locators=None):
        return self._command(db,'ADD_UNKNOWN',dict(operation_id=operation_id,proof_sha=proof_sha), history_locators=history_locators)

    def admit_add_in(self,db,operation_id,*,epoch,at_ms,admit_own_step, history_locators=None):
        """One callback in the same DB transaction, never ordinary-save recursion.

        callback(db) -> (row, request, cached, manifest, manifest_digest), using
        root's private equivalently-extracted own workflow leaf. It may not
        commit, start transactions, perform file writes or network. Integration
        must use the fixed reviewed callback, not a model-supplied callable.
        Only new-row current-stack request can later be sent. A stored/cached
        link is queried without invoking callback, and grants no resend owner.
        """
        p=dict(operation_id=operation_id,epoch=epoch,at_ms=at_ms)
        self._verify(db,'ADD_ADMIT',p)
        state,_,_=_load(db,self.binding_sha);op,batch=_current_child(state,operation_id)
        if op['own_link'] is not None:
            _verify_links(db,state)
            row=db.execute('SELECT * FROM own_steps WHERE id=?',(op['expected_own_step_id'],)).fetchone()
            return {'cached':True,'send_allowed':False,'operation_id':operation_id,
                'claim_id':_claim(op,'ADD','ADD')['id'],'step_pin':_rowpin(row),'request':None}
        # Validate state and freshness before invoking the trusted admission leaf.
        probe=_clone(state);fake={'step_pin':{k:'synthetic-probe' for k in _PIN_FIELDS},'request_sha':ZERO,'manifest_sha':ZERO}
        fake['step_pin'].update(operation='add',slot='draft',created=1.0)
        _add_claim(probe,probe['operations'][operation_id],dict(p,link=fake))
        before_ids={r[0] for r in db.execute('SELECT id FROM own_steps')}
        if not callable(admit_own_step):fail('GROUP_TRUSTED_ADMISSION_REQUIRED')
        token=_ADMITTING.set((id(db),self.binding_sha,operation_id))
        try:row,request,cached,manifest,manifest_digest=admit_own_step(db)
        finally:_ADMITTING.reset(token)
        if not db.in_transaction:fail('GROUP_TRANSACTION_REQUIRED')
        if cached is not None:fail('GROUP_UNLINKED_CACHED_STEP')
        actual=db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone()
        if actual is None or row['id'] in before_ids or not _same(dict(row),dict(actual)):fail('GROUP_OWN_STEP_LINK_HOLD')
        if actual['state']!='RESULT_UNKNOWN' or actual['result']!='{}':fail('GROUP_OWN_STEP_LINK_HOLD')
        _json(manifest);sha(manifest_digest)
        if digest(manifest)!=manifest_digest or actual['manifest_digest']!=manifest_digest:fail('GROUP_OWN_STEP_LINK_HOLD')
        from .http_transport import HTTPRequest
        if type(request) is not HTTPRequest or type(request.body) is not bytes:fail('GROUP_TRUSTED_ADMISSION_REQUIRED')
        link={'step_pin':_rowpin(actual),'request_sha':_sha256(request.body).hexdigest(),'manifest_sha':manifest_digest}
        result=_event(db,self.binding_sha,'ADD_CLAIM',dict(p,link=link), history_locators=history_locators);claim=_claim(result['operations'][operation_id],'ADD','ADD')
        return {'cached':False,'send_allowed':False,'operation_id':operation_id,'claim_id':claim['id'],
            'step_pin':link['step_pin'],'request':request,
            'dispatch_requirement':'ONLY_ORIGINAL_HOST_STACK_AFTER_COMMIT_AND_FRESH_GATE'}


def check_writer(db,binding_sha,*,operation_id=None):
    """No broad skip flag. The ordinary writer holds if any parent is pending.

    A private group admission caller can identify its exact queue-head operation
    in this transaction. That narrow result is not a send or policy grant.
    """
    _tx(db);state,_,_=_load(db,binding_sha)
    if state is None:return
    pending=[b for b in state['batches'].values() if b['state'] not in TERMINAL]
    if not pending:return
    active=_ADMITTING.get()
    if active is None or active[:2]!=(id(db),binding_sha):fail('GROUP_WRITER_ACTIVE')
    if operation_id is None:operation_id=active[2]
    if active!=(id(db),binding_sha,operation_id):fail('GROUP_WRITER_ACTIVE')
    op,b=_current_child(state,operation_id)
    if b is not pending[0] or op['state'] not in ('PLANNED','BASELINES_OBSERVED'):fail('GROUP_WRITER_ACTIVE')

def _account_writer_states(db,history_policy=None, *, history_locators=None):
    """Read only THIS caller's transaction; never OwnStore recursion or repair.

    The caller retains its original complete resource/history/authority checks.
    This additional account-wide check cannot treat another identity's pending
    pool, a broken replay or old-version migration remnants as an empty account.
    """
    if not isinstance(db,sqlite3.Connection) or not db.in_transaction:fail('GROUP_TRANSACTION_REQUIRED')
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if type(version) is not int or version not in (4,5,6,7,8,9):fail('GROUP_SCHEMA_UNVERIFIED')
    if version<9:
        # Preserve trusted maintenance rollback semantics: original checkpoint
        # and ROLLED_BACK marker stay in place. These fixed low-level leaves
        # distinguish them from PREPARED, COMMITTED-on-old-DB or broken proof;
        # neither leaf re-enters OwnStore or grants a write.
        from .own_group_schema import check_pending
        from .own_group_prerequisite import check_pending as check_prerequisite
        try:check_pending(db);check_prerequisite(db)
        except WCEError:raise
        except Exception:fail('GROUP_SCHEMA_UNVERIFIED')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'group_*'").fetchone():fail('GROUP_SCHEMA_UNVERIFIED')
        return ()
    _tx(db)
    row=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
    if row is None:fail('GROUP_SCHEMA_UNVERIFIED')
    _enum(row[0],('SYNTHETIC_SETUP','OPERATOR_ATTESTED'))
    check_records9(db,row[0],history_policy, history_locators=history_locators)
    return tuple(_load(db,row[0])[0] for row in db.execute('SELECT account_key FROM group_pools ORDER BY account_key'))

def check_account_writer(db,*,history_policy=None, history_locators=None):
    """Strict new input/approval/special claim/send barrier. No ADD exception."""
    for state in _account_writer_states(db,history_policy, history_locators=history_locators):
        if any(b['state'] not in TERMINAL for b in state['batches'].values()):fail('GROUP_WRITER_ACTIVE')

@contextmanager
def _workflow_add_check(db,binding,manifest):
    """Fixed original _admit_step_in ADD/draft SQL leaf only; no send owner.

    Even this scope requires cbe's exact _ADMITTING on the SAME connection.
    NEW_INPUT and NEW_APPROVAL never consult it. It cannot survive COMMIT or
    bypass a second pool, current_id, cancellation, old gates or final send.
    """
    active=_ADMITTING.get()
    if active is None or active[0]!=id(db):
        # Ordinary ADD keeps its original accepted manifest domain and errors;
        # Group JSON bounds are not a new ordinary-input restriction.
        yield
        return
    _json(binding);_json(manifest)
    entry=(db,digest(binding),digest(manifest))
    token=_WORKFLOW_ADD.set(entry)
    try:yield
    finally:_WORKFLOW_ADD.reset(token)

def check_workflow_writer(db,binding,manifest,current_id=None,*,history_policy=None, history_locators=None):
    states=_account_writer_states(db,history_policy, history_locators=history_locators)
    for state in states:
        if not any(b['state'] not in TERMINAL for b in state['batches'].values()):continue
        entry=_WORKFLOW_ADD.get()
        if (current_id is not None or entry is None or entry[0] is not db
                or type(binding) is not dict or type(manifest) is not dict
                or entry[1]!=digest(binding) or entry[2]!=digest(manifest)
                or state['binding_sha']!=entry[1]):fail('GROUP_WRITER_ACTIVE')
        check_writer(db,entry[1])

def _linked_state(db,step, *, history_locators=None):
    _tx(db)
    links=db.execute('SELECT account_key,operation_id FROM group_own_step_links WHERE step_id=?',(step['id'],)).fetchall()
    # Full replay catches a missing link even on an ordinary archive's early return.
    states=_account_writer_states(db, history_locators=history_locators)
    found=None
    for state in states:
        for oid,op in state['operations'].items():
            if op['expected_own_step_id']==step['id']:
                if found is not None:fail('GROUP_OWN_STEP_LINK_HOLD')
                found=(state,oid,op)
    if found is None:
        if links:fail('GROUP_OWN_STEP_LINK_HOLD')
        return None
    if len(links)!=1 or tuple(links[0])!=(found[0]['binding_sha'],found[1]):fail('GROUP_OWN_STEP_LINK_HOLD')
    if not _same(_rowpin(step),found[2]['own_link']['step_pin']):fail('GROUP_OWN_STEP_LINK_HOLD')
    return found

def verify_existing_own_step_result(db,step,*,archive_proof_sha,result, history_locators=None):
    """Archive caller has already validated and fsynced its original file proof."""
    sha(archive_proof_sha);_json(result)
    linked=_linked_state(db,step, history_locators=history_locators)
    if linked is None:return False
    _,oid,op=linked
    p={'operation_id':oid,'step_pin':_rowpin(step),'archive_proof_sha':archive_proof_sha,'result':result}
    if op['add_result'] is None or not _same(op['add_result'],p):fail('GROUP_ARCHIVE_REQUIRED')
    _add_result(_clone(op),p)
    return True

def observe_own_step_result(db,step,*,archive_proof_sha,result, history_locators=None):
    """Same transaction as own_steps RESULT_UNKNOWN→SUCCEEDED; no commit.

    Cannot call _load's cross-row final validator during the brief own/group
    split inside this transaction. Reconstruct with the old own row projection
    only for that exact linked step, then validate the final pair before return.
    """
    sha(archive_proof_sha);_json(result);_tx(db)
    links=db.execute('SELECT account_key,operation_id FROM group_own_step_links WHERE step_id=?',(step['id'],)).fetchall()
    if not links:
        # Ordinary path still validates all group integrity/missing expected links.
        if _linked_state(db,step, history_locators=history_locators) is not None:fail('GROUP_OWN_STEP_LINK_HOLD')
        return False
    if len(links)!=1:fail('GROUP_OWN_STEP_LINK_HOLD')
    account,oid=tuple(links[0])
    return _archive_event(db,account,oid,step,archive_proof_sha,result, history_locators=history_locators)

def _archive_event(db,account,oid,step,proof_sha,result, *, history_locators=None):
    current=db.execute('SELECT * FROM own_steps WHERE id=?',(step['id'],)).fetchone()
    if (current is None or not _same(_rowpin(current),_rowpin(step)) or current['state']!='SUCCEEDED'
            or not _same(json.loads(current['result']),result) or digest(result)!=current['result_digest']):
        fail('GROUP_OWN_STEP_LINK_HOLD')
    state,seq,head=_load(db,account,pending_archive={'step_id':step['id'],'result':result})
    op=_op(state,oid)
    p={'operation_id':oid,'step_pin':_rowpin(current),'archive_proof_sha':proof_sha,'result':result}
    if op['add_result'] is not None:
        verify_existing_own_step_result(db,current,archive_proof_sha=proof_sha,result=result, history_locators=history_locators)
        return True
    _append_event(db,account,state,seq,head,'ADD_RESULT',p, history_locators=history_locators)
    return True

