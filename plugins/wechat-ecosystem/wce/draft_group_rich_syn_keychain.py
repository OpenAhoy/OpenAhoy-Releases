"""Issued C1 native backend: real CF/query/decoder, two public SYN effects.

No system Security library is loaded. Only the previously compiled exact C
shim is eligible; a CDLL/CFunc/caller backend alone never qualifies.
"""
from contextlib import contextmanager
from dataclasses import dataclass,field
from hashlib import sha256
import ctypes as c,threading,weakref
from .contracts import WCEError

_STATES={};_STATE_FACTS={};_STATE_QUERIES={};_BACKENDS=weakref.WeakKeyDictionary()
_CONSTANTS=('kSecClass','kSecClassGenericPassword','kSecAttrService','kSecAttrAccount','kSecMatchSearchList','kSecMatchLimit','kSecMatchLimitOne','kSecReturnData')
_CONSTANT_TEXT=('SYN-C1-Class','SYN-C1-GenericPassword','SYN-C1-Service','SYN-C1-Account','SYN-C1-SearchList','SYN-C1-MatchLimit','SYN-C1-LimitOne','SYN-C1-ReturnData')
_THREAD=threading.get_ident


def hold():raise WCEError('GROUP_RICH_SYN_KEYCHAIN_HOLD')


def need(value):
    if value is not True:hold()


@dataclass(eq=False,slots=True)
class _NativeState:
    domain:object=field(repr=False)
    thread:int
    generation:int
    scope:str=field(repr=False)
    cf:object=field(repr=False)
    lib:object=field(repr=False)
    binary:object=field(repr=False)
    functions:tuple=field(repr=False)
    constants:tuple=field(repr=False)
    active_queries:int=0
    closed:bool=False


def _function(lib,name,result,args):
    from .own_keychain import _GROUP_DLL_GETITEM,_GROUP_CAST,_GROUP_CFUNC,_GROUP_CFUNC_CALL,_group_function_class_pin
    fn=_GROUP_DLL_GETITEM(lib,name);fn.restype=result;fn.argtypes=list(args)
    need(isinstance(fn,_GROUP_CFUNC) and type(fn).__call__ is _GROUP_CFUNC_CALL and getattr(fn,'errcheck',None) is None)
    return (fn,_GROUP_CAST(fn,c.c_void_p).value,result,args,fn._flags_,_group_function_class_pin(fn))


def _function_check(pin):
    from .own_keychain import _GROUP_CAST,_validate_group_function_class_pin
    fn,address,result,args,flags,cls=pin;_validate_group_function_class_pin(cls)
    need(_GROUP_CAST(fn,c.c_void_p).value==address and fn.restype is result
         and type(fn.argtypes) in (list,tuple) and tuple(fn.argtypes)==args
         and getattr(fn,'errcheck',None) is None and fn._flags_==flags)
    return fn


def _state(domain):
    assert_rich_syn_keychain_tcb()
    state=_STATES.get(id(domain));f=_STATE_FACTS.get(id(domain))
    need(type(state) is _NativeState and f is not None and f[0] is state and f[1]() is domain
         and state.domain is f[1] and state.thread==f[2]==_THREAD() and state.generation==f[3]
         and type(state.scope)is str and state.scope==f[4] and state.cf is f[5] and state.lib is f[6]
         and state.binary is f[7] and state.functions is f[8] and state.constants is f[9]
         and state.active_queries==_STATE_QUERIES.get(id(domain)) and state.closed is False)
    return state


def validate_native_domain_pure(domain):
    # Issued original identities/ABI only. No file or Path operation, dlsym,
    # CF/native invocation or clock follows the last primitive fence.
    state=_state(domain)
    from .own_keychain import _group_ctypes_original
    _group_ctypes_original()
    for _,pin in state.functions:_function_check(pin)
    return None


def validate_native_domain_full(domain):
    validate_native_domain_pure(domain);state=_state(domain);state.binary.check()
    values=dict(state.functions)
    need(_function_check(values['SYNGetState'])()==3 and _function_check(values['SYNGetGeneration'])()==state.generation)
    for name,pointer,_ in state.constants:need(c.c_void_p.in_dll(state.lib,name).value==pointer)
    return None


