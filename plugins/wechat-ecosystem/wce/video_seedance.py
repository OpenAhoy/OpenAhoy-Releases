"""Fixed Ark China request and a separate, credential-free result download."""
import base64
import json
from http.client import HTTPException
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .contracts import WCEError
from .own_bootstrap_security import decode

MODEL = 'doubao-seedance-2-5-260628'
MINI = 'doubao-seedance-2-0-mini-260615'
PRO = 'doubao-seedance-1-0-pro-250528'
STANDARD = 'doubao-seedance-2-0-260128'
FLASH = 'doubao-seedance-2-5-flash-261115'
FAST = 'doubao-seedance-2-0-fast-260128'
PRO_FAST = 'doubao-seedance-1-0-pro-fast-251015'
ARK_RATIOS = ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16')
MODERN_MODES = ('text', 'first', 'frames', 'reference', 'edit', 'extend')
ARK_MODELS = {
    MODEL: (MODERN_MODES, 4, 30, ('480p', '720p', '1080p', '4k'), True),
    FLASH: (MODERN_MODES, 4, 30, ('480p', '720p'), True),
    STANDARD: (MODERN_MODES, 4, 15, ('480p', '720p', '1080p', '4k'), True),
    FAST: (MODERN_MODES, 4, 15, ('480p', '720p'), True),
    MINI: (MODERN_MODES, 4, 15, ('480p', '720p'), True),
    PRO: (('text', 'first', 'frames'), 2, 12, ('480p', '720p', '1080p'), False),
    PRO_FAST: (('text', 'first'), 2, 12, ('480p', '720p', '1080p'), False),
}
SUPPORTED_MODELS = tuple(ARK_MODELS)
TASKS = 'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks'
RESULT_HOSTS = frozenset({'ark-content-generation-cn-beijing.tos-cn-beijing.volces.com',
                          'ark-acg-cn-beijing.tos-cn-beijing.volces.com'})
TASK_ID = re.compile(r'cgt-[A-Za-z0-9-]{1,120}\Z')
MAX_REQUEST = 64_000_000
MAX_REFERENCE_IMAGES = 30
MAX_RESULT = 64 * 1024 * 1024
MAX_JSON = 256 * 1024
MAX_REJECTION_BODY = 8 * 1024
REJECTION_STATUSES = frozenset({400, 401, 403, 404, 422, 429})
ARK_ERROR_CODES = frozenset({
    'MissingParameter', 'InvalidParameter', 'InvalidParameter.TaskTypeConstraint',
    'InvalidParameter.TaskTypeMismatch', 'InvalidParameter.UnsupportedParameter',
    'InvalidImageURL.EmptyURL', 'InvalidImageURL.InvalidFormat',
    'InvalidEndpoint.ClosedEndpoint', 'InvalidEndpointOrModel.NotFound',
    'InvalidEndpointOrModel.ModelIDAccessDisabled', 'ModelNotOpen',
    'AuthenticationError', 'InvalidAccountStatus', 'AccessDenied',
    'OperationDenied.PermissionDenied', 'OperationDenied.ServiceNotOpen',
    'OperationDenied.ServiceOverdue', 'AccountOverdueError',
    'SensitiveContentDetected', 'InputTextSensitiveContentDetected',
    'InputImageSensitiveContentDetected', 'InputImageSensitiveContentDetected.PrivacyInformation',
    'InputTextSensitiveContentDetected.PolicyViolation', 'InputImageSensitiveContentDetected.PolicyViolation',
    'InputTextRiskDetection', 'InputImageRiskDetection',
    'OutputVideoSensitiveContentDetected', 'OutputVideoSensitiveContentDetected.PolicyViolation',
    'InputVideoSensitiveContentDetected', 'InputVideoSensitiveContentDetected.PolicyViolation',
    'InternalServiceError', 'ServiceUnavailable', 'ServerOverloaded',
    'RateLimitExceeded.EndpointRPMExceeded', 'RateLimitExceeded.EndpointTPMExceeded',
    'ModelAccountRpmRateLimitExceeded', 'ModelAccountTpmRateLimitExceeded',
    'APIAccountRpmRateLimitExceeded', 'QuotaExceeded', 'AccountQuotaExceeded', 'SetLimitExceeded',
})
ARK_TRACE = re.compile(r'(?:20[0-9]{12}[A-Za-z0-9]{20}|021[0-9a-f]{50})', flags=re.ASCII)


def ark_error_code(value, key=None):
    error = value.get('error')
    code = error.get('code') if type(error) is dict else None
    return code if type(code) is str and code in ARK_ERROR_CODES and (key is None or key not in code) else None


class ArkSubmitRejected(WCEError):
    def __init__(self, response, key):
        super().__init__('VIDEO_SUBMIT_REJECTED')
        self.diagnostic = {'http_status': response.code}
        headers = response.headers
        if headers is not None:
            for name in ('X-Tt-Logid', 'X-Request-Id'):
                values = headers.get_all(name, [])
                if (len(values) == 1 and ARK_TRACE.fullmatch(values[0])
                        and key not in values[0] and values[0] not in key):
                    self.diagnostic['ark_request_id'] = values[0]
                    break
        try:
            value = decode(response.read(MAX_REJECTION_BODY + 1), MAX_REJECTION_BODY)
        except (OSError, HTTPException, WCEError):
            return
        code = ark_error_code(value, key) if type(value) is dict else None
        if code:
            self.diagnostic['ark_error_code'] = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_model(model):
    if model not in SUPPORTED_MODELS:
        raise WCEError('VIDEO_MODEL_UNSUPPORTED')


