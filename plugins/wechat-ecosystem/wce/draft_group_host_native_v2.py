"""Fixed Native2 Host local/capture/readiness seams. No caller phase or scope."""
from contextlib import ExitStack
from contextlib import contextmanager
import sys
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary,ref
import json,threading
from .contracts import WCEError
from .draft_group_contracts import canonical,digest

_SEALS=WeakKeyDictionary();_HOST_BINDINGS=WeakKeyDictionary();_MATERIALS=WeakKeyDictionary();_FILE_PINS=WeakKeyDictionary()


def hold(code):raise WCEError(code)

def need(value,code):
    if value is not True:hold(code)


def _host(host):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate,_REGISTRY
    need(type(host)is GroupRuntimeHost and type(host.entry)is GroupExecutionGate
         and _REGISTRY.get(host.entry.id)is host.entry and host.entry.thread==threading.get_ident(), 'GROUP_NATIVE_V2_ACTUAL_HOST_REQUIRED')
    GroupExecutionGate.held_pure(host.entry)
    return host.entry


def is_native_v2(host):
    return host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'


def _binding(host):
    _host(host);binding=_HOST_BINDINGS.get(host)
    need(binding is not None,'GROUP_NATIVE_V2_CURRENT_BINDING_REQUIRED')
    from .draft_group_native_v2_runtime import current_binding_phase
    return binding,current_binding_phase(host,binding)


def _inspection(host):
    from .draft_group_host_review import _INSPECTED_INPUTS,_inspection_image
    seal=_SEALS.get(host);need(seal is not None and seal[0]is host.observer,'GROUP_NATIVE_V2_INSPECTION_REQUIRED')
    observer,observation,inspection,raw=seal;pin=_INSPECTED_INPUTS.get(host.adapter)
    need(pin is not None and pin[0]is inspection and pin[1]==_inspection_image(inspection)
         and pin[2]==digest(observation.value) and observation.raw==raw,'GROUP_NATIVE_V2_INSPECTION_CHANGED')
    host.adapter.pure_fence();return inspection


def validate_native_v2_seal_inputs(host,observer,observation,inspection):
    entry=_host(host)
    from .draft_group_native_v2_stream import (GroupNativeV2SourceObserver,GroupSourceObservationV2,
        validate_native_v2_observer_capture)
    from .draft_group_host_review import _check_role_workspaces,_qualify_qa,_INSPECTED_INPUTS,_inspection_image
    need(type(observer)is GroupNativeV2SourceObserver and host.observer is observer and entry.observer is observer
         and type(observation)is GroupSourceObservationV2,'GROUP_NATIVE_V2_OBSERVER_REQUIRED')
    capture=validate_native_v2_observer_capture(observer)
    need(capture.located_in_entry and capture.raw==host.chain.files['source'].raw
         and capture.policy_raw==host.chain.runtime_policy_file.raw
         and getattr(capture.full,'__self__',None)is entry and getattr(capture.loop,'__self__',None)is entry,
         'GROUP_NATIVE_V2_ORIGINAL_CAPTURE_REQUIRED')
    host.chain.check();facts=observation.value
    need(facts['material_sha256']==host.pins.source_sha and facts['semantic_scope_sha']==host.chain.source['semantic_scope_sha'],
         'GROUP_NATIVE_V2_BASELINE_CHANGED')
    permission=facts['permission_facts'];users=permission['users']
    actual=[{k:v[k]for k in ('thread_id','turn_id','message_id','text_sha256')}for v in users if v['disposition']=='ORIGINAL_REQUEST']
    need(actual==host.chain.semantic['original_human_refs']
         and digest([v['text']for v in users if v['disposition']=='ORIGINAL_REQUEST'])==host.chain.semantic['original_text_set_sha'],
         'GROUP_HOST_HUMAN_SCOPE')
    _check_role_workspaces(host)
    # The original QA/pair/artifact validator consumes only these exact facts.
    # References below come from the actual retained WHOLE records, not hashes
    # or a caller inventory, and raw/typed/task payloads are re-read by it.
    records=GroupNativeV2SourceObserver.retained_records(observer)
    qa_facts={'assistant_facts':[{'raw':v['pair']['raw'],'typed':v['pair']['typed'],'material_category':'QA_FACT'}
                                for v in permission['selected_assistant_facts']],
              'inventory':[{'reference':r.reference()}for r in records]}
    pin=_INSPECTED_INPUTS.get(host.adapter)
    need(pin is not None and pin[0]is inspection and pin[1]==_inspection_image(inspection),'GROUP_SOURCE_INSPECTION_UNISSUED')
    _qualify_qa(host,qa_facts,inspection)
    _INSPECTED_INPUTS[host.adapter]=(inspection,pin[1],digest(facts))
    GroupNativeV2SourceObserver.pure_release_fence(observer);entry.held_pure()
    need(host not in _SEALS,'GROUP_NATIVE_V2_INSPECTION_ALREADY_SEALED')
    _SEALS[host]=(observer,observation,inspection,observation.raw)
    entry.stack.callback(_forget,host)
    return inspection


