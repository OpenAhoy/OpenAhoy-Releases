"""Unarmed actual-Host Operator proposal; separate W1/W2/current registries.

No Native interpretation, OwnProfile construction, token, network, migration or
Parent issuer. JSON containers and shared QA joins remain non-authority facts.
Root must wire the explicit profile dispatch and include these leaves in TCB.
"""
from . import draft_group_operator_time_v2 as time06
from dataclasses import dataclass, replace
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
import time
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .draft_group_contracts import canonical, digest
from . import draft_group_operator_source_codec as codec
from . import draft_group_operator_materials as materials

PHASES = ('INSPECTED_NO_ADMISSION','COMPLETE_SERVICE_NO_ADMISSION',
          'REVIEW_PENDING','REVIEW_COMMITTED','ADMISSION_READY')
_BINDINGS=WeakKeyDictionary();_HOSTS=WeakKeyDictionary();_OBSERVERS=WeakKeyDictionary()
_W1=WeakKeyDictionary();_W2=WeakKeyDictionary();_QA=WeakKeyDictionary()


def need(value, code):
    if value is not True:raise WCEError('GROUP_OPERATOR_'+code)


def is_operator(host):
    return host.chain.source['profile']==codec.SOURCE_PROFILE


def _host(host):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate,_REGISTRY
    from .draft_group_operator_review_chain import FixedOperatorHostPins,FixedOperatorReviewChain
    need(type(host) is GroupRuntimeHost and type(host.entry) is GroupExecutionGate
         and _REGISTRY.get(host.entry.id) is host.entry
         and host.entry.thread==threading.get_ident(),'ACTUAL_HOST_REQUIRED')
    GroupExecutionGate.held_pure(host.entry)
    need(type(host.pins) is FixedOperatorHostPins
         and type(host.chain) is FixedOperatorReviewChain
         and host.chain.entry is host.entry and host.chain.pins is host.pins
         and host.entry.source_kind==codec.ACCOUNT_SOURCE_KIND
         and is_operator(host),'FIXED_OPERATOR_CHAIN_REQUIRED')
    return host.entry


def _view(host):
    _host(host);host.chain.check()
    # The chain owns this exact frozen pure view and its raw-byte image. It is
    # data only; no current binding or qualification recursion occurs here.
    return host.chain.operator_semantics


def original_root_evidence(host):return _view(host).original_root_evidence
def artifact_inventory(host):return _view(host).artifact_inventory
def member_identities(host):return _view(host).member_identities


def source_generation(host,facts):
    _host(host)
    from .draft_group_operator_semantics import operator_generation_values
    return operator_generation_values(facts)


class OperatorAcceptedRequest:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_OPERATOR_W1_PRIVATE_ISSUER_REQUIRED')
    @property
    def authority(self):return False


class OperatorCaseScope:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_OPERATOR_W2_PRIVATE_ISSUER_REQUIRED')
    @property
    def authority(self):return False


class GroupCurrentOperatorSourceBinding:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_OPERATOR_CURRENT_PRIVATE_ISSUER_REQUIRED')
    @property
    def authority(self):return False


class GroupOperatorSourceObserver:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_OPERATOR_OBSERVER_PRIVATE_ISSUER_REQUIRED')
    def pure_release_fence(self):
        facts=_OBSERVERS.get(self)
        need(facts is not None and facts.observer is self,'OBSERVER_UNISSUED')
        _fence(facts)
    def prepare_release(self,raw):
        facts=_OBSERVERS.get(self)
        need(facts is not None and raw==facts.host.chain.files['source'].raw,'SOURCE_CHANGED')
        _fence(facts)
        return json.loads(facts.observation_raw)
    def close(self):
        facts=_OBSERVERS.get(self)
        if facts is not None:_close_if_issued(facts.host,facts.binding)


@dataclass(frozen=True)
class _Live:
    host:object
    entry:object
    binding:object
    observer:object
    resources:object
    observation_raw:str
    pass_raw:str
    inspection:object
    inspection_raw:str
    phase:str
    owner:tuple
    policy_raw:str
    deadline:float
    not_after_ms:int
    w1:object=None
    w2:object=None
    service:object=None
    registry:object=None
    case_row_sha:str|None=None


@dataclass(frozen=True)
class _QaRuntime:
    root:Path
    scope:str


class _GroupQaResources:
    """Actual entry-owned pinned files, not an imitation PREUPLOAD owner."""
    def __init__(self,*args,**kwargs):raise WCEError('GROUP_OPERATOR_QA_OWNER_PRIVATE_REQUIRED')
    def guard(self):
        record=_QA.get(self)
        need(record is not None and record[0] is self.host and not self.closed
             and self.owner==(os.getpid(),threading.get_ident()),'QA_OWNER_UNISSUED')
        entry=_host(self.host);self.host.chain.check()
        need(entry is record[1] and time.monotonic()<entry.deadline
             and canonical(entry.policy.value)==self.policy_raw,'QA_OWNER_CHANGED')
        from .own_body_recovery import code_scope
        need(code_scope()==self.runtime.scope==self.host.chain.config['candidate_scope'],
             'QA_RUNTIME_SOURCE_CHANGED')
        from .draft_group_pin_resources import MAX_RAW_BYTES
        active_bytes=0
        if self.active_files is not None:
            from .own_preupload_selected_files import SelectedMemberFiles
            need(type(self.active_files) is SelectedMemberFiles
                 and self.active_files.parent_resources is self and not self.active_files.closed,
                 'ACTIVE_SELECTED_OWNER_CHANGED')
            active_bytes=self.active_files.pool.raw_bytes+self.active_files.evidence_bytes
        need(entry.pin_pool.raw_bytes+self.pool.raw_bytes+self.evidence_bytes+active_bytes
             <=MAX_RAW_BYTES,'QA_RESOURCE_BOUND')
        from .draft_group_host_review import _derived_budget
        _derived_budget(self.host)
        self.pool.check_all(owner=self)
        for view in self.views.values():view.check()
        entry.held_pure()
        return None
    def values(self):
        self.guard()
        return materials.detached(self.projection)
    def acquire_evidence(self,ref):
        from .own_preupload_qa import reference
        from .draft_group_pin_resources import MAX_RAW_BYTES
        self.guard();reference(ref)
        key=Path(ref['path']);prior=self.views.get(key)
        if prior is not None:
            need(prior.sha==ref['sha256'] and len(prior.raw)==ref['bytes'],'QA_REF_CHANGED')
            return prior
        active_bytes=(0 if self.active_files is None else
                      self.active_files.pool.raw_bytes+self.active_files.evidence_bytes)
        need(self.host.entry.pin_pool.raw_bytes+self.pool.raw_bytes+self.evidence_bytes
             +active_bytes+self.host.adapter.derived_cache.retained_bytes+ref['bytes']<=MAX_RAW_BYTES,'QA_RESOURCE_BOUND')
        from .own_preupload_sources import _EvidenceView
        view=_EvidenceView(self,key,ref['sha256'],ref['bytes'])
        try:
            need(len(view.raw)==ref['bytes'],'QA_RESOURCE_BOUND')
            self.views[key]=view
        except BaseException as original:
            from .draft_group_pin_resources import close_all
            close_all([view.close],original);raise
        self.guard();return view
    def close(self,*,original=None):
        if not self.closed:
            self.closed=True;_QA.pop(self,None)
            from .draft_group_pin_resources import close_all
            close_all([view.close for view in reversed(tuple(self.views.values()))]
                      +[lambda:self.pool.close(owner=self,original=original)],original)


