"""Group-only four-stage acquisition with durable attempts and last primitive fence.

Ordinary get/acquire/load remain unchanged. Token bodies and their hashes are
never persisted. Only original current-stack known commits issue effect owners.
"""
from contextlib import contextmanager
from dataclasses import dataclass,field
from hashlib import sha256
import ctypes
import json
import math
import threading
import time
import weakref
from .draft_group_operator_semantics import original_root_evidence
from .contracts import Secret,WCEError
from .draft_group_runtime_host import (need,hold,canonical,digest,_THREAD,_TIME,_MONOTONIC,_method,
    _REGISTRY,_HISTORY_ISSUED,QualifiedGroupSource,TokenUseScope,validate_admission_scope,
    response_history_context_in,_validate_admission_scope_and_current,_validate_admission_scope_identity_in)
from .own_connection_token import TokenCache,CachedToken,ContinuousClock,token_lock
from .own_bootstrap_security import acquire_pending,_token_request,_token_response,decode,CheckedTokenRejected
from .own_keychain import KeychainCredential,NativeKeychain,credential_scope
from . import own_keychain as _KEYCHAIN_MODULE

_CONTROLLERS={};_OWNERS={};_CONTINUATIONS={}
_OWNER_FACTS={};_OWNER_USED=set()
_CACHE_GET=TokenCache.get;_CACHE_VALID=TokenCache.valid;_CACHE_ACQUIRE=TokenCache._acquire_current
_CLOCK_CALL=ContinuousClock.__call__;_SECRET_REVEAL=Secret.reveal_for_adapter
_KEYCHAIN_LOAD=NativeKeychain.load;_CREDENTIAL_LOAD=KeychainCredential.load;_CREDENTIAL_CHECK=KeychainCredential._check
_CREDENTIAL_SCOPE=credential_scope;_TOKEN_REQUEST=_token_request;_TOKEN_RESPONSE=_token_response
_GROUP_KEYCHAIN_TCB=_KEYCHAIN_MODULE._group_read_tcb_original;_GROUP_KEYCHAIN_TCB_CODE=_GROUP_KEYCHAIN_TCB.__code__


_CLOCK_FACTS=weakref.WeakKeyDictionary()
_CLOCK_DLL=ctypes.CDLL;_CLOCK_GETITEM=ctypes.CDLL.__getitem__;_CLOCK_CAST=ctypes.cast
_CLOCK_CLASS_IMAGE=(ContinuousClock.__bases__,ContinuousClock.__mro__,tuple((name,value,getattr(value,'__code__',None)) for name,value in vars(ContinuousClock).items()))


@dataclass(frozen=True,slots=True)
class _ClockFacts:
    library:object=field(repr=False)
    function:object=field(repr=False)
    address:int
    flags:int
    scale:float
    function_class:tuple=field(repr=False)
    trusted:object=field(repr=False)


_CLOCK_FACTS_CLASS_IMAGE=(_ClockFacts.__bases__,_ClockFacts.__mro__,tuple((name,value,getattr(value,'__code__',None)) for name,value in vars(_ClockFacts).items()))


def _clock_class_original():
    for cls,image in ((ContinuousClock,_CLOCK_CLASS_IMAGE),(_ClockFacts,_CLOCK_FACTS_CLASS_IMAGE)):
        bases,mro,items=image;attrs=type.__getattribute__(cls,'__dict__')
        need(type.__getattribute__(cls,'__bases__')==bases and type.__getattribute__(cls,'__mro__')==mro
             and tuple(attrs)==tuple(name for name,_,_ in items),'GROUP_CLOCK_TCB')
        need(all(attrs[name] is value and (code is None or value.__code__ is code) for name,value,code in items),'GROUP_CLOCK_TCB')


def _prepare_continuous_clock(clock):
    import sys
    need(all(globals().get(name) is fn and fn.__code__ is code for name,fn,code in _CLOCK_HELPER_PINS),'GROUP_CLOCK_TCB')
    _GROUP_KEYCHAIN_TCB();_clock_class_original()
    need(type(clock) is ContinuousClock and ContinuousClock.__call__ is _CLOCK_CALL,'GROUP_CLOCK_TCB')
    if sys.platform!='darwin':
        need(hasattr(time,'CLOCK_BOOTTIME'),'GROUP_CLOCK_TCB');return
    from .own_keychain import _group_function_class_pin
    need(type(clock.lib) is _CLOCK_DLL and clock.lib._name=='/usr/lib/libSystem.B.dylib','GROUP_CLOCK_TCB')
    fn=clock.lib.mach_continuous_time;function_class=_group_function_class_pin(fn)
    trusted=_CLOCK_DLL('/usr/lib/libSystem.B.dylib');symbol=_CLOCK_GETITEM(trusted,'mach_continuous_time')
    need(_CLOCK_CAST(fn,ctypes.c_void_p).value==_CLOCK_CAST(symbol,ctypes.c_void_p).value
         and fn.restype is ctypes.c_uint64 and fn.argtypes is None and getattr(fn,'errcheck',None) is None
         and fn._flags_==symbol._flags_,'GROUP_CLOCK_TCB')
    class Timebase(ctypes.Structure):_fields_=[('numer',ctypes.c_uint32),('denom',ctypes.c_uint32)]
    value=Timebase();timebase=_CLOCK_GETITEM(trusted,'mach_timebase_info')
    timebase.argtypes=[ctypes.POINTER(Timebase)];timebase.restype=ctypes.c_int
    need(timebase(ctypes.byref(value))==0 and value.denom>0,'GROUP_CLOCK_TCB')
    scale=value.numer/value.denom/1e9
    need(type(clock.scale) is float and clock.scale==scale and 0<scale<1,'GROUP_CLOCK_TCB')
    _CLOCK_FACTS[clock]=_ClockFacts(clock.lib,fn,_CLOCK_CAST(fn,ctypes.c_void_p).value,fn._flags_,scale,function_class,trusted)


