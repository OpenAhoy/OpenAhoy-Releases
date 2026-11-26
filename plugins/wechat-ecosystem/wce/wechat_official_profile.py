"""Read short-lived official profile snapshots from a provisioned trusted signer.

There is no network or credential operation on management overview. A trusted
adapter installs the signer and supplies snapshots for the exact local binding.
"""
from base64 import b64decode
from binascii import Error as Base64Error
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
from time import time

from .contracts import WCEError
from .own_identity_checkpoint import Reader
from .prepared_draft_fixture import decode_json

DIRECTORY = 'wechat-official-profiles'
SIGNER = 'signer.pem'


def _private(reader, path, limit):
    with reader.directory(path.parent) as directory:
        import stat
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or not 0 < info.st_size <= limit):
                raise ValueError
            with os.fdopen(os.dup(fd), 'rb') as stream:
                data = stream.read(limit + 1)
            checked = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_ctime_ns)
            if len(data) != info.st_size or identity(info) != identity(os.fstat(fd)) or identity(info) != identity(checked):
                raise ValueError
            return data
        finally:
            os.close(fd)


def _check_signature(public_key, signature, body):
    if not public_key.startswith(b'-----BEGIN PUBLIC KEY-----\n') or len(signature) not in (256, 384, 512):
        return False
    key_fd, key_write = os.pipe()
    sig_fd, sig_write = os.pipe()
    try:
        os.write(key_write, public_key)
        os.write(sig_write, signature)
        os.close(key_write); key_write = None
        os.close(sig_write); sig_write = None
        result = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256',
            '-verify', f'/dev/fd/{key_fd}', '-signature', f'/dev/fd/{sig_fd}'],
            input=body, pass_fds=(key_fd, sig_fd), timeout=2,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin'}, check=False)
        return result.returncode == 0
    finally:
        for fd in (key_fd, sig_fd, key_write, sig_write):
            if fd is not None:
                os.close(fd)


def _name(value, maximum):
    return value if (isinstance(value, str) and 0 < len(value) <= maximum and not re.search(r'[\x00-\x1f\x7f]', value)) else None


def _raster(value):
    if (isinstance(value, dict) and value.get('width') == value.get('height') == 96
            and isinstance(value.get('rgba'), str) and re.fullmatch(r'[A-Za-z0-9+/]{49152}', value['rgba'])):
        return {key: value[key] for key in ('width', 'height', 'rgba')}
    return None


def read_official_profile(registry, connection_id, appid, binding_revision, *, now=time):
    root = Path(registry).parent / DIRECTORY
    if not os.path.lexists(root / SIGNER):
        return {'state': 'SERVICE_NOT_CONFIGURED'}
    reader = Reader(Path(registry).parent)
    try:
        key = _private(reader, root / SIGNER, 2048)
    except (WCEError, OSError, ValueError):
        return {'state': 'UNAVAILABLE'}
    filename = sha256(connection_id.encode()).hexdigest() + '.json'
    try:
        wrapped = decode_json(_private(reader, root / filename, 180000), 180000, max_nodes=16)
        if not isinstance(wrapped, dict) or set(wrapped) != {'payload', 'signature'}:
            return {'state': 'UNAVAILABLE'}
        body = b64decode(wrapped['payload'], validate=True)
        signature = b64decode(wrapped['signature'], validate=True)
        if len(body) > 108000 or not _check_signature(key, signature, body):
            return {'state': 'UNAVAILABLE'}
        value = decode_json(body, 108000, max_nodes=220)
        if (value.get('schema') != 1 or value.get('source') != 'WECHAT_AUTHORIZER_INFO'
                or value.get('connection_id') != connection_id or value.get('app_id') != appid
                or value.get('binding_revision') != binding_revision):
            return {'state': 'UNAVAILABLE'}
        instant, expiry, clock = value.get('observed_at'), value.get('expires_at'), now()
        if (type(instant) is not int or type(expiry) is not int
                 or not 0 < instant < expiry <= instant + 86400 or instant > clock + 60):
            return {'state': 'UNAVAILABLE'}
        if clock >= expiry:
            return {'state': 'STALE', 'observed_at': instant}
        state = value.get('state')
        if state in ('REVOKED', 'AUTH_REQUIRED'):
            return {'state': state, 'observed_at': instant}
        if state != 'ACTIVE':
            return {'state': 'UNAVAILABLE'}
        ids, original = value.get('permissions'), value.get('original_id')
        if (not isinstance(ids, list) or len(ids) > 128
                or any(type(key) is not int or not 0 < key < 2**31 for key in ids)
                or not re.fullmatch(r'gh_[A-Za-z0-9]{1,64}', original or '')
                or type(value.get('account_type')) is not int or value['account_type'] not in (0, 1, 2)):
            return {'state': 'UNAVAILABLE'}
        verification = value.get('verification')
        return {'state': state, 'observed_at': instant,
                'nickname': _name(value.get('nickname'), 128), 'principal_name': _name(value.get('principal_name'), 180),
                'original_id': original, 'account_type': value['account_type'],
                'verification': verification if type(verification) is int else None,
                'permissions': sorted(set(ids)), 'avatar': _raster(value.get('avatar')),
                'qrcode': _raster(value.get('qrcode')),
                'use_official': value.get('use_official') is True}
    except FileNotFoundError:
        return {'state': 'AUTH_REQUIRED'}
    except (WCEError, ValueError, Base64Error, OSError, TypeError, AttributeError, subprocess.SubprocessError):
        return {'state': 'UNAVAILABLE'}
