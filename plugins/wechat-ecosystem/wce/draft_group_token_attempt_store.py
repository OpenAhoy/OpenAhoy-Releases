"""Single durable Group token attempt reducer and hard PREVIEW consumers.

Only actual Host admission/receipt issuers can write. Returned rows contain
facts, never a Secret/POST stage owner. Caller owns transactions and commits.
"""
from . import draft_group_operator_time_v2 as time06
from contextlib import contextmanager
from contextvars import ContextVar
import math
import json
import threading

from .draft_group_contracts import canonical,digest
from .draft_group_source_facts import (plain,closed,sha,ident,integer,enum,clone,hold,
    validate_locator,_events,check_source_fact_records_in,_locator_in,candidate_profile)

CLAIM='GROUP_TOKEN_ACQUISITION_CLAIM_V1'
ARM='GROUP_TOKEN_POST_ARMED_V1'
OUTCOME='GROUP_TOKEN_OUTCOME_V1'
CACHE='GROUP_TOKEN_CACHE_PUBLISHED_V1'
PROFILES=(CLAIM,ARM,OUTCOME,CACHE)
STAGES={CLAIM:'CLAIM',ARM:'POST_ARMED',OUTCOME:'OUTCOME',CACHE:'CACHE_PUBLISHED'}
REASONS=('INITIAL','TIME_RENEWAL','KNOWN_SUCCESS_CACHE_LOSS_RECOVERY')
TRANSPORTS=('OFFICIAL_GROUP_TOKEN_PREPARED_TLS_V1','SYNTHETIC_GROUP_TOKEN_V1')
COMMON=('schema','profile','authority','token_job_id','attempt_id','generation',
        'previous_outcome_event_sha','family_anchor_id','original_scope_sha',
        'first_event_sha','reason','recovery','use','pins','admission')
EXTRA={CLAIM:(),ARM:('prepared_transport_policy',),OUTCOME:('outcome','transport',
       'framing_policy','http_status','wechat_errcode','time_facts','cache_observation'),
       CACHE:('outcome_event_sha','cache_observation','cache_owner_binding_sha')}
USE=('kind','purpose_instance_id','first_purpose_key','operation_id','phase','grant_or_parent_sha')
PINS=('binding_sha','policy_identity_sha','source_material_sha','source_qualification_locator',
      'source_qualification_evidence_sha','registration_sha','helper_acceptance_sha','candidate_scope')
ADMISSION=('id','claim_event_sha','post_arm_event_sha')
_SCOPE=ContextVar('fixed_group_token_write',default=None)
_ISSUED={}


def is_token_profile(profile):
    return type(profile) is str and profile.startswith('GROUP_TOKEN_')


def build_token_job_id(account_key,family_anchor_id,origin_request_identity_sha):
    sha(account_key);sha(family_anchor_id);sha(origin_request_identity_sha)
    return digest({'profile':'GROUP_TOKEN_JOB_ID_V1','account_key':account_key,
        'family_anchor_id':family_anchor_id,'origin_request_identity_sha':origin_request_identity_sha,
        'original_job_kind':'GROUP08_SAME_REQUEST','credential_purpose':'GROUP08_STABLE_TOKEN_V1'})


def build_attempt_id(token_job_id,generation,previous_outcome_event_sha):
    sha(token_job_id);integer(generation,1)
    if previous_outcome_event_sha is not None:sha(previous_outcome_event_sha)
    if (generation==1)!=(previous_outcome_event_sha is None):hold('GROUP_TOKEN_PREDECESSOR_INVALID')
    return digest({'profile':'GROUP_TOKEN_ATTEMPT_ID_V1','token_job_id':token_job_id,
                   'generation':generation,'previous_outcome_event_sha':previous_outcome_event_sha})


def stage_preview_id(attempt_id,profile):
    sha(attempt_id);enum(profile,PROFILES)
    return 'gt-'+digest({'attempt_id':attempt_id,'stage':STAGES[profile]})