def _clock_pure_facts(clock):
    need(all(globals().get(name) is fn and fn.__code__ is code for name,fn,code in _CLOCK_HELPER_PINS),'GROUP_CLOCK_TCB')
    _GROUP_KEYCHAIN_TCB();_clock_class_original()
    import sys
    if sys.platform!='darwin':
        need(type(clock) is ContinuousClock and hasattr(time,'CLOCK_BOOTTIME'),'GROUP_CLOCK_TCB');return None
    from .own_keychain import _validate_group_function_class_pin
    need(type(clock) is ContinuousClock,'GROUP_CLOCK_TCB');f=_CLOCK_FACTS.get(clock)
    need(f is not None,'GROUP_CLOCK_UNPREPARED');_validate_group_function_class_pin(f.function_class)
    fn=f.function
    need(clock.lib is f.library and clock.lib._name=='/usr/lib/libSystem.B.dylib'
         and clock.lib.mach_continuous_time is fn and type(clock.scale) is float and clock.scale==f.scale
         and fn.restype is ctypes.c_uint64 and fn.argtypes is None and getattr(fn,'errcheck',None) is None
         and fn._flags_==f.flags and _CLOCK_CAST(fn,ctypes.c_void_p).value==f.address,'GROUP_CLOCK_TCB')
    return f


def _continuous_primitive(clock):
    import sys
    need(all(globals().get(name) is fn and fn.__code__ is code for name,fn,code in _CLOCK_HELPER_PINS),'GROUP_CLOCK_TCB')
    if sys.platform=='darwin':
        f=_clock_pure_facts(clock)
        return f.function()*f.scale
    need(type(clock) is ContinuousClock and ContinuousClock.__call__ is _CLOCK_CALL
         and hasattr(time,'CLOCK_BOOTTIME'),'GROUP_CLOCK_TCB')
    return time.clock_gettime(time.CLOCK_BOOTTIME)


_CLOCK_HELPER_PINS=tuple((fn.__name__,fn,fn.__code__)for fn in (
    _clock_class_original,_prepare_continuous_clock,_clock_pure_facts,_continuous_primitive))


def _token_pure_valid(cache,value,margin):
    need(type(cache) is TokenCache and type(value) is CachedToken and type(value.token) is Secret,'GROUP_TOKEN_CACHE_TCB')
    need(cache.wall is _TIME and type(cache.continuous) is ContinuousClock and time.time is _TIME and time.monotonic is _MONOTONIC,'GROUP_CLOCK_TCB')
    now,elapsed=_TIME(),_continuous_primitive(cache.continuous)
    numbers=(value.wall_start,value.continuous_start,value.wall_deadline,value.continuous_deadline)
    need(all(type(x) in (int,float) and math.isfinite(x) for x in numbers),'GROUP_TOKEN_TIME_INVALID')
    ttl=value.wall_deadline-value.wall_start
    need(0<ttl<=7200.1 and abs(ttl-(value.continuous_deadline-value.continuous_start))<.000001
         and now>=value.wall_start and elapsed>=value.continuous_start and now+margin<value.wall_deadline
         and elapsed+margin<value.continuous_deadline and abs((now-value.wall_start)-(elapsed-value.continuous_start))<5,'GROUP_TOKEN_EXPIRED')
    return now,elapsed


@dataclass(eq=False)
class GroupEffectOwner:
    controller: object=field(repr=False)
    stage: str
    prepared: object=field(repr=False)
    thread: int
    used: bool=False
    def consume(self,stage,prepared):
        need(_validate_owner is _OWNER_VALIDATE and _OWNER_VALIDATE.__code__ is _OWNER_VALIDATE_CODE,'GROUP_EFFECT_OWNER_TCB')
        _OWNER_VALIDATE(self,stage,prepared,used=False)
        _OWNER_USED.add(id(self));self.used=True
        return self


@dataclass(frozen=True,slots=True)
class _EffectOwnerFacts:
    owner:object=field(repr=False)
    controller:object=field(repr=False)
    entry:object=field(repr=False)
    source:object=field(repr=False)
    token_use:object=field(repr=False)
    cache:object=field(repr=False)
    stage:str
    prepared:object=field(repr=False)
    thread:int


