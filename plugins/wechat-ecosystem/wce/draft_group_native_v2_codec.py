"""Closed Native V2 wire values. Parsing and hashes never issue authority."""
from hashlib import sha256

from .contracts import WCEError
from .draft_revision_native_source import strict_json, canonical
from .draft_group_contracts import digest
from .draft_group_input_files import (_plain, _hash, _id, _int, _ref, _human,
    _role_thread, _record_binding, _pair, _evidence, _deadline)

MAX_MATERIAL = 2 * 1024 * 1024
MAX_PREFIX = 2 * 1024 * 1024 * 1024
MAX_RETAINED = 64 * 1024 * 1024
MODE = 'FIXED_BASELINE_EPHEMERAL_CURRENT_V1'
BASELINE_PROFILE = 'GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'
OBSERVATION_PROFILE = 'GROUP_CURRENT_SOURCE_OBSERVATION_V2'
BINDING_PROFILE = 'GROUP_CURRENT_SOURCE_BINDING_V2'
REVIEW_PROFILE = 'GROUP_CURRENT_SOURCE_REVIEW_V2'
POLICY_PROFILE = 'GROUP_RUNTIME_SOURCE_POLICY_V1'
ACCEPTANCE_PROFILE = 'GROUP_HOST_RUNTIME_POLICY_ACCEPTANCE_V1'
CATEGORIES = ('PREFIX_STRUCTURAL','SESSION_META','TASK_STARTED','TURN_CONTEXT',
    'TASK_TERMINAL','USAGE','CONFIG_HARNESS','CONFIG_AGENTS','USER_RAW',
    'USER_TYPED','ASSISTANT_RAW','ASSISTANT_TYPED','TOOL_CALL','TOOL_RESULT')


def need(ok, suffix='FIELDS'):
    if not ok:
        raise WCEError('GROUP_NATIVE_V2_' + suffix)


def closed(value, keys):
    _plain(value)
    need(type(value) is dict and set(value) == set(keys))
    return value


def seq(value, check, low=0, high=16384):
    need(type(value) is list and low <= len(value) <= high)
    for item in value:
        check(item)


def equal(left, right):
    need(type(left) is type(right) and canonical(left) == canonical(right), 'BINDING')


def profile(value, keys, name, schema):
    closed(value, keys)
    need(type(value['schema']) is int and value['schema'] == schema
         and value['profile'] == name and value['authority'] is False, 'PROFILE')


def _decode(raw, check):
    value = strict_json(raw, maximum=MAX_MATERIAL)
    check(value)
    need(raw == canonical(value) + b'\n', 'CANONICAL')
    return value


def _nullable_hash(value):
    if value is not None:
        _hash(value)


def _rights(value):
    closed(value, ('kind', 'not_after'))
    need(value['kind'] in ('PERSISTENT_DELEGATION', 'EXPLICIT_UNTIL'), 'RIGHTS')
    if value['kind'] == 'PERSISTENT_DELEGATION':
        need(value['not_after'] is None, 'RIGHTS')
    else:
        _int(value['not_after'], 1)


def _stream_contract(value):
    closed(value, ('profile','interpreter_contract_sha256','limits_sha256'))
    need(value['profile'] == 'GROUP_SELECTED_STREAM_CONTRACT_V2', 'CONTRACT')
    _hash(value['interpreter_contract_sha256']); _hash(value['limits_sha256'])


def _selected_pair(value):
    closed(value, ('source_id','raw','typed','terminal'))
    _id(value['source_id'])
    for key in ('raw','typed','terminal'):
        _ref(value[key]); need(value[key]['source_id'] == value['source_id'], 'PAIR_SOURCE')
    need(value['raw']['ordinal'] < value['typed']['ordinal'] < value['terminal']['ordinal'], 'PAIR_ORDER')


def _identity(value):
    closed(value, SOURCE_IDENTITY_KEYS)
    for key in ('source_id','thread_id'):
        _id(value[key])
    for key in ('path_utf8_sha256','session_meta_sha256'):
        _hash(value[key])
    for key in ('device','inode','metadata_ordinal'):
        _int(value[key])


def _start(value):
    closed(value, INTERPRETATION_START_KEYS)
    _id(value['source_id']); _ref(value['reference'])
    need(value['source_id'] == value['reference']['source_id'], 'START_SOURCE')