def _qa_resources(host):
    entry=_host(host);chain=host.chain;container=materials.qa_set(chain.qa_set)
    value=object.__new__(_GroupQaResources)
    value.host,value.owner,value.closed=host,(os.getpid(),threading.get_ident()),False
    from .draft_group_pin_resources import PinPool
    value.pool,value.views,value.evidence_bytes=PinPool(value),{},0
    value.active_files=None
    value.runtime=_QaRuntime(Path(__file__).absolute().parents[1],chain.config['candidate_scope'])
    value.policy_raw=canonical(entry.policy.value)
    value.projection=materials.projection(json.loads(chain.qa_files['member_projection'].raw))
    value.selection=chain.qa_files['selection']
    _QA[value]=(host,entry)
    try:
        for role,ref_name in (('selection','selection_ref'),('artifact_roots','artifact_roots_ref'),
                ('member_projection','member_projection_ref'),('dossier','dossier_ref'),
                ('acceptance','acceptance_ref')):
            pin=chain.qa_files[role];ref=container[ref_name];pin.check()
            need(str(pin.path)==ref['path'] and pin.sha==ref['sha256']
                 and len(pin.raw)==ref['size'],'QA_SET_REF_CHANGED')
        need(value.selection.raw==chain.files['selection'].raw,'QA_SELECTION_CHANGED')
        value.guard();entry.stack.callback(value.close)
        return value
    except BaseException as original:value.close(original=original);raise


@contextmanager
def _selected_files(resources,roots,member):
    from .own_preupload_selected_files import SelectedMemberFiles
    need(resources.active_files is None,'SELECTED_REENTRANT')
    from .draft_group_host_review import _derived_budget
    _derived_budget(resources.host,sum(item['size'] for item in (member['html'],member['body'],*[image['artifact'] for image in member['images']])))
    with SelectedMemberFiles(resources,roots,member,
            extra_raw_bytes=resources.host.entry.pin_pool.raw_bytes+resources.host.adapter.derived_cache.retained_bytes) as files:
        resources.active_files=files
        try:
            resources.guard()
            yield files
        finally:resources.active_files=None


def _check_qa(resources):
    need(type(resources) is _GroupQaResources and resources in _QA,'QA_OWNER_UNISSUED')
    resources.guard();host=resources.host;container=materials.qa_set(host.chain.qa_set)
    need(materials.qa_binding_projection_sha(host.chain.runtime_policy['binding'],
         host.chain.source,container)==container['binding_projection_sha256'],
         'QA_BINDING_PROJECTION_CHANGED')
    from .draft_group_selected_source_codec import decode_manifest
    selected,_,selection_sha=decode_manifest(resources.selection.raw,
        expected_member_projection=tuple(tuple(row) for row in resources.projection['member_projection']))
    need(selected['queue_sha256']==host.chain.source['original_queue_sha']
         and selected['request_set_sha256']==host.chain.source['original_request_set_sha'],
         'ORIGINAL_REQUEST_SET_CHANGED')
    roots_value=json.loads(host.chain.qa_files['artifact_roots'].raw)
    flat=[row for row in roots_value['roots'] if row['kind']=='ORIGINAL_FLAT_ROOT']
    need(len(flat)==1,'ORIGINAL_FLAT_ROOT_REQUIRED')
    from .own_preupload_selected_files import decode_roots
    roots,_=decode_roots(host.chain.qa_files['artifact_roots'].raw,selected,
        Path(flat[0]['absolute_path']),expected_flat_manifest_ref=roots_value['flat_manifest_ref'])
    resources.acquire_evidence(roots_value['flat_manifest_ref'])
    from .own_preupload_qa import CONSUMER_FILES
    from .own_content_qa_join import check_import_package_contents
    consumers=tuple(CONSUMER_FILES)+('draft_group_host_operator.py','draft_group_operator_materials.py','draft_group_pure_derived_cache.py','draft_group_operator_time_v2.py')
    facts=check_import_package_contents(resources,
        dossier_ref=materials.evidence_ref(container['dossier_ref']),
        acceptance_ref=materials.evidence_ref(container['acceptance_ref']),
        selection_sha256=selection_sha,binding_projection_sha256=container['binding_projection_sha256'],
        member_ids=tuple(row['article_id'] for row in selected['members']),
        selected_roots=roots,expected_consumer_files=consumers)
    resources.guard()
    return selected,roots,facts


