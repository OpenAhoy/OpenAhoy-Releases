"""The fixed local-only D -> original prepare INSERT path.

Reservations and child/capsule/upload files must already be durably published
by the private Host. This code never receives an image, creates an upload row,
approves a request, sends HTTP, begins a transaction or commits the caller DB.
"""
from .contracts import WCEError
from .service import canonical,digest
from .own_connection_workflow import PersistentWorkflow
from .own_validation_scope import OwnedConnection,_transaction_marker
from .own_contracts import validate


def need(value,code='GROUP_TARGET_PREPARATION_HOLD'):
    if value is not True:raise WCEError(code)


def _fixed_arguments(profile,manifest,manifest_sha):
    # This stable key is not a public override and is not the business ADD key.
    arguments={'connection_id':profile.connection_id,'request_key':'group-target-'+manifest_sha}
    if manifest['schema'] in (2,3):arguments['document']=manifest['document']
    else:arguments['article']=manifest['article']
    validate('own.documents.prepare' if 'document' in arguments else 'own.articles.prepare',arguments)
    parameters={k:v for k,v in arguments.items()if k not in ('connection_id','request_key')}
    return arguments,parameters


def _read_files(host,child,reservation,capsule,upload_reuse,*,files=None):
    from .draft_group_input_files import FileEvidence
    from .draft_group_target_files import PinnedTargetFiles
    evidence=(child,reservation,capsule,upload_reuse)
    need(all(type(e)is FileEvidence for e in evidence),'GROUP_TARGET_EVIDENCE_REQUIRED')
    need(tuple(e.role for e in evidence)==('child','reservation','execution','upload_reuse'),
         'GROUP_TARGET_EVIDENCE_ROLE')
    if files is None:files=PinnedTargetFiles(host.entry.policy,host.entry.loop_guard)
    for e in evidence:need(files.read(e.role,e.key,expected_sha=e.sha256)==e,'GROUP_TARGET_FILE_CHANGED')
    files.collective_fence()
    return files


def _cached_designation_in(host,db,manifest,child,reservation,capsule,upload_reuse,result):
    """A previous normal commit is observation only, never a new owner."""
    value=child.value;state=host._group_state_in(db)
    preview=state['previews'].get('group-target-'+value['manifest_sha'])
    need(preview is not None,'GROUP_TARGET_PREEXISTING_ORDINARY')
    expected={'schema':1,'profile':'GROUP_TARGET_DESIGNATION_V1','authority':False,
        'binding_sha':digest(manifest['binding']),'operation_id':value['operation_id'],
        'selector':value['selector'],'manifest_sha':value['manifest_sha'],
        'capsule_sha':capsule.sha256,'child_sha':child.sha256,'upload_map_sha':upload_reuse.sha256,
        'reservation_sha':reservation.sha256,'registration_sha':reservation.value['registration_sha'],
        'registration_proof_sha':reservation.value['proof_sha']}
    need(canonical(preview['candidate'])==canonical(expected),'GROUP_TARGET_CACHED_DESIGNATION_CHANGED')
    need(result=={'bundle_id':manifest['bundle_id'],'version':manifest['version'],
                  'revision':manifest['revision'],'content_digest':value['manifest_sha']},
         'GROUP_TARGET_CACHED_RESULT_CHANGED')
    return result


def commit_target_from_files_in(host,db,child,reservation,capsule,upload_reuse,coverage, *, history_locators=None):
    from .draft_group_target_scope import target_preparation_in
    from .draft_group_store import GroupStore
    from .own_group_json import read
    need(type(db)is OwnedConnection and _transaction_marker(db)is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==0,'GROUP_TARGET_WRITE_TRANSACTION_REQUIRED')
    workflow=host.entry.service.workflow
    need(type(workflow)is PersistentWorkflow,'GROUP_TARGET_WORKFLOW_REQUIRED')
    profiles=tuple(workflow.registry.profiles.values())
    need(len(profiles)==1,'GROUP_TARGET_PROFILE_REQUIRED');profile=profiles[0]
    need(profile.binding()==host.chain.config['binding'],'GROUP_TARGET_BINDING_CHANGED')
    lease=workflow._lease(profile)
    need(lease is None and workflow.active_token is None,'GROUP_TARGET_LOCAL_NO_TOKEN')
    host.current_no_token_in(db,host._source, history_locators=history_locators)
    files=_read_files(host,child,reservation,capsule,upload_reuse)
    value=child.value;manifest=read(value['manifest_json'],value['manifest_sha'])
    need(manifest['binding']==profile.binding(),'GROUP_TARGET_BINDING_CHANGED')
    arguments,parameters=_fixed_arguments(profile,manifest,value['manifest_sha'])
    workflow._resource(db,profile, history_locators=history_locators)
    previous=workflow._old_input(db,profile,'prepare',arguments['request_key'],parameters)
    if previous is not None:
        result=_cached_designation_in(host,db,manifest,child,reservation,capsule,upload_reuse,previous)
        host.current_no_token_in(db,host._source, history_locators=history_locators)
        _read_files(host,child,reservation,capsule,upload_reuse,files=files)
        host.pure_release_fence()
        return result
    workflow._current(profile,lease,'local.write')
    with target_preparation_in(host,db,child,reservation,capsule,upload_reuse,coverage,files=files, history_locators=history_locators)as scope:
        need(scope.workflow is workflow and scope.profile is profile and scope.lease is lease,
             'GROUP_TARGET_SCOPE_CHANGED')
        scope.check()
        is_document,document,assets=workflow._prepare_content_in(db,profile,arguments,parameters)
        # The actual scope has proved every slot's original successful upload.
        # This path never calls an encoder or makes a new transmission promise.
        current,candidate=workflow._prepare_manifest_from_content_in(db,profile,arguments,parameters,
            is_document,document,assets,identity=(manifest['bundle_id'],manifest['version']))
        need(canonical(current)==value['manifest_json'] and candidate.content_digest==value['manifest_sha'],
             'GROUP_TARGET_PREPARE_CANDIDATE_CHANGED')
        scope.check()
        store=GroupStore(digest(profile.binding()),_history_partial(host.verify_in, history_locators=history_locators))
        store.register_preview_in(db,**scope.designation_payload(), history_locators=history_locators)
        # No callbacks or file/history reads may be inserted into this gap.
        result=workflow._insert_prepare_records_in(db,profile,lease,arguments,parameters,current)
        scope.finish()
        _read_files(host,child,reservation,capsule,upload_reuse,files=files);host.pure_release_fence()
        return result


from functools import partial as _history_partial
