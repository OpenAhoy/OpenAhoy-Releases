"""Immutable technical source continuations. Never renews FIRST or user scope."""
from . import draft_group_operator_time_v2 as time06
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,field
from hashlib import sha256
import json
import threading
from .draft_group_runtime_host import need,hold,canonical,digest,OwnedConnection,_transaction_marker
from .draft_group_input_files import _FixedFileIO,FileEvidence,_plain,_closed,_hash,_int,decode

PROFILE='GROUP_CURRENT_SOURCE_REVIEW_V1'
PROFILE_V2='GROUP_CURRENT_SOURCE_REVIEW_V2'
KEYS=('schema','profile','authority','family_id','registration_sha','semantic_scope_sha',
    'original_source_material_sha','current_source_material_sha','previous_review_sha','helper_acceptance_sha',
    'original_human_refs_sha','known_user_classifications','qualification_generation_sha','observed_at_ms','not_after_ms')
_SCOPE=ContextVar('fixed_group_source_continuation',default=None);_ISSUED={}


def validate(value):
    _plain(value)
    from .draft_group_operator_source_codec import SOURCE_REVIEW_PROFILE
    if type(value) is dict and value.get('profile') in (SOURCE_REVIEW_PROFILE,time06.SOURCE_REVIEW_PROFILE_V2):
        from .draft_group_operator_review import validate as validate_operator
        return validate_operator(value)
    if type(value) is dict and value.get('profile')==PROFILE_V2:
        from .draft_group_native_v2_codec import validate_source_review
        return validate_source_review(value)
    _closed(value,KEYS)
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE and value['authority'] is False,'GROUP_SOURCE_REVIEW_PROFILE')
    for key in ('family_id','registration_sha','semantic_scope_sha','original_source_material_sha','current_source_material_sha','helper_acceptance_sha','original_human_refs_sha','qualification_generation_sha'):_hash(value[key])
    if value['previous_review_sha'] is not None:_hash(value['previous_review_sha'])
    _int(value['observed_at_ms'],1);_int(value['not_after_ms'],1)
    need(value['not_after_ms']>value['observed_at_ms'],'GROUP_SOURCE_REVIEW_EXPIRED')
    need(type(value['known_user_classifications']) is list,'GROUP_SOURCE_REVIEW_CLASSIFICATIONS')
    for item in value['known_user_classifications']:
        _closed(item,('human','disposition'))
        from .draft_group_input_files import _human
        _human(item['human']);need(item['disposition'] in ('NON_SCOPE_CHANGE','INPUT_FACT','NON_GRANT'),'GROUP_SOURCE_REVIEW_SCOPE_CHANGED')
    return value


@dataclass(frozen=True)
class SourceReviewEvidence:
    role:str
    key:str
    sha256:str
    size:int
    raw:bytes=field(repr=False)
    @property
    def authority(self):return False
    @property
    def value(self):return validate(json.loads(self.raw))


class SourceReviewFiles(_FixedFileIO):
    def _config(self,role):
        need(role=='source_review','GROUP_SOURCE_REVIEW_ROLE')
        return ('group-proofs','group-source-review-',PROFILE,2*1024*1024)
    def _encode(self,role,value):
        self._config(role);validate(value);return (canonical(value)+'\n').encode()
    def _evidence(self,role,key,raw,expected_sha=None):
        self._config(role);_hash(key)
        need(type(raw) is bytes and sha256(raw).hexdigest()==key and (expected_sha is None or key==expected_sha),'GROUP_SOURCE_REVIEW_FILE_SHA')
        value=json.loads(raw);validate(value);need(raw==(canonical(value)+'\n').encode(),'GROUP_SOURCE_REVIEW_CANONICAL')
        return SourceReviewEvidence(role,key,key,len(raw),raw)


def _prefix(original,current):
    need(original['semantic_scope_sha']==current['semantic_scope_sha'] and original['original_user_scope']==current['original_user_scope']
         and original['role_threads']==current['role_threads'] and original['allowed_read_scope']==current['allowed_read_scope'],'GROUP_SOURCE_REVIEW_SCOPE_CHANGED')
    old_windows={w['source_id']:w for w in original['source_windows']};new_windows={w['source_id']:w for w in current['source_windows']}
    need(set(old_windows)==set(new_windows),'GROUP_SOURCE_REVIEW_ROLE_CHANGED')
    for sid,old in old_windows.items():
        new=new_windows[sid]
        for key in ('thread_id','path_utf8_sha256','device','inode','start_offset','start_ordinal','metadata_ordinal','preceding_sha256','session_meta_sha256'):
            need(old[key]==new[key],'GROUP_SOURCE_REVIEW_ORIGINAL_CHANGED')
        need(new['prefix_bytes']>=old['prefix_bytes'],'GROUP_SOURCE_REVIEW_TRUNCATED')
    for key in ('retained_bindings','reviewed_other_records','typed_raw_pairs'):
        need(all(item in current[key] for item in original[key]),'GROUP_SOURCE_REVIEW_PREFIX_CHANGED')
    need(original['qa_sources']==current['qa_sources'],'GROUP_SOURCE_REVIEW_QA_CHANGED')
    old_pairs={canonical(p['human']) for p in original['typed_raw_pairs']};known=[]
    for pair in current['typed_raw_pairs']:
        if canonical(pair['human']) not in old_pairs:
            need(pair['disposition']!='ORIGINAL_REQUEST','GROUP_SOURCE_REVIEW_SCOPE_CHANGED')
            known.append({'human':pair['human'],'disposition':pair['disposition']})
    return known


def _events(db):
    # Old ordinary/Family-only histories do not acquire a new Owned dependency.
    # Every matching namespace, including unknown versions, still takes the
    # original complete replay and transaction-lifetime checks below.
    rows=db.execute("SELECT payload FROM group_events WHERE kind='PREVIEW'").fetchall()
    for row in rows:
        payload=json.loads(row[0]);candidate=payload.get('candidate') if type(payload) is dict else None
        profile=candidate.get('profile') if type(candidate) is dict else None
        if type(profile) is str and profile.startswith('GROUP_CURRENT_SOURCE_REVIEW'):break
    else:return []
    from .draft_group_source_facts import _events as actual
    return [e for e in actual(db) if e['kind']=='PREVIEW' and type(e['payload'].get('candidate')) is dict
        and type(e['payload']['candidate'].get('profile')) is str and e['payload']['candidate']['profile'].startswith('GROUP_CURRENT_SOURCE_REVIEW')]


