"""One installation-local Ark credential, separate from platform accounts."""
from hashlib import sha256
import ctypes as c

from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .x_keychain import XKeychain

SERVICE = 'com.readysteadyscience.openahoy.video.ark.cn-beijing.v1'
SCOPE = sha256(SERVICE.encode()).hexdigest()


class VideoKeychain(XKeychain):
    service = SERVICE
    label = 'OpenAhoy · Volcengine Ark API Key'

    def configured(self):
        result = c.c_void_p()
        try:
            with self.query(SCOPE, deleting=True) as query:
                code = self.sec.SecItemCopyMatching(query, c.byref(result))
            if code not in (0, -25300):
                raise WCEError('VIDEO_KEYCHAIN_ACCESS_REQUIRED')
            return code == 0
        finally:
            if result.value:
                self.cf.CFRelease(result)


def load(backend=None):
    try:
        return (backend if backend is not None else VideoKeychain()).load(SCOPE)
    except Exception:
        raise WCEError('VIDEO_KEYCHAIN_ACCESS_REQUIRED') from None


def status(backend=None):
    try:
        present = VideoKeychain().configured() if backend is None else backend.configured()
        return {'state': 'CONFIGURED' if present else 'NOT_CONFIGURED'}
    except Exception:
        return {'state': 'ACTION_REQUIRED'}


def save(value, backend=None):
    if not valid_secret(value):
        raise WCEError('VIDEO_KEY_INVALID')
    try:
        (backend if backend is not None else VideoKeychain()).put(SCOPE, Secret(value))
    except Exception:
        raise WCEError('VIDEO_KEYCHAIN_SAVE_FAILED') from None
    return {'state': 'CONFIGURED'}
