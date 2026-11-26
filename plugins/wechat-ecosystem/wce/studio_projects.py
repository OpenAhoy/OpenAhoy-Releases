"""Project-local Studio sessions and pinned local media."""
from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
import json
import math
import os
import stat
import re
import subprocess
from urllib.parse import quote
from zlib import compress

from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .project_context import exact_path
from .studio_apple_music import tool
from .studio_rates import layout

CATALOG = 'JiuseraAssets/Audio/Studio/catalog.json'
ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,95}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
AUDIO_TYPES = {'.wav': 'audio/wav', '.flac': 'audio/flac', '.mp3': 'audio/mpeg',
               '.m4a': 'audio/mp4', '.aiff': 'audio/aiff', '.aif': 'audio/aiff'}
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
CHUNK = 384 * 1024
SOURCE_CHUNK = 768 * 1024


class StudioError(WCEError):
    def __init__(self, code, status=422):
        super().__init__(code)
        self.status = status


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                             sort_keys=True, allow_nan=False).encode()).hexdigest()


def read_json(path, fallback=None):
    if not path.exists() and not path.is_symlink():
        return fallback
    file = FileSource(path.parent)
    return json.loads(file.read(path.name))


def require(condition, code='invalid_studio_request', status=400):
    if not condition:
        raise StudioError(code, status)


def valid_id(value):
    return type(value) is str and ID.fullmatch(value) is not None


def media_file(root, relative, types=AUDIO_TYPES):
    require(type(relative) is str and relative.startswith('JiuseraAssets/Audio/')
            and all(part not in ('', '.', '..') for part in relative.split('/'))
            and ':' not in relative and '\0' not in relative, 'studio_media_invalid')
    path = exact_path(str(root / relative))
    require(path.suffix.lower() in types, 'studio_media_invalid')
    return path


@lru_cache(maxsize=512)
def pinned_digest(root, relative, pin):
    data = FileSource(root).iter_html(relative, expected_state=pin)
    value = sha256()
    for block in data:
        value.update(block)
    return value.hexdigest()


def media_pin(root, relative, wanted, types=AUDIO_TYPES):
    path = media_file(root, relative, types)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
            'studio_media_invalid')
    pin = file_state(info)
    require(type(wanted) is str and SHA.fullmatch(wanted)
            and pinned_digest(root, relative, pin) == wanted, 'studio_media_changed', 409)
    return path, pin


def chunk(root, relative, wanted, offset, types=AUDIO_TYPES, *, coding=None):
    path, pin = media_pin(root, relative, wanted, types)
    size = pin[2]
    require(type(offset) is int and 0 <= offset < size, 'studio_media_offset')
    limit = SOURCE_CHUNK if coding is not None else CHUNK
    raw = b''.join(FileSource(root).iter_html(relative, expected_state=pin, offset=offset,
                                             length=min(limit, size - offset)))
    result = {'offset': offset, 'total': size, 'sha256': wanted, 'mime': types[path.suffix.lower()]}
    if coding is not None:
        result.update(size=len(raw), coding='identity')
        if coding == 'deflate' and path.suffix.lower() == '.wav':
            packed = compress(raw, 1)
            if len(packed) < .95 * len(raw):
                raw = packed
                result['coding'] = 'deflate'
    return result | {'bytes': b64encode(raw).decode('ascii')}


def cover_media(root, cover):
    if type(cover) is not dict or type(cover.get('sha256')) is not str or not SHA.fullmatch(cover['sha256']):
        return None
    try:
        path = media_file(root, cover.get('file'), IMAGE_TYPES)
        if 0 < path.stat().st_size <= 4 * 1024 * 1024:
            return {'file': str(path.relative_to(root)), 'sha256': cover['sha256']}
    except (OSError, WCEError):
        pass
    return None


@lru_cache(maxsize=3)
def wave_audition(root, relative, pin, duration):
    """Build a temporary stereo AAC audition without changing the track."""
    folders = relative.split('/')
    with FileSource(root).open_directory(folders[:-1]) as directory:
        fd = os.open(folders[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            require(file_state(os.fstat(fd)) == pin, 'studio_media_changed', 409)
            encoded = subprocess.run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-protocol_whitelist', 'pipe', '-f', 'wav', '-i', 'pipe:0', '-map', '0:a:0',
                '-t', str(duration), '-ac', '2', '-ar', '48000', '-c:a', 'aac', '-b:a', '128k',
                '-movflags', 'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', 'pipe:1'],
                stdin=fd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=45, check=True).stdout
            require(file_state(os.fstat(fd)) == pin, 'studio_media_changed', 409)
        finally:
            os.close(fd)
    require(8 < len(encoded) <= 24 * 1024 * 1024 and encoded[4:8] == b'ftyp', 'studio_preview_invalid', 422)
    return encoded, sha256(encoded).hexdigest()


def preview_chunk(root, track, offset):
    path, pin = media_pin(root, track['file'], track['sha256'])
    require(path.suffix.lower() == '.wav', 'studio_media_invalid', 404)
    raw, checksum = wave_audition(root, track['file'], pin, track['duration'])
    require(type(offset) is int and 0 <= offset < len(raw), 'studio_media_offset')
    return {'offset': offset, 'total': len(raw), 'sha256': checksum, 'mime': 'audio/mp4',
            'bytes': b64encode(raw[offset:offset + CHUNK]).decode('ascii')}


def studio_directory(root, create=False):
    current = root
    require(root.is_dir(), "studio_project_unavailable", 404)
    for name in ('JiuseraAssets', 'Audio', 'Studio'):
        current = exact_path(str(current / name))
        if create:
            current.mkdir(mode=0o700, exist_ok=True)
        require(current.is_dir(), 'studio_project_unavailable', 404)
    path_check(current, True)
    return current