def _validate_owner(owner,stage,prepared,*,used):
    if any(globals().get(name) is not fn or fn.__code__ is not code for name,fn,code in _OWNER_HELPER_PINS):
        raise WCEError('GROUP_EFFECT_OWNER_TCB')
    # Class/helper images are checked before reading a replaceable object's
    # attributes. Authority comes from the original private issue record.
    _owner_tcb_original()
    f=_OWNER_FACTS.get(id(owner))
    need(type(owner) is GroupEffectOwner and type(f) is _EffectOwnerFacts and f.owner is owner
         and _OWNERS.get(id(owner)) is owner and f.thread==_THREAD() and f.stage==stage and f.prepared is prepared
         and (id(owner) in _OWNER_USED) is used,'GROUP_EFFECT_OWNER_REQUIRED')
    controller=f.controller;entry=f.entry
    need(owner.controller is controller and owner.stage==f.stage and owner.prepared is f.prepared
         and owner.thread==f.thread and owner.used is used,'GROUP_EFFECT_OWNER_CHANGED')
    need(_CONTROLLERS.get(id(controller)) is controller and controller.entry is entry
         and controller.source is f.source and controller.use is f.token_use and controller.cache is f.cache
         and not entry.closed and _REGISTRY.get(entry.id) is entry,'GROUP_EFFECT_OWNER_ENTRY')
    return owner


def _owner_tcb_original():
    need(all(globals().get(name) is fn and fn.__code__ is code for name,fn,code in _OWNER_HELPER_PINS),'GROUP_EFFECT_OWNER_TCB')
    for cls,bases,mro,items in _OWNER_CLASS_PINS:
        attrs=type.__getattribute__(cls,'__dict__')
        need(type.__getattribute__(cls,'__bases__')==bases and type.__getattribute__(cls,'__mro__')==mro
             and tuple(attrs)==tuple(name for name,_,_ in items),'GROUP_EFFECT_OWNER_TCB')
        need(all(attrs[name] is value and (code is None or value.__code__ is code) for name,value,code in items),'GROUP_EFFECT_OWNER_TCB')


def _secret_read_owner_for(controller):
    found=[f.owner for f in _OWNER_FACTS.values() if f.controller is controller and f.stage=='SECRET_READ'
           and f.prepared is None and id(f.owner) in _OWNER_USED]
    need(len(found)==1,'GROUP_EFFECT_OWNER_REQUIRED')
    return _validate_owner(found[0],'SECRET_READ',None,used=True)


def _validate_used_owner(owner,prepared):
    return _validate_owner(owner,'TOKEN_POST',prepared,used=True)


@dataclass(frozen=True,eq=False)
class HistoricalTokenReceipt:
    stage: str


def qualify_token_use(host,source,admission_scope,db, *, history_locators=None):
    scope,current=_validate_admission_scope_and_current(admission_scope,db=db, history_locators=history_locators)
    need(scope.host is host and scope.source is source,'GROUP_TOKEN_USE_SCOPE')
    host.validate_original_uploads_in(db,current, history_locators=history_locators)
    details=scope.details;info=host._family_in(db, history_locators=history_locators)
    if details['ledger_kind']=='PREVIEW':
        kind='READ_PURPOSE';operation=None;phase=host._group_state_in(db)['preview_grants'][details['gid']]['registration']['phase']
        instance=details['purpose_key'];grant=details['gid']
    else:
        kind='CHILD_EXECUTION';operation=details['operation_id'];phase=host._group_state_in(db)['operations'][operation]['state']
        instance=details['purpose_key'];grant=details['group_input_sha']
    use={'kind':kind,'purpose_instance_id':instance,'first_purpose_key':details['purpose_key'],
        'operation_id':operation,'phase':phase,'grant_or_parent_sha':grant}
    from .draft_group_token_attempt_store import validate_use
    validate_use(use)
    value=TokenUseScope(source,info['covenant']['family_anchor_id'],host._registration['registration_sha'],instance,phase,use)
    host.entry.issued[id(value)]=value
    if not hasattr(host.entry,'token_use_admissions'):host.entry.token_use_admissions={}
    host.entry.token_use_admissions[id(value)]=scope
    return value


