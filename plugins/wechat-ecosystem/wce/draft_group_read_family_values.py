"""Closed FIRST-family integrity values. No source qualification or authority."""
from hashlib import sha256
from .draft_group_contracts import digest
from .draft_group_input_files import (_plain,_closed,_hash,_id,_int,_enum,_binding,_seq,_maybe,hold,_canonical)

ROUTES=('NEW_ONLY_EXISTING_DELEGATION','REPLACEMENT_EXACT_HUMAN')
PURPOSES=('QUALIFY','PREVIEW_ACCOUNT','EXECUTION_INITIAL_ACCOUNT','PROMOTION_ACCOUNT')
PROFILES={'covenant':(2,'GROUP_READ_COVENANT_V2',2*1024*1024),
    'first_proof':(1,'HOST_VERIFIED_GROUP_READ_FIRST_V1',2*1024*1024),
    'family_root':(1,'GROUP_READ_FAMILY_ROOT_V1',2*1024*1024),
    'request_witness':(1,'GROUP_READ_REQUEST_BINDING_V1',16384)}
CAP_KEYS=('LIST','QUALIFY_GET','ACCOUNT_GET','EXECUTION_GET','TOTAL_GET','ADD','DELETE')

def _human(v,*,text=True):
    _closed(v,('thread_id','turn_id','message_id','text_sha256') if text else ('thread_id','turn_id','message_id'))
    for k in ('thread_id','turn_id','message_id'):_id(v[k])
    if text:_hash(v['text_sha256'])

def _owner(v):
    _closed(v,('tenant','principal'));_id(v['tenant']);_id(v['principal'])

def request_identity(platform_account_sha,primary):
    _plain(primary);_human(primary,text=False);_hash(platform_account_sha)
    return digest({'profile':'GROUP_READ_REQUEST_ID_V1','platform_account_sha':platform_account_sha,'primary_human':primary})

def _anchor(v):
    _closed(v,('profile','request_identity_sha','original_human_request_refs','original_text_sha','stable_owner','platform_account_sha','purpose'))
    _enum(v['profile'],('GROUP_READ_FAMILY_ANCHOR_V1',));_enum(v['purpose'],('GROUP08_SAME_REQUEST',))
    for k in ('request_identity_sha','original_text_sha','platform_account_sha'):_hash(v[k])
    _owner(v['stable_owner']);_seq(v['original_human_request_refs'],_human,1,16)
    refs=v['original_human_request_refs'];ids=[{k:x[k] for k in ('thread_id','turn_id','message_id')} for x in refs]
    if len({digest(x) for x in ids})!=len(ids) or request_identity(v['platform_account_sha'],ids[0])!=v['request_identity_sha']:hold()

def family_anchor(value):
    _plain(value)
    from . import draft_group_operator_source_codec as operator
    if type(value) is dict and value.get('profile')==operator.ANCHOR_PROFILE:
        try:return operator.family_anchor(value)
        except operator.OperatorSourceCodecError:hold('GROUP_OPERATOR_FAMILY_VALUE')
    _anchor(value);return digest(value)

def _source_id(family,purpose,ordinal):
    return digest({'profile':'GROUP_READ_PURPOSE_ID_V1','family_id':family,'purpose':purpose,'ordinal':ordinal})

def _slots(v,count,route):
    if type(v) is not list or len(v)!=count:hold()
    seen=set()
    for ordinal,slot in enumerate(v):
        _closed(slot,('ordinal','old_ref_subjects','get_cap','add_cap','delete_cap'))
        if _int(slot['ordinal'])!=ordinal:hold()
        _seq(slot['old_ref_subjects'],_hash,hi=8);n=len(slot['old_ref_subjects'])
        if len(set(slot['old_ref_subjects']))!=n or seen.intersection(slot['old_ref_subjects']):hold()
        seen.update(slot['old_ref_subjects'])
        expected=2 if n==0 else 5 if n==1 else 5*n+2
        if (_int(slot['get_cap'])!=expected or _int(slot['add_cap'])!=1 or _int(slot['delete_cap'])!=n
            or route==ROUTES[0] and n):hold()

