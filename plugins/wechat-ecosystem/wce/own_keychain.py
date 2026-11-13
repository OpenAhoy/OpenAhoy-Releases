"""Host-only macOS Keychain storage for one explicit WCE connection.

No shell, credential stdout, environment lookup or other-keychain discovery.
The caller owns the human input and only the operator calls load/store.
"""
import ctypes as c
from contextlib import contextmanager
from hashlib import sha256
import json
import re
import sys

from .contracts import Secret, WCEError

SERVICE = 'com.readysteadyscience.wce.own.appsecret.v1'


def credential_scope(config):
    config.check()
    d = config.data
    identity = {k: d[k] for k in ('actor', 'connection_id', 'appid', 'resource_id', 'generation', 'epoch', 'private_directory')}
    return sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def valid_secret(value):
    return type(value) is str and 0 < len(value) <= 4096 and all(33 <= ord(x) <= 126 for x in value)


class NativeKeychain:
    """Generic password in the default macOS keychain; no app-group claims."""
    def __init__(self):
        if sys.platform != 'darwin':
            raise WCEError('BOOTSTRAP_KEYCHAIN_UNAVAILABLE')
        try:
            self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            self.sec = c.CDLL('/System/Library/Frameworks/Security.framework/Security')
            self._configure_functions()
        except Exception:
            raise WCEError('BOOTSTRAP_KEYCHAIN_UNAVAILABLE') from None

    def _configure_functions(self):
        self._function(self.cf, 'CFStringCreateWithBytes', c.c_void_p,
                       [c.c_void_p, c.c_void_p, c.c_long, c.c_uint32, c.c_bool])
        self._function(self.cf, 'CFDataCreate', c.c_void_p, [c.c_void_p, c.c_void_p, c.c_long])
        self._function(self.cf, 'CFDictionaryCreate', c.c_void_p,
                       [c.c_void_p, c.c_void_p, c.c_void_p, c.c_long, c.c_void_p, c.c_void_p])
        self._function(self.cf, 'CFArrayCreate', c.c_void_p,
                       [c.c_void_p, c.c_void_p, c.c_long, c.c_void_p])
        self._function(self.cf, 'CFRelease', None, [c.c_void_p])
        self._function(self.cf, 'CFGetTypeID', c.c_ulong, [c.c_void_p])
        self._function(self.cf, 'CFDataGetTypeID', c.c_ulong, [])
        self._function(self.cf, 'CFDataGetLength', c.c_long, [c.c_void_p])
        self._function(self.cf, 'CFDataGetBytePtr', c.c_void_p, [c.c_void_p])
        for name in ('SecItemAdd', 'SecItemCopyMatching'):
            self._function(self.sec, name, c.c_int32, [c.c_void_p, c.POINTER(c.c_void_p)])
        self._function(self.sec, 'SecItemDelete', c.c_int32, [c.c_void_p])
        self._function(self.sec, 'SecKeychainCopyDefault', c.c_int32, [c.POINTER(c.c_void_p)])

    @staticmethod
    def _function(lib, name, result, args):
        fn = getattr(lib, name); fn.restype = result; fn.argtypes = args

    def constant(self, name, cf=False):
        return c.c_void_p.in_dll(self.cf if cf else self.sec, name).value

    @contextmanager
    def query(self, scope, value=None, reading=False, deleting=False):
        if type(scope) is not str or re.fullmatch('[a-f0-9]{64}', scope) is None:
            raise WCEError('BOOTSTRAP_KEYCHAIN_SCOPE_CHANGED')
        allocated = []
        try:
            def string(value):
                raw = value.encode('utf-8'); buf = c.create_string_buffer(raw)
                ptr = self.cf.CFStringCreateWithBytes(None, buf, len(raw), 0x08000100, False)
                if not ptr: raise ValueError()
                allocated.append(ptr); return ptr
            default = c.c_void_p()
            status = self.sec.SecKeychainCopyDefault(c.byref(default))
            if status != 0 or not default.value:
                raise WCEError(self._error(status))
            allocated.append(default.value)
            pairs = [('kSecClass', self.constant('kSecClassGenericPassword')),
                     ('kSecAttrService', string(SERVICE)), ('kSecAttrAccount', string(scope))]
            if reading or deleting:
                refs = (c.c_void_p * 1)(default.value)
                callbacks = c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeArrayCallBacks'))
                search = self.cf.CFArrayCreate(None, refs, 1, callbacks)
                if not search: raise ValueError()
                allocated.append(search)
                pairs += [('kSecMatchSearchList', search)]
                if reading:
                    pairs += [('kSecMatchLimit', self.constant('kSecMatchLimitOne')),
                              ('kSecReturnData', self.constant('kCFBooleanTrue', True))]
            else:
                pairs += [('kSecUseKeychain', default.value)]
            if value is not None:
                raw = value.encode('ascii'); buf = c.create_string_buffer(raw)
                ptr = self.cf.CFDataCreate(None, buf, len(raw))
                if not ptr: raise ValueError()
                allocated.append(ptr)
                pairs += [('kSecValueData', ptr), ('kSecAttrLabel', string('WCE public account credential'))]
            keys = (c.c_void_p * len(pairs))(*(self.constant(k) for k, _ in pairs))
            values = (c.c_void_p * len(pairs))(*(v for _, v in pairs))
            key_callbacks = c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryKeyCallBacks'))
            value_callbacks = c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryValueCallBacks'))
            query = self.cf.CFDictionaryCreate(None, keys, values, len(pairs), key_callbacks, value_callbacks)
            if not query: raise ValueError()
            allocated.append(query)
            yield query
        finally:
            for ptr in reversed(allocated): self.cf.CFRelease(ptr)

    @staticmethod
    def _error(status):
        if status in (-128, -25293): return 'BOOTSTRAP_KEYCHAIN_ACCESS_DENIED'
        if status in (-25308, -25291): return 'BOOTSTRAP_KEYCHAIN_UNLOCK_OR_ACCESS_REQUIRED'
        if status == -25299: return 'BOOTSTRAP_KEYCHAIN_ITEM_EXISTS'
        return 'BOOTSTRAP_KEYCHAIN_OPERATION_FAILED'

    def load(self, scope):
        result = c.c_void_p()
        try:
            with self.query(scope, reading=True) as query:
                status = self.sec.SecItemCopyMatching(query, c.byref(result))
            return self._decode_read_result(status, result)
        except WCEError:
            raise
        except Exception:
            raise WCEError('BOOTSTRAP_KEYCHAIN_INVALID_ITEM') from None
        finally:
            if result.value: self.cf.CFRelease(result)

    def _decode_read_result(self, status, result):
        if status == -25300: return None
        if status != 0: raise WCEError(self._error(status))
        if not result.value or self.cf.CFGetTypeID(result) != self.cf.CFDataGetTypeID(): raise ValueError()
        length = self.cf.CFDataGetLength(result)
        if not 0 < length <= 4096: raise ValueError()
        pointer = self.cf.CFDataGetBytePtr(result)
        if not pointer: raise ValueError()
        raw = c.string_at(pointer, length)
        value = raw.decode('ascii')
        if not valid_secret(value): raise ValueError()
        return Secret(value)

    def store(self, scope, value):
        if not valid_secret(value): raise WCEError('BOOTSTRAP_CREDENTIAL_INVALID')
        try:
            with self.query(scope, value=value) as query:
                status = self.sec.SecItemAdd(query, None)
            if status != 0: raise WCEError(self._error(status))
        except WCEError:
            raise
        except Exception:
            raise WCEError('BOOTSTRAP_KEYCHAIN_OPERATION_FAILED') from None


