"""Hold a frozen current-publication intent before its original draft changes.

A reservation is persisted by CurrentPublicationStore's existing append-only
head, not an erasable sidecar. This module grants neither UPDATE nor publish.
"""
import os
import re
from .contracts import WCEError
from .publication_contract import binding, digest

PROFILE = 'CURRENT_REVISION_RESERVATION_V1'
FIELDS = frozenset({'profile','case_id','revision_id','binding_sha256','source_sha256',
    'reference_sha256','old_projection_sha256','baseline_sha256','baseline_ordinal','baseline_result_sha256'})


def hold():raise WCEError('CURRENT_REVISION_RESERVATION_HOLD')


def _hex(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _no_old_submit_receipt(publication,handle,guard):
    from .current_publication_store import _bounded_names
    from .own_bootstrap_security import path_check
    from .publication_store import read_file
    directory=publication.legacy.anchor/'current-publication-receipts'
    present=os.path.lexists(directory)
    if not present:
        guard()
        if os.path.lexists(directory):hold()
        return
    path_check(directory,True)
    names=_bounded_names(directory)
    for name in names:
        guard()
        if re.fullmatch(r'[0-9a-f]{64}\.json',name) is None:hold()
        receipt=read_file(directory/name,128*1024)
        fields={'schema','account_key','binding_sha256','intent_handle','method','head_sequence',
            'head_sha256','request_sha256','reason','error_code','http_status','response_sha256','result'}
        if type(receipt) is not dict or set(receipt)!=fields:hold()
        if receipt['intent_handle']==handle and receipt['method']=='freepublish.submit':hold()
    if _bounded_names(directory)!=names:hold()
    guard()


def _from_history(publication, handle, row, case_id, guard, *, baseline_ordinal=None):
    from .draft_revision_guard import policy_binding
    from .draft_revision_store import RevisionStore, OFFICIAL_PROVIDER
    from .draft_revision_wire import baseline_projection as revision_projection
    from .draft_group_wire import GroupSnapshot, baseline_projection as group_projection
    from . import current_draft_inventory as observed
    if (type(case_id) is not str or not _hex(case_id) or type(row) is not dict
            or row.get('intent_handle')!=handle or row.get('state')!='READY'
            or row.get('submit_count')!=0 or row.get('task') is not None
            or row.get('reply') is not None or row.get('queries')!=0
            or row.get('query_pending',False) is not False):hold()
    guard()
    _no_old_submit_receipt(publication,handle,guard)
    revision=RevisionStore(publication.policy.root,
        digest(policy_binding(publication.policy,'OPERATOR_ATTESTED')),guard)
    with revision.connection() as db:
        state=revision._state(db,case_id);case=state['case'];r=state['revision']
        if (case['id']!=case_id or case['provider_profile']!=OFFICIAL_PROVIDER
                or case['binding']!=revision.binding or case['target']!=digest(row['reference'])
                or r['case_id']!=case_id):hold()
        if baseline_ordinal is None:
            if r['state'] not in {'PREPARING','PREPARED'} or r['writes']!=0:hold()
            candidates=[item['ordinal'] for item in state['read_claims']
                if item['phase'] in {'BASELINE','RECOVERY_BASELINE'} and item['state']=='OBSERVED']
            if not candidates:hold()
            ordinal=candidates[-1]
        else:
            ordinal=baseline_ordinal
        if (type(ordinal) is not int or not 1<=ordinal<=len(state['read_claims'])
                or state['read_claims'][ordinal-1]['phase'] not in {'BASELINE','RECOVERY_BASELINE'}
                or state['read_claims'][ordinal-1]['state']!='OBSERVED'):hold()
        snapshot=revision._read_snapshot(state,ordinal)
        if snapshot is None or snapshot.reference!=row['reference']:hold()
        baseline_sha=digest(revision_projection(snapshot))
        result_sha=state['read_claims'][ordinal-1]['result_sha']
        if not _hex(result_sha):hold()
        base=group_projection(GroupSnapshot(snapshot.reference,snapshot.canonical_json,snapshot.response_sha))
    page, targets=observed._read_page(publication.policy.root/'current-draft-publication',
        row['inventory_handle'],row['page'],row['page_sha256'],binding(publication.policy.data),guard)
    if (type(row.get('page_index')) is not int or not 0<=row['page_index']<len(targets)):hold()
    target=targets[row['page_index']]
    if (target['reference']!=row['reference'] or target['projection_sha256']!=row['projection_sha256']
            or digest(target['projection'])!=row['projection_sha256'] or target['projection']!=base):hold()
    guard()
    return {'profile':PROFILE,'case_id':case_id,'revision_id':r['id'],
        'binding_sha256':binding(publication.policy.data),'source_sha256':row['batch_source_sha'],
        'reference_sha256':digest(row['reference']),'old_projection_sha256':row['projection_sha256'],
        'baseline_sha256':baseline_sha,'baseline_ordinal':ordinal,'baseline_result_sha256':result_sha}


def verify_reservation(publication,handle,row,reservation,guard):
    if (type(reservation) is not dict or set(reservation)!=FIELDS or reservation.get('profile')!=PROFILE
            or type(reservation.get('baseline_ordinal')) is not int or not 1<=reservation['baseline_ordinal']<=5
            or any(not _hex(reservation[k]) for k in FIELDS-{'profile','baseline_ordinal'})):hold()
    if _from_history(publication,handle,row,reservation['case_id'],guard,baseline_ordinal=reservation['baseline_ordinal'])!=reservation:hold()


def reserve(publication,handle,case_id,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    if (type(publication) is not Store or type(gate) is not RevisionExecutionGate
            or gate.service.policy is not publication.policy or not callable(guard)
            or gate.held() is not True):hold()
    guard();value,row=publication.target(handle)
    publication._authority(authority,guard,row['batch_source_sha'])
    if handle in value.get('revision_pending_images',{}):
        from .current_publication_pending_image import verify_case_link
        verify_case_link(publication,value,handle,case_id,guard)
    existing=value.get('revision_reservations',{}).get(handle)
    if existing is not None:
        if existing['case_id']!=case_id:hold()
        verify_reservation(publication,handle,row,existing,guard)
        publication._authority(authority,guard,row['batch_source_sha'])
        if gate.held() is not True:hold()
        return existing
    reservation=_from_history(publication,handle,row,case_id,guard)
    value.setdefault('revision_reservations',{})[handle]=reservation
    value['sequence']+=1
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    publication.save(value)
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    return reservation
