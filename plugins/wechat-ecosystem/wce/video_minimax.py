"""MiniMax H3 V2 transport. Credentials and task IDs are scoped to one site."""
from base64 import b64encode
from http.client import HTTPException
import json
from math import isfinite
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

from .contracts import WCEError
from .video_seedance import Ark, MAX_JSON, MAX_REQUEST

H3 = 'MiniMax-H3'
SITES = {'cn': 'https://api.minimax.cn', 'global': 'https://api.minimax.io'}
RATIOS = ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16')
H3_MODES = ('text', 'first', 'last', 'frames', 'reference')
TASK_ID = re.compile(r'[0-9]{1,64}\Z')
CDN = frozenset({'cdn.hailuoai.com', 'cdn.minimax.io', 'cdn.minimax.cn',
                 'algeng-video-infer.oss-cn-shanghai.aliyuncs.com'})


def h3_body(prompt, frames, *, mode, duration, resolution, ratio):
    roles = {'text': (), 'first': ('first_frame',), 'last': ('last_frame',),
             'frames': ('first_frame', 'last_frame'), 'reference': ('reference_image',) * len(frames)}
    if mode not in roles or len(roles[mode]) != len(frames) or mode == 'reference' and not 1 <= len(frames) <= 9:
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    if type(duration) is not int or not 4 <= duration <= 15:
        raise WCEError('VIDEO_DURATION_INVALID')
    if resolution not in ('768P', '2K') or ratio not in ('adaptive', *RATIOS):
        raise WCEError('VIDEO_OUTPUT_INVALID')
    if (mode == 'text' and ratio == 'adaptive') or (mode in ('first', 'last', 'frames') and ratio != 'adaptive'):
        raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
    content = [{'type': 'text', 'text': prompt}]
    for role, (mime, raw) in zip(roles[mode], frames, strict=True):
        content.append({'type': 'image_url', 'role': role,
                        'image_url': {'url': f'data:{mime};base64,{b64encode(raw).decode("ascii")}'}})
    body = json.dumps(dict(model=H3, content=content, resolution=resolution, duration=duration, ratio=ratio),
                      ensure_ascii=False, separators=(',', ':')).encode()
    if len(body) > MAX_REQUEST:
        raise WCEError('VIDEO_REQUEST_TOO_LARGE')
    return body


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
        task = self._request('/v2/video_generation', key, body).get('task_id')
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, key, task, *, model=H3):
        if type(task) is not str or not TASK_ID.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        value = self._request('/v2/query/video_generation/' + task, key).get('task')
        if type(value) is not dict or value.get('id') != task or value.get('model') != model:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        content = value.get('content')
        return {'status': value.get('status'), 'resolution': value.get('resolution'),
                'usage': h3_usage(value.get('usage')),
                'content': {'video_url': content.get('url')} if type(content) is dict else {}}

    def download(self, url, output):
        try:
            parts = urlsplit(url) if type(url) is str and 0 < len(url) <= 8192 and all(33 <= ord(c) <= 126 for c in url) else None
        except ValueError:
            parts = None
        if (parts is None or parts.scheme != 'https' or parts.netloc not in CDN or parts.fragment
                or not parts.path.startswith('/') or '\\' in parts.path):
            raise WCEError('VIDEO_RESULT_SOURCE_INVALID')
        self._download(url, output)