def _forget(host):
    _HOST_BINDINGS.pop(host,None);_SEALS.pop(host,None)


def capture_current_source(host):
    entry=_host(host)
    need(host not in _HOST_BINDINGS and host._source is None,'GROUP_NATIVE_V2_ALREADY_CAPTURED')
    from .draft_group_native_v2_stream import GroupNativeV2SourceObserver
    from .draft_group_native_v2_runtime import capture_current_source_in
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    from .draft_group_response_history import read_group_replay_snapshot_in,release_group_replay_snapshot_in
    with cold_history_snapshot_fixed(entry.policy,entry)as (db, history_locators):
        states,events=read_group_replay_snapshot_in(db)
        try:
            from .draft_group_source_review import collect_native_v2_prefix_proofs_in
            materials=read_native_v2_review_materials_in(db,entry.policy,None,states=states,events=events,host=host)
            with material_scope(materials):
                expectations=collect_native_v2_prefix_proofs_in(host,db,states,events,materials)
                checkpoints={};prefix_markers={}
                for item in expectations:
                    if item['baseline_ordered_sha256']is None:
                        marker={'source_id':item['source_id'],'end':item['baseline_end'],'prefix_sha256':item['baseline_prefix_sha256']}
                        key=(marker['source_id'],marker['end']);prior=prefix_markers.get(key)
                        need(prior is None or prior==marker,'GROUP_NATIVE_V2_PREFIX_EXPECTATION_CONFLICT')
                        prefix_markers[key]=marker
                        continue
                    checkpoint={'end':item['baseline_end'],'absolute_end_ordinal':item['absolute_end_ordinal'],
                        'prefix_sha256':item['baseline_prefix_sha256'],'ordered_records_sha256':item['baseline_ordered_sha256'],
                        'control_sha256':item['baseline_control_sha256']}
                    key=(item['source_id'],checkpoint['end'])
                    prior=checkpoints.get(key)
                    need(prior is None or prior['checkpoint']==checkpoint,'GROUP_NATIVE_V2_PREFIX_EXPECTATION_CONFLICT')
                    checkpoints[key]={'source_id':item['source_id'],'checkpoint':checkpoint}
                observer=GroupNativeV2SourceObserver(host.chain.files['source'].raw,host.chain.runtime_policy_file.raw,(),
                    entry.full_guard,entry.loop_guard,lookups=host.pins.lookups,checkpoints=tuple(checkpoints.values()),prefix_markers=tuple(prefix_markers.values()))
                materials.files.collective_fence()
                host.observer=entry.observer=observer;entry.stack.callback(observer.close)
                binding=capture_current_source_in(host,observer,host.chain.source,host.chain.runtime_policy,host.chain.review,(db,states,events))
        finally:release_group_replay_snapshot_in(db,states,events)
    _HOST_BINDINGS[host]=binding
    return binding


def _local_profile(host):
    entry=_host(host);need(not entry.pre_storage and entry.listener_bound,'GROUP_COMPLETE_LISTENER_REQUIRED')
    workflow=entry.service.workflow;profile=next(iter(workflow.registry.profiles.values()))
    need(workflow._lease(profile)is None and workflow.active_token is None,'GROUP_SOURCE_REGISTRATION_LOCAL_NO_TOKEN')
    workflow._current(profile,None,'local.write')
    return profile


def local_registration_inspection_in(host,db=None, *, history_locators=None):
    if not is_native_v2(host):return host.current_no_token_in(db,host._source, history_locators=history_locators)
    _local_profile(host);binding,phase=_binding(host)
    need(phase in ('COMPLETE_SERVICE_NO_ADMISSION','ADMISSION_READY'),'GROUP_NATIVE_V2_LOCAL_PHASE_REQUIRED')
    from .draft_group_native_v2_runtime import validate_current_source_binding
    validate_current_source_binding(host,binding,required_phase=phase)
    if db is not None:host.validate_history_in(db, history_locators=history_locators)
    current=_inspection(host);host.observer.prepare_release(host.chain.files['source'].raw)
    _local_profile(host);host.pure_release_fence()
    return current



