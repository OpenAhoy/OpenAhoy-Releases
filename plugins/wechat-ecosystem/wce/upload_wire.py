"""Test-only image request encoding and static response classification.

No Operation, executor, journal, sender, receipt or platform material mapping.
Limits, MIME/ID/URL rules and required success fields are local policy.
"""
from dataclasses import dataclass, field
import ipaddress
import json
import math
import re
from secrets import token_hex
from urllib.parse import quote, quote_plus, unquote, unquote_to_bytes, urlencode, urlsplit

from .contracts import Secret, WCEError
from .draft_wire import TOKEN_INVALID_CODES, unique_object
from .http_transport import HTTPRequest, HTTPResponse, MAX_BODY
from .local_preparation import image_check

ENDPOINTS = {"permanent_cover": "/cgi-bin/material/add_material",
             "article_body": "/cgi-bin/media/uploadimg"}
SOURCE_URLS = {
    "permanent_cover": "https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html",
    "article_body": "https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_uploadimage.html",
}
SOURCE_HASHES = {
    "permanent_cover": "6a4f6e4b97dc3c76393fe113031bdf67d61b956ea3e2bf786f3c6a3859fc3d3e",
    "article_body": "0d86e7ec0298be66a9def0a93044b6b92a6da1ca486945ea5bb98c8f221aafc2",
}
from .html_technical_standard import LIMITS
BODY_IMAGE_LIMIT = LIMITS['body_image_bytes_exclusive']
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 256
RESPONSE_REASONS = frozenset({'IMAGE_RESPONSE_KIND', 'IMAGE_RESPONSE_TRANSPORT',
    'IMAGE_RESPONSE_HTTP', 'IMAGE_RESPONSE_BYTES', 'IMAGE_RESPONSE_JSON',
    'IMAGE_RESPONSE_OBJECT', 'IMAGE_JSON_NODES', 'IMAGE_JSON_DEPTH',
    'IMAGE_JSON_STRING_BYTES', 'IMAGE_JSON_STRING_CONTROL',
    'IMAGE_RESPONSE_REFLECTION', 'IMAGE_RESPONSE_FIELDS', 'IMAGE_ERRMSG_TYPE',
    'IMAGE_ERRMSG_LENGTH', 'IMAGE_ERRCODE_TYPE', 'IMAGE_ERROR_WITH_REFERENCE',
    'IMAGE_URL_POLICY', 'IMAGE_BODY_CODE_MISSING', 'IMAGE_MEDIA_IDENTIFIER',
    'IMAGE_RESPONSE_UNDETERMINED', 'IMAGE_PRODUCTION_HOST_POLICY',
    'IMAGE_REFERENCE_HOST', 'IMAGE_REFERENCE_AUTHORITY_CASE', 'IMAGE_REFERENCE_PORT',
    'IMAGE_REFERENCE_PERCENT', 'IMAGE_REFERENCE_PATH', 'IMAGE_REFERENCE_QUERY',
    'IMAGE_REFERENCE_ENCODING', 'IMAGE_REFERENCE_CONTROL', 'IMAGE_REFERENCE_TRAVERSAL',
    'IMAGE_REFERENCE_NESTED_URL', 'IMAGE_REFERENCE_CREDENTIAL'})


def secret_value(secret):
    try:
        value = secret.reveal_for_adapter() if isinstance(secret, Secret) else None
        if (not isinstance(value, str) or not 8 <= len(value) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in value)):
            raise ValueError()
        return value
    except Exception:
        raise WCEError("UPLOAD_SECRET_UNAVAILABLE") from None


def contains_secret(value, secret, *, max_decode_layers=3, max_nodes=1024):
    """Bounded raw/URL-encoded reflection scan; never render the sensitive value."""
    if type(max_nodes) is not int or not 1 <= max_nodes <= 16384:
        raise WCEError('UPLOAD_SCAN_BUDGET_INVALID')
    sensitive = secret_value(secret)
    variants = {v.encode("ascii") for v in
                (sensitive, quote(sensitive, safe=""), quote_plus(sensitive, safe=""))}
    stack, inspected = [value], 0
    while stack:
        inspected += 1
        if inspected > max_nodes:
            return True
        item = stack.pop()
        if isinstance(item, (bytes, str)):
            try:
                item = item.encode("utf-8") if isinstance(item, str) else item
            except UnicodeError:
                return True
            # Include the final decoded layer; binary image data stays binary.
            for layer in range(max_decode_layers + 1):
                if any(v in item for v in variants):
                    return True
                if layer == max_decode_layers:
                    break
                decoded = unquote_to_bytes(item)
                if decoded == item:
                    break
                item = decoded
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (tuple, list)):
            stack.extend(item)
    return False


