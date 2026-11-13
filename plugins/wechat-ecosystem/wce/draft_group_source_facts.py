"""The single Group admission SourceFacts codec and immutable SQL history.

Facts are observations, never current authority or effect owners. No connection,
DDL, commit, secret, network, OwnStore/current re-entry lives in the replay leaf.
"""
from . import draft_group_operator_time_v2 as time06
from contextlib import contextmanager
from contextvars import ContextVar
import json
import threading

from .contracts import WCEError
from .draft_group_contracts import canonical, digest

PROFILE = 'GROUP_ADMISSION_SOURCE_FACTS_V1'
PROFILE_V2 = 'GROUP_ADMISSION_SOURCE_FACTS_V2'
PROFILE_OPERATOR = 'GROUP_ADMISSION_SOURCE_FACTS_OPERATOR_V1'
PROFILE_OPERATOR_V2=time06.SOURCE_FACTS_PROFILE_V2
LOCATOR_PROFILE = 'GROUP_ADMISSION_SOURCE_FACTS_LOCATOR_V1'
MAX_VERSIONS = 4096
KEYS = ('schema','profile','authority','qid','fact_id','previous_fact_event_sha',
        'binding_sha','family_id','first_proof_sha','registration_sha',
        'registration_proof_sha','source_material_sha','current_source_review_sha',
        'original_scope_sha','covenant_sha','purpose_key','gid','parent_execution_sha',
        'operation_id','token_job_id','claim_selector','source_descriptor',
        'qualification_generation_sha','qualified_not_after_ms','host_acceptance_sha',
        'source_observation_sha')
SELECTOR_KEYS = ('ledger_kind','api','slot','ordinal','subject_sha','request_sha')
DESCRIPTOR_KEYS = ('configuration_sha','semantic_adoption_sha','role_tuple_sha',
                   'qa_adoption_sha','artifact_inventory_sha')
DESCRIPTOR_KEYS_V2 = DESCRIPTOR_KEYS + ('native_source_profile','native_observation_profile',
    'native_contract_sha256','permission_facts_sha256','runtime_source_policy_sha','current_binding_sha')
LOCATOR_KEYS = ('account_key','event_seq','event_sha','preview_id','evidence_sha')
_SCOPE = ContextVar('fixed_group_source_facts_write', default=None)
_ISSUED = {}


def hold(code='GROUP_SOURCE_FACT_UNVERIFIED'):
    raise WCEError(code)


def plain(value, *, maximum=16384):
    """Reject objects/hooks before comparison, hashing, string operations or SQL."""
    from .draft_group_store import _json
    _json(value, maximum=maximum)
    return value


def closed(value, keys):
    plain(value)
    if type(value) is not dict or set(value) != set(keys):
        hold('GROUP_FACT_FIELDS_INVALID')
    return value


def sha(value):
    from .draft_group_store import sha as check
    return check(value)


def ident(value):
    from .draft_group_store import identifier
    return identifier(value)


def integer(value, low=0, high=2**63-1):
    from .draft_group_store import integer as check
    return check(value,low,high)


def enum(value, values):
    if type(value) is not str or value not in values:
        hold('GROUP_FACT_ENUM_INVALID')
    return value


def clone(value):
    plain(value,maximum=2*1024*1024)
    return json.loads(canonical(value))


def candidate_profile(payload):
    candidate=payload.get("candidate") if type(payload) is dict else None
    return candidate.get("profile") if type(candidate) is dict else None


def is_source_profile(profile):
    # Reserve the whole named namespace: a typo must not become generic PREVIEW.
    return type(profile) is str and profile.startswith('GROUP_ADMISSION_SOURCE_FACT')


def source_fact_qid(*, binding_sha, ledger_kind, subject, api, slot, ordinal):
    sha(binding_sha); enum(ledger_kind,('PREVIEW','CHILD','TOKEN'))
    ident(subject); ident(slot); integer(ordinal,1)
    enum(api,('LIST','GET') if ledger_kind=='PREVIEW' else
         ('GET','ADD','DELETE') if ledger_kind=='CHILD' else ('STABLE_TOKEN',))
    if ledger_kind=='PREVIEW' and slot != ('PREVIEW_LIST:' if api=='LIST' else 'PREVIEW_GET:')+str(ordinal):
        hold('GROUP_FACT_SELECTOR_INVALID')
    return digest({'profile':LOCATOR_PROFILE,'binding_sha':binding_sha,
                   'ledger_kind':ledger_kind,'subject':subject,'api':api,
                   'slot':slot,'ordinal':ordinal})


