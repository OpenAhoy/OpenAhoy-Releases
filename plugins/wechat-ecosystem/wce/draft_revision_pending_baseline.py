"""Accounted fresh GETs after an immutable pending-image pre-hold.

This private host operation never sends an upload, update or publication.
Each read is counted; an interrupted read can be recovered within its budget.
"""
from hashlib import sha256
import time
from .contracts import WCEError
from .service import digest

def hold():raise WCEError('DRAFT_REVISION_PENDING_BASELINE_HOLD')
def _hex(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def _qualified_profile(profile,proposal):
    from .own_auth import APIS,OwnProfile,validate_profile
    if (type(profile) is not OwnProfile or profile.source_kind!='OPERATOR_ATTESTED'
            or digest(profile.binding())!=proposal['binding_sha256'] or APIS[3] not in profile.granted_actions):hold()
    validate_profile(profile,time.time());return True

def validate(record,pending):
    if (type(record) is not dict or set(record)!={'state','proposal_sha256','request_sha256','snapshot','response_sha256','ordinal'}
            or record['state'] not in {'CLAIMED','OBSERVED','UNKNOWN','MISMATCH'}
            or type(pending) is not dict or record['proposal_sha256']!=pending.get('proposal_sha256')
            or type(record['ordinal']) is not int or not 1<=record['ordinal']<=5
            or not _hex(record['request_sha256'])):hold()
    if record['state']=='OBSERVED':
        if (type(record['snapshot']) is not str or not 0<len(record['snapshot'])<=300000
                or not _hex(record['response_sha256'])):hold()
        from .publication_contract import strict_json
        from .service import canonical
        value=strict_json(record['snapshot'].encode(),maximum=2*1024*1024)
        if canonical(value)!=record['snapshot']:hold()
    elif record['snapshot'] is not None or record['response_sha256'] is not None:hold()
    return True

def observe(store,handle,adapter,pins,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_input import RevisionInputAdapter,PendingImageSelection
    from .draft_revision_registration import TrustedRevisionPins,verify_pins
    from .http_transport import HTTPSender
    from .own_connection_token import TokenCache
    from .own_connection_workflow import PersistentWorkflow
    from .own_wire import encode_draft
    from .draft_revision_wire import parse_get
    from .draft_group_wire import GroupSnapshot,baseline_projection
    from . import current_draft_inventory as inventory
    from .publication_contract import binding
    if (type(store) is not Store or type(adapter) is not RevisionInputAdapter
            or type(adapter.selection) is not PendingImageSelection or type(pins) is not TrustedRevisionPins
            or type(gate) is not RevisionExecutionGate or gate.service is not adapter.service
            or gate.service.policy is not store.policy or gate.deadline!=adapter.deadline
            or gate.held() is not True or not callable(guard)):hold()
    from .draft_revision_publication_window import require_authorization_window
    require_authorization_window(adapter,authority)
    service=adapter.service;guard();verify_pins(pins,adapter);observed=adapter.inspect_pending()
    value,row=store.target(handle);pending=value.get('revision_pending_images',{}).get(handle)
    if (type(pending) is not dict or pending['proposal']!=observed.proposal
            or row['batch_source_sha']!=authority.source_sha):hold()
    _qualified_profile(service.profile(),pending['proposal'])
    store._authority(authority,guard,row['batch_source_sha'])
    existing=value.get('revision_pending_baselines',{}).get(handle)
    if existing is not None:
        validate(existing,pending);guard()
        if existing['state']=='CLAIMED':
            # A previous process may have sent this read. Record its original
            # ordinal as unknown before any later explicit recovery attempt.
            value['revision_pending_baselines'][handle]=dict(existing,state='UNKNOWN');value['sequence']+=1
            store.save(value);guard();return {'state':'READ_INDETERMINATE','read_attempts':existing['ordinal']}
        if existing['state'] in {'OBSERVED','MISMATCH'}:
            return {'state':existing['state'],'read_attempts':existing['ordinal']}
        if existing['ordinal']>=5:return {'state':'READ_BUDGET_EXHAUSTED','read_attempts':existing['ordinal']}
    sender=service.workflow.sender;tokens=service.tokens
    if (type(sender) is not HTTPSender or sender.enabled is not True or type(tokens) is not TokenCache
            or tokens.policy is not store.policy or type(service.workflow) is not PersistentWorkflow
            or service.workflow.policy is not store.policy or service.workflow.token_cache is not tokens):hold()
    claimed=[None]
    def current():
        guard();verify_pins(pins,adapter)
        if gate.held() is not True or adapter.inspect_pending().proposal!=pending['proposal']:hold()
        _qualified_profile(service.profile(),pending['proposal'])
        state,latest=store.target(handle)
        if (state.get('revision_pending_images',{}).get(handle)!=pending or latest!=row
                or (claimed[0] is not None and state.get('revision_pending_baselines',{}).get(handle)!=claimed[0])):hold()
        store._authority(authority,guard,row['batch_source_sha']);return True
    token=tokens.get(guard=current);current()
    if not tokens.valid(token):hold()
    request=encode_draft('get',{'media_id':observed.original.reference},token.token)
    ordinal=1 if existing is None else existing['ordinal']+1
    claim={'state':'CLAIMED','ordinal':ordinal,'proposal_sha256':pending['proposal_sha256'],
        'request_sha256':sha256(request.body).hexdigest(),'snapshot':None,'response_sha256':None}
    value,row=store.target(handle)
    if (value.get('revision_pending_images',{}).get(handle)!=pending
            or value.get('revision_pending_baselines',{}).get(handle)!=existing):hold()
    value.setdefault('revision_pending_baselines',{})[handle]=claim;value['sequence']+=1
    current();store.save(value);claimed[0]=claim
    result={'state':'UNKNOWN','ordinal':ordinal,'proposal_sha256':claim['proposal_sha256'],
        'request_sha256':claim['request_sha256'],'snapshot':None,'response_sha256':None}
    try:
        current()
        timeout=min(30.0,gate.deadline-time.monotonic(),token.wall_deadline-time.time())
        if timeout<=0 or not tokens.valid(token):hold()
        response=sender.send(request,timeout)
        snapshot=parse_get(response,token.token,observed.original.reference,synthetic=False)
        current()
        _,targets=inventory._read_page(store.policy.root/'current-draft-publication',row['inventory_handle'],
            row['page'],row['page_sha256'],binding(store.policy.data),guard)
        target=targets[row['page_index']]
        actual=baseline_projection(GroupSnapshot(snapshot.reference,snapshot.canonical_json,snapshot.response_sha))
        if (target['reference']!=row['reference'] or target['projection_sha256']!=row['projection_sha256']
                or digest(target['projection'])!=row['projection_sha256'] or target['projection']!=actual
                or not adapter.matches_pending_snapshot(snapshot)):
            result['state']='MISMATCH'
        else:
            result.update(state='OBSERVED',snapshot=snapshot.canonical_json,response_sha256=snapshot.response_sha)
    except Exception:
        pass
    # Revalidate before recording; a failed guard leaves the original CLAIMED
    # event intact and never authorizes another GET or upload.
    current();value,_=store.target(handle)
    if value.get('revision_pending_baselines',{}).get(handle)!=claim:hold()
    value['revision_pending_baselines'][handle]=result;value['sequence']+=1
    store.save(value);claimed[0]=result;current();return {'state':('READ_INDETERMINATE' if result['state']=='UNKNOWN' else result['state']),'read_attempts':ordinal}
