"""Fixed immutable Host material replay. No current source or full9 recursion."""
from . import draft_group_operator_time_v2 as time06
from pathlib import Path
import json
from .draft_group_runtime_host import need,hold,PinnedFile,OwnedConnection,ConnectionPolicy,canonical,digest
from .draft_group_read_family_store import prepared_binding,_history_file_guard,_states,_firsts
from .draft_group_input_files import InputFiles,decode
from .draft_group_history_context import current_history_policy


def _context(db,policy):
    need(type(db) is OwnedConnection and db.in_transaction and type(policy) is ConnectionPolicy
         and current_history_policy(db) is policy,'GROUP_HISTORY_POLICY_REQUIRED')


def _materials(policy,configuration_sha):
    from .group_host_jobs import fixed_history_rows
    from .draft_group_host_review import _json,CONFIG_KEYS,SEMANTIC_KEYS,semantic_scope_sha
    from .publication_contract import stable_account
    rows=fixed_history_rows(policy,configuration_sha)
    if not rows:
        from .draft_group_rich_syn_fixture import rich_syn_history_row
        synthetic=rich_syn_history_row(policy,configuration_sha)
        if synthetic is not None:rows=[synthetic]
    need(len(rows)==1,'GROUP_HISTORY_FIXED_LOCATOR_REQUIRED');row=rows[0];paths=dict(row[3]);data={}
    for name,(path,checksum) in paths.items():
        pin=PinnedFile(Path(path),checksum,2*1024*1024)
        try:data[name]=pin.raw
        finally:pin.close()
    config=_json(data['configuration'],CONFIG_KEYS,'GROUP_HOST_CONFIGURATION_V1')
    semantic=_json(data['semantic'],SEMANTIC_KEYS,'HOST_GROUP_SEMANTIC_ADOPTION_V1')
    source=decode('source',data['source']);acceptance=json.loads(data['review'])
    need(acceptance.get('profile')==('GROUP_HOST_RUNTIME_POLICY_ACCEPTANCE_V1' if source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' else 'GROUP_HOST_REVIEW_ACCEPTANCE_V1') and acceptance.get('authority') is False
         and acceptance.get('configuration_sha')==configuration_sha and acceptance.get('semantic_adoption_sha')==paths['semantic'][1]
         and acceptance.get('source_material_sha')==paths['source'][1]
         and acceptance.get('artifact_inventory_sha')==digest(semantic['artifact_inventory'])
         and source['semantic_scope_sha']==semantic_scope_sha(semantic),'GROUP_HISTORY_ACCEPTANCE')
    need(config['semantic_adoption_sha']==paths['semantic'][1] and config['source_material_sha']==paths['source'][1],'GROUP_HISTORY_MATERIAL')
    return row,paths,config,semantic,source


def _validate_source_fact_history_values_in(db,candidate,history_policy,states=None,events=None):
    from .draft_group_source_facts import validate_source_fact
    _context(db,history_policy);c=validate_source_fact(candidate)
    if c['profile'] in ('GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1',time06.SOURCE_FACTS_PROFILE_V2):
        from .draft_group_operator_history import validate_source_fact_history_in
        return validate_source_fact_history_in(db,c,history_policy,states=states,events=events)
    row,paths,config,semantic,source=_materials(history_policy,c['source_descriptor']['configuration_sha'])
    need(c['binding_sha']==digest(config['binding']) and config['binding']['tenant']==history_policy.actor.tenant_id and config['binding']['principal']==history_policy.actor.principal_id and config['binding']['account']==history_policy.data['appid'],'GROUP_HISTORY_BINDING')
    descriptor={'configuration_sha':paths['configuration'][1],'semantic_adoption_sha':paths['semantic'][1],
        'role_tuple_sha':digest(config['role_source_descriptors']),'qa_adoption_sha':digest(semantic['qa_adoptions']),
        'artifact_inventory_sha':digest(semantic['artifact_inventory'])}
    descriptor_base={key:c['source_descriptor'][key]for key in descriptor}
    if c['profile']=='GROUP_ADMISSION_SOURCE_FACTS_V1':
        need(c['source_descriptor']==descriptor,'GROUP_HISTORY_DESCRIPTOR')
    else:
        need(c['profile']=='GROUP_ADMISSION_SOURCE_FACTS_V2'and source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'
             and c['current_source_review_sha']is not None,'GROUP_HISTORY_DESCRIPTOR')
    need(descriptor_base==descriptor and c['source_material_sha']==paths['source'][1]
         and c['host_acceptance_sha']==paths['review'][1] and c['covenant_sha']==config['first_covenant_sha'],'GROUP_HISTORY_DESCRIPTOR')
    files=InputFiles(history_policy,lambda:_history_file_guard(history_policy))
    reg=files.read('registration',c['registration_sha']);proof=files.read('proof',c['registration_proof_sha']);material=files.read('source',c['source_material_sha'])
    need(material.raw==data_source_bytes(paths['source']) and reg.value['source_material_sha']==(c['source_material_sha'] if c['current_source_review_sha'] is None else proof.value['source_material_sha'])
         and reg.value['family_id']==c['family_id'] and reg.value['binding']==config['binding']
         and reg.value['artifacts']==semantic['artifact_inventory'] and proof.value['registration_sha']==reg.sha256
         and proof.value['source_material_sha']==reg.value['source_material_sha'] and proof.value['qualified_binding']==config['binding']
         and proof.value['artifact_inventory_sha']==descriptor['artifact_inventory_sha']
         and (proof.value['helper_acceptance']['sha256']==c['host_acceptance_sha'] or c['current_source_review_sha'] is not None),'GROUP_HISTORY_REGISTRATION')
    if states is None:states=_states(db)
    roots=[p for account,p in _firsts(states) if p['candidate']['family_anchor_id']==c['family_id']]
    need(len(roots)==1,'GROUP_HISTORY_FIRST_REQUIRED');first=roots[0]['candidate']
    need(first['first_proof_sha']==c['first_proof_sha'] and first['covenant_sha']==c['covenant_sha']
         and _original_scope(db,files.policy,c['covenant_sha'])==c['original_scope_sha'],'GROUP_HISTORY_FIRST_BINDING')
    if c['current_source_review_sha'] is not None:
        from .draft_group_source_review import validate_source_review_binding_for_fact_from_replay_in
        return validate_source_review_binding_for_fact_from_replay_in(db,history_policy,c,states,events)
    return None


def validate_source_fact_history_in(db,candidate,history_policy):
    _context(db,history_policy)
    from .draft_group_response_history import read_group_replay_snapshot_in,release_group_replay_snapshot_in
    states,events=read_group_replay_snapshot_in(db)
    try:return _validate_source_fact_history_values_in(db,candidate,history_policy,states,events)
    finally:release_group_replay_snapshot_in(db,states,events)


def validate_source_fact_history_from_replay_in(db,candidate,history_policy,states,events):
    _context(db,history_policy)
    from .draft_group_response_history import verify_group_replay_inputs_in
    verify_group_replay_inputs_in(db,states,events)
    return _validate_source_fact_history_values_in(db,candidate,history_policy,states,events)


def data_source_bytes(pair):
    path,checksum=pair;pin=PinnedFile(Path(path),checksum,2*1024*1024)
    try:return pin.raw
    finally:pin.close()


def validate_token_history_in(db,candidate,history_policy):
    from .draft_group_token_attempt_store import validate_token_candidate
    from .draft_group_source_facts import query_source_fact_in
    _context(db,history_policy);c=validate_token_candidate(candidate)
    fact=query_source_fact_in(db,c['pins']['source_qualification_locator'])
    # B's query returns detached locator/candidate facts. Exact immutable source
    # candidate is replayed independently before the token reducer uses it.
    need(type(fact) is dict and set(fact)=={'candidate','locator'},'GROUP_TOKEN_HISTORY_SOURCE_REQUIRED')
    f=fact['candidate']
    if type(f) is dict and f.get('profile')in ('GROUP_ADMISSION_SOURCE_FACTS_V1','GROUP_ADMISSION_SOURCE_FACTS_V2','GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1',time06.SOURCE_FACTS_PROFILE_V2):
        validate_source_fact_history_in(db,f,history_policy)
        need(c['pins']['source_material_sha']==f['source_material_sha'] and c['pins']['registration_sha']==f['registration_sha']
             and c['pins']['helper_acceptance_sha']==f['host_acceptance_sha'],'GROUP_TOKEN_HISTORY_PINS')
    else:hold('GROUP_TOKEN_HISTORY_SOURCE_REQUIRED')


def read_original_covenant_in(db,policy,covenant_sha):
    _context(db,policy)
    from .draft_group_read_family_files import FamilyFiles,_OBSERVATIONS
    from .draft_group_read_family_store import _ROOT_CURRENT,_RootClosure,_SEAL,_TransactionFence
    from .draft_group_runtime_host import _THREAD
    active=_ROOT_CURRENT.get();observation=_OBSERVATIONS.get()
    if type(active) is _RootClosure:
        need(active.active and active.seal is _SEAL and active.db is db and active.thread==_THREAD()
             and type(active.files) is FamilyFiles and active.files.policy is policy
             and type(active.transaction) is _TransactionFence and active.transaction.db is db,
             'GROUP_HISTORY_FAMILY_CONTEXT_CHANGED')
        need(observation is not None and observation[0] is active.files and observation[1]==_THREAD(),
             'GROUP_HISTORY_FAMILY_CONTEXT_CHANGED')
        # Original RootClosure.current is already checking full9 on this stack.
        # Calling it here would recurse. Reuse its exact observed reader rather
        # than creating a second FamilyFiles that violates the original fence.
        active.transaction.check()
        value=active.files.read('covenant',covenant_sha)
        active.transaction.check()
        return value
    need(observation is None,'GROUP_HISTORY_FAMILY_CONTEXT_CHANGED')
    files=FamilyFiles(policy,lambda:_history_file_guard(policy))
    return files.read('covenant',covenant_sha)


def _original_scope(db,policy,covenant_sha):
    return read_original_covenant_in(db,policy,covenant_sha).value['original_scope_sha']