def validate_use(use):
    closed(use,USE);enum(use['kind'],('READ_PURPOSE','CHILD_EXECUTION'))
    for k in ('purpose_instance_id','first_purpose_key','phase'):ident(use[k])
    sha(use['grant_or_parent_sha'])
    if use['kind']=='READ_PURPOSE':
        if use['operation_id'] is not None:hold('GROUP_TOKEN_USE_INVALID')
    else:ident(use['operation_id'])
    return use


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:hold('GROUP_TOKEN_CLOCK_INVALID')
    return value


def validate_time_facts(value):
    closed(value,('wall_start','continuous_start','wall_deadline','continuous_deadline','margin_seconds'))
    for k in ('wall_start','continuous_start','wall_deadline','continuous_deadline'):_number(value[k])
    if type(value['margin_seconds']) is not int or value['margin_seconds']!=30:hold()
    wall=value['wall_deadline']-value['wall_start'];cont=value['continuous_deadline']-value['continuous_start']
    if not (0<wall<=7200.1 and 0<cont<=7200.1 and abs(wall-cont)<=0.000001):hold('GROUP_TOKEN_TTL_INVALID')
    return value


def validate_token_candidate(candidate):
    plain(candidate)
    if type(candidate) is not dict:hold()
    profile=candidate.get('profile');enum(profile,PROFILES)
    c=closed(candidate,COMMON+EXTRA[profile])
    if type(c['schema']) is not int or c['schema']!=1 or c['authority'] is not False:hold()
    for k in ('token_job_id','attempt_id','family_anchor_id','original_scope_sha','first_event_sha'):sha(c[k])
    integer(c['generation'],1);enum(c['reason'],REASONS);validate_use(c['use'])
    if c['previous_outcome_event_sha'] is not None:sha(c['previous_outcome_event_sha'])
    if c['attempt_id']!=build_attempt_id(c['token_job_id'],c['generation'],c['previous_outcome_event_sha']):hold('GROUP_TOKEN_ATTEMPT_ID_INVALID')
    if (c['generation']==1)!=(c['reason']=='INITIAL'):hold('GROUP_TOKEN_REASON_INVALID')
    r=c['recovery']
    if c['reason']=='KNOWN_SUCCESS_CACHE_LOSS_RECOVERY':
        closed(r,('recovery_id','predecessor_outcome_event_sha','predecessor_cache_publish_event_sha','cache_loss_kind','purpose_instance_id'))
        sha(r['recovery_id']);sha(r['predecessor_outcome_event_sha']);ident(r['purpose_instance_id'])
        enum(r['cache_loss_kind'],('PARSED_SUCCESS_NOT_PUBLISHED','PUBLISHED_CACHE_LOST'))
        if r['cache_loss_kind']=='PARSED_SUCCESS_NOT_PUBLISHED':
            if r['predecessor_cache_publish_event_sha'] is not None:hold()
        else:sha(r['predecessor_cache_publish_event_sha'])
        if (r['predecessor_outcome_event_sha']!=c['previous_outcome_event_sha']
            or r['purpose_instance_id']!=c['use']['purpose_instance_id']
            or r['recovery_id']!=digest({'profile':'GROUP_TOKEN_RECOVERY_ID_V1',
              'token_job_id':c['token_job_id'],'predecessor_outcome_event_sha':c['previous_outcome_event_sha'],
              'purpose_instance_id':r['purpose_instance_id']})):hold('GROUP_TOKEN_RECOVERY_INVALID')
    elif r is not None:hold('GROUP_TOKEN_RECOVERY_INVALID')
    pins=closed(c['pins'],PINS)
    for k in PINS:
        if k!='source_qualification_locator':sha(pins[k])
    validate_locator(pins['source_qualification_locator'])
    if pins['source_qualification_locator']['evidence_sha']!=pins['source_qualification_evidence_sha']:hold()
    a=closed(c['admission'],ADMISSION);ident(a['id'])
    for k in ('claim_event_sha','post_arm_event_sha'):
        if a[k] is not None:sha(a[k])
    if profile==CLAIM:
        if a['claim_event_sha'] is not None or a['post_arm_event_sha'] is not None:hold()
    elif profile==ARM:
        sha(a['claim_event_sha'])
        if a['post_arm_event_sha'] is not None:hold()
        enum(c['prepared_transport_policy'],TRANSPORTS)
    else:
        sha(a['claim_event_sha']);sha(a['post_arm_event_sha'])
    if profile==OUTCOME:
        enum(c['outcome'],('KNOWN_SUCCESS','KNOWN_REJECTED','UNKNOWN'))
        enum(c['transport'],TRANSPORTS+('NO_QUALIFIED_RESPONSE',))
        enum(c['framing_policy'],('STRICT_GROUP_HTTP_FRAMING_V1','NO_COMPLETE_FRAMING'))
        if c['http_status'] is not None:integer(c['http_status'],100,599)
        if c['wechat_errcode'] is not None:
            integer(c['wechat_errcode'],-2**31,2**31-1)
            if c['wechat_errcode']==0:hold()
        if c['cache_observation']!='NOT_CONFIRMED':hold()
        if c['transport']=='NO_QUALIFIED_RESPONSE':
            if any(c[k] is not None for k in ('http_status','wechat_errcode','time_facts')) or c['outcome']!='UNKNOWN' or c['framing_policy']!='NO_COMPLETE_FRAMING':hold()
        if c['outcome']=='KNOWN_SUCCESS':
            if c['transport']=='NO_QUALIFIED_RESPONSE' or c['framing_policy']!='STRICT_GROUP_HTTP_FRAMING_V1' or c['http_status'] is None or not 200<=c['http_status']<300 or c['wechat_errcode'] is not None:hold()
            validate_time_facts(c['time_facts'])
        elif c['time_facts'] is not None:hold()
        if c['outcome']=='KNOWN_REJECTED' and (c['transport']=='NO_QUALIFIED_RESPONSE'
            or c['framing_policy']!='STRICT_GROUP_HTTP_FRAMING_V1' or c['wechat_errcode'] is None or c['http_status']!=200):hold()
    if profile==CACHE:
        sha(c['outcome_event_sha']);sha(c['cache_owner_binding_sha'])
        if c['cache_observation']!='PUBLISHED_IN_ORIGINAL_PROCESS':hold()
    return c