def descriptor_sha(candidate):
    closed(candidate,KEYS)
    return digest({k:v for k,v in candidate.items() if k!='fact_id'})


def source_fact_id(candidate):
    return digest({'qid':candidate['qid'],
                   'previous_fact_event_sha':candidate['previous_fact_event_sha'],
                   'descriptor_sha':descriptor_sha(candidate)})


def validate_source_fact(candidate):
    c=closed(candidate,KEYS)
    if (type(c['schema']) is not int or (c['schema'],c['profile']) not in
        ((1,PROFILE),(2,PROFILE_V2),(1,PROFILE_OPERATOR),(2,PROFILE_OPERATOR_V2)) or c['authority'] is not False):
        hold('GROUP_FACT_PROFILE_INVALID')
    for k in ('qid','fact_id','binding_sha','family_id','first_proof_sha',
              'registration_sha','registration_proof_sha','source_material_sha',
              'original_scope_sha','covenant_sha','qualification_generation_sha',
              'host_acceptance_sha','source_observation_sha'):
        sha(c[k])
    for k in ('previous_fact_event_sha','current_source_review_sha'):
        if c[k] is not None:sha(c[k])
    ident(c['purpose_key']); integer(c['qualified_not_after_ms'],1)
    s=closed(c['claim_selector'],SELECTOR_KEYS)
    enum(s['ledger_kind'],('PREVIEW','CHILD','TOKEN'))
    ident(s['slot']);integer(s['ordinal'],1);sha(s['subject_sha'])
    if c['profile']==PROFILE_OPERATOR_V2:
        try:d=time06.validate_descriptor_v2(c['source_descriptor'])
        except (time06.old.OperatorSourceCodecError,time06.OperatorTimeCodecError):hold('GROUP_FACT_OPERATOR_BINDING')
        if c['current_source_review_sha'] is None:hold('GROUP_FACT_OPERATOR_REVIEW_REQUIRED')
    elif c['profile']==PROFILE_OPERATOR:
        from .draft_group_operator_source_codec import validate_descriptor,OperatorSourceCodecError
        try:d=validate_descriptor(c['source_descriptor'])
        except OperatorSourceCodecError:hold('GROUP_FACT_OPERATOR_BINDING')
        if c['current_source_review_sha'] is None:hold('GROUP_FACT_OPERATOR_REVIEW_REQUIRED')
    else:
        d=closed(c['source_descriptor'],DESCRIPTOR_KEYS if c['profile']==PROFILE else DESCRIPTOR_KEYS_V2)
        for key in DESCRIPTOR_KEYS:sha(d[key])
    if c['profile']==PROFILE_V2:
        if (d['native_source_profile']!='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'
            or d['native_observation_profile']!='GROUP_CURRENT_SOURCE_OBSERVATION_V2'
            or c['current_source_review_sha'] is None):hold('GROUP_FACT_NATIVE_V2_BINDING')
        for key in DESCRIPTOR_KEYS_V2[len(DESCRIPTOR_KEYS)+2:]:sha(d[key])
    if s['ledger_kind']=='PREVIEW':
        ident(c['gid']);subject=c['gid']
        if any(c[k] is not None for k in ('parent_execution_sha','operation_id','token_job_id')):hold()
        sha(s['request_sha'])
    elif s['ledger_kind']=='CHILD':
        ident(c['operation_id']);subject=c['operation_id'];sha(c['parent_execution_sha'])
        if c['gid'] is not None or c['token_job_id'] is not None:hold()
        sha(s['request_sha'])
        if s['api']=='ADD' and s['slot']!='ADD':hold()
    else:
        sha(c['token_job_id']);subject=c['token_job_id']
        if any(c[k] is not None for k in ('gid','parent_execution_sha','operation_id')) or s['request_sha'] is not None:hold()
        expected=digest({'token_job_id':c['token_job_id'],
                         'purpose_instance_id':s['slot'],
                         'acquisition_generation':s['ordinal']})
        if s['subject_sha']!=expected:hold('GROUP_FACT_SELECTOR_INVALID')
    if c['qid']!=source_fact_qid(binding_sha=c['binding_sha'],ledger_kind=s['ledger_kind'],
                               subject=subject,api=s['api'],slot=s['slot'],ordinal=s['ordinal']):hold()
    if c['fact_id']!=source_fact_id(c):hold('GROUP_FACT_ID_INVALID')
    return c


