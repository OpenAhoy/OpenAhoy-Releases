"""AutoDL-style workflow calls with one pinned HTTPS origin and credential-free downloads."""
from http.client import HTTPException, HTTPSConnection
import ipaddress
import json
import re
import socket
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .contracts import WCEError
from .video_seedance import Ark, MAX_JSON, MAX_REQUEST, NoRedirect

RELAY_MODEL = 'MiniMax-H3-Relay'
RESOLUTIONS = ('480p横', '480p竖', '768p横', '768p竖', '960p横', '960p竖')
WORKFLOW = '/api/v1/comfyui/comfyui_workflow/'
TASK = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
HOST = re.compile(r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


def https_url(value, error):
    try:
        if (type(value) is not str or not 0 < len(value) <= 8192
                or '\\' in value or not all(33 <= ord(char) <= 126 for char in value)):
            raise ValueError()
        parts = urlsplit(value)
        if (parts.scheme != 'https' or not HOST.fullmatch(parts.netloc.lower())
                or '#' in value or parts.netloc.lower().endswith(('.localhost', '.local', '.internal', '.test'))):
            raise ValueError()
    except ValueError:
        raise WCEError(error) from None
    return parts


def relay_origin(value):
    parts = https_url(value, 'VIDEO_RELAY_ORIGIN_INVALID')
    if parts.path not in ('', '/') or '?' in value:
        raise WCEError('VIDEO_RELAY_ORIGIN_INVALID')
    return 'https://' + parts.netloc.lower()


def public_destination(host, port, *, resolve=None):
    rows = (resolve or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
    addresses = [row[4][0] for row in rows]
    if not addresses or any(not (ip := ipaddress.ip_address(address)).is_global or ip.is_multicast
                            or ip.is_reserved or ip.is_loopback or ip.is_link_local
                            or ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo
                                                   or ip in ipaddress.IPv6Network('64:ff9b::/96'))
                            for address in addresses):
        raise OSError('Relay destination must resolve to a public address')
    return addresses[0]


class PublicHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = self.connect_public

    @staticmethod
    def connect_public(address, timeout, source_address):
        host, port = address
        ip = public_destination(host, port)
        return socket.create_connection((ip, port), timeout, source_address)


class PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(PublicHTTPSConnection, request, context=self._context)


def workflow_body(inputs):
    fields = {key: inputs[key] for key in ('prompt', 'duration', 'resolution') if key in inputs}
    for name, group in (('ref_image', inputs['reference_images']), ('ref_audio', inputs.get('reference_audio', []))):
        for index, url in enumerate(group):
            https_url(url, 'VIDEO_RELAY_INPUT_URL_INVALID')
            fields[f'{name}_{index}'] = url
    body = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(body) > MAX_REQUEST:
        raise WCEError('VIDEO_REQUEST_TOO_LARGE')
    return body


class Relay(Ark):
    def __init__(self, origin, opener=None):
        self.origin = relay_origin(origin)
        self.opener = opener if opener is not None else build_opener(
            ProxyHandler({}), NoRedirect(), PublicHTTPSHandler())

    def _request(self, path, key, body=None):
        request = Request(self.origin + WORKFLOW + path, data=body, headers={
            'Authorization': key.reveal_for_adapter(), 'Content-Type': 'application/json',
            'Accept': 'application/json'})
        try:
            with self.opener.open(request, timeout=25) as response:
                raw = response.read(MAX_JSON + 1)
                value = json.loads(raw) if len(raw) <= MAX_JSON else None
        except HTTPError as error:
            code = error.code
            error.close()
            if body is None and code in (401, 403):
                raise WCEError('VIDEO_QUERY_AUTH_REQUIRED') from None
            if body is None and code == 404:
                raise WCEError('VIDEO_TASK_NOT_FOUND') from None
            if body is None and code == 429:
                raise WCEError('VIDEO_QUERY_RATE_LIMITED') from None
            raise WCEError('VIDEO_RELAY_UNAVAILABLE') from None
        except (OSError, HTTPException, ValueError, RecursionError, EOFError):
            raise WCEError('VIDEO_RELAY_UNAVAILABLE') from None
        if type(value) is not dict or value.get('code') != 'Success' or type(value.get('data')) is not dict:
            raise WCEError('VIDEO_RELAY_RESPONSE_UNRECOGNIZED')
        return value['data']

    def submit(self, key, body):
        task = self._request('minimax_h3_zm_nono', key, body).get('task_id')
        if type(task) is not str or not TASK.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, key, task, *, model=RELAY_MODEL):
        if type(task) is not str or not TASK.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        data = self._request('result/' + task, key)
        if data.get('task_id') != task:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        code = data.get('status')
        states = {'queued': 'queued', 'running': 'running', 'success': 'succeeded',
                  'completed': 'succeeded', 'failed': 'failed', 'cancelled': 'cancelled', 'expired': 'expired'}
        status = states.get(code.lower()) if type(code) is str else None
        result = {'status': status}
        if status == 'succeeded':
            urls = data.get('results')
            if type(urls) is list and 0 < len(urls) <= 64:
                if all(type(url) is str for url in urls):
                    videos = urls if len(urls) == 1 else [
                        url for url in urls if url.partition('?')[0].lower().endswith('.mp4')]
                else:
                    videos = [item['url'] for item in urls if type(item) is dict and item.get('type') == 'video'
                              and item.get('file_type') == 'mp4' and item.get('output_type') == 'output'
                              and type(item.get('url')) is str]
                if len(videos) == 1:
                    result['content'] = {'video_url': videos[0]}
        return result

    def download(self, url, output):
        https_url(url, 'VIDEO_RESULT_SOURCE_INVALID')
        # Ark's downloader sends only Accept, with this non-redirecting, proxy-free opener.
        self._download(url, output)