def _source_for(info,candidate,event):
    pins=candidate['pins'];item=_locator_in(info,pins['source_qualification_locator'])
    f=item['candidate'];s=f['claim_selector'];loc=item['locator']
    source_event=next((e for e in info['chains'][f['qid']] if e['event_sha']==loc['event_sha']),None)
    if source_event is None or source_event['payload']['source_kind']!=event['payload']['source_kind']:hold('GROUP_TOKEN_SOURCE_DOMAIN_INVALID')
    if (f['token_job_id']!=candidate['token_job_id'] or f['family_id']!=candidate['family_anchor_id']
        or f['original_scope_sha']!=candidate['original_scope_sha'] or f['binding_sha']!=pins['binding_sha']
        or f['source_material_sha']!=pins['source_material_sha'] or f['registration_sha']!=pins['registration_sha']
        or f['host_acceptance_sha']!=pins['helper_acceptance_sha'] or f['purpose_key']!=candidate['use']['first_purpose_key']
        or s['ledger_kind']!='TOKEN' or s['api']!='STABLE_TOKEN' or s['slot']!=candidate['use']['purpose_instance_id']
        or s['ordinal']!=candidate['generation'] or s['request_sha'] is not None
        or loc['account_key']!=event['account_key'] or loc['event_seq']>=event['seq']):hold('GROUP_TOKEN_SOURCE_FACT_INVALID')
    return f