def _commitment(value):
    closed(value, BASELINE_COMMITMENT_KEYS)
    _id(value['source_id']); _int(value['end_byte'], 0, MAX_PREFIX)
    _int(value['absolute_end_ordinal'], 0, 500000)
    _hash(value['prefix_sha256'])
    for key in ('ordered_records_sha256','control_sha256'):
        _nullable_hash(value[key])


def validate_baseline(value):
    profile(value, BASELINE_KEYS, BASELINE_PROFILE, 2)
    need(value['native_qualification_status'] == 'NOT_ASSERTED', 'BASELINE_STATUS')
    seq(value['role_threads'], _role_thread, 1, 4)
    closed(value['original_user_scope'], ('semantic_scope_sha','human_refs'))
    _hash(value['original_user_scope']['semantic_scope_sha'])
    seq(value['original_user_scope']['human_refs'], _human, 1, 16)
    seq(value['source_identities'], _identity, 1, 4)
    seq(value['interpretation_starts'], _start, 1, 4)
    identities = value['source_identities']
    ids = [x['source_id'] for x in identities]
    need(len(set(ids)) == len(ids), 'SOURCE_DUPLICATE')
    equal(ids, [x['source_id'] for x in value['interpretation_starts']])
    need({r['thread_id'] for r in value['role_threads']} == {x['thread_id'] for x in identities}, 'ROLE_SOURCE')
    need(len({(r['role'], r['thread_id']) for r in value['role_threads']}) == len(value['role_threads']), 'ROLE_DUPLICATE')
    seq(value['retained_bindings'], _record_binding)
    seq(value['reviewed_other_records'], _record_binding)
    equal(value['reviewed_other_records'], [x for x in value['retained_bindings']
          if x['category'] not in ('USER_RAW','USER_TYPED')])
    refs = [canonical(x['reference']) for x in value['retained_bindings']]
    need(len(set(refs)) == len(refs), 'BINDING_DUPLICATE')
    seq(value['typed_raw_pairs'], _pair, 1, 1024)
    originals = [x['human'] for x in value['typed_raw_pairs'] if x['disposition'] == 'ORIGINAL_REQUEST']
    equal(originals, value['original_user_scope']['human_refs'])
    seq(value['selected_assistant_pairs'], _selected_pair, 1, 128)
    qa_refs = [canonical(x[k]) for x in value['selected_assistant_pairs'] for k in ('raw','typed')]
    need(len(set(qa_refs)) == len(qa_refs), 'QA_DUPLICATE')
    need(set(qa_refs) == {canonical(x['reference']) for x in value['retained_bindings']
                          if x['category'] == 'QA_FACT'}, 'QA_BINDING')
    seq(value['qa_sources'], _evidence, 1, 3072)
    need(all(x['kind'] == 'QA' for x in value['qa_sources']), 'QA_ROLE')
    _hash(value['semantic_scope_sha'])
    equal(value['semantic_scope_sha'], value['original_user_scope']['semantic_scope_sha'])
    closed(value['allowed_read_scope'], ('family_anchor_sha','covenant_sha'))
    for item in value['allowed_read_scope'].values():
        _hash(item)
    closed(value['expires_policy'], ('mode','not_after'))
    need(value['expires_policy']['mode'] == 'SOURCE_BOUND_CURRENT', 'EXPIRY')
    _deadline(value['expires_policy']['not_after'])
    _stream_contract(value['stream_contract'])
    seq(value['baseline_commitments'], _commitment, 0, 256)
    for group in ('retained_bindings','baseline_commitments'):
        need(all((x['reference'] if group == 'retained_bindings' else x)['source_id'] in ids
                 for x in value[group]), 'SOURCE_SCOPE')
    return value


def _known_review(value):
    closed(value, KNOWN_USER_REVIEW_KEYS)
    _human(value['human']); _ref(value['raw']); _ref(value['typed'])
    need(value['raw']['source_id'] == value['typed']['source_id']
         and value['raw']['ordinal'] < value['typed']['ordinal'], 'USER_PAIR')
    need(value['disposition'] in ('NON_SCOPE_CHANGE','INPUT_FACT','NON_GRANT'), 'USER_DISPOSITION')
    _hash(value['review_artifact_sha'])