class KeychainCredential:
    def __init__(self, config, backend=None):
        self.config = config
        self.scope = credential_scope(config)
        self.backend = NativeKeychain() if backend is None else backend

    def _check(self):
        if credential_scope(self.config) != self.scope:
            raise WCEError('BOOTSTRAP_KEYCHAIN_SCOPE_CHANGED')

    def load(self):
        self._check(); value = self.backend.load(self.scope); self._check()
        if value is not None and type(value) is not Secret:
            raise WCEError('BOOTSTRAP_KEYCHAIN_INVALID_ITEM')
        return value

    def store(self, value):
        self._check(); self.backend.store(self.scope, value); self._check()


_GROUP_QUERY = NativeKeychain.query
_GROUP_DECODE = NativeKeychain._decode_read_result
_GROUP_CHECK = KeychainCredential._check
_GROUP_PREPARED = {}
_GROUP_QUERY_CONTEXT = {}
_GROUP_READ_USED = set()

from dataclasses import dataclass as _group_dataclass, field as _group_field
import threading as _group_threading

_GROUP_DLL = c.CDLL
_GROUP_DLL_INIT = c.CDLL.__init__
_GROUP_DLL_GETITEM = c.CDLL.__getitem__
_GROUP_CAST = c.cast
_GROUP_DLOPEN = c._dlopen
_GROUP_CFUNC = c._CFuncPtr
_GROUP_CFUNC_CALL=c._CFuncPtr.__call__
_GROUP_VOID_P=c.c_void_p;_GROUP_BYREF=c.byref
_GROUP_CTYPES_CODE=tuple((fn,fn.__code__) for fn in (_GROUP_DLL_INIT,_GROUP_DLL_GETITEM,_GROUP_CAST))
_GROUP_SYSTEM_CF = '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
_GROUP_SYSTEM_SEC = '/System/Library/Frameworks/Security.framework/Security'
_GROUP_CF_ABI = (
    ('CFStringCreateWithBytes', c.c_void_p, (c.c_void_p,c.c_void_p,c.c_long,c.c_uint32,c.c_bool)),
    ('CFDataCreate', c.c_void_p, (c.c_void_p,c.c_void_p,c.c_long)),
    ('CFDictionaryCreate', c.c_void_p, (c.c_void_p,c.c_void_p,c.c_void_p,c.c_long,c.c_void_p,c.c_void_p)),
    ('CFArrayCreate', c.c_void_p, (c.c_void_p,c.c_void_p,c.c_long,c.c_void_p)),
    ('CFRelease', None, (c.c_void_p,)), ('CFGetTypeID', c.c_ulong, (c.c_void_p,)),
    ('CFDataGetTypeID', c.c_ulong, ()), ('CFDataGetLength', c.c_long, (c.c_void_p,)),
    ('CFDataGetBytePtr', c.c_void_p, (c.c_void_p,)))
