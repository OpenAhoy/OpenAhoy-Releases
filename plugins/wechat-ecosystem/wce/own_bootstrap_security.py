"""Explicit nonsecret configuration, terminal presentation and ordinary token lease.

No environment/keychain discovery, persistent platform secret or refresh path.
"""
from dataclasses import dataclass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import termios
import time
import unicodedata

from .bounded_file import FileSource, file_state, identity
from .contracts import Actor, Secret, WCEError
from .http_transport import HTTPRequest, HTTPResponse, HTTPSender
from .prepared_contracts import ID, strict_validate

FLAGS = {'platform_ready': False, 'platform_verified': False, 'connected': False}
MAX_JSON = 16384
TOKEN_SOURCE = '6819897cceb5f6d72cf29c0b9be819318620221395133f435d26944c208178a7'
NEWS_SOURCE = '33590fcd94a006ba96d9ce3ade3642fed0cab1679d64d1be0e8e78ba0d687b2c'


class TokenIPDenied(WCEError):
    """Keep the public error code; an optional literal is for the human TTY only."""
    def __init__(self, observed_ip=None):
        super().__init__('BOOTSTRAP_TOKEN_IP_DENIED')
        self.observed_ip = observed_ip


@dataclass(frozen=True)
class TokenRejectionProof:
    """Only the checked single-response parser creates retry evidence."""
    policy: str = 'STRICT_STABLE_TOKEN_IP_REJECTION_V1'
    code: int = 40164
    http_status: int = 200


class CheckedTokenRejected(WCEError):
    def __init__(self, code, observed_ip=None, proof=None):
        super().__init__(code)
        self.observed_ip = observed_ip
        self.proof = proof


def checked_rejection(response, data, secret):
    """Display classification is weaker than evidence permitting another attempt.

    Never retain the response/message/IP in durable proof or exception text.
    """
    message = data.get('errmsg')
    code = data.get('errcode')
    if (response.status != 200 or set(data) != {'errcode', 'errmsg'}
            or type(code) is not int or not -(2**31) <= code < 2**31 or not code
            or type(message) is not str or not 1 <= len(message) <= 512
            or any(unicodedata.category(c) in {'Cf', 'Cc', 'Cs', 'Zl', 'Zp'} for c in message)
            or secret.lower() in message.lower()
            or secret.lower().encode() in response.body.lower()):
        raise WCEError('BOOTSTRAP_TOKEN_INVALID_RESPONSE')
    classes = {40164: 'IP_DENIED', 45009: 'QUOTA_DENIED', 45011: 'QUOTA_DENIED',
               89503: 'ADMIN_PENDING', 89506: 'ADMIN_DENIED', 89507: 'ADMIN_DENIED',
               40013: 'CREDENTIAL_REJECTED', 40001: 'CREDENTIAL_REJECTED',
               40125: 'CREDENTIAL_REJECTED'}
    address = reported_ip(data, secret) if code == 40164 else None
    # ABSENT is supported; a claimed but malformed IP is never retry evidence.
    absent = re.fullmatch(r'not in whitelist(?:,? hint: \[[0-9A-Za-z_-]{1,128}\])?'
                          r'(?:,? rid: [0-9A-Za-z_-]{1,128})?', message) is not None
    proof = TokenRejectionProof() if code == 40164 and (address is not None or absent) else None
    raise CheckedTokenRejected('BOOTSTRAP_TOKEN_' + classes.get(code, 'REJECTED'), address, proof)


