"""Issued local-only target preparation. D and INSERT remain one caller SQL tx."""
from contextlib import contextmanager
from hashlib import sha256
import json
from dataclasses import dataclass,field
from .own_validation_scope import OwnedConnection,_transaction_marker
from .draft_group_contracts import canonical,digest
from .draft_group_input_files import InputFiles,FileEvidence,_plain
from .own_auth import OwnProfile as _ApprovalProfile,OwnerEvidence as _ApprovalEvidence
from .contracts import Actor as _ApprovalActor,WCEError as _ApprovalError
from .own_workflow import OwnWorkflow
from .own_connection_workflow import PersistentWorkflow
from .draft_group_upload_reuse_projection import derive_reuse_projection
from .own_response_archive import row_pin

_ISSUED={}


def hold(code='GROUP_HOST_HOLD'):
    raise _ApprovalError(code)


def need(value,code='GROUP_HOST_HOLD'):
    if value is not True:hold(code)


class TargetPreparationScope:
    def __init__(self):hold('GROUP_TARGET_SCOPE_ISSUER_REQUIRED')
    def check(self):
        need(_ISSUED.get(id(self)) is self and self.host.entry is self.entry and self.entry.issued.get(id(self)) is self,'GROUP_TARGET_SCOPE_UNISSUED')
        self.entry.held_pure();need(type(self.db) is OwnedConnection and self.db.in_transaction
            and _transaction_marker(self.db)==self.epoch,'GROUP_TARGET_TRANSACTION_CHANGED')
        from .draft_group_coverage import verify_account_coverage
        verify_account_coverage(self.coverage,self.host,self.db, history_locators=self.history_locators)
        self.host.current_no_token_in(None,self.source, history_locators=None)
        for e in self.evidence:
            actual=self.files.read(e.role,e.key,expected_sha=e.sha256)
            need(actual==e,'GROUP_TARGET_FILE_CHANGED')
        self.files.collective_fence()
        for receipt in self.proof_receipts:receipt.collective_fence()
        self.files.pure_release_fence();self.host.pure_release_fence();return None
    def admit_designation(self,candidate):
        self.check();need(self.phase=='READY' and canonical(candidate)==canonical(self.designation),'GROUP_TARGET_DESIGNATION_CHANGED')
        self.phase='INSERT_REQUIRED'
        return None
    def finish(self):
        need(self.phase=='INSERT_REQUIRED','GROUP_TARGET_INSERT_REQUIRED')
        row=self.db.execute('SELECT * FROM own_articles WHERE version=?',(self.manifest['version'],)).fetchone()
        need(row is not None and row['manifest']==canonical(self.manifest) and row['digest']==self.designation['manifest_sha'],'GROUP_TARGET_INSERT_MISSING')
        self.host.current_no_token_in(self.db,self.source, history_locators=self.history_locators)
        self.check();self.phase='FINISHED'
        return None


def validate_target_preparation_scope(scope,workflow,db,child=None):
    need(type(scope) is TargetPreparationScope and _ISSUED.get(id(scope)) is scope
         and scope.workflow is workflow and scope.db is db and (child is None or scope.designation['operation_id']==child),'GROUP_TARGET_SCOPE_REQUIRED')
    scope.check();return None