def make_source_fact(**fields):
    """Pure construction only. The actual Host must admit the resulting value."""
    c={'schema':1,'profile':PROFILE,'authority':False,**fields}
    c['fact_id']='0'*64
    c['fact_id']=source_fact_id(c)
    validate_source_fact(c)
    return clone(c)


def make_source_fact_v2(**fields):
    """Pure V2 construction; actual Host admission remains mandatory."""
    c={**fields,'schema':2,'profile':PROFILE_V2,'authority':False,'fact_id':'0'*64}
    c['fact_id']=source_fact_id(c)
    validate_source_fact(c)
    return clone(c)


def make_source_fact_operator(**fields):
    """Detached Operator facts; actual current/admission scope still required."""
    c={**fields,'schema':1,'profile':PROFILE_OPERATOR,'authority':False,'fact_id':'0'*64}
    c['fact_id']=source_fact_id(c)
    validate_source_fact(c)
    return clone(c)


def make_source_fact_for_current_in(host,db,context,claim_selector,previous_fact_event_sha=None,*,admission_scope=None, history_locators=None):
    """Single producer selector. Real issued A context/scope remain mandatory.

    Returns facts only. The original producer registers this exact candidate
    with the same actual context before entering the original append hooks.
    """
    from .draft_group_runtime_host import validate_current_context,validate_admission_scope
    from .draft_group_host_review import GroupRuntimeHost
    ctx=validate_current_context(context,db=db)
    if type(host) is not GroupRuntimeHost or ctx.host is not host:hold('GROUP_FACT_ACTUAL_HOST_REQUIRED')
    selector=clone(claim_selector);closed(selector,SELECTOR_KEYS)
    if selector['ledger_kind']=='TOKEN':
        if ctx.token_use is None:hold('GROUP_FACT_TOKEN_USE_REQUIRED')
        actual=getattr(host.entry,'token_use_admissions',{}).get(id(ctx.token_use))
        if actual is None or admission_scope is not None and admission_scope is not actual:
            hold('GROUP_FACT_ADMISSION_SCOPE_REQUIRED')
        admission_scope=actual
    elif admission_scope is None:hold('GROUP_FACT_ADMISSION_SCOPE_REQUIRED')
    scope=validate_admission_scope(admission_scope,db=db, history_locators=history_locators)
    if scope.host is not host or scope.source is not ctx.source:hold('GROUP_FACT_ADMISSION_SCOPE_CHANGED')
    GroupRuntimeHost.current_no_token_in(host,db,ctx.source,token_use=ctx.token_use, history_locators=history_locators)
    info=host._family_in(db, history_locators=history_locators);covenant=info['covenant'];config=host.chain.config;semantic=host.chain.semantic
    registration=host._registration;binding=digest(config['binding']);details=scope.details
    kind=selector['ledger_kind']
    if kind=='TOKEN':
        from .draft_group_token_attempt_store import build_token_job_id
        from .draft_group_operator_semantics import original_root_evidence
        subject=build_token_job_id(semantic['platform_account_sha'],covenant['family_anchor_id'],
                                  original_root_evidence(host)['origin_request_identity_sha'])
        gid=operation=parent=None;job=subject
        purpose=ctx.token_use.use['first_purpose_key']
        expiry=int(ctx.source.not_after*1000)
    else:
        if kind!=details['ledger_kind']:hold('GROUP_FACT_SELECTOR_INVALID')
        subject=details['gid'] if kind=='PREVIEW' else details['operation_id']
        gid=details['gid'];operation=details['operation_id'];job=None
        parent=details['group_input_sha'] if kind=='CHILD' else None
        purpose=details['purpose_key'];expiry=details['qualified_not_after_ms']
    qid=source_fact_qid(binding_sha=binding,ledger_kind=kind,subject=subject,
        api=selector['api'],slot=selector['slot'],ordinal=selector['ordinal'])
    replay=replay_source_facts(_events(db));chain=replay['chains'].get(qid,[])
    previous=chain[-1]['event_sha'] if chain else None
    if previous_fact_event_sha is not None and previous_fact_event_sha!=previous:
        hold('GROUP_FACT_CHAIN_INVALID')
    source=host.chain.source
    from .draft_group_operator_source_codec import SOURCE_PROFILE
    if source.get('profile')==SOURCE_PROFILE:
        from .draft_group_host_operator import binding_for_host,current_binding_facts
        from .draft_group_operator_review import committed_review_sha
        live=binding_for_host(host,'ADMISSION_READY');observed=current_binding_facts(live)
        review=committed_review_sha(host,live)
        if review!=getattr(host,'_current_source_review_sha',None):hold('GROUP_FACT_CURRENT_REVIEW_CHANGED')
        descriptor=host.chain.descriptor(digest(observed))
        expiry=min(expiry,observed['qualified_not_after_ms']);builder=(make_source_fact_operator_v2
            if observed['profile']==time06.OBSERVATION_PROFILE_V2 else make_source_fact_operator)
        generation=observed['proof_generation_sha']
    else:
        descriptor={'configuration_sha':host.pins.configuration_sha,'semantic_adoption_sha':host.pins.semantic_sha,
            'role_tuple_sha':digest(config['role_source_descriptors']),'qa_adoption_sha':digest(semantic['qa_adoptions']),
            'artifact_inventory_sha':digest(semantic['artifact_inventory'])}
    if source.get('profile')=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
        from .draft_group_native_v2_runtime import (binding_for_current_source,current_binding_facts,
                                                  current_binding_observation)
        live=binding_for_current_source(host);witness=current_binding_facts(live)
        observed=current_binding_observation(host,live)
        from .draft_group_source_review import committed_source_review_sha
        review=committed_source_review_sha(host,live)
        if review!=getattr(host,'_current_source_review_sha',None):hold('GROUP_FACT_CURRENT_REVIEW_CHANGED')
        descriptor.update(native_source_profile=source['profile'],native_observation_profile=observed['profile'],
            native_contract_sha256=witness['native_contract_sha'],permission_facts_sha256=witness['permission_facts_sha'],
            runtime_source_policy_sha=witness['runtime_source_policy_sha'],current_binding_sha=digest(witness))
        expiry=min(expiry,witness['qualified_not_after_ms']);builder=make_source_fact_v2
        generation=digest(observed['sources'])
    elif source.get('profile')=='GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1':
        observed=host.observer.inspect(host.chain.files['source'].raw).value
        review=getattr(host,'_current_source_review_sha',None);builder=make_source_fact
        generation=digest(observed['sources'])
    elif source.get('profile')!=SOURCE_PROFILE:hold('GROUP_FACT_SOURCE_PROFILE_REQUIRED')
    return builder(qid=qid,previous_fact_event_sha=previous,binding_sha=binding,
        family_id=covenant['family_anchor_id'],first_proof_sha=info['first']['candidate']['first_proof_sha'],
        registration_sha=registration['registration_sha'],registration_proof_sha=registration['registration_proof_sha'],
        source_material_sha=host.pins.source_sha,current_source_review_sha=review,
        original_scope_sha=covenant['original_scope_sha'],covenant_sha=config['first_covenant_sha'],purpose_key=purpose,
        gid=gid,parent_execution_sha=parent,operation_id=operation,token_job_id=job,claim_selector=selector,
        source_descriptor=descriptor,qualification_generation_sha=generation,
        qualified_not_after_ms=expiry,host_acceptance_sha=host.pins.review_sha,source_observation_sha=digest(observed))


