"""Read advertised stable tags only; installation belongs to the Codex host.

Git uses the machine's already-configured credential helper internally. This
module never opens account files, keychains, Git config or credential stores.
"""
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
from urllib import request

REPOSITORY = 'OpenAhoy/OpenAhoy-Releases'
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
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


def _latest(raw):
    if type(raw) is not bytes:
        raise UpdateCheckUnavailable()
    entries = {}
    try:
        for line in raw.decode('ascii').splitlines():
            oid, reference = line.split('\t')
            match = TAG.fullmatch(reference)
            # Other tags are not stable version advertisements.
            if match is None:
                continue
            if OID.fullmatch(oid) is None:
                raise UpdateCheckUnavailable()
            version, peeled = match.groups()
            field = 'peeled' if peeled else 'base'
            row = entries.setdefault(version, {})
            if field in row and row[field] != oid:
                raise UpdateCheckUnavailable()
            row[field] = oid
        if not entries:
            raise UpdateCheckUnavailable('NO_STABLE_TAGS')
        if any('base' not in row for row in entries.values()):
            raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE')
        version = max(entries, key=_version)
        row = entries[version]
        return version, row.get('peeled', row['base'])
    except (UnicodeError, ValueError):
        raise UpdateCheckUnavailable('INVALID_TAG_RESPONSE') from None


def check(installed_version, *, runner=None):
    base = {'installed_version': installed_version, 'repository': REPOSITORY}
    phase = 'SOURCE_CHECK'
    try:
        installed = _version(installed_version)
        run = runner or _git
        # Git's insteadOf may rewrite even a fixed argv URL. Do not connect
        # unless Git reports the same exact source selected by this product.
        if run(['--get-url', REMOTE], 3).strip() != REMOTE.encode('ascii'):
            raise UpdateCheckUnavailable('SOURCE_REWRITTEN')
        phase = 'TAG_READ'
        latest, advertised = _latest(run(['--tags', REMOTE, 'refs/tags/v*'], 12))
        remote_version = _version(latest)
        state = ('UPDATE_AVAILABLE' if remote_version > installed else
                 'UP_TO_DATE' if remote_version == installed else 'DEVELOPMENT_AHEAD')
        return dict(base, state=state, latest_version=latest, tag='v'+latest,
            advertised_revision=advertised)
    except (UpdateCheckUnavailable, OSError, subprocess.SubprocessError) as error:
        from .support_diagnostics import CODES
        code = (error.code if isinstance(error, UpdateCheckUnavailable) and error.code in CODES else
                'GIT_UNAVAILABLE' if isinstance(error, FileNotFoundError) else
                'PROCESS_TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'LOCAL_PROCESS_ERROR')
        return dict(base, state='CHECK_UNAVAILABLE', diagnostic={'code': code, 'phase': phase})
