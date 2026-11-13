"""Pure, non-authoritative declarations for Operator-selected original inputs.

Decoding does not accept a request, inspect a file, validate account policy, or
issue source/Group authority. The real Operator must verify every declaration
against its own current policy and Owned history before issuing a witness.
This format deliberately has no Native-human, successful-upload, QA-PASS,
expiry, token, or runtime-seal fields.
"""
from hashlib import sha256
import json
import re

from .contracts import WCEError


SOURCE_TYPE = 'OPERATOR_ATTESTED_SELECTED_REQUEST_V1'
MANIFEST_PROFILE = 'OPERATOR_SELECTED_REQUEST_MANIFEST_V1'
ORIGINAL_QUEUE_SHA256 = '270cd453b7007a4fe0ad72c3d16feadd7a602f5441a614dc8295fa74ef104a21'
MAX_BYTES = 2 * 1024 * 1024
MAX_NODES = 65536
MAX_DEPTH = 20
MAX_INTEGER = 2**63 - 1
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_APPID = re.compile(r'wx[0-9a-fA-F]{16}\Z')
_CREDENTIAL_TEXT = re.compile(
    r'app[_-]?secret|(?:access|refresh)[_-]?token|'
    r'(?:[a-z0-9]+[_-])?api[_-]?key|client[_-]?secret|'
    r'password|authorization|cookie|session[_-]?key|private[_-]?key|'
    r'\bbearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----', re.I)
_ACCOUNT_KEYS = frozenset(('tenant', 'principal', 'client', 'session',
                          'connection', 'account', 'resource', 'epoch',
                          'generation', 'source_kind'))
_MANIFEST_KEYS = frozenset(('schema', 'profile', 'authority', 'qualification',
    'content_source_type', 'selection_kind', 'queue_sha256',
    'request_set_sha256', 'lineage_sha256', 'accounts', 'members',
    'reader_limits_sha256', 'double_pass_fence_sha256'))
_MEMBER_KEYS = frozenset(('ordinal', 'article_id', 'binding_sha256', 'selector',
    'prepare_request_key', 'import_receipt_sha256', 'historical_approval_sha256',
    'settings_sha256', 'html', 'body', 'images'))
_ARTIFACT_KEYS = frozenset(('root_sha256', 'relative_path', 'sha256', 'size',
                          'media_type', 'generation', 'physical_pin'))
_PIN_KEYS = frozenset(('dev', 'ino', 'mode', 'uid', 'gid', 'nlink',
                       'mtime_ns', 'ctime_ns'))


def _hold():
    # Never interpolate untrusted fields or article text into an error.
    raise WCEError('GROUP_SELECTED_SOURCE_DECLARATION_HOLD')


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _hold()


def _integer(value, low=0, high=MAX_INTEGER):
    if type(value) is not int or not low <= value <= high:
        _hold()


def _hash(value):
    if type(value) is not str or _HASH.fullmatch(value) is None:
        _hold()


def _id(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _hold()


def _plain(value):
    """Reject Python custom values and bound traversal before serializing."""
    stack = [(value, 0)]
    remaining = MAX_NODES
    while stack:
        item, depth = stack.pop()
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            _hold()
        kind = type(item)
        if kind is dict:
            if len(item) > 4096 or any(type(key) is not str for key in item):
                _hold()
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif kind is list:
            if len(item) > 4096:
                _hold()
            stack.extend((child, depth + 1) for child in item)
        elif kind is str:
            if len(item) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in item):
                _hold()
            # Control structures contain refs, never credentials or assistant
            # reflections of them. Reject the entire declaration; do not
            # rewrite a path or pretend that sanitizing it preserved identity.
            if _CREDENTIAL_TEXT.search(item) is not None:
                _hold()
            try:
                item.encode('utf-8')
            except UnicodeError:
                _hold()
        elif kind is int:
            _integer(item)
        elif kind not in (bool, type(None)):
            # This closed format has no floats, including finite floats.
            _hold()


def _canonical(value):
    _plain(value)
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        _hold()
    if not 0 < len(raw) <= MAX_BYTES:
        _hold()
    return raw


def _account(value):
    _closed(value, _ACCOUNT_KEYS)
    for key in ('tenant', 'principal', 'client', 'session', 'connection'):
        _id(value[key])
    if (type(value['account']) is not str
            or _APPID.fullmatch(value['account']) is None
            or value['resource'] != value['account']
            or value['source_kind'] != 'OPERATOR_ATTESTED'):
        _hold()
    _integer(value['epoch'])
    _integer(value['generation'], 1)


def _artifact(value, media_types):
    _closed(value, _ARTIFACT_KEYS)
    _hash(value['root_sha256'])
    _hash(value['sha256'])
    _integer(value['generation'], 1)
    if type(value['media_type']) is not str or value['media_type'] not in media_types:
        _hold()
    maximum = 4 * 1024 * 1024 if value['media_type'] == 'text/html' else (
        2 * 1024 * 1024 if value['media_type'] == 'text/markdown' else 1000000 - 1)
    _integer(value['size'], 1, maximum)
    path = value['relative_path']
    if type(path) is not str or not 0 < len(path) <= 4096 or ':' in path or '\\' in path:
        _hold()
    parts = path.split('/')
    if len(parts) > 32 or any(part in ('', '.', '..') for part in parts):
        _hold()
    pin = value['physical_pin']
    _closed(pin, _PIN_KEYS)
    for key in _PIN_KEYS:
        _integer(pin[key], 1 if key == 'ino' else 0)
    if pin['nlink'] != 1 or pin['mode'] not in (0o600, 0o644):
        _hold()