def reported_ip(data, secret):
    """Conservative local grammar, not a promise about every Tencent message."""
    if set(data) - {'errcode', 'errmsg'}:
        return None
    message = data.get('errmsg')
    if type(message) is not str or not 1 <= len(message) <= 512:
        return None
    match = re.fullmatch(
        r'invalid ip ([0-9A-Fa-f:.]+)(?: ipv6 ([0-9A-Fa-f:.]+))?, not in whitelist'
        r'(?:,? hint: \[[0-9A-Za-z_-]{1,128}\])?'
        r'(?:,? rid: [0-9A-Za-z_-]{1,128})?', message)
    if match is None or secret.lower() in message.lower():
        return None
    try:
        address = ipaddress.ip_address(match[1])
        if match[2] is not None:
            alias = ipaddress.ip_address(match[2])
            alias = alias.ipv4_mapped if isinstance(alias, ipaddress.IPv6Address) and alias.ipv4_mapped else alias
            original = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
            if alias != original:
                return None
    except ValueError:
        return None
    literal = str(address)
    if literal.lower() in secret.lower() or secret.lower() in literal.lower():
        return None
    # Synthetic callers may use an IP-shaped secret. Suppress equivalent IPv6
    # spellings and IPv4-mapped aliases, not just an exact substring reflection.
    try:
        credential_address = ipaddress.ip_address(secret)
    except ValueError:
        pass
    else:
        credential_address = (credential_address.ipv4_mapped
            if isinstance(credential_address, ipaddress.IPv6Address) and credential_address.ipv4_mapped
            else credential_address)
        candidate = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
        if credential_address == candidate:
            return None
    return literal


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def decode(data, maximum=MAX_JSON):
    if type(data) is not bytes or not 0 < len(data) <= maximum:
        raise WCEError('BOOTSTRAP_INVALID_JSON')
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise WCEError('BOOTSTRAP_INVALID_JSON') from None


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def path_check(path, directory=False):
    """Every absolute component is nonsymlink; final object is private and owned."""
    path = Path(path)
    if not path.is_absolute() or any(p in {'.', '..'} for p in path.parts) or len(path.parts) > 32:
        raise WCEError('BOOTSTRAP_UNSAFE_PATH')
    try:
        current = Path('/')
        for part in path.parts[1:]:
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError()
            if current != path and not stat.S_ISDIR(info.st_mode):
                raise ValueError()
        if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
                or (not directory and info.st_nlink != 1)):
            raise ValueError()
        return identity(info) if directory else file_state(info)
    except Exception:
        raise WCEError('BOOTSTRAP_UNSAFE_PATH') from None


def private_read(path):
    path = Path(path)
    before = path_check(path)
    if not 0 < path.stat().st_size <= MAX_JSON:
        raise WCEError('BOOTSTRAP_INVALID_JSON')
    source = FileSource(path.parent)
    value = source.read(path.name)
    if before != path_check(path):
        raise WCEError('BOOTSTRAP_PATH_CHANGED')
    from .draft_group_upload_proof_reads import observe_private_read
    observe_private_read(path,value,before)
    return value, before


@dataclass(frozen=True)
class BootstrapConfig:
    path: Path
    data: dict
    file_pin: tuple
    directory_pin: tuple
    image_pin: tuple

    @property
    def root(self):
        return self.path.parent

    @property
    def actor(self):
        a = self.data['actor']
        return Actor(a['tenant_id'], a['principal_id'], a['client_id'], a['session_id'])

    def check(self, now=None):
        if (path_check(self.path) != self.file_pin or path_check(self.root, True) != self.directory_pin
                or path_check(self.root / 'images', True) != self.image_pin):
            raise WCEError('BOOTSTRAP_PATH_CHANGED')
        if (time.time() if now is None else now) >= self.data['expires_at']:
            raise WCEError('BOOTSTRAP_CONFIG_EXPIRED')
        db = self.root / 'state.sqlite3'
        if os.path.lexists(db):
            path_check(db)
        return True


