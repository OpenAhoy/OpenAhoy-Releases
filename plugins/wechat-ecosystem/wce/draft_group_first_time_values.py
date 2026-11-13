"""TIME06 technical records: pure syntax, never absence or permission.

The stable anchor remains V1. Only a fresh typed first issuer may create this
new model. Neither this module nor persisted JSON can establish that issuer.
"""
import json
from hashlib import sha256

TIME_MODEL = 'OPERATOR_TIME06_FIRST_ISSUE_V1'
OBSERVATION_PROFILE = 'GROUP_OPERATOR_FIRST_TECHNICAL_OBSERVATION_V2'
RECORD_PROFILE = 'GROUP_OPERATOR_PRE_PARENT_TIME06_RECORD_V1'
MAPPING_PROFILE = 'GROUP_OPERATOR_BOUND_REAL_PARENT_TIME06_V2'
RESULT_PROFILE = 'GROUP_OPERATOR_FIRST_PREPARE_RESULT_KNOWN_V1'
HISTORY_RESULT_PROFILE = 'GROUP_OPERATOR_FIRST_PREPARE_GRAPH_KNOWN_V1'
EXTRA_OBSERVATION_KEYS = ('schema', 'profile', 'time_model',
    'source_lifetime_not_after_ms', 'first_absence_sha', 'first_invocation_sha',
    'issuer_parent_pid')
EXTRA_RECORD_KEYS = ('time_model', 'source_lifetime_not_after_ms',
    'original_technical_not_after_ms', 'attachment_origin', 'prepare_result')
EXTRA_MAPPING_KEYS = ('time_model', 'source_lifetime_not_after_ms',
    'original_technical_not_after_ms', 'first_absence_sha')
RESULT_KEYS = ('schema', 'profile', 'authority', 'preparation_identity_sha',
    'parent_mapping_sha', 'response_sha', 'runtime_sha', 'service_pid',
    'original_technical_not_after_ms', 'observed_at_ms', 'owner_kind')
HISTORY_RESULT_KEYS = ('schema','profile','authority','preparation_identity_sha',
    'parent_mapping_sha','parent_event','plan_event','original_technical_not_after_ms',
    'observed_at_ms','observation_origin','original_response','owner_kind')
KNOWN_EVENT = 'PREPARE_RESULT_KNOWN'


class FirstTimeHold(ValueError):
    def __init__(self):super().__init__('GROUP_FIRST_TIME06_VALUES_HOLD')


def need(value):
    if value is not True:raise FirstTimeHold()


def integer(value, minimum=1):
    need(type(value) is int and minimum <= value <= 2**63-1)


def checksum(value):
    need(type(value) is str and len(value) == 64
         and all(c in '0123456789abcdef' for c in value))


def image(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):return sha256(image(value)).hexdigest()


def is_time06_observation(value):
    return type(value) is dict and value.get('profile') == OBSERVATION_PROFILE


def validate_observation(value, legacy_keys, legacy_validator):
    need(type(value) is dict and set(value) == set(legacy_keys + EXTRA_OBSERVATION_KEYS))
    need(type(value['schema']) is int and value['schema'] == 2
         and value['profile'] == OBSERVATION_PROFILE and value['time_model'] == TIME_MODEL)
    legacy_validator({key:value[key] for key in legacy_keys})
    for key in ('source_lifetime_not_after_ms', 'issuer_parent_pid'):integer(value[key])
    for key in ('first_absence_sha', 'first_invocation_sha'):checksum(value[key])
    need(value['not_after_ms'] <= value['source_lifetime_not_after_ms'])
    return json.loads(image(value))


def require_same_lifecycle(first, current):
    """No cross-C/source/epoch/first-invocation/D changes in one technical run."""
    need(image(first) == image(current))


def validate_result(value):
    if type(value) is dict and value.get('profile')==HISTORY_RESULT_PROFILE:
        need(set(value)==set(HISTORY_RESULT_KEYS) and type(value['schema']) is int
             and value['schema']==2 and value['authority'] is False
             and value['observation_origin']=='HISTORICAL_COMMITTED_GRAPH_OBSERVATION_V1'
             and value['original_response']=='NOT_ASSERTED'
             and value['owner_kind']=='HISTORICAL_COMPLETE_PARENT_GRAPH')
        for key in ('preparation_identity_sha','parent_mapping_sha'):checksum(value[key])
        for key in ('original_technical_not_after_ms','observed_at_ms'):integer(value[key])
        for key in ('parent_event','plan_event'):
            event=value[key];need(type(event) is dict and set(event)=={'seq','event_sha'})
            integer(event['seq']);checksum(event['event_sha'])
        need(value['parent_event']['seq']<value['plan_event']['seq'])
        return json.loads(image(value))
    need(type(value) is dict and set(value) == set(RESULT_KEYS)
         and type(value['schema']) is int and value['schema'] == 1
         and value['profile'] == RESULT_PROFILE and value['authority'] is False
         and value['owner_kind'] == 'FIXED_LONG_LIVED_H')
    for key in ('preparation_identity_sha', 'parent_mapping_sha', 'response_sha', 'runtime_sha'):
        checksum(value[key])
    for key in ('service_pid', 'original_technical_not_after_ms', 'observed_at_ms'):
        integer(value[key])
    need(value['observed_at_ms'] < value['original_technical_not_after_ms'])
    return json.loads(image(value))