@contextmanager
def target_preparation_in(host,db,child_evidence,reservation_evidence,capsule_evidence,upload_reuse_evidence,coverage_evidence,*,files, history_locators=None):
    from .draft_group_coverage import AccountCoverage,verify_account_coverage
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    need(type(db) is OwnedConnection and db.in_transaction and _transaction_marker(db) is not None,'GROUP_TARGET_TRANSACTION_REQUIRED')
    need(type(coverage_evidence) is AccountCoverage,'GROUP_TARGET_COVERAGE_REQUIRED')
    verify_account_coverage(coverage_evidence,host,db, history_locators=history_locators)
    source=host._source;host.current_no_token_in(db,source, history_locators=history_locators)
    workflow=host.entry.service.workflow;need(type(workflow) is PersistentWorkflow,'GROUP_TARGET_WORKFLOW')
    profile=next(iter(workflow.registry.profiles.values()));lease=workflow._lease(profile)
    need(lease is None and workflow.active_token is None,'GROUP_TARGET_LOCAL_NO_TOKEN')
    workflow._current(profile,lease,'local.write')
    from .draft_group_target_files import PinnedTargetFiles
    need(type(files) is PinnedTargetFiles and files.policy is host.entry.policy,'GROUP_TARGET_FIRST_PINS_REQUIRED')
    evidence=(child_evidence,reservation_evidence,capsule_evidence,upload_reuse_evidence)
    need(all(type(x) is FileEvidence for x in evidence),'GROUP_TARGET_EVIDENCE_REQUIRED')
    need(tuple(x.role for x in evidence)==('child','reservation','execution','upload_reuse'),'GROUP_TARGET_EVIDENCE_ROLE')
    for e in evidence:need(files.read(e.role,e.key,expected_sha=e.sha256)==e,'GROUP_TARGET_FILE_CHANGED')
    h,r,c,u=(x.value for x in evidence)
    need(h['binding']==r['binding']==c['binding']==u['binding']==host.chain.config['binding'],'GROUP_TARGET_BINDING')
    need(r['manifest_sha']==h['manifest_sha']==u['target_manifest_sha'] and r['operation_id']==h['operation_id']==u['operation_id']
         and r['selector']==h['selector']==u['target_selector'] and r['capsule_sha']==capsule_evidence.sha256
         and r['registration_sha']==c['registration_sha']==host._registration['registration_sha']
         and r['proof_sha']==host._registration['registration_proof_sha'],'GROUP_TARGET_ASSOCIATION')
    need(any(x['sha256']==child_evidence.sha256 for x in c['children'])
         and any(x['sha256']==upload_reuse_evidence.sha256 for x in h['upload_reuse']),'GROUP_TARGET_CAPSULE_MEMBER')
    from .own_group_json import read
    manifest=read(h['manifest_json'],h['manifest_sha'])
    assets=workflow._document_content(db,manifest['binding'],manifest['document']) if manifest['schema'] in (2,3) else workflow._content(db,manifest['binding'],manifest['article'])
    need(assets==manifest['assets'],'GROUP_TARGET_ASSETS')
    upload_workflow,_=_history_workflow(host.entry.policy,host.entry.policy.root/'state.sqlite3',profile.binding(),db=db,history_locators=history_locators)
    member_shas={digest(m) for m in h['members']};slotfacts=[];proof_receipts=[]
    need(len(u['entries'])==len(manifest['assets']),'GROUP_TARGET_UPLOAD_COVERAGE')
    for asset,entry in zip(manifest['assets'],u['entries']):
        need(entry['target_asset']==asset and entry['source_member']['member_evidence_sha'] in member_shas,'GROUP_TARGET_UPLOAD_MEMBER')
        original=entry['original_upload'];actual,receipt=read_original_upload_success_with_proofs_in(upload_workflow,db,profile,original['base_step_pin']['id'], history_locators=history_locators)
        need(canonical(actual['proof_files'])==canonical(original['proof_files']),'GROUP_TARGET_UPLOAD_PROOF_FILES')
        receipt.collective_fence();proof_receipts.append(receipt)
        member=next(m for m in h['members'] if digest(m)==entry['source_member']['member_evidence_sha'])
        sm=entry['source_member']
        need(sm['article_id']==member['article_id'] and sm['version_sha']==member['version_sha'] and sm['source_manifest_selector']==actual['selector']
             and sm['source_asset_slot']==actual['slot'] and sm['source_asset_ref']==actual['asset']['asset_ref'],'GROUP_TARGET_UPLOAD_SOURCE_MEMBER')
        for key in ('selector','asset','operation','slot','base_step_pin','snapshot','result_digest'):
            need(canonical(actual[key])==canonical(original[key]),'GROUP_TARGET_UPLOAD_CHANGED')
        slotfacts.append({'target_slot':entry['target_slot'],'mapping':actual['mapping'],'snapshot':actual['snapshot']})
    metadata=target_article_metadata(manifest,h)
    projected=derive_reuse_projection(manifest,slotfacts,article_metadata=metadata)
    need(canonical(projected['projection'])==h['projection_json'],'GROUP_TARGET_PROJECTION_CHANGED')
    need(db.execute('SELECT 1 FROM own_articles WHERE version=?',(manifest['version'],)).fetchone() is None,'GROUP_TARGET_EXISTS')
    from .draft_group_store import check_account_writer
    check_account_writer(db, history_locators=history_locators)
    scope=object.__new__(TargetPreparationScope);scope.host=host;scope.entry=host.entry;scope.source=source
    scope.history_locators=history_locators;scope.db=db;scope.epoch=_transaction_marker(db);scope.workflow=workflow;scope.profile=profile;scope.lease=lease
    scope.coverage=coverage_evidence;scope.files=files;scope.evidence=evidence;scope.proof_receipts=tuple(proof_receipts);scope.manifest=manifest;scope.phase='READY'
    scope.designation={'schema':1,'profile':'GROUP_TARGET_DESIGNATION_V1','authority':False,'binding_sha':digest(h['binding']),
        'operation_id':h['operation_id'],'selector':h['selector'],'manifest_sha':h['manifest_sha'],'capsule_sha':capsule_evidence.sha256,
        'child_sha':child_evidence.sha256,'upload_map_sha':upload_reuse_evidence.sha256,'reservation_sha':reservation_evidence.sha256,
        'registration_sha':r['registration_sha'],'registration_proof_sha':r['proof_sha']}
    _ISSUED[id(scope)]=scope;host.entry.issued[id(scope)]=scope
    host.entry.target_scope=scope
    try:
        scope.check();yield scope
        need(scope.phase=='FINISHED','GROUP_TARGET_PREPARATION_NOT_FINISHED')
    finally:
        _ISSUED.pop(id(scope),None);host.entry.issued.pop(id(scope),None)
        if getattr(host.entry,'target_scope',None) is scope:host.entry.target_scope=None


