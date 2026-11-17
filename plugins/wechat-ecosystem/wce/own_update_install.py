"""Install a verified OpenAhoy release with the official Codex CLI."""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import tomllib
from threading import Thread
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import BadZipFile, ZipFile

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional, read_registry, registry_path, resolve
from .own_connection_registry import mkdir
from .own_updates import OID, REMOTE, REPOSITORY, VERSION, _version, check

PLUGIN = 'wechat-ecosystem'
PUBLIC_MARKET = 'openahoy-distribution'
BUNDLED_CLI = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
ACTIVE = {'CHECKING', 'DOWNLOADING', 'VERIFYING', 'STAGED', 'WAITING_FOR_IDLE', 'INSTALLING'}
MAX_ASSET = 128 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
REQUEST_ID = re.compile(r'[0-9a-f]{32}')
SELECTOR = re.compile(r'wechat-ecosystem@([A-Za-z0-9_-]+)')
BUSY_CODES = {'CONNECTION_BUSY', 'CONNECTION_START_PENDING', 'UPDATE_BUSINESS_BUSY'}
UPDATE_HISTORY = {('BUSY', code) for code in BUSY_CODES} | {
    ('FAILED', 'CONNECTION_NOT_COMMITTED'), ('FAILED', 'UPDATE_ACTIVITY_UNVERIFIED')}
PREVIOUS_RECEIPT = 'UPDATE_PREVIOUS_INSTALL_RECEIPT'
RECEIPT_RACE_CODES = {'BOOTSTRAP_PATH_CHANGED', 'LOCAL_FILE_CHANGED', 'INVALID_LOCAL_FILE'}


def require(condition, code):
    if not condition:
        raise WCEError(code)


class ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        target = urlsplit(newurl)
        if (target.scheme != 'https' or target.netloc not in
                {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}):
            raise WCEError('UPDATE_SOURCE_UNSAFE')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def release(version, revision, folder, progress):
    tag = 'v' + version
    filename = f'openahoy-{version}-macos-arm64.zip'
    url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}'
    base = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}'
    opener = build_opener(ReleaseRedirect())
    with opener.open(base + '/RELEASE.json', timeout=15) as response:
        raw = response.read(32769)
    require(len(raw) <= 32768, 'UPDATE_RELEASE_INVALID')
    metadata = json.loads(raw)
    require(type(metadata) is dict, 'UPDATE_RELEASE_INVALID')
    expected = {'schema': 1, 'product': 'OpenAhoy', 'version': version, 'tag': tag,
                'repository': REPOSITORY, 'plugin': PLUGIN, 'platform': 'macos-arm64',
                'marketplace': PUBLIC_MARKET, 'marketplace_source': REMOTE,
                'plugin_path': './plugins/' + PLUGIN, 'asset': filename, 'asset_url': url,
                'contains_user_accounts': False}
    size = metadata.get('size')
    require(all(metadata.get(key) == value for key, value in expected.items())
            and type(size) is int and 0 < size <= MAX_ASSET
            and all(type(metadata.get(key)) is str and SHA.fullmatch(metadata[key])
                    for key in ('sha256', 'package_manifest_sha256')), 'UPDATE_RELEASE_INVALID')
    progress('DOWNLOADING', downloaded=0, total=size)
    archive = folder / filename
    checksum = sha256()
    deadline = time.monotonic() + 120
    with opener.open(url, timeout=15) as response, archive.open('xb') as output:
        downloaded = 0
        while block := response.read(256 * 1024):
            require(time.monotonic() <= deadline, 'UPDATE_DOWNLOAD_TIMEOUT')
            downloaded += len(block)
            require(downloaded <= size, 'UPDATE_ASSET_SIZE_MISMATCH')
            output.write(block)
            checksum.update(block)
            progress('DOWNLOADING', downloaded=downloaded, total=size)
    require(downloaded == size and checksum.hexdigest() == metadata['sha256'],
            'UPDATE_ASSET_HASH_MISMATCH')
    progress('VERIFYING')
    target = folder / 'plugins' / PLUGIN
    target.mkdir(parents=True)
    with ZipFile(archive) as source:
        prefix = '' if 'package-manifest.json' in source.namelist() else PLUGIN + '/'
        entries = source.infolist()
        require(sum(entry.file_size for entry in entries) <= MAX_ASSET, 'UPDATE_ARCHIVE_INVALID')
        manifest_path = prefix + 'package-manifest.json'
        manifest = source.read(manifest_path)
        require(sha256(manifest).hexdigest() == metadata['package_manifest_sha256'], 'UPDATE_MANIFEST_MISMATCH')
        files = json.loads(manifest)['files']
        require(len(entries) == len(files) + 1 and metadata.get('payload_count') == len(files)
                and {entry.filename for entry in entries} == {manifest_path, *(prefix + n for n in files)},
                'UPDATE_ARCHIVE_INVALID')
        for entry in entries:
            relative = entry.filename.removeprefix(prefix)
            posix = PurePosixPath(relative)
            mode = entry.external_attr >> 16
            require(bool(posix.parts) and posix.parts[0] != '.' and not posix.is_absolute() and '..' not in posix.parts and posix.as_posix() == relative
                    and '\\' not in relative and stat.S_ISREG(mode) and mode & 0o7000 == 0,
                    'UPDATE_ARCHIVE_INVALID')
            raw = source.read(entry)
            if entry.filename != manifest_path:
                require(sha256(raw).hexdigest() == files[relative], 'UPDATE_PAYLOAD_MISMATCH')
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as output:
                output.write(raw)
            path.chmod(0o700 if mode & 0o111 else 0o600)
    verify_package(target, version, metadata['package_manifest_sha256'])
    verify_launch_modes(target)
    return target, metadata['package_manifest_sha256']


