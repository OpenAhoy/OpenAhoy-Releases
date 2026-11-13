"""On-demand, single-flight host token cache. Never retries a business request."""
import ctypes
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
import sys
import threading
import time

from .contracts import Secret, WCEError
from .own_bootstrap_security import acquire_pending, path_check
from .bounded_file import identity
from .own_keychain import KeychainCredential
from .own_connection_policy import locked


@contextmanager
def token_lock(root):
    """Hold and revalidate the same account lock across an OS credential wait."""
    path = root / 'connection-token.lock'
    parent = path_check(root, True)
    with locked(path, nonblocking=True) as fd:
        pin = path_check(path)
        def check():
            info = os.fstat(fd)
            if (path_check(root, True) != parent or path_check(path) != pin
                    or identity(info) != pin[:2] or info.st_nlink != 1):
                raise WCEError('CONNECTION_PATH_CHANGED')
        check()
        yield check


class ContinuousClock:
    """Elapsed time including machine sleep; fail closed on unsupported hosts."""
    def __init__(self):
        if sys.platform == 'darwin':
            self.lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
            self.lib.mach_continuous_time.restype = ctypes.c_uint64
            class Timebase(ctypes.Structure):
                _fields_ = [('numer', ctypes.c_uint32), ('denom', ctypes.c_uint32)]
            value = Timebase()
            self.lib.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
            if self.lib.mach_timebase_info(ctypes.byref(value)) or not value.denom:
                raise WCEError('CONNECTION_CLOCK_UNAVAILABLE')
            self.scale = value.numer / value.denom / 1e9
        elif not hasattr(time, 'CLOCK_BOOTTIME'):
            raise WCEError('CONNECTION_CLOCK_UNAVAILABLE')

    def __call__(self):
        if sys.platform == 'darwin':
            return self.lib.mach_continuous_time() * self.scale
        return time.clock_gettime(time.CLOCK_BOOTTIME)


@dataclass(frozen=True)
class CachedToken:
    token: Secret = field(repr=False)
    wall_start: float
    continuous_start: float
    wall_deadline: float
    continuous_deadline: float


class TokenCache:
    def __init__(self, policy, credential=None, acquire=None, wall=time.time, continuous=None):
        self.policy = policy
        self.credential = credential
        self.acquire = acquire or acquire_pending
        self.wall, self.continuous = wall, continuous or ContinuousClock()
        self.lock = threading.RLock()
        self.cached, self.error = None, None
        self._failure_epoch = 0

    def valid(self, value=None, margin=0):
        value = self.cached if value is None else value
        self.policy.check()
        if value is None:
            return False
        now, elapsed = self.wall(), self.continuous()
        # A backward wall adjustment never lengthens the continuously bounded TTL.
        # An adjustment during acquisition, including sleep, is also rejected.
        return (now >= value.wall_start and elapsed >= value.continuous_start
                and now + margin < value.wall_deadline
                and elapsed + margin < value.continuous_deadline
                and abs((now - value.wall_start) - (elapsed - value.continuous_start)) < 5)

    def _failed(self, error):
        self.error = error.code if isinstance(error, WCEError) else 'CONNECTION_TOKEN_UNDETERMINED'
        self._failure_epoch += 1
        raise WCEError(self.error) from None

    def get(self, guard=None, *, minimum_validity_seconds=30):
        # Trusted caller requirement only; never accepted from MCP arguments.
        if (type(minimum_validity_seconds) not in (int, float)
                or not 30 <= minimum_validity_seconds <= 300
                or not math.isfinite(minimum_validity_seconds)):
            raise WCEError('CONNECTION_TOKEN_WINDOW_INVALID')
        def current():
            self.policy.check()
            if guard is not None: guard()
        # Capture before waiting: callers already sharing a failed flight see
        # that failure once. A new explicit call after it completed may retry
        # immediately; no time gate or automatic acquisition loop is added.
        observed_failure = self._failure_epoch
        with self.lock:
            current()
            if self.valid(margin=minimum_validity_seconds):
                return self.cached
            self.cached = None
            if self.error is not None and self._failure_epoch != observed_failure:
                raise WCEError(self.error)
            # Only the real cache miss participates in the cross-process lock.
            # Local contention/guard failures never become platform cooldowns.
            with token_lock(self.policy.root) as check_lock:
                current()
                def admitted():
                    check_lock()
                    current()
                if minimum_validity_seconds == 30:
                    return self._acquire_current(admitted)
                return self._acquire_current(admitted, minimum_validity_seconds=minimum_validity_seconds)

    def _get_for_group(self, controller):
        from .draft_group_token_runtime import get_for_group
        return get_for_group(self, controller)

    def _acquire_current(self, current, *, minimum_validity_seconds=30):
        try:
            credential = self.credential or KeychainCredential(self.policy)
            secret = credential.load()
            if type(secret) is not Secret:
                raise WCEError('CONNECTION_KEYCHAIN_ITEM_REQUIRED')
        except Exception as error:
            self._failed(error)
        try:
            # Keychain may wait for the human/OS. Recheck the caller, policy
            # and execution deadline before the actual token POST.
            current()
            before_wall, before_cont = self.wall(), self.continuous()
            try:
                token, deadline, _ = self.acquire(self.policy.data['appid'], secret.reveal_for_adapter())
            except Exception as error:
                self._failed(error)
        finally:
            secret = None
        current()
        try:
            ttl = deadline - before_wall
            if not 0 < ttl <= 7200.1:
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            value = CachedToken(token, before_wall, before_cont, deadline, before_cont + ttl)
            if not self.valid(value, margin=30):
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            if minimum_validity_seconds != 30 and not self.valid(value, margin=minimum_validity_seconds):
                raise WCEError('CONNECTION_TOKEN_WINDOW_UNAVAILABLE')
            self.cached, self.error = value, None
            return value
        except Exception as error:
            self._failed(error)

    def clear(self):
        with self.lock:
            self.cached = None

    def seed(self, value, identity_digest):
        """Trusted setup-only in-process handoff; never exposed through IPC."""
        from .service import digest
        with self.lock:
            self.policy.check()
            if (identity_digest != digest(self.policy.data) or type(value) is not CachedToken
                    or type(value.token) is not Secret or self.cached is not None or self.error is not None
                    or not 0 < value.wall_deadline - value.wall_start <= 7200.1
                    or abs((value.continuous_deadline - value.continuous_start)
                           - (value.wall_deadline - value.wall_start)) > .000001
                    or not self.valid(value, margin=30)):
                raise WCEError('CONNECTION_TOKEN_HANDOFF_REJECTED')
            self.cached = value

    def status(self):
        self.policy.check()
        with self.lock:
            if self.valid():
                return {'state': 'CONNECTED', 'token_expires_at': self.cached.wall_deadline,
                        'platform_business_capabilities': 'NOT_VERIFIED'}
            return {'state': 'ACTION_REQUIRED' if self.error else 'BOUND_IDLE',
                    'error': self.error, 'platform_business_capabilities': 'NOT_VERIFIED'}