def _config_rule(value):
    closed(value, CONFIG_EQUIVALENCE_RULE_KEYS)
    need(value['kind'] in ('harness','agents_md'), 'CONFIG_KIND')
    need(value['rule'] in ('EXACT_CONFIG_PAYLOAD_V1','SAME_AGENTS_MD_CONTENT_FIXED_PROVENANCE_REBIND_V1'), 'CONFIG_RULE')
    need(value['rule'] != 'SAME_AGENTS_MD_CONTENT_FIXED_PROVENANCE_REBIND_V1'
         or value['kind'] == 'agents_md', 'CONFIG_RULE')
    _ref(value['reference'])


def validate_runtime_policy(value):
    profile(value, RUNTIME_POLICY_KEYS, POLICY_PROFILE, 1)
    for key in ('core_scope_sha','binding_sha','baseline_source_sha','semantic_scope_sha',
                'native_contract_sha','role_descriptors_sha','qa_selection_sha'):
        _hash(value[key])
    origin = closed(value['origin_source_descriptor'], ORIGIN_SOURCE_DESCRIPTOR_KEYS)
    need(origin['source_profile'] in ('GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1', BASELINE_PROFILE), 'ORIGIN_PROFILE')
    _hash(origin['sha256']); _int(origin['size'], 1, MAX_MATERIAL)
    need(value['allowed_non_user_protocol'] == 'GROUP_NATIVE_FINITE_NON_AUTH_SUFFIX_V2', 'PROTOCOL')
    seq(value['known_user_reviews'], _known_review, 0, 1024)
    humans = [canonical(x['human']) for x in value['known_user_reviews']]
    need(len(set(humans)) == len(humans), 'USER_DUPLICATE')
    seq(value['config_equivalence_rules'], _config_rule, 0, 2)
    need(len({x['kind'] for x in value['config_equivalence_rules']}) == len(value['config_equivalence_rules']), 'CONFIG_DUPLICATE')
    _int(value['original_input_not_after_ms'], 1)
    _rights(value['original_source_rights_expiry'])
    return value


def _path_sha(value):
    need(type(value) is list and len(value) == 2 and type(value[0]) is str
         and value[0].startswith('/') and '\x00' not in value[0], 'DEPENDENCY')
    _hash(value[1])


def validate_policy_acceptance(value):
    profile(value, STATIC_ACCEPTANCE_KEYS, ACCEPTANCE_PROFILE, 1)
    for key in ('configuration_sha','semantic_adoption_sha','source_material_sha',
                'artifact_inventory_sha','first_covenant_sha','read_contract_sha',
                'candidate_scope','unarmed_sha','runtime_source_policy_sha','native_contract_sha'):
        _hash(value[key])
    seq(value['helper_dependencies'], _path_sha, 1, 1024)
    seq(value['retention_evidence'], _path_sha, 1, 1024)
    closed(value['permitted_arm'], ('REVIEW_PATH','REVIEW_SHA'))
    need(type(value['permitted_arm']['REVIEW_PATH']) is str
         and value['permitted_arm']['REVIEW_PATH'].startswith('/')
         and value['permitted_arm']['REVIEW_SHA'] == 'FIXED_REVIEW_BYTES_SHA256', 'ARM')
    need(value['source_binding_mode'] == MODE
         and value['baseline_native_qualification'] == 'NOT_ASSERTED', 'BASELINE_STATUS')
    return value


def decode_baseline(raw):
    return _decode(raw, validate_baseline)


def decode_runtime_policy(raw):
    return _decode(raw, validate_runtime_policy)


def decode_policy_acceptance(raw):
    return _decode(raw, validate_policy_acceptance)


def validate_checkpoint(value):
    closed(value, CHECKPOINT_KEYS)
    _int(value['end'], 0, MAX_PREFIX)
    _int(value['absolute_end_ordinal'], 0, 500000)
    for key in ('prefix_sha256','ordered_records_sha256','control_sha256'):
        _hash(value[key])
    return value


