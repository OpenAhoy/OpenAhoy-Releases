"""Bounded deterministic PNG8 recognition preview for the one fixed original."""
from hashlib import sha256
from . import own_replacement_contract as contracts, own_replacement_files as files
from .contracts import WCEError


def render(data, mime, guard):
    fixed=contracts.B5_CONTRACT['asset']
    if (type(data) is not bytes or sha256(data).hexdigest()!=fixed['sha256']
            or len(data)!=fixed['size'] or mime!=fixed['declared_type']):
        raise WCEError('OWN_BODY5_PREVIEW_HOLD')
    from .own_replacement_batch import _preview
    return _preview(data,mime,guard,require_pinned=False)


def receipt(data,mime,guard):
    return {'schema':'B5_PINNED_PNG8_PREVIEW_V1','source_sha':contracts.B5_CONTRACT['asset']['sha256'],
        'preview':render(data,mime,guard)}


def load(path,declared):
    value,checksum=files.read(path)
    if (checksum!=declared or type(value) is not dict or set(value)!={'schema','source_sha','preview'}
            or value['schema']!='B5_PINNED_PNG8_PREVIEW_V1'
            or value['source_sha']!=contracts.B5_CONTRACT['asset']['sha256']):
        raise WCEError('OWN_BODY5_PREVIEW_HOLD')
    return value


def select(value,data,mime,guard):
    expected=receipt(data,mime,guard)
    if value!=expected: raise WCEError('OWN_BODY5_PREVIEW_HOLD')
    return expected['preview']