D_KEYS=('schema','profile','authority','binding_sha','operation_id','selector','manifest_sha','capsule_sha','child_sha','upload_map_sha','reservation_sha','registration_sha','registration_proof_sha')


def _designation(value):
    from .draft_group_input_files import _closed,_hash,_id,_selector
    _closed(value,D_KEYS)
    need(type(value['schema']) is int and value['schema']==1 and value['profile']=='GROUP_TARGET_DESIGNATION_V1' and value['authority'] is False,'GROUP_TARGET_DESIGNATION_PROFILE')
    _id(value['operation_id']);_selector(value['selector'])
    for key in ('binding_sha','manifest_sha','capsule_sha','child_sha','upload_map_sha','reservation_sha','registration_sha','registration_proof_sha'):_hash(value[key])
    need(value['manifest_sha']==value['selector']['content_digest'],'GROUP_TARGET_MANIFEST_SHA')
    return value


def designation_payload(self):
    self.check();candidate=_designation(json.loads(canonical(self.designation)))
    mid=candidate['manifest_sha'];identity='group-target-'+mid
    return {'preview_id':identity,'source_kind':self.manifest['binding']['source_kind'],'input_sha':candidate['capsule_sha'],
        'request_key':identity,'scope_sha':digest({'profile':'GROUP_TARGET_DESIGNATION_SCOPE_V1','binding_sha':candidate['binding_sha'],
        'operation_id':candidate['operation_id'],'manifest_sha':mid}),'candidate':candidate,'evidence_sha':candidate['reservation_sha']}


TargetPreparationScope.designation_payload=designation_payload


def target_before_event_in(db,account,kind,payload):
    c=payload.get('candidate') if type(payload) is dict and kind=='PREVIEW' else None
    profile=c.get('profile') if type(c) is dict else None
    if type(profile) is not str or not profile.startswith('GROUP_TARGET_DESIGNATION'):return
    _designation(c)
    scope=next((s for s in _ISSUED.values() if s.db is db and s.designation==c),None)
    need(scope is not None and account==c['binding_sha'],'GROUP_TARGET_DESIGNATION_SCOPE_REQUIRED')
    # Exact wrapper is derived from the original files, never caller budget.
    expected=scope.designation_payload()
    need(all(payload[k]==v for k,v in expected.items()) and payload['binding_sha']==account,'GROUP_TARGET_DESIGNATION_WRAPPER')
    scope.admit_designation(c)


def _history_workflow(policy,path,binding,*,db,history_locators):
    from .draft_group_runtime_host import ExistingHistoryStoreView
    from .contracts import Actor
    from types import SimpleNamespace
    from .draft_group_history_context import require_history
    require_history(policy,db,history_locators)
    workflow=object.__new__(OwnWorkflow);workflow.history_locators=history_locators;workflow.db=ExistingHistoryStoreView(path,policy);workflow.policy=policy
    profile=SimpleNamespace(actor=Actor(binding['tenant'],binding['principal'],binding['client'],binding['session']),
        connection_id=binding['connection'],account_id=binding['account'],resource_id=binding['resource'],source_kind=binding['source_kind'],binding=lambda:dict(binding))
    return workflow,profile