def validate_locator(locator):
    closed(locator,LOCATOR_KEYS)
    for k in ('account_key','event_sha','preview_id','evidence_sha'):sha(locator[k])
    integer(locator['event_seq'],1)
    return locator


def _events(db):
    """Owned caller snapshot; every pool, with event and projection equality."""
    from .own_validation_scope import _transaction_marker
    if _transaction_marker(db) is None:hold('GROUP_TRANSACTION_LIFETIME_UNPROVEN')
    if (db.execute('PRAGMA user_version').fetchone()[0]!=9 or
        db.execute('PRAGMA application_id').fetchone()[0]!=0x57434f31):hold('GROUP_SCHEMA_UNVERIFIED')
    if db.execute('PRAGMA foreign_key_check').fetchone():hold('GROUP_SOURCE_FACT_UNVERIFIED')
    from .draft_group_store import _load
    accounts={row[0] for row in db.execute('SELECT account_key FROM group_pools ORDER BY account_key')}
    for account in sorted(accounts):
        _load(db,account)  # Original full event/checksum/materialization replay.
    out=[]
    for row in db.execute('SELECT account_key,seq,kind,payload,event_sha FROM group_events ORDER BY account_key,seq'):
        if row[0] not in accounts:hold('GROUP_FACT_ORPHAN_EVENT')
        p=json.loads(row[3]);plain(p,maximum=2*1024*1024)
        out.append({'account_key':row[0],'seq':row[1],'kind':row[2],
                    'payload':p,'event_sha':row[4]})
    return out


