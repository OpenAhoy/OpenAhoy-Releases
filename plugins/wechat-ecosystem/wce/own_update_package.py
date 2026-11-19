"""Verify update payloads and preserve an installed cache across Codex eviction."""
from contextlib import contextmanager
from ctypes import CDLL, c_char_p, c_int, c_uint, get_errno
from dataclasses import dataclass
import errno
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
RENAME_EXCL = 0x00000004
RETENTION_PARENT = 'openahoy-retained-cache'
RETENTION_CODES = frozenset({
    'UPDATE_OLD_CACHE_RETENTION_FAILED',
    'UPDATE_CACHE_ARCHIVE_DIRECTORY',
    'UPDATE_CACHE_STAGE_PREVIOUS',
    'UPDATE_CACHE_RECHECK_CHANGED',
    'UPDATE_CACHE_ARCHIVE_SWAP',
    'UPDATE_CACHE_ARCHIVE_VERIFY',
    'UPDATE_CACHE_OLD_LAUNCH_RESTORE',
})


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


@contextmanager
def retention_stage(code):
    try:
        yield
    except (OSError, WCEError, AttributeError, ValueError, TypeError):
        raise WCEError(code) from None


def rename_directory(source, target, operation):
    rename = CDLL(None, use_errno=True).renamex_np
    rename.argtypes = [c_char_p, c_char_p, c_uint]
    rename.restype = c_int
    if rename(os.fsencode(source), os.fsencode(target), operation):
        error = get_errno()
        raise OSError(error, os.strerror(error))


def private_retention_directory(path, device):
    info = path.lstat()
    check(path.resolve() == path and safe_type(info, directory=True)
          and stat.S_IMODE(info.st_mode) == 0o700 and info.st_dev == device)


def retain_previous_cache(old, version, package, rollback):
    # The host retires version paths even if there is no Python cache.
    # Archive the original directory atomically and prepare a clean launch copy.
    with retention_stage('UPDATE_CACHE_ARCHIVE_DIRECTORY'):
        parent = old.parents[3] / RETENTION_PARENT
        parent.mkdir(mode=0o700, exist_ok=True)
        private_retention_directory(parent, package.root_pin[0])
        container = Path(tempfile.mkdtemp(prefix=old.parents[1].name + '-' + version + '-', dir=parent))
    archived = container / 'original'
    standby = container / 'standby'
    with retention_stage('UPDATE_CACHE_STAGE_PREVIOUS'):
        clean = verify_package(rollback, version, package.manifest)
        for path in (archived, standby):
            path.mkdir(mode=0o700)
            copy_declared(rollback, path, clean)
            verify_package(path, version, package.manifest)
    with retention_stage('UPDATE_CACHE_RECHECK_CHANGED'):
        current = verify_runtime(old, version, package.manifest)
        # Reading a file may change atime. Compare the same integrity
        # fingerprints as read_declared(), including inode, mtime and ctime.
        check(current.root_pin == package.root_pin and current.caches == package.caches
              and current.declared.keys() == package.declared.keys()
              and all(fingerprint(info) == fingerprint(current.declared[name])
                      for name, info in package.declared.items()))
    with retention_stage('UPDATE_CACHE_ARCHIVE_SWAP'):
        rename_directory(old, archived, RENAME_SWAP)
    with retention_stage('UPDATE_CACHE_ARCHIVE_VERIFY'):
        check(archived.lstat().st_ino == package.root_pin[1])
    return container.name


def restore_previous_launch(old, version, manifest, container_name, verify_modes):
    with retention_stage('UPDATE_CACHE_OLD_LAUNCH_RESTORE'):
        check(type(version) is str and VERSION.fullmatch(version)
              and type(manifest) is str and SHA.fullmatch(manifest))
        prefix = re.escape(old.parents[1].name + '-' + version + '-')
        check(type(container_name) is str and re.fullmatch(prefix + r'[a-z0-9_]{8}', container_name))
        parent = old.parent
        info = parent.lstat()
        check(parent.resolve() == parent and safe_type(info, directory=True))
        retained = old.parents[3] / RETENTION_PARENT
        container = retained / container_name
        for path in (retained, container):
            private_retention_directory(path, info.st_dev)
        archived = container / 'original'
        if not os.path.lexists(old):
            standby = container / 'standby'
            if not os.path.lexists(standby):
                # Codex can prune the compatibility path again on a subsequent
                # install of the same release. Rebuild from the retained original.
                original = verify_runtime(archived, version, manifest)
                with tempfile.TemporaryDirectory(prefix='launch-', dir=container) as scratch:
                    rebuilt = Path(scratch) / 'standby'
                    rebuilt.mkdir(mode=0o700)
                    copy_declared(archived, rebuilt, original)
                    rename_directory(rebuilt, standby, RENAME_EXCL)
            verify_package(standby, version, manifest)
            verify_modes(standby)
            try:
                rename_directory(standby, old, RENAME_EXCL)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise
        verify_runtime(old, version, manifest)
        verify_modes(old)
        verify_runtime(archived, version, manifest)
