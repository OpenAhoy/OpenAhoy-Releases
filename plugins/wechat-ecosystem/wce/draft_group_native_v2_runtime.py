"""Actual-entry opaque Native current binding. Historical values cannot mint it."""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import threading
import time
from types import FunctionType
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .draft_group_contracts import canonical, digest
from .draft_group_native_v2_codec import (MODE, validate_baseline, validate_runtime_policy,
    validate_policy_acceptance, validate_current_binding, validate_observation)
from .draft_group_native_v2_stream import (GroupNativeV2SourceObserver,
    validate_native_v2_observer_capture)

PHASES = ('NATIVE_QA_CHECKED','BOOTSTRAP_LOCAL_ONLY','COMPLETE_SERVICE_NO_ADMISSION',
          'REVIEW_PENDING','REVIEW_COMMITTED','ADMISSION_READY','CLOSED')
_BINDINGS = WeakKeyDictionary()


def hold(code):
    raise WCEError('GROUP_NATIVE_V2_' + code)


def need(condition, code):
    if not condition:
        hold(code)


class GroupCurrentSourceBinding:
    __slots__ = ('__weakref__',)

    def __new__(cls, *args, **kwargs):
        hold('PRIVATE_BINDING_ISSUER_REQUIRED')

    @property
    def authority(self):
        return False


@dataclass(frozen=True)
class _LiveBinding:
    host: object
    entry: object
    observer: object
    capture: object
    phase: str
    witness_raw: str
    observation_raw: bytes
    inspection: object
    thread: int
    review_sha: str | None = None
    review_receipt: object = None


def _actual_host(host):
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate, _REGISTRY
    need(type(host) is GroupRuntimeHost and type(host.entry) is GroupExecutionGate, 'ACTUAL_HOST_REQUIRED')
    entry = host.entry
    need(_REGISTRY.get(entry.id) is entry and entry.thread == threading.get_ident(), 'ACTUAL_ENTRY_REQUIRED')
    GroupExecutionGate.held_pure(entry)
    return entry


def _fixed_leaf(name):
    from . import draft_group_host_review
    leaf = getattr(draft_group_host_review, name, None)
    need(type(leaf) is FunctionType and leaf.__module__ == draft_group_host_review.__name__,
         'FIXED_HOST_READER_REQUIRED')
    return leaf


def _record(host, binding):
    entry = _actual_host(host)
    need(type(binding) is GroupCurrentSourceBinding, 'BINDING_REQUIRED')
    facts = _BINDINGS.get(binding)
    need(facts is not None and facts.host is host and facts.entry is entry
         and entry.issued.get(id(binding)) is binding and facts.thread == threading.get_ident()
         and facts.phase != 'CLOSED', 'BINDING_UNISSUED')
    need(host.observer is facts.observer and host.entry.observer is facts.observer, 'OBSERVER_CHANGED')
    capture = validate_native_v2_observer_capture(facts.observer)
    need(capture is facts.capture, 'CAPTURE_CHANGED')
    if facts.phase!='NATIVE_QA_CHECKED':
        from .draft_group_host_review import GroupInputAdapter
        need(type(host.adapter) is GroupInputAdapter,'ACTUAL_ADAPTER_REQUIRED')
        GroupInputAdapter.validate_qualified_inspection(host.adapter,facts.inspection)
    witness = json.loads(facts.witness_raw)
    validate_current_binding(witness)
    need(witness['entry_epoch_sha'] == digest({'profile':'GROUP_ENTRY_EPOCH_V1','entry_id':entry.id}), 'ENTRY_EPOCH')
    need(time.time()*1000 < witness['qualified_not_after_ms'], 'SOURCE_EXPIRED')
    return facts