def read_validated_target_designation_in(db,c,policy, *, history_locators=None):
    from .draft_group_read_family_store import _history_file_guard
    from .own_workflow import stored
    from .own_lineage import seal
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    from .draft_group_target_files import PinnedTargetFiles
    _designation(c);files=PinnedTargetFiles(policy,lambda:_history_file_guard(policy))
    r=files.read('reservation',c['manifest_sha'],expected_sha=c['reservation_sha']);h=files.read('child',c['child_sha'])
    cap=files.read('execution',c['capsule_sha']);u=files.read('upload_reuse',c['upload_map_sha'])
    reg=files.read('registration',c['registration_sha']);proof=files.read('proof',c['registration_proof_sha'])
    rv,hv,cv,uv=r.value,h.value,cap.value,u.value
    need(rv['selector']==c['selector']==hv['selector']==uv['target_selector'] and rv['manifest_sha']==hv['manifest_sha']==uv['target_manifest_sha']==c['manifest_sha']
         and rv['operation_id']==hv['operation_id']==uv['operation_id']==c['operation_id']
         and rv['registration_sha']==cv['registration_sha']==c['registration_sha'] and rv['proof_sha']==c['registration_proof_sha']
         and rv['capsule_sha']==c['capsule_sha'] and proof.value['registration_sha']==c['registration_sha']
         and digest(hv['binding'])==c['binding_sha'] and rv['binding']==hv['binding']==cv['binding']==uv['binding']==reg.value['binding'],'GROUP_TARGET_HISTORY_FILES')
    need(any(x['sha256']==c['child_sha'] for x in cv['children']) and any(x['sha256']==c['upload_map_sha'] for x in hv['upload_reuse']),'GROUP_TARGET_HISTORY_CAPSULE')
    row=db.execute('SELECT * FROM own_articles WHERE version=?',(c['selector']['version'],)).fetchone()
    need(row is not None and row['manifest']==hv['manifest_json'] and row['digest']==c['manifest_sha'],'GROUP_TARGET_HISTORY_ROW_MISSING')
    manifest=stored(row['manifest'],row['digest']);need(manifest['bundle_id']==c['selector']['bundle_id'] and manifest['binding']==hv['binding'],'GROUP_TARGET_HISTORY_MANIFEST')
    need(seal(db,manifest)['legacy']==0,'GROUP_TARGET_HISTORY_LINEAGE')
    inputs=[r for r in db.execute("SELECT * FROM own_inputs WHERE kind='prepare' AND tenant=? AND principal=? AND connection=?",tuple(manifest['binding'][k] for k in ('tenant','principal','connection')))
        if stored(r['result'],r['result_digest']).get('version')==manifest['version']]
    need(len(inputs)==1,'GROUP_TARGET_HISTORY_INPUT')
    result=stored(inputs[0]['result'],inputs[0]['result_digest'])
    need(result=={'bundle_id':manifest['bundle_id'],'version':manifest['version'],'revision':manifest['revision'],'content_digest':c['manifest_sha']},'GROUP_TARGET_HISTORY_INPUT')
    history,p=_history_workflow(policy,policy.root/'state.sqlite3',manifest['binding'],db=db,history_locators=history_locators);facts=[];proof_receipts=[]
    need(len(uv['entries'])==len(manifest['assets']),'GROUP_TARGET_HISTORY_UPLOAD_COVERAGE')
    for asset,entry in zip(manifest['assets'],uv['entries']):
        original=entry['original_upload'];actual,receipt=read_original_upload_success_with_proofs_in(history,db,p,original['base_step_pin']['id'], history_locators=history_locators)
        need(canonical(actual['proof_files'])==canonical(original['proof_files']),'GROUP_TARGET_HISTORY_PROOF_FILES')
        receipt.collective_fence();proof_receipts.append(receipt)
        sm=entry['source_member'];members=[m for m in hv['members'] if digest(m)==sm['member_evidence_sha']]
        need(len(members)==1 and sm['article_id']==members[0]['article_id'] and sm['version_sha']==members[0]['version_sha']
             and sm['source_manifest_selector']==actual['selector'] and sm['source_asset_slot']==actual['slot']
             and sm['source_asset_ref']==actual['asset']['asset_ref'],'GROUP_TARGET_HISTORY_SOURCE_MEMBER')
        need(entry['target_asset']==asset,'GROUP_TARGET_HISTORY_ASSET')
        for key in ('selector','asset','operation','slot','base_step_pin','snapshot','result_digest'):need(canonical(actual[key])==canonical(original[key]),'GROUP_TARGET_HISTORY_UPLOAD')
        saved=entry['source_save']
        if saved is not None:
            # Parent direct history has no outer OwnStore step validator. The
            # complete original Save/proof reader must be nonrecursive before
            # this branch can certify physical evidence; row/hash is not it.
            hold('GROUP_TARGET_SOURCE_SAVE_HISTORY_READER_REQUIRED')
        facts.append({'target_slot':entry['target_slot'],'mapping':actual['mapping'],'snapshot':actual['snapshot']})
    metadata=target_article_metadata(manifest,hv)
    projected=derive_reuse_projection(manifest,facts,article_metadata=metadata)
    need(canonical(projected['projection'])==hv['projection_json'],'GROUP_TARGET_HISTORY_PROJECTION')
    files.collective_fence()
    for receipt in proof_receipts:receipt.collective_fence()
    files.pure_release_fence()
    return TargetDesignationHistoryFacts(files,tuple(proof_receipts))


@dataclass(frozen=True,eq=False)
class TargetDesignationHistoryFacts:
    files:object=field(repr=False)
    proof_receipts:tuple=field(repr=False)
    authority:bool=field(default=False,init=False)


def _validate_designation_history_in(db,c,policy, *, history_locators=None):
    read_validated_target_designation_in(db,c,policy, history_locators=history_locators)
    return None