def _purpose_values(family,platform,count,subjects,routes):
    # Integrity computation only; direct calls also reject hook-bearing inputs.
    _plain([family,platform,count,subjects,routes]);_hash(family);_hash(platform);_int(count,1,64);_seq(subjects,_hash,hi=8);_seq(routes,lambda x:_enum(x,ROUTES),1,2)
    keys=([('QUALIFY',0)] if subjects else [])+[('PREVIEW_ACCOUNT',0)]
    if ROUTES[1] in routes:keys.append(('EXECUTION_INITIAL_ACCOUNT',0))
    keys.extend(('PROMOTION_ACCOUNT',i) for i in range(1,count))
    out=[]
    for purpose,ordinal in keys:
        qualify=purpose=='QUALIFY'
        if qualify:
            scope={'profile':'GROUP_QUALIFY_SCOPE_V1','family_anchor_id':family,'ordered_subjects':subjects}
            activation={'kind':'FIRST_CURRENT_SCOPE'}
        else:
            permitted=('SNAPSHOT_AND_SAME_GATE_NEW_ONLY' if ROUTES[0] in routes else 'SNAPSHOT_ONLY') if purpose=='PREVIEW_ACCOUNT' else 'EXECUTION_INITIAL_ONLY' if purpose=='EXECUTION_INITIAL_ACCOUNT' else 'PROMOTION_ONLY'
            scope={'profile':'GROUP_ACCOUNT_SCOPE_V1','family_anchor_id':family,'platform_account_sha':platform,'purpose':purpose,'ordinal':ordinal,'count':20,'total_bound':200,'passes':2,'subjects_mode':'DISCOVERY_BOUND_ONCE','permitted_use':permitted}
            if purpose=='PREVIEW_ACCOUNT':activation={'kind':'FIRST_CURRENT_ACCOUNT'}
            elif purpose=='EXECUTION_INITIAL_ACCOUNT':activation={'kind':'EXACT_NEW_SELECTION','route':ROUTES[1],'snapshot_binding':'EXACT_CAPSULE_AND_PREVIEW','one_shot':True}
            else:activation={'kind':'PREVIOUS_CHILD_COMPLETE','previous_ordinal':ordinal-1,'next_ordinal':ordinal,'required_facts':['ACKS','INVALID','FINAL','POOL_CAS']}
        out.append({'purpose':purpose,'ordinal':ordinal,'phase':'QUALIFY' if qualify else 'DISCOVER','source_grant_sha':_source_id(family,purpose,ordinal),'scope':scope,'scope_sha':digest(scope),'list_cap':0 if qualify else 20,'get_cap':len(subjects) if qualify else 200,'activation':activation})
    return out

def _branch_caps(route,slots,q,count):
    coverage=count+(route==ROUTES[1]);execution=sum(x['get_cap'] for x in slots)
    return {'LIST':20*coverage,'QUALIFY_GET':q,'ACCOUNT_GET':200*coverage,'EXECUTION_GET':execution,
        'TOTAL_GET':200*coverage+q+execution,'ADD':len(slots),'DELETE':sum(x['delete_cap'] for x in slots)}

def _caps(v):
    _closed(v,CAP_KEYS)
    for x in v.values():_int(x,0,20000)

