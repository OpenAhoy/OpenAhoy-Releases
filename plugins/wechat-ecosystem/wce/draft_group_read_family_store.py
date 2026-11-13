"""Durable FIRST/replay component. Does not qualify source, QA or human rights."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
from types import MethodType
import json,os,threading,time
from .contracts import WCEError
from .draft_group_contracts import canonical,digest
from .draft_group_input_files import _plain,_closed,_hash,_int,_enum,_canonical,hold
from .own_bootstrap_security import path_check
from .own_connection_policy import ConnectionPolicy
from .publication_contract import binding as publication_binding
from .publication_lock import _writer_guard,verify_pin
from . import draft_group_read_family_values as v
from .draft_group_read_family_files import FamilyFiles,FirstFiles,read_first_files,validate_pack,FOLDER

FIRST='GROUP_READ_FAMILY_ROOT_V1';ROUTE='GROUP_READ_ROUTE_DECISION_V1';ACT='GROUP_READ_PURPOSE_ACTIVATION_V1'
PROFILES=(FIRST,ROUTE,ACT)
_SEAL=object();_SCOPE=ContextVar('private_family_integrity_scope',default=None)
_ROOT_CURRENT=ContextVar('original_family_root_integrity_context',default=None)
_HISTORY_READER=ContextVar('fixed_family_history_evidence_reader',default=None)


def prepared_binding(policy,source_kind):
    d=policy.data
    return {'tenant':d['actor']['tenant_id'],'principal':d['actor']['principal_id'],'client':d['actor']['client_id'],'session':d['actor']['session_id'],'connection':d['connection_id'],'account':d['appid'],'resource':d['resource_id'],'epoch':d['epoch'],'generation':d['generation'],'source_kind':source_kind}


def _origin(value):
    _plain(value);_closed(value,('origin_request_identity_sha','origin_stable_owner','origin_prepared_binding_sha','origin_publication_binding_sha','origin_policy_identity_sha','origin_root_identity','origin_database_identity','origin_registry_parent_identity','origin_anchor_identity','source_evidence_sha'))
    for k in ('origin_request_identity_sha','origin_prepared_binding_sha','origin_publication_binding_sha','origin_policy_identity_sha','source_evidence_sha'):_hash(value[k])
    v._owner(value['origin_stable_owner'])
    for k in ('origin_root_identity','origin_database_identity','origin_registry_parent_identity','origin_anchor_identity'):
        if type(value[k]) is not list or len(value[k])!=2:hold()
        for x in value[k]:_int(x)
    return canonical(value).encode()

@dataclass(frozen=True,slots=True,init=False)
class _TransactionFence:
    """Read-only owned lifetime observation; never changes caller savepoints."""
    db:object=field(repr=False)
    thread:int
    generation:int
    active:bool
    poisoned:bool
    account:str
    other_heads:tuple=field(repr=False)
    def __init__(self,db,account):
        from .own_validation_scope import _transaction_marker
        generation=_transaction_marker(db)
        if generation is None:hold('GROUP_TRANSACTION_LIFETIME_UNPROVEN')
        for key,value in (('db',db),('thread',threading.get_ident()),('generation',generation),('active',True),('poisoned',False),('account',account)):object.__setattr__(self,key,value)
        object.__setattr__(self,'other_heads',self._other_heads())
    def _other_heads(self):
        return tuple(tuple(row) for row in self.db.execute('SELECT account_key,source_kind,seq,head,value_sha FROM group_pools WHERE account_key<>? ORDER BY account_key',(self.account,)))
    def fail(self,code='GROUP_SQL_SNAPSHOT_CHANGED'):
        object.__setattr__(self,'poisoned',True);hold(code)
    def check(self):
        from .own_validation_scope import _transaction_marker
        if (self.poisoned or not self.active or self.thread!=threading.get_ident()
            or _transaction_marker(self.db)!=self.generation):self.fail('GROUP_TRANSACTION_CHANGED')
        if self._other_heads()!=self.other_heads:self.fail()
    def close(self):
        object.__setattr__(self,'active',False)


def _sql_marker(db):
    # No guard/evidence callback and no change of baseline: read facts only.
    return (db.total_changes,tuple(db.execute('PRAGMA '+p).fetchone()[0] for p in
        ('data_version','schema_version','user_version','application_id','query_only')),
        tuple(tuple(row) for row in db.execute('SELECT account_key,source_kind,seq,head,value_sha FROM group_pools ORDER BY account_key')))


def _same_sql(closure,marker):
    closure.transaction.check()
    if _sql_marker(closure.db)!=marker:closure.transaction.fail()


@dataclass(frozen=True,slots=True)
class _RootClosure:
    seal:object=field(repr=False)
    db:object=field(repr=False)
    files:object=field(repr=False)
    origin_raw:bytes=field(repr=False)
    source_kind:str
    history_locators:object=field(repr=False)
    lock_guard:object=field(repr=False)
    thread:int
    transaction:object=field(repr=False)
    @property
    def active(self):return _ROOT_CURRENT.get() is self
    @property
    def authority(self):return False
    def current(self):
        if self.seal is not _SEAL or not self.active or self.thread!=threading.get_ident():hold('GROUP_ORIGINAL_ROOT_UNPROVEN')
        self.transaction.check();marker=_sql_marker(self.db)
        self.lock_guard();f=self.files;p=f.policy;o=json.loads(self.origin_raw)
        if (type(p) is not ConnectionPolicy or type(p.check) is not MethodType or p.check.__func__ is not ConnectionPolicy.check):hold()
        p.check(readonly=True)
        from .own_group_schema import _root
        from .own_store import OwnStore
        if (p.root!=_root(self.db) or self.db.execute('PRAGMA user_version').fetchone()[0]!=9
            or list(path_check(p.root,True))!=o['origin_root_identity'] or list(path_check(p.root/'state.sqlite3')[:2])!=o['origin_database_identity']
            or list(path_check(f.registry.parent,True))!=o['origin_registry_parent_identity'] or list(f.anchor_pin)!=o['origin_anchor_identity']
            or digest(p.data)!=o['origin_policy_identity_sha'] or publication_binding(p.data)!=o['origin_publication_binding_sha']
            or digest(prepared_binding(p,self.source_kind))!=o['origin_prepared_binding_sha']
            or {'tenant':p.data['actor']['tenant_id'],'principal':p.data['actor']['principal_id']}!=o['origin_stable_owner']):hold('GROUP_ORIGINAL_ROOT_UNPROVEN')
        verify_pin(f.publication,required=True)
        head=f.publication._head(allow_pending=False)
        if head['binding_sha']!=o['origin_publication_binding_sha']:hold()
        f.publication._verify_records_in(self.db,allow_pending=False)
        # Full9 invokes only the non-recursive structural family history leaf.
        OwnStore.check(self.db,self.source_kind,p,history=self.history_locators)
        self.lock_guard();f._pure_scope();_same_sql(self,marker)
        return self

@contextmanager
def original_root_scope(db,files,original_evidence,*,source_kind,historical_evidence=None, history_locators=None):
    """Physical/history integrity only. Evidence JSON never supplies authority."""
    if type(files) is not FamilyFiles:hold()
    from .draft_group_history_context import require_history
    require_history(files.policy,db,history_locators)
    _enum(source_kind,('SYNTHETIC_SETUP','OPERATOR_ATTESTED'));raw=_origin(original_evidence)
    if historical_evidence is not None and not callable(historical_evidence):hold()
    prior=_ROOT_CURRENT.get()
    if type(prior) is _RootClosure and prior.active and prior.db is db:prior.transaction.check();
    if type(prior) is _RootClosure and prior.active and prior.db is db and prior.history_locators is not history_locators:hold('GROUP_HISTORY_SCOPE_CHANGED')
    try:guard=_writer_guard(files.root,files.policy.data['appid'])
    except WCEError:
        # A read snapshot may acquire only existing actual shared lock FDs.
        if not db.in_transaction or db.execute('PRAGMA query_only').fetchone()[0]!=1:hold('GROUP_FAMILY_LOCK_REQUIRED')
        from .draft_group_local_reader import _readonly_locks
        with _readonly_locks(files.policy) as (_,current):
            fence=_TransactionFence(db,json.loads(raw)['origin_prepared_binding_sha'])
            closure=_RootClosure(_SEAL,db,files,raw,source_kind,history_locators,current,threading.get_ident(),fence)
            token=_ROOT_CURRENT.set(closure);history=_HISTORY_READER.set(historical_evidence)
            try:
                with files._observing():
                    closure.current();yield closure
                    if not fence.poisoned:closure.current()
            finally:_HISTORY_READER.reset(history);_ROOT_CURRENT.reset(token);fence.close()
    else:
        fence=_TransactionFence(db,json.loads(raw)['origin_prepared_binding_sha'])
        closure=_RootClosure(_SEAL,db,files,raw,source_kind,history_locators,guard,threading.get_ident(),fence)
        token=_ROOT_CURRENT.set(closure);history=_HISTORY_READER.set(historical_evidence)
        try:
            with files._observing():
                closure.current();yield closure
                if not fence.poisoned:closure.current()
        finally:_HISTORY_READER.reset(history);_ROOT_CURRENT.reset(token);fence.close()


def require_closure(closure,db,files):
    if type(closure) is not _RootClosure or closure.db is not db or closure.files is not files:hold('GROUP_ORIGINAL_ROOT_UNPROVEN')
    closure.current()

@contextmanager
def family_scope(db,files,root_closure,*,historical_evidence=None):
    require_closure(root_closure,db,files)
    if historical_evidence is not None and not callable(historical_evidence):hold()
    value=(db,files,root_closure,historical_evidence,threading.get_ident())
    token=_SCOPE.set(value)
    try:yield
    finally:_SCOPE.reset(token)


def _scope(db,*,required=True):
    x=_SCOPE.get()
    if x is None:
        if required:hold('GROUP_READ_FAMILY_REQUIRED')
        return None
    if type(x) is not tuple or len(x)!=5 or x[0] is not db or x[4]!=threading.get_ident() or not x[2].active:hold()
    x[2].transaction.check();x[2].lock_guard();x[1]._pure_scope()
    return x



def resolve_history_policy(db):
    from .draft_group_history_context import current_history_policy
    policy=current_history_policy(db)
    if policy is not None:return policy
    closure=_ROOT_CURRENT.get()
    if type(closure) is _RootClosure and closure.active and closure.db is db and closure.thread==threading.get_ident():
        closure.lock_guard()
        return closure.files.policy
    return None


def _states(db):
    from .draft_group_store import _load
    out={}
    for row in db.execute('SELECT account_key FROM group_pools ORDER BY account_key'):
        state,seq,head=_load(db,row[0]);out[row[0]]=(state,seq,head)
    return out



def check_pack_origin(pack,closure):
    validate_pack(pack);o=json.loads(closure.origin_raw);f=closure.files;r=pack.entry('family_root').value;p=pack.entry('first_proof').value
    expected_directory={'path_utf8_sha256':sha256(str(f.root).encode()).hexdigest(),'device':f.root_identity[0],'inode':f.root_identity[1],'owner_uid':os.getuid()}
    expected_coord={'platform_account_sha':f.publication.key,'anchor_identity':list(f.anchor_pin),'registry_parent_identity':list(f.parent_pin),'coordination_pin_sha':sha256(f.coord_raw).hexdigest()}
    from .draft_group_operator_source_codec import FIRST_PROOF_PROFILE
    source_field='operator_source_evidence_sha' if p['profile']==FIRST_PROOF_PROFILE else 'original_human_evidence_sha'
    if (r['request_identity_sha']!=o['origin_request_identity_sha'] or canonical(r['first_binding'])!=canonical(prepared_binding(f.policy,closure.source_kind))
        or canonical(r['first_directory'])!=canonical(expected_directory) or canonical(r['coordination'])!=canonical(expected_coord)
        or p[source_field]!=o['source_evidence_sha']):hold('GROUP_FIRST_ORIGIN_MISMATCH')


def _history_file_guard(policy):
    # Structural past evidence, never enabled/current-capability authorization.
    if type(policy) is not ConnectionPolicy:hold()
    if (path_check(policy.path)!=policy.pin or path_check(policy.root,True)!=policy.root_pin
        or path_check(policy.root/'images',True)!=policy.image_pin or path_check(policy.root/'state.sqlite3')[:2]!=policy.database_pin[:2]):hold()
    from .own_connection_registry import check_member
    check_member(policy,revocation=False,readonly=True)


def _first_candidate(pack):
    validate_pack(pack);w=pack.entry('request_witness');r=pack.entry('family_root');c=pack.entry('covenant');p=pack.entry('first_proof');rv=r.value
    return {'schema':1,'profile':FIRST,'authority':False,'request_identity_sha':w.key,'family_anchor_id':rv['family_anchor_id'],'platform_account_sha':w.value['platform_account_sha'],'stable_owner':c.value['stable_owner'],'family_root_sha':r.sha256,'request_witness_sha':w.sha256,'covenant_sha':c.sha256,'first_proof_sha':p.sha256,'first_binding_sha':digest(rv['first_binding']),'first_directory_sha':digest(rv['first_directory'])}


def _first_payload(pack,source_kind):
    c=_first_candidate(pack);a=c['family_anchor_id'];scope=digest({'profile':'GROUP_READ_FIRST_SCOPE_V1','family_anchor_id':a,'covenant_sha':c['covenant_sha']})
    return {'binding_sha':c['first_binding_sha'],'source_kind':source_kind,'preview_id':'group-read-family-'+a,'input_sha':c['covenant_sha'],'request_key':'group-read-first-'+a,'scope_sha':scope,'candidate':c,'evidence_sha':c['first_proof_sha']}


def _kind(preview):
    candidate=preview.get('candidate')
    return candidate.get('profile') if type(candidate) is dict and type(candidate.get('profile')) is str else None


def _purpose(c,purpose,ordinal):
    _enum(purpose,v.PURPOSES);_int(ordinal,0,63)
    found=[x for x in c['purposes'] if x['purpose']==purpose and x['ordinal']==ordinal]
    if len(found)!=1:hold('GROUP_READ_PURPOSE_OUTSIDE_FIRST')
    return found[0]


def _gid(binding,p):return digest({'binding_sha':binding,'source_grant_sha':p['source_grant_sha'],'phase':p['phase'],'scope_sha':p['scope_sha']})

def _registration(p,c):return {k:p[k] for k in ('source_grant_sha','phase','scope_sha','list_cap','get_cap')}|{'subjects':c['qualify_subjects'] if p['purpose']=='QUALIFY' else None}


def _firsts(states):
    return [(account,p) for account,(s,_,_) in states.items() for p in s['previews'].values() if _kind(p)==FIRST]


def _history_evidence(x,profile,candidate):
    # Root's fixed actual source/UI reader is separate; bools/dicts cannot pass.
    reader=x[3] if x is not None and x[3] is not None else _HISTORY_READER.get()
    if reader is None:hold('GROUP_FAMILY_HISTORY_EVIDENCE_REQUIRED')
    result=reader(profile,json.loads(canonical(candidate)))
    if type(result) is not bytes or sha256(result).hexdigest()!=candidate['evidence_sha']:hold('GROUP_FAMILY_HISTORY_EVIDENCE_INVALID')


def _validate_family(db,states,files,pack,*,evidence_scope=None):
    validate_pack(pack);expected=_first_payload(pack,pack.entry('family_root').value['first_binding']['source_kind']);a=expected['candidate']['family_anchor_id'];rid=pack.entry('request_witness').key;c=pack.entry('covenant').value
    firsts=[(account,p) for account,p in _firsts(states) if p['candidate'].get('request_identity_sha')==rid or p['candidate'].get('family_anchor_id')==a]
    if len(firsts)!=1 or canonical(firsts[0][1])!=canonical(expected) or firsts[0][0]!=expected['binding_sha']:hold('GROUP_FIRST_UNVERIFIED')
    account=firsts[0][0];state=states[account][0];route_id='group-read-route-'+a;route=state['previews'].get(route_id);decision=None
    if route is not None:
        decision=route['candidate'];_closed(decision,('schema','profile','authority','family_anchor_id','covenant_sha','route','snapshot_sha','capsule_sha','actual_child_count','execution_slot_shas','source_evidence_sha'))
        if type(decision['schema']) is not int or decision['schema']!=1 or decision['profile']!=ROUTE or type(decision['authority']) is not bool or decision['authority'] is not False:hold()
        _enum(decision['route'],c['allowed_routes']);_hash(decision['snapshot_sha']);_hash(decision['capsule_sha']);_hash(decision['source_evidence_sha'])
        count=_int(decision['actual_child_count'],1,c['child_bound']);v._seq(decision['execution_slot_shas'],_hash,count,count)
        branch=next(b for b in c['branches'] if b['route']==decision['route'])
        if decision['execution_slot_shas']!=[digest(s) for s in branch['execution_slots'][:count]] or decision['family_anchor_id']!=a or decision['covenant_sha']!=pack.entry('covenant').sha256:hold()
        if route['input_sha']!=pack.entry('covenant').sha256 or route['evidence_sha']!=decision['source_evidence_sha']:hold()
    activations={}
    for pid,preview in state['previews'].items():
        if _kind(preview)!=ACT:continue
        ac=preview['candidate'];_closed(ac,('schema','profile','authority','family_anchor_id','covenant_sha','purpose','ordinal','source_grant_sha','scope_sha','activation_kind','route_decision_sha','evidence_sha'))
        if ac['family_anchor_id']!=a:continue
        if type(ac['schema']) is not int or ac['schema']!=1 or ac['profile']!=ACT or type(ac['authority']) is not bool or ac['authority'] is not False:hold()
        p=_purpose(c,ac['purpose'],ac['ordinal']);_hash(ac['evidence_sha'])
        if (ac['covenant_sha']!=pack.entry('covenant').sha256 or ac['source_grant_sha']!=p['source_grant_sha'] or ac['scope_sha']!=p['scope_sha']
            or ac['activation_kind']!=p['activation']['kind'] or pid!='group-read-purpose-'+p['source_grant_sha'] or preview['scope_sha']!=p['scope_sha']
            or preview['input_sha']!=pack.entry('covenant').sha256 or preview['evidence_sha']!=ac['evidence_sha']):hold()
        if p['purpose'] in ('QUALIFY','PREVIEW_ACCOUNT'):
            if ac['route_decision_sha'] is not None:hold()
        else:
            if decision is None or ac['route_decision_sha']!=digest(decision):hold()
            if p['purpose']=='EXECUTION_INITIAL_ACCOUNT':
                if decision['route']!=v.ROUTES[1]:hold('GROUP_PURPOSE_INACTIVE')
                _history_evidence(evidence_scope,ACT,ac)
            elif p['ordinal']>=decision['actual_child_count']:hold('GROUP_PURPOSE_INACTIVE')
        activations[p['source_grant_sha']]=ac
    allowed={p['source_grant_sha']:p for p in c['purposes']};used={'LIST':0,'GET':0};unknown=False
    for pool,(s,_,_) in states.items():
        for grant in s['preview_grants'].values():
            p=allowed.get(grant['registration']['source_grant_sha'])
            if p is None:continue
            if pool!=account or grant['grant_id']!=_gid(account,p) or canonical(grant['registration'])!=canonical(_registration(p,c)) or p['source_grant_sha'] not in activations:hold('GROUP_CROSS_POOL_LEDGER_CONFLICT')
            for claim in grant['claims']:
                if claim['preview_id']!='group-read-purpose-'+p['source_grant_sha']:hold()
                used[claim['api']]+=1
                if claim['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED'):unknown=True
    return {'account':account,'first':expected,'covenant':c,'route':decision,'activations':activations,'used':used,'unknown':unknown}


def _check_family_records_in(db,states,policy,*,files):
    # Called by full9 after original replay. Never calls OwnStore/root closure.
    found=_firsts(states)
    tagged=[p for s,_,_ in states.values() for p in s['previews'].values() if _kind(p) in PROFILES]
    if not tagged:return
    if policy is None:hold('GROUP_FAMILY_HISTORY_POLICY_REQUIRED')
    scope=_scope(db,required=False)
    requests=set();legal=set()
    for _,first in found:
        rid=first['candidate'].get('request_identity_sha');_hash(rid)
        if rid in requests:hold('GROUP_DUPLICATE_FIRST')
        requests.add(rid);pack=read_first_files(files,rid);info=_validate_family(db,states,files,pack,evidence_scope=scope);_timeline(db,first['binding_sha'],pack,scope)
        legal.update((info['account'],_gid(info['account'],p)) for p in info['covenant']['purposes'])
    if any((account,gid) not in legal for account,(state,_,_) in states.items() for gid in state['preview_grants']):hold('GROUP_LEGACY_READ_FAMILY_UNATTESTED')
    if any(_kind(p) in (ROUTE,ACT) and p['candidate'].get('family_anchor_id') not in {f['candidate']['family_anchor_id'] for _,f in found} for p in tagged):hold('GROUP_FIRST_REQUIRED')


def check_family_records_in(db,states,policy,*,files=None):
    if not any(_kind(p) in PROFILES for state,_,_ in states.values() for p in state['previews'].values()):return
    if policy is None:hold('GROUP_FAMILY_HISTORY_POLICY_REQUIRED')
    if files is None:
        closure=_ROOT_CURRENT.get()
        if type(closure) is _RootClosure and closure.active and closure.db is db and closure.files.policy is policy and closure.thread==threading.get_ident():files=closure.files
        else:files=FamilyFiles(policy,lambda:_history_file_guard(policy))
    if type(files) is not FamilyFiles or files.policy is not policy:hold()
    with files._observing():return _check_family_records_in(db,states,policy,files=files)


def _existing_ledger_ancestry(db,states,files):
    if not any(state['preview_grants'] for state,_,_ in states.values()):return
    if not _firsts(states):hold('GROUP_LEGACY_READ_FAMILY_UNATTESTED')
    check_family_records_in(db,states,files.policy,files=files)
    # An allocated/unknown/rejected old read may not be bypassed by a new FIRST.
    if any(claim['state']!='OBSERVED' for state,_,_ in states.values() for grant in state['preview_grants'].values() for claim in grant['claims']):hold('GROUP_RESULT_UNKNOWN')


def recover_family_in(db,files,request_identity_sha,*,root_closure,guard):
    require_closure(root_closure,db,files);marker=_sql_marker(db);guard();_hash(request_identity_sha)
    if json.loads(root_closure.origin_raw)['origin_request_identity_sha']!=request_identity_sha:hold()
    pack=read_first_files(files,request_identity_sha);states=_states(db);value=_validate_family(db,states,files,pack,evidence_scope=_scope(db,required=False))
    r=pack.entry('family_root').value
    if digest(prepared_binding(files.policy,root_closure.source_kind))!=digest(r['first_binding']) or r['first_directory']['device']!=files.root_identity[0] or r['first_directory']['inode']!=files.root_identity[1]:hold('GROUP_BINDING_BRIDGE_REQUIRED')
    guard();require_closure(root_closure,db,files);_same_sql(root_closure,marker)
    return json.loads(canonical(value))


def register_first_in(db,group_store,first_files,*,root_closure,guard, history_locators=None):
    if history_locators is None:history_locators=root_closure.history_locators
    if history_locators is not root_closure.history_locators:hold('GROUP_HISTORY_SCOPE_CHANGED')
    files=root_closure.files;require_closure(root_closure,db,files);validate_pack(first_files)
    check_pack_origin(first_files,root_closure)
    actual=read_first_files(files,first_files.entry('request_witness').key)
    if actual!=first_files:hold()
    p=_first_payload(actual,root_closure.source_kind)
    if group_store.binding_sha!=p['binding_sha'] or json.loads(root_closure.origin_raw)['origin_request_identity_sha']!=actual.entry('request_witness').key:hold()
    states=_states(db);matches=[x for account,x in _firsts(states) if x['candidate'].get('request_identity_sha')==actual.entry('request_witness').key]
    if matches:
        if len(matches)!=1 or canonical(matches[0])!=canonical(p):hold()
        return recover_family_in(db,files,actual.entry('request_witness').key,root_closure=root_closure,guard=guard)
    # Untied legacy read ledgers cannot be guessed independent or reset.
    _existing_ledger_ancestry(db,states,files)
    with family_scope(db,files,root_closure):
        group_store.register_preview_in(db,p['preview_id'],source_kind=p['source_kind'],input_sha=p['input_sha'],request_key=p['request_key'],scope_sha=p['scope_sha'],candidate=p['candidate'],evidence_sha=p['evidence_sha'], history_locators=history_locators)
    guard();return {'state':'FIRST_REGISTERED_IN_TRANSACTION','authority':False}


def query_first_in(db,files,request_identity_sha,*,root_closure,guard):
    try:
        require_closure(root_closure,db,files);marker=_sql_marker(db);_hash(request_identity_sha);guard();states=_states(db);absence=None
        if json.loads(root_closure.origin_raw)['origin_request_identity_sha']!=request_identity_sha:hold()
        w=files.optional('request_witness',request_identity_sha)
        matching=[p for _,p in _firsts(states) if p['candidate'].get('request_identity_sha')==request_identity_sha]
        if w is None:
            if matching:hold()
            _existing_ledger_ancestry(db,states,files)
            absence=files._absence_inventory(request_identity_sha)
            result={'state':'ABSENT','authority':False}
        else:
            missing=False
            for role,key,expected in (('covenant',w.value['first_covenant_sha'],None),('first_proof',w.value['first_proof_sha'],None),('family_root',w.value['family_anchor_id'],w.value['family_root_sha'])):
                e=files.optional(role,key,expected_sha=expected)
                if e is None:missing=True
            if missing:
                if matching:hold()
                result={'state':'FILES_PREPARED','reason':'ORIGINAL_BYTES_REQUIRED','authority':False}
            else:
                pack=read_first_files(files,request_identity_sha)
                if matching:_validate_family(db,states,files,pack,evidence_scope=_scope(db,required=False));result={'state':'COMMITTED','authority':False}
                else:
                    _existing_ledger_ancestry(db,states,files)
                    result={'state':'NOT_COMMITTED','authority':False}
        guard();require_closure(root_closure,db,files)
        if absence is not None:files._pure_absence(absence)
        _same_sql(root_closure,marker)
        return result
    except (WCEError,OSError,ValueError,TypeError):return {'state':'UNDETERMINED','authority':False}


def _activation_predicate(state,decision,p,ac,scope):
    if p['purpose'] in ('QUALIFY','PREVIEW_ACCOUNT'):return
    if decision is None or ac['route_decision_sha']!=digest(decision):hold('GROUP_PURPOSE_INACTIVE')
    if p['purpose']=='EXECUTION_INITIAL_ACCOUNT':
        if decision['route']!=v.ROUTES[1]:hold('GROUP_PURPOSE_INACTIVE')
        _history_evidence(scope,ACT,ac);return
    j=p['ordinal']
    if j>=decision['actual_child_count'] or state['pool'] is None:hold('GROUP_PURPOSE_INACTIVE')
    matches=[]
    for batch in state['batches'].values():
        plans=batch['candidate']['children']
        execution=batch['execution']
        if (execution['source_scope_sha']!=decision['capsule_sha'] or execution['preview_sha']!=decision['snapshot_sha']
            or len(plans)!=decision['actual_child_count']):continue
        actual_slots=[{'ordinal':p['ordinal'],'old_ref_subjects':[x['ref_sha'] for x in p['old_ref_set']],
            'get_cap':p['budget']['get_cap'],'add_cap':p['budget']['add_cap'],'delete_cap':p['budget']['delete_cap']} for p in plans]
        if [digest(x) for x in actual_slots]!=decision['execution_slot_shas']:continue
        if batch['cancelled'] or batch['next_ordinal']!=j-1 or j>=len(plans) or batch['expected_head']!=state['pool']['head']:continue
        old=state['operations'][plans[j-1]['operation_id']];nxt=state['operations'][plans[j]['operation_id']]
        if old['state']!='COMPLETE' or old['cancelled'] or nxt['state']!='WAITING':continue
        final=[c for c in old['claims'] if c['kind']=='GET' and c['slot']=='FINAL_NEW']
        if len(final)!=1 or final[0]['outcome']!='MATCHED' or final[0]['state']!='OBSERVED':continue
        if any(x['state']!='RETIREMENT_VERIFIED' for x in old['old_refs']):continue
        matches.append(batch)
    if len(matches)!=1:hold('GROUP_PROMOTION_NOT_READY')


def _discovery_complete(state,account,c):
    if state is None:hold('GROUP_DISCOVERY_PROOF_REQUIRED')
    initial=_purpose(c,'PREVIEW_ACCOUNT',0);grant=state['preview_grants'].get(_gid(account,initial))
    if grant is None or grant['subjects'] is None or grant['hold'] or any(x['state']!='OBSERVED' for x in grant['claims']):hold('GROUP_DISCOVERY_PROOF_REQUIRED')
    if len([x for x in grant['claims'] if x['api']=='GET'])!=len(grant['subjects']):hold()


def _past_unknown(state,allowed):
    if state is None:return False
    return any(claim['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED')
        for grant in state['preview_grants'].values() if grant['registration']['source_grant_sha'] in allowed
        for claim in grant['claims'])


def _timeline(db,account,pack,scope):
    """Pure replay at each family control event; no source/OwnStore recursion."""
    from .draft_group_store import _reduce
    c=pack.entry('covenant').value;a=c['family_anchor_id'];allowed={p['source_grant_sha']:p for p in c['purposes']}
    seen_first=False;seen_route=False;acts=set();grants=set();state=None
    for row in db.execute('SELECT kind,payload FROM group_events WHERE account_key=? ORDER BY seq',(account,)):
        kind=row['kind'];payload=json.loads(row['payload'])
        related=(kind=='PREVIEW' and payload['candidate'].get('family_anchor_id')==a
            or kind=='PREVIEW_GRANT' and payload['source_grant_sha'] in allowed
            or kind in ('PREVIEW_READ','PREVIEW_SUBJECTS') and any(_gid(account,p)==payload['grant_id'] for p in allowed.values()))
        if related and _past_unknown(state,allowed):hold('GROUP_RESULT_UNKNOWN')
        if kind=='PREVIEW':
            candidate=payload['candidate']
            profile=_kind(payload)
            if profile==FIRST and candidate.get('request_identity_sha')==pack.entry('request_witness').key:
                if seen_first:hold('GROUP_DUPLICATE_FIRST')
                seen_first=True
            elif profile==ROUTE and candidate.get('family_anchor_id')==a:
                if not seen_first or seen_route:hold()
                _discovery_complete(state,account,c)
                seen_route=True
            elif profile==ACT and candidate.get('family_anchor_id')==a:
                if not seen_first or candidate['source_grant_sha'] in acts:hold()
                p=allowed.get(candidate['source_grant_sha'])
                if p is None:hold()
                decision=None if state is None else state['previews'].get('group-read-route-'+a,{}).get('candidate')
                _activation_predicate(state,decision,p,candidate,scope)
                acts.add(candidate['source_grant_sha'])
        elif kind=='PREVIEW_GRANT' and payload['source_grant_sha'] in allowed:
            if not seen_first or payload['source_grant_sha'] not in acts or payload['source_grant_sha'] in grants:hold()
            grants.add(payload['source_grant_sha'])
        elif kind=='PREVIEW_READ':
            p=next((p for p in allowed.values() if _gid(account,p)==payload['grant_id']),None)
            if p is not None and (not seen_first or p['source_grant_sha'] not in grants):hold()
        state=_reduce(state,kind,payload)


def before_event_in(db,account,kind,payload):
    """Actual consumer hook, before mutation. Does not replace store.verify."""
    scope=_scope(db,required=False)
    modern=kind=='PREVIEW' and _kind(payload) in PROFILES
    reading=kind in ('PREVIEW_GRANT','PREVIEW_READ','PREVIEW_SUBJECTS','PREVIEW_READ_RESULT')
    if not modern and not reading:return
    scope=_scope(db);files=scope[1];states=_states(db)
    if modern and _kind(payload)==FIRST:
        candidate=payload['candidate'];_hash(candidate.get('request_identity_sha'))
        pack=read_first_files(files,candidate['request_identity_sha']);check_pack_origin(pack,scope[2]);expected=_first_payload(pack,payload['source_kind'])
        if canonical(payload)!=canonical(expected) or account!=expected['binding_sha']:hold()
        if any(p['candidate'].get('request_identity_sha')==candidate['request_identity_sha'] for _,p in _firsts(states)):hold('GROUP_DUPLICATE_FIRST')
        _existing_ledger_ancestry(db,states,files)
        return
    families=[]
    for pool,first in _firsts(states):
        pack=read_first_files(files,first['candidate']['request_identity_sha']);info=_validate_family(db,states,files,pack,evidence_scope=scope)
        if modern:
            matched=payload['candidate'].get('family_anchor_id')==info['covenant']['family_anchor_id']
        elif kind=='PREVIEW_GRANT':matched=payload['source_grant_sha'] in {p['source_grant_sha'] for p in info['covenant']['purposes']}
        else:matched=payload['grant_id'] in {_gid(pool,p) for p in info['covenant']['purposes']}
        if matched:families.append((pack,info))
    if len(families)!=1:hold('GROUP_READ_FAMILY_REQUIRED')
    pack,info=families[0];c=info['covenant'];state=states[info['account']][0]
    if account!=info['account'] or info['account']!=digest(prepared_binding(files.policy,scope[2].source_kind)):hold('GROUP_BINDING_BRIDGE_REQUIRED')
    if kind not in ('PREVIEW_READ_RESULT',) and info['unknown']:hold('GROUP_RESULT_UNKNOWN')
    if reading and kind!='PREVIEW_READ_RESULT' and c['source_rights_expiry']['kind']=='EXPLICIT_UNTIL' and int(time.time()*1000)>=c['source_rights_expiry']['not_after']:hold('GROUP_READ_RIGHTS_EXPIRED')
    if modern:
        candidate=payload['candidate'];pid=payload['preview_id']
        if pid in state['previews']:hold('GROUP_DUPLICATE_FAMILY_RECORD')
        if _kind(payload)==ROUTE:
            # Route decision requires a complete observed initial ACCOUNT ledger.
            _discovery_complete(state,account,c)
        else:
            p=_purpose(c,candidate['purpose'],candidate['ordinal'])
            _activation_predicate(state,info['route'],p,candidate,scope)
    elif kind=='PREVIEW_GRANT':
        p=next(p for p in c['purposes'] if p['source_grant_sha']==payload['source_grant_sha'])
        if canonical(payload)!=canonical(_registration(p,c)) or p['source_grant_sha'] not in info['activations']:hold('GROUP_PURPOSE_INACTIVE')
        if _gid(account,p) in state['preview_grants']:hold('GROUP_DUPLICATE_GRANT_EVENT')
    elif kind=='PREVIEW_READ':
        p=next(p for p in c['purposes'] if _gid(account,p)==payload['grant_id'])
        if payload['preview_id']!='group-read-purpose-'+p['source_grant_sha']:hold()
        if info['route'] is not None:
            if p['purpose']=='EXECUTION_INITIAL_ACCOUNT' and info['route']['route']!=v.ROUTES[1]:hold()
            branch=next(b for b in c['branches'] if b['route']==info['route']['route'])
            cap=branch['caps']['LIST' if payload['api']=='LIST' else 'TOTAL_GET']
            if info['used'][payload['api']]>=cap:hold('GROUP_BUDGET_EXHAUSTED')


def after_event_in(db):
    scope=_scope(db,required=False)
    if scope is None:return
    states=_states(db);check_family_records_in(db,states,scope[1].policy,files=scope[1])


def _register_control(db,store,pack,candidate,*,scope_sha,evidence_sha, history_locators=None):
    a=pack.entry('covenant').value['family_anchor_id']
    pid='group-read-route-'+a if candidate['profile']==ROUTE else 'group-read-purpose-'+candidate['source_grant_sha']
    states=_states(db);old=states.get(store.binding_sha,(None,))[0]
    proposed={'binding_sha':store.binding_sha,'source_kind':pack.entry('family_root').value['first_binding']['source_kind'],'preview_id':pid,'input_sha':pack.entry('covenant').sha256,'request_key':pid,'scope_sha':scope_sha,'candidate':candidate,'evidence_sha':evidence_sha}
    if old is not None and pid in old['previews']:
        if canonical(old['previews'][pid])!=canonical(proposed):hold()
        return
    store.register_preview_in(db,pid,source_kind=proposed['source_kind'],input_sha=proposed['input_sha'],request_key=pid,scope_sha=scope_sha,candidate=candidate,evidence_sha=evidence_sha, history_locators=history_locators)


def record_route_in(db,store,first_files,decision,*,root_closure,guard, history_locators=None):
    if history_locators is None:history_locators=root_closure.history_locators
    if history_locators is not root_closure.history_locators:hold('GROUP_HISTORY_SCOPE_CHANGED')
    files=root_closure.files;require_closure(root_closure,db,files);validate_pack(first_files)
    if type(decision) is not dict:hold()
    with family_scope(db,files,root_closure):
        _register_control(db,store,first_files,decision,scope_sha=digest({'profile':ROUTE,'family_anchor_id':decision['family_anchor_id']}),evidence_sha=decision['source_evidence_sha'], history_locators=history_locators)
    guard()


def restore_purpose_in(db,store,first_files,purpose_key,activation_facts,*,root_closure,guard,historical_evidence=None, history_locators=None):
    if history_locators is None:history_locators=root_closure.history_locators
    if history_locators is not root_closure.history_locators:hold('GROUP_HISTORY_SCOPE_CHANGED')
    files=root_closure.files;require_closure(root_closure,db,files);validate_pack(first_files)
    _plain([purpose_key,activation_facts]);_closed(purpose_key,('purpose','ordinal'))
    c=first_files.entry('covenant').value;p=_purpose(c,purpose_key['purpose'],purpose_key['ordinal'])
    _closed(activation_facts,('route_decision_sha','evidence_sha'));_hash(activation_facts['evidence_sha'])
    if activation_facts['route_decision_sha'] is not None:_hash(activation_facts['route_decision_sha'])
    ac={'schema':1,'profile':ACT,'authority':False,'family_anchor_id':c['family_anchor_id'],'covenant_sha':first_files.entry('covenant').sha256,'purpose':p['purpose'],'ordinal':p['ordinal'],'source_grant_sha':p['source_grant_sha'],'scope_sha':p['scope_sha'],'activation_kind':p['activation']['kind'],**activation_facts}
    with family_scope(db,files,root_closure,historical_evidence=historical_evidence):
        _register_control(db,store,first_files,ac,scope_sha=p['scope_sha'],evidence_sha=ac['evidence_sha'], history_locators=history_locators)
        state,_,_=__import__(__package__+'.draft_group_store',fromlist=['_load'])._load(db,store.binding_sha)
        gid=_gid(store.binding_sha,p);registration=_registration(p,c)
        if gid in state['preview_grants']:
            if canonical(state['preview_grants'][gid]['registration'])!=canonical(registration):hold()
        else:store.register_preview_read_grant_in(db,**registration, history_locators=history_locators)
    guard();return {'grant_id':gid,'preview_id':'group-read-purpose-'+p['source_grant_sha'],'authority':False}
