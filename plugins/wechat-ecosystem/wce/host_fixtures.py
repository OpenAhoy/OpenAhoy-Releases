"""Offline field-contract fixtures, never JWT verification or OAuth authentication.

Only trusted local harnesses construct these synthetic types. They are absent
from tool schemas and do not grant any Tencent connection permissions.
"""
from dataclasses import dataclass
import hmac
import time
from threading import Lock
from uuid import uuid4

from .contracts import Actor, WCEError
from .connection_lifecycle import deadline
from .service import text

EVIDENCE = {"evidence": "OFFLINE_HOST_CONTRACT_ONLY", "authenticated": False,
            "oauth_verified": False, "connected": False, "platform_verified": False}
ISSUER = "https://identity.fixture.invalid"
RESOURCE = "https://mcp.fixture.invalid/wce"
GPT_CALLBACK = "https://chatgpt.com/aip/g-fixture/oauth/callback"


@dataclass(frozen=True)
class SyntheticMCPClaims:
    issuer: str
    resource: str
    audience: str
    expires_at: float
    not_before: float
    scopes: frozenset[str]


class MCPContractFixture:
    """Compare already-trusted synthetic fields; no parsing or token verifier."""
    def __init__(self, actor, profile_id, clock=time.time):
        if not isinstance(actor, Actor):
            raise WCEError("HOST_CONTEXT_INVALID")
        self.actor, self.profile_id, self.clock = actor, text(profile_id, 128), clock

    def accept(self, claims):
        if not isinstance(claims, SyntheticMCPClaims):
            raise WCEError("HOST_FIXTURE_TYPE_REQUIRED")
        if (claims.issuer != ISSUER or claims.resource != RESOURCE or claims.audience != RESOURCE
                or not isinstance(claims.scopes, frozenset) or "wce.tools" not in claims.scopes):
            raise WCEError("MCP_CONTRACT_REJECTED")
        deadline(claims.expires_at, self.clock())
        # Use the same strict finite timestamp validation for nbf, accepting now.
        deadline(claims.not_before, float('-inf'))
        if claims.not_before > self.clock():
            raise WCEError("MCP_CONTRACT_REJECTED")
        return self.actor

    def current_profile(self):
        """One credential-selected profile, empty parameters; no account choice."""
        return {"id": self.profile_id} | EVIDENCE


@dataclass(frozen=True)
class SyntheticGPTCallback:
    state: str
    target: str = GPT_CALLBACK


class GPTActionsContractFixture:
    """Independent once-state/callback fixture; no codes, bearer or network."""
    def __init__(self, actor, clock=time.time):
        if not isinstance(actor, Actor):
            raise WCEError("HOST_CONTEXT_INVALID")
        self.actor, self.clock = actor, clock
        self._transactions = {}
        self._lock = Lock()

    def begin(self, expires_at):
        deadline(expires_at, self.clock())
        transaction, state = uuid4().hex, uuid4().hex
        with self._lock:
            self._transactions[transaction] = (state, expires_at)
        return {"transaction_id": transaction, "state": state, "callback": GPT_CALLBACK} | EVIDENCE

    def complete(self, actor, transaction, callback):
        if not isinstance(callback, SyntheticGPTCallback):
            raise WCEError("HOST_FIXTURE_TYPE_REQUIRED")
        if (not isinstance(transaction, str) or not isinstance(callback.state, str)
                or not callback.state.isascii() or len(callback.state) != 32):
            raise WCEError("GPT_CONTRACT_REJECTED")
        with self._lock:
            pending = self._transactions.get(transaction)
            if (actor != self.actor or pending is None or pending[1] <= self.clock()
                    or not isinstance(callback.state, str) or not hmac.compare_digest(callback.state, pending[0])
                    or callback.target != GPT_CALLBACK):
                raise WCEError("GPT_CONTRACT_REJECTED")
            del self._transactions[transaction]
        return self.actor
