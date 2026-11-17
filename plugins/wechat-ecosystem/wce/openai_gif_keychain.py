"""OpenAI's GIF credential, stored separately from other model keys."""
from hashlib import sha256

from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .video_keychain import VideoKeychain
from .x_keychain import XKeychain

PROVIDER = 'openai_gif'
PURPOSE = 'openahoy:image:openai:gif:key:v1'
SERVICE = 'com.readysteadyscience.openahoy.image.openai.gif.v1'
SCOPE = sha256(SERVICE.encode()).hexdigest()


class GifKeychain(VideoKeychain):
    service = SERVICE
    label = 'OpenAhoy · OpenAI GIF API Key'

    def __init__(self):
        # The configured() query uses this exact scope and does not retrieve key data.
        self.scope = SCOPE
        XKeychain.__init__(self)


def status(backend=None):
    try:
        present = (backend if backend is not None else GifKeychain()).configured()
    except Exception:
        return {'state': 'ACTION_REQUIRED', 'gif_access': 'UNVERIFIED'}
    return {'state': 'CONFIGURED' if present else 'NOT_CONFIGURED', 'gif_access': 'UNVERIFIED'}


def load(backend=None):
    try:
        return (backend if backend is not None else GifKeychain()).load(SCOPE)
    except Exception:
        raise WCEError('GIF_KEYCHAIN_ACCESS_REQUIRED') from None


def save(value, backend=None):
    if not valid_secret(value):
        raise WCEError('GIF_KEY_INVALID')
    try:
        (backend if backend is not None else GifKeychain()).put(SCOPE, Secret(value))
    except Exception:
        raise WCEError('GIF_KEYCHAIN_SAVE_FAILED') from None
    return {'state': 'CONFIGURED', 'gif_access': 'UNVERIFIED'}