def _boundary():
    return "wce-" + token_hex(16)


def build_request(purpose, declared_type, data, secret):
    """Trusted encoding primitive; the business entry validates the frozen package."""
    if not isinstance(purpose, str) or purpose not in ENDPOINTS:
        raise WCEError("INVALID_UPLOAD_PURPOSE")
    if not isinstance(declared_type, str) or declared_type not in {"image/png", "image/jpeg"}:
        raise WCEError("INVALID_LOCAL_IMAGE")
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BODY:
        raise WCEError("UPLOAD_TRANSPORT_LIMIT")
    if purpose == "article_body" and len(data) >= BODY_IMAGE_LIMIT:
        raise WCEError("BODY_IMAGE_LIMIT")
    image_check(data, declared_type)
    boundary = _boundary()
    if not isinstance(boundary, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,70}", boundary) is None:
        raise WCEError("INVALID_MULTIPART_BOUNDARY")
    if boundary.encode("ascii") in data:
        raise WCEError("MULTIPART_BOUNDARY_COLLISION")
    extension = "png" if declared_type == "image/png" else "jpg"
    filename = ("cover" if purpose == "permanent_cover" else "body") + "." + extension
    prefix = ("--" + boundary + '\r\nContent-Disposition: form-data; name="media"; filename="'
              + filename + '"\r\nContent-Type: ' + declared_type + "\r\n\r\n").encode("ascii")
    suffix = ("\r\n--" + boundary + "--\r\n").encode("ascii")
    if len(prefix) + len(data) + len(suffix) > MAX_BODY:
        raise WCEError("UPLOAD_TRANSPORT_LIMIT")
    headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    if contains_secret((prefix, data, suffix, headers), secret):
        raise WCEError("UPLOAD_SECRET_CONTAMINATION")
    query = {"access_token": secret_value(secret)}
    if purpose == "permanent_cover":
        query["type"] = "image"
    return HTTPRequest("POST", ENDPOINTS[purpose] + "?" + urlencode(query), headers,
                       prefix + data + suffix, test_only=True)


def _url(value):
    if (not isinstance(value, str) or not value or len(value) > 2048
            or any(not 33 <= ord(c) <= 126 for c in value) or "\\" in value or "#" in value
            or re.search(r"%(?![A-Fa-f0-9]{2})", value)):
        return False
    try:
        decoded = unquote(value, errors="strict")
        if any(ord(c) < 32 or ord(c) == 127 for c in decoded):
            return False
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.netloc or not parts.hostname
                or parts.username is not None or parts.password is not None or parts.fragment
                or parts.netloc.endswith(":")):
            return False
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return False
        host = parts.hostname
        if ":" in host:
            if "%" in host:
                return False
            ipaddress.IPv6Address(host)
        elif all(c in "0123456789." for c in host):
            ipaddress.IPv4Address(host)
        else:
            if len(host) > 253 or any(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                      is None for label in host.split(".")):
                return False
        return True
    except (ValueError, UnicodeError):
        return False


def _integer(value):
    if len(value) > 11:
        raise ValueError()
    number = int(value)
    if not -(2 ** 31) <= number < 2 ** 31:
        raise ValueError()
    return number


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError()
    return number


def _constant(_):
    raise ValueError()


def _shape_reason(value):
    stack, nodes = [(value, 1)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            return 'IMAGE_JSON_NODES'
        if depth > MAX_JSON_DEPTH:
            return 'IMAGE_JSON_DEPTH'
        if isinstance(item, str):
            if len(item.encode("utf-8")) > 4096:
                return 'IMAGE_JSON_STRING_BYTES'
            if any(ord(c) < 32 or ord(c) == 127 for c in item):
                return 'IMAGE_JSON_STRING_CONTROL'
        elif isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.keys())
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return None


def _shape(value):
    return _shape_reason(value) is None