def _read_pass(host,resources,db,history_locators):
    """One actual RO Owned/H pass: exact selected bytes+prepare+all slot proofs."""
    entry=_host(host);entry.full_guard();resources.guard()
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1,'READONLY_OWNED_REQUIRED')
    require_history(entry.policy,db,history_locators)
    from .draft_group_host_review import GroupInputAdapter,_inspection_image
    need(type(host.adapter) is GroupInputAdapter,'ACTUAL_ADAPTER_REQUIRED')
    selected,roots,qa=_check_qa(resources)
    members,relations,mappings=materials.partition_rows(selected,host.chain.semantic,
        host.chain.source,host.chain.prepared_relations,host.chain.postupload_mapping)
    inspection=GroupInputAdapter.inspect_in(host.adapter,db,None)
    expected_identities=[row['member_identity'] for row in mappings]
    need(inspection['members']==member_identities(host)==expected_identities,'MEMBER_PARTITION_CHANGED')
    from .own_selected_history import _PreparedHistoryReader,_policy_binding
    need(_policy_binding(entry.policy,'OPERATOR_ATTESTED')==host.chain.runtime_policy['binding'],
         'CURRENT_ACCOUNT_POLICY_CHANGED')
    from .draft_group_source_members import read_member_derivation,_bind_original_article
    from .draft_group_target_scope import _history_workflow
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    from .draft_group_upload_reuse_values import _upload
    reader=None;actual_relations=[];actual_uploads=[];derivations=[];source_article_ids=[]
    try:
        reader=_PreparedHistoryReader(entry.policy,db,history_locators)
        for selected_member,prepared,mapped in zip(members,relations,mappings):
            entry.loop_guard()
            with _selected_files(resources,roots,selected_member) as files:
                relation=reader.prepared_relation(prepare_request_key=prepared['prepare_request_key'],
                                                  selector=prepared['selector'])
                need(digest(relation)==prepared['prepared_relation_sha256']
                     and relation['parameters_sha256']==selected_member['import_receipt_sha256'],
                     'PREPARED_RELATION_CHANGED')
                approval=selected_member['historical_approval_sha256']
                if approval is None:
                    need(relation['approval_state']=='ABSENT_VERIFIED'
                         and relation['historical_approvals']==[],'HISTORICAL_APPROVAL_CHANGED')
                else:
                    need(any(row['body_sha256']==approval for row in relation['historical_approvals']),
                         'HISTORICAL_APPROVAL_CHANGED')
                derived=read_member_derivation(inspection,mapped['member_identity'])
                need(derived['report_artifact_sha']==mapped['report_artifact_sha']
                     and derived['html_artifact_sha']==selected_member['html']['sha256']
                     and sha256(files.files['html'].raw).hexdigest()==derived['html_artifact_sha'],
                     'SELECTED_ARTIFACT_CHANGED')
                report=derived['report'];selector=selected_member['selector']
                need(report['source_manifest_selector']==selector,'PREPARED_SELECTOR_CHANGED')
                manifest,manifest_sha=reader._bundle_full(db,reader.profile,
                    selector['bundle_id'],selector['version'])
                need(manifest_sha==selector['content_digest'] and relation['assets']==manifest['assets'],
                     'PREPARED_MANIFEST_CHANGED')
                need(len(manifest['document']['articles'])==1
                     and manifest['document']['articles'][0]['id']==prepared['source_article_id'],
                     'SOURCE_ARTICLE_ID_CHANGED')
                from .draft_group_operator_semantics import operator_original_request_sha
                need(mapped['member_identity']=={'article_id':selected_member['article_id'],
                     'original_request_sha':operator_original_request_sha(selected_member['article_id'],relation)},
                     'ORIGINAL_REQUEST_IDENTITY_CHANGED')
                derived=dict(derived,content_source_type=codec.CONTENT_SOURCE_TYPE,
                             source_article_id=prepared['source_article_id'])
                derivations.append(canonical(derived))
                source_article_ids.append(manifest['document']['articles'][0]['id'])
                _,wanted=_bind_original_article(manifest,derived,mapped['member_identity'])
                selected_assets=[{'asset_ref':image['asset_ref'],'role':image['role'],'slot':image['slot'],
                    'declared_type':image['artifact']['media_type'],'size':image['artifact']['size'],
                    'sha256':image['artifact']['sha256']} for image in selected_member['images']]
                need(manifest['assets']==selected_assets,'SELECTED_ASSET_SET_CHANGED')
                article=manifest['document']['articles'][0]
                need(digest({key:article[key] for key in ('title','author','digest','source_url',
                    'cover_dimensions','cover_info','editorial_intent') if key in article})
                    ==selected_member['settings_sha256'],'SELECTED_SETTINGS_CHANGED')
                workflow,profile=_history_workflow(entry.policy,entry.policy.root/'state.sqlite3',
                    manifest['binding'],db=db,history_locators=history_locators)
                claimed=report['upload_mapping'];need(type(claimed) is list,'UPLOAD_MAPPING_REQUIRED')
                seen=set();uploads=[]
                for mapping in claimed:
                    _upload(mapping,False)
                    facts,receipt=read_original_upload_success_with_proofs_in(workflow,db,profile,
                        mapping['base_step_pin']['id'],history_locators=history_locators)
                    for key in ('selector','slot','operation','asset','base_step_pin','snapshot',
                                'result_digest','proof_files'):
                        need(canonical(facts[key])==canonical(mapping[key]),'ORIGINAL_UPLOAD_CHANGED')
                    slot=facts['slot']
                    need(facts['selector']==selector and slot in wanted and slot not in seen
                         and facts['asset']==wanted[slot],'ORIGINAL_UPLOAD_COVERAGE_CHANGED')
                    seen.add(slot);uploads.append(facts);receipt.collective_fence()
                    if not hasattr(host,'_source_upload_receipts'):host._source_upload_receipts={}
                    prior=host._source_upload_receipts.get(mapping['base_step_pin']['id'])
                    if prior is None:host._source_upload_receipts[mapping['base_step_pin']['id']]=receipt
                    else:prior.collective_fence()
                need(seen==set(wanted) and digest(uploads)==mapped['upload_mapping_sha'],
                     'ORIGINAL_UPLOAD_SET_CHANGED')
                actual_relations.append(relation);actual_uploads.append(uploads)
                files.check();reader.check()
        reader._check_all_history()
        from .draft_group_operator_semantics import require_actual_prepared_values
        need(require_actual_prepared_values(selected['members'],relations,mappings,
            actual_relations,source_article_ids,
            authorized_member_ids=host.chain.semantic['semantic_scope']['authorized_member_ids'],
            binding_sha=digest(host.chain.runtime_policy['binding']))==expected_identities,
            'ACTUAL_PREPARED_JOIN_CHANGED')
        need(not db.execute("SELECT s.id FROM own_steps s JOIN own_articles a ON a.digest=s.manifest_digest "
            "WHERE s.operation='add' AND a.bundle IN ("+','.join('?' for _ in members)+") LIMIT 1",
            tuple(member['selector']['bundle_id'] for member in members)).fetchone(),
            'MEMBER_ALREADY_ADMITTED')
    finally:
        if reader is not None:reader.close()
    for receipt in getattr(host,'_source_upload_receipts',{}).values():receipt.collective_fence()
    inspection['member_derivations']=tuple(derivations)
    from .draft_group_host_review import _INSPECTED_INPUTS
    _INSPECTED_INPUTS[host.adapter]=(inspection,_inspection_image(inspection),None)
    resources.guard();entry.full_guard()
    image={'inspection_sha':digest(_inspection_image(inspection)),
        'selection_sha':host.chain.files['selection'].sha,'relations':actual_relations,
        'uploads':actual_uploads,'qa':qa,'policy_sha':digest(entry.policy.value)}
    return inspection,image


