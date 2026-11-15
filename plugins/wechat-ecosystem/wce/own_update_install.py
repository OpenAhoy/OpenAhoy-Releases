"""Install a verified OpenAhoy release with the official Codex CLI."""
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
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
    require(os.access(target / 'scripts/wce_mcp.sh', os.X_OK), 'UPDATE_LAUNCHER_INVALID')
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


@contextmanager
def maintenance(registry):
    from .own_connection_broker import STARTUP_SECONDS, _replace_idle_software_owner, _startup_gate, _startup_has_owner
    from .own_connection_registry import revoked

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
        policies = [resolve(cid, registry, active=False) for cid in sorted(read_registry(registry)['connections'])]
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
    require(os.access(target / 'scripts/wce_mcp.sh', os.X_OK), 'UPDATE_LAUNCHER_INVALID')


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
        require(registration.get('source_type') == 'git'
                and registration.get('source') == market_source.get('source')
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
            (folder / '.agents/plugins').mkdir(parents=True, exist_ok=True)
            (folder / '.agents/plugins/marketplace.json').write_bytes(raw)
            previous_market = folder / 'previous-marketplace'
            (previous_market / '.agents/plugins').mkdir(parents=True, exist_ok=True)
            prior = json.loads(raw)
            prior['plugins'][0]['source'] = {'source': 'local', 'path': './plugins/' + PLUGIN}
            (previous_market / '.agents/plugins/marketplace.json').write_text(json.dumps(prior))
            previous_target = previous_market / 'plugins' / PLUGIN
            if not previous_target.exists():
                shutil.copytree(rollback, previous_target)
            verify_package(previous_target, previous)
            run('marketplace', 'remove', market_name)
            try:
                run('marketplace', 'add', str(folder))
            except WCEError:
                if not any(entry['name'] == market_name for entry in run('marketplace', 'list')['marketplaces']):
                    run('marketplace', 'add', str(previous_market))
                    if not installed(run('list')):
                        run('add', selector)
                    require(installed(run('list'))[0]['version'] == previous, 'UPDATE_ROLLBACK_UNVERIFIED')
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
                    run('marketplace', 'remove', market_name)
                    run('marketplace', 'add', str(previous_market))
                    if not installed(run('list')):
                        run('add', selector)
                    require(installed(run('list'))[0]['version'] == previous, 'UPDATE_ROLLBACK_UNVERIFIED')
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

    def status(self):
        if not self.root.exists():
            return {'state': 'IDLE'}
        value = self._receipt()
        if value['state'] in ACTIVE | {'INSTALL_UNKNOWN', 'INSTALLED_RELOAD_REQUIRED'}:
            try:
                with locked(self.root / 'worker.lock', nonblocking=True):
                    value = self._receipt()
                    state = value['state']
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
            return dict(value, state='LOADED')
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
                    return prior
                if prior.get('state') in ('INSTALLING', 'INSTALL_UNKNOWN', 'INSTALLED_RELOAD_REQUIRED') and (
                        prior.get('state') != 'INSTALLED_RELOAD_REQUIRED' or prior.get('version') != self.version):
                    return dict(prior, state='INSTALL_UNKNOWN' if prior['state'] == 'INSTALLING' else prior['state'])
                intent = {'version': version, 'revision': revision}
                if request_id is not None:
                    intent['request_id'] = request_id
                row = dict(intent, state='CHECKING')
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
