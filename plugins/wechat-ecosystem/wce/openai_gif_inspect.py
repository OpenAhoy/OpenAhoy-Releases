"""Use macOS ImageIO to verify the actual decoded animation without dependencies."""
from contextlib import contextmanager
import ctypes as c
from functools import lru_cache
from hashlib import sha256
import struct

from .contracts import WCEError


class Rect(c.Structure):
    _fields_ = [(field, c.c_double) for field in ('x', 'y', 'width', 'height')]


@lru_cache(maxsize=1)
def image_io():
    ptr, size = c.c_void_p, c.c_size_t
    cf, io, cg = [c.CDLL(f'/System/Library/Frameworks/{name}.framework/{name}')
                  for name in ('CoreFoundation', 'ImageIO', 'CoreGraphics')]
    for lib, name, result, args in (
        (cf, 'CFDataCreate', ptr, (ptr, c.c_char_p, c.c_long)),
        (cf, 'CFRelease', None, (ptr,)),
        (io, 'CGImageSourceCreateWithData', ptr, (ptr, ptr)),
        (io, 'CGImageSourceGetCount', size, (ptr,)),
        (io, 'CGImageSourceGetStatus', c.c_int, (ptr,)),
        (io, 'CGImageSourceGetStatusAtIndex', c.c_int, (ptr, size)),
        (io, 'CGImageSourceCreateImageAtIndex', ptr, (ptr, size, ptr)),
        (cg, 'CGImageGetWidth', size, (ptr,)), (cg, 'CGImageGetHeight', size, (ptr,)),
        (cg, 'CGColorSpaceCreateDeviceRGB', ptr, ()),
        (cg, 'CGBitmapContextCreate', ptr, (ptr, size, size, size, size, ptr, c.c_uint32)),
        (cg, 'CGContextDrawImage', None, (ptr, Rect, ptr)),
    ):
        method = getattr(lib, name)
        method.restype, method.argtypes = result, args
    return cf, io, cg


@contextmanager
def release(cf, value):
    if not value:
        raise ValueError('ImageIO could not decode image')
    try:
        yield value
    finally:
        cf.CFRelease(value)


@contextmanager
def image_source(raw):
    cf, io, cg = image_io()
    with release(cf, cf.CFDataCreate(None, raw, len(raw))) as data:
        with release(cf, io.CGImageSourceCreateWithData(data, None)) as source:
            yield cf, io, cg, source


def reference_mime(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
        if b'acTL' in raw:  # ImageIO versions differ in whether they enumerate APNG.
            cursor = 8
            while cursor + 12 <= len(raw):
                size = int.from_bytes(raw[cursor:cursor + 4], 'big')
                if raw[cursor + 4:cursor + 8] == b'acTL':
                    raise WCEError('GIF_SOURCE_INVALID')
                cursor += size + 12
    elif raw.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        mime = 'image/webp'
        if raw[12:16] == b'VP8X' and len(raw) > 20 and raw[20] & 2:
            raise WCEError('GIF_SOURCE_INVALID')
    else:
        raise WCEError('GIF_SOURCE_INVALID')
    try:
        with image_source(raw) as (cf, io, cg, source):
            if io.CGImageSourceGetCount(source) != 1 or io.CGImageSourceGetStatus(source) != 0:
                raise ValueError()
            with release(cf, io.CGImageSourceCreateImageAtIndex(source, 0, None)):
                if io.CGImageSourceGetStatusAtIndex(source, 0) != 0:
                    raise ValueError()
    except (OSError, ValueError):
        raise WCEError('GIF_SOURCE_INVALID') from None
    return mime


def gif_facts(raw):
    try:
        if len(raw) < 14 or raw[:6] not in (b'GIF87a', b'GIF89a') or not raw.endswith(b';'):
            raise ValueError()
        canvas_width, canvas_height = struct.unpack_from('<HH', raw, 6)
        if not (0 < canvas_width <= 4096 and 0 < canvas_height <= 4096):
            raise ValueError()
        with image_source(raw) as (cf, io, cg, source):
            frames = io.CGImageSourceGetCount(source)
            if not 2 <= frames <= 16 or io.CGImageSourceGetStatus(source) != 0:
                raise ValueError()
            pixels = set()
            with release(cf, cg.CGColorSpaceCreateDeviceRGB()) as color:
                for index in range(frames):
                    with release(cf, io.CGImageSourceCreateImageAtIndex(source, index, None)) as image:
                        width, height = cg.CGImageGetWidth(image), cg.CGImageGetHeight(image)
                        if (not (0 < width <= canvas_width and 0 < height <= canvas_height)
                                or io.CGImageSourceGetStatusAtIndex(source, index) != 0):
                            raise ValueError()
                        # Normalize the decoded pixels, so palette or compressed-data changes alone
                        # cannot make identical frames count as movement.
                        bitmap = (c.c_ubyte * (4 * width * height))()
                        with release(cf, cg.CGBitmapContextCreate(bitmap, width, height, 8, width * 4, color, 1)) as ctx:
                            cg.CGContextDrawImage(ctx, Rect(0, 0, width, height), image)
                        pixels.add((width, height, sha256(bitmap).digest()))
            if len(pixels) < 2:
                raise ValueError()
        return {'width': canvas_width, 'height': canvas_height, 'frames': frames}
    except (OSError, ValueError, struct.error):
        raise WCEError('GIF_RESULT_INVALID') from None
