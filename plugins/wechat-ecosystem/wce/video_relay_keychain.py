"""A relay connection lives in one dedicated Keychain item."""
from hashlib import sha256
from hmac import compare_digest, digest
import json
import re
import secrets

from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .video_keychain import configured_item, masked_credential, read_for_display
from .video_relay import relay_origin
from .x_keychain import XKeychain


class RelayKeychain(XKeychain):
    service = 'com.readysteadyscience.openahoy.video.comfyui-relay.v1'
    label = 'Jiusera · Video relay'
    scope = sha256(service.encode()).hexdigest()


def _decode(stored):
    if stored is None:
        return None
    row = json.loads(stored.reveal_for_adapter())
    origin = relay_origin(row['origin'])
    token, identity_key = row['token'], row['identity_key']
    if not valid_secret(token) or not re.fullmatch(r'[a-f0-9]{64}', identity_key):
        raise ValueError()
    return origin, token, identity_key


def _read(backend, scope):
    return _decode(backend.load(scope))


def load_relay(backend=None, *, keychain=RelayKeychain):
    try:
        current = _read(backend if backend is not None else keychain(), keychain.scope)
        if current is None:
            return None
        origin, token, identity_key = current
        marker = digest(bytes.fromhex(identity_key), (origin + '\0' + token).encode(), 'sha256').hex()
        return origin, marker, Secret(token)
    except Exception:
        raise WCEError('VIDEO_RELAY_KEYCHAIN_ACCESS_REQUIRED') from None


def relay_status(backend=None, *, keychain=RelayKeychain, show_mask=False):
    try:
        backend = backend if backend is not None else keychain()
        if show_mask:
            state, stored = read_for_display(backend, keychain.scope, lambda: configured_item(backend, keychain.scope))
            current = _decode(stored)
            if current is None:
                return {'state': state}
            return {'state': state, 'base_url': current[0], 'credential_mask': masked_credential(current[1])}
        current = _read(backend, keychain.scope)
        return {'state': 'NOT_CONFIGURED'} if current is None else {'state': 'CONFIGURED', 'base_url': current[0]}
    except Exception:
        return {'state': 'ACTION_REQUIRED'}


def save_relay(origin, token, backend=None, *, keychain=RelayKeychain):
    origin = relay_origin(origin)
    if not valid_secret(token):
        raise WCEError('VIDEO_KEY_INVALID')
    try:
        backend = backend if backend is not None else keychain()
        current = _read(backend, keychain.scope)
        if current and origin == current[0] and compare_digest(token, current[1]):
            return {'state': 'CONFIGURED', 'base_url': origin}
        identity_key = current[2] if current else secrets.token_hex(32)
        payload = json.dumps({'origin': origin, 'identity_key': identity_key, 'token': token},
                             separators=(',', ':'))
        backend.put(keychain.scope, Secret(payload))
    except Exception:
        raise WCEError('VIDEO_RELAY_KEYCHAIN_SAVE_FAILED') from None
    return {'state': 'CONFIGURED', 'base_url': origin}