def _same_attempt(old,new,*,allow_fact_version=False):
    for key in ('token_job_id','attempt_id','generation','previous_outcome_event_sha','family_anchor_id',
                'original_scope_sha','first_event_sha','reason','recovery','use'):
        if canonical(old[key])!=canonical(new[key]):hold('GROUP_TOKEN_STAGE_DRIFT')
    if old['admission']['id']!=new['admission']['id']:hold()
    for k in PINS:
        if allow_fact_version and k in ('source_qualification_locator','source_qualification_evidence_sha'):continue
        if canonical(old['pins'][k])!=canonical(new['pins'][k]):hold('GROUP_TOKEN_STAGE_DRIFT')


def replay_token_records(events,source_info):
    """Pure complete all-pool reducer; unresolved stages are valid readable facts."""
    jobs={};attempts={};admissions={};seen=set();firsts={}
    for event in events:
        if event['kind']!='PREVIEW':continue
        p=event['payload'];c=p.get('candidate');profile=c.get('profile') if type(c) is dict else None
        if profile=='GROUP_READ_FAMILY_ROOT_V1':firsts.setdefault(c['family_anchor_id'],[]).append(event)
        if not is_token_profile(profile):continue
        validate_token_candidate(c);aid=c['attempt_id'];jid=c['token_job_id']
        enum(p['source_kind'],('SYNTHETIC_SETUP','OPERATOR_ATTESTED'))
        transport_policy=('OFFICIAL_GROUP_TOKEN_PREPARED_TLS_V1' if p['source_kind']=='OPERATOR_ATTESTED'
                          else 'SYNTHETIC_GROUP_TOKEN_V1')
        if profile==ARM and c['prepared_transport_policy']!=transport_policy:hold('GROUP_TOKEN_TRANSPORT_DOMAIN_INVALID')
        if profile==OUTCOME and c['transport'] not in (transport_policy,'NO_QUALIFIED_RESPONSE'):hold('GROUP_TOKEN_TRANSPORT_DOMAIN_INVALID')
        expected_id=stage_preview_id(aid,profile)
        if (p['preview_id']!=expected_id or p['request_key']!=expected_id or p['input_sha']!=jid
            or p['scope_sha']!=c['original_scope_sha'] or p['evidence_sha']!=digest(c)
            or p['binding_sha']!=c['pins']['binding_sha'] or event['account_key']!=p['binding_sha']):hold('GROUP_TOKEN_WRAPPER_INVALID')
        roots=firsts.get(c['family_anchor_id'],[])
        if len(roots)!=1:hold('GROUP_TOKEN_FIRST_REQUIRED')
        first=roots[0];fc=first['payload']['candidate']
        if first['payload']['source_kind']!=p['source_kind']:hold('GROUP_TOKEN_TRANSPORT_DOMAIN_INVALID')
        if (c['first_event_sha']!=first['event_sha'] or jid!=build_token_job_id(fc['platform_account_sha'],fc['family_anchor_id'],fc['request_identity_sha'])):hold('GROUP_TOKEN_JOB_INVALID')
        f=_source_for(source_info,c,event)
        # Account ordering is not chronology across roots. The contract requires
        # the actual Family bridge; events within an attempt are linked by SHA.
        if (aid,profile) in seen:hold('GROUP_TOKEN_DUPLICATE_STAGE')
        seen.add((aid,profile))
        if profile==CLAIM:
            if aid in attempts or c['admission']['id'] in admissions:hold('GROUP_TOKEN_DUPLICATE_CLAIM')
            admissions[c['admission']['id']]=aid
            entry={'attempt_id':aid,'token_job_id':jid,'generation':c['generation'],
                   'state':'CLAIMED_UNKNOWN','claim':event,'arm':None,'outcome':None,'cache':None}
            attempts[aid]=entry;jobs.setdefault(jid,[]).append(entry)
        else:
            entry=attempts.get(aid)
            if entry is None:hold('GROUP_TOKEN_STAGE_WITHOUT_CLAIM')
            claim=entry['claim'];cc=claim['payload']['candidate']
            if claim['account_key']==event['account_key'] and claim['seq']>=event['seq']:hold('GROUP_TOKEN_STAGE_ORDER_INVALID')
            _same_attempt(cc,c,allow_fact_version=True)
            if c['admission']['claim_event_sha']!=claim['event_sha']:hold('GROUP_TOKEN_CLAIM_LINK_INVALID')
            if profile==ARM:
                if entry['arm'] is not None or entry['outcome'] is not None:hold()
                oldf=_source_for(source_info,cc,claim)
                for k in ('qid','binding_sha','family_id','first_proof_sha','registration_sha',
                          'registration_proof_sha','source_material_sha','original_scope_sha',
                          'covenant_sha','purpose_key','token_job_id','claim_selector','source_descriptor',
                          'host_acceptance_sha'):
                    if canonical(oldf[k])!=canonical(f[k]):hold('GROUP_TOKEN_ARM_SOURCE_DRIFT')
                if f['qualified_not_after_ms']>oldf['qualified_not_after_ms']:hold('GROUP_TOKEN_ARM_DEADLINE_EXTENDED')
                entry['arm']=event;entry['state']='POST_ARMED_UNKNOWN'
            else:
                arm=entry['arm']
                if arm is None or c['admission']['post_arm_event_sha']!=arm['event_sha']:hold('GROUP_TOKEN_ARM_LINK_INVALID')
                if arm['account_key']==event['account_key'] and arm['seq']>=event['seq']:hold('GROUP_TOKEN_STAGE_ORDER_INVALID')
                _same_attempt(arm['payload']['candidate'],c)
                if profile==OUTCOME:
                    if (c['transport']!='NO_QUALIFIED_RESPONSE' and c['transport']!=arm['payload']['candidate']['prepared_transport_policy']):hold('GROUP_TOKEN_ARM_TRANSPORT_MISMATCH')
                    if entry['outcome'] is not None:hold()
                    entry['outcome']=event;entry['state']=c['outcome']
                else:
                    out=entry['outcome']
                    if out is None or out['payload']['candidate']['outcome']!='KNOWN_SUCCESS' or c['outcome_event_sha']!=out['event_sha']:hold('GROUP_TOKEN_CACHE_WITHOUT_SUCCESS')
                    if out['account_key']==event['account_key'] and out['seq']>=event['seq']:hold('GROUP_TOKEN_STAGE_ORDER_INVALID')
                    entry['cache']=event
    # Sort by stable generation after collecting all physical roots; never use
    # pool ordering as cross-root chronology or ignore a newer unresolved row.
    for jid,chain in jobs.items():
        chain.sort(key=lambda x:x['generation'])
        for i,entry in enumerate(chain):
            c=entry['claim']['payload']['candidate']
            if c['generation']!=i+1:hold('GROUP_TOKEN_GENERATION_GAP')
            if i==0:
                if c['reason']!='INITIAL' or c['previous_outcome_event_sha'] is not None:hold()
            else:
                prior=chain[i-1];out=prior['outcome'];cache=prior['cache']
                if out is None or prior['state']!='KNOWN_SUCCESS' or c['previous_outcome_event_sha']!=out['event_sha']:hold('GROUP_TOKEN_UNKNOWN_PREDECESSOR')
                if out['account_key']==entry['claim']['account_key'] and out['seq']>=entry['claim']['seq']:hold('GROUP_TOKEN_SUCCESSOR_ORDER_INVALID')
                if c['family_anchor_id']!=out['payload']['candidate']['family_anchor_id'] or c['original_scope_sha']!=out['payload']['candidate']['original_scope_sha']:hold('GROUP_TOKEN_SUCCESSOR_SCOPE_DRIFT')
                if c['reason']=='KNOWN_SUCCESS_CACHE_LOSS_RECOVERY':
                    recovery=c['recovery']
                    if (cache is None)!=(recovery['cache_loss_kind']=='PARSED_SUCCESS_NOT_PUBLISHED'):hold('GROUP_TOKEN_CACHE_LOSS_INVALID')
                    if cache is not None and recovery['predecessor_cache_publish_event_sha']!=cache['event_sha']:hold()
    return {'jobs':jobs,'attempts':attempts}