def _replay_values_in(db,policy,events=None):
    from .draft_group_read_family_store import _history_file_guard
    from .draft_group_input_files import InputFiles
    from .draft_group_host_history import _materials
    files=SourceReviewFiles(policy,lambda:_history_file_guard(policy));inputs=InputFiles(policy,lambda:_history_file_guard(policy))
    heads={};by_sha={}
    selected=_events(db) if events is None else [e for e in events if e['kind']=='PREVIEW' and type(e['payload'].get('candidate')) is dict
        and type(e['payload']['candidate'].get('profile')) is str and e['payload']['candidate']['profile'].startswith('GROUP_CURRENT_SOURCE_REVIEW')]
    for event in selected:
        payload=event['payload'];c=validate(payload['candidate']);key=payload['evidence_sha']
        proof=files.read('source_review',key)
        need(proof.value==c and payload['preview_id']==payload['request_key']=='group-source-review-'+key
             and payload['input_sha']==c['current_source_material_sha'] and payload['scope_sha']==c['semantic_scope_sha'],'GROUP_SOURCE_REVIEW_WRAPPER')
        family=c['family_id'];previous=heads.get(family)
        need(c['previous_review_sha']==(None if previous is None else previous),'GROUP_SOURCE_REVIEW_FORK')
        from .draft_group_operator_source_codec import SOURCE_REVIEW_PROFILE
        if c['profile'] in (SOURCE_REVIEW_PROFILE,time06.SOURCE_REVIEW_PROFILE_V2):
            from .draft_group_operator_review import validate_history_in
            validate_history_in(db,policy,c,events=events,previous=None if previous is None else by_sha[previous])
            heads[family]=key;by_sha[key]=c
            continue
        if previous is not None:
            need(by_sha[previous]['profile'] not in (SOURCE_REVIEW_PROFILE,time06.SOURCE_REVIEW_PROFILE_V2),'GROUP_SOURCE_REVIEW_MODE_CHANGED')
        if c['profile']==PROFILE_V2:
            _validate_source_review_v2_history_in(db,policy,c,events=events,previous=None if previous is None else by_sha[previous])
            heads[family]=key;by_sha[key]=c
            continue
        if previous is not None:need(by_sha[previous]['profile']!=PROFILE_V2,'GROUP_SOURCE_REVIEW_VERSION_DOWNGRADE')
        old=inputs.read('source',c['original_source_material_sha']).value;new=inputs.read('source',c['current_source_material_sha']).value
        need(_prefix(old,new)==c['known_user_classifications'] and digest(old['original_user_scope']['human_refs'])==c['original_human_refs_sha'],'GROUP_SOURCE_REVIEW_PREFIX_CHANGED')
        need(old['semantic_scope_sha']==c['semantic_scope_sha'],'GROUP_SOURCE_REVIEW_SCOPE_CHANGED')
        reg=inputs.read('registration',c['registration_sha'])
        need(reg.value['family_id']==family and reg.value['source_material_sha']==c['original_source_material_sha'],'GROUP_SOURCE_REVIEW_REGISTRATION')
        # The accepted helper locator is fixed by reviewed compiled code. Its
        # current source bytes must be exactly the continuation's new material.
        from .group_host_jobs import FIXED_JOB_TABLE
        rows=[r for r in FIXED_JOB_TABLE if dict(r[3])['review'][1]==c['helper_acceptance_sha'] and dict(r[3])['source'][1]==c['current_source_material_sha']]
        need(len(rows)==1,'GROUP_SOURCE_REVIEW_ACCEPTANCE_REQUIRED')
        _,_,config,semantic,_=_materials(policy,dict(rows[0][3])['configuration'][1])
        need(digest(semantic['original_human_refs'])==c['original_human_refs_sha'],'GROUP_SOURCE_REVIEW_HUMAN_CHANGED')
        if previous is not None:
            prior=by_sha[previous]
            need(prior['registration_sha']==c['registration_sha'] and prior['original_source_material_sha']==c['original_source_material_sha']
                 and prior['semantic_scope_sha']==c['semantic_scope_sha'],'GROUP_SOURCE_REVIEW_CHAIN_CHANGED')
        heads[family]=key;by_sha[key]=c
    return heads,by_sha


def _replay(db,policy):
    return _replay_values_in(db,policy)


def check_source_review_records_in(db,states,history_policy):
    if not _events(db):return
    from .own_connection_policy import ConnectionPolicy
    need(type(history_policy) is ConnectionPolicy,'GROUP_SOURCE_REVIEW_HISTORY_POLICY')
    _replay(db,history_policy)


def validate_source_review_binding_in(db,policy,review_sha,registration_sha,current_source_sha,original_scope_sha):
    heads,by_sha=_replay(db,policy);c=by_sha.get(review_sha)
    need(c is not None and heads[c['family_id']]==review_sha and c['registration_sha']==registration_sha
         and c['current_source_material_sha']==current_source_sha and c['semantic_scope_sha']==original_scope_sha,'GROUP_SOURCE_REVIEW_CURRENT_CHAIN')
    return c


def validate_source_review_binding_from_replay_in(db,policy,review_sha,registration_sha,current_source_sha,original_scope_sha,states,events):
    from .draft_group_host_history import _context
    from .draft_group_response_history import verify_group_replay_inputs_in
    _context(db,policy);verify_group_replay_inputs_in(db,states,events)
    heads,by_sha=_replay_values_in(db,policy,events);c=by_sha.get(review_sha)
    need(c is not None and heads[c['family_id']]==review_sha and c['registration_sha']==registration_sha
         and c['current_source_material_sha']==current_source_sha and c['semantic_scope_sha']==original_scope_sha,'GROUP_SOURCE_REVIEW_CURRENT_CHAIN')
    return c


