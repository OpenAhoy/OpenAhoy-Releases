"""One synchronous Images API request. The local job owns its lifetime."""
from base64 import b64decode
from binascii import Error as Base64Error
from http.client import HTTPException
import json
import re
from secrets import token_hex
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from .contracts import WCEError
from .video_seedance import MAX_RESULT, NoRedirect

ENDPOINT = 'https://api.openai.com/v1/images/edits'
MODEL = 'gpt-image-2.6-flare'
MAX_INPUT = 50_000_000
MAX_RESPONSE = (MAX_RESULT + 2) // 3 * 4 + 65536
REQUEST_ID = re.compile(r'req_[A-Za-z0-9_-]{1,128}\Z')
MIME_TYPES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}
REJECTIONS = {
    400: 'GIF_REQUEST_REJECTED', 401: 'GIF_AUTH_REQUIRED', 402: 'GIF_QUOTA_REQUIRED',
    403: 'GIF_ACCESS_REQUIRED', 404: 'GIF_ACCESS_REQUIRED', 413: 'GIF_REQUEST_REJECTED',
    415: 'GIF_REQUEST_REJECTED', 422: 'GIF_REQUEST_REJECTED', 429: 'GIF_RATE_LIMITED',
}
TRANSPORT_PHASES = frozenset({'BEFORE_RESPONSE_HEADERS', 'READ_RESPONSE_BODY'})
DIAGNOSTICS = frozenset(REJECTIONS.values()) | {'GIF_RESPONSE_INVALID', 'GIF_TRANSPORT_UNKNOWN',
    'GIF_HTTP_UNKNOWN', 'GIF_FINALIZE_PENDING', 'GIF_RESULT_INVALID', 'GIF_KEY_NOT_CONFIGURED',
    'GIF_KEYCHAIN_ACCESS_REQUIRED', 'GIF_SOURCE_CHANGED', 'GIF_SOURCE_INVALID', 'GIF_LOCAL_FAILURE'}


class EditFailure(WCEError):
    def __init__(self, code, status=None, *, phase=None):
        self.rejected = status in REJECTIONS
        self.diagnostic = {'code': code}
        if type(status) is int and 100 <= status <= 599:
            self.diagnostic['http_status'] = status
        if phase in TRANSPORT_PHASES:
            self.diagnostic['operation_phase'] = phase
        super().__init__(code)


def multipart(prompt, mime, image):
    boundary = 'OpenAhoy-' + token_hex(24)
    chunks = []
    for field, value in (('model', MODEL), ('output_format', 'gif'), ('n', '1'), ('prompt', prompt)):
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n'.encode())
        chunks.extend((value.encode(), b'\r\n'))
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                  f'filename="reference.{MIME_TYPES[mime]}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    chunks.extend((image, f'\r\n--{boundary}--\r\n'.encode()))
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary


def reflect_request_id(headers, notice):
    identifier = headers.get('x-request-id', '')
    if type(identifier) is str and REQUEST_ID.fullmatch(identifier):
        notice(identifier)


def rejection_code(error):
    code = REJECTIONS.get(error.code, 'GIF_HTTP_UNKNOWN')
    if error.code not in (400, 429):
        return code
    try:
        raw = error.read(16385)
        payload = json.loads(raw) if len(raw) <= 16384 else None
        detail = payload.get('error') if type(payload) is dict else None
        if type(detail) is dict:
            if detail.get('code') == 'insufficient_quota':
                return 'GIF_QUOTA_REQUIRED'
            if detail.get('code') in ('insufficient_permissions', 'model_not_found'):
                return 'GIF_ACCESS_REQUIRED'
    except (OSError, HTTPException, ValueError, RecursionError):
        pass
    return code


class OpenAIImages:
    def __init__(self, opener=None):
        # Use the configured HTTPS CONNECT route for the fixed origin. The
        # default HTTPS handler verifies the origin TLS certificate with SNI.
        self.opener = opener if opener is not None else build_opener(ProxyHandler(), NoRedirect())

    def edit(self, key, prompt, mime, image, notice):
        body, content_type = multipart(prompt, mime, image)
        request = Request(ENDPOINT, method='POST', data=body, headers={
            'Authorization': 'Bearer ' + key.reveal_for_adapter(), 'Content-Type': content_type,
            'Accept': 'application/json'})
        try:
            response = self.opener.open(request, timeout=150)
        except HTTPError as error:
            with error:
                reflect_request_id(error.headers, notice)
                raise EditFailure(rejection_code(error), error.code) from None
        except (OSError, HTTPException, EOFError):
            raise EditFailure('GIF_TRANSPORT_UNKNOWN', phase='BEFORE_RESPONSE_HEADERS') from None
        with response:
            reflect_request_id(response.headers, notice)
            try:
                raw = response.read(MAX_RESPONSE + 1)
            except (OSError, HTTPException, EOFError):
                raise EditFailure('GIF_TRANSPORT_UNKNOWN', phase='READ_RESPONSE_BODY') from None
        try:
            decoded = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
            data = decoded.get('data') if type(decoded) is dict else None
            if type(data) is not list or len(data) != 1 or type(data[0]) is not dict:
                raise ValueError()
            encoded = data[0].get('b64_json')
            result = b64decode(encoded, validate=True) if type(encoded) is str else b''
            if not 0 < len(result) <= MAX_RESULT:
                raise ValueError()
            return result
        except (ValueError, Base64Error, RecursionError):
            raise EditFailure('GIF_RESPONSE_INVALID') from None
