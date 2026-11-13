"""Bounded draft-list syntax and two-pass evidence, without permissions.

The caller owns real read grants, claims, captures, freshness and persistence.
These values neither query an account nor establish account-wide coverage.
"""
from dataclasses import dataclass, field
from .contracts import WCEError
from . import draft_group_wire as wire

PAGE_SIZE = 20
MAX_OBJECTS = 200
MAX_PAGES = 10
PROFILE = 'GROUP_DRAFT_METADATA_LIST_TWO_PASSES_V1'


def fail(code='GROUP_DISCOVERY_HOLD'):
    raise WCEError(code)


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        fail('GROUP_DISCOVERY_BOUND')
    return value


def _offset(value):
    _integer(value, MAX_OBJECTS - PAGE_SIZE)
    if value % PAGE_SIZE:
        fail('GROUP_DISCOVERY_OFFSET')
    return value


def encode_list(offset, secret):
    """Fixed official metadata list; every object still needs a separate GET."""
    _offset(offset)
    return wire._encode('batchget', {'offset': offset, 'count': PAGE_SIZE, 'no_content': 1}, secret)


@dataclass(frozen=True, slots=True)
class ListPage:
    offset: int
    response_json: str = field(repr=False)
    response_sha256: str
    authority: str = 'NONE_LIST_SYNTAX'

    def value(self, *, synthetic=False):
        if (type(self.offset) is not int or type(self.response_json) is not str
                or type(self.response_sha256) is not str or type(self.authority) is not str
                or self.authority != 'NONE_LIST_SYNTAX'):
            fail()
        from .draft_group_contracts import sha, CandidateError
        from .publication_contract import strict_json
        try:
            sha(self.response_sha256)
        except CandidateError:
            fail('GROUP_DISCOVERY_HOLD')
        _offset(self.offset)
        raw = wire._utf8(self.response_json)
        if len(raw) > wire.MAX_BODY:
            fail('GROUP_DISCOVERY_BOUND')
        value = strict_json(raw, maximum=wire.MAX_BODY)
        _page_value(value, self.offset, synthetic=synthetic)
        if wire.canonical(value) != self.response_json:
            fail()
        return value


def _page_value(value, offset, *, synthetic):
    if type(synthetic) is not bool:
        fail('GROUP_VALUE_TYPE_UNVERIFIED')
    wire._exact_json(value)
    required = {'total_count', 'item_count', 'item'}
    if (type(value) is not dict or not required <= set(value)
            or set(value) - required - {'errcode', 'errmsg'}):
        fail('GROUP_DISCOVERY_SHAPE')
    code = value.get('errcode', 0)
    if type(code) is not int or code != 0:
        fail('GROUP_DISCOVERY_REJECTED')
    if 'errmsg' in value and type(value['errmsg']) is not str:
        fail('GROUP_DISCOVERY_SHAPE')
    total = _integer(value['total_count'], MAX_OBJECTS)
    count = _integer(value['item_count'], PAGE_SIZE)
    items = value['item']
    if type(items) is not list or len(items) != count:
        fail('GROUP_DISCOVERY_INCOMPLETE')
    if (total == 0 and offset != 0) or (total > 0 and offset >= total):
        fail('GROUP_DISCOVERY_OFFSET')
    if count != min(PAGE_SIZE, max(0, total - offset)):
        fail('GROUP_DISCOVERY_INCOMPLETE')
    references = []
    for item in items:
        if type(item) is not dict or not {'media_id', 'update_time'} <= set(item):
            fail('GROUP_DISCOVERY_SHAPE')
        wire._reference(item['media_id'], synthetic)
        _integer(item['update_time'], 2**63 - 1)
        # no_content=1 does not establish which same-named content level the
        # server omits. Keep every supplied extension/presence exactly, but
        # infer no body, article type, member count or eligibility from LIST.
        # ALL listed references require separately admitted full draft/get.
        references.append(item['media_id'])
    if len(set(references)) != len(references):
        fail('GROUP_DISCOVERY_DUPLICATE')
    return value


def parse_list(response, secret, offset, *, synthetic=False):
    _offset(offset)
    if (type(response) is not wire.HTTPResponse or type(response.body) is not bytes
            or len(response.body) > wire.MAX_BODY):
        fail('GROUP_RESPONSE_UNDETERMINED')
    from hashlib import sha256
    value = wire.response_value(response, secret, list_response=True)
    code = value.get('errcode', 0)
    if type(code) is not int or not -(2**31) <= code < 2**31:
        fail('GROUP_DISCOVERY_REJECTED')
    response_sha = sha256(response.body).hexdigest()
    if code:
        fail('GROUP_DISCOVERY_REJECTED')
    _page_value(value, offset, synthetic=synthetic)
    return ListPage(offset, wire.canonical(value), response_sha)


def _pass(pages, *, synthetic=False):
    if type(pages) is not tuple or not 1 <= len(pages) <= MAX_PAGES:
        fail('GROUP_DISCOVERY_INCOMPLETE')
    items = []
    total = None
    proof_shas = []
    for index, page in enumerate(pages):
        if type(page) is not ListPage:
            fail('GROUP_DISCOVERY_OFFSET')
        value = page.value(synthetic=synthetic)
        if page.offset != index * PAGE_SIZE:
            fail('GROUP_DISCOVERY_OFFSET')
        if total is None:
            total = value['total_count']
        elif total != value['total_count']:
            fail('GROUP_DISCOVERY_DRIFT')
        items.extend(value['item'])
        proof_shas.append(page.response_sha256)
    expected_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if len(pages) != expected_pages or len(items) != total:
        fail('GROUP_DISCOVERY_INCOMPLETE')
    refs = [item['media_id'] for item in items]
    if len(set(refs)) != len(refs):
        fail('GROUP_DISCOVERY_DUPLICATE')
    return {'total': total, 'items': items, 'response_shas': proof_shas}


def compare_passes(first, second, *, synthetic=False):
    """Private full observations; not a grant, snapshot or unconsumed proof.

    No article body is inferred from the metadata list. Each object still
    requires its own admitted full GET and current eligibility.
    Two equal scans do not make a platform-atomic snapshot.
    """
    left = _pass(first, synthetic=synthetic)
    right = _pass(second, synthetic=synthetic)
    if wire.canonical(left['items']) != wire.canonical(right['items']):
        fail('GROUP_DISCOVERY_DRIFT')
    references = tuple(item['media_id'] for item in left['items'])
    return {'profile': PROFILE, 'authority': 'NONE_TWO_LIST_OBSERVATIONS',
        'platform_atomic': False, 'eligibility': 'SEPARATE_GET_AND_CURRENT_CHECK_REQUIRED',
        'total': left['total'], 'references': references,
        'subject_shas': tuple(wire.reference_sha(r, synthetic=synthetic) for r in references),
        'items_sha': wire.digest(left['items']),
        'pass_response_shas': (tuple(left['response_shas']), tuple(right['response_shas'])),
        'list_used': len(first) + len(second), 'candidate_get_cap': len(references)}
