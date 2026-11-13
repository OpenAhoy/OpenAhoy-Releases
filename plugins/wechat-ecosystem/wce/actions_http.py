"""Fail-closed HTTP application and bounded loopback-only HTTP/1.x test adapter.

This is neither a public production server nor an OAuth provider. A trusted
integration must verify credentials/client/scopes before returning each Actor.
"""
from dataclasses import dataclass
import json
import re
import socket
import socketserver
import threading
import time
from typing import Protocol

from .actions_contracts import MAX_JSON_CHARS, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, ROUTES
from .contracts import Actor, WCEError
from .tools import ToolRouter, validate

EVIDENCE = {"transport": "mock", "mode": "test", "http_entrypoint": "local_preparation",
            "connected": False, "platform_verified": False}


class InvalidCredential(Exception):
    """Verifier certifies credential/client/scope rejection. Never embed secrets."""


class ActorVerifier(Protocol):
    def verify(self, bearer: str, required_scope: str) -> Actor:
        """Verify token, issuer/audience/client/scopes, then bind an existing session.

        Must be thread-safe. Return no identity from unverified claims. Revalidate
        on every request; service independently fences session/grant/resource.
        """


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: tuple = ()


def response(status, payload, headers=()):
    try:
        encoded = json.dumps(payload | EVIDENCE, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        body = encoded.encode("utf-8")
        if len(encoded) > MAX_JSON_CHARS or len(body) > MAX_RESPONSE_BYTES:
            raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError):
        status = 500
        body = json.dumps({"error": "RESPONSE_UNAVAILABLE_QUERY_OR_RECONCILE_OPERATION"} | EVIDENCE).encode()
    return Response(status, body, tuple(headers))


def failure(status, code, headers=()):
    if status == 401:
        headers = tuple(headers) + (("WWW-Authenticate", 'Bearer realm="WCE"'),)
    return response(status, {"error": code}, headers)


ERRORS = {
    "SESSION_INVALID": 401,
    **{code: 403 for code in ("ACCESS_DENIED", "CAPABILITY_UNAVAILABLE", "CONNECTION_REVOKED_OR_EXPIRED",
         "CONNECTION_REAUTHORIZATION_REQUIRED", "CONNECTION_AUTHORIZATION_UNVERIFIED", "TOKEN_EXPIRED",
         "AUTHORIZATION_CHANGED", "CONNECTION_STATE_INCOMPLETE", "TOKEN_UNAVAILABLE")},
    **{code: 404 for code in ("DRAFT_UNAVAILABLE", "OPERATION_UNAVAILABLE", "MATERIAL_UNAVAILABLE")},
    **{code: 409 for code in ("VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT", "UNRESOLVED_OPERATION", "HTTP_QUERY_UNRESOLVED")},
    **{code: 400 for code in ("INVALID_TOOL_ARGUMENTS", "INVALID_INPUT", "INVALID_MATERIALS", "INVALID_NEWS_TITLE",
         "INVALID_NEWS_CONTENT", "INVALID_NEWS_ARTICLE", "FIXTURE_COVER_REQUIRED")},
    "ADAPTER_READ_FAILED": 503, "DRAFT_READBACK_MISMATCH": 503,
}
ERRORS.update({
    **{code: 400 for code in ("INVALID_PREPARATION", "INVALID_LOCAL_IMAGE", "INVALID_FILE_REFERENCE",
        "INVALID_IMAGE_PATH", "INVALID_LOCAL_FILE", "UNSUPPORTED_IMAGE_FORMAT", "ASSET_ROLE_MISMATCH",
        "INVALID_UPLOAD_CONTEXT", "INVALID_PREPARED_DRAFT_CONTEXT")},
    **{code: 404 for code in ("HOST_INPUT_NOT_FOUND", "UPLOAD_NOT_FOUND", "PREPARED_DRAFT_NOT_FOUND")},
    **{code: 409 for code in ("PREPARATION_VERSION_CONFLICT", "ASSET_AUTHORIZATION_STALE", "LOCAL_FILE_CHANGED",
        "UPLOAD_TARGET_REGISTERED", "UNRESOLVED_UPLOAD", "PREPARED_DRAFT_TARGET_REGISTERED", "UNRESOLVED_PREPARED_DRAFT")},
    **{code: 413 for code in ("LOCAL_FILE_LIMIT", "PREPARATION_LIMIT")},
    **{code: 403 for code in ("HOST_INPUT_LEASE_EXPIRED", "UPLOAD_LEASE_EXPIRED", "PREPARED_DRAFT_LEASE_EXPIRED",
        "FILE_REFERENCE_EXPIRED", "FILE_REFERENCE_UNAVAILABLE")},
    **{code: 503 for code in ("SOURCE_UNCONFIGURED", "CANDIDATE_TEST_ONLY", "HOST_INPUT_JOURNAL_CORRUPT",
        "PREPARATION_CORRUPT", "UPLOAD_JOURNAL_CORRUPT", "PREPARED_DRAFT_JOURNAL_CORRUPT",
        "PREPARED_DRAFT_AUTHORIZATION_INVALID")},
})