def _ordered_events(events):
    """Topological stage order across bridged roots, retaining all events."""
    plain_events=list(events)
    priority={'GROUP_READ_FAMILY_ROOT_V1':0,'GROUP_ADMISSION_SOURCE_FACTS_V1':1,'GROUP_ADMISSION_SOURCE_FACTS_V2':1,'GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1':1,time06.SOURCE_FACTS_PROFILE_V2:1,
              CLAIM:2,ARM:3,OUTCOME:4,CACHE:5}
    # Generation precedes stage; original seq still checked by source locator.
    return sorted(plain_events,key=lambda e:(0 if e['kind']=='PREVIEW' and
        candidate_profile(e['payload'])=='GROUP_READ_FAMILY_ROOT_V1' else 1,
        e['payload']['candidate'].get('generation',0) if e['kind']=='PREVIEW' and type(e['payload'].get('candidate')) is dict else 0,
        priority.get(candidate_profile(e['payload']),-1) if e['kind']=='PREVIEW' else -1,
        e['account_key'],e['seq']))


def check_token_records_in(db,states=None,history_policy=None):
    import json
    rows=db.execute("SELECT payload FROM group_events WHERE kind='PREVIEW'").fetchall()
    if not any(is_token_profile(candidate_profile(json.loads(r[0]))) for r in rows):
        return {'jobs':{},'attempts':{}}
    if history_policy is None:
        from .draft_group_read_family_store import resolve_history_policy
        history_policy=resolve_history_policy(db)
    facts=check_source_fact_records_in(db,states,history_policy)
    info=replay_token_records(_ordered_events(_events(db)),facts)
    from .draft_group_runtime_host import validate_token_history_in
    for entry in info['attempts'].values():
        for stage in ('claim','arm','outcome','cache'):
            if entry[stage] is not None:validate_token_history_in(db,entry[stage]['payload']['candidate'],history_policy)
    return info


