"""Operator source review: immutable facts, normal commit, fresh Owned readback.

The registry is local pipeline state. A file/JSON/append is never a source grant.
This module does not acquire a token, migrate storage or invoke a platform API.
"""
from . import draft_group_operator_time_v2 as time06
from contextvars import ContextVar
from dataclasses import dataclass, replace
from weakref import WeakKeyDictionary
import json
import threading
from .draft_group_contracts import canonical, digest
from .draft_group_runtime_host import need, hold, OwnedConnection, _transaction_marker
from .draft_group_input_files import _plain, _closed, _hash, _int, FileEvidence
from . import draft_group_operator_source_codec as codec

PROFILE=codec.SOURCE_REVIEW_PROFILE
KEYS=('schema','profile','authority','content_source_type','family_id','registration_sha',
      'semantic_scope_sha','original_source_material_sha','current_source_material_sha',
      'previous_review_sha','helper_acceptance_sha','qualification_generation_sha',
      'observed_at_ms','not_after_ms','configuration_sha','semantic_adoption_sha',
      'original_root_evidence_sha','runtime_source_policy_sha','current_binding','current_binding_sha')
_SCOPE=ContextVar('operator_source_review_append',default=None)
_FRESH=ContextVar('operator_source_review_fresh_owned',default=None)
_RECEIPTS=WeakKeyDictionary()
_PENDING=WeakKeyDictionary()


def validate(value):
    if type(value) is dict and value.get('profile')==time06.SOURCE_REVIEW_PROFILE_V2:
        return _require_review_time06(value)
    _plain(value);_closed(value,KEYS)
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE
         and value['authority'] is False and value['content_source_type']==codec.CONTENT_SOURCE_TYPE,
         'GROUP_OPERATOR_REVIEW_PROFILE')
    for key in KEYS:
        if key.endswith('_sha') and (key!='previous_review_sha' or value[key] is not None):_hash(value[key])
    for key in ('family_id','registration_sha'):_hash(value[key])
    _int(value['observed_at_ms'],1);_int(value['not_after_ms'],value['observed_at_ms']+1)
    try:observed=codec.validate_observation(value['current_binding'])
    except codec.OperatorSourceCodecError:hold('GROUP_OPERATOR_REVIEW_OBSERVATION')
    need(value['current_binding_sha']==digest(observed)
         and value['original_source_material_sha']==value['current_source_material_sha']==observed['source_material_sha']
         and value['semantic_scope_sha']==observed['semantic_scope_sha']
         and value['runtime_source_policy_sha']==observed['runtime_source_policy_sha']
         and value['qualification_generation_sha']==observed['proof_generation_sha']
         and value['observed_at_ms']==observed['observed_at_ms']
         and value['not_after_ms']==observed['qualified_not_after_ms'], 'GROUP_OPERATOR_REVIEW_BINDING')
    return json.loads(canonical(value))


def validate_history_in(db,policy,candidate,*,states=None,events=None,previous=None):
    """Archived fixed materials only; no current qualification or clock renewal."""
    if type(candidate) is dict and candidate.get('profile')==time06.SOURCE_REVIEW_PROFILE_V2:
        return validate_history_time06_in(db,policy,candidate,states=states,events=events,previous=previous)
    from .draft_group_host_history import _context
    from .draft_group_host_operator import read_operator_review_materials_in
    from .draft_group_input_files import InputFiles
    from .draft_group_read_family_store import _history_file_guard
    _context(db,policy);c=validate(candidate)
    materials=read_operator_review_materials_in(db,policy,c,states=states,events=events)
    try:
        source=materials.source;runtime=materials.runtime_policy;semantic=materials.semantic
        need(c['configuration_sha']==materials.configuration_sha
             and c['semantic_adoption_sha']==materials.semantic_sha
             and c['current_source_material_sha']==materials.source_sha
             and c['helper_acceptance_sha']==materials.review_sha
             and c['runtime_source_policy_sha']==materials.runtime_policy_sha
             and c['original_root_evidence_sha']==semantic['original_root_evidence_sha'],
             'GROUP_OPERATOR_REVIEW_MATERIAL_CHANGED')
        try:codec.validate_material_links(source,runtime,semantic,c['current_binding'],
            materials.descriptor(c['current_binding_sha']),current_binding_sha=c['current_binding_sha'],
            configuration_sha=c['configuration_sha'])
        except codec.OperatorSourceCodecError:hold('GROUP_OPERATOR_REVIEW_MATERIAL_CHANGED')
        inputs=InputFiles(policy,lambda:_history_file_guard(policy))
        registration,registration_pin=inputs._entry('registration',c['registration_sha'])
        origin,origin_pin=inputs._entry('source',c['original_source_material_sha'])
        need(origin.raw==materials.source_raw and registration.value['source_material_sha']==origin.sha256
             and registration.value['family_id']==c['family_id']==source['allowed_read_scope']['family_anchor_sha']
             and registration.value['binding']==runtime['binding'], 'GROUP_OPERATOR_REVIEW_REGISTRATION')
        if previous is not None:
            need(previous['profile']==PROFILE,'GROUP_OPERATOR_REVIEW_MODE_CHANGED')
            for key in ('family_id','registration_sha','original_source_material_sha','semantic_scope_sha'):
                need(previous[key]==c[key],'GROUP_OPERATOR_REVIEW_CHAIN_CHANGED')
            try:codec.validate_continuation(previous['current_binding'],c['current_binding'])
            except codec.OperatorSourceCodecError:hold('GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
        inputs._pure_entries((('registration',registration.key,registration_pin),('source',origin.key,origin_pin)))
        materials.collective_fence()
        return c
    finally:
        from .draft_group_pin_resources import close_all
        import sys
        close_all([materials.close],sys.exc_info()[1])


class _Receipt:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):hold('GROUP_OPERATOR_REVIEW_PRIVATE_RECEIPT_REQUIRED')