def check_target_designations_in(db,states,history_policy, *, history_locators=None):
    from .own_connection_policy import ConnectionPolicy
    from .draft_group_store import _load
    selected=[]
    for account,(state,seq,head) in states.items():
        for p in state['previews'].values():
            c=p.get('candidate');profile=c.get('profile') if type(c) is dict else None
            if type(profile) is str and profile.startswith('GROUP_TARGET_DESIGNATION'):
                _designation(c);identity='group-target-'+c['manifest_sha']
                need(account==c['binding_sha'] and p['preview_id']==p['request_key']==identity and p['input_sha']==c['capsule_sha']
                     and p['scope_sha']==digest({'profile':'GROUP_TARGET_DESIGNATION_SCOPE_V1','binding_sha':account,'operation_id':c['operation_id'],'manifest_sha':c['manifest_sha']})
                     and p['evidence_sha']==c['reservation_sha'],'GROUP_TARGET_HISTORY_WRAPPER')
                selected.append(c)
    if not selected:return
    need(type(history_policy) is ConnectionPolicy,'GROUP_TARGET_HISTORY_POLICY_REQUIRED')
    need(len({c['manifest_sha'] for c in selected})==len(selected),'GROUP_TARGET_HISTORY_DUPLICATE')
    for c in selected:_validate_designation_history_in(db,c,history_policy, history_locators=history_locators)


_APPROVAL_ISSUED={}
_APPROVAL_FACTS={}
_APPROVAL_HELPERS={}


@dataclass(frozen=True,slots=True)
class _ApprovalFacts:
    value:object=field(repr=False)
    host:object=field(repr=False)
    entry:object=field(repr=False)
    scope:object=field(repr=False)
    source:object=field(repr=False)
    context:object=field(repr=False)
    db:object=field(repr=False)
    epoch:int
    thread:int
    profile:object=field(repr=False)
    workflow:object=field(repr=False)
    manifest:object=field(repr=False)
    manifest_json:str=field(repr=False)
    profile_json:str=field(repr=False)
    scope_json:str=field(repr=False)
    operation_id:str
    binding_sha:str
    prepared:object=field(repr=False)
    helpers:tuple=field(repr=False)
    prepared_check:object=field(repr=False)
    host_registry:object=field(repr=False)
    scope_registry:object=field(repr=False)
    admitting:object=field(repr=False)
    thread_get:object=field(repr=False)
    history_locators:object=field(repr=False)


def _approval_profile_image(profile):
    need(type(profile) is _ApprovalProfile and type(profile.actor) is _ApprovalActor
         and type(profile.evidence_tuple) is tuple and type(profile.granted_actions) is frozenset
         and all(type(a) is str for a in profile.granted_actions)
         and all(type(e) is _ApprovalEvidence for e in profile.evidence_tuple),'GROUP_APPROVAL_PROFILE_CHANGED')
    values=dict(vars(profile));values['actor']=dict(vars(profile.actor))
    values['evidence_tuple']=[dict(vars(e)) for e in profile.evidence_tuple]
    values['granted_actions']=sorted(profile.granted_actions)
    _plain(values);return canonical(values)


def _approval_tcb_check(helpers):
    # All lookups below are plain retained module/global dictionaries. Check
    # every fixed leaf before invoking any of them in the unlinked SQL gap.
    for namespace,name,original,code in helpers:
        if name=='__mro_identity__':
            bases=type.__getattribute__(namespace,'__bases__');mro=type.__getattribute__(namespace,'__mro__')
            if (len(bases)!=len(original[0]) or any(a is not b for a,b in zip(bases,original[0]))
                    or len(mro)!=len(original[1]) or any(a is not b for a,b in zip(mro,original[1]))):
                raise _ApprovalError('GROUP_APPROVAL_TCB_CHANGED')
            continue
        if name is None:
            if tuple(namespace)!=original:raise _ApprovalError('GROUP_APPROVAL_TCB_CHANGED')
            continue
        if namespace.get(name) is not original or (code is not None and original.__code__ is not code):
            raise _ApprovalError('GROUP_APPROVAL_TCB_CHANGED')


