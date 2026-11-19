"""One device-local choice for future music creation."""
import os

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional

PROVIDERS = ('suno', 'ace-music')
MAX_REVISION = 2**53 - 1
_FILENAME = 'music-preferences.json'


def read(root):
    try:
        if os.path.lexists(root):
            path_check(root, True)
        record = read_optional(root / _FILENAME)
        if record is None:
            return {'state': 'READY', 'provider': 'suno', 'revision': 0}
        if (type(record) is not dict or set(record) != {'schema', 'provider', 'revision'}
                or type(record['schema']) is not int or record['schema'] != 1
                or record['provider'] not in PROVIDERS or type(record['revision']) is not int
                or not 1 <= record['revision'] <= MAX_REVISION):
            raise WCEError('MUSIC_PREFERENCES_INVALID')
        return {'state': 'READY', 'provider': record['provider'], 'revision': record['revision']}
    except (OSError, ValueError, WCEError):
        return {'state': 'UNAVAILABLE'}


def save(root, provider, expected_revision):
    if provider not in PROVIDERS or type(expected_revision) is not int or not 0 <= expected_revision <= MAX_REVISION:
        raise WCEError('MUSIC_PREFERENCES_INVALID')
    try:
        if not os.path.lexists(root):
            try:
                os.mkdir(root, 0o700)
            except FileExistsError:
                pass
        root_pin = path_check(root, True)
        with locked(root / 'music-preferences.lock'):
            current = read(root)
            if current['state'] != 'READY':
                return current | {'save_status': 'FAILED'}
            if current['revision'] != expected_revision:
                return current | {'save_status': 'STALE'}
            if current['provider'] == provider:
                return current | {'save_status': 'UNCHANGED'}
            revision = expected_revision + 1
            if revision > MAX_REVISION:
                return current | {'save_status': 'FAILED'}
            atomic_write(root / _FILENAME, {'schema': 1, 'provider': provider, 'revision': revision},
                         expected_parent=root_pin)
            return read(root) | {'save_status': 'SAVED'}
    except (OSError, ValueError, WCEError):
        # A failed fsync/readback can race or occur after rename. Show disk state.
        return read(root) | {'save_status': 'FAILED'}
