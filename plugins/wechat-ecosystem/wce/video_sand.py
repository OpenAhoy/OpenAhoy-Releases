"""Sand AI native API for project-local image references and MAGI-2 videos."""
import json
import re
from http.client import HTTPException
from secrets import token_hex
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from .contracts import WCEError
from .video_relay import PublicHTTPSHandler, https_url
from .video_seedance import MAX_JSON, NoRedirect, download_mp4

PROVIDER = 'sand'
MODEL = 'magi-2'
ORIGIN = 'https://api.sand.ai'
GENERATIONS = ORIGIN + '/v2/generations'
ASSETS = ORIGIN + '/v1/assets'
KEYS_URL = 'https://platform.sand.ai/app/keys/'
DOC_URL = 'https://platform.sand.ai/docs/create-generation/'
ANNOUNCEMENT_URL = 'https://sand.ai/blog/magi-2'
DURATIONS = range(4, 31)
RATIOS = ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16')
RESOLUTION = '1080p'
MAX_REFERENCES = 10
POLL_INTERVAL = 10
ID = re.compile(r'[1-9][0-9]{0,18}\Z')
IMAGE_EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg'}
REQUEST_ERRORS = {
    'invalid_request', 'invalid_parameter', 'model_not_supported', 'content_policy_violation',
    'invalid_image', 'image_too_large', 'invalid_image_url', 'image_unavailable',
    'invalid_media_url', 'media_unavailable', 'insufficient_credits', 'invalid_api_key',
    'organization_banned', 'permission_denied', 'asset_not_found', 'generation_not_found',
    'rate_limit_exceeded', 'internal_error', 'service_unavailable',
    '00001', '00002', '00003', '00005', '00006', '00009', '00200', '00202', '00204',
}
FAILURE_CODES = {'generation_failed', 'generation_timeout', 'content_policy_violation',
                 'service_unavailable', 'insufficient_credits'}
STATUSES = {'queued': 'queued', 'processing': 'running', 'succeeded': 'succeeded',
            'failed': 'failed', 'canceled': 'cancelled'}


def identifier(value):
    return value if type(value) is str and ID.fullmatch(value) and int(value) < 2**63 else None


def validate_inputs(prompt, frames, *, mode, duration, resolution, ratio, audio):
    if type(prompt) is not str or not prompt.strip() or len(prompt) > 15000:
        raise WCEError('VIDEO_FRAMES_OR_PROMPT_INVALID')
    if type(duration) is not int or duration not in DURATIONS:
        raise WCEError('VIDEO_DURATION_INVALID')
    if resolution != RESOLUTION or ratio not in RATIOS or type(audio) is not bool:
        raise WCEError('VIDEO_OUTPUT_UNSUPPORTED')
    if not ((mode == 'text' and not frames) or (mode == 'reference' and 1 <= len(frames) <= MAX_REFERENCES)):
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    if any(mime not in IMAGE_EXTENSIONS for mime, _ in frames):
        raise WCEError('VIDEO_FRAME_INVALID')


def request_body(prompt, asset_ids, *, duration, resolution, ratio, audio, mode):
    if ((mode == 'text' and asset_ids) or (mode == 'reference' and not asset_ids)
            or any(not identifier(value) for value in asset_ids)):
        raise WCEError('VIDEO_SAND_ASSET_ID_UNKNOWN')
    parts = [{'type': 'text', 'text': prompt}]
    parts.extend({'type': 'reference_image', 'image': {'assetId': value}} for value in asset_ids)
    return json.dumps({'model': MODEL, 'parts': parts, 'duration': duration, 'aspectRatio': ratio,
                       'resolution': resolution, 'generateAudio': audio},
                      ensure_ascii=False, separators=(',', ':')).encode()


def read_json(response):
    raw = response.read(MAX_JSON + 1)
    document = json.loads(raw) if len(raw) <= MAX_JSON else None
    if type(document) is not dict:
        raise ValueError
    return document


