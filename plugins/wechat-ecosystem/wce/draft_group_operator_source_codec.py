"""Unarmed pure Operator-source format proposal, never an authority issuer.

Only standard-library JSON/hash operations occur here. No file, SQL, clock,
service, registry, grant, Native source, or network operation is performed.
Valid JSON is a detached non-authoritative declaration, not runtime evidence.
"""
from hashlib import sha256
import json
import re


CONTENT_SOURCE_TYPE = 'OPERATOR_ATTESTED_SELECTED_REQUEST_V1'
ACCOUNT_SOURCE_KIND = 'OPERATOR_ATTESTED'
SOURCE_PROFILE = 'GROUP_BATCH_OPERATOR_SELECTED_SOURCE_V1'
OBSERVATION_PROFILE = 'GROUP_CURRENT_OPERATOR_SOURCE_OBSERVATION_V1'
POLICY_PROFILE = 'GROUP_OPERATOR_SELECTED_RUNTIME_POLICY_V1'
SEMANTIC_PROFILE = 'HOST_GROUP_OPERATOR_SEMANTIC_ADOPTION_V1'
REQUEST_PROFILE = 'GROUP_OPERATOR_REQUEST_ID_V1'
ANCHOR_PROFILE = 'GROUP_OPERATOR_READ_FAMILY_ANCHOR_V1'
FIRST_PROOF_PROFILE = 'HOST_VERIFIED_OPERATOR_GROUP_READ_FIRST_V1'
REQUEST_WITNESS_PROFILE = 'GROUP_OPERATOR_READ_REQUEST_BINDING_V1'
FAMILY_ROOT_PROFILE = 'GROUP_OPERATOR_READ_FAMILY_ROOT_V1'
# Reserved for root's later producer/review integration; not decoded here.
SOURCE_FACTS_PROFILE = 'GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1'
SOURCE_REVIEW_PROFILE = 'GROUP_CURRENT_SOURCE_REVIEW_OPERATOR_V1'
PURPOSE = 'GROUP08_SAME_REQUEST'
MAX_BYTES = 2 * 1024 * 1024
MAX_NODES = 65536
MAX_DEPTH = 20
MAX_INTEGER = 2**63 - 1
MAX_MEMBERS = 28
ERROR_CODE = 'GROUP_OPERATOR_SOURCE_CODEC_HOLD'
PROFILES = (SOURCE_PROFILE, OBSERVATION_PROFILE, POLICY_PROFILE, SEMANTIC_PROFILE,
            REQUEST_PROFILE, ANCHOR_PROFILE, FIRST_PROOF_PROFILE,
            REQUEST_WITNESS_PROFILE, FAMILY_ROOT_PROFILE)
HEADER_KEYS = ('schema', 'profile', 'authority', 'content_source_type')
BINDING_KEYS = ('tenant', 'principal', 'client', 'session', 'connection',
                'account', 'resource', 'epoch', 'generation', 'source_kind')
REF_KEYS = ('path', 'sha256', 'size', 'generation')
REQUEST_FIELDS = ('platform_account_sha', 'stable_owner', 'original_queue_sha',
                  'original_request_set_sha', 'account_partition_sha')
SOURCE_KEYS = HEADER_KEYS + ('binding_sha', 'original_queue_sha',
    'operator_request_identity_sha', 'original_request_set_sha', 'account_partition_sha',
    'selection_ref', 'prepared_relation_inventory_ref', 'qa_set_ref',
    'postupload_mapping_ref', 'semantic_scope_sha', 'allowed_read_scope', 'expires_policy')
OBSERVATION_KEYS = HEADER_KEYS + ('source_material_sha', 'runtime_source_policy_sha',
    'binding_sha', 'operator_request_identity_sha', 'original_request_set_sha',
    'account_partition_sha', 'selection_sha', 'qa_set_sha', 'postupload_mapping_sha',
    'prepared_relations_sha', 'semantic_scope_sha', 'policy_fingerprint_sha',
    'stable_owner', 'epoch', 'generation', 'file_generation_sha',
    'proof_generation_sha', 'first_pass_sha', 'second_pass_sha',
    'collective_fence_sha', 'observed_at_ms', 'qualified_not_after_ms')
