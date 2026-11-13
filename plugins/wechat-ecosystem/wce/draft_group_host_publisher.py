"""Actual fixed FIRST and registration proof producer; no token/platform effect."""
from dataclasses import dataclass,field
from hashlib import sha256
import json,os
from .draft_group_runtime_host import need,hold,QualifiedGroupSource,canonical,digest,_TIME,_MONOTONIC
from .draft_group_read_family_files import FamilyFiles,proposed_pack,prepare_first_files,read_first_files
from .draft_group_read_family_store import (original_root_scope,family_scope,register_first_in,
    recover_family_in,query_first_in,prepared_binding,_first_payload,_purpose,_registration)
from . import draft_group_read_family_values as values
from .draft_group_input_files import _FixedFileIO,FileEvidence,InputFiles,_closed,_hash,_int
from .draft_group_operator_semantics import is_operator, original_root_evidence, artifact_inventory, source_generation


class HostProofFiles(_FixedFileIO):
    def _config(self,role):
        need(role=='read_delegation','GROUP_HOST_PROOF_ROLE')
        return ('group-proofs','read-delegation-','HOST_VERIFIED_GROUP_READ_DELEGATION_V1',2*1024*1024)
    def _encode(self,role,value):
        self._config(role);_read_proof(value);return (canonical(value)+'\n').encode()
    def _evidence(self,role,key,raw,expected_sha=None):
        self._config(role);need(sha256(raw).hexdigest()==key and (expected_sha is None or key==expected_sha),'GROUP_HOST_PROOF_SHA')
        value=json.loads(raw);_read_proof(value);need(raw==(canonical(value)+'\n').encode(),'GROUP_HOST_PROOF_CANONICAL')
        return HostReadProof(role,key,key,len(raw),raw)


@dataclass(frozen=True)
class HostReadProof:
    role:str;key:str;sha256:str;size:int;raw:bytes=field(repr=False)
    @property
    def value(self):return _read_proof(json.loads(self.raw))
    @property
    def authority(self):return False


def _current_observation(host):
    if is_operator(host):
        from .draft_group_host_operator import binding_for_host,current_binding_facts
        return current_binding_facts(binding_for_host(host,None))
    return host.observer.inspect(host.chain.files['source'].raw).value


def _read_proof(value):
    _closed(value,('schema','profile','authority','family_id','registration_sha','first_proof_sha','covenant_sha','semantic_scope_sha',
        'source_material_sha','purpose_key','purpose_instance_id','qualified_binding','source_observation_sha','host_acceptance_sha','observed_at_ms','not_after_ms'))
    need(value['schema']==1 and type(value['schema']) is int and value['profile']=='HOST_VERIFIED_GROUP_READ_DELEGATION_V1' and value['authority'] is False,'GROUP_HOST_READ_PROOF')
    for key in ('family_id','registration_sha','first_proof_sha','covenant_sha','semantic_scope_sha','source_material_sha','purpose_key','purpose_instance_id','source_observation_sha','host_acceptance_sha'):_hash(value[key])
    _int(value['observed_at_ms'],1);_int(value['not_after_ms'],value['observed_at_ms']+1)
    from .draft_group_input_files import _binding
    _binding(value['qualified_binding']);return value


def _source(host):
    source=host._source
    need(type(source) is QualifiedGroupSource and host.entry.issued.get(id(source)) is source,'GROUP_CURRENT_SOURCE_REQUIRED')
    if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host):
        from .draft_group_host_review import local_registration_inspection_in
        local_registration_inspection_in(host,history_locators=None)
    else:
        host.current_no_token_in(None,source, history_locators=None)
    return source


def _covenant_template(host):
    expected=host.chain.config['first_covenant_sha'];found=[]
    if is_operator(host):
        pin=host.chain.files['first_covenant'];pin.check()
        need(pin.sha==expected,'GROUP_FIXED_COVENANT_TEMPLATE_REQUIRED')
        found.append(values.decode('covenant',pin.raw))
    else:
        for pin in host.chain.helpers:
            if pin.sha==expected:
                pin.check();found.append(values.decode('covenant',pin.raw))
    need(len(found)==1,'GROUP_FIXED_COVENANT_TEMPLATE_REQUIRED');c=found[0];s=host.chain.semantic
    need(c['original_scope_sha']==host.chain.source['semantic_scope_sha'] and c['read_contract_sha']==s['read_contract_sha']
         and c['source_rights_expiry']==s['source_rights_expiry'] and c['platform_account_sha']==s['platform_account_sha']
         and c['stable_owner']==s['stable_owner'] and c['qualify_subjects']==s['semantic_scope']['qualify_subjects']
         and c['allowed_routes']==s['semantic_scope']['permitted_routes'],'GROUP_COVENANT_SOURCE_SCOPE')
    return c


