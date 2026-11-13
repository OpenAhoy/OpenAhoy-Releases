"""Fixed current-source batch registration and NEW_ONLY Parent preparation.

This private entry accepts no caller path, member, reference, purpose or cap.
It prepares the actual Parent; it does not upload an image, ADD or publish an
article. Public execution consumes that Parent through its original slots.
"""
from .contracts import WCEError
from .service import canonical, digest
from .draft_group_operator_semantics import is_operator, artifact_inventory, original_root_evidence


def need(value, code='GROUP_BATCH_BOOTSTRAP_HOLD'):
    if value is not True:
        raise WCEError(code)


def _registration(host, files, pack, members):
    from .draft_group_input_files import registration_id
    from .draft_group_read_family_store import _gid
    binding = host.chain.config['binding']
    covenant = pack.entry('covenant').value
    purposes = [p for p in covenant['purposes'] if p['purpose'] in ('QUALIFY', 'PREVIEW_ACCOUNT')]
    expected_purposes = {'PREVIEW_ACCOUNT'}
    if covenant['qualify_subjects']:
        expected_purposes.add('QUALIFY')
    need(len(purposes) == len(expected_purposes)
         and {p['purpose'] for p in purposes} == expected_purposes
         and all(p['ordinal'] == 0 for p in purposes), 'GROUP_INITIAL_PURPOSES_REQUIRED')
    source = files.publish('source', host.chain.source)
    need(source.raw == host.chain.files['source'].raw and source.sha256 == host.pins.source_sha,
         'GROUP_BATCH_SOURCE_FILE_CHANGED')
    value = {'schema': 1, 'profile': 'GROUP_REGISTERED_BATCH_INPUT_V1',
             'family_id': covenant['family_anchor_id'], 'input_generation': 1,
             'binding': binding, 'source_material_sha': source.sha256,
             'read_delegation_ids': [_gid(digest(binding), p) for p in purposes],
             'ordered_members': list(members), 'old_sources': [],
             'new_sources': [{'kind': 'OPERATOR_SELECTED_SOURCE' if is_operator(host) else 'NATIVE', 'sha256': source.sha256, 'size': source.size}],
             'qa_evidence': ([{'kind':'QA','sha256':host.chain.files['qa_set'].sha,'size':len(host.chain.files['qa_set'].raw)}] if is_operator(host) else host.chain.source['qa_sources']),
             'artifacts': artifact_inventory(host),
             'previous_registration_sha': None, 'scope': 'LOCAL_INPUT'}
    value['registration_id'] = registration_id(value)
    return files.publish('registration', value), purposes


def _existing_registration(host, files, pack):
    # The fixed pointer is only a locator. Actual bind_registration_in verifies
    # its immutable files, original FIRST, source review and complete history.
    head = files._read_head_bytes(missing=True)
    if head is None:
        return None
    head = files.read_head().value
    if head['family_id'] != pack.entry('covenant').value['family_anchor_id']:
        return None
    registration = files.read('registration', head['registration_sha'])
    if head['schema'] == 2:
        proof_sha = head['registration_proof_sha']
    else:
        from .draft_group_parent import check_parent_records_in
        with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
            history = check_parent_records_in(db, history_policy=host.entry.policy, history_locators=history_locators)
            proofs = {item['parent']['registration_proof_sha'] for item in history['executions'].values()
                      if item['parent']['registration_sha'] == registration.sha256}
        need(len(proofs) == 1, 'GROUP_ORIGINAL_REGISTRATION_PROOF_LOCATOR_REQUIRED')
        proof_sha = next(iter(proofs))
    proof = files.read('proof', proof_sha)
    with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
        host.bind_registration_in(db, registration, proof, history_locators=history_locators)
    return registration, proof


def _known_parent(host):
    from .draft_group_parent import check_parent_records_in
    with _history_transaction(host.entry.service.workflow.db,physical_resources=host.entry) as (db, history_locators):
        history = check_parent_records_in(db, history_policy=host.entry.policy, history_locators=history_locators)
        selected = [(op, item) for op, item in history['executions'].items()
                    if item['parent']['registration_sha'] == host._registration['registration_sha']]
        if not selected:
            return None
        capsules = {item['parent']['source_scope_sha'] for _, item in selected}
        need(len(capsules) == 1, 'GROUP_BATCH_PARENT_AMBIGUOUS')
        state = host._group_state_in(db)
        ordered = sorted((state['operations'][op]['ordinal'], op) for op, _ in selected)
        return {'state': 'ORIGINAL_PARENT_REGISTERED', 'authority': False,
                'operation_ids': [op for _, op in ordered], 'business_calls': 0,
                'platform_readback': 'NOT_PERFORMED_THIS_ENTRY'}


