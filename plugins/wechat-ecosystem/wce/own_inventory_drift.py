"""Pure, bounded inventory-change counters; never equality, authority or I/O.

Fingerprint objects stay inside the request. Only compare's closed counts may
be released after the caller's original authorization guards. Any helper error
must leave the caller's original CHANGED/UNKNOWN result intact.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

MAX_RECORDS = 1000
MAX_ARTICLES = 10
MAX_NODES = 16384
MAX_DEPTH = 64
MAX_ITEM_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 65536
TYPES = ('missing', 'null', 'boolean', 'integer', 'number', 'string', 'array', 'object')
ROOT_FIELDS = ('news_item', 'create_time', 'update_time')
NEWS_FIELDS = ('article_type', 'title', 'content', 'thumb_media_id', 'author', 'digest',
    'content_source_url', 'need_open_comment', 'only_fans_can_comment', 'cover_info',
    'url', 'thumb_url', 'show_cover_pic')
POLICY = 'ORDINARY_INVENTORY_DRIFT_COUNTS_V1'

class InventoryDiagnosticUnavailable(ValueError):
    def __init__(self): super().__init__('INVENTORY_DIAGNOSTIC_UNAVAILABLE')

def _need(value):
    if value is not True: raise InventoryDiagnosticUnavailable()

def _kind(value):
    return {type(None): 'null', bool: 'boolean', int: 'integer', float: 'number',
        str: 'string', list: 'array', dict: 'object'}.get(type(value))

def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')

def _sha(value): return sha256(_canonical(value)).digest()

def _bounded_json(value):
    pending = [(value, 0)]; nodes = 0
    while pending:
        current, depth = pending.pop(); nodes += 1
        _need(nodes <= MAX_NODES and depth <= MAX_DEPTH and _kind(current) is not None)
        if type(current) is float: _need(math.isfinite(current))
        if type(current) is str: _need(len(current) <= MAX_ITEM_BYTES)
        if type(current) is dict:
            _need(nodes + len(pending) + 2 * len(current) <= MAX_NODES)
            _need(all(type(key) is str for key in current))
            for key, child in current.items():
                pending.append((key, depth + 1)); pending.append((child, depth + 1))
        elif type(current) is list:
            _need(nodes + len(pending) + len(current) <= MAX_NODES)
            pending.extend((child, depth + 1) for child in current)
    _need(len(_canonical(value)) <= MAX_ITEM_BYTES)

@dataclass(frozen=True, slots=True)
class _Field:
    present: bool
    kind: str
    value_sha256: bytes | None

@dataclass(frozen=True, slots=True)
class _Unknown:
    count: int
    keys_sha256: bytes
    value_sha256: bytes
    types: tuple

@dataclass(frozen=True, slots=True)
class _Article:
    kind: str
    value_sha256: bytes
    fields: tuple
    unknown: _Unknown

@dataclass(frozen=True, slots=True)
class InventoryFingerprint:
    content_sha256: bytes
    root_fields: tuple
    root_unknown: _Unknown
    articles: tuple

_MISSING = _Field(False, 'missing', None)

def _fields(value, allowlist):
    return tuple(_Field(True, _kind(value[key]), _sha(value[key]))
        if type(value) is dict and key in value else _MISSING for key in allowlist)

def _unknown(value, allowlist):
    extras = {key: child for key, child in value.items() if key not in allowlist} if type(value) is dict else {}
    counts = tuple(sum(_kind(child) == kind for child in extras.values()) for kind in TYPES)
    return _Unknown(len(extras), _sha(sorted(extras)), _sha(extras), counts)

def fingerprint_inventory_item(content):
    """Return only fixed presence/type/32-byte digests, never raw field data."""
    try:
        _need(type(content) is dict); _bounded_json(content)
        items = content.get('news_item')
        if type(items) is list: _need(len(items) <= MAX_ARTICLES)
        else: items = []
        return InventoryFingerprint(_sha(content), _fields(content, ROOT_FIELDS),
            _unknown(content, ROOT_FIELDS), tuple(_Article(_kind(item), _sha(item),
                _fields(item, NEWS_FIELDS), _unknown(item, NEWS_FIELDS)) for item in items))
    except Exception:
        raise InventoryDiagnosticUnavailable() from None

def _digest(value): return type(value) is bytes and len(value) == 32

def _validate_field(value):
    _need(type(value) is _Field and type(value.present) is bool and value.kind in TYPES)
    _need((_digest(value.value_sha256) and value.kind != 'missing') if value.present
          else value.kind == 'missing' and value.value_sha256 is None)

def _validate_unknown(value):
    _need(type(value) is _Unknown and type(value.count) is int and 0 <= value.count <= MAX_NODES
        and _digest(value.keys_sha256) and _digest(value.value_sha256)
        and type(value.types) is tuple and len(value.types) == len(TYPES)
        and all(type(n) is int and 0 <= n <= MAX_NODES for n in value.types)
        and sum(value.types) == value.count and value.types[0] == 0)

def _validate_fingerprint(value):
    _need(type(value) is InventoryFingerprint and _digest(value.content_sha256)
        and type(value.root_fields) is tuple and len(value.root_fields) == len(ROOT_FIELDS)
        and type(value.articles) is tuple and len(value.articles) <= MAX_ARTICLES)
    for field in value.root_fields: _validate_field(field)
    _validate_unknown(value.root_unknown)
    for article in value.articles:
        _need(type(article) is _Article and article.kind in TYPES[1:]
            and _digest(article.value_sha256) and type(article.fields) is tuple
            and len(article.fields) == len(NEWS_FIELDS))
        for field in article.fields: _validate_field(field)
        _validate_unknown(article.unknown)
    _need(value.root_unknown.count + sum(a.unknown.count for a in value.articles) <= MAX_NODES)

def _ref(value):
    return type(value) is str and 0 < len(value) <= 128 and len(value.encode('utf-8')) <= 512

def _snapshots(records, sidecars):
    _need(type(records) is dict and type(sidecars) is dict and len(records) <= MAX_RECORDS
        and set(records) == set(sidecars))
    for ref, row in records.items():
        _need(_ref(ref) and type(row) is dict and set(row) == {'update_time', 'content_sha256'}
            and type(row['update_time']) is int and row['update_time'] >= 0
            and type(row['content_sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['content_sha256']) is not None)
        fp = sidecars[ref]; _validate_fingerprint(fp)
        _need(fp.content_sha256.hex() == row['content_sha256'])

def _type_counts(): return dict.fromkeys(TYPES, 0)

def _field_counts():
    return {'changed': 0, 'presence_changed': 0, 'type_changed': 0,
        'types_before': _type_counts(), 'types_after': _type_counts()}

def _unknown_counts():
    return {'fields_first': 0, 'fields_second': 0, 'keyset_changed': 0, 'values_changed': 0,
        'types_first': _type_counts(), 'types_second': _type_counts()}

def _bucket():
    return {'first_records': 0, 'second_records': 0, 'common_records': 0,
        'added_records': 0, 'removed_records': 0, 'update_time_changed_records': 0,
        'content_changed_records': 0, 'article_count_changed_records': 0,
        'article_positions_changed': 0, 'article_position_type_changed': 0,
        'content_fields': {key: _field_counts() for key in ROOT_FIELDS},
        'news_fields': {key: _field_counts() for key in NEWS_FIELDS},
        'content_unknown': _unknown_counts(), 'news_unknown': _unknown_counts()}

def _field_delta(out, before, after):
    if before == after: return
    out['changed'] += 1
    out['presence_changed'] += before.present != after.present
    out['type_changed'] += before.kind != after.kind
    out['types_before'][before.kind] += 1; out['types_after'][after.kind] += 1

def _unknown_totals(out, value, suffix):
    out['fields_' + suffix] += value.count
    for kind, count in zip(TYPES, value.types): out['types_' + suffix][kind] += count

def _unknown_delta(out, before, after):
    out['keyset_changed'] += before.keys_sha256 != after.keys_sha256
    out['values_changed'] += before.value_sha256 != after.value_sha256

_EMPTY_UNKNOWN = _unknown({}, ())

def _compare(first_records, second_records, first_sidecars, second_sidecars, provisional_target_refs):
    _snapshots(first_records, first_sidecars); _snapshots(second_records, second_sidecars)
    _need(type(provisional_target_refs) in (list, tuple, set, frozenset)
        and len(provisional_target_refs) <= 4 and all(_ref(ref) for ref in provisional_target_refs))
    refs = set(provisional_target_refs); _need(len(refs) == len(provisional_target_refs))
    target = next(iter(refs)) if len(refs) == 1 and next(iter(refs)) in first_records else None
    result = {'schema': 1, 'policy': POLICY,
        'target_basis': 'UNIQUE_COMPLETED_CANDIDATE_GET' if target is not None else 'NONE',
        'inventory': {'first_total': len(first_records), 'second_total': len(second_records),
            'common': len(first_records.keys() & second_records.keys()),
            'added': len(second_records.keys() - first_records.keys()),
            'removed': len(first_records.keys() - second_records.keys())},
        'target': _bucket(), 'non_target': _bucket()}
    for ref in first_records.keys() | second_records.keys():
        out = result['target' if ref == target else 'non_target']
        a, b = first_records.get(ref), second_records.get(ref)
        fa, fb = first_sidecars.get(ref), second_sidecars.get(ref)
        for fp, suffix in ((fa, 'first'), (fb, 'second')):
            if fp is not None:
                out[suffix + '_records'] += 1
                _unknown_totals(out['content_unknown'], fp.root_unknown, suffix)
                for article in fp.articles: _unknown_totals(out['news_unknown'], article.unknown, suffix)
        if a is None: out['added_records'] += 1; continue
        if b is None: out['removed_records'] += 1; continue
        out['common_records'] += 1
        out['update_time_changed_records'] += a['update_time'] != b['update_time']
        out['content_changed_records'] += a['content_sha256'] != b['content_sha256']
        for key, left, right in zip(ROOT_FIELDS, fa.root_fields, fb.root_fields):
            _field_delta(out['content_fields'][key], left, right)
        _unknown_delta(out['content_unknown'], fa.root_unknown, fb.root_unknown)
        out['article_count_changed_records'] += len(fa.articles) != len(fb.articles)
        for index in range(max(len(fa.articles), len(fb.articles))):
            left = fa.articles[index] if index < len(fa.articles) else None
            right = fb.articles[index] if index < len(fb.articles) else None
            out['article_positions_changed'] += left is None or right is None or left.value_sha256 != right.value_sha256
            out['article_position_type_changed'] += (left.kind if left else 'missing') != (right.kind if right else 'missing')
            for key, x, y in zip(NEWS_FIELDS, left.fields if left else (_MISSING,) * len(NEWS_FIELDS),
                                 right.fields if right else (_MISSING,) * len(NEWS_FIELDS)):
                _field_delta(out['news_fields'][key], x, y)
            _unknown_delta(out['news_unknown'], left.unknown if left else _EMPTY_UNKNOWN,
                           right.unknown if right else _EMPTY_UNKNOWN)
    _need(len(_canonical(result)) <= MAX_OUTPUT_BYTES)
    return result

def compare_inventory_snapshots(first_records, second_records, first_sidecars,
                                second_sidecars, provisional_target_refs):
    """Closed counters only. Caller retains its unchanged records equality gate."""
    try:
        return _compare(first_records, second_records, first_sidecars, second_sidecars,
                        provisional_target_refs)
    except Exception:
        raise InventoryDiagnosticUnavailable() from None