def _previous_continuation_in(host,db,history_locators):
    """Read the validated same-family head under this actual RO Owned/H."""
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    from .draft_group_source_review import _replay
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1,'READONLY_OWNED_REQUIRED')
    require_history(host.entry.policy,db,history_locators)
    heads,values=_replay(db,host.entry.policy)
    family=host.chain.source['allowed_read_scope']['family_anchor_sha']
    selected=heads.get(family)
    if selected is None:return None
    prior=values[selected]
    need(prior['profile']==codec.SOURCE_REVIEW_PROFILE
         and prior['family_id']==family
         and prior['original_source_material_sha']==prior['current_source_material_sha']
             ==host.pins.source_sha,'GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
    return codec.validate_observation(prior['current_binding'])


def _observation(host,image,qa_not_after,wall_start,mono_start,previous=None):
    entry=_host(host);chain=host.chain;p=chain.runtime_policy;s=chain.source;m=chain.semantic
    caps=[s['expires_policy']['not_after']*1000,p['original_input_not_after_ms'],
          int(qa_not_after*1000),int((wall_start+entry.deadline-mono_start)*1000)]
    if p['source_rights_expiry']['not_after'] is not None:caps.append(p['source_rights_expiry']['not_after'])
    if previous is not None:caps.append(previous['qualified_not_after_ms'])
    generation=digest(image)
    value={'schema':1,'profile':codec.OBSERVATION_PROFILE,'authority':False,
        'content_source_type':codec.CONTENT_SOURCE_TYPE,'source_material_sha':chain.files['source'].sha,
        'runtime_source_policy_sha':sha256((canonical(p)+'\n').encode()).hexdigest(),
        'binding_sha':digest(p['binding']),'operator_request_identity_sha':s['operator_request_identity_sha'],
        'original_request_set_sha':s['original_request_set_sha'],'account_partition_sha':s['account_partition_sha'],
        'selection_sha':s['selection_ref']['sha256'],'qa_set_sha':s['qa_set_ref']['sha256'],
        'postupload_mapping_sha':s['postupload_mapping_ref']['sha256'],
        'prepared_relations_sha':s['prepared_relation_inventory_ref']['sha256'],
        'semantic_scope_sha':codec.semantic_scope_sha(m),'policy_fingerprint_sha':digest(entry.policy.value),
        'stable_owner':m['stable_owner'],'epoch':p['binding']['epoch'],'generation':p['binding']['generation'],
        'file_generation_sha':generation,'proof_generation_sha':digest(image['uploads']),
        'first_pass_sha':generation,'second_pass_sha':generation,
        'collective_fence_sha':digest({'first':generation,'second':generation,
            'source_sha':chain.files['source'].sha,'runtime_policy_sha':sha256((canonical(p)+'\n').encode()).hexdigest()}),
        'observed_at_ms':int(wall_start*1000),'qualified_not_after_ms':min(caps)}
    value=codec.validate_observation(value)
    if previous is not None:codec.validate_continuation(previous,value)
    return value


def _fence(facts):
    if facts.host.chain.runtime_policy['profile']==time06.POLICY_PROFILE_V2:
        from .draft_group_first_control import time06_current_action_guard
        time06_current_action_guard(facts.host)
    entry=_host(facts.host)
    need(facts.owner==(os.getpid(),threading.get_ident()) and facts.entry is entry
         and not entry.closed and not entry.poisoned
         and canonical(entry.policy.value)==facts.policy_raw
         and time.monotonic()<facts.deadline<=entry.deadline
         and time.time()*1000<facts.not_after_ms,'CURRENT_LIFETIME_CHANGED')
    facts.resources.guard();facts.host.chain.check()
    from .draft_group_host_review import _INSPECTED_INPUTS,_inspection_image
    pin=_INSPECTED_INPUTS.get(facts.host.adapter)
    need(pin is not None and pin[0] is facts.inspection and pin[1]==facts.inspection_raw
         ==_inspection_image(facts.inspection) and pin[2]==digest(json.loads(facts.observation_raw)),
         'INSPECTION_CHANGED')
    for receipt in getattr(facts.host,'_source_upload_receipts',{}).values():receipt.collective_fence()
    entry.full_guard()


def _previous_time06_continuation_in(host,db,history_locators):
    """Read the validated same-family head under this actual RO Owned/H."""
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    from .draft_group_source_review import _replay
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1,'READONLY_OWNED_REQUIRED')
    require_history(host.entry.policy,db,history_locators)
    heads,values=_replay(db,host.entry.policy)
    family=host.chain.source['allowed_read_scope']['family_anchor_sha']
    selected=heads.get(family)
    if selected is None:return None
    prior=values[selected]
    need(prior['profile']==time06.SOURCE_REVIEW_PROFILE_V2
         and prior['family_id']==family
         and prior['original_source_material_sha']==prior['current_source_material_sha']
             ==host.pins.source_sha,'GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
    try:return time06.validate_observation_v2(prior['current_binding'])
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        raise WCEError('GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED') from None

def _observation_time06(host,image,qa_not_after,wall_start,mono_start,*,fixed_source_cap,previous=None):
    try:
        entry=_host(host);chain=host.chain;p=chain.runtime_policy;s=chain.source;m=chain.semantic
        p=time06.validate_runtime_policy_v2(p)
        need(fixed_source_cap<=p['source_lifetime_not_after_ms'],'GROUP_TIME06_SOURCE_CAP_CHANGED')
        bounds=time06.current_time_bounds_v2(p,fixed_source_cap_ms=fixed_source_cap,observed_at_ms=int(wall_start*1000),
            capture_monotonic=mono_start,entry_deadline=entry.deadline,
            qa_not_after_ms=int(qa_not_after*1000),previous_binding=previous)
        generation=digest(image)
        value={'schema':2,'profile':time06.OBSERVATION_PROFILE_V2,'authority':False,
            'content_source_type':codec.CONTENT_SOURCE_TYPE,'source_material_sha':chain.files['source'].sha,
            'runtime_source_policy_sha':sha256((canonical(p)+'\n').encode()).hexdigest(),
            'binding_sha':digest(p['binding']),'operator_request_identity_sha':s['operator_request_identity_sha'],
            'original_request_set_sha':s['original_request_set_sha'],'account_partition_sha':s['account_partition_sha'],
            'selection_sha':s['selection_ref']['sha256'],'qa_set_sha':s['qa_set_ref']['sha256'],
            'postupload_mapping_sha':s['postupload_mapping_ref']['sha256'],
            'prepared_relations_sha':s['prepared_relation_inventory_ref']['sha256'],
            'semantic_scope_sha':codec.semantic_scope_sha(m),'policy_fingerprint_sha':digest(entry.policy.value),
            'stable_owner':m['stable_owner'],'epoch':p['binding']['epoch'],'generation':p['binding']['generation'],
            'file_generation_sha':generation,'proof_generation_sha':digest(image['uploads']),
            'first_pass_sha':generation,'second_pass_sha':generation,
            'collective_fence_sha':digest({'first':generation,'second':generation,
                'source_sha':chain.files['source'].sha,'runtime_policy_sha':sha256((canonical(p)+'\n').encode()).hexdigest()}),
            'observed_at_ms':int(wall_start*1000),**bounds}
        value=time06.validate_observation_v2(value)
        if previous is not None:time06.validate_continuation_v2(previous,value)
        return value
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        raise WCEError('GROUP_OPERATOR_TIME06_OBSERVATION') from None

def _capture_current_source_time06(host):
    entry=_host(host)
    need(host not in _HOSTS and host._source is None and host.observer is None,'ALREADY_CAPTURED')
    resources=_qa_resources(host);wall_start=time.time();mono_start=time.monotonic()
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    from .draft_group_host_review import _INSPECTED_INPUTS,_inspection_image
    try:
        with cold_history_snapshot_fixed(entry.policy,entry) as (db,history):
            from .draft_group_first_control import (require_time06_capture_in,
                time06_capture_source_cap,time06_capture_guard,close_time06_capture_scope)
            scope=require_time06_capture_in(host,db,history_locators=history)
            try:
                fixed_source_cap=time06_capture_source_cap(scope)
                previous=_previous_time06_continuation_in(host,db,history)
                first,first_image=_read_pass(host,resources,db,history)
                second,second_image=_read_pass(host,resources,db,history)
                first_image['time06_source_lifetime_not_after_ms']=fixed_source_cap
                second_image['time06_source_lifetime_not_after_ms']=fixed_source_cap
                need(canonical(first_image)==canonical(second_image),'DOUBLE_PASS_CHANGED')
                need(canonical(previous)==canonical(_previous_time06_continuation_in(host,db,history)),
                     'GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
                time06_capture_guard(scope,host,db,history_locators=history)
            finally:
                import sys
                from .draft_group_pin_resources import close_all
                close_all([lambda:close_time06_capture_scope(scope)],sys.exc_info()[1])
        observed=_observation_time06(host,second_image,second_image['qa']['not_after_wall'],
            wall_start,mono_start,fixed_source_cap=fixed_source_cap,previous=previous)
        # First scope is never consumed after its H closes.
        with cold_history_snapshot_fixed(entry.policy,entry) as (fresh,history):
            final_scope=require_time06_capture_in(host,fresh,history_locators=history)
            try:
                need(time06_capture_source_cap(final_scope)==fixed_source_cap,'GROUP_TIME06_SOURCE_CAP_CHANGED')
                time06_capture_guard(final_scope,host,fresh,history_locators=history)
            finally:
                import sys
                from .draft_group_pin_resources import close_all
                close_all([lambda:close_time06_capture_scope(final_scope)],sys.exc_info()[1])
        binding=object.__new__(GroupCurrentOperatorSourceBinding)
        observer=object.__new__(GroupOperatorSourceObserver)
        facts=_Live(host,entry,binding,observer,resources,canonical(observed),canonical(second_image),
            second,_inspection_image(second),'INSPECTED_NO_ADMISSION',
            (os.getpid(),threading.get_ident()),canonical(entry.policy.value),
            entry.deadline,observed['qualified_not_after_ms'])
        _BINDINGS[binding]=facts;_HOSTS[host]=binding;_OBSERVERS[observer]=facts
        host.observer=entry.observer=observer
        entry.issued[id(binding)]=binding;entry.issued[id(observer)]=observer
        _INSPECTED_INPUTS[host.adapter]=(second,facts.inspection_raw,digest(observed))
        entry.stack.callback(_close_if_issued,host,binding)
        _fence(facts)
        return binding
    except BaseException as original:
        entry.poisoned=True
        from .draft_group_pin_resources import close_all
        value=_HOSTS.get(host)
        close_all([lambda:close_current_source_binding(host,value)] if value is not None
                  else [lambda:resources.close(original=original)],original)
        raise

def _validate_operator_observation_for_host(host,value):
    try:
        # Exact selected held-policy/observation pair, not a source_kind/caller flag.
        p=host.chain.runtime_policy
        if p['profile']==time06.POLICY_PROFILE_V2:
            time06.validate_runtime_policy_v2(p)
            return time06.validate_observation_v2(value)
        need(p['profile']==codec.POLICY_PROFILE,'GROUP_OPERATOR_TIME_MODEL_CHANGED')
        return codec.validate_observation(value)
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        raise WCEError('GROUP_OPERATOR_TIME06_OBSERVATION') from None

def capture_current_source(host):
    if host.chain.runtime_policy['profile']==time06.POLICY_PROFILE_V2:
        return _capture_current_source_time06(host)
    entry=_host(host)
    need(host not in _HOSTS and host._source is None and host.observer is None,'ALREADY_CAPTURED')
    resources=_qa_resources(host);wall_start=time.time();mono_start=time.monotonic()
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    from .draft_group_host_review import _INSPECTED_INPUTS,_inspection_image
    try:
        with cold_history_snapshot_fixed(entry.policy,entry) as (db,history):
            previous=_previous_continuation_in(host,db,history)
            first,first_image=_read_pass(host,resources,db,history)
            second,second_image=_read_pass(host,resources,db,history)
            need(canonical(first_image)==canonical(second_image),'DOUBLE_PASS_CHANGED')
            need(canonical(previous)==canonical(_previous_continuation_in(host,db,history)),
                 'GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
        observed=_observation(host,second_image,second_image['qa']['not_after_wall'],wall_start,mono_start,previous)
        binding=object.__new__(GroupCurrentOperatorSourceBinding)
        observer=object.__new__(GroupOperatorSourceObserver)
        facts=_Live(host,entry,binding,observer,resources,canonical(observed),canonical(second_image),
            second,_inspection_image(second),'INSPECTED_NO_ADMISSION',
            (os.getpid(),threading.get_ident()),canonical(entry.policy.value),
            entry.deadline,observed['qualified_not_after_ms'])
        _BINDINGS[binding]=facts;_HOSTS[host]=binding;_OBSERVERS[observer]=facts
        host.observer=entry.observer=observer
        entry.issued[id(binding)]=binding;entry.issued[id(observer)]=observer
        _INSPECTED_INPUTS[host.adapter]=(second,facts.inspection_raw,digest(observed))
        entry.stack.callback(_close_if_issued,host,binding)
        _fence(facts)
        return binding
    except BaseException as original:
        entry.poisoned=True
        from .draft_group_pin_resources import close_all
        value=_HOSTS.get(host)
        close_all([lambda:close_current_source_binding(host,value)] if value is not None
                  else [lambda:resources.close(original=original)],original)
        raise


def _record(host,binding):
    entry=_host(host)
    need(type(binding) is GroupCurrentOperatorSourceBinding,'BINDING_REQUIRED')
    facts=_BINDINGS.get(binding)
    need(facts is not None and facts.host is host and facts.entry is entry
         and _HOSTS.get(host) is binding and entry.issued.get(id(binding)) is binding
         and host.observer is facts.observer and entry.observer is facts.observer
         and _OBSERVERS.get(facts.observer) is facts,'BINDING_UNISSUED')
    _fence(facts)
    return facts


def binding_for_host(host,required_phase):
    value=_HOSTS.get(host)
    if required_phase is None:_record(host,value)
    else:validate_current_source_binding(host,value,required_phase=required_phase)
    return value


def validate_current_source_binding(host,binding,required_phase='ADMISSION_READY'):
    need(required_phase in PHASES,'PHASE_INVALID')
    facts=_record(host,binding);need(facts.phase==required_phase,'PHASE_REQUIRED')
    if facts.phase!='INSPECTED_NO_ADMISSION':_service_seals(facts)
    return binding


def current_binding_facts(binding):
    need(type(binding) is GroupCurrentOperatorSourceBinding,'BINDING_REQUIRED')
    facts=_BINDINGS.get(binding);need(facts is not None,'BINDING_UNISSUED')
    _record(facts.host,binding)
    return _validate_operator_observation_for_host(facts.host,json.loads(facts.observation_raw))


def current_binding_phase(host,binding):
    return _record(host,binding).phase


def _local_profile(host,*,tokenless):
    entry=_host(host)
    from .own_connection_broker import AccountService,Broker
    from .own_connection_workflow import PersistentWorkflow
    from .own_auth import OwnRegistry
    from .draft_group_runtime_host import GroupExecutionGate
    need(not entry.pre_storage and entry.listener_bound and type(entry.service) is AccountService
         and type(entry.service.workflow) is PersistentWorkflow and type(entry.broker) is Broker
         and GroupExecutionGate._fixed_live_chain(entry),'COMPLETE_SERVICE_REQUIRED')
    workflow=entry.service.workflow
    need(workflow.policy is entry.policy and type(workflow.registry) is OwnRegistry
         and len(workflow.registry.profiles)==1,'ACTUAL_OPERATOR_REGISTRY_REQUIRED')
    profile=next(iter(workflow.registry.profiles.values()))
    need(profile.binding()==host.chain.runtime_policy['binding'],'SERVICE_BINDING_CHANGED')
    if tokenless:
        need(workflow.active_lease is None and workflow.active_token is None
             and getattr(host,'_active_group_token',None) is None,'LOCAL_NO_TOKEN_REQUIRED')
    workflow._current(profile,workflow.active_lease,'local.read')
    entry.full_guard()
    return workflow,profile


def _service_seals(facts):
    workflow,_=_local_profile(facts.host,tokenless=False)
    need(facts.service is facts.entry.service and facts.registry is workflow.registry
         and _W1.get(facts.w1) is facts and _W2.get(facts.w2) is facts
         and facts.entry.issued.get(id(facts.w1)) is facts.w1
         and facts.entry.issued.get(id(facts.w2)) is facts.w2,'W1_W2_UNISSUED')
    from .group_host_jobs import _compiled
    row=_compiled(facts.entry.policy)
    need(dict(row[3])['configuration'][1]==facts.host.pins.configuration_sha
         and digest(row)==facts.case_row_sha,
         'FIXED_CASE_CATALOG_CHANGED')
    return facts


def _replace(facts,**updates):
    value=replace(facts,**updates)
    _BINDINGS[facts.binding]=value;_OBSERVERS[facts.observer]=value
    if value.w1 is not None:_W1[value.w1]=value
    if value.w2 is not None:_W2[value.w2]=value
    return value


def advance_current_source_binding(host,binding,phase,receipt=None):
    facts=_record(host,binding)
    need(phase in PHASES and PHASES.index(phase)==PHASES.index(facts.phase)+1,'PHASE_ORDER')
    if phase=='COMPLETE_SERVICE_NO_ADMISSION':
        workflow,_=_local_profile(host,tokenless=True)
        # Re-read all current accepted relationships, files, QA and original
        # uploads under the actual complete service before either witness.
        _refresh(host,facts,None,None)
        from .group_host_jobs import _compiled,_materialize
        row=_compiled(host.entry.policy)
        need(dict(row[3])['configuration'][1]==host.pins.configuration_sha
             and _materialize(host.entry.policy,row)==host.pins,'FIXED_CASE_PINS_CHANGED')
        w1=object.__new__(OperatorAcceptedRequest);w2=object.__new__(OperatorCaseScope)
        facts=_replace(facts,w1=w1,w2=w2,service=host.entry.service,
                       registry=workflow.registry,case_row_sha=digest(row))
        facts.entry.issued[id(w1)]=w1;facts.entry.issued[id(w2)]=w2
    else:
        _service_seals(facts)
        from .draft_group_operator_review import validate_phase_receipt
        validate_phase_receipt(host,binding,phase,receipt)
    _record(host,binding)
    _replace(facts,phase=phase)
    _record(host,binding)
    return binding


def _refresh_time06(host,facts,db,history):
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    from .draft_group_host_review import _INSPECTED_INPUTS
    from .draft_group_first_control import time06_current_action_guard
    actual_record=_record(host,facts.binding)
    need(actual_record is facts,'GROUP_TIME06_CURRENT_UNISSUED')
    time06_current_action_guard(host)
    try:
        observed=time06.validate_observation_v2(json.loads(facts.observation_raw))
        policy=time06.validate_runtime_policy_v2(host.chain.runtime_policy)
        sealed=json.loads(facts.pass_raw)
        cap=sealed['time06_source_lifetime_not_after_ms']
        time06._integer(cap)
        need(time06.digest(sealed)==observed['file_generation_sha']
             and observed['source_lifetime_not_after_ms']<=cap<=policy['source_lifetime_not_after_ms'],
             'GROUP_TIME06_SEALED_SOURCE_CAP_CHANGED')
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        raise WCEError('GROUP_OPERATOR_TIME06_OBSERVATION') from None
    def read(actual,locators):
        time06_current_action_guard(host)
        _,image=_read_pass(host,facts.resources,actual,locators)
        image['time06_source_lifetime_not_after_ms']=cap
        time06_current_action_guard(host)
        need(canonical(image)==facts.pass_raw,'CURRENT_INPUT_CHANGED')
    try:
        if db is not None:
            from .own_validation_scope import OwnedConnection,_transaction_marker
            from .draft_group_history_context import require_history
            need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'OWNED_REQUIRED')
            require_history(facts.entry.policy,db,history)
        if db is None or db.execute('PRAGMA query_only').fetchone()[0]!=1:
            with cold_history_snapshot_fixed(facts.entry.policy,facts.entry) as (actual,locators):read(actual,locators)
        else:read(db,history)
    except BaseException:
        facts.entry.poisoned=True
        raise
    finally:
        _INSPECTED_INPUTS[host.adapter]=(facts.inspection,facts.inspection_raw,
                                        digest(json.loads(facts.observation_raw)))
    _fence(facts)

def _refresh(host,facts,db,history):
    if host.chain.runtime_policy['profile']==time06.POLICY_PROFILE_V2:
        return _refresh_time06(host,facts,db,history)
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    from .draft_group_host_review import _INSPECTED_INPUTS
    def read(actual,locators):
        _,image=_read_pass(host,facts.resources,actual,locators)
        need(canonical(image)==facts.pass_raw,'CURRENT_INPUT_CHANGED')
    try:
        if db is not None:
            from .own_validation_scope import OwnedConnection,_transaction_marker
            from .draft_group_history_context import require_history
            need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'OWNED_REQUIRED')
            require_history(facts.entry.policy,db,history)
        if db is None or db.execute('PRAGMA query_only').fetchone()[0]!=1:
            with cold_history_snapshot_fixed(facts.entry.policy,facts.entry) as (actual,locators):read(actual,locators)
        else:read(db,history)
    except BaseException:
        facts.entry.poisoned=True
        raise
    finally:
        _INSPECTED_INPUTS[host.adapter]=(facts.inspection,facts.inspection_raw,
                                        digest(json.loads(facts.observation_raw)))
    _fence(facts)


def qualify_local_source(host,initial=False):
    entry=_host(host)
    binding=_HOSTS.get(host)
    if binding is None:binding=capture_current_source(host)
    facts=_record(host,binding)
    from .draft_group_runtime_host import BootstrapSourceInspection,QualifiedGroupSource
    if not entry.pre_storage and facts.phase=='INSPECTED_NO_ADMISSION':
        advance_current_source_binding(host,binding,'COMPLETE_SERVICE_NO_ADMISSION')
        facts=_record(host,binding)
    else:_refresh(host,facts,None,None)
    source_type=BootstrapSourceInspection if entry.pre_storage else QualifiedGroupSource
    value=source_type(host,entry,digest(json.loads(facts.observation_raw)),
        host.chain.source['semantic_scope_sha'],facts.not_after_ms/1000)
    entry.issued[id(value)]=value;host._source=value
    _fence(facts)
    return value


def current_no_token_in(host,db,source,*,token_use=None,initial=False,history_locators=None):
    entry=_host(host);binding=_HOSTS.get(host);facts=_record(host,binding)
    from .draft_group_runtime_host import BootstrapSourceInspection,QualifiedGroupSource,TokenUseScope
    need(source is host._source and type(source) in (BootstrapSourceInspection,QualifiedGroupSource)
         and source.host is host and source.entry is entry
         and entry.issued.get(id(source)) is source
         and source.facts_sha==digest(json.loads(facts.observation_raw)),'SOURCE_UNISSUED')
    if type(source) is BootstrapSourceInspection:
        need(initial and entry.pre_storage and facts.phase=='INSPECTED_NO_ADMISSION'
             and token_use is None,'BOOTSTRAP_LOCAL_ONLY')
    else:
        validate_current_source_binding(host,binding)
    if token_use is not None:
        need(type(token_use) is TokenUseScope and token_use.source is source
             and entry.issued.get(id(token_use)) is token_use,'TOKEN_USE_UNISSUED')
    _refresh(host,facts,db,history_locators)
    return facts.inspection


def local_registration_inspection_in(host,db=None,*,history_locators=None):
    binding=_HOSTS.get(host);facts=_record(host,binding)
    need(facts.phase in ('COMPLETE_SERVICE_NO_ADMISSION','ADMISSION_READY'),'LOCAL_PHASE_REQUIRED')
    _local_profile(host,tokenless=True);_service_seals(facts)
    if db is not None:
        from .own_validation_scope import OwnedConnection,_transaction_marker
        from .draft_group_history_context import require_history
        need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'OWNED_REQUIRED')
        require_history(host.entry.policy,db,history_locators)
    # Never cast the actual local writer into the RO prepared-history facade.
    # Its transaction/history remains independently required above.
    _refresh(host,facts,None,None)
    return facts.inspection