def _covenant(v):
    _closed(v,('schema','profile','authority','family_anchor_id','request_identity_sha','platform_account_sha','stable_owner','original_scope_sha','read_contract_sha','source_rights_expiry','child_bound','qualify_subjects','allowed_routes','purposes','branches','worst_case_caps'))
    for k in ('family_anchor_id','request_identity_sha','platform_account_sha','original_scope_sha','read_contract_sha'):_hash(v[k])
    _owner(v['stable_owner']);_closed(v['source_rights_expiry'],('kind','not_after'))
    expiry=v['source_rights_expiry'];_enum(expiry['kind'],('PERSISTENT_DELEGATION','EXPLICIT_UNTIL'))
    if expiry['kind']=='PERSISTENT_DELEGATION':
        if expiry['not_after'] is not None:hold()
    else:_int(expiry['not_after'],1)
    count=_int(v['child_bound'],1,64);subjects=v['qualify_subjects'];_seq(subjects,_hash,hi=8)
    if len(set(subjects))!=len(subjects):hold()
    routes=v['allowed_routes'];_seq(routes,lambda x:_enum(x,ROUTES),1,2)
    if routes!=[x for x in ROUTES if x in routes]:hold()
    expected=_purpose_values(v['family_anchor_id'],v['platform_account_sha'],count,subjects,routes)
    _plain(v['purposes'])
    if _canonical(v['purposes'])!=_canonical(expected):hold()
    if type(v['branches']) is not list or len(v['branches'])!=len(routes):hold()
    for route,branch in zip(routes,v['branches']):
        _closed(branch,('route','execution_slots','coverage_keys','caps'));_enum(branch['route'],ROUTES)
        if branch['route']!=route:hold()
        _slots(branch['execution_slots'],count,route);_caps(branch['caps'])
        keys=[{'purpose':x['purpose'],'ordinal':x['ordinal']} for x in expected if x['purpose']!='QUALIFY' and (route==ROUTES[1] or x['purpose']!='EXECUTION_INITIAL_ACCOUNT')]
        if _canonical(branch['coverage_keys'])!=_canonical(keys) or _canonical(branch['caps'])!=_canonical(_branch_caps(route,branch['execution_slots'],len(subjects),count)):hold()
    _caps(v['worst_case_caps']);worst={k:max(b['caps'][k] for b in v['branches']) for k in CAP_KEYS}
    if _canonical(worst)!=_canonical(v['worst_case_caps']):hold()

def describe_covenant(*,anchor,original_scope_sha,read_contract_sha,source_rights_expiry,branches,qualify_subjects):
    _plain([anchor,source_rights_expiry,branches,qualify_subjects]);_seq(qualify_subjects,_hash,hi=8);family=family_anchor(anchor)
    if type(branches) is not list or not branches:hold()
    routes=[];made=[];count=None
    for b in branches:
        _closed(b,('route','old_ref_subjects'));_enum(b['route'],ROUTES)
        if type(b['old_ref_subjects']) is not list:hold()
        n=len(b['old_ref_subjects']);_int(n,1,64)
        if count is None:count=n
        if count!=n:hold()
        slots=[]
        for i,refs in enumerate(b['old_ref_subjects']):
            _seq(refs,_hash,hi=8);size=len(refs)
            slots.append({'ordinal':i,'old_ref_subjects':refs,'get_cap':2 if size==0 else 5 if size==1 else 5*size+2,'add_cap':1,'delete_cap':size})
        routes.append(b['route']);made.append({'route':b['route'],'execution_slots':slots,'coverage_keys':None,'caps':_branch_caps(b['route'],slots,len(qualify_subjects),n)})
    purposes=_purpose_values(family,anchor['platform_account_sha'],count,qualify_subjects,routes)
    for b in made:b['coverage_keys']=[{'purpose':x['purpose'],'ordinal':x['ordinal']} for x in purposes if x['purpose']!='QUALIFY' and (b['route']==ROUTES[1] or x['purpose']!='EXECUTION_INITIAL_ACCOUNT')]
    v={'schema':2,'profile':PROFILES['covenant'][1],'authority':False,'family_anchor_id':family,'request_identity_sha':anchor['request_identity_sha'],'platform_account_sha':anchor['platform_account_sha'],'stable_owner':anchor['stable_owner'],'original_scope_sha':original_scope_sha,'read_contract_sha':read_contract_sha,'source_rights_expiry':source_rights_expiry,'child_bound':count,'qualify_subjects':qualify_subjects,'allowed_routes':routes,'purposes':purposes,'branches':made,'worst_case_caps':{k:max(b['caps'][k] for b in made) for k in CAP_KEYS}}
    return validate('covenant',v)

def _directory(v):
    _closed(v,('path_utf8_sha256','device','inode','owner_uid'));_hash(v['path_utf8_sha256'])
    for k in ('device','inode','owner_uid'):_int(v[k])

