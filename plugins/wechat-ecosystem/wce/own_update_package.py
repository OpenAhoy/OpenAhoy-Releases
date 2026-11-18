"""Verify update payloads and preserve an installed cache across Codex eviction."""
from contextlib import contextmanager
from ctypes import CDLL, c_char_p, c_int, c_uint
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from .contracts import WCEError
from .own_updates import PLUGIN, REMOTE, SHA, VERSION, UpdateCheckUnavailable, _git, _tag_revision, pinned_release

MANIFEST = 'package-manifest.json'
PYC = re.compile(r'(.+)\.cpython-[0-9]{2,4}t?(?:\.opt-[12])?\.pyc')
RENAME_SWAP = 0x00000002  # macOS renamex_np(2)


@contextmanager
def package_errors(code):
    try:
        yield
    except (OSError, ValueError, TypeError, RecursionError, KeyError):
        raise WCEError(code) from None


def check(condition, code='UPDATE_PACKAGE_INVALID'):
    if not condition:
        raise WCEError(code)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def safe_type(info, directory=False):
    return ((stat.S_ISDIR(info.st_mode) if directory else
             stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            and info.st_uid == os.getuid() and not info.st_mode & 0o7022)


def read_declared(path, expected):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        check(fingerprint(os.fstat(source.fileno())) == fingerprint(expected))
        data = source.read()
        check(fingerprint(os.fstat(source.fileno())) == fingerprint(expected))
    return data


def unique_fields(pairs):
    result = dict(pairs)
    check(len(result) == len(pairs))
    return result


def package_name(name):
    path = PurePosixPath(name)
    return (path.parts and not path.is_absolute() and path.as_posix() == name
            and '..' not in path.parts and '\\' not in name and '\x00' not in name
            and '__pycache__' not in path.parts and path.suffix != '.pyc')


def declared_manifest(raw):
    info = json.loads(raw, object_pairs_hook=unique_fields)
    check(type(info) is dict and info.keys() == {'schema', 'files'}
          and type(info['schema']) is int and info['schema'] == 1)
    files = info['files']
    check(type(files) is dict and 'plugin.json' in files and MANIFEST not in files
          and all(package_name(name) and type(digest) is str and SHA.fullmatch(digest)
                  for name, digest in files.items()))
    return files


def cache_source(name):
    path = PurePosixPath(name)
    match = PYC.fullmatch(path.name)
    if path.parent.name == '__pycache__' and match:
        return (path.parent.parent / (match[1] + '.py')).as_posix()
    return None


def walk_error(error):
    raise error


def scan_tree(root):
    root_stat = root.lstat()
    check(root.resolve() == root and safe_type(root_stat, directory=True))
    entries, directories = {}, set()
    for directory, children, names in os.walk(root, onerror=walk_error):
        directory = Path(directory)
        for name in children:
            path = directory / name
            check(safe_type(path.lstat(), directory=True))
            directories.add(path.relative_to(root).as_posix())
        for name in names:
            path = directory / name
            info = path.lstat()
            check(safe_type(info))
            entries[path.relative_to(root).as_posix()] = info
    check(fingerprint(root.lstat()) == fingerprint(root_stat))
    return root_stat, entries, directories


@dataclass(frozen=True)
class Package:
    manifest: str
    declared: dict
    caches: dict
    root_pin: tuple


def inspect_package(root, version, manifest_sha, *, installed=False):
    with package_errors('UPDATE_PACKAGE_INVALID'):
        root_stat, entries, directories = scan_tree(root)
        raw = read_declared(root / MANIFEST, entries[MANIFEST])
        manifest = sha256(raw).hexdigest()
        check(manifest_sha is None or manifest == manifest_sha, 'UPDATE_MANIFEST_MISMATCH')
        files = declared_manifest(raw)
        required = files.keys() | {MANIFEST}
        extras = entries.keys() - required
        check(required <= entries.keys() and (not extras or
              (installed and all(cache_source(name) in files for name in extras))))
        allowed = {parent.as_posix() for name in entries for parent in PurePosixPath(name).parents}
        check(directories <= allowed)
        for name, digest in files.items():
            check(sha256(read_declared(root / name, entries[name])).hexdigest() == digest,
                  'UPDATE_PAYLOAD_MISMATCH')
        identity = json.loads(read_declared(root / 'plugin.json', entries['plugin.json']))
        check(type(identity) is dict and identity.get('name') == PLUGIN and identity.get('version') == version,
              'UPDATE_PACKAGE_IDENTITY')
        return Package(manifest, {name: entries[name] for name in required},
                       {name: fingerprint(entries[name]) for name in extras}, fingerprint(root_stat))


def verify_package(root, version, manifest_sha=None):
    return inspect_package(root, version, manifest_sha)


def verify_runtime(root, version, manifest_sha):
    check(type(manifest_sha) is str and SHA.fullmatch(manifest_sha), 'UPDATE_MANIFEST_MISMATCH')
    return inspect_package(root, version, manifest_sha, installed=True)


def trusted_previous_manifest(version):
    """Only a public fixed release can vouch for a dirty installed package."""
    check(VERSION.fullmatch(version), 'UPDATE_OLD_CACHE_UNVERIFIED')
    tag = 'refs/tags/v' + version
    try:
        if _git(['--get-url', REMOTE], 3).strip() != REMOTE.encode('ascii'):
            raise UpdateCheckUnavailable()
        revision = _tag_revision(_git(['--tags', REMOTE, tag, tag + '^{}'], 12), version)
        return pinned_release(version, revision)['package_manifest_sha256']
    except (UpdateCheckUnavailable, OSError, ValueError, KeyError):
        raise WCEError('UPDATE_OLD_CACHE_UNVERIFIED') from None


def copy_declared(source, target, package):
    for name, info in sorted(package.declared.items()):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('xb') as output:
            output.write(read_declared(source / name, info))
        path.chmod(stat.S_IMODE(info.st_mode))


def prepare_previous(old, version, rollback, verify_modes):
    try:
        previous = inspect_package(old, version, None, installed=True)
        verify_modes(old)
    except WCEError:
        raise WCEError('UPDATE_OLD_CACHE_INVALID') from None
    if previous.caches:
        check(trusted_previous_manifest(version) == previous.manifest, 'UPDATE_OLD_CACHE_UNVERIFIED')
    try:
        if not os.path.lexists(rollback):
            with tempfile.TemporaryDirectory(prefix='rollback-', dir=rollback.parent) as scratch:
                stage = Path(scratch) / 'package'
                stage.mkdir(mode=0o700)
                copy_declared(old, stage, previous)
                verify_package(stage, version, previous.manifest)
                verify_modes(stage)
                stage.rename(rollback)
        verify_package(rollback, version, previous.manifest)
        verify_modes(rollback)
    except (OSError, WCEError):
        raise WCEError('UPDATE_ROLLBACK_PACKAGE_INVALID') from None
    return previous


def retain_previous_cache(old, version, package, rollback):
    if not package.caches:
        return
    # Codex evicts old versions on activation. Keep the original inode outside
    # its version store and leave a clean copy at the current registration.
    try:
        parent = old.parents[3] / 'openahoy-retained-cache'
        parent.mkdir(mode=0o700, exist_ok=True)
        info = parent.lstat()
        check(parent.resolve() == parent and safe_type(info, directory=True)
              and stat.S_IMODE(info.st_mode) == 0o700 and info.st_dev == package.root_pin[0])
        container = Path(tempfile.mkdtemp(prefix=old.parents[1].name + '-' + version + '-', dir=parent))
        archived = container / 'original'
        archived.mkdir(mode=0o700)
        clean = verify_package(rollback, version, package.manifest)
        copy_declared(rollback, archived, clean)
        verify_package(archived, version, package.manifest)
        check(verify_runtime(old, version, package.manifest) == package)
        swap = CDLL(None, use_errno=True).renamex_np
        swap.argtypes = [c_char_p, c_char_p, c_uint]
        swap.restype = c_int
        check(swap(os.fsencode(old), os.fsencode(archived), RENAME_SWAP) == 0)
        check(archived.lstat().st_ino == package.root_pin[1])
    except (OSError, WCEError, AttributeError):
        raise WCEError('UPDATE_OLD_CACHE_RETENTION_FAILED') from None