@dataclass(frozen=True)
class _Facts:
    host:object
    binding:object
    writer:object
    writer_epoch:object
    candidate_raw:str
    proof:object
    proof_pin:object
    files:object
    thread:int
    status:str
    event_seq:int|None=None
    event_sha:str|None=None
    readback_db:object=None
    readback_epoch:object=None


def _receipt(host,binding,receipt=None):
    try:value=_PENDING.get(binding) if receipt is None else receipt
    except TypeError:value=None
    need(type(value) is _Receipt,'GROUP_OPERATOR_REVIEW_RECEIPT_REQUIRED')
    facts=_RECEIPTS.get(value)
    need(facts is not None and facts.host is host and facts.binding is binding
         and _PENDING.get(binding) is value and facts.thread==threading.get_ident(),
         'GROUP_OPERATOR_REVIEW_RECEIPT_UNISSUED')
    return value,facts


def validate_phase_receipt(host,binding,phase,receipt):
    value,facts=_receipt(host,binding,receipt)
    if phase=='REVIEW_PENDING':
        need(facts.status=='PREPARED' and type(facts.writer) is OwnedConnection
             and _transaction_marker(facts.writer)==facts.writer_epoch,
             'GROUP_OPERATOR_REVIEW_PREPARED_REQUIRED')
    elif phase in ('REVIEW_COMMITTED','ADMISSION_READY'):
        fresh=_FRESH.get()
        need(facts.status=='READBACKED' and fresh is not None and fresh==(facts.readback_db,binding,facts.proof.sha256)
             and type(facts.readback_db) is OwnedConnection and facts.readback_db is not facts.writer
             and _transaction_marker(facts.readback_db)==facts.readback_epoch,
             'GROUP_OPERATOR_REVIEW_NORMAL_COMMIT_FRESH_OWNED_REQUIRED')
    else:hold('GROUP_OPERATOR_REVIEW_PHASE_INVALID')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return value


def validate_append_scope(host,db,candidate):
    from .draft_group_host_operator import validate_current_source_binding
    receipt=_SCOPE.get();facts=None if receipt is None else _RECEIPTS.get(receipt)
    need(facts is not None and facts.host is host and facts.writer is db
         and type(db) is OwnedConnection and _transaction_marker(db)==facts.writer_epoch
         and facts.thread==threading.get_ident() and facts.candidate_raw==canonical(validate(candidate))
         and facts.status in ('PREPARED','APPENDED'),'GROUP_OPERATOR_REVIEW_ADMISSION_REQUIRED')
    validate_current_source_binding(host,facts.binding,required_phase='REVIEW_PENDING')
    need(getattr(host,'_active_group_token',None) is None,'GROUP_OPERATOR_REVIEW_LOCAL_NO_TOKEN_REQUIRED')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return receipt


