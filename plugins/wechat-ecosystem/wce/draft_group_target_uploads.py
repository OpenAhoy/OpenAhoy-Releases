"""Resolve designated zero-transmission slots from original successful roots."""
from .contracts import WCEError
from .service import canonical,digest


def need(value,code='GROUP_TARGET_UPLOAD_REUSE_HOLD'):
    if value is not True:raise WCEError(code)


def guard_target_approval_in(workflow,db,profile,manifest):
    if db.execute('PRAGMA user_version').fetchone()[0]!=9:return None
    from .draft_group_target_scope import validate_target_approval_in
    return validate_target_approval_in(workflow,db,profile,manifest)


def guard_target_dispatch_in(workflow,db,profile,manifest,operation,slot, *, history_locators=None):
    if db.execute('PRAGMA user_version').fetchone()[0]!=9:return None
    from .draft_group_target_scope import validate_target_dispatch_in
    return validate_target_dispatch_in(workflow,db,profile,manifest,operation,slot, history_locators=history_locators)


def resolve_target_uploads_in(workflow,db,profile,manifest,manifest_sha, *, history_locators=None):
    if db.execute('PRAGMA user_version').fetchone()[0]!=9:return None
    from .draft_group_target_scope import (_target_designation_for,
        validate_target_write_in,target_article_metadata)
    designated=_target_designation_for(db,manifest_sha)
    if designated is None:return None
    need(manifest_sha==digest(manifest) and designated['binding_sha']==digest(manifest['binding'])
         and profile.binding()==manifest['binding'],'GROUP_TARGET_UPLOAD_BINDING')
    validate_target_write_in(workflow,db,profile,manifest,'ADD_UPLOAD_REUSE', history_locators=history_locators)
    from .draft_group_target_files import PinnedTargetFiles
    from .draft_group_read_family_store import _history_file_guard
    policy=workflow.policy;files=PinnedTargetFiles(policy,lambda:_history_file_guard(policy))
    h=files.read('child',designated['child_sha']);u=files.read('upload_reuse',designated['upload_map_sha'])
    files.read('reservation',designated['manifest_sha'],expected_sha=designated['reservation_sha'])
    files.read('execution',designated['capsule_sha'])
    need(h.value['manifest_json']==canonical(manifest) and h.value['manifest_sha']==manifest_sha,
         'GROUP_TARGET_UPLOAD_MANIFEST_CHANGED')
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    from .draft_group_upload_reuse_projection import derive_reuse_projection
    entries=u.value['entries'];need(len(entries)==len(manifest['assets']),'GROUP_TARGET_UPLOAD_COVERAGE')
    facts=[];receipts=[]
    for asset,entry in zip(manifest['assets'],entries):
        original=entry['original_upload']
        actual,receipt=read_original_upload_success_with_proofs_in(workflow,db,profile,original['base_step_pin']['id'], history_locators=history_locators)
        need(entry['target_slot']==asset['slot'] and entry['target_asset']==asset,'GROUP_TARGET_UPLOAD_SLOT')
        for key in ('selector','asset','operation','slot','base_step_pin','snapshot','result_digest','proof_files'):
            need(canonical(actual[key])==canonical(original[key]),'GROUP_TARGET_UPLOAD_ORIGINAL_CHANGED')
        need(all(actual['asset'][key]==asset[key]for key in
                 ('asset_ref','role','declared_type','sha256','size')),'GROUP_TARGET_UPLOAD_ASSET_CHANGED')
        source=entry['source_member']
        need(source['source_manifest_selector']==actual['selector']
             and source['source_asset_slot']==actual['slot']
             and source['source_asset_ref']==actual['asset']['asset_ref'],'GROUP_TARGET_UPLOAD_SOURCE_CHANGED')
        facts.append({'target_slot':asset['slot'],'mapping':actual['mapping'],'snapshot':actual['snapshot']})
        receipts.append(receipt)
    metadata=target_article_metadata(manifest,h.value)
    derived=derive_reuse_projection(manifest,facts,article_metadata=metadata)
    need(canonical(derived['projection'])==h.value['projection_json'],'GROUP_TARGET_UPLOAD_PROJECTION_CHANGED')
    for receipt in receipts:receipt.collective_fence()
    files.collective_fence()
    return derived['mappings'],derived['snapshots']
