"""Official NEWS update protocol, separate from creation and declaration.

No endpoint selection, token acquisition, grant, sender or automatic retry lives
here. Presence-aware snapshots never manufacture absent optional values.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from urllib.parse import urlencode

from .contracts import WCEError
from .http_transport import HTTPRequest, MAX_BODY
from .own_draft_wire import response_value, reference_valid
from .service import canonical, digest
from . import upload_wire

PROFILE = 'OFFICIAL_NEWS_DRAFT_REVISION_V1'
WRITE_FIELDS = frozenset({'article_type', 'title', 'author', 'digest', 'content',
    'content_source_url', 'thumb_media_id', 'need_open_comment',
    'only_fans_can_comment', 'cover_info'})
# Missing values are not filled with the add/get codec's old default ''.
PRESERVATION_FIELDS = frozenset({'title', 'author', 'digest', 'content',
    'content_source_url', 'thumb_media_id', 'need_open_comment', 'only_fans_can_comment'})
CHANGE_FIELDS = frozenset({'title', 'content', 'digest'})
READ_ONLY_FIELDS = frozenset({'url'})  # Official draft/get temporary display link only.


def fail(code='DRAFT_REVISION_WIRE_HOLD'):
    raise WCEError(code)


@dataclass(frozen=True)
class RevisionSnapshot:
    """Immutable private response evidence; rows() returns detached values."""
    reference: str = field(repr=False)
    canonical_json: str = field(repr=False)
    response_sha: str
    profile: str = PROFILE

    def rows(self):
        from .publication_contract import strict_json
        return deepcopy(strict_json(self.canonical_json.encode(), maximum=MAX_BODY)['news_item'])

    def evidence_sha(self):
        return digest({'profile': self.profile, 'reference': self.reference,
                       'snapshot': self.canonical_json})


def _article(row, *, synthetic=False):
    if type(row) is not dict or not PRESERVATION_FIELDS <= set(row):
        fail('DRAFT_REVISION_PRESERVATION_FIELDS_MISSING')
    if row.get('article_type', 'news') != 'news':
        fail('DRAFT_REVISION_ARTICLE_TYPE_UNSUPPORTED')
    if not reference_valid(row['thumb_media_id'], synthetic):
        fail('DRAFT_REVISION_COVER_UNVERIFIED')
    # Reuse the existing accepted document input contract. These are local
    # bounded-input limits, not a claim about new Tencent update field limits.
    from .documents import ARTICLE
    for key, source_key, empty in (('title','title',False), ('author','author',True),
                                   ('digest','digest',True), ('content_source_url','source_url',True)):
        limit = ARTICLE['properties'][source_key]['maxLength']
        value = row[key]
        if (type(value) is not str or len(value) > limit or len(value.encode()) > limit * 4
                or (not empty and not value)):
            fail('DRAFT_REVISION_CONTENT_UNSUPPORTED')
    if 'url' in row:
        if type(row['url']) is not str:
            fail('DRAFT_REVISION_TEMPORARY_URL_TYPE')
        if row['url']:
            from .documents import safe_url
            safe_url(row['url'])
    if row['content_source_url']:
        from .documents import safe_url
        safe_url(row['content_source_url'])
    text = row['content']
    if (type(text) is not str or not text or len(text) >= 20000
            or len(text.encode()) >= 1000000):
        fail('DRAFT_REVISION_CONTENT_UNSUPPORTED')
    for key in ('need_open_comment', 'only_fans_can_comment'):
        if type(row[key]) is not int or row[key] not in (0, 1):
            fail('DRAFT_REVISION_COMMENT_UNVERIFIED')
    if 'cover_info' in row:
        from .editor_contracts import crop_info
        crop_info(row['cover_info'])
    # These complex writable profiles have no implementation in this NEWS case.
    if any(key in row for key in ('product_info', 'image_info')):
        fail('DRAFT_REVISION_COMPLEX_PROFILE_UNSUPPORTED')
    return row


def parse_get(response, secret, reference, *, synthetic=False):
    from hashlib import sha256
    value = response_value(response, secret)
    if 'errcode' in value and value['errcode'] != 0:
        fail('DRAFT_REVISION_GET_REJECTED')
    if not reference_valid(reference, synthetic):
        fail('DRAFT_REVISION_REFERENCE_UNVERIFIED')
    rows = value.get('news_item')
    if type(rows) is not list or not 1 <= len(rows) <= 8:
        fail('DRAFT_REVISION_NEWS_SHAPE')
    for row in rows:
        _article(row, synthetic=synthetic)
    # Preserve the entire reply, including presence and read-only extensions.
    # An executor must decide whether unknown meaningful fields permit updating;
    # this evidence alone never claims any optional value will be preserved.
    encoded = canonical(value)
    if len(encoded.encode()) > MAX_BODY:
        fail('DRAFT_REVISION_CANONICAL_SNAPSHOT_BOUND')
    return RevisionSnapshot(reference, encoded, sha256(response.body).hexdigest())


def baseline_projection(snapshot):
    """Compare content/presence; official temporary display URLs are evidence only."""
    if type(snapshot) is not RevisionSnapshot or snapshot.profile != PROFILE:
        fail('DRAFT_REVISION_SNAPSHOT_UNVERIFIED')
    from .publication_contract import strict_json
    value = deepcopy(strict_json(snapshot.canonical_json.encode(), maximum=MAX_BODY))
    # All top-level data and all other presence/value pairs stay in comparison.
    value['news_item'] = [{key:deepcopy(item) for key,item in row.items() if key != 'url'}
                          for row in snapshot.rows()]
    return {'profile':PROFILE,'reference':snapshot.reference,'response':value}


def update_payload(snapshot, changes, *, index=0, synthetic=False):
    if type(snapshot) is not RevisionSnapshot or snapshot.profile != PROFILE:
        fail('DRAFT_REVISION_SNAPSHOT_UNVERIFIED')
    from .publication_contract import strict_json
    envelope = strict_json(snapshot.canonical_json.encode(), maximum=MAX_BODY)
    if set(envelope) - {'news_item','errcode','errmsg'}:
        fail('DRAFT_REVISION_UNMAPPED_FIELD_UNVERIFIED')
    rows = snapshot.rows()
    if type(index) is not int or index != 0 or len(rows) != 1:
        fail('DRAFT_REVISION_EXACT_SINGLE_CASE_REQUIRED')
    if type(changes) is not dict or not changes or not set(changes) <= CHANGE_FIELDS:
        fail('DRAFT_REVISION_DIFF_OUTSIDE_CASE')
    original = _article(rows[index], synthetic=synthetic)
    if set(original) - WRITE_FIELDS - READ_ONLY_FIELDS:
        fail('DRAFT_REVISION_UNMAPPED_FIELD_UNVERIFIED')
    target = {key: deepcopy(value) for key, value in original.items() if key in WRITE_FIELDS}
    target.setdefault('article_type', 'news')  # Documented NEWS default, never a missing metadata value.
    target.update(deepcopy(changes))
    _article(target, synthetic=synthetic)
    return {'media_id': snapshot.reference, 'index': index, 'articles': target}


def encode_update(payload, secret, *, synthetic=False):
    if type(payload) is not dict or set(payload) != {'media_id', 'index', 'articles'}:
        fail()
    if (not reference_valid(payload['media_id'], synthetic) or type(payload['index']) is not int
            or payload['index'] != 0 or type(payload['articles']) is not dict
            or not set(payload['articles']) <= WRITE_FIELDS):
        fail()
    _article(payload['articles'], synthetic=synthetic)
    if upload_wire.contains_secret(payload, secret):
        fail('RESPONSE_SECRET_REFLECTION')
    return HTTPRequest('POST', '/cgi-bin/draft/update?' + urlencode({
        'access_token': upload_wire.secret_value(secret)}),
        {'Content-Type': 'application/json; charset=utf-8'}, canonical(payload).encode())


def parse_update(response, secret):
    value = response_value(response, secret)
    # get/add historically accepted missing errcode; UPDATE success must be
    # explicit. bool is not int here or in response_value's strict check.
    if 'errcode' not in value or type(value['errcode']) is not int:
        fail('DRAFT_REVISION_EXPLICIT_CODE_REQUIRED')
    code = value['errcode']
    if not -(2**31) <= code < 2**31:
        fail('DRAFT_REVISION_CODE_UNSUPPORTED')
    return {'response_state': 'SUCCEEDED_RESPONSE' if code == 0 else 'REJECTED_RESPONSE',
            'errcode': code, 'platform_effect': 'UNVERIFIED', 'originality': 'UNVERIFIED'}