POLICY_KEYS = HEADER_KEYS + ('binding', 'core_scope_sha', 'source_material_sha',
    'semantic_scope_sha', 'operator_request_identity_sha', 'original_queue_sha',
    'original_request_set_sha', 'account_partition_sha', 'selection_sha', 'qa_set_sha',
    'postupload_mapping_sha', 'prepared_relations_sha', 'original_input_not_after_ms',
    'source_rights_expiry', 'allowed_read_scope')
SEMANTIC_KEYS = HEADER_KEYS + ('binding',) + REQUEST_FIELDS + (
    'operator_request_identity_sha', 'semantic_scope', 'qa_set_ref',
    'artifact_inventory_sha', 'original_root_evidence_sha', 'read_contract_sha',
    'source_rights_expiry')
DESCRIPTOR_KEYS = ('configuration_sha', 'semantic_adoption_sha', 'qa_adoption_sha',
    'artifact_inventory_sha', 'content_source_type', 'selection_sha',
    'operator_request_set_sha', 'prepared_relations_sha', 'postupload_mapping_sha',
    'operator_observation_profile', 'runtime_source_policy_sha', 'current_binding_sha')
REQUEST_KEYS = HEADER_KEYS + REQUEST_FIELDS
ANCHOR_KEYS = HEADER_KEYS + REQUEST_FIELDS + ('request_identity_sha', 'purpose')
FIRST_PROOF_KEYS = HEADER_KEYS + ('family_anchor_id', 'request_identity_sha',
    'covenant_sha', 'operator_source_evidence_sha', 'semantic_review_sha',
    'first_binding', 'first_directory', 'coordination', 'host_provenance',
    'observed_generation_sha', 'observed_ms', 'not_after_ms')
REQUEST_WITNESS_KEYS = HEADER_KEYS + REQUEST_FIELDS + ('request_identity_sha',
    'family_anchor_id', 'family_root_sha', 'first_covenant_sha', 'first_proof_sha')
FAMILY_ROOT_KEYS = HEADER_KEYS + ('family_anchor_id', 'request_identity_sha', 'anchor',
    'first_covenant_sha', 'first_proof_sha', 'first_binding', 'first_directory', 'coordination')

_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_APPID = re.compile(r'wx[0-9a-fA-F]{16}\Z')
_CREDENTIAL = re.compile(
    r'app[_-]?secret|(?:access|refresh)[_-]?token|'
    r'(?:[a-z0-9]+[_-])?api[_-]?key|client[_-]?secret|'
    r'password|authorization|cookie|session[_-]?key|private[_-]?key|'
    r'\bbearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----', re.I)


class OperatorSourceCodecError(ValueError):
    """A fixed safe code; no untrusted input is interpolated into errors."""
    def __init__(self):
        super().__init__(ERROR_CODE)


def _need(condition):
    if condition is not True:
        raise OperatorSourceCodecError()


def _plain(value):
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        _need(nodes <= MAX_NODES and depth <= MAX_DEPTH)
        kind = type(item)
        if kind is dict:
            _need(len(item) <= 4096 and all(type(key) is str for key in item))
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif kind is list:
            _need(len(item) <= 4096)
            stack.extend((child, depth + 1) for child in item)
        elif kind is str:
            _need(len(item) <= 4096 and _CREDENTIAL.search(item) is None
                  and not any(ord(char) < 32 or ord(char) == 127 for char in item))
            try:
                item.encode('utf-8')
            except UnicodeError:
                raise OperatorSourceCodecError() from None
        elif kind is int:
            _need(0 <= item <= MAX_INTEGER)
        else:
            # Floats (including finite floats) and custom hooks are excluded.
            _need(kind in (bool, type(None)))