@dataclass(frozen=True)
class UploadReply:
    """Parsed untrusted fields only: never a platform receipt or executor reply."""
    purpose: str
    classification: str = "UNDETERMINED"
    media_id: str | None = None
    url: str | None = None
    error_code: int | None = None
    requires_credential_update: bool = False
    effect: str = "UNDETERMINED"
    test_only: bool = True
    platform_verified: bool = False
    platform_ready: bool = False
    executor_integration: str = "UNIMPLEMENTED"


RESPONSE_STAGES = ('kind', 'transport', 'http', 'bytes', 'raw_reflection', 'json',
    'object', 'shape', 'decoded_reflection', 'fields', 'errmsg', 'code', 'url',
    'explicit_code', 'media', 'production')
BODY_RESPONSE_POLICY = 'BODY_URL_RESPONSE_V1'
BODY_API_REFERENCE_POLICY = 'BODY_API_REFERENCE_V2'
COVER_RESPONSE_POLICY = 'COVER_RESPONSE_PROJECTION_V1'
REFERENCE_COMPATIBILITY_REASONS = frozenset({
    'IMAGE_REFERENCE_AUTHORITY_CASE', 'IMAGE_REFERENCE_PERCENT',
    'IMAGE_REFERENCE_PATH', 'IMAGE_REFERENCE_QUERY'})


def body_reference_url(value):
    """Closed local response-reference policy, not a CDN fetch permission.

    Preserve the exact API string. Public image format flags are the only query
    accepted. No query removal, scheme upgrade, nested URL or redirect occurs.
    """
    return body_reference_reason(value) is None


def body_reference_reason(value):
    """The exact V1 acceptance set, with fixed first-failure evidence."""
    if not _url(value):
        return 'IMAGE_URL_POLICY'
    try:
        parts = urlsplit(value)
        if parts.hostname != 'mmbiz.qpic.cn':
            return 'IMAGE_REFERENCE_HOST'
        if parts.netloc.lower() != parts.netloc:
            return 'IMAGE_REFERENCE_AUTHORITY_CASE'
        if parts.port not in (None, 80 if parts.scheme == 'http' else 443):
            return 'IMAGE_REFERENCE_PORT'
        # Historical V1 closed compatibility grammar, not an official CDN spec.
        if '%' in value:
            return 'IMAGE_REFERENCE_PERCENT'
        if not re.fullmatch(r'/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', parts.path):
            return 'IMAGE_REFERENCE_PATH'
        if parts.query and re.fullmatch(r'wx_fmt=(?:png|jpeg|jpg)', parts.query) is None:
            return 'IMAGE_REFERENCE_QUERY'
        return None
    except (ValueError, UnicodeError):
        return 'IMAGE_URL_POLICY'


_PCHAR = r"A-Za-z0-9\-._~!$&'()*+,;=:@"
_REFERENCE_CREDENTIAL_KEYS = frozenset({'accesstoken', 'refreshtoken', 'appsecret',
    'secret', 'password', 'passwd', 'authorization', 'auth', 'bearer', 'cookie',
    'session', 'sessionid', 'sid', 'signature', 'sign', 'token', 'apikey', 'key',
    'credential', 'code', 'ticket'})


def _reference_component_reason(value, *, query):
    """Inspect bounded bytes at every decoding layer; never normalize the URL."""
    current = value.encode('ascii')
    for layer in range(5):
        if any(c < 32 or c == 127 or c in b'\\#' for c in current):
            return 'IMAGE_REFERENCE_CONTROL'
        try:
            current.decode('utf-8', errors='strict')
        except UnicodeError:
            return 'IMAGE_REFERENCE_ENCODING'
        if (re.search(rb'[A-Za-z][A-Za-z0-9+.-]*:', current)
                or b'//' in current):
            return 'IMAGE_REFERENCE_NESTED_URL'
        if not query and any(part in (b'.', b'..') for part in current.split(b'/')):
            return 'IMAGE_REFERENCE_TRAVERSAL'
        if query and current:
            entries = re.split(rb'[&;]', current)
            if len(entries) > 64:
                return 'IMAGE_REFERENCE_QUERY'
            for entry in entries:
                key = entry.split(b'=', 1)[0]
                if not key:
                    return 'IMAGE_REFERENCE_QUERY'
                normalized = key.lower().replace(b'-', b'').replace(b'_', b'')
                if normalized.decode('utf-8') in _REFERENCE_CREDENTIAL_KEYS:
                    return 'IMAGE_REFERENCE_CREDENTIAL'
        if b'%' not in current:
            return None
        if re.search(rb'%(?![A-Fa-f0-9]{2})', current) or layer == 4:
            return 'IMAGE_REFERENCE_ENCODING'
        current = unquote_to_bytes(current)
    return 'IMAGE_REFERENCE_ENCODING'


