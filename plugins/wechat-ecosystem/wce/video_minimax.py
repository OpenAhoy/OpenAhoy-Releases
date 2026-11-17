"""MiniMax video transport. Credentials and task IDs are scoped to one site."""
from base64 import b64encode
from http.client import HTTPException
import json
from math import isfinite
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

from .contracts import WCEError
from .video_relay import https_url
from .video_seedance import Ark, MAX_JSON, MAX_REQUEST

H3 = 'MiniMax-H3'
SUBJECT_MODEL = 'S2V-01'
H3_MODELS = {H3: (4, ('768P', '2K')),
             'MiniMax-H3-Highspeed': (4, ('480P', '768P')),
             'MiniMax-H3-Lite': (4, ('480P', '768P')),
             'MiniMax-H3-Max': (5, ('480P', '768P'))}
V1_STANDARD = ('768P', '1080P')
V1_MODELS = {
    'MiniMax-Hailuo-02': {'text': V1_STANDARD, 'first': ('512P', *V1_STANDARD), 'frames': V1_STANDARD},
    'MiniMax-Hailuo-2.3': {'text': V1_STANDARD, 'first': V1_STANDARD},
    'MiniMax-Hailuo-2.3-Fast': {'first': V1_STANDARD},
    'T2V-01': {'text': ('720P',)}, 'T2V-01-Director': {'text': ('720P',)},
    'I2V-01': {'first': ('720P',)}, 'I2V-01-Director': {'first': ('720P',)},
    'I2V-01-live': {'first': ('720P',)},
}
LEGACY_MODELS = V1_MODELS.keys() | {SUBJECT_MODEL}
MINIMAX_MODELS = H3_MODELS.keys() | LEGACY_MODELS
SITES = {'cn': 'https://api.minimax.cn', 'global': 'https://api.minimax.io'}
RATIOS = ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16')
H3_MODES = ('text', 'first', 'last', 'frames', 'reference')
TASK_ID = re.compile(r'[0-9]{1,64}\Z')
CDN = frozenset({'cdn.hailuoai.com', 'cdn.minimax.io', 'cdn.minimax.cn', 'filecdn.minimax.chat',
                 'algeng-video-infer.oss-cn-shanghai.aliyuncs.com'})


def h3_body(prompt, frames, *, mode, duration, resolution, ratio, model=H3):
    if model not in H3_MODELS:
        raise WCEError('VIDEO_MODEL_UNSUPPORTED')
    minimum, resolutions = H3_MODELS[model]
    roles = {'text': (), 'first': ('first_frame',), 'last': ('last_frame',),
             'frames': ('first_frame', 'last_frame'), 'reference': ('reference_image',) * len(frames)}
    if mode not in roles or len(roles[mode]) != len(frames) or mode == 'reference' and not 1 <= len(frames) <= 9:
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    if type(duration) is not int or not minimum <= duration <= 15:
        raise WCEError('VIDEO_DURATION_INVALID')
    if resolution not in resolutions or ratio not in ('adaptive', *RATIOS):
        raise WCEError('VIDEO_OUTPUT_INVALID')
    if (mode == 'text' and ratio == 'adaptive') or (model == 'MiniMax-H3-Lite' and mode == 'reference' and ratio == 'adaptive') or (mode in ('first', 'last', 'frames') and ratio != 'adaptive'):
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    content = [{'type': 'text', 'text': prompt}]
    for role, (mime, raw) in zip(roles[mode], frames, strict=True):
        content.append({'type': 'image_url', 'role': role,
                        'image_url': {'url': f'data:{mime};base64,{b64encode(raw).decode("ascii")}'}})
    body = json.dumps(dict(model=model, content=content, resolution=resolution, duration=duration, ratio=ratio),
                      ensure_ascii=False, separators=(',', ':')).encode()
    if len(body) > MAX_REQUEST:
        raise WCEError('VIDEO_REQUEST_TOO_LARGE')
    return body


def v1_body(prompt, frames, *, model, mode, duration, resolution, ratio):
    sizes = V1_MODELS.get(model, {}).get(mode, ())
    fields = {'text': (), 'first': ('first_frame_image',),
              'frames': ('first_frame_image', 'last_frame_image')}
    if not sizes or len(fields[mode]) != len(frames) or ratio != 'adaptive':
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    if len(prompt) > 2000 or resolution not in sizes:
        raise WCEError('VIDEO_OUTPUT_INVALID')
    durations = (6, 10) if resolution in ('512P', '768P') else (6,)
    if type(duration) is not int or duration not in durations:
        raise WCEError('VIDEO_DURATION_INVALID')
    payload = dict(model=model, prompt=prompt)
    if sizes != ('720P',):
        payload.update(duration=duration, resolution=resolution)
    for field, (mime, raw) in zip(fields[mode], frames, strict=True):
        payload[field] = f'data:{mime};base64,{b64encode(raw).decode("ascii")}'
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    if len(body) > MAX_REQUEST:
        raise WCEError('VIDEO_REQUEST_TOO_LARGE')
    return body