def _coord(v):
    _closed(v,('platform_account_sha','anchor_identity','registry_parent_identity','coordination_pin_sha'))
    _hash(v['platform_account_sha']);_hash(v['coordination_pin_sha'])
    for k in ('anchor_identity','registry_parent_identity'):
        if type(v[k]) is not list or len(v[k])!=2:hold()
        for x in v[k]:_int(x)

def _proof(v):
    _closed(v,('schema','profile','authority','family_anchor_id','request_identity_sha','covenant_sha','original_human_evidence_sha','semantic_review_sha','first_binding','first_directory','coordination','host_provenance','observed_generation_sha','observed_ms','not_after_ms'))
    for k in ('family_anchor_id','request_identity_sha','covenant_sha','original_human_evidence_sha','semantic_review_sha','observed_generation_sha'):_hash(v[k])
    _binding(v['first_binding']);_directory(v['first_directory']);_coord(v['coordination'])
    _closed(v['host_provenance'],('helper_sha','dependencies_sha','unarmed_launcher_sha','pin_review_sha','arm_receipt_sha','code_scope'))
    for x in v['host_provenance'].values():_hash(x)
    _int(v['observed_ms'],1);_int(v['not_after_ms'],v['observed_ms']+1)

def _root(v):
    _closed(v,('schema','profile','authority','family_anchor_id','request_identity_sha','anchor','first_covenant_sha','first_proof_sha','first_binding','first_directory','coordination'))
    for k in ('family_anchor_id','request_identity_sha','first_covenant_sha','first_proof_sha'):_hash(v[k])
    _anchor(v['anchor']);_binding(v['first_binding']);_directory(v['first_directory']);_coord(v['coordination'])
    if family_anchor(v['anchor'])!=v['family_anchor_id'] or v['anchor']['request_identity_sha']!=v['request_identity_sha']:hold()

def _witness(v):
    _closed(v,('schema','profile','authority','request_identity_sha','platform_account_sha','primary_human','family_anchor_id','family_root_sha','first_covenant_sha','first_proof_sha'))
    for k in ('request_identity_sha','platform_account_sha','family_anchor_id','family_root_sha','first_covenant_sha','first_proof_sha'):_hash(v[k])
    _human(v['primary_human'],text=False)
    if request_identity(v['platform_account_sha'],v['primary_human'])!=v['request_identity_sha']:hold()

VALIDATORS={'covenant':_covenant,'first_proof':_proof,'family_root':_root,'request_witness':_witness}

def validate(role,value):
    if type(role) is not str or role not in PROFILES:hold()
    from . import draft_group_operator_source_codec as operator
    profiles={'first_proof':operator.FIRST_PROOF_PROFILE,
              'family_root':operator.FAMILY_ROOT_PROFILE,
              'request_witness':operator.REQUEST_WITNESS_PROFILE}
    if type(value) is dict and role in profiles and value.get('profile')==profiles[role]:
        try:return operator.validate(value,expected_profile=profiles[role])
        except operator.OperatorSourceCodecError:hold('GROUP_OPERATOR_FAMILY_VALUE')
    _plain(value);schema,profile,_=PROFILES[role]
    if type(value) is not dict or type(value.get('schema')) is not int or value['schema']!=schema or type(value.get('profile')) is not str or value['profile']!=profile or type(value.get('authority')) is not bool or value['authority'] is not False:hold()
    VALIDATORS[role](value)
    import json
    return json.loads(_canonical(value))

def encode(role,value):
    checked=validate(role,value);raw=(_canonical(checked)+'\n').encode()
    if len(raw)>PROFILES[role][2]:hold('GROUP_INPUT_FILE_LIMIT')
    return raw

def decode(role,raw):
    from .draft_group_input_files import _parse
    if type(role) is not str or role not in PROFILES:hold()
    value=_parse(raw,PROFILES[role][2])
    if encode(role,value)!=raw:hold()
    return value

def file_sha(role,value):return sha256(encode(role,value)).hexdigest()