def prepare_rich_syn_keychain(domain):
    from .draft_group_rich_syn_fixture import _record,validate_rich_syn_domain,require_rich_syn_full_resources
    require_rich_syn_full_resources(domain)
    from .draft_group_runtime_host import PinnedFile
    from .own_keychain import NativeKeychain,credential_scope,_group_read_tcb_original
    r=_record(domain);facts=validate_rich_syn_domain(domain)
    need(facts.phase=='PREPARING' and r.entry is not None and not r.entry.pre_storage and id(domain) not in _STATES)
    _group_read_tcb_original()
    binary=PinnedFile(r.shim_path,r.shim_sha,16*1024*1024)
    cf=c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation');lib=c.CDLL(str(r.shim_path));binary.check()
    backend=object.__new__(NativeKeychain);backend.cf=cf;backend.sec=lib
    NativeKeychain._configure_functions(backend)
    signatures=(('SYNInitializeConstants',c.c_int32,()),('SYNBindScope',c.c_int32,(c.c_void_p,c.c_int64)),
        ('SYNGetGeneration',c.c_uint64,()),('SYNGetState',c.c_uint32,()),('SYNGetCounter',c.c_uint64,(c.c_uint32,)),
        ('SYNDisposeConstants',c.c_int32,()))
    functions=tuple((name,_function(lib,name,result,args))for name,result,args in signatures)
    f=dict(functions);need(_function_check(f['SYNGetState'])()==0)
    initialized=False
    try:
        need(_function_check(f['SYNInitializeConstants'])()==0);initialized=True
        scope=credential_scope(r.policy);buf=c.create_string_buffer(scope.encode('ascii'))
        need(_function_check(f['SYNBindScope'])(buf,64)==0)
        string_type=_function(cf,'CFStringGetTypeID',c.c_ulong,());string_length=_function(cf,'CFStringGetLength',c.c_long,(c.c_void_p,))
        string_read=_function(cf,'CFStringGetCString',c.c_bool,(c.c_void_p,c.c_void_p,c.c_long,c.c_uint32))
        constants=[]
        for name,expected in zip(_CONSTANTS,_CONSTANT_TEXT,strict=True):
            value=c.c_void_p.in_dll(lib,name).value;need(type(value) is int and value>0)
            need(backend.cf.CFGetTypeID(value)==_function_check(string_type)())
            length=_function_check(string_length)(value);need(type(length) is int and 0<length<128)
            raw=c.create_string_buffer(128);need(_function_check(string_read)(value,raw,128,0x08000100) is True and raw.value.decode('ascii')==expected)
            constants.append((name,value,expected))
        generation=_function_check(f['SYNGetGeneration'])();need(type(generation) is int and generation==1)
        state=_NativeState(weakref.ref(domain),_THREAD(),generation,scope,cf,lib,binary,functions,tuple(constants))
        _STATES[id(domain)]=state
        _STATE_FACTS[id(domain)]=(state,state.domain,state.thread,state.generation,state.scope,state.cf,state.lib,state.binary,state.functions,state.constants)
        _STATE_QUERIES[id(domain)]=0;validate_native_domain_full(domain)
    except BaseException:
        if initialized:
            # BUSY leaves the live library and original pin retained as failure
            # evidence. Never clear constants or unload through an active read.
            code=_function_check(f['SYNDisposeConstants'])()
            if code!=0:
                _STATES[id(domain)]=_NativeState(weakref.ref(domain),_THREAD(),1,'',cf,lib,binary,functions,())
                raise WCEError('GROUP_RICH_SYN_CF_DISPOSE_BUSY')
        binary.close();raise


