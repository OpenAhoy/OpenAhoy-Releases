"""Current-host execution of an already durably registered original correction.

No registration, source/route/provider argument or new authorization is accepted
from a tool. Local status does not construct an AccountService or acquire tokens.
"""
from copy import deepcopy
from .contracts import WCEError
from .service import canonical,digest
from .draft_revision_store import RevisionStore,OFFICIAL_PROVIDER


def hold():raise WCEError('DRAFT_REVISION_REGISTERED_CASE_REQUIRED')


def selected(policy,args):
    from .draft_revision_guard import policy_binding,historical_identity_guard
    history=historical_identity_guard(policy)
    store=RevisionStore(policy.root,digest(policy_binding(policy,'OPERATOR_ATTESTED')),
        history,history_guard=history)
    import os
    if not os.path.lexists(store.root) and not os.path.lexists(store.anchor):hold()
    with store.connection() as db:
        matches=[]
        for row in db.execute('SELECT id FROM cases'):
            state=store._state(db,row['id']);case=state['case'];record=state['registration']
            if case['provider_profile']!=OFFICIAL_PROVIDER:continue
            revision_id=digest({'case':case['id'],'profile':case['profile']})
            if 'revision_id' in args:
                accepted=args['revision_id']==revision_id
            else:
                accepted=(record['acquisition']['original_save_key']==args['original_save_key']
                    and args['revision_artifact_handle']=='revision-artifact-'+case['input_sha'])
            if accepted:matches.append(state)
        if len(matches)!=1:hold()
    return store,deepcopy(matches[0])


def local_status(policy,args):
    store,state=selected(policy,args)
    from .draft_revision_service import status_value
    return status_value(store.state(state['case']['id']),
        comparison_profile=state['registration']['input']['preservation']['profile'])


def execute(service,name,args,deadline,*,cancel_guard=None):
    from .draft_revision_native_source import SourceHold
    from .draft_revision_errors import source_failure
    try:
        return _execute(service,name,args,deadline,cancel_guard=cancel_guard)
    except SourceHold as error:
        raise source_failure(error) from None


def _execute(service,name,args,deadline,*,cancel_guard=None):
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_registration import restore_adapter
    from .draft_revision_provider import OfficialRevisionProvider
    from .draft_revision_service import RevisionContext,DraftRevisionService
    if args['connection_id']!=service.policy.data['connection_id']:hold()
    # Cancellation is scoped to the current Gate context. Shared broker/workflow
    # liveness is never overwritten by a queued or concurrent revision call.
    try:store,state=selected(service.policy,args)
    except WCEError as error:
        if name not in {'own.drafts.revisions.prepare','own.drafts.revisions.execute','own.drafts.revisions.readback'} or error.code!='DRAFT_REVISION_REGISTERED_CASE_REQUIRED':raise
        from .draft_revision_pending_runtime import execute as pending_execute
        return pending_execute(service,name,args,deadline,cancel_guard=cancel_guard)
    case=state['case']
    store.guard=lambda:service.guard(deadline)
    review=None
    stored=store.source_review_proof(case['id'])
    if stored is not None:
        from .draft_revision_review import witness_from_proof
        proof,proof_sha=stored
        review=witness_from_proof(service,store,case,state['registration'],
            proof,proof_sha,deadline,published=True)
    value=state['registration']['input'];original=state['registration']['original']
    adapter=restore_adapter(service,state['registration'],case,deadline,source_review=review)
    # Reconstruct the historical comparison plan from the verified original.
    # Current proof, artifacts and sources are inspected by the action's first
    # _current(), inside its sole Gate and before token, claim or HTTP. A second
    # preflight Gate would discard its full scan and immediately repeat it.
    from .own_workflow import projection
    from .draft_revision_preservation import PreservationPlan
    rendered=projection(original['manifest'],original['mappings'])
    rows=rendered['articles'] if 'articles' in rendered else [rendered]
    if len(rows)!=1:hold()
    urls=tuple(original['mappings'][a['slot']]['url'] for a in original['manifest']['assets'] if a['role']=='body')
    from .draft_revision_registration import DIRECT_PROFILE,BOUND_IMAGE_PROFILE
    if state['registration']['profile']==BOUND_IMAGE_PROFILE:
        from .draft_revision_preservation import ChangedImagePlan
        preservation=ChangedImagePlan(rows[0]['content'],urls,value['source_relation']['changed_index'],value['image_upload']['upload']['url'])
    else:preservation=PreservationPlan(rows[0]['content'],urls)
    if preservation.evidence()!=value['preservation']:hold()
    gate=RevisionExecutionGate(service,deadline,cancel_guard=cancel_guard)
    bridge=None
    if state['registration']['profile'] in (DIRECT_PROFILE,BOUND_IMAGE_PROFILE):
        from .current_publication_revision_bridge import DirectPublicationBridge
        bridge=DirectPublicationBridge(service,adapter,gate,case,deadline)
    context=RevisionContext(case,original['reference'],canonical(value),adapter.current,
        adapter.matches_snapshot,gate,preservation,bridge)
    store.review_observer=lambda ident:adapter.claim_source_review(ident)
    provider=OfficialRevisionProvider(service,store,context,deadline)
    revision=DraftRevisionService(store,context,provider)
    action=name.rsplit('.',1)[-1]
    if action=='prepare':return revision.prepare()
    if action=='execute':return revision.execute()
    if action=='readback':return revision.readback()
    hold()
