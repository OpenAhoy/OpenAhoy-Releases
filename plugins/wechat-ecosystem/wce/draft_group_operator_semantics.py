"""PROPOSAL ONLY: detached Operator material values, no IO or authority.

The fixed chain must read each reference using held actual FDs and authenticate
the real prepared rows separately. These pure functions cannot issue W1/W2.
Do not add this proposal to a product import path without root's integration.
"""
from . import draft_group_operator_time_v2 as time06
from dataclasses import dataclass
from hashlib import sha256
import json
from . import draft_group_operator_source_codec as codec


class OperatorSemanticError(ValueError):
    def __init__(self):
        super().__init__('GROUP_OPERATOR_SEMANTIC_HOLD')


def need(condition):
    if condition is not True:
        raise OperatorSemanticError()


def detached(value):
    return json.loads(codec.canonical(value))


def _closed(value, keys):
    codec.canonical(value)
    need(type(value) is dict and set(value) == set(keys))


def _sha(value):
    need(type(value) is str and len(value) == 64
         and all(c in '0123456789abcdef' for c in value))


def _id(value):
    need(type(value) is str and 1 <= len(value) <= 128
         and value[0].isascii() and value[0].isalnum()
         and all(c.isascii() and (c.isalnum() or c in '_.:-') for c in value))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def reference_json(reference, raw, *, expected_reference, trailing_lf):
    """Byte/reference consistency only; raw must come from the actual FD owner.

    `expected_reference` is compiled/fixed input, not a discovered same-SHA path.
    A caller can self-construct all arguments: successful decoding is no grant.
    """
    codec._plain(reference); codec._ref(reference)
    codec._plain(expected_reference); codec._ref(expected_reference)
    need(reference == expected_reference and type(raw) is bytes
         and type(trailing_lf) is bool and len(raw) == reference['size']
         and sha256(raw).hexdigest() == reference['sha256'])
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                           parse_constant=lambda _: need(False))
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise OperatorSemanticError() from None
    need(raw == codec.canonical(value) + (b'\n' if trailing_lf else b''))
    return detached(value)


def operator_original_request_sha(selected_article_id, relation):
    """Original accepted prepare identity; never current code/time/file pins."""
    _id(selected_article_id); codec.canonical(relation)
    _sha(relation['binding_sha256']); _sha(relation['parameters_sha256'])
    _id(relation['prepare_request_key'])
    selector = relation['selector']
    _closed(selector, ('bundle_id', 'version', 'content_digest'))
    _id(selector['bundle_id']); _id(selector['version']); _sha(selector['content_digest'])
    return codec.digest({'profile':'GROUP_OPERATOR_ORIGINAL_REQUEST_ID_V1',
        'selected_article_id':selected_article_id,
        **{key:relation[key] for key in ('binding_sha256','prepare_request_key',
                                       'parameters_sha256','selector')}})


def member_identities_from_values(selection_members, prepared_members, postupload_rows,
                                  *, authorized_member_ids, binding_sha):
    """Static closed-reference join only; no relation authenticity assertion.

    prepared_members uses root's fixed five-field persisted row. Actual H
    relations are checked separately by require_actual_prepared_values.
    """
    selection_members, prepared_members, postupload_rows, ids = detached([
        selection_members, prepared_members, postupload_rows, authorized_member_ids])
    _sha(binding_sha)
    need(type(ids) is list and 1 <= len(ids) <= 28 and len(ids) == len(set(ids)))
    for item in ids: _id(item)
    need(type(selection_members) is list and type(prepared_members) is list
         and type(postupload_rows) is list)
    selected = [s for s in selection_members if s['article_id'] in ids]
    need([s['article_id'] for s in selected] == ids
         and all(s['binding_sha256'] == binding_sha for s in selected)
         and len(prepared_members) == len(postupload_rows) == len(ids))
    result = []
    for chosen, prepared, mapped, member_id in zip(selected, prepared_members,
                                                 postupload_rows, ids, strict=True):
        _closed(prepared, ('selected_article_id', 'source_article_id',
                           'prepare_request_key', 'selector', 'prepared_relation_sha256'))
        _closed(mapped, ('selected_article_id', 'member_identity',
                        'report_artifact_sha', 'upload_mapping_sha'))
        _id(prepared['source_article_id']); _sha(prepared['prepared_relation_sha256'])
        identity = mapped['member_identity']
        _closed(identity, ('article_id', 'original_request_sha'))
        _id(identity['article_id']); _sha(identity['original_request_sha'])
        _sha(mapped['report_artifact_sha']); _sha(mapped['upload_mapping_sha'])
        need(prepared['selected_article_id'] == mapped['selected_article_id'] == member_id
             and identity['article_id'] == member_id
             and prepared['selector'] == chosen['selector']
             and prepared['prepare_request_key'] == chosen['prepare_request_key'])
        result.append(identity)
    return detached(result)