def api_reference_reason(value):
    """V2 private API-reference policy. This never authorizes a CDN fetch.

    Unknown opaque query data is allowed. Only the controlled token scan and
    explicit credential-key set are covered; arbitrary unknown secrets are not.
    """
    if not _url(value):
        return 'IMAGE_URL_POLICY'
    parts = urlsplit(value)
    if parts.hostname != 'mmbiz.qpic.cn':
        return 'IMAGE_REFERENCE_HOST'
    if parts.port not in (None, 80 if parts.scheme == 'http' else 443):
        return 'IMAGE_REFERENCE_PORT'
    if not re.fullmatch(r'/[' + _PCHAR + r'/%]*', parts.path):
        return 'IMAGE_REFERENCE_PATH'
    if not re.fullmatch(r'[' + _PCHAR + r'/%?]*', parts.query):
        return 'IMAGE_REFERENCE_QUERY'
    return (_reference_component_reason(parts.path, query=False)
            or _reference_component_reason(parts.query, query=True))


@dataclass(frozen=True)
class ReferenceAssessment:
    """Private observation eligibility from the same parsed response value."""
    policy: str
    reason: str
    url: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ResponseInspection:
    reply: UploadReply
    reason: str
    stages: tuple
    code_form: str = 'NOT_EVALUATED'
    reference: ReferenceAssessment | None = None
    cover_projection: tuple | None = None

    def __iter__(self):
        # Transitional unpacking remains compatible; the actual result and
        # evidence always travel together as this immutable object.
        yield self.reply
        yield self.reason

    def diagnostic(self):
        value = {'schema': 2, 'reason': self.reason, 'stages': [list(v) for v in self.stages],
                 'code_form': self.code_form}
        if self.reference is not None:
            value.update(schema=3, reference={'policy': self.reference.policy,
                'reason': self.reference.reason})
        if self.cover_projection is not None:
            value.update(schema=4, projection={'policy': self.cover_projection[0],
                'extra_key_count': self.cover_projection[1]})
        return value


