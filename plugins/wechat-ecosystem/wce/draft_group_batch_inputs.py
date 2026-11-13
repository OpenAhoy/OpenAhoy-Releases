"""Pure ordered assembly of already prepared imported HTML articles.

These detached values carry no source, upload, Parent or execution authority.
The fixed caller must obtain the source manifests from the actual source/QA
validator and original SQL, then revalidate them before D and every effect.
No source article, style, crop, author, provenance or asset reference is edited.
"""
import json

from .contracts import WCEError
from .service import canonical, digest
from . import documents, own_group_json
from .draft_group_input_files import _plain, _binding, _id, _member, _selector
from .import_styles import POLICY as IMPORT_POLICY


def need(value, code='GROUP_BATCH_INPUT_CHANGED'):
    if value is not True:
        raise WCEError(code)


def detached(value):
    _plain(value)
    return json.loads(canonical(value))


def operator_target_article_id(member):
    """Stable target-local namespace only; not a source or request identity."""
    _member(member)
    return 'g'+digest({'profile':'GROUP_OPERATOR_TARGET_ARTICLE_NAMESPACE_V1',
        'article_id':member['article_id'],'original_request_sha':member['original_request_sha']})[:15]


def _source_article(binding, member, supplied, *, multiple):
    from .draft_group_operator_source_codec import CONTENT_SOURCE_TYPE
    ordinary_keys={'selector','manifest','article_id','original_request_sha'}
    operator_keys=ordinary_keys|{'content_source_type','source_article_id'}
    need(type(supplied) is dict and (set(supplied)==ordinary_keys or
         set(supplied)==operator_keys and supplied['content_source_type']==CONTENT_SOURCE_TYPE),
        'GROUP_BATCH_SOURCE_DESCRIPTOR')
    _selector(supplied['selector'])
    need(supplied['article_id'] == member['article_id']
         and supplied['original_request_sha'] == member['original_request_sha'],
         'GROUP_BATCH_SOURCE_MEMBER_CHANGED')
    source = supplied['manifest']
    checksum = digest(source)
    own_group_json.read(canonical(source), checksum)
    need(source['binding'] == binding and source['schema'] == 3
         and source['document'].get('policy') == IMPORT_POLICY,
         'GROUP_BATCH_SOURCE_IMPORT_REQUIRED')
    selector = {'bundle_id': source['bundle_id'], 'version': source['version'],
                'content_digest': checksum}
    need(supplied['selector'] == selector and member['version_sha'] == checksum,
         'GROUP_BATCH_SOURCE_VERSION_CHANGED')
    document = source['document']
    need(documents.normalize(document) == document,
         'GROUP_BATCH_SOURCE_NORMALIZATION_CHANGED')
    source_article_id=supplied['source_article_id'] if set(supplied)==operator_keys else member['article_id']
    _id(source_article_id)
    articles = [a for a in document['articles'] if a['id'] == source_article_id]
    need(len(articles) == 1, 'GROUP_BATCH_SOURCE_ARTICLE_REQUIRED')
    article = articles[0]
    need(article['provenance']['source_sha256'] == member['source_sha'],
         'GROUP_BATCH_SOURCE_HTML_CHANGED')
    # This assembly cannot silently erase a single-article summary merely to
    # fit the original multi-article codec. An explicit reviewed transform is
    # a separate input version, never an implicit fallback in this function.
    need(not multiple or not article.get('digest'),
         'GROUP_BATCH_EXPLICIT_SUMMARY_TRANSFORM_REQUIRED')
    actual_slots = list(documents.assets(document))
    assets = source['assets']
    need(len(assets) == len(actual_slots), 'GROUP_BATCH_SOURCE_ASSET_COVERAGE')
    selected = []
    for (slot, asset_ref, role), asset in zip(actual_slots, assets):
        need((asset['slot'], asset['asset_ref'], asset['role']) == (slot, asset_ref, role),
             'GROUP_BATCH_SOURCE_ASSET_ORDER')
        if slot.startswith(article['id'] + '--'):
            need(type(asset['size']) is int and 0 < asset['size'] < 1000000,
                 'GROUP_BATCH_IMAGE_BELOW_ONE_MB_REQUIRED')
            selected.append(asset)
    expected = list(documents.assets(dict(document, articles=[article])))
    need([(a['slot'], a['asset_ref'], a['role']) for a in selected] == expected,
         'GROUP_BATCH_SOURCE_ASSET_COVERAGE')
    return article, selected, selector