def validate_inspection(host,value,observed_sha):
    facts=_record(host,_HOSTS.get(host))
    need(value is facts.inspection and observed_sha==digest(json.loads(facts.observation_raw)),
         'INSPECTION_UNISSUED')
    return value


def verify_local_family_append_in(host,db,action,binding_sha,details,*,history_locators=None):
    """Only original locally issued FIRST and initial-purpose appends."""
    from .draft_group_read_family_store import (_scope,_first_candidate,_registration,
        read_first_files,FIRST,ACT)
    from .draft_group_host_publisher import HostProofFiles
    from .draft_group_input_files import _plain
    _plain(details);local_registration_inspection_in(host,db,history_locators=history_locators)
    binding=binding_for_host(host,'COMPLETE_SERVICE_NO_ADMISSION')
    validate_current_source_binding(host,binding,required_phase='COMPLETE_SERVICE_NO_ADMISSION')
    need(binding_sha==digest(host.chain.config['binding']),'LOCAL_BINDING_CHANGED')
    scope=_scope(db);files=scope[1]
    need(files.policy is host.entry.policy,'LOCAL_FAMILY_SCOPE_CHANGED')
    if action=='PREVIEW':
        candidate=details['candidate'];profile=candidate.get('profile')
        if profile==FIRST:
            pack=getattr(host,'_first_pack',None)
            need(pack is not None and canonical(_first_candidate(pack))==canonical(candidate)
                 and host.entry.first_candidates.get(digest(candidate))==canonical(candidate),
                 'FIRST_PACK_UNISSUED')
            need(read_first_files(files,pack.entry('request_witness').key)==pack,'FIRST_PACK_CHANGED')
        else:
            need(profile==ACT,'LOCAL_PROFILE_REQUIRED')
            issued=getattr(host.entry,'family_candidates',{}).get(digest(candidate))
            need(issued is not None and issued[0] is db and issued[1]==canonical(candidate),
                 'LOCAL_PURPOSE_UNISSUED')
            info=host._family_in(db,history_locators=history_locators)
            purposes=[p for p in info['covenant']['purposes']
                      if p['source_grant_sha']==candidate['source_grant_sha']]
            need(len(purposes)==1 and purposes[0]['purpose'] in ('QUALIFY','PREVIEW_ACCOUNT')
                 and purposes[0]['ordinal']==0 and candidate['route_decision_sha'] is None
                 and candidate['family_anchor_id']==info['covenant']['family_anchor_id'],
                 'INITIAL_PURPOSE_REQUIRED')
            proof=HostProofFiles(host.entry.policy,host.entry.loop_guard).read('read_delegation',candidate['evidence_sha'])
            need(proof.sha256 in host._registration['proof']['read_delegation_proof_shas']
                 and proof.value['purpose_key']==candidate['source_grant_sha']
                 and proof.value['registration_sha']==host._registration['registration_sha'],
                 'LOCAL_READ_PROOF_CHANGED')
    else:
        need(action=='PREVIEW_GRANT','LOCAL_ACTION_REQUIRED')
        info=host._family_in(db,history_locators=history_locators)
        purposes=[p for p in info['covenant']['purposes'] if p['source_grant_sha']==details['source_grant_sha']]
        need(len(purposes)==1 and purposes[0]['purpose'] in ('QUALIFY','PREVIEW_ACCOUNT')
             and purposes[0]['ordinal']==0 and purposes[0]['source_grant_sha'] in info['activations']
             and canonical(_registration(purposes[0],info['covenant']))==canonical(details),
             'PREVIEW_GRANT_UNISSUED')
    host.pure_release_fence()


