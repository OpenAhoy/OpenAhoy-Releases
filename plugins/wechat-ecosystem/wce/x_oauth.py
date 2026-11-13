"""Ephemeral, one-use loopback PKCE flow. Codes and verifier stay in memory."""
import base64
from contextlib import contextmanager
from hashlib import sha256
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from .contracts import WCEError
from .x_api import CALLBACK, SCOPES


class OAuthFlow:
    def __init__(self, client_id, api, finish, *, server_factory=ThreadingHTTPServer, clock=time.monotonic):
        self.client_id, self.api, self.finish, self.clock = client_id, api, finish, clock
        self.lock = threading.RLock()
        self.state = 'AWAITING_AUTHORIZATION'
        self.result = None
        self.expires = clock() + 300
        self._verifier = secrets.token_urlsafe(48)
        self._state = secrets.token_urlsafe(32)
        self._stop = threading.Event()
        self._terminal_at = None
        flow = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # request target contains the one-time authorization code.

            def do_GET(self):
                if self.headers.get('Host') != '127.0.0.1:62197':
                    self.send_error(400)
                    return
                try:
                    parsed = urlsplit(self.path)
                except ValueError:
                    self.send_error(400)
                    return
                if parsed.scheme or parsed.netloc or parsed.fragment:
                    self.send_error(400)
                    return
                if parsed.path == '/x/done' and not parsed.query:
                    raw = ('<!doctype html><meta charset="utf-8"><title>OpenAhoy · X</title>'
                           '<p>本次授权已处理，请返回 OpenAhoy 查看连接状态。</p>').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(raw)))
                    self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if parsed.path != '/x/callback' or len(parsed.query) > 8192:
                    self.send_error(404)
                    return
                try:
                    values = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True,
                                      max_num_fields=3)
                except ValueError:
                    self.send_error(400)
                    return
                if (set(values) not in ({'code', 'state'}, {'error', 'state'}) or
                        any(len(v) != 1 or not v[0] for v in values.values())):
                    self.send_error(400)
                    return
                if not flow.consume(values):
                    self.send_error(400)
                    return
                self.send_response(303)
                self.send_header('Location', '/x/done')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()

        try:
            self.server = server_factory(('127.0.0.1', 62197), Handler)
        except OSError:
            raise WCEError('X_CALLBACK_PORT_BUSY') from None
        self.server.timeout = 0.2
        self.thread = threading.Thread(target=self._serve, name='OpenAhoy-X-OAuth', daemon=True)
        self.thread.start()

    def authorization_url(self):
        challenge = base64.urlsafe_b64encode(sha256(self._verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://x.com/i/oauth2/authorize?' + urlencode({
            'response_type': 'code', 'client_id': self.client_id, 'redirect_uri': CALLBACK,
            'scope': ' '.join(SCOPES), 'state': self._state,
            'code_challenge': challenge, 'code_challenge_method': 'S256'})

    def consume(self, values):
        with self.lock:
            if (self.state != 'AWAITING_AUTHORIZATION' or self.clock() >= self.expires or
                    not hmac.compare_digest(values['state'][0], self._state)):
                return False
            self.state = 'EXCHANGING'
            verifier = self._verifier
        result, state = None, 'FAILED'
        try:
            if 'error' in values:
                result, state = {'error': 'X_AUTHORIZATION_DENIED'}, 'DENIED'
            else:
                tokens = self.api.exchange(self.client_id, values['code'][0], verifier)
                result = self.finish(self.client_id, tokens, self.commit_guard)
                state = 'BOUND'
        except WCEError as error:
            result = {'error': error.code}
        except Exception:
            result = {'error': 'X_AUTHORIZATION_RESULT_UNKNOWN'}
        finally:
            verifier = ''
            with self.lock:
                if self.state != 'CANCELLED':
                    self.state, self.result = state, result
                self._verifier = self._state = ''
                self._terminal_at = self.clock()
        return True

    @contextmanager
    def commit_guard(self):
        with self.lock:
            if self.state != 'EXCHANGING' or self._stop.is_set() or self.clock() >= self.expires:
                raise WCEError('X_AUTHORIZATION_CANCELLED_OR_EXPIRED')
            yield

    def snapshot(self):
        with self.lock:
            if self.state == 'AWAITING_AUTHORIZATION' and self.clock() >= self.expires:
                self.state = 'EXPIRED'
                self._verifier = self._state = ''
                self._stop.set()
            return {'state': self.state, 'result': self.result}

    def _serve(self):
        try:
            while not self._stop.is_set():
                if self.clock() >= self.expires or (self._terminal_at is not None and self.clock() > self._terminal_at + 10):
                    self.snapshot()
                    break
                self.server.handle_request()
        finally:
            self.server.server_close()

    def close(self):
        # Fence only the short credential commit, not the outbound HTTP exchange.
        with self.lock:
            if self.state in {'AWAITING_AUTHORIZATION', 'EXCHANGING'}:
                self.state = 'CANCELLED'
            self._verifier = self._state = ''
            self._stop.set()
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=1)