def compose_new_only_manifest(binding, operation_id, ordered_members, source_documents):
    """Preserve exact source articles in the original planner's member order.

    ``version_sha`` is the actual original manifest digest, and ``source_sha``
    is its selected article's original HTML provenance digest. Projection
    membership still requires the independent original upload/reuse validator.
    Replaying these same values produces the same local target identity; it
    neither sends nor retries a platform operation.
    """
    value = detached({'binding': binding, 'operation_id': operation_id,
                      'members': ordered_members, 'sources': source_documents})
    binding, operation_id = value['binding'], value['operation_id']
    members, sources = value['members'], value['sources']
    _binding(binding)
    _id(operation_id)
    need(type(members) is list and 1 <= len(members) <= 8
         and type(sources) is list and len(sources) == len(members),
         'GROUP_BATCH_MEMBER_COUNT')
    for member in members:
        _member(member)
        need(member['binding_sha'] == digest(binding) and member['origin'] == 'NEW_NOT_SENT',
             'GROUP_BATCH_NEW_ONLY_REQUIRED')
    need(len({m['article_id'] for m in members}) == len(members),
         'GROUP_BATCH_DUPLICATE_MEMBER')
    articles, assets, links = [], [], []
    for member, supplied in zip(members, sources):
        original_article, original_assets, selector = _source_article(
            binding, member, supplied, multiple=len(members) > 1)
        # Own imported single documents use a local id (commonly s01). Group
        # membership uses the stable selected article id. Rebind only the new
        # target namespace; the original manifest, upload slot/proof, HTML,
        # image references and every editorial field remain exact source bytes.
        article=detached(original_article)
        target_id=(operator_target_article_id(member)
            if supplied.get('content_source_type')=='OPERATOR_ATTESTED_SELECTED_REQUEST_V1'
            else member['article_id'])
        article['id']=target_id
        target_assets=[dict(asset,slot=target_id+asset['slot'][len(original_article['id']):])
                       for asset in original_assets]
        articles.append(article)
        assets.extend(target_assets)
        for original_asset,asset in zip(original_assets,target_assets):
            links.append({'target_slot': asset['slot'], 'source_selector': selector,
                          'source_asset_slot': original_asset['slot'],
                          'member_evidence_sha': digest(member)})
    need(len({article['id'] for article in articles})==len(articles),
         'GROUP_BATCH_TARGET_NAMESPACE_COLLISION')
    document = {'format': 3, 'policy': IMPORT_POLICY, 'articles': articles}
    need(documents.normalize(document) == document,
         'GROUP_BATCH_NORMALIZATION_CHANGED')
    # Source JSON is already normalized. Identity construction is local and
    # deterministic, and does not consume the ADD request key or its budget.
    seed = digest({'profile': 'GROUP_IMPORTED_TARGET_IDENTITY_V1',
                   'binding_sha': digest(binding), 'operation_id': operation_id,
                   'members': members, 'source_selectors': [s['selector'] for s in sources]})
    manifest = {'schema': 3, 'binding': binding, 'bundle_id': 'own-bundle-' + seed[:32],
                'version': 'own-version-' + seed[32:], 'revision': 1,
                'document': document, 'assets': assets}
    checksum = digest(manifest)
    own_group_json.read(canonical(manifest), checksum)
    need(len({a['slot'] for a in assets}) == len(assets), 'GROUP_BATCH_DUPLICATE_ASSET_SLOT')
    return detached({'authority': False, 'manifest': manifest,
                     'manifest_sha': checksum,
                     'selector': {'bundle_id': manifest['bundle_id'],
                                  'version': manifest['version'], 'content_digest': checksum},
                     'source_links': links})


