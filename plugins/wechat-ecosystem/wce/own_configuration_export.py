"""Explicit app-only non-secret configuration artifact; no account mutation.

The fixed Downloads file itself is the receipt for an uncertain export. No
export database, path parameter, server, credential access or rule save exists.
"""
import hashlib
import ctypes
import json
import os
from pathlib import Path
import re
import stat

from .contracts import WCEError
from .own_production_rules import CONTROL, SECRET, FIELDS
from .own_bootstrap_security import unique
from .tools import schema

SPEC = schema({'connection_id': {'type': 'string', 'minLength': 1, 'maxLength': 128},
    'export_id': {'type': 'string', 'pattern': '^config-[a-f0-9]{32}$'},
    'action': {'type': 'string', 'enum': ['write', 'query']},
    'configuration': {'type': 'string'}})
RECEIPT = 'com.openahoy.configuration-export'


def _receipt(fd, binding=None):
    """Fixed 32-byte receipt using public macOS fd APIs (stdlib lacks xattrs)."""
    library = ctypes.CDLL(None, use_errno=True)
    function = library.fsetxattr if binding is not None else library.fgetxattr
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                         ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    function.restype = ctypes.c_int if binding is not None else ctypes.c_ssize_t
    if binding is not None and len(binding) != 32:
        raise WCEError('CONFIG_EXPORT_CONFLICT')
    buffer = ctypes.create_string_buffer(binding, 32) if binding is not None else ctypes.create_string_buffer(32)
    result = function(fd, RECEIPT.encode('ascii'), buffer, 32, 0, 0)
    if result < 0:
        raise OSError(ctypes.get_errno(), 'Export receipt unavailable')
    if binding is None:
        if result != 32:
            raise WCEError('CONFIG_EXPORT_CONFLICT')
        return buffer.raw


def configuration(raw):
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if type(value) is dict and value.get('format') == 'openahoy.x-operating':
            from .x_operating_config import configuration as x_configuration
            return x_configuration(raw)
        if (type(value) is not dict or set(value) != {
                'format', 'schema_version', 'platform', 'account_name', 'fields'}
                or value['format'] != 'openahoy.production-preferences'
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['platform'] != 'wechat_official_account'
                or type(value['account_name']) is not str or not value['account_name'].strip()
                or type(value['fields']) is not dict or set(value['fields']) != set(FIELDS)):
            raise ValueError()
        for text in (value['account_name'], *value['fields'].values()):
            if type(text) is not str or CONTROL.search(text) or SECRET.search(text):
                raise ValueError()
            text.encode('utf-8')
        return value, raw.encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError, WCEError):
        raise WCEError('CONFIG_EXPORT_INVALID') from None


def validate(value):
    # Generic strict_validate has an implicit 64KiB default; no configuration
    # total quota is introduced by this closed, local envelope.
    if (type(value) is not dict or set(value) != {
            'connection_id', 'export_id', 'action', 'configuration'}
            or type(value['connection_id']) is not str or not 0 < len(value['connection_id']) <= 128
            or type(value['export_id']) is not str or re.fullmatch(r'config-[a-f0-9]{32}', value['export_id']) is None
            or type(value['action']) is not str or value['action'] not in {'write', 'query'}
            or type(value['configuration']) is not str):
        raise WCEError('CONFIG_EXPORT_INVALID')


def content_frame(message, metadata_limit):
    """Typed use of the existing content codec envelope; strictly no IO."""
    try:
        if (type(message) is not dict or set(message) != {'jsonrpc', 'id', 'method', 'params'}
                or message['jsonrpc'] != '2.0' or message['method'] != 'tools/call'
                or type(message['id']) not in (str, int)):
            return False
        params = message['params']
        if (type(params) is not dict or set(params) not in ({'name', 'arguments'}, {'name', 'arguments', '_meta'})
                or params['name'] != 'wce.ui.platform.action'):
            return False
        if '_meta' in params and (type(params['_meta']) is not dict
                or len(json.dumps(params['_meta'], ensure_ascii=False, allow_nan=False).encode()) > metadata_limit):
            return False
        args = params['arguments']
        if (type(args) is not dict or set(args) != {'platform_id', 'operation', 'arguments'}
                or args['platform_id'] != 'wechat_official_account' or args['operation'] != 'EXPORT_CONFIG'):
            return False
        validate(args['arguments'])
        configuration(args['arguments']['configuration'])
        return True
    except (WCEError, ValueError, TypeError, UnicodeError, RecursionError):
        return False


def _directory(path):
    """Open each fixed component without following symlinks."""
    if not path.is_absolute() or '..' in path.parts:
        raise WCEError('CONFIG_EXPORT_DIRECTORY_UNAVAILABLE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise WCEError('CONFIG_EXPORT_DIRECTORY_UNAVAILABLE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(folder, filename, raw, binding, temporary=None):
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink not in {1, 2} or info.st_mode & 0o077 or info.st_size != len(raw)):
            raise WCEError('CONFIG_EXPORT_CONFLICT')
        if info.st_nlink == 2:
            try:
                alias = os.stat(temporary, dir_fd=folder, follow_symlinks=False) if temporary else None
            except FileNotFoundError:
                alias = None
            if alias is None or (alias.st_dev, alias.st_ino) != (info.st_dev, info.st_ino):
                raise WCEError('CONFIG_EXPORT_CONFLICT')
        if _receipt(fd) != binding:
            raise WCEError('CONFIG_EXPORT_CONFLICT')
        observed = hashlib.sha256()
        remaining = len(raw) + 1
        while remaining and (part := os.read(fd, min(65536, remaining))):
            observed.update(part)
            remaining -= len(part)
        if observed.hexdigest() != hashlib.sha256(raw).hexdigest():
            raise WCEError('CONFIG_EXPORT_CONFLICT')
        return info
    finally:
        os.close(fd)