class GroupTokenAcquisitionController:
    def __init__(self,host,source,token_use):
        need(type(source) is QualifiedGroupSource and type(token_use) is TokenUseScope
             and source.host is host and host.entry.issued.get(id(source)) is source
             and host.entry.issued.get(id(token_use)) is token_use and token_use.source is source,'GROUP_TOKEN_CONTROLLER_SOURCE')
        need(not host.entry.pre_storage and host.entry.listener_bound,'GROUP_COMPLETE_LISTENER_REQUIRED')
        self.host,self.source,self.use=host,source,token_use;self.entry=host.entry;self.cache=host.entry.service.tokens
        self.admission_scope=host.entry.token_use_admissions[id(token_use)];self.prepared_stage=None;self.prepared=None
        self.claim_event=self.arm_event=None;self.candidate=None;self.value=None;self._secret_used=False;self._post_used=False
        self.transport_shell=None
        _prepare_continuous_clock(self.cache.continuous)
        self._clock_refs=self._clock_snapshot();_CONTROLLERS[id(self)]=self
        _CONTINUATIONS[id(self)]={'controller':self,'host':host,'entry':self.entry,'source':source,'use':token_use,'cache':self.cache,
            'admission_scope':self.admission_scope,'thread':_THREAD(),'claim':None,'arm':None,'prepared_stage':None,'parsed_value':None,'outcome':None}
        self._validate_tcb()
    def _clock_snapshot(self):
        c=self.cache.continuous
        return (c,getattr(c,'lib',None),getattr(c,'scale',None),getattr(getattr(c,'lib',None),'mach_continuous_time',None))
    def _validate_tcb(self):
        _owner_tcb_original()
        _GROUP_KEYCHAIN_TCB();_clock_class_original()
        cache=self.cache;self.entry.held_pure()
        _clock_pure_facts(cache.continuous)
        need(type(cache) is TokenCache and cache is self.entry.service.tokens and cache.policy is self.entry.policy
             and cache.acquire is acquire_pending and cache.wall is _TIME and type(cache.continuous) is ContinuousClock
             and _method(cache,TokenCache,'get') and _method(cache,TokenCache,'valid') and _method(cache,TokenCache,'_acquire_current')
             and TokenCache.get is _CACHE_GET and TokenCache.valid is _CACHE_VALID and TokenCache._acquire_current is _CACHE_ACQUIRE
             and Secret.reveal_for_adapter is _SECRET_REVEAL and self._clock_snapshot()==self._clock_refs,'GROUP_TOKEN_TCB_UNAVAILABLE')
        need(cache.credential is None or type(cache.credential) is KeychainCredential,'GROUP_TOKEN_CREDENTIAL_TCB')
        need(NativeKeychain.load is _KEYCHAIN_LOAD and KeychainCredential.load is _CREDENTIAL_LOAD
             and KeychainCredential._check is _CREDENTIAL_CHECK
             and _KEYCHAIN_MODULE._group_read_tcb_original is _GROUP_KEYCHAIN_TCB
             and _GROUP_KEYCHAIN_TCB.__code__ is _GROUP_KEYCHAIN_TCB_CODE,'GROUP_TOKEN_CREDENTIAL_TCB')
        _GROUP_KEYCHAIN_TCB()
        return None
    @contextmanager
    def _family_transaction(self,write=False,*,historical=False):
        store=self.entry.service.workflow.db
        with _history_transaction(store, write=write,physical_resources=self.entry) as (db, history_locators):
            from .draft_group_read_family_store import FamilyFiles,original_root_scope,family_scope
            files=FamilyFiles(self.entry.policy,self.entry.loop_guard if not historical else lambda:self._historical_guard())
            with original_root_scope(db,files,original_root_evidence(self.host),source_kind=self.host.chain.config['binding']['source_kind'], history_locators=history_locators) as closure:
                with family_scope(db,files,closure):
                    yield db,closure
    @contextmanager
    def _transaction(self,write=False,*,historical=False):
        with self._family_transaction(write=write,historical=historical) as (db,closure):
            if not historical:self.host.current_no_token_in(db,self.source,token_use=self.use, history_locators=closure.history_locators)
            yield db,closure
    def _historical_guard(self):
        from .draft_group_read_family_store import _history_file_guard
        return _history_file_guard(self.entry.policy)
    def query(self):
        from .draft_group_token_attempt_store import build_token_job_id,query_token_attempt_in
        original=original_root_evidence(self.host)
        self.job_id=build_token_job_id(self.host.chain.semantic['platform_account_sha'],self.use.family_id,original['origin_request_identity_sha'])
        with self._transaction() as (db,closure):
            return query_token_attempt_in(db,response_history_context_in(db,self.entry.policy),closure,self.job_id)
    def prepare_current_no_token(self,stage):
        state=_stage_continuation(self)
        need(stage in ('CACHED_RETURN','SECRET_READ','TOKEN_POST','CACHE_PUBLISH'),'GROUP_TOKEN_STAGE')
        self._validate_tcb()
        with self._family_transaction() as (db,closure):
            _validate_admission_scope_identity_in(self.admission_scope,db)
            self.admission_scope.host._validate_scope_details_in(db,self.admission_scope.details, history_locators=closure.history_locators)
            _check_stage_preconditions(self,stage,state)
            self.host.current_no_token_in(db,self.source,token_use=self.use, history_locators=closure.history_locators)
        if self.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP':
            from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
            from .draft_group_rich_syn_keychain import validate_native_domain_full
            validate_native_domain_full(require_rich_syn_domain_for_entry(self.entry))
        _check_stage_preconditions(self,stage,state)
        self.host.observer.prepare_release(self.host.chain.files['source'].raw)
        self.prepared_stage=stage;state['prepared_stage']=stage
    def pure_release_and_issue(self,stage,prepared=None):
        if any(globals().get(name) is not fn or fn.__code__ is not code for name,fn,code in _OWNER_HELPER_PINS):
            raise WCEError('GROUP_EFFECT_OWNER_TCB')
        state=_stage_continuation(self)
        need(self.prepared_stage==state['prepared_stage']==stage,'GROUP_TOKEN_RELEASE_NOT_PREPARED');self._validate_tcb()
        _check_stage_preconditions(self,stage,state)
        if prepared is not None:
            from .draft_group_transport import validate_prepared
            validate_prepared(prepared)
        self.host.pure_release_fence()
        if stage=='SECRET_READ':
            from .own_keychain import _validate_group_read_pure
            from .draft_group_transport import validate_token_transport_shell
            validate_token_transport_shell(self.transport_shell)
            _validate_group_read_pure(self.prepared_credential)
        # No replaceable callback follows the collective native/file fence.
        need(time.time is _TIME and time.monotonic is _MONOTONIC and self._clock_snapshot()==self._clock_refs,'GROUP_CLOCK_TCB')
        now,mono=_TIME(),_MONOTONIC();elapsed=_continuous_primitive(self.cache.continuous)
        need(now<self.source.not_after and mono<self.entry.deadline,'GROUP_TOKEN_SOURCE_EXPIRED')
        if stage=='CACHED_RETURN':_token_pure_valid(self.cache,self.cache.cached,30)
        if stage=='CACHE_PUBLISH':_token_pure_valid(self.cache,self.value,30)
        if prepared is not None:need(mono<prepared.deadline.deadline,'GROUP_TOKEN_POST_DEADLINE')
        owner=GroupEffectOwner(self,stage,prepared,_THREAD());_OWNERS[id(owner)]=owner
        _OWNER_FACTS[id(owner)]=_EffectOwnerFacts(owner,self,self.entry,self.source,self.use,self.cache,stage,prepared,_THREAD())
        self.prepared_stage=None;state['prepared_stage']=None
        return owner
    def _issue_candidate(self,db,candidate, *, history_locators=None):
        context=self.host.current_context_in(db,self.source,token_use=self.use, history_locators=history_locators)
        if not hasattr(self.entry,'token_candidates'):self.entry.token_candidates={}
        self.entry.token_candidates[digest(candidate)]=(context,canonical(candidate))
        return context
    def _source_fact(self,db,generation, *, history_locators=None):
        from .draft_group_source_facts import make_source_fact_for_current_in,register_source_fact_in
        from .draft_group_store import GroupStore
        selector={'ledger_kind':'TOKEN','api':'STABLE_TOKEN','slot':self.use.purpose_instance_id,'ordinal':generation,
            'subject_sha':digest({'token_job_id':self.job_id,'purpose_instance_id':self.use.purpose_instance_id,'acquisition_generation':generation}),'request_sha':None}
        ctx=self.host.current_context_in(db,self.source,token_use=self.use, history_locators=history_locators)
        candidate=make_source_fact_for_current_in(self.host,db,ctx,selector,admission_scope=self.admission_scope, history_locators=history_locators)
        need(candidate['token_job_id']==self.job_id,'GROUP_FACT_TOKEN_JOB_CHANGED')
        if not hasattr(self.entry,'source_candidates'):self.entry.source_candidates={}
        self.entry.source_candidates[digest(candidate)]=(ctx,canonical(candidate))
        return register_source_fact_in(db,GroupStore(candidate['binding_sha'],_history_partial(self.host.verify_in, history_locators=history_locators)),ctx,candidate, history_locators=history_locators)
    def _append_stage(self,candidate):
        state=_stage_continuation(self)
        from .draft_group_store import GroupStore
        from .draft_group_token_attempt_store import CLAIM,ARM,claim_token_acquisition_in,arm_token_post_in
        with self._transaction(write=True) as (db,closure):
            from .draft_group_token_attempt_store import check_token_records_in
            existing=check_token_records_in(db)['attempts'].get(candidate['attempt_id'])
            stage_key='claim' if candidate['profile']==CLAIM else 'arm'
            need(existing is None or existing[stage_key] is None,'GROUP_TOKEN_STAGE_ALREADY_EXISTS')
            ctx=self._issue_candidate(db,candidate, history_locators=closure.history_locators);store=GroupStore(candidate['pins']['binding_sha'],_history_partial(self.host.verify_in, history_locators=closure.history_locators))
            if candidate['profile']==CLAIM:event=claim_token_acquisition_in(db,store,ctx,candidate['reason'],candidate['use'],candidate=candidate, history_locators=closure.history_locators)
            else:event=arm_token_post_in(db,store,ctx,candidate['attempt_id'],candidate=candidate, history_locators=closure.history_locators)
        # The original normal commit and a fresh Owned transaction are both
        # required; a duplicate query in a later process cannot enter here.
        with self._transaction() as (db,closure):
            from .draft_group_token_attempt_store import query_token_attempt_in
            result=query_token_attempt_in(db,response_history_context_in(db,self.entry.policy),closure,self.job_id)
            match=next((x for x in result['attempts'] if x['attempt_id']==candidate['attempt_id']),None)
            key='claim' if candidate['profile']==CLAIM else 'arm'
            need(match is not None and match[key]['event_sha']==event['event_sha'] and canonical(match[key]['payload']['candidate'])==canonical(candidate),'GROUP_TOKEN_COMMIT_UNVERIFIED')
        # Only this original append stack, after normal commit and its fresh
        # Owned readback, records a continuation. Safe/query return data cannot.
        _stage_continuation(self)
        state[key]=(event['event_sha'],canonical(candidate),event)
        if key=='claim':self.claim_event=event
        else:self.arm_event=event
        return event
    def _receipt_write(self,candidate,cache=False):
        from .draft_group_store import GroupStore
        from .draft_group_token_attempt_store import observe_token_outcome_in,observe_token_cache_publish_in
        receipt=HistoricalTokenReceipt(candidate['profile'])
        with self._transaction(write=True,historical=True) as (db,closure):
            _HISTORY_ISSUED[id(receipt)]=(receipt,db,_THREAD(),canonical(candidate))
            try:
                fn=observe_token_cache_publish_in if cache else observe_token_outcome_in
                event=fn(db,GroupStore(candidate['pins']['binding_sha'],_history_partial(self.host.verify_in, history_locators=closure.history_locators)),receipt,history_locators=closure.history_locators)
            finally:_HISTORY_ISSUED.pop(id(receipt),None)
        if not cache and candidate.get('outcome')=='KNOWN_SUCCESS':
            with self._transaction(historical=True) as (db,closure):
                from .draft_group_token_attempt_store import query_token_attempt_in
                result=query_token_attempt_in(db,response_history_context_in(db,self.entry.policy),closure,self.job_id)
                match=next((x for x in result['attempts'] if x['attempt_id']==candidate['attempt_id']),None)
                need(match is not None and match['outcome']['event_sha']==event['event_sha']
                     and canonical(match['outcome']['payload']['candidate'])==canonical(candidate),'GROUP_TOKEN_COMMIT_UNVERIFIED')
            _stage_continuation(self)['outcome']=(event['event_sha'],canonical(candidate))
        return event
    def _get(self):
        from .draft_group_token_attempt_store import (CLAIM,ARM,OUTCOME,CACHE,build_attempt_id,validate_successor_conditions)
        from .draft_group_source_facts import query_source_fact_in
        from .draft_group_transport import (prepare_token_transport_shell,fill_token_request,
            _exchange_group_prepared_once,consume_token_capture)
        self._validate_tcb();cache=self.cache
        with cache.lock:
            history=self.query()  # UNKNOWN blocks before cache, Keychain or POST.
            latest=history['latest']
            if latest is not None:need(latest['state']=='KNOWN_SUCCESS','GROUP_TOKEN_RESULT_UNKNOWN')
            if cache.valid(margin=30):
                self.prepare_current_no_token('CACHED_RETURN');self.pure_release_and_issue('CACHED_RETURN').consume('CACHED_RETURN',None)
                return cache.cached
            cache.cached=None
            with token_lock(self.entry.policy.root) as lock_check:
                lock_check();self.entry.full_guard();history=self.query();latest=history['latest']
                now,cont=_TIME(),_continuous_primitive(cache.continuous)
                reason='INITIAL';loss=None;owner_sha=None
                if latest is not None:
                    t=latest['outcome']['payload']['candidate']['time_facts']
                    if now>=t['wall_deadline']-30 or cont>=t['continuous_deadline']-30:reason='TIME_RENEWAL'
                    else:
                        reason='KNOWN_SUCCESS_CACHE_LOSS_RECOVERY';loss='PARSED_SUCCESS_NOT_PUBLISHED' if latest['cache'] is None else 'PUBLISHED_CACHE_LOST'
                        owner_sha=None if latest['cache'] is None else latest['cache']['payload']['candidate']['cache_owner_binding_sha']
                successor=validate_successor_conditions(history,reason,self.use.use,wall_now=now,continuous_now=cont,cache_available=False,cache_loss_kind=loss,cache_owner_binding_sha=owner_sha)
                with self._transaction(write=True) as (db,closure):locator=self._source_fact(db,successor['generation'], history_locators=closure.history_locators)
                with self._transaction() as (db,closure):
                    query_source_fact_in(db,locator);family=self.host._family_in(db, history_locators=closure.history_locators)
                    from .draft_group_source_facts import _events
                    first=[e for e in _events(db) if e['kind']=='PREVIEW' and e['payload']['candidate'].get('profile')=='GROUP_READ_FAMILY_ROOT_V1' and e['payload']['candidate']['family_anchor_id']==self.use.family_id]
                    need(len(first)==1,'GROUP_TOKEN_FIRST_REQUIRED');first_event=first[0]
                candidate={'schema':1,'profile':CLAIM,'authority':False,'token_job_id':self.job_id,
                    'attempt_id':build_attempt_id(self.job_id,successor['generation'],successor['previous_outcome_event_sha']),
                    'generation':successor['generation'],'previous_outcome_event_sha':successor['previous_outcome_event_sha'],'family_anchor_id':self.use.family_id,
                    'original_scope_sha':family['covenant']['original_scope_sha'],'first_event_sha':first_event['event_sha'],'reason':reason,'recovery':successor['recovery'],'use':self.use.use,
                    'pins':{'binding_sha':digest(self.host.chain.config['binding']),'policy_identity_sha':digest(self.entry.policy.data),'source_material_sha':self.host.pins.source_sha,
                        'source_qualification_locator':locator,'source_qualification_evidence_sha':locator['evidence_sha'],'registration_sha':self.host._registration['registration_sha'],
                        'helper_acceptance_sha':self.host.pins.review_sha,'candidate_scope':self.host.chain.config['candidate_scope']},
                    'admission':{'id':'group-admission-'+os_random(),'claim_event_sha':None,'post_arm_event_sha':None}}
                self.claim_event=self._append_stage(candidate);self.candidate=candidate
                # Fixed HTTP/SSL TCB is prepared before any Secret OS call.
                sender=self.entry.service.workflow.sender
                self.transport_shell=prepare_token_transport_shell(sender,self.host.chain.config['binding']['source_kind'],self.entry.deadline)
                if self.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP':
                    from .draft_group_rich_syn_keychain import new_rich_syn_credential,require_rich_syn_credential
                    credential=cache.credential or new_rich_syn_credential(self)
                    require_rich_syn_credential(self,credential)
                else:credential=cache.credential or KeychainCredential(self.entry.policy)
                _GROUP_KEYCHAIN_TCB()
                need(type(credential) is KeychainCredential and credential.config is self.entry.policy
                     and type(credential.backend) is NativeKeychain
                     and _method(credential,KeychainCredential,'_prepare_group_read'),'GROUP_TOKEN_CREDENTIAL_TCB')
                with credential._prepare_group_read(self) as prepared_read:
                    self.prepare_current_no_token('SECRET_READ');_GROUP_KEYCHAIN_TCB()
                    _KEYCHAIN_MODULE._validate_group_read_pure(prepared_read)
                    self.pure_release_and_issue('SECRET_READ',None).consume('SECRET_READ',None)
                    self._secret_used=True;secret=prepared_read.read_once()
                need(type(secret) is Secret,'GROUP_TOKEN_SECRET_REQUIRED');credential._check()
                request=_TOKEN_REQUEST(self.entry.policy.data['appid'],_SECRET_REVEAL(secret))
                prepared=fill_token_request(self.transport_shell,request)
                armed=json.loads(canonical(candidate));armed['profile']=ARM;armed['prepared_transport_policy']='SYNTHETIC_GROUP_TOKEN_V1' if self.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP' else 'OFFICIAL_GROUP_TOKEN_PREPARED_TLS_V1'
                armed['admission']['claim_event_sha']=_stage_continuation(self)['claim'][0]
                self.arm_event=self._append_stage(armed);self.candidate=armed
                try:
                    self.prepare_current_no_token('TOKEN_POST')
                    # SDK/cache starts are adjacent to the final pure fence,
                    # after ARM commit/readback and every full source callback.
                    before_wall,before_cont=_TIME(),_continuous_primitive(cache.continuous);start_mono=_MONOTONIC()
                    owner=self.pure_release_and_issue('TOKEN_POST',prepared)
                    owner.consume('TOKEN_POST',prepared);self._post_used=True
                    capture=_exchange_group_prepared_once(owner,prepared);response=consume_token_capture(capture)
                    token,deadline,_=_TOKEN_RESPONSE(response,_SECRET_REVEAL(secret),_TIME,7200,True,before_wall,start_mono)
                    ttl=deadline-before_wall;value=CachedToken(token,before_wall,before_cont,deadline,before_cont+ttl)
                    _token_pure_valid(cache,value,30);self.value=value
                    _stage_continuation(self)['parsed_value']=value
                    outcome='KNOWN_SUCCESS';wechat=None;status=response.status
                except BaseException as error:
                    outcome='UNKNOWN';wechat=None;status=None;value=None
                    if type(error) is CheckedTokenRejected:
                        data=decode(response.body)
                        code=data.get('errcode') if type(data) is dict else None
                        if type(code) is int and -(2**31)<=code<2**31 and code!=0:outcome='KNOWN_REJECTED';wechat=code;status=response.status
                    failure=error
                finally:secret=None;request=None
                out=json.loads(canonical(armed));out['profile']=OUTCOME;out.pop('prepared_transport_policy');out['admission']['post_arm_event_sha']=_stage_continuation(self)['arm'][0]
                out.update(outcome=outcome,transport=armed['prepared_transport_policy'] if outcome!='UNKNOWN' else 'NO_QUALIFIED_RESPONSE',
                    framing_policy='STRICT_GROUP_HTTP_FRAMING_V1' if outcome!='UNKNOWN' else 'NO_COMPLETE_FRAMING',http_status=status,wechat_errcode=wechat,
                    time_facts=None if value is None else {'wall_start':value.wall_start,'continuous_start':value.continuous_start,'wall_deadline':value.wall_deadline,
                        'continuous_deadline':value.continuous_deadline,'margin_seconds':30},cache_observation='NOT_CONFIRMED')
                outcome_event=self._receipt_write(out)
                if outcome!='KNOWN_SUCCESS':raise WCEError('GROUP_TOKEN_RESULT_UNKNOWN' if outcome=='UNKNOWN' else 'GROUP_TOKEN_KNOWN_REJECTED') from None
                self.prepare_current_no_token('CACHE_PUBLISH');self.pure_release_and_issue('CACHE_PUBLISH').consume('CACHE_PUBLISH',None)
                cache.cached,cache.error=value,None
                published=json.loads(canonical(armed));published['profile']=CACHE;published.pop('prepared_transport_policy');published['admission']['post_arm_event_sha']=_stage_continuation(self)['arm'][0]
                published.update(outcome_event_sha=outcome_event['event_sha'],cache_observation='PUBLISHED_IN_ORIGINAL_PROCESS',
                    cache_owner_binding_sha=digest({'runtime':self.entry.broker.runtime,'pid':__import__('os').getpid()}))
                try:self._receipt_write(published,cache=True)
                except BaseException:
                    cache.cached=None;raise
                return value



