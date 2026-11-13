"""Idempotently intake an already-uploaded pending image into local OwnStore.

No network call or draft/publication write. The local asset key is bound to
the immutable proposal, so a crash cannot mint a second asset on recovery.
"""
from hashlib import sha256
from .contracts import WCEError
from .service import digest

def hold():raise WCEError('DRAFT_REVISION_PENDING_ASSET_HOLD')

def receive(store,handle,adapter,pins,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_input import RevisionInputAdapter,PendingImageSelection
    from .draft_revision_registration import TrustedRevisionPins,verify_pins
    from .draft_revision_pending_upload import validate as validate_upload,_qualified_profile
    from .own_connection_workflow import PersistentWorkflow
    from .own_connection_input import stage,verify
    if (type(store) is not Store or type(adapter) is not RevisionInputAdapter
            or type(adapter.selection) is not PendingImageSelection or type(pins) is not TrustedRevisionPins
            or type(gate) is not RevisionExecutionGate or gate.service is not adapter.service
            or gate.service.policy is not store.policy or gate.deadline!=adapter.deadline
            or gate.held() is not True or not callable(guard)):hold()
    from .draft_revision_publication_window import require_authorization_window
    require_authorization_window(adapter,authority)
    service=adapter.service;workflow=service.workflow
    if type(workflow) is not PersistentWorkflow or workflow.policy is not store.policy:hold()
    def current():
        guard();verify_pins(pins,adapter)
        if gate.held() is not True:hold()
        observation=adapter.inspect_pending();value,row=store.target(handle)
        pending=value.get('revision_pending_images',{}).get(handle)
        baseline=value.get('revision_pending_baselines',{}).get(handle)
        upload=value.get('revision_pending_uploads',{}).get(handle)
        if (type(pending) is not dict or pending['proposal']!=observation.proposal
                or type(upload) is not dict or upload.get('state')!='SUCCEEDED'
                or row['batch_source_sha']!=authority.source_sha):hold()
        validate_upload(upload,pending,baseline);_qualified_profile(service.profile(),pending['proposal'])
        store._authority(authority,guard,row['batch_source_sha'])
        return pending,upload
    pending,upload=current();proposal=pending['proposal'];selection=adapter.selection
    source=selection.root/selection.new_image_relative_path
    name=stage(store.policy,source,proposal['mime'])
    raw=verify(store.policy,name,proposal['mime'])
    if len(raw)!=proposal['source_size'] or sha256(raw).hexdigest()!=proposal['source_sha256']:hold()
    if current()!=(pending,upload):hold()
    key='revision-asset-'+pending['proposal_sha256']
    profile=service.profile();workflow.activate(profile,deadline=gate.deadline)
    response=workflow.call(store.policy.actor,'own.assets.receive',{'connection_id':profile.connection_id,
        'request_key':key,'relative_path':name,'role':'body','declared_type':proposal['mime']})
    if type(response) is not dict:hold()
    envelope={'connection_id':profile.connection_id,'request_key':key,'input_state':'COMMITTED'}|workflow.evidence()
    if any(response.get(k)!=v for k,v in envelope.items()):hold()
    value={k:v for k,v in response.items() if k not in envelope}
    if (set(value)!={'asset_ref','role','declared_type','size','sha256'}
            or value['role']!='body' or value['declared_type']!=proposal['mime']
            or value['size']!=proposal['source_size'] or value['sha256']!=proposal['source_sha256']):hold()
    if current()!=(pending,upload):hold()
    return value
