"""One claimed official body-image upload for a held pending revision.

Private host entry only. Existing draft uploads and their ordering are not
altered. The append-only current ledger makes a lost reply non-replayable.
"""
from hashlib import sha256
import os
import time
from .contracts import WCEError
from .service import digest

def hold():raise WCEError('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
def _hex(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def _qualified_profile(profile,proposal):
    from .own_auth import APIS,OwnProfile,validate_profile
    if (type(profile) is not OwnProfile or profile.source_kind!='OPERATOR_ATTESTED'
            or digest(profile.binding())!=proposal['binding_sha256'] or APIS[1] not in profile.granted_actions):hold()
    validate_profile(profile,time.time())
    return True

def validate(record,pending,baseline):
    keys={'state','proposal_sha256','request_sha256','image_sha256','url','response_sha256','error_code','receipt_sha256'}
    if (type(record) is not dict or set(record)!=keys or type(pending) is not dict
            or type(baseline) is not dict or baseline.get('state')!='OBSERVED'
            or type(baseline.get('ordinal')) is not int or baseline['ordinal']>3
            or record['state'] not in {'CLAIMED','SUCCEEDED','UNKNOWN','REJECTED'}
            or record['proposal_sha256']!=pending.get('proposal_sha256')
            or record['image_sha256']!=pending.get('proposal',{}).get('source_sha256')
            or not _hex(record['request_sha256'])):hold()
    if record['state']=='SUCCEEDED':
        from .upload_wire import api_reference_reason
        if (type(record['url']) is not str or api_reference_reason(record['url']) is not None
                or not _hex(record['response_sha256']) or not _hex(record['receipt_sha256']) or record['error_code'] is not None):hold()
    elif record['state']=='REJECTED':
        if (record['url'] is not None or not _hex(record['response_sha256']) or not _hex(record['receipt_sha256'])
                or type(record['error_code']) is not int or not -(2**31)<=record['error_code']<2**31
                or record['error_code']==0):hold()
    elif any(record[k] is not None for k in ('url','response_sha256','error_code','receipt_sha256')):hold()
    return True

def _receipt_path(store,proposal_sha):
    if not _hex(proposal_sha):hold()
    return store.legacy.anchor/'pending-image-receipts'/('receipt-'+proposal_sha+'.json')

def _receipt_value(store,handle,claim,result):
    return {'schema':1,'profile':'CURRENT_REVISION_IMAGE_RESPONSE_V1','account_key':store.legacy.key,
        'handle_sha256':digest(handle),'proposal_sha256':claim['proposal_sha256'],
        'request_sha256':claim['request_sha256'],'image_sha256':claim['image_sha256'],
        'state':result['state'],'url':result['url'],'response_sha256':result['response_sha256'],'error_code':result['error_code']}

def _read_receipt(store,handle,claim):
    from .draft_revision_files import read
    path=_receipt_path(store,claim['proposal_sha256'])
    if not os.path.lexists(path):return None
    value,sha=read(path,16384)
    if (type(value) is not dict or value.get('state') not in {'SUCCEEDED','REJECTED'}
            or set(value)!={'schema','profile','account_key','handle_sha256','proposal_sha256','request_sha256',
                'image_sha256','state','url','response_sha256','error_code'}
            or value!=_receipt_value(store,handle,claim,value)):hold()
    result=dict(claim,state=value['state'],url=value['url'],response_sha256=value['response_sha256'],
        error_code=value['error_code'],receipt_sha256=sha)
    return result

def verify_archive(store,handle,record):
    if record['state'] not in {'SUCCEEDED','REJECTED'}:return True
    claim=dict(record,state='CLAIMED',url=None,response_sha256=None,error_code=None,receipt_sha256=None)
    if _read_receipt(store,handle,claim)!=record:hold()
    return True

def _archive(store,handle,claim,result):
    from .own_bootstrap_security import path_check
    from .draft_revision_files import exclusive,read
    from .publication_store import sync_directory
    path=_receipt_path(store,claim['proposal_sha256'])
    try:path.parent.mkdir(mode=0o700)
    except FileExistsError:pass
    path_check(path.parent,True);sync_directory(path.parent.parent)
    value=_receipt_value(store,handle,claim,result)
    try:sha=exclusive(path,value)
    except FileExistsError:
        old,sha=read(path,16384)
        if old!=value:hold()
    return sha

def _check_account_writer(policy):
    """Fail before consuming the unique claim when the writer is already held."""
    import sqlite3
    from .own_history_source import owned_connection
    from .draft_group_store import check_account_writer
    from .draft_group_history_context import locator_scope
    with owned_connection(policy.root/'state.sqlite3',readonly=True,timeout=5) as db, locator_scope(policy,db) as locators:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        try:check_account_writer(db,history_locators=locators)
        finally:db.rollback()

def execute(store,handle,adapter,pins,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_input import RevisionInputAdapter,PendingImageSelection
    from .draft_revision_registration import TrustedRevisionPins,verify_pins
    from .http_transport import HTTPSender
    from .own_connection_token import TokenCache
    from .own_connection_workflow import PersistentWorkflow
    from .own_wire import encode_upload
    from .upload_wire import inspect_response,BODY_API_REFERENCE_POLICY
    from .draft_revision_wire import RevisionSnapshot
    from .draft_group_wire import GroupSnapshot,baseline_projection
    from .publication_contract import binding
    from . import current_draft_inventory as inventory
    if (type(store) is not Store or type(adapter) is not RevisionInputAdapter
            or type(adapter.selection) is not PendingImageSelection or type(pins) is not TrustedRevisionPins
            or type(gate) is not RevisionExecutionGate or gate.service is not adapter.service
            or gate.service.policy is not store.policy or gate.deadline!=adapter.deadline
            or gate.held() is not True or not callable(guard)):hold()
    from .draft_revision_publication_window import require_authorization_window
    require_authorization_window(adapter,authority)
    service=adapter.service;guard();verify_pins(pins,adapter);observed=adapter.inspect_pending()
    value,row=store.target(handle);pending=value.get('revision_pending_images',{}).get(handle)
    baseline=value.get('revision_pending_baselines',{}).get(handle)
    if (type(pending) is not dict or pending['proposal']!=observed.proposal
            or type(baseline) is not dict or baseline.get('state')!='OBSERVED'
            or row['batch_source_sha']!=authority.source_sha):hold()
    store._authority(authority,guard,row['batch_source_sha'])
    existing=value.get('revision_pending_uploads',{}).get(handle)
    if existing is not None:
        validate(existing,pending,baseline);guard()
        if existing['state'] in {'CLAIMED','UNKNOWN'}:
            recovered=_read_receipt(store,handle,existing)
            if recovered is not None:
                validate(recovered,pending,baseline);verify_pins(pins,adapter)
                if gate.held() is not True or adapter.inspect_pending().proposal!=pending['proposal']:hold()
                store._authority(authority,guard,row['batch_source_sha'])
                value['revision_pending_uploads'][handle]=recovered;value['sequence']+=1
                store.save(value);guard();return {'state':recovered['state']}
        else:verify_archive(store,handle,existing)
        return {'state':'UNKNOWN' if existing['state']=='CLAIMED' else existing['state']}
    snapshot=RevisionSnapshot(observed.original.reference,baseline['snapshot'],baseline['response_sha256'])
    _,targets=inventory._read_page(store.policy.root/'current-draft-publication',row['inventory_handle'],
        row['page'],row['page_sha256'],binding(store.policy.data),guard)
    target=targets[row['page_index']]
    actual=baseline_projection(GroupSnapshot(snapshot.reference,snapshot.canonical_json,snapshot.response_sha))
    if (target['reference']!=row['reference'] or target['projection_sha256']!=row['projection_sha256']
            or digest(target['projection'])!=row['projection_sha256'] or target['projection']!=actual
            or not adapter.matches_pending_snapshot(snapshot)):hold()
    profile=service.profile();sender=service.workflow.sender;tokens=service.tokens
    _qualified_profile(profile,pending['proposal'])
    if (type(sender) is not HTTPSender or sender.enabled is not True
            or type(tokens) is not TokenCache or tokens.policy is not store.policy
            or type(service.workflow) is not PersistentWorkflow or service.workflow.policy is not store.policy
            or service.workflow.token_cache is not tokens):hold()
    claimed=[None]
    def current():
        guard();verify_pins(pins,adapter)
        if gate.held() is not True or adapter.inspect_pending().proposal!=pending['proposal']:hold()
        _qualified_profile(service.profile(),pending['proposal'])
        state,latest=store.target(handle)
        if (latest!=row or state.get('revision_pending_images',{}).get(handle)!=pending
                or state.get('revision_pending_baselines',{}).get(handle)!=baseline
                or (claimed[0] is not None and state.get('revision_pending_uploads',{}).get(handle)!=claimed[0])):hold()
        store._authority(authority,guard,row['batch_source_sha']);return True
    current();_check_account_writer(store.policy);current()
    token=tokens.get(guard=current);current()
    if not tokens.valid(token):hold()
    image=adapter._read(adapter.selection.new_image_relative_path,adapter.selection.new_image_sha256)
    if sha256(image).hexdigest()!=pending['proposal']['source_sha256']:hold()
    request=encode_upload('article_body',pending['proposal']['mime'],image,token.token)
    claim={'state':'CLAIMED','proposal_sha256':pending['proposal_sha256'],
        'request_sha256':sha256(request.body).hexdigest(),'image_sha256':sha256(image).hexdigest(),
        'url':None,'response_sha256':None,'error_code':None,'receipt_sha256':None}
    value,_=store.target(handle)
    if (value.get('revision_pending_images',{}).get(handle)!=pending
            or value.get('revision_pending_baselines',{}).get(handle)!=baseline
            or handle in value.get('revision_pending_uploads',{})):hold()
    value.setdefault('revision_pending_uploads',{})[handle]=claim;value['sequence']+=1
    current();store.save(value);claimed[0]=claim
    result=dict(claim,state='UNKNOWN')
    try:
        current()
        _check_account_writer(store.policy)
        current();timeout=min(30.0,gate.deadline-time.monotonic(),token.wall_deadline-time.time())
        if timeout<=0 or not tokens.valid(token):hold()
        response=sender.send(request,timeout)
        parsed=inspect_response('article_body',response,token.token,policy=BODY_API_REFERENCE_POLICY,production=True)
        if parsed.reply.classification=='PARSED_SUCCESS':
            result.update(state='SUCCEEDED',url=parsed.reply.url,response_sha256=sha256(response.body).hexdigest())
        elif parsed.reply.classification=='PLATFORM_ERROR':
            result.update(state='REJECTED',error_code=parsed.reply.error_code,response_sha256=sha256(response.body).hexdigest())
        if result['state'] in {'SUCCEEDED','REJECTED'}:
            result['receipt_sha256']=_archive(store,handle,claim,result)
    except Exception:
        result=dict(claim,state='UNKNOWN')
    current();value,_=store.target(handle)
    if value.get('revision_pending_uploads',{}).get(handle)!=claim:hold()
    value['revision_pending_uploads'][handle]=result;value['sequence']+=1
    store.save(value);claimed[0]=result;current();return {'state':result['state']}