def subject_body(prompt, image_url):
    parts = https_url(image_url, 'VIDEO_SUBJECT_IMAGE_URL_INVALID')
    if parts.path in ('', '/') and not parts.query:
        raise WCEError('VIDEO_SUBJECT_IMAGE_URL_INVALID')
    if not prompt.strip() or len(prompt) > 2000:
        raise WCEError('VIDEO_FRAMES_OR_PROMPT_INVALID')
    return json.dumps({
        'model': SUBJECT_MODEL, 'prompt': prompt,
        'subject_reference': [{'type': 'character', 'image': [image_url]}],
    }, ensure_ascii=False, separators=(',', ':')).encode()


def h3_usage(value):
    if type(value) is not dict:
        return {}
    seconds = ('total_seconds', 'input_seconds', 'output_seconds', 'input_audio_seconds')
    integers = ('input_image_count', 'total_tokens', 'prompt_tokens', 'completion_tokens')
    return {k: v for k, v in value.items()
            if (k in seconds and type(v) in (float, int) and 0 <= v <= 3600 and isfinite(v))
            or (k in integers and type(v) is int and 0 <= v <= 2**53 - 1)}


class MiniMaxRejected(WCEError):
    def __init__(self, code):
        super().__init__('VIDEO_SUBMIT_REJECTED')
        self.diagnostic = {'provider': 'minimax', 'http_status': code}


class MiniMax(Ark):
    def __init__(self, site, opener=None):
        super().__init__(opener)
        self.base = SITES[site]

    def _request(self, path, key, body=None):
        request = Request(self.base + path, data=body, headers={
            'Authorization': 'Bearer ' + key.reveal_for_adapter(),
            'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(request, timeout=25) as response:
                raw = response.read(MAX_JSON + 1)
                value = json.loads(raw) if len(raw) <= MAX_JSON else None
                if type(value) is dict:
                    return value
        except HTTPError as error:
            code = error.code
            error.close()
            if body is not None and code in (400, 401, 402, 403, 422, 429):
                raise MiniMaxRejected(code) from None
            if body is None and code == 404:
                raise WCEError('VIDEO_TASK_NOT_FOUND') from None
            if body is None and code in (401, 403):
                raise WCEError('VIDEO_QUERY_AUTH_REQUIRED') from None
            if body is None and code == 429:
                raise WCEError('VIDEO_QUERY_RATE_LIMITED') from None
        except (OSError, HTTPException, ValueError, RecursionError):
            pass
        raise WCEError('VIDEO_PROVIDER_UNAVAILABLE')

    def submit(self, key, body):
        model = json.loads(body).get('model')
        endpoint = '/v1/video_generation' if model in LEGACY_MODELS else '/v2/video_generation'
        result = self._request(endpoint, key, body)
        if model == SUBJECT_MODEL and not v1_success(result):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        task = result.get('task_id')
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, key, task, *, model=H3):
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        if model in LEGACY_MODELS:
            return self.query_v1(key, task, verify_response=model == SUBJECT_MODEL)
        value = self._request('/v2/query/video_generation/' + task, key).get('task')
        if type(value) is not dict or value.get('id') != task or value.get('model') != model:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        content = value.get('content')
        return {'status': value.get('status'), 'resolution': value.get('resolution'),
                'usage': h3_usage(value.get('usage')),
                'content': {'video_url': content.get('url')} if type(content) is dict else {}}

    def query_v1(self, key, task, *, verify_response=False):
        row = self._request('/v1/query/video_generation?task_id=' + task, key)
        if verify_response and not v1_success(row):
            raise WCEError('VIDEO_PROVIDER_UNAVAILABLE')
        if row.get('task_id') != task:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        states = {'Preparing': 'queued', 'Queueing': 'queued', 'Processing': 'running',
                  'Success': 'succeeded', 'Fail': 'failed'}
        status = row.get('status')
        state = states.get(status) if type(status) is str else None
        if state != 'succeeded':
            return {'status': state}
        file_id = row.get('file_id')
        if type(file_id) is not str or not TASK_ID.fullmatch(file_id):
            raise WCEError('VIDEO_RESULT_INVALID')
        response = self._request('/v1/files/retrieve?file_id=' + file_id, key)
        if verify_response and not v1_success(response):
            raise WCEError('VIDEO_PROVIDER_UNAVAILABLE')
        file = response.get('file')
        if (type(file) is not dict or str(file.get('file_id')) != file_id
                or file.get('purpose') != 'video_generation'):
            raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
        return {'status': state, 'content': {'video_url': file.get('download_url')}}

    def download(self, url, output):
        try:
            parts = urlsplit(url) if type(url) is str and 0 < len(url) <= 8192 and all(33 <= ord(c) <= 126 for c in url) else None
        except ValueError:
            parts = None
        if (parts is None or parts.scheme != 'https' or parts.netloc not in CDN or parts.fragment
                or not parts.path.startswith('/') or '\\' in parts.path):
            raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
        self._download(url, output)


def v1_success(response):
    base = response.get('base_resp')
    return type(base) is dict and type(base.get('status_code')) is int and base['status_code'] == 0