def new_rich_syn_credential(controller):
    from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
    from .own_keychain import (NativeKeychain,KeychainCredential,_GroupBackendFacts,_GROUP_CF_ABI,_GROUP_SEC_ABI,
        _GROUP_DLL_GETITEM,_GROUP_CAST,_group_function_class_pin,_group_read_tcb_original)
    from .draft_group_token_runtime import GroupTokenAcquisitionController,_CONTROLLERS
    need(type(controller) is GroupTokenAcquisitionController and _CONTROLLERS.get(id(controller)) is controller)
    domain=require_rich_syn_domain_for_entry(controller.entry);state=_state(domain);validate_native_domain_pure(domain);_group_read_tcb_original()
    backend=object.__new__(NativeKeychain);backend.cf=state.cf;backend.sec=state.lib
    records=[];classes=[]
    # Functions configured by the original continuous Native ABI leaf. Fresh
    # symbol lookup independently fixes addresses rather than CDLL mirrors.
    for library,abi in ((state.cf,_GROUP_CF_ABI),(state.lib,_GROUP_SEC_ABI)):
        for name,result,args in abi:
            fn=getattr(library,name);classes.append(_group_function_class_pin(fn));symbol=_GROUP_DLL_GETITEM(library,name)
            need(_GROUP_CAST(fn,c.c_void_p).value==_GROUP_CAST(symbol,c.c_void_p).value
                 and fn.restype is result and type(fn.argtypes) in (list,tuple) and tuple(fn.argtypes)==args
                 and getattr(fn,'errcheck',None) is None and fn._flags_==symbol._flags_)
            records.append((library,name,fn,_GROUP_CAST(fn,c.c_void_p).value,result,args,fn._flags_))
    facts=_GroupBackendFacts(backend,state.cf,state.lib,(state.cf._handle,state.lib._handle),(state.cf,state.lib),tuple(records),tuple(classes),state)
    _BACKENDS[backend]=(facts,weakref.ref(controller),weakref.ref(domain))
    return KeychainCredential(controller.entry.policy,backend=backend)


def group_backend_facts_if_issued(backend):
    found=_BACKENDS.get(backend)
    if found is None:return None
    facts,controller_ref,domain_ref=found;controller=controller_ref();domain=domain_ref()
    need(controller is not None and domain is not None)
    from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
    need(require_rich_syn_domain_for_entry(controller.entry) is domain)
    validate_group_backend_facts_pure(facts);return facts


def validate_group_backend_facts_pure(facts):
    found=_BACKENDS.get(facts.backend);need(found is not None and found[0] is facts)
    domain=found[2]();need(domain is not None and facts.rich_record is _state(domain))
    from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
    controller=found[1]();need(controller is not None and require_rich_syn_domain_for_entry(controller.entry) is domain)
    validate_native_domain_pure(domain)
    state=facts.rich_record
    need(facts.cf is state.cf and facts.sec is state.lib)
    return None


@contextmanager
def rich_syn_query_lifetime(backend):
    found=_BACKENDS.get(backend)
    if found is None:yield;return
    facts=found[0];validate_group_backend_facts_pure(facts);state=facts.rich_record;domain=found[2]();need(domain is not None)
    _STATE_QUERIES[id(domain)]+=1;state.active_queries+=1
    try:yield
    finally:
        need(state.active_queries==_STATE_QUERIES[id(domain)])
        _STATE_QUERIES[id(domain)]-=1;state.active_queries-=1


def close_rich_syn_keychain(domain):
    state=_STATES.get(id(domain))
    if state is None:return None
    need(state.domain() is domain and state.thread==_THREAD() and not state.closed and state.active_queries==0)
    from .draft_group_rich_syn_fixture import _SERVICE_DOMAINS
    for service,pair in tuple(_SERVICE_DOMAINS.items()):
        if pair[0] is domain:
            service.tokens.cached=None;service.tokens.credential=None
    values=dict(state.functions)
    for pin in values.values():_function_check(pin)
    counters=tuple(_function_check(values['SYNGetCounter'])(i)for i in range(4))
    need(counters[2:]==(0,0))
    code=_function_check(values['SYNDisposeConstants'])()
    if code!=0:raise WCEError('GROUP_RICH_SYN_CF_DISPOSE_BUSY')
    state.closed=True
    for backend,found in tuple(_BACKENDS.items()):
        if found[0].rich_record is state:_BACKENDS.pop(backend,None)
    state.binary.close();_STATES.pop(id(domain),None);_STATE_FACTS.pop(id(domain),None);_STATE_QUERIES.pop(id(domain),None)
    return {'authority':False,'default_calls':counters[0],'matching_calls':counters[1],
            'add_calls':counters[2],'delete_calls':counters[3],'system_security_calls':0}