def load_config(path, now=None):
    now = time.time() if now is None else now
    try:
        path = Path(path)
        raw, pin = private_read(path)
        d = decode(raw)
        fields = {'schema', 'source_kind', 'appid', 'resource_id', 'connection_id', 'actor',
                  'generation', 'epoch', 'expires_at', 'private_directory'}
        if (type(d) is not dict or set(d) != fields or type(d['schema']) is not int or d['schema'] != 1
                or d['source_kind'] != 'OPERATOR_ATTESTED'
                or type(d['appid']) is not str or re.fullmatch(r'wx[a-fA-F0-9]{16}', d['appid']) is None
                or d['resource_id'] != d['appid'] or type(d['actor']) is not dict
                or set(d['actor']) != {'tenant_id', 'principal_id', 'client_id', 'session_id'}
                or type(d['generation']) is not int or not 1 <= d['generation'] <= 2**63 - 1
                or type(d['epoch']) is not int or not 0 <= d['epoch'] <= 2**63 - 1
                or not finite(d['expires_at']) or not finite(now)
                or not now < d['expires_at'] <= now + 86400
                or type(d['private_directory']) is not str or Path(d['private_directory']) != path.parent):
            raise ValueError()
        for v in (*d['actor'].values(), d['connection_id']):
            strict_validate(v, ID)
        result = BootstrapConfig(path, d, pin, path_check(path.parent, True),
                                 path_check(path.parent / 'images', True))
        result.check(now)
        return result
    except WCEError:
        raise
    except Exception:
        raise WCEError('BOOTSTRAP_INVALID_CONFIG') from None


def safe_text(value):
    """Display encoding only; the immutable article bytes never pass through it."""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    out = []
    for char in text:
        n = ord(char)
        if unicodedata.category(char) in {'Cf', 'Cc', 'Cs', 'Zl', 'Zp'}:
            out.append('\\u%04x' % n)
        else:
            out.append(char)
    return ''.join(out)


class Terminal:
    def __init__(self, source, destination):
        if not source.isatty() or not destination.isatty():
            raise WCEError('BOOTSTRAP_TTY_REQUIRED')
        a, b = os.fstat(source.fileno()), os.fstat(destination.fileno())
        if not stat.S_ISCHR(a.st_mode) or not stat.S_ISCHR(b.st_mode) or a.st_rdev != b.st_rdev:
            raise WCEError('BOOTSTRAP_TTY_MISMATCH')
        self.source, self.destination = source, destination
        self.fd = source.fileno()

    def write(self, trusted):
        self.destination.write(trusted + '\n')
        self.destination.flush()

    def display(self, value):
        text = safe_text(value)
        for start in range(0, len(text), 120):
            self.write('DATA | ' + text[start:start + 120])

    def flush(self):
        termios.tcflush(self.fd, termios.TCIFLUSH)

    def ask(self, label, hidden=False):
        self.flush()
        previous = termios.tcgetattr(self.fd)
        try:
            if hidden:
                mode = termios.tcgetattr(self.fd)
                mode[3] &= ~(termios.ECHO | termios.ECHONL)
                termios.tcsetattr(self.fd, termios.TCSAFLUSH, mode)
            self.write('TRUSTED ' + label)
            value = self.source.readline(4098)
            if not value:
                raise EOFError()
            if len(value) > 4096 or not value.endswith('\n'):
                raise WCEError('BOOTSTRAP_INVALID_INPUT')
            return value[:-1]
        finally:
            if hidden:
                termios.tcsetattr(self.fd, termios.TCSAFLUSH, previous)
                self.write('TRUSTED HIDDEN_INPUT_COMPLETE')


def acquire(appid, secret, sender=None, clock=time.time):
    """One fixed ordinary request. Call only after the separate TTY input gate."""
    return _acquire(appid, secret, sender, clock, 300)


def acquire_pending(appid, secret, sender=None, clock=time.time, *, absolute_deadline=None):
    """Host-private validation; this result grants no active execution lease."""
    return _acquire(appid, secret, sender, clock, 7200,
                    absolute_deadline=absolute_deadline)


