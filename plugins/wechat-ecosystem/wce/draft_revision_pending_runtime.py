"""Host-owned continuation of an already-persisted pending-image proposal.

The model supplies only the existing closed prepare selectors. Paths, human
pins, original target and image bytes come from the immutable private ledger.
"""
from pathlib import Path
from .contracts import WCEError
from .draft_revision_service import bounded_failure
from .service import digest

def hold():raise WCEError('DRAFT_REVISION_PENDING_NOT_REGISTERED')

@bounded_failure
def selected(policy,args,registry=None):
    from .own_connection_policy import registry_path
    from .draft_revision_guard import historical_identity_guard
    from .current_publication_store import Store
    guard=historical_identity_guard(policy)
    target=registry or policy.value.get('registry_path') or registry_path()
    store=Store(policy,Path(target),guard=guard);value=store.read();matches=[]
    for handle,record in value.get('revision_pending_images',{}).items():
        pending_id=digest({'profile':'CURRENT_PENDING_REVISION_ID_V1','proposal_sha256':record['proposal_sha256']})
        if (args.get('revision_id')==pending_id if 'revision_id' in args else
                record['acquisition']['original_save_key']==args.get('original_save_key')
                and args.get('revision_artifact_handle')=='revision-artifact-'+record['proposal_sha256']):
            matches.append((handle,record))
    if len(matches)!=1:hold()
    return store,matches[0][0],matches[0][1]

def _adapter_and_pins(service,record,deadline):
    from .draft_revision_registration import adapter_spec,TrustedRevisionPins
    from .draft_revision_native_lookup import NativeThreadLookup
    from .draft_revision_input import RevisionInputAdapter,PendingImageSelection
    spec=record['acquisition'];windows,selection=adapter_spec(spec)
    if type(selection) is not PendingImageSelection:hold()
    lookup=NativeThreadLookup(Path(spec['state_path']),Path(spec['session_root']),spec['owner_thread'],
        lambda:(service.guard(deadline) or True),allowed_threads=tuple(dict.fromkeys(w.source.thread_id for w in windows)),deadline=deadline)
    adapter=RevisionInputAdapter(service,lookup,windows,selection,spec['original_save_key'],deadline,
        expected_source_sha=record['proposal']['human_source_sha256'])
    r=record['review']
    pins=TrustedRevisionPins(Path(r['helper_path']),r['helper_sha256'],
        tuple((Path(path),sha) for path,sha in r['dependencies']),Path(r['review_path']),r['review_sha256'],
        r['binding'],r['original_save_key'],r['new_source_sha256'],tuple(tuple(p) for p in r['human_pins']))
    return adapter,pins

@bounded_failure
def register_from_reviewed_host(service,adapter,pins,handle,deadline,*,cancel_guard=None):
    """Private fixed-input host entry; returns only the opaque proposal handle."""
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_scan import for_adapter
    from .current_publication_source import Authorization
    from .current_publication_store import Store
    from .current_publication_pending_image import start
    from .own_connection_policy import registry_path
    gate=RevisionExecutionGate(service,deadline,cancel_guard=cancel_guard)
    with gate():
        guard=lambda:(service.guard(deadline) or True)
        registry=Path(service.policy.value.get('registry_path') or registry_path())
        store=Store(service.policy,registry,guard=guard)
        authority=Authorization(service.policy,registry,guard,deadline,native_guard=for_adapter(adapter))
        # Existing accounts must retain their original revision journal: a
        # missing anchor is not proof that no previous claim ever existed.
        from .draft_revision_store import RevisionStore
        revision=RevisionStore(service.policy.root,digest(service.profile().binding()),guard)
        with revision.connection():pass
        record=start(store,handle,adapter,pins,gate,authority,guard)
        return {'original_save_key':record['acquisition']['original_save_key'],
            'revision_artifact_handle':'revision-artifact-'+record['proposal_sha256'],
            'state':'PENDING_IMAGE_PROPOSAL_HELD'}