def _review_for_original_fact(events,source_info,by_sha,source_fact):
    """Pure causal selection after complete physical review-chain validation."""
    from .draft_group_source_facts import validate_source_fact,PROFILE as FACTS_V1,PROFILE_V2 as FACTS_V2
    fact=validate_source_fact(source_fact)
    actual=[item for item in source_info['by_event'].values()
            if item['candidate']['fact_id']==fact['fact_id']]
    need(len(actual)==1 and canonical(actual[0]['candidate'])==canonical(fact),
         'GROUP_SOURCE_REVIEW_ORIGINAL_FACT_REQUIRED')
    locator=actual[0]['locator'];review_sha=fact['current_source_review_sha']
    if review_sha is None:
        need(fact['profile']==FACTS_V1,'GROUP_SOURCE_REVIEW_REQUIRED')
        return None
    c=by_sha.get(review_sha)
    need(c is not None and c['registration_sha']==fact['registration_sha']
         and c['family_id']==fact['family_id']
         and c['current_source_material_sha']==fact['source_material_sha'], 'GROUP_SOURCE_REVIEW_ORIGINAL_BINDING')
    matching=[e for e in events if e['kind']=='PREVIEW' and e['payload'].get('evidence_sha')==review_sha
              and canonical(e['payload'].get('candidate'))==canonical(c)]
    need(len(matching)==1,'GROUP_SOURCE_REVIEW_ORIGINAL_EVENT_REQUIRED')
    event=matching[0]
    need(event['account_key']==locator['account_key']==fact['binding_sha']
         and event['payload'].get('binding_sha')==fact['binding_sha']
         and type(event['seq']) is int and event['seq']<locator['event_seq'],
         'GROUP_SOURCE_REVIEW_FACT_CHRONOLOGY')
    if fact['profile']==FACTS_V2:
        need(c['profile']==PROFILE_V2,'GROUP_SOURCE_REVIEW_VERSION_BINDING')
        witness=c['current_binding'];descriptor=fact['source_descriptor']
        for key,target in (('configuration_sha','configuration_sha'),('native_contract_sha256','native_contract_sha'),
                           ('permission_facts_sha256','permission_facts_sha'),
                           ('runtime_source_policy_sha','runtime_source_policy_sha')):
            need(descriptor[key]==witness[target],'GROUP_SOURCE_REVIEW_FACT_WITNESS')
        need(descriptor['current_binding_sha']==c['current_binding_sha']==digest(witness)
             and fact['source_observation_sha']==witness['source_observation_sha']
             and fact['qualification_generation_sha']==witness['qualification_generation_sha']
             and fact['host_acceptance_sha']==witness['baseline_acceptance_sha']
             and witness['capture_started_at_ms']<fact['qualified_not_after_ms']<=witness['qualified_not_after_ms'],
             'GROUP_SOURCE_REVIEW_FACT_WITNESS')
    elif fact['profile']=='GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1':
        from .draft_group_operator_source_codec import SOURCE_REVIEW_PROFILE,validate_descriptor
        need(c['profile']==SOURCE_REVIEW_PROFILE,'GROUP_SOURCE_REVIEW_VERSION_BINDING')
        witness=c['current_binding'];descriptor=validate_descriptor(fact['source_descriptor'])
        need(descriptor['configuration_sha']==c['configuration_sha']
             and descriptor['semantic_adoption_sha']==c['semantic_adoption_sha']
             and descriptor['current_binding_sha']==c['current_binding_sha']==digest(witness)
             and descriptor['runtime_source_policy_sha']==c['runtime_source_policy_sha']
             and descriptor['selection_sha']==witness['selection_sha']
             and descriptor['qa_adoption_sha']==witness['qa_set_sha']
             and descriptor['postupload_mapping_sha']==witness['postupload_mapping_sha']
             and descriptor['prepared_relations_sha']==witness['prepared_relations_sha']
             and descriptor['operator_request_set_sha']==witness['original_request_set_sha']
             and fact['source_observation_sha']==digest(witness)
             and fact['qualification_generation_sha']==witness['proof_generation_sha']
             and fact['host_acceptance_sha']==c['helper_acceptance_sha']
             and witness['observed_at_ms']<fact['qualified_not_after_ms']<=witness['qualified_not_after_ms'],
             'GROUP_SOURCE_REVIEW_FACT_WITNESS')
    elif fact['profile']==time06.SOURCE_FACTS_PROFILE_V2:
        need(c['profile']==time06.SOURCE_REVIEW_PROFILE_V2,'GROUP_SOURCE_REVIEW_VERSION_BINDING')
        witness=c['current_binding']
        try:descriptor=time06.validate_descriptor_v2(fact['source_descriptor'])
        except (time06.old.OperatorSourceCodecError,time06.OperatorTimeCodecError):
            hold('GROUP_SOURCE_REVIEW_FACT_WITNESS')
        need(descriptor['configuration_sha']==c['configuration_sha']
             and descriptor['semantic_adoption_sha']==c['semantic_adoption_sha']
             and descriptor['current_binding_sha']==c['current_binding_sha']==digest(witness)
             and descriptor['runtime_source_policy_sha']==c['runtime_source_policy_sha']
             and descriptor['selection_sha']==witness['selection_sha']
             and descriptor['qa_adoption_sha']==witness['qa_set_sha']
             and descriptor['postupload_mapping_sha']==witness['postupload_mapping_sha']
             and descriptor['prepared_relations_sha']==witness['prepared_relations_sha']
             and descriptor['operator_request_set_sha']==witness['original_request_set_sha']
             and fact['source_observation_sha']==digest(witness)
             and fact['qualification_generation_sha']==witness['proof_generation_sha']
             and fact['host_acceptance_sha']==c['helper_acceptance_sha']
             and witness['observed_at_ms']<fact['qualified_not_after_ms']<=witness['qualified_not_after_ms'],
             'GROUP_SOURCE_REVIEW_FACT_WITNESS')
    return c


def validate_source_review_binding_for_fact_from_replay_in(db,policy,source_fact,states,events):
    """Historical facts only: original event ordering plus complete file chain.

    This may return an earlier validated Review while later reviews remain in
    the same linear chain. It never restores a live binding/current authority.
    The separate bare-review live leaf above still requires the current head.
    """
    from .draft_group_host_history import _context
    from .draft_group_response_history import verify_group_replay_inputs_in
    from .draft_group_source_facts import replay_source_facts
    _context(db,policy);verify_group_replay_inputs_in(db,states,events)
    info=replay_source_facts(events)
    _,by_sha=_replay_values_in(db,policy,events)
    value=_review_for_original_fact(events,info,by_sha,source_fact)
    verify_group_replay_inputs_in(db,states,events)
    return value