def _approval_helpers(*objects):
    from types import FunctionType,ModuleType
    from . import draft_group_transport as transport
    roots=(_approval_pure,_approval_tcb_check,_approval_profile_image,need,hold,_plain,canonical,
           transport.validate_prepared_identity_pure)
    pins=[];visited=set();classes=set()
    def pin(namespace,name,value,descend=True):
        key=(id(namespace),name)
        if key in visited:return
        visited.add(key);code=value.__code__ if type(value) is FunctionType else None
        pins.append((namespace,name,value,code))
        if type(value) in (staticmethod,classmethod):pin({'function':value.__func__},'function',value.__func__,False)
        if type(value) is property:
            for name,fn in (('get',value.fget),('set',value.fset),('del',value.fdel)):
                if fn is not None:pin({name:fn},name,fn,False)
        if type(value) is type:
            pins.append((value,'__mro_identity__',(type.__getattribute__(value,'__bases__'),type.__getattribute__(value,'__mro__')),None))
            for base in type.__getattribute__(value,'__mro__'):
                if id(base) in classes:continue
                classes.add(id(base));attrs=type.__getattribute__(base,'__dict__')
                pins.append((attrs,None,tuple(attrs),None))
                for attr,member in attrs.items():pin(attrs,attr,member,False)
        if descend and type(value) is FunctionType and value.__module__.startswith('wce.'):
            for item in value.__code__.co_names:
                if item not in value.__globals__:continue
                child=value.__globals__[item];pin(value.__globals__,item,child)
                if type(child) is ModuleType:
                    for attr in value.__code__.co_names:
                        if attr in vars(child):pin(vars(child),attr,vars(child)[attr])
    for fn in roots:pin(fn.__globals__,fn.__name__,fn)
    for cls in (_ApprovalFacts,GroupApprovalScope,_ApprovalProfile,_ApprovalActor,_ApprovalEvidence):
        pin(globals(),cls.__name__ if cls.__name__ in globals() else '_Approval'+{'OwnProfile':'Profile','Actor':'Actor','OwnerEvidence':'Evidence'}[cls.__name__],cls)
    for index,value in enumerate(objects):
        # The private tuple retains this class even when no module alias exists.
        namespace={'class':type(value)};pin(namespace,'class',type(value))
    return tuple(pins),transport.validate_prepared_identity_pure


def _approval_pure(value):
    """No FD, SQL replay, current/source observation or clock in the ADD gap."""
    helpers=_APPROVAL_HELPERS.get(id(value))
    if helpers is not None:_approval_tcb_check(helpers)
    f=_APPROVAL_FACTS.get(id(value))
    need(type(value) is GroupApprovalScope and f is not None and f.value is value
         and _APPROVAL_ISSUED.get(id(value)) is value,'GROUP_APPROVAL_CONTEXT_CHANGED')
    need(type(value.epoch) is int and type(value.operation_id) is str and type(value.binding_sha) is str
         and value.host is f.host and value.entry is f.entry and value.scope is f.scope
         and value.db is f.db and value.profile is f.profile and value.workflow is f.workflow
         and value.manifest is f.manifest and value.prepared is f.prepared
         and value.epoch==f.epoch and value.operation_id==f.operation_id and value.binding_sha==f.binding_sha,
         'GROUP_APPROVAL_CONTEXT_CHANGED')
    need(type(f.entry.thread) is int and type(f.entry.id) is str and f.entry.closed is False
         and f.thread==f.thread_get() and f.entry.thread==f.thread
         and f.host_registry.get(f.entry.id) is f.entry and f.entry.issued.get(id(value)) is value
         and f.host.entry is f.entry and f.entry.service.workflow is f.workflow
         and type(f.db) is OwnedConnection and f.db._content_disabled is False
         and type(f.db._transaction_generation) is int and f.db._transaction_generation==f.epoch and f.db.in_transaction
         and f.admitting.get()==(id(f.db),f.binding_sha,f.operation_id),'GROUP_APPROVAL_CONTEXT_CHANGED')
    pin=f.scope_registry.get(id(f.scope))
    need(pin is not None and pin[0] is f.scope and pin[1] is f.source and pin[2] is f.context
         and f.entry.issued.get(id(f.scope)) is f.scope and f.scope.host is f.host and f.scope.entry is f.entry
         and f.scope.source is f.source and f.scope.context is f.context,'GROUP_APPROVAL_SCOPE_CHANGED')
    _plain(f.scope.details);_plain(f.manifest)
    need(pin[3]==f.scope_json==canonical(f.scope.details) and canonical(f.manifest)==f.manifest_json
         and _approval_profile_image(f.profile)==f.profile_json,'GROUP_APPROVAL_CONTEXT_CHANGED')
    f.prepared_check(f.prepared)
    return f


class GroupApprovalScope:
    def __init__(self):hold('GROUP_APPROVAL_ISSUER_REQUIRED')
    def finish_pure(self):
        _approval_pure(self);return None
    def check(self):
        from .draft_group_store import _ADMITTING,check_writer,_account_writer_states
        _approval_pure(self)
        self.entry.held_pure()
        need(_ADMITTING.get()==(id(self.db),self.binding_sha,self.operation_id),'GROUP_APPROVAL_ADMITTING_REQUIRED')
        check_writer(self.db,self.binding_sha,operation_id=self.operation_id)
        self.host.current_no_token_in(None,self.scope.source, history_locators=None)
        for state in _account_writer_states(self.db,self.entry.policy, history_locators=_APPROVAL_FACTS[id(self)].history_locators):
            if any(b['state'] not in ('COMPLETE','CANCELLED_BEFORE_ADMISSION') for b in state['batches'].values()):
                need(state['binding_sha']==self.binding_sha,'GROUP_APPROVAL_OTHER_POOL_ACTIVE')
        need(self.profile is next(iter(self.workflow.registry.profiles.values())) and self.profile.binding()==self.manifest['binding'],'GROUP_APPROVAL_PROFILE_CHANGED')
        self.host.pure_release_fence();return None