def validate_inspection_diagnostic(value):
    schema = value.get('schema') if type(value) is dict else None
    fields = {'schema', 'reason', 'stages', 'code_form'} | (
        {'reference'} if schema == 3 else {'projection'} if schema == 4 else set())
    if (type(value) is not dict or set(value) != fields
            or type(value['schema']) is not int or value['schema'] not in (2, 3, 4)
            or type(value['reason']) is not str or value['reason'] not in RESPONSE_REASONS | {'PARSED_SUCCESS', 'PLATFORM_ERROR'}
            or type(value['code_form']) is not str or value['code_form'] not in {'NOT_EVALUATED', 'ABSENT', 'ZERO', 'NONZERO', 'INVALID'}
            or type(value['stages']) is not list or len(value['stages']) != len(RESPONSE_STAGES)):
        raise WCEError('OWN_STATE_CORRUPT')
    stopped = False
    for expected, item in zip(RESPONSE_STAGES, value['stages']):
        if (type(item) is not list or len(item) != 2 or item[0] != expected
                or type(item[1]) is not str or item[1] not in {'PASS', 'FAIL', 'NOT_EVALUATED'}
                or (stopped and item[1] != 'NOT_EVALUATED')):
            raise WCEError('OWN_STATE_CORRUPT')
        if item[1] == 'FAIL' or (item[1] == 'NOT_EVALUATED' and expected != 'raw_reflection'):
            stopped = True
    if value['reason'] == 'PARSED_SUCCESS' and any(v[1] != 'PASS' and not (v[0] == 'raw_reflection' and v[1] == 'NOT_EVALUATED') for v in value['stages']):
        raise WCEError('OWN_STATE_CORRUPT')
    trace = dict(value['stages'])
    form = value['code_form']
    if ((trace['code'] == 'NOT_EVALUATED' and form != 'NOT_EVALUATED')
            or (trace['code'] == 'PASS' and form not in {'ABSENT', 'ZERO', 'NONZERO'})
            or (trace['code'] == 'FAIL' and form not in {'INVALID', 'NONZERO'})
            or (value['reason'] == 'PARSED_SUCCESS' and form not in {'ABSENT', 'ZERO'})
            or (value['reason'] == 'PLATFORM_ERROR' and (form != 'NONZERO' or trace['code'] != 'PASS'))):
        raise WCEError('OWN_STATE_CORRUPT')
    if schema == 3:
        reference = value['reference']
        if (type(reference) is not dict or set(reference) != {'policy', 'reason'}
                or reference['policy'] != BODY_API_REFERENCE_POLICY
                or type(reference['reason']) is not str
                or reference['reason'] not in {'REFERENCE_SAFE', 'IMAGE_URL_POLICY'} |
                    {r for r in RESPONSE_REASONS if r.startswith('IMAGE_REFERENCE_')}
                or any(state != 'PASS' for stage, state in value['stages'] if stage != 'production')
                or trace['production'] not in {'PASS', 'FAIL'}
                or (trace['production'] == 'PASS' and reference['reason'] != 'REFERENCE_SAFE')):
            raise WCEError('OWN_STATE_CORRUPT')
    if schema == 4:
        projection = value['projection']
        if (type(projection) is not dict or set(projection) != {'policy', 'extra_key_count'}
                or projection['policy'] != COVER_RESPONSE_POLICY
                or any(trace[stage] != 'PASS' for stage in RESPONSE_STAGES[:10])
                or type(projection['extra_key_count']) is not int
                or not 0 <= projection['extra_key_count'] <= MAX_JSON_NODES):
            raise WCEError('OWN_STATE_CORRUPT')
    return value