def validate_stream_summary(value):
    closed(value, CURRENT_STREAM_SUMMARY_KEYS)
    need(value['schema'] == 'GROUP_NATIVE_CURRENT_STREAM_FACTS_V2'
         and value['authority'] is False, 'STREAM_PROFILE')
    _id(value['source_id'])
    for key in ('thread_sha256','source_registration_sha256','prefix_sha256',
                'request_scope_sha256','generation_sha256','ordered_records_sha256','control_sha256'):
        _hash(value[key])
    _int(value['prefix_bytes'], 1, MAX_PREFIX)
    _int(value['interpretation_start'], 0, value['prefix_bytes'] - 1)
    for key in ('interpretation_start_ordinal','first_ordinal','end_ordinal_exclusive'):
        _int(value[key], 0, 500000)
    _int(value['record_count'], 1, 500000)
    need(value['end_ordinal_exclusive'] - value['first_ordinal'] == value['record_count']
         and value['first_ordinal'] <= value['interpretation_start_ordinal']
         < value['end_ordinal_exclusive'], 'STREAM_COUNT')
    closed(value['category_counts'], CATEGORIES)
    for count in value['category_counts'].values():
        _int(count, 0, 500000)
    need(sum(value['category_counts'].values()) == value['record_count'], 'STREAM_COUNT')
    _int(value['control_record_count'], 1, value['record_count'])
    _int(value['control_raw_bytes'], 1, min(MAX_RETAINED, value['prefix_bytes']))
    seq(value['checkpoints'], validate_checkpoint, 0, 256)
    previous = (-1, -1)
    for checkpoint in value['checkpoints']:
        current = checkpoint['end'], checkpoint['absolute_end_ordinal']
        need(current[0] > previous[0] and current[1] > previous[1]
             and current[0] <= value['prefix_bytes']
             and current[1] <= value['end_ordinal_exclusive'], 'CHECKPOINT_ORDER')
        previous = current
        if checkpoint['end'] == value['prefix_bytes']:
            equal(checkpoint, {'end':value['prefix_bytes'],
                  'absolute_end_ordinal':value['end_ordinal_exclusive'],
                  **{k:value[k] for k in ('prefix_sha256','ordered_records_sha256','control_sha256')}})
    return value


def validate_prefix_proof(value):
    closed(value, PREFIX_PROOF_KEYS)
    _id(value['source_id'])
    need(value['baseline_kind'] in ('M0_EXPECTATION','ORIGIN_V1_MATERIAL','PREVIOUS_REVIEW'), 'PREFIX_KIND')
    for key in ('baseline_locator_sha','baseline_prefix_sha256'):
        _hash(value[key])
    for key in ('baseline_ordered_sha256','baseline_control_sha256'):
        _nullable_hash(value[key])
    _int(value['baseline_end'], 0, MAX_PREFIX)
    checkpoint = validate_checkpoint(value['current_checkpoint'])
    need(checkpoint['end'] == value['baseline_end']
         and checkpoint['prefix_sha256'] == value['baseline_prefix_sha256'], 'PREFIX_CHANGED')
    for key, target in (('baseline_ordered_sha256','ordered_records_sha256'),
                        ('baseline_control_sha256','control_sha256')):
        if value[key] is not None:
            equal(value[key], checkpoint[target])
    return value


def _source_list(values):
    seq(values, validate_stream_summary, 1, 4)
    need(len({x['source_id'] for x in values}) == len(values), 'SOURCE_DUPLICATE')
    need(sum(x['record_count'] for x in values) <= 500000
         and sum(len(x['checkpoints']) for x in values) <= 256, 'STREAM_LIMIT')


def validate_current_binding(value):
    profile(value, CURRENT_BINDING_KEYS, BINDING_PROFILE, 2)
    need(value['binding_mode'] == MODE
         and value['source_observation_profile'] == OBSERVATION_PROFILE, 'BINDING_MODE')
    for key in ('configuration_sha','baseline_source_material_sha','origin_source_material_sha',
                'runtime_source_policy_sha','baseline_acceptance_sha','native_contract_sha',
                'semantic_scope_sha','entry_epoch_sha','source_observation_sha',
                'qualification_generation_sha','permission_facts_sha',
                'prefix_preservation_sha','reviewed_delta_sha'):
        _hash(value[key])
    _int(value['capture_started_at_ms'], 1); _int(value['qualified_not_after_ms'], 1)
    need(0 < value['qualified_not_after_ms'] - value['capture_started_at_ms'] <= 240000, 'CAPTURE_TIME')
    _source_list(value['sources'])
    equal(value['qualification_generation_sha'], digest(value['sources']))
    seq(value['prefix_proofs'], validate_prefix_proof, 0, 256)
    equal(value['prefix_preservation_sha'], digest(value['prefix_proofs']))
    by_id = {x['source_id']:x for x in value['sources']}
    seen = set()
    for proof in value['prefix_proofs']:
        need(proof['source_id'] in by_id, 'PREFIX_SOURCE')
        key = (proof['source_id'], proof['baseline_kind'], proof['baseline_locator_sha'], proof['baseline_end'])
        need(key not in seen, 'PREFIX_DUPLICATE'); seen.add(key)
        need(proof['current_checkpoint'] in by_id[proof['source_id']]['checkpoints'], 'PREFIX_CHECKPOINT')
    return value