def before_event_in(db,account,kind,payload):
    from .draft_group_source_review import _replay
    receipt=_SCOPE.get();facts=None if receipt is None else _RECEIPTS.get(receipt)
    need(facts is not None,'GROUP_OPERATOR_REVIEW_ADMISSION_REQUIRED')
    validate_append_scope(facts.host,db,payload['candidate'])
    need(account==digest(facts.host.chain.config['binding']) and kind=='PREVIEW'
         and facts.status=='PREPARED','GROUP_OPERATOR_REVIEW_WRAPPER')
    heads,_=_replay(db,facts.host.entry.policy)
    need(payload['candidate']['previous_review_sha']==heads.get(payload['candidate']['family_id']),
         'GROUP_SOURCE_REVIEW_FORK')


def after_event_in(db,**kwargs):
    from .draft_group_source_review import _replay,_v2_actual_event
    candidate=kwargs['payload']['candidate'];receipt=_SCOPE.get()
    facts=None if receipt is None else _RECEIPTS.get(receipt)
    need(facts is not None,'GROUP_OPERATOR_REVIEW_ADMISSION_REQUIRED')
    validate_append_scope(facts.host,db,candidate)
    need(facts.status=='PREPARED','GROUP_OPERATOR_REVIEW_DUPLICATE_APPEND')
    heads,values=_replay(db,facts.host.entry.policy)
    need(heads.get(candidate['family_id'])==facts.proof.sha256 and values[facts.proof.sha256]==candidate,
         'GROUP_SOURCE_REVIEW_READBACK')
    seq,event_sha=_v2_actual_event(db,digest(facts.host.chain.config['binding']),candidate,facts.proof.sha256)
    _RECEIPTS[receipt]=replace(facts,status='APPENDED',event_seq=seq,event_sha=event_sha)


def qualify_review_in(host,db,registration_evidence,original_source_evidence,*,history_locators=None):
    from .draft_group_host_operator import (binding_for_host,current_binding_facts,
                                           advance_current_source_binding)
    from .draft_group_source_review import SourceReviewFiles,_replay
    from .draft_group_input_files import InputFiles
    from .draft_group_store import GroupStore
    from functools import partial
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None,
         'GROUP_OPERATOR_REVIEW_OWNED_REQUIRED')
    binding=binding_for_host(host,'COMPLETE_SERVICE_NO_ADMISSION')
    need(type(registration_evidence) is FileEvidence and registration_evidence.role=='registration'
         and type(original_source_evidence) is FileEvidence and original_source_evidence.role=='source',
         'GROUP_SOURCE_REVIEW_INPUT')
    inputs=InputFiles(host.entry.policy,host.entry.full_guard)
    registration,rpin=inputs._entry('registration',registration_evidence.key)
    origin,opin=inputs._entry('source',original_source_evidence.key)
    need(registration==registration_evidence and origin==original_source_evidence,'GROUP_SOURCE_REVIEW_INPUT')
    observed=current_binding_facts(binding);chain=host.chain
    need(registration.value['source_material_sha']==origin.sha256==host.pins.source_sha==observed['source_material_sha']
         and origin.raw==chain.files['source'].raw
         and registration.value['family_id']==chain.source['allowed_read_scope']['family_anchor_sha'],
         'GROUP_SOURCE_REVIEW_ORIGINAL')
    heads,_=_replay(db,host.entry.policy)
    candidate=dict(schema=1,profile=PROFILE,authority=False,content_source_type=codec.CONTENT_SOURCE_TYPE,
        family_id=registration.value['family_id'],registration_sha=registration.sha256,
        semantic_scope_sha=observed['semantic_scope_sha'],original_source_material_sha=origin.sha256,
        current_source_material_sha=origin.sha256,previous_review_sha=heads.get(registration.value['family_id']),
        helper_acceptance_sha=host.pins.review_sha,qualification_generation_sha=observed['proof_generation_sha'],
        observed_at_ms=observed['observed_at_ms'],not_after_ms=observed['qualified_not_after_ms'],
        configuration_sha=host.pins.configuration_sha,semantic_adoption_sha=host.pins.semantic_sha,
        original_root_evidence_sha=chain.semantic['original_root_evidence_sha'],
        runtime_source_policy_sha=observed['runtime_source_policy_sha'],current_binding=observed,
        current_binding_sha=digest(observed))
    if observed['profile']==time06.OBSERVATION_PROFILE_V2:
        candidate.update(schema=2,profile=time06.SOURCE_REVIEW_PROFILE_V2,
            source_lifetime_not_after_ms=observed['source_lifetime_not_after_ms'],
            qualified_not_after_ms=observed['qualified_not_after_ms'])
    validate(candidate)
    files=SourceReviewFiles(host.entry.policy,host.entry.full_guard)
    proof,pin=files._publish_observed('source_review',candidate)
    need(files.read('source_review',proof.key)==proof,'GROUP_SOURCE_REVIEW_READBACK')
    inputs._pure_entries((('registration',registration.key,rpin),('source',origin.key,opin)))
    need(binding not in _PENDING,'GROUP_OPERATOR_REVIEW_ALREADY_PENDING')
    receipt=object.__new__(_Receipt)
    _RECEIPTS[receipt]=_Facts(host,binding,db,_transaction_marker(db),canonical(candidate),proof,pin,
                            files,threading.get_ident(),'PREPARED')
    _PENDING[binding]=receipt;host.entry.stack.callback(_release,binding,receipt)
    advance_current_source_binding(host,binding,'REVIEW_PENDING',receipt=receipt)
    token=_SCOPE.set(receipt)
    if not hasattr(host.entry,'review_candidates'):host.entry.review_candidates={}
    host.entry.review_candidates[digest(candidate)]=(db,canonical(candidate))
    try:
        identity='group-source-review-'+proof.sha256
        GroupStore(digest(chain.config['binding']),partial(host.verify_in,history_locators=history_locators)).register_preview_in(
            db,identity,source_kind=chain.config['binding']['source_kind'],input_sha=origin.sha256,
            request_key=identity,scope_sha=observed['semantic_scope_sha'],candidate=candidate,
            evidence_sha=proof.sha256,history_locators=history_locators)
        need(_receipt(host,binding,receipt)[1].status=='APPENDED','GROUP_OPERATOR_REVIEW_APPEND_UNDETERMINED')
        return proof
    except BaseException:
        _RECEIPTS[receipt]=replace(_RECEIPTS[receipt],status='APPEND_UNKNOWN')
        raise
    finally:_SCOPE.reset(token)