def _stage_continuation(controller):
    state=_CONTINUATIONS.get(id(controller))
    need(type(controller) is GroupTokenAcquisitionController and state is not None and state['controller'] is controller
         and _CONTROLLERS.get(id(controller)) is controller and state['thread']==_THREAD()
         and controller.host is state['host'] and controller.entry is state['entry'] and controller.source is state['source']
         and controller.use is state['use'] and controller.cache is state['cache'] and controller.admission_scope is state['admission_scope'],
         'GROUP_TOKEN_CONTINUATION_REQUIRED')
    return state


def _check_stage_preconditions(controller,stage,state):
    need(_stage_continuation(controller) is state,'GROUP_TOKEN_CONTINUATION_REQUIRED')
    secret_used=any(f.controller is controller and f.stage=='SECRET_READ' and id(f.owner) in _OWNER_USED for f in _OWNER_FACTS.values())
    post_used=any(f.controller is controller and f.stage=='TOKEN_POST' and id(f.owner) in _OWNER_USED for f in _OWNER_FACTS.values())
    if stage=='SECRET_READ':
        need(state['claim'] is not None and controller.claim_event is state['claim'][2] and not secret_used,'GROUP_TOKEN_CLAIM_REQUIRED')
    elif stage=='TOKEN_POST':
        need(state['arm'] is not None and controller.arm_event is state['arm'][2] and secret_used and not post_used,'GROUP_TOKEN_ARM_REQUIRED')
    elif stage=='CACHE_PUBLISH':
        need(state['arm'] is not None and state['outcome'] is not None and state['parsed_value'] is not None
             and controller.value is state['parsed_value'] and post_used,'GROUP_TOKEN_RESULT_REQUIRED')