class SandRequestError(WCEError):
    def __init__(self, operation, status=None, document=None, *, unreadable=False):
        self.task = None
        self.rejected = False
        known = None
        if document:
            value = document.get('code')
            if type(value) is str and value in REQUEST_ERRORS:
                known = value
            details = document.get('details')
            if operation == 'create' and type(details) is dict:
                self.task = identifier(details.get('generation_id'))
        if operation == 'query':
            code = {401: 'VIDEO_QUERY_AUTH_REQUIRED', 403: 'VIDEO_QUERY_AUTH_REQUIRED',
                    404: 'VIDEO_TASK_NOT_FOUND', 429: 'VIDEO_QUERY_RATE_LIMITED'}.get(
                        status, 'VIDEO_PROVIDER_UNAVAILABLE')
        elif operation == 'upload':
            code = 'VIDEO_SAND_UPLOAD_FAILED'
        else:
            self.rejected = status in (400, 401, 403, 404, 405, 406, 415, 429)
            code = ('VIDEO_SUBMIT_REJECTED' if self.rejected else 'VIDEO_TASK_ID_UNKNOWN'
                    if unreadable else 'VIDEO_PROVIDER_UNAVAILABLE')
        self.diagnostic = {'provider': PROVIDER, 'phase': operation, 'code': code}
        if status is not None:
            self.diagnostic['http_status'] = status
        if known:
            self.diagnostic['provider_code'] = known
        super().__init__(code)


class Sand:
    def __init__(self, opener=None, download_opener=None, clock=time.time):
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}), NoRedirect())
        self.download_opener = download_opener if download_opener is not None else build_opener(
            ProxyHandler({}), NoRedirect(), PublicHTTPSHandler())
        self.clock = clock

    def _json(self, key, operation, url, *, expected, data=None, content_type=None):
        headers = {'Accept': 'application/json', 'Authorization': 'Bearer ' + key.reveal_for_adapter()}
        if content_type:
            headers['Content-Type'] = content_type
        request = Request(url, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=45 if operation == 'upload' else 25) as response:
                status = response.status
                if status != expected:
                    raise SandRequestError(operation, status)
                try:
                    return read_json(response)
                except (ValueError, RecursionError):
                    raise SandRequestError(operation, status, unreadable=True) from None
        except HTTPError as error:
            with error:
                try:
                    problem = read_json(error)
                except (OSError, ValueError, RecursionError, HTTPException):
                    problem = None
            raise SandRequestError(operation, error.code, problem) from None
        except (OSError, HTTPException, EOFError):
            raise SandRequestError(operation) from None

    def upload(self, key, frame):
        mime, raw = frame
        boundary = 'Jiusera-' + token_hex(24)
        filename = 'reference.' + IMAGE_EXTENSIONS[mime]
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode()
        data = head + raw + f'\r\n--{boundary}--\r\n'.encode()
        response = self._json(key, 'upload', ASSETS, expected=200, data=data,
                              content_type='multipart/form-data; boundary=' + boundary)
        number = response.get('id')
        if type(number) is not int or not 0 < number < 2**63:
            raise SandRequestError('upload', 200, unreadable=True)
        return str(number)

    def submit(self, key, body):
        response = self._json(key, 'create', GENERATIONS, expected=202, data=body, content_type='application/json')
        task = identifier(response.get('id'))
        if not task:
            raise SandRequestError('create', 202, unreadable=True)
        return task

    def query(self, key, task, *, model):
        if model != MODEL or not identifier(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        response = self._json(key, 'query', GENERATIONS + '/' + task, expected=200)
        if response.get('id') != task:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        status = response.get('status')
        if type(status) is not str or status not in STATUSES:
            raise WCEError('VIDEO_TASK_STATUS_UNKNOWN')
        result = {'status': STATUSES[status]}
        if status == 'succeeded':
            output = response.get('output')
            if type(output) is dict:
                result['content'] = {'video_url': output.get('videoUrl')}
        elif status == 'failed':
            error = response.get('error')
            code = error.get('code') if type(error) is dict else None
            result['failure_code'] = code if type(code) is str and code in FAILURE_CODES else 'generation_failed'
        return result

    def download(self, url, output):
        if url is None:
            raise WCEError('VIDEO_RESULT_URL_UNAVAILABLE')
        parts = https_url(url, 'VIDEO_RESULT_SOURCE_INVALID')
        if parts.path in ('', '/'):
            raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
        # The URL is obtained from the pinned task API, fetched without credentials
        # or redirects, and the connector requires and pins a public IP for TLS.
        download_mp4(self.download_opener, url, output)