def commit_review_in(host,binding,db,review_sha):
    from .draft_group_host_operator import validate_current_source_binding,close_current_source_binding
    from .draft_group_read_family_store import _ROOT_CURRENT,_SCOPE as family_scope
    validate_current_source_binding(host,binding,required_phase='REVIEW_PENDING')
    receipt,facts=_receipt(host,binding)
    need(facts.writer is db and facts.proof.sha256==review_sha and facts.status=='APPENDED'
         and type(db) is OwnedConnection and _transaction_marker(db)==facts.writer_epoch
         and _SCOPE.get() is None and _ROOT_CURRENT.get() is None and family_scope.get() is None,
         'GROUP_OPERATOR_REVIEW_COMMIT_SCOPE_REQUIRED')
    try:
        OwnedConnection.commit(db)
        need(not db.in_transaction,'GROUP_OPERATOR_REVIEW_COMMIT_UNKNOWN')
    except BaseException:
        _RECEIPTS[receipt]=replace(facts,status='COMMIT_UNKNOWN')
        close_current_source_binding(host,binding)
        hold('GROUP_OPERATOR_REVIEW_COMMIT_UNKNOWN')
    _RECEIPTS[receipt]=replace(facts,status='NORMAL_COMMITTED')
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    try:
        with cold_history_snapshot_fixed(host.entry.policy,host.entry) as (fresh,history_locators):
            token=_FRESH.set((fresh,binding,review_sha))
            try:result=finalize_review_in(host,binding,fresh,review_sha)
            finally:_FRESH.reset(token)
        return result
    except BaseException:
        close_current_source_binding(host,binding)
        raise


def finalize_review_in(host,binding,db,review_sha):
    from .draft_group_host_operator import validate_current_source_binding,advance_current_source_binding
    from .draft_group_source_review import _replay_values_in,_v2_actual_event
    from .draft_group_response_history import (read_group_replay_snapshot_in,release_group_replay_snapshot_in,
                                              verify_group_replay_inputs_in)
    validate_current_source_binding(host,binding,required_phase='REVIEW_PENDING')
    receipt,facts=_receipt(host,binding);fresh=_FRESH.get()
    need(fresh is not None and fresh==(db,binding,review_sha) and facts.status=='NORMAL_COMMITTED'
         and facts.proof.sha256==review_sha and type(db) is OwnedConnection and db is not facts.writer
         and _transaction_marker(db) is not None and db.execute('PRAGMA query_only').fetchone()[0]==1,
         'GROUP_OPERATOR_REVIEW_FRESH_OWNED_REQUIRED')
    states,events=read_group_replay_snapshot_in(db)
    try:
        heads,values=_replay_values_in(db,host.entry.policy,events);c=json.loads(facts.candidate_raw)
        need(heads.get(c['family_id'])==review_sha and values[review_sha]==c,'GROUP_SOURCE_REVIEW_READBACK')
        seq,event_sha=_v2_actual_event(db,digest(host.chain.config['binding']),c,review_sha)
        need((seq,event_sha)==(facts.event_seq,facts.event_sha),'GROUP_SOURCE_REVIEW_ORIGINAL_EVENT_CHANGED')
        facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
        verify_group_replay_inputs_in(db,states,events)
        _RECEIPTS[receipt]=replace(facts,status='READBACKED',readback_db=db,readback_epoch=_transaction_marker(db))
        host._current_source_review_sha=review_sha
        advance_current_source_binding(host,binding,'REVIEW_COMMITTED',receipt=receipt)
        advance_current_source_binding(host,binding,'ADMISSION_READY',receipt=receipt)
        return dict(state='SOURCE_REVIEW_COMMITTED_FRESH_OWNED',authority=False,
                    review_sha=review_sha,event_seq=seq,event_sha=event_sha)
    finally:release_group_replay_snapshot_in(db,states,events)


