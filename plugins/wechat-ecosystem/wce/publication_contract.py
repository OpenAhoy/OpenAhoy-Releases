"""Independent public-publication contract. No credential or network effects."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import unicodedata

from .contracts import WCEError
from .service import canonical, digest

POLICY = 'PUBLICATION_POLICY_V1'
ROUTE_POLICY = 'DEFAULT_FREEPUBLISH_WITH_HUMAN_EXPLICIT_MASS'
WIRE_PROFILE = 'WCE_OFFICIAL_PUBLICATION_DOC_WIRE_V1'
SNAPSHOT_PROFILE = 'BOUNDED_DRAFT_SNAPSHOT_V1'
QUALITY_PROFILE = 'PUBLICATION_QA_PROFILE_V2'
CONTENT_PROFILE = 'PUBLICATION_CONTENT_V2_BODY_IMAGES'
CONTRACT = {'policy': POLICY, 'route_policy': ROUTE_POLICY,
    'wire': WIRE_PROFILE, 'snapshot': SNAPSHOT_PROFILE, 'quality': QUALITY_PROFILE,
    'content': CONTENT_PROFILE, 'default_enabled': False,
    'automatic': 'FREEPUBLISH_WITHOUT_PUSH', 'mass': 'HUMAN_EXPLICIT_ONLY',
    'same_content_replay': False, 'backlog': False, 'platform_cas': False,
    'public_apis': ['freepublish.submit', 'freepublish.get'],
    'enablement': 'TRUSTED_HUMAN_SETTINGS_ONLY'}
CONTRACT_SHA = digest(CONTRACT)


def fail(code='PUBLICATION_STATE_UNVERIFIED'):
    raise WCEError(code)


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        fail()


def fingerprint(value):
    return sha256(canonical(value).encode('utf-8')).hexdigest()


def stable_account(data):
    appid = data.get('appid')
    if type(appid) is not str or not re.fullmatch(r'wx[a-fA-F0-9]{16}', appid):
        fail('PUBLICATION_ACCOUNT_UNVERIFIED')
    # The platform AppID is immutable; local aliases/authorization epochs are not.
    return digest({'provider': 'WECHAT_OFFICIAL_ACCOUNT', 'appid': appid.lower()})


def binding(data):
    required = {'actor', 'connection_id', 'appid', 'resource_id', 'generation',
                'epoch', 'private_directory'}
    if type(data) is not dict or set(data) != required:
        fail('PUBLICATION_BINDING_UNVERIFIED')
    if data['appid'] != data['resource_id']:
        fail('PUBLICATION_BINDING_UNVERIFIED')
    return digest(data)


def strict_json(raw, maximum=512 * 1024):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        fail()
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                fail()
            value[key] = item
        return value
    def bad(_):
        fail()
    try:
        value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                           parse_constant=bad)
        def visit(item, depth=0):
            if depth > 32:
                fail()
            if isinstance(item, dict):
                for child in item.values(): visit(child, depth + 1)
            elif isinstance(item, list):
                for child in item: visit(child, depth + 1)
        visit(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        fail()


def normalized_text(text):
    if type(text) is not str:
        fail('PUBLICATION_CONTENT_INVALID')
    return ' '.join(unicodedata.normalize('NFC', text).split())


def member_claims(members):
    """Exact complete-body/visual claims; a shared logo alone is not duplicate."""
    if type(members) is not list or not 1 <= len(members) <= 8:
        fail('PUBLICATION_CONTENT_INVALID')
    claims = set()
    for member in members:
        exact(member, 'id title text images')
        body = normalized_text(member['text'])
        images = member['images']
        if (type(images) is not list or any(type(h) is not str or
                not re.fullmatch('[a-f0-9]{64}', h) for h in images)):
            fail('PUBLICATION_CONTENT_INVALID')
        if not body and not images:
            fail('PUBLICATION_CONTENT_INVALID')
        if body:
            claims.add(('BODY', digest({'profile': CONTENT_PROFILE, 'text': body})))
        else:
            claims.add(('VISUAL', digest({'profile': CONTENT_PROFILE, 'images': sorted(images)})))
        claims.add(('MEMBER_FULL', digest({'profile': CONTENT_PROFILE,
            'text': body, 'images': images})))
    return sorted(claims)