def verify_local_family_append_in(host,db,action,binding_sha,details, *, history_locators=None):
    """Only the original local FIRST/purpose continuation, never an API claim."""
    from .draft_group_read_family_store import (_scope,_first_candidate,_registration,read_first_files,FIRST,ACT)
    from .draft_group_host_publisher import HostProofFiles
    from .draft_group_input_files import _plain
    _plain(details);local_registration_inspection_in(host,db, history_locators=history_locators)
    need(binding_sha==digest(host.chain.config['binding']),'GROUP_HOST_BINDING')
    scope=_scope(db);files=scope[1]
    need(files.policy is host.entry.policy,'GROUP_NATIVE_V2_LOCAL_FAMILY_SCOPE')
    if action=='PREVIEW':
        candidate=details['candidate'];profile=candidate.get('profile')
        if profile==FIRST:
            pack=getattr(host,'_first_pack',None)
            need(pack is not None and canonical(_first_candidate(pack))==canonical(candidate)
                 and host.entry.first_candidates.get(digest(candidate))==canonical(candidate),'GROUP_FIRST_PACK_UNISSUED')
            need(read_first_files(files,pack.entry('request_witness').key)==pack,'GROUP_FIRST_PACK_CHANGED')
        else:
            need(profile==ACT,'GROUP_NATIVE_V2_LOCAL_PROFILE')
            issued=getattr(host.entry,'family_candidates',{}).get(digest(candidate))
            need(issued is not None and issued[0]is db and issued[1]==canonical(candidate),'GROUP_NATIVE_V2_LOCAL_PURPOSE_UNISSUED')
            info=host._family_in(db, history_locators=history_locators);purpose=[p for p in info['covenant']['purposes']if p['source_grant_sha']==candidate['source_grant_sha']]
            need(len(purpose)==1 and purpose[0]['purpose']in ('QUALIFY','PREVIEW_ACCOUNT')and purpose[0]['ordinal']==0
                 and candidate['family_anchor_id']==info['covenant']['family_anchor_id']
                 and candidate['route_decision_sha']is None,'GROUP_NATIVE_V2_INITIAL_PURPOSE_REQUIRED')
            proof=HostProofFiles(host.entry.policy,host.entry.loop_guard).read('read_delegation',candidate['evidence_sha'])
            need(proof.sha256 in host._registration['proof']['read_delegation_proof_shas']
                 and proof.value['purpose_key']==candidate['source_grant_sha']
                 and proof.value['registration_sha']==host._registration['registration_sha'], 'GROUP_NATIVE_V2_LOCAL_READ_PROOF')
    else:
        need(action=='PREVIEW_GRANT','GROUP_NATIVE_V2_LOCAL_ACTION')
        info=host._family_in(db, history_locators=history_locators);purposes=[p for p in info['covenant']['purposes']if p['source_grant_sha']==details['source_grant_sha']]
        need(len(purposes)==1 and purposes[0]['purpose']in ('QUALIFY','PREVIEW_ACCOUNT')and purposes[0]['ordinal']==0
             and purposes[0]['source_grant_sha']in info['activations']
             and canonical(_registration(purposes[0],info['covenant']))==canonical(details),'GROUP_PREVIEW_GRANT_UNISSUED')
    host.pure_release_fence()
    return None

def establish_current_source_review(host):
    if not is_native_v2(host):
        host.current_no_token_in(None,host._source, history_locators=None);return host._source
    _host(host);binding,phase=_binding(host)
    from .draft_group_native_v2_runtime import validate_current_source_binding
    if phase=='ADMISSION_READY':
        validate_current_source_binding(host,binding);_inspection(host);host.pure_release_fence();return binding
    need(phase=='COMPLETE_SERVICE_NO_ADMISSION','GROUP_NATIVE_V2_REVIEW_PHASE_REQUIRED')
    _local_profile(host)
    from .draft_group_input_files import InputFiles
    from .draft_group_read_family_files import FamilyFiles
    from .draft_group_read_family_store import original_root_scope,family_scope
    from .own_validation_scope import content_scope
    from .draft_group_source_review import qualify_source_review_fixed,commit_source_review_v2_in
    workflow=host.entry.service.workflow;policy=host.entry.policy
    need(type(host._registration)is dict,'GROUP_NATIVE_V2_REGISTRATION_REQUIRED')
    inputs=InputFiles(policy,host.entry.loop_guard)
    registration=inputs.read('registration',host._registration['registration_sha'])
    proof=inputs.read('proof',host._registration['registration_proof_sha'])
    head=inputs.read_head()
    need(head.value['schema']==2 and head.value['registration_sha']==registration.sha256
         and head.value['registration_proof_sha']==proof.sha256,'GROUP_NATIVE_V2_HEAD2_REQUIRED')
    origin=inputs.read('source',host.chain.runtime_policy['origin_source_descriptor']['sha256'])
    # Dedicated writer: original content/Family scopes exit before the sole B
    # commit. OwnStore.transaction must not wrap this normal-commit boundary.
    with workflow.db.connect()as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            files=FamilyFiles(policy,host.entry.loop_guard)
            from .own_history_locators import history_scope
            from .draft_group_history_context import physical_material_scope
            with physical_material_scope(db,policy,host.entry), history_scope(policy,db) as history_locators, content_scope(workflow.db,db):
                with original_root_scope(db,files,host.chain.semantic['original_root_evidence'],source_kind=host.chain.config['binding']['source_kind'], history_locators=history_locators)as closure:
                    with family_scope(db,files,closure):review=qualify_source_review_fixed(host,db,registration,origin, history_locators=history_locators)
            commit_source_review_v2_in(host,binding,db,review.sha256)
        except BaseException:
            if db.in_transaction:db.rollback()
            raise
    validate_current_source_binding(host,binding);_inspection(host);host.pure_release_fence()
    host._current_source_review_sha=review.sha256
    return binding


