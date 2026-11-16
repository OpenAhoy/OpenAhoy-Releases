"""Fixed native JWE adapter; private stdin/stdout only, never an MCP server."""
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import threading
import time

IO_TIMEOUT = 20
STORAGE_APP = 'OpenAhoyStorageRecovery.app'
STORAGE_EXECUTABLE = 'Contents/MacOS/OpenAhoyStorageRecovery'
STORAGE_REQUIREMENT = (
    'anchor apple generic and identifier "ai.openahoy.storage-recovery" '
    'and certificate leaf[subject.OU] = "96NDFJJHRY" '
    'and certificate leaf[field.1.2.840.113635.100.6.1.13] exists'
)
from .contracts import Secret, WCEError
from .own_keychain import valid_secret
from .own_bootstrap_security import unique


class NativeCrypto:
    def __init__(self, artifacts=None, *, storage=False):
        directory = Path(artifacts) if artifacts is not None else Path(__file__).resolve().parents[1] / 'native'
        try:
            # All paths are fixed package inputs, never caller supplied locators.
            binary = directory / 'inline-binding-crypto'
            private_paths = [directory, directory / 'manifest.json']
            if storage:
                app = directory / STORAGE_APP
                binary = app / STORAGE_EXECUTABLE
                private_paths.extend((app, app / 'Contents', binary.parent))
            for p in (*private_paths, binary):
                st = p.lstat()
                if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
                    raise ValueError()
            manifest = json.loads((directory / 'manifest.json').read_bytes(), object_pairs_hook=unique)
            if (manifest.get('schema') != 1 or manifest.get('platform') != 'macos-arm64'
                    or hashlib.sha256(binary.read_bytes()).hexdigest() !=
                        manifest['storage_sha256' if storage else 'sha256']
                    or not stat.S_ISREG(binary.stat().st_mode) or binary.stat().st_nlink != 1):
                raise ValueError()
            if storage:
                subprocess.run(['/usr/bin/codesign','--verify','--strict',
                    '-R='+STORAGE_REQUIREMENT,str(app)],check=True,timeout=3,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, close_fds=True, bufsize=0, env={'PATH': '/usr/bin:/bin'})
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
        except Exception:
            raise WCEError('INLINE_BINDING_CRYPTO_UNAVAILABLE') from None
        self.lock, self.closed = threading.Lock(), False

    def _stop(self):
        self.closed = True
        try:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=2)
        finally:
            self.process.stdout.close()

    def call(self, value, *, timeout=None):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise WCEError('INLINE_BINDING_KEY_EXPIRED')
            try:
                raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'
                if len(raw) > 32768:
                    raise ValueError()
                deadline = time.monotonic() + (IO_TIMEOUT if timeout is None else timeout)
                incoming, outgoing = self.process.stdout.fileno(), self.process.stdin.fileno()
                offset = 0
                while offset < len(raw):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([], [outgoing], [], remaining)[1]:
                        raise ValueError()
                    try:
                        written = os.write(outgoing, raw[offset:])
                    except BlockingIOError:
                        continue
                    if written <= 0:
                        raise ValueError()
                    offset += written
                raw = None
                reply = bytearray()
                while not reply.endswith(b'\n'):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([incoming], [], [], remaining)[0]:
                        raise ValueError()
                    try:
                        chunk = os.read(incoming, 32769 - len(reply))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise ValueError()
                    reply.extend(chunk)
                    if len(reply) > 32768 or b'\n' in reply[:-1]:
                        raise ValueError()
                result = json.loads(reply, object_pairs_hook=unique)
                reply[:] = b''
                if type(result) is not dict or type(result.get('ok')) is not bool:
                    raise ValueError()
                if result['ok'] is False:
                    if set(result) != {'ok', 'error'} or result['error'] not in {
                            'ENVELOPE_REJECTED', 'INVALID_REQUEST', 'CRYPTO_UNAVAILABLE', 'KEY_UNAVAILABLE',
                            'RECOVERY_WITNESS_UNAVAILABLE',
                            'RECOVERY_CONFIRMATION_UNAVAILABLE', 'RECOVERY_CONFIRMATION_EXPIRED',
                            'RECOVERY_CONFIRMATION_CANCELLED'}:
                        raise ValueError()
                    return result
                return result
            except Exception:
                self._stop()
                raise WCEError('INLINE_BINDING_CRYPTO_UNAVAILABLE') from None

    def begin(self, appid):
        value = self.call({'operation': 'begin', 'appid': appid})
        if set(value) != {'ok', 'intent', 'kid', 'nonce', 'publicSPKI'} or any(type(v) is not str for k,v in value.items() if k != 'ok'):
            raise WCEError('INLINE_BINDING_CRYPTO_UNAVAILABLE')
        return {k:v for k,v in value.items() if k != 'ok'}

    def decrypt(self, challenge, jwe):
        value = self.call({'operation':'decrypt', 'intent':challenge['intent'], 'jwe':jwe})
        try:
            if set(value) != {'ok','intent','appid','secret'} or value['intent'] != challenge['intent'] or not valid_secret(value['secret']):
                raise ValueError()
            return value['appid'], Secret(value.pop('secret'))
        except Exception:
            raise WCEError('INLINE_BINDING_ENVELOPE_REJECTED') from None
        finally:
            value.clear()

    def cancel(self, challenge):
        self.call({'operation':'cancel', 'intent':challenge['intent']})

    def close(self):
        with self.lock:
            if not self.closed:
                self._stop()
