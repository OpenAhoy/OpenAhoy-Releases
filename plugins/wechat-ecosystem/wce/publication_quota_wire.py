"""Fixed official quota wire data. No I/O, grants, clock or trusted observation.

The host must authorize and journal a query before sending the returned request.
Decoded quota data is not an account-bound lease or shared-accounting proof.
This isolated adapter does not enable publication_quota.TrustedHostProvider.
"""
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlencode, unquote_to_bytes

from .contracts import WCEError
from .http_transport import HTTPRequest, HTTPResponse
from .publication_contract import strict_json
from .publication_quota import PATHS
from . import upload_wire

ENDPOINT = '/cgi-bin/openapi/quota/get'
MAX_RESPONSE = 65536
INT_MAX = 2**31 - 1
MAX_REFRESH_SECONDS = INT_MAX // 1000


@dataclass(frozen=True)
class Frequency:
    period_call_limit: int
    refresh_ms: int


@dataclass(frozen=True)
class QuotaData:
    daily_limit: int
    used: int
    remaining: int
    frequency: Frequency | None


@dataclass(frozen=True)
class QuotaReply:
    reason: str
    http_status: int | None = None
    error_code: int | None = None
    response_sha: str | None = None
    data: QuotaData | None = None


def encode(api_path, secret):
    """Encode only the fixed ordinary-account paths. Never send or log a token."""
    if type(api_path) is not str or api_path not in PATHS:
        raise WCEError('QUOTA_PATH_UNSUPPORTED')
    try:
        credential = upload_wire.secret_value(secret)
    except WCEError:
        raise WCEError('QUOTA_SECRET_UNAVAILABLE') from None
    # PATHS contains only fixed ASCII path literals, no user-controlled query.
    body = ('{"cgi_path":"' + api_path + '"}').encode('ascii')
    return HTTPRequest('POST', ENDPOINT + '?' + urlencode({'access_token': credential}),
                       {'Content-Type': 'application/json; charset=utf-8'}, body)


def _integer(value, maximum=INT_MAX):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError()
    return value


def _frequency(value):
    if 'rate_limit' not in value:
        return None
    limits = value['rate_limit']
    if type(limits) is not dict:
        raise ValueError()
    # Validate every present field before classifying a missing or zero peer.
    checked = {}
    for field, maximum in (('call_count', INT_MAX),
                           ('refresh_second', MAX_REFRESH_SECONDS)):
        if field in limits:
            checked[field] = _integer(limits[field], maximum)
    if (len(checked) != 2 or checked['call_count'] == 0
            or checked['refresh_second'] == 0):
        return None
    return Frequency(checked['call_count'], checked['refresh_second'] * 1000)


def _unsafe_reflection(value, secret):
    if upload_wire.contains_secret(value, secret, max_nodes=16384):
        return True
    # The shared scanner checks three decoded layers. A value that still
    # changes after that budget is undecidable, not evidence of no reflection.
    stack, nodes = [value], 0
    while stack:
        nodes += 1
        if nodes > 16384:
            return True
        item = stack.pop()
        if type(item) in (str, bytes):
            try:
                item = item.encode('utf-8') if type(item) is str else item
            except UnicodeError:
                return True
            for _ in range(3):
                decoded = unquote_to_bytes(item)
                if decoded == item:
                    break
                item = decoded
            else:
                if unquote_to_bytes(item) != item:
                    return True
        elif type(item) is dict:
            stack.extend(item.keys())
            stack.extend(item.values())
        elif type(item) is list:
            stack.extend(item)
    return False


def parse(response, secret):
    """Return only fixed diagnostics and validated numeric data, never raw text.

    Missing ordinary frequency can retain daily data, but cannot satisfy the
    existing Observation contract. A period total is not its remaining quota.
    """
    if type(response) is not HTTPResponse or type(response.status) is not int:
        return QuotaReply('TRANSPORT_UNDETERMINED')
    status = response.status
    if type(response.body) is not bytes or not 0 < len(response.body) <= MAX_RESPONSE:
        return QuotaReply('RESPONSE_BOUND', http_status=status)
    try:
        if _unsafe_reflection(response.body, secret):
            return QuotaReply('RESPONSE_SECRET_REFLECTION', http_status=status)
        if status != 200:
            return QuotaReply('NON_SUCCESS_HTTP', http_status=status)
        value = strict_json(response.body, MAX_RESPONSE)
        if _unsafe_reflection(value, secret):
            return QuotaReply('RESPONSE_SECRET_REFLECTION', http_status=status)
        if type(value) is not dict:
            raise ValueError()
        code = value.get('errcode')
        if type(code) is not int or not -(2**31) <= code <= INT_MAX:
            raise ValueError()
        response_sha = sha256(response.body).hexdigest()
        if code != 0:
            return QuotaReply('API_REJECTED', status, code, response_sha)
        quota = value.get('quota')
        if type(quota) is not dict:
            raise ValueError()
        limit = _integer(quota.get('daily_limit'))
        used = _integer(quota.get('used'))
        remain = _integer(quota.get('remain'))
        # Local conservative consistency rule, not an official identity claim.
        if used + remain > limit:
            raise ValueError()
        frequency = _frequency(value)
        data = QuotaData(limit, used, remain, frequency)
        reason = ('ORDINARY_QUOTA_DATA' if frequency is not None
                  else 'DAILY_ONLY_FREQUENCY_UNVERIFIED')
        return QuotaReply(reason, status, None, response_sha, data)
    except WCEError as error:
        reason = ('QUOTA_SECRET_UNAVAILABLE' if error.code == 'UPLOAD_SECRET_UNAVAILABLE'
                  else 'INVALID_QUOTA_RESPONSE')
        return QuotaReply(reason, http_status=status)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return QuotaReply('INVALID_QUOTA_RESPONSE', http_status=status)
