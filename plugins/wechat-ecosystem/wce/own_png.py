"""Bounded PNG8 subset for an explicitly approved exact RGBA comparison.

This is not a general PNG renderer or C2PA verifier. It rejects color,
orientation, palette, animation and unknown chunks. Only opaque text and caBX
metadata may differ; input files are never modified.
"""
from dataclasses import dataclass
import re
import struct
import zlib

from .contracts import WCEError
from .local_preparation import sha
from .prepared_contracts import strict_validate, ID

POLICY_ID = 'PNG8_RGBA_EXACT_V1'
ORIGIN = 'OFFICIAL_PIXEL_READ_MATCH'
MAX_INPUT = 2097152
MAX_SIDE = 4096
MAX_PIXELS = 4194304
MAX_RGBA = 16777216
MAX_FILTERED = MAX_RGBA + MAX_SIDE
MAX_CHUNKS = 256
IGNORED = (b'tEXt', b'zTXt', b'iTXt', b'caBX')
SIGNATURE = b'\x89PNG\r\n\x1a\n'


def policy():
    return {'id': POLICY_ID, 'decoder': 'WCE_PNG8_SUBSET_V1',
        'max_input_bytes': MAX_INPUT, 'max_side': MAX_SIDE, 'max_pixels': MAX_PIXELS,
        'max_rgba_bytes': MAX_RGBA, 'max_filtered_bytes': MAX_FILTERED,
        'max_chunks': MAX_CHUNKS, 'color_types': [2, 6], 'bit_depth': 8,
        'interlace': 0, 'comparison': 'DIMENSIONS_AND_ALL_UNPREMULTIPLIED_RGBA8_BYTES',
        'ignored_metadata': ['tEXt', 'zTXt', 'iTXt', 'caBX'],
        'c2pa_verified': False, 'final_remote_raw_equal': True}


def recovery_binding(row, intent):
    return {'policy': policy(), 'request_key': row['request_key'],
        'original_attempt_id': row['id'], 'original_intent_digest': row['intent_digest'],
        'asset_sha256': intent['asset']['sha256'], 'asset_size': intent['asset']['size']}


def validate_binding(value):
    try:
        if type(value) is not dict or set(value) != {'policy', 'request_key', 'original_attempt_id',
                'original_intent_digest', 'asset_sha256', 'asset_size'}:
            raise ValueError()
        # Canonical types are significant: bool is not an integer budget.
        from .own_workflow import encoded
        if encoded(value['policy']) != encoded(policy()):
            raise ValueError()
        for key in ('request_key', 'original_attempt_id'):
            strict_validate(value[key], ID)
        for key in ('original_intent_digest', 'asset_sha256'):
            if type(value[key]) is not str or re.fullmatch('[a-f0-9]{64}', value[key]) is None:
                raise ValueError()
        if type(value['asset_size']) is not int or not 0 < value['asset_size'] <= MAX_INPUT:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise WCEError('OWN_STATE_CORRUPT') from None
    return value


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    rgba: bytes

    def fingerprint(self):
        return {'width': self.width, 'height': self.height, 'rgba_sha256': sha(self.rgba)}


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def decode_png(data, guard=lambda: None):
    """Finite input/output budgets plus cooperative guards; no native worker.

    Filtered/RGBA buffers, the transient immutable RGBA copy, compressed input
    and row buffers are each bounded independently of compression ratio. An
    earlier comparison raster can remain in the caller. Ignored metadata is never
    decompressed. Native zlib has a positive output cap; no unbounded flush.
    """
    def fail():
        raise WCEError('OWN_RECONCILE_PNG_UNSUPPORTED')
    guard()
    if type(data) is not bytes or not 0 < len(data) <= MAX_INPUT or not data.startswith(SIGNATURE):
        fail()
    pos, chunks, ihdr, ended, idat_state = 8, 0, None, False, 0
    compressed = bytearray()
    while pos < len(data):
        guard()
        chunks += 1
        if chunks > MAX_CHUNKS or pos + 12 > len(data):
            fail()
        length = struct.unpack_from('>I', data, pos)[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if (end > len(data) or not re.fullmatch(b'[A-Za-z]{4}', kind)
                or not 65 <= kind[2] <= 90):
            fail()
        payload = data[pos + 8:pos + 8 + length]
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff
        if crc != struct.unpack_from('>I', data, pos + 8 + length)[0]:
            fail()
        if chunks == 1 and kind != b'IHDR':
            fail()
        if kind == b'IHDR':
            if ihdr is not None or chunks != 1 or length != 13:
                fail()
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (not 0 < width <= MAX_SIDE or not 0 < height <= MAX_SIDE
                    or width * height > MAX_PIXELS or depth != 8 or color not in (2, 6)
                    or (compression, filtering, interlace) != (0, 0, 0)):
                fail()
            ihdr = width, height, 3 if color == 2 else 4
        elif kind == b'IDAT':
            if ihdr is None or idat_state == 2:
                fail()
            idat_state = 1
            compressed.extend(payload)
        elif kind == b'IEND':
            if length != 0 or idat_state == 0 or not compressed or end != len(data):
                fail()
            ended = True
        elif kind in IGNORED:
            if idat_state == 1:
                idat_state = 2
        else:
            fail()
        pos = end
    if not ended or ihdr is None:
        fail()
    width, height, channels = ihdr
    stride = width * channels
    expected = height * (stride + 1)
    if expected > MAX_FILTERED or width * height * 4 > MAX_RGBA:
        fail()
    guard()
    try:
        decoder = zlib.decompressobj()
        filtered = decoder.decompress(compressed, expected + 1)
        if (len(filtered) != expected or not decoder.eof
                or decoder.unused_data or decoder.unconsumed_tail):
            fail()
    except zlib.error:
        fail()
    guard()
    rgba = bytearray(width * height * 4)
    previous = bytearray(stride)
    for y in range(height):
        if y % 32 == 0:
            guard()
        start = y * (stride + 1)
        method = filtered[start]
        if method > 4:
            fail()
        row = bytearray(filtered[start + 1:start + 1 + stride])
        if method:
            for x in range(stride):
                left = row[x - channels] if x >= channels else 0
                above = previous[x]
                corner = previous[x - channels] if x >= channels else 0
                predictor = (left if method == 1 else above if method == 2 else
                             (left + above) // 2 if method == 3 else _paeth(left, above, corner))
                row[x] = (row[x] + predictor) & 255
        base = y * width * 4
        if channels == 4:
            rgba[base:base + stride] = row
        else:
            for x in range(width):
                target, source = base + x * 4, x * 3
                rgba[target:target + 3] = row[source:source + 3]
                rgba[target + 3] = 255
        previous = row
    guard()
    return Raster(width, height, bytes(rgba))