def verify_package(root, version, manifest_sha=None):
    require(root.resolve() == root and root.is_dir(), 'UPDATE_PACKAGE_INVALID')
    metadata = root / 'package-manifest.json'
    require(metadata.is_file() and not metadata.is_symlink(), 'UPDATE_PACKAGE_INVALID')
    raw = metadata.read_bytes()
    require(manifest_sha is None or sha256(raw).hexdigest() == manifest_sha, 'UPDATE_MANIFEST_MISMATCH')
    files = json.loads(raw)['files']
    paths = list(root.rglob('*'))
    require(not any(path.is_symlink() for path in paths)
            and {path.relative_to(root).as_posix() for path in paths if path.is_file()}
            == files.keys() | {'package-manifest.json'}, 'UPDATE_PACKAGE_INVALID')
    require(all(sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in files.items()),
            'UPDATE_PAYLOAD_MISMATCH')
    identity = json.loads((root / 'plugin.json').read_bytes())
    require(identity.get('name') == PLUGIN and identity.get('version') == version, 'UPDATE_PACKAGE_IDENTITY')


def verify_launch_modes(root):
    names = ('scripts/wce_mcp.sh', 'native/inline-binding-crypto', 'native/openahoy-video-inspect',
             'native/OpenAhoyStorageRecovery.app/Contents/MacOS/OpenAhoyStorageRecovery')
    require((root/names[0]).is_file() and all(os.access(root/name, os.X_OK)
            for name in names if (root/name).is_file()), 'UPDATE_LAUNCHER_INVALID')


def cli(*args, timeout=90):
    executable = next((path for path in (BUNDLED_CLI, Path('/opt/homebrew/bin/codex'),
                                        Path('/usr/local/bin/codex')) if path.is_file()), None)
    require(executable is not None, 'UPDATE_CODEX_CLI_UNAVAILABLE')
    result = subprocess.run([str(executable), 'plugin', *args, '--json'], capture_output=True,
                            stdin=subprocess.DEVNULL, cwd=Path.home(), timeout=timeout)
    require(result.returncode == 0, 'UPDATE_CODEX_CLI_FAILED')
    return json.loads(result.stdout)


def read_market(path):
    info = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022, 'UPDATE_MARKETPLACE_UNSAFE')
    raw = path.read_bytes()
    require(path.lstat().st_ino == info.st_ino and path.read_bytes() == raw, 'UPDATE_MARKETPLACE_CHANGED')
    return raw, info