def publish_first_current(host):
    """Produce P once from real current source; W recovery reuses original bytes."""
    source=_source(host);policy=host.entry.policy;semantic=host.chain.semantic;c=_covenant_template(host)
    if is_operator(host):
        from . import draft_group_operator_source_codec as operator
        anchor={'schema':1,'profile':operator.ANCHOR_PROFILE,'authority':False,
            'content_source_type':operator.CONTENT_SOURCE_TYPE,
            **{key:semantic[key] for key in operator.REQUEST_FIELDS},
            'request_identity_sha':semantic['operator_request_identity_sha'],'purpose':operator.PURPOSE}
        request=anchor['request_identity_sha']
        operator.validate_first_anchor(anchor)
    else:
        refs=semantic['original_human_refs'];primary={k:refs[0][k] for k in ('thread_id','turn_id','message_id')}
        request=values.request_identity(semantic['platform_account_sha'],primary)
        anchor={'profile':'GROUP_READ_FAMILY_ANCHOR_V1','request_identity_sha':request,'original_human_request_refs':refs,
            'original_text_sha':semantic['original_text_set_sha'],'stable_owner':semantic['stable_owner'],
            'platform_account_sha':semantic['platform_account_sha'],'purpose':'GROUP08_SAME_REQUEST'}
    need(values.family_anchor(anchor)==c['family_anchor_id'] and original_root_evidence(host)['origin_request_identity_sha']==request,'GROUP_FIRST_ORIGINAL_REQUEST')
    files=FamilyFiles(policy,host.entry.loop_guard);kind=host.chain.config['binding']['source_kind'];original=original_root_evidence(host)
    with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
        if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host):
            from .draft_group_host_review import local_registration_inspection_in
            local_registration_inspection_in(host,db,history_locators=history_locators)
        else:
            host.current_no_token_in(db,source, history_locators=history_locators)
        with original_root_scope(db,files,original,source_kind=kind, history_locators=history_locators) as closure:
            status=query_first_in(db,files,request,root_closure=closure,guard=host.entry.full_guard)
            if status['state']!='ABSENT':
                need(status['state'] in ('COMMITTED','NOT_COMMITTED'),'GROUP_FIRST_RECOVERY_HOLD')
                pack=read_first_files(files,request)
                need(pack.entry('covenant').sha256==host.chain.config['first_covenant_sha'],'GROUP_FIRST_COVENANT_CHANGED')
            else:
                facts=_current_observation(host);host.observer.prepare_release(host.chain.files['source'].raw);host.pure_release_fence()
                observed=int(_TIME()*1000);not_after=int(min(source.not_after,_TIME()+host.entry.deadline-_MONOTONIC())*1000)
                need(not_after>observed,'GROUP_FIRST_SOURCE_EXPIRED')
                proof={'schema':1,'profile':values.PROFILES['first_proof'][1],'authority':False,'family_anchor_id':c['family_anchor_id'],
                    'request_identity_sha':request,'covenant_sha':host.chain.config['first_covenant_sha'],'original_human_evidence_sha':original['source_evidence_sha'],
                    'semantic_review_sha':host.pins.semantic_sha,'first_binding':host.chain.config['binding'],
                    'first_directory':{'path_utf8_sha256':sha256(str(policy.root).encode()).hexdigest(),'device':policy.root_pin[0],'inode':policy.root_pin[1],'owner_uid':os.getuid()},
                    'coordination':{'platform_account_sha':files.publication.key,'anchor_identity':list(files.anchor_pin),'registry_parent_identity':list(files.parent_pin),'coordination_pin_sha':sha256(files.coord_raw).hexdigest()},
                    'host_provenance':{'helper_sha':host.pins.armed_sha,'dependencies_sha':digest([[str(p),h] for p,h in host.pins.helper_files]),
                        'unarmed_launcher_sha':host.pins.unarmed_sha,'pin_review_sha':host.pins.review_sha,'arm_receipt_sha':host.pins.arm_receipt_sha,'code_scope':host.chain.config['candidate_scope']},
                    'observed_generation_sha':digest(source_generation(host,facts)),'observed_ms':observed,'not_after_ms':not_after}
                if is_operator(host):
                    from . import draft_group_operator_source_codec as operator
                    proof['profile']=operator.FIRST_PROOF_PROFILE
                    proof['content_source_type']=operator.CONTENT_SOURCE_TYPE
                    proof['operator_source_evidence_sha']=proof.pop('original_human_evidence_sha')
                pack=proposed_pack(anchor,c,proof)
                prepare_first_files(files,pack,root_closure=closure,db=db)
    host._first_pack=pack
    if not hasattr(host.entry,'first_candidates'):host.entry.first_candidates={}
    candidate=_first_payload(pack,kind)['candidate'];host.entry.first_candidates[digest(candidate)]=canonical(candidate)
    return pack


