"""AutoDL-style workflow calls with one pinned HTTPS origin and credential-free downloads."""
from contextlib import closing, contextmanager
from http.client import HTTPException, HTTPSConnection
import ipaddress
import json
import re
import socket
import ssl
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .contracts import WCEError
from .video_seedance import Ark, MAX_JSON, MAX_REQUEST, NoRedirect

RELAY_MODEL = 'MiniMax-H3-Relay'
RESOLUTIONS = ('480p横', '480p竖', '768p横', '768p竖', '960p横', '960p竖')
WORKFLOW = '/api/v1/comfyui/comfyui_workflow/'
OFFICIAL_AUTODL_HOST = 'autodl.art'
OFFICIAL_AUTODL_MEDIA_HOST = 'cg-comfyui-prod.tos-cn-beijing.volces.com'
OFFICIAL_AUTODL_MEDIA_ALIAS = 'tos7-public.cn-beijing.tos.volces.com'
FAKE_IP_RANGE = ipaddress.IPv4Network('198.18.0.0/15')
DNS_JSON_LIMIT = 16384
SUBMIT_RESPONSE_WINDOW = 50
PUBLIC_DNS_REQUIRED = 'VIDEO_RELAY_PUBLIC_DNS_REQUIRED'
TRANSPORT_PHASES = frozenset({'DNS_LOOKUP', 'TCP_CONNECT', 'TLS_HANDSHAKE', 'SEND_REQUEST',
                              'WAIT_RESPONSE_HEADERS', 'READ_RESPONSE_BODY'})
TASK = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
HOST = re.compile(r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
SUBMIT_REJECTIONS = {
    400: 'VIDEO_RELAY_INPUT_REJECTED', 401: 'VIDEO_RELAY_AUTH_REQUIRED',
    402: 'VIDEO_RELAY_PAYMENT_REQUIRED', 403: 'VIDEO_RELAY_ACCESS_DENIED',
    404: 'VIDEO_RELAY_WORKFLOW_UNAVAILABLE', 405: 'VIDEO_RELAY_WORKFLOW_UNAVAILABLE',
    413: 'VIDEO_RELAY_INPUT_REJECTED', 415: 'VIDEO_RELAY_INPUT_REJECTED',
    422: 'VIDEO_RELAY_INPUT_REJECTED',
}
SUBMIT_DIAGNOSTIC_CODES = frozenset(SUBMIT_REJECTIONS.values()) | {
    'VIDEO_RELAY_HTTP_UNCERTAIN', 'VIDEO_RELAY_RATE_LIMITED', 'VIDEO_RELAY_RESPONSE_UNRECOGNIZED',
    'VIDEO_RELAY_RESPONSE_INVALID', 'VIDEO_TASK_ID_UNKNOWN', 'NETWORK_TIMEOUT', 'NETWORK_DNS',
    'NETWORK_CONNECT', 'TLS_FAILED', 'VIDEO_RELAY_TRANSPORT_UNCERTAIN', PUBLIC_DNS_REQUIRED,
}


class PublicDestinationError(OSError):
    """The DNS guard refused a destination before opening a connection."""


class RelayTransportTimeout(TimeoutError):
    def __init__(self, phase):
        self.phase = phase
        super().__init__(phase)


@contextmanager
def timeout_phase(phase):
    try:
        yield
    except RelayTransportTimeout:
        raise
    except TimeoutError:
        raise RelayTransportTimeout(phase) from None


class RelaySubmitError(WCEError):
    def __init__(self, code, http_status=None, *, phase=None):
        self.rejected = http_status in SUBMIT_REJECTIONS or code == PUBLIC_DNS_REQUIRED
        self.diagnostic = {'code': code}
        if type(http_status) is int and 100 <= http_status <= 599:
            self.diagnostic['http_status'] = http_status
        if phase in TRANSPORT_PHASES:
            self.diagnostic['operation_phase'] = phase
        super().__init__('VIDEO_SUBMIT_REJECTED' if self.rejected else code)


def transport_code(error):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, PublicDestinationError):
        return PUBLIC_DNS_REQUIRED
    if isinstance(reason, TimeoutError):
        return 'NETWORK_TIMEOUT'
    if isinstance(reason, socket.gaierror):
        return 'NETWORK_DNS'
    if isinstance(reason, ssl.SSLError):
        return 'TLS_FAILED'
    if isinstance(reason, ConnectionRefusedError):
        return 'NETWORK_CONNECT'
    return 'VIDEO_RELAY_TRANSPORT_UNCERTAIN'


def response_json(response):
    raw = response.read(MAX_JSON + 1)
    return json.loads(raw) if len(raw) <= MAX_JSON else None