def os_random():
    import os
    return os.urandom(24).hex()


def get_for_group(cache,controller):
    need(type(controller) is GroupTokenAcquisitionController and _CONTROLLERS.get(id(controller)) is controller
         and controller.cache is cache and type(cache) is TokenCache,'GROUP_TOKEN_CONTROLLER_REQUIRED')
    if controller.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP':
        # LOCAL readiness is source evidence, not an effect-domain permit.
        # Reject before even a Token sourcefact/CLAIM transaction is created.
        from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
        require_rich_syn_domain_for_entry(controller.entry)
    try:
        # Missing original source mappings fail before transport construction,
        # cache release and durable Token CLAIM, preserving the original job.
        with _history_transaction(controller.entry.service.workflow.db,physical_resources=controller.entry) as (db, history_locators):
            controller.host.current_no_token_in(db,controller.source,token_use=controller.use, history_locators=history_locators)
        return controller._get()
    finally:
        if controller.transport_shell is not None:
            from .draft_group_transport import discard_token_transport_shell
            discard_token_transport_shell(controller.transport_shell)
            controller.transport_shell=None


def obtain_group_cached_token(host,scope):
    from .draft_group_runtime_host import obtain_group_cached_token as get
    need(scope.host is host,'GROUP_TOKEN_SCOPE_HOST')
    return get(scope)


_OWNER_CLASS_PINS=tuple((cls,cls.__bases__,cls.__mro__,tuple((name,value,getattr(value,'__code__',None))
    for name,value in vars(cls).items())) for cls in (GroupEffectOwner,_EffectOwnerFacts,GroupTokenAcquisitionController))
_OWNER_HELPER_PINS=tuple((fn.__name__,fn,fn.__code__) for fn in (_validate_owner,_secret_read_owner_for,_owner_tcb_original,_stage_continuation,_check_stage_preconditions,_validate_admission_scope_identity_in,need,canonical))
_OWNER_VALIDATE=_validate_owner;_OWNER_VALIDATE_CODE=_validate_owner.__code__


from .draft_group_history_context import history_transaction as _history_transaction


from functools import partial as _history_partial
