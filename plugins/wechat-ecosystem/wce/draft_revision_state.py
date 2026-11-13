"""Closed revision journal reducer. No authority, filesystem or network calls."""
from copy import deepcopy
from .contracts import WCEError
from .service import digest

PHASES = frozenset({'BASELINE','PRE_SEND','POST_SEND','RECOVERY_BASELINE','RECOVERY_EFFECT'})
ZERO = '0'*64
REVIEW_PROFILE = 'SOURCE_REVIEW_CONTINUATION_V1'
CLAIM_REVIEW_PROFILE = 'SOURCE_REVIEWED_CLAIM_V1'


def hold(code='DRAFT_REVISION_EVENT_HOLD'):
    raise WCEError(code)


def checksum(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def claim_review(value, head=None):
    """Historical claim linkage only. It cannot establish current authority."""
    fields={'profile','review_id','review_sha','manifest_sha','observation_sha','gate_epoch'}
    if (type(value) is not dict or set(value)!=fields
            or value['profile']!=CLAIM_REVIEW_PROFILE
            or any(not checksum(value[k]) for k in fields-{'profile','gate_epoch'})
            or type(value['gate_epoch']) is not str or len(value['gate_epoch'])!=32
            or any(c not in '0123456789abcdef' for c in value['gate_epoch'])):hold()
    if head is not None and (type(head) is not dict
            or value['review_id']!=head['review_id']
            or value['review_sha']!=head['proof_sha']
            or value['manifest_sha']!=head['review_manifest_sha']):hold()
    return deepcopy(value)


def reduce(previous, kind, data):
    """Each accepted event has one deterministic full SQL projection."""
    if type(data) is not dict or (previous is not None and type(previous) is not dict):hold()
    schemas = {
        'REGISTER': {'case','registration'},
        'ADOPT_PENDING_BASELINE': {'witness'},
        'READ_CLAIM': {'ordinal','phase','proof_sha'},
        'READ_RESULT': {'ordinal','status','snapshot_sha','proof_sha'},
        'PREPARED': {'ordinal','baseline_sha','expected_sha','proof_sha'},
        'UPDATE_CLAIM': {'ordinal','request_sha','proof_sha'},
        'UPDATE_RESPONSE': {'response_state','errcode','response_raw_sha','proof_sha'},
        'READ_EFFECT': {'ordinal','matched'},
        'SOURCE_REVIEW': {'review_id','previous_review_sha','proof_sha',
            'review_manifest_sha','origin_binding_sha'},
    }
    expected=schemas.get(kind)
    if expected is None:hold()
    reviewed=previous is not None and 'source_review' in previous
    if kind in {'READ_CLAIM','UPDATE_CLAIM'} and reviewed:
        expected=expected|{'source_review'}
    if set(data)!=expected:hold()
    if kind=='REGISTER':
        if previous is not None: hold()
        case=deepcopy(data['case'])
        return {'case':case,'registration':deepcopy(data['registration']), 'revision':{'case_id':case['id'],
            'id':digest({'case':case['id'],'profile':case['profile']}),
            'state':'PREPARING','reads':0,'writes':0,'baseline_sha':None,
            'expected_sha':None,'preparation_sha':None,'claim_sha':None,
            'response_sha':None,'response_state':None,'request_sha':None,'effect':None},'read_claims':[]}
    if previous is None: hold()
    result=deepcopy(previous); row=result['revision']; reads=result['read_claims']
    if ((result.get('registration') or {}).get('profile')=='HOST_REVIEWED_EXACT_DIRECT_ONE_IMAGE_REVISION_V1'
            and kind in {'READ_CLAIM','PREPARED','UPDATE_CLAIM'} and 'pending_adoption' not in result):hold()
    if kind=='ADOPT_PENDING_BASELINE':
        witness=data['witness'];fields={'profile','account_key','binding_sha256','case_id','handle',
            'proposal_sha256','source_head_sequence','source_head_sha256','baseline_sha256',
            'snapshot_sha256','snapshot','reads'}
        if (type(witness) is not dict or set(witness)!=fields
                or witness['profile']!='CURRENT_PENDING_BASELINE_ADOPTED_V1'
                or result['case']['provider_profile']!='OFFICIAL_OWN_NEWS_REVISION_V1'
                or (result.get('registration') or {}).get('profile')!='HOST_REVIEWED_EXACT_DIRECT_ONE_IMAGE_REVISION_V1'
                or witness['case_id']!=result['case']['id'] or witness['binding_sha256']!=result['case']['binding']
                or row['state']!='PREPARING' or row['reads']!=0 or row['writes']!=0 or reads
                or 'pending_adoption' in result or type(witness['source_head_sequence']) is not int
                or witness['source_head_sequence']<1 or type(witness['handle']) is not str
                or type(witness['reads']) is not list or not 1<=len(witness['reads'])<=5
                or type(witness['snapshot']) is not dict
                or any(not checksum(witness[key]) for key in ('account_key','binding_sha256','case_id',
                    'proposal_sha256','source_head_sha256','baseline_sha256','snapshot_sha256'))):hold()
        for index,item in enumerate(witness['reads'],1):
            if (type(item) is not dict or set(item)!={'ordinal','state','claim_event_sha256','result_event_sha256'}
                    or type(item['ordinal']) is not int or item['ordinal']!=index
                    or item['state']!=('OBSERVED' if index==len(witness['reads']) else 'UNKNOWN')
                    or not checksum(item['claim_event_sha256']) or not checksum(item['result_event_sha256'])):hold()
            reads.append({'ordinal':index,'phase':'BASELINE' if index==1 else 'RECOVERY_BASELINE',
                'state':item['state'],'claim_sha':item['claim_event_sha256'],
                'result_sha':item['result_event_sha256'],
                'snapshot_sha':witness['snapshot_sha256'] if item['state']=='OBSERVED' else None,
                'pending_origin':'CURRENT_PENDING_BASELINE_ADOPTED_V1'})
        row['reads']=len(reads);result['pending_adoption']=deepcopy(witness)
        return result
    if kind=='SOURCE_REVIEW':
        # This pilot only establishes its first review before any claim. A
        # duplicate intent is queried by the store, never appended again here.
        if (reviewed or row['state']!='PREPARING' or row['reads']!=0 or row['writes']!=0
                or reads or data['previous_review_sha'] is not None
                or any(not checksum(data[k]) for k in expected-{'previous_review_sha'})
                or data['origin_binding_sha']!=digest(result['case'])):hold()
        result['source_review']=deepcopy(data)
        return result
    linkage=None
    if kind in {'READ_CLAIM','UPDATE_CLAIM'} and reviewed:
        linkage=claim_review(data['source_review'],result['source_review'])
    if 'ordinal' in data:
        ordinal=data['ordinal']
        if type(ordinal) is not int or not 1<=ordinal<=5: hold()
    if 'proof_sha' in data and not checksum(data['proof_sha']): hold()
    if kind=='READ_CLAIM':
        phase=data['phase']
        if phase not in PHASES or ordinal!=row['reads']+1 or row['reads']>=5: hold()
        if phase in {'BASELINE','RECOVERY_BASELINE'}:
            if row['state']!='PREPARING' or (phase=='BASELINE' and row['reads']!=0): hold()
        elif phase=='PRE_SEND':
            if row['state']!='PREPARED' or row['writes']: hold()
        elif not row['writes']: hold()
        row['reads']=ordinal
        # A past observation stays in its immutable event; status must not
        # present it as the current effect after a newer read was allocated.
        row['effect']=None
        reads.append({'ordinal':ordinal,'phase':phase,'state':'ALLOCATED',
            'claim_sha':data['proof_sha'],'result_sha':None,'snapshot_sha':None})
        if linkage is not None:reads[-1]['source_review']=linkage
    elif kind=='READ_RESULT':
        if ordinal>len(reads) or reads[ordinal-1]['state']!='ALLOCATED': hold()
        if data['status'] not in {'OBSERVED','UNKNOWN'}: hold()
        if (data['status']=='OBSERVED' and not checksum(data['snapshot_sha'])) or (
                data['status']=='UNKNOWN' and data['snapshot_sha'] is not None): hold()
        reads[ordinal-1].update(state=data['status'],result_sha=data['proof_sha'],snapshot_sha=data['snapshot_sha'])
    elif kind=='PREPARED':
        if row['state']!='PREPARING' or row['writes'] or ordinal!=row['reads']: hold()
        observed=reads[ordinal-1]
        if observed['state']!='OBSERVED' or observed['phase'] not in {'BASELINE','RECOVERY_BASELINE'}: hold()
        if not checksum(data['baseline_sha']) or not checksum(data['expected_sha']): hold()
        row.update(state='PREPARED',baseline_sha=data['baseline_sha'],
            expected_sha=data['expected_sha'],preparation_sha=data['proof_sha'])
    elif kind=='UPDATE_CLAIM':
        if row['state']!='PREPARED' or row['writes'] or ordinal!=row['reads']: hold()
        if not checksum(data['request_sha']):hold()
        observed=reads[ordinal-1]
        if observed['state']!='OBSERVED' or observed['phase']!='PRE_SEND': hold()
        # Service verifies complete presence-aware pre-send equality; store also
        # verifies the actual snapshot's baseline projection against PREPARED.
        row.update(state='CLAIMED',writes=1,claim_sha=data['proof_sha'],request_sha=data['request_sha'])
        if linkage is not None:row['claim_source_review']=linkage
    elif kind=='UPDATE_RESPONSE':
        if row['state']!='CLAIMED' or row['writes']!=1 or row['response_sha'] is not None: hold()
        state=data['response_state']; code=data['errcode']
        if state not in {'SUCCEEDED_RESPONSE','REJECTED_RESPONSE','RESULT_UNKNOWN'}: hold()
        if state=='RESULT_UNKNOWN':
            if code is not None or data['response_raw_sha'] is not None: hold()
        elif (type(code) is not int or not -(2**31)<=code<2**31 or
                not checksum(data['response_raw_sha']) or (code==0)!=(state=='SUCCEEDED_RESPONSE')): hold()
        row.update(state=state,response_state=state,response_sha=data['proof_sha'])
    elif kind=='READ_EFFECT':
        if row['writes']!=1 or ordinal!=row['reads'] or type(data['matched']) is not bool: hold()
        observed=reads[ordinal-1]
        if observed['state']!='OBSERVED' or observed['phase'] not in {'POST_SEND','RECOVERY_EFFECT'}: hold()
        # Transport provenance is verified by the concrete service, never
        # inferred by this storage-only reducer (including synthetic fixtures).
        origin='ADMITTED_RESPONSE_AND_READBACK' if row['response_state']=='SUCCEEDED_RESPONSE' else 'CURRENT_DRAFT_OBSERVATION'
        row['effect']={'ordinal':ordinal,'matched':data['matched'],'origin':origin}
    return result