def validate_inspection(host,value,observed_sha):
    seal=_SEALS.get(host)
    need(seal is not None and seal[0]is host.observer and seal[2]is value
         and digest(seal[1].value)==observed_sha,'GROUP_NATIVE_V2_INSPECTION_UNISSUED')
    from .draft_group_native_v2_stream import validate_native_v2_observer_capture
    validate_native_v2_observer_capture(host.observer)
    return value


def static_role_descriptors(chain):
    result=[];material=chain.source
    for role in material['role_threads']:
        identities=[v for v in material['source_identities']if v['thread_id']==role['thread_id']]
        lookups=[v for v in chain.pins.lookups if role['thread_id']in v.allowed_threads]
        need(len(identities)==len(lookups)==1,'GROUP_NATIVE_V2_ROLE_DESCRIPTOR')
        lookup=lookups[0]
        result.append({**role,'owner_thread':lookup.owner_thread,
            'lookup_state_path_sha256':sha256(str(lookup.state_path).encode()).hexdigest(),
            'lookup_root_path_sha256':sha256(str(lookup.session_root).encode()).hexdigest(),
            'source_identity':identities[0]})
    return result


def load_static_chain(chain):
    from .group_host_jobs import runtime_policy_pin_for
    from .draft_group_runtime_host import PinnedFile
    from .draft_group_native_v2_codec import decode_runtime_policy
    path,checksum,extension=runtime_policy_pin_for(chain.pins,chain.entry.policy)
    file=PinnedFile(Path(path),checksum,2*1024*1024,pool=chain.entry.pin_pool,owner=chain.entry)
    chain.entry.pins.append(file);chain.runtime_policy_file=file
    chain.runtime_policy=decode_runtime_policy(file.raw);chain.runtime_extension=extension
    check_static_chain(chain)


def check_static_chain(chain):
    from .draft_group_native_v2_codec import (MODE,validate_baseline,validate_runtime_policy,validate_policy_acceptance,
                                            CATALOG_EXTENSION_KEYS)
    from .draft_group_input_files import _closed
    from .group_host_jobs import runtime_policy_pin_for
    p=chain.pins;c=chain.config;s=chain.semantic;m=validate_baseline(chain.source)
    policy=validate_runtime_policy(chain.runtime_policy);acceptance=validate_policy_acceptance(chain.review)
    path,checksum,extension=runtime_policy_pin_for(p,chain.entry.policy)
    _closed(extension,CATALOG_EXTENSION_KEYS)
    need(extension['schema']==1 and type(extension['schema'])is int
         and extension['profile']=='GROUP_CATALOG_RUNTIME_SOURCE_V1'and extension['mode']==MODE
         and extension['native_qualification']=='NOT_ASSERTED'and extension['baseline_source_sha']==p.source_sha
         and extension['runtime_policy_path']==str(path)and extension['runtime_policy_sha']==checksum,
         'GROUP_NATIVE_V2_CATALOG_MODE')
    need(chain.runtime_policy_file.path==Path(path)and chain.runtime_policy_file.sha==checksum
         and chain.runtime_policy_file.raw==(canonical(policy)+'\n').encode(),'GROUP_NATIVE_V2_POLICY_CHANGED')
    chain.runtime_policy_file.check()
    need(policy['core_scope_sha']==c['candidate_scope']==chain.entry.policy.value['candidate_scope']
         and policy['binding_sha']==digest(c['binding'])and policy['baseline_source_sha']==p.source_sha
         and policy['semantic_scope_sha']==m['semantic_scope_sha']
         and policy['native_contract_sha']==extension['native_contract_sha']==m['stream_contract']['interpreter_contract_sha256']
         and policy['role_descriptors_sha']==digest(c['role_source_descriptors'])
         and policy['qa_selection_sha']==digest(m['selected_assistant_pairs'])
         and policy['original_input_not_after_ms']==int(m['expires_policy']['not_after']*1000)
         and canonical(policy['original_source_rights_expiry'])==canonical(s['source_rights_expiry']),
         'GROUP_NATIVE_V2_STATIC_POLICY_BINDING')
    need(acceptance['runtime_source_policy_sha']==checksum and acceptance['source_binding_mode']==MODE
         and acceptance['native_contract_sha']==policy['native_contract_sha']
         and acceptance['baseline_native_qualification']=='NOT_ASSERTED','GROUP_NATIVE_V2_STATIC_ACCEPTANCE')
    return None