def success_data(value):
    if type(value) is dict and value.get('code') == 'Success' and type(value.get('data')) is dict:
        return value['data']
    return None


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


def autodl_public_addresses(host):
    if host not in {OFFICIAL_AUTODL_HOST, OFFICIAL_AUTODL_MEDIA_HOST}:
        raise ValueError('Host does not have an AutoDL public DNS rule')
    # The resolver IP is fixed to avoid depending on the local DNS that returned Fake IP.
    # TLS verifies the resolver certificate against that IP; the request contains only a public name.
    with closing(HTTPSConnection('1.1.1.1', timeout=5)) as resolver:
        resolver.request('GET', f'/dns-query?name={host}&type=A',
                         headers={'Accept': 'application/dns-json'})
        response = resolver.getresponse()
        raw = response.read(DNS_JSON_LIMIT + 1)
        if (response.status != 200 or len(raw) > DNS_JSON_LIMIT
                or response.getheader('Content-Type', '').split(';', 1)[0].strip() != 'application/dns-json'):
            raise ValueError('Unexpected DNS response')
    value = json.loads(raw)
    if (type(value) is not dict or type(value.get('Status')) is not int or value['Status'] != 0
            or value.get('TC') is not False):
        raise ValueError('Unusable DNS response')
    question = value.get('Question')
    if type(question) is not list or len(question) != 1 or not dns_record(question[0], host, 1):
        raise ValueError('Unexpected DNS question')
    answers = value.get('Answer')
    if type(answers) is not list or not 1 <= len(answers) <= 32:
        raise ValueError('Unexpected DNS answer')
    owner = host
    if host == OFFICIAL_AUTODL_MEDIA_HOST:
        aliases = [record for record in answers if dns_record(record, host, 5)]
        if aliases:
            if len(aliases) != 1 or aliases[0].get('data') not in (
                    OFFICIAL_AUTODL_MEDIA_ALIAS, OFFICIAL_AUTODL_MEDIA_ALIAS + '.'):
                raise ValueError('Unexpected AutoDL media alias')
            owner = OFFICIAL_AUTODL_MEDIA_ALIAS
            answers = [record for record in answers if record is not aliases[0]]
    if not answers or not all(dns_record(record, owner, 1) and type(record.get('data')) is str for record in answers):
        raise ValueError('Unexpected DNS answer')
    return [ipaddress.IPv4Address(record['data']) for record in answers]


def dns_record(record, host, record_type):
    return (type(record) is dict and type(record.get('type')) is int and record['type'] == record_type
            and record.get('name') in (host, host + '.'))


def public_destination(host, port, *, resolve=None, fallback_host=None):
    rows = (resolve or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(row[4][0]) for row in rows]
    if (host == fallback_host and port == 443 and addresses
            and all(ip in FAKE_IP_RANGE for ip in addresses)):
        try:
            addresses = autodl_public_addresses(host)
        except (OSError, HTTPException, ValueError, RecursionError, EOFError):
            raise PublicDestinationError('Public DNS resolution for AutoDL failed') from None
    if not addresses or any(not ip.is_global or ip.is_multicast
                            or ip.is_reserved or ip.is_loopback or ip.is_link_local
                            or ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo
                                                   or ip in ipaddress.IPv6Network('64:ff9b::/96'))
                            for ip in addresses):
        raise PublicDestinationError('Relay destination must resolve to a public address')
    return str(addresses[0])


class PublicHTTPSConnection(HTTPSConnection):
    fallback_host = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = self.connect_public

    def connect(self):
        with timeout_phase('TLS_HANDSHAKE'):
            return super().connect()

    def request(self, method, url, body=None, headers=None, *, encode_chunked=False):
        with timeout_phase('SEND_REQUEST'):
            return super().request(method, url, body, headers or {}, encode_chunked=encode_chunked)

    def getresponse(self):
        with timeout_phase('WAIT_RESPONSE_HEADERS'):
            return super().getresponse()

    @classmethod
    def connect_public(cls, address, timeout, source_address):
        host, port = address
        with timeout_phase('DNS_LOOKUP'):
            ip = public_destination(host, port, fallback_host=cls.fallback_host)
        with timeout_phase('TCP_CONNECT'):
            return socket.create_connection((ip, port), timeout, source_address)