def strict_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    def constant(_):
        raise ValueError
    text = body.decode("utf-8", errors="strict")
    if len(text) > MAX_JSON_CHARS:
        raise ValueError
    data = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(data, dict):
        raise ValueError
    # Reject unpaired surrogate escapes before business writes/digests.
    json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return data


class HTTPApplication:
    def __init__(self, service, verifier: ActorVerifier | None = None, prepared=None):
        self.service = service
        self.verifier = verifier
        if prepared is not None:
            from .prepared_host import HostDraftWorkflow
            if type(prepared) is not HostDraftWorkflow or prepared.service is not service:
                raise WCEError("SOURCE_UNCONFIGURED")
        self.prepared = prepared
        from .prepared_contracts import ROUTES as prepared_routes
        self.routes = ROUTES + prepared_routes if prepared is not None else ROUTES

    def handle(self, method, path, headers, body=b""):
        # Adapter passes raw duplicate-preserving headers, not a flattened dict.
        matches = [(route, route.match(path)) for route in self.routes]
        matches = [(route, args) for route, args in matches if args is not None]
        if not matches:
            return failure(404, "ROUTE_NOT_FOUND")
        selected = next(((r, a) for r, a in matches if r.method == method), None)
        if selected is None:
            return failure(405, "METHOD_NOT_ALLOWED", (("Allow", ", ".join(r.method for r, _ in matches)),))
        route, args = selected
        normalized = {}
        for name, value in headers:
            key = name.lower()
            if key in normalized:
                return failure(400, "DUPLICATE_HEADER")
            normalized[key] = value
        if "transfer-encoding" in normalized:
            return failure(400, "TRANSFER_ENCODING_UNSUPPORTED")
        if "expect" in normalized:
            return failure(417, "EXPECTATION_UNSUPPORTED")
        if "content-encoding" in normalized:
            return failure(415, "CONTENT_ENCODING_UNSUPPORTED")
        if len(body) > MAX_REQUEST_BYTES:
            return failure(413, "REQUEST_TOO_LARGE")
        if method == "GET" and body:
            return failure(400, "GET_BODY_UNSUPPORTED")
        if method == "POST":
            if not re.fullmatch(r"application/json(?:\s*;\s*charset=utf-8)?", normalized.get("content-type", ""), re.I):
                return failure(415, "JSON_UTF8_REQUIRED")
            try:
                args = strict_json(body)
            except (ValueError, UnicodeError, RecursionError):
                return failure(400, "INVALID_JSON_OBJECT")
        if self.verifier is None:
            return failure(503, "AUTHENTICATION_UNCONFIGURED")
        authorization = normalized.get("authorization", "")
        match = re.fullmatch(r"Bearer ([A-Za-z0-9._~+/\-]+=*)", authorization, re.I)
        if not match or len(authorization) > 4096:
            return failure(401, "AUTHENTICATION_REQUIRED")
        try:
            actor = self.verifier.verify(match.group(1), route.scope)
            if (not isinstance(actor, Actor) or any(not isinstance(value, str) or not value.strip() or len(value) > 128
                    for value in (actor.tenant_id, actor.principal_id, actor.client_id, actor.session_id))):
                raise InvalidCredential
        except InvalidCredential:
            return failure(401, "AUTHENTICATION_REQUIRED")
        except Exception:
            return failure(503, "AUTHENTICATION_UNAVAILABLE")
        try:
            if route.tool.startswith("prepared."):
                return response(200, self.prepared.call(actor, route.tool, args, "http"))
            spec = route.arguments()
            validate(args, spec)
            for name, value in args.items():
                if "pattern" in spec["properties"][name] and not re.fullmatch(spec["properties"][name]["pattern"], value):
                    raise WCEError("INVALID_TOOL_ARGUMENTS")
            # No Actor cached globally or shared between concurrent requests.
            result = ToolRouter(self.service, actor).call(route.tool, args)
            return response(200, result)
        except WCEError as error:
            code = error.code if error.code in ERRORS else "BUSINESS_REQUEST_UNAVAILABLE"
            return failure(ERRORS.get(code, 503), code)
        except Exception:
            return failure(500, "INTERNAL_ERROR_QUERY_OR_RECONCILE_OPERATION")