_GROUP_SEC_ABI = (
    ('SecKeychainCopyDefault', c.c_int32, (c.POINTER(c.c_void_p),)),
    ('SecItemCopyMatching', c.c_int32, (c.c_void_p,c.POINTER(c.c_void_p))),
    ('SecItemAdd', c.c_int32, (c.c_void_p,c.POINTER(c.c_void_p))),
    ('SecItemDelete', c.c_int32, (c.c_void_p,)))


def _group_keychain_hold():
    raise WCEError('GROUP_KEYCHAIN_TCB_UNAVAILABLE')


def _group_ctypes_original():
    for cls,bases,mro,attributes in _GROUP_CLASS_PINS:
        if (type.__getattribute__(cls,'__bases__')!=bases or type.__getattribute__(cls,'__mro__')!=mro
                or tuple(type.__getattribute__(cls,'__dict__'))!=tuple(name for name,_,_ in attributes)):
            _group_keychain_hold()
        for name,original,code in attributes:
            if (type.__getattribute__(cls,'__dict__')[name] is not original
                    or (code is not None and original.__code__ is not code)):_group_keychain_hold()
    if (c.CDLL is not _GROUP_DLL or c.CDLL.__init__ is not _GROUP_DLL_INIT
            or c.CDLL.__getitem__ is not _GROUP_DLL_GETITEM or c.cast is not _GROUP_CAST
            or c._dlopen is not _GROUP_DLOPEN or c._CFuncPtr is not _GROUP_CFUNC
            or c._CFuncPtr.__call__ is not _GROUP_CFUNC_CALL or c.c_void_p is not _GROUP_VOID_P or c.byref is not _GROUP_BYREF
            or any(fn.__code__ is not code for fn,code in _GROUP_CTYPES_CODE)):
        _group_keychain_hold()


