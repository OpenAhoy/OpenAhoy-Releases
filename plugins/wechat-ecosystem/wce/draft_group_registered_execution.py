"""Execute only an existing registered NEW_ONLY child and its original slots.

There is no registration, source, media reference, budget or grant argument.
The actual complete Host and durable original Parent must already exist. A
consumed/unknown claim is never converted into a request to send it again.
"""
from .contracts import WCEError
from .service import digest


def need(value, code='GROUP_REGISTERED_EXECUTION_HOLD'):
    if value is not True:
        raise WCEError(code)


def _bind_original_registration_in(host, db, operation_id, *, history_locators=None):
    from .draft_group_parent import check_parent_records_in
    from .draft_group_input_files import InputFiles
    history = check_parent_records_in(db, history_policy=host.entry.policy, history_locators=history_locators)
    record = history['executions'].get(operation_id)
    need(record is not None, 'GROUP_PARENT_REQUIRED')
    parent = record['parent']
    need(parent['binding_sha'] == digest(host.chain.config['binding']), 'GROUP_PARENT_BINDING_CHANGED')
    inputs = InputFiles(host.entry.policy, host.entry.loop_guard)
    registration = inputs.read('registration', parent['registration_sha'])
    proof = inputs.read('proof', parent['registration_proof_sha'])
    host.bind_registration_in(db, registration, proof, history_locators=history_locators)
    need(host._registration['registration_sha'] == parent['registration_sha']
         and host._registration['registration_proof_sha'] == parent['registration_proof_sha'],
         'GROUP_PARENT_REGISTRATION_CHANGED')


def _state_in(host, db, operation_id):
    state = host._group_state_in(db)
    operation = state['operations'].get(operation_id)
    need(operation is not None, 'GROUP_PARENT_REQUIRED')
    need(operation['plan']['route'] == 'CREATE_NEW' and not operation['old_refs'],
         'GROUP_REPLACEMENT_EXACT_REVIEW_REQUIRED')
    return state, operation


def _scope_in(host, db, operation_id, *, history_locators=None):
    from .draft_group_runtime_host import (qualify_target_preparation,
                                           validate_admission_scope)
    scopes = getattr(host.entry, '_registered_child_scopes', None)
    if scopes is None:
        scopes = {}
        host.entry._registered_child_scopes = scopes
    scope = scopes.get(operation_id)
    if scope is None:
        current = host.current_no_token_in(db, host._source, history_locators=history_locators)
        scope = qualify_target_preparation(host, host._source, current, None, operation_id, db, history_locators=history_locators)
        scopes[operation_id] = scope
    else:
        validate_admission_scope(scope, db=db, history_locators=history_locators)
    return scope


def _status_in(host, db, operation_id, *, fresh_slot=None):
    _, operation = _state_in(host, db, operation_id)
    counts = {kind: sum(c['kind'] == kind for c in operation['claims']) for kind in ('GET', 'ADD', 'DELETE')}
    budget = operation['plan']['budget']
    epoch = digest({'profile': 'GROUP_ENTRY_EPOCH_V1', 'entry_id': host.entry.id})
    observations = [c for c in operation['claims'] if c['kind'] == 'GET' and c['slot'] == fresh_slot]
    matched = (len(observations) == 1 and observations[0]['state'] == 'OBSERVED'
               and observations[0]['outcome'] == 'MATCHED' and observations[0]['epoch'] == epoch)
    return {'authority': False, 'operation_id': operation_id, 'state': operation['state'],
            'counts': counts,
            'remaining': {'GET': budget['get_cap'] - counts['GET'],
                          'ADD': budget['add_cap'] - counts['ADD'],
                          'DELETE': budget['delete_cap'] - counts['DELETE']},
            'new_reference_sha': operation['new_ref_sha'],
            'readback_state': 'MATCHED_THIS_EXECUTION' if matched else 'JOURNAL_OBSERVATION_ONLY',
            'platform_originality': 'NOT_SUBMITTED_NO_SUPPORTED_OFFICIAL_PATH'}


def _original_slot(operation, slot):
    matches = [c for c in operation['claims'] if c['slot'] == slot]
    need(not matches, 'GROUP_ORIGINAL_SLOT_ALREADY_CONSUMED')


def _prepare_operator_review(host,operation_id):
    # A fresh public entry has a complete service, but no admission receipt.
    # First re-read original Parent/registration; exit its RO/H before the
    # existing normal Review writer commit and separate fresh-H readback.
    from .draft_group_host_review import is_operator,establish_current_source_review
    if not is_operator(host):return
    workflow=host.entry.service.workflow
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db,history):
        _bind_original_registration_in(host,db,operation_id,history_locators=history)
        from .draft_group_first_control import require_bound_parent_in
        require_bound_parent_in(host,db,operation_id,history_locators=history)
        _,operation=_state_in(host,db,operation_id)
        if operation['state']=='COMPLETE':return
        need(not operation['cancelled'] and operation['state'] not in ('UNKNOWN','HOLD','WAITING'),
             'GROUP_RESULT_UNKNOWN_OR_INACTIVE')
        need(not any(c['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED')
                     for c in operation['claims']),'GROUP_RESULT_UNKNOWN')
    establish_current_source_review(host)


