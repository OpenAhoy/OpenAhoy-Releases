"""X-only OAuth item; reuse macOS ABI setup without changing WeChat storage."""
import ctypes as c
from contextlib import contextmanager
import re

from .contracts import Secret, WCEError
from .own_keychain import NativeKeychain

SERVICE = 'com.readysteadyscience.openahoy.x.oauth2.v1'


class XKeychain(NativeKeychain):
    service = SERVICE
    label = 'Jiusera X OAuth connection'
    @contextmanager
    def query(self, scope, value=None, reading=False, deleting=False):
        if type(scope) is not str or re.fullmatch('[a-f0-9]{64}', scope) is None:
            raise WCEError('X_KEYCHAIN_SCOPE_INVALID')
        allocated = []
        try:
            def string(value):
                raw = value.encode('utf-8')
                ptr = self.cf.CFStringCreateWithBytes(None, c.create_string_buffer(raw), len(raw), 0x08000100, False)
                if not ptr:
                    raise WCEError('X_KEYCHAIN_UNAVAILABLE')
                allocated.append(ptr)
                return ptr
            pairs = [('kSecClass', self.constant('kSecClassGenericPassword')),
                     ('kSecAttrService', string(self.service)), ('kSecAttrAccount', string(scope))]
            default = c.c_void_p()
            status = self.sec.SecKeychainCopyDefault(c.byref(default))
            if status or not default.value:
                raise WCEError('X_KEYCHAIN_ACCESS_REQUIRED')
            allocated.append(default.value)
            if reading or deleting:
                refs = (c.c_void_p * 1)(default.value)
                array = self.cf.CFArrayCreate(None, refs, 1, c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeArrayCallBacks')))
                if not array:
                    raise WCEError('X_KEYCHAIN_UNAVAILABLE')
                allocated.append(array)
                pairs.append(('kSecMatchSearchList', array))
                if reading:
                    pairs += [('kSecReturnData', self.constant('kCFBooleanTrue', True)),
                              ('kSecMatchLimit', self.constant('kSecMatchLimitOne'))]
            else:
                pairs.append(('kSecUseKeychain', default.value))
            if value is not None:
                raw = value.encode('ascii')
                ptr = self.cf.CFDataCreate(None, c.create_string_buffer(raw), len(raw))
                if not ptr:
                    raise WCEError('X_KEYCHAIN_UNAVAILABLE')
                allocated.append(ptr)
                pairs += [('kSecValueData', ptr), ('kSecAttrLabel', string(self.label))]
            keys = (c.c_void_p * len(pairs))(*(self.constant(k) for k, _ in pairs))
            values = (c.c_void_p * len(pairs))(*(v for _, v in pairs))
            query = self.cf.CFDictionaryCreate(None, keys, values, len(pairs),
                c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryKeyCallBacks')),
                c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryValueCallBacks')))
            if not query:
                raise WCEError('X_KEYCHAIN_UNAVAILABLE')
            allocated.append(query)
            yield query
        finally:
            for pointer in reversed(allocated):
                self.cf.CFRelease(pointer)

    def _decode_read_result(self, status, result):
        if status == -25300:
            return None
        if status or not result.value or self.cf.CFGetTypeID(result) != self.cf.CFDataGetTypeID():
            raise WCEError('X_KEYCHAIN_ACCESS_REQUIRED')
        size = self.cf.CFDataGetLength(result)
        if size <= 0:
            raise WCEError('X_KEYCHAIN_INVALID_ITEM')
        return Secret(c.string_at(self.cf.CFDataGetBytePtr(result), size).decode('ascii'))

    def put(self, scope, credential):
        if type(credential) is not Secret:
            raise WCEError('X_KEYCHAIN_INVALID_ITEM')
        # A single atomic SecItemUpdate; never delete the old rotating token first.
        raw = credential.reveal_for_adapter().encode('ascii')
        pointer = self.cf.CFDataCreate(None, c.create_string_buffer(raw), len(raw))
        if not pointer:
            raise WCEError('X_KEYCHAIN_UNAVAILABLE')
        attributes = None
        try:
            keys = (c.c_void_p * 1)(self.constant('kSecValueData'))
            values = (c.c_void_p * 1)(pointer)
            attributes = self.cf.CFDictionaryCreate(None, keys, values, 1,
                c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryKeyCallBacks')),
                c.addressof(c.c_byte.in_dll(self.cf, 'kCFTypeDictionaryValueCallBacks')))
            if not attributes:
                raise WCEError('X_KEYCHAIN_UNAVAILABLE')
            self._function(self.sec, 'SecItemUpdate', c.c_int32, [c.c_void_p, c.c_void_p])
            with self.query(scope, deleting=True) as query:
                status = self.sec.SecItemUpdate(query, attributes)
            if status == -25300:
                with self.query(scope, value=credential.reveal_for_adapter()) as query:
                    status = self.sec.SecItemAdd(query, None)
            if status:
                raise WCEError('X_KEYCHAIN_WRITE_FAILED')
        finally:
            if attributes:
                self.cf.CFRelease(attributes)
            self.cf.CFRelease(pointer)