def _classification(value):
    closed(value, ('human','disposition')); _human(value['human'])
    need(value['disposition'] in ('NON_SCOPE_CHANGE','INPUT_FACT','NON_GRANT'), 'USER_DISPOSITION')


def validate_source_review(value):
    profile(value, SOURCE_REVIEW_KEYS, REVIEW_PROFILE, 2)
    for key in ('family_id','registration_sha','semantic_scope_sha','original_source_material_sha',
                'current_source_material_sha','helper_acceptance_sha','original_human_refs_sha',
                'qualification_generation_sha','runtime_source_policy_sha','current_binding_sha',
                'prefix_preservation_sha','reviewed_delta_sha'):
        _hash(value[key])
    _nullable_hash(value['previous_review_sha'])
    seq(value['known_user_classifications'], _classification, 0, 1024)
    need(len({canonical(x['human']) for x in value['known_user_classifications']})
         == len(value['known_user_classifications']), 'USER_DUPLICATE')
    _int(value['observed_at_ms'], 1); _int(value['not_after_ms'], 1)
    need(value['binding_mode'] == MODE, 'BINDING_MODE')
    witness = validate_current_binding(value['current_binding'])
    equal(value['current_binding_sha'], digest(witness))
    for key, target in (('semantic_scope_sha','semantic_scope_sha'),
                        ('current_source_material_sha','baseline_source_material_sha'),
                        ('original_source_material_sha','origin_source_material_sha'),
                        ('runtime_source_policy_sha','runtime_source_policy_sha'),
                        ('helper_acceptance_sha','baseline_acceptance_sha'),
                        ('qualification_generation_sha','qualification_generation_sha'),
                        ('observed_at_ms','capture_started_at_ms'),
                        ('not_after_ms','qualified_not_after_ms'),
                        ('prefix_preservation_sha','prefix_preservation_sha'),
                        ('reviewed_delta_sha','reviewed_delta_sha')):
        equal(value[key], witness[target])
    return value


def decode_source_review(raw):
    return _decode(raw, validate_source_review)


def _user_fact(value):
    closed(value, ('kind','thread_id','turn_id','message_id','text_sha256','disposition',
                   'raw','typed','raw_response_id','text','review_status'))
    need(value['kind'] == 'USER_TYPED'
         and value['review_status'] == 'EXTERNAL_SEMANTIC_REVIEW_REQUIRED_NOT_AUTHORITY', 'USER_FACT')
    for key in ('thread_id','turn_id','message_id','raw_response_id'):
        _id(value[key])
    _hash(value['text_sha256'])
    need(type(value['text']) is str
         and sha256(value['text'].encode()).hexdigest() == value['text_sha256'], 'USER_TEXT')
    _pair({'human':{k:value[k] for k in ('thread_id','turn_id','message_id','text_sha256')},
           **{k:value[k] for k in ('raw','typed','disposition')}})


def _assistant_fact(value):
    closed(value, ('pair','task','context','terminal'))
    pair = closed(value['pair'], ('profile','authority','kind','thread_id','turn_id',
         'message_id','phase','text_parts','text_parts_sha256','completed_at_ms',
         'raw','typed','raw_payload_sha256','typed_payload_sha256','retention_status','qa_status'))
    need(pair['profile'] == 'GROUP_NATIVE_ASSISTANT_PAIR_FACTS_V1'
         and pair['authority'] is False and pair['kind'] == 'ASSISTANT_PAIR_FACTS'
         and pair['retention_status'] == 'UNVERIFIED' and pair['qa_status'] == 'UNASSESSED', 'QA_PAIR_PROFILE')
    for key in ('thread_id','turn_id','message_id'):
        _id(pair[key])
    need(pair['phase'] in (None,'commentary','partial_answer','final_answer'), 'QA_PHASE')
    seq(pair['text_parts'], lambda x: need(type(x) is str, 'QA_TEXT'), 1, 1024)
    equal(pair['text_parts_sha256'], digest(pair['text_parts']))
    for key in ('raw_payload_sha256','typed_payload_sha256'):
        _hash(pair[key])
    if pair['completed_at_ms'] is not None:
        _int(pair['completed_at_ms'])
    for key in ('raw','typed'):
        _ref(pair[key])
    for key in ('task','context','terminal'):
        _ref(value[key]); need(value[key]['source_id'] == pair['raw']['source_id'], 'QA_SOURCE')
    need(pair['raw']['source_id'] == pair['typed']['source_id']
         and value['task']['ordinal'] < value['context']['ordinal']
         < pair['raw']['ordinal'] < pair['typed']['ordinal'] < value['terminal']['ordinal'], 'QA_ORDER')


