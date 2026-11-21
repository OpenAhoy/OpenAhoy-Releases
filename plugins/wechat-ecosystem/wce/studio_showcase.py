"""Read the immutable offline showcase shipped with the current plugin."""

from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re

from .bounded_file import FileSource, file_state
from .contracts import WCEError

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'studio-showcase'
MEDIA_ID = {'type': 'string', 'pattern': r'^[a-z0-9-]{1,40}$'}
CHUNK_SIZE = 180 * 1024
MIME = {
    'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
    'video/mp4': '.mp4', 'audio/wav': '.wav',
}


@lru_cache(maxsize=1)
def _index():
    try:
        data = json.loads(FileSource(ROOT).read('manifest.json'))
        if data['schema'] != 1 or not data['media'] or len(data['articles']) != 2:
            raise ValueError
        for key, row in data['media'].items():
            if (not re.fullmatch(MEDIA_ID['pattern'], key)
                    or not re.fullmatch(r'[a-z0-9-]+\.[a-z0-9]{2,4}', row['file'])
                    or Path(row['file']).suffix != MIME[row['mime']]
                    or not re.fullmatch(r'[0-9a-f]{64}', row['sha256'])
                    or type(row['bytes']) is not int or not 0 < row['bytes'] <= 5 * 1024 * 1024):
                raise ValueError
        return data
    except (OSError, ValueError, KeyError, TypeError, WCEError):
        raise WCEError('STUDIO_SHOWCASE_UNAVAILABLE') from None


def index():
    data = _index()
    return {
        'schema': data['schema'],
        'articles': data['articles'],
        'media': {key: {name: value for name, value in row.items() if name != 'file'}
                  for key, row in data['media'].items()},
    }


@lru_cache(maxsize=16)
def _read_asset(media_id):
    meta = _index()['media'][media_id]
    try:
        observed = (ROOT / meta['file']).lstat()
        if observed.st_size != meta['bytes']:
            raise WCEError('STUDIO_SHOWCASE_MEDIA_CHANGED')
        content = b''.join(FileSource(ROOT).iter_html(
            meta['file'], expected_state=file_state(observed), length=meta['bytes']))
    except (OSError, WCEError):
        raise WCEError('STUDIO_SHOWCASE_UNAVAILABLE') from None
    if len(content) != meta['bytes'] or sha256(content).hexdigest() != meta['sha256']:
        raise WCEError('STUDIO_SHOWCASE_MEDIA_CHANGED')
    return content


def chunk(media_id, offset):
    meta = _index()['media'].get(media_id)
    if meta is None or not 0 <= offset < meta['bytes']:
        raise WCEError('STUDIO_SHOWCASE_MEDIA_NOT_FOUND')
    part = _read_asset(media_id)[offset:offset + CHUNK_SIZE]
    return {
        'media_id': media_id, 'mime': meta['mime'], 'total': meta['bytes'], 'sha256': meta['sha256'],
        'offset': offset, 'next': offset + len(part), 'data': b64encode(part).decode('ascii'),
    }