def _new_registration(host, files, pack, members):
    from .draft_group_host_publisher import (qualify_initial_read_delegation,
        publish_registration_current)
    registration, purposes = _registration(host, files, pack, members)
    workflow = host.entry.service.workflow
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db, history_locators):
        reads = tuple(qualify_initial_read_delegation(
            host, host._source, registration, p['source_grant_sha'], db, history_locators=history_locators) for p in purposes)
    proof, head = publish_registration_current(host, registration, reads)
    need(head.value['schema'] == 2
         and head.value['registration_proof_sha'] == proof.sha256,
         'GROUP_REGISTRATION_RECOVERY_POINTER_REQUIRED')
    with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
        host.bind_registration_in(db, registration, proof, history_locators=history_locators)
    return registration, proof


def _account_coverage(host, pack):
    from .draft_group_runtime_host import qualify_preview_read_delegation
    from .draft_group_provider import OfficialGroupProvider
    from .draft_group_coverage import bind_account_subjects_in, issue_account_coverage_in
    workflow = host.entry.service.workflow
    purposes = [p for p in pack.entry('covenant').value['purposes']
                if p['purpose'] == 'PREVIEW_ACCOUNT' and p['ordinal'] == 0]
    need(len(purposes) == 1, 'GROUP_INITIAL_ACCOUNT_PURPOSE_REQUIRED')
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db, history_locators):
        scope = qualify_preview_read_delegation(
            host, host._source, pack, purposes[0]['source_grant_sha'], db, history_locators=history_locators)
        state = host._group_state_in(db)
        grant = state['preview_grants'][scope.details['gid']]
        # An earlier entry's read ledger is never reset or silently treated as
        # new current observations. Recovery needs its original explicit route.
        need(not grant['claims'], 'GROUP_ORIGINAL_ACCOUNT_READ_RECOVERY_REQUIRED')
    provider = OfficialGroupProvider(host.entry.service, host, host.entry)
    provider.run_preview(scope, 'LIST_NEXT')
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db,history_locators):
        state = host._group_state_in(db)
        grant = state['preview_grants'][scope.details['gid']]
        first = grant['claims'][0]
        page = provider._read_claim_snapshot_in(db, state, first['id'])
        total = page['total_count']
        need(type(total) is int and total >= 0, 'GROUP_ACCOUNT_LIST_TOTAL_CHANGED')
        pages = max(1, (total + 19) // 20)
        need(2 * pages <= grant['registration']['list_cap'], 'GROUP_ORIGINAL_LIST_CAP_EXHAUSTED')
    for _ in range(2 * pages - 1):
        provider.run_preview(scope, 'LIST_NEXT')
    with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
        references = bind_account_subjects_in(host, db, scope, history_locators=history_locators)
    for _ in references:
        provider.run_preview(scope, 'GET_NEXT')
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db, history_locators):
        return scope, issue_account_coverage_in(host, db, scope, history_locators=history_locators)


def _plan(host, coverage, members):
    from .draft_group_contracts import Article, PoolGroup
    from .draft_group_planner import plan_batch
    with host.entry.service.workflow.db.transaction() as db:
        state = host._group_state_in(db)
        need(state['pool'] is not None, 'GROUP_POOL_REQUIRED')
        groups = []
        for value in state['pool']['groups'].values():
            if value['state'] in ('OPEN', 'FULL', 'PUBLISHED', 'HOLD', 'UNKNOWN'):
                group = dict(value)
                group['members'] = tuple(Article(**m) for m in value['members'])
                groups.append(PoolGroup(**group))
        request_key = 'group-request-' + digest({
            'family_id': host._registration['registration']['family_id'],
            'registration_sha': host._registration['registration_sha']})
        result = plan_batch(state['binding_sha'], request_key,
            tuple(Article(**m) for m in members), tuple(groups), coverage.candidate)
    need(result['plan_state'] == 'CANDIDATE_ALLOCATED'
         and all(p['route'] == 'CREATE_NEW' and not p['old_ref_set'] for p in result['children']),
         'GROUP_BATCH_EXACT_REPLACEMENT_REVIEW_REQUIRED')
    return result