def committed_review_sha(host,binding):
    from .draft_group_host_operator import validate_current_source_binding,current_binding_facts
    validate_current_source_binding(host,binding)
    _,facts=_receipt(host,binding)
    need(facts.status=='READBACKED' and json.loads(facts.candidate_raw)['current_binding_sha']
         ==digest(current_binding_facts(binding)),'GROUP_OPERATOR_REVIEW_COMMITTED_BINDING_REQUIRED')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return facts.proof.sha256


def _release(binding,receipt):
    _PENDING.pop(binding,None);_RECEIPTS.pop(receipt,None)


def _require_review_time06(candidate):
    try:return time06.validate_review_v2(candidate)
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        hold('GROUP_OPERATOR_REVIEW_BINDING')

def validate_history_time06_in(db,policy,candidate,*,states=None,events=None,previous=None):
    """Archived fixed materials only; no current qualification or clock renewal."""
    from .draft_group_host_history import _context
    from .draft_group_host_operator import read_operator_review_materials_in
    from .draft_group_input_files import InputFiles
    from .draft_group_read_family_store import _history_file_guard
    _context(db,policy);c=_require_review_time06(candidate)
    materials=read_operator_review_materials_in(db,policy,c,states=states,events=events)
    try:
        source=materials.source;runtime=materials.runtime_policy;semantic=materials.semantic
        need(c['configuration_sha']==materials.configuration_sha
             and c['semantic_adoption_sha']==materials.semantic_sha
             and c['current_source_material_sha']==materials.source_sha
             and c['helper_acceptance_sha']==materials.review_sha
             and c['runtime_source_policy_sha']==materials.runtime_policy_sha
             and c['original_root_evidence_sha']==semantic['original_root_evidence_sha'],
             'GROUP_OPERATOR_REVIEW_MATERIAL_CHANGED')
        try:time06.validate_material_links_v2(source,runtime,semantic,c['current_binding'],
            materials.descriptor(c['current_binding_sha']),current_binding_sha=c['current_binding_sha'],
            configuration_sha=c['configuration_sha'])
        except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):hold('GROUP_OPERATOR_REVIEW_MATERIAL_CHANGED')
        inputs=InputFiles(policy,lambda:_history_file_guard(policy))
        registration,registration_pin=inputs._entry('registration',c['registration_sha'])
        origin,origin_pin=inputs._entry('source',c['original_source_material_sha'])
        need(origin.raw==materials.source_raw and registration.value['source_material_sha']==origin.sha256
             and registration.value['family_id']==c['family_id']==source['allowed_read_scope']['family_anchor_sha']
             and registration.value['binding']==runtime['binding'], 'GROUP_OPERATOR_REVIEW_REGISTRATION')
        if previous is not None:
            need(previous['profile']==time06.SOURCE_REVIEW_PROFILE_V2,'GROUP_OPERATOR_REVIEW_MODE_CHANGED')
            for key in ('family_id','registration_sha','original_source_material_sha','semantic_scope_sha'):
                need(previous[key]==c[key],'GROUP_OPERATOR_REVIEW_CHAIN_CHANGED')
            try:time06.validate_review_continuation_v2(previous,c)
            except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):hold('GROUP_OPERATOR_REVIEW_CONTINUATION_CHANGED')
        inputs._pure_entries((('registration',registration.key,registration_pin),('source',origin.key,origin_pin)))
        materials.collective_fence()
        return c
    finally:
        from .draft_group_pin_resources import close_all
        import sys
        close_all([materials.close],sys.exc_info()[1])
