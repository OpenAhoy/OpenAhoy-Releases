"""Bounded pure lineage computations within one synchronous broker request.

This never caches SQL rows, validation decisions, authority or proof reads.
Only the lineage default manifest reader participates; general stored JSON
readers retain their own limits and validation on every call.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from hashlib import sha256
import threading

from .own_lineage import manifest as _manifest, semantic as _semantic
from .service import canonical

MAX_ENTRIES = 32
MAX_RETAINED_BYTES = 4 * 1024 * 1024
_CURRENT = ContextVar('wce_lineage_request', default=None)


class _Memo:
    def __init__(self):
        self.thread = threading.get_ident()
        self.active = True
        self.disabled = False
        self.entries = {}
        self.retained = 0

    def clear(self):
        self.entries.clear()
        self.retained = 0

    def reserve(self, size, *, new=False):
        # These are logical canonical data bytes, not a Python heap estimate.
        # Exceeding the optimization budget falls back to full validation.
        if (self.retained + size > MAX_RETAINED_BYTES
                or (new and len(self.entries) >= MAX_ENTRIES)):
            self.disabled = True
            self.clear()
            return False
        self.retained += size
        return True


@contextmanager
def request_scope():
    memo = _Memo()
    token = _CURRENT.set(memo)
    try:
        yield
    finally:
        # copy_context() may retain this same object after reset(). Invalidate
        # it first, so re-entry cannot turn a request memo into a lasting one.
        memo.active = False
        memo.clear()
        _CURRENT.reset(token)


def _memo():
    value = _CURRENT.get()
    return (value if value is not None and value.active and not value.disabled
            and value.thread == threading.get_ident() else None)


def _key(raw, fingerprint):
    if type(raw) is not str or type(fingerprint) is not str:
        return None
    try:
        data = raw.encode('utf-8')
    except UnicodeError:
        return None
    checksum = sha256(data).hexdigest()
    # Keep the bounded original bytes in the key. The hash is an integrity
    # check, never a substitute for equality with previously parsed input.
    return (len(data), checksum, data) if checksum == fingerprint else None


def manifest(row):
    memo = _memo()
    key = _key(row['manifest'], row['digest']) if memo is not None else None
    if key is not None and key in memo.entries:
        return deepcopy(memo.entries[key]['manifest'])
    # Keep the original default reader, canonical/size/node/fallback checks,
    # exception code and ordering. A failed parse never populates the memo.
    value = _manifest(row)
    # Budget both retained raw bytes and the parsed canonical logical data.
    if key is not None and memo.reserve(2 * key[0], new=True):
        memo.entries[key] = {'manifest': deepcopy(value)}
    return value


def semantic_verified(value, fingerprint):
    memo = _memo()
    # validate() has just read each current row through manifest(). Recheck
    # the exact current value too, instead of trusting a mutable caller copy.
    key = _key(canonical(value), fingerprint) if memo is not None else None
    entry = memo.entries.get(key) if memo is not None and key is not None else None
    if entry is not None and 'semantic' in entry:
        return deepcopy(entry['semantic'])
    result = _semantic(value)
    if entry is not None:
        size = len(canonical(result).encode('utf-8'))
        if memo.reserve(size):
            entry['semantic'] = deepcopy(result)
    return result