def canonical(value):
    """Canonical JSON bytes without a newline, suitable for typed identities."""
    _plain(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
        raise OperatorSourceCodecError() from None
    _need(0 < len(raw) <= MAX_BYTES)
    return raw


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _closed(value, keys):
    _need(type(value) is dict and set(value) == set(keys))


def _sha(value):
    _need(type(value) is str and _HASH.fullmatch(value) is not None)


def _integer(value, low=0, high=MAX_INTEGER):
    _need(type(value) is int and low <= value <= high)


def _id(value):
    _need(type(value) is str and _ID.fullmatch(value) is not None)


def _header(value, profile, keys):
    _closed(value, keys)
    _need(type(value['schema']) is int and value['schema'] == 1
          and value['profile'] == profile and value['authority'] is False
          and value['content_source_type'] == CONTENT_SOURCE_TYPE)


def _owner(value):
    _closed(value, ('tenant', 'principal'))
    _id(value['tenant']); _id(value['principal'])


def _binding(value):
    _closed(value, BINDING_KEYS)
    for key in ('tenant', 'principal', 'client', 'session', 'connection'):
        _id(value[key])
    _need(type(value['account']) is str and _APPID.fullmatch(value['account']) is not None
          and value['resource'] == value['account']
          and value['source_kind'] == ACCOUNT_SOURCE_KIND)
    _integer(value['epoch'])
    _integer(value['generation'], 1)


def _ref(value):
    _closed(value, REF_KEYS)
    path = value['path']
    _need(type(path) is str and path.startswith('/') and '\\' not in path
          and ':' not in path)
    parts = path.split('/')[1:]
    _need(1 <= len(parts) <= 32 and all(part not in ('', '.', '..') for part in parts))
    _sha(value['sha256']); _integer(value['size'], 1, MAX_BYTES)
    _integer(value['generation'], 1)


def _rights(value):
    _closed(value, ('kind', 'not_after'))
    if value['kind'] == 'PERSISTENT_DELEGATION':
        _need(value['not_after'] is None)
    else:
        _need(value['kind'] == 'EXPLICIT_UNTIL')
        _integer(value['not_after'], 1)  # Epoch milliseconds.


def _members(value):
    _need(type(value) is list and 1 <= len(value) <= MAX_MEMBERS)
    for member in value:
        _id(member)
    _need(len(set(value)) == len(value))


def _read_scope(value):
    _closed(value, ('purpose', 'family_anchor_sha', 'account_partition_sha', 'member_ids'))
    _need(value['purpose'] == PURPOSE)
    _sha(value['family_anchor_sha']); _sha(value['account_partition_sha'])
    _members(value['member_ids'])


def _request_fields(value):
    _owner(value['stable_owner'])
    for key in ('platform_account_sha', 'original_queue_sha',
                'original_request_set_sha', 'account_partition_sha'):
        _sha(value[key])


def _request_view(value):
    return dict(schema=1, profile=REQUEST_PROFILE, authority=False,
                content_source_type=CONTENT_SOURCE_TYPE,
                **{key: value[key] for key in REQUEST_FIELDS})


def _anchor_view(value):
    return dict(schema=1, profile=ANCHOR_PROFILE, authority=False,
                content_source_type=CONTENT_SOURCE_TYPE,
                **{key: value[key] for key in REQUEST_FIELDS},
                request_identity_sha=digest(_request_view(value)), purpose=PURPOSE)


def _request(value):
    _header(value, REQUEST_PROFILE, REQUEST_KEYS)
    _request_fields(value)


def _anchor(value):
    _header(value, ANCHOR_PROFILE, ANCHOR_KEYS)
    _request_fields(value); _sha(value['request_identity_sha'])
    _need(value['purpose'] == PURPOSE
          and value['request_identity_sha'] == digest(_request_view(value)))


def _source(value):
    _header(value, SOURCE_PROFILE, SOURCE_KEYS)
    for key in ('binding_sha', 'original_queue_sha', 'operator_request_identity_sha',
                'original_request_set_sha', 'account_partition_sha', 'semantic_scope_sha'):
        _sha(value[key])
    for key in ('selection_ref', 'prepared_relation_inventory_ref', 'qa_set_ref',
                'postupload_mapping_ref'):
        _ref(value[key])
    _read_scope(value['allowed_read_scope'])
    _need(value['allowed_read_scope']['account_partition_sha'] == value['account_partition_sha'])
    _closed(value['expires_policy'], ('not_after',))
    _integer(value['expires_policy']['not_after'], 1)  # Epoch seconds; never rounded up.


def _observation(value):
    _header(value, OBSERVATION_PROFILE, OBSERVATION_KEYS)
    for key in OBSERVATION_KEYS:
        if key.endswith('_sha'):
            _sha(value[key])
    _owner(value['stable_owner'])
    _integer(value['epoch']); _integer(value['generation'], 1)
    _integer(value['observed_at_ms'], 1)
    _integer(value['qualified_not_after_ms'], value['observed_at_ms'] + 1)
    _need(value['first_pass_sha'] == value['second_pass_sha'] == value['file_generation_sha'])


def _policy(value):
    _header(value, POLICY_PROFILE, POLICY_KEYS)
    _binding(value['binding'])
    for key in POLICY_KEYS:
        if key.endswith('_sha'):
            _sha(value[key])
    _integer(value['original_input_not_after_ms'], 1)
    _rights(value['source_rights_expiry']); _read_scope(value['allowed_read_scope'])
    _need(value['account_partition_sha'] == value['allowed_read_scope']['account_partition_sha'])


def _semantic(value):
    _header(value, SEMANTIC_PROFILE, SEMANTIC_KEYS)
    _binding(value['binding']); _request_fields(value)
    for key in ('operator_request_identity_sha', 'artifact_inventory_sha',
                'original_root_evidence_sha', 'read_contract_sha'):
        _sha(value[key])
    _need(value['stable_owner'] == {key: value['binding'][key] for key in ('tenant', 'principal')}
          and value['operator_request_identity_sha'] == digest(_request_view(value)))
    _ref(value['qa_set_ref']); _rights(value['source_rights_expiry'])
    scope = value['semantic_scope']
    _closed(scope, ('purpose', 'connection_binding_sha', 'permitted_routes',
        'authorized_member_ids', 'qualify_subjects', 'execution_slots_ref',
        'required_read_purposes', 'forbidden_actions'))
    _need(scope['purpose'] == PURPOSE and scope['connection_binding_sha'] == digest(value['binding'])
          and scope['permitted_routes'] == ['NEW_ONLY_EXISTING_DELEGATION'])
    _members(scope['authorized_member_ids'])
    _need(type(scope['qualify_subjects']) is list and len(scope['qualify_subjects']) <= 8)
    for subject in scope['qualify_subjects']:
        _sha(subject)
    _need(len(set(scope['qualify_subjects'])) == len(scope['qualify_subjects']))
    _ref(scope['execution_slots_ref'])
    expected = ['QUALIFY', 'PREVIEW_ACCOUNT'] if scope['qualify_subjects'] else ['PREVIEW_ACCOUNT']
    _need(scope['required_read_purposes'] == expected
          and scope['forbidden_actions'] == ['publish', 'masssend', 'delete', 'unsupported_settings'])


def _directory(value):
    _closed(value, ('path_utf8_sha256', 'device', 'inode', 'owner_uid'))
    _sha(value['path_utf8_sha256'])
    for key in ('device', 'inode', 'owner_uid'):
        _integer(value[key], 1 if key == 'inode' else 0)


def _pair(value):
    _need(type(value) is list and len(value) == 2)
    for item in value:
        _integer(item)


def _coordination(value):
    _closed(value, ('platform_account_sha', 'anchor_identity',
                    'registry_parent_identity', 'coordination_pin_sha'))
    _sha(value['platform_account_sha']); _sha(value['coordination_pin_sha'])
    _pair(value['anchor_identity']); _pair(value['registry_parent_identity'])


def _first(value):
    _header(value, FIRST_PROOF_PROFILE, FIRST_PROOF_KEYS)
    for key in ('family_anchor_id', 'request_identity_sha', 'covenant_sha',
                'operator_source_evidence_sha', 'semantic_review_sha', 'observed_generation_sha'):
        _sha(value[key])
    _binding(value['first_binding']); _directory(value['first_directory'])
    _coordination(value['coordination'])
    provenance = value['host_provenance']
    _closed(provenance, ('helper_sha', 'dependencies_sha', 'unarmed_launcher_sha',
                        'pin_review_sha', 'arm_receipt_sha', 'code_scope'))
    for item in provenance.values():
        _sha(item)
    _integer(value['observed_ms'], 1)
    _integer(value['not_after_ms'], value['observed_ms'] + 1)


def _witness(value):
    _header(value, REQUEST_WITNESS_PROFILE, REQUEST_WITNESS_KEYS)
    _request_fields(value)
    for key in ('request_identity_sha', 'family_anchor_id', 'family_root_sha',
                'first_covenant_sha', 'first_proof_sha'):
        _sha(value[key])
    _need(value['request_identity_sha'] == digest(_request_view(value))
          and value['family_anchor_id'] == digest(_anchor_view(value)))


def _root(value):
    _header(value, FAMILY_ROOT_PROFILE, FAMILY_ROOT_KEYS)
    _anchor(value['anchor']); _binding(value['first_binding'])
    _directory(value['first_directory']); _coordination(value['coordination'])
    for key in ('family_anchor_id', 'request_identity_sha', 'first_covenant_sha', 'first_proof_sha'):
        _sha(value[key])
    _need(value['family_anchor_id'] == digest(value['anchor'])
          and value['request_identity_sha'] == value['anchor']['request_identity_sha']
          and value['anchor']['stable_owner'] == {
              key: value['first_binding'][key] for key in ('tenant', 'principal')}
          and value['anchor']['platform_account_sha'] == value['coordination']['platform_account_sha'])


_VALIDATORS = dict(zip(PROFILES, (_source, _observation, _policy, _semantic,
    _request, _anchor, _first, _witness, _root)))


def validate(value, *, expected_profile):
    """Detached declaration only; the required expected type prevents fallback."""
    _need(type(expected_profile) is str and expected_profile in PROFILES)
    _plain(value)
    _VALIDATORS[expected_profile](value)
    return json.loads(canonical(value))


def encode(value, *, expected_profile):
    raw = canonical(validate(value, expected_profile=expected_profile)) + b'\n'
    _need(len(raw) <= MAX_BYTES)
    return raw


def _unique(items):
    result = {}
    for key, value in items:
        _need(key not in result)
        result[key] = value
    return result


def decode(raw, *, expected_profile):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                           parse_constant=lambda _: _need(False))
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise OperatorSourceCodecError() from None
    checked = validate(value, expected_profile=expected_profile)
    _need(encode(checked, expected_profile=expected_profile) == raw)
    return checked