def acquire_checked(appid, secret, sender=None, clock=time.time):
    """Trusted Settings only. One ordinary request, with strict error evidence."""
    return _acquire(appid, secret, sender, clock, 7200, checked=True)


def _acquire(appid, secret, sender, clock, maximum_seconds, checked=False, *, absolute_deadline=None):
    if absolute_deadline is not None and (type(absolute_deadline) not in (int, float)
            or not math.isfinite(absolute_deadline)):
        raise WCEError('BOOTSTRAP_TOKEN_DEADLINE_INVALID')
    sender = HTTPSender(enabled=True) if sender is None else sender
    started, monotonic_start = clock(), time.monotonic()
    try:
        request = _token_request(appid, secret)
        timeout = 10.0
        if absolute_deadline is not None:
            remaining = absolute_deadline - time.monotonic()
            if remaining <= 0:
                raise WCEError('BOOTSTRAP_TOKEN_QUEUE_EXPIRED')
            timeout = min(timeout, remaining)
        response = sender.send(request, timeout)
        if absolute_deadline is not None and time.monotonic() >= absolute_deadline:
            raise WCEError('BOOTSTRAP_TOKEN_QUEUE_EXPIRED')
        return _token_response(response, secret, clock, maximum_seconds, checked, started, monotonic_start)
    except WCEError:
        raise
    except Exception:
        raise WCEError('BOOTSTRAP_TOKEN_RESULT_UNKNOWN') from None


def _token_request(appid, secret):
    if (type(appid) is not str or re.fullmatch('wx[a-fA-F0-9]{16}', appid) is None
            or type(secret) is not str or not 1 <= len(secret) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in secret)):
        raise WCEError('BOOTSTRAP_CREDENTIAL_INVALID')
    request = HTTPRequest('POST', '/cgi-bin/stable_token',
        {'Content-Type': 'application/json; charset=utf-8'},
        json.dumps({'grant_type': 'client_credential', 'appid': appid, 'secret': secret,
                    'force_refresh': False}, separators=(',', ':')).encode())
    return request



def _token_response(response, secret, clock, maximum_seconds, checked, started, monotonic_start):
    if type(response) is not HTTPResponse or type(response.status) is not int or not 200 <= response.status < 300:
        raise WCEError('BOOTSTRAP_TOKEN_HTTP_FAILED')
    data = decode(response.body)
    if type(data) is not dict:
        raise WCEError('BOOTSTRAP_TOKEN_INVALID_RESPONSE')
    if 'errcode' in data:
        code = data['errcode']
        if type(code) is not int:
            raise WCEError('BOOTSTRAP_TOKEN_INVALID_RESPONSE')
        if code:
            if checked:
                checked_rejection(response, data, secret)
            if code == 40164:
                raise TokenIPDenied(reported_ip(data, secret))
            classes = {45009: 'QUOTA_DENIED', 45011: 'QUOTA_DENIED',
                       89503: 'ADMIN_PENDING', 89506: 'ADMIN_DENIED', 89507: 'ADMIN_DENIED'}
            raise WCEError('BOOTSTRAP_TOKEN_' + classes.get(code, 'REJECTED'))
    if set(data) - {'access_token', 'expires_in', 'errcode'} or not {'access_token', 'expires_in'} <= set(data):
        raise WCEError('BOOTSTRAP_TOKEN_INVALID_RESPONSE')
    token, ttl = data['access_token'], data['expires_in']
    if (type(token) is not str or not 1 <= len(token) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
            or secret in token or type(ttl) is not int or not 0 < ttl <= 7200):
        raise WCEError('BOOTSTRAP_TOKEN_INVALID_RESPONSE')
    expires = started + min(ttl, maximum_seconds)
    mono_expires = monotonic_start + min(ttl, maximum_seconds)
    if not clock() < expires or not time.monotonic() < mono_expires:
        raise WCEError('BOOTSTRAP_TOKEN_EXPIRED')
    return Secret(token), expires, mono_expires

