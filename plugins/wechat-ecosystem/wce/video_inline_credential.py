"""One-use, purpose-scoped Ark credential submission from the native app."""
from hashlib import sha256
import secrets
import threading
import time

from .contracts import WCEError
from .own_inline_crypto import NativeCrypto
from .openai_gif_keychain import PROVIDER as GIF_PROVIDER, PURPOSE as GIF_PURPOSE, save as save_gif
from .video_keychain import save
from .video_seedance import BYTEPLUS_PROVIDER
from .video_sand import PROVIDER as SAND_PROVIDER
from .video_relay import relay_origin
from .video_relay_keychain import save_relay
from .video_tokenhex import TOKENHEX_PROVIDER, TOKENHEX_PURPOSE, save_tokenhex

PURPOSE = 'openahoy:video:ark:cn-beijing:key:v1'
BYTEPLUS_PURPOSE = 'openahoy:video:ark:ap-southeast-1:key:v1'
SAND_PURPOSE = 'openahoy:video:sand:key:v1'
RELAY_PURPOSE = 'openahoy:video:comfyui-relay:key:v1:'
TTL = 120


class InlineVideoCredential:
    def __init__(self, *, crypto_factory=NativeCrypto, writer=save, relay_writer=save_relay,
                 gif_writer=save_gif, tokenhex_writer=save_tokenhex, clock=time.monotonic):
        self.crypto_factory = crypto_factory
        self.writer = writer
        self.relay_writer = relay_writer
        self.gif_writer = gif_writer
        self.tokenhex_writer = tokenhex_writer
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

    def begin(self, provider='ark', *, base_url=None):
        origin = relay_origin(base_url) if provider == 'relay' else None
        with self.lock:
            if self.closed:
                raise WCEError('VIDEO_CREDENTIAL_SESSION_EXPIRED')
            self._clear()
            crypto = self.crypto_factory()
            try:
                if origin is not None:
                    purpose = RELAY_PURPOSE + sha256(origin.encode()).hexdigest()
                elif provider == BYTEPLUS_PROVIDER:
                    purpose = BYTEPLUS_PURPOSE
                elif provider == SAND_PROVIDER:
                    purpose = SAND_PURPOSE
                elif provider == GIF_PROVIDER:
                    purpose = GIF_PURPOSE
                elif provider == TOKENHEX_PROVIDER:
                    purpose = TOKENHEX_PURPOSE
                else:
                    purpose = PURPOSE if provider == 'ark' else 'openahoy:video:minimax:' + provider + ':key:v1'
                challenge = crypto.begin(purpose)
                session = secrets.token_hex(32)
                timer = threading.Timer(TTL, self._expire, args=(session,))
                timer.daemon = True
                self.pending = {'crypto': crypto, 'challenge': challenge, 'session': session,
                                'created': self.clock(), 'timer': timer, 'purpose': purpose,
                                'provider': provider, 'origin': origin}
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
                if item['provider'] == 'relay':
                    return self.relay_writer(item['origin'], secret.reveal_for_adapter())
                if item['provider'] == GIF_PROVIDER:
                    return self.gif_writer(secret.reveal_for_adapter())
                if item['provider'] == TOKENHEX_PROVIDER:
                    return self.tokenhex_writer(secret.reveal_for_adapter())
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