def validate_binding(value):
    _plain(value); _binding(value)
    return json.loads(canonical(value))


def validate_descriptor(value):
    _plain(value); _closed(value, DESCRIPTOR_KEYS)
    for key in DESCRIPTOR_KEYS:
        if key.endswith('_sha'):
            _sha(value[key])
    _need(value['content_source_type'] == CONTENT_SOURCE_TYPE
          and value['operator_observation_profile'] == OBSERVATION_PROFILE)
    return json.loads(canonical(value))


def request_identity(value):
    return digest(validate(value, expected_profile=REQUEST_PROFILE))


def family_anchor(value):
    return digest(validate(value, expected_profile=ANCHOR_PROFILE))


def validate_first_pack(anchor, first_proof, request_witness, family_root, *, covenant_sha):
    """Pure acyclic FIRST-file consistency; does not read or publish any file."""
    a = validate_first_anchor(anchor)
    p = validate_first_proof(first_proof)
    w = validate_request_witness(request_witness)
    r = validate_family_root(family_root)
    _sha(covenant_sha)
    family = digest(a)
    proof_sha = sha256(encode(p, expected_profile=FIRST_PROOF_PROFILE)).hexdigest()
    root_sha = sha256(encode(r, expected_profile=FAMILY_ROOT_PROFILE)).hexdigest()
    _need(all(item['family_anchor_id'] == family for item in (p, w, r))
          and all(item['request_identity_sha'] == a['request_identity_sha'] for item in (p, w, r))
          and r['anchor'] == a and w['platform_account_sha'] == a['platform_account_sha']
          and all(w[key] == a[key] for key in REQUEST_FIELDS)
          and p['covenant_sha'] == w['first_covenant_sha'] == r['first_covenant_sha'] == covenant_sha
          and w['first_proof_sha'] == r['first_proof_sha'] == proof_sha
          and w['family_root_sha'] == root_sha
          and all(p[key] == r[key] for key in ('first_binding', 'first_directory', 'coordination')))
    return {'authority': False, 'family_anchor_id': family, 'first_proof_sha': proof_sha,
            'family_root_sha': root_sha, 'request_identity_sha': a['request_identity_sha']}


