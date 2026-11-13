"""Bounded editorial metadata. These values confer no publishing or copyright authority."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache

from .contracts import WCEError
from .prepared_contracts import strict_validate
from .tools import schema

COORDINATE = {'type': 'string', 'pattern': r'^(?:0(?:\.[0-9]{1,12})?|1(?:\.0{1,12})?)$'}
CROP = schema({'ratio': {'type': 'string', 'enum': ['2.35_1', '1_1']},
               **{key: COORDINATE for key in ('x1', 'y1', 'x2', 'y2')}})
COVER_INFO = schema({'crop_percent_list': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': CROP}})
DIMENSIONS = schema({key: {'type': 'integer', 'minimum': 1, 'maximum': 4096}
                     for key in ('width', 'height')})
INTENT = schema({'summary': {'type': 'string', 'enum': ['manual_required', 'custom']},
                 'originality': {'type': 'string', 'enum': ['review_required', 'not_requested']}})


def fail():
    raise WCEError('DOCUMENT_EDITORIAL_METADATA')


def crop_info(value, dimensions=None):
    strict_validate(value, COVER_INFO)
    ratios = set()
    for row in value['crop_percent_list']:
        if row['ratio'] in ratios:
            fail()
        ratios.add(row['ratio'])
        try:
            x1, y1, x2, y2 = (Decimal(row[key]) for key in ('x1', 'y1', 'x2', 'y2'))
        except InvalidOperation:
            fail()
        if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
            fail()
        if dimensions is not None:
            width = (x2 - x1) * dimensions['width']
            height = (y2 - y1) * dimensions['height']
            ratio = Decimal('2.35') if row['ratio'] == '2.35_1' else Decimal(1)
            if width < 1 or height < 1 or abs(width - height * ratio) > 1:
                fail()
    return value


def validate(article):
    if ('cover_info' in article) != ('cover_dimensions' in article):
        fail()
    if 'cover_info' in article:
        dimensions = article['cover_dimensions']
        strict_validate(dimensions, DIMENSIONS)
        if dimensions['width'] * dimensions['height'] > 4194304:
            fail()
        crop_info(article['cover_info'], dimensions)
    intent = article.get('editorial_intent')
    if intent is not None:
        strict_validate(intent, INTENT)
        if (intent['summary'] == 'custom') != bool(article.get('digest')):
            fail()


def left_square(width, height):
    dimensions = {'width': width, 'height': height}
    strict_validate(dimensions, DIMENSIONS)
    if width * 100 != height * 235 or width * height > 4194304:
        fail()
    right = format((Decimal(height) / Decimal(width)).quantize(
        Decimal('.000000000001'), rounding=ROUND_HALF_UP), 'f').rstrip('0').rstrip('.')
    value = {'crop_percent_list': [
        {'ratio': '2.35_1', 'x1': '0', 'y1': '0', 'x2': '1', 'y2': '1'},
        {'ratio': '1_1', 'x1': '0', 'y1': '0', 'x2': right, 'y2': '1'}]}
    crop_info(value, dimensions)
    return {'cover_info': value, 'cover_dimensions': dimensions}


@lru_cache(maxsize=64)
def encoded_dimensions(data, mime):
    """Bounded PNG validation or strict JPEG geometry; cache only immutable bytes.

    Sixty-four exact inputs bound retained bytes to 128MiB. No cache entry is an
    identity or permission: callers still verify current assets and authority.
    JPEG scan geometry is not a claim about decoded pixels/mobile rendering.
    """
    if mime == 'image/png':
        from .own_png import decode_png
        raster = decode_png(data)
        width, height = raster.width, raster.height
    elif mime == 'image/jpeg':
        from .import_images import jpeg
        (width, height), _ = jpeg(data, True)
    else:
        fail()
    strict_validate({'width': width, 'height': height}, DIMENSIONS)
    return width, height


def verify_cover(article, data, mime):
    if 'cover_info' in article and encoded_dimensions(data, mime) != (article['cover_dimensions']['width'], article['cover_dimensions']['height']):
        raise WCEError('DOCUMENT_COVER_DIMENSIONS_MISMATCH')


def checks(document, actual=None):
    rows = []
    actual_rows = actual.get('articles', []) if type(actual) is dict else []
    for index, article in enumerate(document['articles']):
        intent = article.get('editorial_intent')
        if intent is None:
            continue
        returned = actual_rows[index] if index < len(actual_rows) else None
        summary = ('PENDING_PLATFORM_VALUE' if returned is None else
                   'PLATFORM_EMPTY_CONFIRMED' if not returned.get('digest') else
                   'PENDING_SEPARATE_EDIT_PLATFORM_FILLED_TEXT')
        if intent['summary'] == 'custom':
            summary = 'CUSTOM_NOT_READ_BACK' if returned is None else (
                'CUSTOM_MATCHED' if returned.get('digest') == article.get('digest') else 'CUSTOM_MISMATCH')
        rows.append({'index': index, 'author': article.get('author', ''), 'summary': summary,
                     'originality': ('NOT_SUBMITTED_NO_SUPPORTED_OFFICIAL_PATH'
                         if intent['originality'] == 'review_required' else 'NOT_REQUESTED')})
    return rows


def geometry(expected, actual, dimensions):
    """Separate one-pixel geometry diagnostic; never changes exact readback state."""
    try:
        crop_info(expected, dimensions)
        crop_info(actual)
        other = {row['ratio']: row for row in actual['crop_percent_list']}
        return all(abs(Decimal(row[key]) - Decimal(other[row['ratio']][key])) *
                   dimensions['width' if key.startswith('x') else 'height'] <= 1
                   for row in expected['crop_percent_list'] for key in ('x1', 'y1', 'x2', 'y2'))
    except (WCEError, KeyError, TypeError, InvalidOperation):
        return False