def _warm_local(host):
    entry=_host(host)
    from .draft_group_runtime_host import AccountService,Broker
    from .own_connection_token import CachedToken
    from .own_auth import OwnTokenScope
    need(not entry.pre_storage and type(entry.service)is AccountService and type(entry.broker)is Broker
         and entry.broker.service is entry.service and entry.broker.policy is entry.policy
         and entry.listener_bound and entry._fixed_live_chain(),'GROUP_NATIVE_V2_WARM_SERVICE_REQUIRED')
    workflow=entry.service.workflow;old=next(iter(workflow.registry.profiles.values()))
    cache=entry.service.tokens.cached;active=workflow.active_token;lease=workflow.active_lease
    if active is not None:
        need(type(active)is CachedToken and active is cache and lease is not None
             and lease.token is active.token and lease.scope==OwnTokenScope.from_profile(old),'GROUP_LOCAL_PHASE_TOKEN_CHANGED')
    else:need(lease is None,'GROUP_LOCAL_PHASE_LEASE_CHANGED')
    # Original ordinary profile/activate leaves establish this call's local
    # identity. No token is acquired or cleared and no business lease is made.
    fresh=AccountService.profile(entry.service)
    workflow.activate(fresh)
    need(entry.service.tokens.cached is cache and workflow.active_lease is None
         and workflow.active_token is None and workflow.execution_deadline is None,'GROUP_NATIVE_V2_WARM_LOCAL_CHANGED')
    entry.full_guard()


def qualify_local_source(host,*,initial=False):
    entry=_host(host)
    from .draft_group_native_v2_runtime import (current_binding_phase,current_binding_facts,
        advance_current_source_binding,validate_current_source_binding)
    from .draft_group_runtime_host import BootstrapSourceInspection,QualifiedGroupSource
    from .draft_group_host_review import semantic_scope_sha
    binding=_HOST_BINDINGS.get(host)
    if binding is None:binding=capture_current_source(host)
    phase=current_binding_phase(host,binding);facts=current_binding_facts(binding)
    if phase=='NATIVE_QA_CHECKED':
        if not entry.pre_storage:_warm_local(host)
        source=BootstrapSourceInspection(host,entry,facts['source_observation_sha'],semantic_scope_sha(host.chain.semantic),facts['qualified_not_after_ms']/1000)
        entry.issued[id(source)]=source;host._source=source
        advance_current_source_binding(host,binding,'BOOTSTRAP_LOCAL_ONLY')
        phase='BOOTSTRAP_LOCAL_ONLY'
    if entry.pre_storage:
        need(initial and phase=='BOOTSTRAP_LOCAL_ONLY'and type(host._source)is BootstrapSourceInspection,'GROUP_NATIVE_V2_BOOTSTRAP_PHASE')
        validate_current_source_binding(host,binding,required_phase=phase);return host._source
    if phase=='BOOTSTRAP_LOCAL_ONLY':
        need(entry.listener_bound,'GROUP_COMPLETE_LISTENER_REQUIRED')
        source=QualifiedGroupSource(host,entry,facts['source_observation_sha'],semantic_scope_sha(host.chain.semantic),facts['qualified_not_after_ms']/1000)
        entry.issued[id(source)]=source;host._source=source
        advance_current_source_binding(host,binding,'COMPLETE_SERVICE_NO_ADMISSION')
        phase='COMPLETE_SERVICE_NO_ADMISSION'
    need(phase in ('COMPLETE_SERVICE_NO_ADMISSION','ADMISSION_READY')and type(host._source)is QualifiedGroupSource,'GROUP_NATIVE_V2_SOURCE_PHASE')
    validate_current_source_binding(host,binding,required_phase=phase)
    _inspection(host);host.pure_release_fence();return host._source