def _child_transport_artifacts(uploads, inventory):
    """Bound H to its own transport assets; C retains the full inventory."""
    from .draft_group_input_files import _artifact, _hash, _plain
    _plain(uploads)
    _plain(inventory)
    need(type(uploads) is list and type(inventory) is list, 'GROUP_CHILD_ARTIFACT_INPUT')
    for item in inventory:
        _artifact(item)
    selected, seen = [], set()
    for upload in uploads:
        asset = upload['asset']
        _hash(asset['sha256'])
        need(type(asset['size']) is int and 0 < asset['size'] < 1000000
             and asset['declared_type'] in ('image/png', 'image/jpeg'), 'GROUP_CHILD_TRANSPORT_ASSET')
        checksum = asset['sha256']
        matches = [item for item in inventory if item['sha256'] == checksum
                   and item['size'] == asset['size'] and item['media_type'] == asset['declared_type']]
        need(len(matches) == 1, 'GROUP_CHILD_TRANSPORT_ARTIFACT_REQUIRED')
        if checksum in seen:
            continue
        selected.append(matches[0])
        seen.add(checksum)
    need(0 < len(selected) <= 48, 'GROUP_CHILD_TRANSPORT_ARTIFACT_BOUND')
    return selected


def _publish_execution(host, files, registration, proof, preview, rows):
    from .draft_group_batch_inputs import compose_new_only_child, compose_new_only_execution
    by_id = {r['article_id']: r for r in rows}
    children = []
    for plan in preview['children']:
        ids = [m['article_id'] for m in plan['members']]
        selected = [by_id[article_id] for article_id in ids]
        sources = [{'selector': row['selector'], 'manifest': row['source_manifest'],
                    'article_id': row['article_id'], 'original_request_sha': row['original_request_sha'],
                    **({key:row[key] for key in ('content_source_type','source_article_id')} if is_operator(host) else {})}
                   for row in selected]
        uploads = [item for row in selected for item in row['original_uploads']]
        artifacts = _child_transport_artifacts(uploads, artifact_inventory(host))
        children.append(compose_new_only_child(plan, sources, uploads, artifacts))
    execution = compose_new_only_execution(registration, proof, preview, children)
    # Acyclic order: U -> H -> C -> R. The existing writer/fsync/readback
    # protocol runs for every file before any designation or target SQL row.
    for child in children:
        files.publish('upload_reuse', child['upload_reuse'])
        files.publish('child', child['child'])
    capsule = files.publish('execution', execution['capsule'])
    need(capsule.sha256 == execution['capsule_sha'], 'GROUP_EXECUTION_CAPSULE_CHANGED')
    reservations = [files.publish('reservation', value) for value in execution['reservations']]
    return capsule, tuple((files.read('child', c['child_descriptor']['sha256']), reservation,
                           files.read('upload_reuse', c['upload_reuse_descriptor']['sha256']))
                          for c, reservation in zip(children, reservations))


def _record_new_only_route(host, db, pack, capsule, preview, *, history_locators=None):
    from .draft_group_read_family_store import (ROUTE, original_root_scope, record_route_in)
    from .draft_group_read_family_files import FamilyFiles
    from .draft_group_store import GroupStore
    covenant = pack.entry('covenant').value
    branches = [b for b in covenant['branches'] if b['route'] == 'NEW_ONLY_EXISTING_DELEGATION']
    need(len(branches) == 1, 'GROUP_NEW_ONLY_COVENANT_REQUIRED')
    count = len(preview['children'])
    need(0 < count <= len(branches[0]['execution_slots']), 'GROUP_ORIGINAL_CHILD_BOUND_EXHAUSTED')
    decision = {'schema': 1, 'profile': ROUTE, 'authority': False,
        'family_anchor_id': covenant['family_anchor_id'], 'covenant_sha': pack.entry('covenant').sha256,
        'route': 'NEW_ONLY_EXISTING_DELEGATION', 'snapshot_sha': preview['candidate_sha'],
        'capsule_sha': capsule.sha256, 'actual_child_count': count,
        'execution_slot_shas': [digest(slot) for slot in branches[0]['execution_slots'][:count]],
        'source_evidence_sha': original_root_evidence(host)['source_evidence_sha']}
    state = host._group_state_in(db)
    prior = state['previews'].get('group-read-route-' + covenant['family_anchor_id'])
    if prior is not None:
        need(canonical(prior['candidate']) == canonical(decision), 'GROUP_ORIGINAL_ROUTE_CHANGED')
        return
    host.entry.family_candidates[digest(decision)] = (db, canonical(decision))
    files = FamilyFiles(host.entry.policy, host.entry.loop_guard)
    with original_root_scope(db, files, original_root_evidence(host),
            source_kind=host.chain.config['binding']['source_kind'], history_locators=history_locators) as root:
        record_route_in(db, GroupStore(state['binding_sha'], _history_partial(host.verify_in, history_locators=history_locators)), pack, decision,
                        root_closure=root, guard=host.entry.full_guard, history_locators=history_locators)


