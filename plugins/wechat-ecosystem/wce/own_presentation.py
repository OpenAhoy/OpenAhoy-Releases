"""Local display data; never an account identity, permission or platform result."""
import base64
import binascii
import os
from pathlib import Path
import secrets
import struct
import stat
import unicodedata

from .bounded_file import identity, FileSource
from .contracts import WCEError
from .own_bootstrap_security import decode, path_check
from .own_connection_policy import locked, registry_path, resolve
from .own_connection_registry import check_member
from .own_png import decode_png, SIGNATURE
from .prepared_contracts import ID, strict_validate
from .service import canonical, digest

SIDE = 96
RGBA_BYTES = SIDE * SIDE * 4
MAX_PNG = 40960
MAX_FILE = 65536
MAX_REVISION = 2**53 - 1
FILENAME = 'presentation.json'


def display_name(value):
    if (type(value) is not str or not 1 <= len(value) <= 64 or not value.strip()
            or any(not c.isprintable() or unicodedata.category(c).startswith('C') for c in value)):
        raise WCEError('PRESENTATION_INVALID_NAME')
    return value.strip()


def b64decode(value, maximum):
    if type(value) is not str or not 0 < len(value) <= (maximum + 2) // 3 * 4:
        raise WCEError('PRESENTATION_INVALID_IMAGE')
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > maximum or base64.b64encode(raw).decode('ascii') != value:
            raise ValueError()
        return raw
    except (ValueError, UnicodeError, binascii.Error):
        raise WCEError('PRESENTATION_INVALID_IMAGE') from None


def validate_avatar(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {'width', 'height', 'rgba'}
            or type(value['width']) is not int or value['width'] != SIDE
            or type(value['height']) is not int or value['height'] != SIDE
            or len(b64decode(value['rgba'], RGBA_BYTES)) != RGBA_BYTES):
        raise WCEError('PRESENTATION_INVALID_IMAGE')
    return value


def from_png(value, guard):
    raw = b64decode(value, MAX_PNG)
    # Reject oversized dimensions before entering the existing bounded decoder.
    if (len(raw) < 33 or raw[:8] != SIGNATURE or raw[8:16] != b'\0\0\0\rIHDR'
            or struct.unpack_from('>II', raw, 16) != (SIDE, SIDE)):
        raise WCEError('PRESENTATION_INVALID_IMAGE')
    try:
        raster = decode_png(raw, guard)
    except WCEError as error:
        if error.code == 'OWN_RECONCILE_PNG_UNSUPPORTED':
            raise WCEError('PRESENTATION_INVALID_IMAGE') from None
        raise
    return {'width': SIDE, 'height': SIDE, 'rgba': base64.b64encode(raster.rgba).decode('ascii')}


def context(connection_id, registry=None):
    strict_validate(connection_id, ID)
    registry = Path(registry) if registry is not None else registry_path()
    policy = resolve(connection_id, registry, active=False)
    entry = check_member(policy, revocation=False) if policy.value['schema'] == 2 else None
    binding = digest({'registry': str(registry), 'identity': policy.data,
                      'owner_digest': policy.value.get('owner_digest')})
    return policy, binding, entry


def read_value(policy, binding):
    path = policy.root / FILENAME
    source = FileSource(policy.root)
    if source.root_identity != policy.root_pin:
        raise WCEError('PRESENTATION_IDENTITY_CHANGED')
    if not os.path.lexists(path):
        if path_check(policy.root, True) != policy.root_pin:
            raise WCEError('PRESENTATION_IDENTITY_CHANGED')
        return None
    try:
        before = path_check(path)
        if not 0 < before[2] <= MAX_FILE:
            raise WCEError('PRESENTATION_INVALID_DATA')
        raw = source.read(FILENAME)
        if (before != path_check(path)
                or path_check(policy.root, True) != policy.root_pin):
            raise WCEError('PRESENTATION_IDENTITY_CHANGED')
        value = decode(raw, MAX_FILE)
    except WCEError as error:
        if error.code == 'BOOTSTRAP_INVALID_JSON':
            raise WCEError('PRESENTATION_INVALID_DATA') from None
        raise
    if (type(value) is not dict or set(value) != {
            'schema', 'binding', 'revision', 'display_name', 'avatar'}
            or type(value['schema']) is not int or value['schema'] != 1):
        raise WCEError('PRESENTATION_INVALID_DATA')
    if value['binding'] != binding:
        raise WCEError('PRESENTATION_IDENTITY_CHANGED')
    try:
        if (type(value['revision']) is not int or not 1 <= value['revision'] <= MAX_REVISION
                or display_name(value['display_name']) != value['display_name']):
            raise WCEError('PRESENTATION_INVALID_DATA')
        validate_avatar(value['avatar'])
    except WCEError:
        raise WCEError('PRESENTATION_INVALID_DATA') from None
    return value


