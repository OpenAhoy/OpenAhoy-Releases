"""Separate official wire encoding with conservative single-news policy.

Encoding does not establish an account capability or resolve the news schema.
The executor must supply independent scoped evidence before live admission.
"""
from dataclasses import dataclass
from html import escape
import re
from secrets import token_hex
from urllib.parse import urlencode, urlsplit

from .contracts import WCEError
from .draft_wire import TOKEN_INVALID_CODES
from .http_transport import HTTPRequest, HTTPResponse, MAX_BODY
from .local_preparation import image_check
from .prepared_draft import SOURCES as DRAFT_SOURCES
from .prepared_draft_fixture import decode_json
from .service import canonical
from . import upload_wire as upload

SOURCES = {k: {'url': upload.SOURCE_URLS[k], 'sha256': upload.SOURCE_HASHES[k]}
           for k in upload.ENDPOINTS} | DRAFT_SOURCES

# Shared technical rules bind the reviewed public snapshot and are distinct
# from account permission, current API acceptance and rendered visual QA.
from .html_technical_standard import LIMITS, validate_payload, validate_upload
NEWS_CONTENT_CHAR_LIMIT = LIMITS['content_chars_exclusive']
NEWS_CONTENT_BYTE_LIMIT = LIMITS['content_bytes_exclusive']


def identifier(value, synthetic):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is None:
        return False
    return synthetic or not value.startswith(('mock-', 'fixture-', 'synthetic-', 'local-', 'own-'))


def image_url(value, synthetic):
    if not upload._url(value):
        return False
    return synthetic or not urlsplit(value).hostname.lower().endswith(('.invalid', '.test', '.localhost'))


def encode_upload(purpose, mime, data, secret):
    if purpose not in upload.ENDPOINTS or mime not in {'image/png', 'image/jpeg'} or type(data) is not bytes:
        raise WCEError('OWN_INVALID_IMAGE')
    if not 0 < len(data) <= MAX_BODY or (purpose == 'article_body' and len(data) >= upload.BODY_IMAGE_LIMIT):
        raise WCEError('OWN_IMAGE_LIMIT')
    image_check(data, mime)
    validate_upload(purpose, mime, data)
    boundary = 'wce-own-' + token_hex(16)
    if boundary.encode() in data:
        raise WCEError('OWN_MULTIPART_COLLISION')
    filename = ('cover' if purpose == 'permanent_cover' else 'body') + ('.png' if mime == 'image/png' else '.jpg')
    prefix = ('--' + boundary + '\r\nContent-Disposition: form-data; name="media"; filename="' + filename
              + '"\r\nContent-Type: ' + mime + '\r\n\r\n').encode('ascii')
    body = prefix + data + ('\r\n--' + boundary + '--\r\n').encode('ascii')
    headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary}
    if len(body) > MAX_BODY or upload.contains_secret((body, headers), secret):
        raise WCEError('OWN_INVALID_IMAGE')
    query = {'access_token': upload.secret_value(secret)}
    if purpose == 'permanent_cover':
        query['type'] = 'image'
    return HTTPRequest('POST', upload.ENDPOINTS[purpose] + '?' + urlencode(query), headers, body)


def render(article, mappings):
    tags, parts = {'paragraph': 'p', 'heading': 'h2', 'quote': 'blockquote'}, []
    for block in article['blocks']:
        if block['type'] in tags:
            tag = tags[block['type']]
            parts.append('<' + tag + '>' + escape(block['text'], quote=True).replace('\n', '<br>') + '</' + tag + '>')
        else:
            alt = escape(block['alt'], quote=True).replace('\n', '&#10;').replace('\t', '&#9;')
            parts.append('<img src="' + escape(mappings[block['slot']]['url'], quote=True) + '" alt="' + alt + '">')
    projected = {'title': article['title'], 'content': ''.join(parts),
                 'thumb_media_id': mappings['cover']['media_id']}
    if (len(projected['title']) > LIMITS['title_chars'] or not projected['content']
            or len(projected['content']) >= NEWS_CONTENT_CHAR_LIMIT
            or len(projected['content'].encode()) >= NEWS_CONTENT_BYTE_LIMIT):
        raise WCEError('OWN_CONSERVATIVE_NEWS_LIMIT')
    return projected


def encode_draft(kind, payload, secret):
    if kind not in {'add', 'get'} or upload.contains_secret(payload, secret):
        raise WCEError('OWN_INVALID_DRAFT_WIRE')
    body = canonical(payload).encode('utf-8')
    if kind == 'add':
        # Validate the actual serialized news fields, not a caller QA flag.
        import json
        validate_payload(json.loads(body))
    return HTTPRequest('POST', '/cgi-bin/draft/' + kind + '?' + urlencode({'access_token': upload.secret_value(secret)}),
                       {'Content-Type': 'application/json; charset=utf-8'}, body)


@dataclass(frozen=True)
class OwnReply:
    result: dict | None = None
    error_code: int | None = None
    credential_update_required: bool = False
    diagnostic: str = 'RESPONSE_UNDETERMINED'
    inspection: upload.ResponseInspection | None = None
    comment_observation: tuple | None = None


