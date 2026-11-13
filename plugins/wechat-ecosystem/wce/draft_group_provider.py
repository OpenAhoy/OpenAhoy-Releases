"""Actual Group committed-continuation provider; no public request parameters.

The host issues source scopes. The original caller SQL commits before this
stack can own one effect. Reopening a claim never recreates that stack owner.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import json,threading,time
from contextlib import contextmanager
from contextvars import ContextVar
from .contracts import WCEError,Secret
from .http_transport import HTTPSender,HTTPRequest
from . import draft_group_wire as wire
from . import draft_group_discovery as discovery
from . import draft_group_store as store
from . import draft_group_response_codec as codec
from .draft_group_response_history import CONTRACT_SHA,locator_from_primary_in
from .draft_group_response_files import GroupResponseFiles,_issue_arrived_pack
from .draft_group_transport import (GroupDeadline,validate_transport_tcb,_prepare_group_transport,
    validate_prepared,_exchange_group_prepared_once,consume_capture,CapturedGroupOutcome,NoQualifiedDisposition)
from .own_validation_scope import OwnedConnection,_transaction_marker

_PREPARED={}
_PENDING={}
_KNOWN={}
_IDENTITIES={}
_USED_BINDINGS={}
_BUSINESS_FACTS={}
_SYN_ADMITTING=ContextVar('fixed_c_syn_admitting_prepared',default=None)
_SYN_WITNESSES={}


def fail():raise WCEError('GROUP_PROVIDER_HOLD')


class PreparedGroupRequest:
    __slots__=('provider','scope','api','slot','selector','request','transport','cached',
        'reference','list_offset','expected_projection','ordinal','subject_sha','child','_pin')
    def __repr__(self):return '<PreparedGroupRequest>'


class PendingAdmission:
    __slots__=('provider','scope','prepared','claim','event','source_locator','normal_commit','readback','thread','row')
    def __repr__(self):return '<PendingGroupAdmission>'


@dataclass(frozen=True,eq=False)
class KnownCommitFacts:
    scope: object=field(repr=False)
    prepared: object=field(repr=False)
    claim_id: str
    admission_event_sha: str
    request_body_sha: str
    source_qualification_locator: dict=field(repr=False)
    normal_commit: bool=True
    identity_json: str=field(default="",repr=False)


def validate_known_commit_pending(pending,scope):
    record=_PENDING.get(id(pending))
    if (record is None or record[0] is not pending or pending.scope is not scope
            or not record[1] or pending.readback!=record[2] or pending.thread!=threading.get_ident()
            or not pending.normal_commit):fail()
    from .draft_group_runtime_host import validate_admission_scope
    validate_admission_scope(scope, history_locators=None)
    facts=_KNOWN.get(id(pending))
    if facts is None:
        facts=KnownCommitFacts(scope,pending.prepared.transport,pending.claim['id'],pending.event['event_sha'],
            sha256(pending.prepared.request.body).hexdigest(),dict(pending.source_locator),
            identity_json=_identity_record(pending).identity_json)
        _KNOWN[id(pending)]=facts
    if facts.identity_json!=_identity_record(pending).identity_json:fail()
    return facts


@dataclass(frozen=True,eq=False)
class _OriginalIdentityFacts:
    pending: object=field(repr=False)
    scope: object=field(repr=False)
    prepared: object=field(repr=False)
    identity_json: str=field(repr=False)
    api: str
    route: str
    source_kind: str
    request_body_sha: str
    syn_stage: str|None=None


def _identity_record(pending):
    record=_IDENTITIES.get(id(pending))
    if (record is None or record.pending is not pending or record.scope is not pending.scope
            or record.prepared is not pending.prepared.transport):fail()
    return record


@dataclass(frozen=True,eq=False)
class _UsedAdmissionBinding:
    owner: object=field(repr=False)
    pending: object=field(repr=False)
    prepared: object=field(repr=False)
    known_facts: object=field(repr=False)
    identity_json: str=field(repr=False)
    syn_stage: str|None=None


def bind_used_group_admission(owner,prepared,transport_facts):
    # The caller has just checked A's real USED-owner registry. This leaf only
    # reads original C registries and primitive immutable snapshots: no current,
    # file, SQL, source/clock callbacks after the last effect-release fence.
    from .draft_group_runtime_host import GroupBusinessOwner
    if type(owner) is not GroupBusinessOwner or not owner.used or not owner.continuation.used:fail()
    pending=owner.continuation.pending
    record=_PENDING.get(id(pending));identity=_identity_record(pending);facts=_KNOWN.get(id(pending))
    if (record is None or record[0] is not pending or record[1] is not True
            or facts is None or owner.continuation.facts is not facts or facts.prepared is not prepared
            or identity.prepared is not prepared or facts.scope is not owner.continuation.scope
            or pending.thread!=threading.get_ident()):fail()
    if (transport_facts.route!=identity.route or transport_facts.request_body_sha!=identity.request_body_sha
            or transport_facts.source_kind!=identity.source_kind or transport_facts.token):fail()
    binding=_UsedAdmissionBinding(owner,pending,prepared,facts,identity.identity_json,identity.syn_stage);_USED_BINDINGS[id(binding)]=binding
    return binding


def validate_bound_group_admission(binding,owner,prepared,pending,primary):
    codec._plain(primary)
    if (type(binding) is not _UsedAdmissionBinding or _USED_BINDINGS.get(id(binding)) is not binding
            or binding.owner is not owner or binding.prepared is not prepared or binding.pending is not pending
            or _KNOWN.get(id(pending)) is not binding.known_facts or _identity_record(pending).identity_json!=binding.identity_json):fail()
    check_primary_identity_value(binding.identity_json,primary)
    return None


def check_primary_identity_value(identity_json,primary):
    """Pure closed data comparison only; no owner/issuer/file qualification."""
    codec._plain(primary)
    actual={key:primary[key] for key in ('binding','account_root_identity_sha','admission','archive_context')}
    if primary['transport']['origin']=='NO_QUALIFIED_RESPONSE':
        if actual['archive_context']['parser_profile']!='NONE':fail()
        actual['archive_context']=dict(actual['archive_context'],parser_profile=codec.PARSERS[actual['admission']['api']])
    if wire.canonical(actual)!=identity_json:fail()
    return None



class OfficialGroupProvider:
    def __init__(self,service,host,gate,*,fixed_contract_pins=None):
        from .own_connection_broker import AccountService
        from .draft_group_runtime_host import GroupExecutionGate
        from .draft_group_host_review import GroupRuntimeHost
        if (type(service) is not AccountService or type(host) is not GroupRuntimeHost
                or type(gate) is not GroupExecutionGate or gate.service is not service or host.entry is not gate):fail()
        if fixed_contract_pins not in (None,CONTRACT_SHA):fail()
        gate.held_pure()
        self.service=service;self.host=host;self.gate=gate;self.workflow=service.workflow
        self.policy=service.policy;self.thread=threading.get_ident()

    def _scope(self,scope,db=None, *, history_locators=None):
        from .draft_group_runtime_host import validate_admission_scope
        validate_admission_scope(scope,db=db, history_locators=history_locators)
        if scope.host is not self.host or scope.entry is not self.gate or self.thread!=threading.get_ident():fail()
        return scope.details

    def _token(self,scope):
        from .draft_group_runtime_host import obtain_group_cached_token
        return obtain_group_cached_token(scope)

    def _profile(self):
        # AccountService activated this exact current delegated profile together
        # with the Group cached lease; there is no synthetic replacement profile.
        profiles=tuple(self.workflow.registry.profiles.values())
        if len(profiles)!=1:fail()
        p=profiles[0]
        if p.binding()!=self.host.chain.config['binding']:fail()
        return p

    def _prepare(self,scope,api,slot,*,selector):
        details=self._scope(scope, history_locators=None)
        cached=self._token(scope)
        if type(cached.token) is not Secret:fail()
        with _history_transaction(self.workflow.db,physical_resources=self.gate) as (db, history_locators):
            self._scope(scope,db, history_locators=history_locators)
            state,_,_=store._load(db,details['account_key'])
            if details['ledger_kind']=='PREVIEW':
                grant=state['preview_grants'][details['gid']]
                claims=[c for c in grant['claims'] if c['api']==api]
                ordinal=len(claims)+1
                if any(c['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED') for c in grant['claims']):fail()
                slot='PREVIEW_'+api+':'+str(ordinal)
                if api=='LIST':
                    # First actual observed total determines both-pass offsets.
                    total=None
                    for old in claims:
                        page=self._read_claim_snapshot_in(db,state,old['id'])
                        if total is None:total=page['total_count']
                        elif total!=page['total_count']:fail()
                    pages=max(1,(total+19)//20) if total is not None else 1
                    if total is not None and ordinal>2*pages:fail()
                    offset=((ordinal-1)%pages)*20
                    request=discovery.encode_list(offset,cached.token);reference=None;expected=None
                    subject=wire.digest({'scope_sha':state['previews'][details['preview_id']]['scope_sha'],'list_ordinal':ordinal,'count':20})
                elif api=='GET':
                    subjects=grant['subjects']
                    if subjects is None or ordinal>len(subjects):fail()
                    subject=subjects[ordinal-1]
                    reference=self._resolve_reference_in(db,scope,subject, history_locators=history_locators)
                    request=wire.encode_get(reference,cached.token,synthetic=state['source_kind']=='SYNTHETIC_SETUP')
                    offset=None;expected=None
                else:fail()
                child=None
            else:
                op=state['operations'][details['operation_id']]
                ordinal=1+len([c for c in op['claims'] if c['kind']==api]);offset=None
                child=self._child_in(db,scope, history_locators=history_locators)
                if api=='ADD':
                    candidate=self._add_candidate(child,state['source_kind']=='SYNTHETIC_SETUP')
                    request=wire.encode_add(candidate,cached.token,synthetic=state['source_kind']=='SYNTHETIC_SETUP')
                    subject=wire.digest({'profile':'GROUP_ADD_TARGET_SUBJECT_V1','operation_id':details['operation_id'],
                        'manifest_sha':child['manifest_sha'],'target_projection_sha':op['pins']['target_projection_sha']})
                    reference=None;expected=None
                else:
                    subject=store._subject(op,slot) if api=='GET' else op['old_refs'][int(slot.split(':')[1])]['ref_sha']
                    reference=self._resolve_reference_in(db,scope,subject, history_locators=history_locators)
                    request=(wire.encode_get if api=='GET' else wire.encode_delete)(reference,cached.token,synthetic=state['source_kind']=='SYNTHETIC_SETUP')
                    from .draft_group_response_history import _expected_projection
                    expected=_expected_projection(op,{'slot':slot,'cursor':op['cursor']}) if api=='GET' else None
        # All callbacks and token validity checks finish before the eventual
        # common pure fence/primitive sample in the Host continuation.
        self.host.current_no_token_in(None,scope.source, history_locators=None)
        if not self.service.tokens.valid(cached):fail()
        now=time.monotonic();wall=time.time()
        deadline=min(self.gate.deadline,now+30,now+cached.wall_deadline-wall,
            now+max(0,details['qualified_not_after_ms']/1000-wall))
        transport=_prepare_group_transport(self.workflow.sender,request,GroupDeadline(deadline,min(10,deadline-now)),
            source_kind=self.host.chain.config['binding']['source_kind'])
        prepared=PreparedGroupRequest()
        for name,value in dict(provider=self,scope=scope,api=api,slot=slot,selector=selector,
                request=request,transport=transport,cached=cached,reference=reference,list_offset=offset,
                expected_projection=expected,ordinal=ordinal,subject_sha=subject,child=child).items():setattr(prepared,name,value)
        prepared._pin=(api,slot,request,transport,cached,reference,offset,expected,ordinal,subject,
            None if child is None else wire.canonical(child))
        _PREPARED[id(prepared)]=prepared
        _BUSINESS_FACTS[id(prepared)]=(prepared,scope,prepared._pin,request.method,request.path,
            wire.canonical(request.headers),request.body,self)
        return prepared

    def prepare_preview_request(self,qualified_read,selector):
        if selector not in ('LIST_NEXT','GET_NEXT'):fail()
        if self._scope(qualified_read, history_locators=None)['ledger_kind']!='PREVIEW':fail()
        return self._prepare(qualified_read,'LIST' if selector=='LIST_NEXT' else 'GET','',selector=selector)

    def prepare_child_request(self,qualified_target,slot):
        if self._scope(qualified_target, history_locators=None)['ledger_kind']!='CHILD' or type(slot) is not str:fail()
        api='ADD' if slot=='ADD' else 'DELETE' if slot.startswith('DELETE:') else 'GET'
        return self._prepare(qualified_target,api,slot,selector=slot)

    def _validate_prepared(self,p):
        if type(p) is not PreparedGroupRequest or _PREPARED.get(id(p)) is not p or p.provider is not self:fail()
        pin=(p.api,p.slot,p.request,p.transport,p.cached,p.reference,p.list_offset,p.expected_projection,p.ordinal,p.subject_sha,
            None if p.child is None else wire.canonical(p.child))
        original=_BUSINESS_FACTS.get(id(p))
        if (original is None or original[0] is not p or original[1] is not p.scope or pin!=original[2]
                or type(p.provider) is not OfficialGroupProvider or p.provider is not original[7]
                or p.request.method!=original[3] or p.request.path!=original[4]
                or wire.canonical(p.request.headers)!=original[5] or p.request.body!=original[6]):fail()
        self._scope(p.scope, history_locators=None);validate_prepared(p.transport)

    def _admit_in(self,db,p, *, history_locators=None):
        self._validate_prepared(p);d=self._scope(p.scope,db, history_locators=history_locators)
        selector={'ledger_kind':d['ledger_kind'],'api':p.api,'slot':p.slot,'ordinal':p.ordinal,
                  'subject_sha':p.subject_sha,'request_sha':sha256(p.request.body).hexdigest()}
        loc=self.host.build_admission_source_fact_in(db,p.scope,selector, history_locators=history_locators)
        # This full fixed verifier is the actual Host; never lambda True.
        journal=store.GroupStore(d['account_key'],_history_partial(self.host.verify_in, history_locators=history_locators))
        at_ms=int(time.time()*1000);epoch=d['source_epoch'];row=None
        if d['ledger_kind']=='PREVIEW':
            claim=journal.claim_preview_read_in(db,d['gid'],d['preview_id'],p.api,
                request_sha=selector['request_sha'],epoch=epoch,at_ms=at_ms, history_locators=history_locators)
        elif p.api=='GET':claim=journal.claim_get_in(db,d['operation_id'],p.slot,epoch=epoch,at_ms=at_ms,request_sha=selector['request_sha'], history_locators=history_locators)
        elif p.api=='DELETE':claim=journal.claim_delete_in(db,d['operation_id'],int(p.slot.split(':')[1]),epoch=epoch,at_ms=at_ms,request_sha=selector['request_sha'], history_locators=history_locators)
        else:
            profile=self._profile();lease=self.workflow.active_lease;child=p.child
            # The sole callback is a fixed local leaf over the original actual
            # OwnWorkflow. It does not commit, network, or publish files.
            def admit(actual):
                a=dict(child['selector'],request_key=self._child_key_in(actual,d['operation_id']))
                from .draft_group_target_approval import authorize_group_add_in
                with authorize_group_add_in(self.host,p.scope,actual,profile,child,prepared=p.transport, history_locators=history_locators) as approval_id:
                    with _syn_admitting_prepared(p,actual,profile,lease):
                        result=self.workflow._admit_step_in(actual,profile,lease,a,add=True,op='add',slot='draft',action='draft.add',selector=child['selector'], history_locators=history_locators)
                        request=result[1]
                        if (result[0]['approval_id']!=approval_id or request is None
                                or request.method!=p.request.method or request.path!=p.request.path
                                or request.headers!=p.request.headers or request.body!=p.request.body):fail()
                # Both actual approval and SYN witness contexts end before the
                # GroupStore receives this row and writes its original link.
                return result
            admission=journal.admit_add_in(db,d['operation_id'],epoch=epoch,at_ms=at_ms,admit_own_step=admit, history_locators=history_locators)
            if admission['cached'] or admission['request'] is None:fail()
            state,_,_=store._load(db,d['account_key']);claim=next(c for c in state['operations'][d['operation_id']]['claims'] if c['id']==admission['claim_id'])
            row=dict(db.execute('SELECT * FROM own_steps WHERE id=?',(admission['step_pin']['id'],)).fetchone())
        if claim['ordinal']!=p.ordinal:fail()
        event=dict(db.execute('SELECT * FROM group_events WHERE account_key=? ORDER BY seq DESC LIMIT 1',(d['account_key'],)).fetchone())
        pending=PendingAdmission();pending.provider=self;pending.scope=p.scope;pending.prepared=p;pending.claim=claim
        pending.event=event;pending.source_locator=loc;pending.normal_commit=False;pending.readback=None;pending.thread=threading.get_ident();pending.row=row
        _PENDING[id(pending)]=(pending,False,None)
        return pending

    def _confirm(self,pending):
        # Called only after the original caller context manager returned normally.
        pending.normal_commit=True
        with _history_transaction(self.workflow.db,physical_resources=self.gate) as (db, history_locators):
            self.host.current_no_token_in(db,pending.scope.source, history_locators=history_locators)
            actual=db.execute('SELECT * FROM group_events WHERE account_key=? AND seq=?',
                (pending.scope.details['account_key'],pending.event['seq'])).fetchone()
            if actual is None or dict(actual)!=pending.event:fail()
            state,_,_=store._load(db,pending.scope.details['account_key'])
            from .draft_group_response_history import _find_claim
            claim=_find_claim(state,pending.claim['id'])[-1]
            if wire.canonical(claim)!=wire.canonical(pending.claim):fail()
            if pending.row is not None:
                row=db.execute('SELECT * FROM own_steps WHERE id=?',(pending.row['id'],)).fetchone()
                if row is None or dict(row)!=pending.row:fail()
            pending.readback=wire.digest({'event':dict(actual),'claim':claim,'row':pending.row})
            from .draft_group_source_facts import query_source_fact_in
            fact=query_source_fact_in(db,pending.source_locator,history_policy=self.policy)['candidate']
            p=pending.prepared;d=pending.scope.details
            selector={'ledger_kind':d['ledger_kind'],'api':p.api,'slot':p.slot,'ordinal':p.ordinal,
                'subject_sha':p.subject_sha,'request_sha':sha256(p.request.body).hexdigest()}
            if (fact['claim_selector']!=selector or fact['family_id']!=d['family_id']
                    or fact['purpose_key']!=d['purpose_key'] or fact['gid']!=d['gid']
                    or fact['operation_id']!=d['operation_id']
                    or (fact['registration_sha'] if d['ledger_kind']=='PREVIEW' else fact['parent_execution_sha'])!=d['group_input_sha']
                    or json.loads(pending.event['payload'])['epoch']!=d['source_epoch']):fail()
            identity=self._original_identity(pending)
            syn_stage=None
            if identity['binding']['source_kind']=='SYNTHETIC_SETUP':
                if d['ledger_kind']=='PREVIEW':
                    family=self.host._family_in(db, history_locators=history_locators)
                    purposes=[x for x in family['covenant']['purposes'] if x['source_grant_sha']==d['purpose_key']]
                    if len(purposes)!=1 or purposes[0]['purpose']!='PREVIEW_ACCOUNT' or p.api!='LIST':fail()
                    syn_stage='PREVIEW_ACCOUNT:LIST:'+str(p.ordinal)
                elif p.api=='ADD' and p.slot=='ADD':syn_stage='CHILD:ADD'
                elif p.api=='GET' and p.slot in ('NEW','FINAL_NEW'):syn_stage='CHILD:GET:'+p.slot
                else:fail()
        api=identity['admission']['api']
        route={'LIST':'/cgi-bin/draft/batchget','GET':'/cgi-bin/draft/get','ADD':'/cgi-bin/draft/add','DELETE':'/cgi-bin/draft/delete'}[api]
        _IDENTITIES[id(pending)]=_OriginalIdentityFacts(pending,pending.scope,pending.prepared.transport,wire.canonical(identity),
            api,route,identity['binding']['source_kind'],identity['admission']['request_sha'],syn_stage)
        _PENDING[id(pending)]=(pending,True,pending.readback)
        from .draft_group_runtime_host import mark_known_commit
        return mark_known_commit(pending.scope,pending)

    def execute_once(self,prepared):
        capture=None
        try:
            self._validate_prepared(prepared)
            with _history_transaction(self.workflow.db, write=True,physical_resources=self.gate) as (db, history_locators):pending=self._admit_in(db,prepared, history_locators=history_locators)
            continuation=self._confirm(pending)
            self.host.current_no_token_in(None,prepared.scope.source, history_locators=None)
            if not self.service.tokens.valid(prepared.cached):fail()
            from .draft_group_runtime_host import issue_business_owner
            owner=issue_business_owner(continuation,prepared.transport)
            owner.consume('BUSINESS',prepared.transport)
            capture=_exchange_group_prepared_once(owner,prepared.transport)
            return self._archive_arrived(pending,capture)
        finally:
            from .draft_group_transport import discard_prepared,forget_archived_arrival
            discard_prepared(prepared.transport)
            if capture is not None:forget_archived_arrival(capture)
            prepared.request=None;prepared.cached=None;prepared._pin=None
            _BUSINESS_FACTS.pop(id(prepared),None);_PREPARED.pop(id(prepared),None)

    def run_preview(self,qualified_read,selector):return self.execute_once(self.prepare_preview_request(qualified_read,selector))
    def run_child(self,qualified_target,slot):return self.execute_once(self.prepare_child_request(qualified_target,slot))

    def _child_in(self,db,scope, *, history_locators=None):
        from .draft_group_input_files import InputFiles
        details=self._scope(scope,db, history_locators=history_locators);files=InputFiles(self.policy,self.gate.full_guard)
        execution=files.read('execution',details['group_input_sha']).value
        if execution['binding']!=self.host.chain.config['binding']:fail()
        matches=[]
        for descriptor in execution['children']:
            e=files.read('child',descriptor['sha256']);value=e.value
            if e.size!=descriptor['size']:fail()
            if value['operation_id']==details['operation_id']:matches.append(value)
        if len(matches)!=1:fail()
        return matches[0]

    def _add_candidate(self,child,synthetic):
        projection=json.loads(child['projection_json'])
        rows=projection['articles'] if type(projection) is dict and set(projection)=={'articles'} else None
        return wire.make_add_candidate(rows,synthetic=synthetic)

    def _child_key_in(self,db,oid):
        state,_,_=store._load(db,self.host.chain.config and wire.digest(self.host.chain.config['binding']))
        return state['operations'][oid]['plan']['child_key']

    def _resolve_reference_in(self,db,scope,subject, *, history_locators=None):
        from .draft_group_runtime_host import resolve_group_reference_in
        # A fixed actual scope/registration source resolver. Constructor strings
        # do not qualify references; the original byte hash is checked again.
        ref=resolve_group_reference_in(db,self.policy,scope,subject, history_locators=history_locators)
        if wire.reference_sha(ref,synthetic=self.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP')!=subject:fail()
        return ref

    def _read_claim_snapshot_in(self,db,state,claim_id):
        from .draft_group_runtime_host import response_history_context_in
        from .draft_group_response_history import load_original_locator_in
        files=GroupResponseFiles.from_history_context(self.policy,response_history_context_in(db,self.policy))
        # Offset of the first pass is known; derive later offsets from earlier
        # completed page total, never assume ten pages for a cap of twenty.
        found=next(g for g in state['preview_grants'].values() if any(c['id']==claim_id for c in g['claims']))
        claims=[c for c in found['claims'] if c['api']=='LIST'];first=claims[0]
        firstloc=load_original_locator_in(files,db,state,first['id'],list_offset=0)
        firstprimary=files.read_primary(firstloc);firstsnapshot=files.read_snapshot(firstloc,firstprimary)
        if firstsnapshot is None:fail()
        total=json.loads(firstsnapshot.raw)['total_count'];pages=max(1,(total+19)//20)
        claim=next(c for c in claims if c['id']==claim_id)
        loc=load_original_locator_in(files,db,state,claim_id,list_offset=((claim['ordinal']-1)%pages)*20)
        snapshot=files.read_snapshot(loc,files.read_primary(loc))
        if snapshot is None:fail()
        return json.loads(snapshot.raw)

    def _original_identity(self,pending):
        p=pending.prepared;d=pending.scope.details
        return {'binding':json.loads(wire.canonical(self.host.chain.config['binding'])),
            'account_root_identity_sha':wire.digest({'device':self.policy.root_pin[0],'inode':self.policy.root_pin[1]}),
            'admission':{'ledger_kind':d['ledger_kind'],'family_id':d['family_id'],'purpose_key':d['purpose_key'],
                'gid':d['gid'],'operation_id':d['operation_id'],'claim_id':pending.claim['id'],'api':p.api,
                'slot':p.slot,'ordinal':p.ordinal,'subject_sha':p.subject_sha,'request_sha':sha256(p.request.body).hexdigest(),
                'admission_event_sha':pending.event['event_sha'],
                'admission_payload_sha':wire.digest(json.loads(pending.event['payload'])),
                'own_step_pin':None if pending.row is None else {k:pending.row[k] for k in store._PIN_FIELDS}},
            'archive_context':{'contract_sha':CONTRACT_SHA,'parser_profile':codec.PARSERS[p.api],
                'group_input_sha':d['group_input_sha'],'source_qualification_sha':pending.source_locator['evidence_sha'],
                'source_qualification_locator':dict(pending.source_locator),'source_epoch':d['source_epoch']}}

    def _archive_arrived(self,pending,arrived):
        p=pending.prepared;d=pending.scope.details
        # Only transport-issued values can enter the response archive. Token
        # captures use another registry/type and never enter these roles.
        if type(arrived) is CapturedGroupOutcome:
            arrived=consume_capture(arrived);response=arrived.response
            completed=arrived.completed_at_ms;origin=arrived.transport_origin
        elif type(arrived) is NoQualifiedDisposition:
            from .draft_group_transport import consume_disposition
            consume_disposition(arrived);response=None;completed=None;origin='NO_QUALIFIED_RESPONSE'
        else:fail()
        classified=codec.classify_response(p.api,d['ledger_kind'],p.slot,response,p.cached.token,
            claim_at_ms=pending.claim['at_ms'],completed_at_ms=completed,reference=p.reference,
            list_offset=p.list_offset,expected_projection_sha=p.expected_projection,
            synthetic=self.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP')
        identity=json.loads(_identity_record(pending).identity_json)
        admission=identity['admission']
        primary={'schema':1,'profile':codec.PROFILE,
            'provenance':'SYNTHETIC_GROUP_WIRE' if identity['binding']['source_kind']=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_GROUP_WIRE',
            **identity,'transport':{'origin':origin,'endpoint':codec.ENDPOINTS[p.api],
                'request_body_sha':admission['request_sha'],'http_status':None if response is None else response.status,
                'response_body_sha':None if response is None else sha256(response.body).hexdigest()},
            'observation':classified.observation}
        if response is None:
            primary['archive_context']=dict(primary['archive_context'],parser_profile='NONE')
        raw=codec.encode_primary(primary,claim_at_ms=pending.claim['at_ms'],expected_projection_sha=p.expected_projection)
        from .draft_group_runtime_host import response_history_context_in
        with self.workflow.db.transaction() as db:
            state,_,_=store._load(db,d['account_key'])
            locator=locator_from_primary_in(db,state,pending.claim['id'],raw,self.policy,
                reference=p.reference,list_offset=p.list_offset)
            context=response_history_context_in(db,self.policy)
        files=GroupResponseFiles.from_history_context(self.policy,context);files.initialize()
        pack=_issue_arrived_pack(locator,primary,classified.snapshot,arrived,p.transport,pending)
        from .draft_group_transport import forget_archived_arrival
        forget_archived_arrival(arrived)
        # Only the safe deterministic proposal survives any later file/SQL
        # failure. Neither raw response nor the token-bearing Request does.
        arrived=None;response=None;p.cached=None;p.request=None;p._pin=None
        files.publish_snapshot(pack);primary_evidence=files.publish_primary(pack)
        own=None
        if p.api=='ADD' and classified.observation['outcome']=='KNOWN_SUCCESS':
            from .own_group_response_archive import publish_group_ownproof
            profile=self._profile()
            own=publish_group_ownproof(self.workflow,profile,pending.row,primary_evidence,files)
        # A fixed historical verifier validates exactly this archived result,
        # and cannot be used for any claim, budget, source or next effect.
        verifier=ArchivedResultVerifier(files,locator,primary_evidence,context)
        with _history_transaction(self.workflow.db, write=True,physical_resources=self.gate) as (db, history_locators):
            journal=store.GroupStore(d['account_key'],verifier)
            obs=primary['observation']
            current_state,_,_=store._load(db,d['account_key'])
            from .draft_group_response_history import _find_claim
            actual=_find_claim(current_state,pending.claim['id'])[-1]
            if actual['proof_sha'] is not None:
                if p.api=='ADD' and obs['outcome']=='KNOWN_SUCCESS':
                    if own is None:fail()
                    from .own_group_response_archive import reconcile_group_add_in
                    reconcile_group_add_in(db,self.workflow,self._profile(),pending.row,primary_evidence,own[0],own[1],files=files, history_locators=history_locators)
                elif actual['proof_sha']!=primary_evidence.sha256 or actual['outcome']!=obs['outcome']:fail()
            elif d['ledger_kind']=='PREVIEW':
                journal.observe_preview_read_in(db,d['gid'],pending.claim['id'],outcome=obs['outcome'],proof_sha=primary_evidence.sha256, history_locators=history_locators)
            elif p.api=='GET':
                journal.observe_get_in(db,d['operation_id'],pending.claim['id'],outcome=obs['outcome'],
                    proof_sha=primary_evidence.sha256,snapshot_sha=obs['projection_sha'],code=obs['code'],at_ms=obs['observed_at_ms'], history_locators=history_locators)
            elif p.api=='DELETE':
                journal.observe_delete_in(db,d['operation_id'],pending.claim['id'],outcome=obs['outcome'],proof_sha=primary_evidence.sha256,code=obs['code'], history_locators=history_locators)
            elif obs['outcome']=='KNOWN_SUCCESS':
                from .own_group_response_archive import reconcile_group_add_in
                reconcile_group_add_in(db,self.workflow,self._profile(),pending.row,primary_evidence,own[0],own[1],files=files, history_locators=history_locators)
            else:journal.add_unknown_in(db,d['operation_id'],proof_sha=primary_evidence.sha256, history_locators=history_locators)
            files.collective_fence()
        # Independent original-ID readback. No token, network or new claim.
        with self.workflow.db.transaction() as db:
            state,_,_=store._load(db,d['account_key']);actual=_find_claim(state,pending.claim['id'])[-1]
            if actual['proof_sha'] is None:fail()
            files.read_primary(locator,expected_proof_sha=primary_evidence.sha256)
            files.read_snapshot(locator,primary_evidence);files.collective_fence()
        try:self.host.current_no_token_in(None,pending.scope.source, history_locators=None)
        except Exception:release='CURRENT_RELEASE_UNAVAILABLE'
        else:release='CURRENT_RELEASE_AVAILABLE'
        _PREPARED.pop(id(p),None);_PENDING.pop(id(pending),None);_KNOWN.pop(id(pending),None);_IDENTITIES.pop(id(pending),None)
        return {'state':'ARCHIVED','claim_id':pending.claim['id'],'outcome':primary['observation']['outcome'],
            'proof_sha':primary_evidence.sha256,'release':release,'authority':False}


    def reconcile_original(self,locator):
        """Original-ID local recovery: no token/API/new claim or owner."""
        from .draft_group_response_files import _validate_locator
        from .draft_group_runtime_host import response_history_context_in
        _validate_locator(locator)
        with self.workflow.db.transaction() as db:
            context=response_history_context_in(db,self.policy)
        files=GroupResponseFiles.from_history_context(self.policy,context)
        evidence=files.read_primary(locator);snapshot=files.read_snapshot(locator,evidence)
        files.redurable_original(locator,evidence,snapshot)
        primary=evidence.value;a=primary['admission'];o=primary['observation']
        own=None;row=None
        if a['api']=='ADD' and o['outcome']=='KNOWN_SUCCESS':
            with self.workflow.db.transaction() as db:
                actual=db.execute('SELECT * FROM own_steps WHERE id=?',(a['own_step_pin']['id'],)).fetchone()
                if actual is None or {k:actual[k] for k in store._PIN_FIELDS}!=a['own_step_pin']:fail()
                row=dict(actual)
            from .own_group_response_archive import publish_group_ownproof
            own=publish_group_ownproof(self.workflow,self._profile(),row,evidence,files)
        verifier=ArchivedResultVerifier(files,locator,evidence,context)
        with _history_transaction(self.workflow.db, write=True,physical_resources=self.gate) as (db, history_locators):
            state,_,_=store._load(db,locator.account_key)
            from .draft_group_response_history import _find_claim
            claim=_find_claim(state,locator.claim_id)[-1]
            if own is not None:
                from .own_group_response_archive import reconcile_group_add_in
                reconcile_group_add_in(db,self.workflow,self._profile(),row,evidence,own[0],own[1],files=files, history_locators=history_locators)
            elif claim['proof_sha'] is not None:
                if claim['proof_sha']!=evidence.sha256 or claim['outcome']!=o['outcome']:fail()
            else:
                journal=store.GroupStore(locator.account_key,verifier)
                if a['ledger_kind']=='PREVIEW':journal.observe_preview_read_in(db,a['gid'],locator.claim_id,outcome=o['outcome'],proof_sha=evidence.sha256, history_locators=history_locators)
                elif a['api']=='GET':journal.observe_get_in(db,a['operation_id'],locator.claim_id,outcome=o['outcome'],proof_sha=evidence.sha256,snapshot_sha=o['projection_sha'],code=o['code'],at_ms=o['observed_at_ms'], history_locators=history_locators)
                elif a['api']=='DELETE':journal.observe_delete_in(db,a['operation_id'],locator.claim_id,outcome=o['outcome'],proof_sha=evidence.sha256,code=o['code'], history_locators=history_locators)
                else:journal.add_unknown_in(db,a['operation_id'],proof_sha=evidence.sha256, history_locators=history_locators)
            files.collective_fence()
        with self.workflow.db.transaction() as db:
            state,_,_=store._load(db,locator.account_key);claim=_find_claim(state,locator.claim_id)[-1]
            if claim['proof_sha'] is None:fail()
            files.read_primary(locator,expected_proof_sha=evidence.sha256);files.collective_fence()
        return {'state':'ARCHIVED','claim_id':locator.claim_id,'outcome':o['outcome'],'proof_sha':evidence.sha256,'authority':False}


class ArchivedResultVerifier:
    """Exact original-result-only historical verifier, never a generic True."""
    __slots__=('files','locator','evidence','context')
    def __init__(self,files,locator,evidence,context):
        self.files=files;self.locator=locator;self.evidence=evidence;self.context=context
    def __call__(self,db,action,binding_sha,details):
        from .draft_group_runtime_host import validate_history_context
        validate_history_context(self.files.policy,self.context,db=db)
        if binding_sha!=self.locator.account_key:fail()
        observed=self.files.read_primary(self.locator,expected_proof_sha=self.evidence.sha256)
        self.files.read_snapshot(self.locator,observed)
        if observed.raw!=self.evidence.raw:fail()
        primary=observed.value;a=primary['admission'];o=primary['observation']
        if a['ledger_kind']=='PREVIEW':
            expected={'grant_id':a['gid'],'claim_id':self.locator.claim_id,'outcome':o['outcome'],'proof_sha':self.evidence.sha256};kind='PREVIEW_READ_RESULT'
        elif a['api']=='GET':
            expected={'operation_id':a['operation_id'],'claim_id':self.locator.claim_id,'outcome':o['outcome'],
                'proof_sha':self.evidence.sha256,'snapshot_sha':o['projection_sha'],'code':o['code'],'at_ms':o['observed_at_ms']};kind='GET_RESULT'
        elif a['api']=='DELETE':
            expected={'operation_id':a['operation_id'],'claim_id':self.locator.claim_id,'outcome':o['outcome'],
                'proof_sha':self.evidence.sha256,'code':o['code']};kind='DELETE_RESULT'
        elif a['api']=='ADD' and o['outcome']!='KNOWN_SUCCESS':
            expected={'operation_id':a['operation_id'],'proof_sha':self.evidence.sha256};kind='ADD_UNKNOWN'
        else:fail()
        if action!=kind or wire.canonical(details)!=wire.canonical(expected):fail()
        state,_,_=store._load(db,binding_sha)
        from .draft_group_response_history import _find_claim
        claim=_find_claim(state,self.locator.claim_id)[-1]
        if claim['state']!='CONSUMED_UNKNOWN' or claim['proof_sha'] is not None:fail()
        self.files.collective_fence()
        return True


@dataclass(frozen=True,slots=True)
class _SYNAdmissionWitness:
    prepared: object=field(repr=False)
    db: object=field(repr=False)
    epoch: object=field(repr=False)
    thread: int
    workflow: object=field(repr=False)
    profile: object=field(repr=False)
    lease: object=field(repr=False)
    profile_fence: str=field(repr=False)
    manifest_json: str=field(repr=False)
    approval_id: str=field(repr=False)
    approval_digest: str=field(repr=False)


def _witness_for_workflow(workflow):
    witness=_SYN_ADMITTING.get()
    if (type(witness) is not _SYNAdmissionWitness or _SYN_WITNESSES.get(id(witness)) is not witness
            or witness.workflow is not workflow or witness.thread!=threading.get_ident()
            or type(witness.db) is not OwnedConnection or _transaction_marker(witness.db)!=witness.epoch):fail()
    p=witness.prepared;d=p.scope.details
    if store._ADMITTING.get()!=(id(witness.db),d['account_key'],d['operation_id']):fail()
    return witness


def current_syn_admitting_database(workflow):
    return _witness_for_workflow(workflow).db


def validate_syn_admitting_prepared_in(workflow,db,profile,lease,action,*,write,read_attempt):
    witness=_witness_for_workflow(workflow);p=witness.prepared
    if (witness.db is not db or witness.profile is not profile or witness.lease is not lease
            or action!='draft.add' or write is not True or read_attempt is not False
            or profile.source_kind!='SYNTHETIC_SETUP' or profile.fence()!=witness.profile_fence
            or workflow.active_lease is not lease or workflow.active_token is not p.cached
            or lease.token is not p.cached.token or p.api!='ADD' or p.slot!='ADD'
            or p.scope.details['ledger_kind']!='CHILD' or p.provider.workflow is not workflow):fail()
    OfficialGroupProvider._validate_prepared(p.provider,p)
    from .draft_group_transport import validate_syn_prepared_transport_in
    facts=validate_syn_prepared_transport_in(p.transport,p.provider.gate)
    if facts.request_body_sha!=sha256(p.request.body).hexdigest():fail()
    manifest=json.loads(witness.manifest_json)
    from .draft_group_target_scope import validate_target_approval_in,GroupApprovalScope,_APPROVAL_ISSUED
    scopes=[s for s in _APPROVAL_ISSUED.values() if type(s) is GroupApprovalScope and s.scope is p.scope
        and s.db is db and s.workflow is workflow and s.profile is profile and wire.canonical(s.manifest)==wire.canonical(manifest)]
    if len(scopes)!=1:fail()
    validate_target_approval_in(workflow,db,profile,manifest)
    approval=workflow._approval(db,profile,manifest,p.child['manifest_sha'])
    if approval['id']!=witness.approval_id or approval['body_digest']!=witness.approval_digest:fail()
    return None


@contextmanager
def _syn_admitting_prepared(p,db,profile,lease):
    if profile.source_kind!='SYNTHETIC_SETUP':
        yield
        return
    if _SYN_ADMITTING.get() is not None:fail()
    OfficialGroupProvider._validate_prepared(p.provider,p)
    if (type(db) is not OwnedConnection or _transaction_marker(db) is None
            or p.api!='ADD' or p.slot!='ADD' or p.scope.details['ledger_kind']!='CHILD'
            or store._ADMITTING.get()!=(id(db),p.scope.details['account_key'],p.scope.details['operation_id'])):fail()
    workflow=p.provider.workflow;manifest=json.loads(p.child['manifest_json'])
    from .draft_group_target_scope import validate_target_approval_in,GroupApprovalScope,_APPROVAL_ISSUED
    scopes=[s for s in _APPROVAL_ISSUED.values() if type(s) is GroupApprovalScope and s.scope is p.scope
        and s.db is db and s.workflow is workflow and s.profile is profile and wire.canonical(s.manifest)==wire.canonical(manifest)]
    if len(scopes)!=1:fail()
    validate_target_approval_in(workflow,db,profile,manifest)
    approval=workflow._approval(db,profile,manifest,p.child['manifest_sha'])
    witness=_SYNAdmissionWitness(p,db,_transaction_marker(db),threading.get_ident(),workflow,profile,lease,
        profile.fence(),wire.canonical(manifest),approval['id'],approval['body_digest'])
    _SYN_WITNESSES[id(witness)]=witness;token=_SYN_ADMITTING.set(witness)
    try:
        validate_syn_admitting_prepared_in(workflow,db,profile,lease,'draft.add',write=True,read_attempt=False)
        yield
    finally:_SYN_ADMITTING.reset(token);_SYN_WITNESSES.pop(id(witness),None)


from .draft_group_history_context import history_transaction as _history_transaction


from functools import partial as _history_partial