def replace_market(path, original, raw):
    before, info = read_market(path)
    require(before == original, 'UPDATE_MARKETPLACE_CHANGED')
    fd, temporary = tempfile.mkstemp(prefix='.openahoy-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode))
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        current, latest = read_market(path)
        require(current == before and latest.st_ino == info.st_ino, 'UPDATE_MARKETPLACE_CHANGED')
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _present(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _displaced_quiescent(policy, registry):
    """Prove an unadopted account has no serving broker without changing its files."""
    from .own_base_domain import DOMAIN
    from .own_bootstrap_ipc import socket_pin
    from .own_bootstrap_security import decode, private_read
    from .own_connection_broker import RUNTIME, SOCKET, socket_address
    from .own_connection_registry import metadata, transaction_path
    from .service import digest

    unknown = 'UPDATE_ACTIVITY_UNVERIFIED'
    root = policy.root
    runtime, endpoint = root / RUNTIME, root / SOCKET
    try:
        # This legacy operator has a different lifecycle and no matching broker lock.
        if any(_present(root / name) for name in ('runtime.json', 'operator.sock')):
            raise WCEError(unknown)
        present = (_present(runtime), _present(endpoint))
        if not any(present):
            return
        endpoint_pin = socket_pin(endpoint) if present[1] else None
        if endpoint_pin is not None:
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(socket_address(endpoint))
                except ConnectionRefusedError:
                    pass
                else:
                    raise WCEError('UPDATE_BUSINESS_BUSY')
        if present[0]:
            raw, runtime_pin = private_read(runtime)
            value = decode(raw)
            fields = {'schema', 'pid', 'instance', 'policy_digest', 'candidate_scope',
                      'identity_digest', 'root_pin'}
            valid = type(value) is dict and type(value.get('schema')) is int and (
                (value['schema'] == 2 and value.keys() == fields)
                or (value['schema'] == 3 and value.keys() == fields | {'domain'} and value.get('domain') == DOMAIN))
            require(valid and type(value['pid']) is int and value['pid'] > 0
                    and all(isinstance(value[key], str) and SHA.fullmatch(value[key])
                            for key in ('instance', 'policy_digest', 'candidate_scope', 'identity_digest'))
                    and type(value['root_pin']) is list and len(value['root_pin']) == 2
                    and all(type(pin) is int and pin >= 0 for pin in value['root_pin'])
                    and value['identity_digest'] == digest(policy.data), unknown)
            matches_current = value['root_pin'] == list(policy.root_pin)
            if not matches_current:
                # The old exact pin is evidence about this file only. It grants no
                # authority to use this account on the current storage volume.
                proof_path = transaction_path(registry, policy.value['transaction'])
                with locked(proof_path.with_suffix('.lock'), shared=True, existing=True,
                            readonly=True, nonblocking=True):
                    proof = metadata(proof_path) or {}
                    entry = (proof.get('policies') or {}).get(str(policy.path)) or {}
                    require(proof.get('state') == 'COMMITTED' and entry.get('after') == policy.value
                            and value['root_pin'] == (entry.get('pins') or {}).get('root'), unknown)
            try:
                os.kill(value['pid'], 0)
            except ProcessLookupError:
                pass
            else:
                # A recycled PID without a listening endpoint cannot identify the broker.
                raise WCEError(unknown)
            require(path_check(runtime) == runtime_pin, unknown)
        require((_present(runtime), _present(endpoint)) == present, unknown)
        if endpoint_pin is not None:
            require(socket_pin(endpoint) == endpoint_pin, unknown)
    except (OSError, TypeError, ValueError, OverflowError, KeyError, AttributeError, WCEError) as error:
        if getattr(error, 'code', None) == 'UPDATE_BUSINESS_BUSY':
            raise
        raise WCEError(unknown) from None


@contextmanager
def maintenance(registry):
    from .own_connection_broker import (STARTUP_SECONDS, _replace_idle_software_owner,
                                       _startup_gate, _startup_has_owner)
    from .own_connection_policy import load_policy
    from .own_connection_registry import MembershipProofError, inspect_storage_binding, revoked

    base = registry.parent
    paths = [base / name for name in ('connection-setup.lock', 'x-platform/connection.lock', 'project-context.lock',
                                      'xhs-platform/binding.lock')]
    paths.extend(sorted((base / 'xhs-platform/accounts').glob('*/account.lock')))
    with ExitStack() as held:
        def take(paths):
            for path in paths:
                if path.parent.is_dir():
                    held.enter_context(locked(path, nonblocking=True))

        take(paths)
        entries = read_registry(registry)['connections']
        policies, unavailable = [], []
        for cid, path in sorted(entries.items()):
            try:
                policies.append(resolve(cid, registry, active=False))
            except WCEError as error:
                displaced = isinstance(error, MembershipProofError) and error.check in {
                    'JOURNAL_DIRECTORY', 'ACCOUNT_ROOT', 'IMAGE_DIRECTORY', 'DATABASE'}
                if not displaced and error.code != 'CONNECTION_VOLUME_WITNESS_CHANGED':
                    raise
                if inspect_storage_binding(registry, cid) == 'PROOF_INCOMPLETE':
                    raise
                policy = load_policy(path, active=False)
                require(policy.data['connection_id'] == cid and policy.value['registry_path'] == str(registry),
                        'UPDATE_ACCOUNT_IDENTITY_CHANGED')
                unavailable.append(policy)

        # A displaced account cannot start or drain its broker. Hold its existing
        # exclusions directly for the software-only switch and demand quiescence.
        for policy in unavailable:
            root = policy.root
            for name in ('connection-start.lock', 'connection.lock', 'connection-policy.lock'):
                held.enter_context(locked(root / name, nonblocking=True, existing=True))
            for name in ('connection-import.lock', 'connection-token.lock', 'cover-read-authority.lock',
                         'presentation.lock', 'publication-settings-ops.lock', 'publication-dispatch.lock',
                         'draft-revision-journal.lock'):
                if os.path.lexists(root / name):
                    held.enter_context(locked(root / name, nonblocking=True, existing=True))
            _displaced_quiescent(policy, registry)
            require(not any(os.path.lexists(str(root / db) + ext)
                            for db in ('state.sqlite3', 'draft-revisions/revision.sqlite3',
                                       'current-draft-management/operations.sqlite3')
                            for ext in ('-wal', '-shm', '-journal')), 'UPDATE_BUSINESS_BUSY')
            require(load_policy(policy.path, active=False) == policy, 'UPDATE_ACCOUNT_IDENTITY_CHANGED')
        for policy in policies:
            if policy.value['enabled'] and not (policy.value['schema'] == 2 and revoked(policy)):
                deadline = time.monotonic() + STARTUP_SECONDS
                held.enter_context(_startup_gate(policy, deadline))
                if _startup_has_owner(policy):
                    _replace_idle_software_owner(policy, deadline)
        for policy in policies:
            take([policy.root / 'connection.lock', policy.root / 'connection-policy.lock'])
        take([base / name for name in ('connections.lock', 'production-rules.lock', 'video-ark/generation.lock')])
        require(not any((base / ('production-rules.sqlite3' + extension)).exists()
                        for extension in ('-wal', '-shm', '-journal')), 'UPDATE_BUSINESS_BUSY')
        yield


def installed(rows):
    return [row for row in rows['installed'] if row.get('name') == PLUGIN and row.get('enabled') is True]


def verify_installation(version, selector, manifest_sha, rows):
    match = SELECTOR.fullmatch(selector)
    require(match and VERSION.fullmatch(version) and SHA.fullmatch(manifest_sha), 'UPDATE_INSTALL_RECEIPT_INVALID')
    current = installed(rows)
    require(len(current) == 1 and current[0]['version'] == version and current[0]['pluginId'] == selector,
            'UPDATE_INSTALL_READBACK_FAILED')
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    target = codex_home / 'plugins/cache' / match[1] / PLUGIN / version
    verify_package(target, version, manifest_sha)
    verify_launch_modes(target)


def _verify_git_market(run, codex_home, name, source, ref, version, manifest):
    raw, _ = read_market(codex_home / 'config.toml')
    registration = tomllib.loads(raw.decode())['marketplaces'][name]
    require(registration.get('source_type') == 'git' and registration.get('source') == source
            and registration.get('ref') == ref, 'UPDATE_MARKETPLACE_CHANGED')
    rows = [item for item in run('marketplace', 'list')['marketplaces'] if item['name'] == name]
    require(len(rows) == 1 and rows[0].get('marketplaceSource', {}).get('source') == source
            and rows[0]['marketplaceSource'].get('sourceType') == 'git', 'UPDATE_MARKETPLACE_CHANGED')
    root = Path(rows[0]['root'])
    data = json.loads(read_market(root / '.agents/plugins/marketplace.json')[0])
    require(data['name'] == name and len(data['plugins']) == 1 and data['plugins'][0]['name'] == PLUGIN
            and data['plugins'][0]['source'] == {'source': 'local', 'path': './plugins/' + PLUGIN},
            'UPDATE_MARKETPLACE_CHANGED')
    target = root / 'plugins' / PLUGIN
    verify_package(target, version, manifest)
    verify_launch_modes(target)


def install(previous, version, target, manifest_sha, registry, folder, progress, *, run=cli):
    active = installed(run('list'))
    require(len(active) == 1 and active[0]['version'] == previous, 'UPDATE_INSTALLED_VERSION_CHANGED')
    row = active[0]
    selector = row['pluginId']
    market_name = selector.removeprefix(PLUGIN + '@')
    require(re.fullmatch(r'[A-Za-z0-9_-]+', market_name) and selector == PLUGIN + '@' + market_name,
            'UPDATE_MARKETPLACE_UNSUPPORTED')
    markets = [item for item in run('marketplace', 'list')['marketplaces'] if item['name'] == market_name]
    require(len(markets) == 1, 'UPDATE_MARKETPLACE_UNSUPPORTED')
    market = markets[0]
    path = Path(market['root']) / '.agents/plugins/marketplace.json'
    raw, _ = read_market(path)
    data = json.loads(raw)
    matches = [item for item in data['plugins'] if item['name'] == PLUGIN]
    require(data['name'] == market_name and len(matches) == 1, 'UPDATE_MARKETPLACE_UNSUPPORTED')
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    market_source = market.get('marketplaceSource') or {}
    git_market = market_name == PUBLIC_MARKET and market_source.get('sourceType') == 'git'
    if git_market:
        config_raw, _ = read_market(codex_home / 'config.toml')
        registration = tomllib.loads(config_raw.decode())['marketplaces'][market_name]
        old_ref = registration.get('ref')
        source = registration.get('source')
        require(registration.get('source_type') == 'git'
                and source == market_source.get('source')
                and market_source.get('source') in (REMOTE, REMOTE.removesuffix('.git'), REPOSITORY)
                and type(old_ref) is str and (old_ref == 'v' + previous or OID.fullmatch(old_ref))
                and len(data['plugins']) == 1, 'UPDATE_MARKETPLACE_UNSUPPORTED')
        require(matches[0]['source'] == {'source': 'local', 'path': './plugins/' + PLUGIN},
                'UPDATE_MARKETPLACE_UNSUPPORTED')
    else:
        require(market_source.get('sourceType') in (None, 'local')
                and path.is_relative_to(Path.home())
                and matches[0]['source'].get('source') in ('local', 'git-subdir'),
                'UPDATE_MARKETPLACE_UNSUPPORTED')
    old = codex_home / 'plugins/cache' / market_name / PLUGIN / previous
    verify_package(old, previous)
    rollback = folder / 'previous'
    if not rollback.exists():
        shutil.copytree(old, rollback)
    verify_package(rollback, previous)
    rollback_manifest = sha256((rollback / 'package-manifest.json').read_bytes()).hexdigest()
    progress('WAITING_FOR_IDLE')
    with maintenance(registry):
        require(read_market(path)[0] == raw and installed(run('list')) == active, 'UPDATE_MARKETPLACE_CHANGED')
        if git_market:
            require(read_market(codex_home / 'config.toml')[0] == config_raw, 'UPDATE_MARKETPLACE_CHANGED')
        verify_package(target, version, manifest_sha)
        if not git_market and not target.is_relative_to(path.parents[2]):
            # The CLI resolves local plugin sources within the marketplace root.
            # Keep the download private and move only the verified package into
            # a contained source folder under that registered local marketplace.
            market_home = path.parents[2]
            require(market_home.stat().st_uid == os.getuid() and not market_home.stat().st_mode & 0o022,
                    'UPDATE_MARKETPLACE_UNSAFE')
            staged = Path(tempfile.mkdtemp(prefix='.openahoy-release-', dir=path.parent))
            staged_target = staged / PLUGIN
            shutil.copytree(target, staged_target)
            verify_package(staged_target, version, manifest_sha)
            target = staged_target
        progress('INSTALLING', plugin_id=selector, manifest_sha256=manifest_sha)
        if git_market:
            def restore_git_market(remove_target=False):
                if remove_target:
                    # Only remove the Git registration we just selected.
                    current = tomllib.loads(read_market(codex_home / 'config.toml')[0].decode())[
                        'marketplaces'][market_name]
                    require(current.get('source_type') == 'git' and current.get('source') == source
                            and current.get('ref') == target_ref, 'UPDATE_MARKETPLACE_CHANGED')
                    run('marketplace', 'remove', market_name)
                run('marketplace', 'add', source, '--ref', old_ref)
                _verify_git_market(run, codex_home, market_name, source, old_ref, previous, rollback_manifest)
                if not installed(run('list')):
                    run('add', selector)
                verify_installation(previous, selector, rollback_manifest, run('list'))

            target_ref = 'v' + version
            run('marketplace', 'remove', market_name)
            try:
                run('marketplace', 'add', source, '--ref', target_ref)
            except WCEError:
                if not any(entry['name'] == market_name for entry in run('marketplace', 'list')['marketplaces']):
                    restore_git_market()
                    raise WCEError('UPDATE_INSTALL_REJECTED') from None
                raise
            try:
                # Verify the bytes the host will actually install, before activating them.
                _verify_git_market(run, codex_home, market_name, source, target_ref, version, manifest_sha)
            except (WCEError, OSError, ValueError, KeyError, TypeError):
                if not (old.parent / version).exists():
                    restore_git_market(remove_target=True)
                    raise WCEError('UPDATE_INSTALL_REJECTED') from None
                raise
        else:
            matches[0]['source'] = {'source': 'local', 'path': './' + os.path.relpath(target, path.parents[2])}
            updated = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
            replace_market(path, raw, updated)

        try:
            run('add', selector)
        except WCEError:
            new = old.parent / version
            current = installed(run('list'))
            old_active = len(current) == 1 and current[0]['pluginId'] == selector and current[0]['version'] == previous
            if not new.exists() and (old_active or (git_market and not current)):
                if git_market:
                    restore_git_market(remove_target=True)
                else:
                    replace_market(path, updated, raw)
                raise WCEError('UPDATE_INSTALL_REJECTED') from None
            raise
        verify_installation(version, selector, manifest_sha, run('list'))
    progress('INSTALLED_RELOAD_REQUIRED')


class UpdateInstaller:
    """One persistent local receipt shared across panels and server processes."""

    def __init__(self, installed_version, registry=None, *, download=release, switch=install, checker=check,
                 readback=verify_installation, run=cli):
        self.version = installed_version
        self.registry = Path(registry or registry_path())
        self.root = self.registry.parent / 'software-updates'
        self.download, self.switch, self.checker = download, switch, checker
        self.readback, self.run = readback, run

    def _receipt(self):
        path = self.root / 'status.json'
        try:
            value = read_optional(path)
        except WCEError as error:
            if error.code not in RECEIPT_RACE_CODES:
                raise
            # Progress replaces the file atomically. Retry the checked read
            # if it overlapped that replacement.
            value = read_optional(path)
        return value or {'state': 'IDLE'}

    def _reconcile_installation(self, value):
        selector = value.get('plugin_id', '')
        manifest = value.get('manifest_sha256', '')
        match = SELECTOR.fullmatch(selector) if isinstance(selector, str) else None
        try:
            if match and isinstance(manifest, str) and SHA.fullmatch(manifest):
                # An exact receipt identifies one marketplace. Listing all
                # markets can block on unrelated sources during panel startup.
                rows = self.run('list', '--marketplace', match[1], timeout=12)
            else:
                # Older receipts lack the selector and manifest hash. A
                # previously verified success can be matched to its staged
                # package, but an old unknown has no proof of the write edge.
                if value['state'] != 'INSTALLED_RELOAD_REQUIRED':
                    return value
                version = value['version']
                require(VERSION.fullmatch(version), 'UPDATE_INSTALL_RECEIPT_INVALID')
                manifests = set()
                for stage in self.root.glob(version + '-*'):
                    if not OID.fullmatch(stage.name.removeprefix(version + '-')):
                        continue
                    marker = read_optional(stage / 'verified.json') or {}
                    digest = marker.get('manifest')
                    if isinstance(digest, str) and SHA.fullmatch(digest):
                        manifests.add(digest)
                require(len(manifests) == 1, 'UPDATE_INSTALL_RECEIPT_INVALID')
                manifest = manifests.pop()
                rows = self.run('list', timeout=12)
                candidates = installed(rows)
                require(len(candidates) == 1, 'UPDATE_INSTALL_READBACK_FAILED')
                selector = candidates[0]['pluginId']
            self.readback(value['version'], selector, manifest, rows)
        except (WCEError, OSError, ValueError, KeyError, IndexError, TypeError, subprocess.SubprocessError):
            return dict(value, state='INSTALL_UNKNOWN', code=value.get('code', 'UPDATE_INSTALL_READBACK_FAILED'))
        verified = dict(value, state='INSTALLED_RELOAD_REQUIRED')
        verified.pop('code', None)
        if value['state'] != 'INSTALLED_RELOAD_REQUIRED':
            atomic_write(self.root / 'status.json', verified)
        return verified

    def _superseded_receipt(self, value):
        target = value.get('version')
        if not isinstance(target, str) or not VERSION.fullmatch(target) or target == self.version:
            return False
        if value.get('state') == 'INSTALLED_RELOAD_REQUIRED':
            return True
        return (_version(target) < _version(self.version)
                and (value.get('state'), value.get('code')) ==
                    ('INSTALL_UNKNOWN', 'UPDATE_INSTALL_READBACK_FAILED'))

    def _historical_update_result(self, value):
        target = value.get('version')
        superseded = self._superseded_receipt(value)
        if ((not superseded and (value.get('state'), value.get('code')) not in UPDATE_HISTORY)
                or not isinstance(target, str) or not VERSION.fullmatch(target)):
            return value
        try:
            home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
            settings = tomllib.loads(read_market(home / 'config.toml')[0].decode())['plugins']
            selectors = [key for key, row in settings.items()
                         if SELECTOR.fullmatch(key) and row.get('enabled') is True]
            require(len(selectors) == 1, 'UPDATE_INSTALL_READBACK_FAILED')
            selector = selectors[0]
            if superseded and value.get('plugin_id') is not None:
                require(selector == value['plugin_id'], 'UPDATE_INSTALL_READBACK_FAILED')
            marketplace = SELECTOR.fullmatch(selector)[1]
            rows = self.run('list', '--marketplace', marketplace, timeout=12)
            candidates = installed(rows)
            require(len(candidates) == 1 and candidates[0].get('pluginId') == selector,
                    'UPDATE_INSTALL_READBACK_FAILED')
            current = candidates[0].get('version')
            require(isinstance(current, str) and VERSION.fullmatch(current)
                    and _version(current) >= _version(self.version)
                    and (superseded or _version(current) >= _version(target)),
                    'UPDATE_INSTALL_READBACK_FAILED')
            package = home / 'plugins/cache' / marketplace / PLUGIN / current
            manifest = sha256((package / 'package-manifest.json').read_bytes()).hexdigest()
            if current == self.version:
                require(Path(__file__).resolve().parent.parent == package, 'UPDATE_INSTALL_READBACK_FAILED')
                state = 'LOADED'
            else:
                # The running package may have been pruned after a host install.
                # Validate the install at the original attempt's advertised revision.
                revision = value.get('revision')
                require(current == target and isinstance(revision, str) and OID.fullmatch(revision),
                        'UPDATE_INSTALL_READBACK_FAILED')
                staged = read_optional(self.root / (target + '-' + revision) / 'verified.json') or {}
                require(staged.get('manifest') == manifest, 'UPDATE_INSTALL_READBACK_FAILED')
                state = 'INSTALLED_RELOAD_REQUIRED'
            self.readback(current, selector, manifest, rows)
            require(self._receipt() == value, 'UPDATE_INSTALL_RECEIPT_CHANGED')
        except (WCEError, OSError, ValueError, KeyError, IndexError, TypeError, subprocess.SubprocessError):
            return value
        return {'state': state, 'version': current,
                'request_id': value.get('request_id'),
                'history': {'version': target, 'code': value.get('code', PREVIOUS_RECEIPT)}}

    def _archived_receipts(self):
        from .own_connection_policy import private_read

        for item in (*self.root.glob('failed-*.json'), *self.root.glob('retained-*.json')):
            try:
                pin = SHA.fullmatch(item.stem.split('-', 1)[1])
                if pin is None:
                    continue
                raw = private_read(item)[0]
                if sha256(raw).hexdigest() != pin[0]:
                    continue
                archived = json.loads(raw)
                if isinstance(archived, dict):
                    yield archived
            except (WCEError, OSError, ValueError, TypeError):
                continue

    def _loaded_history(self, value):
        records = []
        for archived in self._archived_receipts():
            target = archived.get('version')
            if ((archived.get('state'), archived.get('code')) in UPDATE_HISTORY
                    or self._superseded_receipt(archived)) and isinstance(target, str) and VERSION.fullmatch(target):
                records.append((target, archived.get('code', PREVIOUS_RECEIPT)))
        if not records:
            return value
        target, code = max(records, key=lambda item: (_version(item[0]), item[1]))
        return dict(value, history={'version': target, 'code': code})

    def _request_status(self, request_id):
        require(type(request_id) is str and REQUEST_ID.fullmatch(request_id), 'UPDATE_TARGET_INVALID')
        lock = self.root / 'worker.lock'
        if not self.root.exists() or not os.path.lexists(lock):
            return {'state': 'START_NOT_RECORDED', 'request_id': request_id}
        try:
            with locked(lock, nonblocking=True, existing=True):
                if self._receipt().get('request_id') == request_id:
                    return None
                old = next((row for row in self._archived_receipts()
                            if row.get('request_id') == request_id), None)
                state = 'START_ARCHIVED' if old else 'START_NOT_RECORDED'
                return {'state': state, 'request_id': request_id}
        except WCEError as error:
            if error.code != 'CONNECTION_BUSY':
                raise
            if self._receipt().get('request_id') == request_id:
                return None
            return {'state': 'START_UNCONFIRMED', 'request_id': request_id}

    def status(self, request_id=None):
        if request_id is not None:
            outcome = self._request_status(request_id)
            if outcome is not None:
                return outcome
        if not self.root.exists():
            return {'state': 'IDLE'}
        value = self._receipt()
        if value['state'] in ACTIVE | {'INSTALL_UNKNOWN', 'INSTALLED_RELOAD_REQUIRED'}:
            try:
                with locked(self.root / 'worker.lock', nonblocking=True):
                    value = self._receipt()
                    state = value['state']
                    if self._superseded_receipt(value):
                        resolved = self._historical_update_result(value)
                        if resolved['state'] == 'LOADED':
                            return resolved
                    if state == 'INSTALLING':
                        value = dict(value, state='INSTALL_UNKNOWN', code='UPDATE_INSTALL_READBACK_FAILED')
                    elif state in ACTIVE:
                        downloaded = state in ('STAGED', 'WAITING_FOR_IDLE')
                        value = dict(value, state='DOWNLOADED_NOT_INSTALLED' if downloaded else 'INTERRUPTED')
                    if value['state'] in ('INSTALL_UNKNOWN', 'INSTALLED_RELOAD_REQUIRED'):
                        value = self._reconcile_installation(value)
            except WCEError as error:
                if error.code != 'CONNECTION_BUSY':
                    raise
                if value['state'] == 'INSTALLED_RELOAD_REQUIRED':
                    value = dict(value, state='INSTALLING')
        if value['state'] == 'INSTALLED_RELOAD_REQUIRED' and value.get('version') == self.version:
            return self._loaded_history(dict(value, state='LOADED'))
        if (value.get('state'), value.get('code')) in UPDATE_HISTORY:
            return self._historical_update_result(value)
        return value

    def start(self, version, revision, request_id=None):
        require(type(version) is str and VERSION.fullmatch(version) and type(revision) is str and OID.fullmatch(revision)
                and _version(version) > _version(self.version), 'UPDATE_TARGET_INVALID')
        require(request_id is None or type(request_id) is str and REQUEST_ID.fullmatch(request_id),
                'UPDATE_TARGET_INVALID')
        require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'UPDATE_PLATFORM_UNSUPPORTED')
        if not self.registry.parent.exists():
            self.registry.parent.mkdir(mode=0o700, exist_ok=True)
        path_check(self.registry.parent, True)
        try:
            mkdir(self.registry.parent, self.root.name)
        except FileExistsError:
            path_check(self.root, True)
        try:
            with locked(self.root / 'worker.lock', nonblocking=True) as fd:
                prior = read_optional(self.root / 'status.json') or {}
                if request_id is not None and prior.get('request_id') == request_id:
                    require(prior['version'] == version and prior['revision'] == revision, 'UPDATE_TARGET_INVALID')
                    return self._historical_update_result(prior)
                if request_id is not None:
                    old = next((row for row in self._archived_receipts()
                                if row.get('request_id') == request_id), None)
                    if old:
                        require(old.get('version') == version and old.get('revision') == revision,
                                'UPDATE_TARGET_INVALID')
                        return {'state': 'START_ARCHIVED', 'request_id': request_id}
                if prior.get('version') == version and (prior.get('state'), prior.get('code')) in UPDATE_HISTORY:
                    existing = self._historical_update_result(prior)
                    if existing['state'] == 'INSTALLED_RELOAD_REQUIRED':
                        return dict(existing, request_id=request_id)
                superseded = (self._superseded_receipt(prior)
                              and self._historical_update_result(prior)['state'] == 'LOADED')
                if not superseded and prior.get('state') in ('INSTALLING', 'INSTALL_UNKNOWN', 'INSTALLED_RELOAD_REQUIRED') and (
                        prior.get('state') != 'INSTALLED_RELOAD_REQUIRED' or prior.get('version') != self.version):
                    return dict(prior, state='INSTALL_UNKNOWN' if prior['state'] == 'INSTALLING' else prior['state'])
                intent = {'version': version, 'revision': revision}
                if request_id is not None:
                    intent['request_id'] = request_id
                row = dict(intent, state='CHECKING')
                if superseded or prior.get('request_id') or (prior.get('state'), prior.get('code')) in UPDATE_HISTORY:
                    from .own_connection_policy import private_read
                    from .own_identity_recovery import atomic_raw
                    original = private_read(self.root / 'status.json')[0]
                    prefix = 'failed-' if (prior.get('state'), prior.get('code')) in UPDATE_HISTORY else 'retained-'
                    backup = self.root / (prefix + sha256(original).hexdigest() + '.json')
                    if os.path.lexists(backup):
                        require(private_read(backup)[0] == original, 'UPDATE_HISTORY_CHANGED')
                    else:
                        atomic_raw(backup, original, None, exclusive=True)
                atomic_write(self.root / 'status.json', row)
                keeper = os.dup(fd)
                try:
                    Thread(target=self._run, args=(intent, keeper), daemon=True).start()
                except BaseException:
                    os.close(keeper)
                    atomic_write(self.root / 'status.json', dict(intent, state='INTERRUPTED'))
                    raise
                return row
        except WCEError as error:
            if error.code != 'CONNECTION_BUSY':
                raise
            current = self._receipt()
            if request_id is not None and current.get('request_id') == request_id:
                require(current.get('version') == version and current.get('revision') == revision,
                        'UPDATE_TARGET_INVALID')
                return current
            if current['state'] in ACTIVE | {'INSTALLED_RELOAD_REQUIRED', 'INSTALL_UNKNOWN'}:
                return current
            return {'state': 'BUSY', 'code': 'UPDATE_BUSINESS_BUSY'}

    def _run(self, intent, keeper):
        try:
            version, revision = intent['version'], intent['revision']
            state = 'CHECKING'
            readback = {}

            def progress(next_state, **fields):
                nonlocal state
                if next_state == 'INSTALLING':
                    readback.update(fields)
                state = next_state
                row = dict(intent, **readback)
                atomic_write(self.root / 'status.json', dict(row, state=state, **fields))

            try:
                ad = self.checker(self.version)
                require(ad.get('state') == 'UPDATE_AVAILABLE' and ad.get('latest_version') == version
                        and ad.get('advertised_revision') == revision, 'UPDATE_ADVERTISEMENT_CHANGED')
                stage = self.root / (version + '-' + revision)
                try:
                    mkdir(self.root, stage.name)
                except FileExistsError:
                    path_check(stage, True)
                cached = read_optional(stage / 'verified.json')
                if cached:
                    require(type(cached.get('folder')) is str and bool(re.fullmatch(r'release-[A-Za-z0-9_]+', cached['folder']))
                            and type(cached.get('manifest')) is str and bool(SHA.fullmatch(cached['manifest'])),
                            'UPDATE_STAGE_INVALID')
                    folder = stage / cached['folder']
                    target = folder / 'plugins' / PLUGIN
                    manifest = cached['manifest']
                    progress('VERIFYING')
                    verify_package(target, version, manifest)
                else:
                    folder = Path(tempfile.mkdtemp(prefix='release-', dir=stage))
                    try:
                        target, manifest = self.download(version, revision, folder, progress)
                    except BaseException:
                        # This fresh directory has no reference from the CLI or another worker.
                        shutil.rmtree(folder)
                        raise
                    atomic_write(stage / 'verified.json', {'folder': folder.name, 'manifest': manifest})
                progress('STAGED')
                deadline = time.monotonic() + 60
                while True:
                    try:
                        self.switch(self.version, version, target, manifest, self.registry, folder, progress)
                        break
                    except WCEError as error:
                        if state != 'WAITING_FOR_IDLE' or error.code not in BUSY_CODES or time.monotonic() >= deadline:
                            raise
                        time.sleep(1)
            except (WCEError, OSError, ValueError, KeyError, IndexError, TypeError, BadZipFile, subprocess.SubprocessError) as error:
                code = getattr(error, 'code', 'UPDATE_OPERATION_FAILED')
                if code in BUSY_CODES and state == 'WAITING_FOR_IDLE':
                    progress('BUSY', code=code)
                elif state == 'INSTALLING' and code != 'UPDATE_INSTALL_REJECTED':
                    progress('INSTALL_UNKNOWN', code=code)
                else:
                    progress('FAILED', code=code, downloaded=state in ('STAGED', 'WAITING_FOR_IDLE'))
        finally:
            os.close(keeper)