def source_review_before_event_in(db,account,kind,payload):
    c=payload.get('candidate') if type(payload) is dict and kind=='PREVIEW' else None
    profile=c.get('profile') if type(c) is dict else None
    if type(profile) is not str or not profile.startswith('GROUP_CURRENT_SOURCE_REVIEW'):return
    validate(c)
    from .draft_group_operator_source_codec import SOURCE_REVIEW_PROFILE
    if c['profile'] in (SOURCE_REVIEW_PROFILE,time06.SOURCE_REVIEW_PROFILE_V2):
        from .draft_group_operator_review import before_event_in
        return before_event_in(db,account,kind,payload)
    if c['profile']==PROFILE_V2:
        return _source_review_v2_before_event_in(db,account,kind,payload)
    scope=_SCOPE.get()
    need(scope is not None and _ISSUED.get(id(scope)) is scope and scope[0] is db and scope[1].entry.thread==threading.get_ident()
         and scope[2]==canonical(c) and scope[3]==_transaction_marker(db),'GROUP_SOURCE_REVIEW_ADMISSION_REQUIRED')
    scope[1].current_no_token_in(None,scope[1]._source, history_locators=None)
    heads,_=_replay(db,scope[1].entry.policy)
    need(c['previous_review_sha']==heads.get(c['family_id']),'GROUP_SOURCE_REVIEW_FORK')


def source_review_after_event_in(db,**kwargs):
    candidate=kwargs.get('payload',{}).get('candidate') if type(kwargs.get('payload')) is dict else None
    from .draft_group_operator_source_codec import SOURCE_REVIEW_PROFILE
    if type(candidate) is dict and candidate.get('profile') in (SOURCE_REVIEW_PROFILE,time06.SOURCE_REVIEW_PROFILE_V2):
        from .draft_group_operator_review import after_event_in
        return after_event_in(db,**kwargs)
    if type(candidate) is dict and candidate.get('profile')==PROFILE_V2:
        return _source_review_v2_after_event_in(db,**kwargs)
    scope=_SCOPE.get()
    if scope is not None:_replay(db,scope[1].entry.policy)


def qualify_source_review_fixed(host,db,registration_evidence,original_source_evidence, *, history_locators=None):
    """Same fixed current helper and real source; 0 token/platform/permissions."""
    from .draft_group_store import GroupStore
    from .draft_group_input_files import InputFiles
    from .draft_group_runtime_host import _TIME
    from .draft_group_operator_source_codec import SOURCE_PROFILE
    if host.chain.source.get('profile')==SOURCE_PROFILE:
        from .draft_group_operator_review import qualify_review_in
        return qualify_review_in(host,db,registration_evidence,original_source_evidence,history_locators=history_locators)
    if host.chain.source.get('profile')=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
        return _qualify_source_review_v2_fixed(host,db,registration_evidence,original_source_evidence, history_locators=history_locators)
    host.current_no_token_in(None,host._source, history_locators=None)
    need(type(registration_evidence) is FileEvidence and registration_evidence.role=='registration'
         and type(original_source_evidence) is FileEvidence and original_source_evidence.role=='source','GROUP_SOURCE_REVIEW_INPUT')
    inputs=InputFiles(host.entry.policy,host.entry.full_guard)
    need(inputs.read('registration',registration_evidence.key)==registration_evidence
         and inputs.read('source',original_source_evidence.key)==original_source_evidence,'GROUP_SOURCE_REVIEW_INPUT')
    reg=registration_evidence.value;old=original_source_evidence.value;current=host.chain.source
    need(reg['source_material_sha']==original_source_evidence.sha256,'GROUP_SOURCE_REVIEW_ORIGINAL')
    known=_prefix(old,current);heads,_=_replay(db,host.entry.policy)
    facts=host.observer.inspect(host.chain.files['source'].raw).value
    candidate={'schema':1,'profile':PROFILE,'authority':False,'family_id':reg['family_id'],'registration_sha':registration_evidence.sha256,
        'semantic_scope_sha':old['semantic_scope_sha'],'original_source_material_sha':original_source_evidence.sha256,
        'current_source_material_sha':host.pins.source_sha,'previous_review_sha':heads.get(reg['family_id']),
        'helper_acceptance_sha':host.pins.review_sha,'original_human_refs_sha':digest(old['original_user_scope']['human_refs']),
        'known_user_classifications':known,'qualification_generation_sha':digest(facts['sources']),
        'observed_at_ms':int(_TIME()*1000),'not_after_ms':int(host._source.not_after*1000)}
    files=SourceReviewFiles(host.entry.policy,host.entry.full_guard);proof=files.publish('source_review',candidate)
    need(files.read('source_review',proof.key)==proof,'GROUP_SOURCE_REVIEW_READBACK')
    need(inputs.read('source',host.pins.source_sha).raw==host.chain.files['source'].raw,'GROUP_SOURCE_REVIEW_CURRENT_NOT_PUBLISHED')
    binding=digest(host.chain.config['binding']);identity='group-source-review-'+proof.sha256
    scope=(db,host,canonical(candidate),_transaction_marker(db));_ISSUED[id(scope)]=scope;token=_SCOPE.set(scope)
    if not hasattr(host.entry,'review_candidates'):host.entry.review_candidates={}
    host.entry.review_candidates[digest(candidate)]=(db,canonical(candidate))
    try:
        GroupStore(binding,_history_partial(host.verify_in, history_locators=history_locators)).register_preview_in(db,identity,source_kind=host.chain.config['binding']['source_kind'],
            input_sha=host.pins.source_sha,request_key=identity,scope_sha=old['semantic_scope_sha'],candidate=candidate,evidence_sha=proof.sha256, history_locators=history_locators)
    finally:_SCOPE.reset(token);_ISSUED.pop(id(scope),None)
    return proof


def _native_materials(db,policy,candidate,*,states=None,events=None,host=None):
    from types import FunctionType
    from . import draft_group_host_review as actual
    reader=getattr(actual,'read_native_v2_review_materials_in',None)
    material_type=getattr(actual,'NativeV2ReviewHistoryMaterials',None)
    need(type(reader) is FunctionType and type(material_type) is type,
         'GROUP_NATIVE_V2_HISTORY_READER_REQUIRED')
    value=reader(db,policy,candidate,states=states,events=events,host=host)
    need(type(value) is material_type and value.authority is False,
         'GROUP_NATIVE_V2_HISTORY_MATERIALS_REQUIRED')
    return value