def replay_source_facts(events):
    """Pure closed-chain replay. It cannot verify file authority or grant writes."""
    chains={};locators={};by_event={};firsts={}
    for e in events:
        p=e['payload']
        if e['kind']!='PREVIEW':continue
        c=p.get('candidate');profile=c.get('profile') if type(c) is dict else None
        if profile=='GROUP_READ_FAMILY_ROOT_V1':
            firsts.setdefault(c['family_anchor_id'],[]).append(e)
        if not is_source_profile(profile):continue
        validate_source_fact(c)
        if (e['account_key']!=c['binding_sha'] or p['binding_sha']!=c['binding_sha']
            or p['preview_id']!=c['fact_id'] or p['request_key']!='gsf-'+c['fact_id']
            or p['input_sha']!=c['source_material_sha'] or p['scope_sha']!=c['original_scope_sha']
            or p['evidence_sha']!=digest(c)):hold('GROUP_FACT_WRAPPER_INVALID')
        q=c['qid'];chain=chains.setdefault(q,[])
        if (len(chain)>=MAX_VERSIONS or c['previous_fact_event_sha'] !=
            (None if not chain else chain[-1]['event_sha'])):hold('GROUP_FACT_CHAIN_INVALID')
        if chain:
            old=chain[-1]['payload']['candidate']
            if PROFILE_OPERATOR_V2 in (old['profile'],c['profile']) and old['profile']!=c['profile']:
                hold('GROUP_FACT_SOURCE_MODE_CHANGED')
            if (old['profile']==PROFILE_OPERATOR)!=(c['profile']==PROFILE_OPERATOR):
                hold('GROUP_FACT_SOURCE_MODE_CHANGED')
            if old['profile']==PROFILE_V2 and c['profile']!=PROFILE_V2:
                hold('GROUP_FACT_VERSION_ROLLBACK')
            # A version cannot create a different original permission, selector,
            # family or registration. Real technical continuation is checked by A.
            for k in ('binding_sha','family_id','first_proof_sha','original_scope_sha',
                      'covenant_sha','purpose_key','gid','parent_execution_sha',
                      'operation_id','token_job_id','claim_selector'):
                if canonical(old[k])!=canonical(c[k]):hold('GROUP_FACT_REBASE_FORBIDDEN')
        loc={'account_key':e['account_key'],'event_seq':e['seq'],'event_sha':e['event_sha'],
             'preview_id':c['fact_id'],'evidence_sha':p['evidence_sha']}
        key=(e['account_key'],e['seq'])
        if key in locators or e['event_sha'] in by_event:hold('GROUP_FACT_DUPLICATE')
        locators[key]={'locator':loc,'candidate':c};by_event[e['event_sha']]=locators[key]
        chain.append(e)
    for item in locators.values():
        c=item['candidate'];roots=firsts.get(c['family_id'],[])
        if len(roots)!=1:hold('GROUP_FACT_FIRST_REQUIRED')
        root=roots[0];rc=root['payload']['candidate']
        if (rc['first_proof_sha']!=c['first_proof_sha'] or rc['covenant_sha']!=c['covenant_sha']
            or root['account_key']==item['locator']['account_key'] and root['seq']>=item['locator']['event_seq']):hold('GROUP_FACT_FIRST_INVALID')
    return {'chains':chains,'locators':locators,'by_event':by_event,'firsts':firsts}


def _history(db,candidate,history_policy):
    from .draft_group_runtime_host import validate_source_fact_history_in
    validate_source_fact_history_in(db,candidate,history_policy)


def check_source_fact_records_in(db,states=None,history_policy=None):
    # No new Owned/policy dependency for old ordinary/Family-only histories.
    rows=db.execute("SELECT payload FROM group_events WHERE kind='PREVIEW'").fetchall()
    if not any(is_source_profile(candidate_profile(json.loads(r[0]))) for r in rows):
        return {'chains':{},'locators':{},'by_event':{},'firsts':{}}
    if history_policy is None:
        from .draft_group_read_family_store import resolve_history_policy
        history_policy=resolve_history_policy(db)
    info=replay_source_facts(_events(db))
    for item in info['locators'].values():_history(db,item['candidate'],history_policy)
    return info


