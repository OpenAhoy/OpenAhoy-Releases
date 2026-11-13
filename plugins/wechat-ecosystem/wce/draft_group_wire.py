"""GROUP08 NEWS codecs, with no sender, SQL, grant or authenticity claims.

A parsed response is syntax/content evidence only. The provider must separately
verify actual admitted HTTPS capture, subject, claim, source, freshness and scope.
Existing revision/single-news parsers and their evidence formats are unchanged.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from urllib.parse import urlencode

from .contracts import WCEError
from .http_transport import HTTPRequest, HTTPResponse, MAX_BODY
from .own_draft_wire import response_value, reference_valid
from .editor_contracts import crop_info
from . import upload_wire
from .html_technical_standard import LIMITS

PROFILE = 'GROUP_NEWS_FULL_PRESERVATION_V1'
ADD_PROFILE = 'MULTI_NEWS_DIGEST_EMPTY_KEEP_INTERNAL_V1'
REFERENCE_SHA_PROFILE = 'RAW_REF_UTF8_SHA256_V1'
PUBLIC_FIELDS = frozenset({'article_type','title','author','digest','content',
    'content_source_url','thumb_media_id','need_open_comment','only_fans_can_comment','cover_info'})
REQUIRED_PRESERVATION = PUBLIC_FIELDS - {'article_type','cover_info'}
READ_ONLY_FIELDS = frozenset({'url'})
HIDDEN_SETTINGS = ('originality','copyright','repost_permission','paid_content',
                   'automatic_comment_selection','backend_hidden_settings')


def fail(code='GROUP_WIRE_HOLD'):
    raise WCEError(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(value):
    return sha256(_utf8(canonical(value))).hexdigest()


def _utf8(value,code='GROUP_CONTENT_UNSUPPORTED'):
    if type(value) is not str:fail('GROUP_VALUE_TYPE_UNVERIFIED')
    try:return value.encode('utf-8')
    except UnicodeError:fail(code)


def _utf8_length(value):
    return len(_utf8(value))


def _reference(value,synthetic):
    if type(synthetic) is not bool:fail('GROUP_VALUE_TYPE_UNVERIFIED')
    if not reference_valid(value,synthetic):fail('GROUP_REFERENCE_UNVERIFIED')


def reference_sha(reference,*,synthetic=False):
    """Group reference-subject domain only; not canonical JSON evidence hashes."""
    _reference(reference,synthetic)
    return sha256(_utf8(reference)).hexdigest()


def _value(response,secret):
    if (type(response) is not HTTPResponse or type(response.body) is not bytes
            or len(response.body)>MAX_BODY):fail('GROUP_RESPONSE_UNDETERMINED')
    value=response_value(response,secret)
    code=value.get('errcode',0)
    if type(code) is not int or not -(2**31)<=code<2**31:fail('GROUP_CODE_UNSUPPORTED')
    return value,code,sha256(response.body).hexdigest()


def _exact_json(value):
    stack=[(value,0)];count=0
    while stack:
        item,depth=stack.pop();count+=1
        if count>4096 or depth>16:fail('GROUP_VALUE_TYPE_UNVERIFIED')
        kind=type(item)
        if kind is dict:
            if any(type(k) is not str for k in item):fail('GROUP_VALUE_TYPE_UNVERIFIED')
            stack.extend((v,depth+1) for v in item.values())
        elif kind is list:stack.extend((v,depth+1) for v in item)
        elif kind not in (str,int,float,bool,type(None)):fail('GROUP_VALUE_TYPE_UNVERIFIED')


def _row(row,synthetic,*,add=False):
    if type(row) is not dict or any(type(k) is not str for k in row):fail('GROUP_NEWS_SHAPE')
    kind=row.get('article_type','news')
    if type(kind) is not str or kind!='news':fail('GROUP_ARTICLE_TYPE_UNSUPPORTED')
    if not {'title','content','thumb_media_id'}<=set(row):fail('GROUP_PUBLIC_FIELD_UNVERIFIED')
    limits={'title':(LIMITS['title_chars'] if add else 128),'author':(LIMITS['author_chars'] if add else 64),
            'digest':(LIMITS['digest_chars'] if add else 480),'content_source_url':LIMITS['source_url_bytes']}
    for key,limit in limits.items():
        if key not in row:continue
        value=row[key]
        if (type(value) is not str or len(value)>limit or _utf8_length(value)>limit*4
                or key=='title' and not value):fail('GROUP_CONTENT_UNSUPPORTED')
    text=row['content']
    if (type(text) is not str or not text or len(text)>=LIMITS['content_chars_exclusive']
            or _utf8_length(text)>=LIMITS['content_bytes_exclusive']):fail('GROUP_CONTENT_UNSUPPORTED')
    _reference(row['thumb_media_id'],synthetic)
    for key in ('need_open_comment','only_fans_can_comment'):
        if key in row and (type(row[key]) is not int or row[key] not in (0,1)):
            fail('GROUP_COMMENT_UNVERIFIED')
    for key in ('content_source_url','url'):
        if key in row:
            if type(row[key]) is not str:fail('GROUP_CONTENT_UNSUPPORTED')
            if row[key]:
                _utf8(row[key])
                from .documents import safe_url
                safe_url(row[key])
    if 'cover_info' in row:
        _exact_json(row['cover_info']);crop_info(row['cover_info'])
    if add:
        if not REQUIRED_PRESERVATION<=set(row):fail('GROUP_PUBLIC_FIELD_UNVERIFIED')
        if set(row)-PUBLIC_FIELDS-READ_ONLY_FIELDS:fail('GROUP_UNMAPPED_FIELD_HOLD')
    return row


@dataclass(frozen=True,slots=True)
class GroupSnapshot:
    reference: str = field(repr=False)
    canonical_json: str = field(repr=False)
    response_sha256: str
    profile: str = PROFILE

    def value(self):
        # The constructor is public: always revalidate before using a value.
        if (type(self) is not GroupSnapshot or type(self.profile) is not str
                or self.profile!=PROFILE or type(self.canonical_json) is not str):fail('GROUP_SNAPSHOT_UNVERIFIED')
        from .publication_contract import strict_json
        value=strict_json(_utf8(self.canonical_json,'GROUP_SNAPSHOT_UNVERIFIED'),maximum=MAX_BODY)
        if type(value) is not dict or canonical(value)!=self.canonical_json:fail('GROUP_SNAPSHOT_UNVERIFIED')
        _reference(self.reference,True)
        if (type(self.response_sha256) is not str or len(self.response_sha256)!=64
                or any(c not in '0123456789abcdef' for c in self.response_sha256)):
            fail('GROUP_SNAPSHOT_UNVERIFIED')
        code=value.get('errcode',0)
        if type(code) is not int or code!=0:fail('GROUP_SNAPSHOT_UNVERIFIED')
        rows=value.get('news_item')
        if type(rows) is not list or not 1<=len(rows)<=8:fail('GROUP_NEWS_SHAPE')
        for row in rows:_row(row,True)
        return deepcopy(value)

    def rows(self):
        return self.value()['news_item']

    def evidence_sha256(self):
        return digest({'profile':self.profile,'reference':self.reference,'response':self.value()})


@dataclass(frozen=True,slots=True)
class InvalidReferenceObservation:
    reference: str = field(repr=False)
    response_sha256: str
    code: int = 40007
    classification: str = 'INVALID_REF_OBSERVED'
    platform_absence_proved: bool = False


@dataclass(frozen=True,slots=True)
class DeleteAckObservation:
    reference: str = field(repr=False)
    response_sha256: str
    code: int = 0
    classification: str = 'DELETE_ACK_PARSED'
    qualified_transport_verified: bool = False


@dataclass(frozen=True,slots=True)
class AddReferenceObservation:
    reference: str = field(repr=False)
    response_sha256: str
    qualified_transport_verified: bool = False


def parse_get(response,secret,reference,*,synthetic=False):
    _reference(reference,synthetic)
    value,code,response_sha=_value(response,secret)
    if code==40007:return InvalidReferenceObservation(reference,response_sha)
    if code:fail('GROUP_GET_REJECTED')
    rows=value.get('news_item')
    if type(rows) is not list or not 1<=len(rows)<=8:fail('GROUP_NEWS_SHAPE')
    for row in rows:_row(row,synthetic)
    encoded=canonical(value)
    if len(_utf8(encoded))>MAX_BODY:fail('GROUP_SNAPSHOT_BOUND')
    return GroupSnapshot(reference,encoded,response_sha)


def baseline_projection(snapshot,*,synthetic=False):
    if type(snapshot) is not GroupSnapshot:fail('GROUP_SNAPSHOT_UNVERIFIED')
    _reference(snapshot.reference,synthetic)
    value=snapshot.value();rows=value.get('news_item')
    if type(rows) is not list or not 1<=len(rows)<=8:fail('GROUP_NEWS_SHAPE')
    for row in rows:_row(row,synthetic)
    # Preserve every top-level and row extension/presence except temporary URLs.
    value['news_item']=[{k:deepcopy(v) for k,v in row.items() if k not in READ_ONLY_FIELDS} for row in rows]
    return {'profile':PROFILE,'reference':snapshot.reference,'response':value}


def settings_observation(snapshot):
    if type(snapshot) is not GroupSnapshot:fail('GROUP_SNAPSHOT_UNVERIFIED')
    rows=snapshot.rows()
    return {'profile':'NEWS_PUBLIC_FIELDS_ONLY_OBSERVATION_V1','authority':'NONE',
        'unmapped_envelope_field_names':sorted(set(snapshot.value())-{'news_item','errcode','errmsg'}),
        'articles':[{'index':i,'public_presence':{k:k in row for k in sorted(PUBLIC_FIELDS)},
                     'unmapped_field_names':sorted(set(row)-PUBLIC_FIELDS-READ_ONLY_FIELDS),
                     'hidden_settings':{k:'UNKNOWN' for k in HIDDEN_SETTINGS}}
                    for i,row in enumerate(rows)]}


@dataclass(frozen=True,slots=True)
class AddCandidate:
    payload_json: str = field(repr=False)
    original_digests_json: str = field(repr=False)
    profile: str = ADD_PROFILE
    authority: str = 'NONE_LOCAL_CANDIDATE'

    def payload(self):
        _add_candidate_fields(self)
        from .publication_contract import strict_json
        return strict_json(_utf8(self.payload_json,'GROUP_ADD_CANDIDATE_UNVERIFIED'),maximum=MAX_BODY)

    def original_digests(self):
        _add_candidate_fields(self)
        from .publication_contract import strict_json
        return strict_json(_utf8(self.original_digests_json,'GROUP_ADD_CANDIDATE_UNVERIFIED'),maximum=MAX_BODY)


def _add_candidate_fields(candidate):
    if (type(candidate) is not AddCandidate or type(candidate.profile) is not str
            or type(candidate.authority) is not str or type(candidate.payload_json) is not str
            or type(candidate.original_digests_json) is not str or candidate.profile!=ADD_PROFILE
            or candidate.authority!='NONE_LOCAL_CANDIDATE'):fail('GROUP_ADD_CANDIDATE_UNVERIFIED')


def rows_for_add(snapshot,*,synthetic=False):
    """Mandatory legacy-GET seam; do not lose unknown envelope extensions."""
    if type(snapshot) is not GroupSnapshot:fail('GROUP_SNAPSHOT_UNVERIFIED')
    baseline_projection(snapshot,synthetic=synthetic)
    value=snapshot.value()
    if set(value)-{'news_item','errcode','errmsg'}:fail('GROUP_UNMAPPED_FIELD_HOLD')
    for row in value['news_item']:_row(row,synthetic,add=True)
    return deepcopy(value['news_item'])


def make_add_candidate(rows,*,synthetic=False):
    if type(rows) not in (list,tuple) or not 1<=len(rows)<=8:fail('GROUP_NEWS_SHAPE')
    target=[];original=[]
    for index,row in enumerate(rows):
        _row(row,synthetic,add=True)
        original.append({'index':index,'digest':row['digest']})
        item={k:deepcopy(v) for k,v in row.items() if k in PUBLIC_FIELDS}
        item.setdefault('article_type','news')
        if len(rows)>1:item['digest']=''
        target.append(item)
    payload=canonical({'articles':target});internal=canonical(original)
    if len(_utf8(payload))>MAX_BODY:fail('GROUP_PAYLOAD_BOUND')
    return AddCandidate(payload,internal)


def _encode(kind,payload,secret):
    if upload_wire.contains_secret(payload,secret):fail('RESPONSE_SECRET_REFLECTION')
    body=_utf8(canonical(payload))
    if len(body)>MAX_BODY:fail('GROUP_PAYLOAD_BOUND')
    return HTTPRequest('POST','/cgi-bin/draft/'+kind+'?'+urlencode({
        'access_token':upload_wire.secret_value(secret)}),
        {'Content-Type':'application/json; charset=utf-8'},body)


def encode_add(candidate,secret,*,synthetic=False):
    _add_candidate_fields(candidate)
    value=candidate.payload()
    if type(value) is not dict or set(value)!={'articles'}:fail('GROUP_ADD_CANDIDATE_UNVERIFIED')
    checked=make_add_candidate(value['articles'],synthetic=synthetic)
    if checked.payload_json!=candidate.payload_json:fail('GROUP_ADD_CANDIDATE_UNVERIFIED')
    # Internal originals must be present/ordered, but never sent to Tencent.
    original=candidate.original_digests()
    if (type(original) is not list or len(original)!=len(value['articles'])
            or any(type(x) is not dict or set(x)!={'index','digest'} or type(x['index']) is not int
                   or x['index']!=i or type(x['digest']) is not str or len(x['digest'])>LIMITS['digest_chars']
                   for i,x in enumerate(original))):fail('GROUP_ADD_CANDIDATE_UNVERIFIED')
    if len(original)==1 and original[0]['digest']!=value['articles'][0]['digest']:fail('GROUP_ADD_CANDIDATE_UNVERIFIED')
    from .html_technical_standard import validate_payload
    validate_payload(value)
    return _encode('add',value,secret)


def encode_get(reference,secret,*,synthetic=False):
    _reference(reference,synthetic);return _encode('get',{'media_id':reference},secret)


def encode_delete(reference,secret,*,synthetic=False):
    _reference(reference,synthetic);return _encode('delete',{'media_id':reference},secret)


def parse_delete(response,secret,reference,*,synthetic=False):
    _reference(reference,synthetic);value,code,response_sha=_value(response,secret)
    if 'errcode' not in value:fail('GROUP_DELETE_EXPLICIT_CODE_REQUIRED')
    if code:fail('GROUP_DELETE_REJECTED')
    return DeleteAckObservation(reference,response_sha)


def parse_add(response,secret,*,synthetic=False):
    value,code,response_sha=_value(response,secret)
    if code:fail('GROUP_ADD_REJECTED')
    _reference(value.get('media_id'),synthetic)
    return AddReferenceObservation(value['media_id'],response_sha)