def _material_values(materials):
    from .draft_group_native_v2_codec import decode_baseline,decode_runtime_policy,decode_policy_acceptance
    baseline=decode_baseline(materials.baseline_raw)
    policy=decode_runtime_policy(materials.policy_raw)
    acceptance=decode_policy_acceptance(materials.acceptance_raw)
    origin=decode('source',materials.origin_raw)
    need(sha256(materials.baseline_raw).hexdigest()==materials.source_sha==policy['baseline_source_sha']
         and sha256(materials.policy_raw).hexdigest()==acceptance['runtime_source_policy_sha']
         and sha256(materials.acceptance_raw).hexdigest()==materials.acceptance_sha
         and sha256(materials.origin_raw).hexdigest()==policy['origin_source_descriptor']['sha256']
         and len(materials.origin_raw)==policy['origin_source_descriptor']['size']
         and origin['profile']==policy['origin_source_descriptor']['source_profile'], 'GROUP_NATIVE_V2_MATERIAL_BINDING')
    need(acceptance['source_material_sha']==materials.source_sha
         and acceptance['configuration_sha']==materials.configuration_sha
         and acceptance['semantic_adoption_sha']==materials.semantic_adoption_sha
         and acceptance['native_contract_sha']==policy['native_contract_sha']
         ==baseline['stream_contract']['interpreter_contract_sha256'], 'GROUP_NATIVE_V2_ACCEPTANCE_BINDING')
    for key in ('semantic_scope_sha','original_user_scope','role_threads','allowed_read_scope','expires_policy','qa_sources'):
        need(canonical(origin[key])==canonical(baseline[key]),'GROUP_NATIVE_V2_ORIGINAL_SCOPE_CHANGED')
    # Preserve every original authority-bearing whole binding and exact pair.
    for pair in origin['typed_raw_pairs']:
        need(pair in baseline['typed_raw_pairs'],'GROUP_NATIVE_V2_ORIGINAL_USER_PAIR_CHANGED')
    whole={'USER_RAW','USER_TYPED','SESSION_META','TASK_CONTROL','CONFIG_NON_AUTH','QA_FACT'}
    for item in origin['retained_bindings']:
        if item['category'] in whole:
            need(item in baseline['retained_bindings'],'GROUP_NATIVE_V2_ORIGINAL_BINDING_CHANGED')
    if origin['profile']=='GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1':
        identities={x['source_id']:x for x in baseline['source_identities']}
        starts={x['source_id']:x['reference'] for x in baseline['interpretation_starts']}
        need(set(identities)=={x['source_id'] for x in origin['source_windows']},'GROUP_NATIVE_V2_ORIGIN_SOURCES')
        for window in origin['source_windows']:
            identity=identities[window['source_id']];start=starts[window['source_id']]
            for key in ('source_id','thread_id','path_utf8_sha256','device','inode','metadata_ordinal','session_meta_sha256'):
                need(window[key]==identity[key],'GROUP_NATIVE_V2_ORIGIN_IDENTITY')
            need(window['start_offset']==start['byte_start'] and window['start_ordinal']==start['ordinal'],
                 'GROUP_NATIVE_V2_ORIGIN_START')
    else:
        for key in ('source_identities','interpretation_starts','selected_assistant_pairs','stream_contract'):
            need(canonical(origin[key])==canonical(baseline[key]),'GROUP_NATIVE_V2_BASELINE_CHANGED')
    artifacts={item[1] for item in acceptance['helper_dependencies']}
    need(all(item['review_artifact_sha'] in artifacts for item in policy['known_user_reviews']),
         'GROUP_NATIVE_V2_USER_REVIEW_ARTIFACT_REQUIRED')
    materials.files.collective_fence()
    return baseline,policy,acceptance,origin


def _prefix_expectations(baseline,origin,origin_sha,previous,previous_sha):
    values=[]
    for item in baseline['baseline_commitments']:
        values.append({'source_id':item['source_id'],'baseline_kind':'M0_EXPECTATION',
            'baseline_locator_sha':sha256((canonical(baseline)+'\n').encode()).hexdigest(),'baseline_end':item['end_byte'],
            'baseline_prefix_sha256':item['prefix_sha256'],'baseline_ordered_sha256':item['ordered_records_sha256'],
            'baseline_control_sha256':item['control_sha256'],'absolute_end_ordinal':item['absolute_end_ordinal']})
    if origin['profile']=='GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1':
        for item in origin['source_windows']:
            values.append({'source_id':item['source_id'],'baseline_kind':'ORIGIN_V1_MATERIAL',
                'baseline_locator_sha':origin_sha,'baseline_end':item['prefix_bytes'],
                'baseline_prefix_sha256':item['prefix_sha256'],'baseline_ordered_sha256':None,
                'baseline_control_sha256':None,'absolute_end_ordinal':None})
    if previous is not None:
        if previous['profile']==PROFILE_V2:
            for item in previous['current_binding']['sources']:
                values.append({'source_id':item['source_id'],'baseline_kind':'PREVIOUS_REVIEW',
                    'baseline_locator_sha':previous_sha,'baseline_end':item['prefix_bytes'],
                    'baseline_prefix_sha256':item['prefix_sha256'],'baseline_ordered_sha256':item['ordered_records_sha256'],
                    'baseline_control_sha256':item['control_sha256'],'absolute_end_ordinal':item['end_ordinal_exclusive']})
        else:
            # A V1 review's exact current material is additionally read by the
            # fixed origin/material leaf. No nil/hash-only upgrade is allowed.
            need(previous['current_source_material_sha']==origin_sha,'GROUP_NATIVE_V2_V1_REVIEW_BRIDGE_REQUIRED')
    return values


def validate_native_v2_prefix_proofs(expectations,sources):
    from .draft_group_native_v2_codec import validate_prefix_proof
    _plain(expectations);_plain(sources)
    need(type(expectations) is list and len(expectations)<=256,'GROUP_NATIVE_V2_PREFIX_LIMIT')
    by_id={item['source_id']:item for item in sources};proofs=[]
    keys=('source_id','baseline_kind','baseline_locator_sha','baseline_end','baseline_prefix_sha256',
          'baseline_ordered_sha256','baseline_control_sha256','absolute_end_ordinal')
    for item in expectations:
        _closed(item,keys);need(item['source_id'] in by_id,'GROUP_NATIVE_V2_PREFIX_SOURCE')
        matches=[x for x in by_id[item['source_id']]['checkpoints'] if x['end']==item['baseline_end']]
        need(len(matches)==1,'GROUP_NATIVE_V2_PREFIX_CHECKPOINT_REQUIRED')
        checkpoint=matches[0]
        if item['absolute_end_ordinal'] is not None:
            need(checkpoint['absolute_end_ordinal']==item['absolute_end_ordinal'],'GROUP_NATIVE_V2_PREFIX_ORDINAL')
        proof={k:v for k,v in item.items() if k!='absolute_end_ordinal'}
        proof['current_checkpoint']=checkpoint;validate_prefix_proof(proof);proofs.append(proof)
    return proofs