def _pending_id(record):
    return digest({'profile':'CURRENT_PENDING_REVISION_ID_V1','proposal_sha256':record['proposal_sha256']})


def _linked_case(policy,record):
    from .draft_revision_guard import policy_binding,historical_identity_guard
    from .draft_revision_store import RevisionStore
    history=historical_identity_guard(policy)
    store=RevisionStore(policy.root,digest(policy_binding(policy,'OPERATOR_ATTESTED')),history,history_guard=history)
    matches=[]
    with store.connection() as db:
        for row in db.execute('SELECT id FROM cases'):
            state=store._state(db,row['id'])
            registration=state.get('registration')
            data=registration.get('input') if type(registration) is dict else None
            image=data.get('image_upload') if type(data) is dict else None
            if type(image) is dict and image.get('pending')==record['proposal']:
                matches.append(state)
    if len(matches)>1:hold()
    return (store,matches[0]) if matches else None


@bounded_failure
def local_status(policy,args,registry=None):
    store,handle,record=selected(policy,args,registry)
    linked=_linked_case(policy,record)
    if linked is not None:
        from .draft_revision_service import status_value
        revision,state=linked
        if state.get('pending_adoption') is not None:
            result=status_value(revision.state(state['case']['id']),
                comparison_profile=state['registration']['input']['preservation']['profile'])
            result['pending_revision_id']=_pending_id(record)
            return result
    value=store.read();baseline=value.get('revision_pending_baselines',{}).get(handle)
    image=value.get('revision_pending_uploads',{}).get(handle)
    state='PENDING_IMAGE_PROPOSAL_HELD'
    if type(baseline) is dict:
        state={'OBSERVED':'PENDING_IMAGE_READY','UNKNOWN':'READ_INDETERMINATE',
               'CLAIMED':'READ_INDETERMINATE','MISMATCH':'BASELINE_MISMATCH'}[baseline['state']]
    if type(image) is dict:
        state={'CLAIMED':'IMAGE_UPLOAD_UNKNOWN','UNKNOWN':'IMAGE_UPLOAD_UNKNOWN',
               'SUCCEEDED':'IMAGE_UPLOADED','REJECTED':'IMAGE_UPLOAD_REJECTED'}[image['state']]
    if linked is not None:state='CASE_PENDING_ADOPTION'
    return {'revision_id':_pending_id(record),'state':state,
        'read_attempts':baseline['ordinal'] if type(baseline) is dict else 0,
        'write_attempts':0,'platform_effect_verified':False}