def validate_mapping(value, legacy_keys, legacy_validator):
    need(type(value) is dict and set(value) == set(legacy_keys + EXTRA_MAPPING_KEYS)
         and type(value['schema']) is int and value['schema'] == 2
         and value['profile'] == MAPPING_PROFILE and value['time_model'] == TIME_MODEL)
    for key in ('source_lifetime_not_after_ms', 'original_technical_not_after_ms'):
        integer(value[key])
    checksum(value['first_absence_sha'])
    # This internal syntax projection neither rewrites a persisted V1 nor emits
    # one. The complete original Parent/children/event validation remains shared.
    common={key:value[key] for key in legacy_keys}
    common.update(schema=1,profile='GROUP_OPERATOR_BOUND_REAL_PARENT_MAPPING_V1')
    legacy_validator(common)
    need(value['not_after_ms'] == min(value['parent']['not_after_ms'],
                                    value['source_lifetime_not_after_ms']))
    return json.loads(image(value))


# Exact field roles only: shared C/binding/policy/QA/settings and generic s01
# never form case edges. The collector supplies only original Group issuance
# objects, after their own closed codecs/history replay have passed.
CASE_KEYS = frozenset(('original_queue_sha','queue_sha256','original_request_set_sha',
    'request_set_sha256','account_partition_sha','operator_request_identity_sha',
    'request_identity_sha','original_request_identity_sha','original_request_sha',
    'prepare_request_key','manifest_sha','manifest_digest','content_digest'))
ROLE_REFS = {
    'source_material_sha':'source','current_source_material_sha':'source',
    'original_source_material_sha':'source',
    'registration_sha':'registration','registration_proof_sha':'registration_proof',
    'previous_review_sha':'source_review','current_source_review_sha':'source_review',
    'family_id':'family','family_anchor_id':'family','family_anchor_sha':'family',
    'read_covenant_sha':'covenant','first_covenant_sha':'covenant','covenant_sha':'covenant',
    'first_proof_sha':'first_proof','family_root_sha':'family_root',
    'parent_sha':'parent','preview_sha':'preview','snapshot_sha':'preview',
    'operation_id':'operation','claim_id':'claim','response_proof_sha':'response',
    'batch_id':'batch','grant_id':'purpose','gid':'purpose',
    'source_grant_sha':'source_grant','purpose_key':'source_grant','first_purpose_key':'source_grant',
    'snapshot_file_sha':'response_snapshot',
    'execution_input_sha':'execution','capsule_sha':'execution',
    'target_reservation_sha':'reservation','request_witness_sha':'request_witness'}


def case_tokens(value):
    """Pure exact typed indexes, not a general hash search or authorization."""
    stable=set();refs=set();members=set();stack=[value];count=0
    while stack:
        part=stack.pop();count+=1;need(count<=500000)
        if type(part) is list:stack.extend(part);continue
        if type(part) is not dict:continue
        for key,item in part.items():
            if key in CASE_KEYS and type(item) is str:stable.add((key,item))
            if key in ('article_id','selected_article_id') and type(item) is str and item.startswith('WC-'):
                members.add(item)
            if key in ('authorized_member_ids','member_ids') and type(item) is list:
                members.update(x for x in item if type(x) is str and x.startswith('WC-'))
            if key in ROLE_REFS and type(item) is str:refs.add((ROLE_REFS[key],item))
            if key in ('selector','source_manifest_selector') and type(item) is dict:
                need(set(item)=={'bundle_id','version','content_digest'})
                stable.add(('selector',digest(item)))
            if type(item) in (dict,list):stack.append(item)
            elif key in ('manifest_json','projection_json') and type(item) is str:
                try:stack.append(json.loads(item))
                except ValueError:need(False)
    # Queue/request-set spellings differ across Native/Operator containers.
    normalized=set()
    aliases={'queue_sha256':'original_queue_sha','request_set_sha256':'original_request_set_sha',
        'original_request_identity_sha':'request_identity_sha',
        'operator_request_identity_sha':'request_identity_sha',
        'manifest_sha':'content_digest','manifest_digest':'content_digest'}
    for key,item in stable:normalized.add((aliases.get(key,key),item))
    return normalized,refs,members


def related_components(nodes,seed_values):
    """Return facts only. Unjoinable issuance is UNKNOWN, never assumed disjoint.

    nodes are (role,key,value) from actual typed collectors. Full unrelated
    components with explicit disjoint WC members survive; pure FIRST or orphan
    scope without a cross-profile disjoint witness remains unknown.
    """
    need(type(nodes) is list and len(nodes)<=500000)
    seed,_,wanted_members=case_tokens(seed_values);need(bool(wanted_members))
    indexed=[];owners={};parent=list(range(len(nodes)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(i,j):parent[find(j)]=find(i)
    for i,node in enumerate(nodes):
        need(type(node) in (list,tuple) and len(node)==3)
        role,key,value=node;need(type(role) is str and type(key) is str)
        stable,refs,members=case_tokens(value)
        indexed.append((stable,refs,members))
        identities={(role,key)}|refs
        for identity in identities:
            if identity in owners:union(i,owners[identity])
            else:owners[identity]=i
        # Same precise source selector/manifest/member identity is a legitimate
        # relation even when two historical profiles use different FIRST hashes.
        for token in stable|{('WC_MEMBER',x) for x in members}:
            identity=('CASE',token)
            if identity in owners:union(i,owners[identity])
            else:owners[identity]=i
    groups={}
    for i,node in enumerate(nodes):groups.setdefault(find(i),[]).append(i)
    related=[];unknown=[];unrelated=[]
    for indices in groups.values():
        stable=set().union(*(indexed[i][0] for i in indices))
        members=set().union(*(indexed[i][2] for i in indices))
        refs=[(nodes[i][0],nodes[i][1]) for i in indices]
        if stable & seed or members & wanted_members:related.extend(refs)
        elif members:unrelated.extend(refs)
        else:unknown.extend(refs)
    return {'authority':False,'related':sorted(related),'unknown':sorted(unknown),
            'unrelated':sorted(unrelated)}
