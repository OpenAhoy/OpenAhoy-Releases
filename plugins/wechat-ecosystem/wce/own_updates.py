"""Read the published OpenAhoy stable channel and corroborate its Git tag."""
import json
from http.client import HTTPException
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
from urllib import request
from urllib.parse import urlsplit

REPOSITORY = 'OpenAhoy/OpenAhoy-Releases'
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
RELEASES = 'https://github.com/' + REPOSITORY + '/releases'
LATEST_MANIFEST_URL = RELEASES + '/latest/download/RELEASE.json'
PLUGIN = 'wechat-ecosystem'
PUBLIC_MARKET = 'openahoy-distribution'
MAX_ASSET = 128 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
VERSION = re.compile(r'(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\Z')
TAG = re.compile(r'refs/tags/v((?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8}))(\^\{\})?\Z')
OID = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?\Z')


class UpdateCheckUnavailable(Exception):
    def __init__(self, code='UNAVAILABLE'):
        self.code = code
        super().__init__(code)


def _failure(stderr):
    # Only finite categories leave this process. Raw stderr is never logged.
    text = stderr.decode('utf-8', errors='replace').lower()
    for words, code in [
        (('could not resolve host', 'name resolution'), 'NETWORK_DNS'),
        (('timed out', 'timeout'), 'NETWORK_TIMEOUT'),
        (('could not read username', 'terminal prompts disabled'), 'AUTH_REQUIRED'),
        (('repository not found', 'authentication failed', 'error: 401', 'error: 403'), 'ACCESS_UNAVAILABLE'),
        (('certificate', 'ssl peer'), 'TLS_FAILED'),
        (('redirect', 'redirection'), 'REDIRECT_REFUSED'),
        (('failed to connect', 'connection refused', 'network is unreachable'), 'NETWORK_CONNECT')]:
        if any(word in text for word in words):
            return code
    return 'GIT_FAILED'


def _git(arguments, timeout):
    # A protocol carrier bound, not an account/publication/release-count quota.
    maximum = 1024 * 1024
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_')}
    # Finder-launched hosts need not inherit the shell's proxy variables. Git
    # does not consult macOS System Settings itself. Adopt that existing route
    # only for this child, respecting explicit proxy/direct settings and bypass.
    if sys.platform == 'darwin' and not any(
            key.lower() in {'http_proxy', 'https_proxy', 'all_proxy'}
            for key in environment):
        # getproxies() alone treats a lone no_proxy as a complete environment
        # proxy configuration, hiding macOS's static proxy. Read it explicitly.
        proxies = request.getproxies_macosx_sysconf()
        if not (request.proxy_bypass_environment('github.com') or
                request.proxy_bypass_macosx_sysconf('github.com')):
            for scheme in ('http', 'https'):
                if proxies.get(scheme):
                    environment[scheme + '_proxy'] = proxies[scheme]
    environment.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never',
        GIT_ASKPASS='/usr/bin/false', SSH_ASKPASS='/usr/bin/false')
    command = ['/usr/bin/git', '-c', 'credential.interactive=false',
               '-c', 'credential.helper=', '-c', 'http.extraHeader=',
               '-c', 'http.extraHeader=Cache-Control: no-cache',
               '-c', 'core.askPass=/usr/bin/false', '-c', 'http.followRedirects=false',
               '-c', 'http.sslVerify=true', '-c', 'protocol.allow=never',
               '-c', 'protocol.https.allow=always',
               '-c', 'http.' + REMOTE + '.sslVerify=true',
               '-c', 'http.' + REMOTE + '.followRedirects=false',
               'ls-remote', *arguments]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=Path(__file__).resolve().parent,
        env=environment, start_new_session=True)
    deadline = time.monotonic() + timeout
    output = bytearray()
    diagnostic = bytearray()
    reaped = False
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UpdateCheckUnavailable('PROCESS_TIMEOUT')
                events = selector.select(remaining)
                if not events:
                    raise UpdateCheckUnavailable('PROCESS_TIMEOUT')
                for key, _ in events:
                    block = os.read(key.fileobj.fileno(), 16384)
                    if not block:
                        selector.unregister(key.fileobj); continue
                    if key.data == 'stdout':
                        output.extend(block)
                        if len(output) > maximum:
                            raise UpdateCheckUnavailable('CARRIER_LIMIT')
                    elif len(diagnostic) < 65536:
                        diagnostic.extend(block[:65536-len(diagnostic)])
        code = process.wait(timeout=max(0.001, deadline-time.monotonic()))
        reaped = True
        if code != 0:
            raise UpdateCheckUnavailable(_failure(diagnostic))
        return bytes(output)
    finally:
        # Reap the exact new process group, including a timed-out Git helper.
        if not reaped:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.stdout.close()
        process.stderr.close()
        process.wait()


def _version(value):
    if type(value) is not str or VERSION.fullmatch(value) is None:
        raise UpdateCheckUnavailable('INVALID_VERSION')
    return tuple(int(part) for part in value.split('.'))


