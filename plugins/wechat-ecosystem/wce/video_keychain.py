"""One installation-local Ark credential, separate from platform accounts."""
from hashlib import sha256
import ctypes as c

from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .x_keychain import XKeychain
from .video_minimax import SITES

SERVICE = 'com.readysteadyscience.openahoy.video.ark.cn-beijing.v1'
SCOPE = sha256(SERVICE.encode()).hexdigest()
PROVIDERS = ('ark', *SITES)


def scope(provider):
    if provider == 'ark':
        return SCOPE
    if provider not in SITES:
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    return sha256(f'openahoy:minimax:h3:{provider}:v1'.encode()).hexdigest()


class VideoKeychain(XKeychain):
    service = SERVICE
    label = 'Jiusera · Volcengine Ark API Key'

    def __init__(self, provider='ark'):
        if provider in SITES:
            self.service = 'com.readysteadyscience.openahoy.video.minimax.' + provider + '.v1'
            self.label = 'Jiusera · MiniMax H3 · ' + provider
        self.scope = scope(provider)
        super().__init__()

    def configured(self):
        return configured_item(self, self.scope)


def configured_item(backend, key_scope):
    result = c.c_void_p()
    try:
        with backend.query(key_scope, deleting=True) as query:
            code = backend.sec.SecItemCopyMatching(query, c.byref(result))
        if code not in (0, -25300):
            raise WCEError('VIDEO_KEYCHAIN_ACCESS_REQUIRED')
        return code == 0
    finally:
        if result.value:
            backend.cf.CFRelease(result)


def load(backend=None, *, provider='ark'):
    try:
        return (backend if backend is not None else VideoKeychain(provider)).load(scope(provider))
    except Exception:
        raise WCEError('VIDEO_KEYCHAIN_ACCESS_REQUIRED') from None


def status(backend=None, *, provider='ark'):
    try:
        present = VideoKeychain(provider).configured() if backend is None else backend.configured()
        return {'state': 'CONFIGURED' if present else 'NOT_CONFIGURED'}
    except Exception:
        return {'state': 'ACTION_REQUIRED'}


def save(value, backend=None, *, provider='ark'):
    if not valid_secret(value):
        raise WCEError('VIDEO_KEY_INVALID')
    try:
        (backend if backend is not None else VideoKeychain(provider)).put(scope(provider), Secret(value))
    except Exception:
        raise WCEError('VIDEO_KEYCHAIN_SAVE_FAILED') from None
    return {'state': 'CONFIGURED'}
