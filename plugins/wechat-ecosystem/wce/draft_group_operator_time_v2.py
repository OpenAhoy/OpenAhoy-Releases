"""TIME06 pure declarations only. Never absence, issuer, entry or migration.

Old V1 parsers/continuation are called unchanged only for common field syntax.
No V1 object is accepted by these V2 entry points or returned as a V2 upgrade.
No clocks, paths, file/SQL/account, registry, token or network operation occurs.
"""
from hashlib import sha256
import json
import math
from wce import draft_group_operator_source_codec as old

TIME_MODEL='OPERATOR_TIME06_FIRST_ISSUE_V1'
POLICY_PROFILE_V2='GROUP_OPERATOR_SELECTED_RUNTIME_POLICY_V2'
OBSERVATION_PROFILE_V2='GROUP_CURRENT_OPERATOR_SOURCE_OBSERVATION_V2'
SOURCE_REVIEW_PROFILE_V2='GROUP_CURRENT_SOURCE_REVIEW_OPERATOR_V2'
SOURCE_FACTS_PROFILE_V2='GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V2'
POLICY_KEYS_V2=old.POLICY_KEYS+('time_model','source_lifetime_not_after_ms')
OBSERVATION_KEYS_V2=old.OBSERVATION_KEYS+('source_lifetime_not_after_ms',)
REVIEW_KEYS_V1=('schema','profile','authority','content_source_type','family_id','registration_sha',
    'semantic_scope_sha','original_source_material_sha','current_source_material_sha',
    'previous_review_sha','helper_acceptance_sha','qualification_generation_sha',
    'observed_at_ms','not_after_ms','configuration_sha','semantic_adoption_sha',
    'original_root_evidence_sha','runtime_source_policy_sha','current_binding','current_binding_sha')
REVIEW_KEYS_V2=REVIEW_KEYS_V1+('source_lifetime_not_after_ms','qualified_not_after_ms')
PROFILES=(POLICY_PROFILE_V2,OBSERVATION_PROFILE_V2,SOURCE_REVIEW_PROFILE_V2)
STABLE_KEYS=('source_material_sha','runtime_source_policy_sha','binding_sha',
    'operator_request_identity_sha','original_request_set_sha','account_partition_sha',
    'selection_sha','qa_set_sha','postupload_mapping_sha','prepared_relations_sha',
    'semantic_scope_sha','stable_owner','epoch','generation')

class OperatorTimeCodecError(ValueError):
    def __init__(self):super().__init__('GROUP_OPERATOR_TIME06_CODEC_HOLD')

def need(value):
    if value is not True:raise OperatorTimeCodecError()

def _plain(value):
    try:old._plain(value)
    except old.OperatorSourceCodecError:raise OperatorTimeCodecError() from None

def _closed(value,keys):
    _plain(value);need(type(value) is dict and set(value)==set(keys))

def _integer(value,minimum=1):
    need(type(value) is int and minimum<=value<=old.MAX_INTEGER)

def _sha(value):
    try:old._sha(value)
    except old.OperatorSourceCodecError:raise OperatorTimeCodecError() from None

def _header(value,keys,profile):
    _closed(value,keys)
    need(type(value['schema']) is int and value['schema']==2 and value['profile']==profile
         and value['authority'] is False and value['content_source_type']==old.CONTENT_SOURCE_TYPE)

def _common_syntax(value,extra,profile,validator):
    # Internal syntax-only projection; not a returned card, issuer or upgrade.
    v={key:part for key,part in value.items() if key not in extra}
    v.update(schema=1,profile=profile)
    try:validator(v)
    except old.OperatorSourceCodecError:raise OperatorTimeCodecError() from None

def canonical(value):
    _plain(value)
    return old.canonical(value)

def digest(value):return sha256(canonical(value)).hexdigest()

def validate_runtime_policy_v2(value):
    _header(value,POLICY_KEYS_V2,POLICY_PROFILE_V2)
    need(value['time_model']==TIME_MODEL)
    _integer(value['source_lifetime_not_after_ms'])
    _common_syntax(value,('time_model','source_lifetime_not_after_ms'),old.POLICY_PROFILE,old.validate_runtime_policy)
    caps=[value['original_input_not_after_ms']]
    if value['source_rights_expiry']['not_after'] is not None:caps.append(value['source_rights_expiry']['not_after'])
    need(value['source_lifetime_not_after_ms']<=min(caps))
    return json.loads(canonical(value))