@contextmanager
def group_approval_in(host,scope,db,profile,manifest,*,prepared, history_locators=None):
    from .draft_group_runtime_host import validate_admission_scope,_REGISTRY,_ADMISSION_SCOPE_ISSUED,_THREAD
    from .draft_group_transport import validate_prepared
    import threading
    from .draft_group_store import _ADMITTING,_current_child
    from .own_workflow import stored
    validate_admission_scope(scope, history_locators=None)
    need(scope.host is host and scope.details['ledger_kind']=='CHILD' and type(db) is OwnedConnection and db.in_transaction,'GROUP_APPROVAL_SCOPE_REQUIRED')
    binding=digest(manifest['binding']);operation=scope.details['operation_id']
    need(_ADMITTING.get()==(id(db),binding,operation),'GROUP_APPROVAL_ADMITTING_REQUIRED')
    host.current_no_token_in(db,scope.source, history_locators=history_locators);state=host._group_state_in(db);op,batch=_current_child(state,operation)
    need(op['state'] in ('PLANNED','BASELINES_OBSERVED') and op['own_link'] is None,'GROUP_APPROVAL_PARENT_STATE')
    workflow=host.entry.service.workflow
    actual,d=workflow._bundle(db,profile,manifest['bundle_id'],manifest['version'])
    need(canonical(actual)==canonical(manifest),'GROUP_APPROVAL_MANIFEST')
    designation=[p['candidate'] for p in state['previews'].values() if type(p.get('candidate')) is dict
        and p['candidate'].get('profile')=='GROUP_TARGET_DESIGNATION_V1' and p['candidate'].get('manifest_sha')==d]
    need(len(designation)==1 and designation[0]['operation_id']==operation,'GROUP_APPROVAL_DESIGNATION')
    _validate_designation_history_in(db,designation[0],host.entry.policy, history_locators=history_locators)
    validate_prepared(prepared)
    value=object.__new__(GroupApprovalScope);value.host=host;value.entry=host.entry;value.scope=scope
    value.db=db;value.epoch=_transaction_marker(db);value.profile=profile;value.workflow=workflow;value.manifest=actual
    value.operation_id=operation;value.binding_sha=binding;value.prepared=prepared
    helpers,prepared_check=_approval_helpers(host,host.entry,scope,scope.source,scope.context,db,profile,workflow,prepared)
    facts=_ApprovalFacts(value,host,host.entry,scope,scope.source,scope.context,db,value.epoch,threading.get_ident(),
        profile,workflow,actual,canonical(actual),_approval_profile_image(profile),canonical(scope.details),operation,binding,prepared,
        helpers,prepared_check,_REGISTRY,_ADMISSION_SCOPE_ISSUED,_ADMITTING,_THREAD,history_locators)
    _APPROVAL_ISSUED[id(value)]=value;host.entry.issued[id(value)]=value
    _APPROVAL_FACTS[id(value)]=facts
    _APPROVAL_HELPERS[id(value)]=helpers
    pure=_approval_pure;pure_code=pure.__code__;tcb_check=_approval_tcb_check;tcb_code=tcb_check.__code__;issued=host.entry.issued
    try:
        GroupApprovalScope.check(value)
        yield value
        if pure.__code__ is not pure_code or tcb_check.__code__ is not tcb_code:
            raise _ApprovalError('GROUP_APPROVAL_TCB_CHANGED')
        tcb_check(helpers);pure(value)
    finally:
        _APPROVAL_HELPERS.pop(id(value),None);_APPROVAL_FACTS.pop(id(value),None);_APPROVAL_ISSUED.pop(id(value),None);issued.pop(id(value),None)


def target_article_metadata(manifest,child_value):
    metadata=PersistentWorkflow._request_draft_metadata(manifest)
    raw=(canonical(metadata)+'\n').encode();evidence=child_value['expected_metadata']
    need(evidence['kind']=='METADATA' and evidence['sha256']==sha256(raw).hexdigest() and evidence['size']==len(raw),'GROUP_TARGET_METADATA_CHANGED')
    return metadata