def query_token_attempt_in(db,history_reader=None,root_closure=None,token_job_id=None):
    # The reader/closure are actual fixed historical objects, not callables which
    # grant writes. A supplies and verifies the current Owned history context.
    if token_job_id is None:hold('GROUP_TOKEN_JOB_REQUIRED')
    sha(token_job_id)
    from .draft_group_runtime_host import validate_token_query_context
    validate_token_query_context(db,history_reader,root_closure,token_job_id)
    if history_reader is not None and callable(history_reader):hold('GROUP_TOKEN_HISTORY_CONTEXT_REQUIRED')
    info=check_token_records_in(db)
    entries=info['jobs'].get(token_job_id,[])
    # All events already passed the closed per-record codec; do not introduce
    # an accidental per-job lifetime byte/count cap on successful generations.
    return json.loads(canonical({'state':'ABSENT' if not entries else entries[-1]['state'],
                  'attempts':entries,'latest':None if not entries else entries[-1],
                  'authority':False}))


def validate_successor_conditions(history,reason,use,*,wall_now,continuous_now,
        cache_available,cache_loss_kind=None,cache_owner_binding_sha=None):
    """Pure current measurements checker, invoked by actual Host admission.

    This function is not an admission: cache booleans and clocks supplied by a
    caller confer no rights. A must derive them from the actual cache/runtime.
    """
    if type(history) is not dict:hold()
    enum(reason,REASONS);validate_use(use)
    _number(wall_now);_number(continuous_now)
    if type(cache_available) is not bool:hold()
    if cache_available:hold('GROUP_TOKEN_CACHE_HIT_NO_ACQUISITION')
    latest=history.get('latest')
    plain(latest,maximum=128*1024)
    if latest is None:
        if reason!='INITIAL' or cache_loss_kind is not None:hold('GROUP_TOKEN_REASON_INVALID')
        return {'generation':1,'previous_outcome_event_sha':None,'recovery':None}
    if latest['state']!='KNOWN_SUCCESS' or latest['outcome'] is None:hold('GROUP_TOKEN_RESULT_UNKNOWN')
    out=latest['outcome'];oc=out['payload']['candidate'];validate_time_facts(oc['time_facts'])
    if reason=='INITIAL':hold()
    recovery=None
    if reason=='TIME_RENEWAL':
        t=oc['time_facts'];wall=wall_now-t['wall_start'];cont=continuous_now-t['continuous_start']
        if wall<0 or cont<0 or abs(wall-cont)>=5 or (wall_now<t['wall_deadline']-30 and continuous_now<t['continuous_deadline']-30):hold('GROUP_TOKEN_RENEWAL_NOT_DUE')
        if cache_loss_kind is not None:hold()
    else:
        cache=latest['cache'];expected='PARSED_SUCCESS_NOT_PUBLISHED' if cache is None else 'PUBLISHED_CACHE_LOST'
        if cache_loss_kind!=expected:hold('GROUP_TOKEN_CACHE_LOSS_INVALID')
        if cache is not None:
            sha(cache_owner_binding_sha)
            if cache_owner_binding_sha!=cache['payload']['candidate']['cache_owner_binding_sha']:hold()
        recovery={'recovery_id':digest({'profile':'GROUP_TOKEN_RECOVERY_ID_V1','token_job_id':oc['token_job_id'],
            'predecessor_outcome_event_sha':out['event_sha'],'purpose_instance_id':use['purpose_instance_id']}),
            'predecessor_outcome_event_sha':out['event_sha'],
            'predecessor_cache_publish_event_sha':None if cache is None else cache['event_sha'],
            'cache_loss_kind':cache_loss_kind,'purpose_instance_id':use['purpose_instance_id']}
    return {'generation':latest['generation']+1,'previous_outcome_event_sha':out['event_sha'],'recovery':recovery}