def inspect_response(purpose, response, secret, *, policy='LEGACY_V1', production=False):
    """One parse/classification creates the result and its first-failure trace.

    NOT_EVALUATED is retained after early exits. There is no diagnostic parser
    and no untrusted name, errmsg, raw bytes or URL in the trace.
    """
    kind = purpose if isinstance(purpose, str) and purpose in ENDPOINTS else 'unsupported'
    unknown = UploadReply(kind)
    stages = {stage: 'NOT_EVALUATED' for stage in RESPONSE_STAGES}
    code_form = 'NOT_EVALUATED'
    reference = None
    cover_projection = None

    def done(reason, reply=unknown):
        return ResponseInspection(reply, reason, tuple(stages.items()), code_form, reference, cover_projection)

    def gate(stage, condition, reason):
        stages[stage] = 'PASS' if condition else 'FAIL'
        return None if condition else done(reason)

    try:
        body_profile = policy in {BODY_RESPONSE_POLICY, BODY_API_REFERENCE_POLICY}
        cover_profile = policy == COVER_RESPONSE_POLICY
        result = gate('kind', kind != 'unsupported' and policy in {
            'LEGACY_V1', BODY_RESPONSE_POLICY, BODY_API_REFERENCE_POLICY, COVER_RESPONSE_POLICY}
            and (not body_profile or kind == 'article_body')
            and (not cover_profile or kind == 'permanent_cover'), 'IMAGE_RESPONSE_KIND')
        if result: return result
        result = gate('transport', (type(response) is HTTPResponse if body_profile or cover_profile else isinstance(response, HTTPResponse)), 'IMAGE_RESPONSE_TRANSPORT')
        if result: return result
        result = gate('http', type(response.status) is int and 200 <= response.status < 300, 'IMAGE_RESPONSE_HTTP')
        if result: return result
        result = gate('bytes', isinstance(response.body, bytes) and 0 < len(response.body) <= MAX_BODY, 'IMAGE_RESPONSE_BYTES')
        if result: return result
        # The standalone legacy parser historically scanned decoded JSON only.
        # Own/new-profile paths also scan raw text before parsing.
        if production or body_profile or cover_profile:
            result = gate('raw_reflection', not contains_secret(response.body, secret,
                max_decode_layers=4 if body_profile else 3), 'IMAGE_RESPONSE_REFLECTION')
            if result: return result
        try:
            value = json.loads(response.body.decode('utf-8'), object_pairs_hook=unique_object,
                               parse_constant=_constant, parse_int=_integer, parse_float=_float)
        except Exception:
            stages['json'] = 'FAIL'
            return done('IMAGE_RESPONSE_JSON')
        stages['json'] = 'PASS'
        result = gate('object', isinstance(value, dict), 'IMAGE_RESPONSE_OBJECT')
        if result: return result
        try:
            shape_reason = _shape_reason(value)
        except Exception:
            stages['shape'] = 'FAIL'
            return done('IMAGE_RESPONSE_UNDETERMINED')
        result = gate('shape', shape_reason is None, shape_reason or 'IMAGE_RESPONSE_UNDETERMINED')
        if result: return result
        result = gate('decoded_reflection', not contains_secret(value, secret,
            max_decode_layers=4 if body_profile else 3), 'IMAGE_RESPONSE_REFLECTION')
        if result: return result
        allowed = {'url', 'errcode', 'errmsg'} | ({'media_id'} if kind == 'permanent_cover' else set())
        # Inspect the entire untrusted object first. Extensions never reach the
        # returned reference, journal or diagnostic; legacy remains closed-set.
        extras = len(set(value) - allowed)
        result = gate('fields', cover_profile or extras == 0, 'IMAGE_RESPONSE_FIELDS')
        if result: return result
        if cover_profile:
            cover_projection = (COVER_RESPONSE_POLICY, extras)
            value = {key: value[key] for key in allowed if key in value}
        if 'errmsg' in value and not isinstance(value['errmsg'], str):
            stages['errmsg'] = 'FAIL'; return done('IMAGE_ERRMSG_TYPE')
        result = gate('errmsg', 'errmsg' not in value or len(value['errmsg']) <= 2048, 'IMAGE_ERRMSG_LENGTH')
        if result: return result
        code = value.get('errcode', 0)
        code_form = ('ABSENT' if 'errcode' not in value else 'INVALID' if type(code) is not int else
                     'ZERO' if code == 0 else 'NONZERO')
        result = gate('code', type(code) is int, 'IMAGE_ERRCODE_TYPE')
        if result: return result
        if code != 0:
            if 'url' in value or 'media_id' in value:
                stages['code'] = 'FAIL'; return done('IMAGE_ERROR_WITH_REFERENCE')
            return done('PLATFORM_ERROR', UploadReply(kind, 'PLATFORM_ERROR', error_code=code,
                        requires_credential_update=code in TOKEN_INVALID_CODES))
        result = gate('url', _url(value.get('url')), 'IMAGE_URL_POLICY')
        if result: return result
        result = gate('explicit_code', kind != 'article_body' or 'errcode' in value or
            body_profile, 'IMAGE_BODY_CODE_MISSING')
        if result: return result
        media = value.get('media_id')
        result = gate('media', kind != 'permanent_cover' or
            (isinstance(media, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', media) is not None), 'IMAGE_MEDIA_IDENTIFIER')
        if result: return result
        if body_profile:
            safety_reason = api_reference_reason(value['url'])
            reference = ReferenceAssessment(BODY_API_REFERENCE_POLICY,
                safety_reason or 'REFERENCE_SAFE', value['url'] if safety_reason is None else None)
            production_reason = (body_reference_reason(value['url']) if policy == BODY_RESPONSE_POLICY else safety_reason)
        else:
            production_reason = ('IMAGE_PRODUCTION_HOST_POLICY' if production and
                urlsplit(value['url']).hostname.lower().endswith(('.invalid', '.test', '.localhost')) else None)
            if cover_profile and production:
                from .own_wire import identifier
                if production_reason is None and not identifier(media, False):
                    production_reason = 'IMAGE_MEDIA_IDENTIFIER'
        result = gate('production', production_reason is None, production_reason or 'IMAGE_PRODUCTION_HOST_POLICY')
        if result: return result
        return done('PARSED_SUCCESS', UploadReply(kind, 'PARSED_SUCCESS',
            media_id=media if kind == 'permanent_cover' else None, url=value['url']))
    except Exception:
        return done('IMAGE_RESPONSE_UNDETERMINED')


def parse_response(purpose, response, secret):
    return inspect_response(purpose, response, secret).reply
