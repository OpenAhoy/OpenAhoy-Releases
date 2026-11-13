"""Operator SourceFacts historical integrity; never live source qualification."""
from . import draft_group_operator_time_v2 as time06
from .draft_group_runtime_host import need,canonical,digest
from .draft_group_source_facts import validate_source_fact,PROFILE_OPERATOR


def validate_source_fact_history_in(db,candidate,policy,*,states=None,events=None):
    from .draft_group_host_history import _context,_original_scope
    from .draft_group_operator_review_chain import read_operator_review_materials_in
    from .draft_group_read_family_store import _states,_firsts,_history_file_guard
    from .draft_group_input_files import InputFiles
    from .draft_group_source_review import validate_source_review_binding_for_fact_from_replay_in
    from .draft_group_response_history import read_group_replay_snapshot_in,release_group_replay_snapshot_in
    _context(db,policy);c=validate_source_fact(candidate)
    need(c['profile'] in (PROFILE_OPERATOR,time06.SOURCE_FACTS_PROFILE_V2),'GROUP_OPERATOR_HISTORY_PROFILE')
    owned_snapshot=events is None
    if owned_snapshot:states,events=read_group_replay_snapshot_in(db)
    materials=None
    try:
        from .own_history_locators import borrow_entered_history
        materials=read_operator_review_materials_in(db,policy,c['source_descriptor']['configuration_sha'],
            history_locators=borrow_entered_history(policy,db))
        config=materials.config;semantic=materials.semantic
        need(c['source_descriptor']==materials.descriptor(c['source_descriptor']['current_binding_sha'])
             and c['binding_sha']==digest(config['binding'])
             and config['binding']['tenant']==policy.actor.tenant_id
             and config['binding']['principal']==policy.actor.principal_id
             and config['binding']['account']==policy.data['appid']
             and c['source_material_sha']==materials.source_sha
             and c['host_acceptance_sha']==materials.review_sha
             and c['covenant_sha']==config['first_covenant_sha'], 'GROUP_OPERATOR_HISTORY_MATERIAL')
        files=InputFiles(policy,lambda:_history_file_guard(policy))
        registration,rpin=files._entry('registration',c['registration_sha'])
        proof,ppin=files._entry('proof',c['registration_proof_sha'])
        source,spin=files._entry('source',c['source_material_sha'])
        reg,p=registration.value,proof.value
        need(source.raw==materials.source_raw and reg['source_material_sha']==c['source_material_sha']
             and reg['family_id']==c['family_id'] and reg['binding']==config['binding']
             and reg['artifacts']==materials.artifact_inventory
             and p['registration_sha']==registration.sha256 and p['source_material_sha']==source.sha256
             and p['qualified_binding']==config['binding']
             and p['artifact_inventory_sha']==semantic['artifact_inventory_sha']
             and p['helper_acceptance']['sha256']==materials.review_sha,
             'GROUP_OPERATOR_HISTORY_REGISTRATION')
        roots=[p for _,p in _firsts(states) if p['candidate']['family_anchor_id']==c['family_id']]
        need(len(roots)==1,'GROUP_HISTORY_FIRST_REQUIRED');first=roots[0]['candidate']
        need(first['first_proof_sha']==c['first_proof_sha'] and first['covenant_sha']==c['covenant_sha']
             and _original_scope(db,policy,c['covenant_sha'])==c['original_scope_sha'],
             'GROUP_HISTORY_FIRST_BINDING')
        review=validate_source_review_binding_for_fact_from_replay_in(db,policy,c,states,events)
        files._pure_entries((('registration',registration.key,rpin),('proof',proof.key,ppin),('source',source.key,spin)))
        materials.collective_fence()
        return review
    finally:
        from .draft_group_pin_resources import close_all
        callbacks=[] if materials is None else [materials.close]
        if owned_snapshot:callbacks.append(lambda:release_group_replay_snapshot_in(db,states,events))
        import sys
        close_all(callbacks,sys.exc_info()[1])
