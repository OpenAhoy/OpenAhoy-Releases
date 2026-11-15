"""One-use, purpose-scoped Ark credential submission from the native app."""
import secrets
import threading
import time

from .contracts import WCEError
from .own_inline_crypto import NativeCrypto
from .video_keychain import save

PURPOSE = 'openahoy:video:ark:cn-beijing:key:v1'
TTL = 120


class InlineVideoCredential:
    def __init__(self, *, crypto_factory=NativeCrypto, writer=save, clock=time.monotonic):
        self.crypto_factory = crypto_factory
        self.writer = writer
        self.clock = clock
        self.lock = threading.RLock()
        self.pending = None
        self.closed = False

    def _clear(self):
        item, self.pending = self.pending, None
        if item is not None:
            item['timer'].cancel()
            item['crypto'].close()

    def _expire(self, session):
        with self.lock:
            if self.pending and self.pending['session'] == session:
                self._clear()

    def begin(self, provider='ark'):
        with self.lock:
            if self.closed:
                raise WCEError('VIDEO_CREDENTIAL_SESSION_EXPIRED')
            self._clear()
            crypto = self.crypto_factory()
            try:
                purpose = PURPOSE if provider == 'ark' else 'openahoy:video:minimax:' + provider + ':key:v1'
                challenge = crypto.begin(purpose)
                session = secrets.token_hex(32)
                timer = threading.Timer(TTL, self._expire, args=(session,))
                timer.daemon = True
                self.pending = {'crypto': crypto, 'challenge': challenge, 'session': session,
                                'created': self.clock(), 'timer': timer, 'purpose': purpose, 'provider': provider}
                timer.start()
            except BaseException:
                self.pending = None
                crypto.close()
                raise
            return {'state': 'READY', 'purpose': purpose, 'session': session, 'challenge': challenge}

    def submit(self, session, jwe):
        with self.lock:
            item = self.pending
            if (self.closed or item is None or not secrets.compare_digest(session, item['session'])):
                raise WCEError('VIDEO_CREDENTIAL_SESSION_EXPIRED')
            elapsed = self.clock() - item['created']
            try:
                if not 0 <= elapsed < TTL:
                    raise WCEError('VIDEO_CREDENTIAL_SESSION_EXPIRED')
                purpose, secret = item['crypto'].decrypt(item['challenge'], jwe)
                if purpose != item['purpose'] or not 0 <= self.clock() - item['created'] < TTL:
                    raise WCEError('VIDEO_CREDENTIAL_ENVELOPE_REJECTED')
            finally:
                # Spend the challenge before the Keychain call, including failure.
                self._clear()
            try:
                if item['provider'] == 'ark':
                    return self.writer(secret.reveal_for_adapter())
                return self.writer(secret.reveal_for_adapter(), provider=item['provider'])
            finally:
                secret = None

    def cancel(self, session):
        with self.lock:
            if self.pending and secrets.compare_digest(session, self.pending['session']):
                self._clear()
            return {'state': 'CLOSED'}

    def close(self):
        with self.lock:
            self.closed = True
            self._clear()