@_group_dataclass(frozen=True,eq=False,slots=True)
class _GroupBackendFacts:
    backend: object = _group_field(repr=False)
    cf: object = _group_field(repr=False)
    sec: object = _group_field(repr=False)
    handles: tuple
    trusted_libraries: tuple = _group_field(repr=False)
    functions: tuple = _group_field(repr=False)
    function_classes: tuple = _group_field(default=(),repr=False)
    rich_record: object = _group_field(default=None,repr=False)


def _group_function_class_pin(function):
    cls=type(function)
    allowed={'__module__','__firstlineno__','_flags_','_restype_','__static_attributes__','__dict__','__weakref__','__doc__'}
    if (type.__getattribute__(cls,'__bases__')!=(_GROUP_CFUNC,)
            or set(type.__getattribute__(cls,'__dict__'))-allowed
            or cls.__call__ is not _GROUP_CFUNC_CALL):_group_keychain_hold()
    return cls,type.__getattribute__(cls,'__bases__'),type.__getattribute__(cls,'__mro__'),tuple(type.__getattribute__(cls,'__dict__').items())


def _validate_group_function_class_pin(pin):
    cls,bases,mro,items=pin
    actual=type.__getattribute__(cls,'__dict__')
    if (type.__getattribute__(cls,'__bases__')!=bases or type.__getattribute__(cls,'__mro__')!=mro
            or tuple(actual)!=tuple(name for name,_ in items)
            or any(actual[name] is not value for name,value in items)):_group_keychain_hold()


def _pin_group_backend(backend):
    """No Security/CF effect: resolve actual fixed system symbols before query."""
    _group_ctypes_original()
    from .draft_group_rich_syn_keychain import group_backend_facts_if_issued
    rich=group_backend_facts_if_issued(backend)
    if rich is not None:return rich
    if (type(backend) is not NativeKeychain or type(backend.cf) is not _GROUP_DLL
            or type(backend.sec) is not _GROUP_DLL or type(backend.cf._name) is not str or type(backend.sec._name) is not str
            or backend.cf._name != _GROUP_SYSTEM_CF or backend.sec._name != _GROUP_SYSTEM_SEC):
        _group_keychain_hold()
    # Symbol lookup on fresh handles is independent of mutable CDLL attributes.
    # These are fixed OS framework paths, never a caller path/backend discovery.
    trusted_cf, trusted_sec = _GROUP_DLL(_GROUP_SYSTEM_CF), _GROUP_DLL(_GROUP_SYSTEM_SEC)
    if (type(backend.cf._handle) is not int or type(backend.sec._handle) is not int
            or (backend.cf._handle,backend.sec._handle)!=(trusted_cf._handle,trusted_sec._handle)):
        _group_keychain_hold()
    records=[];classes=[]
    for actual,trusted,abi in ((backend.cf,trusted_cf,_GROUP_CF_ABI),(backend.sec,trusted_sec,_GROUP_SEC_ABI)):
        for name,result,args in abi:
            fn=getattr(actual,name);classes.append(_group_function_class_pin(fn));symbol=_GROUP_DLL_GETITEM(trusted,name)
            if (not isinstance(fn,_GROUP_CFUNC) or type(fn).__call__ is not _GROUP_CFUNC_CALL
                    or type(fn.argtypes) not in (list,tuple) or _GROUP_CAST(fn,c.c_void_p).value != _GROUP_CAST(symbol,c.c_void_p).value
                    or fn.restype is not result or tuple(fn.argtypes or ()) != args
                    or getattr(fn,'errcheck',None) is not None or fn._flags_ != symbol._flags_):
                _group_keychain_hold()
            records.append((actual,name,fn,_GROUP_CAST(fn,c.c_void_p).value,result,args,fn._flags_))
    return _GroupBackendFacts(backend,backend.cf,backend.sec,(backend.cf._handle,backend.sec._handle),
        (trusted_cf,trusted_sec),tuple(records),tuple(classes))