def target_after_event_in(db,account=None,kind=None,payload=None):
    """Only pure issued-state and SQL validation inside the D→INSERT gap."""
    c=payload.get('candidate') if type(payload) is dict and kind=='PREVIEW' else None
    profile=c.get('profile') if type(c) is dict else None
    if type(profile) is not str or not profile.startswith('GROUP_TARGET_DESIGNATION'):return False
    from .draft_group_runtime_host import _REGISTRY,_THREAD
    _designation(c)
    scope=next((s for s in _ISSUED.values() if s.db is db and s.designation==c),None)
    need(scope is not None and scope.phase=='INSERT_REQUIRED' and scope.epoch==_transaction_marker(db)
         and scope.entry.thread==_THREAD() and not scope.entry.closed and _REGISTRY.get(scope.entry.id) is scope.entry
         and scope.entry.issued.get(id(scope)) is scope and account==c['binding_sha'],'GROUP_TARGET_GAP_CONTEXT_REQUIRED')
    row=db.execute('SELECT * FROM group_previews WHERE account_key=? AND preview_id=?',(account,'group-target-'+c['manifest_sha'])).fetchone()
    need(row is not None and row['input_sha']==c['capsule_sha'] and row['request_key']=='group-target-'+c['manifest_sha'],'GROUP_TARGET_GAP_SQL')
    value=json.loads(row['value']);need(canonical(value)==row['value'] and digest(value)==row['value_sha']
        and value['candidate']==c and value['evidence_sha']==c['reservation_sha'],'GROUP_TARGET_GAP_SQL')
    return True


def _target_designation_for(db,manifest_sha):
    from .draft_group_store import _load
    found=[]
    for account, in db.execute('SELECT account_key FROM group_pools ORDER BY account_key'):
        state,_,_=_load(db,account)
        for preview in state['previews'].values():
            c=preview.get('candidate')
            if type(c) is dict and c.get('profile')=='GROUP_TARGET_DESIGNATION_V1' and c.get('manifest_sha')==manifest_sha:found.append(c)
    need(len(found)<=1,'GROUP_TARGET_MULTIPLE_DESIGNATIONS')
    return None if not found else found[0]


def validate_target_write_in(workflow,db,profile,manifest,action, *, history_locators=None):
    from .draft_group_runtime_host import _ACTIVE,GroupAdmissionScope
    from .draft_group_store import _ADMITTING,_load,_current_child
    candidate=_target_designation_for(db,digest(manifest))
    if candidate is None:return None
    need(action in ('ADD_UPLOAD_REUSE','CHILD_APPROVAL'),'GROUP_TARGET_ORDINARY_WRITE_FORBIDDEN')
    policy=getattr(workflow,'policy',None);need(policy is not None,'GROUP_TARGET_HISTORY_POLICY_REQUIRED')
    _validate_designation_history_in(db,candidate,policy, history_locators=history_locators)
    entry=getattr(_ACTIVE,'entry',None);admitting=_ADMITTING.get()
    if entry is not None and entry.service.workflow is workflow and admitting==(id(db),candidate['binding_sha'],candidate['operation_id']):
        scopes=[s for s in entry.issued.values() if type(s) is GroupAdmissionScope and s.details['ledger_kind']=='CHILD'
            and s.details['operation_id']==candidate['operation_id'] and s.details['account_key']==candidate['binding_sha']]
        need(len(scopes)==1,'GROUP_TARGET_ADMISSION_SCOPE_REQUIRED');scope=scopes[0]
        entry.held_pure();scope.host.current_no_token_in(None,scope.source, history_locators=None)
        state,_,_=_load(db,candidate['binding_sha']);_current_child(state,candidate['operation_id'])
        return {'mode':'ACTUAL_GROUP_ADMITTING','operation_id':candidate['operation_id'],'authority':False}
    need(action=='ADD_UPLOAD_REUSE','GROUP_TARGET_APPROVAL_FORBIDDEN')
    links=db.execute('SELECT * FROM group_own_step_links WHERE account_key=? AND operation_id=?',(candidate['binding_sha'],candidate['operation_id'])).fetchall()
    need(len(links)==1,'GROUP_TARGET_NOT_ADMITTED')
    row=db.execute('SELECT * FROM own_steps WHERE id=?',(links[0]['step_id'],)).fetchone()
    need(row is not None and row['manifest_digest']==candidate['manifest_sha'] and row['operation']=='add','GROUP_TARGET_HISTORY_LINK')
    return {'mode':'HISTORICAL_READ_ONLY','operation_id':candidate['operation_id'],'authority':False}


def validate_target_approval_in(workflow,db,profile,manifest):
    candidate=_target_designation_for(db,digest(manifest))
    if candidate is None:return None
    scopes=[s for s in _APPROVAL_ISSUED.values() if s.workflow is workflow and s.db is db and s.profile is profile and s.manifest==manifest]
    need(len(scopes)==1,'GROUP_TARGET_ORDINARY_APPROVAL_FORBIDDEN')
    GroupApprovalScope.check(scopes[0]);return None


def validate_target_dispatch_in(workflow,db,profile,manifest,operation,slot, *, history_locators=None):
    if _target_designation_for(db,digest(manifest)) is None:return None
    need(operation=='add' and slot=='draft','GROUP_TARGET_MEDIA_UPLOAD_FORBIDDEN')
    return validate_target_write_in(workflow,db,profile,manifest,'ADD_UPLOAD_REUSE', history_locators=history_locators)
