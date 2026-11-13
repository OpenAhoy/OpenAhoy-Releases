"""Reviewed, fixed three-source recognition previews; never upload inputs."""
import base64
from hashlib import sha256
import re

from .contracts import WCEError
from . import own_replacement_files as files

# Actual fixed output from the reviewed maintenance helper; no pixels in code.
# Missing or different private receipt keeps real-account recovery unavailable.
APPROVED_PREVIEW_RECEIPT_SHA = '39707742f95265082898046d1b89ac785e8031c5c2d247bbf34120ce47e85917'
HELPER_SHA = '6d0f5420fd2243d2e20311c208a6a40cb0368dedc882b6ed17475714bf8211d7'
RUNTIME_PINS_SHA = '30f7710a212050e3d80205a1d1fd491c240edb41ad44297eeb86e1ef98552a11'


def fail():
    raise WCEError('OWN_REPLACEMENT_PREVIEW_UNAVAILABLE')


def load(path, declared_sha):
    pins=(APPROVED_PREVIEW_RECEIPT_SHA,HELPER_SHA,RUNTIME_PINS_SHA)
    if any(type(pin) is not str or re.fullmatch('[a-f0-9]{64}',pin) is None for pin in pins):
        fail()
    receipt,actual_sha=files.read(path)
    if declared_sha!=APPROVED_PREVIEW_RECEIPT_SHA or actual_sha!=APPROVED_PREVIEW_RECEIPT_SHA:
        fail()
    if (type(receipt) is not dict
            or set(receipt)!={'schema','helper_sha256','runtime_pins_sha256','entries'}
            or receipt['schema']!='R1_PINNED_RGBA_PREVIEW_V1'
            or receipt['helper_sha256']!=HELPER_SHA or receipt['runtime_pins_sha256']!=RUNTIME_PINS_SHA
            or type(receipt['entries']) is not list or len(receipt['entries'])!=3):
        fail()
    seen=set()
    for entry in receipt['entries']:
        if (type(entry) is not dict or set(entry)!={'source_sha256','source_mime','source_bytes',
                'original_width','original_height','width','height','rgba','rgba_sha256'}):
            fail()
        if (type(entry['source_sha256']) is not str
                or re.fullmatch('[a-f0-9]{64}',entry['source_sha256']) is None
                or entry['source_sha256'] in seen or entry['source_mime'] not in ('image/jpeg','image/png')
                or type(entry['source_bytes']) is not int or not 0<entry['source_bytes']<1000000
                or any(type(entry[k]) is not int or not 1<=entry[k]<=4096
                       for k in ('original_width','original_height'))
                or entry['original_width']*entry['original_height']>4194304
                or any(type(entry[k]) is not int or not 1<=entry[k]<=320 for k in ('width','height'))
                or type(entry['rgba']) is not str or len(entry['rgba'])>546136):
            fail()
        try: raw=base64.b64decode(entry['rgba'],validate=True)
        except (ValueError,TypeError): fail()
        if (len(raw)!=entry['width']*entry['height']*4
                or base64.b64encode(raw).decode('ascii')!=entry['rgba']
                or sha256(raw).hexdigest()!=entry['rgba_sha256']):
            fail()
        seen.add(entry['source_sha256'])
    return receipt


def select(receipt,data,mime):
    """Rehash the actual immutable asset BLOB, rather than trusting a filename."""
    fingerprint=sha256(data).hexdigest()
    matches=[entry for entry in receipt['entries'] if entry['source_sha256']==fingerprint
             and entry['source_mime']==mime and entry['source_bytes']==len(data)]
    if len(matches)!=1: fail()
    entry=matches[0]
    return {k:entry[k] for k in ('width','height','rgba','original_width','original_height')}|{
        'rgba_sha':entry['rgba_sha256']}
