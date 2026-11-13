"""Bounded official draft projections; identifiers are opaque JSON values.

No reference is interpreted as a URL, filename, executable text or authority.
Extensions are inspected for reflection before projecting required fields.
"""
import unicodedata

from .contracts import WCEError
from .http_transport import HTTPResponse, MAX_BODY
from .prepared_draft_fixture import decode_json
from .service import digest
from . import upload_wire as upload

REASONS = frozenset({'DRAFT_REFERENCE_MISSING', 'DRAFT_REFERENCE_TYPE',
    'DRAFT_REFERENCE_POLICY', 'DRAFT_NEWS_SHAPE', 'DRAFT_ARTICLE_TYPE',
    'DRAFT_TITLE_POLICY', 'DRAFT_CONTENT_POLICY', 'DRAFT_COVER_POLICY',
    'DRAFT_SINGLE_NEWS_REQUIRED', 'DRAFT_REQUEST_REFERENCE_POLICY',
    'DRAFT_INVALID_JSON', 'DRAFT_CODE_TYPE'})


def reference_valid(value, synthetic=False):
    if (type(value) is not str or not 0 < len(value) <= 128
            or len(value.encode('utf-8', errors='replace')) > 512
            or any(c.isspace() or unicodedata.category(c).startswith('C') for c in value)):
        return False
    return synthetic or not value.startswith(('mock-', 'fixture-', 'synthetic-', 'local-', 'own-'))


def reference_reason(value):
    if 'media_id' not in value:
        return 'DRAFT_REFERENCE_MISSING'
    if type(value['media_id']) is not str:
        return 'DRAFT_REFERENCE_TYPE'
    return 'DRAFT_REFERENCE_POLICY'


def response_value(response, secret, *, list_response=False):
    def fail(reason):
        raise WCEError(reason)
    if type(response) is not HTTPResponse:
        fail('TRANSPORT_UNDETERMINED')
    if type(response.status) is not int or not 200 <= response.status < 300:
        fail('NON_SUCCESS_HTTP')
    if upload.contains_secret(response.body, secret):
        fail('RESPONSE_SECRET_REFLECTION')
    # Both walks count dictionary keys and values. Strict parsing rejects an
    # over-budget structure before the equally bounded reflection scan.
    nodes = 16384 if list_response else 4096
    try:
        value = decode_json(response.body, MAX_BODY, max_nodes=nodes)
    except Exception:
        fail('DRAFT_INVALID_JSON')
    if type(value) is not dict:
        fail('INVALID_JSON_SHAPE')
    if upload.contains_secret(value, secret, max_nodes=nodes):
        fail('RESPONSE_SECRET_REFLECTION')
    if type(value.get('errcode', 0)) is not int:
        fail('DRAFT_CODE_TYPE')
    return value


def project_news(value, synthetic=False, *, exclude_non_target=False):
    """Project all news entries; never normalize HTML, entities or image URLs."""
    items = value.get('news_item') if type(value) is dict else None
    if type(items) is not list or not 1 <= len(items) <= 10:
        raise WCEError('DRAFT_NEWS_SHAPE')
    projected = []
    for item in items:
        if type(item) is not dict:
            raise WCEError('DRAFT_NEWS_SHAPE')
        kind = item.get('article_type', 'news')
        if type(kind) is not str or kind not in ('news', 'newspic'):
            raise WCEError('DRAFT_ARTICLE_TYPE')
        if exclude_non_target and (len(items) != 1 or kind == 'newspic'):
            # The reviewed target is exactly one news article. A known other
            # type or multiple entries cannot match; do not impose news-only
            # required fields on it. Retain only a digest for list stability.
            projected.append({'article_type': kind, 'non_target_digest': digest(item)})
            continue
        title, content, cover = (item.get(k) for k in ('title', 'content', 'thumb_media_id'))
        if type(title) is not str or not 0 < len(title) <= 128:
            raise WCEError('DRAFT_TITLE_POLICY')
        if type(content) is not str or len(content) > 20000 or len(content.encode()) > 1_000_000:
            raise WCEError('DRAFT_CONTENT_POLICY')
        if not reference_valid(cover, synthetic):
            raise WCEError('DRAFT_COVER_POLICY')
        projected.append({'article_type': kind, 'title': title, 'content': content, 'thumb_media_id': cover})
    return projected


def exact_single(items, expected):
    return len(items) == 1 and items[0] == {'article_type': 'news'} | expected


COMMENT_FIELDS = ('need_open_comment', 'only_fans_can_comment')


def observe_comments(items):
    """Bounded sidecar only: preserve presence/type, never retain raw strings.

    Call after project_news has validated the response's ordered article shape.
    No missing field receives the platform's documented default.
    """
    types = {type(None): 'null', bool: 'boolean', int: 'integer',
             float: 'number', str: 'string', list: 'array', dict: 'object'}
    return tuple({key: {'present': key in item,
                         'type': types.get(type(item[key]), 'unknown') if key in item else 'missing',
                         'value': item[key] if key in item and type(item[key]) is int
                                  and item[key] in (0, 1) else None}
                  for key in COMMENT_FIELDS} for item in items)


def comment_comparison(expected, observations):
    """Compare explicitly approved ordered settings, apart from strict content.

    None means legacy/no explicit expectation and produces no verification claim.
    Invalid actual data is UNVERIFIED; valid unequal data is MISMATCH.
    """
    if expected is None:
        return None
    if (type(expected) is not list or not 1 <= len(expected) <= 8
            or any(type(row) is not dict or set(row) != set(COMMENT_FIELDS)
                   or any(type(row[key]) is not int or row[key] not in (0, 1)
                          for key in COMMENT_FIELDS) for row in expected)):
        raise WCEError('OWN_COMMENT_EXPECTATION_INVALID')
    rows = observations if type(observations) in (list, tuple) else ()
    count_match = len(rows) == len(expected)
    result = []
    for index, approved in enumerate(expected):
        actual = rows[index] if index < len(rows) and type(rows[index]) is dict else {}
        fields = {}
        for key in COMMENT_FIELDS:
            seen = actual.get(key)
            shape = (type(seen) is dict and set(seen) == {'present', 'type', 'value'}
                     and type(seen['present']) is bool and type(seen['type']) is str
                     and seen['type'] in {'missing', 'null', 'boolean', 'integer',
                                          'number', 'string', 'array', 'object', 'unknown'})
            valid = (shape and seen['present'] and seen['type'] == 'integer'
                     and type(seen['value']) is int and seen['value'] in (0, 1))
            state = ('VERIFIED' if seen['value'] == approved[key] else 'MISMATCH') if valid and count_match else 'UNVERIFIED'
            fields[key] = {'state': state, 'present': seen['present'] if shape else None,
                           'type': seen['type'] if shape else 'unavailable',
                           'actual_value': seen['value'] if valid else None}
        states = {field['state'] for field in fields.values()}
        state = 'MISMATCH' if 'MISMATCH' in states else 'UNVERIFIED' if 'UNVERIFIED' in states else 'VERIFIED'
        result.append({'index': index, 'state': state, 'fields': fields})
    return {'policy': 'EXPLICIT_COMMENT_INTEGER_EXACT_V1',
            'count_match': count_match, 'articles': result}