@contextmanager
def _write_scope(db,context,candidate,*,historical=False, history_locators=None):
    from . import draft_group_runtime_host as host
    if historical:
        actual=host.validate_token_historical_receipt(context,db=db)
        if canonical(actual)!=canonical(candidate):hold('GROUP_TOKEN_RECEIPT_INVALID')
    else:host.validate_token_admission(context,db=db,candidate=candidate, history_locators=history_locators)
    from .own_validation_scope import _transaction_marker
    epoch=_transaction_marker(db)
    if epoch is None:hold('GROUP_TRANSACTION_LIFETIME_UNPROVEN')
    scope=(db,context,clone(candidate),historical,threading.get_ident(),epoch,[])
    _ISSUED[id(scope)]=scope;token=_SCOPE.set(scope)
    try:yield
    finally:_SCOPE.reset(token);_ISSUED.pop(id(scope),None)


def token_before_event_in(db,account,kind,payload, *, history_locators=None):
    c=payload.get('candidate') if kind=='PREVIEW' else None
    profile=c.get('profile') if type(c) is dict else None
    if not is_token_profile(profile):return
    validate_token_candidate(c)
    from .own_validation_scope import _transaction_marker
    scope=_SCOPE.get()
    if (scope is None or _ISSUED.get(id(scope)) is not scope or scope[0] is not db
        or scope[4]!=threading.get_ident() or scope[5]!=_transaction_marker(db)
        or canonical(scope[2])!=canonical(c) or scope[6]):hold('GROUP_TOKEN_ADMISSION_REQUIRED')
    from . import draft_group_runtime_host as host
    if scope[3]:
        actual=host.validate_token_historical_receipt(scope[1],db=db)
        if canonical(actual)!=canonical(c) or profile not in (OUTCOME,CACHE):hold()
    else:
        if profile not in (CLAIM,ARM):hold()
        host.validate_token_admission(scope[1],db=db,candidate=c, history_locators=history_locators)
    check_token_records_in(db)
    scope[6].append((account,stage_preview_id(c['attempt_id'],profile),digest(c)))