class ParseFailure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def request_line_method(line):
    """Only response framing; never an authentication or routing authority."""
    found = re.fullmatch(rb"([A-Z]+) [^\x00-\x20\x7f]+ HTTP/1\.[01]", line) if line.isascii() else None
    return found.group(1).decode("ascii") if found else None


class _Handler(socketserver.BaseRequestHandler):
    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ParseFailure(408, "REQUEST_TIMEOUT")
        self.request.settimeout(remaining)
        try:
            data = self.request.recv(4096)
        except TimeoutError:
            raise ParseFailure(408, "REQUEST_TIMEOUT") from None
        if not data:
            raise ParseFailure(400, "INCOMPLETE_REQUEST")
        return data

    def parse(self):
        deadline = time.monotonic() + self.server.read_deadline
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            buffer += self.receive(deadline)
            # Remember only a complete valid request line for response framing.
            # HEAD forbids a body even if later headers/length parsing fails.
            if b"\r\n" in buffer:
                line = buffer.split(b"\r\n", 1)[0]
                self._head = request_line_method(line) == "HEAD"
            head = buffer.split(b"\r\n\r\n", 1)[0]
            if len(head) > 16384:
                raise ParseFailure(431, "HEADERS_TOO_LARGE")
            if len(head.split(b"\r\n", 1)[0]) > 2048:
                raise ParseFailure(414, "REQUEST_TARGET_TOO_LARGE")
            if any(len(line) > 4096 for line in head.split(b"\r\n")[1:]):
                raise ParseFailure(431, "HEADER_LINE_TOO_LARGE")
        head, body = buffer.split(b"\r\n\r\n", 1)
        try:
            lines = head.decode("ascii").split("\r\n")
        except UnicodeError:
            raise ParseFailure(400, "INVALID_HEADERS") from None
        request = re.fullmatch(r"([A-Z]+) ([^\x00-\x20\x7f]+) (HTTP/1\.[01])", lines[0])
        if not request:
            raise ParseFailure(400, "INVALID_REQUEST_LINE")
        method, path, version = request.groups()
        if not path.startswith("/") or any(char in path for char in ("%", "?", "#", "\\")) or path.startswith("//"):
            raise ParseFailure(400, "INVALID_REQUEST_TARGET")
        if len(lines) - 1 > 32:
            raise ParseFailure(431, "TOO_MANY_HEADERS")
        headers, normalized = [], {}
        for line in lines[1:]:
            found = re.fullmatch(r"([!#$%&'*+.^_`|~0-9A-Za-z-]+):[ \t]*([^\x00-\x08\x0a-\x1f\x7f]*)", line)
            if not found:
                raise ParseFailure(400, "INVALID_HEADERS")
            name, value = found.groups()
            key, value = name.lower(), value.strip(" \t")
            if key in normalized:
                raise ParseFailure(400, "DUPLICATE_HEADER")
            normalized[key] = value
            headers.append((name, value))
        if version == "HTTP/1.1" and not normalized.get("host"):
            raise ParseFailure(400, "HOST_REQUIRED")
        if "host" in normalized and normalized["host"] != f"127.0.0.1:{self.server.server_address[1]}":
            raise ParseFailure(400, "HOST_MISMATCH")
        if "transfer-encoding" in normalized:
            raise ParseFailure(400, "TRANSFER_ENCODING_UNSUPPORTED")
        if "expect" in normalized:
            raise ParseFailure(417, "EXPECTATION_UNSUPPORTED")
        length = normalized.get("content-length")
        if length is None:
            if method == "POST":
                raise ParseFailure(400, "CONTENT_LENGTH_REQUIRED")
            length = 0
        elif not re.fullmatch(r"[0-9]{1,6}", length):
            raise ParseFailure(400, "INVALID_CONTENT_LENGTH")
        else:
            length = int(length)
        if length > MAX_REQUEST_BYTES:
            raise ParseFailure(413, "REQUEST_TOO_LARGE")
        if method != "POST" and length:
            raise ParseFailure(400, "BODY_UNSUPPORTED")
        while len(body) < length:
            body += self.receive(deadline)
        if len(body) != length:
            raise ParseFailure(400, "BODY_LENGTH_MISMATCH")
        return method, path, headers, body

    def handle(self):
        self._head = False
        try:
            parsed = self.parse()
            answer = self.server.application.handle(*parsed)
        except ParseFailure as error:
            answer = failure(error.status, error.code)
        except Exception:
            answer = failure(500, "INTERNAL_ERROR")
        self.server.send_response(self.request, answer, head=self._head)


class LoopbackHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Local test adapter. Fixed bounded workers, total read deadline, joined close."""
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False
    request_queue_size = 8

    def __init__(self, application, address=("127.0.0.1", 0), *, workers=8, read_deadline=3.0):
        if (address[0] != "127.0.0.1" or isinstance(address[1], bool) or not isinstance(address[1], int)
                or not 0 <= address[1] <= 65535 or isinstance(workers, bool) or not isinstance(workers, int)
                or not 1 <= workers <= 8 or not isinstance(read_deadline, (int, float))
                or isinstance(read_deadline, bool) or not 0 < read_deadline <= 3):
            raise ValueError("BOUNDED_LOOPBACK_CONFIGURATION_REQUIRED")
        self.application, self.read_deadline = application, read_deadline
        self._slots = threading.BoundedSemaphore(workers)
        super().__init__(address, _Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            # No ninth worker. Read only a bounded first line to honor HEAD.
            # Incomplete/invalid lines close without a fabricated HTTP reply.
            method = self.busy_method(request)
            if method is not None:
                self.send_response(request, failure(503, "LOCAL_SERVER_BUSY"), head=method == "HEAD")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            self.shutdown_request(request)
            raise

    @staticmethod
    def busy_method(request):
        line, deadline = b"", time.monotonic() + 0.1
        try:
            while not line.endswith(b"\r\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or len(line) >= 2050:
                    return None
                request.settimeout(remaining)
                byte = request.recv(1)
                if not byte:
                    return None
                line += byte
        except OSError:
            return None
        return request_line_method(line[:-2]) if len(line) <= 2050 else None

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        # Never log raw request, address, authorization, body or exception text.
        pass

    @staticmethod
    def send_response(request, answer, *, head=False):
        # Only fixed status and internal headers are emitted. No request echoes.
        from http import HTTPStatus
        line = f"HTTP/1.1 {answer.status} {HTTPStatus(answer.status).phrase}\r\n"
        headers = (("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(answer.body))),
                   ("Connection", "close"), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")) + answer.headers
        wire = (line + "".join(f"{name}: {value}\r\n" for name, value in headers) + "\r\n").encode("ascii")
        if not head:
            wire += answer.body
        try:
            request.settimeout(0.25)
            request.sendall(wire)
        except (OSError, TimeoutError):
            pass


def main():
    """Run a closed local entrypoint; no bearer map, fixture seed or env config."""
    import argparse
    from .mock import MockOfficialAccountAdapter
    from .service import OfficialAccountService
    parser = argparse.ArgumentParser(description="WCE本机HTTP准备入口：鉴权未配置，业务调用拒绝")
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    service = OfficialAccountService(args.db, MockOfficialAccountAdapter(args.db + ".mock.sqlite3"))
    with LoopbackHTTPServer(HTTPApplication(service), ("127.0.0.1", args.port)) as server:
        print(json.dumps({"host": "127.0.0.1", "port": server.server_address[1],
                          "authentication": "UNCONFIGURED", "deployment": "NOT_DEPLOYED"} | EVIDENCE), flush=True)
        try:
            server.serve_forever(poll_interval=0.05)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