@bounded_failure
def execute(service,name,args,deadline,*,cancel_guard=None):
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_scan import for_adapter
    from .current_publication_source import Authorization
    from .own_connection_policy import registry_path
    from .draft_revision_pending_baseline import observe
    from .draft_revision_pending_upload import execute as upload
    from .draft_revision_pending_asset import receive
    from .draft_revision_registration import qualify
    from .draft_revision_input import RevisionInputAdapter,MaterializedImageSelection
    from .draft_revision_store import RevisionStore
    if name not in {'own.drafts.revisions.prepare','own.drafts.revisions.execute','own.drafts.revisions.readback'} or args.get('connection_id')!=service.policy.data['connection_id']:hold()
    store,handle,record=selected(service.policy,args)
    if name=='own.drafts.revisions.readback':
        linked=_linked_case(service.policy,record)
        if linked is None or linked[1].get('pending_adoption') is None:
            return local_status(service.policy,args)
        from .draft_revision_runtime import _execute
        final_id=digest({'case':linked[1]['case']['id'],'profile':linked[1]['case']['profile']})
        return _execute(service,name,{'connection_id':args['connection_id'],'revision_id':final_id},deadline,cancel_guard=cancel_guard)
    if name=='own.drafts.revisions.execute':
        linked=_linked_case(service.policy,record)
        if linked is not None and linked[1].get('pending_adoption') is not None:
            from .draft_revision_runtime import _execute
            case=linked[1]['case'];final_id=digest({'case':case['id'],'profile':case['profile']})
            final={'connection_id':args['connection_id'],'original_save_key':record['acquisition']['original_save_key'],
                'revision_artifact_handle':'revision-artifact-'+case['input_sha']}
            prepared=_execute(service,'own.drafts.revisions.prepare',final,deadline,cancel_guard=cancel_guard)
            if prepared.get('state')!='PREPARED':return prepared
            return _execute(service,name,{'connection_id':args['connection_id'],'revision_id':final_id},deadline,cancel_guard=cancel_guard)
    adapter,pins=_adapter_and_pins(service,record,deadline)
    gate=RevisionExecutionGate(service,deadline,cancel_guard=cancel_guard)
    with gate():
        guard=lambda:(service.guard(deadline) or True)
        registry=Path(service.policy.value.get('registry_path') or registry_path())
        authority=Authorization(service.policy,registry,guard,deadline,native_guard=for_adapter(adapter))
        # A persisted pending hold presupposes this exact pre-existing
        # journal; absence is not evidence that no earlier history existed.
        revision=RevisionStore(service.policy.root,record['proposal']['binding_sha256'],guard)
        with revision.connection():pass
        if name=='own.drafts.revisions.prepare':
            read=observe(store,handle,adapter,pins,gate,authority,guard)
            state=read['state']
            if state=='OBSERVED':state=('PENDING_IMAGE_READY' if read.get('read_attempts',0)<=3 else 'READ_BUDGET_INSUFFICIENT_FOR_UPDATE')
            return {'revision_id':_pending_id(record),'state':state,'read_attempts':read.get('read_attempts',0)}
        value,_=store.target(handle)
        baseline=value.get('revision_pending_baselines',{}).get(handle)
        if type(baseline) is not dict or baseline.get('state')!='OBSERVED':
            return {'revision_id':_pending_id(record),'state':'PENDING_BASELINE_REQUIRED'}
        if baseline['ordinal']>3:
            return {'revision_id':_pending_id(record),'state':'READ_BUDGET_INSUFFICIENT_FOR_UPDATE','read_attempts':baseline['ordinal']}
        # Recheck immediately before the sole upload claim as well.
        with revision.connection():pass
        image=upload(store,handle,adapter,pins,gate,authority,guard)
        if image['state']!='SUCCEEDED':return {'revision_id':_pending_id(record),'state':image['state'],'read_attempts':baseline['ordinal']}
        asset=receive(store,handle,adapter,pins,gate,authority,guard);s=adapter.selection
        material=MaterializedImageSelection(s.root,s.old_relative_path,s.old_sha256,s.new_relative_path,s.new_sha256,
            s.images,s.metadata_relative_path,s.metadata_sha256,s.image_names,s.new_image_relative_path,
            s.new_image_sha256,s.changed_index,handle,asset['asset_ref'])
        complete=RevisionInputAdapter(service,adapter.lookup,adapter.windows,material,adapter.original_save_key,deadline,
            expected_source_sha=record['proposal']['human_source_sha256'])
        qualified=qualify(complete,pins,gate)
        revision=RevisionStore(service.policy.root,qualified.case['binding'],lambda:(service.guard(deadline) or True))
        revision.register(qualified.case,registration=qualified)
        revision.adopt_pending_baseline(store,handle,qualified.case['id'],gate,authority,guard)
        case=qualified.case
    from .draft_revision_runtime import _execute
    final={'connection_id':args['connection_id'],'original_save_key':record['acquisition']['original_save_key'],
        'revision_artifact_handle':'revision-artifact-'+case['input_sha']}
    prepared=_execute(service,'own.drafts.revisions.prepare',final,deadline,cancel_guard=cancel_guard)
    if prepared.get('state')!='PREPARED':return prepared
    return _execute(service,'own.drafts.revisions.execute',{'connection_id':args['connection_id'],
        'revision_id':digest({'case':case['id'],'profile':case['profile']})},deadline,cancel_guard=cancel_guard)
