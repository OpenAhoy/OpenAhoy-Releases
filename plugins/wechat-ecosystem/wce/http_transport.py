"""HTTP plumbing only. No guessed Tencent wire contract or enabled live operation."""
from dataclasses import dataclass, field
import json
import math
import re
import time
import threading
import ssl
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from .contracts import Secret, WCEError
from .service import canonical, digest
from .storage import Database
from .token_provider import TokenKey

MAX_BODY = 2 * 1024 * 1024
STATES = {"SUBMITTED", "PROCESSING", "SUCCEEDED", "FAILED", "RESULT_UNKNOWN"}


@dataclass(frozen=True)
class HTTPRequest:
    method: str
    path: str = field(repr=False)
    headers: dict = field(repr=False)
    body: bytes = field(repr=False)
    test_only: bool = False


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes = field(repr=False)


TRANSPORT_STAGES = frozenset({'PREPARE', 'OPEN_RESPONSE', 'RESPONSE_ENTER',
    'BODY_READ', 'RESPONSE_VALUE', 'RESPONSE_CLOSE', 'SENDER'})
TRANSPORT_KINDS = frozenset({'LOCAL_REJECT', 'TIMEOUT', 'TLS_ERROR',
    'CONNECTION_ERROR', 'OS_ERROR', 'URL_ERROR', 'BODY_LIMIT', 'OTHER'})


def valid_transport_failure(stage, kind, http_status):
    return (type(stage) is str and stage in TRANSPORT_STAGES
        and type(kind) is str and kind in TRANSPORT_KINDS
        and (http_status is None or type(http_status) is int and 100 <= http_status <= 599))


@dataclass(frozen=True)
class TransportFailure:
    """Closed observed facts only. No exception, URL, headers or body retained."""
    stage: str
    kind: str
    http_status: int | None = None

    def __post_init__(self):
        if not valid_transport_failure(self.stage, self.kind, self.http_status):
            raise ValueError('INVALID_TRANSPORT_FAILURE')


def transport_failure(stage, error, http_status=None):
    reason = error.reason if type(error) is URLError else error
    kind = ('TIMEOUT' if isinstance(reason, TimeoutError) else
            'TLS_ERROR' if isinstance(reason, ssl.SSLError) else
            'CONNECTION_ERROR' if isinstance(reason, ConnectionError) else
            'URL_ERROR' if isinstance(error, URLError) else
            'OS_ERROR' if isinstance(reason, OSError) else
            'LOCAL_REJECT' if isinstance(reason, WCEError) else 'OTHER')
    return TransportFailure(stage, kind, http_status)


def _observed_status(response):
    try:
        status = response.code
        return status if type(status) is int and 100 <= status <= 599 else None
    except Exception:
        return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPSender:
    """Real TLS implementation, disabled by default; no proxies or redirects."""
    mode = "live"
    def __init__(self, enabled=False, *, safe_transport_diagnostics=False):
        if type(safe_transport_diagnostics) is not bool:
            raise ValueError('INVALID_TRANSPORT_DIAGNOSTIC_OPTION')
        self._safe_transport_diagnostics = safe_transport_diagnostics
        self.enabled = enabled
        self._thread_opener = threading.local()
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    @property
    def opener(self):
        # Each bounded read worker owns its transport handlers. A thread never
        # inherits another thread's opener or a test's replacement opener.
        if not hasattr(self._thread_opener, 'value'):
            self._thread_opener.value = build_opener(ProxyHandler({}), NoRedirect())
        return self._thread_opener.value

    @opener.setter
    def opener(self, value):
        self._thread_opener.value = value

    def send(self, request, timeout):
        if getattr(self, '_safe_transport_diagnostics', False) is True:
            return self._send_safe(request, timeout)
        req = self._prepare_request(request, timeout)
        try:
            response = self.opener.open(req, timeout=timeout)
        except HTTPError as error:
            response = error  # status/body are data; never expose URL or errmsg.
        return self._response_value(response)

    def _prepare_request(self, request, timeout):
        if request.test_only:
            raise WCEError("CANDIDATE_TEST_ONLY")
        if not self.enabled:
            raise WCEError("HTTP_DISABLED")
        parts = urlsplit(request.path)
        if request.method not in {"GET", "POST"} or parts.scheme or parts.netloc or parts.fragment or not parts.path.startswith("/cgi-bin/") or "\\" in request.path or any(ord(c) < 32 for c in request.path):
            raise WCEError("INVALID_HTTP_REQUEST")
        if not math.isfinite(timeout) or not 0 < timeout <= 30 or len(request.body) > MAX_BODY:
            raise WCEError("INVALID_HTTP_REQUEST")
        req = Request("https://api.weixin.qq.com" + request.path, data=request.body if request.method == "POST" else None,
                      headers=request.headers, method=request.method)
        return req

    def _response_value(self, response):
        if getattr(self, '_safe_transport_diagnostics', False) is True:
            return self._response_value_safe(response)
        with response:
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("Response too large")
            return HTTPResponse(response.code, body)

    def _send_safe(self, request, timeout):
        try:
            req = self._prepare_request(request, timeout)
        except Exception as error:
            return transport_failure('PREPARE', error)
        try:
            response = self.opener.open(req, timeout=timeout)
        except HTTPError as error:
            response = error  # An actually received HTTP error status/body.
        except Exception as error:
            # urllib does not expose a reliable separate connect/write/header
            # boundary. Report only this combined observable call stage.
            return transport_failure('OPEN_RESPONSE', error)
        return self._response_value(response)

    def _response_value_safe(self, response):
        status, stage = _observed_status(response), 'RESPONSE_ENTER'
        try:
            with response:
                stage = 'BODY_READ'
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    value = TransportFailure(stage, 'BODY_LIMIT', status)
                else:
                    stage = 'RESPONSE_VALUE'
                    value = HTTPResponse(response.code, body)
                stage = 'RESPONSE_CLOSE'
            return value
        except Exception as error:
            return transport_failure(stage, error, status)