def current_no_token_in(host,db,source,*,token_use=None,initial=False, history_locators=None):
    entry=_host(host);binding,phase=_binding(host)
    from .draft_group_native_v2_runtime import validate_current_source_binding,current_binding_facts,current_binding_observation
    from .draft_group_runtime_host import BootstrapSourceInspection,QualifiedGroupSource,TokenUseScope
    if initial:
        need(entry.pre_storage and token_use is None and phase=='BOOTSTRAP_LOCAL_ONLY'
             and type(source)is BootstrapSourceInspection,'GROUP_NATIVE_V2_BOOTSTRAP_LOCAL_REQUIRED')
        validate_current_source_binding(host,binding,required_phase='BOOTSTRAP_LOCAL_ONLY')
    else:
        validate_current_source_binding(host,binding)
        need(type(source)is QualifiedGroupSource,'GROUP_HOST_SOURCE_UNISSUED')
    facts=current_binding_facts(binding)
    need(source is host._source and entry.issued.get(id(source))is source and source.host is host
         and source.entry is entry and source.facts_sha==facts['source_observation_sha']
         and source.not_after==facts['qualified_not_after_ms']/1000,'GROUP_HOST_SOURCE_CHANGED')
    host.chain.check();current=_inspection(host)
    observed=host.observer.inspect(host.chain.files['source'].raw)
    need(digest(observed.value)==facts['source_observation_sha']
         and canonical(observed.value)==canonical(current_binding_observation(host,binding)), 'GROUP_NATIVE_V2_OBSERVATION_CHANGED')
    if db is not None:
        host.validate_history_in(db, history_locators=history_locators)
        if token_use is not None or getattr(host,'_active_group_token',None)is not None:host.validate_original_uploads_in(db,current, history_locators=history_locators)
    if token_use is not None:
        need(type(token_use)is TokenUseScope and token_use.source is source and entry.issued.get(id(token_use))is token_use,'GROUP_TOKEN_USE_UNISSUED')
    host.observer.prepare_release(host.chain.files['source'].raw);entry.full_guard()
    return current


@dataclass(frozen=True,eq=False,init=False)
class NativeV2ReviewHistoryMaterials:
    baseline_raw:bytes=field(repr=False)
    policy_raw:bytes=field(repr=False)
    acceptance_raw:bytes=field(repr=False)
    origin_raw:bytes=field(repr=False)
    configuration_sha:str
    semantic_adoption_sha:str
    source_sha:str
    acceptance_sha:str
    files:object=field(repr=False)
    authority:bool=False
    def __init__(self,*args,**kwargs):hold('GROUP_NATIVE_V2_MATERIAL_ISSUER_REQUIRED')


class _MaterialFiles:
    def __init__(self,*args,**kwargs):hold('GROUP_NATIVE_V2_MATERIAL_ISSUER_REQUIRED')
    def collective_fence(self):
        record=_FILE_PINS.get(self);need(record is not None,'GROUP_NATIVE_V2_MATERIAL_FILES_CLOSED')
        lease=record[6]
        if lease is not None:lease.check()
        pins,owner_ref=record[:2];owner=owner_ref();original=_MATERIALS.get(owner)if owner is not None else None
        need(original is not None and original[8]is self,'GROUP_NATIVE_V2_MATERIAL_CHANGED')
        for key,item in zip(NativeV2ReviewHistoryMaterials.__annotations__,original,strict=True):
            actual=object.__getattribute__(owner,key)
            need(type(actual)is type(item) and (actual is item if key=='files'else actual==item),'GROUP_NATIVE_V2_MATERIAL_CHANGED')
        for pin in pins:pin.check()
    def close(self,*,original=None):
        record=_FILE_PINS.pop(self,None)
        if record is not None:
            from .draft_group_pin_resources import close_all
            callbacks=[pin.close for pin in record[0]]
            pool,owner,artifacts,owns_resources=record[2:6]
            if owns_resources:
                callbacks.extend((lambda:artifacts.close(original=original),lambda:pool.close(owner=owner,original=original)))
            close_all(callbacks,original)
    def __del__(self):self.close()


@contextmanager
def material_scope(materials):
    try:yield materials
    finally:materials.files.close(original=sys.exc_info()[1])


