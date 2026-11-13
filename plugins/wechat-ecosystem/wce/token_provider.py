"""Controlled in-memory token leases, isolated by tenant/account/connection/generation.

No secret input configuration or token-acquisition HTTP implementation is shipped.
"""
from dataclasses import dataclass, field
from threading import Lock
import math
import time

from .contracts import Secret, WCEError


@dataclass(frozen=True)
class TokenKey:
    tenant: str
    account: str
    connection: str
    secret_ref: str = field(repr=False)
    generation: int = 1
    token_revision: int = 0


@dataclass(frozen=True)
class TokenLease:
    token: Secret = field(repr=False)
    expires_at: float


class ScopedTokenCache:
    def __init__(self, loader, clock=time.time):
        self.loader, self.clock = loader, clock
        self._cache = {}
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            lease = self._cache.get(key)
            if lease is None or lease.expires_at <= self.clock():
                try:
                    lease = self.loader(key)
                except Exception:
                    raise WCEError("TOKEN_UNAVAILABLE") from None
                if (not isinstance(lease, TokenLease) or not isinstance(lease.token, Secret)
                        or isinstance(lease.expires_at, bool) or not isinstance(lease.expires_at, (int, float))
                        or not math.isfinite(lease.expires_at) or not lease.expires_at > self.clock()):
                    raise WCEError("TOKEN_UNAVAILABLE")
                self._cache[key] = lease
            return lease.token

    def is_current(self, key, token):
        """Validate the same lease at dispatch, without refreshing or replaying."""
        with self._lock:
            lease = self._cache.get(key)
            return lease is not None and lease.token is token and lease.expires_at > self.clock()

    def invalidate(self, key):
        with self._lock:
            self._cache.pop(key, None)

    def invalidate_connection(self, tenant, connection):
        with self._lock:
            for key in list(self._cache):
                if key.tenant == tenant and key.connection == connection:
                    self._cache.pop(key, None)