def register_first_current_in(host,db,pack, *, history_locators=None):
    _source(host);need(getattr(host,'_first_pack',None) is pack,'GROUP_FIRST_PACK_UNISSUED')
    files=FamilyFiles(host.entry.policy,host.entry.loop_guard);kind=host.chain.config['binding']['source_kind']
    from .draft_group_store import GroupStore
    with original_root_scope(db,files,original_root_evidence(host),source_kind=kind, history_locators=history_locators) as closure:
        return register_first_in(db,GroupStore(digest(host.chain.config['binding']),_history_partial(host.verify_in, history_locators=history_locators)),pack,root_closure=closure,guard=host.entry.full_guard, history_locators=history_locators)


@dataclass(frozen=True,eq=False)
class QualifiedPreviewRead:
    host:object=field(repr=False);source:object=field(repr=False);registration:object=field(repr=False)
    family_id:str;purpose:dict;proof:HostReadProof


def qualify_initial_read_delegation(host,source,registration_evidence,purpose_key,db, *, history_locators=None):
    _source(host);need(source is host._source and type(registration_evidence) is FileEvidence and registration_evidence.role=='registration','GROUP_READ_REGISTRATION_REQUIRED')
    files=InputFiles(host.entry.policy,host.entry.loop_guard)
    need(files.read('registration',registration_evidence.key)==registration_evidence and registration_evidence.value['source_material_sha']==host.pins.source_sha,'GROUP_READ_REGISTRATION_BINDING')
    # LOCAL_NO_TOKEN proof/grant registration does not spend a platform read.
    # Actual TokenUse/current-active acquisition separately requires every
    # original successful upload and proof before any Token CLAIM or API.
    info=host._family_in(db, history_locators=history_locators);c=info['covenant'];p=next((p for p in c['purposes'] if p['source_grant_sha']==purpose_key),None)
    need(p is not None and p['purpose'] in ('QUALIFY','PREVIEW_ACCOUNT') and not info['unknown'],'GROUP_PURPOSE_INACTIVE')
    facts=_current_observation(host)
    value={'schema':1,'profile':'HOST_VERIFIED_GROUP_READ_DELEGATION_V1','authority':False,'family_id':c['family_anchor_id'],
        'registration_sha':registration_evidence.sha256,'first_proof_sha':info['first']['candidate']['first_proof_sha'],'covenant_sha':host.chain.config['first_covenant_sha'],
        'semantic_scope_sha':source.semantic_scope_sha,'source_material_sha':host.pins.source_sha,'purpose_key':p['source_grant_sha'],
        'purpose_instance_id':p['source_grant_sha'],'qualified_binding':host.chain.config['binding'],'source_observation_sha':digest(facts),
        'host_acceptance_sha':host.pins.review_sha,'observed_at_ms':int(_TIME()*1000),'not_after_ms':int(source.not_after*1000)}
    proof=HostProofFiles(host.entry.policy,host.entry.loop_guard).publish('read_delegation',value)
    result=QualifiedPreviewRead(host,source,registration_evidence,c['family_anchor_id'],p,proof);host.entry.issued[id(result)]=result
    return result


