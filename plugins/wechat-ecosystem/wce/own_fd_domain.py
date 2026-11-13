"""Process-local scheduling for exact regular-FD attribution, never authority.

Known broker metadata and execution phases share this reentrant domain. The
original SQLite/source witnesses still reject uncoordinated regular-FD opens.
"""
from contextlib import contextmanager, ExitStack
import math
import resource
import threading
import time
from .contracts import WCEError

_LOCK = threading.RLock()
_LOCAL = threading.local()


def fd_capacity_allowed(count, additional, reserve):
    """Keep actual descriptor headroom under the current OS soft limit.

    This is an availability check, never an execution grant. Callers still
    count their real descriptors and retain their own transient reservations.
    Unknown or unlimited limits cannot establish finite available headroom.
    """
    if any(type(value) is not int or value < 0
           for value in (count, additional, reserve)):
        return False
    try:
        limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    except Exception:
        return False
    if type(limits) is not tuple or len(limits) != 2:
        return False
    soft, hard = limits
    if (type(soft) is not int or type(hard) is not int
            or soft <= 0 or soft == resource.RLIM_INFINITY
            or (hard != resource.RLIM_INFINITY and hard < soft)):
        return False
    return count + additional + reserve <= soft


def phase_deadline(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise WCEError('CONNECTION_REQUEST_REJECTED')
    stack = getattr(_LOCAL, 'deadlines', ())
    inherited = stack[-1] if stack else None
    return inherited if inherited is not None else time.monotonic() + seconds

@contextmanager
def regular_fd_domain(*, deadline=None, stop=None, wait=True, admission_deadline=None):
    if (type(wait) is not bool or (deadline is not None and
            (type(deadline) not in (int, float) or not math.isfinite(deadline)))):
        raise WCEError('CONNECTION_REQUEST_REJECTED')
    if admission_deadline is not None:
        try:
            valid = type(admission_deadline) in (int, float) and math.isfinite(admission_deadline)
        except OverflowError:
            valid = False
        if not valid:
            raise WCEError('CONNECTION_REQUEST_REJECTED')
    stack = getattr(_LOCAL, 'deadlines', None)
    if stack is None:
        stack = []
        _LOCAL.deadlines = stack
    parent = stack[-1] if stack else None
    deadline = parent if deadline is None else deadline if parent is None else min(parent, deadline)
    # Admission bounds only waiting for the domain. Once acquired, nested
    # guards inherit the fixed execution deadline; neither value is renewed.
    acquire_deadline = (deadline if admission_deadline is None else admission_deadline
                        if deadline is None else min(deadline, admission_deadline))
    acquired = False
    entered = False
    try:
        while not acquired:
            if stop is not None and stop.is_set():
                raise WCEError('CONNECTION_STOPPED')
            remaining = None if acquire_deadline is None else acquire_deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise WCEError('CONNECTION_QUEUE_EXPIRED')
            if not wait:
                acquired = _LOCK.acquire(blocking=False)
                break
            acquired = _LOCK.acquire(timeout=.05 if remaining is None else min(.05, remaining))
        if acquired:
            if stop is not None and stop.is_set():
                raise WCEError('CONNECTION_STOPPED')
            if acquire_deadline is not None and time.monotonic() >= acquire_deadline:
                raise WCEError('CONNECTION_QUEUE_EXPIRED')
            stack.append(deadline)
            entered = True
        yield acquired
    finally:
        if entered:
            stack.pop()
        if acquired:
            _LOCK.release()


@contextmanager
def owned_lifetime(context, *, deadline, stop=None):
    """Coordinate only acquisition/release, never the long-lived ownership body.

    Finish cleanup even after stop/expiry. This is the original resource-owner
    close responsibility, not a new business deadline or hard exit guarantee.
    """
    resources = ExitStack()
    original = None
    try:
        with regular_fd_domain(deadline=deadline, stop=stop):
            resources.enter_context(context)
        yield
    except BaseException as error:
        original = error
        raise
    finally:
        try:
            # Owner-only release must run even when an outer business phase
            # has expired. It grants no executable phase or renewed deadline.
            with _LOCK:
                resources.close()
        except BaseException:
            if original is None:
                raise