def _validate_group_backend_pure(facts):
    _group_ctypes_original()
    for pin in facts.function_classes:_validate_group_function_class_pin(pin)
    if facts.rich_record is not None:
        from .draft_group_rich_syn_keychain import validate_group_backend_facts_pure
        validate_group_backend_facts_pure(facts)
    backend=facts.backend
    if (type(facts) is not _GroupBackendFacts or type(backend) is not NativeKeychain
            or backend.cf is not facts.cf or backend.sec is not facts.sec
            or type(facts.cf) is not _GROUP_DLL or type(facts.sec) is not _GROUP_DLL
            or type(facts.cf._name) is not str or type(facts.sec._name) is not str
            or facts.cf._name != _GROUP_SYSTEM_CF or (facts.rich_record is None and facts.sec._name != _GROUP_SYSTEM_SEC)
            or (facts.cf._handle,facts.sec._handle) != facts.handles):
        _group_keychain_hold()
    for library,name,fn,address,result,args,flags in facts.functions:
        if (getattr(library,name) is not fn or not isinstance(fn,_GROUP_CFUNC)
                or type(fn).__call__ is not _GROUP_CFUNC_CALL or type(fn.argtypes) not in (list,tuple)
                or _GROUP_CAST(fn,c.c_void_p).value != address or fn.restype is not result
                or tuple(fn.argtypes or ()) != args or getattr(fn,'errcheck',None) is not None or fn._flags_ != flags):
            _group_keychain_hold()


@_group_dataclass(frozen=True,eq=False,slots=True)
class _GroupReadFacts:
    value: object = _group_field(repr=False)
    controller: object = _group_field(repr=False)
    entry: object = _group_field(repr=False)
    source: object = _group_field(repr=False)
    token_use: object = _group_field(repr=False)
    cache: object = _group_field(repr=False)
    credential: object = _group_field(repr=False)
    backend: object = _group_field(repr=False)
    backend_facts: object = _group_field(repr=False)
    scope: str
    query: object = _group_field(repr=False)
    result: object = _group_field(repr=False)
    thread: int
    secret_function: object = _group_field(repr=False)
    release_function: object = _group_field(repr=False)
    owner_checker: object = _group_field(repr=False)
    owner_checker_code: object = _group_field(repr=False)
    owner_selector: object = _group_field(repr=False)
    owner_selector_code: object = _group_field(repr=False)


class _GroupPreparedRead:
    """Issued only while the original fixed query context is actually alive."""
    __slots__=('credential','backend','query','used')
    def __init__(self,*args,**kwargs):
        _group_keychain_hold()
    def validate_pure(self):
        _validate_group_read_pure(self)
    def read_once(self):
        facts=_validate_group_read_pure(self)
        from . import draft_group_token_runtime as runtime
        if (runtime._validate_owner is not facts.owner_checker
                or runtime._validate_owner.__code__ is not facts.owner_checker_code
                or runtime._secret_read_owner_for is not facts.owner_selector
                or runtime._secret_read_owner_for.__code__ is not facts.owner_selector_code
                or facts.controller._secret_used is not True):
            _group_keychain_hold()
        owner=facts.owner_selector(facts.controller)
        facts.owner_checker(owner,'SECRET_READ',None,used=True)
        _GROUP_READ_USED.add(id(self));self.used=True
        try:
            status=facts.secret_function(facts.query,c.byref(facts.result))
            return _GROUP_DECODE(facts.backend,status,facts.result)
        except WCEError:raise
        except Exception:raise WCEError('BOOTSTRAP_KEYCHAIN_INVALID_ITEM') from None
        finally:
            if facts.result.value:facts.release_function(facts.result)
            _GROUP_PREPARED.pop(id(self),None)