def validate_observation(value):
    keys = ('schema','profile','authority','material_sha256','semantic_scope_sha','role_threads',
            'sources','record_count','permission_facts','permission_facts_sha256','retention_summary',
            'qa_adoption_status','assistant_retention_status','authority_producer')
    profile(value, keys, OBSERVATION_PROFILE, 2)
    for key in ('material_sha256','semantic_scope_sha','permission_facts_sha256'):
        _hash(value[key])
    seq(value['role_threads'], _role_thread, 1, 4)
    _source_list(value['sources'])
    _int(value['record_count'], 1, 500000)
    need(value['record_count'] == sum(x['record_count'] for x in value['sources']), 'STREAM_COUNT')
    permission = closed(value['permission_facts'], ('profile','original_user_scope','users',
            'config_bindings','task_bindings','selected_assistant_facts','qa_sources',
            'semantic_scope_sha','allowed_read_scope','original_expires_policy'))
    need(permission['profile'] == 'GROUP_SOURCE_PERMISSION_FACTS_V2', 'PERMISSION_PROFILE')
    equal(value['permission_facts_sha256'], digest(permission))
    equal(value['semantic_scope_sha'], permission['semantic_scope_sha'])
    closed(permission['original_user_scope'], ('semantic_scope_sha','human_refs'))
    equal(value['semantic_scope_sha'], permission['original_user_scope']['semantic_scope_sha'])
    seq(permission['original_user_scope']['human_refs'], _human, 1, 16)
    seq(permission['users'], _user_fact, 1, 1024)
    equal([x for x in permission['original_user_scope']['human_refs']],
          [{k:u[k] for k in ('thread_id','turn_id','message_id','text_sha256')}
           for u in permission['users'] if u['disposition'] == 'ORIGINAL_REQUEST'])
    for key, category in (('config_bindings','CONFIG_NON_AUTH'), ('task_bindings','TASK_CONTROL')):
        seq(permission[key], _record_binding)
        need(all(x['category'] == category for x in permission[key]), 'PERMISSION_BINDING')
    seq(permission['selected_assistant_facts'], _assistant_fact, 1, 128)
    seq(permission['qa_sources'], _evidence, 1, 3072)
    need(all(x['kind'] == 'QA' for x in permission['qa_sources']), 'QA_ROLE')
    closed(permission['allowed_read_scope'], ('family_anchor_sha','covenant_sha'))
    for checksum in permission['allowed_read_scope'].values():
        _hash(checksum)
    closed(permission['original_expires_policy'], ('mode','not_after'))
    need(permission['original_expires_policy']['mode'] == 'SOURCE_BOUND_CURRENT', 'EXPIRY')
    _deadline(permission['original_expires_policy']['not_after'])
    retention = closed(value['retention_summary'], ('whole_record_count','control_fragment_record_count',
                                                   'required_retained_raw_bytes','state_charge_bytes'))
    for key in ('whole_record_count','control_fragment_record_count'):
        _int(retention[key], 0, value['record_count'])
    need(retention['whole_record_count'] + retention['control_fragment_record_count']
         == sum(x['control_record_count'] for x in value['sources']), 'RETENTION_COUNT')
    for key in ('required_retained_raw_bytes','state_charge_bytes'):
        _int(retention[key], 0, MAX_RETAINED)
    need(retention['required_retained_raw_bytes'] + retention['state_charge_bytes'] <= MAX_RETAINED
         and retention['required_retained_raw_bytes'] == sum(x['control_raw_bytes'] for x in value['sources']), 'RETENTION_LIMIT')
    need(value['qa_adoption_status'] == 'UNPROVEN_REQUIRES_HOST_ARTIFACT_AND_ADOPTION_REVIEW'
         and value['assistant_retention_status'] == 'UNVERIFIED' and value['authority_producer'] == 'NONE', 'FACTS_ONLY')
    return value
