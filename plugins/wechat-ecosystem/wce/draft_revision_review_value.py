"""Pure historical values for the one reviewed source-continuation profile.

No grant, current-source observation, path access or expiry decision occurs here.
The caller supplies an externally trusted expected digest and the immutable
original Case/registration; their existing registration validator remains required.
Evidence paths are inert descriptors. Whole-value commitments are not interpreted.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math

from .contracts import WCEError
from .service import canonical, digest

REVIEW_PROFILE = 'SOURCE_REVIEW_CONTINUATION_V1'
CLAIM_PROFILE = 'SOURCE_REVIEWED_CLAIM_V1'
ERROR = 'DRAFT_REVISION_SOURCE_REVIEW_HOLD'
_LIMIT = 2 * 1024 * 1024
_JOURNAL = 'EXACT_DRAFT_REVISION_JOURNAL_V4'
_PROVIDER = 'OFFICIAL_OWN_NEWS_REVISION_V1'
_SINGLE = 'EXACT_SINGLE_TEXT_MATERIAL'
_IMAGE = 'EXACT_TEXT_LOCAL_IMAGE_NON_GRANT'
_IMAGE_REASON = 'NON_GRANT_OTHER_ARTICLE_RESEARCH_AND_REFERENCE_IMAGE'
_GROUP_REASON = 'NON_GRANT_FUTURE_DRAFT_GROUPING_POLICY'
_CLARIFY_REASON = 'NON_GRANT_GROUP08_CLARIFICATION_NO_ORIGINAL_CASE_CHANGE'
_RESUME_REASON = 'GENUINE_COMPOSER_RESUME_EXACT_ORIGINAL_CASE_ONLY'
_PENDING = 'MATERIALS_PENDING_FINAL_PROFILE_AND_MANIFEST_REVIEW_NO_PUBLICATION_OR_PRODUCT_PERMISSION'
_TOP = frozenset('acceptance all_retained_record_bindings all_retained_record_bindings_sha256 authority completeness_origin creation_precondition external_trust_root image_evidence instance_profile inventory_evidence material_review_evidence non_grant_context_raw old_seven_pair_evidence opaque_envelope_policy origin origin_pins pair_material_evidence public_producer_research purpose reviewed_new_users schema scope_rules source_windows'.split())
_CASE = frozenset('profile id source_key binding target original_step source_sha registration_proof_sha input_sha targets maximum_reads maximum_updates provider_profile target_basis'.split())
_ORIGIN = frozenset('acquisition_sha256 add_upload_delete_publish_maximum binding case_id connection_id historical_register_evidence input_sha256 maximum_reads maximum_updates new_html_sha256 origin_case_canonical_sha256 origin_case_digest_codec origin_profile original_save_key original_step_sha256 provider_profile registration_proof_sha256 revision_id source_key source_sha256 target_basis_sha256 target_reference_sha256'.split())
_PAIR = frozenset('authority candidate_raw_ordinals group message_id profile raw raw_ordered_content_sha256 raw_response_id_utf8_sha256 retained_complete retained_identity_uses_raw_utf8_hash thread_id turn_id typed typed_ordered_content_sha256'.split())
_RECORD = frozenset('category payload_canonical_sha256 reference safe_projection_sha256'.split())
_REF = frozenset('source_id ordinal byte_start byte_end raw_line_sha256'.split())
_SOURCE = frozenset('source_id path device inode thread_id start_offset start_ordinal preceding_sha256 session_meta_sha256 metadata_ordinal'.split())
_WINDOW = frozenset('path_utf8_sha256 preceding_sha256 prefix_bytes prefix_sha256 retained_records session_meta_sha256 source_registration_sha256 start_offset start_ordinal thread_id'.split())
_PIN = frozenset('thread_id turn_id message_id text_sha256 purpose'.split())
_SCOPE = {'fields': ['content'], 'get_maximum': 5, 'update_maximum': 1,
          'add_maximum': 0, 'upload_maximum': 0, 'delete_maximum': 0, 'publish_maximum': 0}


def _need(condition):
    if not condition:
        raise WCEError(ERROR)


def _keys(value, keys):
    _need(type(value) is dict and set(value) == set(keys))


def _hash(value):
    _need(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value))


def _text(value, maximum=4096):
    _need(type(value) is str and 0 < len(value.encode('utf-8')) <= maximum and '\x00' not in value)


def _int(value, minimum=0, maximum=2**63-1):
    _need(type(value) is int and minimum <= value <= maximum)


def _same(actual, expected):
    # JSON equality alone treats False == 0 and True == 1.
    _need(canonical(actual) == canonical(expected))


def _plain(value, depth=0, budget=None):
    if budget is None:
        budget = [100000, _LIMIT]
    budget[0] -= 1
    budget[1] -= 2
    _need(depth <= 32 and budget[0] >= 0 and budget[1] >= 0)
    kind = type(value)
    if kind is dict:
        _need(all(type(k) is str for k in value))
        for k, v in value.items():
            _need(len(k) <= budget[1])
            budget[1] -= len(k.encode('utf-8')) + 2
            _plain(v, depth+1, budget)
    elif kind is list:
        for v in value:
            _plain(v, depth+1, budget)
    elif kind is str:
        _need(len(value) <= budget[1])
        budget[1] -= len(value.encode('utf-8'))
    elif kind is float:
        _need(math.isfinite(value))
        budget[1] -= 32
    elif kind is int:
        # Bound numeric encoding work before canonical JSON allocates its text.
        _need(value.bit_length() <= 16384)
        budget[1] -= max(1, (value.bit_length()*30103)//100000+1) + 1
    else:
        _need(kind in (bool, type(None)))
        budget[1] -= 5
    _need(budget[1] >= 0)


def _snapshot(value):
    _plain(value)
    _need(len(canonical(value).encode('utf-8')) <= _LIMIT)
    return deepcopy(value)


def _pairs(items):
    result = {}
    for key, value in items:
        _need(key not in result)
        result[key] = value
    return result


def _parse(raw, maximum=_LIMIT):
    _need(type(raw) is bytes and 0 < len(raw) <= maximum)
    def reject(_):
        raise WCEError(ERROR)
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=reject)
    _plain(result)
    return result


def _descriptor(value, *, sized=True):
    _keys(value, {'path', 'sha256', 'bytes'} if sized else {'path', 'sha256'})
    _text(value['path'])
    _hash(value['sha256'])
    if sized:
        _int(value['bytes'], 1)


def _case(case):
    """Bind the already validated original Case; not a selector/grant validator."""
    _keys(case, _CASE)
    _same([case['profile'], case['provider_profile'], case['maximum_reads'], case['maximum_updates']],
          [_JOURNAL, _PROVIDER, 5, 1])
    for key in _CASE - {'profile', 'targets', 'maximum_reads', 'maximum_updates', 'provider_profile', 'target_basis'}:
        _hash(case[key])
    _need(type(case['target_basis']) is dict and type(case['targets']) is list)


def _origin(manifest, case, registration):
    _case(case)
    _keys(registration, 'profile scope source_sha input original derived acquisition review'.split())
    _need(registration['profile'] == 'HOST_REVIEWED_ORIGINAL_NEWS_CONTENT_CORRECTION_V1')
    _same(registration['scope'], _SCOPE)
    _need(digest(registration) == case['registration_proof_sha'])
    value = registration['input']
    _need(type(value) is dict and digest(value) == case['input_sha'])
    _keys(value['changes'], {'content'})
    _text(value['changes']['content'], _LIMIT)
    for actual, expected in ((registration['source_sha'], case['source_sha']),
        (value['source_binding_sha'], case['source_sha']), (value['binding'], case['binding']),
        (value['reference_sha'], case['target']), (value['original_step_sha'], case['original_step'])):
        _need(actual == expected)
    _same(value['target_basis'], case['target_basis'])
    spec = registration['acquisition']
    _keys(spec, 'owner_thread state_path session_root windows artifacts original_save_key artifact_root_identity'.split())
    for key in ('owner_thread', 'state_path', 'session_root', 'original_save_key'):
        _text(spec[key])
    _need(type(spec['artifact_root_identity']) is list and len(spec['artifact_root_identity']) == 2)
    for number in spec['artifact_root_identity']:
        _int(number)
    _keys(spec['artifacts'], 'root old_relative_path old_sha256 new_relative_path new_sha256 images'.split())
    for key in ('root', 'old_relative_path', 'new_relative_path'):
        _text(spec['artifacts'][key])
    for key in ('old_sha256', 'new_sha256'):
        _hash(spec['artifacts'][key])
    _need(spec['artifacts']['new_sha256'] == value['source_relation']['new_source_sha256'])
    review = registration['review']
    _keys(review, 'helper_sha256 review_sha256 dependencies_sha256 original_save_key human_pins_sha256'.split())
    for key in set(review) - {'original_save_key'}:
        _hash(review[key])
    _need(review['original_save_key'] == spec['original_save_key'])
    origin = manifest['origin']
    _keys(origin, _ORIGIN)
    fixed = {'acquisition_sha256': digest(spec), 'binding': case['binding'], 'case_id': case['id'],
        'input_sha256': case['input_sha'], 'origin_case_canonical_sha256': digest(case),
        'origin_case_digest_codec': 'PRODUCTION_SERVICE_CANONICAL_JSON_UTF8_V1',
        'origin_profile': case['profile'], 'provider_profile': case['provider_profile'],
        'original_save_key': spec['original_save_key'], 'original_step_sha256': case['original_step'],
        'registration_proof_sha256': case['registration_proof_sha'], 'source_key': case['source_key'],
        'source_sha256': case['source_sha'], 'target_basis_sha256': digest(case['target_basis']),
        'target_reference_sha256': case['target'], 'maximum_reads': 5, 'maximum_updates': 1,
        'add_upload_delete_publish_maximum': 0,
        'revision_id': digest({'case': case['id'], 'profile': case['profile']}),
        'new_html_sha256': spec['artifacts']['new_sha256'],
        'connection_id': registration['original']['manifest']['binding']['connection']}
    for key, expected in fixed.items():
        _same(origin[key], expected)
    _hash(origin['new_html_sha256'])
    _text(origin['connection_id'])
    history = origin['historical_register_evidence']
    _keys(history, {'kind', 'not_live_state_proof', 'path', 'sha256'})
    _same(history['not_live_state_proof'], True)
    _need(history['kind'] == 'PRESERVED_IMMUTABLE_REGISTER_EVENT_FROM_VERIFIED_030_MAINTENANCE_BACKUP')
    _descriptor({k: history[k] for k in ('path', 'sha256')}, sized=False)
    return spec


def _windows(manifest, spec):
    windows = manifest['source_windows']
    _need(type(windows) is list and len(windows) == 2)
    _need(type(spec['windows']) is list and len(spec['windows']) == 2)
    _need(type(manifest['origin_pins']) is list and len(manifest['origin_pins']) == 2)
    sources, pin_ids = {}, []
    for index, (window, item, pins) in enumerate(zip(windows, spec['windows'], manifest['origin_pins'])):
        _keys(window, _WINDOW)
        _keys(item, {'source', 'pins'})
        source = item['source']
        _keys(source, _SOURCE)
        for key in ('source_id', 'path', 'thread_id'):
            _text(source[key])
        for key in ('device', 'inode', 'start_offset', 'start_ordinal', 'metadata_ordinal'):
            _int(source[key])
        for key in ('preceding_sha256', 'session_meta_sha256'):
            _hash(source[key])
        source_id = source['source_id']
        _need(source_id not in sources)
        _need(source['thread_id'] not in [s['source']['thread_id'] for s in sources.values()])
        commitment = dict(source)
        commitment['path_sha256'] = sha256(commitment.pop('path').encode('utf-8')).hexdigest()
        _need(window['source_registration_sha256'] == digest(commitment))
        _need(window['path_utf8_sha256'] == commitment['path_sha256'])
        for key in ('thread_id', 'start_offset', 'start_ordinal', 'preceding_sha256', 'session_meta_sha256'):
            _same(window[key], source[key])
        _int(window['prefix_bytes'], source['start_offset']+1)
        _hash(window['prefix_sha256'])
        _same(window['retained_records'], (79, 89)[index])
        _same(pins, item['pins'])
        _need(type(pins) is list and len(pins) == (3, 4)[index])
        for pin in pins:
            _keys(pin, _PIN)
            for key in ('thread_id', 'turn_id', 'message_id'):
                _text(pin[key])
            _hash(pin['text_sha256'])
            _need(pin['purpose'] in {'initial_edit', 'refinement', 'resume_same_case'})
            _need(pin['thread_id'] == source['thread_id'])
            identity = tuple(pin[k] for k in ('thread_id', 'turn_id', 'message_id'))
            _need(identity not in pin_ids)
            pin_ids.append(identity)
        sources[source_id] = {'source': source, 'window': window}
    return sources, pin_ids


def _records(manifest, sources):
    records = manifest['all_retained_record_bindings']
    _need(type(records) is list and len(records) == 168)
    _need(digest(records) == manifest['all_retained_record_bindings_sha256'])
    by_ref = {}
    for record in records:
        _keys(record, _RECORD)
        _need(record['category'] in {'contexts', 'tasks', 'typed_users', 'user_responses'})
        _hash(record['payload_canonical_sha256'])
        _hash(record['safe_projection_sha256'])
        ref = record['reference']
        _keys(ref, _REF)
        _hash(ref['raw_line_sha256'])
        _need(ref['source_id'] in sources)
        source, window = sources[ref['source_id']]['source'], sources[ref['source_id']]['window']
        _int(ref['ordinal'], source['start_ordinal'])
        _int(ref['byte_start'], source['start_offset'], window['prefix_bytes']-1)
        _int(ref['byte_end'], ref['byte_start']+1, window['prefix_bytes'])
        identity = (ref['source_id'], ref['ordinal'])
        _need(identity not in by_ref)
        by_ref[identity] = record
    for source_id, item in sources.items():
        refs = sorted((r['reference'] for r in records if r['reference']['source_id'] == source_id), key=lambda r: r['ordinal'])
        _need(len(refs) == item['window']['retained_records'])
        _need(all(a['byte_end'] <= b['byte_start'] for a, b in zip(refs, refs[1:])))
    return by_ref


def _pairing(manifest, sources, pin_ids, by_ref):
    old, new = manifest['old_seven_pair_evidence'], manifest['reviewed_new_users']
    _need(type(old) is list and len(old) == 7 and type(new) is list and len(new) == 7)
    used_raw, used_typed, identities, old_ids, reasons, images = set(), set(), set(), [], [], []
    for index, row in enumerate(old + new):
        fresh = index >= len(old)
        _keys(row, _PAIR | ({'authorizes_new_action_or_budget', 'disposition', 'full_text_sha256', 'support'} if fresh else set()))
        _same(row['authority'], False)
        _same(row['retained_identity_uses_raw_utf8_hash'], True)
        _need(row['group'] == ('NEW_TYPED' if fresh else 'OLD_PIN'))
        for key in ('thread_id', 'turn_id', 'message_id'):
            _text(row[key])
        identity = tuple(row[k] for k in ('thread_id', 'turn_id', 'message_id'))
        _need(identity not in identities)
        identities.add(identity)
        for key in ('raw_ordered_content_sha256', 'typed_ordered_content_sha256', 'raw_response_id_utf8_sha256'):
            _hash(row[key])
        refs = []
        for key, category, used in (('raw', 'user_responses', used_raw), ('typed', 'typed_users', used_typed)):
            record = row[key]
            _keys(record, _RECORD)
            _keys(record['reference'], _REF)
            ref = record['reference']
            pair_key = (ref['source_id'], ref['ordinal'])
            _need(pair_key in by_ref and pair_key not in used)
            _same(record, by_ref[pair_key])
            _need(record['category'] == category)
            _need(sources[ref['source_id']]['source']['thread_id'] == row['thread_id'])
            used.add(pair_key)
            refs.append(ref)
        _need(refs[0]['source_id'] == refs[1]['source_id'] and refs[0]['ordinal'] < refs[1]['ordinal'])
        _same(row['candidate_raw_ordinals'], [refs[0]['ordinal']])
        if not fresh:
            _need(row['profile'] == _SINGLE)
            _same(row['retained_complete'], True)
            old_ids.append(identity)
            continue
        _same(row['authorizes_new_action_or_budget'], False)
        _hash(row['full_text_sha256'])
        reason = row['disposition']
        reasons.append(reason)
        _need(reason in {_IMAGE_REASON, _GROUP_REASON, _CLARIFY_REASON, _RESUME_REASON})
        image = reason == _IMAGE_REASON
        _need(row['profile'] == (_IMAGE if image else _SINGLE))
        _same(row['retained_complete'], not image)
        support = row['support']
        support_keys = {'api_content_vector_sha256', 'evidence'}
        if reason in {_IMAGE_REASON, _GROUP_REASON}:
            support_keys.add('semantic_review_evidence')
        if reason == _RESUME_REASON:
            support_keys.add('native_standard_observation_sha256')
        _keys(support, support_keys)
        _hash(support['api_content_vector_sha256'])
        _descriptor(support['evidence'])
        if 'semantic_review_evidence' in support:
            _descriptor(support['semantic_review_evidence'])
        if 'native_standard_observation_sha256' in support:
            _hash(support['native_standard_observation_sha256'])
        if image:
            images.append(row)
    _same(old_ids, pin_ids)
    _same(reasons, [_IMAGE_REASON, _GROUP_REASON, *([_CLARIFY_REASON]*4), _RESUME_REASON])
    contexts = manifest['non_grant_context_raw']
    _need(type(contexts) is list and len(contexts) == 11)
    for context in contexts:
        _keys(context, _RECORD | {'role'})
        _need(context['role'] in {'harness', 'agents_md'})
        record = {k: context[k] for k in _RECORD}
        _keys(record['reference'], _REF)
        key = (record['reference']['source_id'], record['reference']['ordinal'])
        _need(key in by_ref and key not in used_raw and record['category'] == 'user_responses')
        _same(record, by_ref[key])
        used_raw.add(key)
    _need(used_raw == {k for k, r in by_ref.items() if r['category'] == 'user_responses'})
    _need(used_typed == {k for k, r in by_ref.items() if r['category'] == 'typed_users'})
    return images[0]


def _schema(manifest):
    _keys(manifest, _TOP)
    fixed = {'schema': 'R219_EXACT_SOURCE_REVIEW_MATERIAL_MANIFEST_V1',
        'purpose': 'REVIEW_ONE_EXISTING_ORIGINAL_CASE_NOT_A_GRANT', 'authority': False,
        'acceptance': _PENDING, 'completeness_origin': 'SUPPORTED_TYPED_API_AND_RAW_ALL_PARTS_EXACT_INSTANCE_V1',
        'creation_precondition': {'first_source_review_only': True, 'previous_review_sha256': None, 'reads': 0, 'state': 'PREPARING', 'writes': 0},
        'external_trust_root': {'helper_and_launcher_hashes_not_back_embedded_here': True,
            'independent_arm_receipt_pins_final_armed_bytes': True, 'manifest_pinned_before_helper_review': True,
            'only_two_REVIEW_constants_may_change_on_arm': True,
            'required': 'EXACT_REVIEWED_MAINTENANCE_PACKAGE_NOT_MODEL_OR_MCP_ARGUMENT', 'review_pins_unarmed_launcher': True},
        'scope_rules': {'all_existing_record_value_changes_HOLD': True, 'all_new_or_changed_USER_HOLD': True,
            'latest_positive_composer_required': True, 'no_implicit_scope_time_or_budget_refresh': True,
            'no_runtime_attachment_path_reads': True, 'ordinary_non_USER_append_requires_fresh_full_scan': True,
            'origin_hashes_and_seven_pins_unchanged': True, 'review_labels_are_not_grants': True},
        'opaque_envelope_policy': {'adoption': 'REQUIRES_EXPLICIT_CASE_SPECIFIC_PROFILE_REVIEW',
            'disposition': 'EXACT_FROZEN_CANONICAL_AND_RAWLINE_BINDING_ONLY_NO_INTERPRETATION_OR_GRANT',
            'fields': ['CodexHarnessMetadata.user_input_order', 'RetainedSource.revision', 'McpAttribution.sources', 'ContentItemProvenance.Harness.hook'],
            'keysets_verified': True, 'task_and_context_outer_shapes': 'ALL_RECORDS_BOUND_NOT_GENERAL_SCHEMA_VALIDATED', 'value_schema_validated': False}}
    for key, expected in fixed.items():
        _same(manifest[key], expected)
    for key in ('image_evidence', 'inventory_evidence', 'material_review_evidence', 'pair_material_evidence'):
        _descriptor(manifest[key])
    instance = manifest['instance_profile']
    _keys(instance, {'name', 'path', 'sha256'})
    _need(instance['name'] == 'HOST_REVIEWED_NON_GRANT_TEXT_LOCAL_IMAGE_EXACT_V1')
    _descriptor({k: instance[k] for k in ('path', 'sha256')}, sized=False)
    public = manifest['public_producer_research']
    _keys(public, {'commit', 'installed_binary_commit_equivalence', 'path', 'sha256'})
    _need(type(public['commit']) is str and len(public['commit']) == 40 and all(c in '0123456789abcdef' for c in public['commit']))
    _need(public['installed_binary_commit_equivalence'] == 'UNPROVEN')
    _descriptor({k: public[k] for k in ('path', 'sha256')}, sized=False)


def _asset(raw, descriptor, image):
    _need(type(raw) is bytes and 0 < len(raw) <= 64*1024 and len(raw) == descriptor['bytes'])
    _need(sha256(raw).hexdigest() == descriptor['sha256'])
    asset = _parse(raw, 64*1024)
    _keys(asset, 'authority before_after_identity_equal logical_alias logical_path_sha256 message_id physical_path_sha256 png_signature profile raw_inline_correspondence scope sha256 size thread_id turn_id'.split())
    for key, value in {'authority': False, 'before_after_identity_equal': True,
        'logical_alias': 'EXACT_MACOS_VAR_SYMLINK_VERIFIED', 'png_signature': True,
        'profile': 'SUPPORTED_API_USER_ATTACHMENT_READ_V1', 'raw_inline_correspondence': 'NOT_YET_COMPARED',
        'scope': 'ONE_EXPLICIT_USER_ATTACHMENT_ONLY'}.items():
        _same(asset[key], value)
    for key in ('logical_path_sha256', 'physical_path_sha256', 'sha256'):
        _hash(asset[key])
    _int(asset['size'], 1, 16*1024*1024)
    for key in ('message_id', 'thread_id', 'turn_id'):
        _need(asset[key] == image[key])
    return asset


def validate_manifest(manifest_raw: bytes, asset_raw: bytes, expected_manifest_sha: str,
                      case: dict, registration: dict) -> dict:
    """Validate pinned historical values; return detached manifest and asset.

    This checks the whole-asset witness, not the image/path component equations.
    The source observer must independently check those against current raw/typed
    bytes. The original registration validator remains the owner's responsibility.
    """
    try:
        _hash(expected_manifest_sha)
        _need(type(manifest_raw) is bytes and 0 < len(manifest_raw) <= _LIMIT)
        _need(sha256(manifest_raw).hexdigest() == expected_manifest_sha)
        manifest = _parse(manifest_raw)
        case, registration = _snapshot(case), _snapshot(registration)
        _schema(manifest)
        spec = _origin(manifest, case, registration)
        sources, pin_ids = _windows(manifest, spec)
        records = _records(manifest, sources)
        image = _pairing(manifest, sources, pin_ids, records)
        asset = _asset(asset_raw, manifest['image_evidence'], image)
        return {'manifest': manifest, 'asset': asset, 'manifest_sha': expected_manifest_sha}
    except (WCEError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise WCEError(ERROR) from None


def review_id(case_id, manifest_sha, previous=None):
    """Stable first-review identity; observation time grants no new identity."""
    _hash(case_id)
    _hash(manifest_sha)
    _need(previous is None)
    return digest({'profile': REVIEW_PROFILE, 'case_id': case_id,
                   'manifest_sha': manifest_sha, 'previous_review_sha': previous})


def validate_review_proof(proof: dict, expected_sha: str, case, registration) -> dict:
    """Replay immutable creation integrity without current TTL/state decisions."""
    try:
        _hash(expected_sha)
        proof = _snapshot(proof)
        case, registration = _snapshot(case), _snapshot(registration)
        _keys(proof, 'schema profile origin_profile binding case_id case_sha revision_id review_id previous_review_sha manifest_raw manifest_sha asset_raw acceptance creation'.split())
        # Immutable proof files use canonical JSON plus one terminal newline.
        _need(sha256((canonical(proof)+'\n').encode('utf-8')).hexdigest() == expected_sha)
        _same(proof['schema'], 2)
        for key, value in {'profile': REVIEW_PROFILE, 'origin_profile': case['profile'], 'binding': case['binding'],
            'case_id': case['id'], 'case_sha': digest(case), 'previous_review_sha': None,
            'revision_id': digest({'case': case['id'], 'profile': case['profile']}),
            'review_id': review_id(case['id'], proof['manifest_sha'])}.items():
            _same(proof[key], value)
        _keys(proof['acceptance'], 'helper_sha dependencies_sha review_sha unarmed_launcher_sha arm_receipt_sha candidate_scope'.split())
        for value in proof['acceptance'].values():
            _hash(value)
        creation = proof['creation']
        _keys(creation, 'journal_seq journal_sha reads writes state observed_at'.split())
        _int(creation['journal_seq'], 1)
        _hash(creation['journal_sha'])
        for key, value in {'reads': 0, 'writes': 0, 'state': 'PREPARING'}.items():
            _same(creation[key], value)
        observed = creation['observed_at']
        _need(type(observed) in (int, float) and math.isfinite(observed) and observed > 0)
        _need(type(proof['manifest_raw']) is str and type(proof['asset_raw']) is str)
        return validate_manifest(proof['manifest_raw'].encode('utf-8'), proof['asset_raw'].encode('utf-8'),
                                 proof['manifest_sha'], case, registration)
    except (WCEError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise WCEError(ERROR) from None