def evidence_descriptor(kind, raw):
    """Descriptor of actual canonical file bytes; no authority is inferred."""
    from hashlib import sha256
    need(type(raw) is bytes and len(raw) > 0, 'GROUP_BATCH_EVIDENCE_BYTES')
    return {'kind': kind, 'sha256': sha256(raw).hexdigest(), 'size': len(raw)}


def compose_new_only_child(plan_child, source_documents, original_uploads, artifacts):
    """Build U before H, with the original per-slot success values unchanged.

    Inputs are values from the actual fixed caller, not issued objects. The
    target creator re-reads every original SQL row/proof; neither this result
    nor a syntactically valid U can replace that check.
    """
    from .draft_group_contracts import budget_for
    from .draft_group_input_files import encode
    from .draft_group_upload_reuse_projection import derive_reuse_projection
    from .own_connection_workflow import PersistentWorkflow
    data = detached({'plan': plan_child, 'sources': source_documents,
                     'uploads': original_uploads, 'artifacts': artifacts})
    plan, sources, uploads = data['plan'], data['sources'], data['uploads']
    need(type(plan) is dict and plan.get('route') == 'CREATE_NEW'
         and plan.get('old_ref_set') == [] and canonical(plan.get('budget')) == canonical(budget_for(0)),
         'GROUP_BATCH_NEW_ONLY_PLAN_REQUIRED')
    need(type(plan.get('members')) is list and type(uploads) is list,
         'GROUP_BATCH_SOURCE_DESCRIPTOR')
    members = []
    for position, item in enumerate(plan['members']):
        need(type(item) is dict and type(item.get('target_position')) is int
             and item['target_position'] == position and item.get('source_old_index') is None,
             'GROUP_BATCH_PLAN_MEMBER_ORDER')
        member = {k: v for k, v in item.items() if k not in ('target_position', 'source_old_index')}
        _member(member)
        members.append(member)
    need(type(plan.get('member_count')) is int and plan['member_count'] == len(members),
         'GROUP_BATCH_PLAN_MEMBER_COUNT')
    need(len(sources) > 0, 'GROUP_BATCH_SOURCE_DESCRIPTOR')
    binding = sources[0]['manifest']['binding']
    assembled = compose_new_only_manifest(binding, plan['operation_id'], members, sources)
    manifest, selector = assembled['manifest'], assembled['selector']
    upload_keys = ('selector', 'slot', 'operation', 'asset', 'base_step_pin',
                   'snapshot', 'result_digest', 'proof_files')
    selected, slot_facts, used = [], [], set()
    member_by_sha = {digest(member): member for member in members}
    for asset, link in zip(manifest['assets'], assembled['source_links']):
        matches = [(index, value) for index, value in enumerate(uploads)
                   if type(value) is dict and value.get('selector') == link['source_selector']
                   and value.get('slot') == link['source_asset_slot']]
        need(len(matches) == 1, 'GROUP_BATCH_ORIGINAL_UPLOAD_REQUIRED')
        index, actual = matches[0]
        need(index not in used, 'GROUP_BATCH_DUPLICATE_ORIGINAL_UPLOAD')
        used.add(index)
        original = {key: actual[key] for key in upload_keys}
        need(dict(original['asset'],slot=asset['slot']) == asset and 'mapping' in actual,
             'GROUP_BATCH_UPLOAD_ASSET_CHANGED')
        member = member_by_sha[link['member_evidence_sha']]
        selected.append({'target_slot': asset['slot'], 'target_asset': asset,
            'source_member': {'article_id': member['article_id'], 'version_sha': member['version_sha'],
                'source_manifest_selector': link['source_selector'], 'source_asset_slot': actual['slot'],
                'source_asset_ref': asset['asset_ref'], 'member_evidence_sha': link['member_evidence_sha']},
            'original_upload': original, 'source_save': None,
            'transmission': 'NONE_REUSE_VERIFIED_SUCCESS'})
        slot_facts.append({'target_slot': asset['slot'], 'mapping': actual['mapping'],
                           'snapshot': actual['snapshot']})
    need(len(used) == len(uploads), 'GROUP_BATCH_UNSELECTED_UPLOAD')
    reuse = {'schema': 1, 'profile': 'GROUP_TARGET_UPLOAD_REUSE_MAP_V1', 'authority': False,
             'binding': binding, 'operation_id': plan['operation_id'], 'target_selector': selector,
             'target_manifest_sha': assembled['manifest_sha'], 'entries': selected}
    reuse_raw = encode('upload_reuse', reuse)
    metadata = PersistentWorkflow._request_draft_metadata(manifest)
    projected = derive_reuse_projection(manifest, slot_facts, article_metadata=metadata)['projection']
    need(len(projected['articles']) == len(members), 'GROUP_BATCH_PROJECTION_COVERAGE')
    for member, row in zip(members, projected['articles']):
        need(member['projection_sha'] == digest(row), 'GROUP_BATCH_SOURCE_PROJECTION_CHANGED')
    child = {'schema': 1, 'profile': 'GROUP_EXECUTION_CHILD_V1', 'binding': binding,
             'operation_id': plan['operation_id'], 'selector': selector,
             'manifest_json': canonical(manifest), 'manifest_sha': assembled['manifest_sha'],
             'projection_json': canonical(projected), 'projection_sha': digest(projected),
             'members': members, 'upload_reuse': [evidence_descriptor('UPLOAD', reuse_raw)],
             'expected_metadata': evidence_descriptor('METADATA', (canonical(metadata) + '\n').encode()),
             'execution_budget': evidence_descriptor('BUDGET', (canonical(plan['budget']) + '\n').encode()),
             'artifact_descriptors': data['artifacts']}
    child_raw = encode('child', child)
    return detached({'authority': False, 'upload_reuse': reuse, 'child': child,
                     'upload_reuse_descriptor': evidence_descriptor('UPLOAD', reuse_raw),
                     'child_descriptor': evidence_descriptor('CHILD', child_raw)})