def normalize_catalog(root, project_id, contents, *, include_recent=False):
    require(type(contents) is dict and contents.get('schema') == 1, 'studio_catalog_invalid')
    songs = contents.get('songs')
    require(type(songs) is list and len(songs) <= 500, 'studio_catalog_invalid')
    identifiers = set()
    result = []
    for song in songs:
        require(type(song) is dict and valid_id(song.get('id')) and song['id'] not in identifiers
                and type(song.get('name')) is str and 0 < len(song['name']) <= 240,
                'studio_catalog_invalid')
        identifiers.add(song['id'])
        versions = song.get('versions')
        require(type(versions) is list and 0 < len(versions) <= 64, 'studio_catalog_invalid')
        takes = []
        used = set()
        for version in versions:
            require(type(version) is dict and valid_id(version.get('id')) and version['id'] not in used
                    and not version['id'].startswith('master-'), 'studio_catalog_invalid')
            used.add(version['id'])
            version_id = version['id']
            track_list = version.get('tracks')
            require(type(track_list) is list and 0 < len(track_list) <= 128, 'studio_catalog_invalid')
            track_ids = set()
            tracks = []
            for source in track_list:
                require(type(source) is dict and valid_id(source.get('id')) and source['id'] not in track_ids
                        and type(source.get('name')) is str and 0 < len(source['name']) <= 240,
                        'studio_catalog_invalid')
                track_ids.add(source['id'])
                timings = {field: source.get(field, 0) for field in ('start', 'sourceIn', 'duration')}
                require(all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1200
                            for value in timings.values()) and timings['duration'] > 0
                        and timings['start'] + timings['duration'] <= 1200, 'studio_catalog_invalid')
                path = media_file(root, source.get('file'))
                checksum = source.get('sha256')
                require(type(checksum) is str and SHA.fullmatch(checksum), 'studio_catalog_invalid')
                target = '/source/' + '/'.join(map(quote, (project_id, song['id'], version_id, source['id'])))
                tracks.append({'id': source['id'], 'name': source['name'], **timings,
                               'file': str(path.relative_to(root)), 'sha256': checksum, 'url': target})
            offsets = {t['url']: root / t['file'] for t in tracks}
            minimum = math.ceil(max(t['start'] + t['duration'] for t in tracks))
            limit = version.get('timelineLimit', max(180, minimum))
            require(type(limit) is int and minimum <= limit <= 1200, 'studio_catalog_invalid')
            name = version.get('name', version_id)
            lyrics = version.get('lyrics', '')
            require(type(name) is str and 0 < len(name) <= 240 and type(lyrics) is str
                    and len(lyrics) <= 32768, 'studio_catalog_invalid')
            take = {'id': version_id, 'name': name, 'tracks': tracks, 'lyrics': lyrics,
                    'timelineLimit': limit, 'localImport': True,
                    'masterRate': layout(contents, song, version | {'tracks': tracks}, offsets.get)}
            if 'provider' in version:
                provider = version['provider']
                require(provider in ('suno', 'ace-music') and valid_id(version.get('providerClip')),
                        'studio_catalog_invalid')
                take.update(provider=provider, source={'suno': 'Suno', 'ace-music': 'ACE'}[provider],
                            providerClip=version['providerClip'])
                for key in ('productionRequest', 'sourceVersion', 'stemGroup'):
                    if key in version:
                        require(valid_id(version[key]), 'studio_catalog_invalid')
                        take[key] = version[key]
                if 'stemState' in version:
                    require(version['stemState'] in ('ready', 'partial'), 'studio_catalog_invalid')
                    take['stemState'] = version['stemState']
            cover = cover_media(root, version.get('cover', song.get('cover')))
            if cover:
                take['cover'] = '/cover/' + '/'.join(map(quote, (project_id, song['id'], version_id)))
                take['coverMedia'] = cover
            if include_recent and len(tracks) == 1 and not tracks[0]['start'] and not tracks[0]['sourceIn']:
                dates = {key: version[key] for key in ('generatedAt', 'archivedAt')
                         if type(version.get(key)) in (int, float) and math.isfinite(version[key]) and version[key] > 0}
                if dates:
                    try:
                        info = (root / tracks[0]['file']).lstat()
                        if (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                                and info.st_nlink == 1 and info.st_size > 0):
                            take.update(dates)
                    except OSError:
                        pass  # Media can disappear after the catalog was written.
            takes.append(take)
        adopted = song.get('adopted', takes[0]['id'])
        require(adopted in used, 'studio_catalog_invalid')
        item = {'id': song['id'], 'name': song['name'], 'versions': takes, 'adopted': adopted}
        bpm, meter = song.get('bpm'), song.get('meter')
        if type(bpm) in (int, float) and 20 <= bpm <= 400:
            item['bpm'] = bpm
        if (type(meter) is dict and type(meter.get('beats')) is int and 1 <= meter['beats'] <= 32
                and type(meter.get('note')) is int and meter['note'] in (1, 2, 4, 8, 16, 32)):
            item['meter'] = {'beats': meter['beats'], 'note': meter['note']}
        for name, limit in (('reference', 64), ('category', 64), ('credits', 280), ('note', 1200)):
            if type(song.get(name)) is str and 0 < len(song[name].strip()) <= limit:
                item[name] = song[name]
        updated = song.get('updatedAt')
        if type(updated) in (int, float) and math.isfinite(updated) and updated > 0:
            item['updatedAt'] = updated
        result.append(item)
    return result