class AutoDLWorkflowHTTPSConnection(PublicHTTPSConnection):
    fallback_host = OFFICIAL_AUTODL_HOST

    def request(self, method, url, body=None, headers=None, *, encode_chunked=False):
        self._submit_deadline = monotonic() + SUBMIT_RESPONSE_WINDOW if method == 'POST' else None
        return super().request(method, url, body, headers, encode_chunked=encode_chunked)

    def getresponse(self):
        deadline = self._submit_deadline
        connection = self.sock
        if deadline is None or connection is None:
            return super().getresponse()
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise RelayTransportTimeout('WAIT_RESPONSE_HEADERS')
        previous = connection.gettimeout()
        connection.settimeout(remaining)
        try:
            response = super().getresponse()
        except BaseException:
            if connection.fileno() >= 0:
                connection.settimeout(previous)
            raise
        remaining = deadline - monotonic()
        if remaining <= 0:
            response.close()
            raise RelayTransportTimeout('WAIT_RESPONSE_HEADERS')
        if connection.fileno() >= 0:
            connection.settimeout(min(previous, remaining) if previous is not None else remaining)
        return response


class AutoDLMediaHTTPSConnection(PublicHTTPSConnection):
    fallback_host = OFFICIAL_AUTODL_MEDIA_HOST


class PublicHTTPSHandler(HTTPSHandler):
    connection = PublicHTTPSConnection

    def https_open(self, request):
        return self.do_open(self.connection, request, context=self._context)


class AutoDLWorkflowHTTPSHandler(PublicHTTPSHandler):
    connection = AutoDLWorkflowHTTPSConnection


class AutoDLMediaHTTPSHandler(PublicHTTPSHandler):
    connection = AutoDLMediaHTTPSConnection


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
        self.workflow_opener = self.opener
        if opener is None and self.origin == 'https://' + OFFICIAL_AUTODL_HOST:
            self.workflow_opener = build_opener(ProxyHandler({}), NoRedirect(), AutoDLWorkflowHTTPSHandler())
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), AutoDLMediaHTTPSHandler())

    def _request(self, path, authorization, body=None):
        request = Request(self.origin + WORKFLOW + path, data=body, headers={
            'Authorization': authorization, 'Content-Type': 'application/json',
            'Accept': 'application/json'})
        return self.workflow_opener.open(request, timeout=25)

    def submit(self, key, body):
        authorization = key.reveal_for_adapter()
        try:
            with self._request('minimax_h3_zm_nono', authorization, body) as response:
                with timeout_phase('READ_RESPONSE_BODY'):
                    value = response_json(response)
        except HTTPError as error:
            status = error.code
            # A documented task receipt from this origin permits querying that original task.
            with error:
                try:
                    task = self._submit_task(success_data(response_json(error)), authorization)
                except (OSError, HTTPException, ValueError, RecursionError, EOFError):
                    task = None
            if task is not None:
                return task
            code = SUBMIT_REJECTIONS.get(status, 'VIDEO_RELAY_RATE_LIMITED' if status == 429
                                         else 'VIDEO_RELAY_HTTP_UNCERTAIN')
            raise RelaySubmitError(code, status) from None
        except (ValueError, RecursionError):
            raise RelaySubmitError('VIDEO_RELAY_RESPONSE_INVALID') from None
        except (OSError, HTTPException, EOFError) as error:
            reason = error.reason if isinstance(error, URLError) else error
            phase = reason.phase if isinstance(reason, RelayTransportTimeout) else None
            raise RelaySubmitError(transport_code(error), phase=phase) from None
        if value is None:
            raise RelaySubmitError('VIDEO_RELAY_RESPONSE_INVALID')
        data = success_data(value)
        if data is None:
            raise RelaySubmitError('VIDEO_RELAY_RESPONSE_UNRECOGNIZED')
        task = self._submit_task(data, authorization)
        if task is None:
            raise RelaySubmitError('VIDEO_TASK_ID_UNKNOWN')
        return task

    @staticmethod
    def _submit_task(data, authorization):
        task = data.get('task_id') if data is not None else None
        if type(task) is str and TASK.fullmatch(task) and authorization not in task:
            return task
        return None

    def query(self, key, task, *, model=RELAY_MODEL):
        if type(task) is not str or not TASK.fullmatch(task):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        try:
            with self._request('result/' + task, key.reveal_for_adapter()) as response:
                data = success_data(response_json(response))
        except HTTPError as error:
            code = error.code
            error.close()
            if code in (401, 403):
                raise WCEError('VIDEO_QUERY_AUTH_REQUIRED') from None
            if code == 404:
                raise WCEError('VIDEO_TASK_NOT_FOUND') from None
            if code == 429:
                raise WCEError('VIDEO_QUERY_RATE_LIMITED') from None
            raise WCEError('VIDEO_RELAY_UNAVAILABLE') from None
        except (OSError, HTTPException, ValueError, RecursionError, EOFError) as error:
            if transport_code(error) == PUBLIC_DNS_REQUIRED:
                raise WCEError(PUBLIC_DNS_REQUIRED) from None
            raise WCEError('VIDEO_RELAY_UNAVAILABLE') from None
        if data is None:
            raise WCEError('VIDEO_RELAY_RESPONSE_UNRECOGNIZED')
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