def project(policy, binding, entry):
    label = entry['label'] if entry else None
    has_label = bool(label and label not in {policy.data['connection_id'], policy.data['appid']})
    fallback = label if has_label else '未设置名称'
    base = {'display_name': fallback, 'avatar': None, 'revision': 0,
            'state': 'MISSING' if entry else 'LEGACY',
            'name_source': 'REGISTRY_LABEL' if has_label else 'UNSET',
            'avatar_source': 'UNSET'}
    try:
        value = read_value(policy, binding)
    except WCEError as error:
        if error.code != 'PRESENTATION_INVALID_DATA':
            raise
        return base | {'state': 'INVALID', 'revision': None}
    if value is not None:
        return base | {'display_name': value['display_name'], 'avatar': value['avatar'],
            'revision': value['revision'], 'state': 'SAVED', 'name_source': 'LOCAL_USER',
            'avatar_source': 'LOCAL_USER' if value['avatar'] else 'UNSET'}
    return base


def read(connection_id, registry=None):
    return project(*context(connection_id, registry))


def publish(policy, value, admit):
    """One atomic display replacement. A post-replace failure is not replayed."""
    parent = os.open(policy.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.presentation-' + secrets.token_hex(16)
    admitted = False
    try:
        if identity(os.fstat(parent)) != policy.root_pin:
            raise WCEError('PRESENTATION_IDENTITY_CHANGED')
        raw = (canonical(value) + '\n').encode()
        if len(raw) > MAX_FILE:
            raise WCEError('PRESENTATION_INVALID_DATA')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(raw)
                output.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        admit()
        if path_check(policy.root, True) != policy.root_pin:
            raise WCEError('PRESENTATION_IDENTITY_CHANGED')
        admitted = True
        os.replace(temporary, FILENAME, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        if (path_check(policy.root, True) != policy.root_pin
                or read_value(policy, value['binding']) != value):
            raise WCEError('PRESENTATION_WRITE_UNKNOWN')
    except Exception:
        if admitted:
            raise WCEError('PRESENTATION_WRITE_UNKNOWN') from None
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        finally:
            os.close(parent)


def save(value, registry=None, guard=lambda: None):
    if type(value) is not dict or set(value) != {
            'connection_id', 'expected_revision', 'display_name', 'avatar_png'}:
        raise WCEError('SETTINGS_INVALID_REQUEST')
    name = display_name(value['display_name'])
    revision = value['expected_revision']
    if type(revision) is not int or not 0 <= revision < MAX_REVISION:
        raise WCEError('PRESENTATION_STALE')
    guard()
    policy, binding, entry = context(value['connection_id'], registry)
    if entry is None:
        raise WCEError('CONNECTION_UPGRADE_REVIEW_REQUIRED')
    selected_registry = Path(registry) if registry is not None else registry_path()
    avatar = value['avatar_png']
    converted = from_png(avatar, guard) if avatar not in (None, '') else None
    display_lock = policy.root / 'presentation.lock'
    registry_lock = selected_registry.parent / 'connections.lock'
    parent_pins = [path_check(path.parent, True) for path in (display_lock, registry_lock)]
    with locked(display_lock, nonblocking=True) as display_fd, \
            locked(registry_lock, nonblocking=True) as registry_fd:
        def check_locks():
            try:
                for path, fd, parent_pin in zip((display_lock, registry_lock),
                                               (display_fd, registry_fd), parent_pins):
                    info = os.fstat(fd)
                    if (path_check(path.parent, True) != parent_pin
                            or identity(info) != path_check(path)[:2]
                            or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                        raise WCEError('PRESENTATION_IDENTITY_CHANGED')
            except OSError:
                raise WCEError('PRESENTATION_IDENTITY_CHANGED') from None

        def admit():
            current, current_binding, _ = context(value['connection_id'], selected_registry)
            if current_binding != binding or current.root_pin != policy.root_pin:
                raise WCEError('PRESENTATION_IDENTITY_CHANGED')
            original = read_value(current, binding)
            if (original['revision'] if original else 0) != revision:
                raise WCEError('PRESENTATION_STALE')
            guard()
            check_locks()
            return original

        old = admit()
        updated = {'schema': 1, 'binding': binding, 'revision': revision + 1,
                   'display_name': name,
                   'avatar': (old['avatar'] if old else None) if avatar is None else converted}
        publish(policy, updated, admit)
        try:
            check_locks()
        except WCEError:
            raise WCEError('PRESENTATION_WRITE_UNKNOWN') from None
        return {'state': 'PRESENTATION_SAVED', 'presentation': project(policy, binding, entry)}