def establish_current_source_review(host):
    entry=_host(host);binding=_HOSTS.get(host);facts=_record(host,binding)
    if facts.phase=='ADMISSION_READY':
        validate_current_source_binding(host,binding);return binding
    local_registration_inspection_in(host)
    from .draft_group_input_files import InputFiles
    from .draft_group_read_family_files import FamilyFiles
    from .draft_group_read_family_store import original_root_scope,family_scope
    from .own_validation_scope import content_scope
    from .own_history_locators import history_scope
    from .draft_group_history_context import physical_material_scope
    from .draft_group_operator_review import qualify_review_in,commit_review_in
    inputs=InputFiles(entry.policy,entry.loop_guard)
    need(type(host._registration) is dict,'REGISTRATION_REQUIRED')
    registration=inputs.read('registration',host._registration['registration_sha'])
    proof=inputs.read('proof',host._registration['registration_proof_sha'])
    head=inputs.read_head()
    need(head.value['schema']==2 and head.value['registration_sha']==registration.sha256
         and head.value['registration_proof_sha']==proof.sha256,'HEAD2_REQUIRED')
    origin=inputs.read('source',host.pins.source_sha)
    workflow=entry.service.workflow
    with workflow.db.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            files=FamilyFiles(entry.policy,entry.loop_guard)
            with physical_material_scope(db,entry.policy,entry),history_scope(entry.policy,db) as locators,content_scope(workflow.db,db):
                with original_root_scope(db,files,original_root_evidence(host),
                        source_kind='OPERATOR_ATTESTED',history_locators=locators) as closure:
                    with family_scope(db,files,closure):
                        review=qualify_review_in(host,db,registration,origin,history_locators=locators)
            commit_review_in(host,binding,db,review.sha256)
        except BaseException as original:
            from .draft_group_pin_resources import close_all
            close_all([lambda:close_current_source_binding(host,binding)]
                      +([db.rollback] if db.in_transaction else []),original)
            raise
    validate_current_source_binding(host,binding)
    return binding