def collect_native_v2_prefix_proofs_in(host,db,states,events,materials):
    from .draft_group_response_history import verify_group_replay_inputs_in
    from .draft_group_source_facts import replay_source_facts
    from .draft_group_host_history import validate_source_fact_history_from_replay_in
    verify_group_replay_inputs_in(db,states,events)
    baseline,policy,acceptance,origin=_material_values(materials)
    info=replay_source_facts(events)
    for item in info['locators'].values():
        candidate=item['candidate']
        if candidate['binding_sha']==digest(host.chain.config['binding']):
            validate_source_fact_history_from_replay_in(db,candidate,host.entry.policy,states,events)
    heads,by_sha=_replay_values_in(db,host.entry.policy,events)
    family=baseline['allowed_read_scope']['family_anchor_sha'];previous_sha=heads.get(family)
    previous=None if previous_sha is None else by_sha[previous_sha]
    values=_prefix_expectations(baseline,origin,policy['origin_source_descriptor']['sha256'],previous,previous_sha)
    materials.files.collective_fence();verify_group_replay_inputs_in(db,states,events)
    return values


def _validate_source_review_v2_history_in(db,policy,candidate,*,events=None,previous=None):
    from .draft_group_response_history import (read_group_replay_snapshot_in,release_group_replay_snapshot_in)
    from .draft_group_native_v2_codec import validate_source_review
    c=validate_source_review(candidate)
    states,actual=read_group_replay_snapshot_in(db)
    try:
        if events is not None:
            need(canonical(events)==canonical(actual),'GROUP_NATIVE_V2_HISTORY_EVENTS_CHANGED')
        materials=_native_materials(db,policy,c,states=states,events=actual)
        from .draft_group_host_native_v2 import material_scope
        with material_scope(materials):
            baseline,runtime,acceptance,origin=_material_values(materials)
            witness=c['current_binding']
            need(c['current_source_material_sha']==materials.source_sha
                 and c['original_source_material_sha']==runtime['origin_source_descriptor']['sha256']
                 and c['helper_acceptance_sha']==materials.acceptance_sha
                 and c['runtime_source_policy_sha']==acceptance['runtime_source_policy_sha']
                 and witness['configuration_sha']==materials.configuration_sha
                 and witness['native_contract_sha']==runtime['native_contract_sha'],'GROUP_NATIVE_V2_REVIEW_MATERIAL_CHANGED')
            from .draft_group_input_files import InputFiles
            from .draft_group_read_family_store import _history_file_guard
            inputs=InputFiles(policy,lambda:_history_file_guard(policy))
            registration,registration_pin=inputs._entry('registration',c['registration_sha'])
            need(registration.value['family_id']==c['family_id']
                 and registration.value['source_material_sha']==c['original_source_material_sha'], 'GROUP_NATIVE_V2_REVIEW_REGISTRATION')
            need(c['original_human_refs_sha']==digest(origin['original_user_scope']['human_refs']),
                 'GROUP_NATIVE_V2_REVIEW_HUMAN_CHANGED')
            expected=_prefix_expectations(baseline,origin,c['original_source_material_sha'],previous,c['previous_review_sha'])
            proofs=validate_native_v2_prefix_proofs(expected,witness['sources'])
            need(canonical(proofs)==canonical(witness['prefix_proofs']), 'GROUP_NATIVE_V2_REVIEW_PREFIX_CHANGED')
            known=[{'human':x['human'],'disposition':x['disposition']} for x in runtime['known_user_reviews']]
            need(canonical(known)==canonical(c['known_user_classifications'])
                 and witness['reviewed_delta_sha']==digest(runtime['known_user_reviews']), 'GROUP_NATIVE_V2_REVIEW_CLASSIFICATIONS')
            if previous is not None:
                for key in ('family_id','registration_sha','original_source_material_sha','semantic_scope_sha'):
                    need(previous[key]==c[key],'GROUP_NATIVE_V2_REVIEW_CHAIN_CHANGED')
            inputs._pure_entries((('registration',registration.key,registration_pin),))
            materials.files.collective_fence()
            return c
    finally:release_group_replay_snapshot_in(db,states,actual)


# These receipts are local pipeline state, never effect owners or public wire.
from dataclasses import replace as _replace
from weakref import WeakKeyDictionary as _WeakKeyDictionary
_V2_SCOPE=ContextVar('fixed_group_source_review_v2_append',default=None)
_V2_FRESH=ContextVar('fixed_group_source_review_v2_fresh_ro',default=None)
_V2_RECEIPTS=_WeakKeyDictionary()
_V2_PENDING=_WeakKeyDictionary()


class _ReviewV2Receipt:
    __slots__=('__weakref__',)
    def __new__(cls,*args,**kwargs):hold('GROUP_SOURCE_REVIEW_PRIVATE_RECEIPT_REQUIRED')


@dataclass(frozen=True)
class _ReviewV2Facts:
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


def _v2_receipt(host,binding,receipt=None):
    value=_V2_PENDING.get(binding) if receipt is None else receipt
    need(type(value) is _ReviewV2Receipt,'GROUP_SOURCE_REVIEW_RECEIPT_REQUIRED')
    facts=_V2_RECEIPTS.get(value)
    need(facts is not None and facts.host is host and facts.binding is binding
         and _V2_PENDING.get(binding) is value and facts.thread==threading.get_ident(),
         'GROUP_SOURCE_REVIEW_RECEIPT_UNISSUED')
    return value,facts


def validate_source_review_v2_phase_receipt(host,binding,phase,receipt):
    value,facts=_v2_receipt(host,binding,receipt)
    if phase=='REVIEW_PENDING':
        need(facts.status=='PREPARED' and type(facts.writer) is OwnedConnection
             and _transaction_marker(facts.writer)==facts.writer_epoch,'GROUP_SOURCE_REVIEW_PREPARED_REQUIRED')
    elif phase in ('REVIEW_COMMITTED','ADMISSION_READY'):
        fresh=_V2_FRESH.get()
        need(facts.status=='READBACKED' and fresh is not None and fresh[0] is facts.readback_db
             and fresh[1] is binding and fresh[2]==facts.proof.sha256
             and type(facts.readback_db) is OwnedConnection and facts.readback_db is not facts.writer
             and _transaction_marker(facts.readback_db)==facts.readback_epoch,
             'GROUP_SOURCE_REVIEW_NORMAL_COMMIT_FRESH_OWNED_REQUIRED')
    else:hold('GROUP_SOURCE_REVIEW_PHASE_INVALID')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return value