def token_after_event_in(db,*,account=None,kind=None,payload=None):
    scope=_SCOPE.get()
    profile=candidate_profile(payload) if kind=='PREVIEW' else None
    if is_token_profile(profile) and scope is None:hold('GROUP_TOKEN_ADMISSION_REQUIRED')
    if scope is None:
        check_token_records_in(db)
        return
    if _ISSUED.get(id(scope)) is not scope or scope[0] is not db or len(scope[6])!=1:hold()
    info=check_token_records_in(db)
    account,pid,evidence=scope[6][0];c=scope[2]
    entry=info['attempts'].get(c['attempt_id'])
    stage={CLAIM:'claim',ARM:'arm',OUTCOME:'outcome',CACHE:'cache'}[c['profile']]
    event=None if entry is None else entry[stage]
    if event is None or event['account_key']!=account or event['payload']['preview_id']!=pid or event['payload']['evidence_sha']!=evidence:hold()


def _append(db,store,context,candidate,*,historical=False, history_locators=None):
    validate_token_candidate(candidate)
    from .draft_group_store import GroupStore
    if type(store) is not GroupStore or store.binding_sha!=candidate['pins']['binding_sha']:hold()
    info=check_token_records_in(db);entry=info['attempts'].get(candidate['attempt_id'])
    stage={CLAIM:'claim',ARM:'arm',OUTCOME:'outcome',CACHE:'cache'}[candidate['profile']]
    old=None if entry is None else entry[stage]
    if old is not None:
        if canonical(old['payload']['candidate'])!=canonical(candidate):hold('GROUP_TOKEN_STAGE_CONFLICT')
        return clone(old)  # Readback is facts only; A cannot mint from this path.
    with _write_scope(db,context,candidate,historical=historical, history_locators=history_locators):
        pid=stage_preview_id(candidate['attempt_id'],candidate['profile'])
        source_kind=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
        store.register_preview_in(db,pid,source_kind=source_kind,input_sha=candidate['token_job_id'],
            request_key=pid,scope_sha=candidate['original_scope_sha'],candidate=clone(candidate),evidence_sha=digest(candidate), history_locators=history_locators)
    return clone(check_token_records_in(db)['attempts'][candidate['attempt_id']][stage])


def claim_token_acquisition_in(db,group_store,live_token_context,reason,use,*,candidate, history_locators=None):
    validate_token_candidate(candidate)
    if candidate['profile']!=CLAIM or candidate['reason']!=reason or canonical(candidate['use'])!=canonical(use):hold()
    return _append(db,group_store,live_token_context,candidate, history_locators=history_locators)


def arm_token_post_in(db,group_store,live_token_context,attempt_id,*,candidate, history_locators=None):
    validate_token_candidate(candidate)
    if candidate['profile']!=ARM or candidate['attempt_id']!=attempt_id:hold()
    return _append(db,group_store,live_token_context,candidate, history_locators=history_locators)


def observe_token_outcome_in(db,group_store,historical_token_receipt, *, history_locators=None):
    from .draft_group_runtime_host import validate_token_historical_receipt
    candidate=validate_token_historical_receipt(historical_token_receipt,db=db)
    validate_token_candidate(candidate)
    if candidate['profile']!=OUTCOME:hold()
    return _append(db,group_store,historical_token_receipt,candidate,historical=True, history_locators=history_locators)


def observe_token_cache_publish_in(db,group_store,historical_cache_receipt, *, history_locators=None):
    from .draft_group_runtime_host import validate_token_historical_receipt
    candidate=validate_token_historical_receipt(historical_cache_receipt,db=db)
    validate_token_candidate(candidate)
    if candidate['profile']!=CACHE:hold()
    return _append(db,group_store,historical_cache_receipt,candidate,historical=True, history_locators=history_locators)


class GroupTokenAttemptStore:
    query_token_attempt_in=staticmethod(query_token_attempt_in)
    claim_token_acquisition_in=staticmethod(claim_token_acquisition_in)
    arm_token_post_in=staticmethod(arm_token_post_in)
    observe_token_outcome_in=staticmethod(observe_token_outcome_in)
    observe_token_cache_publish_in=staticmethod(observe_token_cache_publish_in)
