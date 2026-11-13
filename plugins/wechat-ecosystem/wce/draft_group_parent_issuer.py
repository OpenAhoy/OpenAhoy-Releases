"""Current fixed NEW_ONLY parent producer, never authority from stored JSON.

The caller owns the original entry/writer/Owned transaction. All files have
already been published before this context. This module sends no request,
waits for no human, starts no transaction, and does not commit caller SQL.
Replacement requires the separate actual protected T1 handler; it cannot
fall through to this no-dialogue NEW_ONLY issuer.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,replace
import json,threading,time,weakref
from .contracts import WCEError
from .service import canonical,digest
from .own_validation_scope import OwnedConnection,_transaction_marker

_CURRENT=ContextVar('group_actual_parent_creation',default=None)
_ISSUED={}
_CURRENT_FILES=weakref.WeakKeyDictionary()
_TIME=time.time;_THREAD=threading.get_ident
NEW_ONLY='NEW_ONLY_EXISTING_DELEGATION'


def need(value,code='GROUP_PARENT_ISSUER_HOLD'):
    if value is not True:raise WCEError(code)


def _current(host,db):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate,QualifiedGroupSource
    need(type(host)is GroupRuntimeHost and type(host.entry)is GroupExecutionGate,
         'GROUP_PARENT_ACTUAL_HOST_REQUIRED')
    host.entry.held_pure()
    need(type(db)is OwnedConnection and _transaction_marker(db)is not None,
         'GROUP_PARENT_OWNED_TRANSACTION_REQUIRED')
    source=host._source
    need(type(source)is QualifiedGroupSource and source.host is host
         and source.entry is host.entry and host.entry.issued.get(id(source))is source,
         'GROUP_PARENT_CURRENT_SOURCE_REQUIRED')
    # The caller first performs full historical verification. This callback is
    # also used by immutable event hooks, so it must not recurse into that
    # verification through current_no_token_in(db).
    host.current_no_token_in(None,source, history_locators=None)
    return source


def _canonical_payload(value):return(canonical(value)+'\n').encode()


def _release_current_files(entry_ref):
    entry=entry_ref()
    if entry is not None:_CURRENT_FILES.pop(entry,None)


def _descriptor(kind,value):
    from hashlib import sha256
    raw=_canonical_payload(value)
    return {'kind':kind,'sha256':sha256(raw).hexdigest(),'size':len(raw)}


def _inputs(host,db,capsule,files):
    from .draft_group_input_files import FileEvidence
    from .draft_group_target_scope import target_article_metadata
    from .own_group_json import read
    need(type(capsule)is FileEvidence and capsule.role=='execution',
         'GROUP_PARENT_CAPSULE_REQUIRED')
    need(files.read('execution',capsule.key,expected_sha=capsule.sha256)==capsule,
         'GROUP_PARENT_CAPSULE_CHANGED')
    c=capsule.value;registration=host._registration
    need(c['binding']==host.chain.config['binding']
         and c['registration_sha']==registration['registration_sha']
         and c['source_material_sha']==registration['registration']['source_material_sha'],
         'GROUP_PARENT_REGISTRATION_CHANGED')
    source=files.read('source',c['source_material_sha'],expected_sha=c['source_material_sha'])
    children=[];settings=[];designations=[]
    state=host._group_state_in(db)
    for spec in c['children']:
        child=files.read('child',spec['sha256'],expected_sha=spec['sha256'])
        need(spec=={'kind':'CHILD','sha256':child.sha256,'size':len(child.raw)},
             'GROUP_PARENT_CHILD_DESCRIPTOR')
        h=child.value;manifest=read(h['manifest_json'],h['manifest_sha'])
        metadata=target_article_metadata(manifest,h)
        target=state['previews'].get('group-target-'+h['manifest_sha'])
        need(target is not None and target['candidate']['profile']=='GROUP_TARGET_DESIGNATION_V1',
             'GROUP_PARENT_TARGET_REQUIRED')
        d=target['candidate']
        need(d['capsule_sha']==capsule.sha256 and d['child_sha']==child.sha256
             and d['operation_id']==h['operation_id']
             and d['registration_sha']==registration['registration_sha']
             and d['registration_proof_sha']==registration['registration_proof_sha'],
             'GROUP_PARENT_TARGET_CHANGED')
        row=db.execute('SELECT manifest,digest FROM own_articles WHERE version=?',
                       (h['selector']['version'],)).fetchone()
        need(row is not None and row['manifest']==h['manifest_json']
             and row['digest']==h['manifest_sha'],'GROUP_PARENT_TARGET_ROW_REQUIRED')
        children.append((child,h));settings.append({'operation_id':h['operation_id'],
                                                    'article_metadata':metadata})
        designations.append(d)
    from .draft_group_parent import expected_settings_descriptor
    need(c['expected_metadata']==expected_settings_descriptor(settings),
         'GROUP_PARENT_SETTINGS_CHANGED')
    files.collective_fence()
    return c,source,tuple(children),tuple(designations),state


def _derive_new_only(host,db,coverage,capsule,preview,files, *, history_locators=None):
    from .draft_group_coverage import verify_account_coverage,_record,_collect
    from .draft_group_contracts import Article,PoolGroup
    from .draft_group_planner import plan_batch
    from .draft_group_parent import (parent_budget_descriptor,original_input_expiry_ms,
                                     original_not_after_ms)
    verify_account_coverage(coverage,host,db, history_locators=history_locators);record=_record(coverage)
    state,proof,_,_=_collect(host,db,record.scope,record.files, history_locators=history_locators)
    c,source,children,designations,state2=_inputs(host,db,capsule,files)
    need(canonical(state)==canonical(state2),'GROUP_PARENT_SQL_CHANGED')
    registration=host._registration;reg=registration['registration']
    articles=tuple(Article(**m)for m in reg['ordered_members'])
    need(all(a.origin=='NEW_NOT_SENT'for a in articles),'GROUP_PARENT_NEW_ONLY_REQUIRED')
    need(state['pool']is not None,'GROUP_PARENT_POOL_REQUIRED')
    groups=[]
    for value in state['pool']['groups'].values():
        if value['state']not in('OPEN','FULL','PUBLISHED','HOLD','UNKNOWN'):continue
        item=dict(value);item['members']=tuple(Article(**m)for m in item['members'])
        groups.append(PoolGroup(**item))
    groups=tuple(groups)
    derived=plan_batch(state['binding_sha'],preview['request_key'],articles,groups,record.candidate)
    need(canonical(derived)==canonical(preview) and preview['plan_state']=='CANDIDATE_ALLOCATED',
         'GROUP_PARENT_ALLOCATION_CHANGED')
    need(c['preview_core_sha']==preview['candidate_sha'] and c['route_profile']=='CREATE_NEW'
         and len(children)==len(preview['children']),'GROUP_PARENT_PREVIEW_CHANGED')
    pins=[];parent_children=[];budgets=[]
    for (child,h),plan in zip(children,preview['children']):
        need(plan['route']=='CREATE_NEW' and not plan['old_ref_set']
             and plan['budget']['delete_cap']==0 and h['operation_id']==plan['operation_id'],
             'GROUP_PARENT_NEW_ONLY_REQUIRED')
        members=[{k:v for k,v in m.items()if k not in('target_position','source_old_index')}
                 for m in plan['members']]
        need(h['members']==members and h['execution_budget']==_descriptor('BUDGET',plan['budget']),
             'GROUP_PARENT_MEMBER_OR_BUDGET_CHANGED')
        pins.append({'operation_id':plan['operation_id'],'target_projection_sha':h['projection_sha'],
                     'old_projection_shas':[]})
        parent_children.append({'operation_id':plan['operation_id'],
            'target_manifest_sha':h['manifest_sha'],'target_projection_sha':h['projection_sha'],
            'old_reference_shas':[],'budget':plan['budget']})
        budgets.append({'operation_id':plan['operation_id'],'budget':plan['budget']})
    need(c['execution_budget']==parent_budget_descriptor(budgets),'GROUP_PARENT_BUDGET_CHANGED')
    info=host._family_in(db, history_locators=history_locators);purpose=record.scope.details['purpose_key']
    selected=[p for p in info['covenant']['purposes']if p['source_grant_sha']==purpose]
    need(info['route']is not None and info['route']['route']==NEW_ONLY
         and len(selected)==1 and selected[0]['purpose']=='PREVIEW_ACCOUNT'
         and purpose in info['activations'] and c['family_id']==info['covenant']['family_anchor_id'],
         'GROUP_PARENT_FIRST_ROUTE_REQUIRED')
    now=int(_TIME()*1000)
    original_input_ms=original_input_expiry_ms(source.value['expires_policy']['not_after'])
    rights=info['covenant']['source_rights_expiry']
    need(rights==host.chain.semantic['source_rights_expiry'],'GROUP_PARENT_ORIGINAL_RIGHTS_CHANGED')
    expiry=original_not_after_ms(original_input_ms,rights)
    need(0<=now-proof['observed_at_ms']<=60000 and proof['latest_observed_at_ms']<=now<expiry,
         'GROUP_PARENT_CREATION_EXPIRED')
    common={'schema':1,'authority':False,'binding_sha':state['binding_sha'],
        'family_id':c['family_id'],'registration_sha':c['registration_sha'],
        'registration_proof_sha':registration['registration_proof_sha'],
        'source_material_sha':c['source_material_sha'],'semantic_scope_sha':host._source.semantic_scope_sha,
        'preview_sha':preview['candidate_sha'],'settings_sha':c['expected_metadata']['sha256'],
        'route':NEW_ONLY,'first_purpose_key':purpose,
        'original_source_rights_expiry':rights,'original_input_not_after_ms':original_input_ms,
        'selection_receipt_sha':None,'snapshot_preview_sha':None}
    adoption=dict(common,profile='GROUP_INPUT_ADOPTION_V1',capsule_sha=capsule.sha256,
        creation_entry_epoch=record.scope.details['source_epoch'],
        coverage_grant_id=record.scope.details['gid'],coverage_proof_sha=digest(proof),
        coverage_receipts_sha=digest(proof['receipts']),oldest_observed_at_ms=proof['observed_at_ms'],
        latest_observed_at_ms=proof['latest_observed_at_ms'],adopted_at_ms=now,
        adoption_kind='AUTO_NEW_ONLY')
    parent=dict(common,profile='GROUP_QUALIFIED_PARENT_GRANT_V1',batch_id=preview['batch_id'],
        request_key=preview['request_key'],source_scope_sha=capsule.sha256,
        adoption_sha=digest(adoption),children=parent_children,
        read_covenant_sha=info['first']['candidate']['covenant_sha'],created_at_ms=now,not_after_ms=expiry)
    execution={'parent_grant_sha':digest(parent),'preview_sha':preview['candidate_sha'],
               'settings_sha':common['settings_sha'],'source_scope_sha':capsule.sha256,'child_pins':pins}
    return adoption,parent,execution,articles,groups,record.candidate


@dataclass(frozen=True)
class _CreationRecord:
    value:object
    host:object
    entry:object
    db:object
    epoch:int
    thread:int
    coverage:object
    capsule:object
    files:object
    adoption_json:str
    parent_json:str
    plan_json:str
    articles:tuple
    groups:tuple
    candidate:object
    oldest:int
    not_after:int
    phase:str='READY'


def _creation(value):
    record=_ISSUED.get(id(value))
    need(type(value)is ParentCreation and type(record)is _CreationRecord
         and record.value is value and _CURRENT.get()is value
         and record.entry.issued.get(id(value))is value
         and record.thread==_THREAD() and record.entry is record.host.entry
         and _transaction_marker(record.db)==record.epoch,
         'GROUP_PARENT_ISSUER_UNISSUED')
    return record


def _phase(value,phase):
    record=_creation(value)
    _ISSUED[id(value)]=replace(record,phase=phase)


class ParentCreation:
    __slots__=()
    def __init__(self):raise WCEError('GROUP_PARENT_ISSUER_REQUIRED')
    def check(self, *, history_locators=None):
        record=_creation(self)
        _current(record.host,record.db)
        from .draft_group_coverage import verify_account_coverage
        verify_account_coverage(record.coverage,record.host,record.db, history_locators=history_locators)
        # Retain and re-use the original first file observations. This also
        # rechecks the actual target SQL after every replaceable preparation
        # callback; a source callback cannot alter a target after its last read.
        c,_,children,_,_=_inputs(record.host,record.db,record.capsule,record.files)
        parent=json.loads(record.parent_json)
        need(c['preview_core_sha']==parent['preview_sha']
             and [{'operation_id':h['operation_id'],'target_manifest_sha':h['manifest_sha'],
                   'target_projection_sha':h['projection_sha']}for _,h in children]
             ==[{k:child[k]for k in('operation_id','target_manifest_sha','target_projection_sha')}
                for child in parent['children']],'GROUP_PARENT_CURRENT_TARGET_CHANGED')
        record.files.collective_fence();record.files.pure_release_fence();record.host.pure_release_fence()
        now=int(_TIME()*1000)
        need(record.oldest<=now<=record.oldest+60000 and now<record.not_after,
             'GROUP_PARENT_CREATION_EXPIRED')
    def append_and_plan(self, *, history_locators=None):
        from .draft_group_parent import register_adoption_in,register_parent_in
        from .draft_group_store import GroupStore
        ParentCreation.check(self,history_locators=history_locators);record=_creation(self)
        need(record.phase=='READY','GROUP_PARENT_ALREADY_SUBMITTED')
        adoption=json.loads(record.adoption_json);parent=json.loads(record.parent_json)
        payload=json.loads(record.plan_json)
        store=GroupStore(parent['binding_sha'],_history_partial(record.host.verify_in, history_locators=history_locators))
        register_adoption_in(record.host,record.db,store,adoption, history_locators=history_locators);_phase(self,'ADOPTION_RECORDED')
        register_parent_in(record.host,record.db,store,parent, history_locators=history_locators);_phase(self,'PARENT_RECORDED')
        result=store.plan_in(record.db,payload['candidate'],articles=record.articles,groups=record.groups,
                            coverage=record.candidate,execution=payload['execution'], history_locators=history_locators)
        _phase(self,'FINISHED');ParentCreation.check(self,history_locators=history_locators);return result


@contextmanager
def parent_creation_in(host,db,coverage,capsule,preview, *, history_locators=None):
    from .draft_group_target_files import PinnedTargetFiles
    need(_CURRENT.get()is None,'GROUP_PARENT_REENTRANT')
    source=_current(host,db)
    need(db.execute('PRAGMA query_only').fetchone()[0]==0,'GROUP_PARENT_WRITE_TRANSACTION_REQUIRED')
    host.current_no_token_in(db,source, history_locators=history_locators)
    files=PinnedTargetFiles(host.entry.policy,host.entry.loop_guard)
    values=_derive_new_only(host,db,coverage,capsule,preview,files, history_locators=history_locators)
    adoption,parent,execution,articles,groups,candidate=values
    payload={'candidate':preview,'articles':[a.value()for a in articles],
             'groups':[g.value()for g in groups],'coverage':candidate.value(),
             'legacy':None,'execution':execution}
    value=object.__new__(ParentCreation)
    _ISSUED[id(value)]=_CreationRecord(value,host,host.entry,db,_transaction_marker(db),_THREAD(),
        coverage,capsule,files,canonical(adoption),canonical(parent),canonical(payload),articles,groups,candidate,
        adoption['oldest_observed_at_ms'],parent['not_after_ms'])
    host.entry.issued[id(value)]=value;token=_CURRENT.set(value)
    try:
        ParentCreation.check(value,history_locators=history_locators);yield value
        need(_creation(value).phase=='FINISHED','GROUP_PARENT_PLAN_NOT_FINISHED')
    finally:
        _CURRENT.reset(token);_ISSUED.pop(id(value),None);host.entry.issued.pop(id(value),None)


def validate_parent_append_in(host,db,kind,payload,*,history_locators=None):
    value=_CURRENT.get()
    record=_creation(value)
    need(record.host is host and record.db is db,'GROUP_PARENT_ISSUER_REQUIRED')
    ParentCreation.check(value,history_locators=history_locators)
    expected={'ADOPTION':record.adoption_json,'PARENT':record.parent_json,'PLAN':record.plan_json}
    need(kind in expected and canonical(payload)==expected[kind],'GROUP_PARENT_PAYLOAD_CHANGED')
    phase={'ADOPTION':'READY','PARENT':'ADOPTION_RECORDED','PLAN':'PARENT_RECORDED'}[kind]
    need(record.phase==phase,'GROUP_PARENT_WRITE_ORDER')
    return None


def validate_parent_plan_in(host,db,details,*,history_locators=None):
    return validate_parent_append_in(host,db,'PLAN',details,history_locators=history_locators)


def validate_parent_current_in(host,db,operation_id,parent_record, *, history_locators=None):
    from .draft_group_target_files import PinnedTargetFiles
    source=_current(host,db)
    # This is the current child-issuance entry, never the historical PREVIEW
    # replay hook. The complete original all-pool/OwnStore history is required
    # here before any typed parent object can be issued.
    host.current_no_token_in(db,source, history_locators=history_locators)
    need(type(parent_record)is dict and parent_record['binding_sha']==digest(host.chain.config['binding'])
         and parent_record['registration_sha']==host._registration['registration_sha']
         and parent_record['registration_proof_sha']==host._registration['registration_proof_sha'],
         'GROUP_PARENT_CURRENT_REGISTRATION_CHANGED')
    # The historical validator has already verified every original record and
    # fixed wrapper against the original PLAN. Re-read current exact C/H/D here.
    by_capsule=_CURRENT_FILES.get(host.entry)
    if by_capsule is None:
        by_capsule={};_CURRENT_FILES[host.entry]=by_capsule
        # The retained reader's original guard references this entry. Drop the
        # readers at the actual entry close instead of retaining that cycle.
        host.entry.stack.callback(_release_current_files,weakref.ref(host.entry))
    files=by_capsule.get(parent_record['source_scope_sha'])
    if files is None:
        files=PinnedTargetFiles(host.entry.policy,host.entry.loop_guard)
        by_capsule[parent_record['source_scope_sha']]=files
    capsule=files.read('execution',parent_record['source_scope_sha'],expected_sha=parent_record['source_scope_sha'])
    c,source,children,designations,state=_inputs(host,db,capsule,files)
    need(parent_record['source_material_sha']==c['source_material_sha']
         and parent_record['semantic_scope_sha']==host._source.semantic_scope_sha
         and parent_record['original_source_rights_expiry']==host.chain.semantic['source_rights_expiry'],
         'GROUP_PARENT_CURRENT_SCOPE_CHANGED')
    matches=[h for _,h in children if h['operation_id']==operation_id]
    need(len(matches)==1 and any(child['operation_id']==operation_id for child in parent_record['children']),
         'GROUP_PARENT_CURRENT_CHILD_CHANGED')
    files.collective_fence();files.pure_release_fence();host.pure_release_fence()
    need(int(_TIME()*1000)<parent_record['not_after_ms'],'GROUP_PARENT_EXPIRED')
    return None


from functools import partial as _history_partial