def run_registered_child(host, operation_id, *, readback_phase=None):
    """Use ADD -> NEW -> SWITCH -> FINAL_NEW -> COMPLETE once, under one Gate.

    ``readback_phase`` chooses only an existing public NEW/FINAL contract. A
    historical completed result is returned locally and does not acquire a
    token or relabel an old GET as a new observation.
    """
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate, deactivate_group_token_for_local
    from .draft_group_input_files import _id
    from .draft_group_provider import OfficialGroupProvider
    from .draft_group_local_transition import new_only_local_transition_in, LocalTransition
    need(type(host) is GroupRuntimeHost and type(host.entry) is GroupExecutionGate,
         'GROUP_ACTUAL_HOST_REQUIRED')
    _id(operation_id)
    need(readback_phase is None or readback_phase in ('NEW', 'FINAL'), 'GROUP_READ_PHASE_NOT_APPLICABLE')
    host.entry.held_pure()
    _prepare_operator_review(host,operation_id)
    workflow = host.entry.service.workflow
    with _history_transaction(workflow.db,physical_resources=host.entry) as (db, history_locators):
        _bind_original_registration_in(host, db, operation_id, history_locators=history_locators)
        from .draft_group_first_control import require_bound_parent_in
        require_bound_parent_in(host,db,operation_id,history_locators=history_locators)
        _, operation = _state_in(host, db, operation_id)
        if operation['state'] == 'COMPLETE':
            return _status_in(host, db, operation_id)
        need(not operation['cancelled'] and operation['state'] not in ('UNKNOWN', 'HOLD', 'WAITING'),
             'GROUP_RESULT_UNKNOWN_OR_INACTIVE')
        need(not any(c['state'] in ('CONSUMED_UNKNOWN', 'UNKNOWN', 'KNOWN_REJECTED')
                     for c in operation['claims']), 'GROUP_RESULT_UNKNOWN')
        scope = _scope_in(host, db, operation_id, history_locators=history_locators)
    provider = OfficialGroupProvider(host.entry.service, host, host.entry)
    if readback_phase is not None:
        slot = 'NEW' if readback_phase == 'NEW' else 'FINAL_NEW'
        with workflow.db.transaction() as db:
            _, operation = _state_in(host, db, operation_id)
            required_state = 'NEW_OBSERVED' if slot == 'NEW' else 'SWITCHED_OLD_RETAINED'
            need(operation['state'] == required_state, 'GROUP_READ_PHASE_NOT_APPLICABLE')
            _original_slot(operation, slot)
        provider.run_child(scope, slot)
        with workflow.db.transaction() as db:
            return _status_in(host, db, operation_id, fresh_slot=slot)
    # Five fixed states, no general retry loop or unknown-result replay. The
    # original reducer is checked again before each preparation and effect.
    for _ in range(5):
        with workflow.db.transaction() as db:
            _, operation = _state_in(host, db, operation_id)
            state = operation['state']
            need(not operation['cancelled'] and not any(
                c['state'] in ('CONSUMED_UNKNOWN', 'UNKNOWN', 'KNOWN_REJECTED') for c in operation['claims']),
                'GROUP_RESULT_UNKNOWN')
            if state == 'COMPLETE':
                return _status_in(host, db, operation_id, fresh_slot='FINAL_NEW')
            if state == 'PLANNED':
                slot = 'ADD'
            elif state == 'NEW_OBSERVED':
                slot = 'NEW'
            elif state == 'SWITCHED_OLD_RETAINED':
                final = [c for c in operation['claims'] if c['kind'] == 'GET' and c['slot'] == 'FINAL_NEW']
                need(len(final) <= 1, 'GROUP_ORIGINAL_SLOT_CHANGED')
                if final:
                    need(final[0]['state'] == 'OBSERVED' and final[0]['outcome'] == 'MATCHED',
                         'GROUP_FINAL_READ_REQUIRED')
                    slot = None
                else:
                    slot = 'FINAL_NEW'
            elif state == 'NEW_VERIFIED':
                slot = None
            else:
                raise WCEError('GROUP_REGISTERED_PHASE_NOT_SUPPORTED')
            if slot is not None:
                _original_slot(operation, slot)
        if slot is not None:
            provider.run_child(scope, slot)
        else:
            deactivate_group_token_for_local(host)
            action = 'SWITCH' if state == 'NEW_VERIFIED' else 'COMPLETE'
            with _history_transaction(workflow.db, write=True,physical_resources=host.entry) as (db, history_locators):
                with new_only_local_transition_in(host, db, scope, action, history_locators=history_locators) as transition:
                    LocalTransition.apply(transition, history_locators=history_locators)
    with workflow.db.transaction() as db:
        _, operation = _state_in(host, db, operation_id)
        need(operation['state'] == 'COMPLETE', 'GROUP_REGISTERED_PHASE_LIMIT')
        return _status_in(host, db, operation_id, fresh_slot='FINAL_NEW')


from .draft_group_history_context import history_transaction as _history_transaction