BASELINE_KEYS = ('schema', 'profile', 'authority', 'native_qualification_status', 'role_threads', 'original_user_scope', 'source_identities', 'interpretation_starts', 'retained_bindings', 'typed_raw_pairs', 'reviewed_other_records', 'selected_assistant_pairs', 'qa_sources', 'semantic_scope_sha', 'allowed_read_scope', 'expires_policy', 'stream_contract', 'baseline_commitments')
CATALOG_EXTENSION_KEYS = ('schema', 'profile', 'mode', 'baseline_source_sha', 'runtime_policy_path', 'runtime_policy_sha', 'native_contract_sha', 'native_qualification')
CURRENT_BINDING_KEYS = ('schema', 'profile', 'authority', 'binding_mode', 'configuration_sha', 'baseline_source_material_sha', 'origin_source_material_sha', 'runtime_source_policy_sha', 'baseline_acceptance_sha', 'native_contract_sha', 'semantic_scope_sha', 'entry_epoch_sha', 'capture_started_at_ms', 'qualified_not_after_ms', 'source_observation_profile', 'source_observation_sha', 'sources', 'qualification_generation_sha', 'permission_facts_sha', 'prefix_proofs', 'prefix_preservation_sha', 'reviewed_delta_sha')
RUNTIME_POLICY_KEYS = ('schema', 'profile', 'authority', 'core_scope_sha', 'binding_sha', 'baseline_source_sha', 'origin_source_descriptor', 'semantic_scope_sha', 'native_contract_sha', 'role_descriptors_sha', 'qa_selection_sha', 'allowed_non_user_protocol', 'known_user_reviews', 'config_equivalence_rules', 'original_input_not_after_ms', 'original_source_rights_expiry')
SOURCE_REVIEW_KEYS = ('schema', 'profile', 'authority', 'family_id', 'registration_sha', 'semantic_scope_sha', 'original_source_material_sha', 'current_source_material_sha', 'previous_review_sha', 'helper_acceptance_sha', 'original_human_refs_sha', 'known_user_classifications', 'qualification_generation_sha', 'observed_at_ms', 'not_after_ms', 'binding_mode', 'runtime_source_policy_sha', 'current_binding', 'current_binding_sha', 'prefix_preservation_sha', 'reviewed_delta_sha')
STATIC_ACCEPTANCE_KEYS = ('schema', 'profile', 'authority', 'configuration_sha', 'semantic_adoption_sha', 'source_material_sha', 'artifact_inventory_sha', 'first_covenant_sha', 'read_contract_sha', 'candidate_scope', 'unarmed_sha', 'helper_dependencies', 'retention_evidence', 'permitted_arm', 'source_binding_mode', 'runtime_source_policy_sha', 'baseline_native_qualification', 'native_contract_sha')
BASELINE_COMMITMENT_KEYS = ('source_id', 'end_byte', 'absolute_end_ordinal', 'prefix_sha256', 'ordered_records_sha256', 'control_sha256')
CHECKPOINT_KEYS = ('end', 'absolute_end_ordinal', 'prefix_sha256', 'ordered_records_sha256', 'control_sha256')
CONFIG_EQUIVALENCE_RULE_KEYS = ('kind', 'rule', 'reference')
CURRENT_STREAM_SUMMARY_KEYS = ('schema', 'authority', 'source_id', 'thread_sha256', 'source_registration_sha256', 'interpretation_start', 'interpretation_start_ordinal', 'prefix_bytes', 'prefix_sha256', 'record_count', 'first_ordinal', 'end_ordinal_exclusive', 'category_counts', 'request_scope_sha256', 'generation_sha256', 'ordered_records_sha256', 'control_sha256', 'control_record_count', 'control_raw_bytes', 'checkpoints')
INTERPRETATION_START_KEYS = ('source_id', 'reference')
KNOWN_USER_REVIEW_KEYS = ('human', 'raw', 'typed', 'disposition', 'review_artifact_sha')
ORIGIN_SOURCE_DESCRIPTOR_KEYS = ('source_profile', 'sha256', 'size')
PREFIX_PROOF_KEYS = ('source_id', 'baseline_kind', 'baseline_locator_sha', 'baseline_end', 'baseline_prefix_sha256', 'baseline_ordered_sha256', 'baseline_control_sha256', 'current_checkpoint')
SOURCE_IDENTITY_KEYS = ('source_id', 'thread_id', 'path_utf8_sha256', 'device', 'inode', 'session_meta_sha256', 'metadata_ordinal')