def request_body(prompt, frames, *, model=MODEL, mode='frames', duration=5, resolution='720p',
                 audio=False, reference=None, direction=None, ratio='adaptive'):
    validate_model(model)
    modes, minimum, maximum, resolutions, supports_audio = ARK_MODELS[model]
    if mode not in modes:
        raise WCEError('VIDEO_MODE_UNSUPPORTED')
    if type(duration) is not int or not minimum <= duration <= maximum and not (
            duration == -1 and supports_audio):
        raise WCEError('VIDEO_DURATION_INVALID')
    if resolution not in resolutions or type(audio) is not bool or (audio and not supports_audio):
        raise WCEError('VIDEO_OUTPUT_UNSUPPORTED')
    if ratio not in ('adaptive', *ARK_RATIOS):
        raise WCEError('VIDEO_OUTPUT_INVALID')
    if mode == 'edit' and duration != -1 or mode == 'extend' and direction not in ('before','after'):
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    minimum, maximum = {'first': (1, 1), 'frames': (2, 2), 'reference': (1, MAX_REFERENCE_IMAGES)}.get(mode, (0, 0))
    if not minimum <= len(frames) <= maximum or (mode in ('edit', 'extend')) != bool(reference):
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    if mode == 'extend':
        side = '向前' if direction == 'before' else '向后'
        prompt = f'将参考视频{side}延长。{prompt}'
    content = [{'type': 'text', 'text': prompt}]
    roles = ('first_frame', 'last_frame')[:len(frames)] if mode in ('first', 'frames') else ('reference_image',) * len(frames)
    for role, (mime, raw) in zip(roles, frames, strict=True):
        encoded = base64.b64encode(raw).decode('ascii')
        content.append({'type': 'image_url', 'role': role,
                        'image_url': {'url': f'data:{mime};base64,{encoded}'}})
    if reference:
        content.append({'type': 'video_url', 'role': 'reference_video', 'video_url': {'url': reference}})
    value = {'model': model, 'content': content, 'duration': duration, 'resolution': resolution,
             'ratio': ratio}
    if supports_audio:
        value['generate_audio'] = audio
    if model in (MODEL, FLASH):
        value['output_format'] = 'mp4'
    if mode in ('reference', 'edit', 'extend'):
        value['omni_reference_task_type'] = mode
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    if len(raw) > MAX_REQUEST:
        raise WCEError('VIDEO_REQUEST_TOO_LARGE')
    return raw


def result_url(url):
    if (type(url) is not str or not 0 < len(url) <= 8192
            or any(not 33 <= ord(char) <= 126 for char in url)):
        raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
    try:
        parts = urlsplit(url)
    except ValueError:
        raise WCEError('VIDEO_RESULT_SOURCE_INVALID') from None
    if (parts.scheme != 'https' or parts.netloc not in RESULT_HOSTS or parts.fragment
            or not parts.path.startswith('/') or '\\' in parts.path):
        raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
    return url


class Ark:
    def __init__(self, opener=None):
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}), NoRedirect())

    def _json(self, url, key, body=None):
        api_key = key.reveal_for_adapter()
        request = Request(url, data=body, headers={
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(request, timeout=25) as response:
                raw = response.read(MAX_JSON + 1)
                if len(raw) > MAX_JSON:
                    raise ValueError()
                value = json.loads(raw)
                if type(value) is not dict:
                    raise ValueError()
                return value
        except HTTPError as error:
            code = error.code
            if body is not None and code in REJECTION_STATUSES:
                try:
                    rejection = ArkSubmitRejected(error, api_key)
                finally:
                    error.close()
                raise rejection from None
            error.close()
            if body is None and code == 404:
                raise WCEError('VIDEO_TASK_NOT_FOUND') from None
            if body is None and code == 429:
                raise WCEError('VIDEO_QUERY_RATE_LIMITED') from None
            if body is None and code in (401, 403):
                raise WCEError('VIDEO_QUERY_AUTH_REQUIRED') from None
            raise WCEError('VIDEO_PROVIDER_UNAVAILABLE') from None
        except (OSError, HTTPException, ValueError, RecursionError):
            raise WCEError('VIDEO_PROVIDER_UNAVAILABLE') from None

    def submit(self, key, body):
        task = self._json(TASKS, key, body).get('id')
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, key, task, *, model=MODEL):
        validate_model(model)
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        value = self._json(TASKS + '/' + task, key)
        if value.get('id') != task or value.get('model') != model:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        if value.get('status') == 'failed':
            # Keep only a known code. Provider messages can echo inputs or URLs.
            code = ark_error_code(value, key.reveal_for_adapter())
            if code:
                value['error'] = {'code': code}
            else:
                value.pop('error', None)
        return value

    def download(self, url, output):
        result_url(url)
        self._download(url, output)

    def _download(self, url, output):
        try:
            with self.opener.open(Request(url, headers={'Accept': 'video/mp4'}), timeout=25) as response:
                size = 0
                deadline = time.monotonic() + 90
                while chunk := response.read(65536):
                    if time.monotonic() >= deadline:
                        raise WCEError('VIDEO_DOWNLOAD_INCOMPLETE')
                    size += len(chunk)
                    if size > MAX_RESULT:
                        raise WCEError('VIDEO_RESULT_TOO_LARGE')
                    output.write(chunk)
                length = response.headers.get('Content-Length')
                if not size or (length is not None and str(size) != length):
                    raise WCEError('VIDEO_DOWNLOAD_INCOMPLETE')
        except HTTPError as error:
            code = error.code
            error.close()
            if code in (401, 403, 404, 410):
                raise WCEError('VIDEO_RESULT_URL_UNAVAILABLE') from None
            raise WCEError('VIDEO_DOWNLOAD_INCOMPLETE') from None
        except (OSError, HTTPException, ValueError):
            raise WCEError('VIDEO_DOWNLOAD_INCOMPLETE') from None