def export(value, rows, *, downloads=None, platform_id='wechat_official_account', artifact='configuration'):
    """downloads is trusted test injection, never a tool argument."""
    validate(value)
    config, raw = configuration(value['configuration'])
    if config['platform'] != platform_id or artifact not in ('configuration', 'skill'):
        raise WCEError('CONFIG_EXPORT_INVALID')
    if artifact == 'skill':
        if platform_id != 'x': raise WCEError('CONFIG_EXPORT_INVALID')
        from .x_operating_config import skill
        raw = skill(config).encode('utf-8')
    try:
        binding = hashlib.sha256(value['connection_id'].encode('utf-8')).digest()
    except UnicodeError:
        raise WCEError('CONFIG_EXPORT_INVALID') from None
    selected = next((r for r in rows if r['connection_id'] == value['connection_id']), None)
    presented = selected.get('presentation', {}) if selected else {}
    name = presented.get('display_name')
    if platform_id == 'x':
        if not selected or selected.get('platform_id') != 'x' or not name or name != config['account_name']:
            raise WCEError('CONFIG_EXPORT_ACCOUNT_MISMATCH')
    elif (presented.get('state') not in {'SAVED', 'MISSING', 'LEGACY'}
            or presented.get('name_source') not in {'LOCAL_USER', 'REGISTRY_LABEL'}
            or not name or name != config['account_name']
            or sum(r.get('presentation', {}).get('display_name') == name for r in rows) != 1
            or name == '未命名公众号 · ' + str((selected or {}).get('account_id', ''))[-8:]):
        raise WCEError('CONFIG_EXPORT_ACCOUNT_MISMATCH')
    nonce = value['export_id'].removeprefix('config-')
    filename = ('OpenAhoy-X-Skill-' + nonce + '.md' if artifact == 'skill'
                else 'OpenAhoy-配置-' + nonce + '.json')
    temporary = '.openahoy-' + nonce + '.partial'
    directory = Path(downloads) if downloads is not None else Path.home() / 'Downloads'
    folder = None
    created = None
    published = False
    try:
        folder = _directory(directory)
        folder_pin = os.fstat(folder)
        def check_directory():
            current = os.stat(directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (folder_pin.st_dev, folder_pin.st_ino):
                raise WCEError('CONFIG_EXPORT_DIRECTORY_CHANGED')
        check_directory()
        try:
            prior = _read(folder, filename, raw, binding, temporary)
            if prior.st_nlink == 2:
                # Recover only our exact, fully verified published alias. A
                # query never creates another file or writes field contents.
                try:
                    alias = os.stat(temporary, dir_fd=folder, follow_symlinks=False)
                    if (alias.st_dev, alias.st_ino) != (prior.st_dev, prior.st_ino):
                        raise WCEError('CONFIG_EXPORT_CONFLICT')
                    os.unlink(temporary, dir_fd=folder)
                    os.fsync(folder)
                except FileNotFoundError:
                    pass
                _read(folder, filename, raw, binding)
        except FileNotFoundError:
            if value['action'] == 'query':
                try:
                    os.stat(temporary, dir_fd=folder, follow_symlinks=False)
                    state = 'CONFIG_EXPORT_IN_PROGRESS'
                except FileNotFoundError:
                    state = 'CONFIG_EXPORT_NOT_FOUND'
                return {'state': state, 'export_id': value['export_id'], 'filename': filename}
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=folder)
            try:
                created = os.fstat(fd)
                offset = 0
                while offset < len(raw):
                    count = os.write(fd, raw[offset:])
                    if count <= 0:
                        raise OSError()
                    offset += count
                _receipt(fd, binding)
                os.fsync(fd)
            finally:
                os.close(fd)
            check_directory()
            # link is exclusive: it cannot overwrite a user file or symlink.
            os.link(temporary, filename, src_dir_fd=folder, dst_dir_fd=folder,
                    follow_symlinks=False)
            published = True
            os.unlink(temporary, dir_fd=folder)
            created = None
            os.fsync(folder)
            _read(folder, filename, raw, binding)
        check_directory()
        return {'state': 'CONFIG_EXPORTED', 'export_id': value['export_id'],
                'filename': filename, 'sha256': hashlib.sha256(raw).hexdigest(),
                'utf8_bytes': len(raw), 'destination': 'Downloads'}
    except WCEError:
        raise
    except OSError:
        raise WCEError('CONFIG_EXPORT_RESULT_UNKNOWN' if published else
                       'CONFIG_EXPORT_UNAVAILABLE') from None
    finally:
        if folder is not None:
            if created is not None:
                try:
                    current = os.stat(temporary, dir_fd=folder, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                        os.unlink(temporary, dir_fd=folder)
                except OSError:
                    pass
            os.close(folder)