def _prepare_local_registration(host):
    """Original fixed local prefix; no caller inputs or network effect."""
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import (GroupExecutionGate, publish_first_current,
        register_first_current_in)
    from .draft_group_source_members import source_members_for_registration_in
    from .draft_group_input_files import InputFiles
    need(type(host) is GroupRuntimeHost and type(host.entry) is GroupExecutionGate,
         'GROUP_ACTUAL_HOST_REQUIRED')
    host.entry.full_guard()
    native_v2 = host.chain.source['profile'] == 'GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(host)
    workflow = host.entry.service.workflow
    files = InputFiles(host.entry.policy, host.entry.loop_guard)
    files.initialize()
    pack = publish_first_current(host)
    existing = _existing_registration(host, files, pack)
    if existing is not None:
        if native_v2:
            from .draft_group_host_review import establish_current_source_review
            establish_current_source_review(host)
        known = _known_parent(host)
        if known is not None:
            return known, files, pack, None, existing[0], existing[1], workflow
    with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
        register_first_current_in(host, db, pack, history_locators=history_locators)
        if native_v2:
            from .draft_group_host_review import local_registration_inspection_in
            current = local_registration_inspection_in(host, db,history_locators=history_locators)
            host.validate_history_in(db, history_locators=history_locators)
            bound = source_members_for_registration_in(host, db, current=current, history_locators=history_locators)
        else:
            bound = source_members_for_registration_in(host, db, history_locators=history_locators)
    registration, proof = existing or _new_registration(host, files, pack, bound['members'])
    need(canonical(registration.value['ordered_members']) == canonical(list(bound['members'])),
         'GROUP_ORIGINAL_BATCH_MEMBERS_CHANGED')
    from .draft_group_host_publisher import restore_initial_read_purposes_current_in
    with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
        restore_initial_read_purposes_current_in(host, db, history_locators=history_locators)
    if native_v2:
        from .draft_group_host_review import establish_current_source_review
        establish_current_source_review(host)
    return None, files, pack, bound, registration, proof, workflow


def prepare_current_batch(host):
    from .draft_group_runtime_host import deactivate_group_token_for_local
    from .draft_group_coverage import issue_account_coverage_in
    from .draft_group_pool_issuer import account_pool_transition_in, PoolTransition
    from .draft_group_target_creator import commit_target_from_files_in
    from .draft_group_parent_issuer import parent_creation_in, ParentCreation
    known, files, pack, bound, registration, proof, workflow = _prepare_local_registration(host)
    if known is not None:
        return known
    scope, coverage = _account_coverage(host, pack)
    deactivate_group_token_for_local(host)
    with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
        with account_pool_transition_in(host, db, coverage, history_locators=history_locators) as transition:
            PoolTransition.apply(transition, history_locators=history_locators)
        # The same observed proof and its original oldest time are retained;
        # only the pool generation/head after our own event are reflected.
        coverage = issue_account_coverage_in(host, db, scope, history_locators=history_locators)
    preview = _plan(host, coverage, bound['members'])
    capsule, targets = _publish_execution(host, files, registration, proof, preview, bound['source_rows'])
    from .draft_group_first_control import first_parent_transaction,append_parent_and_plan
    parent_scope=(first_parent_transaction(host) if is_operator(host) else
                  _history_transaction(workflow.db,write=True,physical_resources=host.entry))
    with parent_scope as (db,history_locators):
        for child, reservation, upload_reuse in targets:
            commit_target_from_files_in(host, db, child, reservation, capsule, upload_reuse, coverage, history_locators=history_locators)
        _record_new_only_route(host, db, pack, capsule, preview, history_locators=history_locators)
        with parent_creation_in(host, db, coverage, capsule, preview, history_locators=history_locators) as creation:
            if is_operator(host):append_parent_and_plan(creation,history_locators=history_locators)
            else:ParentCreation.append_and_plan(creation,history_locators=history_locators)
    host.entry.full_guard()
    return {'state': 'ORIGINAL_PARENT_REGISTERED', 'authority': False,
            'batch_handle': preview['batch_id'], 'request_key': preview['request_key'],
            'operation_ids': [child['operation_id'] for child in preview['children']],
            'draft_writes': 0, 'platform_readback': 'NOT_PERFORMED_THIS_ENTRY'}


from .draft_group_history_context import history_transaction as _history_transaction


from functools import partial as _history_partial
