"""Short-lived external-browser transport. No MCP-visible session capability."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
import threading
import time

from .contracts import WCEError

LIFETIME = 300
NAVIGATION_TIMEOUT = 15
LAUNCH_TIMEOUT = 4
LAUNCH_KILL_WAIT = 1
LAUNCH_TOTAL_TIMEOUT = 6
MAX_BODY = 8192
MAX_PRESENTATION_BODY = 65536
RULE_ERRORS = frozenset({'RULES_ACCOUNT_UNAVAILABLE','RULES_CHUNK_CONFLICT','RULES_IDENTITY_CHANGED','RULES_INCOMPLETE','RULES_INVALID_REQUEST','RULES_INVALID_STORE','RULES_INVALID_UNICODE','RULES_IO_UNAVAILABLE','RULES_LEGACY_CHANGED','RULES_OPERATION_COMMITTED','RULES_OPERATION_CONFLICT','RULES_OPERATION_UNAVAILABLE','RULES_SCHEMA_UNSUPPORTED','RULES_SECRET_NOT_ALLOWED','RULES_VERSION_CONFLICT','RULES_VERSION_UNAVAILABLE','RULES_WRITE_RESULT_UNKNOWN'})
SAFE_ERRORS = frozenset({
    'DRAFT_RESTORE_HOLD', 'DRAFT_RESTORE_REVIEW_CHANGED', 'DRAFT_RESTORE_RESULT_UNKNOWN',
    'DRAFT_RESTORE_SOURCE_INVALID', 'DRAFT_RESTORE_SOURCE_CHANGED', 'DRAFT_RESTORE_SCOPE_MISMATCH',
    'DRAFT_RESTORE_PARENT_NOT_QUALIFIED', 'DRAFT_RESTORE_PARENT_CHANGED',
    'DRAFT_RESTORE_ALREADY_SUBMITTED_OR_PUBLISHED', 'DRAFT_RESTORE_MIGRATION_HOLD',
    'DRAFT_RESTORE_HUMAN_REVIEW_REQUIRED', 'DRAFT_RESTORE_AUTHORITY_EXPIRED',
    'REVIEW_RUNTIME_UNAVAILABLE', 'PUBLICATION_ADMISSION_UNKNOWN',
    'PUBLICATION_PRODUCER_UNAVAILABLE', 'PUBLICATION_BASELINE_LOCK_UNAVAILABLE',
    'PUBLICATION_ENABLE_EVIDENCE_CHANGED', 'PUBLICATION_PERMISSION_EXPIRY_UNSUPPORTED',
    'PUBLICATION_DISABLE_RESULT_UNKNOWN', 'PUBLICATION_OPERATION_ID_INVALID',
    'R1_REVIEW_CHANGED', 'R1_RISK_ACK_REQUIRED', 'R1_PREVIEW_INVALID', 'R1_STATUS_INVALID',
    'OWN_REPLACEMENT_PREVIEW_UNAVAILABLE', 'OWN_REPLACEMENT_NOT_CONFIGURED',
    'OWN_REPLACEMENT_ALREADY_REVIEWED_QUERY_ORIGINAL', 'OWN_REPLACEMENT_STOPPED',
    'OWN_REPLACEMENT_SCHEMA_REQUIRED', 'OWN_REPLACEMENT_INPUT_CHANGED',
    'OWN_REPLACEMENT_SPENT_ORPHAN', 'OWN_REPLACEMENT_RECORD_HOLD',
    'SETTINGS_INVALID_REQUEST', 'SETTINGS_ACCESS_DENIED', 'SETTINGS_EXPIRED',
    'SETTINGS_REVIEW_REQUIRED', 'SETTINGS_REVIEW_CHANGED', 'SETTINGS_BUSY',
    'SETTINGS_RESULT_UNDETERMINED', 'SETTINGS_OPEN_FAILED',
    'CONNECTION_BUSY', 'CONNECTION_LOCKED', 'CONNECTION_NOT_BOUND',
    'CONNECTION_REVIEW_CHANGED', 'CONNECTION_RESOURCE_ALREADY_BOUND',
    'CONNECTION_ACCOUNT_LIMIT', 'CONNECTION_ENROLLMENT_LIMIT',
    'CONNECTION_INVALID_APPID', 'CONNECTION_INVALID_LABEL',
    'CONNECTION_ENROLLMENT_REQUIRES_RECONCILIATION',
    'CONNECTION_OWNER_CONFLICT', 'CONNECTION_RECOVERY_CONFLICT',
    'CONNECTION_UPGRADE_REVIEW_REQUIRED', 'BOOTSTRAP_CREDENTIAL_INVALID',
    'COVER_READ_DATABASE_BUSY', 'COVER_READ_DATABASE_UNSUPPORTED',
    'COVER_READ_SNAPSHOT_CHANGED', 'COVER_READ_TARGET_UNSUPPORTED',
    'COVER_READ_TARGET_LIMIT', 'COVER_READ_AUTHORITY_INVALID',
    'COVER_READ_METADATA_LIMIT', 'OWN_RECONCILE_NOT_UNKNOWN',
    'BOOTSTRAP_TOKEN_IP_DENIED', 'BOOTSTRAP_TOKEN_ADMIN_PENDING', 'BOOTSTRAP_TOKEN_ADMIN_DENIED',
    'BOOTSTRAP_TOKEN_QUOTA_DENIED', 'BOOTSTRAP_TOKEN_CREDENTIAL_REJECTED', 'BOOTSTRAP_TOKEN_REJECTED',
    'BOOTSTRAP_TOKEN_HTTP_FAILED', 'BOOTSTRAP_TOKEN_INVALID_RESPONSE', 'BOOTSTRAP_TOKEN_RESULT_UNKNOWN',
    'CONNECTION_TOKEN_TIME_INVALID', 'CONNECTION_CHECK_COOLDOWN', 'CONNECTION_CHECK_LIMIT',
    'CONNECTION_CHECK_SPENT', 'CONNECTION_CHECK_HISTORY_INVALID', 'CONNECTION_CHECK_BUDGET_REQUIRED',
    'CONNECTION_CHECK_BUDGET_CHANGED', 'CONNECTION_CHECK_BUDGET_SPENT', 'CONNECTION_CHECK_BUDGET_TARGET',
    'CONNECTION_ENROLLMENT_ATTEMPT_LIMIT', 'CONNECTION_DISCONNECTED',
    'PRESENTATION_INVALID_NAME', 'PRESENTATION_INVALID_IMAGE', 'PRESENTATION_INVALID_DATA',
    'PRESENTATION_IDENTITY_CHANGED', 'PRESENTATION_STALE', 'PRESENTATION_WRITE_UNKNOWN',
    'SETTINGS_NAVIGATION_STALE', 'SETTINGS_NAVIGATION_NOT_CONFIRMED',
    'SETTINGS_NAVIGATION_UNKNOWN', 'SETTINGS_FOCUS_UNAVAILABLE',
    'SETTINGS_LAUNCH_UNKNOWN',
})


def safe_error(error):
    code = getattr(error, 'code', None)
    return code if code in SAFE_ERRORS | RULE_ERRORS else 'SETTINGS_RESULT_UNDETERMINED'


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if type(value) is not dict:
        raise ValueError()
    return value


def external_browser(url):
    # The capability goes only over a bounded stdin pipe, never argv/env/logs.
    # The fixed isolated helper calls LaunchServices in its own memory.
    if not _trusted_bootstrap_url(url):
        raise WCEError('SETTINGS_OPEN_FAILED')
    root = str(Path(__file__).resolve().parents[1])
    program = ('import sys\n'
               'sys.path.insert(0, ' + repr(root) + ')\n'
               'from wce.own_settings_http import _trusted_bootstrap_url, _launch_safari\n'
               'raw=sys.stdin.buffer.read(256)\n'
               'url=raw.decode("ascii")\n'
               'if not _trusted_bootstrap_url(url): raise SystemExit(2)\n'
               '_launch_safari(url)\n')
    done, cancelled = threading.Event(), threading.Event()
    gate = threading.Lock()
    result = {'child': None, 'code': 'SETTINGS_LAUNCH_UNKNOWN'}

    def stop(child):
        try:
            child.kill()
        except OSError:
            pass
        try:
            child.wait(timeout=LAUNCH_KILL_WAIT)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def run_helper():
        try:
            try:
                child = subprocess.Popen([sys.executable, '-I', '-B', '-c', program],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, start_new_session=True,
                    env={'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'})
            except Exception:
                result['code'] = 'SETTINGS_OPEN_FAILED'
                return
            with gate:
                result['child'] = child
                expired = cancelled.is_set()
            if expired:
                stop(child)
                return
            try:
                child.communicate(url.encode('ascii'), timeout=LAUNCH_TIMEOUT)
            except Exception:
                stop(child)
                return
            if child.returncode == 0:
                result['code'] = None
        finally:
            done.set()

    # Bound even a stuck process creation call. A helper created after timeout
    # receives no capability. If the OS already accepted the URL, the caller
    # revokes the session and retains UNKNOWN; no second launch is attempted.
    threading.Thread(target=run_helper, daemon=True).start()
    if not done.wait(LAUNCH_TOTAL_TIMEOUT):
        with gate:
            cancelled.set()
            child = result['child']
        if child is not None:
            try:
                child.kill()
            except OSError:
                pass
        raise WCEError('SETTINGS_LAUNCH_UNKNOWN')
    if result['code']:
        raise WCEError(result['code'])


def _trusted_bootstrap_url(url):
    match = re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/#([A-Za-z0-9_-]{43})',
                         url) if type(url) is str else None
    return bool(match and int(match.group(1)) <= 65535)


def _launch_safari(url, libraries=None):
    """Fixed Safari LaunchServices call; no subprocess or Apple Events access."""
    import ctypes
    from ctypes import c_char_p, c_int32, c_long, c_uint32, c_void_p
    if libraries is None:
        libraries = (ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'),
                     ctypes.CDLL('/System/Library/Frameworks/CoreServices.framework/CoreServices'))
    cf, ls = libraries
    cf.CFStringCreateWithCString.argtypes = (c_void_p, c_char_p, c_uint32)
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFURLCreateWithString.argtypes = (c_void_p, c_void_p, c_void_p)
    cf.CFURLCreateWithString.restype = c_void_p
    cf.CFURLGetFileSystemRepresentation.argtypes = (c_void_p, ctypes.c_bool, c_void_p, c_long)
    cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = (c_void_p, c_char_p, c_long, ctypes.c_bool)
    cf.CFURLCreateFromFileSystemRepresentation.restype = c_void_p
    cf.CFArrayGetCount.argtypes = (c_void_p,)
    cf.CFArrayGetCount.restype = c_long
    cf.CFArrayGetValueAtIndex.argtypes = (c_void_p, c_long)
    cf.CFArrayGetValueAtIndex.restype = c_void_p
    cf.CFArrayCreate.argtypes = (c_void_p, ctypes.POINTER(c_void_p), c_long, c_void_p)
    cf.CFArrayCreate.restype = c_void_p
    cf.CFRelease.argtypes = (c_void_p,)
    cf.CFRelease.restype = None
    cf.CFRunLoopRunInMode.argtypes = (c_void_p, ctypes.c_double, ctypes.c_bool)
    cf.CFRunLoopRunInMode.restype = c_int32
    class LaunchSpec(ctypes.Structure):
        # LSOpen.h declares this C structure under #pragma pack(push, 2).
        _layout_ = 'ms'
        _pack_ = 2
        _fields_ = [('appURL', c_void_p), ('itemURLs', c_void_p),
                    ('passThruParams', c_void_p), ('launchFlags', c_uint32),
                    ('asyncRefCon', c_void_p)]
    ls.LSOpenFromURLSpec.argtypes = (ctypes.POINTER(LaunchSpec), c_void_p)
    ls.LSOpenFromURLSpec.restype = c_int32
    ls.LSCopyApplicationURLsForBundleIdentifier.argtypes = (c_void_p, c_void_p)
    ls.LSCopyApplicationURLsForBundleIdentifier.restype = c_void_p
    refs = []
    try:
        text = cf.CFStringCreateWithCString(None, url.encode('utf-8'), 0x08000100)
        if not text: raise ValueError('CF allocation failed')
        refs.append(text)
        item = cf.CFURLCreateWithString(None, text, None)
        if not item: raise ValueError('CF allocation failed')
        refs.append(item)
        bundle = cf.CFStringCreateWithCString(None, b'com.apple.Safari', 0x08000100)
        if not bundle: raise ValueError('CF allocation failed')
        refs.append(bundle)
        applications = ls.LSCopyApplicationURLsForBundleIdentifier(bundle, None)
        if not applications: raise ValueError('Safari unavailable')
        refs.append(applications)
        if cf.CFArrayGetCount(applications) < 1: raise ValueError('Safari unavailable')
        # The first system-ranked application is borrowed from this retained
        # array. Safari can reside in a Cryptex rather than /System/Applications.
        app = cf.CFArrayGetValueAtIndex(applications, 0)
        if not app: raise ValueError('Safari unavailable')
        location = ctypes.create_string_buffer(4096)
        if not cf.CFURLGetFileSystemRepresentation(app, True, location, len(location)):
            raise ValueError('Safari unavailable')
        # A registered duplicate bundle ID must never receive the capability.
        # Accept only Safari in the OS-protected system application locations.
        resolved = Path(os.fsdecode(location.value)).resolve(strict=True)
        if str(resolved) not in {
                '/System/Applications/Safari.app',
                '/System/Volumes/Preboot/Cryptexes/App/System/Applications/Safari.app'} or not resolved.is_dir():
            raise ValueError('Safari unavailable')
        # Use the verified protected path, not a possibly writable alias
        # returned by LaunchServices whose target could change after checking.
        safari = os.fsencode(resolved)
        app = cf.CFURLCreateFromFileSystemRepresentation(None, safari, len(safari), True)
        if not app: raise ValueError('CF allocation failed')
        refs.append(app)
        values = (c_void_p * 1)(item)
        array = cf.CFArrayCreate(None, values, 1, None)
        if not array: raise ValueError('CF allocation failed')
        refs.append(array)
        # kLSLaunchDefaults | kLSLaunchDontAddToRecents.
        spec = LaunchSpec(app, array, None, 0x101, None)
        if ls.LSOpenFromURLSpec(ctypes.byref(spec), None) != 0:
            raise ValueError('LaunchServices failed')
        # LaunchServices queues asynchronous work even with default flags.
        # A short-lived CLI helper must service its run loop before exiting;
        # otherwise acceptance can be observed without URL delivery to Safari.
        mode = cf.CFStringCreateWithCString(None, b'kCFRunLoopDefaultMode', 0x08000100)
        if not mode: raise ValueError('CF allocation failed')
        refs.append(mode)
        cf.CFRunLoopRunInMode(mode, 1.0, False)
    finally:
        for ref in reversed(refs):
            cf.CFRelease(ref)


def focus_browser():
    # Activate the application only. This is not proof the page/tab is focused:
    # the authenticated page must later confirm visibility and focus.
    done = threading.Event()
    result = {'ok': False}
    def activate():
        try:
            process = subprocess.run(['/usr/bin/open', '-b', 'com.apple.Safari'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5, check=False)
            result['ok'] = process.returncode == 0
        except Exception:
            pass
        finally:
            done.set()
    # subprocess.run's timeout begins only after process creation. Bound the
    # entire invocation, including creation, without blocking the manager.
    threading.Thread(target=activate, daemon=True).start()
    if not done.wait(LAUNCH_TOTAL_TIMEOUT) or not result['ok']:
        raise WCEError('SETTINGS_FOCUS_UNAVAILABLE')


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        pass


class SettingsSession:
    def __init__(self, backend, html, csp, wall=time.time, clock=time.monotonic,
                 *, shared_server=None, embedding_guard=None):
        self.backend, self.html, self.csp = backend, html.encode(), csp
        self.wall, self.clock = wall, clock
        self.started_wall, self.started = wall(), clock()
        self.bootstrap = secrets.token_urlsafe(32)
        self.session = self.csrf = None
        self.lock = threading.RLock()
        self.navigation_condition = threading.Condition(self.lock)
        self.navigation_revision = 0
        self.navigation_sequence = 0
        self.navigation = None
        self.closed = threading.Event()
        self.embedding_guard = embedding_guard
        self.owns_server = shared_server is None
        self.server = shared_server or LimitedServer(('127.0.0.1', 0), SettingsHandler)
        if self.owns_server:
            self.server.settings = self
        self.host = '127.0.0.1:' + str(self.server.server_port)
        self.origin = 'http://' + self.host
        self.thread = None
        if self.owns_server:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                           name='wce-settings-http')
            self.thread.start()
        self.timer = threading.Thread(target=self._expire, daemon=True,
                                      name='wce-settings-expiry')
        self.timer.start()

    def _expire(self):
        while not self.closed.wait(0.5):
            try:
                with self.lock:
                    self.check()
            except WCEError:
                self.close()

    def check(self):
        if self.embedding_guard is not None:
            self.embedding_guard()
        elapsed, wall_elapsed = self.clock() - self.started, self.wall() - self.started_wall
        if (self.closed.is_set() or elapsed < 0 or wall_elapsed < 0
                or elapsed >= LIFETIME or wall_elapsed >= LIFETIME
                or abs(elapsed - wall_elapsed) >= 5):
            raise WCEError('SETTINGS_EXPIRED')

    def launch(self, opener=external_browser):
        try:
            opener(self.origin + '/#' + self.bootstrap)
        except WCEError as error:
            self.close()
            if error.code == 'SETTINGS_LAUNCH_UNKNOWN':
                raise WCEError('SETTINGS_LAUNCH_UNKNOWN') from None
            raise WCEError('SETTINGS_OPEN_FAILED') from None
        except Exception:
            self.close()
            raise WCEError('SETTINGS_OPEN_FAILED') from None
        return {'state': 'SETTINGS_OPENED', 'expires_in_seconds': LIFETIME}

    def prepare_add(self, *, fresh=False):
        """Reserve only a UI navigation. Account selection is not touched."""
        with self.lock:
            self.check()
            with self.backend.lock:
                self.backend.check(self.check)
                if (self.backend.state not in {'READY', 'RESULT'} or self.backend.review is not None
                        or self.backend.pending_recovery is not None
                        or getattr(self.backend, 'navigation_pending', False)
                        or (not fresh and (self.session is None or self.csrf is None))):
                    raise WCEError('SETTINGS_BUSY')
                if self.navigation and self.navigation['state'] in {'PREPARING', 'READY', 'APPLIED', 'UNKNOWN'}:
                    raise WCEError('SETTINGS_BUSY')
                self.navigation_sequence += 1
                self.navigation = {'sequence': self.navigation_sequence, 'state': 'PREPARING',
                    'deadline': min(self.started + LIFETIME, self.clock() + NAVIGATION_TIMEOUT)}
                self.backend.navigation_pending = True
                return self.navigation_sequence

    def enable_add(self, sequence):
        with self.lock:
            self.check()
            with self.backend.lock:
                self.backend.check(self.check)
                current = self.navigation
                if (not current or current['sequence'] != sequence or current['state'] != 'PREPARING'
                        or self.clock() >= current['deadline']):
                    raise WCEError('SETTINGS_NAVIGATION_STALE')
                current['state'] = 'READY'
                self.navigation_condition.notify_all()

    def cancel_add(self, sequence):
        """Only unconsumed navigation can be cancelled; selected is unchanged."""
        with self.lock:
            with self.backend.lock:
                current = self.navigation
                if not current or current['sequence'] != sequence:
                    raise WCEError('SETTINGS_NAVIGATION_STALE')
                if current['state'] in {'PREPARING', 'READY'}:
                    current['state'] = 'CANCELLED'
                    # Invalidate requests that left the page before the
                    # reservation, even if they arrive after cancellation.
                    self.navigation_revision += 1
                    self.backend.navigation_pending = False
                    self.navigation_condition.notify_all()
                    return
                if current['state'] not in {'CANCELLED', 'COMPLETE'}:
                    current['state'] = 'UNKNOWN'
                    self.navigation_condition.notify_all()

    def wait_add(self, sequence):
        with self.navigation_condition:
            while True:
                current = self.navigation
                if not current or current['sequence'] != sequence:
                    raise WCEError('SETTINGS_NAVIGATION_STALE')
                if current['state'] == 'COMPLETE':
                    try:
                        self.check()
                    except WCEError:
                        return {'state': 'SETTINGS_ADD_UNKNOWN'}
                    return {'state': 'SETTINGS_ADD_READY'}
                if current['state'] in {'CANCELLED', 'UNKNOWN'}:
                    return {'state': 'SETTINGS_ADD_UNKNOWN' if current['state'] == 'UNKNOWN'
                            else 'SETTINGS_ADD_NOT_CONFIRMED'}
                try:
                    self.check()
                except WCEError:
                    self.cancel_add(sequence)
                    continue
                remaining = current['deadline'] - self.clock()
                if remaining <= 0:
                    self.cancel_add(sequence)
                    continue
                self.navigation_condition.wait(min(remaining, 0.25))

    def navigation_call(self, path, value, client_revision):
        # Called with the session lock already held and after session + CSRF
        # authentication. Lock order matches close: session then backend.
        with self.backend.lock:
            self.backend.check(self.check)
            current = self.navigation
            if path == '/navigation/poll':
                if value:
                    raise WCEError('SETTINGS_INVALID_REQUEST')
                if not current or current['state'] != 'READY':
                    return {'state': 'NONE', 'revision': self.navigation_revision}
                if self.clock() >= current['deadline']:
                    self.cancel_add(current['sequence'])
                    return {'state': 'NONE', 'revision': self.navigation_revision}
                return {'state': 'READY', 'sequence': current['sequence']}
            expected = {'sequence', 'visible', 'focused'} if path in {
                '/navigation/ack', '/navigation/complete'} else {'sequence'}
            if set(value) != expected or type(value['sequence']) is not int or not current \
                    or value['sequence'] != current['sequence']:
                raise WCEError('SETTINGS_NAVIGATION_STALE')
            if path in {'/navigation/ack', '/navigation/complete'} and (
                    value['visible'] is not True or value['focused'] is not True):
                raise WCEError('SETTINGS_NAVIGATION_STALE')
            if path == '/navigation/status':
                return {'state': current['state'], 'sequence': current['sequence'],
                        'revision': self.navigation_revision}
            if path == '/navigation/ack':
                if (current['state'] != 'READY' or self.clock() >= current['deadline']
                        or client_revision != self.navigation_revision
                        or self.backend.state not in {'READY', 'RESULT'}
                        or self.backend.review is not None or self.backend.pending_recovery is not None):
                    raise WCEError('SETTINGS_NAVIGATION_STALE')
                self.backend.selected = None
                self.backend.clear_target()
                self.backend.state = 'READY'
                self.backend.result = {'state': 'NOT_SUBMITTED'}
                self.navigation_revision += 1
                current['state'] = 'APPLIED'
                self.navigation_condition.notify_all()
                return {'state': 'APPLIED', 'sequence': current['sequence'],
                        'revision': self.navigation_revision}
            if path == '/navigation/complete':
                if current['state'] == 'APPLIED' and self.clock() >= current['deadline']:
                    current['state'] = 'UNKNOWN'
                    self.navigation_condition.notify_all()
                    raise WCEError('SETTINGS_NAVIGATION_UNKNOWN')
                if (current['state'] not in {'APPLIED', 'UNKNOWN'}
                        or client_revision != self.navigation_revision
                        or self.backend.state != 'READY' or self.backend.selected is not None
                        or self.backend.review is not None or self.backend.pending_recovery is not None):
                    raise WCEError('SETTINGS_NAVIGATION_STALE')
                current['state'] = 'COMPLETE'
                self.backend.navigation_pending = False
                self.navigation_condition.notify_all()
                return {'state': 'COMPLETE', 'sequence': current['sequence'],
                        'revision': self.navigation_revision}
            raise WCEError('SETTINGS_INVALID_REQUEST')

    def close(self):
        try:
            with self.lock:
                if self.closed.is_set():
                    return
                self.closed.set()
                self.bootstrap = self.session = self.csrf = None
                with self.backend.lock:
                    if self.navigation and self.navigation['state'] in {'PREPARING', 'READY'}:
                        self.navigation['state'] = 'CANCELLED'
                        self.navigation_revision += 1
                        self.backend.navigation_pending = False
                    elif self.navigation and self.navigation['state'] == 'APPLIED':
                        self.navigation['state'] = 'UNKNOWN'
                    self.navigation_condition.notify_all()
                    self.backend.close()
        finally:
            if self.closed.is_set() and self.owns_server:
                self.server.shutdown()
                self.server.server_close()

    def handle(self, path, headers, value):
        with self.lock:
            self.check()
            if path == '/bootstrap':
                if (set(value) != {'bootstrap'} or type(value['bootstrap']) is not str
                        or not self.bootstrap or self.clock() - self.started >= 30
                        or not hmac.compare_digest(value['bootstrap'], self.bootstrap)):
                    raise WCEError('SETTINGS_ACCESS_DENIED')
                self.bootstrap = None
                self.session, self.csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                return {'session': self.session, 'csrf': self.csrf, 'expires_in_seconds':
                        max(0, int(LIFETIME - (self.clock() - self.started))),
                        'navigation_revision': self.navigation_revision}
            if (not self.session or not self.csrf
                    or not hmac.compare_digest(headers.get('X-WCE-Session', ''), self.session)
                    or not hmac.compare_digest(headers.get('X-WCE-CSRF', ''), self.csrf)):
                raise WCEError('SETTINGS_ACCESS_DENIED')
            revision = headers.get('X-WCE-Navigation-Revision')
            if revision is None and self.navigation_sequence == 0:
                revision = '0'  # Compatibility until navigation is first used.
            if (type(revision) is not str or not revision.isascii() or not revision.isdecimal()
                    or len(revision) > 16):
                raise WCEError('SETTINGS_NAVIGATION_STALE')
            revision = int(revision)
            if path in {'/navigation/poll', '/navigation/ack', '/navigation/status', '/navigation/complete'}:
                return self.navigation_call(path, value, revision)
            if revision != self.navigation_revision:
                raise WCEError('SETTINGS_NAVIGATION_STALE')
        if path == '/close' and not value:
            self.close()
            return {'state': 'CLOSED'}
        if path in {'/rules/read', '/rules/save', '/rules/restore'}:
            from .own_production_rules_protocol import READ, SAVE, RESTORE, call
            with self.backend.lock:
                self.backend.check(self.check)
                if (self.backend.state not in {'READY', 'RESULT'}
                        or self.backend.review is not None
                        or getattr(self.backend, 'navigation_pending', False)):
                    raise WCEError('SETTINGS_BUSY')
                return call({'/rules/read': READ, '/rules/save': SAVE,
                             '/rules/restore': RESTORE}[path], value, self.backend.registry)
        if path not in {'/overview', '/review', '/commit', '/result', '/cancel', '/cover-recoveries',
                        '/continue', '/select', '/diagnostic', '/presentation', '/publication-status', '/restore-status'}:
            raise WCEError('SETTINGS_INVALID_REQUEST')
        # Backend admission rechecks closure/expiry and its review under its lock.
        # Closing the UI cannot retract an already dispatched ordinary request.
        def check_request():
            self.check()
            if revision != self.navigation_revision:
                raise WCEError('SETTINGS_NAVIGATION_STALE')
        return self.backend.call(path, value, check_request)

    def send_recovery_review(self, headers, value, respond):
        """Private preview/capability response, with the original lock order."""
        from .service import digest
        with self.lock:
            self.check()
            if (not self.session or not self.csrf
                    or not hmac.compare_digest(headers.get('X-WCE-Session', ''), self.session)
                    or not hmac.compare_digest(headers.get('X-WCE-CSRF', ''), self.csrf)):
                raise WCEError('SETTINGS_ACCESS_DENIED')
            with self.backend.lock:
                self.backend.check(self.check)
                current = self.backend.review
                if (current is None or current['intent'] not in {'RECOVER_BODY_BATCH_V1','RECOVER_BODY5_ONCE_V1'}
                        or current['id'] != value['review_id']
                        or value['review'].get('intent')!=current['intent']
                        or (current['intent']=='RECOVER_BODY5_ONCE_V1')!=(current['prepared'].get('contract_sha')=='337ce7b69a0a07bb00f884d1f53ae8aa01b9868666ac6e9904f596acacf5b59c')
                        or value['review']['body_recovery'].get('contract_sha')!=current['prepared'].get('contract_sha')
                        or current['display_sha'] != digest(value['review']['body_recovery'])):
                    raise WCEError('R1_REVIEW_CHANGED')
                respond(200, value)

    def send_diagnostic(self, headers, value, respond):
        """Final private-response gate, serialized with target change/closure.

        Only the small bounded loopback write holds both locks. Once bytes have
        entered the socket, the browser generation check clears stale delivery.
        """
        with self.lock:
            self.check()
            if (not self.session or not self.csrf
                    or not hmac.compare_digest(headers.get('X-WCE-Session', ''), self.session)
                    or not hmac.compare_digest(headers.get('X-WCE-CSRF', ''), self.csrf)):
                raise WCEError('SETTINGS_ACCESS_DENIED')
            with self.backend.lock:
                self.backend.check(self.check)
                if self.backend.state != 'RESULT' or self.backend.diagnostic != value:
                    value = {'state': 'NONE'}
                respond(200, value)

    def send_restore_review(self, headers, value, respond):
        """Do not return a private review after navigation, target change or closure."""
        from .service import digest
        with self.lock:
            self.check()
            if (not self.session or not self.csrf
                    or not hmac.compare_digest(headers.get('X-WCE-Session', ''), self.session)
                    or not hmac.compare_digest(headers.get('X-WCE-CSRF', ''), self.csrf)
                    or headers.get('X-WCE-Navigation-Revision') != str(self.navigation_revision)):
                raise WCEError('SETTINGS_ACCESS_DENIED')
            with self.backend.lock:
                self.backend.check(self.check)
                current = self.backend.review
                if (self.backend.state != 'REVIEW' or current is None or current['intent'] != 'RESTORE_DRAFTS'
                        or current['id'] != value['review_id'] or current['target'] != self.backend.selected
                        or current['generation'] != self.backend.generation
                        or current['restore_display_sha'] != digest(value['review']['restore_drafts'])):
                    raise WCEError('DRAFT_RESTORE_REVIEW_CHANGED')
                respond(200, value)


class SettingsHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)
        # One request retains its original session even if a shared listener
        # publishes a new page between admission and response.
        self.settings = self.server.settings

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.respond(400, {'error': 'SETTINGS_INVALID_REQUEST'})

    def respond(self, code, value, html=False):
        raw = value if html else json.dumps(value, ensure_ascii=True).encode()
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', self.settings.csp if self.settings is not None else "default-src 'none'; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(raw)
        except (OSError, TimeoutError):
            pass
        self.close_connection = True

    def valid_headers(self, post=False):
        settings = self.settings
        if settings is None:
            return False
        for name in ('Host', 'Origin', 'Content-Length', 'Content-Type',
                     'X-WCE-Session', 'X-WCE-CSRF', 'X-WCE-Navigation-Revision'):
            if len(self.headers.get_all(name, [])) > 1:
                return False
        if self.headers.get('Host') != settings.host or self.headers.get_all('Transfer-Encoding'):
            return False
        if post and (self.headers.get('Origin') != settings.origin
                     or self.headers.get('Content-Type') != 'application/json'):
            return False
        return True

    def do_GET(self):
        if not self.valid_headers() or self.path != '/':
            self.respond(403, {'error': 'SETTINGS_ACCESS_DENIED'})
            return
        try:
            self.settings.check()
        except WCEError:
            self.respond(403, {'error': 'SETTINGS_EXPIRED'})
            return
        self.respond(200, self.settings.html, html=True)

    def do_POST(self):
        if not self.valid_headers(post=True):
            self.respond(403, {'error': 'SETTINGS_ACCESS_DENIED'})
            return
        try:
            size = self.headers.get('Content-Length', '')
            maximum = (MAX_PRESENTATION_BODY if self.path in {'/presentation', '/rules/save'}
                       else MAX_BODY)
            if not size.isascii() or not size.isdecimal() or not 1 <= int(size) <= maximum:
                raise ValueError()
            raw = self.rfile.read(int(size))
            if len(raw) != int(size):
                raise ValueError()
            value = parse_json(raw)
            raw = None
        except (ValueError, UnicodeError, RecursionError, OSError):
            self.respond(400, {'error': 'SETTINGS_INVALID_REQUEST'})
            return
        try:
            result = self.settings.handle(self.path, self.headers, value)
            value = None
            if (self.path == '/review' and result.get('review', {}).get('intent') in {'RECOVER_BODY_BATCH_V1','RECOVER_BODY5_ONCE_V1'}):
                self.settings.send_recovery_review(self.headers, result, self.respond)
            elif self.path == '/review' and result.get('review', {}).get('intent') == 'RESTORE_DRAFTS':
                self.settings.send_restore_review(self.headers, result, self.respond)
            elif self.path == '/diagnostic':
                self.settings.send_diagnostic(self.headers, result, self.respond)
            else:
                self.respond(200, result)
        except Exception as error:
            value = None
            self.respond(409, {'error': safe_error(error)})

    def unsupported(self):
        self.respond(405, {'error': 'SETTINGS_INVALID_REQUEST'})

    do_OPTIONS = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_TRACE = unsupported