def _locator_in(info,locator):
    validate_locator(locator);item=info['locators'].get((locator['account_key'],locator['event_seq']))
    if item is None or canonical(item['locator'])!=canonical(locator):hold('GROUP_FACT_LOCATOR_INVALID')
    return item


def query_source_fact_in(db,locator,*,history_policy=None):
    info=check_source_fact_records_in(db,history_policy=history_policy)
    return clone(_locator_in(info,locator))


@contextmanager
def _write_scope(db,context,candidate, *, history_locators=None):
    from .draft_group_runtime_host import validate_source_fact_admission
    validate_source_fact_admission(context,db=db,candidate=candidate, history_locators=history_locators)
    from .own_validation_scope import _transaction_marker
    epoch=_transaction_marker(db)
    if epoch is None:hold('GROUP_TRANSACTION_LIFETIME_UNPROVEN')
    record=(db,context,clone(candidate),threading.get_ident(),epoch,[])
    _ISSUED[id(record)]=record;token=_SCOPE.set(record)
    try:yield
    finally:_SCOPE.reset(token);_ISSUED.pop(id(record),None)


def before_event_in(db,account,kind,payload, *, history_locators=None):
    c=payload.get('candidate') if kind=='PREVIEW' else None
    profile=c.get('profile') if type(c) is dict else None
    if not is_source_profile(profile):return
    validate_source_fact(c)
    from .own_validation_scope import _transaction_marker
    scope=_SCOPE.get()
    if (scope is None or _ISSUED.get(id(scope)) is not scope or scope[0] is not db
        or scope[3]!=threading.get_ident() or scope[4]!=_transaction_marker(db)
        or canonical(scope[2])!=canonical(c) or scope[5]):hold('GROUP_FACT_ADMISSION_REQUIRED')
    from .draft_group_runtime_host import validate_source_fact_admission
    validate_source_fact_admission(scope[1],db=db,candidate=c, history_locators=history_locators)
    info=check_source_fact_records_in(db)
    prior=info['chains'].get(c['qid'],[])
    if c['previous_fact_event_sha']!=(None if not prior else prior[-1]['event_sha']):hold('GROUP_FACT_CHAIN_INVALID')
    scope[5].append((account,c['fact_id'],digest(c)))


def after_event_in(db,*,account=None,kind=None,payload=None):
    scope=_SCOPE.get()
    profile=candidate_profile(payload) if kind=='PREVIEW' else None
    if is_source_profile(profile) and scope is None:hold('GROUP_FACT_ADMISSION_REQUIRED')
    if scope is None:
        check_source_fact_records_in(db)
        return
    if _ISSUED.get(id(scope)) is not scope or scope[0] is not db or len(scope[5])!=1:hold()
    info=check_source_fact_records_in(db)
    account,fid,evidence=scope[5][0]
    found=[x for x in info['locators'].values() if x['locator']['account_key']==account and x['locator']['preview_id']==fid]
    if len(found)!=1 or found[0]['locator']['evidence_sha']!=evidence:hold()


def register_source_fact_in(db,group_store,live_context,candidate, *, history_locators=None):
    validate_source_fact(candidate)
    from .draft_group_store import GroupStore
    if type(group_store) is not GroupStore or group_store.binding_sha!=candidate['binding_sha']:hold()
    # Duplicate requests are read-only queries, never new current authority.
    info=check_source_fact_records_in(db)
    old=[x for x in info['locators'].values() if x['candidate']['fact_id']==candidate['fact_id']]
    if old:
        if len(old)!=1 or canonical(old[0]['candidate'])!=canonical(candidate):hold()
        return clone(old[0]['locator'])
    with _write_scope(db,live_context,candidate, history_locators=history_locators):
        group_store.register_preview_in(db,candidate['fact_id'],source_kind=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0],
            input_sha=candidate['source_material_sha'],request_key='gsf-'+candidate['fact_id'],
            scope_sha=candidate['original_scope_sha'],candidate=clone(candidate),evidence_sha=digest(candidate), history_locators=history_locators)
    result=check_source_fact_records_in(db)
    return clone(next(x['locator'] for x in result['locators'].values() if x['candidate']['fact_id']==candidate['fact_id']))


def make_source_fact_operator_v2(**fields):
    """Detached Operator facts; actual current/admission scope still required."""
    c={**fields,'schema':2,'profile':PROFILE_OPERATOR_V2,'authority':False,'fact_id':'0'*64}
    c['fact_id']=source_fact_id(c)
    validate_source_fact(c)
    return clone(c)
