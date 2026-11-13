"""Private immutable pre-baseline hold for an exact one-image revision.

This state blocks the old READY target. It is not a baseline, a publication
successor, an upload claim, or permission to call a platform API.
"""
from dataclasses import asdict
from .contracts import WCEError
from .publication_contract import binding,digest

PROFILE='CURRENT_REVISION_PENDING_IMAGE_V1'
def hold():raise WCEError('CURRENT_REVISION_PENDING_HOLD')
def _hex(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def _qualified_profile(profile,proposal):
    import time
    from .own_auth import OwnProfile,validate_profile
    if (type(profile) is not OwnProfile or profile.source_kind!='OPERATOR_ATTESTED'
            or digest(profile.binding())!=proposal['binding_sha256']):hold()
    validate_profile(profile,time.time());return True

def validate(row,record):
    from .draft_revision_registration import adapter_spec
    from .draft_revision_input import PendingImageSelection
    if (type(row) is not dict or row.get('state')!='READY' or row.get('submit_count')!=0
            or row.get('task') is not None or row.get('reply') is not None or row.get('queries')!=0
            or row.get('query_pending',False) is not False or type(record) is not dict
            or set(record)!={'profile','proposal','proposal_sha256','policy_binding_sha256','acquisition','review'}
            or record['profile']!=PROFILE or type(record['proposal']) is not dict
            or digest(record['proposal'])!=record['proposal_sha256']
            or record['policy_binding_sha256']!=row.get('binding_sha256')):hold()
    p=record['proposal'];fields={'profile','original_manifest_sha256','old_source_sha256','new_source_sha256',
        'metadata_sha256','skeleton_sha256','changed_index','slot','source_sha256','source_size','mime',
        'original_image_sha256','unchanged_source_sha256','human_source_sha256','binding_sha256',
        'reference_sha256','original_step_sha256','original_intent_sha256','original_result_sha256'}
    if (set(p)!=fields or p['profile']!='DIRECT_SAFE_HTML_ONE_IMAGE_PENDING_V1'
            or p['reference_sha256']!=digest(row.get('reference'))
            or any(not _hex(p[k]) for k in fields-{'profile','changed_index','slot','source_size','mime','unchanged_source_sha256'})
            or type(p['changed_index']) is not int or not 0<=p['changed_index']<=3
            or type(p['slot']) is not str or not p['slot'] or len(p['slot'])>128
            or type(p['source_size']) is not int or not 0<p['source_size']<1000000
            or p['mime'] not in ('image/png','image/jpeg') or type(p['unchanged_source_sha256']) is not list
            or any(not _hex(x) for x in p['unchanged_source_sha256'])):hold()
    windows,selection=adapter_spec(record['acquisition'],check_files=False)
    review=record['review']
    if (type(selection) is not PendingImageSelection or selection.changed_index!=p['changed_index']
            or selection.new_image_sha256!=p['source_sha256'] or selection.new_sha256!=p['new_source_sha256']
            or selection.old_sha256!=p['old_source_sha256'] or selection.metadata_sha256!=p['metadata_sha256']
            or selection.images[p['changed_index']].sha256!=p['original_image_sha256']
            or [x.sha256 for i,x in enumerate(selection.images) if i!=p['changed_index']]!=p['unchanged_source_sha256']
            or type(review) is not dict or set(review)!={'helper_path','helper_sha256','review_path','review_sha256',
                'dependencies','binding','original_save_key','new_source_sha256','human_pins'}
            or review['binding']!=p['binding_sha256'] or review['new_source_sha256']!=p['new_source_sha256']
            or review['original_save_key']!=record['acquisition']['original_save_key']
            or any(not _hex(review[k]) for k in ('helper_sha256','review_sha256','binding','new_source_sha256'))):hold()
    from pathlib import Path
    from .draft_revision_source_views import canonical_pins,source_binding,RELATION
    actual=canonical_pins(windows)
    stable_sha=source_binding(record['acquisition']['owner_thread'],windows)
    if (stable_sha!=p['human_source_sha256'] or type(review['human_pins']) is not list
            or any(type(item) is not list or len(item)!=5 or any(type(v) is not str for v in item) for item in review['human_pins'])
            or tuple(sorted(tuple(item) for item in review['human_pins']))!=actual
            or (record['acquisition'].get('view_relation')==RELATION
                and tuple(tuple(item) for item in review['human_pins'])!=actual)
            or any(type(review[k]) is not str or not Path(review[k]).is_absolute() for k in ('helper_path','review_path'))
            or type(review['dependencies']) is not list or len(review['dependencies'])>32
            or any(type(item) is not list or len(item)!=2 or type(item[0]) is not str
                or not Path(item[0]).is_absolute() or not _hex(item[1]) for item in review['dependencies'])):hold()
    return True

def start(store,handle,adapter,pins,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_input import RevisionInputAdapter,PendingImageSelection
    from .draft_revision_registration import TrustedRevisionPins,verify_pins,acquisition_spec
    from .current_publication_revision_reservation import _no_old_submit_receipt
    if (type(store) is not Store or type(adapter) is not RevisionInputAdapter
            or type(adapter.selection) is not PendingImageSelection or type(pins) is not TrustedRevisionPins
            or type(gate) is not RevisionExecutionGate or gate.service is not adapter.service
            or gate.service.policy is not store.policy or gate.deadline!=adapter.deadline
            or gate.held() is not True or not callable(guard)):hold()
    from .draft_revision_publication_window import require_authorization_window
    require_authorization_window(adapter,authority)
    guard();verify_pins(pins,adapter);observed=adapter.inspect_pending();proposal=observed.proposal
    _qualified_profile(adapter.service.profile(),proposal)
    value,row=store.target(handle);store._authority(authority,guard,row['batch_source_sha'])
    if (proposal['binding_sha256']!=digest(adapter.service.profile().binding())
            or row['binding_sha256']!=binding(store.policy.data)
            or proposal['reference_sha256']!=digest(row['reference'])
            or row['batch_source_sha']!=authority.source_sha
            or handle in value.get('revision_reservations',{})):hold()
    _no_old_submit_receipt(store,handle,guard)
    review=asdict(pins);review['helper_path']=str(pins.helper_path);review['review_path']=str(pins.review_path)
    review['dependencies']=[[str(path),sha] for path,sha in pins.dependencies]
    review['human_pins']=[list(item) for item in pins.human_pins]
    record={'profile':PROFILE,'proposal':proposal,'proposal_sha256':digest(proposal),
        'policy_binding_sha256':binding(store.policy.data),
        'acquisition':acquisition_spec(adapter),'review':review}
    validate(row,record)
    old=value.get('revision_pending_images',{}).get(handle)
    if old is not None:
        if old!=record:hold()
        guard();return old
    if adapter.inspect_pending().proposal!=proposal or gate.held() is not True:hold()
    verify_pins(pins,adapter);store._authority(authority,guard,row['batch_source_sha'])
    value.setdefault('revision_pending_images',{})[handle]=record;value['sequence']+=1
    store.save(value)
    guard()
    if gate.held() is not True:hold()
    return record

def verify_case_link(store,value,handle,case_id,guard):
    """Bind a completed one-image upload to the exact final revision Case."""
    from .draft_revision_guard import policy_binding
    from .draft_revision_store import RevisionStore
    from .draft_revision_registration import BOUND_IMAGE_PROFILE
    pending=value.get('revision_pending_images',{}).get(handle)
    baseline=value.get('revision_pending_baselines',{}).get(handle)
    upload=value.get('revision_pending_uploads',{}).get(handle)
    if (type(pending) is not dict or type(baseline) is not dict or baseline.get('state')!='OBSERVED'
            or type(upload) is not dict or upload.get('state')!='SUCCEEDED'):hold()
    from .draft_revision_pending_upload import validate as validate_upload
    validate_upload(upload,pending,baseline)
    revision=RevisionStore(store.policy.root,digest(policy_binding(store.policy,'OPERATOR_ATTESTED')),guard)
    with revision.connection() as db:
        state=revision._state(db,case_id);record=state['registration'];case=state['case']
        if (record.get('profile')!=BOUND_IMAGE_PROFILE or case['target']!=pending['proposal']['reference_sha256']
                or record['input'].get('image_upload')!={'pending':pending['proposal'],'upload':upload}
                or record['input'].get('source_relation',{}).get('pending_sha256')!=pending['proposal_sha256']):hold()
    guard();return True