def require_actual_prepared_values(selection_members, prepared_members, postupload_rows,
                                   actual_relations, actual_source_article_ids, *,
                                   authorized_member_ids, binding_sha):
    """Exact pure comparison of actual H-reader outputs; still not an issuer.

    Caller must obtain actual_relations and actual_source_article_ids from its
    current real Owned/H reader and actual manifest, never from these JSON rows.
    No input_id, import receipt or file hash stands in for parameters_sha256.
    """
    identities = member_identities_from_values(selection_members, prepared_members,
        postupload_rows, authorized_member_ids=authorized_member_ids, binding_sha=binding_sha)
    selected, rows, relations, source_ids = detached([selection_members, prepared_members,
        actual_relations, actual_source_article_ids])
    selected = [s for s in selected if s['article_id'] in authorized_member_ids]
    need(type(relations) is list and type(source_ids) is list
         and len(relations) == len(source_ids) == len(identities))
    for chosen, row, relation, identity, source_id in zip(selected, rows, relations,
                                                        identities, source_ids, strict=True):
        _closed(relation, ('profile', 'authority', 'qualification', 'binding_sha256',
            'selector', 'prepare_request_key', 'input_id', 'parameters_sha256',
            'result_sha256', 'lineage_sha256', 'approval_state',
            'historical_approvals', 'assets'))
        _id(source_id)
        need(relation['profile'] == 'OPERATOR_PREPARED_RELATION_FACT_V1'
             and relation['authority'] is False and relation['qualification'] == 'NOT_ASSERTED'
             and relation['binding_sha256'] == binding_sha
             and relation['selector'] == chosen['selector']
             and relation['prepare_request_key'] == chosen['prepare_request_key']
             and relation['approval_state'] in ('ABSENT_VERIFIED', 'HISTORY_ONLY')
             and type(relation['historical_approvals']) is list and type(relation['assets']) is list)
        _id(relation['input_id'])
        for key in ('parameters_sha256','result_sha256','lineage_sha256'): _sha(relation[key])
        expected_assets = [{'asset_ref': i['asset_ref'], 'role': i['role'],
            'slot': i['slot'], 'declared_type': i['artifact']['media_type'],
            'size': i['artifact']['size'], 'sha256': i['artifact']['sha256']}
            for i in chosen['images']]
        need(relation['assets'] == expected_assets
             and row['source_article_id'] == source_id
             and row['prepared_relation_sha256'] == codec.digest(relation)
             and identity['original_request_sha'] == operator_original_request_sha(chosen['article_id'], relation))
    return identities


def validate_root_values(value):
    """Mirror only the neutral _origin data shape; RootClosure checks reality."""
    _closed(value, ('origin_request_identity_sha', 'origin_stable_owner',
        'origin_prepared_binding_sha', 'origin_publication_binding_sha',
        'origin_policy_identity_sha', 'origin_root_identity',
        'origin_database_identity', 'origin_registry_parent_identity',
        'origin_anchor_identity', 'source_evidence_sha'))
    _closed(value['origin_stable_owner'], ('tenant', 'principal'))
    for item in value['origin_stable_owner'].values(): _id(item)
    for key, item in value.items():
        if key.endswith('_sha'): _sha(item)
        elif key.endswith('_identity'):
            need(type(item) is list and len(item) == 2
                 and all(type(i) is int and 0 <= i < 2**63 for i in item))
    return detached(value)


@dataclass(frozen=True)
class OperatorSemanticView:
    # Publicly constructible pure data. Actual Host must authenticate/own it.
    semantic_raw: bytes
    source_raw: bytes
    artifact_inventory_raw: bytes
    original_root_evidence_raw: bytes
    member_identities_raw: bytes
    execution_slots_raw: bytes
    semantic_scope_sha: str
    request_identity_sha: str

    @property
    def authority(self): return False

    @property
    def artifact_inventory(self): return json.loads(self.artifact_inventory_raw)
    @property
    def original_root_evidence(self): return json.loads(self.original_root_evidence_raw)
    @property
    def member_identities(self): return json.loads(self.member_identities_raw)
    @property
    def execution_slots(self): return json.loads(self.execution_slots_raw)