def capture_current_source_in(host, observer, baseline, policy, acceptance, history):
    """No current/no-token precondition: real static+Native+QA bootstrap leaf."""
    entry = _actual_host(host)
    need(type(observer) is GroupNativeV2SourceObserver and host.observer is observer
         and entry.observer is observer, 'OBSERVER_REQUIRED')
    validate_baseline(baseline); validate_runtime_policy(policy); validate_policy_acceptance(acceptance)
    capture = validate_native_v2_observer_capture(observer)
    need(capture.located_in_entry, 'ENTRY_NATIVE_LOOKUP_REQUIRED')
    # Resource-only observers using True guards cannot become current bindings.
    from .draft_group_runtime_host import GroupExecutionGate
    need(getattr(capture.full,'__self__',None) is entry
         and getattr(capture.full,'__func__',None) is GroupExecutionGate.full_guard
         and getattr(capture.loop,'__self__',None) is entry
         and getattr(capture.loop,'__func__',None) is GroupExecutionGate.loop_guard, 'ACTUAL_GUARDS_REQUIRED')
    need(type(history) is tuple and len(history) == 3, 'ACTUAL_REPLAY_HISTORY_REQUIRED')
    db,states,events = history
    from .draft_group_response_history import verify_group_replay_inputs_in
    verify_group_replay_inputs_in(db,states,events)
    need(capture.raw == host.chain.files['source'].raw
         and sha256(capture.raw).hexdigest() == host.pins.source_sha
         and capture.policy_raw == (canonical(policy)+'\n').encode()
         and capture.raw == (canonical(baseline)+'\n').encode(), 'STATIC_INPUT_CHANGED')
    need(sha256(capture.policy_raw).hexdigest() == acceptance['runtime_source_policy_sha']
         and acceptance['source_material_sha'] == policy['baseline_source_sha'] == host.pins.source_sha
         and acceptance['configuration_sha'] == host.pins.configuration_sha
         and acceptance['semantic_adoption_sha'] == host.pins.semantic_sha
         and acceptance['native_contract_sha'] == policy['native_contract_sha']
         == baseline['stream_contract']['interpreter_contract_sha256'], 'STATIC_POLICY_BINDING')
    need(canonical(acceptance)+'\n' == host.chain.files['review'].raw.decode(), 'STATIC_ACCEPTANCE_CHANGED')
    # This fixed A leaf checks actual installed catalog/P0 roots, origin files,
    # original registration/FIRST and the complete old physical material chain.
    from .draft_group_source_review import _native_materials
    material_facts = _native_materials(db,entry.policy,None,states=states,events=events,host=host)
    from .draft_group_host_native_v2 import material_scope
    with material_scope(material_facts):
        need(material_facts.baseline_raw == capture.raw and material_facts.policy_raw == capture.policy_raw
             and material_facts.acceptance_raw == host.chain.files['review'].raw
             and material_facts.configuration_sha == host.pins.configuration_sha
             and material_facts.semantic_adoption_sha == host.pins.semantic_sha
             and material_facts.source_sha == host.pins.source_sha
             and material_facts.acceptance_sha == host.pins.review_sha, 'HISTORY_MATERIALS_CHANGED')
        from .draft_group_source_review import collect_native_v2_prefix_proofs_in
        prefix_proofs = collect_native_v2_prefix_proofs_in(host,db,states,events,material_facts)
        observation = GroupNativeV2SourceObserver.prepare_release(observer,capture.raw)
        sealed_capture=validate_native_v2_observer_capture(observer)
        need(sealed_capture.entry is capture.entry and sealed_capture.raw is capture.raw
             and sealed_capture.policy_raw is capture.policy_raw
             and sealed_capture.wall_start==capture.wall_start and sealed_capture.monotonic_start==capture.monotonic_start
             and sealed_capture.not_after==capture.not_after and sealed_capture.deadline==capture.deadline
             and type(sealed_capture.observation_raw) is bytes
             and observation.raw==sealed_capture.observation_raw,'CAPTURE_SEAL_REQUIRED')
        capture=sealed_capture
        value = validate_observation(observation.value)
        from .draft_group_host_review import GroupInputAdapter
        need(type(host.adapter) is GroupInputAdapter, 'ACTUAL_ADAPTER_REQUIRED')
        inspection = GroupInputAdapter.inspect_in(host.adapter,None,value)
        checked = _fixed_leaf('validate_native_v2_seal_inputs')(host,observer,observation,inspection)
        need(checked is inspection, 'ACTUAL_QA_INSPECTION_REQUIRED')
        from .draft_group_source_review import validate_native_v2_prefix_proofs
        proofs = validate_native_v2_prefix_proofs(prefix_proofs,value['sources'])
        witness = {'schema':2,'profile':'GROUP_CURRENT_SOURCE_BINDING_V2','authority':False,'binding_mode':MODE,
            'configuration_sha':host.pins.configuration_sha,'baseline_source_material_sha':host.pins.source_sha,
            'origin_source_material_sha':policy['origin_source_descriptor']['sha256'],
            'runtime_source_policy_sha':acceptance['runtime_source_policy_sha'],'baseline_acceptance_sha':host.pins.review_sha,
            'native_contract_sha':policy['native_contract_sha'],'semantic_scope_sha':value['semantic_scope_sha'],
            'entry_epoch_sha':digest({'profile':'GROUP_ENTRY_EPOCH_V1','entry_id':entry.id}),
            'capture_started_at_ms':int(capture.wall_start*1000),
            'qualified_not_after_ms':int(min(capture.not_after,
                capture.wall_start+entry.deadline-capture.monotonic_start)*1000),
            'source_observation_profile':value['profile'],'source_observation_sha':digest(value),
            'sources':value['sources'],'qualification_generation_sha':digest(value['sources']),
            'permission_facts_sha':value['permission_facts_sha256'],'prefix_proofs':proofs,
            'prefix_preservation_sha':digest(proofs),'reviewed_delta_sha':digest(policy['known_user_reviews'])}
        validate_current_binding(witness)
        GroupNativeV2SourceObserver.pure_release_fence(observer)
        _actual_host(host)
        need(not any(f.host is host and f.phase != 'CLOSED' for f in _BINDINGS.values()), 'BINDING_ALREADY_ISSUED')
        binding = object.__new__(GroupCurrentSourceBinding)
        _BINDINGS[binding] = _LiveBinding(host,entry,observer,capture,'NATIVE_QA_CHECKED',
                                        canonical(witness),observation.raw,inspection,threading.get_ident())
        entry.issued[id(binding)] = binding
        entry.stack.callback(_close_if_issued,host,binding)
        return binding