def validate_observation_v2(value):
    _header(value,OBSERVATION_KEYS_V2,OBSERVATION_PROFILE_V2)
    _integer(value['source_lifetime_not_after_ms'])
    _common_syntax(value,('source_lifetime_not_after_ms',),old.OBSERVATION_PROFILE,old.validate_observation)
    need(value['qualified_not_after_ms']<=value['source_lifetime_not_after_ms']
         and value['qualified_not_after_ms']<=value['observed_at_ms']+240000)
    return json.loads(canonical(value))

def validate_descriptor_v2(value):
    _closed(value,old.DESCRIPTOR_KEYS)
    need(value['operator_observation_profile']==OBSERVATION_PROFILE_V2)
    shadow=dict(value,operator_observation_profile=old.OBSERVATION_PROFILE)
    try:old.validate_descriptor(shadow)
    except old.OperatorSourceCodecError:raise OperatorTimeCodecError() from None
    return json.loads(canonical(value))

def validate_continuation_v2(previous,current):
    a=validate_observation_v2(previous);b=validate_observation_v2(current)
    need(all(a[key]==b[key] for key in STABLE_KEYS)
         and b['observed_at_ms']>=a['observed_at_ms']
         and b['source_lifetime_not_after_ms']<=a['source_lifetime_not_after_ms'])
    # B is this entry only, never compared with the previous entry's B.
    return b

def current_time_bounds_v2(policy,*,fixed_source_cap_ms,observed_at_ms,capture_monotonic,entry_deadline,
                           qa_not_after_ms,previous_binding=None):
    """Pure min calculation. Caller supplies actual clocks/QA under real scope.

    This does not prove the inputs, first absence, original lifetime or an Entry.
    No now+24h or old V1 qualified cap is ever made into a fixed source lifetime.
    """
    p=validate_runtime_policy_v2(policy);_integer(observed_at_ms);_integer(qa_not_after_ms)
    _integer(fixed_source_cap_ms);need(fixed_source_cap_ms<=p['source_lifetime_not_after_ms'])
    need(type(capture_monotonic) in (int,float) and type(entry_deadline) in (int,float)
         and math.isfinite(capture_monotonic) and math.isfinite(entry_deadline)
         and 0<entry_deadline-capture_monotonic<=300)
    caps=[fixed_source_cap_ms,qa_not_after_ms]
    if previous_binding is not None:caps.append(validate_observation_v2(previous_binding)['source_lifetime_not_after_ms'])
    lifetime=min(caps)
    qualified=min(lifetime,observed_at_ms+240000,
        math.floor(observed_at_ms+(entry_deadline-capture_monotonic)*1000))
    need(qualified>observed_at_ms)
    return {'source_lifetime_not_after_ms':lifetime,'qualified_not_after_ms':qualified}

def validate_review_v2(value):
    _header(value,REVIEW_KEYS_V2,SOURCE_REVIEW_PROFILE_V2)
    for key in REVIEW_KEYS_V1:
        if key.endswith('_sha') and (key!='previous_review_sha' or value[key] is not None):_sha(value[key])
    _sha(value['family_id']);_sha(value['registration_sha'])
    for key in ('observed_at_ms','not_after_ms','source_lifetime_not_after_ms','qualified_not_after_ms'):_integer(value[key])
    o=validate_observation_v2(value['current_binding'])
    need(value['current_binding_sha']==digest(o)
         and value['original_source_material_sha']==value['current_source_material_sha']==o['source_material_sha']
         and value['semantic_scope_sha']==o['semantic_scope_sha']
         and value['runtime_source_policy_sha']==o['runtime_source_policy_sha']
         and value['qualification_generation_sha']==o['proof_generation_sha']
         and value['observed_at_ms']==o['observed_at_ms']
         and value['not_after_ms']==value['qualified_not_after_ms']==o['qualified_not_after_ms']
         and value['source_lifetime_not_after_ms']==o['source_lifetime_not_after_ms'])
    return json.loads(canonical(value))

def validate_review_continuation_v2(previous,current):
    a=validate_review_v2(previous);b=validate_review_v2(current)
    for key in ('family_id','registration_sha','original_source_material_sha','current_source_material_sha',
                'semantic_scope_sha','configuration_sha','semantic_adoption_sha',
                'original_root_evidence_sha','runtime_source_policy_sha','helper_acceptance_sha'):
        need(a[key]==b[key])
    need(b['previous_review_sha']==sha256(encode(a)).hexdigest())
    validate_continuation_v2(a['current_binding'],b['current_binding'])
    # Actual replay still verifies physical bytes/SHA and original event order.
    return b

