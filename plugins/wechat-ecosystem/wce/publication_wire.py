"""Finite official publication wire profile; encoding never grants permission.

This module performs no I/O, retries, token renewal, polling or state mutation.
Callers own one-shot claims and must keep malformed write replies UNKNOWN.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit

from .contracts import WCEError
from .http_transport import HTTPRequest, HTTPResponse
from . import upload_wire as upload

PROFILE = 'WCE_OFFICIAL_PUBLICATION_DOC_WIRE_V1'
URL_PROFILE = 'WECHAT_ARTICLE_URL_V1'
MAX_RESPONSE = 256 * 1024
METHODS = {
    'freepublish.submit': ('/cgi-bin/freepublish/submit', 'PUBLISH_TASK'),
    'freepublish.get': ('/cgi-bin/freepublish/get', 'PUBLISH_TASK'),
    'mass.sendall': ('/cgi-bin/message/mass/sendall', 'MASS_TASK'),
    'mass.get': ('/cgi-bin/message/mass/get', 'MASS_TASK'),
}
MASS_STATES = frozenset({'SEND_SUCCESS', 'SENDING', 'SEND_FAIL', 'DELETE'})
_DIGITS = re.compile(r'[1-9][0-9]{0,127}\Z', re.ASCII)


@dataclass(frozen=True)
class DraftMediaID:
    value: str
    account_key: str
    intent_id: str


@dataclass(frozen=True)
class ArticleID:
    value: str
    account_key: str
    intent_id: str


@dataclass(frozen=True)
class TaskID:
    kind: str
    digits: str
    wire_type: str
    raw_token: str
    account_key: str
    intent_id: str
    source_method: str
    response_sha: str
    profile: str = PROFILE


@dataclass(frozen=True)
class Reply:
    result: dict | None = None
    error_code: int | None = None
    reason: str = 'RESPONSE_UNDETERMINED'
    response_sha: str | None = None
    http_status: int | None = None
    profile: str = PROFILE


@dataclass(frozen=True)
class _String:
    value: str
    raw: str = field(repr=False)


@dataclass(frozen=True)
class _Integer:
    raw: str


class _Invalid(ValueError):
    pass


class _JSON:
    """Bounded JSON scanner retaining original number and string tokens."""
    def __init__(self, body):
        if type(body) is not bytes or len(body) > MAX_RESPONSE:
            raise _Invalid('RESPONSE_BOUND')
        self.text = body.decode('utf-8', errors='strict')
        self.index, self.nodes = 0, 0

    def space(self):
        while self.index < len(self.text) and self.text[self.index] in ' \t\r\n':
            self.index += 1

    def value(self, depth=0):
        self.space()
        self.nodes += 1
        if depth > 32 or self.nodes > 16384 or self.index == len(self.text):
            raise _Invalid('JSON_BOUND')
        start = self.index
        char = self.text[start]
        if char == '"':
            value, end = json.decoder.scanstring(self.text, start + 1, True)
            value.encode('utf-8', errors='strict')  # reject isolated surrogates
            self.index = end
            return _String(value, self.text[start:end])
        if char in '{[':
            self.index += 1
            result = {} if char == '{' else []
            end_char = '}' if char == '{' else ']'
            self.space()
            if self.index < len(self.text) and self.text[self.index] == end_char:
                self.index += 1
                return result
            while True:
                if char == '{':
                    key = self.value(depth + 1)
                    if type(key) is not _String or key.value in result:
                        raise _Invalid('JSON_DUPLICATE_OR_KEY')
                    self.space()
                    if self.index == len(self.text) or self.text[self.index] != ':':
                        raise _Invalid('INVALID_JSON')
                    self.index += 1
                    result[key.value] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.space()
                if self.index == len(self.text):
                    raise _Invalid('INVALID_JSON')
                separator = self.text[self.index]
                self.index += 1
                if separator == end_char:
                    return result
                if separator != ',':
                    raise _Invalid('INVALID_JSON')
        if char in '-0123456789':
            match = re.match(r'-?(?:0|[1-9][0-9]*)', self.text[start:], re.ASCII)
            if not match or len(match[0]) > 129:
                raise _Invalid('INTEGER_BOUND')
            self.index += len(match[0])
            # JSON float/exponent and malformed leading-zero forms cannot be
            # silently consumed as a smaller integer prefix.
            if self.index < len(self.text) and self.text[self.index] not in ' \t\r\n,]}':
                raise _Invalid('JSON_NUMBER_TYPE')
            return _Integer(match[0])
        for word, value in (('true', True), ('false', False), ('null', None)):
            if self.text.startswith(word, start):
                self.index += len(word)
                return value
        raise _Invalid('INVALID_JSON')

    def parse(self):
        value = self.value()
        self.space()
        if self.index != len(self.text) or type(value) is not dict:
            raise _Invalid('INVALID_JSON_SHAPE')
        return value


def _plain(value):
    if type(value) is _String:
        return value.value
    if type(value) is _Integer:
        return value.raw
    if type(value) is dict:
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is list:
        return [_plain(item) for item in value]
    return value


def _int(value, low, high):
    if type(value) is not _Integer or not low <= int(value.raw) <= high:
        raise _Invalid('INTEGER_POLICY')
    return int(value.raw)


def _opaque(value, limit):
    return (type(value) is str and 0 < len(value.encode('utf-8')) <= limit
            and not any(c.isspace() or unicodedata.category(c).startswith('C') for c in value))


def _binding(account_key, intent_id):
    if not _opaque(account_key, 512) or not _opaque(intent_id, 512):
        raise _Invalid('BINDING_REQUIRED')


def _id(value, allowed, *, method, account_key, intent_id, response_sha):
    if type(value) is _Integer and 'N' in allowed and _DIGITS.fullmatch(value.raw):
        digits, kind, raw = value.raw, 'JSON_INTEGER_TOKEN', value.raw
    elif (type(value) is _String and 'S' in allowed and _DIGITS.fullmatch(value.value)
          and value.raw == '"' + value.value + '"'):
        digits, kind, raw = value.value, 'JSON_DECIMAL_STRING', value.raw
    else:
        raise _Invalid('TASK_ID_POLICY')
    return TaskID(METHODS[method][1], digits, kind, raw, account_key, intent_id,
                  method, response_sha)


def _get_id_failure(value, *, present, expected_digits):
    # Fixed non-authorizing reason only; never expose raw, ID, length or errmsg.
    if not present:
        return 'TASK_ID_POLICY_MISSING'
    if value is None:
        return 'TASK_ID_POLICY_NULL'
    if type(value) is bool:
        return 'TASK_ID_POLICY_BOOLEAN'
    if type(value) is _Integer:
        if not _DIGITS.fullmatch(value.raw):
            return 'TASK_ID_POLICY_INTEGER_FORMAT'
        return ('TASK_ID_POLICY_INTEGER_MATCH' if value.raw == expected_digits
                else 'TASK_ID_POLICY_INTEGER_DIFFERENT')
    if type(value) is _String:
        if not _DIGITS.fullmatch(value.value):
            return 'TASK_ID_POLICY_STRING_FORMAT'
        if value.raw != '"' + value.value + '"':
            return ('TASK_ID_POLICY_STRING_ESCAPED_MATCH' if value.value == expected_digits
                    else 'TASK_ID_POLICY_STRING_ESCAPED_DIFFERENT')
        # This case is accepted by _id and is not reachable on its failure.
        return 'TASK_ID_POLICY_STRING_FORMAT'
    return 'TASK_ID_POLICY_OTHER'


def _task(task, kind, account_key, intent_id):
    if (type(task) is not TaskID or task.kind != kind or task.account_key != account_key
            or task.intent_id != intent_id or task.profile != PROFILE
            or type(task.digits) is not str or not _DIGITS.fullmatch(task.digits)
            or type(task.response_sha) is not str or not re.fullmatch('[0-9a-f]{64}', task.response_sha)
            or task.source_method not in METHODS or METHODS[task.source_method][1] != kind
            or task.wire_type not in {'JSON_INTEGER_TOKEN', 'JSON_DECIMAL_STRING'}
            or task.raw_token != (task.digits if task.wire_type == 'JSON_INTEGER_TOKEN'
                                  else '"' + task.digits + '"')
            or (task.source_method == 'mass.sendall' and task.wire_type != 'JSON_INTEGER_TOKEN')
            or (task.source_method == 'freepublish.get' and task.wire_type != 'JSON_DECIMAL_STRING')):
        raise _Invalid('TASK_BINDING_MISMATCH')
    return task


def encode(method, payload, token, *, account_key, intent_id):
    """Return one fixed POST request; no arbitrary endpoint or retry path."""
    try:
        _binding(account_key, intent_id)
        if method not in METHODS or type(payload) is not dict:
            raise _Invalid('INVALID_METHOD_OR_PAYLOAD')
        if method.endswith('.get'):
            if set(payload) != {'task_id'}:
                raise _Invalid('INVALID_QUERY_PAYLOAD')
            task = _task(payload['task_id'], METHODS[method][1], account_key, intent_id)
            body = {('publish_id' if method == 'freepublish.get' else 'msg_id'): task.digits}
        else:
            required = {'media_id', 'clientmsgid'} if method == 'mass.sendall' else {'media_id'}
            if set(payload) != required:
                raise _Invalid('INVALID_SUBMIT_PAYLOAD')
            media = payload['media_id']
            if (type(media) is not DraftMediaID or media.account_key != account_key
                    or media.intent_id != intent_id or not _opaque(media.value, 512)):
                raise _Invalid('DRAFT_BINDING_MISMATCH')
            body = {'media_id': media.value}
            if method == 'mass.sendall':
                client = payload['clientmsgid']
                if type(client) is not str or not re.fullmatch('[0-9a-f]{32}', client):
                    raise _Invalid('CLIENTMSGID_POLICY')
                body = {'filter': {'is_to_all': True}, 'mpnews': body, 'msgtype': 'mpnews',
                        'send_ignore_reprint': 0, 'clientmsgid': client}
        if upload.contains_secret(body, token, max_nodes=16384):
            raise _Invalid('REQUEST_SECRET_REFLECTION')
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        return HTTPRequest('POST', METHODS[method][0] + '?' + urlencode({'access_token': upload.secret_value(token)}),
                           {'Content-Type': 'application/json; charset=utf-8'}, encoded)
    except (_Invalid, UnicodeError, TypeError, ValueError) as error:
        raise WCEError(str(error) if type(error) is _Invalid else 'INVALID_PUBLICATION_REQUEST') from None


def _article_url_reason(value):
    """Closed, non-authoritative URL classification; never return input bytes."""
    try:
        if (type(value) is not str or not 0 < len(value.encode('utf-8')) <= 4096
                or '\\' in value
                or any(c.isspace() or unicodedata.category(c).startswith('C') for c in value)
                or re.search(r'%(?![0-9a-fA-F]{2})', value)):
            return 'URL_FORMAT'
        if '#' in value and (value.count('#') != 1 or not value.endswith('#rd')):
            return 'FRAGMENT'
        try:
            parts = urlsplit(value)
        except ValueError:
            return 'URL_FORMAT'
        if parts.scheme not in ('http', 'https'):
            return 'SCHEME'
        try:
            if (parts.hostname != 'mp.weixin.qq.com'
                    or parts.username is not None or parts.password is not None
                    or parts.port not in ((None, 80) if parts.scheme == 'http' else (None, 443))
                    or parts.netloc not in (('mp.weixin.qq.com', 'mp.weixin.qq.com:80')
                                            if parts.scheme == 'http' else
                                            ('mp.weixin.qq.com', 'mp.weixin.qq.com:443'))):
                return 'AUTHORITY'
        except ValueError:
            return 'AUTHORITY'
        if parts.fragment not in ('', 'rd'):
            return 'FRAGMENT'
        if '%' in parts.path:
            return 'PATH'
        try:
            pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True,
                              encoding='utf-8', errors='strict')
        except (ValueError, UnicodeError):
            return 'QUERY'
        query = dict(pairs)
        if len(query) != len(pairs):
            return 'QUERY'
        extras = {'chksm', 'scene', 'ascene', 'devicetype', 'version', 'lang', 'from', 'isappinstalled', 'wx_header'}
        identity = {'__biz', 'mid', 'idx', 'sn'}
        if set(query) - extras - identity:
            return 'QUERY'
        for key, item in pairs:
            if (not item or len(item) > 256 or '%' in item or any(ord(c) < 33 or ord(c) > 126 for c in item)
                    or any(c in item for c in '&=\\?#')):
                if not (key == '__biz' and re.fullmatch(r'[A-Za-z0-9+/_-]{1,254}={0,2}', item)):
                    return 'QUERY'
            if key == '__biz' and not re.fullmatch(r'[A-Za-z0-9+/_-]{1,254}={0,2}', item):
                return 'QUERY'
            if key in {'mid', 'idx'} and not _DIGITS.fullmatch(item):
                return 'QUERY'
            if key == 'sn' and not re.fullmatch('[0-9a-fA-F]{32}', item):
                return 'QUERY'
            if key == 'chksm' and not re.fullmatch('[0-9a-fA-F]{1,256}', item):
                return 'QUERY'
        if parts.path == '/s':
            return 'SUPPORTED' if identity <= set(query) else 'QUERY'
        return 'SUPPORTED' if re.fullmatch(r'/s/[A-Za-z0-9_-]+', parts.path) else 'PATH'
    except (ValueError, UnicodeError):
        return 'URL_FORMAT'


def article_url_supported(value):
    """Validate a returned URL; never resolve, fetch, normalize or construct it."""
    return _article_url_reason(value) == 'SUPPORTED'


def _publication(value, count, account_key, intent_id):
    status = _int(value.get('publish_status'), 0, 6)
    fail = value.get('fail_idx')
    if type(fail) is not list:
        raise _Invalid('FAIL_INDEX_SHAPE')
    indices = tuple(_int(item, 1, count) for item in fail)
    if len(set(indices)) != len(indices) or (status == 0 and indices):
        raise _Invalid('FAIL_INDEX_POLICY')
    result = {'platform_status': status, 'fail_idx': indices,
              'effect': ('PUBLISHED_WITHOUT_PUSH' if status == 0 else 'PLATFORM_STATUS_OBSERVED'),
              'url_evidence': 'URL_EVIDENCE_INCOMPLETE', 'article_urls': ()}
    if status != 0:
        if 'article_id' in value or 'article_detail' in value:
            raise _Invalid('CONTRADICTORY_PUBLICATION_FIELDS')
        return result
    # Success status is evidence in its own right. Missing URL metadata does
    # not authorize a second submit; malformed present identity/count/indices
    # remain query-unverified instead of being presented as complete proof.
    if 'article_id' in value:
        article = value['article_id']
        if type(article) is not _String or not _opaque(article.value, 512):
            raise _Invalid('ARTICLE_ID_POLICY')
        result['article_id'] = ArticleID(article.value, account_key, intent_id)
    if 'article_detail' not in value:
        result['url_diagnostics'] = tuple((index, 'DETAIL_ABSENT') for index in range(1, count + 1))
        return result
    detail = value['article_detail']
    if type(detail) is not dict or _int(detail.get('count'), 1, 8) != count:
        raise _Invalid('ARTICLE_DETAIL_COUNT')
    rows = detail.get('item')
    if type(rows) is not list or len(rows) != count:
        raise _Invalid('ARTICLE_DETAIL_ITEMS')
    urls, diagnostics, complete = [], [], 'article_id' in result
    for index, row in enumerate(rows, 1):
        if type(row) is not dict or _int(row.get('idx'), 1, count) != index:
            raise _Invalid('ARTICLE_DETAIL_INDEX')
        url = row.get('article_url')
        if url is None:
            diagnostics.append((index, 'URL_MISSING_OR_NULL'))
            complete = False
            continue
        if type(url) is not _String:
            raise _Invalid('ARTICLE_URL_TYPE')
        reason = _article_url_reason(url.value)
        if reason == 'SUPPORTED':
            urls.append((index, url.value))
        else:
            diagnostics.append((index, reason))
            complete = False
    result['article_urls'] = tuple(urls)
    if diagnostics:
        result['url_diagnostics'] = tuple(diagnostics)
    if complete:
        result['url_evidence'] = 'COMPLETE'
    return result


def parse(method, response, token, *, account_key, intent_id, expected_task=None, article_count=None):
    """Project only method-specific evidence; caller persists request SHA too.

    result=None is never permission to retry. Nonzero error_code means an
    unambiguous error branch; malformed or contradictory bodies have no code.
    """
    response_sha, status = None, None
    try:
        _binding(account_key, intent_id)
        if method not in METHODS:
            raise _Invalid('INVALID_METHOD')
        if type(response) is not HTTPResponse or type(response.status) is not int:
            raise _Invalid('TRANSPORT_UNDETERMINED')
        status = response.status
        if type(response.body) is not bytes or len(response.body) > MAX_RESPONSE:
            raise _Invalid('RESPONSE_BOUND')
        response_sha = sha256(response.body).hexdigest()
        if upload.contains_secret(response.body, token, max_nodes=16384):
            raise _Invalid('RESPONSE_SECRET_REFLECTION')
        if status != 200:
            raise _Invalid('NON_SUCCESS_HTTP')
        value = _JSON(response.body).parse()
        if upload.contains_secret(_plain(value), token, max_nodes=16384):
            raise _Invalid('RESPONSE_SECRET_REFLECTION')
        query = method.endswith('.get')
        if query:
            _task(expected_task, METHODS[method][1], account_key, intent_id)
        code = _int(value['errcode'], -(2**31), 2**31 - 1) if 'errcode' in value else None
        publication_fields = {'publish_id', 'publish_status', 'article_id', 'article_detail', 'fail_idx'}
        mass_fields = {'msg_id', 'msg_status'}
        success_fields = publication_fields | mass_fields | {'msg_data_id'}
        if code is not None and code != 0:
            if success_fields & value.keys():
                raise _Invalid('CONTRADICTORY_ERROR_SUCCESS')
            return Reply(error_code=code, reason='QUERY_ERROR' if query else 'PLATFORM_REJECTED',
                         response_sha=response_sha, http_status=status)
        if not query and code is None:
            raise _Invalid('SUBMIT_CODE_REQUIRED')
        foreign_fields = mass_fields if method.startswith('freepublish') else publication_fields
        if foreign_fields & value.keys():
            raise _Invalid('CONTRADICTORY_ROUTE_FIELDS')
        field_name = 'publish_id' if method.startswith('freepublish') else 'msg_id'
        allowed = 'N' if method == 'mass.sendall' else 'NS'
        try:
            task = _id(value.get(field_name), allowed, method=method, account_key=account_key,
                       intent_id=intent_id, response_sha=response_sha)
        except _Invalid as error:
            if method != 'freepublish.get' or str(error) != 'TASK_ID_POLICY':
                raise
            raise _Invalid(_get_id_failure(value.get(field_name), present=field_name in value,
                                           expected_digits=expected_task.digits)) from None
        if query and task.digits != expected_task.digits:
            raise _Invalid('TASK_ID_MISMATCH')
        if method == 'freepublish.get':
            if type(article_count) is not int or not 1 <= article_count <= 8:
                raise _Invalid('ARTICLE_COUNT_REQUIRED')
            result = _publication(value, article_count, account_key, intent_id)
        elif method == 'mass.get':
            mass_status = value.get('msg_status')
            if type(mass_status) is not _String or mass_status.value not in MASS_STATES:
                raise _Invalid('MASS_STATUS_POLICY')
            result = {'platform_status': mass_status.value, 'url_evidence': 'NOT_AVAILABLE',
                      'effect': 'TARGETED_ALL_FOLLOWERS_STATUS_ONLY'}
        else:
            if {'publish_status', 'msg_status', 'article_detail', 'article_id', 'fail_idx'} & value.keys():
                raise _Invalid('CONTRADICTORY_SUBMIT_STATUS')
            result = {}
        # Preserve original accepted task for querying; observed wire spelling
        # belongs to response evidence and must never rewrite original identity.
        result.update({'task': expected_task if query else task, 'observed_task': task})
        return Reply(result=result, reason='PARSED_SUCCESS', response_sha=response_sha, http_status=status)
    except _Invalid as error:
        return Reply(reason=str(error), response_sha=response_sha, http_status=status)
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError, WCEError):
        return Reply(reason='INVALID_JSON_OR_RESPONSE', response_sha=response_sha, http_status=status)
