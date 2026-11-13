"""Private reviewed-host registration for one no-new-image correction."""
from .contracts import WCEError
from .service import digest
from .draft_revision_service import bounded_failure

def hold():raise WCEError('DRAFT_REVISION_DIRECT_HOST_HOLD')

def _require_ready(current,row,handle,case_id):
    if (type(current) is not dict or type(row) is not dict
            or row.get('state')!='READY' or row.get('submit_count')!=0
            or row.get('task') is not None or row.get('reply') is not None
            or row.get('queries')!=0 or row.get('query_pending',False) is not False
            or handle in current.get('revision_pending_images',{})):hold()
    existing=current.get('revision_reservations',{}).get(handle)
    if existing is not None and (type(existing) is not dict or existing.get('case_id')!=case_id):hold()

@bounded_failure
def register(service,adapter,pins,deadline,*,expected_handle,cancel_guard=None):
    from .own_connection_broker import AccountService
    from .own_auth import OwnProfile
    from .draft_revision_input import RevisionInputAdapter,DirectArtifactSelection
    from .draft_revision_registration import TrustedRevisionPins,qualify,DIRECT_PROFILE
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_store import RevisionStore
    if (type(service) is not AccountService or type(adapter) is not RevisionInputAdapter
            or adapter.service is not service or type(adapter.selection) is not DirectArtifactSelection
            or type(pins) is not TrustedRevisionPins or adapter.deadline!=deadline):hold()
    gate=RevisionExecutionGate(service,deadline,cancel_guard=cancel_guard)
    with gate():
        profile=service.profile()
        if type(profile) is not OwnProfile or profile.source_kind!='OPERATOR_ATTESTED':hold()
        from pathlib import Path
        from .own_connection_policy import registry_path
        from .draft_revision_scan import for_adapter
        from .current_publication_source import Authorization
        from .draft_revision_publication_window import require_authorization_window
        guard=lambda:(service.guard(deadline) or True)
        registry=Path(service.policy.value.get('registry_path') or registry_path())
        authority=Authorization(service.policy,registry,guard,deadline,native_guard=for_adapter(adapter))
        require_authorization_window(adapter,authority)
        qualified=qualify(adapter,pins,gate)
        require_authorization_window(adapter,authority)
        if qualified.record['profile']!=DIRECT_PROFILE or qualified.case['binding']!=digest(profile.binding()):hold()
        # The trusted host pins the expected current handle. Compare it under
        # the same gate and current authorization before registering a Case.
        from .current_publication_revision_bridge import DirectPublicationBridge
        from .current_publication_revision_reservation import _no_old_submit_receipt
        import re
        if type(expected_handle) is not str or re.fullmatch(r'current-pub-[a-f0-9]{48}',expected_handle) is None:hold()
        publication, current_authority, current_guard, handle = DirectPublicationBridge(
            service,adapter,gate,qualified.case,deadline)._context()
        if handle != expected_handle:hold()
        current, row = publication.target(handle)
        publication._authority(current_authority,current_guard,row['batch_source_sha'])
        _require_ready(current,row,handle,qualified.case['id'])
        _no_old_submit_receipt(publication,handle,current_guard)
        require_authorization_window(adapter,current_authority)
        current_guard()
        store=RevisionStore(service.policy.root,qualified.case['binding'],lambda:(service.guard(deadline) or True))
        store.register(qualified.case,registration=qualified)
        return {'original_save_key':pins.original_save_key,
            'revision_artifact_handle':'revision-artifact-'+qualified.case['input_sha'],
            'revision_id':digest({'case':qualified.case['id'],'profile':qualified.case['profile']}),
            'state':'HOST_REGISTERED'}