def release_metadata(raw, version):
    """Validate the same public payload identity for discovery and download."""
    try:
        if len(raw) > 32768:
            raise ValueError()
        metadata = json.loads(raw)
        filename = f'openahoy-{version}-macos-arm64.zip'
        expected = {'schema': 1, 'product': 'OpenAhoy', 'version': version, 'tag': 'v' + version,
                    'repository': REPOSITORY, 'plugin': PLUGIN, 'platform': 'macos-arm64',
                    'marketplace': PUBLIC_MARKET, 'marketplace_source': REMOTE,
                    'plugin_path': './plugins/' + PLUGIN, 'asset': filename,
                    'asset_url': f'{RELEASES}/download/v{version}/{filename}',
                    'contains_user_accounts': False}
        size = metadata.get('size') if type(metadata) is dict else None
        if (type(size) is not int or not 0 < size <= MAX_ASSET
                or type(metadata.get('schema')) is not int
                or metadata.get('contains_user_accounts') is not False
                or any(metadata.get(key) != value for key, value in expected.items())
                or any(type(metadata.get(key)) is not str or not SHA.fullmatch(metadata[key])
                       for key in ('sha256', 'package_manifest_sha256'))
                or type(metadata.get('payload_count')) is not int or metadata['payload_count'] < 1):
            raise ValueError()
        return metadata
    except (ValueError, TypeError, RecursionError):
        raise UpdateCheckUnavailable('RELEASE_CHANNEL_INVALID') from None


class StableRedirect(request.HTTPRedirectHandler):
    def __init__(self):
        self.version = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            target = urlsplit(newurl)
        except ValueError:
            raise UpdateCheckUnavailable('REDIRECT_REFUSED') from None
        official = f'/{REPOSITORY}/releases/download/v'
        if target.scheme == 'https' and target.netloc == 'github.com' and req.full_url == LATEST_MANIFEST_URL:
            version = target.path.removeprefix(official).removesuffix('/RELEASE.json')
            if (target.path == official + version + '/RELEASE.json'
                    and VERSION.fullmatch(version) and not target.query and not target.fragment):
                self.version = version
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        if (self.version and req.full_url == f'{RELEASES}/download/v{self.version}/RELEASE.json'
                and target.scheme == 'https' and target.netloc in
                {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}):
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        raise UpdateCheckUnavailable('REDIRECT_REFUSED')


def _read_release(url, redirect):
    probe = request.Request(url, headers={
        'Cache-Control': 'no-cache, max-age=0', 'Pragma': 'no-cache', 'User-Agent': 'OpenAhoy Update'})
    try:
        with request.build_opener(redirect).open(probe, timeout=5) as response:
            return response.read(32769)
    except (OSError, HTTPException):
        raise UpdateCheckUnavailable('RELEASE_CHANNEL_UNAVAILABLE') from None


def published_stable():
    redirect = StableRedirect()
    raw = _read_release(LATEST_MANIFEST_URL, redirect)
    if redirect.version is None:
        raise UpdateCheckUnavailable('RELEASE_CHANNEL_INVALID')
    return release_metadata(raw, redirect.version)


def pinned_release(version, revision):
    url = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/RELEASE.json'
    # The stable redirect handler refuses redirects from the pinned raw URL.
    return release_metadata(_read_release(url, StableRedirect()), version)


def _tag_revision(raw, version):
    if type(raw) is not bytes:
        raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE')
    entries = {}
    try:
        for line in raw.decode('ascii').splitlines():
            oid, reference = line.split('\t')
            match = TAG.fullmatch(reference)
            if match is None or match[1] != version:
                continue
            if OID.fullmatch(oid) is None:
                raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE')
            field = 'peeled' if match[2] else 'base'
            if field in entries and entries[field] != oid:
                raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE')
            entries[field] = oid
        if not entries:
            raise UpdateCheckUnavailable('RELEASE_CHANNEL_CHANGED')
        if 'base' not in entries:
            raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE')
        return entries.get('peeled', entries['base'])
    except (UnicodeError, ValueError):
        raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE') from None


def check(installed_version, *, runner=None, publisher=None, pinned=None):
    base = {'installed_version': installed_version, 'repository': REPOSITORY}
    phase = 'SOURCE_CHECK'
    try:
        installed = _version(installed_version)
        run = runner or _git
        # Git's insteadOf may rewrite even a fixed argv URL. Do not connect
        # unless Git reports the same exact source selected by this product.
        if run(['--get-url', REMOTE], 3).strip() != REMOTE.encode('ascii'):
            raise UpdateCheckUnavailable('SOURCE_REWRITTEN')
        phase = 'RELEASE_READ'
        metadata = (publisher or published_stable)()
        latest = metadata['version']
        remote_version = _version(latest)
        phase = 'TAG_READ'
        tag_ref = 'refs/tags/v' + latest
        advertised = _tag_revision(run(['--tags', REMOTE, tag_ref, tag_ref + '^{}'], 12), latest)
        phase = 'RELEASE_READ'
        if (pinned or pinned_release)(latest, advertised) != metadata:
            raise UpdateCheckUnavailable('RELEASE_CHANNEL_CHANGED')
        state = ('UPDATE_AVAILABLE' if remote_version > installed else
                 'UP_TO_DATE' if remote_version == installed else 'DEVELOPMENT_AHEAD')
        return dict(base, state=state, latest_version=latest, tag='v'+latest,
            advertised_revision=advertised, package_manifest_sha256=metadata['package_manifest_sha256'])
    except (UpdateCheckUnavailable, OSError, subprocess.SubprocessError) as error:
        from .support_diagnostics import CODES
        code = (error.code if isinstance(error, UpdateCheckUnavailable) and error.code in CODES else
                'GIT_UNAVAILABLE' if isinstance(error, FileNotFoundError) else
                'PROCESS_TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'LOCAL_PROCESS_ERROR')
        return dict(base, state='CHECK_UNAVAILABLE', diagnostic={'code': code, 'phase': phase})
