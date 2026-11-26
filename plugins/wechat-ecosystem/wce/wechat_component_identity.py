"""Public display fields returned for a verified WeChat authorizer."""
from urllib.parse import urlsplit


AVATAR_HOSTS = frozenset({
    'wx.qlogo.cn', 'thirdwx.qlogo.cn', 'mmbiz.qpic.cn', 'mmbiz.qlogo.cn',
})


def _text(value, limit):
    if not isinstance(value, str) or len(value) > limit:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value.strip() or None


def _avatar(value):
    value = _text(value, 2048)
    if not value or any(c in value for c in ('\\', '?', '#')) or any(c.isspace() for c in value):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme != 'https' or parts.netloc not in AVATAR_HOSTS or parts.path in ('', '/'):
        return None
    return value


def clean_authorizer_info(raw):
    if not isinstance(raw, dict):
        return None
    instant = raw.get('verifiedAt')
    if type(instant) is not int or not 0 < instant <= 253402300799:
        return None
    category = raw.get('serviceTypeId')
    verification = raw.get('verifyTypeId')
    return {
        'nickname': _text(raw.get('nickname'), 128),
        'avatarUrl': _avatar(raw.get('avatarUrl')),
        'alias': _text(raw.get('alias'), 128),
        'serviceTypeId': category if type(category) is int and category in (0, 1, 2) else None,
        'verifyTypeId': verification if type(verification) is int and -1 <= verification < 2**31 else None,
        'verifiedAt': instant,
    }


def official_profile_fields(info):
    info = clean_authorizer_info(info)
    if info is None:
        return {}
    return {
        'nickname': info['nickname'], 'avatar_url': info['avatarUrl'],
        'alias': info['alias'], 'account_type': info['serviceTypeId'],
        'verification': info['verifyTypeId'], 'service_type_id': info['serviceTypeId'],
        'verify_type_id': info['verifyTypeId'], 'identity_verified_at': info['verifiedAt'],
        'use_official': bool(info['nickname']),
    }