def require_rich_syn_credential(controller,credential):
    from .own_keychain import KeychainCredential
    need(type(credential) is KeychainCredential and credential.config is controller.entry.policy)
    found=_BACKENDS.get(credential.backend)
    need(found is not None and found[1]() is controller)
    group_backend_facts_if_issued(credential.backend);return credential


def assert_rich_syn_keychain_tcb():
    # Verify helpers/primitives before calling even the local assertion helper.
    if any(globals().get(name) is not fn or fn.__code__ is not code for name,fn,code in _FUNCTION_PINS):
        raise WCEError('GROUP_RICH_SYN_TCB_CHANGED')
    if any(globals().get(name) is not original for name,original in _PRIMITIVE_PINS):
        raise WCEError('GROUP_RICH_SYN_TCB_CHANGED')
    for fn,code,cells in _CLOSURE_PINS:
        need(fn.__code__ is code and all(cell.cell_contents is original for cell,original in cells))
    for name,fn,code in _FUNCTION_PINS:
        need(globals().get(name) is fn and fn.__code__ is code)
    for cls,bases,mro,items in _CLASS_PINS:
        attrs=type.__getattribute__(cls,'__dict__')
        need(type.__getattribute__(cls,'__bases__')==bases and type.__getattribute__(cls,'__mro__')==mro
             and tuple(attrs)==tuple(name for name,_,_ in items))
        for name,member,code in items:
            need(attrs[name] is member and (code is None or member.__code__ is code))
    for name,fn,code in _DOMAIN_FUNCTION_PINS:
        need(getattr(_DOMAIN_MODULE,name) is fn and fn.__code__ is code)
    _DOMAIN_MODULE.assert_rich_syn_fixture_tcb()
    return None


RICH_KEYCHAIN_TCB_NAMES=tuple(name for name,value in tuple(globals().items())
    if getattr(value,'__module__',None)==__name__ and hasattr(value,'__code__'))
_FUNCTION_PINS=tuple((name,globals()[name],globals()[name].__code__)for name in RICH_KEYCHAIN_TCB_NAMES)
_CLASS_PINS=tuple((cls,type.__getattribute__(cls,'__bases__'),type.__getattribute__(cls,'__mro__'),
    tuple((name,value,getattr(value,'__code__',None)) for name,value in type.__getattribute__(cls,'__dict__').items()))for cls in (_NativeState,))
from . import draft_group_rich_syn_fixture as _DOMAIN_MODULE
_DOMAIN_FUNCTION_PINS=tuple((name,getattr(_DOMAIN_MODULE,name),getattr(_DOMAIN_MODULE,name).__code__)
    for name in _DOMAIN_MODULE.RICH_FIXTURE_TCB_NAMES)


# contextmanager wrappers and descriptor functions retain mutable function
# objects. Pin their actual code and closure cells, not merely the wrapper.
def _closure_images():
    from types import FunctionType
    pending=[fn for _,fn,_ in _FUNCTION_PINS]
    for cls,*_ in _CLASS_PINS:
        for value in vars(cls).values():
            if type(value) is property:pending.extend(fn for fn in (value.fget,value.fset,value.fdel) if fn is not None)
            elif type(value) in (staticmethod,classmethod):pending.append(value.__func__)
            elif type(value) is FunctionType:pending.append(value)
    found={};images=[]
    while pending:
        fn=pending.pop()
        if type(fn) is not FunctionType or id(fn) in found:continue
        found[id(fn)]=fn;cells=tuple((cell,cell.cell_contents)for cell in (fn.__closure__ or ()))
        images.append((fn,fn.__code__,cells))
        pending.extend(value for _,value in cells if type(value) is FunctionType)
        wrapped=getattr(fn,'__wrapped__',None)
        if type(wrapped) is FunctionType:pending.append(wrapped)
    return tuple(images)

_CLOSURE_PINS=_closure_images()

_PRIMITIVE_PINS=tuple((name,globals()[name])for name in ('_THREAD',))