def validate_source_review_v2_append_scope(host,db,candidate):
    from .draft_group_native_v2_runtime import validate_current_source_binding
    scope=_V2_SCOPE.get()
    need(scope is not None and type(scope) is _ReviewV2Receipt,'GROUP_SOURCE_REVIEW_ADMISSION_REQUIRED')
    facts=_V2_RECEIPTS.get(scope)
    need(facts is not None and facts.host is host and facts.writer is db
         and type(db) is OwnedConnection and _transaction_marker(db)==facts.writer_epoch
         and facts.thread==threading.get_ident() and facts.candidate_raw==canonical(candidate)
         and facts.status in ('PREPARED','APPENDED'),'GROUP_SOURCE_REVIEW_ADMISSION_REQUIRED')
    validate_current_source_binding(host,facts.binding,required_phase='REVIEW_PENDING')
    need(getattr(host,'_active_group_token',None) is None,'GROUP_SOURCE_REVIEW_LOCAL_NO_TOKEN_REQUIRED')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return scope


def _source_review_v2_before_event_in(db,account,kind,payload):
    scope=_V2_SCOPE.get();facts=None if scope is None else _V2_RECEIPTS.get(scope)
    need(facts is not None,'GROUP_SOURCE_REVIEW_ADMISSION_REQUIRED')
    validate_source_review_v2_append_scope(facts.host,db,payload['candidate'])
    need(account==digest(facts.host.chain.config['binding']) and kind=='PREVIEW'
         and facts.status=='PREPARED','GROUP_SOURCE_REVIEW_WRAPPER')
    heads,_=_replay(db,facts.host.entry.policy)
    c=payload['candidate']
    need(c['previous_review_sha']==heads.get(c['family_id']),'GROUP_SOURCE_REVIEW_FORK')


def _v2_actual_event(db,account,candidate,review_sha):
    identity='group-source-review-'+review_sha;found=[]
    for row in db.execute('SELECT seq,event_sha,payload FROM group_events WHERE account_key=? AND kind=? ORDER BY seq',(account,'PREVIEW')):
        payload=json.loads(row[2])
        if payload.get('preview_id')==identity or payload.get('request_key')==identity:
            need(payload.get('preview_id')==payload.get('request_key')==identity
                 and payload.get('input_sha')==candidate['current_source_material_sha']
                 and payload.get('scope_sha')==candidate['semantic_scope_sha']
                 and payload.get('evidence_sha')==review_sha
                 and canonical(payload.get('candidate'))==canonical(candidate),'GROUP_SOURCE_REVIEW_WRAPPER')
            found.append((row[0],row[1]))
    need(len(found)==1,'GROUP_SOURCE_REVIEW_ORIGINAL_EVENT_REQUIRED')
    return found[0]


def _source_review_v2_after_event_in(db,**kwargs):
    c=kwargs['payload']['candidate'];scope=_V2_SCOPE.get()
    facts=None if scope is None else _V2_RECEIPTS.get(scope)
    need(facts is not None,'GROUP_SOURCE_REVIEW_ADMISSION_REQUIRED')
    validate_source_review_v2_append_scope(facts.host,db,c)
    need(facts.status=='PREPARED','GROUP_SOURCE_REVIEW_DUPLICATE_APPEND')
    heads,values=_replay(db,facts.host.entry.policy)
    need(heads.get(c['family_id'])==facts.proof.sha256
         and values[facts.proof.sha256]==c,'GROUP_SOURCE_REVIEW_READBACK')
    seq,event_sha=_v2_actual_event(db,digest(facts.host.chain.config['binding']),c,facts.proof.sha256)
    _V2_RECEIPTS[scope]=_replace(facts,status='APPENDED',event_seq=seq,event_sha=event_sha)


def _qualify_source_review_v2_fixed(host,db,registration_evidence,original_source_evidence, *, history_locators=None):
    from .draft_group_native_v2_runtime import (_binding_for_host,current_binding_facts,
        current_binding_observation,advance_current_source_binding)
    from .draft_group_input_files import InputFiles
    from .draft_group_store import GroupStore
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'GROUP_SOURCE_REVIEW_OWNED_REQUIRED')
    binding=_binding_for_host(host,'COMPLETE_SERVICE_NO_ADMISSION')
    need(type(registration_evidence) is FileEvidence and registration_evidence.role=='registration'
         and type(original_source_evidence) is FileEvidence and original_source_evidence.role=='source',
         'GROUP_SOURCE_REVIEW_INPUT')
    inputs=InputFiles(host.entry.policy,host.entry.full_guard)
    registration,registration_pin=inputs._entry('registration',registration_evidence.key)
    origin,origin_pin=inputs._entry('source',original_source_evidence.key)
    need(registration==registration_evidence and origin==original_source_evidence,'GROUP_SOURCE_REVIEW_INPUT')
    reg=registration.value;witness=current_binding_facts(binding);observed=current_binding_observation(host,binding)
    need(reg['source_material_sha']==origin.sha256==witness['origin_source_material_sha']
         and reg['family_id']==host.chain.source['allowed_read_scope']['family_anchor_sha'], 'GROUP_SOURCE_REVIEW_ORIGINAL')
    heads,_=_replay(db,host.entry.policy)
    runtime=host.observer._policy
    candidate={'schema':2,'profile':PROFILE_V2,'authority':False,'family_id':reg['family_id'],
        'registration_sha':registration.sha256,'semantic_scope_sha':witness['semantic_scope_sha'],
        'original_source_material_sha':origin.sha256,'current_source_material_sha':witness['baseline_source_material_sha'],
        'previous_review_sha':heads.get(reg['family_id']),'helper_acceptance_sha':witness['baseline_acceptance_sha'],
        'original_human_refs_sha':digest(origin.value['original_user_scope']['human_refs']),
        'known_user_classifications':[{'human':x['human'],'disposition':x['disposition']} for x in runtime['known_user_reviews']],
        'qualification_generation_sha':witness['qualification_generation_sha'],'observed_at_ms':witness['capture_started_at_ms'],
        'not_after_ms':witness['qualified_not_after_ms'],'binding_mode':witness['binding_mode'],
        'runtime_source_policy_sha':witness['runtime_source_policy_sha'],'current_binding':witness,
        'current_binding_sha':digest(witness),'prefix_preservation_sha':witness['prefix_preservation_sha'],
        'reviewed_delta_sha':witness['reviewed_delta_sha']}
    validate(candidate)
    files=SourceReviewFiles(host.entry.policy,host.entry.full_guard)
    proof,pin=files._publish_observed('source_review',candidate)
    need(files.read('source_review',proof.key)==proof,'GROUP_SOURCE_REVIEW_READBACK')
    inputs._pure_entries((('registration',registration.key,registration_pin),('source',origin.key,origin_pin)))
    need(binding not in _V2_PENDING,'GROUP_SOURCE_REVIEW_ALREADY_PENDING')
    receipt=object.__new__(_ReviewV2Receipt)
    facts=_ReviewV2Facts(host,binding,db,_transaction_marker(db),canonical(candidate),proof,pin,files,
                       threading.get_ident(),'PREPARED')
    _V2_RECEIPTS[receipt]=facts;_V2_PENDING[binding]=receipt
    host.entry.stack.callback(_release_review_v2_receipt,binding,receipt)
    advance_current_source_binding(host,binding,'REVIEW_PENDING',receipt=receipt)
    token=_V2_SCOPE.set(receipt)
    if not hasattr(host.entry,'review_candidates'):host.entry.review_candidates={}
    host.entry.review_candidates[digest(candidate)]=(db,canonical(candidate))
    try:
        identity='group-source-review-'+proof.sha256
        GroupStore(digest(host.chain.config['binding']),_history_partial(host.verify_in, history_locators=history_locators)).register_preview_in(db,identity,
            source_kind=host.chain.config['binding']['source_kind'],input_sha=host.pins.source_sha,
            request_key=identity,scope_sha=witness['semantic_scope_sha'],candidate=candidate,evidence_sha=proof.sha256, history_locators=history_locators)
        _,actual=_v2_receipt(host,binding,receipt)
        need(actual.status=='APPENDED','GROUP_SOURCE_REVIEW_APPEND_UNDETERMINED')
        return proof
    except BaseException:
        _V2_RECEIPTS[receipt]=_replace(_V2_RECEIPTS[receipt],status='APPEND_UNKNOWN')
        raise
    finally:_V2_SCOPE.reset(token)