def validate(value):
    _plain(value);need(type(value) is dict and type(value.get('profile')) is str)
    validators={POLICY_PROFILE_V2:validate_runtime_policy_v2,
        OBSERVATION_PROFILE_V2:validate_observation_v2,SOURCE_REVIEW_PROFILE_V2:validate_review_v2}
    need(value['profile'] in validators)
    return validators[value['profile']](value)

def encode(value):return canonical(validate(value))+b'\n'

def decode(raw):
    need(type(raw) is bytes and 0<len(raw)<=old.MAX_BYTES)
    def unique(rows):
        value={}
        for key,part in rows:need(key not in value);value[key]=part
        return value
    try:value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:need(False))
    except (ValueError,UnicodeError,RecursionError,OverflowError):raise OperatorTimeCodecError() from None
    value=validate(value);need(encode(value)==raw);return value


def validate_material_links_v2(source, policy, semantic, observation, descriptor, *,
                            current_binding_sha, configuration_sha):
    """Pure cross-document consistency, not authenticity or current authority."""
    s = old.validate_source(source)
    p = validate_runtime_policy_v2(policy)
    m = old.validate_semantic(semantic)
    o = validate_observation_v2(observation)
    d = validate_descriptor_v2(descriptor)
    old._sha(current_binding_sha); old._sha(configuration_sha)
    source_sha = sha256(old.encode(s, expected_profile=old.SOURCE_PROFILE)).hexdigest()
    policy_sha = sha256(encode(p)).hexdigest()
    semantic_sha = sha256(old.encode(m, expected_profile=old.SEMANTIC_PROFILE)).hexdigest()
    need(p['binding'] == m['binding']
          and s['binding_sha'] == o['binding_sha'] == digest(p['binding'])
          and o['stable_owner'] == m['stable_owner']
          and o['epoch'] == p['binding']['epoch']
          and o['generation'] == p['binding']['generation']
          and p['source_material_sha'] == o['source_material_sha'] == source_sha
          and o['runtime_source_policy_sha'] == d['runtime_source_policy_sha'] == policy_sha
          and d['configuration_sha'] == configuration_sha
          and d['current_binding_sha'] == current_binding_sha == digest(o)
          and d['semantic_adoption_sha'] == semantic_sha
          and d['artifact_inventory_sha'] == m['artifact_inventory_sha']
          and s['semantic_scope_sha'] == p['semantic_scope_sha']
          == o['semantic_scope_sha'] == old.semantic_scope_sha(m))
    for key in ('original_queue_sha', 'original_request_set_sha', 'account_partition_sha',
                'operator_request_identity_sha'):
        need(s[key] == p[key] == m[key])
        if key != 'original_queue_sha':
            need(o[key] == s[key])
    need(s['allowed_read_scope'] == p['allowed_read_scope']
          and s['allowed_read_scope']['family_anchor_sha'] == digest(old._anchor_view(m))
          and s['allowed_read_scope']['member_ids'] == m['semantic_scope']['authorized_member_ids']
          and s['qa_set_ref'] == m['qa_set_ref']
          and s['selection_ref']['sha256'] == p['selection_sha'] == o['selection_sha']
          == d['selection_sha']
          and s['qa_set_ref']['sha256'] == p['qa_set_sha'] == o['qa_set_sha'] == d['qa_adoption_sha']
          and s['postupload_mapping_ref']['sha256'] == p['postupload_mapping_sha']
          == o['postupload_mapping_sha'] == d['postupload_mapping_sha']
          and s['prepared_relation_inventory_ref']['sha256'] == p['prepared_relations_sha']
          == o['prepared_relations_sha'] == d['prepared_relations_sha']
          and d['operator_request_set_sha'] == s['original_request_set_sha']
          and p['source_rights_expiry'] == m['source_rights_expiry'])
    caps = [s['expires_policy']['not_after'] * 1000, p['original_input_not_after_ms']]
    if p['source_rights_expiry']['not_after'] is not None:
        caps.append(p['source_rights_expiry']['not_after'])
    need(p['source_lifetime_not_after_ms'] <= min(caps)
          and o['source_lifetime_not_after_ms'] <= p['source_lifetime_not_after_ms'])
    return {'authority': False, 'content_source_type': old.CONTENT_SOURCE_TYPE,
            'source_material_sha': source_sha, 'runtime_source_policy_sha': policy_sha,
            'semantic_adoption_sha': semantic_sha, 'observation_sha': digest(o)}


def decode_runtime_policy_v2(raw):
    """Fixed F/chain reader: a ReviewV2 raw cannot substitute for policy raw."""
    return validate_runtime_policy_v2(decode(raw))