def register_read_purpose_current_in(host,db,qualified, *, history_locators=None):
    from .draft_group_read_family_store import restore_purpose_in,ACT
    from .draft_group_store import GroupStore
    _source(host);need(type(qualified) is QualifiedPreviewRead and qualified.host is host and host.entry.issued.get(id(qualified)) is qualified,'GROUP_QUALIFIED_READ_UNISSUED')
    need(qualified.proof.sha256 in host._registration['proof']['read_delegation_proof_shas'],'GROUP_READ_PROOF_NOT_REGISTERED')
    files=FamilyFiles(host.entry.policy,host.entry.loop_guard);pack=read_first_files(files,original_root_evidence(host)['origin_request_identity_sha'])
    p=qualified.purpose;ac={'schema':1,'profile':ACT,'authority':False,'family_anchor_id':qualified.family_id,'covenant_sha':pack.entry('covenant').sha256,
        'purpose':p['purpose'],'ordinal':p['ordinal'],'source_grant_sha':p['source_grant_sha'],'scope_sha':p['scope_sha'],'activation_kind':p['activation']['kind'],
        'route_decision_sha':None,'evidence_sha':qualified.proof.sha256}
    if not hasattr(host.entry,'family_candidates'):host.entry.family_candidates={}
    host.entry.family_candidates[digest(ac)]=(db,canonical(ac))
    with original_root_scope(db,files,original_root_evidence(host),source_kind=host.chain.config['binding']['source_kind'], history_locators=history_locators) as closure:
        return restore_purpose_in(db,GroupStore(digest(host.chain.config['binding']),_history_partial(host.verify_in, history_locators=history_locators)),pack,
            {'purpose':p['purpose'],'ordinal':p['ordinal']},{'route_decision_sha':None,'evidence_sha':qualified.proof.sha256},root_closure=closure,guard=host.entry.full_guard, history_locators=history_locators)


def publish_registration_current(host,registration_evidence,qualified_reads):
    from .draft_group_read_family_store import _gid
    source=_source(host);need(type(registration_evidence) is FileEvidence and registration_evidence.role=='registration','GROUP_REGISTRATION_BASE_REQUIRED')
    files=InputFiles(host.entry.policy,host.entry.loop_guard)
    need(files.read('registration',registration_evidence.key)==registration_evidence,'GROUP_REGISTRATION_BASE_CHANGED')
    need(type(qualified_reads) is tuple and all(type(q) is QualifiedPreviewRead and q.host is host
         and q.registration==registration_evidence and host.entry.issued.get(id(q)) is q for q in qualified_reads),'GROUP_READ_QUALIFICATION_REQUIRED')
    with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
        if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host):
            from .draft_group_host_review import local_registration_inspection_in
            local_registration_inspection_in(host,db,history_locators=history_locators)
        else:
            host.current_no_token_in(db,source, history_locators=history_locators)
        info=host._family_in(db, history_locators=history_locators)
        expected=[_gid(digest(host.chain.config['binding']),q.purpose) for q in qualified_reads]
        need(registration_evidence.value['family_id']==info['covenant']['family_anchor_id']
             and registration_evidence.value['read_delegation_ids']==expected,'GROUP_REGISTRATION_PURPOSES')
    facts=_current_observation(host);generation=(canonical(source_generation(host,facts))+'\n').encode()
    review=host.chain.files['review'];value={'schema':1,'profile':'HOST_VERIFIED_GROUP_REGISTRATION_V1','registration_sha':registration_evidence.sha256,
        'source_material_sha':host.pins.source_sha,'read_delegation_proof_shas':[q.proof.sha256 for q in qualified_reads],
        'artifact_inventory_sha':digest(artifact_inventory(host)),'original_save_evidence_sha':digest(registration_evidence.value['old_sources']),
        'helper_acceptance':{'kind':'HELPER_ACCEPTANCE','sha256':review.sha,'size':len(review.raw)},'qualified_binding':host.chain.config['binding'],
        'observed_generation':{'kind':'GENERATION','sha256':sha256(generation).hexdigest(),'size':len(generation)},'not_after':source.not_after}
    proof=files.publish('proof',value);need(files.read('proof',proof.key)==proof,'GROUP_REGISTRATION_PROOF_READBACK')
    head_path=host.entry.policy.root/'group-input-head.json'
    old=files.read_head() if head_path.exists() else None
    head={'schema':2,'profile':'GROUP_SELECTED_INPUT_HEAD_V2','registration_proof_sha':proof.sha256,'family_id':registration_evidence.value['family_id'],
        'seq':1 if old is None else old.value['seq']+1,'registration_sha':registration_evidence.sha256,
        'previous_head_sha':None if old is None else old.sha256,'source_material_sha':host.pins.source_sha}
    if old is not None and old.value['registration_sha']==registration_evidence.sha256 and old.value['source_material_sha']==host.pins.source_sha:
        need(old.value['schema']==2 and old.value['registration_proof_sha']==proof.sha256,'GROUP_ORIGINAL_REGISTRATION_PROOF_CHANGED')
        return proof,old
    plan=files.prepare_head(head,None if old is None else old.sha256);files.commit_head(plan)
    current=files.read_head();need(current.value==head,'GROUP_REGISTRATION_HEAD_READBACK')
    return proof,current