def compose_new_only_execution(registration, registration_proof, preview, children):
    """Compose U -> H -> C -> R values without a self-hash or SQL mutation.

    FileEvidence is an integrity value, not an issued registration or grant.
    The Parent issuer independently recomputes the actual account allocation,
    checks original SQL registration/proof and D rows, and consumes its own
    actual current coverage before these files can support a PLAN.
    """
    from .draft_group_input_files import FileEvidence, encode, registration_id
    from .draft_group_parent import expected_settings_descriptor, parent_budget_descriptor
    from .own_connection_workflow import PersistentWorkflow
    for evidence, role in ((registration, 'registration'), (registration_proof, 'proof')):
        need(type(evidence) is FileEvidence and evidence.role == role,
             'GROUP_BATCH_REGISTRATION_EVIDENCE_REQUIRED')
        need(evidence.size == len(evidence.raw)
             and evidence_descriptor('ARTIFACT', evidence.raw)['sha256'] == evidence.sha256,
             'GROUP_BATCH_REGISTRATION_EVIDENCE_CHANGED')
    reg, proof = registration.value, registration_proof.value
    need(proof['registration_sha'] == registration.sha256
         and proof['source_material_sha'] == reg['source_material_sha']
         and proof['qualified_binding'] == reg['binding'],
         'GROUP_BATCH_REGISTRATION_PROOF_CHANGED')
    value = detached({'preview': preview, 'children': children})
    preview, children = value['preview'], value['children']
    need(type(preview) is dict and preview.get('plan_state') == 'CANDIDATE_ALLOCATED'
         and preview.get('binding_sha') == digest(reg['binding'])
         and preview.get('candidate_sha') == digest({k: v for k, v in preview.items() if k != 'candidate_sha'}),
         'GROUP_BATCH_PREVIEW_CHANGED')
    need(type(children) is list and 1 <= len(children) <= 64
         and len(children) == len(preview['children']), 'GROUP_BATCH_CHILD_COVERAGE')
    need(not reg['old_sources'], 'GROUP_BATCH_NEW_ONLY_REQUIRED')
    _id(reg['registration_id'])
    need(reg['registration_id'] == registration_id({k: v for k, v in reg.items() if k != 'registration_id'}),
         'GROUP_BATCH_REGISTRATION_CHANGED')
    descriptors, reuse_descriptors, settings, budgets, all_members = [], [], [], [], []
    for child, plan in zip(children, preview['children']):
        need(type(child) is dict and child.get('authority') is False,
             'GROUP_BATCH_CHILD_VALUE_REQUIRED')
        h, u = child['child'], child['upload_reuse']
        hraw, uraw = encode('child', h), encode('upload_reuse', u)
        hspec, uspec = evidence_descriptor('CHILD', hraw), evidence_descriptor('UPLOAD', uraw)
        need(child['child_descriptor'] == hspec and child['upload_reuse_descriptor'] == uspec
             and h['binding'] == reg['binding'] and u['binding'] == reg['binding']
             and h['operation_id'] == u['operation_id'] == plan['operation_id']
             and h['selector'] == u['target_selector']
             and h['manifest_sha'] == u['target_manifest_sha']
             and plan['route'] == 'CREATE_NEW' and not plan['old_ref_set']
             and h['upload_reuse'] == [uspec], 'GROUP_BATCH_CHILD_CHANGED')
        members = [{k: v for k, v in member.items() if k not in ('target_position', 'source_old_index')}
                   for member in plan['members']]
        need(h['members'] == members, 'GROUP_BATCH_PLAN_MEMBER_ORDER')
        manifest = own_group_json.read(h['manifest_json'], h['manifest_sha'])
        need(len(u['entries']) == len(manifest['assets']), 'GROUP_BATCH_UPLOAD_COVERAGE_CHANGED')
        identities = {digest(member): member for member in h['members']}
        for entry, asset in zip(u['entries'], manifest['assets']):
            source = entry['source_member']
            member = identities.get(source['member_evidence_sha'])
            need(entry['target_slot'] == asset['slot'] and entry['target_asset'] == asset
                 and member is not None and source['article_id'] == member['article_id']
                 and source['version_sha'] == member['version_sha']
                 and entry['source_save'] is None, 'GROUP_BATCH_UPLOAD_MEMBER_CHANGED')
        metadata = PersistentWorkflow._request_draft_metadata(manifest)
        need(h['expected_metadata'] == evidence_descriptor('METADATA', (canonical(metadata) + '\n').encode())
             and h['execution_budget'] == evidence_descriptor('BUDGET', (canonical(plan['budget']) + '\n').encode()),
             'GROUP_BATCH_CHILD_SETTINGS_OR_BUDGET_CHANGED')
        descriptors.append(hspec)
        reuse_descriptors.append(uspec)
        settings.append({'operation_id': h['operation_id'], 'article_metadata': metadata})
        budgets.append({'operation_id': h['operation_id'], 'budget': plan['budget']})
        all_members.extend(h['members'])
    need(all_members == reg['ordered_members'], 'GROUP_BATCH_REGISTERED_MEMBER_COVERAGE')
    capsule = {'schema': 1, 'profile': 'GROUP_EXECUTION_INPUT_CAPSULE_V1', 'binding': reg['binding'],
        'family_id': reg['family_id'], 'registration_sha': registration.sha256,
        'source_material_sha': reg['source_material_sha'], 'preview_core_sha': preview['candidate_sha'],
        'route_profile': 'CREATE_NEW', 'children': descriptors, 'old_sources': [],
        'new_sources': reg['new_sources'], 'upload_reuse': reuse_descriptors,
        'expected_metadata': expected_settings_descriptor(settings),
        'read_delegation_ids': reg['read_delegation_ids'],
        'execution_budget': parent_budget_descriptor(budgets), 'artifact_descriptors': reg['artifacts']}
    raw = encode('execution', capsule)
    checksum = evidence_descriptor('CHILD', raw)['sha256']
    reservations = []
    for child in children:
        h = child['child']
        reservation = {'schema': 1, 'profile': 'GROUP_TARGET_RESERVATION_V1', 'binding': reg['binding'],
            'manifest_sha': h['manifest_sha'], 'selector': h['selector'],
            'registration_sha': registration.sha256, 'capsule_sha': checksum,
            'operation_id': h['operation_id'], 'proof_sha': registration_proof.sha256}
        encode('reservation', reservation)
        reservations.append(reservation)
    return detached({'authority': False, 'capsule': capsule, 'capsule_sha': checksum,
                     'reservations': reservations})