def commit_source_review_v2_in(host,binding,db,review_sha):
    """Dedicated writer only: original scopes exit, one real normal commit."""
    from .draft_group_native_v2_runtime import validate_current_source_binding,close_current_source_binding
    from .draft_group_read_family_store import _ROOT_CURRENT,_SCOPE as family_scope
    validate_current_source_binding(host,binding,required_phase='REVIEW_PENDING')
    receipt,facts=_v2_receipt(host,binding)
    need(facts.writer is db and facts.proof.sha256==review_sha and facts.status=='APPENDED'
         and type(db) is OwnedConnection and _transaction_marker(db)==facts.writer_epoch
         and _V2_SCOPE.get() is None and _ROOT_CURRENT.get() is None and family_scope.get() is None,
         'GROUP_SOURCE_REVIEW_COMMIT_SCOPE_REQUIRED')
    try:
        OwnedConnection.commit(db)
        need(not db.in_transaction,'GROUP_SOURCE_REVIEW_COMMIT_UNKNOWN')
    except BaseException:
        _V2_RECEIPTS[receipt]=_replace(facts,status='COMMIT_UNKNOWN')
        close_current_source_binding(host,binding)
        hold('GROUP_SOURCE_REVIEW_COMMIT_UNKNOWN')
    _V2_RECEIPTS[receipt]=_replace(facts,status='NORMAL_COMMITTED')
    from .draft_group_runtime_host import cold_history_snapshot_fixed
    try:
        with cold_history_snapshot_fixed(host.entry.policy,host.entry) as (fresh, history_locators):
            token=_V2_FRESH.set((fresh,binding,review_sha))
            try:result=finalize_source_review_v2_in(host,binding,fresh,review_sha)
            finally:_V2_FRESH.reset(token)
        return result
    except BaseException:
        close_current_source_binding(host,binding)
        raise


def finalize_source_review_v2_in(host,binding,db,review_sha):
    from .draft_group_native_v2_runtime import validate_current_source_binding,advance_current_source_binding
    from .draft_group_response_history import (read_group_replay_snapshot_in,release_group_replay_snapshot_in,
                                              verify_group_replay_inputs_in)
    validate_current_source_binding(host,binding,required_phase='REVIEW_PENDING')
    receipt,facts=_v2_receipt(host,binding)
    fresh=_V2_FRESH.get()
    need(fresh is not None and fresh[0] is db and fresh[1] is binding and fresh[2]==review_sha
         and facts.status=='NORMAL_COMMITTED' and facts.proof.sha256==review_sha
         and type(db) is OwnedConnection and db is not facts.writer and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1,'GROUP_SOURCE_REVIEW_FRESH_OWNED_REQUIRED')
    states,events=read_group_replay_snapshot_in(db)
    try:
        heads,values=_replay_values_in(db,host.entry.policy,events)
        c=json.loads(facts.candidate_raw)
        need(heads.get(c['family_id'])==review_sha and values[review_sha]==c,'GROUP_SOURCE_REVIEW_READBACK')
        seq,event_sha=_v2_actual_event(db,digest(host.chain.config['binding']),c,review_sha)
        need(seq==facts.event_seq and event_sha==facts.event_sha,'GROUP_SOURCE_REVIEW_ORIGINAL_EVENT_CHANGED')
        facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
        verify_group_replay_inputs_in(db,states,events)
        _V2_RECEIPTS[receipt]=_replace(facts,status='READBACKED',readback_db=db,readback_epoch=_transaction_marker(db))
        host._current_source_review_sha=review_sha
        advance_current_source_binding(host,binding,'REVIEW_COMMITTED',receipt=receipt)
        advance_current_source_binding(host,binding,'ADMISSION_READY',receipt=receipt)
        return {'state':'SOURCE_REVIEW_COMMITTED_FRESH_OWNED','authority':False,'review_sha':review_sha,
                'event_seq':seq,'event_sha':event_sha}
    finally:release_group_replay_snapshot_in(db,states,events)


def _release_review_v2_receipt(binding,receipt):
    _V2_PENDING.pop(binding,None);_V2_RECEIPTS.pop(receipt,None)


def committed_source_review_sha(host,binding):
    from .draft_group_native_v2_runtime import validate_current_source_binding,current_binding_facts
    validate_current_source_binding(host,binding)
    _,facts=_v2_receipt(host,binding)
    need(facts.status=='READBACKED' and json.loads(facts.candidate_raw)['current_binding_sha']
         ==digest(current_binding_facts(binding)), 'GROUP_SOURCE_REVIEW_COMMITTED_BINDING_REQUIRED')
    facts.files._pure_entries((('source_review',facts.proof.key,facts.proof_pin),))
    return facts.proof.sha256


from functools import partial as _history_partial