def _issue_group_prepared_read(controller):
    from . import draft_group_token_runtime as runtime
    active=_GROUP_QUERY_CONTEXT.get(id(controller))
    if (type(controller) is not runtime.GroupTokenAcquisitionController
            or runtime._CONTROLLERS.get(id(controller)) is not controller or active is None
            or active[0] is not controller or active[4]!=_group_threading.get_ident()):
        _group_keychain_hold()
    _,credential,query,backend_facts,_=active
    if type(query) is not int or query<=0:_group_keychain_hold()
    value=object.__new__(_GroupPreparedRead)
    value.credential=credential;value.backend=credential.backend;value.query=query;value.used=False
    records={(name,id(library)):fn for library,name,fn,*_ in backend_facts.functions}
    facts=_GroupReadFacts(value,controller,controller.entry,controller.source,controller.use,controller.cache,
        credential,credential.backend,backend_facts,credential.scope,query,c.c_void_p(),
        _group_threading.get_ident(),records[('SecItemCopyMatching',id(credential.backend.sec))],
        records[('CFRelease',id(credential.backend.cf))],runtime._validate_owner,runtime._validate_owner.__code__,
        runtime._secret_read_owner_for,runtime._secret_read_owner_for.__code__)
    _GROUP_PREPARED[id(value)]=facts
    return value


def _validate_group_read_pure(value):
    _group_read_tcb_original()
    facts=_GROUP_PREPARED.get(id(value))
    if type(value) is not _GroupPreparedRead or type(facts) is not _GroupReadFacts or facts.value is not value:
        _group_keychain_hold()
    from . import draft_group_token_runtime as runtime
    from .draft_group_runtime_host import _REGISTRY
    controller=facts.controller;credential=facts.credential;entry=facts.entry
    active=_GROUP_QUERY_CONTEXT.get(id(controller))
    if (type(controller) is not runtime.GroupTokenAcquisitionController or runtime._CONTROLLERS.get(id(controller)) is not controller
            or controller.entry is not entry or controller.source is not facts.source or controller.use is not facts.token_use
            or controller.cache is not facts.cache or _REGISTRY.get(entry.id) is not entry
            or entry.closed or entry.thread!=facts.thread or facts.thread!=_group_threading.get_ident()
            or active is None or active[0] is not controller or active[1] is not credential
            or active[2] is not facts.query or active[3] is not facts.backend_facts or active[4]!=facts.thread
            or controller.prepared_credential is not value or value.credential is not credential
            or type(credential) is not KeychainCredential or credential.config is not entry.policy
            or type(credential.scope) is not str or credential.scope!=facts.scope or value.backend is not facts.backend or credential.backend is not facts.backend
            or value.query is not facts.query or value.used is not False or id(value) in _GROUP_READ_USED
            or facts.result.value is not None):
        _group_keychain_hold()
    _group_read_tcb_original()
    _validate_group_backend_pure(facts.backend_facts)
    return facts


@contextmanager
def _prepare_group_read(self,controller):
    from .draft_group_token_runtime import GroupTokenAcquisitionController,_CONTROLLERS
    if (type(controller) is not GroupTokenAcquisitionController or _CONTROLLERS.get(id(controller)) is not controller
            or type(self) is not KeychainCredential or type(self.backend) is not NativeKeychain
            or self.config is not controller.entry.policy or '_check' in self.__dict__
            or 'query' in self.backend.__dict__ or id(controller) in _GROUP_QUERY_CONTEXT):
        _group_keychain_hold()
    _group_read_tcb_original()
    _GROUP_CHECK(self);backend_facts=_pin_group_backend(self.backend)
    prepared=None
    try:
        from .draft_group_rich_syn_keychain import rich_syn_query_lifetime
        with rich_syn_query_lifetime(self.backend),_GROUP_QUERY(self.backend,self.scope,reading=True) as query:
            _GROUP_QUERY_CONTEXT[id(controller)]=(controller,self,query,backend_facts,_group_threading.get_ident())
            prepared=_issue_group_prepared_read(controller);controller.prepared_credential=prepared
            _validate_group_read_pure(prepared)
            yield prepared
    finally:
        _GROUP_QUERY_CONTEXT.pop(id(controller),None)
        if prepared is not None:
            _GROUP_PREPARED.pop(id(prepared),None);_GROUP_READ_USED.discard(id(prepared))
        controller.prepared_credential=None