@dataclass(frozen=True)
class WireReply:
    state: str = "RESULT_UNKNOWN"
    reference: str | None = None
    token_invalid: bool = False
    rejected: bool = False
    items: tuple = ()
    next_cursor: str | None = None


class Codec(Protocol):
    """Trusted verified contract must own token placement, fields and error mapping."""
    def request(self, payload: dict, token: Secret) -> HTTPRequest: ...
    def response(self, response: HTTPResponse) -> WireReply: ...
    def reconcile_payload(self, reference: str) -> dict: ...
    def page_payload(self, payload: dict, cursor: str) -> dict: ...


@dataclass(frozen=True)
class Operation:
    name: str
    write: bool
    codec: Codec = field(repr=False)
    official_source: str | None = None
    source_sha256: str | None = None
    reconciles: str | None = None
    test_only: bool = False


@dataclass(frozen=True)
class HTTPBinding:
    tenant: str
    principal: str
    connection: str
    account_id: str
    secret_ref: str = field(repr=False)
    mode: str = "test"
    qualification_verified: bool = False
    capabilities: frozenset = frozenset()
    expires_at: float = 0
    generation: int = 1
    resource_id: str | None = None
    token_revision: int = 0


HTTP_SCHEMA = """
CREATE TABLE IF NOT EXISTS transport_config(id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims(
 tenant TEXT, principal TEXT, connection TEXT, account TEXT, request_key TEXT, action TEXT,
 fingerprint TEXT, generation INTEGER, state TEXT, reference TEXT,
 PRIMARY KEY(tenant,principal,connection,account,request_key));
"""