def parse(operation, response, secret, synthetic, reference=None):
    if operation in {'add', 'get'}:
        return parse_draft(operation, response, secret, synthetic, reference)
    try:
        if type(response) is not HTTPResponse:
            return OwnReply(diagnostic='TRANSPORT_UNDETERMINED')
        if type(response.status) is not int or not 200 <= response.status < 300:
            return OwnReply(diagnostic='NON_SUCCESS_HTTP')
        if upload.contains_secret(response.body, secret):
            return OwnReply(diagnostic='RESPONSE_SECRET_REFLECTION')
        value = decode_json(response.body)
        if type(value) is not dict or upload.contains_secret(value, secret) or type(value.get('errcode', 0)) is not int:
            return OwnReply(diagnostic='INVALID_JSON_SHAPE')
        code = value.get('errcode', 0)
        if code:
            return OwnReply(error_code=code, credential_update_required=code in TOKEN_INVALID_CODES)
        if operation in {'cover', 'body'}:
            purpose = 'permanent_cover' if operation == 'cover' else 'article_body'
            inspection = upload.inspect_response(purpose, response, secret, production=not synthetic)
            parsed, reason = inspection.reply, inspection.reason
            if parsed.classification != 'PARSED_SUCCESS':
                return OwnReply(diagnostic=reason, inspection=inspection)
            if not image_url(parsed.url, synthetic):
                return OwnReply(diagnostic='IMAGE_PRODUCTION_HOST_POLICY')
            if operation == 'cover' and not identifier(parsed.media_id, synthetic):
                return OwnReply(diagnostic='INVALID_MEDIA_IDENTIFIER')
            return OwnReply({'media_id': parsed.media_id, 'url': parsed.url} if operation == 'cover' else {'url': parsed.url}, inspection=inspection)
    except Exception:
        return OwnReply(diagnostic='INVALID_JSON_OR_RESPONSE')
    return OwnReply()


def parse_draft(operation, response, secret, synthetic, reference=None):
    from .own_draft_wire import response_value, reference_valid, reference_reason, project_news, observe_comments
    try:
        value = response_value(response, secret)
        code = value.get('errcode', 0)
        if code:
            return OwnReply(error_code=code, credential_update_required=code in TOKEN_INVALID_CODES)
        if operation == 'add':
            if not reference_valid(value.get('media_id'), synthetic):
                return OwnReply(diagnostic=reference_reason(value))
            return OwnReply({'reference': value['media_id']})
        if not reference_valid(reference, synthetic):
            return OwnReply(diagnostic='DRAFT_REQUEST_REFERENCE_POLICY')
        items = project_news(value, synthetic)
        if len(items) != 1 or items[0]['article_type'] != 'news':
            return OwnReply(diagnostic='DRAFT_SINGLE_NEWS_REQUIRED')
        return OwnReply({k: items[0][k] for k in ('title', 'content', 'thumb_media_id')},
                        comment_observation=observe_comments(value['news_item']))
    except WCEError as error:
        return OwnReply(diagnostic=error.code)
    except Exception:
        return OwnReply(diagnostic='INVALID_JSON_OR_RESPONSE')


def inspect_body_response(response, secret):
    return upload.inspect_response('article_body', response, secret,
        policy=upload.BODY_RESPONSE_POLICY, production=True)


def parse_group_get(response, secret, synthetic, reference, *, requested_cover_indices=()):
    """V2 ordered metadata projection. Preserve all legacy single-news parsers."""
    from .own_draft_wire import response_value, reference_valid, project_news, observe_comments
    from .documents import safe_url
    try:
        value = response_value(response, secret)
        code = value.get('errcode', 0)
        if code:
            return OwnReply(error_code=code, credential_update_required=code in TOKEN_INVALID_CODES)
        if not reference_valid(reference, synthetic):
            return OwnReply(diagnostic='DRAFT_REQUEST_REFERENCE_POLICY')
        rows = project_news(value, synthetic)
        if len(rows) > 8 or any(row['article_type'] != 'news' for row in rows):
            return OwnReply(diagnostic='DRAFT_NEWS_SHAPE')
        indices = frozenset(requested_cover_indices)
        if any(type(i) is not int or i < 0 or i >= len(rows) for i in indices):
            return OwnReply(diagnostic='DRAFT_CONTENT_POLICY')
        for index, (projected, raw) in enumerate(zip(rows, value['news_item'])):
            for key, limit in (('author', 16), ('digest', 120), ('content_source_url', 1024)):
                item = raw.get(key, '')
                if type(item) is not str or len(item) > limit or len(item.encode()) > limit * 4:
                    return OwnReply(diagnostic='DRAFT_CONTENT_POLICY')
                if key == 'content_source_url' and item:
                    safe_url(item)
                projected[key] = item
            if index in indices:
                from .editor_contracts import crop_info
                projected['cover_info'] = crop_info(raw.get('cover_info'))
        return OwnReply({'articles': rows},
                        comment_observation=observe_comments(value['news_item']))
    except WCEError as error:
        return OwnReply(diagnostic=error.code if error.code in (
            'RESPONSE_SECRET_REFLECTION', 'NON_SUCCESS_HTTP', 'TRANSPORT_UNDETERMINED',
            'DRAFT_INVALID_JSON', 'DRAFT_CODE_TYPE', 'DRAFT_NEWS_SHAPE', 'DRAFT_ARTICLE_TYPE',
            'DRAFT_TITLE_POLICY', 'DRAFT_CONTENT_POLICY', 'DRAFT_COVER_POLICY') else 'DRAFT_CONTENT_POLICY')
    except Exception:
        return OwnReply(diagnostic='INVALID_JSON_OR_RESPONSE')


def group_comparison(expected, actual):
    left = expected['articles']
    right = actual.get('articles', []) if isinstance(actual, dict) else []
    fields = ('title', 'content', 'thumb_media_id', 'author', 'digest', 'content_source_url', 'article_type')
    return {'policy': 'ORDERED_DOCUMENT_EXACT_V2', 'count_match': len(left) == len(right),
        'articles': [{'index': i, **{k: i < len(right) and row[k] == right[i].get(k)
                                   for k in fields + (('cover_info',) if 'cover_info' in row else ())}}
                     for i, row in enumerate(left)]}