def _group_read_tcb_original():
    if any(getattr(_GROUP_RICH_MODULE,name) is not fn or fn.__code__ is not code for name,fn,code in _GROUP_RICH_FUNCTIONS):_group_keychain_hold()
    current=(NativeKeychain.query,NativeKeychain._decode_read_result,KeychainCredential._check,credential_scope,
        _validate_group_read_pure,_issue_group_prepared_read,_prepare_group_read,
        _GroupPreparedRead.read_once,_GroupPreparedRead.validate_pure,_GroupPreparedRead.__init__,
        _pin_group_backend,_validate_group_backend_pure,_group_read_tcb_original,
        NativeKeychain.__init__,KeychainCredential.__init__,NativeKeychain.constant,NativeKeychain._function,NativeKeychain._configure_functions,
        KeychainCredential._prepare_group_read,_group_function_class_pin,_validate_group_function_class_pin,_group_ctypes_original,_group_keychain_hold)
    if (current != _GROUP_READ_REFERENCES or _GROUP_QUERY is not current[0]
            or _GROUP_DECODE is not current[1] or _GROUP_CHECK is not current[2]
            or any(fn.__code__ is not code for fn,code in _GROUP_READ_CODE_REFERENCES)
            or (NativeKeychain.query.__wrapped__,_prepare_group_read.__wrapped__) != _GROUP_GENERATORS
            or any(fn.__code__ is not code for fn,code in _GROUP_GENERATOR_CODE_REFERENCES)):
        _group_keychain_hold()
    for wrapper,generator in zip((NativeKeychain.query,_prepare_group_read),_GROUP_GENERATORS):
        if wrapper.__closure__ is None or not any(cell.cell_contents is generator for cell in wrapper.__closure__):
            _group_keychain_hold()
    _group_ctypes_original()
    _GROUP_RICH_MODULE.assert_rich_syn_keychain_tcb()


KeychainCredential._prepare_group_read=_prepare_group_read
_GROUP_READ_REFERENCES=(NativeKeychain.query,NativeKeychain._decode_read_result,KeychainCredential._check,credential_scope,
    _validate_group_read_pure,_issue_group_prepared_read,_prepare_group_read,
    _GroupPreparedRead.read_once,_GroupPreparedRead.validate_pure,_GroupPreparedRead.__init__,
    _pin_group_backend,_validate_group_backend_pure,_group_read_tcb_original,
        NativeKeychain.__init__,KeychainCredential.__init__,NativeKeychain.constant,NativeKeychain._function,NativeKeychain._configure_functions,
        KeychainCredential._prepare_group_read,_group_function_class_pin,_validate_group_function_class_pin,_group_ctypes_original,_group_keychain_hold)
_GROUP_READ_CODE_REFERENCES=tuple((fn,fn.__code__) for fn in _GROUP_READ_REFERENCES)
_GROUP_GENERATORS=(NativeKeychain.query.__wrapped__,_prepare_group_read.__wrapped__)
_GROUP_GENERATOR_CODE_REFERENCES=tuple((fn,fn.__code__) for fn in _GROUP_GENERATORS)
_GROUP_CLASS_PINS=tuple((cls,type.__getattribute__(cls,'__bases__'),type.__getattribute__(cls,'__mro__'),
    tuple((name,value,getattr(value,'__code__',None)) for name,value in type.__getattribute__(cls,'__dict__').items()))
    for cls in (NativeKeychain,KeychainCredential,_GroupBackendFacts,_GroupReadFacts,_GroupPreparedRead,_GROUP_DLL,_GROUP_CFUNC,_GROUP_VOID_P))

from . import draft_group_rich_syn_keychain as _GROUP_RICH_MODULE
_GROUP_RICH_FUNCTIONS=tuple((name,getattr(_GROUP_RICH_MODULE,name),getattr(_GROUP_RICH_MODULE,name).__code__)
    for name in _GROUP_RICH_MODULE.RICH_KEYCHAIN_TCB_NAMES)
