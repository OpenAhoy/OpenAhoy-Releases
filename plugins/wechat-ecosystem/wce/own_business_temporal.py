"""Pure per-context temporal ceiling. No FD, lock, source or authority issuer."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time
from wce.contracts import WCEError

_CEILING = ContextVar('wce_business_parent_ceiling', default=None)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def bound_deadline(original_absolute):
    """Preserve the caller's clock/expired value; only reduce a finite cap."""
    if not _finite(original_absolute):
        raise WCEError('GROUP_DEADLINE')
    inherited = _CEILING.get()
    return original_absolute if inherited is None else min(original_absolute, inherited)


def phase_deadline(seconds):
    if not _finite(seconds) or seconds <= 0:
        raise WCEError('GROUP_DEADLINE')
    now = time.monotonic()
    local = now + seconds
    if not math.isfinite(local):
        raise WCEError('GROUP_DEADLINE')
    inherited = _CEILING.get()
    deadline = local if inherited is None else min(local, inherited)
    if deadline <= now:
        raise WCEError('GROUP_DEADLINE')
    return deadline


@contextmanager
def deadline_scope(absolute_deadline):
    now = time.monotonic()
    if not _finite(absolute_deadline) or not now < absolute_deadline <= now + 300:
        raise WCEError('GROUP_DEADLINE')
    inherited = _CEILING.get()
    effective = absolute_deadline if inherited is None else min(inherited, absolute_deadline)
    if effective <= now:
        raise WCEError('GROUP_DEADLINE')
    token = _CEILING.set(effective)
    try:
        yield effective
    finally:
        _CEILING.reset(token)
