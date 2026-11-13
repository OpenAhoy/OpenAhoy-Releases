"""Read-only provenance bridge from pending GET budget into a final Case.

The pending journal is a distinct origin, never a CapturedRevisionResponse.
Do not call current Store.read here: revision replay may itself be reached from
current Store.read while holding the revision journal lock.
"""
from copy import deepcopy
from .contracts import WCEError
from .service import digest

PROFILE='CURRENT_PENDING_BASELINE_ADOPTED_V1'

def hold():raise WCEError('DRAFT_REVISION_PENDING_ADOPTION_HOLD')

def _hex(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def extract(events, handle, account_key, proposal, *, original_count=None):
    """Extract this target's exact prefix from already hash-verified events.

    No assertion about other targets is derived here.
    """
    from .current_publication_pending_image import validate as validate_pending
    from .draft_revision_pending_baseline import validate as validate_baseline
    if type(events) is not list or not events or type(handle) is not str:hold()
    previous=None;locked_pending=None;locked_row=None;claim=None;records=[];final=None
    for ordinal,event in enumerate(events):
        if (type(event) is not dict or set(event)!={'value','previous_sha256'}
                or type(event['value']) is not dict or event['value'].get('account_key')!=account_key):hold()
        value=event['value']; pending=value.get('revision_pending_images',{}).get(handle)
        baseline=value.get('revision_pending_baselines',{}).get(handle)
        row=value.get('targets',{}).get(handle)
        if locked_pending is None:
            if pending is None:
                if baseline is not None:hold()
                continue
            if type(row) is not dict:hold()
            validate_pending(row,pending)
            if pending.get('proposal')!=proposal or pending.get('proposal_sha256')!=digest(proposal):hold()
            locked_pending=deepcopy(pending);locked_row=deepcopy(row)
        elif pending!=locked_pending or row!=locked_row:
            hold()
        if baseline is None:
            if previous is not None:hold()
            continue
        validate_baseline(baseline,locked_pending)
        if baseline==previous:continue
        if previous is None:
            if baseline['state']!='CLAIMED' or baseline['ordinal']!=1:hold()
            claim=(event['previous_sha256'] if original_count is not None and ordinal>=original_count else digest(event))
        elif previous['state']=='CLAIMED':
            if (baseline['state'] not in {'UNKNOWN','OBSERVED'} or baseline['ordinal']!=previous['ordinal']
                    or any(baseline[k]!=previous[k] for k in ('proposal_sha256','request_sha256'))):hold()
            records.append({'ordinal':baseline['ordinal'],'state':baseline['state'],
                'claim_event_sha256':claim,'result_event_sha256':(event['previous_sha256'] if original_count is not None and ordinal>=original_count else digest(event))})
            if baseline['state']=='OBSERVED':final=deepcopy(baseline)
        elif previous['state']=='UNKNOWN':
            if (baseline['state']!='CLAIMED' or baseline['ordinal']!=previous['ordinal']+1
                    or any(baseline[k]!=previous[k] for k in ('proposal_sha256','request_sha256'))):hold()
            claim=(event['previous_sha256'] if original_count is not None and ordinal>=original_count else digest(event))
        else:hold()
        previous=deepcopy(baseline)
    if (locked_pending is None or final is None or previous!=final
            or len(records)!=final['ordinal'] or records[-1]['state']!='OBSERVED'
            or any(item['state']!='UNKNOWN' for item in records[:-1])):hold()
    if final['request_sha256']!=digest({'media_id':locked_row['reference']}):hold()
    return {'pending':locked_pending,'row':locked_row,'baseline':final,'reads':records}


def source(revision, case, registration, guard, *, anchor=None):
    """Authenticate the live anchored event chain without Store.read/revision SQL."""
    from pathlib import Path
    from .own_connection_policy import load_policy,registry_path
    from .draft_revision_guard import policy_binding
    from .publication_contract import exact
    from .publication_store import read_file
    from .current_publication_store import Store,MAX_LEDGER,_bounded_names
    from .draft_revision_pending_upload import validate as validate_upload,verify_archive
    from .draft_revision_registration import BOUND_IMAGE_PROFILE
    from .draft_revision_wire import RevisionSnapshot,baseline_projection as revision_projection,_article
    from .draft_group_wire import GroupSnapshot,baseline_projection as group_projection
    from . import current_draft_inventory as inventory
    if (type(registration) is not dict or registration.get('profile')!=BOUND_IMAGE_PROFILE
            or type(case) is not dict or not callable(guard)):hold()
    image=registration.get('input',{}).get('image_upload')
    if type(image) is not dict or set(image)!={'pending','upload'} or type(image['pending']) is not dict:hold()
    proposal=image['pending'];proposal_sha=digest(proposal)
    policy=load_policy(revision.account/'connection-policy.json',active=False)
    if policy.root!=revision.account or digest(policy_binding(policy,'OPERATOR_ATTESTED'))!=revision.binding:hold()
    registry=Path(policy.value.get('registry_path') or registry_path())
    current=Store(policy,registry,guard=guard);guard()
    enrollment=current._marker();head=read_file(current.path,16384)
    exact(head,'schema account_key sequence sha256')
    if (head['schema']!=1 or head['account_key']!=current.legacy.key
            or type(head['sequence']) is not int or not 1<=head['sequence']<=4096
            or head['sequence']!=enrollment['sequence'] or head['sha256']!=enrollment['head_sha256']):hold()
    expected=head['sha256'];events=[]
    for seq in range(head['sequence'],0,-1):
        guard();event=read_file(current.directory/('event-'+str(seq)+'.json'),MAX_LEDGER)
        exact(event,'value previous_sha256')
        if (digest(event)!=expected or event['value'].get('sequence')!=seq
                or event['value'].get('schema')!=1 or event['value'].get('account_key')!=current.legacy.key):hold()
        expected=event['previous_sha256'];events.append(event)
    if expected is not None:hold()
    if _bounded_names(current.directory)!={'event-'+str(i)+'.json' for i in range(1,head['sequence']+1)}:hold()
    events.reverse()
    if anchor is not None and (type(anchor) is not dict or set(anchor)!={'sequence','sha256'}
            or type(anchor['sequence']) is not int or anchor['sequence']<1 or not _hex(anchor['sha256'])):hold()
    old_anchor=(anchor is not None and anchor['sequence']<=head['sequence']
                and digest(events[anchor['sequence']-1])==anchor['sha256'])
    from .current_publication_continuation import ContinuationIndex
    import os
    index=ContinuationIndex(current)
    present=[os.path.lexists(p) for p in (index.enrollment_path,index.marker_path,index.db_path,index.head_path)]
    if any(present) and not all(present):hold()
    extension=False
    if all(present) and not old_anchor:
        with index._db(readonly=True) as (continuation,identity):
            continuation_head=index._head(continuation,identity,recover=False)
            selected=continuation.execute('SELECT 1 FROM legacy_revision_proposals WHERE proposal_sha=?',(proposal_sha,)).fetchone()
            extension=selected is not None and continuation_head['seq']>0
    if extension:
        from .current_publication_revision_history import extend
        original_count=len(events)
        events,cutoff,cutoff_sha,handle,last=extend(current,events,proposal_sha,anchor,guard)
        history=extract(events,handle,current.legacy.key,proposal,original_count=original_count)
    else:
        if anchor is None:cutoff=head['sequence'];cutoff_sha=head['sha256']
        else:
            if not old_anchor:hold()
            cutoff=anchor['sequence'];cutoff_sha=anchor['sha256']
        events=events[:cutoff];last=events[-1]['value'];pending_map=last.get('revision_pending_images',{})
        if type(pending_map) is not dict:hold()
        matches=[h for h,v in pending_map.items() if type(v) is dict and v.get('proposal_sha256')==proposal_sha]
        if len(matches)!=1:hold()
        handle=matches[0];history=extract(events,handle,current.legacy.key,proposal)
    pending=history['pending'];row=history['row'];baseline=history['baseline']
    upload=last.get('revision_pending_uploads',{}).get(handle)
    pending_review=pending.get('review');final_review=registration.get('review')
    pending_acquisition=pending.get('acquisition');final_acquisition=registration.get('acquisition')
    if (type(upload) is not dict or upload.get('state')!='SUCCEEDED'
            or image['upload']!=upload or case.get('target')!=proposal.get('reference_sha256')
            or case.get('binding')!=proposal.get('binding_sha256')
            or case.get('source_sha')!=proposal.get('human_source_sha256')
            or case.get('original_step')!=proposal.get('original_step_sha256')
            or registration['input'].get('source_relation',{}).get('pending_sha256')!=proposal_sha
            or type(pending_review) is not dict or type(final_review) is not dict
            or type(pending_acquisition) is not dict or type(final_acquisition) is not dict
            or any(pending_review.get(k)!=final_review.get(k) for k in ('helper_sha256','review_sha256','original_save_key'))
            or digest(pending_review.get('dependencies'))!=final_review.get('dependencies_sha256')
            or digest(pending_review.get('human_pins'))!=final_review.get('human_pins_sha256')
            or pending_acquisition.get('original_save_key')!=final_acquisition.get('original_save_key')):hold()
    validate_upload(upload,pending,baseline)
    verify_archive(current,handle,upload)
    snapshot=RevisionSnapshot(row['reference'],baseline['snapshot'],baseline['response_sha256'])
    for article in snapshot.rows():_article(article,synthetic=False)
    group=group_projection(GroupSnapshot(snapshot.reference,snapshot.canonical_json,snapshot.response_sha))
    _,targets=inventory._read_page(policy.root/'current-draft-publication',row['inventory_handle'],
        row['page'],row['page_sha256'],row['binding_sha256'],guard)
    if (type(row['page_index']) is not int or not 0<=row['page_index']<len(targets)
            or targets[row['page_index']]['reference']!=row['reference']
            or targets[row['page_index']]['projection_sha256']!=row['projection_sha256']
            or digest(targets[row['page_index']]['projection'])!=row['projection_sha256']
            or targets[row['page_index']]['projection']!=group):hold()
    if current._marker()!=enrollment or read_file(current.path,16384)!=head or _bounded_names(current.directory)!={'event-'+str(i)+'.json' for i in range(1,head['sequence']+1)}:hold()
    guard()
    return {'profile':PROFILE,'account_key':current.legacy.key,'binding_sha256':revision.binding,
        'case_id':case['id'],'handle':handle,'proposal_sha256':proposal_sha,
        'source_head_sequence':cutoff,'source_head_sha256':cutoff_sha,
        'baseline_sha256':digest(revision_projection(snapshot)),'snapshot_sha256':snapshot.evidence_sha(),
        'snapshot':{'reference':snapshot.reference,'canonical_json':snapshot.canonical_json,
            'response_sha':snapshot.response_sha,'profile':snapshot.profile},'reads':history['reads']}


def adopt(revision,publication,handle,case_id,gate,authority,guard):
    """Private same-gate transition; replay adopts the original event only."""
    from .draft_revision_store import RevisionStore
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    if (type(revision) is not RevisionStore or type(publication) is not Store
            or type(gate) is not RevisionExecutionGate or gate.service.policy is not publication.policy
            or gate.service.policy.root!=revision.account or not callable(guard) or gate.held() is not True):hold()
    guard();value,row=publication.target(handle)
    publication._authority(authority,guard,row['batch_source_sha'])
    pending=value.get('revision_pending_images',{}).get(handle)
    if type(pending) is not dict or value.get('revision_pending_baselines',{}).get(handle,{}).get('state')!='OBSERVED':hold()
    def check():
        guard()
        if gate.held() is not True:hold()
        publication._authority(authority,guard,row['batch_source_sha'])
    with revision.connection(write=True,guard=check) as db:
        state=revision._state(db,case_id);old=state.get('pending_adoption')
        if old is not None:
            anchor={'sequence':old['source_head_sequence'],'sha256':old['source_head_sha256']}
            witness=source(revision,state['case'],state['registration'],check,anchor=anchor)
            if witness!=old or witness['handle']!=handle:hold()
        else:
            witness=source(revision,state['case'],state['registration'],check)
            if witness['handle']!=handle:hold()
            revision._event(db,case_id,'ADOPT_PENDING_BASELINE',{'witness':witness},guard=check)
    check()
    # Reopen the already committed journal; never allocate another read here.
    return revision.state(case_id)