def semantic_scope_sha(value):
    checked = validate_semantic(value)
    return digest({key: checked[key] for key in REQUEST_FIELDS + (
        'operator_request_identity_sha', 'semantic_scope', 'read_contract_sha',
        'source_rights_expiry')})


def validate_material_links(source, policy, semantic, observation, descriptor, *,
                            current_binding_sha, configuration_sha):
    """Pure cross-document consistency, not authenticity or current authority."""
    s = validate_source(source)
    p = validate_runtime_policy(policy)
    m = validate_semantic(semantic)
    o = validate_observation(observation)
    d = validate_descriptor(descriptor)
    _sha(current_binding_sha); _sha(configuration_sha)
    source_sha = sha256(encode(s, expected_profile=SOURCE_PROFILE)).hexdigest()
    policy_sha = sha256(encode(p, expected_profile=POLICY_PROFILE)).hexdigest()
    semantic_sha = sha256(encode(m, expected_profile=SEMANTIC_PROFILE)).hexdigest()
    _need(p['binding'] == m['binding']
          and s['binding_sha'] == o['binding_sha'] == digest(p['binding'])
          and o['stable_owner'] == m['stable_owner']
          and o['epoch'] == p['binding']['epoch']
          and o['generation'] == p['binding']['generation']
          and p['source_material_sha'] == o['source_material_sha'] == source_sha
          and o['runtime_source_policy_sha'] == d['runtime_source_policy_sha'] == policy_sha
          and d['configuration_sha'] == configuration_sha
          and d['current_binding_sha'] == current_binding_sha
          and d['semantic_adoption_sha'] == semantic_sha
          and d['artifact_inventory_sha'] == m['artifact_inventory_sha']
          and s['semantic_scope_sha'] == p['semantic_scope_sha']
          == o['semantic_scope_sha'] == semantic_scope_sha(m))
    for key in ('original_queue_sha', 'original_request_set_sha', 'account_partition_sha',
                'operator_request_identity_sha'):
        _need(s[key] == p[key] == m[key])
        if key != 'original_queue_sha':
            _need(o[key] == s[key])
    _need(s['allowed_read_scope'] == p['allowed_read_scope']
          and s['allowed_read_scope']['family_anchor_sha'] == digest(_anchor_view(m))
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
    _need(o['qualified_not_after_ms'] <= min(caps))
    return {'authority': False, 'content_source_type': CONTENT_SOURCE_TYPE,
            'source_material_sha': source_sha, 'runtime_source_policy_sha': policy_sha,
            'semantic_adoption_sha': semantic_sha, 'observation_sha': digest(o)}


def validate_continuation(previous, current):
    """Same-source technical observation only, never cross-mode/source renewal."""
    old = validate(previous, expected_profile=OBSERVATION_PROFILE)
    new = validate(current, expected_profile=OBSERVATION_PROFILE)
    stable = ('source_material_sha', 'binding_sha', 'operator_request_identity_sha',
              'original_request_set_sha', 'account_partition_sha', 'selection_sha',
              'qa_set_sha', 'postupload_mapping_sha', 'prepared_relations_sha',
              'semantic_scope_sha', 'stable_owner', 'epoch', 'generation')
    _need(all(old[key] == new[key] for key in stable)
          and new['observed_at_ms'] >= old['observed_at_ms']
          and new['qualified_not_after_ms'] <= old['qualified_not_after_ms'])
    return new


def validate_source(value):
    return validate(value, expected_profile=SOURCE_PROFILE)


def validate_observation(value):
    return validate(value, expected_profile=OBSERVATION_PROFILE)


def validate_runtime_policy(value):
    return validate(value, expected_profile=POLICY_PROFILE)


def validate_semantic(value):
    return validate(value, expected_profile=SEMANTIC_PROFILE)


def validate_request(value):
    return validate(value, expected_profile=REQUEST_PROFILE)


def validate_first_anchor(value):
    return validate(value, expected_profile=ANCHOR_PROFILE)


def validate_first_proof(value):
    return validate(value, expected_profile=FIRST_PROOF_PROFILE)


def validate_request_witness(value):
    return validate(value, expected_profile=REQUEST_WITNESS_PROFILE)


def validate_family_root(value):
    return validate(value, expected_profile=FAMILY_ROOT_PROFILE)