def _selector(value):
    _closed(value, frozenset(('bundle_id', 'version', 'content_digest')))
    _id(value['bundle_id'])
    _id(value['version'])
    _hash(value['content_digest'])


def _member(value, ordinal, account_hashes):
    _closed(value, _MEMBER_KEYS)
    _integer(value['ordinal'], 0, 27)
    if value['ordinal'] != ordinal:
        _hold()
    _id(value['article_id'])
    _hash(value['binding_sha256'])
    if value['binding_sha256'] not in account_hashes:
        _hold()
    _selector(value['selector'])
    _id(value['prepare_request_key'])
    for key in ('import_receipt_sha256', 'settings_sha256'):
        _hash(value[key])
    if value['historical_approval_sha256'] is not None:
        _hash(value['historical_approval_sha256'])
    _artifact(value['html'], frozenset(('text/html',)))
    _artifact(value['body'], frozenset(('text/markdown',)))
    images = value['images']
    if type(images) is not list or not 1 <= len(images) <= 33:
        _hold()
    slots, covers = set(), 0
    for image in images:
        _closed(image, frozenset(('slot', 'role', 'asset_ref', 'artifact')))
        _id(image['slot'])
        _id(image['asset_ref'])
        if image['slot'] in slots or type(image['role']) is not str or image['role'] not in ('cover', 'body'):
            _hold()
        slots.add(image['slot'])
        covers += image['role'] == 'cover'
        _artifact(image['artifact'], frozenset(('image/png', 'image/jpeg')))
    if covers != 1:
        _hold()


def member_projection(value):
    """Non-authoritative selection shape, suitable for exact caller comparison.

    Call only on a validated declaration. Matching this projection is data
    equality, never evidence that the expected values came from an Operator.
    """
    # Include selector, settings, input keys and physical declarations as well
    # as ordered image occurrences. Selecting only IDs/image hashes would let
    # a different prepared version pass an otherwise exact comparison.
    return tuple((member['article_id'], member['binding_sha256'],
                  sha256(_canonical(member)).hexdigest())
                 for member in value['members'])


def _expected_projection(value):
    if type(value) is not tuple or len(value) != 28:
        _hold()
    for item in value:
        if type(item) is not tuple or len(item) != 3:
            _hold()
        _id(item[0])
        _hash(item[1])
        _hash(item[2])


def encode_manifest(value, *, expected_member_projection):
    """Validate and detach a declaration. No witness is returned or registered."""
    _expected_projection(expected_member_projection)
    _plain(value)
    _closed(value, _MANIFEST_KEYS)
    if (type(value['schema']) is not int or value['schema'] != 1
            or value['profile'] != MANIFEST_PROFILE or value['authority'] is not False
            or value['qualification'] != 'NOT_ASSERTED'
            or value['content_source_type'] != SOURCE_TYPE
            or value['selection_kind'] != 'DELEGATED_AGENT_SELECTED_EXACT_ARTIFACTS'
            or value['queue_sha256'] != ORIGINAL_QUEUE_SHA256):
        _hold()
    for key in ('request_set_sha256', 'lineage_sha256',
                'reader_limits_sha256', 'double_pass_fence_sha256'):
        _hash(value[key])
    accounts = value['accounts']
    if type(accounts) is not list or len(accounts) != 2:
        _hold()
    for account in accounts:
        _account(account)
    account_hashes = tuple(sha256(_canonical(account)).hexdigest() for account in accounts)
    if (len(set(account_hashes)) != 2
            or len({account['account'] for account in accounts}) != 2
            or len({account['connection'] for account in accounts}) != 2
            or len({(account['tenant'], account['principal']) for account in accounts}) != 1):
        _hold()
    members = value['members']
    if type(members) is not list or len(members) != 28:
        _hold()
    for ordinal, member in enumerate(members):
        _member(member, ordinal, account_hashes)
    if (len({member['article_id'] for member in members}) != 28
            or [sum(m['binding_sha256'] == binding for m in members)
                for binding in account_hashes] != [12, 16]
            or sum(len(m['images']) for m in members) != 109
            or type(expected_member_projection) is not tuple
            or member_projection(value) != expected_member_projection):
        _hold()
    return _canonical(value)


def _pairs(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            _hold()
        value[key] = child
    return value


def decode_manifest(raw, *, expected_member_projection):
    """Strict UTF8 JSON to detached plain data, without issuing acceptance."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _hold()
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _hold())
    except (ValueError, UnicodeError, OverflowError, RecursionError):
        _hold()
    canonical = encode_manifest(value, expected_member_projection=expected_member_projection)
    if raw != canonical:
        _hold()
    # JSON has no caller-owned mutable aliases after this parse.
    return value, canonical, sha256(canonical).hexdigest()