def validate_current_source_binding(host, binding, *, required_phase='ADMISSION_READY'):
    need(type(required_phase) is str and required_phase in PHASES[:-1], 'PHASE_INVALID')
    facts = _record(host,binding)
    need(facts.phase == required_phase, 'PHASE_REQUIRED')
    return binding


def current_binding_facts(binding):
    need(type(binding) is GroupCurrentSourceBinding, 'BINDING_REQUIRED')
    facts = _BINDINGS.get(binding)
    need(facts is not None, 'BINDING_UNISSUED')
    _record(facts.host,binding)
    return json.loads(facts.witness_raw)


def current_binding_observation(host,binding):
    facts = _record(host,binding)
    return json.loads(facts.observation_raw)


def _binding_for_host(host,phase):
    _actual_host(host)
    matches=[value for value,facts in _BINDINGS.items() if facts.host is host and facts.phase==phase]
    need(len(matches)==1,'PHASE_BINDING_REQUIRED')
    return validate_current_source_binding(host,matches[0],required_phase=phase)


def binding_for_current_source(host):
    return _binding_for_host(host,'ADMISSION_READY')


def current_binding_phase(host,binding):
    return _record(host,binding).phase


def advance_current_source_binding(host,binding,phase,*,receipt=None):
    facts = _record(host,binding)
    need(type(phase) is str and phase in PHASES, 'PHASE_INVALID')
    need(PHASES.index(phase) == PHASES.index(facts.phase)+1, 'PHASE_ORDER')
    entry = facts.entry
    if phase == 'BOOTSTRAP_LOCAL_ONLY':
        from .draft_group_runtime_host import BootstrapSourceInspection,AccountService,GroupExecutionGate,Broker
        source = host._source
        warm=(not entry.pre_storage and type(entry.service) is AccountService and entry.listener_bound
              and type(entry.broker) is Broker and entry.broker.service is entry.service
              and entry.broker.policy is entry.policy and GroupExecutionGate._fixed_live_chain(entry))
        need((entry.pre_storage or warm) and type(source) is BootstrapSourceInspection
             and entry.issued.get(id(source)) is source and source.host is host and source.entry is entry
             and source.facts_sha == digest(json.loads(facts.observation_raw)), 'BOOTSTRAP_SOURCE_REQUIRED')
        if warm:
            workflow=entry.service.workflow
            need(workflow.active_lease is None and workflow.active_token is None
                 and workflow.execution_deadline is None,'WARM_LOCAL_NO_ADMISSION_REQUIRED')
    elif phase == 'COMPLETE_SERVICE_NO_ADMISSION':
        from .draft_group_runtime_host import QualifiedGroupSource, AccountService
        source = host._source
        need(not entry.pre_storage and entry.listener_bound and type(entry.service) is AccountService
             and type(source) is QualifiedGroupSource and entry.issued.get(id(source)) is source
             and source.host is host and source.entry is entry
             and source.facts_sha == digest(json.loads(facts.observation_raw)), 'COMPLETE_SERVICE_REQUIRED')
    elif phase in ('REVIEW_PENDING','REVIEW_COMMITTED','ADMISSION_READY'):
        from .draft_group_source_review import validate_source_review_v2_phase_receipt
        validate_source_review_v2_phase_receipt(host,binding,phase,receipt)
    elif phase == 'CLOSED':
        close_current_source_binding(host,binding); return binding
    _record(host,binding)
    _BINDINGS[binding] = replace(facts,phase=phase,review_receipt=receipt or facts.review_receipt)
    return binding


def close_current_source_binding(host,binding):
    need(type(binding) is GroupCurrentSourceBinding, 'BINDING_REQUIRED')
    facts = _BINDINGS.get(binding)
    need(facts is not None and facts.host is host, 'BINDING_UNISSUED')
    facts.entry.issued.pop(id(binding),None)
    _BINDINGS.pop(binding,None)


def _close_if_issued(host,binding):
    if binding in _BINDINGS:
        close_current_source_binding(host,binding)