def build_operator_view(semantic, source, *, artifact_inventory,
                        original_root_evidence, member_identities, execution_slots):
    """Compile already-read/validated values; no IO, QA/rights/issuer assertion.

    Actual readers validate inventory artifacts, slots via original covenant,
    full selection/prepared joins and all physical pins before this data step.
    """
    m = codec.validate_semantic(semantic); s = codec.validate_source(source)
    inventory, original, members, slots = detached([
        artifact_inventory, original_root_evidence, member_identities, execution_slots])
    need(type(inventory) is list and inventory and type(slots) is list
         and slots and type(members) is list)
    validate_root_values(original)
    for identity in members:
        _closed(identity, ('article_id', 'original_request_sha'))
        _id(identity['article_id']); _sha(identity['original_request_sha'])
    need([x['article_id'] for x in members] == m['semantic_scope']['authorized_member_ids']
         and len(members) == len({x['article_id'] for x in members})
         and codec.digest(inventory) == m['artifact_inventory_sha']
         and codec.digest(original) == m['original_root_evidence_sha']
         and original['origin_request_identity_sha'] == m['operator_request_identity_sha']
         and original['origin_stable_owner'] == m['stable_owner']
         and s['binding_sha'] == codec.digest(m['binding'])
         and s['qa_set_ref'] == m['qa_set_ref']
         and s['semantic_scope_sha'] == codec.semantic_scope_sha(m))
    for key in ('original_queue_sha','operator_request_identity_sha',
                'original_request_set_sha','account_partition_sha'):
        need(s[key] == m[key])
    need(s['allowed_read_scope']['member_ids'] == m['semantic_scope']['authorized_member_ids'])
    return OperatorSemanticView(codec.canonical(m), codec.canonical(s),
        codec.canonical(inventory), codec.canonical(original), codec.canonical(members),
        codec.canonical(slots), codec.semantic_scope_sha(m), m['operator_request_identity_sha'])


def operator_generation_values(facts):
    """Pure generation projection; actual observation must be issuer-verified."""
    if type(facts) is dict and facts.get('profile')==time06.OBSERVATION_PROFILE_V2:
        try:checked=time06.validate_observation_v2(facts)
        except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
            from .contracts import WCEError
            raise WCEError('GROUP_OPERATOR_SEMANTIC_HOLD') from None
    else:checked = codec.validate_observation(facts)
    return {'profile':'GROUP_OPERATOR_QUALIFICATION_GENERATION_V1','authority':False,
        'source_observation_sha':codec.digest(checked),
        **{key:checked[key] for key in ('source_material_sha','file_generation_sha',
            'proof_generation_sha','first_pass_sha','second_pass_sha','collective_fence_sha')}}


_LEGACY_SOURCE_PROFILES = ('GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1',
                           'GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2')


def is_operator(host):
    """Pure dispatch usable before capture; never tests/creates a live grant."""
    profile = host.chain.source['profile']
    need(type(profile) is str and profile in (codec.SOURCE_PROFILE,) + _LEGACY_SOURCE_PROFILES)
    return profile == codec.SOURCE_PROFILE


def _checked_chain(host):
    # The actual consumer's issuer still requires exact GroupRuntimeHost/Gate.
    # chain.check reads its own data view directly, never calls these wrappers.
    host.entry.held_pure()
    host.chain.check()
    is_operator(host)
    return host.chain


def _operator_view(chain):
    view = chain.operator_semantics
    need(type(view) is OperatorSemanticView
         and view.semantic_raw == codec.canonical(chain.semantic)
         and view.source_raw == codec.canonical(chain.source))
    return view


def original_root_evidence(host):
    chain = _checked_chain(host)
    return (_operator_view(chain).original_root_evidence if is_operator(host)
            else chain.semantic['original_root_evidence'])


def artifact_inventory(host):
    chain = _checked_chain(host)
    return (_operator_view(chain).artifact_inventory if is_operator(host)
            else chain.semantic['artifact_inventory'])


def member_identities(host):
    chain = _checked_chain(host)
    return (_operator_view(chain).member_identities if is_operator(host)
            else chain.semantic['semantic_scope']['authorized_member_identities'])


def source_generation(host, facts):
    _checked_chain(host)
    if is_operator(host):
        need(facts['source_material_sha'] == host.pins.source_sha)
        return operator_generation_values(facts)
    # Preserve the legacy object and algorithm, including legacy validators.
    return facts['sources']