class HTTPExecutor:
    """Adapter-layer executor; the wire fixture bridge uses only test bindings.

    Fixture operations remain fictional; draft_wire supplies a separate narrow
    read codec. No live account binding is shipped. Live enablement and verified
    account/operation evidence are required; test-only codecs always reject live.
    """
    def __init__(self, path, binding, provider, sender=None, clock=time.time, registry_guard=None):
        if binding.mode not in {"test", "live"}:
            raise WCEError("TRANSPORT_MODE_MISMATCH")
        self.db = Database(path, HTTP_SCHEMA, 0x57434832)
        self.binding, self.provider = binding, provider
        self.sender, self.clock = sender or HTTPSender(), clock
        self.registry_guard = registry_guard
        with self.db.transaction(write=True) as db:
            config = db.execute("SELECT mode FROM transport_config WHERE id=1").fetchone()
            if config is None:
                if db.execute("SELECT 1 FROM claims LIMIT 1").fetchone():
                    raise WCEError("MODE_STATE_UNVERIFIED")
                db.execute("INSERT INTO transport_config VALUES(1,?)", (binding.mode,))
            elif config["mode"] != binding.mode:
                raise WCEError("MODE_STATE_MISMATCH")

    def _guard(self, operation, expected_binding=None):
        b = self.binding
        if (operation.test_only or getattr(operation.codec, "test_only", False)) and b.mode != "test":
            raise WCEError("CANDIDATE_TEST_ONLY")
        if expected_binding is not None and b != expected_binding:
            raise WCEError("AUTHORIZATION_CHANGED")
        if not all(isinstance(v, str) and v for v in (b.tenant, b.principal, b.connection, b.account_id)):
            raise WCEError("ACCOUNT_CAPABILITY_UNVERIFIED")
        if b.resource_id is not None and (not isinstance(b.resource_id, str) or b.resource_id != b.account_id):
            raise WCEError("ACCOUNT_CAPABILITY_UNVERIFIED")
        if b.mode not in {"test", "live"} or self.sender.mode != b.mode:
            raise WCEError("TRANSPORT_MODE_MISMATCH")
        if b.expires_at <= self.clock() or not b.qualification_verified or operation.name not in b.capabilities:
            raise WCEError("ACCOUNT_CAPABILITY_UNVERIFIED")
        if self.registry_guard is not None:
            self.registry_guard(operation.name)
        if b.mode == "live":
            if not operation.official_source or not operation.official_source.startswith("https://developers.weixin.qq.com/") or not operation.source_sha256 or not re.fullmatch("[a-f0-9]{64}", operation.source_sha256):
                raise WCEError("WIRE_CONTRACT_UNVERIFIED")
            if not getattr(self.sender, "enabled", False):
                raise WCEError("HTTP_DISABLED")

    def _exchange(self, operation, payload, binding):
        self._guard(operation, binding)
        b = binding
        try:
            key = TokenKey(b.tenant, b.account_id, b.connection, b.secret_ref, b.generation, b.token_revision)
            token = self.provider.get(key)
            request = operation.codec.request(payload, token)
            self._guard(operation, b)
            if not self.provider.is_current(key, token):
                return WireReply()
            self._guard(operation, b)
            response = self.sender.send(request, timeout=10)
            self._guard(operation, b)
            if not isinstance(response, HTTPResponse) or not isinstance(response.body, bytes) or len(response.body) > MAX_BODY or not 200 <= response.status < 300:
                return WireReply()
            reply = operation.codec.response(response)
            if not isinstance(reply, WireReply) or reply.state not in STATES or type(reply.token_invalid) is not bool or type(reply.rejected) is not bool:
                return WireReply()
            if reply.token_invalid:
                self.provider.invalidate(key)
                # Do not refresh and replay the write, even on token failures.
                return WireReply(token_invalid=True)
            # Never return a token echoed in any codec-produced response field.
            stack = [reply.reference, reply.items, reply.next_cursor]
            inspected = 0
            while stack:
                inspected += 1
                if inspected > 10000:
                    return WireReply()
                item = stack.pop()
                if isinstance(item, str) and token.reveal_for_adapter() in item:
                    return WireReply()
                if isinstance(item, (list, tuple)):
                    stack.extend(item)
                elif isinstance(item, dict):
                    stack.extend(item.keys())
                    stack.extend(item.values())
            if reply.reference is not None and (not isinstance(reply.reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", reply.reference) or token.reveal_for_adapter() in reply.reference):
                return WireReply()
            self._guard(operation, b)
            return reply
        except Exception:
            return WireReply()  # no response/exception/token text in results.

    def _view(self, row):
        return {"request_key": row["request_key"], "action": row["action"],
                "state": row["state"], "reference": row["reference"], "mode": self.binding.mode,
                "account_id": row["account"], "connection_id": row["connection"],
                "transport": "mock" if self.binding.mode == "test" else "http", "platform_verified": False}

    def execute(self, operation, payload, request_key):
        self._guard(operation)
        if not operation.write or not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_key):
            raise WCEError("INVALID_HTTP_OPERATION")
        b = self.binding
        fingerprint = digest({"mode": b.mode, "connection": b.connection, "account": b.account_id, "action": operation.name, "payload": payload, "generation": b.generation})
        with self.db.transaction(write=True) as db:
            old = db.execute("SELECT * FROM claims WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (b.tenant, b.principal, b.connection, b.account_id, request_key)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise WCEError("IDEMPOTENCY_CONFLICT")
                return self._view(old)
            if b.resource_id is not None:
                unresolved = db.execute("SELECT 1 FROM claims WHERE tenant=? AND account=? AND action=? AND state='RESULT_UNKNOWN'",
                                        (b.tenant, b.resource_id, operation.name)).fetchone()
            else:
                unresolved = db.execute("SELECT 1 FROM claims WHERE tenant=? AND connection=? AND account=? AND action=? AND state='RESULT_UNKNOWN'",
                                        (b.tenant, b.connection, b.account_id, operation.name)).fetchone()
            if unresolved:
                raise WCEError("UNRESOLVED_OPERATION")
            db.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,NULL)", (b.tenant, b.principal, b.connection, b.account_id, request_key, operation.name, fingerprint, b.generation, "RESULT_UNKNOWN"))
        reply = self._exchange(operation, payload, b)
        if self.binding != b:
            raise WCEError("AUTHORIZATION_CHANGED")  # original claim remains UNKNOWN
        try:
            self._guard(operation, b)  # persistent authority before accepting success
        except WCEError:
            reply = WireReply()  # existing claim remains UNKNOWN; no stale data/ref
        state = "FAILED" if reply.rejected else reply.state
        if state != "FAILED" and reply.reference is None:
            state = "RESULT_UNKNOWN"
        with self.db.transaction(write=True) as db:
            db.execute("UPDATE claims SET state=?,reference=? WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (state, reply.reference, b.tenant, b.principal, b.connection, b.account_id, request_key))
            return self._view(db.execute("SELECT * FROM claims WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (b.tenant, b.principal, b.connection, b.account_id, request_key)).fetchone())

    def reconcile(self, request_key, status_operation):
        self._guard(status_operation)
        if status_operation.write:
            raise WCEError("INVALID_HTTP_OPERATION")
        b = self.binding
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM claims WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (b.tenant, b.principal, b.connection, b.account_id, request_key)).fetchone()
            if row is None or row["generation"] != b.generation:
                raise WCEError("OPERATION_UNAVAILABLE")
            if status_operation.reconciles != row["action"]:
                raise WCEError("STATUS_ACTION_MISMATCH")
            if row["reference"] is None or row["state"] in {"SUCCEEDED", "FAILED"}:
                return self._view(row)
        try:
            payload = status_operation.codec.reconcile_payload(row["reference"])
        except Exception:
            raise WCEError("HTTP_QUERY_UNRESOLVED") from None
        reply = self._exchange(status_operation, payload, b)
        if reply.reference is not None and reply.reference != row["reference"]:
            reply = WireReply()
        self._guard(status_operation, b)
        with self.db.transaction(write=True) as db:
            latest = db.execute("SELECT * FROM claims WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (b.tenant, b.principal, b.connection, b.account_id, request_key)).fetchone()
            if latest["state"] not in {"SUCCEEDED", "FAILED"}:
                state = reply.state
                if latest["state"] == "PROCESSING" and state == "SUBMITTED":
                    state = "PROCESSING"
                db.execute("UPDATE claims SET state=? WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (state, b.tenant, b.principal, b.connection, b.account_id, request_key))
            return self._view(db.execute("SELECT * FROM claims WHERE tenant=? AND principal=? AND connection=? AND account=? AND request_key=?", (b.tenant, b.principal, b.connection, b.account_id, request_key)).fetchone())

    def pages(self, operation, payload, limit=20):
        if operation.write or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise WCEError("INVALID_HTTP_OPERATION")
        self._guard(operation)
        binding = self.binding
        result, seen = [], set()
        for _ in range(limit):
            reply = self._exchange(operation, payload, binding)
            self._guard(operation, binding)
            if reply.state != "SUCCEEDED" or not isinstance(reply.items, tuple) or len(reply.items) > 100:
                raise WCEError("HTTP_QUERY_UNRESOLVED")
            result.extend(reply.items)
            if reply.next_cursor is None:
                return result
            if not isinstance(reply.next_cursor, str) or not 1 <= len(reply.next_cursor) <= 128 or reply.next_cursor in seen:
                raise WCEError("INVALID_PAGE_CURSOR")
            seen.add(reply.next_cursor)
            try:
                payload = operation.codec.page_payload(payload, reply.next_cursor)
            except Exception:
                raise WCEError("HTTP_QUERY_UNRESOLVED") from None
        raise WCEError("PAGE_LIMIT_REACHED")