def read_native_v2_review_materials_in(db,policy,candidate,*,states=None,events=None,host=None):
    from .draft_group_host_history import _context
    from .draft_group_response_history import (verify_group_replay_inputs_in,read_group_replay_snapshot_in,
                                              release_group_replay_snapshot_in)
    _context(db,policy)
    if states is None and events is None:
        states,events=read_group_replay_snapshot_in(db)
        try:return read_native_v2_review_materials_in(db,policy,candidate,states=states,events=events,host=host)
        finally:release_group_replay_snapshot_in(db,states,events)
    need(states is not None and events is not None,'GROUP_NATIVE_V2_REPLAY_PAIR_REQUIRED')
    verify_group_replay_inputs_in(db,states,events)
    if candidate is None:
        _host(host);need(host.entry.policy is policy and is_native_v2(host),'GROUP_NATIVE_V2_STATIC_HOST_REQUIRED')
        pins=host.pins;configuration_sha=pins.configuration_sha
    else:
        from .draft_group_native_v2_codec import validate_source_review
        checked=validate_source_review(candidate);configuration_sha=checked['current_binding']['configuration_sha']
        from .group_host_jobs import native_v2_pins_for_history
        pins=native_v2_pins_for_history(policy,configuration_sha)
    from .group_host_jobs import runtime_policy_pin_for
    path,checksum,extension=runtime_policy_pin_for(pins,policy)
    from .draft_group_runtime_host import PinnedFile
    from .draft_group_pin_resources import PinPool,close_all
    from .draft_group_artifact_resources import ArtifactResources
    from .draft_group_history_context import current_physical_material_resources
    lease=current_physical_material_resources(db,policy)
    if host is not None:
        entry=_host(host);need(entry.policy is policy,'GROUP_NATIVE_V2_STATIC_HOST_REQUIRED')
        if lease is not None:need(lease.check()[1] is entry,'GROUP_HISTORY_PHYSICAL_CHANGED')
        pool,resource_owner,artifacts,owns_resources=entry.pin_pool,entry,entry.artifact_resources,False
    elif lease is not None:
        pool,resource_owner,artifacts=lease.check();owns_resources=False
    else:
        resource_owner=object();pool=PinPool(resource_owner)
        artifacts=ArtifactResources(pool,owner=resource_owner);owns_resources=True
    held=[];raw={}
    try:
        for name in ('configuration','semantic','source','review','arm_receipt','unarmed','armed'):
            pin=PinnedFile(getattr(pins,name+'_path'),getattr(pins,name+'_sha'),2*1024*1024,pool=pool,owner=resource_owner);held.append(pin);raw[name]=pin.raw
        policy_file=PinnedFile(Path(path),checksum,2*1024*1024,pool=pool,owner=resource_owner);held.append(policy_file)
        for file,sha in pins.helper_files+pins.retention_evidence:
            pin=PinnedFile(file,sha,2*1024*1024,pool=pool,owner=resource_owner);held.append(pin)
        from .draft_group_native_v2_codec import decode_baseline,decode_runtime_policy,decode_policy_acceptance
        baseline=decode_baseline(raw['source']);runtime=decode_runtime_policy(policy_file.raw);acceptance=decode_policy_acceptance(raw['review'])
        from .draft_group_host_review import _json,CONFIG_KEYS,SEMANTIC_KEYS,semantic_scope_sha,_arm_ast
        config=_json(raw['configuration'],CONFIG_KEYS,'GROUP_HOST_CONFIGURATION_V1')
        semantic=_json(raw['semantic'],SEMANTIC_KEYS,'HOST_GROUP_SEMANTIC_ADOPTION_V1')
        need(config['semantic_adoption_sha']==pins.semantic_sha and config['source_material_sha']==pins.source_sha
             and acceptance['configuration_sha']==configuration_sha and acceptance['semantic_adoption_sha']==pins.semantic_sha
             and acceptance['source_material_sha']==pins.source_sha and acceptance['artifact_inventory_sha']==digest(semantic['artifact_inventory'])
             and acceptance['runtime_source_policy_sha']==checksum and runtime['baseline_source_sha']==pins.source_sha
             and baseline['semantic_scope_sha']==semantic_scope_sha(semantic),'GROUP_NATIVE_V2_HISTORY_BINDING')
        expected={'first_covenant_sha':config['first_covenant_sha'],'read_contract_sha':config['read_contract_sha'],
            'candidate_scope':config['candidate_scope'],'unarmed_sha':pins.unarmed_sha,
            'helper_dependencies':[[str(p),h]for p,h in pins.helper_files],
            'retention_evidence':[[str(p),h]for p,h in pins.retention_evidence],
            'permitted_arm':{'REVIEW_PATH':str(pins.review_path),'REVIEW_SHA':'FIXED_REVIEW_BYTES_SHA256'}}
        need(all(acceptance[key]==value for key,value in expected.items()),'GROUP_NATIVE_V2_HISTORY_ACCEPTANCE')
        need(runtime['core_scope_sha']==config['candidate_scope']and runtime['binding_sha']==digest(config['binding'])
             and runtime['semantic_scope_sha']==baseline['semantic_scope_sha']
             and runtime['native_contract_sha']==extension['native_contract_sha']==baseline['stream_contract']['interpreter_contract_sha256']
             and runtime['role_descriptors_sha']==digest(config['role_source_descriptors'])
             and runtime['qa_selection_sha']==digest(baseline['selected_assistant_pairs'])
             and runtime['original_input_not_after_ms']==int(baseline['expires_policy']['not_after']*1000)
             and canonical(runtime['original_source_rights_expiry'])==canonical(semantic['source_rights_expiry']), 'GROUP_NATIVE_V2_HISTORY_POLICY')
        need(config['original_root_evidence_sha']==digest(semantic['original_root_evidence'])
             and baseline['original_user_scope']['human_refs']==semantic['original_human_refs'], 'GROUP_NATIVE_V2_HISTORY_SEMANTIC')
        inventory=semantic['artifact_inventory'];bysha={item['sha256']:item for item in inventory}
        for adoption in semantic['qa_adoptions']:
            selected=[item for item in baseline['selected_assistant_pairs']if item['raw']==adoption['raw_record_ref']and item['typed']==adoption['typed_record_ref']]
            need(len(selected)==1 and selected[0]['terminal']==adoption['task_complete_ref']
                 and adoption['reviewed_artifact_set_sha']==digest(inventory)
                 and adoption['qa_report_artifact']in inventory and adoption['production_rule_sha']in bysha,
                 'GROUP_NATIVE_V2_HISTORY_QA')
        before,left=_arm_ast(raw['unarmed']);after,right=_arm_ast(raw['armed']);arm=json.loads(raw['arm_receipt'])
        need(before==after and arm['unarmed_sha']==pins.unarmed_sha and arm['review_sha']==pins.review_sha and arm['armed_sha']==pins.armed_sha
             and arm['ast_diff']==['REVIEW_PATH','REVIEW_SHA'] and acceptance['unarmed_sha']==pins.unarmed_sha,
             'GROUP_NATIVE_V2_HISTORY_ARM')
        if runtime['origin_source_descriptor']['sha256']==pins.source_sha:origin_raw=raw['source']
        else:
            from .draft_group_input_files import InputFiles
            from .draft_group_read_family_store import _history_file_guard
            inputs=InputFiles(policy,lambda:_history_file_guard(policy))
            key=runtime['origin_source_descriptor']['sha256']
            origin_raw=inputs.read('source',key).raw
            folder,name=inputs._name('source',key)
            origin_pin=PinnedFile(inputs._base_path(folder)/folder/name,key,2*1024*1024,pool=pool,owner=resource_owner)
            held.append(origin_pin);need(origin_pin.raw==origin_raw,'GROUP_NATIVE_V2_ORIGIN_CHANGED')
        need(len(origin_raw)==runtime['origin_source_descriptor']['size']
             and sha256(origin_raw).hexdigest()==runtime['origin_source_descriptor']['sha256'],'GROUP_NATIVE_V2_ORIGIN_BYTES')
        # Original FIRST/covenant evidence is checked from the actual C5 replay;
        # historical material validation never invokes current or _load.
        from .draft_group_read_family_store import check_family_records_in
        check_family_records_in(db,states,policy)
        selection=artifacts.selection(semantic['artifact_inventory'],pins.artifact_roots)
        for artifact_index,spec in enumerate(semantic['artifact_inventory']):
            roots=[root for key,root in pins.artifact_roots if key==spec['root_sha']]
            need(len(roots)==1,'GROUP_NATIVE_V2_ARTIFACT_ROOT')
            pin=artifacts.acquire(selection,artifact_index,4*1024*1024 if spec['media_type']=='text/html'else 2*1024*1024)
            held.append(pin);need(len(pin.raw)==spec['size'],'GROUP_NATIVE_V2_ARTIFACT_BYTES')
        verify_group_replay_inputs_in(db,states,events)
        files=object.__new__(_MaterialFiles)
        value=object.__new__(NativeV2ReviewHistoryMaterials)
        data=(raw['source'],policy_file.raw,raw['review'],origin_raw,configuration_sha,pins.semantic_sha,pins.source_sha,pins.review_sha,files,False)
        for key,item in zip(NativeV2ReviewHistoryMaterials.__annotations__,data,strict=True):object.__setattr__(value,key,item)
        _MATERIALS[value]=data;_FILE_PINS[files]=(tuple(held),ref(value),pool,resource_owner,artifacts,owns_resources,lease)
        files.collective_fence();held=[]
        return value
    except BaseException as original:
        callbacks=[pin.close for pin in held]
        if owns_resources:
            callbacks.extend((lambda:artifacts.close(original=original),lambda:pool.close(owner=resource_owner,original=original)))
        close_all(callbacks,original)
        raise
