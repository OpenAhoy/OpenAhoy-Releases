"""One installation-local Ark credential, separate from platform accounts."""
from hashlib import sha256
import ctypes as c

from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .x_keychain import XKeychain
from .video_minimax import SITES
from .video_seedance import BYTEPLUS_PROVIDER
from .video_sand import PROVIDER as SAND_PROVIDER

SERVICE = 'com.readysteadyscience.openahoy.video.ark.cn-beijing.v1'
SCOPE = sha256(SERVICE.encode()).hexdigest()
BYTEPLUS_SERVICE = 'com.readysteadyscience.openahoy.video.ark.ap-southeast-1.v1'
BYTEPLUS_SCOPE = sha256(BYTEPLUS_SERVICE.encode()).hexdigest()
SAND_SERVICE = 'com.readysteadyscience.openahoy.video.sand.v1'
SAND_SCOPE = sha256(SAND_SERVICE.encode()).hexdigest()
PROVIDERS = ('ark', BYTEPLUS_PROVIDER, SAND_PROVIDER, *SITES)


def scope(provider):
    if provider == 'ark':
        return SCOPE
    if provider == BYTEPLUS_PROVIDER:
        return BYTEPLUS_SCOPE
    if provider == SAND_PROVIDER:
        return SAND_SCOPE
    if provider not in SITES:
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    return sha256(f'openahoy:minimax:h3:{provider}:v1'.encode()).hexdigest()


class VideoKeychain(XKeychain):
    service = SERVICE
    label = 'Jiusera · Volcengine Ark API Key'

    def __init__(self, provider='ark'):
        if provider == BYTEPLUS_PROVIDER:
            self.service = BYTEPLUS_SERVICE
            self.label = 'Jiusera · BytePlus ModelArk API Key'
        elif provider == SAND_PROVIDER:
            self.service = SAND_SERVICE
            self.label = 'Jiusera · Sand AI API Key'
        elif provider in SITES:
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


def masked_credential(value):
    """Expose a fixed-length hint without disclosing short values or their length."""
    if not valid_secret(value):
        raise WCEError('VIDEO_KEY_INVALID')
    return (value[:4] if len(value) > 8 else '') + '********'


def read_for_display(backend, key_scope, configured):
    try:
        with backend.without_user_interaction():
            try:
                item = backend.load(key_scope)
            except Exception:
                return ('CONFIGURED' if configured() else 'NOT_CONFIGURED'), None
            return ('NOT_CONFIGURED' if item is None else 'CONFIGURED'), item
    except Exception:
        return 'ACTION_REQUIRED', None


def display_status(backend, key_scope):
    state, item = read_for_display(backend, key_scope, backend.configured)
    result = {'state': state}
    if item is not None:
        result['credential_mask'] = masked_credential(item.reveal_for_adapter())
    return result


def load(backend=None, *, provider='ark'):
    try:
        return (backend if backend is not None else VideoKeychain(provider)).load(scope(provider))
    except Exception:
        raise WCEError('VIDEO_KEYCHAIN_ACCESS_REQUIRED') from None


def status(backend=None, *, provider='ark', show_mask=False):
    try:
        keychain = VideoKeychain(provider) if backend is None else backend
        if show_mask:
            return display_status(keychain, scope(provider))
        present = keychain.configured()
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