def restore_initial_read_purposes_current_in(host,db, *, history_locators=None):
    """Restore only original initial local SQL registrations after head CAS.

    No proof is reissued, no read is sent and no claim or cap is reset. The
    current Host still has to qualify every later TokenUse and actual read.
    Historical proof times remain historical; they are never a fresh lease.
    """
    from .draft_group_read_family_store import restore_purpose_in,ACT,_gid
    from .draft_group_store import GroupStore
    from .own_validation_scope import OwnedConnection,_transaction_marker
    _source(host)
    need(type(db)is OwnedConnection and _transaction_marker(db)is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==0,'GROUP_READ_RESTORE_TRANSACTION')
    source=host._source
    if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host):
        from .draft_group_host_review import local_registration_inspection_in
        local_registration_inspection_in(host,db,history_locators=history_locators)
    else:
        host.current_no_token_in(db,source, history_locators=history_locators)
    registration=host._registration;reg=registration['registration'];approved=registration['proof']
    info=host._family_in(db, history_locators=history_locators);need(not info['unknown'],'GROUP_RESULT_UNKNOWN')
    purposes=[p for p in info['covenant']['purposes']if p['purpose']in('QUALIFY','PREVIEW_ACCOUNT')]
    expected_purposes={'PREVIEW_ACCOUNT'}
    if info['covenant']['qualify_subjects']:
        expected_purposes.add('QUALIFY')
    need(len(purposes)==len(expected_purposes) and {p['purpose']for p in purposes}==expected_purposes
         and all(p['ordinal']==0 for p in purposes),'GROUP_INITIAL_PURPOSES_REQUIRED')
    shas=approved['read_delegation_proof_shas']
    need(len(shas)==len(purposes) and len(set(shas))==len(purposes)
         and reg['read_delegation_ids']==[_gid(info['account'],p)for p in purposes],
         'GROUP_ORIGINAL_READ_PROOFS_REQUIRED')
    files=HostProofFiles(host.entry.policy,host.entry.loop_guard)
    proofs=[files.read('read_delegation',key)for key in shas]
    pack=read_first_files(FamilyFiles(host.entry.policy,host.entry.loop_guard),
                          original_root_evidence(host)['origin_request_identity_sha'])
    for purpose,evidence in zip(purposes,proofs):
        value=evidence.value
        need(value['family_id']==reg['family_id']==info['covenant']['family_anchor_id']
             and value['registration_sha']==registration['registration_sha']
             and value['first_proof_sha']==pack.entry('first_proof').sha256
             and value['covenant_sha']==pack.entry('covenant').sha256
             and value['semantic_scope_sha']==source.semantic_scope_sha
             and value['source_material_sha']==reg['source_material_sha']
             and value['purpose_key']==value['purpose_instance_id']==purpose['source_grant_sha']
             and value['qualified_binding']==reg['binding']==host.chain.config['binding']
             and value['host_acceptance_sha']==approved['helper_acceptance']['sha256']
             and value['not_after_ms']==int(approved['not_after']*1000),
             'GROUP_ORIGINAL_READ_PROOF_CHANGED')
        candidate={'schema':1,'profile':ACT,'authority':False,'family_anchor_id':reg['family_id'],
            'covenant_sha':pack.entry('covenant').sha256,'purpose':purpose['purpose'],
            'ordinal':purpose['ordinal'],'source_grant_sha':purpose['source_grant_sha'],
            'scope_sha':purpose['scope_sha'],'activation_kind':purpose['activation']['kind'],
            'route_decision_sha':None,'evidence_sha':evidence.sha256}
        if not hasattr(host.entry,'family_candidates'):host.entry.family_candidates={}
        host.entry.family_candidates[digest(candidate)]=(db,canonical(candidate))
        family_files=FamilyFiles(host.entry.policy,host.entry.loop_guard)
        with original_root_scope(db,family_files,original_root_evidence(host),
                source_kind=host.chain.config['binding']['source_kind'], history_locators=history_locators)as root:
            restore_purpose_in(db,GroupStore(info['account'],_history_partial(host.verify_in, history_locators=history_locators)),pack,
                {'purpose':purpose['purpose'],'ordinal':purpose['ordinal']},
                {'route_decision_sha':None,'evidence_sha':evidence.sha256},
                root_closure=root,guard=host.entry.full_guard, history_locators=history_locators)
    if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host):
        from .draft_group_host_review import local_registration_inspection_in
        local_registration_inspection_in(host,db,history_locators=history_locators)
    else:
        host.current_no_token_in(db,source, history_locators=history_locators)
    host.pure_release_fence()
    return None


from .draft_group_history_context import history_transaction as _history_transaction


from functools import partial as _history_partial