def read_operator_review_materials_in(db,policy,candidate,*,states=None,events=None,host=None):
    # Historical path takes fixed catalog SHA, never current source qualification.
    from .draft_group_host_history import _context
    _context(db,policy)
    if states is not None or events is not None:
        from .draft_group_response_history import verify_group_replay_inputs_in
        verify_group_replay_inputs_in(db,states,events)
    if candidate is None:
        need(host is not None,'HISTORICAL_CONFIGURATION_REQUIRED')
        _host(host);configuration_sha=host.pins.configuration_sha
    else:
        need(type(candidate) is dict and 'configuration_sha' in candidate,'HISTORICAL_CONFIGURATION_REQUIRED')
        configuration_sha=candidate['configuration_sha'];codec._sha(configuration_sha)
    from .draft_group_history_context import require_history
    from .own_history_locators import borrow_entered_history
    history=borrow_entered_history(policy,db)
    require_history(policy,db,history)
    from .draft_group_operator_review_chain import read_operator_review_materials_in as actual
    return actual(db,policy,configuration_sha,history_locators=history)


def close_current_source_binding(host,binding):
    need(type(binding) is GroupCurrentOperatorSourceBinding,'BINDING_REQUIRED')
    facts=_BINDINGS.get(binding)
    need(facts is not None and facts.host is host,'BINDING_UNISSUED')
    _BINDINGS.pop(binding,None);_HOSTS.pop(host,None);_OBSERVERS.pop(facts.observer,None)
    if facts.w1 is not None:_W1.pop(facts.w1,None)
    if facts.w2 is not None:_W2.pop(facts.w2,None)
    for value in (binding,facts.observer,facts.w1,facts.w2):
        if value is not None:facts.entry.issued.pop(id(value),None)
    if host.observer is facts.observer:host.observer=None
    if facts.entry.observer is facts.observer:facts.entry.observer=None
    source=host._source
    if source is not None:
        facts.entry.issued.pop(id(source),None);host._source=None
    facts.resources.close()


def _close_if_issued(host,binding):
    if binding in _BINDINGS:close_current_source_binding(host,binding)
